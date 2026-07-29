from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.bank_interest_ledger import SourceProvenance
from engine.contracts import OfficialContractRegistry
from engine.loss_setoff import (
    CoverageStatus,
    CurrentReturnFilingFacts,
    CurrentYearAmount,
    IncomeBucket,
    LossCategory,
    LossSetOffCoverage,
    LossSetOffFacts,
    LossSetOffIntegrityError,
    LossFilingOutputOperation,
    PriorYearLoss,
    ReturnTimeliness,
    SetOffPhase,
    SetOffTargetOrder,
    assess_loss_setoff,
    build_loss_adjustment_itr2_draft,
    build_loss_adjustment_itr3_draft,
)
from engine.rules.ay2026_27 import TABLE
from engine.securities_fifo import SecurityFifoResult
from engine.securities_filing import build_delivery_security_slice


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def _provenance(label: str) -> SourceProvenance:
    return SourceProvenance(
        source_document=f"{label}.json",
        source_sha256=("a" * 63) + str(len(label) % 10),
        source_location=f"/{label}",
        importer="test-normalizer",
        importer_version="1.0",
    )


def _amount(
    bucket: IncomeBucket,
    value: str,
    event_id: str,
) -> CurrentYearAmount:
    return CurrentYearAmount(
        event_id=event_id,
        bucket=bucket,
        amount=Decimal(value),
        evidence_references=(f"evidence:{event_id}",),
        source_provenance=(_provenance(event_id),),
    )


def _prior(
    assessment_year: int,
    category: LossCategory,
    amount: str,
    *,
    filing_date: date = date(2025, 7, 20),
    filing_due_date: date = date(2025, 7, 31),
) -> PriorYearLoss:
    identifier = f"ay{assessment_year}-{category.value}"
    return PriorYearLoss(
        assessment_year=assessment_year,
        category=category,
        amount=Decimal(amount),
        filing_date=filing_date,
        filing_due_date=filing_due_date,
        evidence_references=(f"schedule-cfl:{identifier}",),
        source_provenance=(_provenance(identifier),),
    )


def _filing(
    status: ReturnTimeliness = ReturnTimeliness.TIMELY,
) -> CurrentReturnFilingFacts:
    return CurrentReturnFilingFacts(
        status=status,
        evidence_reference="human:current-return-filing-status",
        source_provenance=_provenance("current-return"),
    )


def _coverage(
    *,
    current: CoverageStatus = CoverageStatus.COMPLETE,
    prior: CoverageStatus = CoverageStatus.COMPLETE,
    buckets: tuple[IncomeBucket, ...] = tuple(IncomeBucket),
) -> LossSetOffCoverage:
    return LossSetOffCoverage(
        current_income_status=current,
        covered_current_income_buckets=buckets,
        prior_loss_history_status=prior,
        evidence_reference="human:loss-input-coverage",
        source_provenance=_provenance("loss-coverage"),
    )


def _facts(
    *amounts: CurrentYearAmount,
    prior: tuple[PriorYearLoss, ...] = (),
    filing: CurrentReturnFilingFacts | None = None,
    target_order: SetOffTargetOrder | None = None,
    coverage: LossSetOffCoverage | None = None,
) -> LossSetOffFacts:
    return LossSetOffFacts(
        assessment_year="2026-27",
        current_year_amounts=amounts,
        brought_forward_losses=prior,
        current_return_filing=filing or _filing(),
        target_order=target_order or SetOffTargetOrder.default(),
        coverage=coverage or _coverage(),
    )


def _slice(facts: LossSetOffFacts):
    assessment = assess_loss_setoff(facts)
    assert assessment.blockers == ()
    assert assessment.filing_slice is not None
    return assessment.filing_slice


def _plain(value):
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


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
    IncomeBucket.STCG_20: ("CapGain", "ShortTerm", "ShortTerm20Per"),
    IncomeBucket.STCG_30: ("CapGain", "ShortTerm", "ShortTerm30Per"),
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


def _set_path(parent, path: tuple[str, ...], value) -> None:
    for component in path[:-1]:
        parent = parent[component]
    parent[path[-1]] = value


