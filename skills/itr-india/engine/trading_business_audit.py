"""Deterministic section 44AB/44AD applicability assessment."""

from __future__ import annotations

from decimal import Decimal

from engine.trading_business_ledger import (
    Section44ADFilingFacts,
    Section44ADElection,
    TradingAuditFacts,
    TradingLedger,
)
from engine.trading_business_types import (
    Section44ADOtherBusinessSplitStatus,
    TaxAuditApplicabilityAssessment,
    TaxAuditBasis,
    TaxAuditApplicabilityStatus,
    TaxAuditUnresolvedCondition,
    TradingReconciliationResult,
)


_ONE_CRORE = Decimal("10000000")
_TEN_CRORE = Decimal("100000000")
_FIVE_PERCENT = Decimal("0.05")


def assess_tax_audit_applicability(
    ledger: TradingLedger,
    result: TradingReconciliationResult,
) -> TaxAuditApplicabilityAssessment:
    facts = ledger.audit_facts
    if facts is None:
        return _assessment(
            TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED,
            aggregate_business_turnover=None,
            unresolved_conditions=(
                TaxAuditUnresolvedCondition.ALL_BUSINESS_TAX_AUDIT_FACTS,
            ),
        )

    trading_turnover = sum(
        (
            segment_result.turnover
            for segment_result in result.segment_results.values()
        ),
        Decimal("0"),
    )
    aggregate_turnover = (
        trading_turnover + facts.other_business_turnover
        if facts.other_business_turnover_complete
        else None
    )
    section_44ad_filing_facts = (
        _validated_section_44ad_filing_facts(
            facts,
            trading_turnover,
        )
    )
    section_44ad_other_business_split_status = (
        _section_44ad_other_business_split_status(facts)
    )
    receipts_ratio = _cash_ratio(
        facts.cash_receipts,
        facts.aggregate_amounts_received,
        facts.cash_flow_population_complete,
    )
    payments_ratio = _cash_ratio(
        facts.cash_payments,
        facts.aggregate_payments_made,
        facts.cash_flow_population_complete,
    )
    section_44ab_a_turnover = _section_44ab_a_turnover(
        facts,
        trading_turnover,
        aggregate_turnover,
        section_44ad_filing_facts,
        section_44ad_other_business_split_status,
    )

    required_bases = _required_bases(
        facts,
        section_44ab_a_turnover,
        receipts_ratio,
        payments_ratio,
    )
    unresolved = _unresolved_conditions(
        facts,
        trading_turnover,
        aggregate_turnover,
        receipts_ratio,
        payments_ratio,
        section_44ad_filing_facts,
        section_44ad_other_business_split_status,
    )
    if required_bases:
        return _assessment(
            TaxAuditApplicabilityStatus.REQUIRED,
            aggregate_business_turnover=aggregate_turnover,
            cash_receipts_ratio=receipts_ratio,
            cash_payments_ratio=payments_ratio,
            bases=required_bases,
            unresolved_conditions=unresolved,
            section_44ad_filing_facts=section_44ad_filing_facts,
        )
    if unresolved:
        return _assessment(
            TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED,
            aggregate_business_turnover=aggregate_turnover,
            cash_receipts_ratio=receipts_ratio,
            cash_payments_ratio=payments_ratio,
            unresolved_conditions=unresolved,
            section_44ad_filing_facts=section_44ad_filing_facts,
        )
    return _assessment(
        TaxAuditApplicabilityStatus.NOT_REQUIRED,
        aggregate_business_turnover=aggregate_turnover,
        cash_receipts_ratio=receipts_ratio,
        cash_payments_ratio=payments_ratio,
        bases=_not_required_bases(
            facts,
            section_44ab_a_turnover,
            section_44ad_filing_facts,
            section_44ad_other_business_split_status,
        ),
        section_44ad_filing_facts=section_44ad_filing_facts,
    )


def _required_bases(
    facts: TradingAuditFacts,
    section_44ab_a_turnover: Decimal | None,
    receipts_ratio: Decimal | None,
    payments_ratio: Decimal | None,
) -> tuple[TaxAuditBasis, ...]:
    bases: list[TaxAuditBasis] = []
    if facts.other_audit_obligation is True:
        bases.append(TaxAuditBasis.OTHER_AUDIT_OBLIGATION)
    if (
        facts.section_44ad_lockout_applies is True
        and facts.total_income_exceeds_basic_exemption is True
    ):
        bases.append(TaxAuditBasis.SECTION_44AB_E_44AD_LOCKOUT)
    if section_44ab_a_turnover is not None:
        if section_44ab_a_turnover > _TEN_CRORE:
            bases.append(
                TaxAuditBasis.SECTION_44AB_A_TURNOVER_ABOVE_10_CRORE
            )
        elif (
            section_44ab_a_turnover > _ONE_CRORE
            and (
                (
                    receipts_ratio is not None
                    and receipts_ratio > _FIVE_PERCENT
                )
                or (
                    payments_ratio is not None
                    and payments_ratio > _FIVE_PERCENT
                )
            )
        ):
            bases.append(
                TaxAuditBasis.SECTION_44AB_A_CASH_RATIO_ABOVE_5_PERCENT
            )
    return tuple(sorted(bases, key=lambda basis: basis.value))


