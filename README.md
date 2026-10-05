# Lead-OS
Automate sales, sale calls, emails and leads

## Run locally

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env    # then fill in values
.venv\Scripts\uvicorn app.main:app --reload
```

Run tests with `.venv\Scripts\python -m pytest`.

## Settings

| Setting | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | Turns on the Claude agent brain. Without it, scripted replies are used. |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Sends customer messages by Gmail (app password, not your normal password). |
| `DATABASE_URL` | Postgres connection string. Without it, a local SQLite file in `data/` is used. |
| `ADMIN_API_KEY` | Required to view or change business (tenant) settings. |
| `MESSAGING_WEBHOOK_URL`, `CRM_WEBHOOK_URL` | Optional webhooks for SMS and CRM sync. |

## Businesses (tenants)

Each lead belongs to a business via `tenant_id`. A demo business, `demo-hvac`, is created on startup.
Add or update one with the admin key:

```
curl -X PUT https://YOUR-APP.onrender.com/api/tenants/acme-plumbing \
  -H "X-Admin-Key: YOUR_ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"tenant_id": "acme-plumbing", "business_name": "Acme Plumbing", "service_postal_codes": ["10001", "10002"], "booking_url": "https://acme.example/book"}'
```
