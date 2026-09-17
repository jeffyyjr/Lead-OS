import json
import sqlite3
from pathlib import Path
from typing import Optional

from app.models import Lead, WorkflowEvent

DB_PATH = Path("data/lead_os.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )


def save_lead(lead: Lead) -> Lead:
    payload = lead.model_dump(mode="json")
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO leads (id, tenant_id, phone, email, payload) VALUES (?, ?, ?, ?, ?)",
            (lead.id, lead.tenant_id, lead.phone, lead.email, json.dumps(payload)),
        )
    return lead


def get_lead(lead_id: str) -> Optional[Lead]:
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return Lead.model_validate(json.loads(row["payload"])) if row else None


def find_duplicate(tenant_id: str, phone: str | None, email: str | None) -> Optional[Lead]:
    with _connect() as conn:
        if phone:
            row = conn.execute(
                "SELECT payload FROM leads WHERE tenant_id = ? AND phone = ? LIMIT 1",
                (tenant_id, phone),
            ).fetchone()
            if row:
                return Lead.model_validate(json.loads(row["payload"]))
        if email:
            row = conn.execute(
                "SELECT payload FROM leads WHERE tenant_id = ? AND email = ? LIMIT 1",
                (tenant_id, email),
            ).fetchone()
            if row:
                return Lead.model_validate(json.loads(row["payload"]))
    return None


def add_event(event: WorkflowEvent) -> WorkflowEvent:
    payload = event.model_dump(mode="json")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (id, lead_id, tenant_id, event_type, payload) VALUES (?, ?, ?, ?, ?)",
            (event.id, event.lead_id, event.tenant_id, event.event_type, json.dumps(payload)),
        )
    return event


def list_events(lead_id: str) -> list[WorkflowEvent]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM events WHERE lead_id = ? ORDER BY rowid ASC",
            (lead_id,),
        ).fetchall()
    return [WorkflowEvent.model_validate(json.loads(row["payload"])) for row in rows]
