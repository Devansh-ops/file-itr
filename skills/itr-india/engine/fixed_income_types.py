"""Domain result types for AY 2026-27 fixed-income computation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

from engine.bank_interest_ledger import SourceProvenance


class FixedIncomeTaxBucket(StrEnum):
    STCG_SLAB = "stcg_slab"
    LTCG_112 = "ltcg_112"
    STCG_50AA = "stcg_50aa"


@dataclass(frozen=True, slots=True)
class FixedIncomeBlocker:
    code: str
    message: str
    event_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()


class FixedIncomeReconciliationError(ValueError):
    def __init__(self, blockers: list[FixedIncomeBlocker]):
        self.blockers = tuple(
            sorted(
                blockers,
                key=lambda item: (
                    item.code,
                    item.event_ids,
                    item.evidence_references,
                    item.message,
                ),
            )
        )
        self.blocker_codes = frozenset(
            blocker.code for blocker in self.blockers
        )
        super().__init__(
            "Fixed-income reconciliation blocked: "
            + "; ".join(
                f"{blocker.code}: {blocker.message}"
                for blocker in self.blockers
            )
        )


@dataclass(frozen=True, slots=True)
class MatchedFixedIncomeDisposal:
    account_id: str
    isin: str
    disposal_event_id: str
    acquisition_event_id: str
    acquisition_date: date
    disposal_date: date
    quantity: Decimal
    capital_proceeds: Decimal
    interest_component: Decimal
    deductible_charges: Decimal
    cost_basis: Decimal
    gain: Decimal
    tax_bucket: FixedIncomeTaxBucket
    lineage_event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FixedIncomeReconciliationResult:
    interest_income: Decimal
    tds_credit: Decimal
    cash_receipts: Decimal
    non_deductible_stt: Decimal
    capital_gain_totals: Mapping[FixedIncomeTaxBucket, Decimal]
    matched_disposals: tuple[MatchedFixedIncomeDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]


@dataclass(frozen=True, slots=True)
class FixedIncomeAuditLine:
    output_path: str
    amount: Decimal
    transformation: str
    event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FixedIncomeSlice:
    interest_income: Decimal
    tds_credit: Decimal
    cash_receipts: Decimal
    non_deductible_stt: Decimal
    capital_gain_totals: Mapping[FixedIncomeTaxBucket, Decimal]
    matched_disposals: tuple[MatchedFixedIncomeDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]
    filing_values: Mapping[str, Any]
    audit_trace: tuple[FixedIncomeAuditLine, ...]


def provenance_reference(provenance: SourceProvenance) -> str:
    return (
        f"{provenance.source_document}"
        f"#{provenance.source_location}"
    )
