"""
YAML rule parser.

Loads workflow rules from YAML files into Rule objects.

Usage:
    rules = RuleParser.from_file("rules.yaml")
    engine = RuleEngine(rules)
"""

from pathlib import Path
from typing import Union

import yaml

from src.rules.models import Rule, Trigger, Condition, Action


class RuleParser:
    """Parse YAML rule definitions into Rule objects."""

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> list[Rule]:
        """Load rules from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.parse(data)

    @classmethod
    def from_string(cls, yaml_string: str) -> list[Rule]:
        """Load rules from a YAML string."""
        data = yaml.safe_load(yaml_string)
        return cls.parse(data)

    @classmethod
    def parse(cls, data: dict) -> list[Rule]:
        """Parse a rules dictionary into Rule objects."""
        rules = []
        for rule_data in data.get("rules", []):
            rules.append(cls._parse_rule(rule_data))
        return rules

    @classmethod
    def _parse_rule(cls, data: dict) -> Rule:
        """Parse a single rule definition."""
        trigger_data = data.get("trigger", {})
        trigger = Trigger(
            event=trigger_data.get("event", ""),
            project=trigger_data.get("project", ""),
            field_changed=trigger_data.get("field_changed", ""),
            new_value=trigger_data.get("new_value", ""),
            old_value=trigger_data.get("old_value", ""),
        )

        conditions = [
            Condition(
                field=c.get("field", ""),
                operator=c.get("operator", "eq"),
                value=c.get("value"),
            )
            for c in data.get("conditions", [])
        ]

        actions = [
            Action(
                type=a.get("type", ""),
                params=a.get("params", {}),
                on_error=a.get("on_error", "log"),
            )
            for a in data.get("actions", [])
        ]

        return Rule(
            name=data.get("name", "unnamed"),
            trigger=trigger,
            conditions=conditions,
            actions=actions,
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
