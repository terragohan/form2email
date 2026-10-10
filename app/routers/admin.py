import secrets

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import Settings, get_settings
from app.db import get_store
from app.schemas import EndpointStatus
from app.services import endpoints as svc
from app.store.base import EndpointRow, Store

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(
    settings: Settings = Depends(get_settings),
    x_admin_token: str | None = Header(default=None),
) -> None:
    # When no admin token is configured the admin API is disabled entirely and
    # indistinguishable from any other unknown route.
    if not settings.admin_token:
        raise HTTPException(status_code=404, detail="Not found")
    if x_admin_token is None or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def get_endpoint_by_id(
    endpoint_id: str, store: Store = Depends(get_store)
) -> EndpointRow:
    endpoint = store.get_endpoint_by_id(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.post(
    "/endpoints/{endpoint_id}/permanent",
    response_model=EndpointStatus,
    dependencies=[Depends(require_admin)],
)
def make_endpoint_permanent(
    endpoint: EndpointRow = Depends(get_endpoint_by_id),
    store: Store = Depends(get_store),
) -> EndpointStatus:
    svc.make_permanent(store, endpoint)
    return svc.to_status(endpoint)


@router.delete(
    "/endpoints/{endpoint_id}/permanent",
    response_model=EndpointStatus,
    dependencies=[Depends(require_admin)],
)
def revoke_endpoint_permanent(
    endpoint: EndpointRow = Depends(get_endpoint_by_id),
    store: Store = Depends(get_store),
) -> EndpointStatus:
    if not endpoint.is_permanent:
        raise HTTPException(status_code=409, detail="Endpoint is not permanent")
    svc.revoke_permanent(store, endpoint)
    return svc.to_status(endpoint)
