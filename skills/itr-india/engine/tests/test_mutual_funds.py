from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from engine.mutual_funds import (
    FundClassificationDecision,
    FundTaxBucket,
    MutualFundLedgerError,
    MutualFundReconciliationError,
    StatutoryFundClass,
    compute_mutual_fund_slice,
    load_mutual_fund_ledger,
)
from engine.readiness import (
    BlockerCategory,
    BlockerOverridePolicy,
    DecisionAction,
    DecisionJournal,
    FilingReadiness,
    HumanDecision,
)


SCHEME = "INF000000001"
SCHEME_2 = "INF000000002"


def _source(n):
    return {
        "source_document": f"inputs/fund-{n}.json",
        "source_sha256": f"{n:064x}",
        "source_location": f"item:{n}",
        "importer": "mutual-fund-fixture",
        "importer_version": "1.0.0",
    }


def _primary_evidence(
    *,
    domestic_equity_percentage=None,
    debt_money_market_percentage=None,
    structure="direct",
    underlying_fund_percentage=None,
    underlying_domestic_equity_percentage=None,
    specified_fund_units_percentage=None,
    equity_averaging_method=None,
    debt_averaging_method=None,
    underlying_exchange_traded=None,
):
    if equity_averaging_method is None and (
        domestic_equity_percentage is not None
        or underlying_domestic_equity_percentage is not None
    ):
        equity_averaging_method = "annual_average_monthly_opening_closing"
    if debt_averaging_method is None and (
        debt_money_market_percentage is not None
        or specified_fund_units_percentage is not None
    ):
        debt_averaging_method = "annual_average_daily_closing"
    if underlying_exchange_traded is None and structure == "fund_of_funds":
        underlying_exchange_traded = True
    return {
        "evidence_id": "classification-1",
        "authority": "amc",
        "period_start": "2025-04-01",
        "period_end": "2026-03-31",
        "structure": structure,
        "domestic_equity_percentage": domestic_equity_percentage,
        "debt_money_market_percentage": debt_money_market_percentage,
        "underlying_fund_percentage": underlying_fund_percentage,
        "underlying_domestic_equity_percentage": (
            underlying_domestic_equity_percentage
        ),
        "specified_fund_units_percentage": specified_fund_units_percentage,
        "equity_averaging_method": equity_averaging_method,
        "debt_averaging_method": debt_averaging_method,
        "underlying_exchange_traded": underlying_exchange_traded,
        "provenance": _source(10),
    }


def _event(
    event_id,
    sequence,
    event_type,
    event_date,
    quantity,
    *,
    gross_amount="0",
    charges="0",
    stt_paid=False,
    stt_status=None,
    switch_id=None,
    scheme_id=SCHEME,
    account_id="folio-a",
    to_account_id=None,
    fmv_31jan2018_per_unit=None,
):
    if stt_status is None and event_type in {
        "sale",
        "redemption",
        "switch_out",
    }:
        stt_status = "paid" if stt_paid else "unknown"
    return {
        "event_id": event_id,
        "sequence": sequence,
        "event_type": event_type,
        "event_date": event_date,
        "account_id": account_id,
        "to_account_id": to_account_id,
        "scheme_id": scheme_id,
        "quantity": quantity,
        "gross_amount": gross_amount,
        "deductible_charges": charges,
        "stt_status": stt_status,
        "switch_id": switch_id,
        "fmv_31jan2018_per_unit": fmv_31jan2018_per_unit,
        "provenance": _source(sequence),
    }


def _ledger(*, evidence, events):
    return {
        "schema_version": "1.0",
        "assessment_year": "2026-27",
        "schemes": [
            {
                "scheme_id": SCHEME,
                "scheme_name": "Definitely Debt Marketing Name",
                "listing": {
                    "exchange_listed": False,
                    "provenance": _source(12),
                },
                "classification_evidence": (
                    [] if evidence is None else [evidence]
                ),
            }
        ],
        "events": events,
        "account_summaries": [
            {
                "account_id": "folio-a",
                "gross_disposal_proceeds": "1500",
                "closing_positions": [
                    {
                        "scheme_id": SCHEME,
                        "quantity": "0",
                        "provenance": _source(91),
                    }
                ],
                "provenance": _source(90),
            }
        ],
    }


