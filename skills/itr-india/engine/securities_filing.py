"""Schedule CG and 112A mapping for reconciled delivery-security disposals."""

from __future__ import annotations

from collections.abc import MutableMapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from types import MappingProxyType
from typing import Any, Mapping

from engine.bank_interest_ledger import SourceProvenance
from engine.securities_fifo import MatchedDisposal, SecurityFifoResult


@dataclass(frozen=True, slots=True)
class SecurityAuditLine:
    output_path: str
    amount: Decimal
    transformation: str
    sale_event_ids: tuple[str, ...]
    acquisition_event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class DeliverySecuritySlice:
    matched_disposals: tuple[MatchedDisposal, ...]
    closing_positions: Mapping[tuple[str, str], Decimal]
    short_term_gain: Decimal
    long_term_gain: Decimal
    total_gain: Decimal
    deductible_charges: Decimal
    non_deductible_stt: Decimal
    schedule_cg: Mapping[str, Any]
    schedule_112a: Mapping[str, Any]
    audit_trace: tuple[SecurityAuditLine, ...]


def build_delivery_security_slice(
    fifo: SecurityFifoResult,
) -> DeliverySecuritySlice:
    short_matches = tuple(
        match for match in fifo.matched_disposals if not match.is_long_term
    )
    long_matches = tuple(
        match for match in fifo.matched_disposals if match.is_long_term
    )
    short_gain = _sum(match.gain for match in short_matches)
    long_gain = _sum(match.gain for match in long_matches)
    schedule_112a = _schedule_112a(long_matches)
    schedule_cg = _schedule_cg(
        short_matches,
        long_matches,
        schedule_112a,
    )
    rounded_gains = {
        "short": schedule_cg["ShortTermCapGainFor23"]["TotalSTCG"],
        "long": schedule_cg["LongTermCapGain23"]["TotalLTCG"],
    }
    return DeliverySecuritySlice(
        matched_disposals=fifo.matched_disposals,
        closing_positions=MappingProxyType(dict(fifo.closing_positions)),
        short_term_gain=short_gain,
        long_term_gain=long_gain,
        total_gain=short_gain + long_gain,
        deductible_charges=fifo.deductible_charges,
        non_deductible_stt=fifo.non_deductible_stt,
        schedule_cg=_freeze(schedule_cg),
        schedule_112a=_freeze(schedule_112a),
        audit_trace=_audit_trace(
            short_matches,
            long_matches,
            rounded_gains,
            schedule_cg,
            schedule_112a,
        ),
    )


def build_delivery_security_itr2_draft(
    base_itr2: Mapping[str, Any],
    filing_slice: DeliverySecuritySlice,
) -> dict[str, Any]:
    draft = deepcopy(dict(base_itr2))
    try:
        itr2 = draft["ITR"]["ITR2"]
        if not isinstance(itr2, MutableMapping):
            raise TypeError("/ITR/ITR2 must be an object")
    except (KeyError, TypeError) as exc:
        raise ValueError("Base draft must contain an object at /ITR/ITR2") from exc
    itr2["ScheduleCGFor23"] = _thaw(filing_slice.schedule_cg)
    itr2["Schedule112A"] = _thaw(filing_slice.schedule_112a)
    return draft


def _schedule_112a(
    matches: tuple[MatchedDisposal, ...],
) -> dict[str, Any]:
    keys = [str(index) for index in range(len(matches))]
    sale_values = _allocate_match_amounts(
        keys,
        matches,
        lambda match: match.gross_proceeds,
    )
    actual_costs = _allocate_match_amounts(
        keys,
        matches,
        lambda match: match.actual_cost_basis,
    )
    fair_values = _allocate_match_amounts(
        keys,
        matches,
        lambda match: match.fair_market_value,
    )
    expenses = _allocate_match_amounts(
        keys,
        matches,
        lambda match: match.sale_charges,
    )
    details = [
        _schedule_112a_detail(
            match,
            sale_value=sale_values[str(index)],
            actual_cost=actual_costs[str(index)],
            fair_value=fair_values[str(index)],
            expenses=expenses[str(index)],
        )
        for index, match in enumerate(matches)
    ]
    schedule = {
        "SaleValue112A": _detail_sum(details, "TotSaleValue"),
        "CostAcqWithoutIndx112A": _detail_sum(
            details,
            "CostAcqWithoutIndx",
        ),
        "AcquisitionCost112A": _detail_sum(details, "AcquisitionCost"),
        "LTCGBeforelowerB1B2112A": _detail_sum(
            details,
            "LTCGBeforelowerB1B2",
        ),
        "FairMktValueCapAst112A": _detail_sum(
            details,
            "TotFairMktValueCapAst",
        ),
        "ExpExclCnctTransfer112A": _detail_sum(
            details,
            "ExpExclCnctTransfer",
        ),
        "Deductions112A": _detail_sum(details, "TotalDeductions"),
        "Balance112A": _detail_sum(details, "Balance"),
        "TotalBalance112A": _detail_sum(details, "Balance"),
    }
    if details:
        schedule["Schedule112ADtls"] = details
    return schedule


