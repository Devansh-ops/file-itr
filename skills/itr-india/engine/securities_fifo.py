"""Account-local FIFO reconciliation for listed delivery securities."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.bank_interest_ledger import SourceProvenance
from engine.securities_ledger import (
    SecurityEvent,
    SecurityEventType,
    SecurityLedger,
    TaxTreatment,
)


@dataclass(frozen=True, slots=True)
class SecurityBlocker:
    code: str
    message: str
    event_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()


class SecurityReconciliationError(ValueError):
    def __init__(self, blockers: list[SecurityBlocker]):
        self.blockers = tuple(
            sorted(
                blockers,
                key=lambda blocker: (
                    blocker.code,
                    blocker.event_ids,
                    blocker.evidence_references,
                    blocker.message,
                ),
            )
        )
        self.blocker_codes = frozenset(
            blocker.code for blocker in self.blockers
        )
        super().__init__(
            "Security reconciliation blocked: "
            + "; ".join(
                f"{blocker.code}: {blocker.message}"
                for blocker in self.blockers
            )
        )


@dataclass(frozen=True, slots=True)
class MatchedDisposal:
    account_id: str
    isin: str
    security_name: str
    sale_event_id: str
    acquisition_event_id: str
    acquisition_date: date
    sale_date: date
    quantity: Decimal
    gross_proceeds: Decimal
    sale_charges: Decimal
    actual_cost_basis: Decimal
    fair_market_value: Decimal
    cost_basis: Decimal
    gain: Decimal
    is_long_term: bool
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class SecurityFifoResult:
    matched_disposals: tuple[MatchedDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]
    deductible_charges: Decimal
    non_deductible_stt: Decimal


@dataclass(slots=True)
class _Lot:
    acquisition_event_id: str
    acquisition_sequence: int
    acquisition_date: date
    quantity: Decimal
    total_cost: Decimal
    fmv_31jan2018_per_unit: Decimal | None
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


def reconcile_security_fifo(ledger: SecurityLedger) -> SecurityFifoResult:
    blockers: list[SecurityBlocker] = []
    security_by_isin = {
        security.isin: security for security in ledger.securities
    }
    for security in ledger.securities:
        if security.tax_treatment is TaxTreatment.UNRESOLVED:
            blockers.append(
                SecurityBlocker(
                    "AMBIGUOUS_TAX_TREATMENT",
                    (
                        f"{security.isin} investment-versus-business treatment "
                        "is unresolved"
                    ),
                )
            )
        elif security.tax_treatment is TaxTreatment.BUSINESS:
            blockers.append(
                SecurityBlocker(
                    "BUSINESS_TREATMENT_REQUIRES_ITR3",
                    (
                        f"{security.isin} is explicitly business inventory, "
                        "not Schedule CG"
                    ),
                )
            )
    for event in ledger.events:
        if (
            event.event_type is SecurityEventType.SELL
            and not event.stt_paid
        ):
            blockers.append(
                _event_blocker(
                    "NON_STT_DELIVERY_SALE_UNSUPPORTED",
                    "This Schedule CG/112A slice supports only STT-paid sales",
                    event,
                )
            )
        if (
            event.event_type is SecurityEventType.CORPORATE_ACTION
            and event.corporate_action not in {"split", "bonus"}
        ):
            blockers.append(
                _event_blocker(
                    "UNSUPPORTED_CORPORATE_ACTION",
                    f"{event.corporate_action!r} is not supported",
                    event,
                )
            )
    if blockers:
        raise SecurityReconciliationError(blockers)

    lots: dict[tuple[str, str], list[_Lot]] = defaultdict(list)
    matches: list[MatchedDisposal] = []
    gross_sales: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    ordered_events = sorted(
        ledger.events,
        key=lambda event: (event.event_date, event.sequence),
    )
    for event in ordered_events:
        key = (event.account_id, event.isin)
        if event.event_type is SecurityEventType.BUY:
            lots[key].append(
                _Lot(
                    acquisition_event_id=event.event_id,
                    acquisition_sequence=event.sequence,
                    acquisition_date=event.event_date,
                    quantity=event.quantity,
                    total_cost=event.gross_amount + event.deductible_charges,
                    fmv_31jan2018_per_unit=event.fmv_31jan2018_per_unit,
                    evidence_references=(event.evidence_reference,),
                    source_provenance=(event.provenance,),
                )
            )
        elif event.event_type is SecurityEventType.TRANSFER:
            transferred = _consume_lots(
                lots[key],
                event.quantity,
                event,
                blockers,
            )
            _add_transfer_charges(transferred, event.deductible_charges)
            destination = lots[(event.to_account_id or "", event.isin)]
            destination.extend(transferred)
            destination.sort(key=_lot_sort_key)
        elif event.event_type is SecurityEventType.CORPORATE_ACTION:
            _apply_corporate_action(lots[key], event)
        else:
            gross_sales[event.account_id] += event.gross_amount
            sold_lots = _consume_lots(
                lots[key],
                event.quantity,
                event,
                blockers,
            )
            remaining_proceeds = event.gross_amount
            remaining_charges = event.deductible_charges
            for index, sold_lot in enumerate(sold_lots):
                if index == len(sold_lots) - 1:
                    proceeds = remaining_proceeds
                    sale_charges = remaining_charges
                else:
                    fraction = sold_lot.quantity / event.quantity
                    proceeds = event.gross_amount * fraction
                    sale_charges = event.deductible_charges * fraction
                    remaining_proceeds -= proceeds
                    remaining_charges -= sale_charges
                actual_cost, fair_value, cost_basis = _cost_details(
                    sold_lot,
                    proceeds,
                    event,
                    blockers,
                )
                matches.append(
                    MatchedDisposal(
                        account_id=event.account_id,
                        isin=event.isin,
                        security_name=security_by_isin[event.isin].security_name,
                        sale_event_id=event.event_id,
                        acquisition_event_id=sold_lot.acquisition_event_id,
                        acquisition_date=sold_lot.acquisition_date,
                        sale_date=event.event_date,
                        quantity=sold_lot.quantity,
                        gross_proceeds=proceeds,
                        sale_charges=sale_charges,
                        actual_cost_basis=actual_cost,
                        fair_market_value=fair_value,
                        cost_basis=cost_basis,
                        gain=proceeds - sale_charges - cost_basis,
                        is_long_term=event.event_date
                        > _add_months(sold_lot.acquisition_date, 12),
                        evidence_references=tuple(
                            sorted(
                                {
                                    *sold_lot.evidence_references,
                                    event.evidence_reference,
                                }
                            )
                        ),
                        source_provenance=sold_lot.source_provenance,
                    )
                )

    closing_positions = {
        key: sum((lot.quantity for lot in account_lots), Decimal("0"))
        for key, account_lots in lots.items()
        if any(lot.quantity > 0 for lot in account_lots)
    }
    _reconcile_broker_summaries(
        ledger,
        gross_sales,
        closing_positions,
        blockers,
    )
    if blockers:
        raise SecurityReconciliationError(blockers)
    broker_provenance = _broker_provenance_by_account(ledger)
    matches = [
        replace(
            match,
            source_provenance=_merge_provenance(
                match.source_provenance,
                broker_provenance[match.account_id],
            ),
        )
        for match in matches
    ]
    return SecurityFifoResult(
        matched_disposals=tuple(matches),
        closing_positions=MappingProxyType(
            dict(sorted(closing_positions.items()))
        ),
        deductible_charges=sum(
            (event.deductible_charges for event in ledger.events),
            Decimal("0"),
        ),
        non_deductible_stt=sum(
            (event.stt for event in ledger.events),
            Decimal("0"),
        ),
    )


def _consume_lots(
    lots: list[_Lot],
    quantity: Decimal,
    event: SecurityEvent,
    blockers: list[SecurityBlocker],
) -> list[_Lot]:
    available = sum((lot.quantity for lot in lots), Decimal("0"))
    if available < quantity:
        blockers.append(
            _event_blocker(
                "INSUFFICIENT_ACCOUNT_HOLDING",
                f"{event.event_id} needs {quantity} units but account has {available}",
                event,
            )
        )
        return []
    remaining = quantity
    consumed: list[_Lot] = []
    while remaining > 0:
        lot = lots[0]
        taken = min(remaining, lot.quantity)
        cost = lot.total_cost * taken / lot.quantity
        consumed.append(
            _Lot(
                acquisition_event_id=lot.acquisition_event_id,
                acquisition_sequence=lot.acquisition_sequence,
                acquisition_date=lot.acquisition_date,
                quantity=taken,
                total_cost=cost,
                fmv_31jan2018_per_unit=lot.fmv_31jan2018_per_unit,
                evidence_references=tuple(
                    sorted(
                        {
                            *lot.evidence_references,
                            event.evidence_reference,
                        }
                    )
                ),
                source_provenance=_merge_provenance(
                    lot.source_provenance,
                    (event.provenance,),
                ),
            )
        )
        lot.quantity -= taken
        lot.total_cost -= cost
        remaining -= taken
        if lot.quantity == 0:
            lots.pop(0)
    return consumed


def _apply_corporate_action(lots: list[_Lot], event: SecurityEvent) -> None:
    ratio = (event.ratio_numerator or Decimal("0")) / (
        event.ratio_denominator or Decimal("1")
    )
    if event.corporate_action == "split":
        for lot in lots:
            lot.quantity *= ratio
            if lot.fmv_31jan2018_per_unit is not None:
                lot.fmv_31jan2018_per_unit /= ratio
            lot.evidence_references = tuple(
                sorted(
                    {
                        *lot.evidence_references,
                        event.evidence_reference,
                    }
                )
            )
            lot.source_provenance = _merge_provenance(
                lot.source_provenance,
                (event.provenance,),
            )
        return
    existing_quantity = sum((lot.quantity for lot in lots), Decimal("0"))
    bonus_quantity = existing_quantity * ratio
    if bonus_quantity:
        entitlement_references = tuple(
            sorted(
                {
                    event.evidence_reference,
                    *(
                        reference
                        for lot in lots
                        for reference in lot.evidence_references
                    ),
                }
            )
        )
        entitlement_provenance = _merge_provenance(
            *(lot.source_provenance for lot in lots),
            (event.provenance,),
        )
        lots.append(
            _Lot(
                acquisition_event_id=event.event_id,
                acquisition_sequence=event.sequence,
                acquisition_date=event.event_date,
                quantity=bonus_quantity,
                total_cost=Decimal("0"),
                fmv_31jan2018_per_unit=event.fmv_31jan2018_per_unit,
                evidence_references=entitlement_references,
                source_provenance=entitlement_provenance,
            )
        )


def _add_transfer_charges(
    transferred: list[_Lot],
    charges: Decimal,
) -> None:
    if not transferred or charges == 0:
        return
    total_quantity = sum(
        (lot.quantity for lot in transferred),
        Decimal("0"),
    )
    remaining = charges
    for index, lot in enumerate(transferred):
        if index == len(transferred) - 1:
            allocated = remaining
        else:
            allocated = charges * lot.quantity / total_quantity
            remaining -= allocated
        lot.total_cost += allocated


def _lot_sort_key(lot: _Lot) -> tuple[date, int, str]:
    return (
        lot.acquisition_date,
        lot.acquisition_sequence,
        lot.acquisition_event_id,
    )


def _cost_details(
    lot: _Lot,
    proceeds: Decimal,
    sale: SecurityEvent,
    blockers: list[SecurityBlocker],
) -> tuple[Decimal, Decimal, Decimal]:
    if lot.acquisition_date > date(2018, 1, 31):
        return lot.total_cost, Decimal("0"), lot.total_cost
    if lot.fmv_31jan2018_per_unit is None:
        blockers.append(
            _event_blocker(
                "MISSING_31JAN2018_FMV",
                f"{lot.acquisition_event_id} needs grandfathering FMV",
                sale,
            )
        )
        return lot.total_cost, Decimal("0"), lot.total_cost
    fair_value = lot.fmv_31jan2018_per_unit * lot.quantity
    deemed_cost = max(lot.total_cost, min(fair_value, proceeds))
    return lot.total_cost, fair_value, deemed_cost


def _reconcile_broker_summaries(
    ledger: SecurityLedger,
    gross_sales: dict[str, Decimal],
    closing_positions: dict[tuple[str, str], Decimal],
    blockers: list[SecurityBlocker],
) -> None:
    summaries = {
        summary.account_id: summary for summary in ledger.broker_summaries
    }
    event_accounts = {
        event.account_id for event in ledger.events
    } | {
        event.to_account_id
        for event in ledger.events
        if event.to_account_id is not None
    }
    for account_id in sorted(event_accounts - summaries.keys()):
        blockers.append(
            SecurityBlocker(
                "MISSING_BROKER_SUMMARY",
                f"Account {account_id} has no broker reconciliation summary",
            )
        )
    for account_id, summary in sorted(summaries.items()):
        if summary.gross_sale_proceeds != gross_sales[account_id]:
            blockers.append(
                SecurityBlocker(
                    "BROKER_SALE_PROCEEDS_MISMATCH",
                    f"Account {account_id} ledger sales {gross_sales[account_id]} "
                    f"do not match broker {summary.gross_sale_proceeds}",
                    evidence_references=(
                        _provenance_reference(summary.provenance),
                    ),
                )
            )
        reported = {
            position.isin: position.quantity
            for position in summary.closing_positions
        }
        actual_isins = {
            isin
            for (account, isin), quantity in closing_positions.items()
            if account == account_id and quantity > 0
        }
        for isin in sorted(actual_isins | reported.keys()):
            actual = closing_positions.get((account_id, isin), Decimal("0"))
            expected = reported.get(isin, Decimal("0"))
            if actual != expected:
                position = next(
                    (
                        item
                        for item in summary.closing_positions
                        if item.isin == isin
                    ),
                    None,
                )
                references = {
                    _provenance_reference(summary.provenance)
                }
                if position is not None:
                    references.add(
                        _provenance_reference(position.provenance)
                    )
                blockers.append(
                    SecurityBlocker(
                        "BROKER_CLOSING_POSITION_MISMATCH",
                        f"Account {account_id} {isin} closing quantity {actual} "
                        f"does not match broker {expected}",
                        evidence_references=tuple(sorted(references)),
                    )
                )


def _event_blocker(
    code: str,
    message: str,
    event: SecurityEvent,
) -> SecurityBlocker:
    return SecurityBlocker(
        code,
        message,
        (event.event_id,),
        (event.evidence_reference,),
    )


def _provenance_reference(provenance: SourceProvenance) -> str:
    return (
        f"{provenance.source_document}"
        f"#{provenance.source_location}"
    )


def _merge_provenance(
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


def _broker_provenance_by_account(
    ledger: SecurityLedger,
) -> dict[str, tuple[SourceProvenance, ...]]:
    return {
        summary.account_id: _merge_provenance(
            (summary.provenance,),
            tuple(
                position.provenance
                for position in summary.closing_positions
            ),
        )
        for summary in ledger.broker_summaries
    }


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
