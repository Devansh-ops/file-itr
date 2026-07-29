"""Evidence-first, disposal-date-specific mutual-fund classification."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.bank_interest_ledger import SourceProvenance
from engine.mutual_fund_ledger import (
    FundClassificationEvidence,
    MutualFundEvent,
    MutualFundLedger,
    MutualFundScheme,
    PortfolioAveragingMethod,
    StatutoryFundClass,
    SttStatus,
)
from engine.mutual_fund_types import (
    FundClassificationInterval,
    FundResearchRequest,
    MutualFundBlocker,
    event_references,
    provenance_reference,
)
from engine.readiness import (
    DecisionAction,
    DecisionFinding,
    DecisionJournal,
    FilingBlocker,
    HumanDecision,
    ReadinessAssessment,
)


@dataclass(frozen=True, slots=True)
class ResolvedFundClassification:
    disposal_event_id: str
    scheme_id: str
    disposal_date: date
    classification: StatutoryFundClass
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class FundClassificationDecision(HumanDecision):
    scheme_id: str
    effective_from: date
    effective_to: date
    classification: StatutoryFundClass
    disposal_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        HumanDecision.__post_init__(self)
        if self.action is not DecisionAction.CONFIRM_CLASSIFICATION:
            raise ValueError(
                "fund classification decision requires "
                "CONFIRM_CLASSIFICATION action"
            )
        if not self.scheme_id.strip():
            raise ValueError("scheme_id must be non-empty")
        if (
            type(self.effective_from) is not date
            or type(self.effective_to) is not date
        ):
            raise ValueError(
                "classification decision dates must be date values"
            )
        if self.effective_to < self.effective_from:
            raise ValueError("classification decision period is reversed")
        if not isinstance(self.classification, StatutoryFundClass):
            raise ValueError(
                "classification must be a StatutoryFundClass"
            )
        if any(
            not isinstance(event_id, str)
            for event_id in self.disposal_event_ids
        ):
            raise ValueError("disposal_event_ids must contain text")
        event_ids = tuple(
            sorted(
                {
                    event_id.strip()
                    for event_id in self.disposal_event_ids
                    if event_id.strip()
                }
            )
        )
        if not event_ids:
            raise ValueError("disposal_event_ids must not be empty")
        object.__setattr__(self, "scheme_id", self.scheme_id.strip())
        object.__setattr__(self, "disposal_event_ids", event_ids)

    def audit_details(self) -> Mapping[str, object]:
        return {
            "classification": self.classification.value,
            "disposal_event_ids": list(self.disposal_event_ids),
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat(),
            "scheme_id": self.scheme_id,
        }


@dataclass(frozen=True, slots=True)
class FundClassificationConfirmationResult:
    assessment: "FundClassificationAssessment"
    applied_decision_ids: tuple[str, ...]
    findings: tuple[DecisionFinding, ...]


@dataclass(frozen=True, slots=True)
class FundClassificationAssessment:
    classifications: Mapping[str, StatutoryFundClass]
    classification_intervals: tuple[FundClassificationInterval, ...]
    resolved_by_disposal_event_id: Mapping[
        str,
        ResolvedFundClassification,
    ]
    blockers: tuple[MutualFundBlocker, ...]
    research_manifest: tuple[FundResearchRequest, ...]
    stt_unknown_event_ids: frozenset[str]


class _IncompleteClassificationEvidence(ValueError):
    def __init__(self, missing_facts: tuple[str, ...]):
        self.missing_facts = missing_facts
        super().__init__(
            "Incomplete fund classification evidence: "
            + ", ".join(missing_facts)
        )


class _InvalidClassificationAveraging(ValueError):
    def __init__(self, field: str):
        self.field = field
        super().__init__(f"Invalid statutory averaging method for {field}")


def assess_mutual_fund_classification(
    ledger: MutualFundLedger,
) -> FundClassificationAssessment:
    blockers: list[MutualFundBlocker] = []
    research_manifest: list[FundResearchRequest] = []
    classifications: dict[str, StatutoryFundClass] = {}
    resolved_by_event: dict[str, ResolvedFundClassification] = {}
    intervals = _classification_intervals(ledger)

    disposals_by_scheme = {
        scheme.scheme_id: tuple(
            event
            for event in ledger.events
            if (
                event.scheme_id == scheme.scheme_id
                and event.event_type.is_disposal
            )
        )
        for scheme in ledger.schemes
    }
    for scheme in ledger.schemes:
        scheme_events = disposals_by_scheme[scheme.scheme_id]
        for event in scheme_events:
            _resolve_disposal_classification(
                scheme,
                event,
                resolved_by_event,
                blockers,
                research_manifest,
            )
        resolved = {
            resolved_by_event[event.event_id].classification
            for event in scheme_events
            if event.event_id in resolved_by_event
        }
        if (
            len(resolved) == 1
            and len(
                [
                    event
                    for event in scheme_events
                    if event.event_id in resolved_by_event
                ]
            )
            == len(scheme_events)
            and scheme_events
        ):
            classifications[scheme.scheme_id] = next(iter(resolved))

    stt_unknown_event_ids: set[str] = set()
    events_by_id = {event.event_id: event for event in ledger.events}
    for event_id, resolution in resolved_by_event.items():
        event = events_by_id[event_id]
        if (
            resolution.classification
            is StatutoryFundClass.EQUITY_ORIENTED
            and event.stt_status is SttStatus.UNKNOWN
        ):
            stt_unknown_event_ids.add(event_id)
            blockers.append(
                MutualFundBlocker(
                    "MISSING_EQUITY_FUND_STT_EVIDENCE",
                    (
                        f"{event_id} cannot use sections 111A/112A "
                        "until its STT status is known"
                    ),
                    (event.scheme_id,),
                    event_references([event]),
                )
            )
            research_manifest.append(
                _research_request(
                    event.scheme_id,
                    (event,),
                    ("stt_on_transfer",),
                )
            )

    return FundClassificationAssessment(
        classifications=MappingProxyType(classifications),
        classification_intervals=intervals,
        resolved_by_disposal_event_id=MappingProxyType(
            resolved_by_event
        ),
        blockers=tuple(blockers),
        research_manifest=tuple(research_manifest),
        stt_unknown_event_ids=frozenset(stt_unknown_event_ids),
    )


def apply_human_classification_confirmations(
    ledger: MutualFundLedger,
    assessment: FundClassificationAssessment,
    readiness: ReadinessAssessment,
    decision_journal: DecisionJournal,
) -> FundClassificationConfirmationResult:
    """Build a provisional assessment without changing primary-evidence facts."""

    resolved_by_event = dict(
        assessment.resolved_by_disposal_event_id
    )
    events_by_id = {event.event_id: event for event in ledger.events}
    blockers_by_id = {
        blocker.blocker_id: blocker for blocker in readiness.blockers
    }
    applied: list[str] = []
    findings: list[DecisionFinding] = []
    for decision in decision_journal.decisions:
        if not isinstance(decision, FundClassificationDecision):
            continue
        blocker = blockers_by_id.get(decision.blocker_id)
        problem = _confirmation_problem(
            decision,
            blocker,
            readiness,
            events_by_id,
            resolved_by_event,
        )
        if problem is not None:
            findings.append(
                DecisionFinding(
                    decision.decision_id,
                    "INVALID_CLASSIFICATION_CONFIRMATION",
                    problem,
                )
            )
            continue
        for event_id in decision.disposal_event_ids:
            event = events_by_id[event_id]
            resolved_by_event[event_id] = ResolvedFundClassification(
                disposal_event_id=event_id,
                scheme_id=event.scheme_id,
                disposal_date=event.event_date,
                classification=decision.classification,
                evidence_references=tuple(
                    sorted(
                        {
                            *decision.evidence_references,
                            f"decision:{decision.decision_id}",
                        }
                    )
                ),
                source_provenance=(),
            )
        applied.append(decision.decision_id)

    classifications: dict[str, StatutoryFundClass] = {}
    for scheme in ledger.schemes:
        disposals = tuple(
            event
            for event in ledger.events
            if (
                event.scheme_id == scheme.scheme_id
                and event.event_type.is_disposal
            )
        )
        scheme_resolutions = {
            resolved_by_event[event.event_id].classification
            for event in disposals
            if event.event_id in resolved_by_event
        }
        if (
            disposals
            and len(scheme_resolutions) == 1
            and all(
                event.event_id in resolved_by_event
                for event in disposals
            )
        ):
            classifications[scheme.scheme_id] = next(
                iter(scheme_resolutions)
            )
    stt_unknown = frozenset(
        event_id
        for event_id, resolution in resolved_by_event.items()
        if (
            resolution.classification
            is StatutoryFundClass.EQUITY_ORIENTED
            and events_by_id[event_id].stt_status is SttStatus.UNKNOWN
        )
    )
    return FundClassificationConfirmationResult(
        assessment=replace(
            assessment,
            classifications=MappingProxyType(classifications),
            resolved_by_disposal_event_id=MappingProxyType(
                resolved_by_event
            ),
            stt_unknown_event_ids=stt_unknown,
        ),
        applied_decision_ids=tuple(sorted(applied)),
        findings=tuple(
            sorted(
                findings,
                key=lambda item: (item.code, item.decision_id),
            )
        ),
    )


def _confirmation_problem(
    decision: FundClassificationDecision,
    blocker: FilingBlocker | None,
    readiness: ReadinessAssessment,
    events_by_id: Mapping[str, MutualFundEvent],
    resolved_by_event: Mapping[str, ResolvedFundClassification],
) -> str | None:
    if decision.context_fingerprint != readiness.context_fingerprint:
        return "The classification confirmation belongs to a stale context"
    if blocker is None:
        return "The targeted classification blocker is no longer present"
    if decision.affected_outputs != blocker.affected_outputs:
        return "The confirmation does not bind the blocker's exact outputs"
    if blocker.code not in {
        "MISSING_PRIMARY_CLASSIFICATION_EVIDENCE",
        "INCOMPLETE_PRIMARY_CLASSIFICATION_EVIDENCE",
    }:
        return "This blocker cannot be resolved by human classification"
    for event_id in decision.disposal_event_ids:
        event = events_by_id.get(event_id)
        if event is None or not event.event_type.is_disposal:
            return f"{event_id} is not a known mutual-fund disposal"
        if event.scheme_id != decision.scheme_id:
            return f"{event_id} belongs to a different scheme"
        if not (
            decision.effective_from
            <= event.event_date
            <= decision.effective_to
        ):
            return f"{event_id} falls outside the confirmed period"
        if event_id in resolved_by_event:
            return f"{event_id} already has a primary-evidence classification"
        if (
            provenance_reference(event.provenance)
            not in blocker.evidence_references
        ):
            return f"{event_id} is not affected by the targeted blocker"
    return None


def _classification_intervals(
    ledger: MutualFundLedger,
) -> tuple[FundClassificationInterval, ...]:
    intervals: list[FundClassificationInterval] = []
    for scheme in ledger.schemes:
        for evidence in scheme.classification_evidence:
            try:
                classification = _classify(evidence)
            except (
                _IncompleteClassificationEvidence,
                _InvalidClassificationAveraging,
            ):
                continue
            reference = provenance_reference(evidence.provenance)
            intervals.append(
                FundClassificationInterval(
                    scheme_id=scheme.scheme_id,
                    period_start=evidence.period_start,
                    period_end=evidence.period_end,
                    classification=classification,
                    evidence_references=(reference,),
                    source_provenance=(evidence.provenance,),
                )
            )
    return tuple(
        sorted(
            intervals,
            key=lambda item: (
                item.scheme_id,
                item.period_start,
                item.period_end,
                item.evidence_references,
            ),
        )
    )


def _resolve_disposal_classification(
    scheme: MutualFundScheme,
    event: MutualFundEvent,
    resolved_by_event: dict[str, ResolvedFundClassification],
    blockers: list[MutualFundBlocker],
    research_manifest: list[FundResearchRequest],
) -> None:
    applicable = tuple(
        evidence
        for evidence in scheme.classification_evidence
        if (
            evidence.period_start
            <= event.event_date
            <= evidence.period_end
        )
    )
    if not applicable:
        blockers.append(
            MutualFundBlocker(
                "MISSING_PRIMARY_CLASSIFICATION_EVIDENCE",
                (
                    f"{scheme.scheme_id} lacks primary classification "
                    f"evidence for {event.event_date.isoformat()}"
                ),
                (scheme.scheme_id,),
                event_references([event]),
            )
        )
        research_manifest.append(
            _research_request(
                scheme.scheme_id,
                (event,),
                (
                    "domestic_equity_percentage",
                    "debt_money_market_percentage",
                    "fund_structure_and_underlying_percentages",
                ),
            )
        )
        return

    missing_facts: set[str] = set()
    invalid_averaging_fields: set[str] = set()
    evidenced_classes: set[StatutoryFundClass] = set()
    for evidence in applicable:
        try:
            evidenced_classes.add(_classify(evidence))
        except _IncompleteClassificationEvidence as exc:
            missing_facts.update(exc.missing_facts)
        except _InvalidClassificationAveraging as exc:
            invalid_averaging_fields.add(exc.field)
    references = tuple(
        sorted(
            {
                *(
                    provenance_reference(evidence.provenance)
                    for evidence in applicable
                ),
                *event_references([event]),
            }
        )
    )
    if len(evidenced_classes) > 1:
        blockers.append(
            MutualFundBlocker(
                "CONFLICTING_PRIMARY_CLASSIFICATION_EVIDENCE",
                (
                    f"{scheme.scheme_id} primary sources imply different "
                    f"statutory classes for {event.event_date.isoformat()}"
                ),
                (scheme.scheme_id,),
                references,
            )
        )
        research_manifest.append(
            _research_request(
                scheme.scheme_id,
                (event,),
                ("authoritative_period_classification",),
            )
        )
        return
    if invalid_averaging_fields and not evidenced_classes:
        fields = tuple(sorted(invalid_averaging_fields))
        blockers.append(
            MutualFundBlocker(
                "INVALID_CLASSIFICATION_AVERAGING_METHOD",
                (
                    f"{scheme.scheme_id} uses the wrong statutory "
                    f"averaging method for {', '.join(fields)}"
                ),
                (scheme.scheme_id,),
                references,
            )
        )
        research_manifest.append(
            _research_request(
                scheme.scheme_id,
                (event,),
                tuple(f"{field}_averaging_method" for field in fields),
            )
        )
        return
    if missing_facts and not evidenced_classes:
        missing = tuple(sorted(missing_facts))
        blockers.append(
            MutualFundBlocker(
                "INCOMPLETE_PRIMARY_CLASSIFICATION_EVIDENCE",
                (
                    f"{scheme.scheme_id} primary evidence lacks "
                    f"{', '.join(missing)}"
                ),
                (scheme.scheme_id,),
                references,
            )
        )
        research_manifest.append(
            _research_request(
                scheme.scheme_id,
                (event,),
                missing,
            )
        )
        return
    resolved_by_event[event.event_id] = ResolvedFundClassification(
        disposal_event_id=event.event_id,
        scheme_id=event.scheme_id,
        disposal_date=event.event_date,
        classification=next(iter(evidenced_classes)),
        evidence_references=references,
        source_provenance=tuple(
            evidence.provenance for evidence in applicable
        ),
    )


def _research_request(
    scheme_id: str,
    events: tuple[MutualFundEvent, ...],
    required_facts: tuple[str, ...],
) -> FundResearchRequest:
    return FundResearchRequest(
        scheme_id=scheme_id,
        sale_dates=tuple(
            event.event_date.isoformat() for event in events
        ),
        required_facts=required_facts,
        accepted_authorities=("ais_sft", "amc", "sebi", "amfi"),
    )


def _classify(
    evidence: FundClassificationEvidence,
) -> StatutoryFundClass:
    if evidence.structure.value == "direct":
        if (
            evidence.domestic_equity_percentage is not None
            and evidence.domestic_equity_percentage >= Decimal("65")
        ):
            _require_averaging(
                evidence.equity_averaging_method,
                PortfolioAveragingMethod
                .ANNUAL_AVERAGE_MONTHLY_OPENING_CLOSING,
                "domestic_equity_percentage",
            )
            return StatutoryFundClass.EQUITY_ORIENTED
        if (
            evidence.debt_money_market_percentage is not None
            and evidence.debt_money_market_percentage > Decimal("65")
        ):
            _require_averaging(
                evidence.debt_averaging_method,
                PortfolioAveragingMethod.ANNUAL_AVERAGE_DAILY_CLOSING,
                "debt_money_market_percentage",
            )
            return StatutoryFundClass.SPECIFIED_MUTUAL_FUND
        missing = tuple(
            name
            for name, value in (
                (
                    "domestic_equity_percentage",
                    evidence.domestic_equity_percentage,
                ),
                (
                    "debt_money_market_percentage",
                    evidence.debt_money_market_percentage,
                ),
            )
            if value is None
        )
        if missing:
            raise _IncompleteClassificationEvidence(missing)
        return StatutoryFundClass.OTHER_MUTUAL_FUND
    if (
        evidence.underlying_fund_percentage is not None
        and evidence.underlying_domestic_equity_percentage is not None
        and evidence.underlying_exchange_traded is True
        and evidence.underlying_fund_percentage >= Decimal("90")
        and evidence.underlying_domestic_equity_percentage >= Decimal("90")
    ):
        _require_averaging(
            evidence.equity_averaging_method,
            PortfolioAveragingMethod
            .ANNUAL_AVERAGE_MONTHLY_OPENING_CLOSING,
            "underlying_domestic_equity_percentage",
        )
        return StatutoryFundClass.EQUITY_ORIENTED
    if (
        evidence.specified_fund_units_percentage is not None
        and evidence.specified_fund_units_percentage >= Decimal("65")
    ):
        _require_averaging(
            evidence.debt_averaging_method,
            PortfolioAveragingMethod.ANNUAL_AVERAGE_DAILY_CLOSING,
            "specified_fund_units_percentage",
        )
        return StatutoryFundClass.SPECIFIED_MUTUAL_FUND
    missing = tuple(
        name
        for name, value in (
            ("underlying_fund_percentage", evidence.underlying_fund_percentage),
            (
                "underlying_domestic_equity_percentage",
                evidence.underlying_domestic_equity_percentage,
            ),
            (
                "specified_fund_units_percentage",
                evidence.specified_fund_units_percentage,
            ),
            (
                "underlying_exchange_traded",
                evidence.underlying_exchange_traded,
            ),
        )
        if value is None
    )
    if missing:
        raise _IncompleteClassificationEvidence(missing)
    return StatutoryFundClass.OTHER_MUTUAL_FUND


def _require_averaging(
    actual: PortfolioAveragingMethod | None,
    expected: PortfolioAveragingMethod,
    field: str,
) -> None:
    if actual is not expected:
        raise _InvalidClassificationAveraging(field)
