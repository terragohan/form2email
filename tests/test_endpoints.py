from app.config import Settings, get_settings
from app.main import app
from tests.conftest import create_endpoint, create_verified_endpoint, verify_endpoint


def test_create_endpoint_returns_urls_and_sends_verification(client, fake_mailer):
    payload = create_endpoint(client)

    assert payload["verification"] == "pending"
    assert payload["destination_email"] == "owner@example.com"
    assert payload["origin"] == "example.com"
    assert payload["public_url"].startswith("http://testserver/f/")
    assert payload["manage_url"].startswith("http://testserver/api/endpoints/")
    assert payload["manage_page_url"].startswith("http://testserver/manage/")
    assert len(fake_mailer.sent) == 1
    assert fake_mailer.sent[0]["to"] == "owner@example.com"
    assert "http://testserver/verify/" in fake_mailer.sent[0]["html"]
    assert "example.com" in fake_mailer.sent[0]["html"]
    # The email must also carry the URLs — raw tokens are unrecoverable later.
    assert payload["public_url"] in fake_mailer.sent[0]["html"]
    # The email links to the manage page, not the raw manage API URL.
    assert payload["manage_page_url"] in fake_mailer.sent[0]["html"]
    assert payload["manage_url"] not in fake_mailer.sent[0]["html"]


def test_origin_is_normalized_from_url(client):
    payload = create_endpoint(client, origin="https://Example.com")
    assert payload["origin"] == "example.com"


def test_origin_is_normalized_from_bare_domain_with_port(client):
    payload = create_endpoint(client, origin="Example.com:443")
    assert payload["origin"] == "example.com"


def test_create_endpoint_rejects_origin_with_path(client):
    response = client.post(
        "/api/endpoints",
        json={
            "destination_email": "owner@example.com",
            "origin": "https://example.com/some/page",
        },
    )
    assert response.status_code == 422


def test_create_endpoint_rejects_non_http_origin(client):
    response = client.post(
        "/api/endpoints",
        json={"destination_email": "owner@example.com", "origin": "ftp://example.com"},
    )
    assert response.status_code == 422


def test_origin_accepts_localhost(client):
    payload = create_endpoint(client, origin="http://localhost:3000")
    assert payload["origin"] == "localhost"


def test_create_endpoint_rejects_invalid_origin(client):
    response = client.post(
        "/api/endpoints",
        json={"destination_email": "owner@example.com", "origin": "not a domain!"},
    )
    assert response.status_code == 422


def test_create_endpoint_requires_origin(client):
    response = client.post(
        "/api/endpoints", json={"destination_email": "owner@example.com"}
    )
    assert response.status_code == 422


def test_create_endpoint_rejects_invalid_email(client):
    response = client.post("/api/endpoints", json={"destination_email": "not-an-email"})
    assert response.status_code == 422


def test_verify_activates_endpoint(client, fake_mailer, store):
    payload = create_endpoint(client)
    verify_endpoint(client, fake_mailer)

    status = client.get(payload["manage_url"]).json()
    assert status["origin"] == "example.com"
    assert status["verified"] is True
    assert status["active"] is True
    assert status["expires_at"] is not None
    assert 6.9 < status["days_remaining"] <= 7.0


def test_verification_link_is_single_use(client, fake_mailer):
    create_endpoint(client)
    verify_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]

    assert client.get(verify_url).status_code == 200
    assert client.get(verify_url).status_code == 404


def test_unknown_verification_token_is_404(client):
    assert client.get("/verify/does-not-exist").status_code == 404


def test_manage_url_requires_valid_token(client):
    assert client.get("/api/endpoints/nope").status_code == 404


def test_resend_verification_rotates_token(client, fake_mailer):
    payload = create_endpoint(client)
    first_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]

    response = client.post(f"{payload['manage_url']}/verification")
    assert response.status_code == 200
    second_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]
    assert second_url != first_url
    # Resend can't re-include the URLs — raw tokens are unrecoverable server-side.
    assert payload["public_url"] not in fake_mailer.sent[-1]["html"]

    # Old token is dead, new token verifies.
    assert client.get(first_url).status_code == 404
    assert client.get(second_url).status_code == 200


def test_resend_verification_after_verified_conflicts(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(f"{payload['manage_url']}/verification")
    assert response.status_code == 409


def test_create_rolls_back_when_verification_email_fails(client, fake_mailer, store):
    deleted_ids: list[str] = []
    real_delete = store.delete_endpoint

    def spy_delete(endpoint_id: str) -> None:
        deleted_ids.append(endpoint_id)
        real_delete(endpoint_id)

    store.delete_endpoint = spy_delete
    fake_mailer.fail = True
    response = client.post(
        "/api/endpoints",
        json={"destination_email": "owner@example.com", "origin": "example.com"},
    )
    assert response.status_code == 502
    assert len(deleted_ids) == 1  # the orphan endpoint was rolled back


def test_create_rate_limited_per_ip(client):
    body = {"destination_email": "owner@example.com", "origin": "example.com"}
    for _ in range(5):
        assert client.post("/api/endpoints", json=body).status_code == 201
    response = client.post("/api/endpoints", json=body)
    assert response.status_code == 429


def _cap_verification_emails(limit: int) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        base_url="http://testserver",
        rate_limit_verification_per_email_per_day=limit,
        rate_limit_create_per_hour=50,
    )


def test_verification_emails_capped_per_address(client):
    _cap_verification_emails(2)
    body = {"destination_email": "owner@example.com", "origin": "example.com"}
    assert client.post("/api/endpoints", json=body).status_code == 201
    assert client.post("/api/endpoints", json=body).status_code == 201
    assert client.post("/api/endpoints", json=body).status_code == 429
    # A different destination address has its own bucket.
    other = {"destination_email": "someone-else@example.com", "origin": "example.com"}
    assert client.post("/api/endpoints", json=other).status_code == 201


def test_resend_verification_shares_the_per_address_cap(client):
    _cap_verification_emails(1)
    payload = create_endpoint(client)  # sends the one allowed email
    response = client.post(f"{payload['manage_url']}/verification")
    assert response.status_code == 429