def _base_for_projection(form: str, result):
    form_key = form.replace("-", "")
    fixture_key = form_key.lower()
    base = json.loads(
        (FIXTURES / f"{fixture_key}-minimal.json").read_text(
            encoding="utf-8"
        )
    )
    itr = base["ITR"][form_key]
    part_b_ti = itr["PartB-TI"]
    income = result.income_before_inter_head_setoff
    for bucket, path in _PART_B_SOURCE_PATH.items():
        if form == "ITR-2" and bucket in {
            IncomeBucket.NON_SPECULATIVE_BUSINESS,
            IncomeBucket.SPECULATIVE_BUSINESS,
            IncomeBucket.VDA_BUSINESS_115BBH,
        }:
            continue
        _set_path(part_b_ti, path, int(income[bucket]))

    short = sum(
        (
            int(income[bucket])
            for bucket in (
                IncomeBucket.STCG_20,
                IncomeBucket.STCG_30,
                IncomeBucket.STCG_APPLICABLE,
                IncomeBucket.STCG_DTAA,
            )
        ),
        0,
    )
    long = sum(
        (
            int(income[bucket])
            for bucket in (
                IncomeBucket.LTCG_12_5,
                IncomeBucket.LTCG_DTAA,
            )
        ),
        0,
    )
    capital_vda = int(income[IncomeBucket.VDA_CAPITAL_115BBH])
    business_vda = int(income[IncomeBucket.VDA_BUSINESS_115BBH])
    part_b_ti["CapGain"]["ShortTerm"]["TotalShortTerm"] = short
    part_b_ti["CapGain"]["LongTerm"]["TotalLongTerm"] = long
    part_b_ti["CapGain"]["ShortTermLongTermTotal"] = short + long
    part_b_ti["CapGain"]["TotalCapGains"] = short + long + capital_vda
    other_sources = sum(
        (
            int(income[bucket])
            for bucket in (
                IncomeBucket.OTHER_SOURCES_NORMAL,
                IncomeBucket.OTHER_SOURCES_RACE_HORSE,
                IncomeBucket.OTHER_SOURCES_DTAA,
            )
        ),
        0,
    )
    part_b_ti["IncFromOS"]["TotIncFromOS"] = other_sources
    if form == "ITR-3":
        business = part_b_ti["ProfBusGain"]
        business["TotProfBusGain"] = (
            business["ProfGainNoSpecBus"]
            + business["ProfGainSpecBus"]
            + business["ProfGainSpecifiedBus"]
            + business["ProfIncome115BBF"]
        )
        source = result.current_source_amounts
        schedule_bp = itr["ITR3ScheduleBP"]
        non_speculative = int(
            source[IncomeBucket.NON_SPECULATIVE_BUSINESS]
        )
        speculative = int(source[IncomeBucket.SPECULATIVE_BUSINESS])
        schedule_bp["BusinessIncOthThanSpec"][
            "IncomeOtherThanRule"
        ] = non_speculative
        schedule_bp["BusinessIncOthThanSpec"][
            "IncRecCredPLOthHeadDtls"
        ]["115BBH"] = business_vda
        schedule_bp["SpecBusinessInc"][
            "AdjustedPLFrmSpecuBus"
        ] = speculative
        schedule_bp["IncChrgUnHdProftGain"] = (
            non_speculative + speculative
        )
        schedule_bp["BusSetoffCurrYr"]["LossSetOffOnBusLoss"] = max(
            -non_speculative,
            0,
        )

    if result.has_capital_activity:
        zero_fifo = SecurityFifoResult(
            matched_disposals=(),
            closing_positions={},
            deductible_charges=Decimal("0"),
            non_deductible_stt=Decimal("0"),
        )
        schedule_cg = _plain(
            build_delivery_security_slice(zero_fifo).schedule_cg
        )
        source_losses = result.schedule_cg_current_year_losses[
            "InLossSetOff"
        ]
        capital_matrix = result.schedule_cg_current_year_losses
        raw_short = sum(
            int(capital_matrix[target]["CurrYearIncome"])
            - int(source_losses[source])
            for target, source in (
                ("InStcg20Per", "StclSetoff20Per"),
                ("InStcg30Per", "StclSetoff30Per"),
                ("InStcgAppRate", "StclSetoffAppRate"),
                ("InStcgDTAARate", "StclSetoffDTAARate"),
            )
        )
        raw_long = sum(
            int(capital_matrix[target]["CurrYearIncome"])
            - int(source_losses[source])
            for target, source in (
                ("InLtcg12_5Per", "LtclSetOff12_5Per"),
                ("InLtcgDTAARate", "LtclSetOffDTAARate"),
            )
        )
        schedule_cg["ShortTermCapGainFor23"]["TotalSTCG"] = raw_short
        schedule_cg["LongTermCapGain23"]["TotalLTCG"] = raw_long
        schedule_cg["SumOfCGIncm"] = short + long
        schedule_cg["IncmFromVDATrnsf"] = capital_vda
        schedule_cg["TotScheduleCGFor23"] = (
            short + long + capital_vda
        )
        if form == "ITR-3":
            schedule_cg["DeducClaimInfo"] = {"TotDeductClaim": 0}
            schedule_cg["ShortTermCapGainFor23"][
                "SlumpSaleInStcg"
            ] = {
                "FMV11UAEii": 0,
                "FMV11UAEiii": 0,
                "FullConsideration": 0,
                "NetWorthOfDivision": 0,
                "CapgainonAssets": 0,
            }
            schedule_cg["ShortTermCapGainFor23"]["SaleOnOtherAssets"][
                "DeemedStcgOnAssets"
            ] = 0
            schedule_cg["ShortTermCapGainFor23"]["SaleOnOtherAssets"][
                "ExemptionOrDednUs54"
            ] = {"ExemptionGrandTotal": 0}
            schedule_cg["LongTermCapGain23"][
                "SlumpSaleInLtcgDtls"
            ] = {}
            schedule_cg["AccruOrRecOfCG"][
                "VDATrnsfGainsUnder30Per"
            ] = _plain(
                schedule_cg["AccruOrRecOfCG"]["ShortTermUnder20Per"]
            )
        itr["ScheduleCGFor23"] = schedule_cg
    if result.has_vda_activity:
        itr["ScheduleVDA"] = {
            "ScheduleVDADtls": [],
            **(
                {"TotIncBusiness": business_vda}
                if form == "ITR-3"
                else {}
            ),
            "TotIncCapGain": capital_vda,
        }
    return base