def _schedule_112a_detail(
    match: MatchedDisposal,
    *,
    sale_value: int,
    actual_cost: int,
    fair_value: int,
    expenses: int,
) -> dict[str, Any]:
    before_cutoff = match.acquisition_date <= date(2018, 1, 31)
    if before_cutoff:
        filing_quantity = _filing_quantity(match.quantity)
        quantity = _number(filing_quantity)
        sale_price = _per_unit_for_total(
            sale_value,
            filing_quantity,
            "sale price",
        )
        fair_value_per_unit = _per_unit_for_total(
            fair_value,
            filing_quantity,
            "31 January 2018 FMV",
        )
    else:
        quantity = 0
        sale_price = 0
        fair_value_per_unit = 0
        fair_value = 0
    before_lower = min(sale_value, fair_value) if before_cutoff else 0
    deemed_cost = max(actual_cost, before_lower)
    deductions = deemed_cost + expenses
    gain = sale_value - deductions
    return {
        "ShareOnOrBefore": "BE" if before_cutoff else "AE",
        "ISINCode": match.isin if before_cutoff else "INNOTREQUIRD",
        "ShareUnitName": (
            match.security_name if before_cutoff else "CONSOLIDATED"
        ),
        "NumSharesUnits": quantity,
        "SalePricePerShareUnit": sale_price,
        "TotSaleValue": sale_value,
        "CostAcqWithoutIndx": deemed_cost,
        "AcquisitionCost": actual_cost,
        "LTCGBeforelowerB1B2": before_lower,
        "FairMktValuePerShareunit": fair_value_per_unit,
        "TotFairMktValueCapAst": fair_value,
        "ExpExclCnctTransfer": expenses,
        "TotalDeductions": deductions,
        "Balance": gain,
    }


