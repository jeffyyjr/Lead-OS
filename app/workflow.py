from datetime import datetime, timezone

from app.models import Lead, LeadReply, LeadStatus, TenantConfig, WorkflowEvent
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
        lead.status = LeadStatus.HUMAN_REVIEW
        record(lead, "human_escalation", reason="emergency_keyword")
    elif not lead.consent_to_contact:
        lead.status = LeadStatus.HUMAN_REVIEW
        record(lead, "human_escalation", reason="no_contact_consent")
    else:
        lead.status = LeadStatus.CONTACTED
        record(lead, "acknowledgement_queued", channel="auto")
        lead.status = LeadStatus.QUALIFYING
        record(lead, "qualification_started")
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
        lead.status = LeadStatus.HUMAN_REVIEW
        record(lead, "human_escalation", reason="outside_service_area", postal_code=lead.postal_code)
    elif not required_questions(lead, tenant):
        lead.status = LeadStatus.QUALIFIED
        record(lead, "lead_qualified")
    else:
        lead.status = LeadStatus.QUALIFYING
        record(lead, "qualification_pending", missing_count=len(required_questions(lead, tenant)))
    lead.updated_at = datetime.now(timezone.utc)
    return save_lead(lead)


def apply_reply(lead: Lead, reply: LeadReply, tenant: TenantConfig) -> Lead:
    text = reply.message.strip().lower()
    if text in {"stop", "unsubscribe", "cancel", "end", "quit"}:
        lead.status = LeadStatus.OPTED_OUT
        lead.consent_to_contact = False
        record(lead, "opt_out", source="reply")
        return save_lead(lead)

    # Deterministic MVP extraction. AI extraction can replace/augment this later.
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
    lead.updated_at = datetime.now(timezone.utc)
    record(lead, "appointment_booked", appointment_time=appointment_time, notes=notes)
    return save_lead(lead)


def schedule_followups(lead: Lead, tenant: TenantConfig) -> list[dict]:
    if lead.status in {LeadStatus.BOOKED, LeadStatus.OPTED_OUT, LeadStatus.WON, LeadStatus.LOST}:
        return []
    jobs = [{"lead_id": lead.id, "after_days": day, "action": "follow_up"} for day in tenant.follow_up_days]
    record(lead, "followups_scheduled", schedule=jobs)
    return jobs
