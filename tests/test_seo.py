import json
import re
import xml.etree.ElementTree as ET

from app.main import GUIDES, SITEMAP_PATHS
from tests.conftest import create_endpoint, create_verified_endpoint

PUBLIC_PATHS = ["/", "/how-it-works", "/for-coding-tools", "/guides"] + [
    f"/guides/{slug}" for slug in GUIDES
]


def _title(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()


def _description(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]+)"', html).group(1)


def _jsonld(html: str) -> dict:
    match = re.search(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S
    )
    assert match, "no JSON-LD block found"
    return json.loads(match.group(1))


def test_robots_txt(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "User-agent: *" in body
    for private in ("/api/", "/manage/", "/verify/", "/f/", "/healthz"):
        assert f"Disallow: {private}" in body
    # OAI-SearchBot (ChatGPT search) is explicitly permitted with the same
    # restrictions; GPTBot policy is untouched (wildcard only).
    assert "User-agent: OAI-SearchBot" in body
    assert "GPTBot" not in body
    assert "Sitemap: http://testserver/sitemap.xml" in body


def test_robots_txt_is_not_rate_limited(client):
    # Crawlers must never hit the meta routes' 3/minute shared bucket.
    for _ in range(5):
        assert client.get("/robots.txt").status_code == 200


def test_sitemap_xml(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.text)
    locs = [el.text for el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert locs == [f"http://testserver{path}" for path in SITEMAP_PATHS]
    assert len(locs) == 14
    # Only public, canonical pages — no token, API, or utility routes.
    for loc in locs:
        for excluded in ("/f/", "/manage/", "/verify/", "/api/", "healthz"):
            assert excluded not in loc


def test_sitemap_is_not_rate_limited(client):
    for _ in range(5):
        assert client.get("/sitemap.xml").status_code == 200


def test_homepage_seo(client):
    response = client.get("/")
    html = response.text
    assert response.status_code == 200
    assert _title(html) == "Form2Email — Free HTML Form to Email Service | No Backend"
    assert "no backend" in _description(html).lower()
    assert 'rel="canonical" href="http://testserver/"' in html
    assert 'property="og:title"' in html
    assert 'property="og:url" content="http://testserver/"' in html
    assert 'property="og:image" content="http://testserver/static/og-image.png"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert "noindex" not in html
    assert len(re.findall(r"<h1", html)) == 1

    data = _jsonld(html)
    assert data["@context"] == "https://schema.org"
    assert data["@type"] == "WebApplication"
    assert data["name"] == "Form2Email"
    assert data["url"] == "http://testserver/"
    assert data["offers"]["price"] == "0"
    assert "aggregateRating" not in data

    # Visible FAQ and crawlable links to every guide.
    assert 'id="faq"' in html
    assert "Frequently asked questions" in html
    for slug in GUIDES:
        assert f'href="/guides/{slug}"' in html


def test_public_pages_have_unique_metadata(client):
    titles, descriptions = {}, {}
    for path in PUBLIC_PATHS:
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.text
        assert len(re.findall(r"<h1", html)) == 1, path
        assert f'rel="canonical" href="http://testserver{path}"' in html, path
        assert "noindex" not in html, path
        titles[path] = _title(html)
        descriptions[path] = _description(html)
    assert len(set(titles.values())) == len(PUBLIC_PATHS), titles
    assert len(set(descriptions.values())) == len(PUBLIC_PATHS), descriptions


def test_guides_have_breadcrumb_jsonld_and_examples(client):
    for slug in GUIDES:
        response = client.get(f"/guides/{slug}")
        html = response.text
        assert response.status_code == 200, slug
        data = _jsonld(html)
        assert data["@type"] == "BreadcrumbList", slug
        items = data["itemListElement"]
        assert [i["position"] for i in items] == [1, 2, 3]
        assert items[-1]["item"] == f"http://testserver/guides/{slug}"
        # Every guide shows a working example wired to the real API.
        assert "&lt;form" in html, slug
        assert "/f/your-token" in html, slug
        assert "/api/endpoints" in html, slug
        # Internal linking: at least two sibling guides.
        sibling_links = re.findall(r'href="/guides/([a-z-]+)"', html)
        assert len(set(sibling_links) - {slug}) >= 2, slug


def test_manage_page_is_noindex(client, fake_mailer):
    payload = create_endpoint(client)
    manage_token = payload["manage_page_url"].rsplit("/", 1)[-1]
    response = client.get(f"/manage/{manage_token}")
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text
    assert 'rel="canonical"' not in response.text


def test_form_page_is_noindex(client, fake_mailer):
    payload = create_verified_endpoint(client, fake_mailer)
    public_token = payload["public_url"].rsplit("/", 1)[-1]
    response = client.get(f"/f/{public_token}")
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text


def test_verified_page_is_noindex(client, fake_mailer):
    create_endpoint(client)
    verify_url = fake_mailer.sent[-1]["html"].split('href="')[1].split('"')[0]
    response = client.get(verify_url)
    assert response.status_code == 200
    assert '<meta name="robots" content="noindex, nofollow">' in response.text


def test_unknown_page_renders_branded_html_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "page not found" in response.text
    assert "noindex" in response.text
    assert 'href="/"' in response.text


def test_unknown_guide_is_html_404(client):
    response = client.get("/guides/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")


def test_api_and_form_404s_stay_json(client):
    # Endpoint behavior is unchanged for API/form consumers.
    assert client.get("/api/does-not-exist").headers["content-type"].startswith(
        "application/json"
    )
    form = client.get("/f/does-not-exist")
    assert form.status_code == 404
    assert form.json() == {"detail": "Form not found"}


def test_internal_links_resolve(client):
    html = client.get("/").text + client.get("/guides").text
    hrefs = {
        href.split("#")[0]
        for href in re.findall(r'href="(/[^"]*)"', html)
        if href.split("#")[0] and not href.startswith("/static/")
    }
    for href in sorted(hrefs):
        response = client.get(href)
        assert response.status_code == 200, href