def _pointer_get(document, pointer: str):
    value = document
    for component in pointer.removeprefix("/").split("/"):
        value = value[component]
    return value


def _pointer_exists(document, pointer: str) -> bool:
    try:
        _pointer_get(document, pointer)
    except (KeyError, TypeError):
        return False
    return True


def test_current_ltc_loss_is_restricted_to_ltcg():
    result = _slice(
        _facts(
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            _amount(IncomeBucket.LTCG_12_5, "-40", "ltcl"),
        )
    )

    assert result.income_after_setoff[IncomeBucket.STCG_20] == Decimal("100")
    assert result.current_loss_remaining[LossCategory.LONG_TERM_CAPITAL] == Decimal(
        "40"
    )
    assert not result.allocations


def test_restricted_current_ltc_loss_is_used_before_flexible_stc_loss():
    result = _slice(
        _facts(
            _amount(IncomeBucket.STCG_APPLICABLE, "50", "stcg"),
            _amount(IncomeBucket.LTCG_12_5, "100", "ltcg"),
            _amount(IncomeBucket.STCG_20, "-40", "stcl"),
            _amount(IncomeBucket.LTCG_DTAA, "-30", "ltcl"),
        )
    )

    assert result.income_after_setoff[IncomeBucket.STCG_APPLICABLE] == Decimal("10")
    assert result.income_after_setoff[IncomeBucket.LTCG_12_5] == Decimal("70")
    assert result.current_loss_remaining[LossCategory.SHORT_TERM_CAPITAL] == 0
    assert result.current_loss_remaining[LossCategory.LONG_TERM_CAPITAL] == 0
    assert result.allocations[0].loss_category is LossCategory.LONG_TERM_CAPITAL


def test_current_non_speculative_business_loss_uses_speculation_then_cyla_targets():
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "500", "salary"),
            _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "-60", "fno"),
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "30", "intraday"),
            _amount(IncomeBucket.STCG_20, "20", "stcg"),
            _amount(IncomeBucket.VDA_CAPITAL_115BBH, "50", "vda"),
        )
    )

    assert result.income_after_setoff[IncomeBucket.SALARY] == Decimal("500")
    assert (
        result.income_after_setoff[IncomeBucket.VDA_CAPITAL_115BBH]
        == Decimal("50")
    )
    assert result.income_after_setoff[IncomeBucket.SPECULATIVE_BUSINESS] == 0
    assert result.income_after_setoff[IncomeBucket.STCG_20] == 0
    assert (
        result.current_loss_remaining[LossCategory.NON_SPECULATIVE_BUSINESS]
        == Decimal("10")
    )
    assert [
        (allocation.phase, allocation.target_bucket, allocation.amount)
        for allocation in result.allocations
    ] == [
        (
            SetOffPhase.CURRENT_BUSINESS_INTRA_HEAD,
            IncomeBucket.SPECULATIVE_BUSINESS,
            Decimal("30"),
        ),
        (
            SetOffPhase.CURRENT_YEAR_INTER_HEAD,
            IncomeBucket.STCG_20,
            Decimal("20"),
        ),
    ]


def test_current_business_loss_can_offset_dtaa_other_source_income():
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.NON_SPECULATIVE_BUSINESS,
                "-100",
                "business-loss",
            ),
            _amount(
                IncomeBucket.OTHER_SOURCES_DTAA,
                "100",
                "dtaa-other-source",
            ),
        )
    )

    assert result.income_after_setoff[IncomeBucket.OTHER_SOURCES_DTAA] == 0
    assert (
        result.current_loss_remaining[
            LossCategory.NON_SPECULATIVE_BUSINESS
        ]
        == 0
    )
    assert [
        (allocation.target_bucket, allocation.amount)
        for allocation in result.allocations
    ] == [(IncomeBucket.OTHER_SOURCES_DTAA, Decimal("100"))]


def test_current_speculation_loss_does_not_reduce_non_speculative_profit():
    result = _slice(
        _facts(
            _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "100", "fno"),
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "-40", "intraday"),
        )
    )

    assert (
        result.income_after_setoff[IncomeBucket.NON_SPECULATIVE_BUSINESS]
        == Decimal("100")
    )
    assert result.current_loss_remaining[LossCategory.SPECULATIVE_BUSINESS] == 40
    assert result.allocations == ()


def test_vda_losses_are_neither_netted_set_off_nor_carried_forward():
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "100",
                "vda-gain",
            ),
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "-60",
                "vda-loss",
            ),
            _amount(IncomeBucket.STCG_20, "25", "stcg"),
        )
    )

    assert (
        result.income_after_setoff[IncomeBucket.VDA_CAPITAL_115BBH]
        == Decimal("100")
    )
    assert result.disallowed_vda_loss == Decimal("60")
    assert result.allocations == ()
    assert all(
        amount == 0
        for amount in result.current_loss_remaining.values()
    )
    assert result.schedule_cfl_itr3["CurrentAYloss"]["LossSummaryDetail"][
        "TotalSTCGPTILossCF"
    ] == 0


