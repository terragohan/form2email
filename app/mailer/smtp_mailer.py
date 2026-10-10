import smtplib
from email.message import EmailMessage


class SmtpMailer:
    """Plain SMTP sender using the stdlib — no SDK, any provider, or a local
    Postfix/relay listening on localhost (set SMTP_HOST accordingly)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        mail_from: str,
        starttls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._mail_from = mail_from
        self._starttls = starttls

    def send(
        self, *, to: str, subject: str, html: str, reply_to: str | None = None
    ) -> None:
        message = EmailMessage()
        message["From"] = self._mail_from
        message["To"] = to
        message["Subject"] = subject
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content("This email requires an HTML-capable mail client.")
        message.add_alternative(html, subtype="html")

        if self._port == 465:
            connection: smtplib.SMTP = smtplib.SMTP_SSL(self._host, self._port, timeout=30)
        else:
            connection = smtplib.SMTP(self._host, self._port, timeout=30)
        with connection as smtp:
            if self._port != 465 and self._starttls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)
