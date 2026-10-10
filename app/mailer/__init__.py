from app.config import get_settings
from app.mailer.base import Mailer
from app.mailer.resend_mailer import ResendMailer
from app.mailer.smtp_mailer import SmtpMailer

__all__ = ["Mailer", "ResendMailer", "SmtpMailer", "get_mailer"]

_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    global _mailer
    if _mailer is None:
        settings = get_settings()
        if settings.mail_driver == "smtp":
            _mailer = SmtpMailer(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                mail_from=settings.mail_from,
                starttls=settings.smtp_starttls,
            )
        else:
            _mailer = ResendMailer()
    return _mailer
