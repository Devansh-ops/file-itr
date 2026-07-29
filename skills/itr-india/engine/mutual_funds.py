"""Public facade for AY 2026-27 Indian mutual-fund computation."""

from dataclasses import replace

from engine.mutual_fund_classification import (
    FundClassificationDecision,
    FundClassificationAssessment,
    apply_human_classification_confirmations,
    assess_mutual_fund_classification,
)
from engine.mutual_fund_filing import build_mutual_fund_slice
from engine.mutual_fund_ledger import (
    EvidenceAuthority,
    FundClassificationEvidence,
    FundEventType,
    FundListingEvidence,
    FundStructure,
    MutualFundAccountSummary,
    MutualFundClosingPosition,
    MutualFundEvent,
    MutualFundLedger,
    MutualFundLedgerError,
    MutualFundScheme,
    PortfolioAveragingMethod,
    StatutoryFundClass,
    SttStatus,
    load_mutual_fund_ledger,
)
from engine.mutual_fund_reconciliation import (
    MutualFundFifoResult,
    reconcile_mutual_fund_fifo,
)
from engine.mutual_fund_types import (
    FundAuditLine,
    FundClassificationInterval,
    FundResearchRequest,
    FundTaxBucket,
    MatchedFundDisposal,
    MutualFundBlocker,
    MutualFundReconciliationError,
    MutualFundSlice,
)
from engine.readiness import DecisionJournal


def compute_mutual_fund_slice(
    ledger: MutualFundLedger,
    *,
    decision_journal: DecisionJournal | None = None,
) -> MutualFundSlice:
    if decision_journal is None:
        decision_journal = DecisionJournal.empty(
            f"ay{ledger.assessment_year}:mutual-funds"
        )
    assessment = assess_mutual_fund_classification(ledger)
    fifo = reconcile_mutual_fund_fifo(ledger, assessment)
    primary_slice = build_mutual_fund_slice(
        ledger,
        assessment,
        fifo,
        decision_journal,
    )
    confirmation_result = apply_human_classification_confirmations(
        ledger,
        assessment,
        primary_slice.readiness,
        decision_journal,
    )
    if not confirmation_result.applied_decision_ids:
        return replace(
            primary_slice,
            classification_decision_findings=(
                confirmation_result.findings
            ),
        )
    provisional_fifo = reconcile_mutual_fund_fifo(
        ledger,
        confirmation_result.assessment,
    )
    provisional_slice = build_mutual_fund_slice(
        ledger,
        confirmation_result.assessment,
        provisional_fifo,
        DecisionJournal.empty(
            f"ay{ledger.assessment_year}:mutual-funds-provisional"
        ),
    )
    return replace(
        primary_slice,
        provisional_classifications=(
            confirmation_result.assessment.classifications
        ),
        provisional_bucket_totals=provisional_fifo.bucket_totals,
        provisional_matched_disposals=(
            provisional_fifo.matched_disposals
        ),
        provisional_filing_values=provisional_slice.filing_values,
        applied_classification_decision_ids=(
            confirmation_result.applied_decision_ids
        ),
        classification_decision_findings=(
            confirmation_result.findings
        ),
    )


__all__ = [
    "EvidenceAuthority",
    "FundAuditLine",
    "FundClassificationAssessment",
    "FundClassificationDecision",
    "FundClassificationEvidence",
    "FundClassificationInterval",
    "FundEventType",
    "FundListingEvidence",
    "FundResearchRequest",
    "FundStructure",
    "FundTaxBucket",
    "MatchedFundDisposal",
    "MutualFundAccountSummary",
    "MutualFundBlocker",
    "MutualFundClosingPosition",
    "MutualFundEvent",
    "MutualFundFifoResult",
    "MutualFundLedger",
    "MutualFundLedgerError",
    "MutualFundReconciliationError",
    "MutualFundScheme",
    "MutualFundSlice",
    "PortfolioAveragingMethod",
    "StatutoryFundClass",
    "SttStatus",
    "assess_mutual_fund_classification",
    "build_mutual_fund_slice",
    "compute_mutual_fund_slice",
    "load_mutual_fund_ledger",
    "reconcile_mutual_fund_fifo",
]
