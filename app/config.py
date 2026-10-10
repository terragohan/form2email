from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "sqlite:///./form2email.db"
    # Cloudflare D1 (used when DATABASE_URL=d1): the account/database the
    # database lives in, and an API token with "Cloudflare D1: Edit".
    cloudflare_account_id: str = ""
    cloudflare_d1_database_id: str = ""
    cloudflare_api_token: str = ""
    resend_api_key: str = ""
    mail_from: str = "onboarding@resend.dev"
    base_url: str = "http://localhost:8000"
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
    # one per-IP bucket — static but unthrottled they'd be an easy target
    # for billed Lambda invocations.
    rate_limit_meta_per_minute: int = 3
    # Submissions with a larger Content-Length are rejected with 413 before
    # the body is parsed.
    max_submission_body_bytes: int = 65536
    # Shared secret the Cloudflare Worker sends on every request. When empty
    # (local dev), the gate is disabled. Set a long random value in production.
    origin_token: str = ""
    # Token protecting the admin API (X-Admin-Token header). When empty, the
    # admin routes are disabled (they return 404).
    admin_token: str = ""
    # Mail transport: "resend" (HTTP API, default) or "smtp" (any provider,
    # including a local Postfix/relay — point SMTP_HOST at it).
    mail_driver: str = "resend"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
