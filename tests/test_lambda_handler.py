import json

from app.main import app
from lambda_handler import handler


def _event(method: str, path: str, headers: dict | None = None, body: str | None = None) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "lambda", **(headers or {})},
        "requestContext": {
            "accountId": "offline",
            "apiId": "offline",
            "domainName": "lambda",
            "requestId": "offline",
            "stage": "$default",
            "time": "01/Jan/2026:00:00:00 +0000",
            "timeEpoch": 0,
            "http": {"method": method, "path": path, "protocol": "HTTP/1.1", "sourceIp": "127.0.0.1"},
        },
        "body": body,
        "isBase64Encoded": False,
    }


def test_healthz_via_lambda_handler():
    response = handler(_event("GET", "/healthz"), None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"ok": True}


def test_unknown_route_via_lambda_handler():
    response = handler(_event("GET", "/nope"), None)
    assert response["statusCode"] == 404


def test_origin_token_gate_via_lambda_handler():
    app.state.origin_token = "secret-token"
    try:
        assert handler(_event("GET", "/healthz"), None)["statusCode"] == 403
        authorized = _event(
            "GET", "/healthz", headers={"X-Form2Email-Origin-Token": "secret-token"}
        )
        assert handler(authorized, None)["statusCode"] == 200
    finally:
        app.state.origin_token = ""


def test_create_endpoint_validation_via_lambda_handler():
    response = handler(
        _event(
            "POST",
            "/api/endpoints",
            headers={"content-type": "application/json"},
            body=json.dumps({"destination_email": "not-an-email"}),
        ),
        None,
    )
    assert response["statusCode"] == 422
