"""
Jira webhook event parser.

Parses raw Jira webhook payloads into JiraEvent objects
for the rule engine to process.

Handles event types:
- jira:issue_created
- jira:issue_updated
- comment_created

Usage:
    parser = JiraWebhookParser()
    event = parser.parse(webhook_payload)
"""

from src.rules.models import JiraEvent


class JiraWebhookParser:
    """Parse Jira webhook payloads into JiraEvent objects."""

    # Map Jira webhook event names to our internal event types
    EVENT_MAP = {
        "jira:issue_created": "issue_created",
        "jira:issue_updated": "issue_updated",
        "jira:issue_deleted": "issue_deleted",
        "comment_created": "comment_created",
    }

    def parse(self, payload: dict) -> JiraEvent:
        """
        Parse a Jira webhook payload into a JiraEvent.

        Args:
            payload: Raw webhook JSON payload.

        Returns:
            Parsed JiraEvent with extracted fields.
        """
        webhook_event = payload.get("webhookEvent", "")
        event_type = self.EVENT_MAP.get(webhook_event, webhook_event)

        issue = payload.get("issue", {})
        fields = issue.get("fields", {})

        # Extract changes from changelog
        changes = {}
        changelog = payload.get("changelog", {})
        for item in changelog.get("items", []):
            field_id = item.get("field", "")
            changes[field_id] = {
                "from": item.get("fromString", ""),
                "to": item.get("toString", ""),
            }

        # Extract assignee
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}

        return JiraEvent(
            event_type=event_type,
            project_key=fields.get("project", {}).get("key", ""),
            issue_key=issue.get("key", ""),
            summary=fields.get("summary", ""),
            status=fields.get("status", {}).get("name", ""),
            priority=fields.get("priority", {}).get("name", ""),
            assignee=assignee.get("displayName", ""),
            assignee_email=assignee.get("emailAddress", ""),
            reporter=reporter.get("displayName", ""),
            reporter_email=reporter.get("emailAddress", ""),
            description=self._extract_description(fields.get("description")),
            labels=fields.get("labels", []),
            changes=changes,
            timestamp=payload.get("timestamp", ""),
            raw_payload=payload,
        )

    @staticmethod
    def _extract_description(desc) -> str:
        """Extract text from ADF or plain text description."""
        if desc is None:
            return ""
        if isinstance(desc, str):
            return desc
        if isinstance(desc, dict):
            # Atlassian Document Format — extract text nodes
            texts = []
            for block in desc.get("content", []):
                for node in block.get("content", []):
                    if node.get("type") == "text":
                        texts.append(node.get("text", ""))
            return " ".join(texts)
        return str(desc)
