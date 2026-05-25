"""Shared HTTP timeout configuration for LLM / ASR clients under parallel Celery load."""

from __future__ import annotations

import httpx


def httpx_timeout_for_upstream_read(*, read_seconds: float, connect_seconds: float = 30.0) -> httpx.Timeout:
    """Prefer a generous read budget; connect stays bounded to fail fast on dead peers."""
    read_s = max(30.0, min(float(read_seconds), 7200.0))
    con = min(max(5.0, float(connect_seconds)), 120.0)
    write_cap = min(600.0, max(120.0, read_s * 0.25))
    return httpx.Timeout(connect=con, read=read_s, write=write_cap, pool=10.0)