def test_disallowed_vda_losses_preserve_their_tax_heads():
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "-30",
                "capital-vda-loss",
            ),
            _amount(
                IncomeBucket.VDA_BUSINESS_115BBH,
                "-40",
                "business-vda-loss",
            ),
        )
    )

    assert result.disallowed_vda_losses == {
        IncomeBucket.VDA_CAPITAL_115BBH: Decimal("30"),
        IncomeBucket.VDA_BUSINESS_115BBH: Decimal("40"),
    }
    assert result.disallowed_vda_loss == Decimal("70")


def test_business_vda_is_protected_and_requires_itr3():
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.NON_SPECULATIVE_BUSINESS,
                "-100",
                "business-loss",
            ),
            _amount(
                IncomeBucket.VDA_BUSINESS_115BBH,
                "80",
                "business-vda",
            ),
        )
    )

    assert result.allocations == ()
    assert (
        result.income_after_setoff[
            IncomeBucket.VDA_BUSINESS_115BBH
        ]
        == Decimal("80")
    )
    assert (
        result.current_loss_remaining[
            LossCategory.NON_SPECULATIVE_BUSINESS
        ]
        == Decimal("100")
    )
    assert result.has_business_activity
    assert not result.has_capital_activity
    assert result.has_vda_activity
    with pytest.raises(ValueError, match="ITR-2 cannot contain"):
        build_loss_adjustment_itr2_draft(
            _base_for_projection("ITR-2", result),
            result,
        )


def test_mixed_vda_heads_reconcile_to_distinct_itr3_sources():
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "50",
                "capital-vda",
            ),
            _amount(
                IncomeBucket.VDA_BUSINESS_115BBH,
                "70",
                "business-vda",
            ),
        )
    )
    base = _base_for_projection("ITR-3", result)

    draft = build_loss_adjustment_itr3_draft(base, result)
    itr3 = draft["ITR"]["ITR3"]

    assert itr3["ScheduleVDA"] == {
        "ScheduleVDADtls": [],
        "TotIncBusiness": 70,
        "TotIncCapGain": 50,
    }
    assert itr3["ITR3ScheduleBP"]["BusinessIncOthThanSpec"][
        "IncRecCredPLOthHeadDtls"
    ]["115BBH"] == 70
    assert itr3["PartB-TI"]["ProfBusGain"]["ProfIncome115BBF"] == 70
    assert itr3["PartB-TI"]["ProfBusGain"]["TotProfBusGain"] == 70
    assert itr3["ScheduleCGFor23"]["IncmFromVDATrnsf"] == 50
    assert itr3["PartB-TI"]["CapGain"]["CapGains30Per115BBH"] == 50
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-3",
        draft,
    )


def test_current_year_capital_loss_has_priority_over_brought_forward_loss():
    result = _slice(
        _facts(
            _amount(IncomeBucket.STCG_20, "100", "stcg-gain"),
            _amount(IncomeBucket.STCG_APPLICABLE, "-80", "current-stcl"),
            prior=(_prior(2024, LossCategory.SHORT_TERM_CAPITAL, "80"),),
        )
    )

    current = [
        allocation
        for allocation in result.allocations
        if allocation.phase is SetOffPhase.CURRENT_CAPITAL_INTRA_HEAD
    ]
    brought_forward = [
        allocation
        for allocation in result.allocations
        if allocation.phase is SetOffPhase.BROUGHT_FORWARD_CAPITAL
    ]
    assert sum((item.amount for item in current), Decimal("0")) == Decimal("80")
    assert sum((item.amount for item in brought_forward), Decimal("0")) == Decimal(
        "20"
    )
    assert result.brought_forward_remaining[0].amount == Decimal("60")


def test_brought_forward_ltc_and_stc_restrictions_and_oldest_first():
    result = _slice(
        _facts(
            _amount(IncomeBucket.STCG_20, "50", "stcg"),
            _amount(IncomeBucket.LTCG_12_5, "100", "ltcg"),
            prior=(
                _prior(2024, LossCategory.LONG_TERM_CAPITAL, "70"),
                _prior(2019, LossCategory.SHORT_TERM_CAPITAL, "60"),
                _prior(2025, LossCategory.SHORT_TERM_CAPITAL, "60"),
            ),
        )
    )

    assert result.income_after_setoff[IncomeBucket.STCG_20] == 0
    assert result.income_after_setoff[IncomeBucket.LTCG_12_5] == 0
    by_origin = {
        balance.assessment_year: balance.amount
        for balance in result.brought_forward_remaining
    }
    assert by_origin == {2019: Decimal("0"), 2024: Decimal("0"), 2025: Decimal("40")}


