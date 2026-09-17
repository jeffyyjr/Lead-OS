from datetime import datetime, timezone

from app.brain import reason_about_lead
from app.models import AgentRole, Lead, LeadStatus, TenantConfig, WorkflowEvent
from app.store import add_event, save_lead
from app.tools import execute_tools


def _event(lead: Lead, event_type: str, **detail) -> None:
    add_event(WorkflowEvent(lead_id=lead.id, tenant_id=lead.tenant_id, event_type=event_type, detail=detail))


def handoff_to_agent(lead: Lead, role: AgentRole, reason: str) -> Lead:
    lead.status = LeadStatus.AGENT_HANDOFF
    lead.current_agent = role
    lead.agent_reason = reason
    lead.updated_at = datetime.now(timezone.utc)
    _event(lead, "agent_handoff", agent=role.value, reason=reason)
    return save_lead(lead)


def _role(value):
    if not value:
        return None
    try:
        return AgentRole(value)
    except ValueError:
        return None


def run_agent(lead: Lead, tenant: TenantConfig) -> dict:
    if not lead.current_agent:
        return {"action": "none", "reason": "no_agent_assigned"}

    role = lead.current_agent
    decision = reason_about_lead(lead, tenant)
    action = decision.get("action", "no_op")
    message = decision.get("message")
    next_agent = _role(decision.get("next_agent"))

    if not lead.consent_to_contact:
        action, next_agent, message = "hold_no_contact", AgentRole.CONSENT, None
    if role == AgentRole.SAFETY:
        action, next_agent = "safety_message", None

    if action == "close_out_of_area":
        lead.status, lead.current_agent = LeadStatus.LOST, None
    elif action == "hold_no_contact":
        lead.status, lead.current_agent = LeadStatus.AGENT_HANDOFF, AgentRole.CONSENT
    elif action == "ask_question":
        lead.status, lead.current_agent = LeadStatus.QUALIFYING, next_agent or AgentRole.QUALIFICATION
    elif action == "offer_booking":
        lead.status, lead.current_agent = LeadStatus.QUALIFIED, AgentRole.BOOKING
    elif action == "follow_up":
        lead.current_agent = AgentRole.FOLLOWUP
    elif action == "safety_message":
        lead.status, lead.current_agent = LeadStatus.AGENT_HANDOFF, AgentRole.SAFETY
    elif next_agent:
        lead.current_agent = next_agent

    lead.agent_reason = decision.get("reason") or action
    lead.updated_at = datetime.now(timezone.utc)
    save_lead(lead)

    tool_results = execute_tools(action, lead, tenant, message)
    _event(lead, "agent_action_executed", agent=role.value, action=action, tools=tool_results)
    _event(lead, "agent_decision", agent=role.value, action=action, next_agent=lead.current_agent.value if lead.current_agent else None, message=message, confidence=decision.get("confidence"), reasoning_source="llm_or_safe_fallback")
    return {"action": action, "message": message, "next_agent": lead.current_agent.value if lead.current_agent else None, "reason": lead.agent_reason, "confidence": decision.get("confidence"), "tools": tool_results}
