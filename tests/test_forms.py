from app.security import hash_token
from tests.conftest import create_endpoint, create_verified_endpoint


def test_form_page_served_for_verified_endpoint(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.get(payload["public_url"])
    assert response.status_code == 200
    assert "<form" in response.text
    assert payload["public_url"] in response.text


def test_form_page_404_for_unknown_token(client):
    assert client.get("/f/does-not-exist").status_code == 404


def test_submit_relays_email(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={
            "name": "Ada",
            "email": "ada@example.org",
            "subject": "Hello",
            "message": "It works",
            "company": "Analytical Engines Ltd",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    relay = fake_mailer.sent[-1]
    assert relay["to"] == "owner@example.com"
    assert relay["reply_to"] == "ada@example.org"
    assert "Hello" in relay["subject"]
    assert "It works" in relay["html"]
    assert "Analytical Engines Ltd" in relay["html"]
    assert "example.com" in relay["html"]


def test_submit_json_body(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        json={"name": "Grace", "email": "grace@example.org", "message": "via JSON"},
    )
    assert response.status_code == 200
    assert "via JSON" in fake_mailer.sent[-1]["html"]


def test_submit_honors_redirect_field(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={
            "name": "Alan",
            "email": "alan@example.org",
            "message": "redirect me",
            "_redirect": "https://example.com/thanks",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "https://example.com/thanks"


def test_submit_to_unverified_endpoint_is_403(client, fake_mailer):
    payload = create_endpoint(client)
    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 403
    # Only the verification email was sent, no relay.
    assert len(fake_mailer.sent) == 1


def test_submit_records_failed_forward_and_returns_502(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    fake_mailer.fail = True
    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 502

    endpoint = store.get_by_manage_token(
        hash_token(payload["manage_url"].rsplit("/", 1)[-1])
    )
    submissions = store.list_submissions(endpoint.id)
    assert len(submissions) == 1
    assert submissions[0].forward_status == "failed"
    assert submissions[0].forwarded_at is None


def test_submit_rate_limited_per_ip(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    for _ in range(30):
        assert client.post(
            payload["public_url"],
            data={"name": "A", "email": "a@b.co", "message": "hi"},
        ).status_code == 200
    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 429


def test_submit_backoff_grows_exponentially(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    for _ in range(30):
        client.post(
            payload["public_url"],
            data={"name": "A", "email": "a@b.co", "message": "hi"},
        )
    retry_after = []
    for _ in range(3):
        response = client.post(
            payload["public_url"],
            data={"name": "A", "email": "a@b.co", "message": "hi"},
        )
        assert response.status_code == 429
        retry_after.append(int(response.headers["retry-after"]))
    assert retry_after == [1, 2, 4]


def test_submit_with_matching_origin_header_allowed(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200


def test_submit_with_subdomain_origin_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": "https://app.example.com"},
    )
    assert response.status_code == 403


def test_submit_with_registered_subdomain_allowed(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer, origin="app.example.com")
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": "https://app.example.com"},
    )
    assert response.status_code == 200


def test_submit_with_mismatched_origin_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": "https://evil.example.net"},
    )
    assert response.status_code == 403
    assert len(fake_mailer.sent) == 1  # verification email only, nothing relayed


def test_submit_with_lookalike_domain_rejected(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": "https://evil-example.com"},
    )
    assert response.status_code == 403


def test_submit_with_matching_referer_allowed(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Referer": "https://example.com/contact"},
    )
    assert response.status_code == 200


def test_submit_without_origin_headers_allowed(client, fake_mailer):
    # Non-browser clients (curl, server-to-server) send no Origin/Referer.
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"name": "A", "email": "a@b.co", "message": "hi"},
        headers={"Origin": ""},
    )
    assert response.status_code == 200


def test_submit_rejects_oversized_body(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(payload["public_url"], json={"message": "x" * 70_000})
    assert response.status_code == 413


def test_submit_rejects_overlong_message(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(payload["public_url"], json={"message": "x" * 20_001})
    assert response.status_code == 422


def test_submit_rejects_too_many_extra_fields(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    body = {"message": "hi", **{f"field{i}": "x" for i in range(25)}}
    response = client.post(payload["public_url"], json=body)
    assert response.status_code == 422


def _stored_submission(store, payload):
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    endpoint = store.get_by_public_token(hash_token(public_token))
    return store.list_submissions(endpoint.id)[0]


def test_submit_coerces_scalars_and_drops_nested_json(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        json={"message": "hi", "meta": {"nested": 1}, "count": 42},
    )
    assert response.status_code == 200
    assert _stored_submission(store, payload).extra_fields == {"count": "42"}


def test_submit_multipart_drops_file_uploads(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    response = client.post(
        payload["public_url"],
        data={"message": "hi"},
        files={"attachment": ("a.txt", b"hi")},
    )
    assert response.status_code == 200
    assert _stored_submission(store, payload).extra_fields == {}