def _unresolved_conditions(
    facts: TradingAuditFacts,
    trading_turnover: Decimal,
    aggregate_turnover: Decimal | None,
    receipts_ratio: Decimal | None,
    payments_ratio: Decimal | None,
    section_44ad_filing_facts: Section44ADFilingFacts | None,
    section_44ad_other_business_split_status: (
        Section44ADOtherBusinessSplitStatus
    ),
) -> tuple[TaxAuditUnresolvedCondition, ...]:
    unresolved: list[TaxAuditUnresolvedCondition] = []
    condition = TaxAuditUnresolvedCondition
    if aggregate_turnover is None:
        unresolved.append(
            condition.COMPLETE_OTHER_BUSINESS_TURNOVER
        )
    if facts.other_audit_obligation is None:
        unresolved.append(
            condition.OTHER_AUDIT_OBLIGATION
        )
    if facts.section_44ad_election is None:
        unresolved.append(
            condition.SECTION_44AD_ELECTION
        )
    if facts.section_44ad_lockout_applies is None:
        unresolved.append(
            condition.SECTION_44AD_HISTORY
        )
    elif (
        facts.section_44ad_lockout_applies
        and facts.total_income_exceeds_basic_exemption is None
    ):
        unresolved.append(
            condition.SECTION_44AD_LOCKOUT_TOTAL_INCOME_COMPARISON
        )
    if (
        facts.section_44ad_election
        is Section44ADElection.ELECTED
    ):
        if facts.section_44ad_eligibility_confirmed is not True:
            unresolved.append(
                condition.SECTION_44AD_ELIGIBILITY
            )
        if facts.section_44ad_presumptive_income_compliant is not True:
            unresolved.append(
                condition.SECTION_44AD_PRESUMPTIVE_INCOME_COMPLIANCE
            )
        if facts.section_44ad_covers_trading_business is None:
            unresolved.append(
                condition.SECTION_44AD_TRADING_COVERAGE
            )
        elif (
            section_44ad_other_business_split_status
            is Section44ADOtherBusinessSplitStatus.MISSING
        ):
            unresolved.append(
                condition.SECTION_44AD_OTHER_BUSINESS_TURNOVER_SPLIT
            )
        if facts.section_44ad_covers_trading_business is True:
            if facts.section_44ad_filing_facts is None:
                unresolved.append(
                    condition.SECTION_44AD_FILING_AMOUNTS
                )
            elif section_44ad_filing_facts is None:
                unresolved.append(
                    condition.SECTION_44AD_FILING_CROSS_TIE
                )
    if (
        not facts.cash_flow_population_complete
        or receipts_ratio is None
        or payments_ratio is None
    ):
        unresolved.append(
            condition.COMPLETE_ALL_BUSINESS_CASH_FLOW_POPULATION
        )
    if (
        facts.auditor_trading_turnover is not None
        and facts.auditor_trading_turnover != trading_turnover
    ):
        unresolved.append(
            condition.AUDITOR_TRADING_TURNOVER_DISAGREEMENT
        )
    return tuple(
        sorted(
            set(unresolved),
            key=lambda condition: condition.value,
        )
    )


def _validated_section_44ad_filing_facts(
    facts: TradingAuditFacts,
    trading_turnover: Decimal,
) -> Section44ADFilingFacts | None:
    filing_facts = facts.section_44ad_filing_facts
    if (
        facts.section_44ad_election
        is not Section44ADElection.ELECTED
        or facts.section_44ad_eligibility_confirmed is not True
        or facts.section_44ad_presumptive_income_compliant is not True
        or facts.section_44ad_covers_trading_business is not True
        or filing_facts is None
        or not filing_facts.cross_ties(trading_turnover)
    ):
        return None
    return filing_facts


