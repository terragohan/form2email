from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.config import Settings, get_settings
from app.ratelimit import limit_meta
from app.render import render

router = APIRouter(tags=["meta"], dependencies=[Depends(limit_meta)])

FIELD_LIMITS = {
    "name": 200,
    "email": 320,
    "subject": 500,
    "message": 20_000,
    "extra_fields": 20,
    "extra_field_key": 100,
    "extra_field_value": 1000,
}

ERROR_SEMANTICS = {
    "403": "Email not verified yet, or the submission's Origin/Referer doesn't exactly match the registered origin",
    "410": "Endpoint expired — extend it from the manage page to revive it",
    "413": "Submission body over the size cap",
    "422": "A field is over its length cap or the origin is invalid",
    "429": "Rate limited — slow down and retry (Retry-After header on submit)",
    "502": "The mail provider failed to deliver — the submission is still stored; try again",
}


@router.get("/llms.txt", response_class=PlainTextResponse)
def llms_txt(settings: Settings = Depends(get_settings)) -> str:
    return render("llms.txt", settings=settings)


@router.get("/for-coding-tools", response_class=HTMLResponse)
def for_coding_tools(settings: Settings = Depends(get_settings)) -> str:
    return render("for-coding-tools.html", settings=settings)


@router.get("/api/info")
def api_info(settings: Settings = Depends(get_settings)) -> dict:
    base = settings.base_url.rstrip("/")
    return {
        "name": "Form2Email",
        "description": (
            "Turn any HTML form into an email. Create an endpoint with a "
            "destination address and the domain your form lives on, verify "
            "the email by clicking the link we send, then point your form at "
            "the public URL — every submission lands in the destination inbox."
        ),
        "base_url": base,
        "docs": {
            "prompt_guide": f"{base}/for-coding-tools",
            "llms_txt": f"{base}/llms.txt",
            "openapi": f"{base}/openapi.json",
            "how_it_works": f"{base}/how-it-works",
        },
        "authentication": "None — the API is unauthenticated; tokens are issued in responses",
        "verification_flow": [
            "POST /api/endpoints with destination_email + origin",
            "A human must click the link in the verification email we send (single-use, expires in 24h)",
            "After verification the endpoint accepts submissions for 7 days",
            "Extend any time (+7 days per call, free) via POST <manage_url>/extend",
        ],
        "operations": {
            "create_endpoint": {
                "method": "POST",
                "path": "/api/endpoints",
                "content_type": "application/json",
                "request_fields": {
                    "destination_email": "EmailStr — inbox that receives submissions",
                    "origin": "Bare domain or http(s):// origin the form lives on; normalized to a hostname; exact match on submit, subdomains must be registered separately",
                },
                "response_fields": {
                    "public_url": "Form target URL — submissions POST here",
                    "manage_url": "API URL for status/extend/resend (secret)",
                    "manage_page_url": "Human-friendly manage page (secret)",
                    "destination_email": "Echoed back",
                    "origin": "Normalized origin",
                    "verification": "always 'pending' on creation",
                },
            },
            "endpoint_status": {"method": "GET", "path": "<manage_url>"},
            "extend": {
                "method": "POST",
                "path": "<manage_url>/extend",
                "note": "+7 days, free; revives expired endpoints; no-op on permanent endpoints",
            },
            "resend_verification": {"method": "POST", "path": "<manage_url>/verification"},
            "submit": {
                "method": "POST",
                "path": "<public_url>",
                "content_type": "application/x-www-form-urlencoded or application/json",
                "fields": {
                    "name": "optional, becomes part of the relay",
                    "email": "optional, becomes Reply-To on the relay",
                    "subject": "optional",
                    "message": "the body of the relay email",
                    "_redirect": "optional; browser submitters get a 303 here",
                    "anything else": "listed as additional fields in the relay",
                },
                "origin_rule": (
                    "Browser posts must carry an Origin/Referer matching the "
                    "registered origin exactly; requests with no origin "
                    "headers (curl, server-to-server) are always accepted."
                ),
            },
        },
        "errors": ERROR_SEMANTICS,
        "rate_limits": {
            "endpoint_creation_per_ip_per_hour": settings.rate_limit_create_per_hour,
            "submissions_per_ip_per_minute": settings.rate_limit_submit_per_minute,
            "verification_emails_per_address_per_day": settings.rate_limit_verification_per_email_per_day,
            "submit_backoff_seconds": {
                "base": settings.rate_limit_submit_backoff_base_seconds,
                "max": settings.rate_limit_submit_backoff_max_seconds,
                "rule": "each attempt past the submit cap doubles the lockout",
            },
        },
        "limits": {
            "max_submission_body_bytes": settings.max_submission_body_bytes,
            "field_length_limits": FIELD_LIMITS,
            "endpoint_ttl_days": settings.default_ttl_days,
            "verification_token_ttl_hours": settings.verification_token_ttl_hours,
        },
        "deliverability": (
            f"Verification and relay emails are sent from {settings.mail_from} — "
            "destination inboxes should add it as a trusted sender."
        ),
    }
