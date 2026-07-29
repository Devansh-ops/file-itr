"""Versioned normalized ledger for intraday and F&O business."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from engine.bank_interest_ledger import SourceProvenance


Money = Annotated[Decimal, Field(ge=0)]
PositiveQuantity = Annotated[
    Decimal,
    Field(gt=0, decimal_places=8),
]
Price = Annotated[
    Decimal,
    Field(ge=0, decimal_places=8),
]


class TradingInputBasis(StrEnum):
    TRADING_DETAIL = "trading_detail"
    BROKER_TRADING_SUMMARY_ONLY = "broker_trading_summary_only"


class TradingAccountingBasis(StrEnum):
    REGULAR_BOOKS = "regular_books"
    NO_BOOKS = "no_books"


class TradingSegment(StrEnum):
    EQUITY_INTRADAY = "equity_intraday"
    FUTURES = "futures"
    OPTIONS = "options"

    @property
    def is_speculative(self) -> bool:
        return self is TradingSegment.EQUITY_INTRADAY


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class TradingSettlementType(StrEnum):
    SQUARE_OFF = "square_off"
    CASH_SETTLEMENT = "cash_settlement"
    EXPIRY_WORTHLESS = "expiry_worthless"
    EXPIRY_UNEXERCISED = "expiry_unexercised"


class TradingMatchingMethod(StrEnum):
    BROKER_CLOSED_POSITION = "broker_closed_position"
    FIFO = "fifo"


class TradingExpenseType(StrEnum):
    BROKERAGE_AND_EXCHANGE_CHARGES = (
        "brokerage_and_exchange_charges"
    )
    SECURITIES_TRANSACTION_TAX = (
        "securities_transaction_tax"
    )
    GST_NOT_CLAIMED_AS_INPUT_CREDIT = (
        "gst_not_claimed_as_input_credit"
    )
    STAMP_DUTY = "stamp_duty"
    OTHER_ALLOWABLE_BUSINESS_EXPENSE = (
        "other_allowable_business_expense"
    )


class Section44ADElection(StrEnum):
    ELECTED = "elected"
    NOT_ELECTED = "not_elected"


class TradingExpenseComponent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    expense_id: str = Field(min_length=1)
    expense_type: TradingExpenseType
    amount: Money
    deductibility_evidenced: Literal[True]
    provenance: SourceProvenance


class DerivativeEligibilityEvidence(BaseModel):
    """Evidence for the securities-derivative exception in section 43(5)(d)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    contract_note_id: str = Field(min_length=1)
    contract_note_timestamp: datetime
    exchange: str = Field(min_length=1)
    client_identity_and_pan_present: Literal[True]
    electronic_trade: Literal[True]
    registered_intermediary: Literal[True]
    exchange_recognition_reference: str = Field(min_length=1)
    provenance: SourceProvenance


class Section44ADFilingFacts(BaseModel):
    """Human-confirmed inputs for the ITR-3 section 44AD fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    bank_mode_turnover: Money
    cash_turnover: Money
    other_mode_turnover: Money
    bank_mode_income: Money
    non_bank_mode_income: Money
    declared_income: Money
    provenance: SourceProvenance

    @property
    def turnover(self) -> Decimal:
        return (
            self.bank_mode_turnover
            + self.cash_turnover
            + self.other_mode_turnover
        )

    def cross_ties(self, trading_turnover: Decimal) -> bool:
        return (
            self.turnover == trading_turnover
            and (
                self.bank_mode_income + self.non_bank_mode_income
                == self.declared_income
            )
            and (
                self.bank_mode_income
                >= self.bank_mode_turnover * Decimal("0.06")
            )
            and (
                self.non_bank_mode_income
                >= (
                    self.cash_turnover + self.other_mode_turnover
                )
                * Decimal("0.08")
            )
            and self.declared_income <= self.turnover
        )


class TradingAuditFacts(BaseModel):
    """All-business facts needed for a section 44AB/44AD decision."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    other_business_turnover: Money = Decimal("0")
    other_business_turnover_complete: bool = False
    aggregate_amounts_received: Money | None = None
    cash_receipts: Money | None = None
    aggregate_payments_made: Money | None = None
    cash_payments: Money | None = None
    cash_flow_population_complete: bool = False
    section_44ad_election: Section44ADElection | None = None
    section_44ad_eligibility_confirmed: bool | None = None
    section_44ad_presumptive_income_compliant: bool | None = None
    section_44ad_covers_trading_business: bool | None = None
    section_44ad_other_business_turnover: Money | None = None
    section_44ad_filing_facts: Section44ADFilingFacts | None = None
    section_44ad_lockout_applies: bool | None = None
    total_income_exceeds_basic_exemption: bool | None = None
    other_audit_obligation: bool | None = None
    auditor_trading_turnover: Money | None = None
    provenance: SourceProvenance

    @model_validator(mode="after")
    def cash_components_cross_tie(self) -> "TradingAuditFacts":
        _require_component_not_above_total(
            "cash receipts",
            self.cash_receipts,
            self.aggregate_amounts_received,
        )
        _require_component_not_above_total(
            "cash payments",
            self.cash_payments,
            self.aggregate_payments_made,
        )
        _require_component_not_above_total(
            "section 44AD other-business turnover",
            self.section_44ad_other_business_turnover,
            self.other_business_turnover,
        )
        if (
            self.section_44ad_election
            is Section44ADElection.NOT_ELECTED
            and self.section_44ad_covers_trading_business is True
        ):
            raise ValueError(
                "section 44AD cannot cover trading without an election"
            )
        if (
            self.section_44ad_election
            is Section44ADElection.NOT_ELECTED
            and self.section_44ad_other_business_turnover is not None
        ):
            raise ValueError(
                "section 44AD other-business turnover requires an "
                "election"
            )
        if (
            self.section_44ad_filing_facts is not None
            and (
                self.section_44ad_election
                is not Section44ADElection.ELECTED
                or self.section_44ad_covers_trading_business is not True
            )
        ):
            raise ValueError(
                "section 44AD trading filing facts require an election "
                "that covers trading"
            )
        return self


