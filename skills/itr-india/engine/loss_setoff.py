"""AY 2026-27 loss set-off, carry-forward, and filing schedules.

The public seam accepts source-provenanced current-year income buckets and
prior-year loss pools.  It applies current-year restrictions first, then
brought-forward restrictions oldest-first, and emits mutually cross-tied
Schedule CG, BP, CYLA, BFLA, CFL, and Part B-TI values.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from engine.bank_interest_ledger import SourceProvenance


SUPPORTED_ASSESSMENT_YEAR = "2026-27"
_CURRENT_AY_START = 2026


class IncomeBucket(StrEnum):
    SALARY = "salary"
    HOUSE_PROPERTY = "house_property"
    NON_SPECULATIVE_BUSINESS = "non_speculative_business"
    SPECULATIVE_BUSINESS = "speculative_business"
    STCG_20 = "stcg_20"
    STCG_30 = "stcg_30"
    STCG_APPLICABLE = "stcg_applicable"
    STCG_DTAA = "stcg_dtaa"
    LTCG_12_5 = "ltcg_12_5"
    LTCG_DTAA = "ltcg_dtaa"
    OTHER_SOURCES_NORMAL = "other_sources_normal"
    OTHER_SOURCES_RACE_HORSE = "other_sources_race_horse"
    OTHER_SOURCES_DTAA = "other_sources_dtaa"
    VDA_CAPITAL_115BBH = "vda_capital_115bbh"
    VDA_BUSINESS_115BBH = "vda_business_115bbh"


class LossCategory(StrEnum):
    SHORT_TERM_CAPITAL = "short_term_capital"
    LONG_TERM_CAPITAL = "long_term_capital"
    NON_SPECULATIVE_BUSINESS = "non_speculative_business"
    SPECULATIVE_BUSINESS = "speculative_business"


class ReturnTimeliness(StrEnum):
    TIMELY = "timely"
    LATE = "late"
    UNKNOWN = "unknown"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class SetOffPhase(StrEnum):
    CURRENT_CAPITAL_INTRA_HEAD = "current_capital_intra_head"
    CURRENT_BUSINESS_INTRA_HEAD = "current_business_intra_head"
    CURRENT_YEAR_INTER_HEAD = "current_year_inter_head"
    BROUGHT_FORWARD_CAPITAL = "brought_forward_capital"
    BROUGHT_FORWARD_BUSINESS = "brought_forward_business"


@dataclass(frozen=True, slots=True)
class CurrentYearAmount:
    event_id: str
    bucket: IncomeBucket
    amount: Decimal
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class PriorYearLoss:
    assessment_year: int
    category: LossCategory
    amount: Decimal | None
    filing_date: date | None
    filing_due_date: date | None
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class CurrentReturnFilingFacts:
    status: ReturnTimeliness
    evidence_reference: str
    source_provenance: SourceProvenance


@dataclass(frozen=True, slots=True)
class LossSetOffCoverage:
    current_income_status: CoverageStatus
    covered_current_income_buckets: tuple[IncomeBucket, ...]
    prior_loss_history_status: CoverageStatus
    evidence_reference: str
    source_provenance: SourceProvenance


_SHORT_CAPITAL_TARGETS = (
    IncomeBucket.STCG_20,
    IncomeBucket.STCG_30,
    IncomeBucket.STCG_APPLICABLE,
    IncomeBucket.STCG_DTAA,
    IncomeBucket.LTCG_12_5,
    IncomeBucket.LTCG_DTAA,
)
_LONG_CAPITAL_TARGETS = (
    IncomeBucket.LTCG_12_5,
    IncomeBucket.LTCG_DTAA,
)
_VDA_BUCKETS = (
    IncomeBucket.VDA_CAPITAL_115BBH,
    IncomeBucket.VDA_BUSINESS_115BBH,
)
_CURRENT_BUSINESS_TARGETS = (
    IncomeBucket.HOUSE_PROPERTY,
    IncomeBucket.STCG_20,
    IncomeBucket.STCG_30,
    IncomeBucket.STCG_APPLICABLE,
    IncomeBucket.STCG_DTAA,
    IncomeBucket.LTCG_12_5,
    IncomeBucket.LTCG_DTAA,
    IncomeBucket.OTHER_SOURCES_NORMAL,
    IncomeBucket.OTHER_SOURCES_DTAA,
)
_BROUGHT_FORWARD_BUSINESS_TARGETS = (
    IncomeBucket.NON_SPECULATIVE_BUSINESS,
    IncomeBucket.SPECULATIVE_BUSINESS,
)


@dataclass(frozen=True, slots=True)
class SetOffTargetOrder:
    current_short_term_capital: tuple[IncomeBucket, ...]
    current_long_term_capital: tuple[IncomeBucket, ...]
    current_non_speculative_business: tuple[IncomeBucket, ...]
    brought_forward_short_term_capital: tuple[IncomeBucket, ...]
    brought_forward_long_term_capital: tuple[IncomeBucket, ...]
    brought_forward_non_speculative_business: tuple[IncomeBucket, ...]

    @classmethod
    def default(cls) -> "SetOffTargetOrder":
        return cls(
            current_short_term_capital=_SHORT_CAPITAL_TARGETS,
            current_long_term_capital=_LONG_CAPITAL_TARGETS,
            current_non_speculative_business=_CURRENT_BUSINESS_TARGETS,
            brought_forward_short_term_capital=_SHORT_CAPITAL_TARGETS,
            brought_forward_long_term_capital=_LONG_CAPITAL_TARGETS,
            brought_forward_non_speculative_business=(
                _BROUGHT_FORWARD_BUSINESS_TARGETS
            ),
        )


@dataclass(frozen=True, slots=True)
class LossSetOffFacts:
    assessment_year: str
    current_year_amounts: tuple[CurrentYearAmount, ...]
    brought_forward_losses: tuple[PriorYearLoss, ...]
    current_return_filing: CurrentReturnFilingFacts | None
    target_order: SetOffTargetOrder
    coverage: LossSetOffCoverage | None


@dataclass(frozen=True, slots=True)
class LossSetOffBlocker:
    code: str
    message: str
    required_input: str
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LossSetOffAllocation:
    phase: SetOffPhase
    loss_category: LossCategory
    source_bucket: IncomeBucket | None
    target_bucket: IncomeBucket
    amount: Decimal
    origin_assessment_year: int
    rule_keys: tuple[str, ...]
    event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


@dataclass(frozen=True, slots=True)
class BroughtForwardBalance:
    assessment_year: int
    category: LossCategory
    original_amount: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class LossAuditLine:
    output_path: str
    amount: Decimal
    projected_value: int | str | None
    transformation: str
    rule_keys: tuple[str, ...]
    event_ids: tuple[str, ...]
    evidence_references: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


class LossFilingOutputOperation(StrEnum):
    SET = "set"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class LossFilingOutputDelta:
    form: str
    path: tuple[str, ...]
    projected_value: int | str | None
    context_amount: Decimal
    operation: LossFilingOutputOperation = LossFilingOutputOperation.SET

    @property
    def output_path(self) -> str:
        return f"/ITR/{self.form}/" + "/".join(self.path)


@dataclass(frozen=True, slots=True)
class LossAdjustmentSlice:
    allocations: tuple[LossSetOffAllocation, ...]
    current_source_amounts: Mapping[IncomeBucket, Decimal]
    income_before_inter_head_setoff: Mapping[IncomeBucket, Decimal]
    income_after_setoff: Mapping[IncomeBucket, Decimal]
    current_loss_remaining: Mapping[LossCategory, Decimal]
    brought_forward_remaining: tuple[BroughtForwardBalance, ...]
    disallowed_vda_losses: Mapping[IncomeBucket, Decimal]
    forfeited_current_losses: Mapping[LossCategory, Decimal]
    schedule_cg_current_year_losses: Mapping[str, Any]
    schedule_bp_current_year_business_setoff: Mapping[str, Any]
    schedule_cyla_itr2: Mapping[str, Any]
    schedule_cyla_itr3: Mapping[str, Any]
    schedule_bfla_itr2: Mapping[str, Any]
    schedule_bfla_itr3: Mapping[str, Any]
    schedule_cfl_itr2: Mapping[str, Any]
    schedule_cfl_itr3: Mapping[str, Any]
    part_b_ti: Mapping[str, int]
    output_deltas_itr2: tuple[LossFilingOutputDelta, ...]
    output_deltas_itr3: tuple[LossFilingOutputDelta, ...]
    allocation_audit_trace: tuple[LossAuditLine, ...]
    audit_trace_itr2: tuple[LossAuditLine, ...]
    audit_trace_itr3: tuple[LossAuditLine, ...]
    decision_evidence_references: tuple[str, ...]
    decision_source_provenance: tuple[SourceProvenance, ...]
    used_rule_keys: tuple[str, ...]
    has_business_activity: bool
    has_capital_activity: bool
    has_vda_activity: bool

    @property
    def audit_trace(self) -> tuple[LossAuditLine, ...]:
        return (
            *self.allocation_audit_trace,
            *self.audit_trace_itr2,
            *self.audit_trace_itr3,
        )

    @property
    def disallowed_vda_loss(self) -> Decimal:
        """Total protected VDA loss across both tax heads."""
        return sum(
            self.disallowed_vda_losses.values(),
            Decimal("0"),
        )


@dataclass(frozen=True, slots=True)
class LossSetOffAssessment:
    blockers: tuple[LossSetOffBlocker, ...]
    filing_slice: LossAdjustmentSlice | None


class LossSetOffIntegrityError(ValueError):
    """A non-overridable loss-computation invariant failed."""


@dataclass(slots=True)
class _ComputationState:
    current_source_amounts: dict[IncomeBucket, Decimal]
    initial_income: dict[IncomeBucket, Decimal]
    cyla_income: dict[IncomeBucket, Decimal]
    bfla_income: dict[IncomeBucket, Decimal]
    final_income: dict[IncomeBucket, Decimal]
    current_source_losses: dict[IncomeBucket, Decimal]
    current_loss_remaining: dict[LossCategory, Decimal]
    prior_losses: tuple[PriorYearLoss, ...]
    prior_amounts: dict[tuple[int, LossCategory], Decimal]
    prior_remaining: dict[tuple[int, LossCategory], Decimal]
    allocations: list[LossSetOffAllocation]
    disallowed_vda_losses: dict[IncomeBucket, Decimal]
    current_business_loss_after_intra_head: Decimal


_CAPITAL_SOURCE_FIELD = {
    IncomeBucket.STCG_20: "StclSetoff20Per",
    IncomeBucket.STCG_30: "StclSetoff30Per",
    IncomeBucket.STCG_APPLICABLE: "StclSetoffAppRate",
    IncomeBucket.STCG_DTAA: "StclSetoffDTAARate",
    IncomeBucket.LTCG_12_5: "LtclSetOff12_5Per",
    IncomeBucket.LTCG_DTAA: "LtclSetOffDTAARate",
}
_CAPITAL_TARGET_FIELD = {
    IncomeBucket.STCG_20: "InStcg20Per",
    IncomeBucket.STCG_30: "InStcg30Per",
    IncomeBucket.STCG_APPLICABLE: "InStcgAppRate",
    IncomeBucket.STCG_DTAA: "InStcgDTAARate",
    IncomeBucket.LTCG_12_5: "InLtcg12_5Per",
    IncomeBucket.LTCG_DTAA: "InLtcgDTAARate",
}
_CAPITAL_SOURCE_ORDER = tuple(_CAPITAL_SOURCE_FIELD)
_SHORT_SOURCE_BUCKETS = _CAPITAL_SOURCE_ORDER[:4]
_LONG_SOURCE_BUCKETS = _CAPITAL_SOURCE_ORDER[4:]

_CYLA_FIELD = {
    IncomeBucket.SALARY: "Salary",
    IncomeBucket.HOUSE_PROPERTY: "HP",
    IncomeBucket.NON_SPECULATIVE_BUSINESS: "BusProfExclSpecProf",
    IncomeBucket.SPECULATIVE_BUSINESS: "SpeculativeInc",
    IncomeBucket.STCG_20: "STCG20Per",
    IncomeBucket.STCG_30: "STCG30Per",
    IncomeBucket.STCG_APPLICABLE: "STCGAppRate",
    IncomeBucket.STCG_DTAA: "STCGDTAARate",
    IncomeBucket.LTCG_12_5: "LTCG12_5Per",
    IncomeBucket.LTCG_DTAA: "LTCGDTAARate",
    IncomeBucket.OTHER_SOURCES_NORMAL: "OthSrcExclRaceHorse",
    IncomeBucket.OTHER_SOURCES_RACE_HORSE: "OthSrcRaceHorse",
    IncomeBucket.OTHER_SOURCES_DTAA: "IncOSDTAA",
}

_ITR3_CFL_YEAR_FIELD = {
    2018: "LossCFFromPrevYrToAY",
    2019: "LossCFCurrentAssmntYear",
    2020: "LossCFCurrentAssmntYear2021",
    2021: "LossCFCurrentAssmntYear2022",
    2022: "LossCFCurrentAssmntYear2023",
    2023: "LossCFCurrentAssmntYear2024",
    2024: "LossCFCurrentAssmntYear2025",
    2025: "LossCFCurrentAssmntYear2026",
}
_ITR2_CFL_YEAR_FIELD = {
    2018: "LossCFFromPrev8thYearFromAY",
    2019: "LossCFFromPrev7thYearFromAY",
    2020: "LossCFFromPrev6thYearFromAY",
    2021: "LossCFFromPrev5thYearFromAY",
    2022: "LossCFFromPrev4thYearFromAY",
    2023: "LossCFFromPrev3rdYearFromAY",
    2024: "LossCFFromPrev2ndYearFromAY",
    2025: "LossCFFromPrevYrToAY",
}
_CFL_CATEGORY_FIELD = {
    LossCategory.SHORT_TERM_CAPITAL: "TotalSTCGPTILossCF",
    LossCategory.LONG_TERM_CAPITAL: "TotalLTCGPTILossCF",
    LossCategory.NON_SPECULATIVE_BUSINESS: "BusLossOthThanSpecLossCF",
    LossCategory.SPECULATIVE_BUSINESS: "LossFrmSpecBusCF",
}

_RULE_CURRENT_PRIORITY = "loss.current_year.priority"
_RULE_STCL = "loss.capital.short_term.targets"
_RULE_LTCL = "loss.capital.long_term.targets"
_RULE_CURRENT_BUSINESS = "loss.business.current_year.targets"
_RULE_BF_BUSINESS = "loss.business.brought_forward.targets"
_RULE_SPECULATION = "loss.speculation.targets"
_RULE_VDA = "loss.vda.no_setoff_or_carry"
_RULE_TIMELY = "loss.carry_forward.timely_return"


def assess_loss_setoff(facts: LossSetOffFacts) -> LossSetOffAssessment:
    """Assess evidence, compute loss adjustments, and fail closed on blockers."""
    _validate_integrity(facts)
    blockers = _evidence_blockers(facts)
    if blockers:
        return LossSetOffAssessment(blockers=tuple(blockers), filing_slice=None)

    economic_state = _run_setoff(facts, whole_rupees=False)
    residual = {
        category: amount
        for category, amount in economic_state.current_loss_remaining.items()
        if amount > 0
    }
    if residual and (
        facts.current_return_filing is None
        or facts.current_return_filing.status is ReturnTimeliness.UNKNOWN
    ):
        return LossSetOffAssessment(
            blockers=(
                LossSetOffBlocker(
                    code="current_return_timeliness_required",
                    message=(
                        "Current-year business/capital loss remains after "
                        "set-off, but section 139(3) timeliness is unknown."
                    ),
                    required_input=(
                        "Ask a human whether the AY 2026-27 return is or will "
                        "be filed within the section 139(1) due date."
                    ),
                ),
            ),
            filing_slice=None,
        )

    filing_state = _run_setoff(facts, whole_rupees=True)
    filing_slice = _build_slice(facts, economic_state, filing_state)
    return LossSetOffAssessment(blockers=(), filing_slice=filing_slice)


def build_loss_adjustment_itr3_draft(
    base_itr3: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
) -> dict[str, Any]:
    """Apply the complete ITR-3 loss-adjustment schedules to a base draft."""
    draft = deepcopy(dict(base_itr3))
    itr3 = _return_object(draft, "ITR3")
    _validate_loss_projection_base(itr3, filing_slice, form="ITR3")
    _prepare_owned_schedule_branches(itr3, filing_slice)
    _apply_loss_output_deltas(itr3, filing_slice.output_deltas_itr3)
    return draft


def build_loss_adjustment_itr2_draft(
    base_itr2: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
) -> dict[str, Any]:
    """Apply capital-only loss-adjustment schedules to a base ITR-2 draft."""
    if filing_slice.has_business_activity:
        raise ValueError(
            "ITR-2 cannot contain speculative or non-speculative business "
            "income/loss; use ITR-3"
        )
    draft = deepcopy(dict(base_itr2))
    itr2 = _return_object(draft, "ITR2")
    _validate_loss_projection_base(itr2, filing_slice, form="ITR2")
    _prepare_owned_schedule_branches(itr2, filing_slice)
    _apply_loss_output_deltas(itr2, filing_slice.output_deltas_itr2)
    return draft


_PART_B_SOURCE_PATH = {
    IncomeBucket.SALARY: ("Salaries",),
    IncomeBucket.HOUSE_PROPERTY: ("IncomeFromHP",),
    IncomeBucket.NON_SPECULATIVE_BUSINESS: (
        "ProfBusGain",
        "ProfGainNoSpecBus",
    ),
    IncomeBucket.SPECULATIVE_BUSINESS: (
        "ProfBusGain",
        "ProfGainSpecBus",
    ),
    IncomeBucket.STCG_20: (
        "CapGain",
        "ShortTerm",
        "ShortTerm20Per",
    ),
    IncomeBucket.STCG_30: (
        "CapGain",
        "ShortTerm",
        "ShortTerm30Per",
    ),
    IncomeBucket.STCG_APPLICABLE: (
        "CapGain",
        "ShortTerm",
        "ShortTermAppRate",
    ),
    IncomeBucket.STCG_DTAA: (
        "CapGain",
        "ShortTerm",
        "ShortTermSplRateDTAA",
    ),
    IncomeBucket.LTCG_12_5: (
        "CapGain",
        "LongTerm",
        "LongTerm12_5Per",
    ),
    IncomeBucket.LTCG_DTAA: (
        "CapGain",
        "LongTerm",
        "LongTermSplRateDTAA",
    ),
    IncomeBucket.OTHER_SOURCES_NORMAL: (
        "IncFromOS",
        "OtherSrcThanOwnRaceHorse",
    ),
    IncomeBucket.OTHER_SOURCES_RACE_HORSE: (
        "IncFromOS",
        "FromOwnRaceHorse",
    ),
    IncomeBucket.OTHER_SOURCES_DTAA: (
        "IncFromOS",
        "IncChargblSplRate",
    ),
    IncomeBucket.VDA_CAPITAL_115BBH: (
        "CapGain",
        "CapGains30Per115BBH",
    ),
    IncomeBucket.VDA_BUSINESS_115BBH: (
        "ProfBusGain",
        "ProfIncome115BBF",
    ),
}

_UNSUPPORTED_LOSS_FIELDS = {
    "TotHPlossCurYr",
    "TotHPlossCurYrSetoff",
    "BalHPlossCurYrAftSetoff",
    "TotOthSrcLossNoRaceHorse",
    "TotOthSrcLossNoRaceHorseSetoff",
    "BalOthSrcLossNoRaceHorseAftSetoff",
    "BFUnabsorbedDeprSetoff",
    "BFAllUs35Cl4Setoff",
    "TotUnabsorbedDeprSetoff",
    "TotAllUs35cl4Setoff",
    "TotalHPPTILossCF",
    "LossFrmSpecifiedBusCF",
    "OthSrcLossRaceHorseCF",
}

_SUPPORTED_BFLA_BUCKETS = {
    *(_CYLA_FIELD[bucket] for bucket in _CAPITAL_SOURCE_ORDER),
    _CYLA_FIELD[IncomeBucket.NON_SPECULATIVE_BUSINESS],
    _CYLA_FIELD[IncomeBucket.SPECULATIVE_BUSINESS],
}


def _validate_loss_projection_base(
    itr: dict[str, Any],
    filing_slice: LossAdjustmentSlice,
    *,
    form: str,
) -> None:
    part_b_ti = itr.get("PartB-TI")
    if not isinstance(part_b_ti, dict):
        raise ValueError(
            f"Base {form} must contain a PartB-TI object"
        )
    schedule_bp = itr.get("ITR3ScheduleBP")
    if form == "ITR3":
        if not isinstance(schedule_bp, dict):
            raise ValueError(
                "Base ITR3 must contain an ITR3ScheduleBP object"
            )
        _validate_schedule_bp_sources(schedule_bp, filing_slice)
    if filing_slice.has_capital_activity:
        schedule_cg = itr.get("ScheduleCGFor23")
        if not isinstance(schedule_cg, dict):
            raise ValueError(
                f"Base {form} must contain a ScheduleCGFor23 object when "
                "capital facts exist"
            )
        _validate_schedule_cg_sources(schedule_cg, filing_slice, form)
    if filing_slice.has_vda_activity:
        schedule_vda = itr.get("ScheduleVDA")
        if not isinstance(schedule_vda, dict):
            raise ValueError(
                f"Base {form} must contain a ScheduleVDA object when "
                "VDA facts exist"
            )
        _validate_schedule_vda_sources(
            schedule_vda,
            filing_slice,
            form,
        )
    _reject_unsupported_loss_values(itr, filing_slice, form)
    _validate_part_b_source_income(part_b_ti, filing_slice, form)


def _validate_schedule_cg_sources(
    schedule_cg: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
    form: str,
) -> None:
    matrix = filing_slice.schedule_cg_current_year_losses
    initial = matrix["InLossSetOff"]
    raw_short = sum(
        (
            int(matrix[_CAPITAL_TARGET_FIELD[bucket]]["CurrYearIncome"])
            - int(initial[_CAPITAL_SOURCE_FIELD[bucket]])
            for bucket in _SHORT_SOURCE_BUCKETS
        ),
        0,
    )
    raw_long = sum(
        (
            int(matrix[_CAPITAL_TARGET_FIELD[bucket]]["CurrYearIncome"])
            - int(initial[_CAPITAL_SOURCE_FIELD[bucket]])
            for bucket in _LONG_SOURCE_BUCKETS
        ),
        0,
    )
    capital_income = sum(
        (
            _integer(
                filing_slice.income_before_inter_head_setoff[bucket]
            )
            for bucket in _CAPITAL_SOURCE_ORDER
        ),
        0,
    )
    vda_income = _integer(
        filing_slice.income_before_inter_head_setoff[
            IncomeBucket.VDA_CAPITAL_115BBH
        ]
    )
    expected = (
        (("ShortTermCapGainFor23", "TotalSTCG"), raw_short),
        (("LongTermCapGain23", "TotalLTCG"), raw_long),
        (("SumOfCGIncm",), capital_income),
        (("IncmFromVDATrnsf",), vda_income),
        (("TotScheduleCGFor23",), capital_income + vda_income),
    )
    for path, amount in expected:
        actual = _projection_value(schedule_cg, path, form)
        if actual != amount:
            joined = "/".join(path)
            raise ValueError(
                f"{form} ScheduleCGFor23 source-income mismatch at "
                f"{joined}: expected {amount}, found {actual}"
            )


def _validate_schedule_vda_sources(
    schedule_vda: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
    form: str,
) -> None:
    income = filing_slice.income_before_inter_head_setoff
    expected = [
        (
            ("TotIncCapGain",),
            _integer(income[IncomeBucket.VDA_CAPITAL_115BBH]),
        )
    ]
    if form == "ITR3":
        expected.append(
            (
                ("TotIncBusiness",),
                _integer(income[IncomeBucket.VDA_BUSINESS_115BBH]),
            )
        )
    for path, amount in expected:
        actual = _projection_value(schedule_vda, path, form)
        if actual != amount:
            joined = "/".join(path)
            raise ValueError(
                f"{form} ScheduleVDA source-income mismatch at {joined}: "
                f"expected {amount}, found {actual}"
            )


def _validate_schedule_bp_sources(
    schedule_bp: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
) -> None:
    source = filing_slice.current_source_amounts
    non_speculative = _integer(
        source[IncomeBucket.NON_SPECULATIVE_BUSINESS]
    )
    speculative = _integer(
        source[IncomeBucket.SPECULATIVE_BUSINESS]
    )
    business_vda = _integer(
        source[IncomeBucket.VDA_BUSINESS_115BBH]
    )
    expected = (
        (
            ("BusinessIncOthThanSpec", "IncomeOtherThanRule"),
            non_speculative,
        ),
        (
            (
                "BusinessIncOthThanSpec",
                "IncRecCredPLOthHeadDtls",
                "115BBH",
            ),
            business_vda,
        ),
        (
            ("SpecBusinessInc", "AdjustedPLFrmSpecuBus"),
            speculative,
        ),
        (
            ("IncChrgUnHdProftGain",),
            non_speculative + speculative,
        ),
        (
            ("BusSetoffCurrYr", "LossSetOffOnBusLoss"),
            max(-non_speculative, 0),
        ),
    )
    for path, amount in expected:
        actual = _projection_value(schedule_bp, path, "ITR3")
        if actual != amount:
            joined = "/".join(path)
            raise ValueError(
                "ITR3 ScheduleBP source-income mismatch at "
                f"{joined}: expected {amount}, found {actual}"
            )


def _validate_part_b_source_income(
    part_b_ti: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
    form: str,
) -> None:
    income = filing_slice.income_before_inter_head_setoff
    expected: list[tuple[tuple[str, ...], int]] = []
    for bucket, path in _PART_B_SOURCE_PATH.items():
        if form == "ITR2" and bucket in {
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
            IncomeBucket.VDA_BUSINESS_115BBH,
        }:
            continue
        expected.append((path, _integer(income[bucket])))

    short = sum(
        _integer(income[bucket])
        for bucket in _SHORT_SOURCE_BUCKETS
    )
    long = sum(
        _integer(income[bucket])
        for bucket in _LONG_SOURCE_BUCKETS
    )
    capital_vda = _integer(
        income[IncomeBucket.VDA_CAPITAL_115BBH]
    )
    expected.extend(
        (
            (("CapGain", "ShortTerm", "TotalShortTerm"), short),
            (("CapGain", "LongTerm", "TotalLongTerm"), long),
            (("CapGain", "ShortTermLongTermTotal"), short + long),
            (
                ("CapGain", "TotalCapGains"),
                short + long + capital_vda,
            ),
            (
                ("IncFromOS", "TotIncFromOS"),
                sum(
                    _integer(income[bucket])
                    for bucket in (
                        IncomeBucket.OTHER_SOURCES_NORMAL,
                        IncomeBucket.OTHER_SOURCES_RACE_HORSE,
                        IncomeBucket.OTHER_SOURCES_DTAA,
                    )
                ),
            ),
        )
    )
    if form == "ITR3":
        expected.append(
            (
                ("ProfBusGain", "TotProfBusGain"),
                _integer(
                    income[IncomeBucket.NON_SPECULATIVE_BUSINESS]
                    + income[IncomeBucket.SPECULATIVE_BUSINESS]
                    + income[IncomeBucket.VDA_BUSINESS_115BBH]
                ),
            )
        )
    for path, amount in expected:
        actual = _projection_value(part_b_ti, path, form)
        if actual != amount:
            joined = "/".join(path)
            raise ValueError(
                f"{form} PartB-TI source-income mismatch at {joined}: "
                f"expected {amount}, found {actual}"
            )


def _projection_value(
    value: Mapping[str, Any],
    path: tuple[str, ...],
    form: str,
) -> int:
    current: Any = value
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            raise ValueError(
                f"Base {form} is missing required source-income field "
                f"{'/'.join(path)}"
            )
        current = current[component]
    if not isinstance(current, int):
        raise ValueError(
            f"Base {form} source-income field {'/'.join(path)} must be "
            "an integer"
        )
    return current


def _reject_unsupported_loss_values(
    itr: Mapping[str, Any],
    filing_slice: LossAdjustmentSlice,
    form: str,
) -> None:
    deltas = (
        filing_slice.output_deltas_itr2
        if form == "ITR2"
        else filing_slice.output_deltas_itr3
    )
    generated_paths = {
        delta.path
        for delta in deltas
        if delta.operation is LossFilingOutputOperation.SET
    }
    unsupported_paths: list[str] = []
    for schedule_name in ("ScheduleCYLA", "ScheduleBFLA", "ScheduleCFL"):
        schedule = itr.get(schedule_name)
        if schedule is None:
            continue
        if not isinstance(schedule, Mapping):
            raise ValueError(f"Base {schedule_name} must be an object")
        for path, value in _leaf_values(schedule, (schedule_name,)):
            field = path[-1]
            unsupported = field in _UNSUPPORTED_LOSS_FIELDS
            if field == "BFlossPrevYrUndSameHeadSetoff":
                unsupported = len(path) < 2 or path[1] not in (
                    _SUPPORTED_BFLA_BUCKETS
                )
            if path not in generated_paths:
                unsupported = True
            if unsupported and value not in (0, Decimal("0")):
                unsupported_paths.append("/".join(path))
    if unsupported_paths:
        raise ValueError(
            "Base return contains nonzero unsupported loss branches: "
            + ", ".join(sorted(unsupported_paths))
        )


def _leaf_values(
    value: Any,
    path: tuple[str, ...],
) -> tuple[tuple[tuple[str, ...], Any], ...]:
    if isinstance(value, Mapping):
        return tuple(
            leaf
            for key, item in value.items()
            for leaf in _leaf_values(item, (*path, key))
        )
    if isinstance(value, (list, tuple)):
        return tuple(
            leaf
            for index, item in enumerate(value)
            for leaf in _leaf_values(item, (*path, str(index)))
        )
    return ((path, value),)


def _prepare_owned_schedule_branches(
    itr: dict[str, Any],
    filing_slice: LossAdjustmentSlice,
) -> None:
    for schedule_name in ("ScheduleCYLA", "ScheduleBFLA", "ScheduleCFL"):
        itr[schedule_name] = {}
    if filing_slice.has_capital_activity:
        schedule_cg = itr["ScheduleCGFor23"]
        schedule_cg["CurrYrLosses"] = {}
    schedule_bp = itr.get("ITR3ScheduleBP")
    if isinstance(schedule_bp, dict):
        schedule_bp["BusSetoffCurrYr"] = {}


def _apply_loss_output_deltas(
    itr: dict[str, Any],
    deltas: tuple[LossFilingOutputDelta, ...],
) -> None:
    for delta in deltas:
        parent = itr
        for component in delta.path[:-1]:
            if (
                delta.operation is LossFilingOutputOperation.REMOVE
                and component not in parent
            ):
                parent = {}
                break
            child = parent.setdefault(component, {})
            if not isinstance(child, dict):
                raise ValueError(
                    "Loss filing output path is not an object: "
                    f"{'/'.join(delta.path)}"
                )
            parent = child
        if delta.operation is LossFilingOutputOperation.REMOVE:
            parent.pop(delta.path[-1], None)
        else:
            parent[delta.path[-1]] = deepcopy(delta.projected_value)


def _validate_integrity(facts: LossSetOffFacts) -> None:
    if facts.assessment_year != SUPPORTED_ASSESSMENT_YEAR:
        raise LossSetOffIntegrityError(
            f"Loss engine supports only AY {SUPPORTED_ASSESSMENT_YEAR}"
        )
    _validate_target_order(facts.target_order)
    event_ids = [item.event_id for item in facts.current_year_amounts]
    if any(not event_id for event_id in event_ids):
        raise LossSetOffIntegrityError("Current-year event_id cannot be empty")
    if len(event_ids) != len(set(event_ids)):
        raise LossSetOffIntegrityError(
            "Duplicate current-year event_id would double count income/loss"
        )
    for item in facts.current_year_amounts:
        if not isinstance(item.bucket, IncomeBucket):
            raise LossSetOffIntegrityError(
                f"Unknown current-year income bucket: {item.bucket!r}"
            )
        if not item.amount.is_finite():
            raise LossSetOffIntegrityError(
                f"Current-year amount {item.event_id!r} is not finite"
            )
    prior_keys = [
        (item.assessment_year, item.category)
        for item in facts.brought_forward_losses
    ]
    if len(prior_keys) != len(set(prior_keys)):
        raise LossSetOffIntegrityError(
            "Prior-year loss pools must be unique by assessment year/category"
        )
    for item in facts.brought_forward_losses:
        if not isinstance(item.category, LossCategory):
            raise LossSetOffIntegrityError(
                f"Unknown prior-year loss category: {item.category!r}"
            )
        if item.assessment_year >= _CURRENT_AY_START:
            raise LossSetOffIntegrityError(
                "Brought-forward loss assessment year must precede AY 2026-27"
            )
        if item.amount is not None and (
            not item.amount.is_finite() or item.amount <= 0
        ):
            raise LossSetOffIntegrityError(
                "Prior-year loss amount must be a positive finite value"
            )
    dates_by_year: dict[int, set[date]] = defaultdict(set)
    for item in facts.brought_forward_losses:
        if item.filing_date is not None:
            dates_by_year[item.assessment_year].add(item.filing_date)
    conflict_years = [
        assessment_year
        for assessment_year, dates in dates_by_year.items()
        if len(dates) > 1
    ]
    if conflict_years:
        raise LossSetOffIntegrityError(
            "Prior loss pools for one assessment year have conflicting "
            f"return filing dates: {conflict_years}"
        )
    if facts.current_return_filing is not None and not isinstance(
        facts.current_return_filing.status,
        ReturnTimeliness,
    ):
        raise LossSetOffIntegrityError(
            "Current return timeliness must use ReturnTimeliness"
        )
    if facts.coverage is not None:
        if not isinstance(
            facts.coverage.current_income_status,
            CoverageStatus,
        ) or not isinstance(
            facts.coverage.prior_loss_history_status,
            CoverageStatus,
        ):
            raise LossSetOffIntegrityError(
                "Loss coverage statuses must use CoverageStatus"
            )
        if any(
            not isinstance(bucket, IncomeBucket)
            for bucket in facts.coverage.covered_current_income_buckets
        ):
            raise LossSetOffIntegrityError(
                "Loss coverage contains an unknown income bucket"
            )
        if len(facts.coverage.covered_current_income_buckets) != len(
            set(facts.coverage.covered_current_income_buckets)
        ):
            raise LossSetOffIntegrityError(
                "Loss coverage contains duplicate income buckets"
            )


def _validate_target_order(order: SetOffTargetOrder) -> None:
    expected = {
        "current_short_term_capital": _SHORT_CAPITAL_TARGETS,
        "current_long_term_capital": _LONG_CAPITAL_TARGETS,
        "current_non_speculative_business": _CURRENT_BUSINESS_TARGETS,
        "brought_forward_short_term_capital": _SHORT_CAPITAL_TARGETS,
        "brought_forward_long_term_capital": _LONG_CAPITAL_TARGETS,
        "brought_forward_non_speculative_business": (
            _BROUGHT_FORWARD_BUSINESS_TARGETS
        ),
    }
    for field_name, eligible in expected.items():
        supplied = getattr(order, field_name)
        if len(supplied) != len(set(supplied)) or set(supplied) != set(eligible):
            raise LossSetOffIntegrityError(
                f"{field_name} must be an exhaustive permutation of every "
                "eligible target; a target cannot be skipped silently"
            )


def _evidence_blockers(facts: LossSetOffFacts) -> list[LossSetOffBlocker]:
    blockers: list[LossSetOffBlocker] = []
    coverage = facts.coverage
    if coverage is None or (
        coverage.current_income_status is not CoverageStatus.COMPLETE
        or set(coverage.covered_current_income_buckets) != set(IncomeBucket)
    ):
        blockers.append(
            LossSetOffBlocker(
                code="current_income_coverage_incomplete",
                message=(
                    "The loss computation does not establish complete "
                    "coverage of every supported current-year income bucket."
                ),
                required_input=(
                    "Ask a human to confirm every supported income bucket, "
                    "including explicit zero/none categories."
                ),
            )
        )
    if coverage is None or (
        coverage.prior_loss_history_status is not CoverageStatus.COMPLETE
    ):
        blockers.append(
            LossSetOffBlocker(
                code="prior_loss_history_coverage_required",
                message=(
                    "The complete prior-year loss history has not been "
                    "confirmed."
                ),
                required_input=(
                    "Ask a human to confirm the latest Schedule CFL history "
                    "is complete, including an explicit no-prior-loss answer."
                ),
            )
        )
    if coverage is not None and (
        not coverage.evidence_reference
        or not isinstance(coverage.source_provenance, SourceProvenance)
    ):
        blockers.append(
            LossSetOffBlocker(
                code="loss_coverage_evidence_missing",
                message="Loss input coverage lacks its human evidence record.",
                required_input=(
                    "Provide the coverage attestation and source provenance."
                ),
            )
        )
    allowed_negative = {
        *_CAPITAL_SOURCE_ORDER,
        IncomeBucket.NON_SPECULATIVE_BUSINESS,
        IncomeBucket.SPECULATIVE_BUSINESS,
        *_VDA_BUCKETS,
    }
    for item in facts.current_year_amounts:
        if not item.evidence_references:
            blockers.append(
                LossSetOffBlocker(
                    code="current_amount_evidence_missing",
                    message=f"{item.event_id} has no evidence reference.",
                    required_input="Provide the source evidence reference.",
                )
            )
        if not item.source_provenance:
            blockers.append(
                LossSetOffBlocker(
                    code="current_amount_provenance_missing",
                    message=f"{item.event_id} has no source provenance.",
                    required_input="Provide source provenance for the amount.",
                    evidence_references=item.evidence_references,
                )
            )
        if item.amount < 0 and item.bucket not in allowed_negative:
            blockers.append(
                LossSetOffBlocker(
                    code="unsupported_current_loss_bucket",
                    message=(
                        f"Negative {item.bucket.value} is not supported by "
                        "this loss engine."
                    ),
                    required_input=(
                        "Ask a human to classify and support the loss under a "
                        "covered statutory category."
                    ),
                    evidence_references=item.evidence_references,
                )
            )
    for item in facts.brought_forward_losses:
        label = f"AY {item.assessment_year}-{str(item.assessment_year + 1)[-2:]}"
        if item.amount is None:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_amount_missing",
                    message=f"{label} {item.category.value} amount is missing.",
                    required_input="Provide the loss balance from Schedule CFL.",
                )
            )
        if item.filing_date is None:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_filing_date_missing",
                    message=f"{label} return filing date is missing.",
                    required_input=(
                        "Provide the prior return acknowledgement filing date."
                    ),
                )
            )
        if item.filing_due_date is None:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_due_date_missing",
                    message=f"{label} section 139(1) due date is missing.",
                    required_input=(
                        "Provide the applicable due date for the prior return."
                    ),
                )
            )
        if not item.evidence_references:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_evidence_missing",
                    message=f"{label} loss has no Schedule CFL evidence.",
                    required_input=(
                        "Provide the prior ITR/Schedule CFL or assessment record."
                    ),
                )
            )
        if not item.source_provenance:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_provenance_missing",
                    message=f"{label} loss evidence has no source provenance.",
                    required_input="Provide provenance for the prior loss record.",
                    evidence_references=item.evidence_references,
                )
            )
        if (
            item.filing_date is not None
            and item.filing_due_date is not None
            and item.filing_date > item.filing_due_date
        ):
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_return_late",
                    message=(
                        f"{label} loss return was filed after the supplied "
                        "section 139(1) due date."
                    ),
                    required_input=(
                        "Ask a human for corrected timeliness evidence or "
                        "remove the unsupported carry-forward claim."
                    ),
                    evidence_references=item.evidence_references,
                )
            )
        horizon = (
            4
            if item.category is LossCategory.SPECULATIVE_BUSINESS
            else 8
        )
        if _CURRENT_AY_START - item.assessment_year > horizon:
            blockers.append(
                LossSetOffBlocker(
                    code="prior_loss_expired",
                    message=(
                        f"{label} {item.category.value} is outside its "
                        f"{horizon}-assessment-year set-off window."
                    ),
                    required_input=(
                        "Ask a human to remove the expired pool or provide a "
                        "supported statutory exception."
                    ),
                    evidence_references=item.evidence_references,
                )
            )
    filing = facts.current_return_filing
    if filing is not None:
        if not filing.evidence_reference:
            blockers.append(
                LossSetOffBlocker(
                    code="current_return_filing_evidence_missing",
                    message="Current return timeliness has no evidence reference.",
                    required_input="Provide the human filing-status attestation.",
                )
            )
        if not isinstance(filing.source_provenance, SourceProvenance):
            blockers.append(
                LossSetOffBlocker(
                    code="current_return_filing_provenance_missing",
                    message=(
                        "Current return timeliness has no source provenance."
                    ),
                    required_input=(
                        "Provide provenance for the human filing-status "
                        "attestation."
                    ),
                    evidence_references=(
                        (filing.evidence_reference,)
                        if filing.evidence_reference
                        else ()
                    ),
                )
            )
    return blockers


def _run_setoff(
    facts: LossSetOffFacts,
    *,
    whole_rupees: bool,
) -> _ComputationState:
    aggregate = {bucket: Decimal("0") for bucket in IncomeBucket}
    vda_income = {
        bucket: Decimal("0")
        for bucket in _VDA_BUCKETS
    }
    vda_loss = {
        bucket: Decimal("0")
        for bucket in _VDA_BUCKETS
    }
    rows_by_bucket: dict[IncomeBucket, list[CurrentYearAmount]] = defaultdict(list)
    for item in facts.current_year_amounts:
        rows_by_bucket[item.bucket].append(item)
        if item.bucket in _VDA_BUCKETS:
            if item.amount >= 0:
                vda_income[item.bucket] += item.amount
            else:
                vda_loss[item.bucket] += -item.amount
        else:
            aggregate[item.bucket] += item.amount
    if whole_rupees:
        aggregate = {
            bucket: _rupees(amount)
            for bucket, amount in aggregate.items()
        }
        vda_income = {
            bucket: _rupees(amount)
            for bucket, amount in vda_income.items()
        }
        vda_loss = {
            bucket: _rupees(amount)
            for bucket, amount in vda_loss.items()
        }

    current_source_amounts = dict(aggregate)
    current_source_amounts.update(vda_income)
    initial_income = {
        bucket: max(amount, Decimal("0"))
        for bucket, amount in aggregate.items()
    }
    initial_income.update(vda_income)
    incomes = dict(initial_income)
    source_losses = {
        bucket: max(-aggregate[bucket], Decimal("0"))
        for bucket in (
            *_CAPITAL_SOURCE_ORDER,
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
        )
    }
    allocations: list[LossSetOffAllocation] = []

    for source_bucket in _LONG_SOURCE_BUCKETS:
        _allocate_current(
            amount=source_losses[source_bucket],
            source_bucket=source_bucket,
            category=LossCategory.LONG_TERM_CAPITAL,
            targets=facts.target_order.current_long_term_capital,
            incomes=incomes,
            allocations=allocations,
            rows_by_bucket=rows_by_bucket,
            phase=SetOffPhase.CURRENT_CAPITAL_INTRA_HEAD,
            rule_keys=(_RULE_CURRENT_PRIORITY, _RULE_LTCL),
        )
    for source_bucket in _SHORT_SOURCE_BUCKETS:
        _allocate_current(
            amount=source_losses[source_bucket],
            source_bucket=source_bucket,
            category=LossCategory.SHORT_TERM_CAPITAL,
            targets=facts.target_order.current_short_term_capital,
            incomes=incomes,
            allocations=allocations,
            rows_by_bucket=rows_by_bucket,
            phase=SetOffPhase.CURRENT_CAPITAL_INTRA_HEAD,
            rule_keys=(_RULE_CURRENT_PRIORITY, _RULE_STCL),
        )

    non_spec_loss = source_losses[IncomeBucket.NON_SPECULATIVE_BUSINESS]
    intra_used = _allocate_current(
        amount=non_spec_loss,
        source_bucket=IncomeBucket.NON_SPECULATIVE_BUSINESS,
        category=LossCategory.NON_SPECULATIVE_BUSINESS,
        targets=(IncomeBucket.SPECULATIVE_BUSINESS,),
        incomes=incomes,
        allocations=allocations,
        rows_by_bucket=rows_by_bucket,
        phase=SetOffPhase.CURRENT_BUSINESS_INTRA_HEAD,
        rule_keys=(_RULE_CURRENT_PRIORITY, _RULE_CURRENT_BUSINESS),
    )
    business_after_intra = non_spec_loss - intra_used
    cyla_income = dict(incomes)
    inter_used = _allocate_current(
        amount=business_after_intra,
        source_bucket=IncomeBucket.NON_SPECULATIVE_BUSINESS,
        category=LossCategory.NON_SPECULATIVE_BUSINESS,
        targets=facts.target_order.current_non_speculative_business,
        incomes=incomes,
        allocations=allocations,
        rows_by_bucket=rows_by_bucket,
        phase=SetOffPhase.CURRENT_YEAR_INTER_HEAD,
        rule_keys=(_RULE_CURRENT_PRIORITY, _RULE_CURRENT_BUSINESS),
    )
    current_business_remaining = business_after_intra - inter_used
    bfla_income = dict(incomes)

    prior_amounts: dict[tuple[int, LossCategory], Decimal] = {}
    prior_remaining: dict[tuple[int, LossCategory], Decimal] = {}
    for item in facts.brought_forward_losses:
        assert item.amount is not None
        amount = _rupees(item.amount) if whole_rupees else item.amount
        key = (item.assessment_year, item.category)
        prior_amounts[key] = amount
        prior_remaining[key] = amount

    for category, targets, rule_keys in (
        (
            LossCategory.SPECULATIVE_BUSINESS,
            (IncomeBucket.SPECULATIVE_BUSINESS,),
            (_RULE_SPECULATION, _RULE_TIMELY),
        ),
        (
            LossCategory.NON_SPECULATIVE_BUSINESS,
            facts.target_order.brought_forward_non_speculative_business,
            (_RULE_BF_BUSINESS, _RULE_TIMELY),
        ),
        (
            LossCategory.LONG_TERM_CAPITAL,
            facts.target_order.brought_forward_long_term_capital,
            (_RULE_LTCL, _RULE_TIMELY),
        ),
        (
            LossCategory.SHORT_TERM_CAPITAL,
            facts.target_order.brought_forward_short_term_capital,
            (_RULE_STCL, _RULE_TIMELY),
        ),
    ):
        for prior in sorted(
            (
                item
                for item in facts.brought_forward_losses
                if item.category is category
            ),
            key=lambda item: item.assessment_year,
        ):
            key = (prior.assessment_year, prior.category)
            used = _allocate_prior(
                prior=prior,
                amount=prior_remaining[key],
                targets=targets,
                incomes=incomes,
                allocations=allocations,
                phase=(
                    SetOffPhase.BROUGHT_FORWARD_CAPITAL
                    if category
                    in {
                        LossCategory.SHORT_TERM_CAPITAL,
                        LossCategory.LONG_TERM_CAPITAL,
                    }
                    else SetOffPhase.BROUGHT_FORWARD_BUSINESS
                ),
                rule_keys=rule_keys,
            )
            prior_remaining[key] -= used

    current_loss_remaining = {
        LossCategory.SHORT_TERM_CAPITAL: sum(
            (
                source_losses[bucket]
                - _current_allocated_from(allocations, bucket)
                for bucket in _SHORT_SOURCE_BUCKETS
            ),
            Decimal("0"),
        ),
        LossCategory.LONG_TERM_CAPITAL: sum(
            (
                source_losses[bucket]
                - _current_allocated_from(allocations, bucket)
                for bucket in _LONG_SOURCE_BUCKETS
            ),
            Decimal("0"),
        ),
        LossCategory.NON_SPECULATIVE_BUSINESS: (
            current_business_remaining
        ),
        LossCategory.SPECULATIVE_BUSINESS: source_losses[
            IncomeBucket.SPECULATIVE_BUSINESS
        ],
    }
    return _ComputationState(
        current_source_amounts=current_source_amounts,
        initial_income=initial_income,
        cyla_income=cyla_income,
        bfla_income=bfla_income,
        final_income=dict(incomes),
        current_source_losses=source_losses,
        current_loss_remaining=current_loss_remaining,
        prior_losses=facts.brought_forward_losses,
        prior_amounts=prior_amounts,
        prior_remaining=prior_remaining,
        allocations=allocations,
        disallowed_vda_losses=vda_loss,
        current_business_loss_after_intra_head=business_after_intra,
    )


def _allocate_current(
    *,
    amount: Decimal,
    source_bucket: IncomeBucket,
    category: LossCategory,
    targets: tuple[IncomeBucket, ...],
    incomes: dict[IncomeBucket, Decimal],
    allocations: list[LossSetOffAllocation],
    rows_by_bucket: Mapping[IncomeBucket, list[CurrentYearAmount]],
    phase: SetOffPhase,
    rule_keys: tuple[str, ...],
) -> Decimal:
    remaining = amount
    source_rows = rows_by_bucket.get(source_bucket, [])
    for target in targets:
        used = min(remaining, incomes[target])
        if used <= 0:
            continue
        incomes[target] -= used
        allocations.append(
            LossSetOffAllocation(
                phase=phase,
                loss_category=category,
                source_bucket=source_bucket,
                target_bucket=target,
                amount=used,
                origin_assessment_year=_CURRENT_AY_START,
                rule_keys=rule_keys,
                event_ids=tuple(sorted(row.event_id for row in source_rows)),
                evidence_references=tuple(
                    sorted(
                        {
                            reference
                            for row in source_rows
                            for reference in row.evidence_references
                        }
                    )
                ),
                source_provenance=_unique_provenance(
                    provenance
                    for row in source_rows
                    for provenance in row.source_provenance
                ),
            )
        )
        remaining -= used
        if remaining == 0:
            break
    return amount - remaining


def _allocate_prior(
    *,
    prior: PriorYearLoss,
    amount: Decimal,
    targets: tuple[IncomeBucket, ...],
    incomes: dict[IncomeBucket, Decimal],
    allocations: list[LossSetOffAllocation],
    phase: SetOffPhase,
    rule_keys: tuple[str, ...],
) -> Decimal:
    remaining = amount
    for target in targets:
        used = min(remaining, incomes[target])
        if used <= 0:
            continue
        incomes[target] -= used
        allocations.append(
            LossSetOffAllocation(
                phase=phase,
                loss_category=prior.category,
                source_bucket=None,
                target_bucket=target,
                amount=used,
                origin_assessment_year=prior.assessment_year,
                rule_keys=rule_keys,
                event_ids=(),
                evidence_references=prior.evidence_references,
                source_provenance=_unique_provenance(
                    prior.source_provenance
                ),
            )
        )
        remaining -= used
        if remaining == 0:
            break
    return amount - remaining


def _current_allocated_from(
    allocations: list[LossSetOffAllocation],
    source_bucket: IncomeBucket,
) -> Decimal:
    return sum(
        (
            allocation.amount
            for allocation in allocations
            if allocation.origin_assessment_year == _CURRENT_AY_START
            and allocation.source_bucket is source_bucket
        ),
        Decimal("0"),
    )


def _build_slice(
    facts: LossSetOffFacts,
    economic: _ComputationState,
    filing: _ComputationState,
) -> LossAdjustmentSlice:
    filing_status = (
        facts.current_return_filing.status
        if facts.current_return_filing is not None
        else ReturnTimeliness.UNKNOWN
    )
    if filing_status is ReturnTimeliness.LATE:
        forfeited = {
            category: amount
            for category, amount in economic.current_loss_remaining.items()
            if amount > 0
        }
    else:
        forfeited = {}
    carryable_filing = (
        {
            category: Decimal("0")
            for category in LossCategory
        }
        if filing_status is ReturnTimeliness.LATE
        else filing.current_loss_remaining
    )

    schedule_cg = _schedule_cg_current_losses(filing)
    schedule_bp = _schedule_bp_current_business(filing)
    schedule_cyla_itr3 = _schedule_cyla(filing, form="ITR-3")
    schedule_cyla_itr2 = _schedule_cyla(filing, form="ITR-2")
    schedule_bfla_itr3 = _schedule_bfla(filing, form="ITR-3")
    schedule_bfla_itr2 = _schedule_bfla(filing, form="ITR-2")
    schedule_cfl_itr3 = _schedule_cfl(
        filing,
        carryable_filing,
        form="ITR-3",
    )
    schedule_cfl_itr2 = _schedule_cfl(
        filing,
        carryable_filing,
        form="ITR-2",
    )
    part_b_ti = _part_b_ti(filing, carryable_filing)
    business_activity = any(
        item.bucket
        in {
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
            IncomeBucket.VDA_BUSINESS_115BBH,
        }
        and item.amount != 0
        for item in facts.current_year_amounts
    ) or any(
        item.category
        in {
            LossCategory.NON_SPECULATIVE_BUSINESS,
            LossCategory.SPECULATIVE_BUSINESS,
        }
        for item in facts.brought_forward_losses
    )
    capital_activity = any(
        item.bucket
        in {
            *_CAPITAL_SOURCE_ORDER,
            IncomeBucket.VDA_CAPITAL_115BBH,
        }
        and item.amount != 0
        for item in facts.current_year_amounts
    ) or any(
        item.category
        in {
            LossCategory.SHORT_TERM_CAPITAL,
            LossCategory.LONG_TERM_CAPITAL,
        }
        for item in facts.brought_forward_losses
    )
    vda_activity = any(
        item.bucket in _VDA_BUCKETS and item.amount != 0
        for item in facts.current_year_amounts
    )
    used_rule_keys = {
        rule_key
        for allocation in economic.allocations
        for rule_key in allocation.rule_keys
    }
    used_rule_keys.update(_rule_keys_for_facts(facts))
    if any(economic.current_loss_remaining.values()) or facts.brought_forward_losses:
        used_rule_keys.add(_RULE_TIMELY)
    output_deltas_itr2 = _filing_output_deltas(
        form="ITR2",
        has_capital_activity=capital_activity,
        schedule_cg=schedule_cg,
        schedule_bp=None,
        schedule_cyla=schedule_cyla_itr2,
        schedule_bfla=schedule_bfla_itr2,
        schedule_cfl=schedule_cfl_itr2,
        part_b_ti=part_b_ti,
    )
    output_deltas_itr3 = _filing_output_deltas(
        form="ITR3",
        has_capital_activity=capital_activity,
        schedule_cg=schedule_cg,
        schedule_bp=schedule_bp,
        schedule_cyla=schedule_cyla_itr3,
        schedule_bfla=schedule_bfla_itr3,
        schedule_cfl=schedule_cfl_itr3,
        part_b_ti=part_b_ti,
    )
    decision_references, decision_provenance = _decision_evidence(facts)
    all_references, all_provenance = _all_evidence(facts)
    allocation_trace = _allocation_audit_trace(economic)
    audit_trace_itr2 = _filing_audit_trace(
        facts,
        economic,
        output_deltas_itr2,
        all_references,
        all_provenance,
    )
    audit_trace_itr3 = _filing_audit_trace(
        facts,
        economic,
        output_deltas_itr3,
        all_references,
        all_provenance,
    )
    return LossAdjustmentSlice(
        allocations=tuple(economic.allocations),
        current_source_amounts=_freeze(filing.current_source_amounts),
        income_before_inter_head_setoff=_freeze(filing.cyla_income),
        income_after_setoff=_freeze(economic.final_income),
        current_loss_remaining=_freeze(economic.current_loss_remaining),
        brought_forward_remaining=tuple(
            BroughtForwardBalance(
                assessment_year=assessment_year,
                category=category,
                original_amount=economic.prior_amounts[
                    (assessment_year, category)
                ],
                amount=amount,
            )
            for (assessment_year, category), amount in sorted(
                economic.prior_remaining.items(),
                key=lambda item: (item[0][0], item[0][1].value),
            )
        ),
        disallowed_vda_losses=_freeze(
            economic.disallowed_vda_losses
        ),
        forfeited_current_losses=_freeze(forfeited),
        schedule_cg_current_year_losses=_freeze(schedule_cg),
        schedule_bp_current_year_business_setoff=_freeze(schedule_bp),
        schedule_cyla_itr2=_freeze(schedule_cyla_itr2),
        schedule_cyla_itr3=_freeze(schedule_cyla_itr3),
        schedule_bfla_itr2=_freeze(schedule_bfla_itr2),
        schedule_bfla_itr3=_freeze(schedule_bfla_itr3),
        schedule_cfl_itr2=_freeze(schedule_cfl_itr2),
        schedule_cfl_itr3=_freeze(schedule_cfl_itr3),
        part_b_ti=_freeze(part_b_ti),
        output_deltas_itr2=output_deltas_itr2,
        output_deltas_itr3=output_deltas_itr3,
        allocation_audit_trace=allocation_trace,
        audit_trace_itr2=audit_trace_itr2,
        audit_trace_itr3=audit_trace_itr3,
        decision_evidence_references=decision_references,
        decision_source_provenance=decision_provenance,
        used_rule_keys=tuple(sorted(used_rule_keys)),
        has_business_activity=business_activity,
        has_capital_activity=capital_activity,
        has_vda_activity=vda_activity,
    )


def _rule_keys_for_facts(facts: LossSetOffFacts) -> set[str]:
    keys: set[str] = set()
    negative_buckets = {
        item.bucket
        for item in facts.current_year_amounts
        if item.amount < 0
    }
    if negative_buckets & set(_SHORT_SOURCE_BUCKETS):
        keys.update({_RULE_CURRENT_PRIORITY, _RULE_STCL})
    if negative_buckets & set(_LONG_SOURCE_BUCKETS):
        keys.update({_RULE_CURRENT_PRIORITY, _RULE_LTCL})
    if IncomeBucket.NON_SPECULATIVE_BUSINESS in negative_buckets:
        keys.update({_RULE_CURRENT_PRIORITY, _RULE_CURRENT_BUSINESS})
    if IncomeBucket.SPECULATIVE_BUSINESS in negative_buckets:
        keys.add(_RULE_SPECULATION)
    if negative_buckets & set(_VDA_BUCKETS):
        keys.add(_RULE_VDA)
    for prior in facts.brought_forward_losses:
        keys.add(_RULE_TIMELY)
        if prior.category is LossCategory.SHORT_TERM_CAPITAL:
            keys.add(_RULE_STCL)
        elif prior.category is LossCategory.LONG_TERM_CAPITAL:
            keys.add(_RULE_LTCL)
        elif prior.category is LossCategory.NON_SPECULATIVE_BUSINESS:
            keys.add(_RULE_BF_BUSINESS)
        elif prior.category is LossCategory.SPECULATIVE_BUSINESS:
            keys.add(_RULE_SPECULATION)
    return keys


def _schedule_cg_current_losses(
    state: _ComputationState,
) -> dict[str, Any]:
    zeros = {
        field: 0 for field in _CAPITAL_SOURCE_FIELD.values()
    }
    schedule: dict[str, Any] = {
        "InLossSetOff": dict(zeros),
        "TotLossSetOff": dict(zeros),
        "LossRemainSetOff": dict(zeros),
    }
    for source_bucket, source_field in _CAPITAL_SOURCE_FIELD.items():
        schedule["InLossSetOff"][source_field] = _integer(
            state.current_source_losses[source_bucket]
        )
        allocated = sum(
            (
                item.amount
                for item in state.allocations
                if item.phase is SetOffPhase.CURRENT_CAPITAL_INTRA_HEAD
                and item.source_bucket is source_bucket
            ),
            Decimal("0"),
        )
        schedule["TotLossSetOff"][source_field] = _integer(allocated)
        schedule["LossRemainSetOff"][source_field] = _integer(
            state.current_source_losses[source_bucket] - allocated
        )
    for target_bucket, target_field in _CAPITAL_TARGET_FIELD.items():
        permitted_sources = [
            source_bucket
            for source_bucket in _CAPITAL_SOURCE_ORDER
            if source_bucket is not target_bucket
            and (
                target_bucket in _LONG_TARGET_SET
                or source_bucket in _SHORT_SOURCE_BUCKETS
            )
        ]
        row = {
            "CurrYearIncome": _integer(state.initial_income[target_bucket]),
        }
        for source_bucket in permitted_sources:
            source_field = _CAPITAL_SOURCE_FIELD[source_bucket]
            row[source_field] = _integer(
                sum(
                    (
                        item.amount
                        for item in state.allocations
                        if item.phase
                        is SetOffPhase.CURRENT_CAPITAL_INTRA_HEAD
                        and item.source_bucket is source_bucket
                        and item.target_bucket is target_bucket
                    ),
                    Decimal("0"),
                )
            )
        row["CurrYrCapGain"] = _integer(state.cyla_income[target_bucket])
        schedule[target_field] = row
    return schedule


_LONG_TARGET_SET = set(_LONG_CAPITAL_TARGETS)


def _schedule_bp_current_business(
    state: _ComputationState,
) -> dict[str, Any]:
    original_loss = state.current_source_losses[
        IncomeBucket.NON_SPECULATIVE_BUSINESS
    ]
    intra_setoff = _allocated(
        state,
        SetOffPhase.CURRENT_BUSINESS_INTRA_HEAD,
    )
    schedule: dict[str, Any] = {
        "LossSetOffOnBusLoss": _integer(original_loss),
        "TotLossSetOffOnBus": _integer(intra_setoff),
        "LossRemainSetOffOnBus": _integer(
            state.current_business_loss_after_intra_head
        ),
    }
    if original_loss or state.initial_income[IncomeBucket.SPECULATIVE_BUSINESS]:
        schedule["SpeculativeInc"] = {
            "IncOfCurYrUnderThatHead": _integer(
                state.initial_income[IncomeBucket.SPECULATIVE_BUSINESS]
            ),
            "BusLossSetoff": _integer(intra_setoff),
            "IncOfCurYrAfterSetOff": _integer(
                state.cyla_income[IncomeBucket.SPECULATIVE_BUSINESS]
            ),
        }
    return schedule


def _schedule_cyla(
    state: _ComputationState,
    *,
    form: str,
) -> dict[str, Any]:
    schedule: dict[str, Any] = {}
    required_capital = set(_CAPITAL_TARGET_FIELD)
    business_setoffs = _allocations_by_target(
        state,
        SetOffPhase.CURRENT_YEAR_INTER_HEAD,
    )
    for bucket, field in _CYLA_FIELD.items():
        if form == "ITR-2" and bucket in {
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
        }:
            continue
        start = state.cyla_income[bucket]
        end = state.bfla_income[bucket]
        required = bucket in required_capital
        if not required and not (start or end or business_setoffs.get(bucket)):
            continue
        row: dict[str, int] = {
            "IncOfCurYrUnderThatHead": _integer(start),
            "IncOfCurYrAfterSetOff": _integer(end),
        }
        business_setoff = business_setoffs.get(bucket, Decimal("0"))
        if business_setoff:
            row["BusLossSetoff"] = _integer(business_setoff)
        schedule[field] = {"IncCYLA": row}
    current_business = (
        state.current_business_loss_after_intra_head
        if form == "ITR-3"
        else Decimal("0")
    )
    business_setoff_total = (
        _allocated(state, SetOffPhase.CURRENT_YEAR_INTER_HEAD)
        if form == "ITR-3"
        else Decimal("0")
    )
    schedule["TotalCurYr"] = {
        "TotHPlossCurYr": 0,
        **({"TotBusLoss": _integer(current_business)} if form == "ITR-3" else {}),
        "TotOthSrcLossNoRaceHorse": 0,
    }
    schedule["TotalLossSetOff"] = {
        "TotHPlossCurYrSetoff": 0,
        **(
            {"TotBusLossSetoff": _integer(business_setoff_total)}
            if form == "ITR-3"
            else {}
        ),
        "TotOthSrcLossNoRaceHorseSetoff": 0,
    }
    schedule["LossRemAftSetOff"] = {
        "BalHPlossCurYrAftSetoff": 0,
        **(
            {
                "BalBusLossAftSetoff": _integer(
                    state.current_loss_remaining[
                        LossCategory.NON_SPECULATIVE_BUSINESS
                    ]
                )
            }
            if form == "ITR-3"
            else {}
        ),
        "BalOthSrcLossNoRaceHorseAftSetoff": 0,
    }
    return schedule


def _schedule_bfla(
    state: _ComputationState,
    *,
    form: str,
) -> dict[str, Any]:
    schedule: dict[str, Any] = {}
    bf_setoffs = _allocations_by_target(
        state,
        SetOffPhase.BROUGHT_FORWARD_CAPITAL,
        SetOffPhase.BROUGHT_FORWARD_BUSINESS,
    )
    required = {
        IncomeBucket.SALARY,
        *_CAPITAL_TARGET_FIELD,
    }
    for bucket, field in _CYLA_FIELD.items():
        if form == "ITR-2" and bucket in {
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
        }:
            continue
        start = state.bfla_income[bucket]
        end = state.final_income[bucket]
        setoff = bf_setoffs.get(bucket, Decimal("0"))
        if bucket not in required and not (start or end or setoff):
            continue
        row = _bfla_row(
            bucket=bucket,
            start=start,
            setoff=setoff,
            end=end,
            form=form,
        )
        schedule[field] = {"IncBFLA": row}
    total_setoff = _allocated(
        state,
        SetOffPhase.BROUGHT_FORWARD_CAPITAL,
        SetOffPhase.BROUGHT_FORWARD_BUSINESS,
    )
    schedule["TotalBFLossSetOff"] = {
        "TotBFLossSetoff": _integer(total_setoff),
        **(
            {
                "TotUnabsorbedDeprSetoff": 0,
                "TotAllUs35cl4Setoff": 0,
            }
            if form == "ITR-3"
            else {}
        ),
    }
    schedule["IncomeOfCurrYrAftCYLABFLA"] = _integer(
        sum(
            (
                state.final_income[bucket]
                for bucket in _CYLA_FIELD
                if not (
                    form == "ITR-2"
                    and bucket
                    in {
                        IncomeBucket.NON_SPECULATIVE_BUSINESS,
                        IncomeBucket.SPECULATIVE_BUSINESS,
                    }
                )
            ),
            Decimal("0"),
        )
    )
    return schedule


def _bfla_row(
    *,
    bucket: IncomeBucket,
    start: Decimal,
    setoff: Decimal,
    end: Decimal,
    form: str,
) -> dict[str, int]:
    row = {
        "IncOfCurYrUndHeadFromCYLA": _integer(start),
        "IncOfCurYrAfterSetOffBFLosses": _integer(end),
    }
    if bucket is IncomeBucket.SALARY:
        return row
    if form == "ITR-2":
        if bucket not in {
            IncomeBucket.OTHER_SOURCES_NORMAL,
            IncomeBucket.OTHER_SOURCES_DTAA,
        }:
            row["BFlossPrevYrUndSameHeadSetoff"] = _integer(setoff)
        return row
    if bucket not in {
        IncomeBucket.OTHER_SOURCES_NORMAL,
        IncomeBucket.OTHER_SOURCES_DTAA,
    }:
        if setoff:
            row["BFlossPrevYrUndSameHeadSetoff"] = _integer(setoff)
    row["BFUnabsorbedDeprSetoff"] = 0
    row["BFAllUs35Cl4Setoff"] = 0
    return row


def _schedule_cfl(
    state: _ComputationState,
    current_carryable: Mapping[LossCategory, Decimal],
    *,
    form: str,
) -> dict[str, Any]:
    summary_before = _loss_summary(form)
    summary_adjusted = _loss_summary(form)
    summary_current = _loss_summary(form)
    year_field = (
        _ITR3_CFL_YEAR_FIELD if form == "ITR-3" else _ITR2_CFL_YEAR_FIELD
    )
    rows: dict[int, dict[str, Any]] = defaultdict(dict)
    dates: dict[int, date] = {}
    for prior in state.prior_losses:
        if form == "ITR-2" and prior.category in {
            LossCategory.NON_SPECULATIVE_BUSINESS,
            LossCategory.SPECULATIVE_BUSINESS,
        }:
            continue
        assert prior.filing_date is not None
        key = (prior.assessment_year, prior.category)
        amount = state.prior_amounts[key]
        field = _CFL_CATEGORY_FIELD[prior.category]
        rows[prior.assessment_year][field] = _integer(amount)
        dates[prior.assessment_year] = prior.filing_date
        summary_before[field] += _integer(amount)
    schedule: dict[str, Any] = {}
    for assessment_year, amounts in sorted(rows.items()):
        detail = {"DateOfFiling": dates[assessment_year].isoformat(), **amounts}
        if form == "ITR-2" and assessment_year >= 2022:
            detail = {
                "DateOfFiling": dates[assessment_year].isoformat(),
                "TotalHPPTILossCF": 0,
                "TotalSTCGPTILossCF": amounts.get(
                    "TotalSTCGPTILossCF",
                    0,
                ),
                "TotalLTCGPTILossCF": amounts.get(
                    "TotalLTCGPTILossCF",
                    0,
                ),
            }
        schedule[year_field[assessment_year]] = {
            "CarryFwdLossDetail": detail
        }
    for allocation in state.allocations:
        if allocation.phase not in {
            SetOffPhase.BROUGHT_FORWARD_CAPITAL,
            SetOffPhase.BROUGHT_FORWARD_BUSINESS,
        }:
            continue
        if form == "ITR-2" and allocation.loss_category in {
            LossCategory.NON_SPECULATIVE_BUSINESS,
            LossCategory.SPECULATIVE_BUSINESS,
        }:
            continue
        summary_adjusted[_CFL_CATEGORY_FIELD[allocation.loss_category]] += (
            _integer(allocation.amount)
        )
    for category, amount in current_carryable.items():
        if form == "ITR-2" and category in {
            LossCategory.NON_SPECULATIVE_BUSINESS,
            LossCategory.SPECULATIVE_BUSINESS,
        }:
            continue
        summary_current[_CFL_CATEGORY_FIELD[category]] = _integer(amount)
    total = {
        field: summary_before[field]
        - summary_adjusted[field]
        + summary_current[field]
        for field in summary_before
    }
    schedule["TotalOfBFLossesEarlierYrs"] = {
        "LossSummaryDetail": summary_before
    }
    schedule["AdjTotBFLossInBFLA"] = {
        "LossSummaryDetail": summary_adjusted
    }
    schedule["CurrentAYloss"] = {"LossSummaryDetail": summary_current}
    schedule["TotalLossCFSummary"] = {"LossSummaryDetail": total}
    return schedule


def _loss_summary(form: str) -> dict[str, int]:
    if form == "ITR-2":
        return {
            "TotalHPPTILossCF": 0,
            "TotalSTCGPTILossCF": 0,
            "TotalLTCGPTILossCF": 0,
            "OthSrcLossRaceHorseCF": 0,
        }
    return {
        "TotalHPPTILossCF": 0,
        "BusLossOthThanSpecLossCF": 0,
        "LossFrmSpecBusCF": 0,
        "LossFrmSpecifiedBusCF": 0,
        "TotalSTCGPTILossCF": 0,
        "TotalLTCGPTILossCF": 0,
        "OthSrcLossRaceHorseCF": 0,
    }


def _part_b_ti(
    state: _ComputationState,
    current_carryable: Mapping[LossCategory, Decimal],
) -> dict[str, int]:
    total_income = sum(state.cyla_income.values(), Decimal("0"))
    current_setoff = _allocated(
        state,
        SetOffPhase.CURRENT_YEAR_INTER_HEAD,
    )
    brought_forward = _allocated(
        state,
        SetOffPhase.BROUGHT_FORWARD_CAPITAL,
        SetOffPhase.BROUGHT_FORWARD_BUSINESS,
    )
    balance = total_income - current_setoff
    return {
        "TotalTI": _integer(total_income),
        "CurrentYearLoss": _integer(current_setoff),
        "BalanceAfterSetoffLosses": _integer(balance),
        "BroughtFwdLossesSetoff": _integer(brought_forward),
        "GrossTotalIncome": _integer(balance - brought_forward),
        "LossesOfCurrentYearCarriedFwd": _integer(
            sum(current_carryable.values(), Decimal("0"))
        ),
    }


def _filing_output_deltas(
    *,
    form: str,
    has_capital_activity: bool,
    schedule_cg: Mapping[str, Any],
    schedule_bp: Mapping[str, Any] | None,
    schedule_cyla: Mapping[str, Any],
    schedule_bfla: Mapping[str, Any],
    schedule_cfl: Mapping[str, Any],
    part_b_ti: Mapping[str, int],
) -> tuple[LossFilingOutputDelta, ...]:
    roots: list[tuple[tuple[str, ...], Mapping[str, Any]]] = [
        (("ScheduleCYLA",), schedule_cyla),
        (("ScheduleBFLA",), schedule_bfla),
        (("ScheduleCFL",), schedule_cfl),
        (("PartB-TI",), part_b_ti),
    ]
    if has_capital_activity:
        roots.append(
            (("ScheduleCGFor23", "CurrYrLosses"), schedule_cg)
        )
    if schedule_bp is not None:
        roots.append(
            (("ITR3ScheduleBP", "BusSetoffCurrYr"), schedule_bp)
        )
    deltas = [
        delta
        for prefix, value in roots
        for delta in _flatten_output_deltas(form, prefix, value)
    ]
    if not has_capital_activity:
        deltas.append(
            LossFilingOutputDelta(
                form=form,
                path=("ScheduleCGFor23",),
                projected_value=None,
                context_amount=Decimal("0"),
                operation=LossFilingOutputOperation.REMOVE,
            )
        )
    output_paths = [delta.output_path for delta in deltas]
    if len(output_paths) != len(set(output_paths)):
        raise LossSetOffIntegrityError(
            f"{form} loss filing output paths must be unique"
        )
    return tuple(sorted(deltas, key=lambda item: item.output_path))


def _flatten_output_deltas(
    form: str,
    path: tuple[str, ...],
    value: Any,
) -> tuple[LossFilingOutputDelta, ...]:
    if isinstance(value, Mapping):
        return tuple(
            delta
            for key, item in value.items()
            for delta in _flatten_output_deltas(
                form,
                (*path, key),
                item,
            )
        )
    if not isinstance(value, (int, str)):
        raise LossSetOffIntegrityError(
            f"Unsupported loss filing output at {'/'.join(path)}: "
            f"{type(value).__name__}"
        )
    return (
        LossFilingOutputDelta(
            form=form,
            path=path,
            projected_value=value,
            context_amount=(
                Decimal(value) if isinstance(value, int) else Decimal("0")
            ),
        ),
    )


def _allocation_audit_trace(
    state: _ComputationState,
) -> tuple[LossAuditLine, ...]:
    return tuple(
        LossAuditLine(
            output_path=(
                f"/allocations/{index}/{allocation.phase.value}/"
                f"{allocation.target_bucket.value}"
            ),
            amount=allocation.amount,
            projected_value=format(allocation.amount, "f"),
            transformation="apply-verified-loss-eligibility-and-order",
            rule_keys=allocation.rule_keys,
            event_ids=allocation.event_ids,
            evidence_references=allocation.evidence_references,
            source_provenance=allocation.source_provenance,
        )
        for index, allocation in enumerate(state.allocations)
    )


def _filing_audit_trace(
    facts: LossSetOffFacts,
    state: _ComputationState,
    deltas: tuple[LossFilingOutputDelta, ...],
    evidence_references: tuple[str, ...],
    source_provenance: tuple[SourceProvenance, ...],
) -> tuple[LossAuditLine, ...]:
    rule_keys = {
        rule_key
        for allocation in state.allocations
        for rule_key in allocation.rule_keys
    }
    rule_keys.update(_rule_keys_for_facts(facts))
    if any(state.current_loss_remaining.values()) or facts.brought_forward_losses:
        rule_keys.add(_RULE_TIMELY)
    event_ids = tuple(
        sorted(item.event_id for item in facts.current_year_amounts)
    )
    return tuple(
        LossAuditLine(
            output_path=delta.output_path,
            amount=delta.context_amount,
            projected_value=delta.projected_value,
            transformation="project-cross-tied-loss-adjustment-leaf",
            rule_keys=tuple(sorted(rule_keys)),
            event_ids=event_ids,
            evidence_references=evidence_references,
            source_provenance=source_provenance,
        )
        for delta in deltas
    )


def _decision_evidence(
    facts: LossSetOffFacts,
) -> tuple[tuple[str, ...], tuple[SourceProvenance, ...]]:
    references: set[str] = set()
    provenance: list[SourceProvenance] = []
    if facts.coverage is not None:
        references.add(facts.coverage.evidence_reference)
        provenance.append(facts.coverage.source_provenance)
    if facts.current_return_filing is not None:
        references.add(facts.current_return_filing.evidence_reference)
        provenance.append(facts.current_return_filing.source_provenance)
    return (
        tuple(sorted(reference for reference in references if reference)),
        _unique_provenance(provenance),
    )


def _all_evidence(
    facts: LossSetOffFacts,
) -> tuple[tuple[str, ...], tuple[SourceProvenance, ...]]:
    decision_references, decision_provenance = _decision_evidence(facts)
    references = tuple(
        sorted(
            {
                reference
                for item in facts.current_year_amounts
                for reference in item.evidence_references
            }
            | {
                reference
                for item in facts.brought_forward_losses
                for reference in item.evidence_references
            }
            | set(decision_references)
        )
    )
    provenance = _unique_provenance(
        provenance
        for item in facts.current_year_amounts
        for provenance in item.source_provenance
    )
    provenance = _unique_provenance(
        (
            *provenance,
            *(
                provenance
                for item in facts.brought_forward_losses
                for provenance in item.source_provenance
            ),
            *decision_provenance,
        )
    )
    return references, provenance


def _allocated(
    state: _ComputationState,
    *phases: SetOffPhase,
) -> Decimal:
    return sum(
        (
            item.amount
            for item in state.allocations
            if item.phase in phases
        ),
        Decimal("0"),
    )


def _allocations_by_target(
    state: _ComputationState,
    *phases: SetOffPhase,
) -> dict[IncomeBucket, Decimal]:
    totals: dict[IncomeBucket, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in state.allocations:
        if item.phase in phases:
            totals[item.target_bucket] += item.amount
    return dict(totals)


def _return_object(draft: dict[str, Any], form_key: str) -> dict[str, Any]:
    try:
        value = draft["ITR"][form_key]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"Base draft must contain an object at /ITR/{form_key}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(
            f"Base draft must contain an object at /ITR/{form_key}"
        )
    return value


def _integer(value: Decimal | int) -> int:
    decimal_value = (
        value if isinstance(value, Decimal) else Decimal(value)
    )
    if decimal_value != decimal_value.to_integral_value():
        raise LossSetOffIntegrityError(
            "Official filing value was not rounded to whole rupees"
        )
    return int(decimal_value)


def _rupees(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _unique_provenance(
    values: Any,
) -> tuple[SourceProvenance, ...]:
    unique = {value.sort_key(): value for value in values}
    return tuple(unique[key] for key in sorted(unique))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "BroughtForwardBalance",
    "CoverageStatus",
    "CurrentReturnFilingFacts",
    "CurrentYearAmount",
    "IncomeBucket",
    "LossAdjustmentSlice",
    "LossAuditLine",
    "LossCategory",
    "LossFilingOutputDelta",
    "LossFilingOutputOperation",
    "LossSetOffAllocation",
    "LossSetOffAssessment",
    "LossSetOffBlocker",
    "LossSetOffCoverage",
    "LossSetOffFacts",
    "LossSetOffIntegrityError",
    "PriorYearLoss",
    "ReturnTimeliness",
    "SetOffPhase",
    "SetOffTargetOrder",
    "assess_loss_setoff",
    "build_loss_adjustment_itr2_draft",
    "build_loss_adjustment_itr3_draft",
]
