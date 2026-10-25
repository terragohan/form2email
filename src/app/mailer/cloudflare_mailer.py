def _to_js(message):
    from js import Object
    from pyodide.ffi import to_js

    return to_js(message, dict_converter=Object.fromEntries)


class CloudflareMailer:
    def __init__(self, *, email, mail_from: str) -> None:
        self._email = email
        self._mail_from = mail_from

    async def send(
        self, *, to: str, subject: str, html: str, reply_to: str | None = None
    ) -> None:
        message = {
            "to": to,
            "from": self._mail_from,
            "subject": subject,
            "html": html,
        }
        if reply_to:
            message["replyTo"] = reply_to
        await self._email.send(_to_js(message))
