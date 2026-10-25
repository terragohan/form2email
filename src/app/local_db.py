from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_local_settings


class Base(DeclarativeBase):
    pass


_settings = get_local_settings()
_connect_args = (
    {"check_same_thread": False}
    if _settings.database_url.startswith("sqlite")
    else {}
)
engine = create_engine(_settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_local_store():
    from app.store.sqlalchemy_store import SqlAlchemyStore

    db = SessionLocal()
    try:
        yield SqlAlchemyStore(db)
    finally:
        db.close()
