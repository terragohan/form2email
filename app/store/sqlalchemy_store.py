import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Endpoint, Submission, utcnow
from app.store.base import EndpointRow, SubmissionRow

_MUTABLE_FIELDS = (
    "email_verified_at",
    "verification_token_hash",
    "verification_expires_at",
    "expires_at",
    "is_permanent",
    "permanent_at",
)


def _endpoint_to_row(model: Endpoint) -> EndpointRow:
    return EndpointRow(
        id=model.id,
        public_token_hash=model.public_token_hash,
        manage_token_hash=model.manage_token_hash,
        destination_email=model.destination_email,
        origin=model.origin,
        email_verified_at=model.email_verified_at,
        verification_token_hash=model.verification_token_hash,
        verification_expires_at=model.verification_expires_at,
        created_at=model.created_at,
        expires_at=model.expires_at,
        is_permanent=model.is_permanent,
        permanent_at=model.permanent_at,
    )


def _submission_to_row(model: Submission) -> SubmissionRow:
    return SubmissionRow(
        id=model.id,
        endpoint_id=model.endpoint_id,
        received_at=model.received_at,
        sender_name=model.sender_name,
        sender_email=model.sender_email,
        subject=model.subject,
        message=model.message,
        extra_fields=model.extra_fields or {},
        forwarded_at=model.forwarded_at,
        forward_status=model.forward_status,
    )


class SqlAlchemyStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_endpoint(
        self,
        *,
        public_token_hash: str,
        manage_token_hash: str,
        destination_email: str,
        origin: str,
        verification_token_hash: str,
        verification_expires_at,
    ) -> EndpointRow:
        model = Endpoint(
            id=str(uuid.uuid4()),
            public_token_hash=public_token_hash,
            manage_token_hash=manage_token_hash,
            destination_email=destination_email,
            origin=origin,
            verification_token_hash=verification_token_hash,
            verification_expires_at=verification_expires_at,
            created_at=utcnow(),
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _endpoint_to_row(model)

    def get_by_public_token(self, token_hash: str) -> EndpointRow | None:
        return self._get_row(Endpoint.public_token_hash == token_hash)

    def get_by_manage_token(self, token_hash: str) -> EndpointRow | None:
        return self._get_row(Endpoint.manage_token_hash == token_hash)

    def get_by_verification_token(self, token_hash: str) -> EndpointRow | None:
        return self._get_row(Endpoint.verification_token_hash == token_hash)

    def get_endpoint_by_id(self, endpoint_id: str) -> EndpointRow | None:
        model = self._session.get(Endpoint, endpoint_id)
        return _endpoint_to_row(model) if model else None

    def _get_row(self, condition) -> EndpointRow | None:
        model = self._session.scalar(select(Endpoint).where(condition))
        return _endpoint_to_row(model) if model else None

    def update_endpoint(self, row: EndpointRow) -> None:
        model = self._session.get(Endpoint, row.id)
        if model is None:
            raise KeyError(f"endpoint {row.id} not found")
        for field in _MUTABLE_FIELDS:
            setattr(model, field, getattr(row, field))
        self._session.commit()

    def delete_endpoint(self, endpoint_id: str) -> None:
        model = self._session.get(Endpoint, endpoint_id)
        if model is not None:
            self._session.delete(model)
            self._session.commit()

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
        model = Submission(
            id=str(uuid.uuid4()),
            endpoint_id=endpoint_id,
            received_at=utcnow(),
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            message=message,
            extra_fields=extra_fields,
            forward_status="pending",
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _submission_to_row(model)

    def get_submission(self, submission_id: str) -> SubmissionRow | None:
        model = self._session.get(Submission, submission_id)
        return _submission_to_row(model) if model else None

    def list_submissions(self, endpoint_id: str) -> list[SubmissionRow]:
        models = self._session.scalars(
            select(Submission)
            .where(Submission.endpoint_id == endpoint_id)
            .order_by(Submission.received_at)
        ).all()
        return [_submission_to_row(model) for model in models]

    def mark_submission_forwarded(
        self, submission_id: str, *, status: str, forwarded_at
    ) -> None:
        model = self._session.get(Submission, submission_id)
        if model is None:
            raise KeyError(f"submission {submission_id} not found")
        model.forward_status = status
        model.forwarded_at = forwarded_at
        self._session.commit()
