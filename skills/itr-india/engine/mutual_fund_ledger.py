"""Versioned normalized ledger for Indian mutual-fund holdings."""

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
Percentage = Annotated[Decimal, Field(ge=0, le=100)]


class FundEventType(StrEnum):
    PURCHASE = "purchase"
    REINVESTMENT = "reinvestment"
    SALE = "sale"
    REDEMPTION = "redemption"
    SWITCH_IN = "switch_in"
    SWITCH_OUT = "switch_out"
    TRANSFER = "transfer"

    @property
    def is_acquisition(self) -> bool:
        return self in {
            FundEventType.PURCHASE,
            FundEventType.REINVESTMENT,
            FundEventType.SWITCH_IN,
        }

    @property
    def is_disposal(self) -> bool:
        return self in {
            FundEventType.SALE,
            FundEventType.REDEMPTION,
            FundEventType.SWITCH_OUT,
        }

    @property
    def is_switch(self) -> bool:
        return self in {
            FundEventType.SWITCH_IN,
            FundEventType.SWITCH_OUT,
        }


class SttStatus(StrEnum):
    PAID = "paid"
    NOT_PAID = "not_paid"
    UNKNOWN = "unknown"


class EvidenceAuthority(StrEnum):
    AIS_SFT = "ais_sft"
    AMC = "amc"
    SEBI = "sebi"
    AMFI = "amfi"


class FundStructure(StrEnum):
    DIRECT = "direct"
    FUND_OF_FUNDS = "fund_of_funds"


class PortfolioAveragingMethod(StrEnum):
    ANNUAL_AVERAGE_MONTHLY_OPENING_CLOSING = (
        "annual_average_monthly_opening_closing"
    )
    ANNUAL_AVERAGE_DAILY_CLOSING = "annual_average_daily_closing"


class StatutoryFundClass(StrEnum):
    EQUITY_ORIENTED = "equity_oriented"
    SPECIFIED_MUTUAL_FUND = "specified_mutual_fund"
    OTHER_MUTUAL_FUND = "other_mutual_fund"


class FundClassificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    authority: EvidenceAuthority
    period_start: date
    period_end: date
    structure: FundStructure
    domestic_equity_percentage: Percentage | None
    debt_money_market_percentage: Percentage | None
    underlying_fund_percentage: Percentage | None
    underlying_domestic_equity_percentage: Percentage | None
    specified_fund_units_percentage: Percentage | None
    equity_averaging_method: PortfolioAveragingMethod | None
    debt_averaging_method: PortfolioAveragingMethod | None
    underlying_exchange_traded: bool | None
    provenance: SourceProvenance

    @model_validator(mode="after")
    def period_is_valid(self) -> "FundClassificationEvidence":
        if self.period_end < self.period_start:
            raise ValueError("classification evidence period is reversed")
        return self


class FundListingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exchange_listed: bool
    provenance: SourceProvenance


class MutualFundScheme(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme_id: str = Field(pattern=r"^INF[0-9A-Z]{9}$")
    scheme_name: str = Field(min_length=1)
    listing: FundListingEvidence
    classification_evidence: tuple[FundClassificationEvidence, ...]


class MutualFundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    event_type: FundEventType
    event_date: date
    account_id: str = Field(min_length=1)
    to_account_id: str | None
    scheme_id: str = Field(pattern=r"^INF[0-9A-Z]{9}$")
    quantity: Quantity
    gross_amount: Money
    deductible_charges: Money
    stt_status: SttStatus | None
    switch_id: str | None
    fmv_31jan2018_per_unit: Money | None
    provenance: SourceProvenance

    @model_validator(mode="after")
    def event_shape_is_valid(self) -> "MutualFundEvent":
        if (
            self.event_type.is_acquisition
            or self.event_type.is_disposal
        ):
            if self.quantity <= 0 or self.gross_amount <= 0:
                raise ValueError(
                    "acquisition/disposal requires positive quantity and amount"
                )
        if self.event_type.is_disposal and not (
            date(2025, 4, 1)
            <= self.event_date
            <= date(2026, 3, 31)
        ):
            raise ValueError("disposal must fall within FY 2025-26")
        if self.event_type.is_disposal and self.stt_status is None:
            raise ValueError("disposal requires paid/not-paid/unknown STT status")
        if not self.event_type.is_disposal and self.stt_status is not None:
            raise ValueError("STT status is allowed only on disposals")
        if self.event_type is FundEventType.TRANSFER:
            if self.quantity <= 0:
                raise ValueError("transfer requires positive quantity")
            if (
                not self.to_account_id
                or self.to_account_id == self.account_id
            ):
                raise ValueError(
                    "transfer requires a different to_account_id"
                )
            if self.gross_amount or self.switch_id:
                raise ValueError(
                    "transfer cannot contain proceeds, STT, or switch_id"
                )
        if self.event_type.is_switch:
            if not self.switch_id:
                raise ValueError("switch event requires switch_id")
        elif self.switch_id is not None:
            raise ValueError("switch_id is allowed only on switch events")
        return self


class MutualFundClosingPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme_id: str = Field(pattern=r"^INF[0-9A-Z]{9}$")
    quantity: Quantity
    provenance: SourceProvenance


class MutualFundAccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1)
    gross_disposal_proceeds: Money
    closing_positions: tuple[MutualFundClosingPosition, ...]
    provenance: SourceProvenance

    @model_validator(mode="after")
    def positions_are_unique(self) -> "MutualFundAccountSummary":
        _require_unique(
            "closing position scheme",
            [position.scheme_id for position in self.closing_positions],
        )
        return self


class MutualFundLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    assessment_year: Literal["2026-27"]
    schemes: tuple[MutualFundScheme, ...]
    events: tuple[MutualFundEvent, ...]
    account_summaries: tuple[MutualFundAccountSummary, ...]

    @model_validator(mode="after")
    def identities_and_references_are_valid(self) -> "MutualFundLedger":
        _require_unique(
            "scheme_id",
            [scheme.scheme_id for scheme in self.schemes],
        )
        _require_unique("event_id", [event.event_id for event in self.events])
        _require_unique("sequence", [event.sequence for event in self.events])
        _require_unique(
            "account summary",
            [summary.account_id for summary in self.account_summaries],
        )
        known_schemes = {scheme.scheme_id for scheme in self.schemes}
        referenced = {event.scheme_id for event in self.events} | {
            position.scheme_id
            for summary in self.account_summaries
            for position in summary.closing_positions
        }
        unknown = sorted(referenced - known_schemes)
        if unknown:
            raise ValueError(
                f"unknown scheme IDs: {', '.join(unknown)}"
            )
        for scheme in self.schemes:
            _require_unique(
                f"{scheme.scheme_id} classification evidence_id",
                [
                    evidence.evidence_id
                    for evidence in scheme.classification_evidence
                ],
            )
        return self


class MutualFundLedgerError(ValueError):
    pass


def load_mutual_fund_ledger(data: Mapping[str, Any]) -> MutualFundLedger:
    if not isinstance(data, Mapping):
        raise MutualFundLedgerError("Mutual-fund ledger must be a mapping")
    if data.get("schema_version") != "1.0":
        raise MutualFundLedgerError(
            f"Mutual-fund schema_version {data.get('schema_version')!r} "
            "is not supported"
        )
    try:
        return MutualFundLedger.model_validate(data)
    except ValidationError as exc:
        raise MutualFundLedgerError(str(exc)) from exc


def _require_unique(label: str, values: list[object]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
