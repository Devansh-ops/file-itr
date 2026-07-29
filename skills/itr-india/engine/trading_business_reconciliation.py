"""Recompute trading results and reconcile broker trading summaries."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import MappingProxyType

from engine.trading_business_ledger import (
    TradingInputBasis,
    TradingLedger,
    TradingSegment,
    TradingTrade,
)
from engine.trading_business_types import (
    TradingLossCategories,
    TradingReconciliationBlocker,
    TradingReconciliationResult,
    TradingSegmentResult,
)


class TradingReconciliationError(ValueError):
    def __init__(
        self,
        blockers: list[TradingReconciliationBlocker],
    ) -> None:
        self.blockers = tuple(
            sorted(
                blockers,
                key=lambda blocker: (
                    blocker.account_id,
                    blocker.segment.value,
                    blocker.code,
                    blocker.message,
                ),
            )
        )
        self.blocker_codes = frozenset(
            blocker.code for blocker in self.blockers
        )
        super().__init__(
            "Trading reconciliation blocked: "
            + "; ".join(
                f"{blocker.code}: {blocker.message}"
                for blocker in self.blockers
            )
        )


def reconcile_trading_business(
    ledger: TradingLedger,
) -> TradingReconciliationResult:
    if (
        ledger.input_basis
        is TradingInputBasis.BROKER_TRADING_SUMMARY_ONLY
    ):
        segment_results = _summary_segment_results(ledger)
    else:
        segment_results = _detail_segment_results(ledger)
        _reconcile_summaries(ledger)
    speculative = sum(
        (
            result.net_profit_loss
            for segment, result in segment_results.items()
            if segment.is_speculative
        ),
        Decimal("0"),
    )
    non_speculative = sum(
        (
            result.net_profit_loss
            for segment, result in segment_results.items()
            if not segment.is_speculative
        ),
        Decimal("0"),
    )
    return TradingReconciliationResult(
        segment_results=MappingProxyType(segment_results),
        speculative_business_result=speculative,
        non_speculative_business_result=non_speculative,
        total_business_result=speculative + non_speculative,
        loss_categories=TradingLossCategories(
            speculative_loss=max(-speculative, Decimal("0")),
            non_speculative_business_loss=max(
                -non_speculative,
                Decimal("0"),
            ),
        ),
    )


def _detail_segment_results(
    ledger: TradingLedger,
) -> dict[TradingSegment, TradingSegmentResult]:
    by_segment = defaultdict(list)
    for trade in ledger.trades:
        by_segment[trade.segment].append(trade)
    results = {}
    for segment, trades in sorted(
        by_segment.items(),
        key=lambda item: item[0].value,
    ):
        results[segment] = _result_from_trades(segment, trades)
    return results


def _summary_segment_results(
    ledger: TradingLedger,
) -> dict[TradingSegment, TradingSegmentResult]:
    by_segment = defaultdict(list)
    for summary in ledger.broker_trading_summaries:
        by_segment[summary.segment].append(summary)
    return {
        segment: TradingSegmentResult(
            segment=segment,
            gross_profit=sum(
                (item.gross_profit for item in summaries),
                Decimal("0"),
            ),
            gross_loss=sum(
                (item.gross_loss for item in summaries),
                Decimal("0"),
            ),
            turnover=sum(
                (item.turnover for item in summaries),
                Decimal("0"),
            ),
            expenses=sum(
                (item.expenses for item in summaries),
                Decimal("0"),
            ),
            expense_totals=MappingProxyType({}),
            net_profit_loss=sum(
                (item.net_profit_loss for item in summaries),
                Decimal("0"),
            ),
        )
        for segment, summaries in sorted(
            by_segment.items(),
            key=lambda item: item[0].value,
        )
    }


def _result_from_trades(
    segment: TradingSegment,
    trades: list[TradingTrade],
) -> TradingSegmentResult:
    trade_results = [trade.gross_profit_loss for trade in trades]
    gross_profit = sum(
        (value for value in trade_results if value > 0),
        Decimal("0"),
    )
    gross_loss = sum(
        (-value for value in trade_results if value < 0),
        Decimal("0"),
    )
    expenses = sum(
        (
            trade.deductible_expenses_total for trade in trades
        ),
        Decimal("0"),
    )
    expense_totals = defaultdict(Decimal)
    for trade in trades:
        for expense in trade.expense_components:
            expense_totals[expense.expense_type] += expense.amount
    turnover = sum(
        (trade.tax_audit_turnover for trade in trades),
        Decimal("0"),
    )
    return TradingSegmentResult(
        segment=segment,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        turnover=turnover,
        expenses=expenses,
        expense_totals=MappingProxyType(
            dict(
                sorted(
                    expense_totals.items(),
                    key=lambda item: item[0].value,
                )
            )
        ),
        net_profit_loss=gross_profit - gross_loss - expenses,
    )


def _reconcile_summaries(
    ledger: TradingLedger,
) -> None:
    trades_by_group = defaultdict(list)
    for trade in ledger.trades:
        trades_by_group[(trade.account_id, trade.segment)].append(trade)
    computed_by_group = {
        group: _result_from_trades(group[1], trades)
        for group, trades in trades_by_group.items()
    }
    summaries_by_group = {
        (summary.account_id, summary.segment): summary
        for summary in ledger.broker_trading_summaries
    }
    blockers: list[TradingReconciliationBlocker] = []
    for account_id, segment in sorted(
        set(computed_by_group) | set(summaries_by_group),
        key=lambda group: (group[0], group[1].value),
    ):
        computed = computed_by_group.get((account_id, segment))
        summary = summaries_by_group.get((account_id, segment))
        observed = (
            TradingSegmentResult(
                segment=segment,
                gross_profit=summary.gross_profit,
                gross_loss=summary.gross_loss,
                turnover=summary.turnover,
                expenses=summary.expenses,
                expense_totals=MappingProxyType({}),
                net_profit_loss=summary.net_profit_loss,
            )
            if summary is not None
            else None
        )
        references = tuple(
            (
                f"{summary.provenance.source_document}"
                f"#{summary.provenance.source_location}",
            )
            if summary is not None
            else ()
        )
        if computed is None or observed is None:
            blockers.append(
                TradingReconciliationBlocker(
                    code="BROKER_TRADING_SEGMENT_MISMATCH",
                    message=(
                        f"{account_id}/{segment.value} is missing from "
                        "detail or broker trading summary"
                    ),
                    account_id=account_id,
                    segment=segment,
                    computed_amount=None,
                    observed_amount=None,
                    evidence_references=references,
                )
            )
            continue
        for field_name, code in (
            (
                "gross_profit",
                "BROKER_TRADING_GROSS_PROFIT_MISMATCH",
            ),
            (
                "gross_loss",
                "BROKER_TRADING_GROSS_LOSS_MISMATCH",
            ),
            (
                "turnover",
                "BROKER_TRADING_TURNOVER_MISMATCH",
            ),
            (
                "expenses",
                "BROKER_TRADING_EXPENSES_MISMATCH",
            ),
            (
                "net_profit_loss",
                "BROKER_TRADING_NET_RESULT_MISMATCH",
            ),
        ):
            computed_amount = getattr(computed, field_name)
            observed_amount = getattr(observed, field_name)
            if computed_amount == observed_amount:
                continue
            blockers.append(
                TradingReconciliationBlocker(
                    code=code,
                    message=(
                        f"{account_id}/{segment.value} {field_name} "
                        f"computed as {computed_amount} but "
                        f"broker reported {observed_amount}"
                    ),
                    account_id=account_id,
                    segment=segment,
                    computed_amount=computed_amount,
                    observed_amount=observed_amount,
                    evidence_references=references,
                )
            )
    if blockers:
        raise TradingReconciliationError(blockers)


__all__ = [
    "TradingReconciliationError",
    "reconcile_trading_business",
]
