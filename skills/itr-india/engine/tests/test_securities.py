import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine.contracts import OfficialContractRegistry
from engine.securities import (
    SecurityLedgerError,
    SecurityReconciliationError,
    build_delivery_security_itr2_draft,
    compute_delivery_security_slice,
    load_security_ledger,
)


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
RELIANCE = "INE002A01018"


def _source(n):
    return {
        "source_document": f"inputs/broker-{n}.csv",
        "source_sha256": f"{n:064x}",
        "source_location": f"row:{n}",
        "importer": "security-fixture",
        "importer_version": "1.0.0",
    }


def _event(
    event_id,
    sequence,
    event_type,
    event_date,
    account_id,
    quantity,
    *,
    gross_amount="0",
    deductible_charges="0",
    stt="0",
    stt_paid=True,
    to_account_id=None,
    corporate_action=None,
    ratio_numerator=None,
    ratio_denominator=None,
    fmv_31jan2018_per_unit=None,
):
    return {
        "event_id": event_id,
        "sequence": sequence,
        "event_type": event_type,
        "event_date": event_date,
        "account_id": account_id,
        "to_account_id": to_account_id,
        "isin": RELIANCE,
        "quantity": quantity,
        "gross_amount": gross_amount,
        "deductible_charges": deductible_charges,
        "stt": stt,
        "stt_paid": stt_paid,
        "corporate_action": corporate_action,
        "ratio_numerator": ratio_numerator,
        "ratio_denominator": ratio_denominator,
        "fmv_31jan2018_per_unit": fmv_31jan2018_per_unit,
        "provenance": _source(sequence),
    }


def _ledger(events, summaries, *, treatment="investment"):
    return {
        "schema_version": "1.0",
        "assessment_year": "2026-27",
        "securities": [
            {
                "isin": RELIANCE,
                "security_name": "Reliance Industries Ltd",
                "tax_treatment": treatment,
            }
        ],
        "events": events,
        "broker_summaries": summaries,
    }


def _summary(account_id, gross_sales, closing_quantity):
    source_n = 90 if account_id == "demat-a" else 91
    return {
        "account_id": account_id,
        "gross_sale_proceeds": gross_sales,
        "closing_positions": [
            {
                "isin": RELIANCE,
                "quantity": closing_quantity,
                "provenance": _source(source_n + 10),
            }
        ],
        "provenance": _source(source_n),
    }


def _multi_demat_events():
    return [
        _event(
            "buy-old",
            1,
            "buy",
            "2024-05-01",
            "demat-a",
            "100",
            gross_amount="1000",
            deductible_charges="10",
            stt="5",
        ),
        _event(
            "transfer-a-b",
            2,
            "transfer",
            "2025-06-01",
            "demat-a",
            "40",
            to_account_id="demat-b",
        ),
        _event(
            "buy-new",
            3,
            "buy",
            "2025-07-01",
            "demat-a",
            "20",
            gross_amount="400",
        ),
        _event(
            "sell-a",
            4,
            "sell",
            "2025-08-01",
            "demat-a",
            "70",
            gross_amount="1400",
            deductible_charges="14",
            stt="7",
        ),
        _event(
            "sell-b",
            5,
            "sell",
            "2025-08-02",
            "demat-b",
            "20",
            gross_amount="500",
            deductible_charges="5",
            stt="2.5",
        ),
    ]


