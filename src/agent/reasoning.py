"""
LLM reasoning agent for edge-case workflow decisions.

When the rule engine encounters ambiguous situations (scheduling
conflicts, unclear priority, missing information), it escalates
to this agent for intelligent decision-making.

Usage:
    agent = ReasoningAgent(api_key="...")
    decision = agent.resolve_conflict(event, conflict_details)
"""

from dataclasses import dataclass
from typing import Optional

from src.rules.models import JiraEvent
from src.rules.engine import ActionResult


REASONING_PROMPT = """You are a security operations workflow assistant.
You help resolve edge cases in threat modeling service automation.

Given a Jira event and context, decide the best course of action.
Consider:
- Priority and urgency of the request
- Team member availability
- SLA implications
- Past patterns for similar requests

Respond in JSON:
{
  "decision": "schedule|reschedule|defer|escalate",
  "reason": "Brief explanation",
  "suggested_actions": [
    {"type": "action_type", "params": {...}}
  ],
  "confidence": 0.85
}"""


@dataclass
class ReasoningResult:
    """Result from LLM reasoning."""

    decision: str
    reason: str
    suggested_actions: list[dict]
    confidence: float
    raw_response: str = ""


class ReasoningAgent:
    """
    LLM agent for edge-case workflow reasoning.

    Handles situations like:
    - Calendar conflicts for high-priority TM sessions
    - Ambiguous priority when auto-triage is uncertain
    - Scheduling across time zones with complex constraints
    - Deciding whether to bump existing meetings
    """

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None

        if api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                pass

    def reason(self, event: JiraEvent, params: dict) -> ActionResult:
        """
        Make a decision about an edge-case event.

        This is called by the rule engine when a rule escalates
        to the LLM agent via the "escalate_to_llm" action type.
        """
        context = params.get("context", "")
        question = params.get("question", "How should this be handled?")

        prompt = (
            f"Event: {event.event_type} on {event.issue_key}\n"
            f"Summary: {event.summary}\n"
            f"Priority: {event.priority}\n"
            f"Status: {event.status}\n"
            f"Context: {context}\n"
            f"Question: {question}\n"
        )

        if self._client:
            result = self._call_api(prompt)
        else:
            result = self._fallback(event)

        return ActionResult(
            action_type="escalate_to_llm",
            success=True,
            message=f"LLM decision: {result.decision} — {result.reason}",
            details={
                "decision": result.decision,
                "confidence": result.confidence,
                "suggested_actions": result.suggested_actions,
            },
        )

    def resolve_conflict(
        self,
        event: JiraEvent,
        existing_meetings: list[dict],
        available_slots: list[dict],
    ) -> ReasoningResult:
        """
        Resolve a scheduling conflict for a TM session.

        Considers the priority of the new request vs existing meetings
        and suggests the best path forward.
        """
        prompt = (
            f"Scheduling conflict for {event.issue_key} ({event.priority} priority):\n"
            f"Summary: {event.summary}\n\n"
            f"Existing meetings in the target window:\n"
        )
        for m in existing_meetings:
            prompt += f"  - {m.get('title', 'Untitled')} at {m.get('time', 'TBD')}\n"

        prompt += f"\nAvailable alternative slots:\n"
        for s in available_slots:
            prompt += f"  - {s.get('time', 'TBD')}\n"

        prompt += "\nShould we bump an existing meeting, use an alternative slot, or defer?"

        if self._client:
            return self._call_api(prompt)
        return self._fallback(event)

    def _call_api(self, prompt: str) -> ReasoningResult:
        """Call the Anthropic API."""
        import json

        response = self._client.messages.create(
            model=self.model,
            max_tokens=500,
            system=REASONING_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}

        return ReasoningResult(
            decision=data.get("decision", "defer"),
            reason=data.get("reason", ""),
            suggested_actions=data.get("suggested_actions", []),
            confidence=data.get("confidence", 0.5),
            raw_response=raw,
        )

    @staticmethod
    def _fallback(event: JiraEvent) -> ReasoningResult:
        """Conservative fallback when API is unavailable."""
        if event.priority in ("Critical", "High"):
            return ReasoningResult(
                decision="schedule",
                reason="High priority — schedule at next available slot",
                suggested_actions=[
                    {"type": "create_calendar_event", "params": {"priority": "high"}}
                ],
                confidence=0.6,
            )
        return ReasoningResult(
            decision="defer",
            reason="API unavailable — deferring for manual review",
            suggested_actions=[],
            confidence=0.3,
        )
