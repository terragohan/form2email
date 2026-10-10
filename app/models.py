import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    # Naive UTC everywhere so SQLite and Postgres behave identically and all
    # comparisons stay naive-vs-naive.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    public_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    manage_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    destination_email: Mapped[str] = mapped_column(String(320))
    origin: Mapped[str] = mapped_column(String(253))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_token_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_permanent: Mapped[bool] = mapped_column(Boolean, default=False)
    permanent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None

    def is_active(self, now: datetime) -> bool:
        if not self.is_verified:
            return False
        if self.is_permanent:
            return True
        return self.expires_at is not None and now < self.expires_at


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    endpoint_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("endpoints.id"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sender_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    forwarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    forward_status: Mapped[str] = mapped_column(String(20), default="sent")

    endpoint: Mapped[Endpoint] = relationship(back_populates="submissions")
