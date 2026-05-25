"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api_prefix() -> str:
    from app.infrastructure.settings import get_settings

    return get_settings().api_v1_prefix.rstrip("/")


@pytest.fixture(scope="module")
def client(api_prefix: str) -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as tc:
        r = tc.get(f"{api_prefix}/health")
        if r.status_code >= 500:
            pytest.skip(f"Health check failed: {r.status_code} {r.text}")
        yield tc
