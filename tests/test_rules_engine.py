"""Tests for rule engine, models, parser, and connectors."""

import pytest

from src.rules.models import (
    Rule, Trigger, Condition, Action, JiraEvent, EventType, ActionType,
)
from src.rules.engine import RuleEngine, ActionResult
from src.rules.parser import RuleParser
from src.connectors.jira_webhook import JiraWebhookParser
from src.connectors.outlook import OutlookConnector, CalendarEvent
from src.connectors.audit import AuditLogger


# === Model Tests ===

class TestTrigger:
    def test_matches_event_type(self):
        trigger = Trigger(event="issue_updated", project="TM")
        event = JiraEvent(event_type="issue_updated", project_key="TM", issue_key="TM-1")
        assert trigger.matches_event(event)

    def test_no_match_wrong_project(self):
        trigger = Trigger(event="issue_updated", project="TM")
        event = JiraEvent(event_type="issue_updated", project_key="DEV", issue_key="DEV-1")
        assert not trigger.matches_event(event)

    def test_matches_field_change(self):
        trigger = Trigger(
            event="issue_updated", project="TM",
            field_changed="status", new_value="Scheduled",
        )
        event = JiraEvent(
            event_type="issue_updated", project_key="TM", issue_key="TM-1",
            changes={"status": {"from": "Triaged", "to": "Scheduled"}},
        )
        assert trigger.matches_event(event)

    def test_no_match_wrong_new_value(self):
        trigger = Trigger(
            event="issue_updated", project="TM",
            field_changed="status", new_value="Closed",
        )
        event = JiraEvent(
            event_type="issue_updated", project_key="TM", issue_key="TM-1",
            changes={"status": {"from": "Triaged", "to": "Scheduled"}},
        )
        assert not trigger.matches_event(event)


class TestCondition:
    def test_equals(self):
        c = Condition(field="priority", operator="eq", value="Critical")
        assert c.evaluate({"priority": "Critical"})
        assert not c.evaluate({"priority": "Low"})

    def test_in_operator(self):
        c = Condition(field="priority", operator="in", value=["Critical", "High"])
        assert c.evaluate({"priority": "High"})
        assert not c.evaluate({"priority": "Low"})

    def test_exists(self):
        c = Condition(field="assignee", operator="exists")
        assert c.evaluate({"assignee": "alice"})
        assert not c.evaluate({"assignee": ""})
        assert not c.evaluate({"assignee": None})

    def test_contains(self):
        c = Condition(field="description", operator="contains", value="payment")
        assert c.evaluate({"description": "Review payment service"})
        assert not c.evaluate({"description": "Internal tool"})

    def test_dotted_field_path(self):
        c = Condition(field="issue.priority", operator="eq", value="High")
        assert c.evaluate({"issue": {"priority": "High"}})

    def test_gt_operator(self):
        c = Condition(field="score", operator="gt", value=10)
        assert c.evaluate({"score": 15})
        assert not c.evaluate({"score": 5})


# === Rule Tests ===

class TestRule:
    def _make_event(self, **kwargs):
        defaults = dict(
            event_type="issue_updated", project_key="TM", issue_key="TM-1",
            summary="Test", status="Scheduled", priority="High",
            assignee="alice", changes={"status": {"from": "Triaged", "to": "Scheduled"}},
        )
        defaults.update(kwargs)
        return JiraEvent(**defaults)

    def test_rule_fires(self):
        rule = Rule(
            name="test",
            trigger=Trigger(event="issue_updated", project="TM"),
            conditions=[Condition(field="priority", operator="in", value=["High", "Critical"])],
        )
        event = self._make_event()
        assert rule.should_fire(event, event.to_context())

    def test_rule_disabled(self):
        rule = Rule(
            name="test",
            trigger=Trigger(event="issue_updated", project="TM"),
            enabled=False,
        )
        event = self._make_event()
        assert not rule.should_fire(event, event.to_context())

    def test_rule_conditions_not_met(self):
        rule = Rule(
            name="test",
            trigger=Trigger(event="issue_updated", project="TM"),
            conditions=[Condition(field="priority", operator="eq", value="Critical")],
        )
        event = self._make_event(priority="Low")
        assert not rule.should_fire(event, event.to_context())


# === Engine Tests ===

class TestRuleEngine:
    def _make_event(self):
        return JiraEvent(
            event_type="issue_updated", project_key="TM", issue_key="TM-42",
            summary="Payment API", status="Scheduled", priority="High",
            assignee="alice", assignee_email="alice@corp.com",
            reporter="bob", reporter_email="bob@corp.com",
            changes={"status": {"from": "Triaged", "to": "Scheduled"}},
        )

    def test_dry_run(self):
        rule = Rule(
            name="schedule",
            trigger=Trigger(event="issue_updated", project="TM"),
            actions=[Action(type="create_calendar_event", params={"title": "TM: {issue.summary}"})],
        )
        engine = RuleEngine(rules=[rule], dry_run=True)
        results = engine.process_event(self._make_event())

        assert results[0].fired
        assert results[0].actions[0].success
        assert "[DRY RUN]" in results[0].actions[0].message

    def test_engine_with_outlook_connector(self):
        rule = Rule(
            name="schedule",
            trigger=Trigger(event="issue_updated", project="TM"),
            actions=[Action(
                type="create_calendar_event",
                params={
                    "title": "TM: {issue.summary}",
                    "attendees": ["{issue.assignee.email}"],
                    "duration_minutes": 90,
                },
            )],
        )
        outlook = OutlookConnector()
        engine = RuleEngine(rules=[rule], connectors={"outlook": outlook})
        results = engine.process_event(self._make_event())

        assert results[0].fired
        assert results[0].actions[0].success
        assert len(outlook.events_created) == 1

    def test_template_resolution(self):
        event = self._make_event()
        resolved = RuleEngine._resolve_params(
            {"title": "TM: {issue.summary}", "key": "{issue.key}"},
            event,
        )
        assert resolved["title"] == "TM: Payment API"
        assert resolved["key"] == "TM-42"

    def test_no_matching_rules(self):
        rule = Rule(
            name="wrong_project",
            trigger=Trigger(event="issue_updated", project="DEV"),
        )
        engine = RuleEngine(rules=[rule])
        results = engine.process_event(self._make_event())
        assert not results[0].fired

    def test_priority_ordering(self):
        low = Rule(name="low", trigger=Trigger(event="issue_updated", project="TM"), priority=100)
        high = Rule(name="high", trigger=Trigger(event="issue_updated", project="TM"), priority=10)
        engine = RuleEngine(rules=[low, high])
        assert engine.rules[0].name == "high"


