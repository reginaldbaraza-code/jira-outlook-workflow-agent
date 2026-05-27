"""
FastAPI webhook listener for Jira events.

Receives Jira webhooks, parses them, and routes through the rule engine.

Run:
    uvicorn src.server:app --port 8080
"""

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException

from src.connectors.jira_webhook import JiraWebhookParser
from src.connectors.outlook import OutlookConnector
from src.rules.engine import RuleEngine
from src.rules.parser import RuleParser

app = FastAPI(
    title="Jira-Outlook Workflow Agent",
    description="Webhook listener for Jira→Outlook workflow automation",
    version="0.1.0",
)

parser = JiraWebhookParser()
rules_file = Path("rules.yaml")
outlook_connector = OutlookConnector()
engine = RuleEngine(rules=[], connectors={"outlook": outlook_connector})


def reload_rules() -> int:
    """Load rules from rules.yaml and refresh the engine."""
    if not rules_file.exists():
        engine.rules = []
        return 0

    engine.rules = sorted(RuleParser.from_file(rules_file), key=lambda r: r.priority)
    return len(engine.rules)


def serialize_results(results):
    """Convert RuleResult objects into JSON-safe dictionaries."""
    return [
        {
            "rule_name": result.rule_name,
            "fired": result.fired,
            "skipped_reason": result.skipped_reason,
            "actions": [
                {
                    "action_type": action.action_type,
                    "success": action.success,
                    "message": action.message,
                    "details": action.details,
                    "timestamp": action.timestamp,
                }
                for action in result.actions
            ],
        }
        for result in results
    ]


@app.get("/")
async def root():
    """Health check."""
    return {
        "service": "Jira-Outlook Workflow Agent",
        "status": "healthy",
        "version": "0.1.0",
        "rules_loaded": len(engine.rules),
        "rules_file": str(rules_file),
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
    results = engine.process_event(event)

    fired_count = sum(1 for r in results if r.fired)

    return {
        "status": "processed",
        "event_type": event.event_type,
        "issue_key": event.issue_key,
        "project": event.project_key,
        "rules_evaluated": len(results),
        "rules_fired": fired_count,
        "results": serialize_results(results),
    }


@app.get("/rules")
async def list_rules():
    """List active rules loaded from rules.yaml."""
    return {
        "count": len(engine.rules),
        "rules": [
            {
                "name": rule.name,
                "description": rule.description,
                "enabled": rule.enabled,
                "priority": rule.priority,
                "trigger": {
                    "event": rule.trigger.event,
                    "project": rule.trigger.project,
                    "field_changed": rule.trigger.field_changed,
                    "new_value": rule.trigger.new_value,
                    "old_value": rule.trigger.old_value,
                },
                "conditions": [
                    {
                        "field": condition.field,
                        "operator": condition.operator,
                        "value": condition.value,
                    }
                    for condition in rule.conditions
                ],
                "actions": [
                    {"type": action.type, "params": action.params, "on_error": action.on_error}
                    for action in rule.actions
                ],
            }
            for rule in engine.rules
        ],
    }


@app.post("/rules/reload")
async def reload_rules_endpoint():
    """Reload rules from disk without restarting the server."""
    count = reload_rules()
    return {
        "status": "reloaded",
        "count": count,
        "rules_file": str(rules_file),
    }


@app.get("/audit")
async def get_audit_log():
    """Get recent audit entries (placeholder)."""
    return {
        "entries": [],
        "total": 0,
    }


@app.on_event("startup")
async def startup_event():
    """Load rules on service startup."""
    reload_rules()
