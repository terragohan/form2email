from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.db import get_store
from app.render import render
from app.services import endpoints as svc
from app.store.base import Store

router = APIRouter(tags=["verify"])


@router.get("/verify/{token}", response_class=HTMLResponse)
def verify_email(token: str, store: Store = Depends(get_store)) -> str:
    endpoint = svc.find_by_verification_token(store, token)
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail="Verification link is invalid or has already been used",
        )
    if not svc.verification_is_current(endpoint):
        raise HTTPException(
            status_code=410,
            detail="Verification link has expired — request a new one from your manage URL",
        )
    svc.mark_verified(store, endpoint)
    return render(
        "verified.html",
        expires_at=endpoint.expires_at,
        is_permanent=endpoint.is_permanent,
    )