def _risk_decision_for_first_blocker(result):
    blocker = result.readiness.blockers[0]
    decision = HumanDecision(
        decision_id="mf-decision-1",
        blocker_id=blocker.blocker_id,
        action=DecisionAction.ACCEPT_RISK,
        actor="taxpayer",
        decided_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
        reason="Reviewed the unresolved classification evidence.",
        evidence_references=("human-note.md#mutual-fund-classification",),
        affected_outputs=blocker.affected_outputs,
        context_fingerprint=result.readiness.context_fingerprint,
    )
    return DecisionJournal.empty("ay2026-27:mutual-funds").append(decision)


def _classification_decision(
    result,
    *,
    classification,
    disposal_event_id,
    effective_from="2025-04-01",
    effective_to="2026-03-31",
):
    blocker = result.readiness.blockers[0]
    if isinstance(effective_from, str):
        effective_from = date.fromisoformat(effective_from)
    if isinstance(effective_to, str):
        effective_to = date.fromisoformat(effective_to)
    decision = FundClassificationDecision(
        decision_id="mf-classification-1",
        blocker_id=blocker.blocker_id,
        action=DecisionAction.CONFIRM_CLASSIFICATION,
        actor="taxpayer",
        decided_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
        reason="Confirmed the scheme tax class from the retained evidence.",
        evidence_references=("human-note.md#mutual-fund-classification",),
        affected_outputs=blocker.affected_outputs,
        context_fingerprint=result.readiness.context_fingerprint,
        scheme_id=SCHEME,
        effective_from=effective_from,
        effective_to=effective_to,
        classification=classification,
        disposal_event_ids=(disposal_event_id,),
    )
    return DecisionJournal.empty("ay2026-27:mutual-funds").append(decision)


def test_primary_composition_evidence_not_scheme_name_drives_classification():
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=_primary_evidence(
                domestic_equity_percentage="70",
                debt_money_market_percentage="20",
            ),
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2024-01-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                    stt_paid=True,
                ),
            ],
        )
    )

    result = compute_mutual_fund_slice(ledger)

    assert result.classifications[SCHEME] is StatutoryFundClass.EQUITY_ORIENTED
    assert result.bucket_totals == {
        FundTaxBucket.LTCG_112A: Decimal("500")
    }
    assert result.independently_ready
    assert not result.blockers
    assert result.filing_values == {
        "ScheduleCG": {
            "STCG111A": Decimal("0"),
            "LTCG112A": Decimal("500"),
            "STCG50AA": Decimal("0"),
            "STCGOther": Decimal("0"),
            "LTCG112": Decimal("0"),
            "Total": Decimal("500"),
        }
    }
    trace = {
        line.output_path: line
        for line in result.audit_trace
    }["/ScheduleCG/LTCG112A"]
    assert trace.amount == Decimal("500")
    assert trace.acquisition_event_ids == ("purchase",)
    assert trace.disposal_event_ids == ("sale",)
    assert {
        "item:1",
        "item:2",
        "item:10",
        "item:12",
        "item:90",
        "item:91",
    } <= {
        source.source_location for source in trace.source_provenance
    }
    with pytest.raises(TypeError):
        result.filing_values["ScheduleCG"]["Total"] = Decimal("999")