def test_account_fifo_and_linked_transfer_preserve_basis_and_dates():
    ledger = load_security_ledger(
        _ledger(
            _multi_demat_events(),
            [
                _summary("demat-a", "1400", "10"),
                _summary("demat-b", "500", "20"),
            ],
        )
    )

    result = compute_delivery_security_slice(ledger)

    assert result.short_term_gain == Decimal("-2")
    assert result.long_term_gain == Decimal("875")
    assert result.total_gain == Decimal("873")
    assert result.deductible_charges == Decimal("29")
    assert result.non_deductible_stt == Decimal("14.5")
    assert [
        (
            match.account_id,
            match.sale_event_id,
            match.acquisition_event_id,
            match.quantity,
            match.acquisition_date.isoformat(),
            match.cost_basis,
            match.gain,
        )
        for match in result.matched_disposals
    ] == [
        (
            "demat-a",
            "sell-a",
            "buy-old",
            Decimal("60"),
            "2024-05-01",
            Decimal("606"),
            Decimal("582"),
        ),
        (
            "demat-a",
            "sell-a",
            "buy-new",
            Decimal("10"),
            "2025-07-01",
            Decimal("200"),
            Decimal("-2"),
        ),
        (
            "demat-b",
            "sell-b",
            "buy-old",
            Decimal("20"),
            "2024-05-01",
            Decimal("202"),
            Decimal("293"),
        ),
    ]
    assert result.closing_positions == {
        ("demat-a", RELIANCE): Decimal("10"),
        ("demat-b", RELIANCE): Decimal("20"),
    }


def test_deductible_charges_reduce_gain_but_stt_never_does():
    events = [
        _event(
            "buy",
            1,
            "buy",
            "2025-05-01",
            "demat-a",
            "10",
            gross_amount="100",
            deductible_charges="10",
            stt="1000",
        ),
        _event(
            "sell",
            2,
            "sell",
            "2025-06-01",
            "demat-a",
            "10",
            gross_amount="200",
            deductible_charges="20",
            stt="2000",
        ),
    ]
    ledger = load_security_ledger(
        _ledger(events, [_summary("demat-a", "200", "0")])
    )

    result = compute_delivery_security_slice(ledger)

    assert result.total_gain == Decimal("70")
    assert result.deductible_charges == Decimal("30")
    assert result.non_deductible_stt == Decimal("3000")


def test_quantity_beyond_official_four_decimal_precision_is_rejected():
    events = [
        _event(
            "buy",
            1,
            "buy",
            "2025-05-01",
            "demat-a",
            "1.00001",
            gross_amount="100001",
        )
    ]

    with pytest.raises(SecurityLedgerError, match="decimal places"):
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "0", "1.00001")])
        )