def _audit_trace(
    short_matches: tuple[MatchedDisposal, ...],
    long_matches: tuple[MatchedDisposal, ...],
    rounded_gains: Mapping[str, int],
    schedule_cg: Mapping[str, Any],
    schedule_112a: Mapping[str, Any],
) -> tuple[SecurityAuditLine, ...]:
    all_matches = (*short_matches, *long_matches)
    lines: list[SecurityAuditLine] = []
    schedule_112a_header = {
        key: value
        for key, value in schedule_112a.items()
        if key != "Schedule112ADtls"
    }
    lines.extend(
        _numeric_audit_lines(
            "/ITR/ITR2/Schedule112A",
            schedule_112a_header,
            long_matches,
            "sum-officially-balanced-schedule-112a-detail-values",
            include_zero=bool(long_matches),
        )
    )
    details = schedule_112a.get("Schedule112ADtls", ())
    for index, (detail, match) in enumerate(
        zip(details, long_matches, strict=True)
    ):
        lines.extend(
            _numeric_audit_lines(
                f"/ITR/ITR2/Schedule112A/Schedule112ADtls/{index}",
                detail,
                (match,),
                (
                    "apply-schedule-112a-rules-84-85-87-88-89-"
                    "with-whole-rupee-rounding"
                ),
                include_zero=True,
            )
        )
    short = schedule_cg["ShortTermCapGainFor23"]
    if short_matches:
        lines.extend(
            _numeric_audit_lines(
                (
                    "/ITR/ITR2/ScheduleCGFor23/"
                    "ShortTermCapGainFor23/EquityMFonSTT"
                ),
                short["EquityMFonSTT"],
                short_matches,
                "round-source-components-then-derive-balanced-stcg",
                include_zero=True,
            )
        )
        lines.append(
            _audit_line(
                (
                    "/ITR/ITR2/ScheduleCGFor23/"
                    "ShortTermCapGainFor23/TotalSTCG"
                ),
                Decimal(rounded_gains["short"]),
                short_matches,
                "cross-tie-active-stcg-category",
            )
        )
    if long_matches:
        lines.extend(
            _numeric_audit_lines(
                (
                    "/ITR/ITR2/ScheduleCGFor23/"
                    "LongTermCapGain23/SaleOfEquityShareUs112A"
                ),
                schedule_cg["LongTermCapGain23"][
                    "SaleOfEquityShareUs112A"
                ],
                long_matches,
                "cross-tie-schedule-112a-balance",
                include_zero=True,
            )
        )
        lines.append(
            _audit_line(
                (
                    "/ITR/ITR2/ScheduleCGFor23/"
                    "LongTermCapGain23/TotalLTCG"
                ),
                Decimal(rounded_gains["long"]),
                long_matches,
                "cross-tie-active-ltcg-category",
            )
        )
    for field in ("SumOfCGIncm", "TotScheduleCGFor23"):
        lines.append(
            _audit_line(
                f"/ITR/ITR2/ScheduleCGFor23/{field}",
                Decimal(schedule_cg[field]),
                all_matches,
                "apply-statutory-current-year-capital-loss-setoff-matrix",
            )
        )
    lines.extend(
        _numeric_audit_lines(
            "/ITR/ITR2/ScheduleCGFor23/CurrYrLosses",
            schedule_cg["CurrYrLosses"],
            all_matches,
            "apply-statutory-current-year-capital-loss-setoff-matrix",
            include_zero=False,
        )
    )
    lines.extend(
        _numeric_audit_lines(
            "/ITR/ITR2/ScheduleCGFor23/AccruOrRecOfCG",
            schedule_cg["AccruOrRecOfCG"],
            all_matches,
            "allocate-taxable-gain-across-positive-net-date-ranges",
            include_zero=False,
        )
    )
    return tuple(line for line in lines if line.sale_event_ids)


def _numeric_audit_lines(
    path: str,
    value: Any,
    matches: tuple[MatchedDisposal, ...],
    transformation: str,
    *,
    include_zero: bool,
) -> list[SecurityAuditLine]:
    if isinstance(value, Mapping):
        lines: list[SecurityAuditLine] = []
        for key, item in value.items():
            lines.extend(
                _numeric_audit_lines(
                    f"{path}/{key}",
                    item,
                    matches,
                    transformation,
                    include_zero=include_zero,
                )
            )
        return lines
    if isinstance(value, (list, tuple)):
        lines = []
        for index, item in enumerate(value):
            lines.extend(
                _numeric_audit_lines(
                    f"{path}/{index}",
                    item,
                    matches,
                    transformation,
                    include_zero=include_zero,
                )
            )
        return lines
    if (
        isinstance(value, (int, float, Decimal))
        and not isinstance(value, bool)
        and (include_zero or value != 0)
    ):
        return [
            _audit_line(
                path,
                Decimal(str(value)),
                matches,
                transformation,
            )
        ]
    return []


def _audit_line(
    output_path: str,
    amount: Decimal,
    matches: tuple[MatchedDisposal, ...],
    transformation: str,
) -> SecurityAuditLine:
    return SecurityAuditLine(
        output_path=output_path,
        amount=amount,
        transformation=transformation,
        sale_event_ids=tuple(
            sorted({match.sale_event_id for match in matches})
        ),
        acquisition_event_ids=tuple(
            sorted({match.acquisition_event_id for match in matches})
        ),
        evidence_references=tuple(
            sorted(
                {
                    reference
                    for match in matches
                    for reference in match.evidence_references
                }
            )
        ),
        source_provenance=_audit_provenance(matches),
    )


def _audit_provenance(
    matches: tuple[MatchedDisposal, ...],
) -> tuple[SourceProvenance, ...]:
    unique = {
        (
            provenance.source_document,
            provenance.source_sha256,
            provenance.source_location,
            provenance.importer,
            provenance.importer_version,
        ): provenance
        for match in matches
        for provenance in match.source_provenance
    }
    return tuple(unique[key] for key in sorted(unique))


