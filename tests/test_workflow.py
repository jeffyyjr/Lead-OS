from app.agents import run_agent
from app.models import AgentRole, Lead, LeadCreate, LeadReply, LeadStatus
from app.workflow import apply_reply, book_lead, demo_tenant, evaluate_qualification, initial_route


def test_golden_path_qualifies_and_books():
    tenant = demo_tenant()
    lead = Lead(**LeadCreate(
        name="Test Homeowner",
        phone="+15555550001",
        service_type="AC repair",
        postal_code="19054",
        urgency="today",
        property_type="residential",
        preferred_time="tomorrow morning",
        consent_to_contact=True,
    ).model_dump())

    initial_route(lead, tenant)
    evaluate_qualification(lead, tenant)
    assert lead.status == LeadStatus.QUALIFIED
    assert lead.current_agent == AgentRole.BOOKING

    book_lead(lead, "2026-09-18T09:00:00-04:00")
    assert lead.status == LeadStatus.BOOKED
    assert lead.current_agent == AgentRole.FOLLOWUP


def test_stop_reply_opts_out():
    tenant = demo_tenant()
    lead = Lead(**LeadCreate(name="Test", phone="+15555550002", consent_to_contact=True).model_dump())
    initial_route(lead, tenant)
    apply_reply(lead, LeadReply(message="STOP"), tenant)
    assert lead.status == LeadStatus.OPTED_OUT
    assert lead.consent_to_contact is False
    assert lead.current_agent is None


def test_outside_service_area_routes_to_agent_and_closes():
    tenant = demo_tenant()
    lead = Lead(**LeadCreate(
        name="Outside Area",
        phone="+15555550003",
        postal_code="99999",
        service_type="AC repair",
        urgency="today",
        property_type="residential",
        preferred_time="today",
        consent_to_contact=True,
    ).model_dump())
    evaluate_qualification(lead, tenant)
    assert lead.status == LeadStatus.AGENT_HANDOFF
    assert lead.current_agent == AgentRole.SERVICE_AREA
    result = run_agent(lead, tenant)
    assert result["action"] == "close_out_of_area"
    assert lead.status == LeadStatus.LOST


def test_emergency_routes_to_safety_agent():
    tenant = demo_tenant()
    lead = Lead(**LeadCreate(
        name="Emergency",
        phone="+15555550004",
        message="I smell a gas leak",
        consent_to_contact=True,
    ).model_dump())
    initial_route(lead, tenant)
    assert lead.status == LeadStatus.AGENT_HANDOFF
    assert lead.current_agent == AgentRole.SAFETY
    result = run_agent(lead, tenant)
    # Sends the preapproved safety script and pauses sales automation.
    assert result["action"] == "safety_message"
    assert "emergency" in result["message"]
    assert "booking" not in result["tools"]
    assert lead.status == LeadStatus.AGENT_HANDOFF
    assert lead.current_agent == AgentRole.SAFETY
