from app import tools
from app.models import Lead, LeadCreate


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def _lead(consent=True):
    return Lead(**LeadCreate(name="Test", email="customer@example.com", consent_to_contact=consent).model_dump())


def test_sends_gmail_when_configured(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-password")
    monkeypatch.setattr(tools.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()

    result = tools.send_customer_message(_lead(), "Hi there")

    assert result == {"ok": True, "mode": "gmail", "sent": True}
    assert FakeSMTP.sent[0]["To"] == "customer@example.com"
    assert "Reply STOP" in FakeSMTP.sent[0].get_content()


def test_never_emails_without_consent(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "shop@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "test-app-password")
    monkeypatch.setattr(tools.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()

    result = tools.send_customer_message(_lead(consent=False), "Hi there")

    assert result["mode"] == "blocked"
    assert FakeSMTP.sent == []
