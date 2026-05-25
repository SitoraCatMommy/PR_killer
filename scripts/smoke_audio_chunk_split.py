#!/usr/bin/env python3
"""Smoke test: ffmpeg opus segments stay under TRANSCRIPTION_MAX_SEGMENT_BYTES (no API keys)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

# Allow running from repo root without PYTHONPATH=.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ria:ria@localhost:5432/research_intel")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql+psycopg://ria:ria@localhost:5432/research_intel")
os.environ.setdefault("UPLOAD_STORAGE_PATH", str(_REPO / ".smoke_uploads"))

from app.infrastructure.settings import Settings
from app.services.audio_segment_split_service import split_audio_into_segment_files


def _sine_wav(path: Path, seconds: int = 90) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={seconds}",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(path),
    ]
    subprocess.run(cmd, check=True, timeout=120)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ria-smoke-"))
    wav = tmp / "tone.wav"
    print("Step 1: generate synthetic stereo WAV (~90 s, s16le)…")
    _sine_wav(wav, seconds=90)
    print(f"  created {wav} size={wav.stat().st_size} bytes")

    # Force many small segments without touching global env file.
    st = Settings(
        UPLOAD_STORAGE_PATH=str(_REPO / ".smoke_uploads"),
        TRANSCRIPTION_MAX_SEGMENT_BYTES=4 * 1024 * 1024,
        AUDIO_TRANSCRIPTION_CHUNK_SECONDS=600.0,
        AUDIO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=2.0,
    )
    root = Path(st.upload_storage_path)
    root.mkdir(parents=True, exist_ok=True)

    pid = uuid4()
    aid = uuid4()
    print("Step 2: split with TRANSCRIPTION_MAX_SEGMENT_BYTES=4MiB (strict cap + mono opus)…")
    plan = split_audio_into_segment_files(
        settings=st,
        project_id=pid,
        source_audio_id=aid,
        input_path=wav,
        ffmpeg_timeout_per_slice=120,
    )
    print(f"  segments={len(plan)}")
    max_b = 0
    for idx, start_ms, end_ms, rel in plan:
        p = root / rel
        sz = p.stat().st_size if p.is_file() else 0
        max_b = max(max_b, sz)
        print(f"  seg {idx}: {start_ms}-{end_ms} ms rel={rel} bytes={sz}")
        if sz > st.transcription_max_segment_bytes:
            print("FAIL: segment larger than cap", file=sys.stderr)
            return 2
    print(f"Step 3: OK — largest opus slice = {max_b} bytes (cap {st.transcription_max_segment_bytes})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
