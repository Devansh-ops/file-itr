"""Public facade for AY 2026-27 fixed-income computation."""

from engine.fixed_income_filing import build_fixed_income_slice
from engine.fixed_income_ledger import (
    FixedIncomeAccountSummary,
    FixedIncomeClosingPosition,
    FixedIncomeEvent,
    FixedIncomeEventType,
    FixedIncomeInstrument,
    FixedIncomeInstrumentKind,
    FixedIncomeLedger,
    FixedIncomeLedgerError,
    FixedIncomeLegalForm,
    FixedIncomeReceiptObservation,
    FixedIncomeTermsEvidence,
    ReceiptEvidenceType,
    SettlementBreakdown,
    UnsupportedFixedIncomeFeature,
    load_fixed_income_ledger,
)
from engine.fixed_income_reconciliation import reconcile_fixed_income
from engine.fixed_income_types import (
    FixedIncomeAuditLine,
    FixedIncomeBlocker,
    FixedIncomeReconciliationError,
    FixedIncomeReconciliationResult,
    FixedIncomeSlice,
    FixedIncomeTaxBucket,
    MatchedFixedIncomeDisposal,
)


def compute_fixed_income_slice(
    ledger: FixedIncomeLedger,
) -> FixedIncomeSlice:
    return build_fixed_income_slice(
        ledger,
        reconcile_fixed_income(ledger),
    )


__all__ = [
    "FixedIncomeAccountSummary",
    "FixedIncomeAuditLine",
    "FixedIncomeBlocker",
    "FixedIncomeClosingPosition",
    "FixedIncomeEvent",
    "FixedIncomeEventType",
    "FixedIncomeInstrument",
    "FixedIncomeInstrumentKind",
    "FixedIncomeLedger",
    "FixedIncomeLedgerError",
    "FixedIncomeLegalForm",
    "FixedIncomeReceiptObservation",
    "FixedIncomeReconciliationError",
    "FixedIncomeReconciliationResult",
    "FixedIncomeSlice",
    "FixedIncomeTaxBucket",
    "FixedIncomeTermsEvidence",
    "MatchedFixedIncomeDisposal",
    "ReceiptEvidenceType",
    "SettlementBreakdown",
    "UnsupportedFixedIncomeFeature",
    "build_fixed_income_slice",
    "compute_fixed_income_slice",
    "load_fixed_income_ledger",
    "reconcile_fixed_income",
]
