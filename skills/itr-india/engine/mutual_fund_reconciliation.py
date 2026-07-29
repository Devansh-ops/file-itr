"""Account-local FIFO reconciliation for Indian mutual-fund units."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.bank_interest_ledger import SourceProvenance
from engine.mutual_fund_classification import FundClassificationAssessment
from engine.mutual_fund_ledger import (
    FundEventType,
    MutualFundEvent,
    MutualFundLedger,
    StatutoryFundClass,
    SttStatus,
)
from engine.mutual_fund_types import (
    FundTaxBucket,
    MatchedFundDisposal,
    MutualFundBlocker,
    MutualFundReconciliationError,
    event_references,
    merge_provenance,
    provenance_reference,
)


@dataclass(frozen=True, slots=True)
class MutualFundFifoResult:
    matched_disposals: tuple[MatchedFundDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]
    bucket_totals: Mapping[FundTaxBucket, Decimal]


@dataclass(slots=True)
class _Lot:
    acquisition_event_id: str
    acquisition_sequence: int
    acquired: date
    quantity: Decimal
    cost: Decimal
    fmv_31jan2018_per_unit: Decimal | None
    source_provenance: tuple[SourceProvenance, ...]


def reconcile_mutual_fund_fifo(
    ledger: MutualFundLedger,
    assessment: FundClassificationAssessment,
) -> MutualFundFifoResult:
    switch_blockers = _switch_blockers(ledger)
    if switch_blockers:
        raise MutualFundReconciliationError(switch_blockers)

    schemes = {scheme.scheme_id: scheme for scheme in ledger.schemes}
    lots: dict[tuple[str, str], list[_Lot]] = defaultdict(list)
    totals: dict[FundTaxBucket, Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    matches: list[MatchedFundDisposal] = []
    for event in sorted(
        ledger.events,
        key=lambda item: (item.event_date, item.sequence),
    ):
        key = (event.account_id, event.scheme_id)
        if event.event_type.is_acquisition:
            lots[key].append(
                _Lot(
                    event.event_id,
                    event.sequence,
                    event.event_date,
                    event.quantity,
                    event.gross_amount + event.deductible_charges,
                    event.fmv_31jan2018_per_unit,
                    (event.provenance,),
                )
            )
            continue
        if event.event_type is FundEventType.TRANSFER:
            transferred = _consume_lots(lots[key], event.quantity, event)
            _allocate_transfer_charges(
                transferred,
                event.deductible_charges,
            )
            transferred = [
                _Lot(
                    lot.acquisition_event_id,
                    lot.acquisition_sequence,
                    lot.acquired,
                    lot.quantity,
                    lot.cost,
                    lot.fmv_31jan2018_per_unit,
                    merge_provenance(
                        lot.source_provenance,
                        (event.provenance,),
                    ),
                )
                for lot in transferred
            ]
            destination = lots[
                (event.to_account_id or "", event.scheme_id)
            ]
            destination.extend(transferred)
            destination.sort(key=_lot_sort_key)
            continue
        if not event.event_type.is_disposal:
            continue
        disposed_lots = _consume_lots(
            lots[key],
            event.quantity,
            event,
        )
        remaining_proceeds = event.gross_amount
        remaining_charges = event.deductible_charges
        for index, lot in enumerate(disposed_lots):
            if index == len(disposed_lots) - 1:
                lot_proceeds = remaining_proceeds
                lot_charges = remaining_charges
            else:
                fraction = lot.quantity / event.quantity
                lot_proceeds = event.gross_amount * fraction
                lot_charges = event.deductible_charges * fraction
                remaining_proceeds -= lot_proceeds
                remaining_charges -= lot_charges
            resolution = assessment.resolved_by_disposal_event_id.get(
                event.event_id
            )
            classification = (
                resolution.classification
                if resolution is not None
                else None
            )
            cost_basis = _cost_basis(
                lot,
                lot_proceeds,
                event,
                classification,
            )
            gain = lot_proceeds - lot_charges - cost_basis
            bucket = None
            if (
                classification is not None
                and event.event_id
                not in assessment.stt_unknown_event_ids
            ):
                bucket = _bucket(
                    classification,
                    lot.acquired,
                    event.event_date,
                    schemes[
                        event.scheme_id
                    ].listing.exchange_listed,
                    event.stt_status,
                )
                totals[bucket] += gain
            source_provenance = merge_provenance(
                lot.source_provenance,
                (event.provenance,),
            )
            matches.append(
                MatchedFundDisposal(
                    account_id=event.account_id,
                    scheme_id=event.scheme_id,
                    disposal_event_id=event.event_id,
                    acquisition_event_id=lot.acquisition_event_id,
                    acquisition_date=lot.acquired,
                    disposal_date=event.event_date,
                    quantity=lot.quantity,
                    gross_proceeds=lot_proceeds,
                    deductible_charges=lot_charges,
                    cost_basis=cost_basis,
                    gain=gain,
                    classification=classification,
                    tax_bucket=bucket,
                    source_provenance=source_provenance,
                    evidence_references=tuple(
                        sorted(
                            provenance_reference(source)
                            for source in source_provenance
                        )
                    ),
                )
            )

    closing_positions = {
        key: sum((lot.quantity for lot in account_lots), Decimal("0"))
        for key, account_lots in lots.items()
        if any(lot.quantity > 0 for lot in account_lots)
    }
    summary_blockers = _summary_blockers(ledger, closing_positions)
    if summary_blockers:
        raise MutualFundReconciliationError(summary_blockers)
    matches = _enrich_matches(
        matches,
        ledger,
        assessment,
    )
    return MutualFundFifoResult(
        matched_disposals=tuple(matches),
        closing_positions=MappingProxyType(
            dict(sorted(closing_positions.items()))
        ),
        bucket_totals=MappingProxyType(dict(totals)),
    )


def _cost_basis(
    lot: _Lot,
    lot_proceeds: Decimal,
    event: MutualFundEvent,
    classification: StatutoryFundClass | None,
) -> Decimal:
    if (
        classification is not StatutoryFundClass.EQUITY_ORIENTED
        or lot.acquired > date(2018, 1, 31)
    ):
        return lot.cost
    if lot.fmv_31jan2018_per_unit is None:
        raise MutualFundReconciliationError(
            [
                MutualFundBlocker(
                    "MISSING_31JAN2018_FMV",
                    (
                        f"{lot.acquisition_event_id} requires "
                        "31 January 2018 FMV"
                    ),
                    (event.scheme_id,),
                    event_references([event]),
                )
            ]
        )
    fair_value = lot.fmv_31jan2018_per_unit * lot.quantity
    return max(lot.cost, min(fair_value, lot_proceeds))


def _consume_lots(
    lots: list[_Lot],
    quantity: Decimal,
    event: MutualFundEvent,
) -> list[_Lot]:
    available = sum((lot.quantity for lot in lots), Decimal("0"))
    if available < quantity:
        raise MutualFundReconciliationError(
            [
                MutualFundBlocker(
                    "INSUFFICIENT_ACCOUNT_HOLDING",
                    (
                        f"{event.event_id} needs {quantity} units but "
                        f"{event.account_id} has {available}"
                    ),
                    (event.scheme_id,),
                    event_references([event]),
                )
            ]
        )
    remaining = quantity
    consumed: list[_Lot] = []
    while remaining > 0:
        lot = lots[0]
        taken = min(remaining, lot.quantity)
        cost = lot.cost * taken / lot.quantity
        consumed.append(
            _Lot(
                lot.acquisition_event_id,
                lot.acquisition_sequence,
                lot.acquired,
                taken,
                cost,
                lot.fmv_31jan2018_per_unit,
                lot.source_provenance,
            )
        )
        lot.quantity -= taken
        lot.cost -= cost
        remaining -= taken
        if lot.quantity == 0:
            lots.pop(0)
    return consumed


def _summary_blockers(
    ledger: MutualFundLedger,
    closing_positions: dict[tuple[str, str], Decimal],
) -> list[MutualFundBlocker]:
    summaries = {
        summary.account_id: summary for summary in ledger.account_summaries
    }
    accounts = {
        event.account_id for event in ledger.events
    } | {
        event.to_account_id
        for event in ledger.events
        if event.to_account_id is not None
    }
    blockers: list[MutualFundBlocker] = []
    for account_id in sorted(accounts - summaries.keys()):
        blockers.append(
            MutualFundBlocker(
                "MISSING_ACCOUNT_SUMMARY",
                f"Account {account_id} has no reconciliation summary",
            )
        )
    gross_by_account: dict[str, Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for event in ledger.events:
        if event.event_type.is_disposal:
            gross_by_account[event.account_id] += event.gross_amount
    for account_id, summary in sorted(summaries.items()):
        summary_reference = provenance_reference(summary.provenance)
        if summary.gross_disposal_proceeds != gross_by_account[account_id]:
            blockers.append(
                MutualFundBlocker(
                    "ACCOUNT_DISPOSAL_PROCEEDS_MISMATCH",
                    (
                        f"{account_id} ledger disposals "
                        f"{gross_by_account[account_id]} do not match "
                        f"summary {summary.gross_disposal_proceeds}"
                    ),
                    evidence_references=(summary_reference,),
                )
            )
        reported = {
            position.scheme_id: position
            for position in summary.closing_positions
        }
        actual_schemes = {
            scheme_id
            for (account, scheme_id), quantity in closing_positions.items()
            if account == account_id and quantity > 0
        }
        for scheme_id in sorted(actual_schemes | reported.keys()):
            actual = closing_positions.get(
                (account_id, scheme_id),
                Decimal("0"),
            )
            position = reported.get(scheme_id)
            expected = (
                position.quantity if position is not None else Decimal("0")
            )
            if actual != expected:
                references = {summary_reference}
                if position is not None:
                    references.add(
                        provenance_reference(position.provenance)
                    )
                blockers.append(
                    MutualFundBlocker(
                        "ACCOUNT_CLOSING_POSITION_MISMATCH",
                        (
                            f"{account_id} {scheme_id} closing {actual} "
                            f"does not match summary {expected}"
                        ),
                        (scheme_id,),
                        tuple(sorted(references)),
                    )
                )
    return blockers


def _enrich_matches(
    matches: list[MatchedFundDisposal],
    ledger: MutualFundLedger,
    assessment: FundClassificationAssessment,
) -> list[MatchedFundDisposal]:
    summary_provenance = {
        summary.account_id: merge_provenance(
            (summary.provenance,),
            tuple(
                position.provenance
                for position in summary.closing_positions
            ),
        )
        for summary in ledger.account_summaries
    }
    schemes = {scheme.scheme_id: scheme for scheme in ledger.schemes}
    return [
        replace(
            match,
            source_provenance=merge_provenance(
                match.source_provenance,
                summary_provenance[match.account_id],
                assessment.resolved_by_disposal_event_id.get(
                    match.disposal_event_id
                ).source_provenance
                if match.disposal_event_id
                in assessment.resolved_by_disposal_event_id
                else (),
                (schemes[match.scheme_id].listing.provenance,),
            ),
            evidence_references=tuple(
                sorted(
                    {
                        *match.evidence_references,
                        *(
                            assessment.resolved_by_disposal_event_id[
                                match.disposal_event_id
                            ].evidence_references
                            if match.disposal_event_id
                            in assessment.resolved_by_disposal_event_id
                            else ()
                        ),
                        provenance_reference(
                            schemes[match.scheme_id].listing.provenance
                        ),
                        *(
                            provenance_reference(source)
                            for source in summary_provenance[
                                match.account_id
                            ]
                        ),
                    }
                )
            ),
        )
        for match in matches
    ]


def _allocate_transfer_charges(
    lots: list[_Lot],
    charges: Decimal,
) -> None:
    if not lots or not charges:
        return
    total_quantity = sum((lot.quantity for lot in lots), Decimal("0"))
    remaining = charges
    for index, lot in enumerate(lots):
        if index == len(lots) - 1:
            allocated = remaining
        else:
            allocated = charges * lot.quantity / total_quantity
            remaining -= allocated
        lot.cost += allocated


def _lot_sort_key(lot: _Lot) -> tuple[date, int, str]:
    return (
        lot.acquired,
        lot.acquisition_sequence,
        lot.acquisition_event_id,
    )


def _switch_blockers(
    ledger: MutualFundLedger,
) -> list[MutualFundBlocker]:
    switch_events: dict[str, list[MutualFundEvent]] = defaultdict(list)
    for event in ledger.events:
        if event.event_type.is_switch:
            switch_events[event.switch_id or ""].append(event)
    blockers: list[MutualFundBlocker] = []
    for switch_id, events in sorted(switch_events.items()):
        outgoing = [
            event
            for event in events
            if event.event_type is FundEventType.SWITCH_OUT
        ]
        incoming = [
            event
            for event in events
            if event.event_type is FundEventType.SWITCH_IN
        ]
        if not switch_id or len(outgoing) != 1 or len(incoming) != 1:
            blockers.append(
                MutualFundBlocker(
                    "UNPAIRED_SWITCH",
                    f"Switch {switch_id!r} must have one out and one in leg",
                    tuple(sorted({event.scheme_id for event in events})),
                    event_references(events),
                )
            )
            continue
        out_event = outgoing[0]
        in_event = incoming[0]
        if (
            out_event.event_date != in_event.event_date
            or out_event.gross_amount - out_event.deductible_charges
            != in_event.gross_amount
        ):
            blockers.append(
                MutualFundBlocker(
                    "SWITCH_CONSIDERATION_MISMATCH",
                    (
                        f"Switch {switch_id} net outgoing consideration "
                        "must equal incoming acquisition amount on the same date"
                    ),
                    tuple(
                        sorted(
                            {out_event.scheme_id, in_event.scheme_id}
                        )
                    ),
                    event_references(events),
                )
            )
    return blockers


def _bucket(
    classification: StatutoryFundClass,
    acquisition_date: date,
    sale_date: date,
    exchange_listed: bool,
    stt_status: SttStatus | None,
) -> FundTaxBucket:
    if classification is StatutoryFundClass.EQUITY_ORIENTED:
        if stt_status is SttStatus.NOT_PAID:
            if sale_date > _add_months(acquisition_date, 12):
                return FundTaxBucket.LTCG_112
            return FundTaxBucket.STCG_SLAB
        if sale_date > _add_months(acquisition_date, 12):
            return FundTaxBucket.LTCG_112A
        return FundTaxBucket.STCG_111A
    if (
        classification is StatutoryFundClass.SPECIFIED_MUTUAL_FUND
        and acquisition_date >= date(2023, 4, 1)
    ):
        return FundTaxBucket.STCG_50AA
    holding_months = 12 if exchange_listed else 24
    if sale_date > _add_months(acquisition_date, holding_months):
        return FundTaxBucket.LTCG_112
    return FundTaxBucket.STCG_SLAB


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
