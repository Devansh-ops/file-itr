"""Domain result types for intraday and F&O business."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

from engine.readiness import ReadinessAssessment
from engine.trading_business_ledger import (
    Section44ADFilingFacts,
    TradingAccountingBasis,
    TradingExpenseType,
    TradingSegment,
)


@dataclass(frozen=True, slots=True)
class TradingSegmentResult:
    segment: TradingSegment
    gross_profit: Decimal
    gross_loss: Decimal
    turnover: Decimal
    expenses: Decimal
    expense_totals: Mapping[TradingExpenseType, Decimal]
    net_profit_loss: Decimal


@dataclass(frozen=True, slots=True)
class TradingLossCategories:
    speculative_loss: Decimal
    non_speculative_business_loss: Decimal


class TaxAuditApplicabilityStatus(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"


class TaxAuditReturnCondition(StrEnum):
    SECTION_44AB_A = "bi"
    SECTION_44AB_E = "bii"
    OTHER = "biii"


class Section44ADOtherBusinessSplitStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"
    VALID = "valid"


class TaxAuditBasis(StrEnum):
    OTHER_AUDIT_OBLIGATION = "other_audit_obligation"
    SECTION_44AB_A_TURNOVER_ABOVE_10_CRORE = (
        "section_44AB_a_turnover_above_10_crore"
    )
    SECTION_44AB_A_CASH_RATIO_ABOVE_5_PERCENT = (
        "section_44AB_a_cash_ratio_above_5_percent"
    )
    SECTION_44AB_E_44AD_LOCKOUT = (
        "section_44AB_e_44AD_lockout"
    )
    SECTION_44AB_A_TURNOVER_UP_TO_1_CRORE = (
        "section_44AB_a_turnover_up_to_1_crore"
    )
    SECTION_44AB_A_ENHANCED_THRESHOLD = (
        "section_44AB_a_enhanced_threshold"
    )
    SECTION_44AD_PRESUMPTIVE_BUSINESS = (
        "section_44AD_presumptive_business"
    )


class TaxAuditUnresolvedCondition(StrEnum):
    ALL_BUSINESS_TAX_AUDIT_FACTS = (
        "all_business_tax_audit_facts"
    )
    COMPLETE_OTHER_BUSINESS_TURNOVER = (
        "complete_other_business_turnover"
    )
    OTHER_AUDIT_OBLIGATION = "other_audit_obligation"
    SECTION_44AD_ELECTION = "section_44ad_election"
    SECTION_44AD_HISTORY = "section_44ad_history"
    SECTION_44AD_LOCKOUT_TOTAL_INCOME_COMPARISON = (
        "section_44ad_lockout_total_income_comparison"
    )
    SECTION_44AD_ELIGIBILITY = "section_44ad_eligibility"
    SECTION_44AD_PRESUMPTIVE_INCOME_COMPLIANCE = (
        "section_44ad_presumptive_income_compliance"
    )
    SECTION_44AD_TRADING_COVERAGE = (
        "section_44ad_trading_coverage"
    )
    SECTION_44AD_OTHER_BUSINESS_TURNOVER_SPLIT = (
        "section_44ad_other_business_turnover_split"
    )
    SECTION_44AD_FILING_AMOUNTS = (
        "section_44ad_filing_amounts"
    )
    SECTION_44AD_FILING_CROSS_TIE = (
        "section_44ad_filing_cross_tie"
    )
    COMPLETE_ALL_BUSINESS_CASH_FLOW_POPULATION = (
        "complete_all_business_cash_flow_population"
    )
    AUDITOR_TRADING_TURNOVER_DISAGREEMENT = (
        "auditor_trading_turnover_disagreement"
    )


@dataclass(frozen=True, slots=True)
class TaxAuditApplicabilityAssessment:
    status: TaxAuditApplicabilityStatus
    aggregate_business_turnover: Decimal | None
    cash_receipts_ratio: Decimal | None
    cash_payments_ratio: Decimal | None
    bases: tuple[TaxAuditBasis, ...]
    unresolved_conditions: tuple[TaxAuditUnresolvedCondition, ...]
    section_44ad_filing_facts: Section44ADFilingFacts | None


@dataclass(frozen=True, slots=True)
class TradingReconciliationBlocker:
    code: str
    message: str
    account_id: str
    segment: TradingSegment
    computed_amount: Decimal | None
    observed_amount: Decimal | None
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradingAuditLine:
    output_path: str
    amount: Decimal
    transformation: str
    trade_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradingReconciliationResult:
    segment_results: Mapping[TradingSegment, TradingSegmentResult]
    speculative_business_result: Decimal
    non_speculative_business_result: Decimal
    total_business_result: Decimal
    loss_categories: TradingLossCategories


class TradingFilingOutputOperation(StrEnum):
    ADD = "add"
    SET = "set"
    REMOVE = "remove"
    EXTEND_UNIQUE = "extend_unique"


@dataclass(frozen=True, slots=True)
class TradingFilingOutputDelta:
    path: tuple[str, ...]
    context_amount: Decimal
    operation: TradingFilingOutputOperation
    projected_value: Any = None

    @property
    def output_path(self) -> str:
        return "/ITR/ITR3/" + "/".join(self.path)


@dataclass(frozen=True, slots=True)
class Section44ADTradingFilingValues:
    filing_facts: Section44ADFilingFacts
    business_natures: tuple[tuple[str, str], ...]

    @property
    def turnover(self) -> Decimal:
        return self.filing_facts.turnover

    @property
    def declared_income(self) -> Decimal:
        return self.filing_facts.declared_income


@dataclass(frozen=True, slots=True)
class TradingBusinessSlice:
    accounting_basis: TradingAccountingBasis
    segment_results: Mapping[TradingSegment, TradingSegmentResult]
    speculative_business_result: Decimal
    non_speculative_business_result: Decimal
    total_business_result: Decimal
    loss_categories: TradingLossCategories
    tax_audit_applicability: TaxAuditApplicabilityAssessment
    section_44ad_filing_values: (
        Section44ADTradingFilingValues | None
    )
    output_deltas: tuple[TradingFilingOutputDelta, ...]
    filing_values: Mapping[str, Any]
    audit_trace: tuple[TradingAuditLine, ...]
    readiness: ReadinessAssessment
