from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import Settings, get_settings
from app.db import get_store
from app.render import render
from app.routers import admin, endpoints, forms, meta, verify
from app.services import endpoints as svc
from app.store.base import Store


class OriginTokenMiddleware(BaseHTTPMiddleware):
    """Rejects requests missing the shared origin token.

    In production only the Cloudflare Worker can reach the app (the firewall
    allows Cloudflare IPs only), and the worker adds the token — so direct
    origin access bypassing Cloudflare is rejected here. Disabled when
    ORIGIN_TOKEN is unset (local development).
    """

    async def dispatch(self, request, call_next):
        token = request.app.state.origin_token
        if token and request.headers.get("X-Form2Email-Origin-Token") != token:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        return await call_next(request)


app = FastAPI(title="Form2Email", version="0.1.0")
app.state.origin_token = get_settings().origin_token
app.add_middleware(OriginTokenMiddleware)
# The app is only reachable through the Cloudflare Worker in production, so
# trusting forwarded headers is safe and required for correct per-client rate
# limiting.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
app.include_router(endpoints.router)
app.include_router(verify.router)
app.include_router(forms.router)
app.include_router(meta.router)
app.include_router(admin.router, include_in_schema=False)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index(settings: Settings = Depends(get_settings)) -> str:
    return render("index.html", mail_from=settings.mail_from)


@app.get("/how-it-works", response_class=HTMLResponse)
def how_it_works(settings: Settings = Depends(get_settings)) -> str:
    return render("how-it-works.html", mail_from=settings.mail_from)


@app.get("/manage/{manage_token}", response_class=HTMLResponse)
def manage_page(manage_token: str, store: Store = Depends(get_store)) -> HTMLResponse:
    endpoint = svc.find_by_manage_token(store, manage_token)
    if endpoint is None:
        return HTMLResponse(render("manage.html", found=False), status_code=404)
    return HTMLResponse(
        render(
            "manage.html",
            found=True,
            manage_token=manage_token,
            status=svc.to_status(endpoint),
        )
    )
