import json
import os
import urllib.parse
import urllib.request
from typing import Any

from app.models import Lead, TenantConfig


def send_customer_message(lead: Lead, message: str | None) -> dict[str, Any]:
    """Send through a configured webhook, or safely simulate when no provider is configured."""
    if not message:
        return {"ok": True, "mode": "none", "sent": False}
    if not lead.consent_to_contact:
        return {"ok": False, "mode": "blocked", "sent": False, "reason": "no_contact_consent"}
    webhook = os.getenv("MESSAGING_WEBHOOK_URL")
    if not webhook:
        return {"ok": True, "mode": "simulation", "sent": False, "message": message}
    payload = json.dumps({"lead_id": lead.id, "phone": lead.phone, "email": lead.email, "message": message}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return {"ok": 200 <= response.status < 300, "mode": "webhook", "sent": True, "status": response.status}
    except Exception as exc:
        return {"ok": False, "mode": "webhook", "sent": False, "error": type(exc).__name__}


def booking_action(lead: Lead, tenant: TenantConfig) -> dict[str, Any]:
    """Return the configured booking destination. Never invent calendar availability."""
    if not tenant.booking_url:
        return {"ok": False, "mode": "unconfigured", "reason": "booking_provider_not_configured"}
    return {"ok": True, "mode": "booking_link", "booking_url": tenant.booking_url}


def update_crm(lead: Lead, event: str) -> dict[str, Any]:
    webhook = os.getenv("CRM_WEBHOOK_URL")
    if not webhook:
        return {"ok": True, "mode": "simulation", "synced": False}
    payload = json.dumps({"event": event, "lead": lead.model_dump(mode="json")}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return {"ok": 200 <= response.status < 300, "mode": "webhook", "synced": True, "status": response.status}
    except Exception as exc:
        return {"ok": False, "mode": "webhook", "synced": False, "error": type(exc).__name__}


def execute_tools(action: str, lead: Lead, tenant: TenantConfig, message: str | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if action in {"ask_question", "follow_up", "safety_message", "close_out_of_area"}:
        results["messaging"] = send_customer_message(lead, message)
    elif action == "offer_booking":
        booking = booking_action(lead, tenant)
        results["booking"] = booking
        booking_message = message
        if booking.get("ok") and booking.get("booking_url"):
            booking_message = f"{message or 'You’re ready to schedule.'} {booking['booking_url']}"
        results["messaging"] = send_customer_message(lead, booking_message)
    results["crm"] = update_crm(lead, action)
    return results
