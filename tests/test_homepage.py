from tests.conftest import create_endpoint, create_verified_endpoint


def test_homepage_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'name="destination_email"' in response.text
    assert 'name="origin"' in response.text
    assert "/api/endpoints" in response.text
    assert 'href="/how-it-works"' in response.text
    assert "/static/style.css" in response.text


def test_how_it_works_page(client):
    response = client.get("/how-it-works")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "How it works" in response.text
    assert "permanent" in response.text.lower()
    assert "7 days" in response.text
    assert "410" in response.text


def test_manage_page_renders_pending_endpoint(client, fake_mailer):
    payload = create_endpoint(client)
    manage_token = payload["manage_page_url"].rsplit("/", 1)[-1]

    response = client.get(f"/manage/{manage_token}")
    assert response.status_code == 200
    assert "owner@example.com" in response.text
    assert "example.com" in response.text
    assert "Pending verification" in response.text
    assert "Resend verification email" in response.text


def test_manage_page_renders_active_endpoint(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    manage_token = payload["manage_page_url"].rsplit("/", 1)[-1]

    response = client.get(f"/manage/{manage_token}")
    assert response.status_code == 200
    assert "Active" in response.text
    assert "Extend 7 days" in response.text
    assert "days left" in response.text


def test_manage_page_unknown_token_is_404(client):
    response = client.get("/manage/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.text.lower()
