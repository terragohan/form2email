import json
from datetime import datetime

import httpx
import pytest

from app.store.d1 import D1Error, D1Store
from app.store.base import iso_or_none

ACCOUNT = "acct-1"
DATABASE = "db-1"
TOKEN = "cf-token"
URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/d1/database/{DATABASE}/query"


class FakeD1Transport(httpx.BaseTransport):
    """Captures queries and serves scripted rows."""

    def __init__(self, rows: list[dict] | None = None, fail: dict | None = None):
        self.requests: list[dict] = []
        self.rows = [{"ok": 1}] if rows is None else rows
        self.fail = fail

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        auth = request.headers.get("Authorization")
        if auth != f"Bearer {TOKEN}":
            return httpx.Response(403, json={"success": False, "errors": ["bad token"]})
        if self.fail:
            return httpx.Response(200, json={"success": False, "errors": [self.fail]})
        result = {
            "results": self.rows,
            "success": True,
            "meta": {"duration": 1, "changes": 0},
        }
        return httpx.Response(200, json={"success": True, "result": [result]})


def make_store(transport: FakeD1Transport) -> D1Store:
    client = httpx.Client(transport=transport)
    return D1Store(
        account_id=ACCOUNT,
        database_id=DATABASE,
        api_token=TOKEN,
        client=client,
    )


def _endpoint_row_dict() -> dict:
    return {
        "id": "ep-1",
        "public_token_hash": "pub",
        "manage_token_hash": "man",
        "destination_email": "owner@example.com",
        "origin": "example.com",
        "email_verified_at": None,
        "verification_token_hash": "ver",
        "verification_expires_at": "2026-10-03 10:00:00",
        "created_at": "2026-10-02 10:00:00",
        "expires_at": None,
        "is_permanent": 0,
        "permanent_at": None,
    }


def test_create_endpoint_sends_insert_and_returns_row():
    transport = FakeD1Transport(rows=[_endpoint_row_dict()])
    store = make_store(transport)

    row = store.create_endpoint(
        public_token_hash="pub",
        manage_token_hash="man",
        destination_email="owner@example.com",
        origin="example.com",
        verification_token_hash="ver",
        verification_expires_at=datetime(2026, 10, 3, 10, 0, 0),
    )

    sql = transport.requests[0]["sql"]
    assert sql.startswith("INSERT INTO endpoints")
    params = transport.requests[0]["params"]
    assert params[1] == "pub" and params[3] == "owner@example.com"
    # datetime params are serialized to ISO strings
    assert params[6] == "2026-10-03T10:00:00"
    assert row.id == "ep-1"
    assert row.is_permanent is False
    assert row.verification_expires_at == datetime(2026, 10, 3, 10, 0, 0)


def test_get_by_token_queries_by_hash():
    transport = FakeD1Transport(rows=[_endpoint_row_dict()])
    store = make_store(transport)

    row = store.get_by_public_token("pub")

    assert transport.requests[0]["sql"].startswith("SELECT * FROM endpoints")
    assert transport.requests[0]["params"] == ["pub"]
    assert row.destination_email == "owner@example.com"


def test_get_by_missing_token_returns_none():
    transport = FakeD1Transport(rows=[])
    store = make_store(transport)

    assert store.get_by_manage_token("nope") is None


def test_get_endpoint_by_id_queries_by_id():
    transport = FakeD1Transport(rows=[_endpoint_row_dict()])
    store = make_store(transport)

    row = store.get_endpoint_by_id("ep-1")

    assert transport.requests[0]["sql"].startswith("SELECT * FROM endpoints")
    assert "WHERE id = ?" in transport.requests[0]["sql"]
    assert transport.requests[0]["params"] == ["ep-1"]
    assert row is not None
    assert row.id == "ep-1"
    assert row.destination_email == "owner@example.com"


def test_get_endpoint_by_id_missing_returns_none():
    transport = FakeD1Transport(rows=[])
    store = make_store(transport)

    assert store.get_endpoint_by_id("nope") is None


def test_update_endpoint_writes_mutable_fields_only():
    transport = FakeD1Transport()
    store = make_store(transport)
    row = store.get_by_public_token("pub") if False else None  # build row manually
    from app.store.base import EndpointRow

    endpoint = EndpointRow(
        id="ep-1",
        public_token_hash="pub",
        manage_token_hash="man",
        destination_email="owner@example.com",
        origin="example.com",
        email_verified_at=datetime(2026, 10, 2, 12, 0, 0),
        verification_token_hash=None,
        verification_expires_at=None,
        created_at=datetime(2026, 10, 2, 10, 0, 0),
        expires_at=datetime(2026, 10, 9, 12, 0, 0),
        is_permanent=False,
        permanent_at=None,
    )

    store.update_endpoint(endpoint)

    sql = transport.requests[0]["sql"]
    assert sql.startswith("UPDATE endpoints SET")
    assert "public_token_hash" not in sql  # immutable fields untouched
    params = transport.requests[0]["params"]
    assert params[0] == "2026-10-02T12:00:00"
    assert params[3] == "2026-10-09T12:00:00"
    assert params[-1] == "ep-1"


def test_mark_submission_forwarded():
    transport = FakeD1Transport()
    store = make_store(transport)

    store.mark_submission_forwarded(
        "sub-1", status="sent", forwarded_at=datetime(2026, 10, 2, 12, 0, 0)
    )

    sql = transport.requests[0]["sql"]
    assert sql.startswith("UPDATE submissions SET")
    assert transport.requests[0]["params"] == ["sent", "2026-10-02T12:00:00", "sub-1"]


def test_submission_roundtrip_parses_json_extra_fields():
    row = {
        "id": "sub-1",
        "endpoint_id": "ep-1",
        "received_at": "2026-10-02 10:00:00",
        "sender_name": "Ada",
        "sender_email": "ada@example.org",
        "subject": "Hi",
        "message": "Hello",
        "extra_fields": '{"company": "ACME"}',
        "forwarded_at": None,
        "forward_status": "pending",
    }
    transport = FakeD1Transport(rows=[row])
    store = make_store(transport)

    submission = store.get_submission("sub-1")

    assert submission.extra_fields == {"company": "ACME"}
    assert submission.received_at == datetime(2026, 10, 2, 10, 0, 0)
    assert submission.forward_status == "pending"


def test_api_error_raises_d1_error():
    transport = FakeD1Transport(fail={"code": 7500, "message": "no such table"})
    store = make_store(transport)

    with pytest.raises(D1Error, match="no such table"):
        store.get_by_public_token("pub")


def test_bad_auth_raises_d1_error():
    transport = FakeD1Transport()
    store = D1Store(
        account_id=ACCOUNT,
        database_id=DATABASE,
        api_token="wrong",
        client=httpx.Client(transport=transport),
    )

    with pytest.raises(D1Error):
        store.get_by_public_token("pub")


def test_iso_or_none_helper():
    assert iso_or_none(datetime(2026, 10, 2, 10, 0, 0)) == "2026-10-02T10:00:00"
    assert iso_or_none(None) is None