def _schedule_cg(
    short_matches: tuple[MatchedDisposal, ...],
    long_matches: tuple[MatchedDisposal, ...],
    schedule_112a: Mapping[str, Any],
) -> dict[str, Any]:
    short_sale = _sum(match.gross_proceeds for match in short_matches)
    short_cost = _sum(match.cost_basis for match in short_matches)
    short_expenses = _sum(match.sale_charges for match in short_matches)
    rounded_short_sale = _rupees(
        short_sale
        + _sum(match.gross_proceeds for match in long_matches)
    ) - int(schedule_112a["SaleValue112A"])
    rounded_short_cost = _rupees(
        short_cost
        + _sum(match.cost_basis for match in long_matches)
    ) - int(schedule_112a["CostAcqWithoutIndx112A"])
    rounded_short_expenses = _rupees(
        short_expenses
        + _sum(match.sale_charges for match in long_matches)
    ) - int(schedule_112a["ExpExclCnctTransfer112A"])
    if min(
        rounded_short_sale,
        rounded_short_cost,
        rounded_short_expenses,
    ) < 0:
        raise ValueError(
            "Schedule 112A whole-rupee detail allocation leaves a negative "
            "short-term component; normalize filing-compatible rows"
        )
    rounded_short_deductions = (
        rounded_short_cost + rounded_short_expenses
    )
    short_gain = rounded_short_sale - rounded_short_deductions
    long_gain = int(schedule_112a["TotalBalance112A"])
    short = _short_term_zero()
    if short_matches:
        short["EquityMFonSTT"] = [
            {
                "MFSectionCode": "1A",
                "EquityMFonSTTDtls": {
                    "FullConsideration": rounded_short_sale,
                    "DeductSec48": {
                        "AquisitCost": rounded_short_cost,
                        "ImproveCost": 0,
                        "ExpOnTrans": rounded_short_expenses,
                        "TotalDedn": rounded_short_deductions,
                    },
                    "BalanceCG": short_gain,
                    "LossSec94of7Or94of8": 0,
                    "CapgainonAssets": short_gain,
                },
            }
        ]
    short["TotalSTCG"] = short_gain
    long = _long_term_zero()
    long["SaleOfEquityShareUs112A"] = {
        "BalanceCG": long_gain,
        "DeductionUs54F": 0,
        "CapgainonAssets": long_gain,
    }
    long["TotalLTCG"] = long_gain
    losses, taxable_total = _current_year_losses(
        short_gain,
        long_gain,
    )
    return {
        "ShortTermCapGainFor23": short,
        "LongTermCapGain23": long,
        "SumOfCGIncm": taxable_total,
        "IncmFromVDATrnsf": 0,
        "TotScheduleCGFor23": taxable_total,
        "CurrYrLosses": losses,
        "AccruOrRecOfCG": _accrual_ranges(
            short_matches,
            long_matches,
            short_target=losses["InStcg20Per"]["CurrYrCapGain"],
            long_target=losses["InLtcg12_5Per"]["CurrYrCapGain"],
        ),
    }


def _short_term_zero() -> dict[str, Any]:
    return {
        "NRITransacSec48Dtl": {
            "NRItaxSTTPaid": 0,
            "NRItaxSTTNotPaid": 0,
        },
        "NRISecur115AD": _other_security_zero(),
        "SaleOnOtherAssets": _other_security_zero(),
        "TotalAmtDeemedStcg": 0,
        "PassThrIncNatureSTCG": 0,
        "TotalAmtNotTaxUsDTAAStcg": 0,
        "TotalAmtTaxUsDTAAStcg": 0,
        "TotalSTCG": 0,
    }


def _other_security_zero() -> dict[str, Any]:
    return {
        "FullValueConsdRecvUnqshr": 0,
        "FairMrktValueUnqshr": 0,
        "FullValueConsdSec50CA": 0,
        "FullValueConsdOthUnqshr": 0,
        "FullConsideration": 0,
        "DeductSec48": {
            "AquisitCost": 0,
            "ImproveCost": 0,
            "ExpOnTrans": 0,
            "TotalDedn": 0,
        },
        "BalanceCG": 0,
        "LossSec94of7Or94of8": 0,
        "CapgainonAssets": 0,
    }


