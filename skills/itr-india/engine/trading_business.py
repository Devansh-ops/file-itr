"""Public facade for AY 2026-27 intraday and F&O business."""

from engine.trading_business_audit import (
    assess_tax_audit_applicability,
)
from engine.trading_business_filing import (
    TradingFilingError,
    build_trading_business_itr3_draft,
    build_trading_business_slice,
)
from engine.trading_business_ledger import (
    BrokerTradingSummary,
    DerivativeEligibilityEvidence,
    PositionSide,
    Section44ADFilingFacts,
    Section44ADElection,
    TradingAccountingBasis,
    TradingAuditFacts,
    TradingExpenseComponent,
    TradingExpenseType,
    TradingInputBasis,
    TradingLedger,
    TradingLedgerError,
    TradingMatchingMethod,
    TradingSegment,
    TradingSettlementType,
    TradingTrade,
    load_trading_ledger,
)
from engine.trading_business_reconciliation import (
    TradingReconciliationError,
    reconcile_trading_business,
)
from engine.trading_business_types import (
    Section44ADOtherBusinessSplitStatus,
    Section44ADTradingFilingValues,
    TaxAuditApplicabilityAssessment,
    TaxAuditApplicabilityStatus,
    TaxAuditBasis,
    TaxAuditReturnCondition,
    TaxAuditUnresolvedCondition,
    TradingAuditLine,
    TradingBusinessSlice,
    TradingFilingOutputDelta,
    TradingFilingOutputOperation,
    TradingLossCategories,
    TradingReconciliationBlocker,
    TradingReconciliationResult,
    TradingSegmentResult,
)
from engine.readiness import DecisionJournal


def compute_trading_business_slice(
    ledger: TradingLedger,
    *,
    decision_journal: DecisionJournal | None = None,
) -> TradingBusinessSlice:
    if decision_journal is None:
        decision_journal = DecisionJournal.empty(
            f"ay{ledger.assessment_year}:trading-business"
        )
    result = reconcile_trading_business(ledger)
    return build_trading_business_slice(
        ledger,
        result,
        assess_tax_audit_applicability(ledger, result),
        decision_journal,
    )


__all__ = [
    "PositionSide",
    "Section44ADElection",
    "Section44ADFilingFacts",
    "Section44ADOtherBusinessSplitStatus",
    "DerivativeEligibilityEvidence",
    "TaxAuditApplicabilityAssessment",
    "TaxAuditApplicabilityStatus",
    "TaxAuditBasis",
    "TaxAuditReturnCondition",
    "TaxAuditUnresolvedCondition",
    "Section44ADTradingFilingValues",
    "TradingAuditFacts",
    "TradingAuditLine",
    "BrokerTradingSummary",
    "TradingBusinessSlice",
    "TradingAccountingBasis",
    "TradingExpenseComponent",
    "TradingExpenseType",
    "TradingFilingError",
    "TradingFilingOutputDelta",
    "TradingFilingOutputOperation",
    "TradingInputBasis",
    "TradingLedger",
    "TradingLedgerError",
    "TradingLossCategories",
    "TradingMatchingMethod",
    "TradingReconciliationError",
    "TradingReconciliationBlocker",
    "TradingReconciliationResult",
    "TradingSegment",
    "TradingSettlementType",
    "TradingSegmentResult",
    "TradingTrade",
    "assess_tax_audit_applicability",
    "build_trading_business_itr3_draft",
    "build_trading_business_slice",
    "compute_trading_business_slice",
    "load_trading_ledger",
    "reconcile_trading_business",
]
