import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_store
from app.mailer import get_mailer
from app.main import app
from app.ratelimit import limiter
from app.store.sqlalchemy_store import SqlAlchemyStore


class FakeMailer:
    """Captures outbound mail instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail = False

    def send(self, *, to: str, subject: str, html: str, reply_to: str | None = None) -> None:
        if self.fail:
            raise RuntimeError("provider error")
        self.sent.append({"to": to, "subject": subject, "html": html, "reply_to": reply_to})


@pytest.fixture
def fake_mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def store():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    yield SqlAlchemyStore(session)
    session.close()
    engine.dispose()


@pytest.fixture
def client(store, fake_mailer):
    def override_store():
        yield store

    def override_settings() -> Settings:
        return Settings(
            base_url="http://testserver",
            default_ttl_days=7,
            verification_token_ttl_hours=24,
            rate_limit_create_per_hour=5,
            rate_limit_submit_per_minute=30,
            # Tests that exercise the per-address verification cap set their
            # own override; the default of 3/day would otherwise trip the
            # per-IP create test.
            rate_limit_verification_per_email_per_day=1000,
        )

    app.dependency_overrides[get_store] = override_store
    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    app.dependency_overrides[get_settings] = override_settings
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_endpoint(client, origin: str = "example.com") -> dict:
    response = client.post(
        "/api/endpoints",
        json={"destination_email": "owner@example.com", "origin": origin},
    )
    assert response.status_code == 201, response.text
    return response.json()


def verify_endpoint(client, fake_mailer) -> None:
    verify_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]
    response = client.get(verify_url)
    assert response.status_code == 200, response.text


def create_verified_endpoint(client, fake_mailer, origin: str = "example.com") -> dict:
    payload = create_endpoint(client, origin=origin)
    verify_endpoint(client, fake_mailer)
    return payload
