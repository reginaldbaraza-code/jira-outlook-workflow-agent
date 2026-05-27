# Jira-Outlook Workflow Agent 🔄

A rule engine that listens for Jira webhook events and automatically performs Outlook calendar/email actions. Define rules in YAML (trigger → conditions → actions), and the engine handles the rest. For ambiguous situations, it escalates to an LLM for a decision.

## The Problem

If you run a threat modeling service, you spend a surprising amount of time on the glue between tools:

- High-priority ticket lands → you manually create a 90-minute calendar invite with the right people
- Ticket gets rescheduled → you manually update the meeting
- Assessment is completed → you manually send a follow-up email to the team
- An SLA is about to breach → you manually check calendars for an urgent slot

This project replaces that manual glue with declarative rules.

## How It Works

```
Jira Webhooks ──▶ Rule Engine ──▶ Outlook Calendar / Email
                      │
                  LLM Fallback ──▶ Audit Log
```

1. Jira fires a webhook when a ticket changes (created, updated, status transition)
2. The webhook parser extracts the event into a structured `JiraEvent` object
3. The rule engine evaluates every active rule against the event
4. For each matching rule, it executes the actions (create meeting, send email, add comment)
5. Everything is logged in the audit trail for compliance

For edge cases (scheduling conflicts, ambiguous priority), a rule can escalate to the LLM agent, which reasons about the situation and suggests the best course of action.

## Rule Definition

Rules live in a YAML file. Each rule has a trigger (what event to watch for), conditions (what to check), and actions (what to do):

```yaml
rules:
  - name: schedule_critical_tm
    description: Auto-create calendar invite for critical TM requests
    trigger:
      event: issue_updated
      project: TM
      field_changed: status
      new_value: Scheduled
    conditions:
      - field: priority
        operator: in
        value: [Critical, High]
      - field: assignee
        operator: exists
    actions:
      - type: create_calendar_event
        params:
          title: "Threat Model: {issue.summary}"
          duration_minutes: 90
          attendees:
            - "{issue.assignee.email}"
            - "{issue.reporter.email}"
      - type: add_jira_comment
        params:
          text: "📅 Calendar invite sent to {issue.assignee}"
```

Template variables (`{issue.key}`, `{issue.summary}`, `{issue.assignee.email}`) are resolved from the Jira event at runtime.

## Supported Condition Operators

`eq`, `neq`, `in`, `not_in`, `exists`, `not_exists`, `contains`, `gt`, `lt`, `matches` (regex)

## Supported Action Types

`create_calendar_event`, `update_calendar_event`, `cancel_calendar_event`, `send_email`, `add_jira_comment`, `update_jira_field`, `escalate_to_llm`

## Quick Start

```bash
git clone https://github.com/reginaldbaraza-code/jira-outlook-workflow-agent.git
cd jira-outlook-workflow-agent
pip install -e ".[dev]"

# Run all 28 tests
pytest -v

# Start the webhook listener
uvicorn src.server:app --port 8080

# See example rules
cat rules.yaml.example
```

## Project Structure

```
jira-outlook-workflow-agent/
├── src/
│   ├── rules/
│   │   ├── models.py          # Rule, Trigger, Condition, Action, JiraEvent dataclasses
│   │   ├── engine.py          # Rule evaluation + action dispatch + dry-run mode
│   │   └── parser.py          # YAML rule file parser
│   ├── connectors/
│   │   ├── jira_webhook.py    # Parses Jira webhook payloads into JiraEvent objects
│   │   ├── outlook.py         # Outlook calendar/email via MS Graph API interface
│   │   └── audit.py           # Action audit logger with success rate tracking
│   ├── agent/
│   │   └── reasoning.py       # LLM reasoning for edge cases (Anthropic API)
│   └── server.py              # FastAPI webhook listener at /webhook/jira
├── tests/
│   └── test_rules_engine.py   # 28 tests covering all modules
├── rules.yaml.example         # 3 example rules (schedule, alert, LLM escalation)
└── pyproject.toml
```

## Tech Stack

- **Python 3.11+**, **FastAPI**, **PyYAML**, **httpx**, **Anthropic SDK**, **pytest** (28 tests)

## License

MIT
