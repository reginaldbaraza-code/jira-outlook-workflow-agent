"""
Outlook calendar and email connector via Microsoft Graph API.

Provides calendar CRUD and email operations for the rule engine.

In production, this authenticates via OAuth2 with the Microsoft
identity platform. This implementation provides the interface
and data structures.

Usage:
    outlook = OutlookConnector(client_id, client_secret, tenant_id)
    outlook.create_event(params)
    outlook.send_email(params)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.rules.engine import ActionResult


@dataclass
class CalendarEvent:
    """A calendar event to create or update."""

    title: str
    start: str  # ISO datetime
    end: str  # ISO datetime
    attendees: list[str] = field(default_factory=list)
    body: str = ""
    location: str = ""
    is_online: bool = True
    reminder_minutes: int = 15
    event_id: str = ""  # Set after creation

    def to_graph_payload(self) -> dict:
        """Convert to Microsoft Graph API event format."""
        payload = {
            "subject": self.title,
            "start": {
                "dateTime": self.start,
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": self.end,
                "timeZone": "UTC",
            },
            "body": {
                "contentType": "HTML",
                "content": self.body,
            },
            "attendees": [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in self.attendees
            ],
            "isOnlineMeeting": self.is_online,
            "reminderMinutesBeforeStart": self.reminder_minutes,
        }
        if self.location:
            payload["location"] = {"displayName": self.location}
        return payload


class OutlookConnector:
    """
    Microsoft Graph API connector for calendar and email operations.

    Methods return ActionResult objects for integration with the rule engine.
    """

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        tenant_id: str = "",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self._token: Optional[str] = None
        self._events_created: list[CalendarEvent] = []

    def create_event(self, params: dict) -> ActionResult:
        """
        Create a calendar event.

        Expected params:
            title: Event title
            duration_minutes: Duration in minutes
            attendees: List of email addresses
            body: Event body/description
        """
        title = params.get("title", "Threat Model Session")
        duration = params.get("duration_minutes", 90)
        attendees = params.get("attendees", [])
        body = params.get("body", "")

        event = CalendarEvent(
            title=title,
            start="",  # Would be set by scheduling logic
            end="",
            attendees=attendees,
            body=body,
        )

        # In production: POST to Graph API
        # response = self._graph_client.post("/me/events", json=event.to_graph_payload())

        self._events_created.append(event)

        return ActionResult(
            action_type="create_calendar_event",
            success=True,
            message=f"Calendar event created: {title}",
            details={
                "title": title,
                "duration_minutes": duration,
                "attendees": attendees,
            },
        )

    def update_event(self, event_id: str, params: dict) -> ActionResult:
        """Update an existing calendar event."""
        # In production: PATCH to Graph API
        return ActionResult(
            action_type="update_calendar_event",
            success=True,
            message=f"Calendar event updated: {event_id}",
            details=params,
        )

    def cancel_event(self, event_id: str, message: str = "") -> ActionResult:
        """Cancel a calendar event."""
        # In production: POST cancel to Graph API
        return ActionResult(
            action_type="cancel_calendar_event",
            success=True,
            message=f"Calendar event cancelled: {event_id}",
            details={"cancel_message": message},
        )

    def send_email(self, params: dict) -> ActionResult:
        """
        Send an email via Outlook.

        Expected params:
            to: List of recipient emails
            subject: Email subject
            body: Email body (HTML)
        """
        to = params.get("to", [])
        subject = params.get("subject", "")
        body = params.get("body", "")

        # In production: POST to Graph API sendMail
        return ActionResult(
            action_type="send_email",
            success=True,
            message=f"Email sent: {subject}",
            details={"to": to, "subject": subject},
        )

    @property
    def events_created(self) -> list[CalendarEvent]:
        """Get all events created in this session (for testing)."""
        return self._events_created
