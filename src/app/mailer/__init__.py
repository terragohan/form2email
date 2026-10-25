from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.mailer.base import Mailer
from app.mailer.cloudflare_mailer import CloudflareMailer

__all__ = ["Mailer", "CloudflareMailer", "get_mailer"]


def get_mailer(
    request: Request, settings: Settings = Depends(get_settings)
) -> Mailer:
    env = request.scope.get("env")
    if env is None or getattr(env, "EMAIL", None) is None:
        raise RuntimeError("Cloudflare EMAIL binding is not configured")
    return CloudflareMailer(email=env.EMAIL, mail_from=settings.mail_from)
