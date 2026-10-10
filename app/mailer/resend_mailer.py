import resend

from app.config import get_settings


class ResendMailer:
    def __init__(self) -> None:
        settings = get_settings()
        resend.api_key = settings.resend_api_key
        self._mail_from = settings.mail_from

    def send(
        self, *, to: str, subject: str, html: str, reply_to: str | None = None
    ) -> None:
        params: resend.Emails.SendParams = {
            "from": self._mail_from,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            params["reply_to"] = reply_to
        resend.Emails.send(params)
