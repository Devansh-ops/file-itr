from __future__ import annotations

from collections.abc import MutableMapping
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
import json
from types import MappingProxyType
from typing import Any, Mapping

from engine.bank_interest_ledger import InterestKind, SourceProvenance
from engine.bank_interest_reconciliation import (
    AccountOwnershipTrace,
    BankReconciliationError,
    ReconciledInterestEvent,
    ReconciliationBlocker,
)


@dataclass(frozen=True)
class AuditTraceLine:
    output_path: str
    amount: Decimal
    input_amount: Decimal
    transformation: str
    event_ids: tuple[str, ...]
    account_ownership: tuple[AccountOwnershipTrace, ...]
    sources: tuple[SourceProvenance, ...]


@dataclass(frozen=True)
class BankInterestSlice:
    savings_interest: Decimal
    term_deposit_interest: Decimal
    other_interest: Decimal
    total_interest: Decimal
    tds_claimed: Decimal
    schedule_os: Mapping[str, Any]
    schedule_tds2: Mapping[str, Any]
    audit_trace: tuple[AuditTraceLine, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            {
                "savings_interest": str(self.savings_interest),
                "term_deposit_interest": str(self.term_deposit_interest),
                "other_interest": str(self.other_interest),
                "total_interest": str(self.total_interest),
                "tds_claimed": str(self.tds_claimed),
                "schedule_os": _thaw(self.schedule_os),
                "schedule_tds2": _thaw(self.schedule_tds2),
                "audit_trace": [
                    {
                        "output_path": line.output_path,
                        "amount": str(line.amount),
                        "input_amount": str(line.input_amount),
                        "transformation": line.transformation,
                        "event_ids": list(line.event_ids),
                        "account_ownership": [
                            {
                                **asdict(account),
                                "ownership": account.ownership.value,
                                "ownership_share": (
                                    str(account.ownership_share)
                                    if account.ownership_share is not None
                                    else None
                                ),
                            }
                            for account in line.account_ownership
                        ],
                        "sources": [
                            source.model_dump(mode="json") for source in line.sources
                        ],
                    }
                    for line in self.audit_trace
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class _RoundedInterest:
    savings: int
    term_deposit: int
    other: int
    total: int


@dataclass(frozen=True)
class _TdsDetail:
    index: int
    tan: str
    gross_interest: Decimal
    tds_claimed: Decimal
    events: tuple[ReconciledInterestEvent, ...]


def build_bank_interest_slice(
    events: tuple[ReconciledInterestEvent, ...],
) -> BankInterestSlice:
    savings_events = tuple(
        event for event in events if event.interest_kind is InterestKind.SAVINGS
    )
    term_events = tuple(
        event for event in events if event.interest_kind is InterestKind.TERM_DEPOSIT
    )
    other_events = tuple(
        event for event in events if event.interest_kind is InterestKind.OTHER
    )
    savings = _sum_interest(savings_events)
    term = _sum_interest(term_events)
    other = _sum_interest(other_events)
    total = savings + term + other
    rounded = _allocate_interest_rupees(
        {
            "savings": savings,
            "term_deposit": term,
            "other": other,
        }
    )
    tds_details = _build_tds_details(events)
    tds_claimed = sum(
        (detail.tds_claimed for detail in tds_details),
        Decimal("0"),
    )
    schedule_os = _freeze(_schedule_os(rounded))
    schedule_tds2 = _freeze(_schedule_tds2(tds_details))
    audit_trace = _audit_trace(
        events=events,
        savings_events=savings_events,
        term_events=term_events,
        other_events=other_events,
        savings=savings,
        term=term,
        other=other,
        total=total,
        rounded=rounded,
        tds_details=tds_details,
        tds_claimed=tds_claimed,
    )
    return BankInterestSlice(
        savings_interest=savings,
        term_deposit_interest=term,
        other_interest=other,
        total_interest=total,
        tds_claimed=tds_claimed,
        schedule_os=schedule_os,
        schedule_tds2=schedule_tds2,
        audit_trace=audit_trace,
    )


def build_bank_interest_itr2_draft(
    base_itr2: Mapping[str, Any],
    filing_slice: BankInterestSlice,
) -> dict[str, Any]:
    draft = deepcopy(dict(base_itr2))
    try:
        itr2 = draft["ITR"]["ITR2"]
        if not isinstance(itr2, MutableMapping):
            raise TypeError("/ITR/ITR2 must be an object")
    except (KeyError, TypeError) as exc:
        raise BankReconciliationError(
            [
                ReconciliationBlocker(
                    "INVALID_ITR2_BASE",
                    "Base draft must contain /ITR/ITR2",
                )
            ]
        ) from exc
    itr2["ScheduleOS"] = _thaw(filing_slice.schedule_os)
    itr2["ScheduleTDS2"] = _thaw(filing_slice.schedule_tds2)
    return draft


def _sum_interest(events: tuple[ReconciledInterestEvent, ...]) -> Decimal:
    return sum((event.gross_interest for event in events), Decimal("0"))


def _allocate_interest_rupees(amounts: dict[str, Decimal]) -> _RoundedInterest:
    floors = {
        key: int(amount.to_integral_value(rounding=ROUND_FLOOR))
        for key, amount in amounts.items()
    }
    target = _rupees(sum(amounts.values(), Decimal("0")))
    remaining = target - sum(floors.values())
    ranked = sorted(
        amounts,
        key=lambda key: (
            -(amounts[key] - Decimal(floors[key])),
            key,
        ),
    )
    allocated = dict(floors)
    for key in ranked[:remaining]:
        allocated[key] += 1
    return _RoundedInterest(
        savings=allocated["savings"],
        term_deposit=allocated["term_deposit"],
        other=allocated["other"],
        total=target,
    )


def _schedule_os(rounded: _RoundedInterest) -> dict[str, Any]:
    required_zero_fields = (
        "DividendGross",
        "IntrstFrmIncmTaxRefund",
        "NatofPassThrghIncome",
        "RentFromMachPlantBldgs",
        "Tot562x",
        "Aggrtvaluewithoutcons562x",
        "Immovpropwithoutcons562x",
        "Immovpropinadeqcons562x",
        "Anyotherpropwithoutcons562x",
        "Anyotherpropinadeqcons562x",
        "FamilyPension",
        "AnyOtherIncome",
        "IncChargeableSpecialRates",
        "LtryPzzlChrgblUs115BB",
        "IncChrgblUs115BBE",
        "CashCreditsUs68",
        "UnExplndInvstmntsUs69",
        "UnExplndMoneyUs69A",
        "UnDsclsdInvstmntsUs69B",
        "UnExplndExpndtrUs69C",
        "AmtBrwdRepaidOnHundiUs69D",
        "OthersGross",
        "PassThrIncOSChrgblSplRate",
        "IncomeNotified89AOS",
    )
    income = {field: 0 for field in required_zero_fields}
    income.update(
        {
            "GrossIncChrgblTaxAtAppRate": rounded.total,
            "InterestGross": rounded.total,
            "IntrstFrmSavingBank": rounded.savings,
            "IntrstFrmTermDeposit": rounded.term_deposit,
            "IntrstFrmOthers": rounded.other,
            "Deductions": {
                "Expenses": 0,
                "DeductionUs57iia": 0,
                "Depreciation": 0,
                "TotDeductions": 0,
            },
            "BalanceNoRaceHorse": rounded.total,
            "TaxAccumulatedBalRecPF": {
                "TotalIncomeBenefit": 0,
                "TotalTaxBenefit": 0,
            },
        }
    )
    schedule: dict[str, Any] = {
        "IncOthThanOwnRaceHorse": income,
        "TotOthSrcNoRaceHorse": rounded.total,
        "IncChargeable": rounded.total,
    }
    for field in (
        "IncFrmLottery",
        "DividendIncUs115BBDA",
        "DividendIncUs115BBDAaiii",
        "DividendIncUs115A1ai",
        "DividendIncUs115AC",
        "DividendIncUs115ACA",
        "DividendIncUs115AD1i",
        "DividendDTAA",
        "NOT89A",
    ):
        schedule[field] = {"DateRange": _zero_date_range()}
    return schedule


def _zero_date_range() -> dict[str, int]:
    return {
        "Upto15Of6": 0,
        "Upto15Of9": 0,
        "Up16Of9To15Of12": 0,
        "Up16Of12To15Of3": 0,
        "Up16Of3To31Of3": 0,
    }


def _build_tds_details(
    events: tuple[ReconciledInterestEvent, ...],
) -> tuple[_TdsDetail, ...]:
    by_tan: dict[str, list[ReconciledInterestEvent]] = defaultdict(list)
    for event in events:
        if event.tds_amount > 0 and event.deductor_tan:
            by_tan[event.deductor_tan].append(event)
    return tuple(
        _TdsDetail(
            index=index,
            tan=tan,
            gross_interest=_sum_interest(tuple(by_tan[tan])),
            tds_claimed=sum(
                (event.tds_amount for event in by_tan[tan]),
                Decimal("0"),
            ),
            events=tuple(sorted(by_tan[tan], key=lambda event: event.event_id)),
        )
        for index, tan in enumerate(sorted(by_tan))
    )


def _schedule_tds2(details: tuple[_TdsDetail, ...]) -> dict[str, Any]:
    rows = []
    for detail in details:
        claimed = int(detail.tds_claimed)
        rows.append(
            {
                "TDSCreditName": "S",
                "TANOfDeductor": detail.tan,
                "TDSSection": "94A",
                "TaxDeductCreditDtls": {
                    "TaxDeductedOwnHands": claimed,
                    "TaxClaimedOwnHands": claimed,
                },
                "GrossAmount": _rupees(detail.gross_interest),
                "HeadOfIncome": "OS",
                "AmtCarriedFwd": 0,
            }
        )
    schedule: dict[str, Any] = {
        "TotalTDSonOthThanSals": sum(
            row["TaxDeductCreditDtls"]["TaxClaimedOwnHands"] for row in rows
        )
    }
    if rows:
        schedule["TDSOthThanSalaryDtls"] = rows
    return schedule


def _audit_trace(
    *,
    events: tuple[ReconciledInterestEvent, ...],
    savings_events: tuple[ReconciledInterestEvent, ...],
    term_events: tuple[ReconciledInterestEvent, ...],
    other_events: tuple[ReconciledInterestEvent, ...],
    savings: Decimal,
    term: Decimal,
    other: Decimal,
    total: Decimal,
    rounded: _RoundedInterest,
    tds_details: tuple[_TdsDetail, ...],
    tds_claimed: Decimal,
) -> tuple[AuditTraceLine, ...]:
    allocation = "largest-remainder-to-rounded-total-INR"
    lines = [
        _trace_line(path, total, rounded.total, events, allocation)
        for path in (
            "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/GrossIncChrgblTaxAtAppRate",
            "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/InterestGross",
            "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/BalanceNoRaceHorse",
            "/ITR/ITR2/ScheduleOS/TotOthSrcNoRaceHorse",
            "/ITR/ITR2/ScheduleOS/IncChargeable",
        )
    ]
    lines.extend(
        (
            _trace_line(
                "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/IntrstFrmSavingBank",
                savings,
                rounded.savings,
                savings_events,
                allocation,
            ),
            _trace_line(
                "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/IntrstFrmTermDeposit",
                term,
                rounded.term_deposit,
                term_events,
                allocation,
            ),
            _trace_line(
                "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/IntrstFrmOthers",
                other,
                rounded.other,
                other_events,
                allocation,
            ),
            _trace_line(
                "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals",
                tds_claimed,
                int(tds_claimed),
                tuple(event for event in events if event.tds_amount > 0),
                "exact-whole-INR-from-Form-26AS",
            ),
        )
    )
    for detail in tds_details:
        prefix = (
            f"/ITR/ITR2/ScheduleTDS2/TDSOthThanSalaryDtls/{detail.index}"
        )
        for suffix in (
            "/TaxDeductCreditDtls/TaxDeductedOwnHands",
            "/TaxDeductCreditDtls/TaxClaimedOwnHands",
        ):
            lines.append(
                _trace_line(
                    prefix + suffix,
                    detail.tds_claimed,
                    int(detail.tds_claimed),
                    detail.events,
                    "exact-whole-INR-from-Form-26AS",
                )
            )
        lines.append(
            _trace_line(
                prefix + "/GrossAmount",
                detail.gross_interest,
                _rupees(detail.gross_interest),
                detail.events,
                "round-half-up-to-whole-INR",
            )
        )
    return tuple(
        line for line in lines if line.input_amount != 0 or line.amount != 0
    )


def _trace_line(
    output_path: str,
    input_amount: Decimal,
    output_amount: int,
    events: tuple[ReconciledInterestEvent, ...],
    transformation: str,
) -> AuditTraceLine:
    ownership = {
        (
            event.ownership.account_id,
            event.ownership.ownership.value,
            event.ownership.ownership_share,
        ): event.ownership
        for event in events
    }
    sources = {
        source.sort_key(): source
        for event in events
        for source in event.sources
    }
    return AuditTraceLine(
        output_path=output_path,
        amount=Decimal(output_amount),
        input_amount=input_amount,
        transformation=transformation,
        event_ids=tuple(sorted(event.event_id for event in events)),
        account_ownership=tuple(ownership[key] for key in sorted(ownership)),
        sources=tuple(sources[key] for key in sorted(sources)),
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)


def _rupees(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
