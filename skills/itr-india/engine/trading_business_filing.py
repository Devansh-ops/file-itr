"""Filing projection for reconciled intraday and F&O business."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from engine.trading_business_types import (
    Section44ADTradingFilingValues,
    TaxAuditApplicabilityAssessment,
    TaxAuditApplicabilityStatus,
    TradingAuditLine,
    TradingBusinessSlice,
    TradingFilingOutputDelta,
    TradingFilingOutputOperation,
    TradingReconciliationResult,
)
from engine.trading_business_ledger import (
    Section44ADElection,
    TradingAccountingBasis,
    TradingInputBasis,
    TradingLedger,
)
from engine.trading_business_output import (
    build_trading_filing_output_deltas,
    output_amounts,
)
from engine.readiness import (
    BlockerCategory,
    BlockerOverridePolicy,
    ComputationBasis,
    DecisionJournal,
    FilingBlocker,
    FilingComputationContext,
    FilingReadiness,
    assess_filing_readiness,
)


_AUDIT_OUTPUT_PATH = (
    "/ITR/ITR3/PartA_GEN2/AuditInfo/LiableSec44ABflg"
)


class TradingFilingError(ValueError):
    pass


def build_trading_business_slice(
    ledger: TradingLedger,
    result: TradingReconciliationResult,
    tax_audit_applicability: TaxAuditApplicabilityAssessment,
    decision_journal: DecisionJournal,
) -> TradingBusinessSlice:
    section_44ad_values = _section_44ad_filing_values(
        result,
        tax_audit_applicability,
    )
    output_deltas = build_trading_filing_output_deltas(
        ledger.accounting_basis,
        result,
        tax_audit_applicability,
        section_44ad_values,
    )
    filing_output_amounts = output_amounts(output_deltas)
    filing_values = {
        "ScheduleBP": {
            "SpeculativeBusinessIncome": (
                result.speculative_business_result
            ),
            "NonSpeculativeBusinessIncome": (
                result.non_speculative_business_result
            ),
            "TotalTradingBusinessIncome": (
                result.total_business_result
            ),
        },
        "PartA_GEN2": {
            "TaxAuditApplicability": (
                tax_audit_applicability.status.value
            ),
            "AggregateBusinessTurnover": (
                tax_audit_applicability.aggregate_business_turnover
            ),
        },
    }
    if section_44ad_values is not None:
        filing_values["ScheduleBP"][
            "Section44ADDeclaredIncome"
        ] = section_44ad_values.declared_income
    filing_values = _freeze(filing_values)
    context = FilingComputationContext.create(
        computation_basis=(
            ComputationBasis.SOURCE_SUMMARY_ONLY
            if ledger.input_basis
            is TradingInputBasis.BROKER_TRADING_SUMMARY_ONLY
            else ComputationBasis.INDEPENDENT_EVIDENCE
        ),
        normalized_input_sha256=sha256(
            ledger.model_dump_json().encode("utf-8")
        ).hexdigest(),
        output_amounts=filing_output_amounts,
    )
    blockers: list[FilingBlocker] = []
    if (
        ledger.input_basis
        is TradingInputBasis.BROKER_TRADING_SUMMARY_ONLY
    ):
        blockers.append(
            _summary_only_blocker(ledger, filing_output_amounts)
        )
    if (
        tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    ):
        blockers.append(
            _tax_audit_review_blocker(tax_audit_applicability)
        )
    if (
        ledger.accounting_basis is TradingAccountingBasis.NO_BOOKS
        and section_44ad_values is None
        and result.non_speculative_business_result < 0
    ):
        blockers.append(_no_books_fno_loss_blocker())
    if (
        tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
        and tax_audit_applicability.aggregate_business_turnover
        is None
    ):
        blockers.append(_aggregate_turnover_blocker())
    if (
        ledger.audit_facts is not None
        and ledger.audit_facts.section_44ad_election
        is Section44ADElection.ELECTED
        and ledger.audit_facts.section_44ad_covers_trading_business
        is True
        and section_44ad_values is None
    ):
        blockers.append(_section_44ad_filing_facts_blocker())
    readiness = assess_filing_readiness(
        context=context,
        blockers=tuple(blockers),
        decision_journal=decision_journal,
    )
    return TradingBusinessSlice(
        accounting_basis=ledger.accounting_basis,
        segment_results=result.segment_results,
        speculative_business_result=(
            result.speculative_business_result
        ),
        non_speculative_business_result=(
            result.non_speculative_business_result
        ),
        total_business_result=result.total_business_result,
        loss_categories=result.loss_categories,
        tax_audit_applicability=tax_audit_applicability,
        section_44ad_filing_values=section_44ad_values,
        output_deltas=output_deltas,
        filing_values=filing_values,
        audit_trace=_audit_trace(
            ledger,
            result,
            section_44ad_values,
            output_deltas,
        ),
        readiness=readiness,
    )


def build_trading_business_itr3_draft(
    base_return: Mapping[str, Any],
    trading_slice: TradingBusinessSlice,
) -> dict[str, Any]:
    """Project reconciled trading results into an AY 2026-27 ITR-3."""
    if trading_slice.readiness.state not in {
        FilingReadiness.INDEPENDENTLY_FILING_READY,
        FilingReadiness.FILING_READY_BY_HUMAN_OVERRIDE,
    }:
        raise TradingFilingError(
            "Trading business slice is not filing-ready"
        )
    if (
        trading_slice.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    ):
        raise TradingFilingError(
            "Tax-audit applicability requires human review before "
            "an ITR-3 draft can be projected"
        )
    draft = deepcopy(base_return)
    itr3 = draft["ITR"]["ITR3"]
    if any(
        delta.path[0] == "TradingAccount"
        for delta in trading_slice.output_deltas
    ):
        itr3.setdefault(
            "TradingAccount",
            {
                "OperatingRevenueTotal": 0,
                "SalesGrossReceiptsTotal": 0,
                "TotRevenueFrmOperations": 0,
                "TardingAccTotCred": 0,
                "DirectExpenses": 0,
            },
        )
    _apply_output_deltas(itr3, trading_slice.output_deltas)
    return draft


def _section_44ad_filing_values(
    result: TradingReconciliationResult,
    assessment: TaxAuditApplicabilityAssessment,
) -> Section44ADTradingFilingValues | None:
    filing_facts = assessment.section_44ad_filing_facts
    if filing_facts is None:
        return None
    business_natures: list[tuple[str, str]] = []
    if any(
        segment.is_speculative for segment in result.segment_results
    ):
        business_natures.append(
            ("Speculative trading", "21009")
        )
    if any(
        not segment.is_speculative for segment in result.segment_results
    ):
        business_natures.append(
            ("Futures and options trading", "21010")
        )
    return Section44ADTradingFilingValues(
        filing_facts=filing_facts,
        business_natures=tuple(business_natures),
    )


def _apply_output_deltas(
    itr3: dict[str, Any],
    deltas: tuple[TradingFilingOutputDelta, ...],
) -> None:
    for delta in deltas:
        parent = itr3
        for component in delta.path[:-1]:
            child = parent.setdefault(component, {})
            if not isinstance(child, dict):
                raise TradingFilingError(
                    f"ITR-3 output path is not an object: {component}"
                )
            parent = child
        field_name = delta.path[-1]
        if delta.operation is TradingFilingOutputOperation.ADD:
            _add_amount(
                parent,
                field_name,
                _whole_rupees(delta.context_amount),
            )
        elif delta.operation is TradingFilingOutputOperation.SET:
            parent[field_name] = deepcopy(delta.projected_value)
        elif delta.operation is TradingFilingOutputOperation.REMOVE:
            parent.pop(field_name, None)
        elif (
            delta.operation
            is TradingFilingOutputOperation.EXTEND_UNIQUE
        ):
            existing = parent.setdefault(field_name, [])
            if not isinstance(existing, list):
                raise TradingFilingError(
                    f"ITR-3 output path is not an array: {field_name}"
                )
            for value in delta.projected_value:
                if value not in existing:
                    existing.append(deepcopy(value))


def _no_books_fno_loss_blocker() -> FilingBlocker:
    return FilingBlocker(
        blocker_id="trading-business:no-books-fno-loss",
        code="NO_BOOKS_FNO_LOSS_REQUIRES_ACCOUNTING_ROUTE",
        message=(
            "The AY 2026-27 no-books NetProfit field cannot represent "
            "an F&O loss; a human must resolve the accounting route"
        ),
        category=BlockerCategory.UNSUPPORTED_SCOPE,
        override_policy=BlockerOverridePolicy.PROHIBITED,
        affected_outputs=(
            "/ITR/ITR3/PARTA_PL/NoBooksOfAccPL/NetProfit",
        ),
    )


def _aggregate_turnover_blocker() -> FilingBlocker:
    return FilingBlocker(
        blocker_id="trading-business:aggregate-turnover",
        code="AGGREGATE_BUSINESS_TURNOVER_REQUIRED_FOR_ITR3",
        message=(
            "Aggregate turnover for every business is required to "
            "populate the ITR-3 audit-information turnover band"
        ),
        category=BlockerCategory.EVIDENCE_GAP,
        override_policy=BlockerOverridePolicy.PROHIBITED,
        affected_outputs=(
            "/ITR/ITR3/PartA_GEN2/AuditInfo/"
            "TotalSalesExcOneCr",
        ),
    )


def _section_44ad_filing_facts_blocker() -> FilingBlocker:
    return FilingBlocker(
        blocker_id="trading-business:section-44ad-filing-facts",
        code="SECTION_44AD_TRADING_FILING_FACTS_REQUIRED",
        message=(
            "The section 44AD trading route requires human-confirmed "
            "turnover and declared-income components that cross-tie"
        ),
        category=BlockerCategory.EVIDENCE_GAP,
        override_policy=BlockerOverridePolicy.PROHIBITED,
        affected_outputs=(
            "/ITR/ITR3/PARTA_PL/PersumptiveInc44AD",
            (
                "/ITR/ITR3/ITR3ScheduleBP/"
                "BusinessIncOthThanSpec/DeemedProfitBusUs/Section44AD"
            ),
        ),
    )


def _summary_only_blocker(
    ledger: TradingLedger,
    output_amounts: Mapping[str, Decimal],
) -> FilingBlocker:
    references = _evidence_references(
        tuple(ledger.broker_trading_summaries)
    )
    return FilingBlocker(
        blocker_id="trading-business:broker-trading-summary-only",
        code="BROKER_TRADING_SUMMARY_ONLY",
        message=(
            "Broker trading summary is available without trading detail; "
            "turnover and trade results are not independently recomputed"
        ),
        category=BlockerCategory.SOURCE_SUMMARY_LIMITATION,
        override_policy=BlockerOverridePolicy.ELIGIBLE,
        affected_outputs=tuple(output_amounts),
        evidence_references=references,
    )


def _tax_audit_review_blocker(
    assessment: TaxAuditApplicabilityAssessment,
) -> FilingBlocker:
    return FilingBlocker(
        blocker_id="trading-business:tax-audit-human-review",
        code="TAX_AUDIT_HUMAN_REVIEW_REQUIRED",
        message=(
            "Tax-audit applicability cannot be decided until these "
            "conditions are resolved: "
            + ", ".join(assessment.unresolved_conditions)
        ),
        category=BlockerCategory.EVIDENCE_GAP,
        override_policy=BlockerOverridePolicy.PROHIBITED,
        affected_outputs=(_AUDIT_OUTPUT_PATH,),
    )


def _audit_trace(
    ledger: TradingLedger,
    result: TradingReconciliationResult,
    section_44ad_values: Section44ADTradingFilingValues | None,
    output_deltas: tuple[TradingFilingOutputDelta, ...],
) -> tuple[TradingAuditLine, ...]:
    if section_44ad_values is not None:
        provenance = section_44ad_values.filing_facts.provenance
        references = (
            (
                f"{provenance.source_document}"
                f"#{provenance.source_location}"
            ),
        )
        trade_ids = tuple(
            sorted(trade.trade_id for trade in ledger.trades)
        )
        turnover_output = _selected_output_path(
            output_deltas,
            (
                "/ITR/ITR3/PARTA_PL/PersumptiveInc44AD/"
                "GrsTrnOverOrReceipt",
            ),
        )
        income_output = _selected_output_path(
            output_deltas,
            (
                "/ITR/ITR3/PARTA_PL/PersumptiveInc44AD/"
                "TotPersumptiveInc44AD",
            ),
        )
        return (
            TradingAuditLine(
                output_path=turnover_output,
                amount=section_44ad_values.turnover,
                transformation=(
                    "sum-human-confirmed-section-44AD-turnover-modes"
                ),
                trade_ids=trade_ids,
                evidence_references=references,
            ),
            TradingAuditLine(
                output_path=income_output,
                amount=section_44ad_values.declared_income,
                transformation=(
                    "sum-human-confirmed-section-44AD-income-rates"
                ),
                trade_ids=trade_ids,
                evidence_references=references,
            ),
        )
    lines: list[TradingAuditLine] = []
    groups = (
        (
            "Intraday",
            tuple(
                segment
                for segment in result.segment_results
                if segment.is_speculative
            ),
            "sum-absolute-settlement-differences",
        ),
        (
            "Future",
            tuple(
                segment
                for segment in result.segment_results
                if not segment.is_speculative
            ),
            (
                "sum-futures-absolute-differences-and-"
                "options-premium-components"
            ),
        ),
    )
    for field_prefix, segments, turnover_transformation in groups:
        if not segments:
            continue
        trades = tuple(
            trade
            for trade in ledger.trades
            if trade.segment in segments
        )
        summaries = tuple(
            summary
            for summary in ledger.broker_trading_summaries
            if summary.segment in segments
        )
        references = _evidence_references(
            (*trades, *summaries)
        )
        turnover = sum(
            (
                result.segment_results[segment].turnover
                for segment in segments
            ),
            Decimal("0"),
        )
        net_result = sum(
            (
                result.segment_results[segment].net_profit_loss
                for segment in segments
            ),
            Decimal("0"),
        )
        if field_prefix == "Intraday":
            turnover_candidates = (
                "/ITR/ITR3/TradingAccount/TurnoverIntradayTrd",
                "/ITR/ITR3/PARTA_PL/TurnverFrmSpecActivity",
            )
            income_candidates = (
                "/ITR/ITR3/TradingAccount/IncomeIntradayTrd",
                "/ITR/ITR3/PARTA_PL/NetIncomeFrmSpecActivity",
            )
        else:
            turnover_candidates = (
                "/ITR/ITR3/TradingAccount/TurnoverFutureTrd",
                "/ITR/ITR3/PARTA_PL/NoBooksOfAccPL/GrossReceipt",
            )
            income_candidates = (
                "/ITR/ITR3/TradingAccount/IncomeFutureTrd",
                "/ITR/ITR3/PARTA_PL/NoBooksOfAccPL/NetProfit",
            )
        turnover_output = _selected_output_path(
            output_deltas,
            turnover_candidates,
        )
        income_output = _selected_output_path(
            output_deltas,
            income_candidates,
        )
        lines.extend(
            (
                TradingAuditLine(
                    output_path=turnover_output,
                    amount=turnover,
                    transformation=turnover_transformation,
                    trade_ids=tuple(
                        sorted(trade.trade_id for trade in trades)
                    ),
                    evidence_references=references,
                ),
                TradingAuditLine(
                    output_path=income_output,
                    amount=net_result,
                    transformation=(
                        "gross-trade-result-less-evidenced-expenses"
                    ),
                    trade_ids=tuple(
                        sorted(trade.trade_id for trade in trades)
                    ),
                    evidence_references=references,
                ),
            )
        )
    return tuple(lines)


def _selected_output_path(
    output_deltas: tuple[TradingFilingOutputDelta, ...],
    candidates: tuple[str, ...],
) -> str:
    available = {
        delta.output_path for delta in output_deltas
    }
    selected = tuple(
        candidate for candidate in candidates if candidate in available
    )
    if len(selected) != 1:
        raise TradingFilingError(
            "Audit trace requires exactly one projected output from: "
            + ", ".join(candidates)
        )
    return selected[0]


def _evidence_references(items: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                (
                    f"{item.provenance.source_document}"
                    f"#{item.provenance.source_location}"
                )
                for item in items
            }
        )
    )


def _add_amount(
    target: dict[str, Any],
    field_name: str,
    amount: int,
) -> None:
    target[field_name] = target.get(field_name, 0) + amount


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _whole_rupees(value: Decimal) -> int:
    return int(
        value.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


__all__ = [
    "TradingFilingError",
    "build_trading_business_itr3_draft",
    "build_trading_business_slice",
]
