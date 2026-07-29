"""Auditable filing-readiness states and append-only human decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FilingReadiness(str, Enum):
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"
    INDEPENDENTLY_FILING_READY = "independently_filing_ready"
    FILING_READY_BY_HUMAN_OVERRIDE = "filing_ready_by_human_override"


class ComputationBasis(str, Enum):
    INDEPENDENT_EVIDENCE = "independent_evidence"
    SOURCE_SUMMARY_ONLY = "source_summary_only"


class BlockerCategory(str, Enum):
    EVIDENCE_GAP = "evidence_gap"
    SOURCE_SUMMARY_LIMITATION = "source_summary_limitation"
    INTEGRITY_FAILURE = "integrity_failure"
    UNSUPPORTED_SCOPE = "unsupported_scope"


class BlockerOverridePolicy(str, Enum):
    ELIGIBLE = "eligible"
    PROHIBITED = "prohibited"


class DecisionAction(str, Enum):
    ACCEPT_RISK = "accept_risk"


@dataclass(frozen=True, slots=True)
class FilingComputationContext:
    computation_basis: ComputationBasis
    normalized_input_sha256: str
    output_amounts: tuple[tuple[str, Decimal], ...]

    @classmethod
    def create(
        cls,
        *,
        computation_basis: ComputationBasis,
        normalized_input_sha256: str,
        output_amounts: (
            Mapping[str, Decimal] | Iterable[tuple[str, Decimal]]
        ),
    ) -> "FilingComputationContext":
        if isinstance(output_amounts, Mapping):
            amounts = tuple(output_amounts.items())
        else:
            amounts = tuple(output_amounts)
        return cls(
            computation_basis=computation_basis,
            normalized_input_sha256=normalized_input_sha256,
            output_amounts=amounts,
        )

    def __post_init__(self) -> None:
        _require_enum(
            "computation_basis",
            self.computation_basis,
            ComputationBasis,
        )
        input_fingerprint = _validated_fingerprint(
            self.normalized_input_sha256,
            field_name="normalized_input_sha256",
        )
        normalized_amounts: list[tuple[str, Decimal]] = []
        seen_paths: set[str] = set()
        for output_path, amount in self.output_amounts:
            _require_text("output_amount path", output_path)
            normalized_path = output_path.strip()
            if normalized_path in seen_paths:
                raise ValueError(
                    f"Duplicate normalized output path: {normalized_path}"
                )
            if not isinstance(amount, Decimal) or not amount.is_finite():
                raise ValueError(
                    "output_amounts values must be finite Decimal amounts"
                )
            seen_paths.add(normalized_path)
            normalized_amounts.append((normalized_path, amount.normalize()))
        object.__setattr__(
            self,
            "normalized_input_sha256",
            input_fingerprint,
        )
        object.__setattr__(
            self,
            "output_amounts",
            tuple(sorted(normalized_amounts)),
        )

    @property
    def fingerprint(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def canonical_json(self) -> str:
        return json.dumps(
            _context_json(self),
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class FilingBlocker:
    blocker_id: str
    code: str
    message: str
    category: BlockerCategory
    override_policy: BlockerOverridePolicy
    affected_outputs: tuple[str, ...]
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_enum("category", self.category, BlockerCategory)
        _require_enum(
            "override_policy",
            self.override_policy,
            BlockerOverridePolicy,
        )
        _require_text("blocker_id", self.blocker_id)
        _require_text("code", self.code)
        _require_text("message", self.message)
        outputs = _normalized_nonempty_texts(
            "affected_outputs",
            self.affected_outputs,
        )
        evidence = _normalized_texts(
            "evidence_references",
            self.evidence_references,
        )
        object.__setattr__(self, "affected_outputs", outputs)
        object.__setattr__(self, "evidence_references", evidence)
        if (
            self.category is BlockerCategory.INTEGRITY_FAILURE
            and self.override_policy is BlockerOverridePolicy.ELIGIBLE
        ):
            raise ValueError("integrity failures cannot be override eligible")


@dataclass(frozen=True, slots=True)
class HumanDecision:
    decision_id: str
    blocker_id: str
    action: DecisionAction
    actor: str
    decided_at: datetime
    reason: str
    evidence_references: tuple[str, ...]
    affected_outputs: tuple[str, ...]
    context_fingerprint: str

    def __post_init__(self) -> None:
        _require_enum("action", self.action, DecisionAction)
        _require_text("decision_id", self.decision_id)
        _require_text("blocker_id", self.blocker_id)
        _require_text("actor", self.actor)
        _require_text("reason", self.reason)
        if not isinstance(self.decided_at, datetime):
            raise ValueError("decided_at must be a datetime")
        if (
            self.decided_at.tzinfo is None
            or self.decided_at.utcoffset() is None
        ):
            raise ValueError("decided_at must be timezone-aware")
        evidence = _normalized_nonempty_texts(
            "evidence_references",
            self.evidence_references,
        )
        outputs = _normalized_nonempty_texts(
            "affected_outputs",
            self.affected_outputs,
        )
        fingerprint = _validated_fingerprint(
            self.context_fingerprint,
            field_name="context_fingerprint",
        )
        object.__setattr__(self, "evidence_references", evidence)
        object.__setattr__(self, "affected_outputs", outputs)
        object.__setattr__(self, "context_fingerprint", fingerprint)


@dataclass(frozen=True, slots=True)
class DecisionJournalEntry:
    sequence: int
    previous_entry_sha256: str
    decision: HumanDecision

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("journal entry sequence must be a positive integer")
        previous = _validated_fingerprint(
            self.previous_entry_sha256,
            field_name="previous_entry_sha256",
        )
        if not isinstance(self.decision, HumanDecision):
            raise ValueError("journal entry decision must be a HumanDecision")
        object.__setattr__(self, "previous_entry_sha256", previous)

    @property
    def entry_sha256(self) -> str:
        payload = json.dumps(
            {
                "decision": _decision_json(self.decision),
                "previous_entry_sha256": self.previous_entry_sha256,
                "sequence": self.sequence,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def with_previous_entry_sha256(
        self,
        previous_entry_sha256: str,
    ) -> "DecisionJournalEntry":
        return replace(
            self,
            previous_entry_sha256=previous_entry_sha256,
        )


@dataclass(frozen=True, slots=True)
class DecisionJournal:
    journal_id: str
    entries: tuple[DecisionJournalEntry, ...] = ()

    def __post_init__(self) -> None:
        _require_text("journal_id", self.journal_id)
        object.__setattr__(self, "journal_id", self.journal_id.strip())
        if not isinstance(self.entries, tuple):
            raise ValueError("entries must be an immutable tuple")
        if not self.verify_history():
            raise ValueError("Decision journal history chain is invalid")

    @classmethod
    def empty(cls, journal_id: str) -> "DecisionJournal":
        return cls(journal_id=journal_id)

    @property
    def decisions(self) -> tuple[HumanDecision, ...]:
        return tuple(entry.decision for entry in self.entries)

    @property
    def history_sha256(self) -> str:
        if self.entries:
            return self.entries[-1].entry_sha256
        return _journal_genesis_sha256(self.journal_id)

    def append(self, decision: HumanDecision) -> "DecisionJournal":
        if not isinstance(decision, HumanDecision):
            raise ValueError("decision must be a HumanDecision")
        if any(
            existing.decision.decision_id == decision.decision_id
            for existing in self.entries
        ):
            raise ValueError(f"Duplicate decision_id: {decision.decision_id}")
        entry = DecisionJournalEntry(
            sequence=len(self.entries) + 1,
            previous_entry_sha256=self.history_sha256,
            decision=decision,
        )
        return DecisionJournal(
            journal_id=self.journal_id,
            entries=(*self.entries, entry),
        )

    def verify_history(self) -> bool:
        expected_previous = _journal_genesis_sha256(self.journal_id)
        seen_decision_ids: set[str] = set()
        for expected_sequence, entry in enumerate(self.entries, start=1):
            if not isinstance(entry, DecisionJournalEntry):
                return False
            if entry.sequence != expected_sequence:
                return False
            if entry.previous_entry_sha256 != expected_previous:
                return False
            if entry.decision.decision_id in seen_decision_ids:
                return False
            seen_decision_ids.add(entry.decision.decision_id)
            expected_previous = entry.entry_sha256
        return True

    def canonical_json(self) -> str:
        return json.dumps(
            _journal_json(self),
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class DecisionFinding:
    decision_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReadinessAssessment:
    state: FilingReadiness
    context: FilingComputationContext
    blockers: tuple[FilingBlocker, ...]
    active_blockers: tuple[FilingBlocker, ...]
    accepted_risks: tuple[FilingBlocker, ...]
    decision_journal: DecisionJournal
    applied_decision_ids: tuple[str, ...]
    decision_findings: tuple[DecisionFinding, ...]

    @property
    def computation_basis(self) -> ComputationBasis:
        return self.context.computation_basis

    @property
    def context_fingerprint(self) -> str:
        return self.context.fingerprint

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "accepted_risks": [
                    _blocker_json(blocker) for blocker in self.accepted_risks
                ],
                "active_blockers": [
                    _blocker_json(blocker) for blocker in self.active_blockers
                ],
                "applied_decision_ids": list(self.applied_decision_ids),
                "blockers": [
                    _blocker_json(blocker) for blocker in self.blockers
                ],
                "context": _context_json(self.context),
                "context_fingerprint": self.context.fingerprint,
                "decision_findings": [
                    {
                        "code": finding.code,
                        "decision_id": finding.decision_id,
                        "message": finding.message,
                    }
                    for finding in self.decision_findings
                ],
                "decision_journal": _journal_json(self.decision_journal),
                "state": self.state.value,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def assess_filing_readiness(
    *,
    context: FilingComputationContext,
    decision_journal: DecisionJournal,
    blockers: Iterable[FilingBlocker] = (),
) -> ReadinessAssessment:
    """Recompute readiness from immutable computation facts and decisions."""

    if not isinstance(context, FilingComputationContext):
        raise ValueError("context must be a FilingComputationContext")
    if not isinstance(decision_journal, DecisionJournal):
        raise ValueError("decision_journal must be a DecisionJournal")
    ordered_blockers = tuple(sorted(blockers, key=lambda item: item.blocker_id))
    ordered_decisions = decision_journal.decisions
    _require_unique_ids(
        "blocker_id",
        (blocker.blocker_id for blocker in ordered_blockers),
    )
    if (
        context.computation_basis is ComputationBasis.SOURCE_SUMMARY_ONLY
        and not any(
            blocker.category is BlockerCategory.SOURCE_SUMMARY_LIMITATION
            for blocker in ordered_blockers
        )
    ):
        raise ValueError(
            "SOURCE_SUMMARY_ONLY requires a visible "
            "SOURCE_SUMMARY_LIMITATION blocker"
        )

    blocker_by_id = {
        blocker.blocker_id: blocker for blocker in ordered_blockers
    }
    accepted_ids: set[str] = set()
    applied_decision_ids: list[str] = []
    findings: list[DecisionFinding] = []
    computed_output_paths = {
        output_path for output_path, _ in context.output_amounts
    }
    for decision in ordered_decisions:
        blocker = blocker_by_id.get(decision.blocker_id)
        if blocker is None:
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "STALE_DECISION",
                    "The targeted blocker is not present in this recomputation",
                )
            )
            continue
        if decision.context_fingerprint != context.fingerprint:
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "STALE_CONTEXT",
                    "The decision belongs to a different computation context",
                )
            )
            continue
        if decision.affected_outputs != blocker.affected_outputs:
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "AFFECTED_OUTPUTS_MISMATCH",
                    "The decision does not name exactly the blocker's outputs",
                )
            )
            continue
        if not set(blocker.affected_outputs).issubset(computed_output_paths):
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "AFFECTED_OUTPUTS_NOT_COMPUTED",
                    "The computation context does not bind every affected output",
                )
            )
            continue
        if blocker.override_policy is BlockerOverridePolicy.PROHIBITED:
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "NON_OVERRIDABLE_BLOCKER",
                    "This blocker cannot be accepted by human override",
                )
            )
            continue
        if decision.action is DecisionAction.ACCEPT_RISK:
            accepted_ids.add(blocker.blocker_id)
            applied_decision_ids.append(decision.decision_id)

    accepted_risks = tuple(
        blocker
        for blocker in ordered_blockers
        if blocker.blocker_id in accepted_ids
    )
    active_blockers = tuple(
        blocker
        for blocker in ordered_blockers
        if blocker.blocker_id not in accepted_ids
    )
    if not active_blockers:
        if accepted_risks:
            state = FilingReadiness.FILING_READY_BY_HUMAN_OVERRIDE
        else:
            state = FilingReadiness.INDEPENDENTLY_FILING_READY
    elif (
        context.computation_basis is ComputationBasis.SOURCE_SUMMARY_ONLY
        and all(
            blocker.category is BlockerCategory.SOURCE_SUMMARY_LIMITATION
            for blocker in active_blockers
        )
    ):
        state = FilingReadiness.PROVISIONAL
    else:
        state = FilingReadiness.BLOCKED

    return ReadinessAssessment(
        state=state,
        context=context,
        blockers=ordered_blockers,
        active_blockers=active_blockers,
        accepted_risks=accepted_risks,
        decision_journal=decision_journal,
        applied_decision_ids=tuple(sorted(applied_decision_ids)),
        decision_findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.code,
                    finding.decision_id,
                ),
            )
        ),
    )


def _validated_fingerprint(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    fingerprint = value.lower()
    if not _SHA256_RE.fullmatch(fingerprint):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return fingerprint


def _normalized_texts(
    field_name: str,
    values: Iterable[str],
) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        _require_text(field_name, value)
        normalized.append(value.strip())
    return tuple(sorted(set(normalized)))


def _normalized_nonempty_texts(
    field_name: str,
    values: Iterable[str],
) -> tuple[str, ...]:
    normalized = _normalized_texts(field_name, values)
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _require_enum(field_name: str, value: object, enum_type: type[Enum]) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field_name} must be a {enum_type.__name__}")


def _require_unique_ids(field_name: str, values: Iterable[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        joined = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate {field_name}: {joined}")


def _journal_genesis_sha256(journal_id: str) -> str:
    payload = json.dumps(
        {
            "journal_id": journal_id.strip(),
            "schema_version": "1.0",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _context_json(context: FilingComputationContext) -> dict[str, object]:
    return {
        "computation_basis": context.computation_basis.value,
        "normalized_input_sha256": context.normalized_input_sha256,
        "output_amounts": {
            output_path: format(amount, "f")
            for output_path, amount in context.output_amounts
        },
    }


def _journal_json(journal: DecisionJournal) -> dict[str, object]:
    return {
        "entries": [
            {
                "decision": _decision_json(entry.decision),
                "entry_sha256": entry.entry_sha256,
                "previous_entry_sha256": entry.previous_entry_sha256,
                "sequence": entry.sequence,
            }
            for entry in journal.entries
        ],
        "history_sha256": journal.history_sha256,
        "journal_id": journal.journal_id,
        "schema_version": "1.0",
    }


def _blocker_json(blocker: FilingBlocker) -> dict[str, object]:
    return {
        "affected_outputs": list(blocker.affected_outputs),
        "blocker_id": blocker.blocker_id,
        "category": blocker.category.value,
        "code": blocker.code,
        "evidence_references": list(blocker.evidence_references),
        "message": blocker.message,
        "override_policy": blocker.override_policy.value,
    }


def _decision_json(decision: HumanDecision) -> dict[str, object]:
    return {
        "action": decision.action.value,
        "actor": decision.actor,
        "affected_outputs": list(decision.affected_outputs),
        "blocker_id": decision.blocker_id,
        "context_fingerprint": decision.context_fingerprint,
        "decided_at": decision.decided_at.isoformat(),
        "decision_id": decision.decision_id,
        "evidence_references": list(decision.evidence_references),
        "reason": decision.reason,
    }
