from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.db import get_store
from app.mailer import Mailer, get_mailer
from app.ratelimit import limit_creates, limit_verification_emails
from app.render import render
from app.schemas import (
    CreateEndpointRequest,
    EndpointCreated,
    EndpointStatus,
    MessageResponse,
)
from app.services import endpoints as svc
from app.store.base import EndpointRow, Store

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])


def get_endpoint_by_manage_token(
    manage_token: str, store: Store = Depends(get_store)
) -> EndpointRow:
    endpoint = svc.find_by_manage_token(store, manage_token)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


def _send_verification_email(
    mailer: Mailer,
    settings: Settings,
    endpoint: EndpointRow,
    token: str,
    public_url: str | None = None,
    manage_page_url: str | None = None,
) -> None:
    verify_url = f"{settings.base_url}/verify/{token}"
    html = render(
        "email/verification.html",
        destination_email=endpoint.destination_email,
        origin=endpoint.origin,
        verify_url=verify_url,
        public_url=public_url,
        manage_page_url=manage_page_url,
        ttl_hours=settings.verification_token_ttl_hours,
        ttl_days=settings.default_ttl_days,
        mail_from=settings.mail_from,
    )
    mailer.send(
        to=endpoint.destination_email,
        subject="Verify your Form2Email endpoint",
        html=html,
    )


@router.post(
    "",
    response_model=EndpointCreated,
    status_code=201,
    dependencies=[Depends(limit_creates)],
)
def create_endpoint(
    body: CreateEndpointRequest,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
    mailer: Mailer = Depends(get_mailer),
) -> EndpointCreated:
    limit_verification_emails(str(body.destination_email), settings)
    endpoint, public_token, manage_token, verification_token = svc.create_endpoint(
        store, str(body.destination_email), body.origin
    )
    public_url = f"{settings.base_url}/f/{public_token}"
    manage_url = f"{settings.base_url}/api/endpoints/{manage_token}"
    manage_page_url = f"{settings.base_url}/manage/{manage_token}"
    try:
        _send_verification_email(
            mailer,
            settings,
            endpoint,
            verification_token,
            public_url=public_url,
            manage_page_url=manage_page_url,
        )
    except Exception:
        # Roll the endpoint back rather than leaving an unverifiable orphan
        # the user never hears about (e.g. misconfigured mail provider).
        store.delete_endpoint(endpoint.id)
        raise HTTPException(
            status_code=502,
            detail="Verification email could not be sent — check email configuration",
        )
    return EndpointCreated(
        public_url=public_url,
        manage_url=manage_url,
        manage_page_url=manage_page_url,
        destination_email=endpoint.destination_email,
        origin=endpoint.origin,
        verification="pending",
    )


@router.get("/{manage_token}", response_model=EndpointStatus)
def endpoint_status(
    endpoint: EndpointRow = Depends(get_endpoint_by_manage_token),
) -> EndpointStatus:
    return svc.to_status(endpoint)


@router.post("/{manage_token}/verification", response_model=MessageResponse)
def resend_verification(
    endpoint: EndpointRow = Depends(get_endpoint_by_manage_token),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
    mailer: Mailer = Depends(get_mailer),
) -> MessageResponse:
    if endpoint.is_verified:
        raise HTTPException(status_code=409, detail="Email already verified")
    limit_verification_emails(endpoint.destination_email, settings)
    token = svc.rotate_verification_token(store, endpoint)
    _send_verification_email(mailer, settings, endpoint, token)
    return MessageResponse(detail="Verification email sent")


@router.post("/{manage_token}/extend", response_model=EndpointStatus)
def extend_endpoint(
    endpoint: EndpointRow = Depends(get_endpoint_by_manage_token),
    store: Store = Depends(get_store),
) -> EndpointStatus:
    if not endpoint.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    if endpoint.is_permanent:
        raise HTTPException(
            status_code=409, detail="Endpoint is permanent and does not expire"
        )
    svc.extend(store, endpoint)
    return svc.to_status(endpoint)
