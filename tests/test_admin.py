import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.db import get_store
from app.mailer import get_mailer
from app.main import app
from app.models import utcnow
from app.ratelimit import limiter
from app.security import hash_token
from tests.conftest import create_verified_endpoint

ADMIN_TOKEN = "test-admin-token"


@pytest.fixture
def admin_client(store, fake_mailer):
    def override_store():
        yield store

    def override_settings() -> Settings:
        return Settings(
            base_url="http://testserver",
            default_ttl_days=7,
            verification_token_ttl_hours=24,
            rate_limit_create_per_hour=5,
            rate_limit_submit_per_minute=30,
            admin_token=ADMIN_TOKEN,
        )

    app.dependency_overrides[get_store] = override_store
    app.dependency_overrides[get_mailer] = lambda: fake_mailer
    app.dependency_overrides[get_settings] = override_settings
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _endpoint_id(store, payload) -> str:
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    return store.get_by_public_token(hash_token(public_token)).id


def _permanent_url(store, payload) -> str:
    return f"/api/admin/endpoints/{_endpoint_id(store, payload)}/permanent"


def test_admin_routes_hidden_from_openapi(admin_client):
    paths = admin_client.get("/openapi.json").json()["paths"]
    assert not any(path.startswith("/api/admin") for path in paths)


def test_admin_routes_404_when_token_unset(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    url = _permanent_url(store, payload)
    assert client.post(url, headers={"X-Admin-Token": "anything"}).status_code == 404
    assert client.delete(url, headers={"X-Admin-Token": "anything"}).status_code == 404


def test_admin_rejects_missing_or_wrong_token(admin_client, fake_mailer, store):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    url = _permanent_url(store, payload)
    assert admin_client.post(url).status_code == 403
    assert (
        admin_client.post(url, headers={"X-Admin-Token": "wrong"}).status_code == 403
    )
    assert admin_client.delete(url).status_code == 403


def test_make_permanent_sets_flag(admin_client, fake_mailer, store):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    endpoint = store.get_by_public_token(
        hash_token(payload["public_url"].rsplit("/", 1)[-1])
    )

    response = admin_client.post(
        _permanent_url(store, payload), headers={"X-Admin-Token": ADMIN_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["permanent"] is True

    endpoint = store.get_endpoint_by_id(endpoint.id)
    assert endpoint.is_permanent is True
    assert endpoint.permanent_at is not None

    status = admin_client.get(payload["manage_url"]).json()
    assert status["permanent"] is True
    assert status["active"] is True

    # Extend makes no sense for a permanent endpoint.
    assert admin_client.post(f"{payload['manage_url']}/extend").status_code == 409


def test_make_permanent_revives_expired_endpoint(admin_client, fake_mailer, store):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    endpoint = store.get_by_public_token(
        hash_token(payload["public_url"].rsplit("/", 1)[-1])
    )
    endpoint.expires_at = utcnow() - timedelta(days=1)
    store.update_endpoint(endpoint)
    assert (
        admin_client.post(
            payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
        ).status_code
        == 410
    )

    response = admin_client.post(
        _permanent_url(store, payload), headers={"X-Admin-Token": ADMIN_TOKEN}
    )
    assert response.status_code == 200
    assert response.json()["active"] is True

    assert (
        admin_client.post(
            payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
        ).status_code
        == 200
    )


def test_make_permanent_is_idempotent(admin_client, fake_mailer, store):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    url = _permanent_url(store, payload)
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    assert admin_client.post(url, headers=headers).status_code == 200
    first = store.get_endpoint_by_id(_endpoint_id(store, payload)).permanent_at
    assert first is not None

    assert admin_client.post(url, headers=headers).status_code == 200
    second = store.get_endpoint_by_id(_endpoint_id(store, payload)).permanent_at
    # A re-grant must not re-stamp permanent_at.
    assert second == first

    status = admin_client.get(payload["manage_url"]).json()
    assert status["permanent"] is True


def test_revoke_permanent_clears_flag_and_resets_expiry(
    admin_client, fake_mailer, store
):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    url = _permanent_url(store, payload)
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    assert admin_client.post(url, headers=headers).status_code == 200

    response = admin_client.delete(url, headers=headers)
    assert response.status_code == 200
    assert response.json()["permanent"] is False

    endpoint = store.get_endpoint_by_id(_endpoint_id(store, payload))
    assert endpoint.is_permanent is False
    assert endpoint.permanent_at is None
    # Revocation restarts the TTL from now so the endpoint doesn't instantly 410.
    remaining = (endpoint.expires_at - utcnow()).total_seconds() / 86400
    assert 6.9 < remaining <= 7.0

    status = admin_client.get(payload["manage_url"]).json()
    assert status["active"] is True
    assert status["permanent"] is False


def test_revoke_permanent_requires_permanent(admin_client, fake_mailer, store):
    payload = create_verified_endpoint(admin_client, fake_mailer)
    endpoint = store.get_endpoint_by_id(_endpoint_id(store, payload))
    expires_before = endpoint.expires_at

    response = admin_client.delete(
        _permanent_url(store, payload), headers={"X-Admin-Token": ADMIN_TOKEN}
    )
    assert response.status_code == 409

    # A temporary endpoint's expiry must be left untouched.
    endpoint = store.get_endpoint_by_id(_endpoint_id(store, payload))
    assert endpoint.is_permanent is False
    assert endpoint.expires_at == expires_before


def test_admin_unknown_endpoint_id_is_404(admin_client):
    url = f"/api/admin/endpoints/{uuid.uuid4()}/permanent"
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    assert admin_client.post(url, headers=headers).status_code == 404
    assert admin_client.delete(url, headers=headers).status_code == 404