def test_brought_forward_business_categories_remain_separate():
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "1000", "salary"),
            _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "50", "fno"),
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "50", "intraday"),
            prior=(
                _prior(2024, LossCategory.SPECULATIVE_BUSINESS, "40"),
                _prior(2023, LossCategory.NON_SPECULATIVE_BUSINESS, "70"),
            ),
        )
    )

    assert result.income_after_setoff[IncomeBucket.SALARY] == Decimal("1000")
    assert result.income_after_setoff[IncomeBucket.NON_SPECULATIVE_BUSINESS] == 0
    assert result.income_after_setoff[IncomeBucket.SPECULATIVE_BUSINESS] == 0
    by_category = {
        balance.category: balance.amount
        for balance in result.brought_forward_remaining
    }
    assert by_category[LossCategory.SPECULATIVE_BUSINESS] == 0
    assert by_category[LossCategory.NON_SPECULATIVE_BUSINESS] == Decimal("10")


def test_incomplete_late_and_expired_prior_loss_evidence_blocks():
    incomplete = PriorYearLoss(
        assessment_year=2024,
        category=LossCategory.SHORT_TERM_CAPITAL,
        amount=None,
        filing_date=None,
        filing_due_date=None,
        evidence_references=(),
        source_provenance=(),
    )
    assessment = assess_loss_setoff(
        _facts(
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            prior=(
                incomplete,
                _prior(
                    2023,
                    LossCategory.LONG_TERM_CAPITAL,
                    "10",
                    filing_date=date(2024, 8, 1),
                    filing_due_date=date(2024, 7, 31),
                ),
                _prior(2021, LossCategory.SPECULATIVE_BUSINESS, "10"),
            ),
        )
    )

    assert assessment.filing_slice is None
    assert {blocker.code for blocker in assessment.blockers} == {
        "prior_loss_amount_missing",
        "prior_loss_filing_date_missing",
        "prior_loss_due_date_missing",
        "prior_loss_evidence_missing",
        "prior_loss_provenance_missing",
        "prior_loss_return_late",
        "prior_loss_expired",
    }


def test_incomplete_current_bucket_or_prior_loss_history_coverage_blocks():
    assessment = assess_loss_setoff(
        _facts(
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            coverage=_coverage(
                current=CoverageStatus.INCOMPLETE,
                prior=CoverageStatus.UNKNOWN,
                buckets=(IncomeBucket.STCG_20,),
            ),
        )
    )

    assert assessment.filing_slice is None
    assert {blocker.code for blocker in assessment.blockers} == {
        "current_income_coverage_incomplete",
        "prior_loss_history_coverage_required",
    }


def test_unknown_current_return_timeliness_blocks_current_carry_forward():
    assessment = assess_loss_setoff(
        _facts(
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "-40", "intraday"),
            filing=_filing(ReturnTimeliness.UNKNOWN),
        )
    )

    assert assessment.filing_slice is None
    assert [blocker.code for blocker in assessment.blockers] == [
        "current_return_timeliness_required"
    ]
    assert "human" in assessment.blockers[0].required_input.lower()


def test_late_current_return_forfeits_non_house_property_carry_forward():
    result = _slice(
        _facts(
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "-40", "intraday"),
            _amount(IncomeBucket.LTCG_12_5, "-25", "ltcl"),
            filing=_filing(ReturnTimeliness.LATE),
        )
    )

    assert result.forfeited_current_losses == {
        LossCategory.LONG_TERM_CAPITAL: Decimal("25"),
        LossCategory.SPECULATIVE_BUSINESS: Decimal("40"),
    }
    assert all(
        value == 0
        for value in result.schedule_cfl_itr3["CurrentAYloss"][
            "LossSummaryDetail"
        ].values()
    )


def test_decisive_human_evidence_is_validated_and_retained():
    filing = _filing(ReturnTimeliness.TIMELY)
    coverage = _coverage()
    result = _slice(
        _facts(
            _amount(IncomeBucket.LTCG_12_5, "-25", "ltcl"),
            filing=filing,
            coverage=coverage,
        )
    )

    assert set(result.decision_evidence_references) == {
        filing.evidence_reference,
        coverage.evidence_reference,
    }
    assert set(result.decision_source_provenance) == {
        filing.source_provenance,
        coverage.source_provenance,
    }
    for line in (*result.audit_trace_itr2, *result.audit_trace_itr3):
        assert filing.evidence_reference in line.evidence_references
        assert coverage.evidence_reference in line.evidence_references
        assert filing.source_provenance in line.source_provenance
        assert coverage.source_provenance in line.source_provenance

    missing_filing_provenance = replace(
        filing,
        source_provenance=None,
    )
    missing_coverage_provenance = replace(
        coverage,
        source_provenance=None,
    )
    assessment = assess_loss_setoff(
        _facts(
            _amount(IncomeBucket.LTCG_12_5, "-25", "ltcl"),
            filing=missing_filing_provenance,
            coverage=missing_coverage_provenance,
        )
    )
    assert {blocker.code for blocker in assessment.blockers} == {
        "current_return_filing_provenance_missing",
        "loss_coverage_evidence_missing",
    }

    unknown_without_provenance = replace(
        _filing(ReturnTimeliness.UNKNOWN),
        source_provenance=None,
    )
    assessment = assess_loss_setoff(
        _facts(
            _amount(IncomeBucket.SALARY, "100", "salary"),
            filing=unknown_without_provenance,
        )
    )
    assert [blocker.code for blocker in assessment.blockers] == [
        "current_return_filing_provenance_missing"
    ]