def test_transfer_reorders_original_lots_in_destination_fifo_and_carries_charge():
    events = [
        _event(
            "buy-source-old",
            1,
            "buy",
            "2024-01-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
        _event(
            "buy-destination-new",
            2,
            "buy",
            "2025-05-01",
            "demat-b",
            "10",
            gross_amount="200",
        ),
        _event(
            "transfer",
            3,
            "transfer",
            "2025-06-01",
            "demat-a",
            "5",
            to_account_id="demat-b",
            deductible_charges="5",
        ),
        _event(
            "sell",
            4,
            "sell",
            "2025-07-01",
            "demat-b",
            "5",
            gross_amount="100",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(
                events,
                [
                    _summary("demat-a", "0", "5"),
                    _summary("demat-b", "100", "10"),
                ],
            )
        )
    )

    (match,) = result.matched_disposals
    assert match.acquisition_event_id == "buy-source-old"
    assert match.acquisition_date.isoformat() == "2024-01-01"
    assert match.cost_basis == Decimal("55")
    assert match.gain == Decimal("45")
    assert result.deductible_charges == Decimal("5")
    with pytest.raises(TypeError):
        result.closing_positions[("demat-a", RELIANCE)] = Decimal("999")


@pytest.mark.parametrize("treatment", ["unresolved", "business"])
def test_ambiguous_or_business_treatment_cannot_enter_schedule_cg(treatment):
    ledger = load_security_ledger(
        _ledger(
            _multi_demat_events(),
            [
                _summary("demat-a", "1400", "10"),
                _summary("demat-b", "500", "20"),
            ],
            treatment=treatment,
        )
    )

    with pytest.raises(SecurityReconciliationError) as caught:
        compute_delivery_security_slice(ledger)

    expected = (
        "AMBIGUOUS_TAX_TREATMENT"
        if treatment == "unresolved"
        else "BUSINESS_TREATMENT_REQUIRES_ITR3"
    )
    assert expected in caught.value.blocker_codes


def test_split_and_bonus_are_supported_but_merger_blocks():
    supported = [
        _event(
            "buy",
            1,
            "buy",
            "2024-01-01",
            "demat-a",
            "10",
            gross_amount="1000",
        ),
        _event(
            "split",
            2,
            "corporate_action",
            "2025-04-01",
            "demat-a",
            "0",
            corporate_action="split",
            ratio_numerator="2",
            ratio_denominator="1",
        ),
        _event(
            "bonus",
            3,
            "corporate_action",
            "2025-05-01",
            "demat-a",
            "0",
            corporate_action="bonus",
            ratio_numerator="1",
            ratio_denominator="1",
        ),
        _event(
            "sell",
            4,
            "sell",
            "2025-08-01",
            "demat-a",
            "25",
            gross_amount="2500",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(supported, [_summary("demat-a", "2500", "15")])
        )
    )

    assert result.closing_positions[("demat-a", RELIANCE)] == Decimal("15")
    assert result.total_gain == Decimal("1500")

    unsupported = supported[:1] + [
        _event(
            "merger",
            2,
            "corporate_action",
            "2025-04-01",
            "demat-a",
            "0",
            corporate_action="merger",
            ratio_numerator="1",
            ratio_denominator="1",
        )
    ]
    with pytest.raises(SecurityReconciliationError) as caught:
        compute_delivery_security_slice(
            load_security_ledger(
                _ledger(unsupported, [_summary("demat-a", "0", "10")])
            )
        )
    assert "UNSUPPORTED_CORPORATE_ACTION" in caught.value.blocker_codes


def test_pre_2018_bonus_carries_fmv_and_entitlement_provenance():
    events = [
        _event(
            "buy",
            1,
            "buy",
            "2017-01-01",
            "demat-a",
            "10",
            gross_amount="500",
            fmv_31jan2018_per_unit="50",
        ),
        _event(
            "bonus",
            2,
            "corporate_action",
            "2018-01-15",
            "demat-a",
            "0",
            corporate_action="bonus",
            ratio_numerator="1",
            ratio_denominator="1",
            fmv_31jan2018_per_unit="30",
        ),
        _event(
            "sell",
            3,
            "sell",
            "2025-08-01",
            "demat-a",
            "20",
            gross_amount="2000",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "2000", "0")])
        )
    )

    bonus_match = next(
        match
        for match in result.matched_disposals
        if match.acquisition_event_id == "bonus"
    )
    assert bonus_match.fair_market_value == Decimal("300")
    assert bonus_match.cost_basis == Decimal("300")
    assert bonus_match.gain == Decimal("700")
    assert {"row:1", "row:2", "row:3"} <= {
        source.source_location
        for source in bonus_match.source_provenance
    }


