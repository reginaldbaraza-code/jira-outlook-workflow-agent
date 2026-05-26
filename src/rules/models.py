"""
Rule data models.

Defines the structure for declarative workflow rules:
- Rule: a named trigger→conditions→actions pipeline
- Condition: a field comparison predicate
- Action: an operation to perform when conditions are met
- JiraEvent: parsed webhook event payload

Usage:
    rule = Rule(
        name="auto_schedule",
        trigger=Trigger(event="issue_updated", project="TM"),
        conditions=[Condition(field="priority", operator="in", value=["Critical"])],
        actions=[Action(type="create_calendar_event", params={...})],
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventType(Enum):
    """Jira webhook event types we handle."""

    ISSUE_CREATED = "issue_created"
    ISSUE_UPDATED = "issue_updated"
    ISSUE_DELETED = "issue_deleted"
    COMMENT_CREATED = "comment_created"


class ActionType(Enum):
    """Supported action types."""

    CREATE_CALENDAR_EVENT = "create_calendar_event"
    UPDATE_CALENDAR_EVENT = "update_calendar_event"
    CANCEL_CALENDAR_EVENT = "cancel_calendar_event"
    SEND_EMAIL = "send_email"
    ADD_JIRA_COMMENT = "add_jira_comment"
    UPDATE_JIRA_FIELD = "update_jira_field"
    ESCALATE_TO_LLM = "escalate_to_llm"


class Operator(Enum):
    """Comparison operators for conditions."""

    EQUALS = "eq"
    NOT_EQUALS = "neq"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    CONTAINS = "contains"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    MATCHES = "matches"  # Regex


@dataclass
class Trigger:
    """Defines when a rule should be evaluated."""

    event: str
    project: str = ""
    field_changed: str = ""
    new_value: str = ""
    old_value: str = ""

    def matches_event(self, jira_event: "JiraEvent") -> bool:
        """Check if this trigger matches a Jira event."""
        if self.event != jira_event.event_type:
            return False
        if self.project and self.project != jira_event.project_key:
            return False
        if self.field_changed:
            change = jira_event.changes.get(self.field_changed, {})
            if not change:
                return False
            if self.new_value and change.get("to") != self.new_value:
                return False
            if self.old_value and change.get("from") != self.old_value:
                return False
        return True


@dataclass
class Condition:
    """A predicate that must be true for a rule to fire."""

    field: str
    operator: str  # One of Operator values
    value: Any = None

    def evaluate(self, context: dict) -> bool:
        """Evaluate this condition against an event context."""
        actual = self._resolve_field(context, self.field)
        op = self.operator

        if op == "eq":
            return actual == self.value
        elif op == "neq":
            return actual != self.value
        elif op == "in":
            return actual in self.value
        elif op == "not_in":
            return actual not in self.value
        elif op == "exists":
            return actual is not None and actual != ""
        elif op == "not_exists":
            return actual is None or actual == ""
        elif op == "contains":
            return isinstance(actual, str) and self.value in actual
        elif op == "gt":
            return actual is not None and actual > self.value
        elif op == "lt":
            return actual is not None and actual < self.value
        elif op == "matches":
            import re
            return bool(re.search(self.value, str(actual or "")))
        else:
            return False

    @staticmethod
    def _resolve_field(context: dict, field_path: str) -> Any:
        """Resolve a dotted field path against a context dict."""
        parts = field_path.split(".")
        current = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


@dataclass
class Action:
    """An operation to perform when a rule fires."""

    type: str  # One of ActionType values
    params: dict = field(default_factory=dict)
    on_error: str = "log"  # "log", "abort", "retry"


@dataclass
class Rule:
    """A complete workflow rule: trigger → conditions → actions."""

    name: str
    trigger: Trigger
    conditions: list[Condition] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    description: str = ""
    enabled: bool = True
    priority: int = 100  # Lower = higher priority

    def should_fire(self, event: "JiraEvent", context: dict) -> bool:
        """Check if this rule should fire for an event."""
        if not self.enabled:
            return False
        if not self.trigger.matches_event(event):
            return False
        return all(c.evaluate(context) for c in self.conditions)


@dataclass
class JiraEvent:
    """A parsed Jira webhook event."""

    event_type: str
    project_key: str
    issue_key: str
    summary: str = ""
    status: str = ""
    priority: str = ""
    assignee: str = ""
    assignee_email: str = ""
    reporter: str = ""
    reporter_email: str = ""
    description: str = ""
    labels: list[str] = field(default_factory=list)
    changes: dict = field(default_factory=dict)  # field_name → {from, to}
    timestamp: str = ""
    raw_payload: dict = field(default_factory=dict)

    def to_context(self) -> dict:
        """Convert to a flat context dict for condition evaluation."""
        return {
            "event_type": self.event_type,
            "project": self.project_key,
            "key": self.issue_key,
            "summary": self.summary,
            "status": self.status,
            "priority": self.priority,
            "assignee": self.assignee,
            "assignee_email": self.assignee_email,
            "reporter": self.reporter,
            "reporter_email": self.reporter_email,
            "description": self.description,
            "labels": self.labels,
        }
