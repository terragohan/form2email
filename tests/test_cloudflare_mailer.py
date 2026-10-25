import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Request

from app.config import Settings, get_settings
from app.mailer import CloudflareMailer, get_mailer


class FakeEmailBinding:
    def __init__(self, error: Exception | None = None):
        self.messages = []
        self.error = error

    async def send(self, message):
        if self.error:
            raise self.error
        self.messages.append(message)


def test_send_builds_message_with_reply_to(monkeypatch):
    monkeypatch.setattr("app.mailer.cloudflare_mailer._to_js", lambda message: message)
    email = FakeEmailBinding()
    mailer = CloudflareMailer(email=email, mail_from="form2email@terragohan.com")

    asyncio.run(
        mailer.send(
            to="owner@example.com",
            subject="Verify your Form2Email endpoint",
            html="<p>click</p>",
            reply_to="ada@example.org",
        )
    )

    assert email.messages == [
        {
            "to": "owner@example.com",
            "from": "form2email@terragohan.com",
            "subject": "Verify your Form2Email endpoint",
            "html": "<p>click</p>",
            "replyTo": "ada@example.org",
        }
    ]


def test_send_omits_reply_to(monkeypatch):
    monkeypatch.setattr("app.mailer.cloudflare_mailer._to_js", lambda message: message)
    email = FakeEmailBinding()
    mailer = CloudflareMailer(email=email, mail_from="form2email@terragohan.com")

    asyncio.run(mailer.send(to="owner@example.com", subject="hi", html="<p>x</p>"))

    assert "replyTo" not in email.messages[0]


def test_send_propagates_provider_error(monkeypatch):
    monkeypatch.setattr("app.mailer.cloudflare_mailer._to_js", lambda message: message)
    mailer = CloudflareMailer(
        email=FakeEmailBinding(RuntimeError("delivery failed")),
        mail_from="form2email@terragohan.com",
    )

    with pytest.raises(RuntimeError, match="delivery failed"):
        asyncio.run(mailer.send(to="owner@example.com", subject="hi", html="<p>x</p>"))


def test_get_mailer_uses_request_email_binding():
    email = FakeEmailBinding()
    request = Request({"type": "http", "env": SimpleNamespace(EMAIL=email)})

    mailer = get_mailer(request, Settings(mail_from="forms@example.com"))

    assert isinstance(mailer, CloudflareMailer)
    assert mailer._email is email
    assert mailer._mail_from == "forms@example.com"


def test_get_mailer_requires_email_binding():
    request = Request({"type": "http"})
    with pytest.raises(RuntimeError, match="EMAIL binding"):
        get_mailer(request, Settings())


def test_worker_settings_are_read_from_request_env():
    request = Request(
        {
            "type": "http",
            "env": SimpleNamespace(
                BASE_URL="https://form2email.example",
                MAIL_FROM="forms@example.com",
                DEFAULT_TTL_DAYS="14",
                ADMIN_TOKEN="secret",
            ),
        }
    )

    settings = get_settings(request)

    assert settings.base_url == "https://form2email.example"
    assert settings.mail_from == "forms@example.com"
    assert settings.default_ttl_days == 14
    assert settings.admin_token == "secret"