def test_pre_2018_lot_uses_grandfathered_cost_and_112a_disclosure():
    events = [
        _event(
            "buy-old",
            1,
            "buy",
            "2017-01-01",
            "demat-a",
            "10",
            gross_amount="500",
            fmv_31jan2018_per_unit="80",
        ),
        _event(
            "sell",
            2,
            "sell",
            "2025-08-01",
            "demat-a",
            "10",
            gross_amount="1000",
            deductible_charges="10",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "1000", "0")])
        )
    )

    (match,) = result.matched_disposals
    (detail,) = result.schedule_112a["Schedule112ADtls"]
    assert match.actual_cost_basis == Decimal("500")
    assert match.cost_basis == Decimal("800")
    assert match.fair_market_value == Decimal("800")
    assert match.gain == Decimal("190")
    assert detail["ShareOnOrBefore"] == "BE"
    assert detail["ISINCode"] == RELIANCE
    assert detail["CostAcqWithoutIndx"] == 800
    assert detail["AcquisitionCost"] == 500
    assert detail["LTCGBeforelowerB1B2"] == 800
    assert detail["FairMktValuePerShareunit"] == 80
    assert detail["TotFairMktValueCapAst"] == 800
    assert (
        detail["TotSaleValue"]
        == detail["NumSharesUnits"] * detail["SalePricePerShareUnit"]
    )
    assert detail["CostAcqWithoutIndx"] == max(
        detail["AcquisitionCost"],
        detail["LTCGBeforelowerB1B2"],
    )
    assert (
        detail["TotFairMktValueCapAst"]
        == detail["NumSharesUnits"] * detail["FairMktValuePerShareunit"]
    )
    assert detail["TotalDeductions"] == (
        detail["CostAcqWithoutIndx"]
        + detail["ExpExclCnctTransfer"]
    )
    assert detail["Balance"] == (
        detail["TotSaleValue"] - detail["TotalDeductions"]
    )
    assert result.schedule_112a["TotalBalance112A"] == 190


def test_broker_sale_and_closing_holding_mismatches_block():
    ledger = load_security_ledger(
        _ledger(
            _multi_demat_events(),
            [
                _summary("demat-a", "1401", "11"),
                _summary("demat-b", "500", "20"),
            ],
        )
    )

    with pytest.raises(SecurityReconciliationError) as caught:
        compute_delivery_security_slice(ledger)

    assert caught.value.blocker_codes == {
        "BROKER_CLOSING_POSITION_MISMATCH",
        "BROKER_SALE_PROCEEDS_MISMATCH",
    }
    for blocker in caught.value.blockers:
        assert blocker.evidence_references
        assert all("#row:" in ref for ref in blocker.evidence_references)


def test_schedule_cg_112a_and_draft_cross_tie_and_validate():
    ledger = load_security_ledger(
        _ledger(
            _multi_demat_events(),
            [
                _summary("demat-a", "1400", "10"),
                _summary("demat-b", "500", "20"),
            ],
        )
    )

    result = compute_delivery_security_slice(ledger)
    base = json.loads(
        (FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8")
    )
    draft = build_delivery_security_itr2_draft(base, result)

    assert result.schedule_112a["SaleValue112A"] == 1700
    assert result.schedule_112a["TotalBalance112A"] == 875
    assert (
        result.schedule_cg["ShortTermCapGainFor23"]["TotalSTCG"]
        == -2
    )
    assert result.schedule_cg["LongTermCapGain23"]["TotalLTCG"] == 875
    assert result.schedule_cg["TotScheduleCGFor23"] == 873
    losses = result.schedule_cg["CurrYrLosses"]
    assert losses["InLossSetOff"]["StclSetoff20Per"] == 2
    assert losses["InLtcg12_5Per"]["StclSetoff20Per"] == 2
    assert losses["TotLossSetOff"]["StclSetoff20Per"] == 2
    assert losses["LossRemainSetOff"]["StclSetoff20Per"] == 0
    for detail in result.schedule_112a["Schedule112ADtls"]:
        assert detail["ShareOnOrBefore"] == "AE"
        assert detail["NumSharesUnits"] == 0
        assert detail["SalePricePerShareUnit"] == 0
        assert detail["FairMktValuePerShareunit"] == 0
        assert detail["TotFairMktValueCapAst"] == 0
        assert detail["TotalDeductions"] == (
            detail["CostAcqWithoutIndx"]
            + detail["ExpExclCnctTransfer"]
        )
        assert detail["Balance"] == (
            detail["TotSaleValue"] - detail["TotalDeductions"]
        )
    assert draft["ITR"]["ITR2"]["Schedule112A"]["TotalBalance112A"] == 875
    assert (
        draft["ITR"]["ITR2"]["ScheduleCGFor23"]["TotScheduleCGFor23"]
        == 873
    )
    trace_by_path = {line.output_path: line for line in result.audit_trace}
    for path in (
        "/ITR/ITR2/Schedule112A/SaleValue112A",
        "/ITR/ITR2/Schedule112A/TotalBalance112A",
        "/ITR/ITR2/ScheduleCGFor23/ShortTermCapGainFor23/TotalSTCG",
        "/ITR/ITR2/ScheduleCGFor23/LongTermCapGain23/TotalLTCG",
        "/ITR/ITR2/ScheduleCGFor23/TotScheduleCGFor23",
    ):
        assert path in trace_by_path
        assert trace_by_path[path].sale_event_ids
        assert trace_by_path[path].evidence_references
        assert trace_by_path[path].source_provenance
        assert all(
            len(source.source_sha256) == 64
            and source.importer == "security-fixture"
            and source.importer_version == "1.0.0"
            for source in trace_by_path[path].source_provenance
        )
    sale_trace_sources = trace_by_path[
        "/ITR/ITR2/Schedule112A/SaleValue112A"
    ].source_provenance
    assert any(
        source.source_location in {"row:90", "row:91"}
        for source in sale_trace_sources
    )
    assert any(
        source.source_location in {"row:100", "row:101"}
        for source in sale_trace_sources
    )
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-2",
        draft,
    )


