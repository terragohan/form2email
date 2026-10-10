from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_uses_d1 = _settings.database_url.startswith("d1")

engine = None
SessionLocal = None
if not _uses_d1:
    _connect_args = (
        {"check_same_thread": False}
        if _settings.database_url.startswith("sqlite")
        else {}
    )
    engine = create_engine(_settings.database_url, connect_args=_connect_args)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )


_d1_store = None


def _get_d1_store():
    global _d1_store
    if _d1_store is None:
        from app.store.d1 import D1Store

        settings = get_settings()
        _d1_store = D1Store(
            account_id=settings.cloudflare_account_id,
            database_id=settings.cloudflare_d1_database_id,
            api_token=settings.cloudflare_api_token,
        )
    return _d1_store


def get_store():
    """FastAPI dependency yielding the active storage backend.

    DATABASE_URL=d1 selects Cloudflare D1 (Lambda); anything else is a
    SQLAlchemy URL (SQLite locally/on the droplet, Postgres-ready).
    """
    if get_settings().database_url.startswith("d1"):
        yield _get_d1_store()
        return
    from app.store.sqlalchemy_store import SqlAlchemyStore

    db = SessionLocal()
    try:
        yield SqlAlchemyStore(db)
    finally:
        db.close()
