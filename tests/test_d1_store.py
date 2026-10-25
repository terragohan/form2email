import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import Request

from app.db import get_store
from app.store.base import EndpointRow, iso_or_none
from app.store.d1 import D1Error, D1Store


def test_get_store_requires_d1_binding():
    request = Request({"type": "http"})
    with pytest.raises(RuntimeError, match="DB binding"):
        next(get_store(request))


def test_get_store_uses_request_d1_binding():
    database = FakeD1Database()
    request = Request({"type": "http", "env": SimpleNamespace(DB=database)})
    store = next(get_store(request))
    assert isinstance(store, D1Store)
    assert store._database is database


class FakeD1Database:
    def __init__(self, rows: list[dict] | None = None, error: Exception | None = None):
        self.rows = [{"ok": 1}] if rows is None else rows
        self.error = error
        self.requests: list[dict] = []

    def prepare(self, sql: str):
        return FakeD1Statement(self, sql)


class FakeD1Statement:
    def __init__(self, database: FakeD1Database, sql: str):
        self.database = database
        self.sql = sql
        self.params: list = []

    def bind(self, *params):
        self.params = list(params)
        return self

    async def all(self):
        self.database.requests.append({"sql": self.sql, "params": self.params})
        if self.database.error:
            raise self.database.error
        return FakeD1Result({"results": self.database.rows, "success": True})


class FakeD1Result:
    def __init__(self, payload):
        self.payload = payload

    def to_py(self):
        return self.payload


def make_store(database: FakeD1Database) -> D1Store:
    return D1Store(database)


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
    database = FakeD1Database(rows=[_endpoint_row_dict()])
    store = make_store(database)

    row = asyncio.run(
        store.create_endpoint(
            public_token_hash="pub",
            manage_token_hash="man",
            destination_email="owner@example.com",
            origin="example.com",
            verification_token_hash="ver",
            verification_expires_at=datetime(2026, 10, 3, 10, 0, 0),
        )
    )

    sql = database.requests[0]["sql"]
    assert sql.startswith("INSERT INTO endpoints")
    params = database.requests[0]["params"]
    assert params[1] == "pub" and params[3] == "owner@example.com"
    assert params[6] == "2026-10-03T10:00:00"
    assert row.id == "ep-1"
    assert row.is_permanent is False
    assert row.verification_expires_at == datetime(2026, 10, 3, 10, 0, 0)


def test_get_by_token_queries_by_hash():
    database = FakeD1Database(rows=[_endpoint_row_dict()])
    store = make_store(database)

    row = asyncio.run(store.get_by_public_token("pub"))

    assert database.requests[0]["sql"].startswith("SELECT * FROM endpoints")
    assert database.requests[0]["params"] == ["pub"]
    assert row.destination_email == "owner@example.com"


def test_get_by_missing_token_returns_none():
    store = make_store(FakeD1Database(rows=[]))
    assert asyncio.run(store.get_by_manage_token("nope")) is None


def test_get_endpoint_by_id_queries_by_id():
    database = FakeD1Database(rows=[_endpoint_row_dict()])
    store = make_store(database)

    row = asyncio.run(store.get_endpoint_by_id("ep-1"))

    assert "WHERE id = ?" in database.requests[0]["sql"]
    assert database.requests[0]["params"] == ["ep-1"]
    assert row is not None
    assert row.id == "ep-1"
    assert row.destination_email == "owner@example.com"


def test_get_endpoint_by_id_missing_returns_none():
    store = make_store(FakeD1Database(rows=[]))
    assert asyncio.run(store.get_endpoint_by_id("nope")) is None


def test_update_endpoint_writes_mutable_fields_only():
    database = FakeD1Database()
    store = make_store(database)
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

    asyncio.run(store.update_endpoint(endpoint))

    sql = database.requests[0]["sql"]
    assert sql.startswith("UPDATE endpoints SET")
    assert "public_token_hash" not in sql
    params = database.requests[0]["params"]
    assert params[0] == "2026-10-02T12:00:00"
    assert params[3] == "2026-10-09T12:00:00"
    assert params[-1] == "ep-1"


def test_mark_submission_forwarded():
    database = FakeD1Database()
    store = make_store(database)

    asyncio.run(
        store.mark_submission_forwarded(
            "sub-1", status="sent", forwarded_at=datetime(2026, 10, 2, 12, 0, 0)
        )
    )

    assert database.requests[0]["sql"].startswith("UPDATE submissions SET")
    assert database.requests[0]["params"] == [
        "sent",
        "2026-10-02T12:00:00",
        "sub-1",
    ]


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
    store = make_store(FakeD1Database(rows=[row]))

    submission = asyncio.run(store.get_submission("sub-1"))

    assert submission.extra_fields == {"company": "ACME"}
    assert submission.received_at == datetime(2026, 10, 2, 10, 0, 0)
    assert submission.forward_status == "pending"


def test_binding_error_raises_d1_error():
    store = make_store(FakeD1Database(error=RuntimeError("no such table")))
    with pytest.raises(D1Error, match="no such table"):
        asyncio.run(store.get_by_public_token("pub"))


def test_iso_or_none_helper():
    assert iso_or_none(datetime(2026, 10, 2, 10, 0, 0)) == "2026-10-02T10:00:00"
    assert iso_or_none(None) is None
