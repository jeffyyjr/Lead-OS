import json
import logging
import os
from typing import Any, Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from app.models import AgentRole, Lead, TenantConfig

log = logging.getLogger(__name__)

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

SYSTEM_PROMPT = """You are a specialist inside Lead-OS, an autonomous lead-response and booking system for home-service businesses.
You receive the current agent role, the lead, and the business (tenant) config, and decide the next action.
Never override an opt-out or missing contact consent. Never invent appointment availability, prices, warranties, licenses, or service coverage. Emergency/safety situations must use safety_message and must not provide repair instructions. Keep customer-facing messages short and useful.
"""


class AgentDecision(BaseModel):
    action: Literal["ask_question", "offer_booking", "follow_up", "close_out_of_area", "hold_no_contact", "safety_message", "no_op"]
    message: Optional[str] = Field(description="Customer-facing message, or null if nothing should be sent")
    next_agent: Optional[Literal["qualification_agent", "booking_agent", "followup_agent", "service_area_agent", "consent_agent", "safety_agent"]]
    reason: str
    confidence: float


def _fallback(lead: Lead, tenant: TenantConfig) -> dict[str, Any]:
    role = lead.current_agent
    if role == AgentRole.CONSENT:
        return {"action": "hold_no_contact", "message": None, "extracted": {}, "next_agent": None, "reason": "No contact consent", "confidence": 1.0}
    if role == AgentRole.SAFETY:
        return {"action": "safety_message", "message": "For safety, move away from the suspected hazard and contact the appropriate emergency or utility service. We’ll pause normal service scheduling for now.", "extracted": {}, "next_agent": None, "reason": "Emergency keyword", "confidence": 1.0}
    if role == AgentRole.SERVICE_AREA:
        return {"action": "close_out_of_area", "message": "Thanks for reaching out. This property is outside our configured service area, so we can’t schedule this request.", "extracted": {}, "next_agent": None, "reason": "Outside configured service area", "confidence": 1.0}
    if role == AgentRole.BOOKING:
        return {"action": "offer_booking", "message": "You’re qualified for scheduling. What appointment time works best for you?", "extracted": {}, "next_agent": "booking_agent", "reason": "Ready to book", "confidence": 0.9}
    if role == AgentRole.FOLLOWUP:
        return {"action": "follow_up", "message": "Just checking back on your service request. Would you like to schedule an appointment?", "extracted": {}, "next_agent": "followup_agent", "reason": "Follow-up due", "confidence": 0.9}
    return {"action": "ask_question", "message": "What service do you need, what ZIP code is the property in, how urgent is it, and what time works best?", "extracted": {}, "next_agent": "qualification_agent", "reason": "Qualification incomplete", "confidence": 0.8}


def reason_about_lead(lead: Lead, tenant: TenantConfig) -> dict[str, Any]:
    """Ask Claude for the next action when configured, with a deterministic fallback.

    ANTHROPIC_API_KEY enables the reasoning layer. CLAUDE_MODEL can override the default.
    The model proposes actions; Lead-OS still enforces deterministic consent/safety boundaries.
    """
    if not lead.consent_to_contact and lead.current_agent != AgentRole.CONSENT:
        lead.current_agent = AgentRole.CONSENT
    if lead.current_agent in {AgentRole.CONSENT, AgentRole.SAFETY, AgentRole.SERVICE_AREA}:
        return _fallback(lead, tenant)

    if not os.getenv("ANTHROPIC_API_KEY"):
        return _fallback(lead, tenant)

    try:
        client = anthropic.Anthropic(timeout=30.0, max_retries=1)
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            # Retry on a fallback model if the request is declined.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps({
                "agent": lead.current_agent.value if lead.current_agent else None,
                "lead": lead.model_dump(mode="json"),
                "tenant": tenant.model_dump(mode="json"),
            })}],
            output_format=AgentDecision,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            log.warning("Claude returned no decision (stop_reason=%s)", response.stop_reason)
            return _fallback(lead, tenant)
        return response.parsed_output.model_dump()
    except (anthropic.APIError, ValueError) as exc:
        log.warning("Claude request failed: %s", type(exc).__name__)
        return _fallback(lead, tenant)
