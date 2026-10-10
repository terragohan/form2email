import json
import uuid
from datetime import datetime
from typing import Any

import httpx

from app.models import utcnow
from app.store.base import (
    EndpointRow,
    SubmissionRow,
    iso_or_none,
    parse_dt,
)

_QUERY_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account}"
    "/d1/database/{database}/query"
)


class D1Error(RuntimeError):
    pass


def _params(values: tuple) -> list[Any]:
    """D1 params accept null/str/number — datetimes become ISO strings,
    bools become ints."""
    out = []
    for value in values:
        if isinstance(value, datetime):
            out.append(value.isoformat())
        elif isinstance(value, bool):
            out.append(int(value))
        else:
            out.append(value)
    return out


class D1Store:
    """Cloudflare D1 over the HTTP API.

    Rate limits (~50 queries/s per database) are far above this service's
    volume; the latency cost is one edge round trip per query. If that ever
    matters, front D1 with a Worker binding instead of the REST API — the SQL
    here is standard SQLite and would carry over unchanged.
    """

    def __init__(
        self,
        *,
        account_id: str,
        database_id: str,
        api_token: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = _QUERY_URL.format(account=account_id, database=database_id)
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self._client = client or httpx.Client(timeout=30)

    def _query(self, sql: str, values: tuple = ()) -> list[dict]:
        response = self._client.post(
            self._url,
            headers=self._headers,
            json={"sql": sql, "params": _params(values)},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise D1Error(f"D1 HTTP {response.status_code}: {response.text[:200]}") from exc
        if not payload.get("success"):
            raise D1Error(str(payload.get("errors")))
        results = payload["result"]
        if results and not results[0].get("success", True):
            raise D1Error(str(results[0].get("errors")))
        return results[0]["results"] if results else []

    @staticmethod
    def _endpoint_from(row: dict) -> EndpointRow:
        return EndpointRow(
            id=row["id"],
            public_token_hash=row["public_token_hash"],
            manage_token_hash=row["manage_token_hash"],
            destination_email=row["destination_email"],
            origin=row["origin"],
            email_verified_at=parse_dt(row["email_verified_at"]),
            verification_token_hash=row["verification_token_hash"],
            verification_expires_at=parse_dt(row["verification_expires_at"]),
            created_at=parse_dt(row["created_at"]),
            expires_at=parse_dt(row["expires_at"]),
            is_permanent=bool(row["is_permanent"]),
            permanent_at=parse_dt(row["permanent_at"]),
        )

    @staticmethod
    def _submission_from(row: dict) -> SubmissionRow:
        return SubmissionRow(
            id=row["id"],
            endpoint_id=row["endpoint_id"],
            received_at=parse_dt(row["received_at"]),
            sender_name=row["sender_name"],
            sender_email=row["sender_email"],
            subject=row["subject"],
            message=row["message"],
            extra_fields=json.loads(row["extra_fields"] or "{}"),
            forwarded_at=parse_dt(row["forwarded_at"]),
            forward_status=row["forward_status"],
        )

    def create_endpoint(
        self,
        *,
        public_token_hash: str,
        manage_token_hash: str,
        destination_email: str,
        origin: str,
        verification_token_hash: str,
        verification_expires_at: datetime,
    ) -> EndpointRow:
        endpoint_id = str(uuid.uuid4())
        self._query(
            "INSERT INTO endpoints (id, public_token_hash, manage_token_hash,"
            " destination_email, origin, verification_token_hash,"
            " verification_expires_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                endpoint_id,
                public_token_hash,
                manage_token_hash,
                destination_email,
                origin,
                verification_token_hash,
                verification_expires_at,
                utcnow().isoformat(),
            ),
        )
        return self.get_by_manage_token(manage_token_hash)

    def get_by_public_token(self, token_hash: str) -> EndpointRow | None:
        rows = self._query(
            "SELECT * FROM endpoints WHERE public_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    def get_by_manage_token(self, token_hash: str) -> EndpointRow | None:
        rows = self._query(
            "SELECT * FROM endpoints WHERE manage_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    def get_by_verification_token(self, token_hash: str) -> EndpointRow | None:
        rows = self._query(
            "SELECT * FROM endpoints WHERE verification_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    def get_endpoint_by_id(self, endpoint_id: str) -> EndpointRow | None:
        rows = self._query("SELECT * FROM endpoints WHERE id = ?", (endpoint_id,))
        return self._endpoint_from(rows[0]) if rows else None

    def update_endpoint(self, row: EndpointRow) -> None:
        self._query(
            "UPDATE endpoints SET email_verified_at = ?,"
            " verification_token_hash = ?, verification_expires_at = ?,"
            " expires_at = ?, is_permanent = ?, permanent_at = ?"
            " WHERE id = ?",
            (
                iso_or_none(row.email_verified_at),
                row.verification_token_hash,
                iso_or_none(row.verification_expires_at),
                iso_or_none(row.expires_at),
                row.is_permanent,
                iso_or_none(row.permanent_at),
                row.id,
            ),
        )

    def delete_endpoint(self, endpoint_id: str) -> None:
        self._query("DELETE FROM endpoints WHERE id = ?", (endpoint_id,))

    def create_submission(
        self,
        *,
        endpoint_id: str,
        sender_name: str | None,
        sender_email: str | None,
        subject: str | None,
        message: str | None,
        extra_fields: dict,
    ) -> SubmissionRow:
        submission_id = str(uuid.uuid4())
        self._query(
            "INSERT INTO submissions (id, endpoint_id, received_at, sender_name,"
            " sender_email, subject, message, extra_fields, forward_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                submission_id,
                endpoint_id,
                utcnow().isoformat(),
                sender_name,
                sender_email,
                subject,
                message,
                json.dumps(extra_fields),
            ),
        )
        return self.get_submission(submission_id)

    def get_submission(self, submission_id: str) -> SubmissionRow | None:
        rows = self._query(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)
        )
        return self._submission_from(rows[0]) if rows else None

    def list_submissions(self, endpoint_id: str) -> list[SubmissionRow]:
        rows = self._query(
            "SELECT * FROM submissions WHERE endpoint_id = ?"
            " ORDER BY received_at",
            (endpoint_id,),
        )
        return [self._submission_from(row) for row in rows]

    def mark_submission_forwarded(
        self, submission_id: str, *, status: str, forwarded_at: datetime | None
    ) -> None:
        self._query(
            "UPDATE submissions SET forward_status = ?, forwarded_at = ?"
            " WHERE id = ?",
            (status, iso_or_none(forwarded_at), submission_id),
        )
