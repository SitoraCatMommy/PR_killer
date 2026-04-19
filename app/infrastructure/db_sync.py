"""Synchronous DB access for Celery workers (avoid asyncio in task bodies)."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.settings import get_settings

_sync_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_sync_engine():
    global _sync_engine, _SessionLocal
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = create_engine(
            str(settings.database_url_sync),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _SessionLocal = sessionmaker(bind=_sync_engine, autoflush=False, expire_on_commit=False)
    return _sync_engine


@contextmanager
def sync_session_scope() -> Generator[Session, None, None]:
    get_sync_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
