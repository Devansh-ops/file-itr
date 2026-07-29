"""Immutable filing projection and audit trace for fixed income."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping

from engine.fixed_income_ledger import (
    FixedIncomeEvent,
    FixedIncomeLedger,
    FixedIncomeReceiptObservation,
)
from engine.fixed_income_types import (
    FixedIncomeAuditLine,
    FixedIncomeReconciliationResult,
    FixedIncomeSlice,
    FixedIncomeTaxBucket,
    provenance_reference,
)


_SCHEDULE_CG_FIELD_BY_BUCKET = {
    FixedIncomeTaxBucket.STCG_50AA: "STCG50AA",
    FixedIncomeTaxBucket.STCG_SLAB: "STCGOther",
    FixedIncomeTaxBucket.LTCG_112: "LTCG112",
}


def build_fixed_income_slice(
    ledger: FixedIncomeLedger,
    result: FixedIncomeReconciliationResult,
) -> FixedIncomeSlice:
    filing_values = _filing_values(
        result.interest_income,
        result.tds_credit,
        result.capital_gain_totals,
    )
    return FixedIncomeSlice(
        interest_income=result.interest_income,
        tds_credit=result.tds_credit,
        cash_receipts=result.cash_receipts,
        non_deductible_stt=result.non_deductible_stt,
        capital_gain_totals=result.capital_gain_totals,
        matched_disposals=result.matched_disposals,
        closing_positions=result.closing_positions,
        filing_values=_freeze(filing_values),
        audit_trace=_audit_trace(ledger, result),
    )


def _filing_values(
    interest_income: Decimal,
    tds_credit: Decimal,
    totals: Mapping[FixedIncomeTaxBucket, Decimal],
) -> dict[str, Any]:
    schedule_cg = {
        field: totals.get(bucket, Decimal("0"))
        for bucket, field in _SCHEDULE_CG_FIELD_BY_BUCKET.items()
    }
    schedule_cg["Total"] = sum(
        schedule_cg.values(),
        Decimal("0"),
    )
    return {
        "ScheduleOS": {
            "InterestOnSecurities": interest_income,
        },
        "ScheduleTDS2": {
            "FixedIncomeTDS": tds_credit,
        },
        "ScheduleCG": schedule_cg,
    }


def _audit_trace(
    ledger: FixedIncomeLedger,
    result: FixedIncomeReconciliationResult,
) -> tuple[FixedIncomeAuditLine, ...]:
    observations_by_event: dict[
        str,
        list[FixedIncomeReceiptObservation],
    ] = defaultdict(list)
    for observation in ledger.receipt_observations:
        observations_by_event[observation.event_id].append(observation)
    lines: list[FixedIncomeAuditLine] = []
    interest_events = tuple(
        event
        for event in ledger.events
        if event.event_type.is_receipt and event.interest_component
    )
    if result.interest_income:
        lines.append(
            _income_audit_line(
                "/ScheduleOS/InterestOnSecurities",
                result.interest_income,
                "sum-evidenced-coupon-and-accrued-interest",
                interest_events,
                observations_by_event,
            )
        )
    tds_events = tuple(
        event
        for event in ledger.events
        if event.event_type.is_receipt and event.tds_withheld
    )
    if result.tds_credit:
        lines.append(
            _income_audit_line(
                "/ScheduleTDS2/FixedIncomeTDS",
                result.tds_credit,
                "sum-form-26as-reconciled-fixed-income-tds",
                tds_events,
                observations_by_event,
            )
        )
    instrument_by_isin = {
        instrument.isin: instrument for instrument in ledger.instruments
    }
    for bucket, amount in sorted(
        result.capital_gain_totals.items(),
        key=lambda item: item[0].value,
    ):
        bucket_matches = tuple(
            match
            for match in result.matched_disposals
            if match.tax_bucket is bucket
        )
        event_ids = tuple(
            sorted(
                {
                    identifier
                    for match in bucket_matches
                    for identifier in (
                        *match.lineage_event_ids,
                        match.disposal_event_id,
                    )
                }
            )
        )
        references = {
            reference
            for match in bucket_matches
            for reference in match.evidence_references
        }
        references.update(
            provenance_reference(
                instrument_by_isin[match.isin].terms.provenance
            )
            for match in bucket_matches
        )
        lines.append(
            FixedIncomeAuditLine(
                output_path=(
                    f"/ScheduleCG/"
                    f"{_SCHEDULE_CG_FIELD_BY_BUCKET[bucket]}"
                ),
                amount=amount,
                transformation=(
                    "account-local-fifo-then-event-date-debt-classification"
                ),
                event_ids=event_ids,
                evidence_references=tuple(sorted(references)),
            )
        )
    return tuple(lines)


def _income_audit_line(
    output_path: str,
    amount: Decimal,
    transformation: str,
    events: tuple[FixedIncomeEvent, ...],
    observations_by_event: Mapping[
        str,
        list[FixedIncomeReceiptObservation],
    ],
) -> FixedIncomeAuditLine:
    references = {
        provenance_reference(event.provenance) for event in events
    }
    references.update(
        provenance_reference(observation.provenance)
        for event in events
        for observation in observations_by_event[event.event_id]
    )
    return FixedIncomeAuditLine(
        output_path=output_path,
        amount=amount,
        transformation=transformation,
        event_ids=tuple(sorted(event.event_id for event in events)),
        evidence_references=tuple(sorted(references)),
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


__all__ = ["build_fixed_income_slice"]
