import json
import uuid
from datetime import datetime
from typing import Any

from app.clock import utcnow
from app.store.base import (
    EndpointRow,
    SubmissionRow,
    iso_or_none,
    parse_dt,
)


class D1Error(RuntimeError):
    pass


def _params(values: tuple) -> list[Any]:
    out = []
    for value in values:
        if isinstance(value, datetime):
            out.append(value.isoformat())
        elif isinstance(value, bool):
            out.append(int(value))
        else:
            out.append(value)
    return out


def _python(value):
    return value.to_py() if hasattr(value, "to_py") else value


class D1Store:
    def __init__(self, database) -> None:
        self._database = database

    async def _query(self, sql: str, values: tuple = ()) -> list[dict]:
        try:
            statement = self._database.prepare(sql)
            if values:
                statement = statement.bind(*_params(values))
            result = _python(await statement.all())
            rows = result["results"] if isinstance(result, dict) else result.results
            return [dict(_python(row)) for row in _python(rows)]
        except Exception as exc:
            raise D1Error(str(exc)) from exc

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

    async def create_endpoint(
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
        await self._query(
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
                utcnow(),
            ),
        )
        return await self.get_by_manage_token(manage_token_hash)

    async def get_by_public_token(self, token_hash: str) -> EndpointRow | None:
        rows = await self._query(
            "SELECT * FROM endpoints WHERE public_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    async def get_by_manage_token(self, token_hash: str) -> EndpointRow | None:
        rows = await self._query(
            "SELECT * FROM endpoints WHERE manage_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    async def get_by_verification_token(self, token_hash: str) -> EndpointRow | None:
        rows = await self._query(
            "SELECT * FROM endpoints WHERE verification_token_hash = ?", (token_hash,)
        )
        return self._endpoint_from(rows[0]) if rows else None

    async def get_endpoint_by_id(self, endpoint_id: str) -> EndpointRow | None:
        rows = await self._query("SELECT * FROM endpoints WHERE id = ?", (endpoint_id,))
        return self._endpoint_from(rows[0]) if rows else None

    async def update_endpoint(self, row: EndpointRow) -> None:
        await self._query(
            "UPDATE endpoints SET email_verified_at = ?,"
            " verification_token_hash = ?, verification_expires_at = ?,"
            " expires_at = ?, is_permanent = ?, permanent_at = ?"
            " WHERE id = ?",
            (
                row.email_verified_at,
                row.verification_token_hash,
                row.verification_expires_at,
                row.expires_at,
                row.is_permanent,
                row.permanent_at,
                row.id,
            ),
        )

    async def delete_endpoint(self, endpoint_id: str) -> None:
        await self._query("DELETE FROM endpoints WHERE id = ?", (endpoint_id,))

    async def create_submission(
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
        await self._query(
            "INSERT INTO submissions (id, endpoint_id, received_at, sender_name,"
            " sender_email, subject, message, extra_fields, forward_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                submission_id,
                endpoint_id,
                utcnow(),
                sender_name,
                sender_email,
                subject,
                message,
                json.dumps(extra_fields),
            ),
        )
        return await self.get_submission(submission_id)

    async def get_submission(self, submission_id: str) -> SubmissionRow | None:
        rows = await self._query(
            "SELECT * FROM submissions WHERE id = ?", (submission_id,)
        )
        return self._submission_from(rows[0]) if rows else None

    async def list_submissions(self, endpoint_id: str) -> list[SubmissionRow]:
        rows = await self._query(
            "SELECT * FROM submissions WHERE endpoint_id = ?"
            " ORDER BY received_at",
            (endpoint_id,),
        )
        return [self._submission_from(row) for row in rows]

    async def mark_submission_forwarded(
        self, submission_id: str, *, status: str, forwarded_at: datetime | None
    ) -> None:
        await self._query(
            "UPDATE submissions SET forward_status = ?, forwarded_at = ?"
            " WHERE id = ?",
            (status, forwarded_at, submission_id),
        )
