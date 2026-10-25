from datetime import timedelta

from app.config import Settings
from app.clock import utcnow
from app.schemas import EndpointStatus
from app.security import generate_token, hash_token
from app.store.base import EndpointRow, Store


def to_status(endpoint: EndpointRow) -> EndpointStatus:
    now = utcnow()
    days_remaining = None
    if endpoint.expires_at is not None and not endpoint.is_permanent:
        days_remaining = max(
            0.0, (endpoint.expires_at - now).total_seconds() / 86400
        )
    return EndpointStatus(
        destination_email=endpoint.destination_email,
        origin=endpoint.origin,
        verified=endpoint.is_verified,
        active=endpoint.is_active(now),
        permanent=endpoint.is_permanent,
        expires_at=endpoint.expires_at,
        days_remaining=days_remaining,
    )


async def create_endpoint(
    store: Store, settings: Settings, destination_email: str, origin: str
) -> tuple[EndpointRow, str, str, str]:
    """Create an unverified endpoint.

    Returns (endpoint, public_token, manage_token, verification_token). The raw
    tokens are only available here — the DB stores SHA-256 hashes.
    """
    public_token = generate_token()
    manage_token = generate_token()
    verification_token = generate_token()
    endpoint = await store.create_endpoint(
        public_token_hash=hash_token(public_token),
        manage_token_hash=hash_token(manage_token),
        destination_email=destination_email,
        origin=origin,
        verification_token_hash=hash_token(verification_token),
        verification_expires_at=utcnow()
        + timedelta(hours=settings.verification_token_ttl_hours),
    )
    return endpoint, public_token, manage_token, verification_token


async def find_by_public_token(store: Store, token: str) -> EndpointRow | None:
    return await store.get_by_public_token(hash_token(token))


async def find_by_manage_token(store: Store, token: str) -> EndpointRow | None:
    return await store.get_by_manage_token(hash_token(token))


async def find_by_verification_token(store: Store, token: str) -> EndpointRow | None:
    return await store.get_by_verification_token(hash_token(token))


async def mark_verified(
    store: Store, settings: Settings, endpoint: EndpointRow
) -> None:
    """Activate the endpoint: TTL starts now, verification token is consumed."""
    endpoint.email_verified_at = utcnow()
    endpoint.expires_at = endpoint.email_verified_at + timedelta(
        days=settings.default_ttl_days
    )
    endpoint.verification_token_hash = None
    endpoint.verification_expires_at = None
    await store.update_endpoint(endpoint)


async def rotate_verification_token(
    store: Store, settings: Settings, endpoint: EndpointRow
) -> str:
    """Issue a fresh verification token (used for resend). Returns the raw token."""
    token = generate_token()
    endpoint.verification_token_hash = hash_token(token)
    endpoint.verification_expires_at = utcnow() + timedelta(
        hours=settings.verification_token_ttl_hours
    )
    await store.update_endpoint(endpoint)
    return token


async def extend(store: Store, settings: Settings, endpoint: EndpointRow) -> None:
    """Add one TTL period. An expired endpoint restarts from now."""
    now = utcnow()
    base = endpoint.expires_at if endpoint.expires_at and endpoint.expires_at > now else now
    endpoint.expires_at = base + timedelta(days=settings.default_ttl_days)
    await store.update_endpoint(endpoint)


async def make_permanent(store: Store, endpoint: EndpointRow) -> None:
    """Grant permanence: the endpoint never expires. Idempotent — an already
    permanent endpoint keeps its original permanent_at."""
    if endpoint.is_permanent:
        return
    endpoint.is_permanent = True
    endpoint.permanent_at = utcnow()
    await store.update_endpoint(endpoint)


async def revoke_permanent(
    store: Store, settings: Settings, endpoint: EndpointRow
) -> None:
    """Revoke permanence and restart the TTL from now, so a revoked endpoint
    becomes an ordinary temporary endpoint rather than instantly expiring."""
    endpoint.is_permanent = False
    endpoint.permanent_at = None
    endpoint.expires_at = utcnow() + timedelta(days=settings.default_ttl_days)
    await store.update_endpoint(endpoint)


def verification_is_current(endpoint: EndpointRow) -> bool:
    return (
        endpoint.verification_token_hash is not None
        and endpoint.verification_expires_at is not None
        and utcnow() < endpoint.verification_expires_at
    )