# === Parser Tests ===

class TestRuleParser:
    def test_parse_yaml(self):
        yaml_str = """
rules:
  - name: test_rule
    description: A test rule
    priority: 10
    trigger:
      event: issue_updated
      project: TM
      field_changed: status
      new_value: Scheduled
    conditions:
      - field: priority
        operator: in
        value: [Critical, High]
    actions:
      - type: create_calendar_event
        params:
          title: "TM Session"
          duration_minutes: 90
"""
        rules = RuleParser.from_string(yaml_str)
        assert len(rules) == 1
        assert rules[0].name == "test_rule"
        assert rules[0].priority == 10
        assert rules[0].trigger.field_changed == "status"
        assert len(rules[0].conditions) == 1
        assert len(rules[0].actions) == 1

    def test_parse_multiple_rules(self):
        yaml_str = """
rules:
  - name: rule1
    trigger:
      event: issue_created
      project: TM
  - name: rule2
    trigger:
      event: issue_updated
      project: TM
"""
        rules = RuleParser.from_string(yaml_str)
        assert len(rules) == 2


# === Webhook Parser Tests ===

class TestJiraWebhookParser:
    def test_parse_issue_updated(self):
        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": "TM-42",
                "fields": {
                    "project": {"key": "TM"},
                    "summary": "Review payment service",
                    "status": {"name": "Scheduled"},
                    "priority": {"name": "High"},
                    "assignee": {
                        "displayName": "Alice",
                        "emailAddress": "alice@corp.com",
                    },
                    "reporter": {
                        "displayName": "Bob",
                        "emailAddress": "bob@corp.com",
                    },
                    "labels": ["threat-model"],
                },
            },
            "changelog": {
                "items": [
                    {"field": "status", "fromString": "Triaged", "toString": "Scheduled"},
                ],
            },
        }
        parser = JiraWebhookParser()
        event = parser.parse(payload)

        assert event.event_type == "issue_updated"
        assert event.issue_key == "TM-42"
        assert event.project_key == "TM"
        assert event.assignee == "Alice"
        assert event.assignee_email == "alice@corp.com"
        assert event.changes["status"]["to"] == "Scheduled"

    def test_parse_missing_assignee(self):
        payload = {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "key": "TM-1",
                "fields": {
                    "project": {"key": "TM"},
                    "summary": "New request",
                    "status": {"name": "New"},
                    "priority": {"name": "Medium"},
                    "assignee": None,
                    "reporter": {"displayName": "Charlie", "emailAddress": "c@corp.com"},
                    "labels": [],
                },
            },
        }
        parser = JiraWebhookParser()
        event = parser.parse(payload)
        assert event.assignee == ""
        assert event.reporter == "Charlie"


# === Outlook Connector Tests ===

class TestOutlookConnector:
    def test_create_event(self):
        outlook = OutlookConnector()
        result = outlook.create_event({
            "title": "TM Session",
            "duration_minutes": 90,
            "attendees": ["alice@corp.com"],
        })
        assert result.success
        assert len(outlook.events_created) == 1

    def test_calendar_event_to_graph(self):
        event = CalendarEvent(
            title="TM Session",
            start="2026-06-01T10:00:00",
            end="2026-06-01T11:30:00",
            attendees=["alice@corp.com", "bob@corp.com"],
            body="Threat model session",
        )
        payload = event.to_graph_payload()
        assert payload["subject"] == "TM Session"
        assert len(payload["attendees"]) == 2
        assert payload["isOnlineMeeting"] is True


# === Audit Logger Tests ===

class TestAuditLogger:
    def test_log_action(self):
        audit = AuditLogger()
        entry = audit.log_action("test_rule", "create_event", True, "TM-1")
        assert entry.success
        assert audit.total_actions == 1

    def test_get_failures(self):
        audit = AuditLogger()
        audit.log_action("rule1", "create_event", True, "TM-1")
        audit.log_action("rule2", "send_email", False, "TM-2", message="SMTP error")
        failures = audit.get_failures()
        assert len(failures) == 1
        assert failures[0].rule_name == "rule2"

    def test_success_rate(self):
        audit = AuditLogger()
        audit.log_action("r1", "a", True)
        audit.log_action("r2", "a", True)
        audit.log_action("r3", "a", False)
        assert audit.success_rate == pytest.approx(66.67, abs=0.1)

    def test_get_by_issue(self):
        audit = AuditLogger()
        audit.log_action("r1", "a", True, "TM-1")
        audit.log_action("r2", "a", True, "TM-2")
        audit.log_action("r3", "a", True, "TM-1")
        assert len(audit.get_by_issue("TM-1")) == 2
