# Jira-Outlook Workflow Agent 🔄

A rule engine that bridges Jira webhooks to Outlook calendar actions, with LLM reasoning for edge cases. Automates the tedious glue work between ticket management and calendar scheduling.

## Problem

Security teams running threat modeling services constantly context-switch between Jira and Outlook:
- New high-priority ticket → manually create a calendar invite
- Ticket rescheduled → manually update the meeting
- Assessment completed → manually send follow-up emails
- SLA approaching → manually check calendar for availability

This agent automates those workflows with a declarative rule engine and an LLM fallback for ambiguous situations.

## Architecture

```
┌──────────────┐     ┌────────────────┐     ┌──────────────────┐
│  Jira        │────▶│  Rule Engine   │────▶│  Outlook         │
│  Webhooks    │     │                │     │  Calendar/Email   │
└──────────────┘     │  ┌──────────┐  │     └──────────────────┘
                     │  │ LLM      │  │
                     │  │ Fallback │  │     ┌──────────────────┐
                     │  └──────────┘  │────▶│  Audit Log       │
                     └────────────────┘     └──────────────────┘
```

## Features

### Rule Engine (`src/rules/`)
- **Declarative rules** — Define trigger→condition→action rules in YAML
- **Event matching** — Match Jira webhook events by type, project, status, priority
- **Condition evaluation** — Combine conditions with AND/OR/NOT logic
- **Action execution** — Create/update/cancel calendar events, send emails
- **Dry-run mode** — Preview actions without executing them

### Connectors (`src/connectors/`)
- **Jira connector** — Parse webhook payloads, extract event metadata
- **Outlook connector** — Calendar CRUD via Microsoft Graph API
- **Audit logger** — Record every action for compliance

### LLM Agent (`src/agent/`)
- **Edge case handler** — Route ambiguous events to LLM for decision
- **Conflict resolver** — Handle scheduling conflicts intelligently
- **Natural language rules** — Convert plain English rules to engine format

## Quick Start

```bash
git clone https://github.com/reginaldbaraza-code/jira-outlook-workflow-agent.git
cd jira-outlook-workflow-agent
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run webhook listener
uvicorn src.server:app --port 8080

# Or run in dry-run mode
python -m src.engine --dry-run --rules rules.yaml
```

## Rule Definition

Rules are defined in YAML with a trigger→condition→action pattern:

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
          body: "TM session for {issue.key}: {issue.summary}"

      - type: add_jira_comment
        params:
          text: "📅 Calendar invite sent to {issue.assignee.displayName}"
```

## Project Structure

```
jira-outlook-workflow-agent/
├── src/
│   ├── rules/
│   │   ├── engine.py       # Rule evaluation engine
│   │   ├── models.py       # Rule, Condition, Action dataclasses
│   │   ├── parser.py       # YAML rule parser
│   │   └── templates.py    # Template variable resolution
│   ├── connectors/
│   │   ├── jira_webhook.py # Jira webhook parser
│   │   ├── outlook.py      # MS Graph calendar/email client
│   │   └── audit.py        # Action audit logger
│   ├── agent/
│   │   ├── reasoning.py    # LLM edge-case reasoning
│   │   └── prompts.py      # Prompt templates
│   └── server.py           # FastAPI webhook listener
├── tests/
├── rules.yaml.example
└── pyproject.toml
```

## Tech Stack

- **Python 3.11+** — Core language
- **FastAPI** — Webhook listener
- **httpx** — Async HTTP client
- **PyYAML** — Rule definition parsing
- **Anthropic SDK** — LLM reasoning fallback
- **pytest** — Testing

## License

MIT