@pytest.mark.parametrize(
    ("evidence", "expected_classification", "expected_bucket"),
    [
        (
            _primary_evidence(
                domestic_equity_percentage="10",
                debt_money_market_percentage="66",
            ),
            StatutoryFundClass.SPECIFIED_MUTUAL_FUND,
            FundTaxBucket.STCG_50AA,
        ),
        (
            _primary_evidence(
                domestic_equity_percentage="40",
                debt_money_market_percentage="65",
            ),
            StatutoryFundClass.OTHER_MUTUAL_FUND,
            FundTaxBucket.LTCG_112,
        ),
        (
            _primary_evidence(
                structure="fund_of_funds",
                underlying_fund_percentage="90",
                underlying_domestic_equity_percentage="90",
                specified_fund_units_percentage="10",
            ),
            StatutoryFundClass.EQUITY_ORIENTED,
            FundTaxBucket.LTCG_112A,
        ),
        (
            _primary_evidence(
                structure="fund_of_funds",
                underlying_fund_percentage="80",
                underlying_domestic_equity_percentage="80",
                specified_fund_units_percentage="65",
            ),
            StatutoryFundClass.SPECIFIED_MUTUAL_FUND,
            FundTaxBucket.STCG_50AA,
        ),
    ],
)
def test_statutory_percentage_boundaries_cover_direct_and_fund_of_funds(
    evidence,
    expected_classification,
    expected_bucket,
):
    result = compute_mutual_fund_slice(
        load_mutual_fund_ledger(
            _ledger(
                evidence=evidence,
                events=[
                    _event(
                        "purchase",
                        1,
                        "purchase",
                        "2023-04-01",
                        "10",
                        gross_amount="1000",
                    ),
                    _event(
                        "sale",
                        2,
                        "sale",
                        "2025-05-02",
                        "10",
                        gross_amount="1500",
                        stt_paid=(
                            expected_classification
                            is StatutoryFundClass.EQUITY_ORIENTED
                        ),
                    ),
                ],
            )
        )
    )

    assert result.classifications[SCHEME] is expected_classification
    assert result.bucket_totals == {expected_bucket: Decimal("500")}


def test_missing_primary_evidence_emits_research_manifest_and_blocks_readiness():
    result = compute_mutual_fund_slice(
        load_mutual_fund_ledger(
            _ledger(
                evidence=None,
                events=[
                    _event(
                        "purchase",
                        1,
                        "purchase",
                        "2024-01-01",
                        "10",
                        gross_amount="1000",
                    ),
                    _event(
                        "sale",
                        2,
                        "sale",
                        "2025-05-02",
                        "10",
                        gross_amount="1500",
                    ),
                ],
            )
        )
    )

    assert not result.independently_ready
    assert {blocker.code for blocker in result.blockers} == {
        "MISSING_PRIMARY_CLASSIFICATION_EVIDENCE"
    }
    (request,) = result.research_manifest
    assert request.scheme_id == SCHEME
    assert request.sale_dates == ("2025-05-02",)
    assert request.required_facts == (
        "domestic_equity_percentage",
        "debt_money_market_percentage",
        "fund_structure_and_underlying_percentages",
    )
    assert result.bucket_totals == {}


def test_human_confirmation_uses_journal_without_rewriting_computed_amounts():
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=None,
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2023-04-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "redemption",
                    2,
                    "redemption",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                ),
            ],
        )
    )
    unresolved = compute_mutual_fund_slice(ledger)
    journal = _classification_decision(
        unresolved,
        classification=StatutoryFundClass.SPECIFIED_MUTUAL_FUND,
        disposal_event_id="redemption",
    )
    assert "specified_mutual_fund" in journal.canonical_json()

    overridden = compute_mutual_fund_slice(
        ledger,
        decision_journal=journal,
    )

    assert overridden.classifications == {}
    assert overridden.bucket_totals == unresolved.bucket_totals == {}
    assert not overridden.independently_ready
    assert overridden.readiness.state is (
        FilingReadiness.BLOCKED
    )
    assert overridden.readiness.blockers == unresolved.readiness.blockers
    assert overridden.provisional_bucket_totals == {
        FundTaxBucket.STCG_50AA: Decimal("500")
    }
    assert overridden.applied_classification_decision_ids == (
        "mf-classification-1",
    )
    assert overridden.research_manifest[0].scheme_id == SCHEME


def test_classification_confirmation_rejects_datetime_effective_boundary():
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=None,
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2024-01-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                ),
            ],
        )
    )
    unresolved = compute_mutual_fund_slice(ledger)

    with pytest.raises(ValueError, match="date values"):
        _classification_decision(
            unresolved,
            classification=StatutoryFundClass.OTHER_MUTUAL_FUND,
            disposal_event_id="sale",
            effective_from=datetime(
                2025,
                4,
                1,
                tzinfo=timezone.utc,
            ),
        )


