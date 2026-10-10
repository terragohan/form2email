from app.main import app


def test_token_gate_disabled_by_default(client):
    app.state.origin_token = ""
    assert client.get("/healthz").status_code == 200


def test_missing_token_rejected_when_configured(client):
    app.state.origin_token = "secret-token"
    response = client.get("/healthz")
    assert response.status_code == 403
    app.state.origin_token = ""


def test_wrong_token_rejected_when_configured(client):
    app.state.origin_token = "secret-token"
    response = client.get(
        "/healthz", headers={"X-Form2Email-Origin-Token": "wrong"}
    )
    assert response.status_code == 403
    app.state.origin_token = ""


def test_correct_token_allowed_when_configured(client):
    app.state.origin_token = "secret-token"
    response = client.get(
        "/healthz", headers={"X-Form2Email-Origin-Token": "secret-token"}
    )
    assert response.status_code == 200
    app.state.origin_token = ""
