from datetime import timedelta

from app.models import utcnow
from app.security import hash_token
from tests.conftest import create_verified_endpoint


def _endpoint_for(store, payload):
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    return store.get_by_public_token(hash_token(public_token))


def test_expired_endpoint_rejects_submissions(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    endpoint = _endpoint_for(store, payload)
    endpoint.expires_at = utcnow() - timedelta(seconds=1)
    store.update_endpoint(endpoint)

    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 410
    assert client.get(payload["public_url"]).status_code == 410

    status = client.get(payload["manage_url"]).json()
    assert status["active"] is False
    assert status["days_remaining"] == 0.0


def test_extend_adds_seven_days(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    endpoint = _endpoint_for(store, payload)
    before = endpoint.expires_at

    response = client.post(f"{payload['manage_url']}/extend")
    assert response.status_code == 200
    delta = _endpoint_for(store, payload).expires_at - before
    assert timedelta(days=6, hours=23) < delta <= timedelta(days=7)


def test_extend_revives_expired_endpoint(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    endpoint = _endpoint_for(store, payload)
    endpoint.expires_at = utcnow() - timedelta(days=1)
    store.update_endpoint(endpoint)

    response = client.post(f"{payload['manage_url']}/extend")
    assert response.status_code == 200
    assert response.json()["active"] is True

    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 200


def test_extend_requires_verification(client, fake_mailer):
    from tests.conftest import create_endpoint

    payload = create_endpoint(client)
    response = client.post(f"{payload['manage_url']}/extend")
    assert response.status_code == 403


def test_permanent_endpoint_never_expires(client, fake_mailer, store):
    payload = create_verified_endpoint(client, fake_mailer)
    endpoint = _endpoint_for(store, payload)
    endpoint.is_permanent = True
    endpoint.expires_at = utcnow() - timedelta(days=30)
    store.update_endpoint(endpoint)

    response = client.post(
        payload["public_url"], data={"name": "A", "email": "a@b.co", "message": "hi"}
    )
    assert response.status_code == 200

    status = client.get(payload["manage_url"]).json()
    assert status["active"] is True
    assert status["permanent"] is True

    # Extend makes no sense for permanent endpoints.
    assert client.post(f"{payload['manage_url']}/extend").status_code == 409
