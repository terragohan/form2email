from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class EndpointRow:
    id: str
    public_token_hash: str
    manage_token_hash: str
    destination_email: str
    origin: str
    email_verified_at: datetime | None
    verification_token_hash: str | None
    verification_expires_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    is_permanent: bool
    permanent_at: datetime | None

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None

    def is_active(self, now: datetime) -> bool:
        if not self.is_verified:
            return False
        if self.is_permanent:
            return True
        return self.expires_at is not None and now < self.expires_at


@dataclass
class SubmissionRow:
    id: str
    endpoint_id: str
    received_at: datetime
    sender_name: str | None
    sender_email: str | None
    subject: str | None
    message: str | None
    extra_fields: dict
    forwarded_at: datetime | None
    forward_status: str


class Store(Protocol):
    """Storage backend for endpoints and submissions.

    Two implementations: SqlAlchemyStore (SQLite/Postgres via DATABASE_URL)
    and D1Store (Cloudflare D1 over its HTTP API).
    """

    def create_endpoint(
        self,
        *,
        public_token_hash: str,
        manage_token_hash: str,
        destination_email: str,
        origin: str,
        verification_token_hash: str,
        verification_expires_at: datetime,
    ) -> EndpointRow: ...

    def get_by_public_token(self, token_hash: str) -> EndpointRow | None: ...

    def get_by_manage_token(self, token_hash: str) -> EndpointRow | None: ...

    def get_by_verification_token(self, token_hash: str) -> EndpointRow | None: ...

    def get_endpoint_by_id(self, endpoint_id: str) -> EndpointRow | None: ...

    def update_endpoint(self, row: EndpointRow) -> None: ...

    def delete_endpoint(self, endpoint_id: str) -> None: ...

    def create_submission(
        self,
        *,
        endpoint_id: str,
        sender_name: str | None,
        sender_email: str | None,
        subject: str | None,
        message: str | None,
        extra_fields: dict,
    ) -> SubmissionRow: ...

    def get_submission(self, submission_id: str) -> SubmissionRow | None: ...

    def list_submissions(self, endpoint_id: str) -> list[SubmissionRow]: ...

    def mark_submission_forwarded(
        self, submission_id: str, *, status: str, forwarded_at: datetime | None
    ) -> None: ...


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def parse_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