class TradingTrade(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    trade_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    segment: TradingSegment
    account_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    position_side: PositionSide
    opened_on: date
    closed_on: date
    execution_ids: tuple[str, ...]
    matching_method: TradingMatchingMethod
    quantity: PositiveQuantity
    contract_multiplier: PositiveQuantity
    opening_price: Price
    closing_price: Price
    settlement_type: TradingSettlementType = (
        TradingSettlementType.SQUARE_OFF
    )
    expense_components: tuple[TradingExpenseComponent, ...]
    derivative_eligibility: (
        DerivativeEligibilityEvidence | None
    ) = None
    provenance: SourceProvenance

    @model_validator(mode="after")
    def trade_is_supported(self) -> "TradingTrade":
        _require_unique(
            "execution_id",
            list(self.execution_ids),
        )
        if not self.execution_ids:
            raise ValueError(
                "trade requires at least one child execution"
            )
        _require_unique(
            "expense_id",
            [
                expense.expense_id
                for expense in self.expense_components
            ],
        )
        if self.opening_price <= 0:
            raise ValueError(
                "opening execution price must be positive"
            )
        if (
            self.segment is not TradingSegment.OPTIONS
            and self.closing_price <= 0
        ):
            raise ValueError(
                "non-option closing execution price must be positive"
            )
        if (
            self.closing_price == 0
            and (
                self.segment is not TradingSegment.OPTIONS
                or (
                    self.position_side is PositionSide.LONG
                    and self.settlement_type
                    is not TradingSettlementType.EXPIRY_WORTHLESS
                )
                or (
                    self.position_side is PositionSide.SHORT
                    and self.settlement_type
                    is not TradingSettlementType.EXPIRY_UNEXERCISED
                )
            )
        ):
            raise ValueError(
                "zero option close requires the matching expiry outcome"
            )
        if (
            self.settlement_type
            in {
                TradingSettlementType.EXPIRY_WORTHLESS,
                TradingSettlementType.EXPIRY_UNEXERCISED,
            }
            and (
                self.segment is not TradingSegment.OPTIONS
                or self.closing_price != 0
                or (
                    self.settlement_type
                    is TradingSettlementType.EXPIRY_WORTHLESS
                    and self.position_side is not PositionSide.LONG
                )
                or (
                    self.settlement_type
                    is TradingSettlementType.EXPIRY_UNEXERCISED
                    and self.position_side is not PositionSide.SHORT
                )
            )
        ):
            raise ValueError(
                "option expiry outcome must match side and zero close"
            )
        if (
            self.segment is TradingSegment.EQUITY_INTRADAY
            and self.contract_multiplier != 1
        ):
            raise ValueError(
                "equity intraday contract multiplier must be one"
            )
        if (
            self.segment is TradingSegment.EQUITY_INTRADAY
            and self.derivative_eligibility is not None
        ):
            raise ValueError(
                "equity intraday cannot carry derivative eligibility"
            )
        if (
            self.segment
            in {TradingSegment.FUTURES, TradingSegment.OPTIONS}
            and self.derivative_eligibility is None
        ):
            raise ValueError(
                "F&O requires section 43(5)(d) eligibility evidence"
            )
        if (
            self.derivative_eligibility is not None
            and self.derivative_eligibility.exchange != self.exchange
        ):
            raise ValueError(
                "derivative eligibility exchange must match the trade"
            )
        if self.opened_on > self.closed_on:
            raise ValueError("trade cannot close before it opens")
        if not (
            date(2025, 4, 1)
            <= self.closed_on
            <= date(2026, 3, 31)
        ):
            raise ValueError("trade must close within FY 2025-26")
        if (
            self.segment is TradingSegment.EQUITY_INTRADAY
            and self.opened_on != self.closed_on
        ):
            raise ValueError(
                "equity intraday trade must open and close on one date"
            )
        return self

    @property
    def opening_total(self) -> Decimal:
        return (
            self.quantity
            * self.contract_multiplier
            * self.opening_price
        )

    @property
    def closing_total(self) -> Decimal:
        return (
            self.quantity
            * self.contract_multiplier
            * self.closing_price
        )

    @property
    def gross_profit_loss(self) -> Decimal:
        if self.position_side is PositionSide.LONG:
            return self.closing_total - self.opening_total
        return self.opening_total - self.closing_total

    @property
    def tax_audit_turnover(self) -> Decimal:
        if self.segment is TradingSegment.OPTIONS:
            return max(self.opening_total, self.closing_total)
        return abs(self.gross_profit_loss)

    @property
    def deductible_expenses_total(self) -> Decimal:
        return sum(
            (
                expense.amount
                for expense in self.expense_components
            ),
            Decimal("0"),
        )


class BrokerTradingSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    summary_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    segment: TradingSegment
    gross_profit: Money
    gross_loss: Money
    turnover: Money
    expenses: Money
    net_profit_loss: Decimal
    provenance: SourceProvenance

    @model_validator(mode="after")
    def summary_cross_ties(self) -> "BrokerTradingSummary":
        expected = (
            self.gross_profit
            - self.gross_loss
            - self.expenses
        )
        if self.net_profit_loss != expected:
            raise ValueError(
                "broker trading summary net result must equal "
                "profit less loss and expenses"
            )
        return self


class TradingLedger(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    schema_version: Literal["1.0"]
    assessment_year: Literal["2026-27"]
    input_basis: TradingInputBasis
    accounting_basis: TradingAccountingBasis
    trades: tuple[TradingTrade, ...]
    broker_trading_summaries: tuple[BrokerTradingSummary, ...]
    audit_facts: TradingAuditFacts | None = None

    @model_validator(mode="after")
    def ledger_is_coherent(self) -> "TradingLedger":
        _require_unique(
            "trade_id",
            [trade.trade_id for trade in self.trades],
        )
        _require_unique(
            "trade sequence",
            [trade.sequence for trade in self.trades],
        )
        _require_unique(
            "execution_id",
            [
                execution_id
                for trade in self.trades
                for execution_id in trade.execution_ids
            ],
        )
        _require_unique(
            "expense_id",
            [
                expense.expense_id
                for trade in self.trades
                for expense in trade.expense_components
            ],
        )
        _require_unique(
            "summary_id",
            [
                summary.summary_id
                for summary in self.broker_trading_summaries
            ],
        )
        _require_unique(
            "broker account/segment summary",
            [
                (summary.account_id, summary.segment)
                for summary in self.broker_trading_summaries
            ],
        )
        if (
            self.input_basis
            is TradingInputBasis.TRADING_DETAIL
            and not self.trades
        ):
            raise ValueError(
                "trading-detail basis requires trades"
            )
        if (
            self.input_basis
            is TradingInputBasis.BROKER_TRADING_SUMMARY_ONLY
            and self.trades
        ):
            raise ValueError(
                "summary-only basis cannot contain trading detail"
            )
        if not self.broker_trading_summaries:
            raise ValueError("broker trading summaries are required")
        detailed_groups = {
            (trade.account_id, trade.segment)
            for trade in self.trades
        }
        summary_groups = {
            (summary.account_id, summary.segment)
            for summary in self.broker_trading_summaries
        }
        if detailed_groups - summary_groups:
            raise ValueError(
                "every trade account/segment requires a broker "
                "trading summary"
            )
        return self


class TradingLedgerError(ValueError):
    pass


def load_trading_ledger(
    data: Mapping[str, Any],
) -> TradingLedger:
    if not isinstance(data, Mapping):
        raise TradingLedgerError("Trading ledger must be a mapping")
    if data.get("schema_version") != "1.0":
        raise TradingLedgerError(
            f"Trading schema_version {data.get('schema_version')!r} "
            "is not supported"
        )
    try:
        return TradingLedger.model_validate(data)
    except ValidationError as exc:
        raise TradingLedgerError(str(exc)) from exc


def _require_unique(
    label: str,
    values: list[object],
) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")


def _require_component_not_above_total(
    label: str,
    component: Decimal | None,
    total: Decimal | None,
) -> None:
    if component is not None and total is None:
        raise ValueError(f"{label} requires its aggregate total")
    if component is not None and total is not None and component > total:
        raise ValueError(f"{label} cannot exceed its aggregate total")
