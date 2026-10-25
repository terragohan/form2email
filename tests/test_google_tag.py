from app.config import Settings, get_settings
from app.main import app
from tests.conftest import create_endpoint


GTAG_ID = "G-E693TEST"
GTAG_SRC = f'src="https://www.googletagmanager.com/gtag/js?id={GTAG_ID}"'


def _configure_tag() -> None:
    def override_settings() -> Settings:
        return Settings(base_url="http://testserver", google_tag_id=GTAG_ID)

    app.dependency_overrides[get_settings] = override_settings


def test_google_tag_omitted_by_default(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "googletagmanager" not in response.text
    assert "dataLayer" not in response.text


def test_google_tag_on_homepage_and_guide(client):
    _configure_tag()
    try:
        homepage = client.get("/")
        guide = client.get("/guides/contact-form")
    finally:
        app.dependency_overrides.pop(get_settings)

    for response in (homepage, guide):
        assert response.status_code == 200
        assert GTAG_SRC in response.text
        assert f"gtag('config', '{GTAG_ID}')" in response.text


def test_google_tag_on_form_and_verified_pages(client, fake_mailer):
    payload = create_endpoint(client)
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    verify_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]

    _configure_tag()
    try:
        verified_page = client.get(verify_url)
        form_page = client.get(f"/f/{public_token}")
    finally:
        app.dependency_overrides.pop(get_settings)

    assert verified_page.status_code == 200
    assert GTAG_SRC in verified_page.text
    assert form_page.status_code == 200
    assert GTAG_SRC in form_page.text


def test_unknown_page_renders_branded_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "404" in response.text
