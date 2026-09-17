from fastapi import FastAPI, HTTPException

from app.models import BookingRequest, Lead, LeadCreate, LeadReply, LeadStatus
from app.store import find_duplicate, get_lead, init_db, list_events, save_lead
from app.workflow import (
    apply_reply,
    book_lead,
    demo_tenant,
    initial_route,
    required_questions,
    schedule_followups,
)

app = FastAPI(title="Lead-OS", version="0.2.0")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"service": "Lead-OS", "status": "running", "version": "0.2.0"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/leads", response_model=Lead)
def create_lead(payload: LeadCreate):
    if not payload.phone and not payload.email:
        raise HTTPException(status_code=400, detail="phone or email is required")

    existing = find_duplicate(payload.tenant_id, payload.phone, payload.email)
    if existing:
        return existing

    tenant = demo_tenant()
    lead = Lead(**payload.model_dump())
    save_lead(lead)
    return initial_route(lead, tenant)


@app.get("/api/leads/{lead_id}", response_model=Lead)
def read_lead(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@app.get("/api/leads/{lead_id}/events")
def read_events(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return list_events(lead_id)


@app.get("/api/leads/{lead_id}/questions")
def qualification_questions(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return {"questions": required_questions(lead, demo_tenant())}


@app.post("/api/leads/{lead_id}/reply", response_model=Lead)
def reply_to_lead(lead_id: str, payload: LeadReply):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return apply_reply(lead, payload, demo_tenant())


@app.post("/api/leads/{lead_id}/book", response_model=Lead)
def book(lead_id: str, payload: BookingRequest):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return book_lead(lead, payload.appointment_time, payload.notes)


@app.post("/api/leads/{lead_id}/followups")
def create_followups(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return {"jobs": schedule_followups(lead, demo_tenant())}


@app.post("/api/leads/{lead_id}/opt-out", response_model=Lead)
def opt_out(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    lead.status = LeadStatus.OPTED_OUT
    lead.consent_to_contact = False
    return save_lead(lead)


@app.post("/api/demo/hvac", response_model=Lead)
def demo_hvac():
    payload = LeadCreate(
        tenant_id="demo-hvac",
        source="website",
        name="Demo Homeowner",
        phone="+15555550123",
        service_type="AC repair",
        postal_code="19054",
        urgency="today",
        property_type="residential",
        preferred_time="this afternoon",
        message="My AC stopped working and the house is getting hot.",
        consent_to_contact=True,
    )
    existing = find_duplicate(payload.tenant_id, payload.phone, payload.email)
    if existing:
        return existing
    lead = Lead(**payload.model_dump())
    save_lead(lead)
    lead = initial_route(lead, demo_tenant())
    from app.workflow import evaluate_qualification
    return evaluate_qualification(lead, demo_tenant())
