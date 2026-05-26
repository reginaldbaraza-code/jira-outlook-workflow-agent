"""
Rule evaluation engine.

Processes Jira events against a set of rules and dispatches
matched actions to the appropriate connectors.

Usage:
    engine = RuleEngine(rules, connectors)
    results = engine.process_event(jira_event)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.rules.models import Rule, JiraEvent, Action


@dataclass
class ActionResult:
    """Result of executing a single action."""

    action_type: str
    success: bool
    message: str = ""
    details: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class RuleResult:
    """Result of evaluating and executing a rule."""

    rule_name: str
    fired: bool
    actions: list[ActionResult] = field(default_factory=list)
    skipped_reason: str = ""


class RuleEngine:
    """
    Evaluates Jira events against rules and executes actions.

    The engine processes rules in priority order (lower number = higher priority).
    When a rule matches:
    1. All conditions are evaluated against the event context
    2. If all conditions pass, actions are executed in order
    3. Results are logged via the audit connector

    Features:
    - Priority-based rule ordering
    - Dry-run mode for testing
    - Action error handling (log, abort, retry)
    - Template variable resolution in action params
    """

    def __init__(
        self,
        rules: list[Rule] = None,
        connectors: dict = None,
        dry_run: bool = False,
    ):
        self.rules = sorted(rules or [], key=lambda r: r.priority)
        self.connectors = connectors or {}
        self.dry_run = dry_run
        self._execution_log: list[RuleResult] = []

    def process_event(self, event: JiraEvent) -> list[RuleResult]:
        """
        Process a Jira event against all rules.

        Args:
            event: Parsed Jira webhook event.

        Returns:
            List of RuleResult for each evaluated rule.
        """
        results = []
        context = event.to_context()

        for rule in self.rules:
            if not rule.enabled:
                results.append(RuleResult(
                    rule_name=rule.name, fired=False,
                    skipped_reason="Rule disabled",
                ))
                continue

            if rule.should_fire(event, context):
                action_results = self._execute_actions(rule, event, context)
                result = RuleResult(
                    rule_name=rule.name,
                    fired=True,
                    actions=action_results,
                )
            else:
                result = RuleResult(
                    rule_name=rule.name, fired=False,
                    skipped_reason="Conditions not met",
                )

            results.append(result)

        self._execution_log.extend(results)
        return results

    def _execute_actions(
        self,
        rule: Rule,
        event: JiraEvent,
        context: dict,
    ) -> list[ActionResult]:
        """Execute all actions for a fired rule."""
        results = []

        for action in rule.actions:
            if self.dry_run:
                results.append(ActionResult(
                    action_type=action.type,
                    success=True,
                    message=f"[DRY RUN] Would execute: {action.type}",
                    details=self._resolve_params(action.params, event),
                ))
                continue

            try:
                result = self._dispatch_action(action, event, context)
                results.append(result)

                if not result.success and action.on_error == "abort":
                    break

            except Exception as e:
                results.append(ActionResult(
                    action_type=action.type,
                    success=False,
                    message=f"Error: {str(e)}",
                ))
                if action.on_error == "abort":
                    break

        return results

    def _dispatch_action(
        self,
        action: Action,
        event: JiraEvent,
        context: dict,
    ) -> ActionResult:
        """Dispatch an action to the appropriate connector."""
        resolved_params = self._resolve_params(action.params, event)

        if action.type == "create_calendar_event":
            connector = self.connectors.get("outlook")
            if connector:
                return connector.create_event(resolved_params)
            return ActionResult(
                action_type=action.type,
                success=False,
                message="Outlook connector not configured",
            )

        elif action.type == "send_email":
            connector = self.connectors.get("outlook")
            if connector:
                return connector.send_email(resolved_params)
            return ActionResult(
                action_type=action.type,
                success=False,
                message="Outlook connector not configured",
            )

        elif action.type == "add_jira_comment":
            connector = self.connectors.get("jira")
            if connector:
                return connector.add_comment(
                    event.issue_key,
                    resolved_params.get("text", ""),
                )
            return ActionResult(
                action_type=action.type,
                success=False,
                message="Jira connector not configured",
            )

        elif action.type == "escalate_to_llm":
            connector = self.connectors.get("agent")
            if connector:
                return connector.reason(event, resolved_params)
            return ActionResult(
                action_type=action.type,
                success=False,
                message="LLM agent not configured",
            )

        return ActionResult(
            action_type=action.type,
            success=False,
            message=f"Unknown action type: {action.type}",
        )

    @staticmethod
    def _resolve_params(params: dict, event: JiraEvent) -> dict:
        """Resolve template variables in action params."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                resolved[key] = (
                    value
                    .replace("{issue.key}", event.issue_key)
                    .replace("{issue.summary}", event.summary)
                    .replace("{issue.status}", event.status)
                    .replace("{issue.priority}", event.priority)
                    .replace("{issue.assignee}", event.assignee)
                    .replace("{issue.assignee.email}", event.assignee_email)
                    .replace("{issue.reporter}", event.reporter)
                    .replace("{issue.reporter.email}", event.reporter_email)
                )
            elif isinstance(value, list):
                resolved[key] = [
                    RuleEngine._resolve_params({"_": item}, event)["_"]
                    if isinstance(item, str) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                resolved[key] = RuleEngine._resolve_params(value, event)
            else:
                resolved[key] = value
        return resolved

    @property
    def execution_log(self) -> list[RuleResult]:
        """Get the full execution log."""
        return self._execution_log

    def get_fired_rules(self) -> list[RuleResult]:
        """Get only rules that fired."""
        return [r for r in self._execution_log if r.fired]