def test_target_order_must_be_an_exhaustive_permutation():
    default = SetOffTargetOrder.default()
    unsafe = replace(
        default,
        current_non_speculative_business=(
            IncomeBucket.STCG_20,
        ),
    )

    with pytest.raises(LossSetOffIntegrityError, match="exhaustive permutation"):
        assess_loss_setoff(
            _facts(
                _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "-10", "fno"),
                _amount(IncomeBucket.STCG_20, "10", "stcg"),
                target_order=unsafe,
            )
        )


def test_itr3_adjustment_schedules_cross_tie_and_validate_official_schema():
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "500", "salary"),
            _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "-60", "fno"),
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "30", "intraday"),
            _amount(IncomeBucket.STCG_20, "50", "stcg"),
            _amount(IncomeBucket.LTCG_12_5, "100", "ltcg"),
            _amount(IncomeBucket.VDA_CAPITAL_115BBH, "25", "vda"),
            prior=(_prior(2024, LossCategory.LONG_TERM_CAPITAL, "70"),),
        )
    )

    cyla = result.schedule_cyla_itr3
    bfla = result.schedule_bfla_itr3
    cfl = result.schedule_cfl_itr3
    assert cyla["TotalCurYr"]["TotBusLoss"] == 30
    assert cyla["TotalLossSetOff"]["TotBusLossSetoff"] == 30
    assert cyla["STCG20Per"]["IncCYLA"] == {
        "IncOfCurYrUnderThatHead": 50,
        "BusLossSetoff": 30,
        "IncOfCurYrAfterSetOff": 20,
    }
    assert bfla["LTCG12_5Per"]["IncBFLA"][
        "BFlossPrevYrUndSameHeadSetoff"
    ] == 70
    assert bfla["IncomeOfCurrYrAftCYLABFLA"] == 550
    assert cfl["TotalOfBFLossesEarlierYrs"]["LossSummaryDetail"][
        "TotalLTCGPTILossCF"
    ] == 70
    assert cfl["AdjTotBFLossInBFLA"]["LossSummaryDetail"][
        "TotalLTCGPTILossCF"
    ] == 70
    assert cfl["TotalLossCFSummary"]["LossSummaryDetail"][
        "TotalLTCGPTILossCF"
    ] == 0
    assert result.part_b_ti == {
        "TotalTI": 675,
        "CurrentYearLoss": 30,
        "BalanceAfterSetoffLosses": 645,
        "BroughtFwdLossesSetoff": 70,
        "GrossTotalIncome": 575,
        "LossesOfCurrentYearCarriedFwd": 0,
    }

    base = _base_for_projection("ITR-3", result)
    draft = build_loss_adjustment_itr3_draft(base, result)
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-3",
        draft,
    )


def test_itr2_capital_adjustment_schedules_validate_official_schema():
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "500", "salary"),
            _amount(IncomeBucket.HOUSE_PROPERTY, "40", "house-property"),
            _amount(
                IncomeBucket.OTHER_SOURCES_NORMAL,
                "30",
                "other-sources",
            ),
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            prior=(_prior(2024, LossCategory.SHORT_TERM_CAPITAL, "20"),),
        )
    )
    base = _base_for_projection("ITR-2", result)

    draft = build_loss_adjustment_itr2_draft(base, result)

    assert draft["ITR"]["ITR2"]["ScheduleBFLA"]["STCG20Per"]["IncBFLA"][
        "BFlossPrevYrUndSameHeadSetoff"
    ] == 20
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-2",
        draft,
    )