def _long_term_zero() -> dict[str, Any]:
    return {
        "SaleOfEquityShareUs112A": _equity_112a_zero(),
        "NRISaleOfEquityShareUs112A": _equity_112a_zero(),
        "NRISaleofForeignAsset": {
            "SaleonSpecAsset": 0,
            "DednSpecAssetus115": 0,
            "BalonSpeciAsset": 0,
        },
        "SaleofAssetNADtls": {},
        "TotalAmtDeemedLtcg": 0,
        "PassThrIncNatureLTCG": 0,
        "TotalAmtNotTaxUsDTAALtcg": 0,
        "TotalAmtTaxUsDTAALtcg": 0,
        "TotalLTCG": 0,
    }


def _equity_112a_zero() -> dict[str, int]:
    return {"BalanceCG": 0, "DeductionUs54F": 0, "CapgainonAssets": 0}


def _current_year_losses(
    short_gain: int,
    long_gain: int,
) -> tuple[dict[str, Any], int]:
    six = {
        "StclSetoff20Per": 0,
        "StclSetoff30Per": 0,
        "StclSetoffAppRate": 0,
        "StclSetoffDTAARate": 0,
        "LtclSetOff12_5Per": 0,
        "LtclSetOffDTAARate": 0,
    }
    losses = {
        "InLossSetOff": dict(six),
        "InStcg20Per": _income_setoff(
            "StclSetoff30Per",
            "StclSetoffAppRate",
            "StclSetoffDTAARate",
        ),
        "InStcg30Per": _income_setoff(
            "StclSetoff20Per",
            "StclSetoffAppRate",
            "StclSetoffDTAARate",
        ),
        "InStcgAppRate": _income_setoff(
            "StclSetoff20Per",
            "StclSetoff30Per",
            "StclSetoffDTAARate",
        ),
        "InStcgDTAARate": _income_setoff(
            "StclSetoff20Per",
            "StclSetoff30Per",
            "StclSetoffAppRate",
        ),
        "InLtcg12_5Per": _income_setoff(
            "StclSetoff20Per",
            "StclSetoff30Per",
            "StclSetoffAppRate",
            "StclSetoffDTAARate",
            "LtclSetOffDTAARate",
        ),
        "InLtcgDTAARate": _income_setoff(
            "StclSetoff20Per",
            "StclSetoff30Per",
            "StclSetoffAppRate",
            "StclSetoffDTAARate",
            "LtclSetOff12_5Per",
        ),
        "TotLossSetOff": dict(six),
        "LossRemainSetOff": dict(six),
    }
    short_income = max(short_gain, 0)
    long_income = max(long_gain, 0)
    short_loss = max(-short_gain, 0)
    long_loss = max(-long_gain, 0)
    short_loss_to_long = min(short_loss, long_income)
    taxable_long = long_income - short_loss_to_long
    remaining_short_loss = short_loss - short_loss_to_long

    losses["InStcg20Per"]["CurrYearIncome"] = short_income
    losses["InStcg20Per"]["CurrYrCapGain"] = short_income
    losses["InLtcg12_5Per"]["CurrYearIncome"] = long_income
    losses["InLtcg12_5Per"]["StclSetoff20Per"] = short_loss_to_long
    losses["InLtcg12_5Per"]["CurrYrCapGain"] = taxable_long
    losses["InLossSetOff"]["StclSetoff20Per"] = short_loss
    losses["InLossSetOff"]["LtclSetOff12_5Per"] = long_loss
    losses["TotLossSetOff"]["StclSetoff20Per"] = short_loss_to_long
    losses["LossRemainSetOff"]["StclSetoff20Per"] = (
        remaining_short_loss
    )
    losses["LossRemainSetOff"]["LtclSetOff12_5Per"] = long_loss
    return losses, short_income + taxable_long


def _income_setoff(*fields: str) -> dict[str, int]:
    return {
        "CurrYearIncome": 0,
        **{field: 0 for field in fields},
        "CurrYrCapGain": 0,
    }


