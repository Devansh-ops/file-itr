"""Versioned normalized ledger for Indian fixed-income investments."""

from __future__ import annotations

from datetime import date
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
Quantity = Annotated[Decimal, Field(ge=0, decimal_places=4)]


class FixedIncomeInstrumentKind(StrEnum):
    GOVERNMENT_SECURITY = "government_security"
    PLAIN_BOND = "plain_bond"
    MARKET_LINKED_DEBENTURE = "market_linked_debenture"


class FixedIncomeLegalForm(StrEnum):
    BOND_OR_DEBENTURE = "bond_or_debenture"
    OTHER_SECURITY = "other_security"


class UnsupportedFixedIncomeFeature(StrEnum):
    DEFAULTED = "defaulted"
    RESTRUCTURED = "restructured"
    PERPETUAL = "perpetual"
    CONVERTIBLE = "convertible"
    BASIS_DISPUTED = "basis_disputed"
    DEEP_DISCOUNT_OR_STRIP = "deep_discount_or_strip"


class FixedIncomeEventType(StrEnum):
    ACQUISITION = "acquisition"
    COUPON = "coupon"
    SALE = "sale"
    REDEMPTION = "redemption"
    MATURITY = "maturity"
    TRANSFER = "transfer"

    @property
    def is_disposal(self) -> bool:
        return self in {
            FixedIncomeEventType.SALE,
            FixedIncomeEventType.REDEMPTION,
            FixedIncomeEventType.MATURITY,
        }

    @property
    def is_receipt(self) -> bool:
        return self is FixedIncomeEventType.COUPON or self.is_disposal