@pytest.mark.parametrize(
    ("form", "bucket"),
    [
        ("ITR-2", IncomeBucket.LTCG_12_5),
        ("ITR-3", IncomeBucket.SPECULATIVE_BUSINESS),
    ],
)
def test_current_loss_cfl_validates_each_supported_official_schema(
    form: str,
    bucket: IncomeBucket,
):
    result = _slice(_facts(_amount(bucket, "-25", "current-loss")))
    base = _base_for_projection(form, result)
    draft = (
        build_loss_adjustment_itr2_draft(base, result)
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft(base, result)
    )

    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        form,
        draft,
    )


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_capital_projection_requires_an_object_schedule_cg(form: str):
    result = _slice(
        _facts(_amount(IncomeBucket.STCG_20, "25", "stcg"))
    )
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )
    form_key = form.replace("-", "")
    base = _base_for_projection(form, result)
    del base["ITR"][form_key]["ScheduleCGFor23"]

    with pytest.raises(
        ValueError,
        match="ScheduleCGFor23 object.*capital",
    ):
        builder(base, result)

    base = _base_for_projection(form, result)
    base["ITR"][form_key]["ScheduleCGFor23"] = []
    with pytest.raises(
        ValueError,
        match="ScheduleCGFor23 object.*capital",
    ):
        builder(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_capital_projection_reconciles_schedule_cg_source_totals(form: str):
    result = _slice(
        _facts(
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            _amount(IncomeBucket.STCG_30, "-25", "stcl"),
        )
    )
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["ScheduleCGFor23"][
        "ShortTermCapGainFor23"
    ]["TotalSTCG"] = 74
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    with pytest.raises(
        ValueError,
        match="ScheduleCGFor23 source-income mismatch.*TotalSTCG",
    ):
        builder(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
@pytest.mark.parametrize(
    ("field", "incorrect"),
    [
        ("IncmFromVDATrnsf", 0),
        ("SumOfCGIncm", 1),
        ("TotScheduleCGFor23", 49),
    ],
)
def test_vda_projection_reconciles_all_schedule_cg_aggregates(
    form: str,
    field: str,
    incorrect: int,
):
    result = _slice(
        _facts(
            _amount(IncomeBucket.VDA_CAPITAL_115BBH, "50", "vda")
        )
    )
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["ScheduleCGFor23"][field] = incorrect
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    with pytest.raises(
        ValueError,
        match=rf"ScheduleCGFor23 source-income mismatch.*{field}",
    ):
        builder(base, result)


@pytest.mark.parametrize(
    ("path", "incorrect"),
    [
        (
            (
                "ITR3ScheduleBP",
                "BusinessIncOthThanSpec",
                "IncRecCredPLOthHeadDtls",
                "115BBH",
            ),
            0,
        ),
        (("PartB-TI", "ProfBusGain", "ProfIncome115BBF"), 0),
        (("ScheduleVDA", "TotIncBusiness"), 0),
    ],
)
def test_business_vda_projection_rejects_source_mismatches(
    path: tuple[str, ...],
    incorrect: int,
):
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.VDA_BUSINESS_115BBH,
                "50",
                "business-vda",
            )
        )
    )
    base = _base_for_projection("ITR-3", result)
    _set_path(base["ITR"]["ITR3"], path, incorrect)

    with pytest.raises(ValueError, match="source-income mismatch"):
        build_loss_adjustment_itr3_draft(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_capital_vda_projection_rejects_schedule_vda_mismatch(form: str):
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "50",
                "capital-vda",
            )
        )
    )
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["ScheduleVDA"]["TotIncCapGain"] = 0
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    with pytest.raises(
        ValueError,
        match="ScheduleVDA source-income mismatch.*TotIncCapGain",
    ):
        builder(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_no_capital_recomputation_removes_a_stale_schedule_cg(form: str):
    result = _slice(_facts(_amount(IncomeBucket.SALARY, "100", "salary")))
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["ScheduleCGFor23"] = {
        "CurrYrLosses": {
            "LossRemainSetOff": {"StclSetoff20Per": 99}
        }
    }
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    draft = builder(base, result)
    deltas = (
        result.output_deltas_itr2
        if form == "ITR-2"
        else result.output_deltas_itr3
    )
    trace = (
        result.audit_trace_itr2
        if form == "ITR-2"
        else result.audit_trace_itr3
    )

    assert "ScheduleCGFor23" not in draft["ITR"][form_key]
    removal = next(
        delta
        for delta in deltas
        if delta.output_path == f"/ITR/{form_key}/ScheduleCGFor23"
    )
    assert removal.operation is LossFilingOutputOperation.REMOVE
    assert removal.output_path in {line.output_path for line in trace}


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_projection_rejects_nonzero_unsupported_prior_loss_branches(
    form: str,
):
    result = _slice(_facts(_amount(IncomeBucket.SALARY, "100", "salary")))
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["ScheduleCFL"] = {
        "TotalLossCFSummary": {
            "LossSummaryDetail": {"TotalHPPTILossCF": 10}
        }
    }
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    with pytest.raises(
        ValueError,
        match="unsupported loss branch.*TotalHPPTILossCF",
    ):
        builder(base, result)


@pytest.mark.parametrize(
    "field",
    ["BrtFwdBusLoss", "AdjustAccTax115BACAmt"],
)
def test_projection_rejects_every_unmodelled_cfl_leaf(field: str):
    result = _slice(_facts(_amount(IncomeBucket.SALARY, "100", "salary")))
    base = _base_for_projection("ITR-3", result)
    base["ITR"]["ITR3"]["ScheduleCFL"] = {
        "LossCFCurrentAssmntYear2025": {
            "CarryFwdLossDetail": {
                "DateOfFiling": "2025-07-20",
                field: 10,
            }
        }
    }

    with pytest.raises(
        ValueError,
        match=rf"unsupported loss branch.*{field}",
    ):
        build_loss_adjustment_itr3_draft(base, result)


def test_itr3_projection_rejects_unabsorbed_depreciation_setoff():
    result = _slice(_facts(_amount(IncomeBucket.SALARY, "100", "salary")))
    base = _base_for_projection("ITR-3", result)
    base["ITR"]["ITR3"]["ScheduleBFLA"]["STCG20Per"]["IncBFLA"][
        "BFUnabsorbedDeprSetoff"
    ] = 10

    with pytest.raises(
        ValueError,
        match="unsupported loss branch.*BFUnabsorbedDeprSetoff",
    ):
        build_loss_adjustment_itr3_draft(base, result)


@pytest.mark.parametrize(
    ("path", "incorrect"),
    [
        (("BusinessIncOthThanSpec", "IncomeOtherThanRule"), -59),
        (("SpecBusinessInc", "AdjustedPLFrmSpecuBus"), 29),
        (("IncChrgUnHdProftGain",), -29),
        (("BusSetoffCurrYr", "LossSetOffOnBusLoss"), 59),
    ],
)
def test_itr3_business_loss_sources_must_reconcile_before_projection(
    path: tuple[str, ...],
    incorrect: int,
):
    result = _slice(
        _facts(
            _amount(
                IncomeBucket.NON_SPECULATIVE_BUSINESS,
                "-60",
                "fno",
            ),
            _amount(
                IncomeBucket.SPECULATIVE_BUSINESS,
                "30",
                "intraday",
            ),
        )
    )
    base = _base_for_projection("ITR-3", result)
    schedule_bp = base["ITR"]["ITR3"]["ITR3ScheduleBP"]
    schedule_bp["BusinessIncOthThanSpec"]["IncomeOtherThanRule"] = -60
    schedule_bp["SpecBusinessInc"]["AdjustedPLFrmSpecuBus"] = 30
    schedule_bp["IncChrgUnHdProftGain"] = -30
    schedule_bp["BusSetoffCurrYr"]["LossSetOffOnBusLoss"] = 60
    _set_path(schedule_bp, path, incorrect)

    with pytest.raises(
        ValueError,
        match=r"ScheduleBP source-income mismatch",
    ):
        build_loss_adjustment_itr3_draft(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_part_b_ti_source_income_must_reconcile_before_projection(form: str):
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "100", "salary"),
            _amount(IncomeBucket.OTHER_SOURCES_NORMAL, "20", "interest"),
        )
    )
    base = _base_for_projection(form, result)
    form_key = form.replace("-", "")
    base["ITR"][form_key]["PartB-TI"]["Salaries"] = 99
    builder = (
        build_loss_adjustment_itr2_draft
        if form == "ITR-2"
        else build_loss_adjustment_itr3_draft
    )

    with pytest.raises(
        ValueError,
        match="PartB-TI source-income mismatch.*Salaries",
    ):
        builder(base, result)


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_every_projected_leaf_has_an_exact_form_specific_audit_binding(
    form: str,
):
    result = _slice(
        _facts(
            _amount(IncomeBucket.SALARY, "500", "salary"),
            _amount(IncomeBucket.STCG_20, "100", "stcg"),
            _amount(IncomeBucket.LTCG_12_5, "-25", "ltcl"),
            prior=(_prior(2024, LossCategory.SHORT_TERM_CAPITAL, "20"),),
        )
    )
    base = _base_for_projection(form, result)
    if form == "ITR-2":
        deltas = result.output_deltas_itr2
        trace = result.audit_trace_itr2
        draft = build_loss_adjustment_itr2_draft(base, result)
    else:
        deltas = result.output_deltas_itr3
        trace = result.audit_trace_itr3
        draft = build_loss_adjustment_itr3_draft(base, result)

    assert {delta.output_path for delta in deltas} == {
        line.output_path for line in trace
    }
    assert len({delta.output_path for delta in deltas}) == len(deltas)
    for delta in deltas:
        if delta.operation is LossFilingOutputOperation.REMOVE:
            assert not _pointer_exists(draft, delta.output_path)
        else:
            assert _pointer_get(draft, delta.output_path) == delta.projected_value