def test_missing_classification_risk_acceptance_cannot_understate_a_ready_return():
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=None,
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2024-01-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                ),
            ],
        )
    )
    unresolved = compute_mutual_fund_slice(ledger)

    attempted_override = compute_mutual_fund_slice(
        ledger,
        decision_journal=_risk_decision_for_first_blocker(unresolved),
    )

    assert attempted_override.readiness.state is FilingReadiness.BLOCKED
    assert attempted_override.readiness.applied_decision_ids == ()
    assert [
        finding.code
        for finding in attempted_override.readiness.decision_findings
    ] == ["NON_OVERRIDABLE_BLOCKER"]


def test_incomplete_primary_composition_facts_remain_unresolved():
    result = compute_mutual_fund_slice(
        load_mutual_fund_ledger(
            _ledger(
                evidence=_primary_evidence(
                    domestic_equity_percentage="10",
                    debt_money_market_percentage=None,
                ),
                events=[
                    _event(
                        "purchase",
                        1,
                        "purchase",
                        "2024-01-01",
                        "10",
                        gross_amount="1000",
                    ),
                    _event(
                        "sale",
                        2,
                        "sale",
                        "2025-05-02",
                        "10",
                        gross_amount="1500",
                    ),
                ],
            )
        )
    )

    assert not result.independently_ready
    assert {blocker.code for blocker in result.blockers} == {
        "INCOMPLETE_PRIMARY_CLASSIFICATION_EVIDENCE"
    }
    assert result.research_manifest[0].required_facts == (
        "debt_money_market_percentage",
    )
    assert result.bucket_totals == {}


def test_debt_percentage_with_wrong_averaging_method_cannot_classify():
    evidence = _primary_evidence(
        domestic_equity_percentage="10",
        debt_money_market_percentage="70",
    )
    evidence["debt_averaging_method"] = (
        "annual_average_monthly_opening_closing"
    )
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=evidence,
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2023-04-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                ),
            ],
        )
    )
    result = compute_mutual_fund_slice(ledger)

    assert not result.independently_ready
    assert {blocker.code for blocker in result.blockers} == {
        "INVALID_CLASSIFICATION_AVERAGING_METHOD"
    }
    assert result.bucket_totals == {}
    (structured,) = result.readiness.blockers
    assert structured.category is BlockerCategory.INTEGRITY_FAILURE
    assert structured.override_policy is BlockerOverridePolicy.PROHIBITED
    attempted_override = compute_mutual_fund_slice(
        ledger,
        decision_journal=_risk_decision_for_first_blocker(result),
    )
    assert attempted_override.readiness.state is FilingReadiness.BLOCKED
    assert [
        finding.code
        for finding in attempted_override.readiness.decision_findings
    ] == ["NON_OVERRIDABLE_BLOCKER"]


def test_switch_out_is_disposal_and_switch_in_starts_a_new_fifo_lot():
    evidence = _primary_evidence(
        domestic_equity_percentage="70",
        debt_money_market_percentage="20",
    )
    data = _ledger(
        evidence=evidence,
        events=[
            _event(
                "purchase-a",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "switch-out-a",
                2,
                "switch_out",
                "2025-05-02",
                "10",
                gross_amount="1500",
                charges="10",
                stt_paid=True,
                switch_id="switch-1",
            ),
            _event(
                "switch-in-b",
                3,
                "switch_in",
                "2025-05-02",
                "15",
                gross_amount="1490",
                switch_id="switch-1",
                scheme_id=SCHEME_2,
            ),
            _event(
                "sale-b",
                4,
                "sale",
                "2025-06-02",
                "15",
                gross_amount="1600",
                stt_paid=True,
                scheme_id=SCHEME_2,
            ),
        ],
    )
    data["schemes"].append(
        {
            "scheme_id": SCHEME_2,
            "scheme_name": "Destination Equity Fund",
            "listing": {
                "exchange_listed": False,
                "provenance": _source(13),
            },
            "classification_evidence": [evidence],
        }
    )
    data["account_summaries"][0]["gross_disposal_proceeds"] = "3100"
    data["account_summaries"][0]["closing_positions"].append(
        {
            "scheme_id": SCHEME_2,
            "quantity": "0",
            "provenance": _source(92),
        }
    )

    ledger = load_mutual_fund_ledger(data)
    result = compute_mutual_fund_slice(ledger)

    assert result.bucket_totals == {
        FundTaxBucket.LTCG_112A: Decimal("490"),
        FundTaxBucket.STCG_111A: Decimal("110"),
    }
    assert [
        (
            match.disposal_event_id,
            match.acquisition_event_id,
            match.acquisition_date.isoformat(),
            match.gain,
        )
        for match in result.matched_disposals
    ] == [
        ("switch-out-a", "purchase-a", "2024-01-01", Decimal("490")),
        ("sale-b", "switch-in-b", "2025-05-02", Decimal("110")),
    ]


