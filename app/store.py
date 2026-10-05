import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.models import Lead, TenantConfig, WorkflowEvent

# Postgres when DATABASE_URL is set (e.g. on Render), otherwise a local SQLite file.
DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = Path("data/lead_os.db")


@contextmanager
def _connect():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            yield _Conn(conn, "%s")
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield _Conn(conn, "?")
        finally:
            conn.close()


class _Conn:
    """Lets queries be written with ? placeholders for both SQLite and Postgres."""

    def __init__(self, conn, placeholder: str):
        self.conn = conn
        self.placeholder = placeholder

    def execute(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql.replace("?", self.placeholder), params)


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )


def save_lead(lead: Lead) -> Lead:
    payload = lead.model_dump(mode="json")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO leads (id, tenant_id, phone, email, payload) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET tenant_id = excluded.tenant_id, phone = excluded.phone,
                email = excluded.email, payload = excluded.payload
            """,
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
        rows = conn.execute("SELECT payload FROM events WHERE lead_id = ?", (lead_id,)).fetchall()
    events = [WorkflowEvent.model_validate(json.loads(row["payload"])) for row in rows]
    return sorted(events, key=lambda event: event.created_at)


def save_tenant(tenant: TenantConfig) -> TenantConfig:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tenants (tenant_id, payload) VALUES (?, ?)
            ON CONFLICT (tenant_id) DO UPDATE SET payload = excluded.payload
            """,
            (tenant.tenant_id, tenant.model_dump_json()),
        )
    return tenant


def get_tenant(tenant_id: str) -> Optional[TenantConfig]:
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
    return TenantConfig.model_validate_json(row["payload"]) if row else None


def list_tenants() -> list[TenantConfig]:
    with _connect() as conn:
        rows = conn.execute("SELECT payload FROM tenants ORDER BY tenant_id").fetchall()
    return [TenantConfig.model_validate_json(row["payload"]) for row in rows]
