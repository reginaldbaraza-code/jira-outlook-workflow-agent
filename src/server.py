"""
FastAPI webhook listener for Jira events.

Receives Jira webhooks, parses them, and routes through the rule engine.

Run:
    uvicorn src.server:app --port 8080
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from src.connectors.jira_webhook import JiraWebhookParser

app = FastAPI(
    title="Jira-Outlook Workflow Agent",
    description="Webhook listener for Jira→Outlook workflow automation",
    version="0.1.0",
)

parser = JiraWebhookParser()


@app.get("/")
async def root():
    """Health check."""
    return {
        "service": "Jira-Outlook Workflow Agent",
        "status": "healthy",
        "version": "0.1.0",
    }


@app.post("/webhook/jira")
async def handle_jira_webhook(request: Request):
    """
    Receive and process Jira webhooks.

    In production, this:
    1. Validates the webhook signature
    2. Parses the event
    3. Runs it through the rule engine
    4. Returns results
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = parser.parse(payload)

    # In production: engine.process_event(event)
    return {
        "status": "received",
        "event_type": event.event_type,
        "issue_key": event.issue_key,
        "project": event.project_key,
    }


@app.get("/rules")
async def list_rules():
    """List active rules (placeholder)."""
    return {
        "count": 0,
        "rules": [],
        "message": "Load rules via config to populate",
    }


@app.get("/audit")
async def get_audit_log():
    """Get recent audit entries (placeholder)."""
    return {
        "entries": [],
        "total": 0,
    }
