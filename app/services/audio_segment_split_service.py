"""Split large interview audio into time-bounded files via ffmpeg (disk-backed, worker-safe)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from app.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _run(cmd: list[str], *, timeout: int) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[:4000]
        raise RuntimeError(f"ffmpeg/ffprobe failed rc={proc.returncode}: {err}")


def probe_duration_seconds(media_path: Path, *, timeout: int = 120) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {(proc.stderr or '')[:800]}")
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError("ffprobe returned empty duration")
    return float(raw)


def _encode_opus_slice(
    *,
    input_path: Path,
    start_sec: float,
    dur_sec: float,
    abs_out: Path,
    ffmpeg_timeout: int,
) -> None:
    """Mono opus 48k — small payloads for OpenAI / Gemini per slice."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_sec:.6f}",
        "-i",
        str(input_path),
        "-t",
        f"{dur_sec:.6f}",
        "-vn",
        "-ac",
        "1",
        "-acodec",
        "libopus",
        "-b:a",
        "48k",
        str(abs_out),
    ]
    _run(cmd, timeout=ffmpeg_timeout)


def _build_segment_plan(
    *,
    settings: Settings,
    project_id: UUID,
    source_audio_id: UUID,
    input_path: Path,
    chunk_seconds: float,
    overlap_seconds: float,
    max_segment_bytes: int,
    ffmpeg_timeout_per_slice: int,
) -> list[tuple[int, int, int, str]]:
    """Single pass: fixed windows; each file must be non-empty."""
    chunk_ms = int(chunk_seconds * 1000)
    overlap_ms = int(overlap_seconds * 1000)
    if chunk_ms <= 0:
        raise ValueError("chunk_ms must be positive")

    root = Path(settings.upload_storage_path)
    rel_base = Path("research_sources") / str(project_id) / "audio_segments" / str(source_audio_id)
    out_dir = root / rel_base
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    duration_sec = probe_duration_seconds(input_path)
    total_ms = max(0, int(round(duration_sec * 1000)))
    if total_ms == 0:
        raise RuntimeError("audio_duration_zero")

    out: list[tuple[int, int, int, str]] = []
    pos_ms = 0
    idx = 0
    while pos_ms < total_ms:
        start_ms = max(0, pos_ms - overlap_ms) if pos_ms > 0 else 0
        raw_end = pos_ms + chunk_ms
        if raw_end < total_ms:
            raw_end += overlap_ms
        end_ms = min(total_ms, raw_end)
        if end_ms <= start_ms:
            break
        start_sec = start_ms / 1000.0
        dur_sec = max(0.01, (end_ms - start_ms) / 1000.0)
        seg_name = f"seg_{idx:04d}.opus"
        abs_seg = out_dir / seg_name
        rel_path = str(rel_base / seg_name).replace("\\", "/")
        _encode_opus_slice(
            input_path=input_path,
            start_sec=start_sec,
            dur_sec=dur_sec,
            abs_out=abs_seg,
            ffmpeg_timeout=ffmpeg_timeout_per_slice,
        )
        if not abs_seg.is_file() or abs_seg.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced empty segment idx={idx}")
        if abs_seg.stat().st_size > max_segment_bytes:
            raise RuntimeError(
                f"segment_file_too_large idx={idx} bytes={abs_seg.stat().st_size} "
                f"max={max_segment_bytes} — reduce AUDIO_TRANSCRIPTION_CHUNK_SECONDS or "
                "lower TRANSCRIPTION_MAX_SEGMENT_BYTES"
            )
        out.append((idx, start_ms, end_ms, rel_path))
        logger.info(
            "audio_segment_split idx=%s start_ms=%s end_ms=%s path=%s bytes=%s",
            idx,
            start_ms,
            end_ms,
            rel_path,
            abs_seg.stat().st_size,
        )
        idx += 1
        pos_ms += chunk_ms
    return out


def split_audio_into_segment_files(
    *,
    settings: Settings | None = None,
    project_id: UUID,
    source_audio_id: UUID,
    input_path: Path,
    chunk_seconds: float | None = None,
    overlap_seconds: float | None = None,
    ffmpeg_timeout_per_slice: int = 3600,
) -> list[tuple[int, int, int, str]]:
    """
    Cut ``input_path`` into overlapping windows on disk.

    Returns list of (segment_index, start_ms, end_ms, relative_storage_path).

    Slices are sized so each opus file stays under ``TRANSCRIPTION_MAX_SEGMENT_BYTES``
    (OpenAI 25 MB file limit; Gemini inline audio). If a pass still overshoots (rare),
    chunk length is halved and the split is retried.
    """
    st = settings or get_settings()
    overlap = float(overlap_seconds if overlap_seconds is not None else st.audio_transcription_chunk_overlap_seconds)
    max_bytes = int(st.transcription_max_segment_bytes)
    requested = float(chunk_seconds if chunk_seconds is not None else st.audio_transcription_chunk_seconds)
    effective_cap = float(st.effective_audio_transcription_chunk_seconds)
    chunk_sec = min(requested, effective_cap)
    chunk_sec = max(60.0, chunk_sec)

    last_err: Exception | None = None
    for attempt in range(12):
        try:
            plan = _build_segment_plan(
                settings=st,
                project_id=project_id,
                source_audio_id=source_audio_id,
                input_path=input_path,
                chunk_seconds=chunk_sec,
                overlap_seconds=overlap,
                max_segment_bytes=max_bytes,
                ffmpeg_timeout_per_slice=ffmpeg_timeout_per_slice,
            )
            return plan
        except RuntimeError as e:
            last_err = e
            if "segment_file_too_large" not in str(e):
                raise
            chunk_sec = max(60.0, chunk_sec / 2.0)
            logger.warning(
                "audio_segment_split_oversize_retry attempt=%s new_chunk_sec=%s err=%s",
                attempt + 1,
                chunk_sec,
                e,
            )
    raise RuntimeError(f"audio_segment_split: could not fit segments under {max_bytes} bytes") from last_err