class SettlementBreakdown(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    CLEAN_CAPITAL_ONLY = "clean_capital_only"
    CLEAN_PLUS_ACCRUED_INTEREST = "clean_plus_accrued_interest"
    UNRESOLVED_DIRTY = "unresolved_dirty"


class ReceiptEvidenceType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    FORM_26AS = "form_26as"
    AIS = "ais"
    ISSUER_STATEMENT = "issuer_statement"
    CONTRACT_NOTE = "contract_note"


class FixedIncomeTermsEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_kind: FixedIncomeInstrumentKind
    legal_form: FixedIncomeLegalForm
    exchange_listed: bool
    statutory_zero_coupon_bond: bool
    unsupported_features: tuple[UnsupportedFixedIncomeFeature, ...]
    provenance: SourceProvenance

    @model_validator(mode="after")
    def features_are_unique(self) -> "FixedIncomeTermsEvidence":
        if len(self.unsupported_features) != len(
            set(self.unsupported_features)
        ):
            raise ValueError("unsupported_features must be unique")
        if (
            self.statutory_zero_coupon_bond
            and self.instrument_kind
            is FixedIncomeInstrumentKind.MARKET_LINKED_DEBENTURE
        ):
            raise ValueError(
                "market-linked debenture cannot use the statutory "
                "zero-coupon-bond classification"
            )
        if (
            self.instrument_kind
            is FixedIncomeInstrumentKind.PLAIN_BOND
            and self.legal_form
            is not FixedIncomeLegalForm.BOND_OR_DEBENTURE
        ):
            raise ValueError(
                "plain bond must be evidenced as a bond or debenture"
            )
        return self


class FixedIncomeInstrument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    instrument_name: str = Field(min_length=1, max_length=125)
    terms: FixedIncomeTermsEvidence


class FixedIncomeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    event_type: FixedIncomeEventType
    event_date: date
    account_id: str = Field(min_length=1)
    to_account_id: str | None
    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    quantity: Quantity
    capital_component: Money
    interest_component: Money
    deductible_charges: Money
    securities_transaction_tax: Money
    tds_withheld: Money
    cash_settlement: Money
    exchange_listed_on_event: bool | None
    settlement_breakdown: SettlementBreakdown
    provenance: SourceProvenance

    @model_validator(mode="after")
    def event_shape_is_valid(self) -> "FixedIncomeEvent":
        if self.event_type is FixedIncomeEventType.ACQUISITION:
            if self.quantity <= 0 or self.capital_component <= 0:
                raise ValueError(
                    "acquisition requires positive quantity and capital component"
                )
            expected = (
                self.capital_component
                + self.interest_component
                + self.deductible_charges
                + self.securities_transaction_tax
            )
            if self.tds_withheld or self.cash_settlement != expected:
                raise ValueError(
                    "acquisition cash must equal capital, interest, and charges"
                )
            self._require_capital_settlement_breakdown()
        elif self.event_type is FixedIncomeEventType.COUPON:
            if (
                self.quantity
                or self.capital_component
                or self.interest_component <= 0
                or self.deductible_charges
                or self.securities_transaction_tax
            ):
                raise ValueError(
                    "coupon requires only a positive interest component"
                )
            if (
                self.exchange_listed_on_event is not None
                or self.settlement_breakdown
                is not SettlementBreakdown.NOT_APPLICABLE
            ):
                raise ValueError(
                    "coupon does not carry listing or capital-price facts"
                )
            self._require_receipt_cash_identity()
        elif self.event_type.is_disposal:
            if self.quantity <= 0 or self.capital_component <= 0:
                raise ValueError(
                    "disposal requires positive quantity and capital component"
                )
            if self.exchange_listed_on_event is None:
                raise ValueError(
                    "disposal requires evidenced listing status on event date"
                )
            self._require_capital_settlement_breakdown()
            self._require_receipt_cash_identity()
        else:
            if (
                self.quantity <= 0
                or not self.to_account_id
                or self.to_account_id == self.account_id
            ):
                raise ValueError(
                    "transfer requires quantity and a different destination"
                )
            if any(
                (
                    self.capital_component,
                    self.interest_component,
                    self.tds_withheld,
                )
            ):
                raise ValueError(
                    "transfer cannot contain capital, interest, or TDS"
                )
            if self.cash_settlement != (
                self.deductible_charges
                + self.securities_transaction_tax
            ):
                raise ValueError(
                    "transfer cash must equal charges and STT"
                )
            if (
                self.exchange_listed_on_event is not None
                or self.settlement_breakdown
                is not SettlementBreakdown.NOT_APPLICABLE
            ):
                raise ValueError(
                    "transfer does not carry listing or settlement facts"
                )
        if self.event_type.is_receipt and not (
            date(2025, 4, 1)
            <= self.event_date
            <= date(2026, 3, 31)
        ):
            raise ValueError("receipt event must fall within FY 2025-26")
        if self.event_date > date(2026, 3, 31):
            raise ValueError(
                "fixed-income event cannot be after FY 2025-26"
            )
        return self

    def _require_capital_settlement_breakdown(self) -> None:
        if (
            self.settlement_breakdown
            is SettlementBreakdown.NOT_APPLICABLE
        ):
            raise ValueError(
                "acquisition/disposal requires a settlement breakdown"
            )
        if (
            self.settlement_breakdown
            is SettlementBreakdown.CLEAN_CAPITAL_ONLY
            and self.interest_component
        ):
            raise ValueError(
                "clean-capital-only settlement cannot contain interest"
            )
        if (
            self.settlement_breakdown
            is SettlementBreakdown.CLEAN_PLUS_ACCRUED_INTEREST
            and not self.interest_component
        ):
            raise ValueError(
                "clean-plus-accrued-interest settlement requires interest"
            )
        if (
            self.settlement_breakdown
            is SettlementBreakdown.UNRESOLVED_DIRTY
            and self.interest_component
        ):
            raise ValueError(
                "unresolved dirty settlement cannot claim an interest split"
            )

    def _require_receipt_cash_identity(self) -> None:
        if self.tds_withheld > self.interest_component:
            raise ValueError("TDS cannot exceed the interest component")
        expected = (
            self.capital_component
            + self.interest_component
            - self.deductible_charges
            - self.securities_transaction_tax
            - self.tds_withheld
        )
        if self.cash_settlement != expected:
            raise ValueError(
                "receipt cash must reconcile capital, interest, charges, and TDS"
            )


class FixedIncomeReceiptObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    evidence_type: ReceiptEvidenceType
    gross_interest: Money | None
    tds_withheld: Money | None
    net_cash_received: Money | None
    provenance: SourceProvenance

    @model_validator(mode="after")
    def observation_shape_is_valid(self) -> "FixedIncomeReceiptObservation":
        if (
            self.gross_interest is None
            and self.tds_withheld is None
            and self.net_cash_received is None
        ):
            raise ValueError("receipt observation must state at least one fact")
        if (
            self.evidence_type is ReceiptEvidenceType.BANK_STATEMENT
            and self.net_cash_received is None
        ):
            raise ValueError("bank observation requires net cash")
        if (
            self.evidence_type is ReceiptEvidenceType.FORM_26AS
            and (
                self.gross_interest is None
                or self.tds_withheld is None
            )
        ):
            raise ValueError("Form 26AS observation requires interest and TDS")
        return self


class FixedIncomeClosingPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    quantity: Quantity
    provenance: SourceProvenance


class FixedIncomeAccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1)
    net_cash_receipts: Money
    closing_positions: tuple[FixedIncomeClosingPosition, ...]
    provenance: SourceProvenance


class FixedIncomeLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    assessment_year: Literal["2026-27"]
    instruments: tuple[FixedIncomeInstrument, ...]
    events: tuple[FixedIncomeEvent, ...]
    receipt_observations: tuple[FixedIncomeReceiptObservation, ...]
    account_summaries: tuple[FixedIncomeAccountSummary, ...]

    @model_validator(mode="after")
    def identities_and_references_are_valid(self) -> "FixedIncomeLedger":
        _require_unique(
            "instrument ISIN",
            [instrument.isin for instrument in self.instruments],
        )
        _require_unique("event_id", [event.event_id for event in self.events])
        _require_unique("sequence", [event.sequence for event in self.events])
        _require_unique(
            "observation_id",
            [
                observation.observation_id
                for observation in self.receipt_observations
            ],
        )
        _require_unique(
            "account summary",
            [summary.account_id for summary in self.account_summaries],
        )
        for summary in self.account_summaries:
            _require_unique(
                f"{summary.account_id} closing-position ISIN",
                [
                    position.isin
                    for position in summary.closing_positions
                ],
            )
        known_isins = {
            instrument.isin for instrument in self.instruments
        }
        referenced_isins = {event.isin for event in self.events} | {
            position.isin
            for summary in self.account_summaries
            for position in summary.closing_positions
        }
        if referenced_isins - known_isins:
            raise ValueError("fixed-income ledger references unknown ISINs")
        event_ids = {event.event_id for event in self.events}
        observed_event_ids = {
            observation.event_id
            for observation in self.receipt_observations
        }
        if observed_event_ids - event_ids:
            raise ValueError(
                "receipt observations reference unknown events"
            )
        receipt_event_ids = {
            event.event_id
            for event in self.events
            if event.event_type.is_receipt
        }
        if observed_event_ids - receipt_event_ids:
            raise ValueError(
                "receipt observations must reference receipt events"
            )
        summarized_accounts = {
            summary.account_id for summary in self.account_summaries
        }
        referenced_accounts = {
            event.account_id for event in self.events
        } | {
            event.to_account_id
            for event in self.events
            if event.to_account_id is not None
        }
        if referenced_accounts - summarized_accounts:
            raise ValueError(
                "every event account requires an account summary"
            )
        return self


class FixedIncomeLedgerError(ValueError):
    pass


def load_fixed_income_ledger(
    data: Mapping[str, Any],
) -> FixedIncomeLedger:
    if not isinstance(data, Mapping):
        raise FixedIncomeLedgerError(
            "Fixed-income ledger must be a mapping"
        )
    if data.get("schema_version") != "1.0":
        raise FixedIncomeLedgerError(
            f"Fixed-income schema_version {data.get('schema_version')!r} "
            "is not supported"
        )
    try:
        return FixedIncomeLedger.model_validate(data)
    except ValidationError as exc:
        raise FixedIncomeLedgerError(str(exc)) from exc


def _require_unique(label: str, values: list[object]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
