from typing import Protocol


class Mailer(Protocol):
    async def send(
        self, *, to: str, subject: str, html: str, reply_to: str | None = None
    ) -> None: ...
