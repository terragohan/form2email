from app.mailer import Mailer
from app.models import utcnow
from app.render import render
from app.store.base import EndpointRow, Store, SubmissionRow

STANDARD_FIELDS = {"name", "email", "subject", "message"}

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 320
MAX_SUBJECT_LENGTH = 500
MAX_MESSAGE_LENGTH = 20_000
MAX_EXTRA_FIELDS = 20
MAX_EXTRA_KEY_LENGTH = 100
MAX_EXTRA_VALUE_LENGTH = 1000


def _clean(value, max_length: int, field: str) -> str | None:
    """Normalize one submitted field: strings pass through, numbers and
    booleans are coerced, anything else (uploaded files, nested JSON) is
    dropped. Overly long values are rejected rather than silently
    truncated."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    if len(value) > max_length:
        raise ValueError(f"{field} is longer than {max_length} characters")
    return value


def _extra_fields(data: dict) -> dict[str, str]:
    extra: dict[str, str] = {}
    for key, value in data.items():
        if key in STANDARD_FIELDS:
            continue
        if not isinstance(key, str) or len(key) > MAX_EXTRA_KEY_LENGTH:
            continue
        cleaned = _clean(value, MAX_EXTRA_VALUE_LENGTH, f"extra field {key!r}")
        if cleaned is not None:
            extra[key] = cleaned
        if len(extra) > MAX_EXTRA_FIELDS:
            raise ValueError(f"more than {MAX_EXTRA_FIELDS} extra fields")
    return extra


def record_and_forward(
    store: Store, mailer: Mailer, endpoint: EndpointRow, data: dict, mail_from: str
) -> SubmissionRow:
    """Persist the submission and relay it by email.

    Raises ValueError on over-length fields. Delivery failures are recorded
    as forward_status="failed" (no retry queue in the MVP — see INIT-005).
    """
    submission = store.create_submission(
        endpoint_id=endpoint.id,
        sender_name=_clean(data.get("name"), MAX_NAME_LENGTH, "name"),
        sender_email=_clean(data.get("email"), MAX_EMAIL_LENGTH, "email"),
        subject=_clean(data.get("subject"), MAX_SUBJECT_LENGTH, "subject"),
        message=_clean(data.get("message"), MAX_MESSAGE_LENGTH, "message"),
        extra_fields=_extra_fields(data),
    )

    subject = (
        f"New form submission: {submission.subject}"
        if submission.subject
        else "New form submission"
    )
    html = render(
        "email/submission.html",
        sender_name=submission.sender_name,
        sender_email=submission.sender_email,
        subject=submission.subject,
        message=submission.message,
        extra_fields=submission.extra_fields,
        origin=endpoint.origin,
        mail_from=mail_from,
    )
    reply_to = (
        submission.sender_email
        if submission.sender_email and "@" in submission.sender_email
        else None
    )
    try:
        mailer.send(
            to=endpoint.destination_email,
            subject=subject,
            html=html,
            reply_to=reply_to,
        )
        submission.forward_status = "sent"
        submission.forwarded_at = utcnow()
        store.mark_submission_forwarded(
            submission.id, status="sent", forwarded_at=submission.forwarded_at
        )
    except Exception:
        submission.forward_status = "failed"
        store.mark_submission_forwarded(
            submission.id, status="failed", forwarded_at=None
        )
    return submission
