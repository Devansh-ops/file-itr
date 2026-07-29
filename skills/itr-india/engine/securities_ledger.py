"""Versioned normalized ledger for Indian listed delivery securities."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from engine.bank_interest_ledger import SourceProvenance


NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
QuantityDecimal = Annotated[Decimal, Field(ge=0, decimal_places=4)]


class SecurityEventType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"
    CORPORATE_ACTION = "corporate_action"


class TaxTreatment(StrEnum):
    INVESTMENT = "investment"
    BUSINESS = "business"
    UNRESOLVED = "unresolved"


class SecurityDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    security_name: str = Field(min_length=1, max_length=125)
    tax_treatment: TaxTreatment


class SecurityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    event_type: SecurityEventType
    event_date: date
    account_id: str = Field(min_length=1)
    to_account_id: str | None = None
    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    quantity: QuantityDecimal
    gross_amount: NonNegativeDecimal = Decimal("0")
    deductible_charges: NonNegativeDecimal = Decimal("0")
    stt: NonNegativeDecimal = Decimal("0")
    stt_paid: bool
    corporate_action: str | None = None
    ratio_numerator: PositiveDecimal | None = None
    ratio_denominator: PositiveDecimal | None = None
    fmv_31jan2018_per_unit: NonNegativeDecimal | None = None
    provenance: SourceProvenance

    @property
    def evidence_reference(self) -> str:
        return (
            f"{self.provenance.source_document}"
            f"#{self.provenance.source_location}"
        )

    @model_validator(mode="after")
    def validate_event_shape(self) -> "SecurityEvent":
        if self.event_date > date(2026, 3, 31):
            raise ValueError("event_date cannot be after FY 2025-26")
        if self.event_type in {SecurityEventType.BUY, SecurityEventType.SELL}:
            if self.quantity <= 0 or self.gross_amount <= 0:
                raise ValueError("buy/sell requires positive quantity and gross_amount")
        elif self.event_type is SecurityEventType.TRANSFER:
            if self.quantity <= 0:
                raise ValueError("transfer requires positive quantity")
            if not self.to_account_id or self.to_account_id == self.account_id:
                raise ValueError("transfer requires a different to_account_id")
            if self.gross_amount or self.stt:
                raise ValueError(
                    "transfer cannot contain proceeds or STT"
                )
        else:
            if not self.corporate_action:
                raise ValueError("corporate_action event requires its action name")
            if self.ratio_numerator is None or self.ratio_denominator is None:
                raise ValueError("corporate_action event requires a positive ratio")
            if self.quantity != 0:
                raise ValueError("corporate_action quantity must be zero")
            self._require_zero_cash_fields()
        if (
            self.event_type is SecurityEventType.SELL
            and not date(2025, 4, 1) <= self.event_date <= date(2026, 3, 31)
        ):
            raise ValueError("sale must fall within FY 2025-26")
        return self

    def _require_zero_cash_fields(self) -> None:
        if self.gross_amount or self.deductible_charges or self.stt:
            raise ValueError("non-trade events cannot contain cash amounts")


class ClosingPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    isin: str = Field(pattern=r"^IN[0-9A-Z]{10}$")
    quantity: QuantityDecimal
    provenance: SourceProvenance


class BrokerAccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1)
    gross_sale_proceeds: NonNegativeDecimal
    closing_positions: tuple[ClosingPosition, ...]
    provenance: SourceProvenance

    @model_validator(mode="after")
    def positions_are_unique(self) -> "BrokerAccountSummary":
        isins = [position.isin for position in self.closing_positions]
        if len(isins) != len(set(isins)):
            raise ValueError("closing_positions contains duplicate ISINs")
        return self


class SecurityLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    assessment_year: Literal["2026-27"]
    securities: tuple[SecurityDefinition, ...]
    events: tuple[SecurityEvent, ...]
    broker_summaries: tuple[BrokerAccountSummary, ...]

    @model_validator(mode="after")
    def validate_ledger_identity(self) -> "SecurityLedger":
        _require_unique(
            "security ISIN",
            [security.isin for security in self.securities],
        )
        _require_unique("event_id", [event.event_id for event in self.events])
        _require_unique("sequence", [event.sequence for event in self.events])
        _require_unique(
            "broker summary account",
            [summary.account_id for summary in self.broker_summaries],
        )
        known_isins = {security.isin for security in self.securities}
        unknown = sorted({event.isin for event in self.events} - known_isins)
        unknown.extend(
            sorted(
                {
                    position.isin
                    for summary in self.broker_summaries
                    for position in summary.closing_positions
                }
                - known_isins
            )
        )
        if unknown:
            raise ValueError(f"events reference unknown ISINs: {', '.join(unknown)}")
        return self


class SecurityLedgerError(ValueError):
    pass


def load_security_ledger(data: Mapping[str, Any]) -> SecurityLedger:
    if not isinstance(data, Mapping):
        raise SecurityLedgerError("Security ledger must be a mapping")
    if data.get("schema_version") != "1.0":
        raise SecurityLedgerError(
            f"Security ledger schema_version {data.get('schema_version')!r} "
            "is not supported"
        )
    try:
        return SecurityLedger.model_validate(data)
    except ValidationError as exc:
        raise SecurityLedgerError(str(exc)) from exc


def _require_unique(label: str, values: list[object]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
