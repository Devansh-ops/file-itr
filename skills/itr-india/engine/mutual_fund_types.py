"""Shared result contracts for mutual-fund computation modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from engine.bank_interest_ledger import SourceProvenance
from engine.mutual_fund_ledger import MutualFundEvent, StatutoryFundClass
from engine.readiness import DecisionFinding, ReadinessAssessment


class FundTaxBucket(StrEnum):
    STCG_111A = "stcg_111a"
    LTCG_112A = "ltcg_112a"
    STCG_50AA = "stcg_50aa"
    STCG_SLAB = "stcg_slab"
    LTCG_112 = "ltcg_112"


@dataclass(frozen=True, slots=True)
class MutualFundBlocker:
    code: str
    message: str
    scheme_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()


class MutualFundReconciliationError(ValueError):
    def __init__(self, blockers: list[MutualFundBlocker]):
        self.blockers = tuple(
            sorted(
                blockers,
                key=lambda item: (
                    item.code,
                    item.scheme_ids,
                    item.evidence_references,
                ),
            )
        )
        self.blocker_codes = frozenset(
            blocker.code for blocker in self.blockers
        )
        super().__init__(
            "Mutual-fund reconciliation blocked: "
            + "; ".join(
                f"{blocker.code}: {blocker.message}"
                for blocker in self.blockers
            )
        )


@dataclass(frozen=True, slots=True)
class FundResearchRequest:
    scheme_id: str
    sale_dates: tuple[str, ...]
    required_facts: tuple[str, ...]
    accepted_authorities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FundClassificationInterval:
    scheme_id: str
    period_start: date
    period_end: date
    classification: StatutoryFundClass
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class FundAuditLine:
    output_path: str
    amount: Decimal
    transformation: str
    acquisition_event_ids: tuple[str, ...]
    disposal_event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class MatchedFundDisposal:
    account_id: str
    scheme_id: str
    disposal_event_id: str
    acquisition_event_id: str
    acquisition_date: date
    disposal_date: date
    quantity: Decimal
    gross_proceeds: Decimal
    deductible_charges: Decimal
    cost_basis: Decimal
    gain: Decimal
    classification: StatutoryFundClass | None
    tax_bucket: FundTaxBucket | None
    source_provenance: tuple[SourceProvenance, ...]
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MutualFundSlice:
    classifications: Mapping[str, StatutoryFundClass]
    classification_intervals: tuple[FundClassificationInterval, ...]
    bucket_totals: Mapping[FundTaxBucket, Decimal]
    independently_ready: bool
    blockers: tuple[MutualFundBlocker, ...]
    research_manifest: tuple[FundResearchRequest, ...]
    matched_disposals: tuple[MatchedFundDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]
    filing_values: Mapping[str, Any]
    audit_trace: tuple[FundAuditLine, ...]
    readiness: ReadinessAssessment
    provisional_classifications: Mapping[str, StatutoryFundClass]
    provisional_bucket_totals: Mapping[FundTaxBucket, Decimal]
    provisional_matched_disposals: tuple[MatchedFundDisposal, ...]
    provisional_filing_values: Mapping[str, Any]
    applied_classification_decision_ids: tuple[str, ...]
    classification_decision_findings: tuple[DecisionFinding, ...]


def provenance_reference(provenance: SourceProvenance) -> str:
    return (
        f"{provenance.source_document}"
        f"#{provenance.source_location}"
    )


def event_references(
    events: list[MutualFundEvent],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                provenance_reference(event.provenance)
                for event in events
            }
        )
    )


def merge_provenance(
    *groups: tuple[SourceProvenance, ...],
) -> tuple[SourceProvenance, ...]:
    unique = {
        (
            item.source_document,
            item.source_sha256,
            item.source_location,
            item.importer,
            item.importer_version,
        ): item
        for group in groups
        for item in group
    }
    return tuple(unique[key] for key in sorted(unique))


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value
