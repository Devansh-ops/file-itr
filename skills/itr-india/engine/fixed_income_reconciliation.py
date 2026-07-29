"""Reconcile fixed-income evidence, FIFO lots, and tax classifications."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType

from engine.fixed_income_ledger import (
    FixedIncomeEvent,
    FixedIncomeEventType,
    FixedIncomeInstrument,
    FixedIncomeInstrumentKind,
    FixedIncomeLegalForm,
    FixedIncomeLedger,
    FixedIncomeReceiptObservation,
    ReceiptEvidenceType,
    SettlementBreakdown,
)
from engine.fixed_income_types import (
    FixedIncomeBlocker,
    FixedIncomeReconciliationError,
    FixedIncomeReconciliationResult,
    FixedIncomeTaxBucket,
    MatchedFixedIncomeDisposal,
    provenance_reference,
)


_SECTION_50AA_UNLISTED_DEBT_CUTOFF = date(2024, 7, 23)


@dataclass(slots=True)
class _Lot:
    acquisition_event_id: str
    acquisition_date: date
    sequence: int
    quantity: Decimal
    capital_cost: Decimal
    lineage_event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]


def reconcile_fixed_income(
    ledger: FixedIncomeLedger,
) -> FixedIncomeReconciliationResult:
    _check_computation_prerequisites(ledger)
    _reconcile_receipt_observations(ledger)
    instruments = {
        instrument.isin: instrument for instrument in ledger.instruments
    }
    lots: dict[tuple[str, str], list[_Lot]] = defaultdict(list)
    matches: list[MatchedFixedIncomeDisposal] = []
    totals: dict[FixedIncomeTaxBucket, Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for event in sorted(
        ledger.events,
        key=lambda item: (item.event_date, item.sequence),
    ):
        key = (event.account_id, event.isin)
        if event.event_type is FixedIncomeEventType.ACQUISITION:
            lots[key].append(
                _Lot(
                    event.event_id,
                    event.event_date,
                    event.sequence,
                    event.quantity,
                    event.capital_component
                    + event.deductible_charges,
                    (event.event_id,),
                    (provenance_reference(event.provenance),),
                )
            )
            continue
        if event.event_type is FixedIncomeEventType.TRANSFER:
            transferred_lots = _consume_lots(
                lots[key],
                event.quantity,
                event,
            )
            _carry_transfer_cost_and_lineage(
                transferred_lots,
                event,
            )
            assert event.to_account_id is not None
            destination = (event.to_account_id, event.isin)
            lots[destination].extend(transferred_lots)
            lots[destination].sort(key=_lot_sort_key)
            continue
        if not event.event_type.is_disposal:
            continue
        disposed_lots = _consume_lots(
            lots[key],
            event.quantity,
            event,
        )
        remaining_proceeds = event.capital_component
        remaining_charges = event.deductible_charges
        for index, lot in enumerate(disposed_lots):
            if index == len(disposed_lots) - 1:
                proceeds = remaining_proceeds
                charges = remaining_charges
            else:
                fraction = lot.quantity / event.quantity
                proceeds = event.capital_component * fraction
                charges = event.deductible_charges * fraction
                remaining_proceeds -= proceeds
                remaining_charges -= charges
            gain = proceeds - charges - lot.capital_cost
            bucket = _tax_bucket(
                instruments[event.isin],
                event,
                lot.acquisition_date,
            )
            totals[bucket] += gain
            matches.append(
                MatchedFixedIncomeDisposal(
                    account_id=event.account_id,
                    isin=event.isin,
                    disposal_event_id=event.event_id,
                    acquisition_event_id=lot.acquisition_event_id,
                    acquisition_date=lot.acquisition_date,
                    disposal_date=event.event_date,
                    quantity=lot.quantity,
                    capital_proceeds=proceeds,
                    interest_component=(
                        event.interest_component
                        * lot.quantity
                        / event.quantity
                    ),
                    deductible_charges=charges,
                    cost_basis=lot.capital_cost,
                    gain=gain,
                    tax_bucket=bucket,
                    lineage_event_ids=lot.lineage_event_ids,
                    evidence_references=tuple(
                        sorted(
                            {
                                *lot.evidence_references,
                                provenance_reference(
                                    event.provenance
                                ),
                            }
                        )
                    ),
                )
            )
    closing_positions = {
        key: sum((lot.quantity for lot in value), Decimal("0"))
        for key, value in lots.items()
        if any(lot.quantity > 0 for lot in value)
    }
    _reconcile_account_summaries(ledger, closing_positions)
    receipt_events = tuple(
        event for event in ledger.events if event.event_type.is_receipt
    )
    return FixedIncomeReconciliationResult(
        interest_income=sum(
            (event.interest_component for event in receipt_events),
            Decimal("0"),
        ),
        tds_credit=sum(
            (event.tds_withheld for event in receipt_events),
            Decimal("0"),
        ),
        cash_receipts=sum(
            (event.cash_settlement for event in receipt_events),
            Decimal("0"),
        ),
        non_deductible_stt=sum(
            (
                event.securities_transaction_tax
                for event in ledger.events
            ),
            Decimal("0"),
        ),
        capital_gain_totals=MappingProxyType(dict(totals)),
        matched_disposals=tuple(matches),
        closing_positions=MappingProxyType(closing_positions),
    )


def _check_computation_prerequisites(
    ledger: FixedIncomeLedger,
) -> None:
    blockers: list[FixedIncomeBlocker] = []
    instrument_by_isin = {
        instrument.isin: instrument for instrument in ledger.instruments
    }
    for instrument in ledger.instruments:
        for feature in instrument.terms.unsupported_features:
            blockers.append(
                FixedIncomeBlocker(
                    code=f"UNSUPPORTED_{feature.value.upper()}",
                    message=(
                        f"{instrument.isin} requires human treatment "
                        f"for {feature.value}"
                    ),
                    event_ids=tuple(
                        sorted(
                            event.event_id
                            for event in ledger.events
                            if event.isin == instrument.isin
                        )
                    ),
                    evidence_references=(
                        provenance_reference(
                            instrument.terms.provenance
                        ),
                    ),
                )
            )
    for event in ledger.events:
        instrument = instrument_by_isin[event.isin]
        if (
            event.settlement_breakdown
            is SettlementBreakdown.UNRESOLVED_DIRTY
        ):
            blockers.append(
                FixedIncomeBlocker(
                    code="UNRESOLVED_DIRTY_SETTLEMENT",
                    message=(
                        f"{event.event_id} lacks an evidenced clean-price "
                        "and accrued-interest split"
                    ),
                    event_ids=(event.event_id,),
                    evidence_references=(
                        provenance_reference(event.provenance),
                    ),
                )
            )
        if (
            event.event_type.is_disposal
            and not event.exchange_listed_on_event
            and instrument.terms.statutory_zero_coupon_bond
            and instrument.terms.legal_form
            is FixedIncomeLegalForm.BOND_OR_DEBENTURE
            and event.event_date
            >= _SECTION_50AA_UNLISTED_DEBT_CUTOFF
        ):
            blockers.append(
                FixedIncomeBlocker(
                    code=(
                        "UNLISTED_ZERO_COUPON_50AA_"
                        "CLASSIFICATION_CONFLICT"
                    ),
                    message=(
                        f"{event.event_id} is both an unlisted "
                        "bond/debenture and a statutory zero-coupon bond; "
                        "human legal classification is required"
                    ),
                    event_ids=(event.event_id,),
                    evidence_references=tuple(
                        sorted(
                            {
                                provenance_reference(event.provenance),
                                provenance_reference(
                                    instrument.terms.provenance
                                ),
                            }
                        )
                    ),
                )
            )
    if blockers:
        raise FixedIncomeReconciliationError(blockers)


def _reconcile_receipt_observations(
    ledger: FixedIncomeLedger,
) -> None:
    observations_by_event: dict[
        str,
        list[FixedIncomeReceiptObservation],
    ] = defaultdict(list)
    for observation in ledger.receipt_observations:
        observations_by_event[observation.event_id].append(observation)
    blockers: list[FixedIncomeBlocker] = []
    for event in ledger.events:
        if not event.event_type.is_receipt:
            continue
        observations = observations_by_event[event.event_id]
        bank_values = {
            observation.net_cash_received
            for observation in observations
            if (
                observation.evidence_type
                is ReceiptEvidenceType.BANK_STATEMENT
            )
        }
        if len(bank_values) > 1:
            blockers.append(
                _receipt_blocker(
                    "CASH_OBSERVATION_CONFLICT",
                    (
                        f"{event.event_id} has conflicting bank "
                        "receipt observations"
                    ),
                    event,
                    observations,
                )
            )
        if event.cash_settlement not in bank_values:
            blockers.append(
                _receipt_blocker(
                    "CASH_RECEIPT_MISMATCH",
                    f"{event.event_id} cash has no matching bank observation",
                    event,
                    observations,
                )
            )
        interest_values = {
            observation.gross_interest
            for observation in observations
            if observation.gross_interest is not None
        }
        if len(interest_values) > 1:
            blockers.append(
                _receipt_blocker(
                    "INTEREST_OBSERVATION_CONFLICT",
                    (
                        f"{event.event_id} has conflicting gross "
                        "interest observations"
                    ),
                    event,
                    observations,
                )
            )
        if (
            interest_values
            and event.interest_component not in interest_values
        ):
            blockers.append(
                _receipt_blocker(
                    "INTEREST_OBSERVATION_MISMATCH",
                    (
                        f"{event.event_id} interest component "
                        "does not reconcile"
                    ),
                    event,
                    observations,
                )
            )
        form_26as = [
            observation
            for observation in observations
            if (
                observation.evidence_type
                is ReceiptEvidenceType.FORM_26AS
            )
        ]
        if event.tds_withheld or form_26as:
            form_26as_values = {
                (
                    observation.gross_interest,
                    observation.tds_withheld,
                )
                for observation in form_26as
            }
            if len(form_26as_values) > 1:
                blockers.append(
                    _receipt_blocker(
                        "TDS_FORM26AS_CONFLICT",
                        (
                            f"{event.event_id} has conflicting "
                            "Form 26AS observations"
                        ),
                        event,
                        observations,
                    )
                )
            if not any(
                observation.gross_interest
                == event.interest_component
                and observation.tds_withheld == event.tds_withheld
                for observation in form_26as
            ):
                blockers.append(
                    _receipt_blocker(
                        "TDS_FORM26AS_MISMATCH",
                        (
                            f"{event.event_id} TDS does not "
                            "reconcile to Form 26AS"
                        ),
                        event,
                        observations,
                    )
                )
    if blockers:
        raise FixedIncomeReconciliationError(blockers)


def _receipt_blocker(
    code: str,
    message: str,
    event: FixedIncomeEvent,
    observations: list[FixedIncomeReceiptObservation],
) -> FixedIncomeBlocker:
    references = {
        provenance_reference(event.provenance),
        *(
            provenance_reference(observation.provenance)
            for observation in observations
        ),
    }
    return FixedIncomeBlocker(
        code=code,
        message=message,
        event_ids=(event.event_id,),
        evidence_references=tuple(sorted(references)),
    )


def _consume_lots(
    lots: list[_Lot],
    quantity: Decimal,
    event: FixedIncomeEvent,
) -> list[_Lot]:
    available = sum((lot.quantity for lot in lots), Decimal("0"))
    if available < quantity:
        raise FixedIncomeReconciliationError(
            [
                FixedIncomeBlocker(
                    "INSUFFICIENT_ACCOUNT_HOLDING",
                    (
                        f"{event.event_id} has insufficient "
                        "account-local units"
                    ),
                    (event.event_id,),
                    (provenance_reference(event.provenance),),
                )
            ]
        )
    remaining = quantity
    consumed: list[_Lot] = []
    while remaining > 0:
        lot = lots[0]
        taken = min(remaining, lot.quantity)
        cost = lot.capital_cost * taken / lot.quantity
        consumed.append(
            _Lot(
                lot.acquisition_event_id,
                lot.acquisition_date,
                lot.sequence,
                taken,
                cost,
                lot.lineage_event_ids,
                lot.evidence_references,
            )
        )
        lot.quantity -= taken
        lot.capital_cost -= cost
        remaining -= taken
        if lot.quantity == 0:
            lots.pop(0)
    return consumed


def _carry_transfer_cost_and_lineage(
    lots: list[_Lot],
    event: FixedIncomeEvent,
) -> None:
    remaining_charges = event.deductible_charges
    event_reference = provenance_reference(event.provenance)
    for index, lot in enumerate(lots):
        if index == len(lots) - 1:
            charges = remaining_charges
        else:
            charges = (
                event.deductible_charges
                * lot.quantity
                / event.quantity
            )
            remaining_charges -= charges
        lot.capital_cost += charges
        lot.lineage_event_ids = (
            *lot.lineage_event_ids,
            event.event_id,
        )
        lot.evidence_references = tuple(
            sorted(
                {
                    *lot.evidence_references,
                    event_reference,
                }
            )
        )


def _lot_sort_key(lot: _Lot) -> tuple[date, int, str]:
    return (
        lot.acquisition_date,
        lot.sequence,
        lot.acquisition_event_id,
    )


def _reconcile_account_summaries(
    ledger: FixedIncomeLedger,
    closing_positions: dict[tuple[str, str], Decimal],
) -> None:
    blockers: list[FixedIncomeBlocker] = []
    for summary in ledger.account_summaries:
        account_id = summary.account_id
        cash = sum(
            (
                event.cash_settlement
                for event in ledger.events
                if (
                    event.account_id == account_id
                    and event.event_type.is_receipt
                )
            ),
            Decimal("0"),
        )
        if cash != summary.net_cash_receipts:
            blockers.append(
                FixedIncomeBlocker(
                    "ACCOUNT_CASH_RECEIPTS_MISMATCH",
                    f"{account_id} net cash does not reconcile",
                    evidence_references=(
                        provenance_reference(summary.provenance),
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
        for isin in actual_isins | reported.keys():
            if closing_positions.get(
                (account_id, isin),
                Decimal("0"),
            ) != reported.get(isin, Decimal("0")):
                blockers.append(
                    FixedIncomeBlocker(
                        "ACCOUNT_CLOSING_POSITION_MISMATCH",
                        (
                            f"{account_id} {isin} closing "
                            "position does not reconcile"
                        ),
                        evidence_references=(
                            provenance_reference(summary.provenance),
                        ),
                    )
                )
    if blockers:
        raise FixedIncomeReconciliationError(blockers)


def _tax_bucket(
    instrument: FixedIncomeInstrument,
    event: FixedIncomeEvent,
    acquisition_date: date,
) -> FixedIncomeTaxBucket:
    if (
        instrument.terms.instrument_kind
        is FixedIncomeInstrumentKind.MARKET_LINKED_DEBENTURE
    ):
        return FixedIncomeTaxBucket.STCG_50AA
    if (
        instrument.terms.legal_form
        is FixedIncomeLegalForm.BOND_OR_DEBENTURE
        and not event.exchange_listed_on_event
        and event.event_date
        >= _SECTION_50AA_UNLISTED_DEBT_CUTOFF
    ):
        return FixedIncomeTaxBucket.STCG_50AA
    holding_months = (
        12
        if (
            event.exchange_listed_on_event
            or instrument.terms.statutory_zero_coupon_bond
        )
        else 24
    )
    if event.event_date > _add_months(acquisition_date, holding_months):
        return FixedIncomeTaxBucket.LTCG_112
    return FixedIncomeTaxBucket.STCG_SLAB


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


__all__ = ["reconcile_fixed_income"]