def test_repeated_loss_computation_is_deterministic():
    facts = _facts(
        _amount(IncomeBucket.STCG_20, "100.40", "stcg"),
        _amount(IncomeBucket.LTCG_12_5, "-25.10", "ltcl"),
        prior=(_prior(2024, LossCategory.SHORT_TERM_CAPITAL, "30.20"),),
    )

    assert assess_loss_setoff(facts) == assess_loss_setoff(facts)


def test_every_loss_rule_used_by_the_slice_is_verified_for_ay_2026_27():
    result = _slice(
        _facts(
            _amount(IncomeBucket.NON_SPECULATIVE_BUSINESS, "-40", "fno"),
            _amount(IncomeBucket.SPECULATIVE_BUSINESS, "10", "intraday"),
            _amount(
                IncomeBucket.VDA_CAPITAL_115BBH,
                "-5",
                "vda-loss",
            ),
            prior=(
                _prior(2024, LossCategory.SHORT_TERM_CAPITAL, "10"),
                _prior(2023, LossCategory.SPECULATIVE_BUSINESS, "10"),
            ),
        )
    )

    assert set(result.used_rule_keys) == {
        "loss.business.current_year.targets",
        "loss.capital.short_term.targets",
        "loss.carry_forward.timely_return",
        "loss.current_year.priority",
        "loss.speculation.targets",
        "loss.vda.no_setoff_or_carry",
    }
    for key in result.used_rule_keys:
        assert TABLE.get(key, date(2025, 6, 1)).confidence == "verified"


def test_current_business_rule_records_dtaa_other_sources_target():
    assert TABLE.get(
        "loss.business.current_year.targets",
        date(2025, 6, 1),
    ).value == (
        "business_income",
        "house_property_income",
        "capital_gain",
        "ordinary_other_sources",
        "dtaa_other_sources",
    )
