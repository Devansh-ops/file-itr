"""Single-source output deltas for the trading-business ITR-3 slice."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from engine.trading_business_ledger import (
    TradingAccountingBasis,
    TradingSegment,
)
from engine.trading_business_types import (
    Section44ADTradingFilingValues,
    TaxAuditApplicabilityAssessment,
    TaxAuditApplicabilityStatus,
    TaxAuditBasis,
    TaxAuditReturnCondition,
    TradingFilingOutputDelta,
    TradingFilingOutputOperation,
    TradingReconciliationResult,
    TradingSegmentResult,
)


_AUDIT_PATH = ("PartA_GEN2", "AuditInfo")


def build_trading_filing_output_deltas(
    accounting_basis: TradingAccountingBasis,
    result: TradingReconciliationResult,
    assessment: TaxAuditApplicabilityAssessment,
    section_44ad_values: Section44ADTradingFilingValues | None,
) -> tuple[TradingFilingOutputDelta, ...]:
    """Describe every projection write and readiness-bound output once."""
    deltas: list[TradingFilingOutputDelta] = []
    if section_44ad_values is not None:
        deltas.extend(_section_44ad_deltas(section_44ad_values))
    else:
        if accounting_basis is TradingAccountingBasis.REGULAR_BOOKS:
            deltas.extend(_regular_books_deltas(result))
        else:
            deltas.extend(_no_books_deltas(result))
        deltas.extend(_ordinary_schedule_bp_deltas(result))
    deltas.extend(_tax_audit_deltas(assessment))
    output_paths = [delta.output_path for delta in deltas]
    if len(output_paths) != len(set(output_paths)):
        raise ValueError("Trading filing output paths must be unique")
    return tuple(deltas)


def output_amounts(
    deltas: tuple[TradingFilingOutputDelta, ...],
) -> dict[str, Decimal]:
    return {
        delta.output_path: delta.context_amount
        for delta in sorted(
            deltas,
            key=lambda item: item.output_path,
        )
    }


def _regular_books_deltas(
    result: TradingReconciliationResult,
) -> tuple[TradingFilingOutputDelta, ...]:
    speculative_income = result.speculative_business_result
    non_speculative_income = result.non_speculative_business_result
    total_income = result.total_business_result
    values = (
        (
            ("TradingAccount", "TurnoverIntradayTrd"),
            _group_turnover(
                result.segment_results,
                speculative=True,
            ),
        ),
        (
            ("TradingAccount", "IncomeIntradayTrd"),
            speculative_income,
        ),
        (
            ("TradingAccount", "TurnoverFutureTrd"),
            _group_turnover(
                result.segment_results,
                speculative=False,
            ),
        ),
        (
            ("TradingAccount", "IncomeFutureTrd"),
            non_speculative_income,
        ),
        (
            (
                "PARTA_PL",
                "CreditsToPL",
                "GrossProfitTrnsfFrmTrdAcc",
            ),
            total_income,
        ),
        (
            ("PARTA_PL", "CreditsToPL", "TotCreditsToPL"),
            total_income,
        ),
        (("PARTA_PL", "DebitsToPL", "PBIDTA"), total_income),
        (("PARTA_PL", "DebitsToPL", "PBT"), total_income),
        (
            ("PARTA_PL", "TaxProvAppr", "ProfitAfterTax"),
            total_income,
        ),
        (
            ("PARTA_PL", "TaxProvAppr", "AmtAvlAppr"),
            total_income,
        ),
        (
            ("PARTA_PL", "TaxProvAppr", "ProprietorAccBalTrf"),
            total_income,
        ),
    )
    return tuple(_add(path, amount) for path, amount in values)


def _no_books_deltas(
    result: TradingReconciliationResult,
) -> tuple[TradingFilingOutputDelta, ...]:
    segment_results = result.segment_results
    fno_turnover = _group_turnover(
        segment_results,
        speculative=False,
    )
    values = (
        (
            ("PARTA_PL", "TurnverFrmSpecActivity"),
            _group_turnover(
                segment_results,
                speculative=True,
            ),
        ),
        (
            ("PARTA_PL", "GrossProfit"),
            _group_gross_result(
                segment_results,
                speculative=True,
            ),
        ),
        (
            ("PARTA_PL", "Expenditure"),
            _group_expenses(
                segment_results,
                speculative=True,
            ),
        ),
        (
            ("PARTA_PL", "NetIncomeFrmSpecActivity"),
            result.speculative_business_result,
        ),
        (
            ("PARTA_PL", "NoBooksOfAccPL", "GrossReceipt"),
            fno_turnover,
        ),
        (
            (
                "PARTA_PL",
                "NoBooksOfAccPL",
                "GrsRcptAccPayeeOrBankMode",
            ),
            fno_turnover,
        ),
        (
            ("PARTA_PL", "NoBooksOfAccPL", "GrossProfit"),
            _group_gross_result(
                segment_results,
                speculative=False,
            ),
        ),
        (
            ("PARTA_PL", "NoBooksOfAccPL", "Expenses"),
            _group_expenses(
                segment_results,
                speculative=False,
            ),
        ),
        (
            ("PARTA_PL", "NoBooksOfAccPL", "NetProfit"),
            result.non_speculative_business_result,
        ),
        (
            (
                "PARTA_PL",
                "NoBooksOfAccPL",
                "TotBusinessProfession",
            ),
            result.non_speculative_business_result,
        ),
    )
    return tuple(_add(path, amount) for path, amount in values)


def _ordinary_schedule_bp_deltas(
    result: TradingReconciliationResult,
) -> tuple[TradingFilingOutputDelta, ...]:
    speculative_income = result.speculative_business_result
    non_speculative_income = result.non_speculative_business_result
    total_income = result.total_business_result
    business = ("ITR3ScheduleBP", "BusinessIncOthThanSpec")
    values = [
        (
            ("ITR3ScheduleBP", "SpecBusinessInc", "NetPLFrmSpecBus"),
            speculative_income,
        ),
        (
            (
                "ITR3ScheduleBP",
                "SpecBusinessInc",
                "AdjustedPLFrmSpecuBus",
            ),
            speculative_income,
        ),
        (business + ("ProfBfrTaxPL",), total_income),
        (business + ("NetPLFromSpecBus",), speculative_income),
    ]
    values.extend(
        (
            business + (field_name,),
            non_speculative_income,
        )
        for field_name in (
            "BalancePLOthThanSpecBus",
            "AdjustedPLOthThanSpecBus",
            "AdjustPLAfterDeprOthSpecInc",
            "TotAfterAddToPLDeprOthSpecInc",
            "PLAftAdjDedBusOthThanSpec",
            "NetPLAftAdjBusOthThanSpec",
            "NetPLBusOthThanSpec7A7B7C",
            "IncomeOtherThanRule",
        )
    )
    values.append(
        (("ITR3ScheduleBP", "IncChrgUnHdProftGain"), total_income)
    )
    return tuple(_add(path, amount) for path, amount in values)


def _section_44ad_deltas(
    values: Section44ADTradingFilingValues,
) -> tuple[TradingFilingOutputDelta, ...]:
    business = ("ITR3ScheduleBP", "BusinessIncOthThanSpec")
    facts = values.filing_facts
    declared_income = values.declared_income
    nature_values = tuple(
        {
            "NameOfBusiness": name,
            "CodeAD": code,
        }
        for name, code in values.business_natures
    )
    deltas = [
        TradingFilingOutputDelta(
            path=("PARTA_PL", "NatOfBus44AD"),
            context_amount=Decimal("0"),
            operation=TradingFilingOutputOperation.EXTEND_UNIQUE,
            projected_value=nature_values,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "GrsTrnOverOrReceipt",
            ),
            values.turnover,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "GrsTrnOverBank",
            ),
            facts.bank_mode_turnover,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "GrsTotalTrnOverInCash",
            ),
            facts.cash_turnover,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "GrsTrnOverAnyOthMode",
            ),
            facts.other_mode_turnover,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "TotPersumptiveInc44AD",
            ),
            declared_income,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "PersumptiveInc44AD6Per",
            ),
            facts.bank_mode_income,
        ),
        _add(
            (
                "PARTA_PL",
                "PersumptiveInc44AD",
                "PersumptiveInc44AD8Per",
            ),
            facts.non_bank_mode_income,
        ),
        _add(
            business
            + (
                "ProfitLossInclRefrdSec",
                "ProfitLossUs44AD",
            ),
            declared_income,
        ),
        _add(
            business + ("TotalProfitFrmActCvrd",),
            declared_income,
        ),
        _add(
            business + ("DeemedProfitBusUs", "Section44AD"),
            declared_income,
        ),
        _add(
            business
            + ("DeemedProfitBusUs", "TotDeemedProfitBusUs"),
            declared_income,
        ),
    ]
    for field_name in (
        "NetPLAftAdjBusOthThanSpec",
        "NetPLBusOthThanSpec7A7B7C",
        "IncomeOtherThanRule",
    ):
        deltas.append(
            _add(business + (field_name,), declared_income)
        )
    deltas.append(
        _add(
            ("ITR3ScheduleBP", "IncChrgUnHdProftGain"),
            declared_income,
        )
    )
    return tuple(deltas)


def _tax_audit_deltas(
    assessment: TaxAuditApplicabilityAssessment,
) -> tuple[TradingFilingOutputDelta, ...]:
    deltas: list[TradingFilingOutputDelta] = []
    turnover = assessment.aggregate_business_turnover
    if turnover is not None:
        if turnover <= Decimal("10000000"):
            turnover_category = "Upto1CR"
        elif turnover <= Decimal("100000000"):
            turnover_category = "Upto10CR"
        else:
            turnover_category = "MoreThan10CR"
        deltas.append(
            _set(
                _AUDIT_PATH + ("TotalSalesExcOneCr",),
                turnover,
                turnover_category,
            )
        )
    if assessment.cash_receipts_ratio is not None:
        deltas.append(
            _set(
                _AUDIT_PATH + ("AgrOFAllAmtsRcvd",),
                assessment.cash_receipts_ratio,
                (
                    "Upto5Per"
                    if assessment.cash_receipts_ratio
                    <= Decimal("0.05")
                    else "MoreThan5Per"
                ),
            )
        )
    if assessment.cash_payments_ratio is not None:
        deltas.append(
            _set(
                _AUDIT_PATH + ("AgrOFAllPayMade",),
                assessment.cash_payments_ratio,
                (
                    "Upto5Per"
                    if assessment.cash_payments_ratio
                    <= Decimal("0.05")
                    else "MoreThan5Per"
                ),
            )
        )
    if (
        assessment.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    ):
        return tuple(deltas)

    required = (
        assessment.status is TaxAuditApplicabilityStatus.REQUIRED
    )
    deltas.append(
        _set(
            _AUDIT_PATH + ("LiableSec44ABflg",),
            Decimal("1") if required else Decimal("0"),
            "Y" if required else "N",
        )
    )
    if not required:
        deltas.extend(
            (
                _remove(_AUDIT_PATH + ("Cndnfor44AB",)),
                _remove(_AUDIT_PATH + ("BiiDetails",)),
            )
        )
        return tuple(deltas)

    condition = _tax_audit_return_condition(assessment)
    deltas.append(
        _set(
            _AUDIT_PATH + ("Cndnfor44AB",),
            Decimal("0"),
            condition.value,
        )
    )
    if condition is TaxAuditReturnCondition.SECTION_44AB_E:
        deltas.append(
            _set(
                _AUDIT_PATH + ("BiiDetails",),
                Decimal("0"),
                {
                    "44AD": "Y",
                    "44ADA": "N",
                    "44AE": "N",
                    "44BB": "N",
                },
            )
        )
    else:
        deltas.append(_remove(_AUDIT_PATH + ("BiiDetails",)))
    return tuple(deltas)


def _tax_audit_return_condition(
    assessment: TaxAuditApplicabilityAssessment,
) -> TaxAuditReturnCondition:
    if any(
        basis
        in {
            TaxAuditBasis.SECTION_44AB_A_TURNOVER_ABOVE_10_CRORE,
            TaxAuditBasis.SECTION_44AB_A_CASH_RATIO_ABOVE_5_PERCENT,
        }
        for basis in assessment.bases
    ):
        return TaxAuditReturnCondition.SECTION_44AB_A
    if (
        TaxAuditBasis.SECTION_44AB_E_44AD_LOCKOUT
        in assessment.bases
    ):
        return TaxAuditReturnCondition.SECTION_44AB_E
    return TaxAuditReturnCondition.OTHER


def _add(
    path: tuple[str, ...],
    amount: Decimal,
) -> TradingFilingOutputDelta:
    return TradingFilingOutputDelta(
        path=path,
        context_amount=amount,
        operation=TradingFilingOutputOperation.ADD,
    )


def _set(
    path: tuple[str, ...],
    context_amount: Decimal,
    projected_value: object,
) -> TradingFilingOutputDelta:
    return TradingFilingOutputDelta(
        path=path,
        context_amount=context_amount,
        operation=TradingFilingOutputOperation.SET,
        projected_value=projected_value,
    )


def _remove(path: tuple[str, ...]) -> TradingFilingOutputDelta:
    return TradingFilingOutputDelta(
        path=path,
        context_amount=Decimal("0"),
        operation=TradingFilingOutputOperation.REMOVE,
    )


def _group_turnover(
    segment_results: Mapping[TradingSegment, TradingSegmentResult],
    *,
    speculative: bool,
) -> Decimal:
    return sum(
        (
            segment_result.turnover
            for segment, segment_result in segment_results.items()
            if segment.is_speculative is speculative
        ),
        Decimal("0"),
    )


def _group_gross_result(
    segment_results: Mapping[TradingSegment, TradingSegmentResult],
    *,
    speculative: bool,
) -> Decimal:
    return sum(
        (
            segment_result.gross_profit - segment_result.gross_loss
            for segment, segment_result in segment_results.items()
            if segment.is_speculative is speculative
        ),
        Decimal("0"),
    )


def _group_expenses(
    segment_results: Mapping[TradingSegment, TradingSegmentResult],
    *,
    speculative: bool,
) -> Decimal:
    return sum(
        (
            segment_result.expenses
            for segment, segment_result in segment_results.items()
            if segment.is_speculative is speculative
        ),
        Decimal("0"),
    )


__all__ = [
    "build_trading_filing_output_deltas",
    "output_amounts",
]
