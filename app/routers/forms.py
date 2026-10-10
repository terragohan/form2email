from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import Settings, get_settings
from app.db import get_store
from app.mailer import Mailer, get_mailer
from app.models import utcnow
from app.ratelimit import limit_submits
from app.render import render
from app.schemas import host_from_url, host_matches_origin
from app.services import endpoints as svc
from app.services import submissions as submission_svc
from app.store.base import EndpointRow, Store

router = APIRouter(prefix="/f", tags=["forms"])


def _get_active_endpoint(store: Store, public_token: str) -> EndpointRow:
    endpoint = svc.find_by_public_token(store, public_token)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Form not found")
    if not endpoint.is_verified:
        raise HTTPException(status_code=403, detail="Endpoint email is not verified")
    if not endpoint.is_active(utcnow()):
        raise HTTPException(status_code=410, detail="Endpoint has expired")
    return endpoint


def _origin_allowed(request: Request, endpoint: EndpointRow) -> bool:
    """Match-or-absent: reject posts whose browser Origin/Referer is present and
    doesn't match the stored origin. Requests without either header (curl,
    server-to-server, mobile apps) are allowed."""
    raw = request.headers.get("origin") or request.headers.get("referer")
    if not raw:
        return True
    return host_matches_origin(host_from_url(raw), endpoint.origin)


def _matching_origin(request: Request, endpoint: EndpointRow) -> str | None:
    """The request's Origin header verbatim when its hostname exactly matches
    the endpoint's registered origin, else None."""
    raw = request.headers.get("origin")
    if raw and host_matches_origin(host_from_url(raw), endpoint.origin):
        return raw
    return None


def _apply_cors(request: Request, endpoint: EndpointRow, response: Response) -> None:
    """Reflect Access-Control-Allow-Origin (plus Vary) on responses to requests
    whose Origin matches the endpoint. Requests with no Origin header (curl,
    server-to-server) get no CORS headers."""
    origin = _matching_origin(request, endpoint)
    if origin is not None:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers.append("Vary", "Origin")


@router.options("/{public_token}")
def preflight_form(
    public_token: str,
    request: Request,
    store: Store = Depends(get_store),
) -> Response:
    endpoint = _get_active_endpoint(store, public_token)
    origin = request.headers.get("origin")
    if not origin or not host_matches_origin(host_from_url(origin), endpoint.origin):
        raise HTTPException(
            status_code=403,
            detail=f"Submissions must come from {endpoint.origin}",
        )
    response = Response(status_code=200)
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        request.headers.get("access-control-request-headers") or "Content-Type"
    )
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers.append("Vary", "Origin")
    return response


@router.get("/{public_token}", response_class=HTMLResponse)
def form_page(
    public_token: str,
    request: Request,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    endpoint = _get_active_endpoint(store, public_token)
    response = HTMLResponse(
        render("form.html", action_url=f"{settings.base_url}/f/{public_token}")
    )
    _apply_cors(request, endpoint, response)
    return response


@router.post("/{public_token}", dependencies=[Depends(limit_submits)])
async def submit_form(
    public_token: str,
    request: Request,
    store: Store = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
    settings: Settings = Depends(get_settings),
) -> Response:
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > settings.max_submission_body_bytes:
        raise HTTPException(status_code=413, detail="Submission too large")

    endpoint = _get_active_endpoint(store, public_token)
    if not _origin_allowed(request, endpoint):
        raise HTTPException(
            status_code=403,
            detail=f"Submissions must come from {endpoint.origin}",
        )

    if "application/json" in request.headers.get("content-type", ""):
        data = await request.json()
    else:
        data = dict(await request.form())
    redirect_url = data.pop("_redirect", None)

    try:
        submission = submission_svc.record_and_forward(
            store, mailer, endpoint, data, settings.mail_from
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if submission.forward_status != "sent":
        raise HTTPException(
            status_code=502, detail="Failed to deliver the submission email"
        )
    if redirect_url:
        response: Response = RedirectResponse(str(redirect_url), status_code=303)
    else:
        response = JSONResponse({"ok": True, "submission_id": submission.id})
    _apply_cors(request, endpoint, response)
    return response
