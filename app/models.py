from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    AGENT_HANDOFF = "agent_handoff"
    BOOKED = "booked"
    ESTIMATE_COMPLETED = "estimate_completed"
    WON = "won"
    LOST = "lost"
    REENGAGEMENT = "reengagement"
    OPTED_OUT = "opted_out"


class AgentRole(str, Enum):
    QUALIFICATION = "qualification_agent"
    BOOKING = "booking_agent"
    SERVICE_AREA = "service_area_agent"
    SAFETY = "safety_agent"
    CONSENT = "consent_agent"
    FOLLOWUP = "followup_agent"


class TenantConfig(BaseModel):
    tenant_id: str
    business_name: str
    timezone: str = "America/New_York"
    service_postal_codes: list[str] = Field(default_factory=list)
    booking_url: Optional[str] = None
    emergency_keywords: list[str] = Field(default_factory=lambda: ["gas leak", "smoke", "sparks", "carbon monoxide"])
    follow_up_days: list[int] = Field(default_factory=lambda: [1, 3, 7, 14])


class LeadCreate(BaseModel):
    tenant_id: str = "demo-hvac"
    source: str = "web"
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    service_type: Optional[str] = None
    postal_code: Optional[str] = None
    urgency: Optional[str] = None
    property_type: Optional[str] = None
    preferred_time: Optional[str] = None
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
    property_type: Optional[str] = None
    preferred_time: Optional[str] = None
    message: Optional[str] = None
    consent_to_contact: bool = False
    status: LeadStatus = LeadStatus.NEW
    current_agent: Optional[AgentRole] = None
    agent_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeadReply(BaseModel):
    message: str


class BookingRequest(BaseModel):
    appointment_time: str
    notes: Optional[str] = None


class WorkflowEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    tenant_id: str
    event_type: str
    detail: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
