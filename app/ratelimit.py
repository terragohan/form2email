import hashlib
import math
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings


class RateLimiter:
    """In-memory sliding-window limiter, keyed per client IP and bucket,
    with exponential backoff for keys that keep hitting the cap.

    Single-process only — INIT-003 replaces this with a shared store.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._backoff: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def hit(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def hit_backoff(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        base_seconds: float,
        max_seconds: float,
    ) -> float:
        """0 when the hit is allowed; otherwise seconds until retry.

        Once a key exceeds the sliding-window cap, every further attempt
        doubles the lockout (base, 2*base, 4*base, ... up to max_seconds).
        A successful hit clears the strikes.
        """
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            strikes, locked_until = self._backoff.get(key, (0, 0.0))
            if now >= locked_until and len(hits) < limit:
                hits.append(now)
                self._backoff.pop(key, None)
                return 0.0
            strikes = min(strikes + 1, 32)
            locked_until = now + min(
                base_seconds * 2 ** (strikes - 1), max_seconds
            )
            self._backoff[key] = (strikes, locked_until)
            return locked_until - now

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._backoff.clear()


limiter = RateLimiter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_creates(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    if not limiter.hit(
        f"create:{_client_ip(request)}", settings.rate_limit_create_per_hour, 3600
    ):
        raise HTTPException(status_code=429, detail="Too many endpoints created")


def limit_verification_emails(email: str, settings: Settings) -> None:
    """Cap verification emails per destination address, across all clients —
    the per-IP create cap alone would still let a caller flood someone
    else's mailbox from rotating IPs. Not a route dependency: call it with
    the parsed address before sending."""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    if not limiter.hit(
        f"verify-email:{digest}",
        settings.rate_limit_verification_per_email_per_day,
        86400,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many verification emails requested for this address",
        )


def limit_submits(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    retry_after = limiter.hit_backoff(
        f"submit:{_client_ip(request)}",
        settings.rate_limit_submit_per_minute,
        60,
        settings.rate_limit_submit_backoff_base_seconds,
        settings.rate_limit_submit_backoff_max_seconds,
    )
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many submissions — slow down and retry later",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


def limit_meta(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Cap the discovery/docs routes (/api/info, /llms.txt,
    /for-coding-tools) per client IP. They're static and cheap, but
    unthrottled they make an easy amplification target for billed
    Lambda invocations. One shared bucket across all three routes."""
    if not limiter.hit(
        f"meta:{_client_ip(request)}", settings.rate_limit_meta_per_minute, 60
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many requests — slow down and retry later",
        )
