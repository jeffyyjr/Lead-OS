import json
import os
import urllib.request
from typing import Any

from app.models import AgentRole, Lead, TenantConfig


SYSTEM_PROMPT = """You are a specialist inside Lead-OS, an autonomous lead-response and booking system for home-service businesses.
Return ONLY valid JSON with keys: action, message, extracted, next_agent, reason, confidence.
Allowed actions: ask_question, offer_booking, follow_up, close_out_of_area, hold_no_contact, safety_message, no_op.
Allowed next_agent values: qualification, booking, followup, service_area, consent, safety, null.
Never override an opt-out or missing contact consent. Never invent appointment availability, prices, warranties, licenses, or service coverage. Emergency/safety situations must use safety_message and must not provide repair instructions. Keep customer-facing messages short and useful.
"""


def _fallback(lead: Lead, tenant: TenantConfig) -> dict[str, Any]:
    role = lead.current_agent
    if role == AgentRole.CONSENT:
        return {"action": "hold_no_contact", "message": None, "extracted": {}, "next_agent": None, "reason": "No contact consent", "confidence": 1.0}
    if role == AgentRole.SAFETY:
        return {"action": "safety_message", "message": "For safety, move away from the suspected hazard and contact the appropriate emergency or utility service. We’ll pause normal service scheduling for now.", "extracted": {}, "next_agent": None, "reason": "Emergency keyword", "confidence": 1.0}
    if role == AgentRole.SERVICE_AREA:
        return {"action": "close_out_of_area", "message": "Thanks for reaching out. This property is outside our configured service area, so we can’t schedule this request.", "extracted": {}, "next_agent": None, "reason": "Outside configured service area", "confidence": 1.0}
    if role == AgentRole.BOOKING:
        return {"action": "offer_booking", "message": "You’re qualified for scheduling. What appointment time works best for you?", "extracted": {}, "next_agent": "booking", "reason": "Ready to book", "confidence": 0.9}
    if role == AgentRole.FOLLOWUP:
        return {"action": "follow_up", "message": "Just checking back on your service request. Would you like to schedule an appointment?", "extracted": {}, "next_agent": "followup", "reason": "Follow-up due", "confidence": 0.9}
    return {"action": "ask_question", "message": "What service do you need, what ZIP code is the property in, how urgent is it, and what time works best?", "extracted": {}, "next_agent": "qualification", "reason": "Qualification incomplete", "confidence": 0.8}


def reason_about_lead(lead: Lead, tenant: TenantConfig) -> dict[str, Any]:
    """Use an OpenAI-compatible reasoning call when configured, with a deterministic fallback.

    OPENAI_API_KEY enables the reasoning layer. OPENAI_MODEL can override the default.
    The model proposes actions; Lead-OS still enforces deterministic consent/safety boundaries.
    """
    if not lead.consent_to_contact and lead.current_agent != AgentRole.CONSENT:
        lead.current_agent = AgentRole.CONSENT
    if lead.current_agent in {AgentRole.CONSENT, AgentRole.SAFETY, AgentRole.SERVICE_AREA}:
        return _fallback(lead, tenant)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback(lead, tenant)

    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "agent": lead.current_agent.value if lead.current_agent else None,
                "lead": lead.model_dump(mode="json"),
                "tenant": tenant.model_dump(mode="json"),
            })},
        ],
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        result = json.loads(body["choices"][0]["message"]["content"])
        if result.get("action") not in {"ask_question", "offer_booking", "follow_up", "close_out_of_area", "hold_no_contact", "safety_message", "no_op"}:
            return _fallback(lead, tenant)
        return result
    except Exception:
        return _fallback(lead, tenant)
