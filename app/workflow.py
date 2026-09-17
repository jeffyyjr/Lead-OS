from datetime import datetime, timezone

from app.agents import handoff_to_agent
from app.models import AgentRole, Lead, LeadReply, LeadStatus, TenantConfig, WorkflowEvent
from app.store import add_event, save_lead


def demo_tenant() -> TenantConfig:
    return TenantConfig(
        tenant_id="demo-hvac",
        business_name="Demo HVAC Co.",
        service_postal_codes=["19054", "19055", "19056", "19057"],
        booking_url="https://example.com/book",
    )


def record(lead: Lead, event_type: str, **detail):
    add_event(
        WorkflowEvent(
            lead_id=lead.id,
            tenant_id=lead.tenant_id,
            event_type=event_type,
            detail=detail,
        )
    )


def initial_route(lead: Lead, tenant: TenantConfig) -> Lead:
    text = (lead.message or "").lower()
    if any(keyword in text for keyword in tenant.emergency_keywords):
        return handoff_to_agent(lead, AgentRole.SAFETY, "emergency_keyword")
    if not lead.consent_to_contact:
        return handoff_to_agent(lead, AgentRole.CONSENT, "no_contact_consent")

    lead.status = LeadStatus.CONTACTED
    lead.current_agent = AgentRole.QUALIFICATION
    record(lead, "acknowledgement_queued", channel="auto")
    lead.status = LeadStatus.QUALIFYING
    record(lead, "agent_assigned", agent=AgentRole.QUALIFICATION.value)
    lead.updated_at = datetime.now(timezone.utc)
    return save_lead(lead)


def required_questions(lead: Lead, tenant: TenantConfig) -> list[str]:
    questions = []
    if not lead.service_type:
        questions.append("What service do you need help with?")
    if not lead.postal_code:
        questions.append("What ZIP code is the property in?")
    if not lead.urgency:
        questions.append("How urgent is the issue?")
    if not lead.property_type:
        questions.append("Is this a residential or commercial property?")
    if not lead.preferred_time:
        questions.append("What day or time works best for an appointment?")
    return questions


def evaluate_qualification(lead: Lead, tenant: TenantConfig) -> Lead:
    if lead.postal_code and tenant.service_postal_codes and lead.postal_code not in tenant.service_postal_codes:
        return handoff_to_agent(lead, AgentRole.SERVICE_AREA, "outside_service_area")

    missing = required_questions(lead, tenant)
    if not missing:
        lead.status = LeadStatus.QUALIFIED
        lead.current_agent = AgentRole.BOOKING
        lead.agent_reason = "qualified_ready_to_book"
        record(lead, "lead_qualified")
        record(lead, "agent_handoff", agent=AgentRole.BOOKING.value, reason="qualified_ready_to_book")
    else:
        lead.status = LeadStatus.QUALIFYING
        lead.current_agent = AgentRole.QUALIFICATION
        lead.agent_reason = "missing_qualification_fields"
        record(lead, "qualification_pending", missing_count=len(missing), questions=missing)

    lead.updated_at = datetime.now(timezone.utc)
    return save_lead(lead)


def apply_reply(lead: Lead, reply: LeadReply, tenant: TenantConfig) -> Lead:
    text = reply.message.strip().lower()
    if text in {"stop", "unsubscribe", "cancel", "end", "quit"}:
        lead.status = LeadStatus.OPTED_OUT
        lead.consent_to_contact = False
        lead.current_agent = None
        lead.agent_reason = "opted_out"
        record(lead, "opt_out", source="reply")
        return save_lead(lead)

    for postal in tenant.service_postal_codes:
        if postal in text:
            lead.postal_code = postal
            break
    if any(word in text for word in ["today", "asap", "emergency", "urgent"]):
        lead.urgency = "urgent"
    if "residential" in text or "home" in text or "house" in text:
        lead.property_type = "residential"
    elif "commercial" in text or "business" in text:
        lead.property_type = "commercial"

    record(lead, "lead_reply_received", message=reply.message)
    return evaluate_qualification(lead, tenant)


def book_lead(lead: Lead, appointment_time: str, notes: str | None = None) -> Lead:
    if lead.status in {LeadStatus.OPTED_OUT, LeadStatus.WON, LeadStatus.LOST}:
        return lead
    lead.status = LeadStatus.BOOKED
    lead.current_agent = AgentRole.FOLLOWUP
    lead.agent_reason = "appointment_booked"
    lead.updated_at = datetime.now(timezone.utc)
    record(lead, "appointment_booked", appointment_time=appointment_time, notes=notes)
    record(lead, "agent_handoff", agent=AgentRole.FOLLOWUP.value, reason="appointment_booked")
    return save_lead(lead)


def schedule_followups(lead: Lead, tenant: TenantConfig) -> list[dict]:
    if lead.status in {LeadStatus.BOOKED, LeadStatus.OPTED_OUT, LeadStatus.WON, LeadStatus.LOST}:
        return []
    lead.current_agent = AgentRole.FOLLOWUP
    jobs = [{"lead_id": lead.id, "after_days": day, "action": "agent_follow_up"} for day in tenant.follow_up_days]
    record(lead, "followups_scheduled", schedule=jobs, agent=AgentRole.FOLLOWUP.value)
    save_lead(lead)
    return jobs
