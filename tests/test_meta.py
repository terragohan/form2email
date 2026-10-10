def test_llms_txt(client):
    response = client.get("/llms.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "/api/endpoints" in response.text
    assert "http://testserver" in response.text
    assert "onboarding@resend.dev" in response.text


def test_for_coding_tools_page(client):
    response = client.get("/for-coding-tools")
    assert response.status_code == 200
    assert "Set up a Form2Email endpoint" in response.text
    assert "onboarding@resend.dev" in response.text
    assert "/api/info" in response.text


def test_api_info(client):
    response = client.get("/api/info")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Form2Email"
    assert body["base_url"] == "http://testserver"
    assert body["operations"]["create_endpoint"]["path"] == "/api/endpoints"
    assert body["operations"]["submit"]["method"] == "POST"
    for code in ("403", "410", "413", "422", "429", "502"):
        assert code in body["errors"]
    assert body["limits"]["max_submission_body_bytes"] == 65536


def test_meta_routes_share_a_per_ip_bucket(client):
    for _ in range(3):
        assert client.get("/api/info").status_code == 200
    assert client.get("/api/info").status_code == 429
    # One shared bucket: the other meta routes are spent too.
    assert client.get("/llms.txt").status_code == 429
    assert client.get("/for-coding-tools").status_code == 429
