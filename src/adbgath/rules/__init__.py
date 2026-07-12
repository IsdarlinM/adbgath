from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    title: str
    severity: str
    confidence: str
    description: str
    evidence: str
    impact: str
    mitigation: str
    component: str = "device"
    validation: str = "Validate on an authorized test target."
    false_positive: str = "Review OEM-specific or application-specific behavior."
    references: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "impact": self.impact,
            "mitigation": self.mitigation,
            "component": self.component,
            "validation": self.validation,
            "false_positive": self.false_positive,
            "references": list(self.references),
            "metadata": self.metadata,
        }


RuleCheck = Callable[[dict[str, Any]], Finding | None]


class RuleEngine:
    def __init__(self) -> None:
        self._rules: list[RuleCheck] = []

    def register(self, rule: RuleCheck) -> RuleCheck:
        self._rules.append(rule)
        return rule

    def evaluate(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for rule in self._rules:
            finding = rule(context)
            if finding:
                findings.append(finding.to_dict())
        return findings


engine = RuleEngine()
