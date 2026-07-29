"""Map bank-interest reconciliation failures into generic filing blockers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Iterable

from engine.bank_interest_filing import BankInterestSlice, build_bank_interest_slice
from engine.bank_interest_ledger import BankInterestLedger
from engine.bank_interest_reconciliation import (
    BankReconciliationResult,
    ReconciliationBlocker,
    inspect_bank_interest_reconciliation,
)
from engine.readiness import (
    BlockerCategory,
    BlockerOverridePolicy,
    ComputationBasis,
    DecisionJournal,
    FilingBlocker,
    FilingComputationContext,
    ReadinessAssessment,
    assess_filing_readiness,
)


_SCHEDULE_OS = "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/InterestGross"
_SCHEDULE_TDS2 = "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals"


@dataclass(frozen=True, slots=True)
class _BlockerPolicy:
    category: BlockerCategory
    override_policy: BlockerOverridePolicy
    affected_outputs: tuple[str, ...]


_INTEGRITY_ALL_OUTPUTS = _BlockerPolicy(
    BlockerCategory.INTEGRITY_FAILURE,
    BlockerOverridePolicy.PROHIBITED,
    (_SCHEDULE_OS, _SCHEDULE_TDS2),
)
_EVIDENCE_ALL_OUTPUTS = _BlockerPolicy(
    BlockerCategory.EVIDENCE_GAP,
    BlockerOverridePolicy.PROHIBITED,
    (_SCHEDULE_OS, _SCHEDULE_TDS2),
)
_BANK_BLOCKER_POLICIES = {
    "ACCOUNT_METADATA_MISMATCH": _INTEGRITY_ALL_OUTPUTS,
    "DUPLICATE_BANK_EVENT": _INTEGRITY_ALL_OUTPUTS,
    "DUPLICATE_EVIDENCE": _INTEGRITY_ALL_OUTPUTS,
    "DUPLICATE_SOURCE": _INTEGRITY_ALL_OUTPUTS,
    "EVENT_METADATA_MISMATCH": _INTEGRITY_ALL_OUTPUTS,
    "INTEREST_MISMATCH": _INTEGRITY_ALL_OUTPUTS,
    "INVALID_ITR2_BASE": _BlockerPolicy(
        BlockerCategory.INTEGRITY_FAILURE,
        BlockerOverridePolicy.PROHIBITED,
        ("/ITR/ITR2",),
    ),
    "MISSING_26AS_CREDIT": _BlockerPolicy(
        BlockerCategory.EVIDENCE_GAP,
        BlockerOverridePolicy.ELIGIBLE,
        (_SCHEDULE_TDS2,),
    ),
    "OWNERSHIP_UNRESOLVED": _EVIDENCE_ALL_OUTPUTS,
    "TAN_MISMATCH": _BlockerPolicy(
        BlockerCategory.INTEGRITY_FAILURE,
        BlockerOverridePolicy.PROHIBITED,
        (_SCHEDULE_TDS2,),
    ),
    "TDS_MISMATCH": _BlockerPolicy(
        BlockerCategory.INTEGRITY_FAILURE,
        BlockerOverridePolicy.PROHIBITED,
        (_SCHEDULE_TDS2,),
    ),
    "UNEXPLAINED_PORTAL_ENTRY": _EVIDENCE_ALL_OUTPUTS,
}


@dataclass(frozen=True, slots=True)
class BankInterestReadinessComputation:
    filing_slice: BankInterestSlice | None
    readiness: ReadinessAssessment
    reconciliation: BankReconciliationResult


def compute_bank_interest_with_readiness(
    ledger: BankInterestLedger,
    decision_journal: DecisionJournal,
) -> BankInterestReadinessComputation:
    """Compute safe bank outputs, then apply the decision journal to readiness."""

    reconciliation = inspect_bank_interest_reconciliation(ledger)
    blockers = bank_interest_filing_blockers(reconciliation.blockers)
    computation_is_safe = all(
        blocker.override_policy is BlockerOverridePolicy.ELIGIBLE
        for blocker in blockers
    )
    filing_slice = (
        build_bank_interest_slice(reconciliation.events)
        if computation_is_safe
        else None
    )
    output_amounts = _output_amounts(filing_slice)
    context = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256=_ledger_sha256(ledger),
        output_amounts=output_amounts,
    )
    readiness = assess_filing_readiness(
        context=context,
        blockers=blockers,
        decision_journal=decision_journal,
    )
    return BankInterestReadinessComputation(
        filing_slice=filing_slice,
        readiness=readiness,
        reconciliation=reconciliation,
    )


def bank_interest_filing_blockers(
    blockers: Iterable[ReconciliationBlocker],
) -> tuple[FilingBlocker, ...]:
    """Classify bank blockers without making incomplete computations overridable."""

    structured = [_to_filing_blocker(blocker) for blocker in blockers]
    return tuple(sorted(structured, key=lambda blocker: blocker.blocker_id))


def _to_filing_blocker(blocker: ReconciliationBlocker) -> FilingBlocker:
    try:
        policy = _BANK_BLOCKER_POLICIES[blocker.code]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported bank-interest blocker code: {blocker.code}"
        ) from exc
    payload = json.dumps(
        {
            "code": blocker.code,
            "evidence_references": list(blocker.evidence_references),
            "event_ids": list(blocker.event_ids),
            "message": blocker.message,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = sha256(payload).hexdigest()[:16]
    return FilingBlocker(
        blocker_id=f"bank-interest:{blocker.code.lower()}:{digest}",
        code=blocker.code,
        message=blocker.message,
        category=policy.category,
        override_policy=policy.override_policy,
        affected_outputs=policy.affected_outputs,
        evidence_references=blocker.evidence_references,
    )


def _ledger_sha256(ledger: BankInterestLedger) -> str:
    rows = [
        row.model_dump(mode="json")
        for row in ledger.evidence_rows
    ]
    rows.sort(
        key=lambda row: json.dumps(
            row,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    payload = json.dumps(
        {
            "assessment_year": ledger.assessment_year,
            "evidence_rows": rows,
            "schema_version": ledger.schema_version,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _output_amounts(
    filing_slice: BankInterestSlice | None,
) -> dict[str, Decimal]:
    if filing_slice is None:
        return {}
    amounts = {
        line.output_path: line.amount
        for line in filing_slice.audit_trace
    }
    amounts.setdefault(_SCHEDULE_OS, filing_slice.total_interest)
    amounts.setdefault(_SCHEDULE_TDS2, filing_slice.tds_claimed)
    return amounts