def test_switch_legs_must_reconcile_net_consideration():
    evidence = _primary_evidence(
        domestic_equity_percentage="70",
        debt_money_market_percentage="20",
    )
    data = _ledger(
        evidence=evidence,
        events=[
            _event(
                "purchase-a",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "switch-out-a",
                2,
                "switch_out",
                "2025-05-02",
                "10",
                gross_amount="1500",
                charges="10",
                stt_paid=True,
                switch_id="switch-1",
            ),
            _event(
                "switch-in-b",
                3,
                "switch_in",
                "2025-05-02",
                "15",
                gross_amount="1489",
                switch_id="switch-1",
                scheme_id=SCHEME_2,
            ),
        ],
    )
    data["schemes"].append(
        {
            "scheme_id": SCHEME_2,
            "scheme_name": "Destination Equity Fund",
            "listing": {
                "exchange_listed": False,
                "provenance": _source(13),
            },
            "classification_evidence": [evidence],
        }
    )

    with pytest.raises(MutualFundReconciliationError) as caught:
        compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    assert caught.value.blocker_codes == {
        "SWITCH_CONSIDERATION_MISMATCH"
    }
    assert len(caught.value.blockers[0].evidence_references) == 2


def test_own_folio_transfer_preserves_original_lot_and_account_local_fifo():
    evidence = _primary_evidence(
        domestic_equity_percentage="70",
        debt_money_market_percentage="20",
    )
    data = _ledger(
        evidence=evidence,
        events=[
            _event(
                "buy-old-a",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
                account_id="folio-a",
            ),
            _event(
                "buy-new-b",
                2,
                "purchase",
                "2025-04-01",
                "10",
                gross_amount="2000",
                account_id="folio-b",
            ),
            _event(
                "transfer-a-b",
                3,
                "transfer",
                "2025-04-10",
                "5",
                charges="5",
                account_id="folio-a",
                to_account_id="folio-b",
            ),
            _event(
                "sale-b",
                4,
                "sale",
                "2025-05-02",
                "5",
                gross_amount="1500",
                stt_paid=True,
                account_id="folio-b",
            ),
        ],
    )
    data["account_summaries"][0]["gross_disposal_proceeds"] = "0"
    data["account_summaries"][0]["closing_positions"][0]["quantity"] = "5"
    data["account_summaries"].append(
        {
            "account_id": "folio-b",
            "gross_disposal_proceeds": "1500",
            "closing_positions": [
                {
                    "scheme_id": SCHEME,
                    "quantity": "10",
                    "provenance": _source(93),
                }
            ],
            "provenance": _source(94),
        }
    )

    ledger = load_mutual_fund_ledger(data)
    result = compute_mutual_fund_slice(ledger)

    (match,) = result.matched_disposals
    assert match.acquisition_event_id == "buy-old-a"
    assert match.acquisition_date.isoformat() == "2024-01-01"
    assert match.cost_basis == Decimal("505")
    assert match.gain == Decimal("995")
    assert match.tax_bucket is FundTaxBucket.LTCG_112A
    assert result.closing_positions == {
        ("folio-a", SCHEME): Decimal("5"),
        ("folio-b", SCHEME): Decimal("10"),
    }
    with pytest.raises(TypeError):
        result.closing_positions[("folio-a", SCHEME)] = Decimal("999")


