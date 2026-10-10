from app.config import Settings
from app.mailer import SmtpMailer, get_mailer


class _RecordingSMTP:
    instances: list["_RecordingSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_args = None
        self.sent = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.sent.append(message)


class _RecordingSMTPSSL(_RecordingSMTP):
    instances: list["_RecordingSMTPSSL"] = []


def _make_mailer(**overrides) -> SmtpMailer:
    defaults = dict(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        mail_from="forms@terragohan.com",
    )
    defaults.update(overrides)
    return SmtpMailer(**defaults)


def test_send_builds_html_message_with_reply_to(monkeypatch):
    monkeypatch.setattr("app.mailer.smtp_mailer.smtplib.SMTP", _RecordingSMTP)
    mailer = _make_mailer()

    mailer.send(
        to="owner@example.com",
        subject="Verify your Form2Email endpoint",
        html="<p>click</p>",
        reply_to="ada@example.org",
    )

    smtp = _RecordingSMTP.instances[-1]
    assert smtp.host == "smtp.example.com" and smtp.port == 587
    assert smtp.starttls_called
    assert smtp.login_args == ("user", "pass")
    message = smtp.sent[0]
    assert message["To"] == "owner@example.com"
    assert message["From"] == "forms@terragohan.com"
    assert message["Subject"] == "Verify your Form2Email endpoint"
    assert message["Reply-To"] == "ada@example.org"
    assert "<p>click</p>" in message.get_payload()[-1].get_payload()


def test_send_omits_reply_to_and_login_when_not_given(monkeypatch):
    monkeypatch.setattr("app.mailer.smtp_mailer.smtplib.SMTP", _RecordingSMTP)
    mailer = _make_mailer(username="", password="")

    mailer.send(to="owner@example.com", subject="hi", html="<p>x</p>")

    smtp = _RecordingSMTP.instances[-1]
    assert "Reply-To" not in smtp.sent[0]
    assert smtp.login_args is None


def test_port_465_uses_implicit_ssl_and_skips_starttls(monkeypatch):
    monkeypatch.setattr("app.mailer.smtp_mailer.smtplib.SMTP_SSL", _RecordingSMTPSSL)
    mailer = _make_mailer(port=465)

    mailer.send(to="owner@example.com", subject="hi", html="<p>x</p>")

    smtp = _RecordingSMTPSSL.instances[-1]
    assert smtp.port == 465
    assert not smtp.starttls_called
    assert len(smtp.sent) == 1


def test_starttls_disabled_when_configured(monkeypatch):
    monkeypatch.setattr("app.mailer.smtp_mailer.smtplib.SMTP", _RecordingSMTP)
    mailer = _make_mailer(starttls=False)

    mailer.send(to="owner@example.com", subject="hi", html="<p>x</p>")

    assert not _RecordingSMTP.instances[-1].starttls_called


def test_get_mailer_selects_smtp_driver(monkeypatch):
    import app.mailer as mailer_module

    monkeypatch.setattr(
        mailer_module,
        "get_settings",
        lambda: Settings(
            mail_driver="smtp",
            smtp_host="smtp.example.com",
            mail_from="forms@terragohan.com",
        ),
    )
    monkeypatch.setattr(mailer_module, "_mailer", None)

    mailer = get_mailer()

    assert isinstance(mailer, SmtpMailer)
    assert mailer._host == "smtp.example.com"
    assert mailer._mail_from == "forms@terragohan.com"


def test_get_mailer_defaults_to_resend(monkeypatch):
    import app.mailer as mailer_module
    from app.mailer import ResendMailer

    monkeypatch.setattr(mailer_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(mailer_module, "_mailer", None)

    assert isinstance(get_mailer(), ResendMailer)
