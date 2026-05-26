"""
Action audit logger.

Records every action taken by the rule engine for compliance
and debugging. Provides a complete trail of what happened,
when, and why.

Usage:
    audit = AuditLogger()
    audit.log_action(rule_name, action_type, success, details)
    recent = audit.get_recent(limit=10)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: str
    rule_name: str
    action_type: str
    success: bool
    issue_key: str = ""
    message: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "rule_name": self.rule_name,
            "action_type": self.action_type,
            "success": self.success,
            "issue_key": self.issue_key,
            "message": self.message,
            "details": self.details,
        }


class AuditLogger:
    """
    Audit logger for workflow actions.

    In production, logs to a persistent store (database, SIEM, etc.).
    This implementation uses an in-memory list for testing.
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []

    def log_action(
        self,
        rule_name: str,
        action_type: str,
        success: bool,
        issue_key: str = "",
        message: str = "",
        details: dict = None,
    ) -> AuditEntry:
        """Record an action in the audit log."""
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat(),
            rule_name=rule_name,
            action_type=action_type,
            success=success,
            issue_key=issue_key,
            message=message,
            details=details or {},
        )
        self._entries.append(entry)
        return entry

    def get_recent(self, limit: int = 20) -> list[AuditEntry]:
        """Get the most recent audit entries."""
        return self._entries[-limit:]

    def get_by_issue(self, issue_key: str) -> list[AuditEntry]:
        """Get all audit entries for a specific Jira issue."""
        return [e for e in self._entries if e.issue_key == issue_key]

    def get_failures(self) -> list[AuditEntry]:
        """Get all failed actions."""
        return [e for e in self._entries if not e.success]

    @property
    def total_actions(self) -> int:
        return len(self._entries)

    @property
    def success_rate(self) -> float:
        if not self._entries:
            return 100.0
        successes = sum(1 for e in self._entries if e.success)
        return (successes / len(self._entries)) * 100
