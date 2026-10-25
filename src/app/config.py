from functools import lru_cache

from fastapi import Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./form2email.db"
    mail_from: str = "form2email@terragohan.com"
    base_url: str = "http://localhost:8000"
    # Google tag (GA4) measurement ID, injected into <head> on every page.
    # Empty disables the tag.
    google_tag_id: str = ""
    default_ttl_days: int = 7
    verification_token_ttl_hours: int = 24
    rate_limit_create_per_hour: int = 5
    rate_limit_submit_per_minute: int = 30
    # Exponential backoff once an IP exceeds the submit cap: each further
    # attempt doubles the lockout from base to max seconds.
    rate_limit_submit_backoff_base_seconds: float = 1.0
    rate_limit_submit_backoff_max_seconds: float = 300.0
    # Verification emails sent to any single address per day, across all
    # clients — stops endpoint creation from being used to flood a mailbox.
    rate_limit_verification_per_email_per_day: int = 3
    # Discovery/docs routes (/api/info, /llms.txt, /for-coding-tools) share
    # one per-IP bucket to limit unnecessary Worker invocations.
    rate_limit_meta_per_minute: int = 3
    # Submissions with a larger Content-Length are rejected with 413 before
    # the body is parsed.
    max_submission_body_bytes: int = 65536
    # Token protecting the admin API (X-Admin-Token header). When empty, the
    # admin routes are disabled (they return 404).
    admin_token: str = ""


@lru_cache
def get_local_settings() -> Settings:
    return Settings()


def get_settings(request: Request) -> Settings:
    env = request.scope.get("env")
    if env is None:
        return get_local_settings()
    values = {}
    for field in Settings.model_fields:
        value = getattr(env, field.upper(), None)
        if value is not None:
            values[field] = str(value)
    return Settings(**values)