def _not_required_bases(
    facts: TradingAuditFacts,
    section_44ab_a_turnover: Decimal | None,
    section_44ad_filing_facts: Section44ADFilingFacts | None,
    section_44ad_other_business_split_status: (
        Section44ADOtherBusinessSplitStatus
    ),
) -> tuple[TaxAuditBasis, ...]:
    bases: list[TaxAuditBasis] = []
    if section_44ab_a_turnover is not None:
        if section_44ab_a_turnover <= _ONE_CRORE:
            bases.append(
                TaxAuditBasis.SECTION_44AB_A_TURNOVER_UP_TO_1_CRORE
            )
        else:
            bases.append(
                TaxAuditBasis.SECTION_44AB_A_ENHANCED_THRESHOLD
            )
    has_presumptive_business = (
        section_44ad_filing_facts is not None
        or (
            section_44ad_other_business_split_status
            is Section44ADOtherBusinessSplitStatus.VALID
            and facts.section_44ad_other_business_turnover
            is not None
            and facts.section_44ad_other_business_turnover > 0
        )
    )
    if has_presumptive_business:
        bases.append(
            TaxAuditBasis.SECTION_44AD_PRESUMPTIVE_BUSINESS
        )
    return tuple(sorted(bases, key=lambda basis: basis.value))


def _section_44ab_a_turnover(
    facts: TradingAuditFacts,
    trading_turnover: Decimal,
    aggregate_turnover: Decimal | None,
    section_44ad_filing_facts: Section44ADFilingFacts | None,
    section_44ad_other_business_split_status: (
        Section44ADOtherBusinessSplitStatus
    ),
) -> Decimal | None:
    if facts.section_44ad_election is None:
        return None
    if (
        facts.section_44ad_election
        is Section44ADElection.ELECTED
        and (
            facts.section_44ad_eligibility_confirmed is not True
            or facts.section_44ad_presumptive_income_compliant
            is not True
            or facts.section_44ad_covers_trading_business is None
            or (
                facts.section_44ad_covers_trading_business is True
                and section_44ad_filing_facts is None
            )
        )
    ):
        return None
    if (
        section_44ad_other_business_split_status
        is Section44ADOtherBusinessSplitStatus.MISSING
    ):
        return None
    if (
        section_44ad_other_business_split_status
        is Section44ADOtherBusinessSplitStatus.VALID
    ):
        presumptive_other_turnover = (
            facts.section_44ad_other_business_turnover
        )
        assert presumptive_other_turnover is not None
        ordinary_turnover = (
            facts.other_business_turnover
            - presumptive_other_turnover
        )
        if section_44ad_filing_facts is None:
            ordinary_turnover += trading_turnover
        return ordinary_turnover
    return aggregate_turnover


def _section_44ad_other_business_split_status(
    facts: TradingAuditFacts,
) -> Section44ADOtherBusinessSplitStatus:
    applicable = (
        facts.section_44ad_election
        is Section44ADElection.ELECTED
        and facts.section_44ad_eligibility_confirmed is True
        and facts.section_44ad_presumptive_income_compliant is True
        and facts.section_44ad_covers_trading_business is not None
        and facts.other_business_turnover_complete
    )
    if not applicable:
        return Section44ADOtherBusinessSplitStatus.NOT_APPLICABLE
    if facts.section_44ad_other_business_turnover is None:
        return Section44ADOtherBusinessSplitStatus.MISSING
    return Section44ADOtherBusinessSplitStatus.VALID


def _cash_ratio(
    cash_amount: Decimal | None,
    aggregate_amount: Decimal | None,
    population_complete: bool,
) -> Decimal | None:
    if (
        not population_complete
        or cash_amount is None
        or aggregate_amount is None
    ):
        return None
    if aggregate_amount == 0:
        return Decimal("0") if cash_amount == 0 else None
    return cash_amount / aggregate_amount


def _assessment(
    status: TaxAuditApplicabilityStatus,
    *,
    aggregate_business_turnover: Decimal | None,
    cash_receipts_ratio: Decimal | None = None,
    cash_payments_ratio: Decimal | None = None,
    bases: tuple[TaxAuditBasis, ...] = (),
    unresolved_conditions: (
        tuple[TaxAuditUnresolvedCondition, ...]
    ) = (),
    section_44ad_filing_facts: Section44ADFilingFacts | None = None,
) -> TaxAuditApplicabilityAssessment:
    return TaxAuditApplicabilityAssessment(
        status=status,
        aggregate_business_turnover=aggregate_business_turnover,
        cash_receipts_ratio=cash_receipts_ratio,
        cash_payments_ratio=cash_payments_ratio,
        bases=bases,
        unresolved_conditions=unresolved_conditions,
        section_44ad_filing_facts=section_44ad_filing_facts,
    )


__all__ = ["assess_tax_audit_applicability"]
