from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


CURRENT_BANK_LEDGER_VERSION = "1.0"
SUPPORTED_ASSESSMENT_YEAR = "2026-27"


class EvidenceType(StrEnum):
    BANK_STATEMENT = "bank_statement"
    AIS = "ais"
    FORM_26AS = "form_26as"


class InterestKind(StrEnum):
    SAVINGS = "savings"
    TERM_DEPOSIT = "term_deposit"
    OTHER = "other"


class OwnershipType(StrEnum):
    SELF = "self"
    JOINT_UNRESOLVED = "joint_unresolved"
    OTHER = "other"


NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
OwnershipShare = Annotated[Decimal, Field(ge=0, le=1)]


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_document: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_location: str = Field(min_length=1)
    importer: str = Field(min_length=1)
    importer_version: str = Field(min_length=1)

    def identity_key(self) -> tuple[str, ...]:
        return (
            self.source_sha256,
            self.source_location,
            self.importer,
            self.importer_version,
        )

    def sort_key(self) -> tuple[str, ...]:
        return (*self.identity_key(), self.source_document)


class BankInterestEvidenceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    evidence_reference: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    bank_name: str = Field(min_length=1)
    account_last4: str = Field(pattern=r"^[A-Za-z0-9]{4}$")
    ownership: OwnershipType
    ownership_share: OwnershipShare | None
    interest_kind: InterestKind
    period_start: date
    period_end: date
    gross_interest: NonNegativeDecimal
    tds_amount: NonNegativeDecimal | None = None
    deductor_tan: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{4}[0-9]{5}[A-Z]$",
    )
    provenance: SourceProvenance

    @model_validator(mode="after")
    def validate_evidence_invariants(self) -> "BankInterestEvidenceRow":
        if self.ownership is OwnershipType.SELF and self.ownership_share != Decimal("1"):
            raise ValueError("self-owned account must have ownership_share=1")
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if self.period_start < date(2025, 4, 1) or self.period_end > date(2026, 3, 31):
            raise ValueError("interest period must fall within FY 2025-26")
        if self.tds_amount is not None and self.tds_amount > 0 and not self.deductor_tan:
            raise ValueError("positive tds_amount requires deductor_tan")
        if (
            self.tds_amount is not None
            and self.tds_amount != self.tds_amount.to_integral_value()
        ):
            raise ValueError("tds_amount must be whole INR")
        if self.evidence_type is EvidenceType.FORM_26AS and (
            self.tds_amount is None or self.deductor_tan is None
        ):
            raise ValueError(
                "Form 26AS evidence must state its TDS credit amount and deductor TAN"
            )
        return self


class BankInterestLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    assessment_year: Literal["2026-27"]
    evidence_rows: tuple[BankInterestEvidenceRow, ...]


class _BankInterestLedgerV0_1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"]
    ay: Literal["2026-27"]
    entries: tuple[BankInterestEvidenceRow, ...]


@dataclass(frozen=True)
class LoadedBankInterestLedger:
    ledger: BankInterestLedger
    migrations: tuple[str, ...]


class LedgerVersionError(ValueError):
    pass


class LedgerValidationError(ValueError):
    pass


def load_bank_interest_ledger(data: Mapping[str, Any]) -> LoadedBankInterestLedger:
    if not isinstance(data, Mapping):
        raise LedgerValidationError("Bank-interest ledger must be a mapping")
    version = data.get("schema_version")
    if version == CURRENT_BANK_LEDGER_VERSION:
        try:
            ledger = BankInterestLedger.model_validate(data)
        except ValidationError as exc:
            raise LedgerValidationError(str(exc)) from exc
        return LoadedBankInterestLedger(ledger=ledger, migrations=())
    if version == "0.1":
        try:
            legacy = _BankInterestLedgerV0_1.model_validate(data)
            ledger = BankInterestLedger(
                schema_version=CURRENT_BANK_LEDGER_VERSION,
                assessment_year=legacy.ay,
                evidence_rows=legacy.entries,
            )
        except ValidationError as exc:
            raise LedgerValidationError(str(exc)) from exc
        return LoadedBankInterestLedger(
            ledger=ledger,
            migrations=("bank-interest:0.1->1.0",),
        )
    raise LedgerVersionError(
        f"Bank-interest ledger schema_version {version!r} is not supported"
    )
