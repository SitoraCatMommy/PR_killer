"""Local ASR via the `whisper` CLI (openai-whisper package). Requires audio on disk."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

from app.infrastructure.settings import Settings
from app.services.transcription.data import StructuredTranscriptionResult, TranscriptSegmentData

logger = logging.getLogger(__name__)


def _whisper_cli_sync(
    audio_file_path: Path,
    settings: Settings,
) -> StructuredTranscriptionResult:
    exe = settings.whisper_local_command
    resolved = shutil.which(exe)
    if resolved is None:
        raise RuntimeError(
            f"whisper_local: command {exe!r} not found on PATH. Install Whisper "
            "(e.g. `pip install openai-whisper`) or set WHISPER_LOCAL_COMMAND."
        )
    with tempfile.TemporaryDirectory(prefix="ria_whisper_") as td:
        td_path = Path(td)
        cmd = [
            resolved,
            str(audio_file_path),
            "--model",
            settings.whisper_local_model,
            "--output_dir",
            str(td_path),
            "--output_format",
            "json",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=float(settings.whisper_local_timeout_seconds),
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            logger.error("whisper_local: whisper failed rc=%s stderr=%s", proc.returncode, err[:2000])
            raise RuntimeError(
                f"whisper_local: whisper exited with code {proc.returncode}: {err[:500]}"
            )
        stem = audio_file_path.stem
        json_path = td_path / f"{stem}.json"
        if not json_path.is_file():
            raise RuntimeError(f"whisper_local: expected JSON output at {json_path} not found")
        data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("whisper_local: invalid JSON from whisper")

    text = str(data.get("text") or "").strip()
    segments_out: list[TranscriptSegmentData] = []
    for row in data.get("segments") or []:
        if not isinstance(row, dict):
            continue
        seg_text = str(row.get("text") or "").strip()
        if not seg_text:
            continue
        try:
            start_d = Decimal(str(float(row.get("start", 0))))
        except (TypeError, ValueError):
            start_d = Decimal("0")
        try:
            end_d = Decimal(str(float(row.get("end", 0))))
        except (TypeError, ValueError):
            end_d = start_d + Decimal("1")
        segments_out.append(
            TranscriptSegmentData(
                speaker_label=None,
                start_seconds=start_d,
                end_seconds=end_d,
                text=seg_text,
                confidence_score=None,
            )
        )
    if not segments_out and text:
        segments_out.append(
            TranscriptSegmentData(None, Decimal("0.000"), Decimal("1.000"), text, None)
        )
    full_text = text or " ".join(s.text for s in segments_out)
    lang = data.get("language") if isinstance(data.get("language"), str) else None
    label = f"whisper_local:{settings.whisper_local_model}"
    return StructuredTranscriptionResult(
        full_text=full_text,
        language=lang,
        segments=segments_out,
        provider_name=label,
    )


class WhisperLocalTranscriptionProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe_structured(
        self,
        *,
        audio_bytes: bytes,
        mime_type: str | None,
        language_hint: str | None,
        audio_file_path: Path | None,
        filename_hint: str | None,
    ) -> StructuredTranscriptionResult:
        if audio_file_path is None or not audio_file_path.is_file():
            raise ValueError(
                "whisper_local requires audio_file_path pointing to an existing file "
                "(worker must read from upload storage)"
            )
        return await asyncio.to_thread(_whisper_cli_sync, audio_file_path, self._settings)
