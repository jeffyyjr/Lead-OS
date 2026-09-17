from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Lead-OS", version="0.1.0")


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    BOOKED = "booked"
    HUMAN_REVIEW = "human_review"
    OPTED_OUT = "opted_out"


class LeadCreate(BaseModel):
    tenant_id: str = "demo-hvac"
    source: str = "web"
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    service_type: Optional[str] = None
    postal_code: Optional[str] = None
    urgency: Optional[str] = None
    message: Optional[str] = None
    consent_to_contact: bool = False


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    source: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    service_type: Optional[str] = None
    postal_code: Optional[str] = None
    urgency: Optional[str] = None
    message: Optional[str] = None
    consent_to_contact: bool = False
    status: LeadStatus = LeadStatus.NEW
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


LEADS: dict[str, Lead] = {}


@app.get("/")
def root():
    return {"service": "Lead-OS", "status": "running", "version": "0.1.0"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/leads", response_model=Lead)
def create_lead(payload: LeadCreate):
    if not payload.phone and not payload.email:
        raise HTTPException(status_code=400, detail="phone or email is required")

    # Simple MVP deduplication by tenant + phone/email.
    for existing in LEADS.values():
        if existing.tenant_id != payload.tenant_id:
            continue
        if payload.phone and existing.phone == payload.phone:
            return existing
        if payload.email and existing.email == payload.email:
            return existing

    lead = Lead(**payload.model_dump())
    lead.status = LeadStatus.CONTACTED if payload.consent_to_contact else LeadStatus.HUMAN_REVIEW
    LEADS[lead.id] = lead
    return lead


@app.get("/api/leads/{lead_id}", response_model=Lead)
def get_lead(lead_id: str):
    lead = LEADS.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@app.post("/api/leads/{lead_id}/opt-out", response_model=Lead)
def opt_out(lead_id: str):
    lead = LEADS.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    lead.status = LeadStatus.OPTED_OUT
    lead.consent_to_contact = False
    lead.updated_at = datetime.now(timezone.utc)
    return lead


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
        message="My AC stopped working and the house is getting hot.",
        consent_to_contact=True,
    )
    lead = Lead(**payload.model_dump(), status=LeadStatus.QUALIFYING)
    LEADS[lead.id] = lead
    return lead