def test_account_sale_and_closing_position_summaries_must_reconcile():
    data = _ledger(
        evidence=_primary_evidence(
            domestic_equity_percentage="70",
            debt_money_market_percentage="20",
        ),
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale",
                2,
                "sale",
                "2025-05-02",
                "10",
                gross_amount="1500",
                stt_paid=True,
            ),
        ],
    )
    data["account_summaries"][0]["gross_disposal_proceeds"] = "1501"
    data["account_summaries"][0]["closing_positions"][0]["quantity"] = "1"

    with pytest.raises(MutualFundReconciliationError) as caught:
        compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    assert caught.value.blocker_codes == {
        "ACCOUNT_DISPOSAL_PROCEEDS_MISMATCH",
        "ACCOUNT_CLOSING_POSITION_MISMATCH",
    }
    assert all(
        blocker.evidence_references
        for blocker in caught.value.blockers
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unknown_scheme", "unknown scheme"),
        ("duplicate_event", "event_id values must be unique"),
        ("outside_fy_disposal", "disposal must fall within FY 2025-26"),
    ],
)
def test_ledger_rejects_structurally_invalid_fund_events(mutation, message):
    data = _ledger(
        evidence=_primary_evidence(
            domestic_equity_percentage="70",
            debt_money_market_percentage="20",
        ),
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale",
                2,
                "sale",
                "2025-05-02",
                "10",
                gross_amount="1500",
                stt_paid=True,
            ),
        ],
    )
    if mutation == "unknown_scheme":
        data["events"][1]["scheme_id"] = SCHEME_2
    elif mutation == "duplicate_event":
        data["events"][1]["event_id"] = "purchase"
    else:
        data["events"][1]["event_date"] = "2026-04-01"

    with pytest.raises(MutualFundLedgerError, match=message):
        load_mutual_fund_ledger(data)


def test_equity_oriented_disposal_without_stt_evidence_blocks_special_bucket():
    result = compute_mutual_fund_slice(
        load_mutual_fund_ledger(
            _ledger(
                evidence=_primary_evidence(
                    domestic_equity_percentage="70",
                    debt_money_market_percentage="20",
                ),
                events=[
                    _event(
                        "purchase",
                        1,
                        "purchase",
                        "2024-01-01",
                        "10",
                        gross_amount="1000",
                    ),
                    _event(
                        "sale",
                        2,
                        "sale",
                        "2025-05-02",
                        "10",
                        gross_amount="1500",
                        stt_paid=False,
                    ),
                ],
            )
        )
    )

    assert result.classifications[SCHEME] is StatutoryFundClass.EQUITY_ORIENTED
    assert result.bucket_totals == {}
    assert not result.independently_ready
    assert {blocker.code for blocker in result.blockers} == {
        "MISSING_EQUITY_FUND_STT_EVIDENCE"
    }
    assert result.research_manifest[0].required_facts == (
        "stt_on_transfer",
    )


@pytest.mark.parametrize(
    ("acquisition_date", "expected_bucket"),
    [
        ("2025-04-01", FundTaxBucket.STCG_SLAB),
        ("2024-04-01", FundTaxBucket.LTCG_112),
    ],
)
def test_known_non_stt_equity_disposal_uses_ordinary_tax_bucket(
    acquisition_date,
    expected_bucket,
):
    result = compute_mutual_fund_slice(
        load_mutual_fund_ledger(
            _ledger(
                evidence=_primary_evidence(
                    domestic_equity_percentage="70",
                    debt_money_market_percentage="20",
                ),
                events=[
                    _event(
                        "purchase",
                        1,
                        "purchase",
                        acquisition_date,
                        "10",
                        gross_amount="1000",
                    ),
                    _event(
                        "sale",
                        2,
                        "sale",
                        "2025-05-02",
                        "10",
                        gross_amount="1500",
                        stt_status="not_paid",
                    ),
                ],
            )
        )
    )

    assert result.independently_ready
    assert result.bucket_totals == {expected_bucket: Decimal("500")}
    assert not result.blockers


