from dotenv import load_dotenv
load_dotenv()

import os
import secrets

from fastapi import FastAPI, Header, HTTPException

from app.agents import run_agent
from app.models import BookingRequest, Lead, LeadCreate, LeadReply, LeadStatus, TenantConfig
from app.store import find_duplicate, get_lead, get_tenant, init_db, list_events, list_tenants, save_lead, save_tenant
from app.workflow import apply_reply, book_lead, demo_tenant, evaluate_qualification, initial_route, required_questions, schedule_followups

app = FastAPI(title="Lead-OS", version="0.4.0")


@app.on_event("startup")
def startup():
    init_db()
    if not get_tenant(demo_tenant().tenant_id):
        save_tenant(demo_tenant())


def tenant_for(tenant_id: str) -> TenantConfig:
    tenant = get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    return tenant


def require_admin(x_admin_key: str | None) -> None:
    """Tenant settings (like the booking link sent to customers) need ADMIN_API_KEY to change."""
    expected = os.getenv("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="invalid admin key")


@app.get("/api/tenants", response_model=list[TenantConfig])
def read_tenants(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return list_tenants()


@app.get("/api/tenants/{tenant_id}", response_model=TenantConfig)
def read_tenant(tenant_id: str, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    return tenant_for(tenant_id)


@app.put("/api/tenants/{tenant_id}", response_model=TenantConfig)
def upsert_tenant(tenant_id: str, payload: TenantConfig, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    if payload.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id in body must match the URL")
    return save_tenant(payload)


@app.get("/")
def root():
    return {"service": "Lead-OS", "status": "running", "version": "0.4.0", "mode": "autonomous_agent_reasoning"}


@app.get("/health")
def health():
    return {"ok": True, "mode": "autonomous_agent_reasoning"}


@app.post("/api/leads", response_model=Lead)
def create_lead(payload: LeadCreate):
    if not payload.phone and not payload.email:
        raise HTTPException(status_code=400, detail="phone or email is required")
    existing = find_duplicate(payload.tenant_id, payload.phone, payload.email)
    if existing:
        return existing
    tenant = tenant_for(payload.tenant_id)
    lead = Lead(**payload.model_dump())
    save_lead(lead)
    lead = initial_route(lead, tenant)
    if lead.status == LeadStatus.QUALIFYING:
        lead = evaluate_qualification(lead, tenant)
    if lead.status == LeadStatus.AGENT_HANDOFF:
        run_agent(lead, tenant)
        lead = get_lead(lead.id) or lead
    return lead


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
    return {"questions": required_questions(lead, tenant_for(lead.tenant_id))}


@app.post("/api/leads/{lead_id}/reply", response_model=Lead)
def reply_to_lead(lead_id: str, payload: LeadReply):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    updated = apply_reply(lead, payload, tenant_for(lead.tenant_id))
    if updated.status == LeadStatus.AGENT_HANDOFF:
        run_agent(updated, tenant_for(lead.tenant_id))
        updated = get_lead(updated.id) or updated
    return updated


@app.post("/api/leads/{lead_id}/agent/run")
def execute_agent(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    result = run_agent(lead, tenant_for(lead.tenant_id))
    return {"lead": get_lead(lead_id), "agent_result": result}


@app.post("/api/leads/{lead_id}/agent/loop")
def execute_agent_loop(lead_id: str, max_steps: int = 5):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    max_steps = max(1, min(max_steps, 10))
    results = []
    for _ in range(max_steps):
        lead = get_lead(lead_id) or lead
        if not lead.current_agent or lead.status in {LeadStatus.BOOKED, LeadStatus.WON, LeadStatus.LOST, LeadStatus.OPTED_OUT}:
            break
        signature = (lead.status, lead.current_agent)
        result = run_agent(lead, tenant_for(lead.tenant_id))
        results.append(result)
        updated = get_lead(lead_id) or lead
        # Stop once the customer has been messaged (wait for their reply)
        # or the agent made no progress, so the same message never repeats.
        if result.get("message") or (updated.status, updated.current_agent) == signature:
            break
    return {"lead": get_lead(lead_id), "steps": results}


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
    return {"jobs": schedule_followups(lead, tenant_for(lead.tenant_id))}


@app.post("/api/leads/{lead_id}/opt-out", response_model=Lead)
def opt_out(lead_id: str):
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    lead.status = LeadStatus.OPTED_OUT
    lead.consent_to_contact = False
    lead.current_agent = None
    lead.agent_reason = "opted_out"
    return save_lead(lead)


@app.post("/api/demo/hvac", response_model=Lead)
def demo_hvac():
    payload = LeadCreate(tenant_id="demo-hvac", source="website", name="Demo Homeowner", phone="+15555550123", service_type="AC repair", postal_code="19054", urgency="today", property_type="residential", preferred_time="this afternoon", message="My AC stopped working and the house is getting hot.", consent_to_contact=True)
    existing = find_duplicate(payload.tenant_id, payload.phone, payload.email)
    if existing:
        return existing
    lead = Lead(**payload.model_dump())
    save_lead(lead)
    lead = initial_route(lead, tenant_for(lead.tenant_id))
    return evaluate_qualification(lead, tenant_for(lead.tenant_id))
