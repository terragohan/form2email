from datetime import timedelta

from app.models import utcnow
from app.security import hash_token
from tests.conftest import create_endpoint, create_verified_endpoint

SUBMISSION = {"name": "A", "email": "a@b.co", "message": "hi"}


def _expire(payload, store):
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    endpoint = store.get_by_public_token(hash_token(public_token))
    endpoint.expires_at = utcnow() - timedelta(seconds=1)
    store.update_endpoint(endpoint)


def test_preflight_from_registered_origin(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.options(
        payload["public_url"],
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["access-control-allow-methods"] == "POST, GET, OPTIONS"
    assert response.headers["access-control-allow-headers"] == "content-type"
    assert response.headers["access-control-max-age"] == "86400"
    assert response.headers["vary"] == "Origin"


def test_preflight_defaults_allow_headers_to_content_type(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.options(
        payload["public_url"], headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-headers"] == "Content-Type"


def test_preflight_from_foreign_origin_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.options(
        payload["public_url"], headers={"Origin": "https://evil.example.net"}
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_subdomain_origin_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.options(
        payload["public_url"], headers={"Origin": "https://app.example.com"}
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_unknown_token_is_404(client):
    response = client.options(
        "/f/does-not-exist", headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 404
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_unverified_endpoint_is_403(client, fake_mailer):
    payload = create_endpoint(client)
    response = client.options(
        payload["public_url"], headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_expired_endpoint_is_410(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    _expire(payload, store)
    response = client.options(
        payload["public_url"], headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 410
    assert "access-control-allow-origin" not in response.headers


def test_post_with_matching_origin_reflects_acao(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        json=SUBMISSION,
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["vary"] == "Origin"


def test_post_with_subdomain_origin_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        json=SUBMISSION,
        headers={"Origin": "https://app.example.com"},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_post_from_registered_subdomain_reflects_acao(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer, origin="app.example.com")
    response = client.post(
        payload["public_url"],
        json=SUBMISSION,
        headers={"Origin": "https://app.example.com"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def test_post_without_origin_has_no_cors_headers(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(payload["public_url"], json=SUBMISSION)
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_post_with_mismatched_origin_403_and_no_acao(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        json=SUBMISSION,
        headers={"Origin": "https://evil.example.net"},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_form_page_with_matching_origin_reflects_acao(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.get(
        payload["public_url"], headers={"Origin": "https://example.com"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
    assert response.headers["vary"] == "Origin"


def test_form_page_without_origin_has_no_cors_headers(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.get(payload["public_url"])
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