def test_pre_2018_equity_fund_lot_uses_grandfathered_cost():
    data = _ledger(
        evidence=_primary_evidence(
            domestic_equity_percentage="70",
            debt_money_market_percentage="20",
        ),
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                "2017-01-01",
                "10",
                gross_amount="500",
                fmv_31jan2018_per_unit="80",
            ),
            _event(
                "sale",
                2,
                "sale",
                "2025-05-02",
                "10",
                gross_amount="1000",
                charges="10",
                stt_paid=True,
            ),
        ],
    )
    data["account_summaries"][0]["gross_disposal_proceeds"] = "1000"
    result = compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    (match,) = result.matched_disposals
    assert match.cost_basis == Decimal("800")
    assert match.gain == Decimal("190")
    assert match.tax_bucket is FundTaxBucket.LTCG_112A


@pytest.mark.parametrize(
    (
        "evidence",
        "exchange_listed",
        "acquisition_date",
        "sale_date",
        "expected_bucket",
    ),
    [
        (
            _primary_evidence(
                domestic_equity_percentage="10",
                debt_money_market_percentage="70",
            ),
            False,
            "2023-03-31",
            "2025-04-01",
            FundTaxBucket.LTCG_112,
        ),
        (
            _primary_evidence(
                domestic_equity_percentage="10",
                debt_money_market_percentage="70",
            ),
            False,
            "2023-04-01",
            "2025-04-01",
            FundTaxBucket.STCG_50AA,
        ),
        (
            _primary_evidence(
                domestic_equity_percentage="20",
                debt_money_market_percentage="20",
            ),
            True,
            "2024-04-01",
            "2025-04-01",
            FundTaxBucket.STCG_SLAB,
        ),
        (
            _primary_evidence(
                domestic_equity_percentage="20",
                debt_money_market_percentage="20",
            ),
            True,
            "2024-04-01",
            "2025-04-02",
            FundTaxBucket.LTCG_112,
        ),
    ],
)
def test_section_50aa_cutoff_and_listed_unit_holding_boundaries(
    evidence,
    exchange_listed,
    acquisition_date,
    sale_date,
    expected_bucket,
):
    data = _ledger(
        evidence=evidence,
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                acquisition_date,
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale",
                2,
                "sale",
                sale_date,
                "10",
                gross_amount="1500",
            ),
        ],
    )
    data["schemes"][0]["listing"]["exchange_listed"] = exchange_listed

    result = compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    assert result.bucket_totals == {expected_bucket: Decimal("500")}


def test_conflicting_primary_classification_evidence_blocks_independent_result():
    equity = _primary_evidence(
        domestic_equity_percentage="70",
        debt_money_market_percentage="20",
    )
    debt = _primary_evidence(
        domestic_equity_percentage="10",
        debt_money_market_percentage="70",
    )
    debt["evidence_id"] = "classification-2"
    debt["provenance"] = _source(11)
    data = _ledger(
        evidence=equity,
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale",
                2,
                "sale",
                "2025-05-02",
                "10",
                gross_amount="1500",
                stt_paid=True,
            ),
        ],
    )
    data["schemes"][0]["classification_evidence"].append(debt)

    ledger = load_mutual_fund_ledger(data)
    result = compute_mutual_fund_slice(ledger)

    assert SCHEME not in result.classifications
    assert result.bucket_totals == {}
    assert not result.independently_ready
    assert {blocker.code for blocker in result.blockers} == {
        "CONFLICTING_PRIMARY_CLASSIFICATION_EVIDENCE"
    }
    assert len(result.blockers[0].evidence_references) == 3
    (structured,) = result.readiness.blockers
    assert structured.category is BlockerCategory.INTEGRITY_FAILURE
    assert structured.override_policy is BlockerOverridePolicy.PROHIBITED
    attempted_override = compute_mutual_fund_slice(
        ledger,
        decision_journal=_risk_decision_for_first_blocker(result),
    )
    assert attempted_override.readiness.state is FilingReadiness.BLOCKED
    assert [
        finding.code
        for finding in attempted_override.readiness.decision_findings
    ] == ["NON_OVERRIDABLE_BLOCKER"]


