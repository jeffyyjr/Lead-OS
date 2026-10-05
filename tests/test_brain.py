from types import SimpleNamespace

from app import brain
from app.models import AgentRole, Lead, LeadCreate
from app.workflow import demo_tenant


def _fake_client(response):
    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: response))

    return FakeAnthropic


def _lead():
    lead = Lead(**LeadCreate(name="Test", phone="+15555550010", consent_to_contact=True).model_dump())
    lead.current_agent = AgentRole.QUALIFICATION
    return lead


def test_uses_claude_decision(monkeypatch):
    decision = brain.AgentDecision(action="ask_question", message="What ZIP code?", next_agent="qualification_agent", reason="missing zip", confidence=0.9)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(brain.anthropic, "Anthropic", _fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=decision)))

    result = brain.reason_about_lead(_lead(), demo_tenant())

    assert result["action"] == "ask_question"
    assert result["message"] == "What ZIP code?"
    assert AgentRole(result["next_agent"]) == AgentRole.QUALIFICATION


def test_refusal_uses_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(brain.anthropic, "Anthropic", _fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None)))

    result = brain.reason_about_lead(_lead(), demo_tenant())

    assert result == brain._fallback(_lead(), demo_tenant())


def test_safety_never_calls_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(brain.anthropic, "Anthropic", lambda **kw: (_ for _ in ()).throw(AssertionError("called Claude")))
    lead = _lead()
    lead.current_agent = AgentRole.SAFETY

    assert brain.reason_about_lead(lead, demo_tenant())["action"] == "safety_message"