def test_long_term_loss_cannot_offset_short_term_gain():
    events = [
        _event(
            "buy-long",
            1,
            "buy",
            "2024-01-01",
            "demat-a",
            "10",
            gross_amount="300",
        ),
        _event(
            "sell-long",
            2,
            "sell",
            "2025-05-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
        _event(
            "buy-short",
            3,
            "buy",
            "2025-06-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
        _event(
            "sell-short",
            4,
            "sell",
            "2025-07-01",
            "demat-a",
            "10",
            gross_amount="200",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "300", "0")])
        )
    )

    assert result.schedule_cg["ShortTermCapGainFor23"]["TotalSTCG"] == 100
    assert result.schedule_cg["LongTermCapGain23"]["TotalLTCG"] == -200
    assert result.schedule_cg["TotScheduleCGFor23"] == 100
    assert (
        result.schedule_cg["CurrYrLosses"]["LossRemainSetOff"][
            "LtclSetOff12_5Per"
        ]
        == 200
    )
    losses = result.schedule_cg["CurrYrLosses"]
    assert losses["InLossSetOff"]["LtclSetOff12_5Per"] == 200
    assert losses["TotLossSetOff"]["LtclSetOff12_5Per"] == 0
    assert (
        losses["InLossSetOff"]["LtclSetOff12_5Per"]
        - losses["TotLossSetOff"]["LtclSetOff12_5Per"]
        == losses["LossRemainSetOff"]["LtclSetOff12_5Per"]
    )
    trace = {line.output_path: line for line in result.audit_trace}
    assert trace[
        "/ITR/ITR2/ScheduleCGFor23/TotScheduleCGFor23"
    ].amount == Decimal("100")
    assert trace[
        (
            "/ITR/ITR2/ScheduleCGFor23/CurrYrLosses/"
            "LossRemainSetOff/LtclSetOff12_5Per"
        )
    ].amount == Decimal("200")
    base = json.loads(
        (FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8")
    )
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-2",
        build_delivery_security_itr2_draft(base, result),
    )


