from datetime import datetime, timezone

from app.models import AgentRole, Lead, LeadStatus, TenantConfig, WorkflowEvent
from app.store import add_event, save_lead


def _event(lead: Lead, event_type: str, **detail) -> None:
    add_event(
        WorkflowEvent(
            lead_id=lead.id,
            tenant_id=lead.tenant_id,
            event_type=event_type,
            detail=detail,
        )
    )


def handoff_to_agent(lead: Lead, role: AgentRole, reason: str) -> Lead:
    lead.status = LeadStatus.AGENT_HANDOFF
    lead.current_agent = role
    lead.agent_reason = reason
    lead.updated_at = datetime.now(timezone.utc)
    _event(lead, "agent_handoff", agent=role.value, reason=reason)
    return save_lead(lead)


def run_agent(lead: Lead, tenant: TenantConfig) -> dict:
    """Execute the currently assigned specialist agent deterministically.

    This is the autonomous fallback layer. It never requires a human queue.
    Provider-backed LLM reasoning can be added behind the same interface later.
    """
    if not lead.current_agent:
        return {"action": "none", "reason": "no_agent_assigned"}

    role = lead.current_agent

    if role == AgentRole.CONSENT:
        # Do not contact a lead when consent is absent. Automation can safely
        # disposition the lead and wait for a new consent-bearing inbound event.
        lead.agent_reason = "awaiting_contact_consent"
        _event(lead, "agent_decision", agent=role.value, action="hold_no_contact")
        save_lead(lead)
        return {"action": "hold_no_contact"}

    if role == AgentRole.SAFETY:
        # Safety agent blocks ordinary sales automation and returns a predefined
        # safety disposition rather than improvising hazardous advice.
        lead.agent_reason = "safety_script_required"
        _event(lead, "agent_decision", agent=role.value, action="send_safety_script_and_pause_sales")
        save_lead(lead)
        return {
            "action": "send_safety_script_and_pause_sales",
            "message_type": "preapproved_emergency_safety",
        }

    if role == AgentRole.SERVICE_AREA:
        lead.status = LeadStatus.LOST
        lead.agent_reason = "outside_service_area"
        _event(lead, "agent_decision", agent=role.value, action="close_out_of_area")
        save_lead(lead)
        return {"action": "close_out_of_area"}

    if role == AgentRole.QUALIFICATION:
        lead.status = LeadStatus.QUALIFYING
        lead.current_agent = AgentRole.QUALIFICATION
        _event(lead, "agent_decision", agent=role.value, action="continue_qualification")
        save_lead(lead)
        return {"action": "continue_qualification"}

    if role == AgentRole.BOOKING:
        _event(lead, "agent_decision", agent=role.value, action="request_booking_slot")
        return {"action": "request_booking_slot", "booking_url": tenant.booking_url}

    if role == AgentRole.FOLLOWUP:
        _event(lead, "agent_decision", agent=role.value, action="continue_followup_sequence")
        return {"action": "continue_followup_sequence"}

    return {"action": "none", "reason": "unsupported_agent"}