def _accrual_ranges(
    short_matches: tuple[MatchedDisposal, ...],
    long_matches: tuple[MatchedDisposal, ...],
    *,
    short_target: int,
    long_target: int,
) -> dict[str, Any]:
    zero = _date_range()
    short = _gains_by_date(short_matches, short_target)
    long = _gains_by_date(long_matches, long_target)
    return {
        "ShortTermUnder20Per": {"DateRange": short},
        "ShortTermUnder30Per": {"DateRange": dict(zero)},
        "ShortTermUnderAppRate": {"DateRange": dict(zero)},
        "ShortTermUnderDTAARate": {"DateRange": dict(zero)},
        "LongTermUnder12_5Per": {"DateRange": long},
        "LongTermUnderDTAARate": {"DateRange": dict(zero)},
    }


def _date_range() -> dict[str, int]:
    return {
        "Upto15Of6": 0,
        "Upto15Of9": 0,
        "Up16Of9To15Of12": 0,
        "Up16Of12To15Of3": 0,
        "Up16Of3To31Of3": 0,
    }


def _gains_by_date(
    matches: tuple[MatchedDisposal, ...],
    target: int,
) -> dict[str, int]:
    amounts: dict[str, Decimal] = {
        key: Decimal("0") for key in _date_range()
    }
    for match in matches:
        if match.sale_date <= date(2025, 6, 15):
            key = "Upto15Of6"
        elif match.sale_date <= date(2025, 9, 15):
            key = "Upto15Of9"
        elif match.sale_date <= date(2025, 12, 15):
            key = "Up16Of9To15Of12"
        elif match.sale_date <= date(2026, 3, 15):
            key = "Up16Of12To15Of3"
        else:
            key = "Up16Of3To31Of3"
        amounts[key] += match.gain
    positive_weights = {
        key: max(amount, Decimal("0"))
        for key, amount in amounts.items()
    }
    return _allocate_weighted_total(positive_weights, target)


def _detail_sum(details: list[dict[str, Any]], field: str) -> int:
    return sum(int(detail[field]) for detail in details)


def _allocate_match_amounts(
    keys: list[str],
    matches: tuple[MatchedDisposal, ...],
    getter: Any,
) -> dict[str, int]:
    return _allocate_rupees(
        {
            key: getter(match)
            for key, match in zip(keys, matches, strict=True)
        }
    )


def _per_unit_for_total(
    total: int,
    quantity: Decimal,
    label: str,
) -> int | float:
    per_unit = (Decimal(total) / quantity).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    product = per_unit * quantity
    if product != Decimal(total):
        raise ValueError(
            f"Schedule 112A {label} cannot satisfy whole-rupee total "
            "at four decimal places; normalize a filing-compatible row"
        )
    return _number(per_unit)


def _filing_quantity(quantity: Decimal) -> Decimal:
    emitted = quantity.quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
    if emitted != quantity:
        raise ValueError(
            "Schedule 112A quantity exceeds the official four-decimal "
            "precision; normalize a filing-compatible row"
        )
    return emitted


def _allocate_weighted_total(
    weights: Mapping[str, Decimal],
    target: int,
) -> dict[str, int]:
    if target < 0:
        raise ValueError("Accrual-range target cannot be negative")
    total_weight = _sum(weights.values())
    if target == 0:
        return {key: 0 for key in weights}
    if total_weight <= 0:
        raise ValueError(
            "Positive accrual target has no positive dated gain to allocate"
        )
    exact = {
        key: Decimal(target) * weight / total_weight
        for key, weight in weights.items()
    }
    return _allocate_rupees(exact, target=target)


def _allocate_rupees(
    amounts: Mapping[str, Decimal],
    *,
    target: int | None = None,
) -> dict[str, int]:
    if not amounts:
        if target not in (None, 0):
            raise ValueError("Cannot allocate a non-zero total without values")
        return {}
    floors = {
        key: int(value.to_integral_value(rounding=ROUND_FLOOR))
        for key, value in amounts.items()
    }
    allocated_total = (
        _rupees(_sum(amounts.values()))
        if target is None
        else target
    )
    remaining = allocated_total - sum(floors.values())
    if remaining < 0 or remaining > len(amounts):
        raise ValueError(
            "Rupee allocation target is inconsistent with source amounts"
        )
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
    return allocated


def _sum(values: Any) -> Decimal:
    return sum(values, Decimal("0"))


def _rupees(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _number(value: Decimal) -> int | float:
    rounded = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return deepcopy(value)