def test_rounding_is_allocated_so_schedule_totals_cross_tie():
    events = [
        _event(
            "buy-long-1",
            1,
            "buy",
            "2024-01-01",
            "demat-a",
            "1",
            gross_amount="1",
        ),
        _event(
            "buy-long-2",
            2,
            "buy",
            "2024-01-02",
            "demat-a",
            "1",
            gross_amount="1",
        ),
        _event(
            "sell-long",
            3,
            "sell",
            "2025-05-01",
            "demat-a",
            "2",
            gross_amount="2.5",
        ),
        _event(
            "buy-short",
            4,
            "buy",
            "2025-06-01",
            "demat-a",
            "2",
            gross_amount="2",
        ),
        _event(
            "sell-short",
            5,
            "sell",
            "2025-07-01",
            "demat-a",
            "2",
            gross_amount="2.5",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "5", "0")])
        )
    )

    details = result.schedule_112a["Schedule112ADtls"]
    assert sum(detail["Balance"] for detail in details) == 1
    assert result.schedule_112a["TotalBalance112A"] == 1
    assert all(
        detail["Balance"]
        == detail["TotSaleValue"] - detail["TotalDeductions"]
        for detail in details
    )
    short_gain = result.schedule_cg["ShortTermCapGainFor23"]["TotalSTCG"]
    long_gain = result.schedule_cg["LongTermCapGain23"]["TotalLTCG"]
    assert (short_gain, long_gain) == (0, 1)
    assert result.schedule_cg["TotScheduleCGFor23"] == 1
    short_detail = result.schedule_cg["ShortTermCapGainFor23"][
        "EquityMFonSTT"
    ][0]["EquityMFonSTTDtls"]
    assert short_detail["BalanceCG"] == (
        short_detail["FullConsideration"]
        - short_detail["DeductSec48"]["TotalDedn"]
    )


def test_partial_short_term_loss_setoff_preserves_loss_row_identity():
    events = [
        _event(
            "buy-long",
            1,
            "buy",
            "2024-01-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
        _event(
            "sell-long",
            2,
            "sell",
            "2025-05-01",
            "demat-a",
            "10",
            gross_amount="200",
        ),
        _event(
            "buy-short",
            3,
            "buy",
            "2025-06-01",
            "demat-a",
            "10",
            gross_amount="300",
        ),
        _event(
            "sell-short",
            4,
            "sell",
            "2025-07-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "300", "0")])
        )
    )

    losses = result.schedule_cg["CurrYrLosses"]
    assert losses["InLossSetOff"]["StclSetoff20Per"] == 200
    assert losses["TotLossSetOff"]["StclSetoff20Per"] == 100
    assert losses["LossRemainSetOff"]["StclSetoff20Per"] == 100
    assert (
        losses["InLossSetOff"]["StclSetoff20Per"]
        - losses["TotLossSetOff"]["StclSetoff20Per"]
        == losses["LossRemainSetOff"]["StclSetoff20Per"]
    )
    assert result.schedule_cg["TotScheduleCGFor23"] == 0
    long_ranges = result.schedule_cg["AccruOrRecOfCG"][
        "LongTermUnder12_5Per"
    ]["DateRange"]
    assert sum(long_ranges.values()) == 0


def test_table_f_nets_dated_losses_and_ties_to_current_year_gain():
    events = [
        _event(
            "buy-gain",
            1,
            "buy",
            "2025-05-01",
            "demat-a",
            "10",
            gross_amount="100",
        ),
        _event(
            "sell-gain",
            2,
            "sell",
            "2025-06-01",
            "demat-a",
            "10",
            gross_amount="200",
        ),
        _event(
            "buy-loss",
            3,
            "buy",
            "2025-06-20",
            "demat-a",
            "10",
            gross_amount="200",
        ),
        _event(
            "sell-loss",
            4,
            "sell",
            "2025-07-01",
            "demat-a",
            "10",
            gross_amount="150",
        ),
    ]
    result = compute_delivery_security_slice(
        load_security_ledger(
            _ledger(events, [_summary("demat-a", "350", "0")])
        )
    )

    losses = result.schedule_cg["CurrYrLosses"]
    ranges = result.schedule_cg["AccruOrRecOfCG"][
        "ShortTermUnder20Per"
    ]["DateRange"]
    assert losses["InStcg20Per"]["CurrYrCapGain"] == 50
    assert sum(ranges.values()) == 50
