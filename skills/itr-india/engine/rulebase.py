from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Optional


class RuleConfidence(StrEnum):
    VERIFIED = "verified"
    CONTESTED = "contested"
    UNSUPPORTED = "unsupported"

    @property
    def is_filing_ready(self) -> bool:
        return self is RuleConfidence.VERIFIED

    @property
    def trace_flag(self) -> str:
        return "" if self.is_filing_ready else f"  [{self.value.upper()}]"


@dataclass(frozen=True)
class Rule:
    key: str
    value: Any
    authority: str
    source_primary: str
    source_secondary: str
    effective_from: date
    effective_to: Optional[date]
    confidence: RuleConfidence
    confidence_note: str = ""

    def __post_init__(self) -> None:
        try:
            normalized = RuleConfidence(self.confidence)
        except (TypeError, ValueError):
            return
        object.__setattr__(self, "confidence", normalized)

    def active_on(self, d: date) -> bool:
        if d < self.effective_from:
            return False
        if self.effective_to is not None and d > self.effective_to:
            return False
        return True


class RuleValidationError(ValueError):
    pass


class RuleReadinessError(ValueError):
    pass


def validate_rule(r: Rule) -> None:
    for f in ("authority", "source_primary", "source_secondary"):
        if not getattr(r, f):
            raise RuleValidationError(f"Rule {r.key!r} missing required provenance field {f!r}")
    if not isinstance(r.confidence, RuleConfidence):
        raise RuleValidationError(f"Rule {r.key!r} invalid confidence {r.confidence!r}")
    if not r.confidence.is_filing_ready and not r.confidence_note:
        raise RuleValidationError(
            f"Non-verified rule {r.key!r} must carry a confidence_note"
        )
    if r.effective_to is not None and r.effective_to < r.effective_from:
        raise RuleValidationError(
            f"Rule {r.key!r} has effective_to ({r.effective_to}) before "
            f"effective_from ({r.effective_from})")


class RuleTable:
    def __init__(self, rules: list[Rule]):
        for r in rules:
            validate_rule(r)
        self._rules = list(rules)

    def get(self, key: str, on: date) -> Rule:
        matches = [r for r in self._rules if r.key == key and r.active_on(on)]
        if not matches:
            raise KeyError(f"No active rule {key!r} on {on.isoformat()}")
        if len(matches) > 1:
            raise KeyError(f"Ambiguous: {len(matches)} active rules {key!r} on {on.isoformat()}")
        return matches[0]

    def all(self) -> list[Rule]:
        return list(self._rules)

    def require_filing_ready(self, used_rule_keys: list[str], on: date) -> None:
        keys = sorted(set(used_rule_keys))
        if not keys:
            raise RuleReadinessError(
                "Filing package has no rule usage evidence; independent readiness is blocked"
            )
        try:
            selected = [self.get(key, on) for key in keys]
        except KeyError as exc:
            raise RuleReadinessError(
                f"Filing package uses a rule outside the authoritative baseline: {exc}"
            ) from exc
        blocked = [rule for rule in selected if not rule.confidence.is_filing_ready]
        if blocked:
            details = "; ".join(
                f"{rule.key} [{rule.confidence}]: {rule.confidence_note}"
                for rule in blocked
            )
            raise RuleReadinessError(
                f"Rules block independent filing readiness: {details}"
            )