def test_human_acceptance_of_incomplete_facts_keeps_original_blocker_visible():
    ledger = load_mutual_fund_ledger(
        _ledger(
            evidence=_primary_evidence(
                domestic_equity_percentage="10",
                debt_money_market_percentage=None,
            ),
            events=[
                _event(
                    "purchase",
                    1,
                    "purchase",
                    "2024-01-01",
                    "10",
                    gross_amount="1000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-05-02",
                    "10",
                    gross_amount="1500",
                ),
            ],
        )
    )
    unresolved = compute_mutual_fund_slice(ledger)

    overridden = compute_mutual_fund_slice(
        ledger,
        decision_journal=_classification_decision(
            unresolved,
            classification=StatutoryFundClass.OTHER_MUTUAL_FUND,
            disposal_event_id="sale",
        ),
    )

    assert overridden.classifications == {}
    assert overridden.bucket_totals == {}
    assert overridden.readiness.state is (
        FilingReadiness.BLOCKED
    )
    assert overridden.provisional_bucket_totals == {
        FundTaxBucket.STCG_SLAB: Decimal("500")
    }
    assert {blocker.code for blocker in overridden.blockers} == {
        "INCOMPLETE_PRIMARY_CLASSIFICATION_EVIDENCE"
    }


def test_classification_is_resolved_for_each_disposal_evidence_period():
    first_period = _primary_evidence(
        domestic_equity_percentage="70",
        debt_money_market_percentage="20",
    )
    first_period["period_end"] = "2025-09-30"
    second_period = _primary_evidence(
        domestic_equity_percentage="10",
        debt_money_market_percentage="70",
    )
    second_period.update(
        {
            "evidence_id": "classification-2",
            "period_start": "2025-10-01",
            "provenance": _source(11),
        }
    )
    data = _ledger(
        evidence=first_period,
        events=[
            _event(
                "purchase",
                1,
                "purchase",
                "2024-01-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale-first-period",
                2,
                "sale",
                "2025-06-02",
                "5",
                gross_amount="750",
                stt_paid=True,
            ),
            _event(
                "sale-second-period",
                3,
                "sale",
                "2025-11-02",
                "5",
                gross_amount="800",
                stt_paid=True,
            ),
        ],
    )
    data["schemes"][0]["classification_evidence"].append(second_period)
    data["account_summaries"][0]["gross_disposal_proceeds"] = "1550"

    result = compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    assert result.independently_ready
    assert SCHEME not in result.classifications
    assert result.bucket_totals == {
        FundTaxBucket.LTCG_112A: Decimal("250"),
        FundTaxBucket.STCG_50AA: Decimal("300"),
    }
    assert [
        (match.disposal_event_id, match.classification)
        for match in result.matched_disposals
    ] == [
        (
            "sale-first-period",
            StatutoryFundClass.EQUITY_ORIENTED,
        ),
        (
            "sale-second-period",
            StatutoryFundClass.SPECIFIED_MUTUAL_FUND,
        ),
    ]
    assert {
        interval.classification
        for interval in result.classification_intervals
    } == {
        StatutoryFundClass.EQUITY_ORIENTED,
        StatutoryFundClass.SPECIFIED_MUTUAL_FUND,
    }


def test_dividend_reinvestment_creates_a_new_fifo_acquisition_lot():
    data = _ledger(
        evidence=_primary_evidence(
            domestic_equity_percentage="70",
            debt_money_market_percentage="20",
        ),
        events=[
            _event(
                "reinvestment",
                1,
                "reinvestment",
                "2025-04-01",
                "10",
                gross_amount="1000",
            ),
            _event(
                "sale",
                2,
                "sale",
                "2025-05-02",
                "10",
                gross_amount="1500",
                stt_paid=True,
            ),
        ],
    )

    result = compute_mutual_fund_slice(load_mutual_fund_ledger(data))

    (match,) = result.matched_disposals
    assert match.acquisition_event_id == "reinvestment"
    assert match.cost_basis == Decimal("1000")
    assert match.tax_bucket is FundTaxBucket.STCG_111A
