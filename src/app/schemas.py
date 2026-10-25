import re
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, EmailStr, field_validator

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)


def host_from_url(value: str) -> str | None:
    """Extract a normalized hostname from a domain, origin, or full URL."""
    value = value.strip().lower()
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        host = urlsplit(value).hostname
    except ValueError:
        return None
    return host if host and _DOMAIN_RE.match(host) else None


def host_matches_origin(host: str | None, origin: str) -> bool:
    """True only when the hostname exactly equals the registered origin.
    Subdomains are not implied: app.example.com does not match example.com
    unless it was registered itself (evil-example.com never matches)."""
    if host is None:
        return False
    return host == origin


def normalize_origin(value: str) -> str:
    """Normalize a registered origin to a bare hostname. Accepts
    `http(s)://<domain>` or a bare `<domain>` (an optional port is dropped).
    Anything else — other schemes, userinfo, paths, query strings — is
    rejected."""
    raw = value.strip().lower()
    if "://" in raw and not raw.startswith(("http://", "https://")):
        raise ValueError(f"Invalid domain or origin: {value!r}")
    candidate = raw if "://" in raw else "http://" + raw
    try:
        parts = urlsplit(candidate)
        parts.port  # raises on a malformed or out-of-range port
    except ValueError:
        raise ValueError(f"Invalid domain or origin: {value!r}") from None
    if (
        parts.username
        or parts.password
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(f"Invalid domain or origin: {value!r}")
    host = host_from_url(raw)
    if host is None:
        raise ValueError(f"Invalid domain or origin: {value!r}")
    return host


class CreateEndpointRequest(BaseModel):
    destination_email: EmailStr
    origin: str

    @field_validator("origin", mode="before")
    @classmethod
    def _normalize_origin(cls, value: str) -> str:
        return normalize_origin(value)


class EndpointCreated(BaseModel):
    public_url: str
    manage_url: str
    manage_page_url: str
    destination_email: str
    origin: str
    verification: str


class EndpointStatus(BaseModel):
    destination_email: str
    origin: str
    verified: bool
    active: bool
    permanent: bool
    expires_at: datetime | None
    days_remaining: float | None


class MessageResponse(BaseModel):
    detail: str
