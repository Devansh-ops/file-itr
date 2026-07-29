from datetime import datetime, timezone
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from engine.contracts import OfficialContractRegistry
from engine.trading_business import (
    TaxAuditApplicabilityStatus,
    TradingFilingError,
    TradingLedgerError,
    TradingReconciliationError,
    TradingSegment,
    build_trading_business_itr3_draft,
    compute_trading_business_slice,
    load_trading_ledger,
)
from engine.readiness import (
    DecisionAction,
    DecisionJournal,
    FilingReadiness,
    HumanDecision,
)


def _source(number):
    return {
        "source_document": f"inputs/trading-{number}.json",
        "source_sha256": f"{number:064x}",
        "source_location": f"item:{number}",
        "importer": "trading-fixture",
        "importer_version": "1.0.0",
    }


def _trade(
    trade_id,
    sequence,
    segment,
    side,
    opening_price,
    closing_price,
    expenses,
    *,
    settlement_type="square_off",
    account_id="broker-a",
    quantity="1",
    contract_multiplier="1",
    derivative_eligibility=True,
):
    trade = {
        "trade_id": trade_id,
        "sequence": sequence,
        "segment": segment,
        "account_id": account_id,
        "instrument_id": f"instrument-{sequence}",
        "exchange": "NSE",
        "position_side": side,
        "opened_on": "2025-06-10",
        "closed_on": "2025-06-10",
        "execution_ids": [f"execution-{sequence}"],
        "matching_method": "broker_closed_position",
        "quantity": quantity,
        "contract_multiplier": contract_multiplier,
        "opening_price": opening_price,
        "closing_price": closing_price,
        "settlement_type": settlement_type,
        "expense_components": (
            [
                {
                    "expense_id": f"expense-{sequence}",
                    "expense_type": (
                        "brokerage_and_exchange_charges"
                    ),
                    "amount": expenses,
                    "deductibility_evidenced": True,
                    "provenance": _source(sequence + 100),
                }
            ]
            if Decimal(expenses)
            else []
        ),
        "provenance": _source(sequence),
    }
    if segment in {"futures", "options"}:
        trade["derivative_eligibility"] = (
            {
                "contract_note_id": f"contract-note-{sequence}",
                "contract_note_timestamp": (
                    "2025-06-10T10:00:00+05:30"
                ),
                "exchange": "NSE",
                "client_identity_and_pan_present": True,
                "electronic_trade": True,
                "registered_intermediary": True,
                "exchange_recognition_reference": (
                    "Notification 2/2006"
                ),
                "provenance": _source(sequence + 200),
            }
            if derivative_eligibility
            else None
        )
    return trade


def _summary(
    number,
    segment,
    *,
    gross_profit,
    gross_loss,
    turnover,
    expenses,
    net_profit_loss,
    account_id="broker-a",
):
    return {
        "summary_id": f"summary-{number}",
        "account_id": account_id,
        "segment": segment,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "turnover": turnover,
        "expenses": expenses,
        "net_profit_loss": net_profit_loss,
        "provenance": _source(number),
    }


def _audit_facts(**overrides):
    facts = {
        "other_business_turnover": "0",
        "other_business_turnover_complete": True,
        "aggregate_amounts_received": "1000",
        "cash_receipts": "0",
        "aggregate_payments_made": "1000",
        "cash_payments": "0",
        "cash_flow_population_complete": True,
        "section_44ad_election": "not_elected",
        "section_44ad_lockout_applies": False,
        "other_audit_obligation": False,
        "provenance": _source(900),
    }
    facts.update(overrides)
    return facts


def _ledger(
    *,
    trades,
    summaries,
    input_basis="trading_detail",
    audit_facts=None,
    accounting_basis="regular_books",
):
    return {
        "schema_version": "1.0",
        "assessment_year": "2026-27",
        "input_basis": input_basis,
        "accounting_basis": accounting_basis,
        "trades": trades,
        "broker_trading_summaries": summaries,
        "audit_facts": (
            _audit_facts() if audit_facts is None else audit_facts
        ),
    }


def test_trade_detail_recomputes_and_reconciles_intraday_and_futures():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "20",
                ),
                _trade(
                    "futures-loss",
                    2,
                    "futures",
                    "long",
                    "2000",
                    "1700",
                    "30",
                ),
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="200",
                    expenses="20",
                    net_profit_loss="180",
                ),
                _summary(
                    21,
                    "futures",
                    gross_profit="0",
                    gross_loss="300",
                    turnover="300",
                    expenses="30",
                    net_profit_loss="-330",
                ),
            ],
        )
    )

    result = compute_trading_business_slice(ledger)

    speculative = result.segment_results[
        TradingSegment.EQUITY_INTRADAY
    ]
    assert speculative.gross_profit == Decimal("200")
    assert speculative.gross_loss == Decimal("0")
    assert speculative.turnover == Decimal("200")
    assert speculative.expenses == Decimal("20")
    assert speculative.expense_totals == {
        "brokerage_and_exchange_charges": Decimal("20")
    }
    assert speculative.net_profit_loss == Decimal("180")

    non_speculative = result.segment_results[
        TradingSegment.FUTURES
    ]
    assert non_speculative.gross_profit == Decimal("0")
    assert non_speculative.gross_loss == Decimal("300")
    assert non_speculative.turnover == Decimal("300")
    assert non_speculative.expenses == Decimal("30")
    assert non_speculative.net_profit_loss == Decimal("-330")

    assert result.speculative_business_result == Decimal("180")
    assert result.non_speculative_business_result == Decimal("-330")
    assert result.total_business_result == Decimal("-150")
    assert result.loss_categories.speculative_loss == Decimal("0")
    assert (
        result.loss_categories.non_speculative_business_loss
        == Decimal("330")
    )
    assert result.filing_values["ScheduleBP"] == {
        "SpeculativeBusinessIncome": Decimal("180"),
        "NonSpeculativeBusinessIncome": Decimal("-330"),
        "TotalTradingBusinessIncome": Decimal("-150"),
    }
    assert (
        result.readiness.state
        is FilingReadiness.INDEPENDENTLY_FILING_READY
    )
    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.NOT_REQUIRED
    )
    assert (
        result.tax_audit_applicability.aggregate_business_turnover
        == Decimal("500")
    )
    assert len(
        {line.output_path for line in result.audit_trace}
    ) == len(result.audit_trace)
    assert {
        delta.output_path for delta in result.output_deltas
    } == {
        path
        for path, _amount in result.readiness.context.output_amounts
    }

    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )
    draft = build_trading_business_itr3_draft(base, result)
    itr3 = draft["ITR"]["ITR3"]
    assert itr3["TradingAccount"]["TurnoverIntradayTrd"] == 200
    assert itr3["TradingAccount"]["IncomeIntradayTrd"] == 180
    assert itr3["TradingAccount"]["TurnoverFutureTrd"] == 300
    assert itr3["TradingAccount"]["IncomeFutureTrd"] == -330
    assert itr3["PARTA_PL"]["TurnverFrmSpecActivity"] == 0
    assert itr3["PARTA_PL"]["NetIncomeFrmSpecActivity"] == 0
    assert (
        itr3["PARTA_PL"]["CreditsToPL"][
            "GrossProfitTrnsfFrmTrdAcc"
        ]
        == -150
    )
    assert itr3["PARTA_PL"]["CreditsToPL"]["TotCreditsToPL"] == -150
    assert (
        itr3["PARTA_PL"]["CreditsToPL"][
            "GrossProfitTrnsfFrmTrdAcc"
        ]
        == (
            itr3["TradingAccount"].get(
                "GrossProfitFrmBusProf",
                0,
            )
            + itr3["TradingAccount"]["IncomeIntradayTrd"]
            + itr3["TradingAccount"]["IncomeFutureTrd"]
        )
    )
    assert (
        itr3["PartA_GEN2"]["AuditInfo"]["TotalSalesExcOneCr"]
        == "Upto1CR"
    )
    assert (
        itr3["PartA_GEN2"]["AuditInfo"]["LiableSec44ABflg"]
        == "N"
    )
    assert (
        itr3["ITR3ScheduleBP"]["SpecBusinessInc"][
            "AdjustedPLFrmSpecuBus"
        ]
        == 180
    )
    assert (
        itr3["ITR3ScheduleBP"]["SpecBusinessInc"][
            "NetPLFrmSpecBus"
        ]
        == (
            itr3["TradingAccount"]["IncomeIntradayTrd"]
            + itr3["PARTA_PL"]["NetIncomeFrmSpecActivity"]
        )
    )
    assert (
        itr3["ITR3ScheduleBP"]["BusinessIncOthThanSpec"][
            "BalancePLOthThanSpecBus"
        ]
        == -330
    )
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate("ITR-3", draft)


def test_itr3_projection_adds_to_existing_business_values():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "20",
                ),
                _trade(
                    "futures-loss",
                    2,
                    "futures",
                    "long",
                    "2000",
                    "1700",
                    "30",
                ),
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="200",
                    expenses="20",
                    net_profit_loss="180",
                ),
                _summary(
                    21,
                    "futures",
                    gross_profit="0",
                    gross_loss="300",
                    turnover="300",
                    expenses="30",
                    net_profit_loss="-330",
                ),
            ],
        )
    )
    result = compute_trading_business_slice(ledger)
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )
    itr3 = base["ITR"]["ITR3"]
    itr3["TradingAccount"] = {
        "OperatingRevenueTotal": 0,
        "SalesGrossReceiptsTotal": 0,
        "TotRevenueFrmOperations": 0,
        "TardingAccTotCred": 0,
        "DirectExpenses": 0,
        "GrossProfitFrmBusProf": 0,
        "TurnoverIntradayTrd": 60,
        "IncomeIntradayTrd": 50,
        "TurnoverFutureTrd": 50,
        "IncomeFutureTrd": 40,
    }
    credits = itr3["PARTA_PL"]["CreditsToPL"]
    credits["GrossProfitTrnsfFrmTrdAcc"] = 90
    credits["TotCreditsToPL"] = 90
    itr3["PARTA_PL"]["DebitsToPL"]["PBIDTA"] = 90
    itr3["PARTA_PL"]["DebitsToPL"]["PBT"] = 90
    for field in (
        "ProfitAfterTax",
        "AmtAvlAppr",
        "ProprietorAccBalTrf",
    ):
        itr3["PARTA_PL"]["TaxProvAppr"][field] = 90
    bp = itr3["ITR3ScheduleBP"]
    business = bp["BusinessIncOthThanSpec"]
    for field in (
        "ProfBfrTaxPL",
        "BalancePLOthThanSpecBus",
        "AdjustedPLOthThanSpecBus",
        "AdjustPLAfterDeprOthSpecInc",
        "TotAfterAddToPLDeprOthSpecInc",
        "PLAftAdjDedBusOthThanSpec",
        "NetPLAftAdjBusOthThanSpec",
        "NetPLBusOthThanSpec7A7B7C",
        "IncomeOtherThanRule",
    ):
        business[field] = 90 if field == "ProfBfrTaxPL" else 40
    business["NetPLFromSpecBus"] = 50
    bp["SpecBusinessInc"]["NetPLFrmSpecBus"] = 50
    bp["SpecBusinessInc"]["AdjustedPLFrmSpecuBus"] = 50
    bp["IncChrgUnHdProftGain"] = 90
    original = deepcopy(base)

    draft = build_trading_business_itr3_draft(base, result)

    projected = draft["ITR"]["ITR3"]
    trading = projected["TradingAccount"]
    assert trading["TurnoverIntradayTrd"] == 260
    assert trading["IncomeIntradayTrd"] == 230
    assert trading["TurnoverFutureTrd"] == 350
    assert trading["IncomeFutureTrd"] == -290
    assert (
        projected["PARTA_PL"]["CreditsToPL"][
            "GrossProfitTrnsfFrmTrdAcc"
        ]
        == -60
    )
    assert projected["PARTA_PL"]["DebitsToPL"]["PBIDTA"] == -60
    assert projected["PARTA_PL"]["DebitsToPL"]["PBT"] == -60
    projected_bp = projected["ITR3ScheduleBP"]
    assert (
        projected_bp["SpecBusinessInc"]["AdjustedPLFrmSpecuBus"]
        == 230
    )
    assert (
        projected_bp["BusinessIncOthThanSpec"][
            "BalancePLOthThanSpecBus"
        ]
        == -290
    )
    assert projected_bp["IncChrgUnHdProftGain"] == -60
    assert base == original
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate("ITR-3", draft)


def test_no_books_projection_uses_only_no_books_fields():
    ledger = load_trading_ledger(
        _ledger(
            accounting_basis="no_books",
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "20",
                ),
                _trade(
                    "future-profit",
                    2,
                    "futures",
                    "long",
                    "1000",
                    "1100",
                    "10",
                ),
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="200",
                    expenses="20",
                    net_profit_loss="180",
                ),
                _summary(
                    21,
                    "futures",
                    gross_profit="100",
                    gross_loss="0",
                    turnover="100",
                    expenses="10",
                    net_profit_loss="90",
                ),
            ],
        )
    )
    result = compute_trading_business_slice(ledger)
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )

    draft = build_trading_business_itr3_draft(base, result)

    itr3 = draft["ITR"]["ITR3"]
    assert "TradingAccount" not in itr3
    part_a_pl = itr3["PARTA_PL"]
    assert part_a_pl["TurnverFrmSpecActivity"] == 200
    assert part_a_pl["GrossProfit"] == 200
    assert part_a_pl["Expenditure"] == 20
    assert part_a_pl["NetIncomeFrmSpecActivity"] == 180
    no_books = part_a_pl["NoBooksOfAccPL"]
    assert no_books["GrossReceipt"] == 100
    assert no_books["GrossProfit"] == 100
    assert no_books["Expenses"] == 10
    assert no_books["NetProfit"] == 90
    assert no_books["TotBusinessProfession"] == 90
    assert {
        line.output_path for line in result.audit_trace
    } == {
        "/ITR/ITR3/PARTA_PL/TurnverFrmSpecActivity",
        "/ITR/ITR3/PARTA_PL/NetIncomeFrmSpecActivity",
        "/ITR/ITR3/PARTA_PL/NoBooksOfAccPL/GrossReceipt",
        "/ITR/ITR3/PARTA_PL/NoBooksOfAccPL/NetProfit",
    }
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate("ITR-3", draft)


def test_no_books_fno_loss_blocks_until_accounting_route_is_resolved():
    ledger = load_trading_ledger(
        _ledger(
            accounting_basis="no_books",
            trades=[
                _trade(
                    "future-loss",
                    1,
                    "futures",
                    "long",
                    "1000",
                    "900",
                    "10",
                )
            ],
            summaries=[
                _summary(
                    20,
                    "futures",
                    gross_profit="0",
                    gross_loss="100",
                    turnover="100",
                    expenses="10",
                    net_profit_loss="-110",
                )
            ],
        )
    )

    result = compute_trading_business_slice(ledger)

    assert result.readiness.state is FilingReadiness.BLOCKED
    assert {
        blocker.code for blocker in result.readiness.active_blockers
    } == {"NO_BOOKS_FNO_LOSS_REQUIRES_ACCOUNTING_ROUTE"}
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(TradingFilingError, match="filing-ready"):
        build_trading_business_itr3_draft(base, result)


def test_summary_only_is_provisional_until_human_accepts_gap():
    ledger = load_trading_ledger(
        _ledger(
            input_basis="broker_trading_summary_only",
            trades=[],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="200",
                    expenses="20",
                    net_profit_loss="180",
                ),
                _summary(
                    21,
                    "futures",
                    gross_profit="0",
                    gross_loss="300",
                    turnover="300",
                    expenses="30",
                    net_profit_loss="-330",
                ),
            ],
        )
    )
    empty_journal = DecisionJournal.empty(
        "ay2026-27:trading-business"
    )

    provisional = compute_trading_business_slice(
        ledger,
        decision_journal=empty_journal,
    )

    assert provisional.total_business_result == Decimal("-150")
    assert provisional.readiness.state is FilingReadiness.PROVISIONAL
    (blocker,) = provisional.readiness.active_blockers
    assert blocker.code == "BROKER_TRADING_SUMMARY_ONLY"
    assert {
        (
            "/ITR/ITR3/PARTA_PL/CreditsToPL/"
            "GrossProfitTrnsfFrmTrdAcc"
        ),
        "/ITR/ITR3/PARTA_PL/CreditsToPL/TotCreditsToPL",
        (
            "/ITR/ITR3/ITR3ScheduleBP/BusinessIncOthThanSpec/"
            "NetPLAftAdjBusOthThanSpec"
        ),
        "/ITR/ITR3/PartA_GEN2/AuditInfo/TotalSalesExcOneCr",
        "/ITR/ITR3/PartA_GEN2/AuditInfo/AgrOFAllAmtsRcvd",
    }.issubset(blocker.affected_outputs)
    assert set(blocker.affected_outputs) == {
        path
        for path, _amount in (
            provisional.readiness.context.output_amounts
        )
    }
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(
        TradingFilingError,
        match="filing-ready",
    ):
        build_trading_business_itr3_draft(base, provisional)

    decision = HumanDecision(
        decision_id="accept-summary-only",
        blocker_id=blocker.blocker_id,
        action=DecisionAction.ACCEPT_RISK,
        actor="Devansh Sehgal",
        decided_at=datetime(
            2026,
            7,
            29,
            16,
            30,
            tzinfo=timezone.utc,
        ),
        reason=(
            "Contract-level export is unavailable; accept this broker "
            "trading summary for the filing."
        ),
        evidence_references=(
            "human-decisions.md#trading-summary-only",
        ),
        affected_outputs=blocker.affected_outputs,
        context_fingerprint=(
            provisional.readiness.context_fingerprint
        ),
    )
    accepted = compute_trading_business_slice(
        ledger,
        decision_journal=empty_journal.append(decision),
    )

    assert (
        accepted.readiness.state
        is FilingReadiness.FILING_READY_BY_HUMAN_OVERRIDE
    )
    assert accepted.readiness.blockers == (blocker,)
    assert accepted.readiness.accepted_risks == (blocker,)
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate(
        "ITR-3",
        build_trading_business_itr3_draft(base, accepted),
    )


def test_options_turnover_retains_sale_premium_without_double_counting():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "long-close-profit",
                    1,
                    "options",
                    "long",
                    "500",
                    "800",
                    "0",
                ),
                _trade(
                    "short-close-profit",
                    2,
                    "options",
                    "short",
                    "900",
                    "400",
                    "0",
                ),
                _trade(
                    "long-expiry-loss",
                    3,
                    "options",
                    "long",
                    "50",
                    "0",
                    "0",
                    settlement_type="expiry_worthless",
                ),
                _trade(
                    "short-expiry-profit",
                    4,
                    "options",
                    "short",
                    "70",
                    "0",
                    "0",
                    settlement_type="expiry_unexercised",
                ),
            ],
            summaries=[
                _summary(
                    20,
                    "options",
                    gross_profit="870",
                    gross_loss="50",
                    turnover="1820",
                    expenses="0",
                    net_profit_loss="820",
                )
            ],
        )
    )

    result = compute_trading_business_slice(ledger)

    options = result.segment_results[TradingSegment.OPTIONS]
    assert options.gross_profit == Decimal("870")
    assert options.gross_loss == Decimal("50")
    assert options.turnover == Decimal("1820")
    assert options.net_profit_loss == Decimal("820")
    assert result.speculative_business_result == Decimal("0")
    assert result.non_speculative_business_result == Decimal("820")


def test_quantity_and_contract_multiplier_drive_trade_level_result():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "future-profit",
                    1,
                    "futures",
                    "long",
                    "100",
                    "110",
                    "25",
                    quantity="10",
                    contract_multiplier="25",
                )
            ],
            summaries=[
                _summary(
                    20,
                    "futures",
                    gross_profit="2500",
                    gross_loss="0",
                    turnover="2500",
                    expenses="25",
                    net_profit_loss="2475",
                )
            ],
        )
    )

    result = compute_trading_business_slice(ledger)

    futures = result.segment_results[TradingSegment.FUTURES]
    assert futures.gross_profit == Decimal("2500")
    assert futures.turnover == Decimal("2500")
    assert futures.expenses == Decimal("25")
    assert futures.net_profit_loss == Decimal("2475")


def test_fno_requires_section_43_5_d_eligibility_evidence():
    with pytest.raises(
        TradingLedgerError,
        match="section 43\\(5\\)\\(d\\) eligibility evidence",
    ):
        load_trading_ledger(
            _ledger(
                trades=[
                    _trade(
                        "future-without-contract-note",
                        1,
                        "futures",
                        "long",
                        "100",
                        "110",
                        "0",
                        derivative_eligibility=False,
                    )
                ],
                summaries=[
                    _summary(
                        20,
                        "futures",
                        gross_profit="10",
                        gross_loss="0",
                        turnover="10",
                        expenses="0",
                        net_profit_loss="10",
                    )
                ],
            )
        )


def test_option_expiry_outcome_must_match_side_and_zero_close():
    with pytest.raises(
        TradingLedgerError,
        match="option expiry outcome must match",
    ):
        load_trading_ledger(
            _ledger(
                trades=[
                    _trade(
                        "invalid-expiry",
                        1,
                        "options",
                        "long",
                        "50",
                        "10",
                        "0",
                        settlement_type="expiry_worthless",
                    )
                ],
                summaries=[
                    _summary(
                        20,
                        "options",
                        gross_profit="0",
                        gross_loss="40",
                        turnover="50",
                        expenses="0",
                        net_profit_loss="-40",
                    )
                ],
            )
        )


@pytest.mark.parametrize(
    (
        "audit_overrides",
        "expected_status",
        "expected_basis",
    ),
    [
        (
            {"other_business_turnover": "100000001"},
            TaxAuditApplicabilityStatus.REQUIRED,
            "section_44AB_a_turnover_above_10_crore",
        ),
        (
            {
                "other_business_turnover": "20000000",
                "aggregate_amounts_received": "100",
                "cash_receipts": "6",
            },
            TaxAuditApplicabilityStatus.REQUIRED,
            "section_44AB_a_cash_ratio_above_5_percent",
        ),
        (
            {"other_business_turnover": "20000000"},
            TaxAuditApplicabilityStatus.NOT_REQUIRED,
            "section_44AB_a_enhanced_threshold",
        ),
        (
            {
                "section_44ad_lockout_applies": True,
                "total_income_exceeds_basic_exemption": True,
            },
            TaxAuditApplicabilityStatus.REQUIRED,
            "section_44AB_e_44AD_lockout",
        ),
        (
            {"other_audit_obligation": True},
            TaxAuditApplicabilityStatus.REQUIRED,
            "other_audit_obligation",
        ),
    ],
)
def test_tax_audit_applicability_decision_table(
    audit_overrides,
    expected_status,
    expected_basis,
):
    ledger = _single_intraday_ledger(
        _audit_facts(**audit_overrides)
    )

    result = compute_trading_business_slice(ledger)

    assert result.tax_audit_applicability.status is expected_status
    assert expected_basis in result.tax_audit_applicability.bases


def test_incomplete_all_business_cash_population_requires_human_review():
    facts = _audit_facts(
        other_business_turnover="20000000",
        cash_flow_population_complete=False,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        "complete_all_business_cash_flow_population"
        in result.tax_audit_applicability.unresolved_conditions
    )
    assert result.readiness.state is FilingReadiness.BLOCKED
    assert {
        blocker.code for blocker in result.readiness.active_blockers
    } == {"TAX_AUDIT_HUMAN_REVIEW_REQUIRED"}


def test_required_audit_basis_wins_over_unresolved_cash_population():
    facts = _audit_facts(
        other_business_turnover="100000001",
        cash_flow_population_complete=False,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert result.readiness.state is FilingReadiness.INDEPENDENTLY_FILING_READY


def test_required_audit_with_unknown_aggregate_turnover_blocks_draft():
    facts = _audit_facts(
        other_business_turnover_complete=False,
        other_audit_obligation=True,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert result.readiness.state is FilingReadiness.BLOCKED
    assert {
        blocker.code for blocker in result.readiness.active_blockers
    } == {"AGGREGATE_BUSINESS_TURNOVER_REQUIRED_FOR_ITR3"}


def test_required_tax_audit_projects_section_44ab_fields():
    ledger = _single_intraday_ledger(
        _audit_facts(other_business_turnover="100000001")
    )
    result = compute_trading_business_slice(ledger)
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )

    draft = build_trading_business_itr3_draft(base, result)

    audit_info = draft["ITR"]["ITR3"]["PartA_GEN2"]["AuditInfo"]
    assert audit_info["TotalSalesExcOneCr"] == "MoreThan10CR"
    assert audit_info["LiableSec44ABflg"] == "Y"
    assert audit_info["Cndnfor44AB"] == "bi"
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate("ITR-3", draft)


def test_valid_section_44ad_election_uses_presumptive_filing_route():
    facts = _audit_facts(
        aggregate_amounts_received="100",
        cash_receipts="6",
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=True,
        section_44ad_other_business_turnover="0",
        section_44ad_filing_facts={
            "bank_mode_turnover": "18800000",
            "cash_turnover": "0",
            "other_mode_turnover": "1200000",
            "bank_mode_income": "1128000",
            "non_bank_mode_income": "96000",
            "declared_income": "1224000",
            "provenance": _source(901),
        },
    )
    ledger = _large_intraday_ledger(
        facts,
        accounting_basis="no_books",
    )

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.NOT_REQUIRED
    )
    assert (
        "section_44AD_presumptive_business"
        in result.tax_audit_applicability.bases
    )
    base = json.loads(
        (FIXTURES / "itr3-minimal.json").read_text(
            encoding="utf-8"
        )
    )

    draft = build_trading_business_itr3_draft(base, result)

    itr3 = draft["ITR"]["ITR3"]
    assert itr3["PARTA_PL"]["NatOfBus44AD"] == [
        {
            "NameOfBusiness": "Speculative trading",
            "CodeAD": "21009",
        }
    ]
    assert itr3["PARTA_PL"]["PersumptiveInc44AD"] == {
        "GrsTrnOverOrReceipt": 20000000,
        "GrsTrnOverBank": 18800000,
        "GrsTotalTrnOverInCash": 0,
        "GrsTrnOverAnyOthMode": 1200000,
        "TotPersumptiveInc44AD": 1224000,
        "PersumptiveInc44AD6Per": 1128000,
        "PersumptiveInc44AD8Per": 96000,
    }
    business = itr3["ITR3ScheduleBP"]["BusinessIncOthThanSpec"]
    assert business["ProfBfrTaxPL"] == 0
    assert (
        business["ProfitLossInclRefrdSec"]["ProfitLossUs44AD"]
        == 1224000
    )
    assert business["TotalProfitFrmActCvrd"] == 1224000
    assert business["DeemedProfitBusUs"]["Section44AD"] == 1224000
    assert (
        business["DeemedProfitBusUs"]["TotDeemedProfitBusUs"]
        == 1224000
    )
    assert business["IncomeOtherThanRule"] == 1224000
    assert itr3["ITR3ScheduleBP"]["IncChrgUnHdProftGain"] == 1224000
    assert {
        line.output_path for line in result.audit_trace
    } == {
        "/ITR/ITR3/PARTA_PL/PersumptiveInc44AD/"
        "GrsTrnOverOrReceipt",
        "/ITR/ITR3/PARTA_PL/PersumptiveInc44AD/"
        "TotPersumptiveInc44AD",
    }
    assert {
        line.evidence_references for line in result.audit_trace
    } == {
        ("inputs/trading-901.json#item:901",),
    }
    OfficialContractRegistry.for_assessment_year(
        "2026-27"
    ).validate("ITR-3", draft)


@pytest.mark.parametrize(
    ("audit_overrides", "unresolved_condition"),
    [
        (
            {},
            "section_44ad_filing_amounts",
        ),
        (
            {
                "section_44ad_filing_facts": {
                    "bank_mode_turnover": "199",
                    "cash_turnover": "0",
                    "other_mode_turnover": "0",
                    "bank_mode_income": "12",
                    "non_bank_mode_income": "0",
                    "declared_income": "12",
                    "provenance": _source(902),
                },
            },
            "section_44ad_filing_cross_tie",
        ),
    ],
)
def test_section_44ad_filing_values_are_human_input_and_must_cross_tie(
    audit_overrides,
    unresolved_condition,
):
    facts = _audit_facts(
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=True,
        section_44ad_other_business_turnover="0",
        **audit_overrides,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        unresolved_condition
        in result.tax_audit_applicability.unresolved_conditions
    )
    assert result.readiness.state is FilingReadiness.BLOCKED


def test_required_audit_does_not_override_missing_44ad_filing_facts():
    facts = _audit_facts(
        other_audit_obligation=True,
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=True,
        section_44ad_other_business_turnover="0",
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert result.readiness.state is FilingReadiness.BLOCKED
    assert (
        "SECTION_44AD_TRADING_FILING_FACTS_REQUIRED"
        in {
            blocker.code
            for blocker in result.readiness.active_blockers
        }
    )


def test_required_audit_does_not_mask_invalid_44ad_percentages():
    facts = _audit_facts(
        other_audit_obligation=True,
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=True,
        section_44ad_other_business_turnover="0",
        section_44ad_filing_facts={
            "bank_mode_turnover": "200",
            "cash_turnover": "0",
            "other_mode_turnover": "0",
            "bank_mode_income": "11",
            "non_bank_mode_income": "0",
            "declared_income": "11",
            "provenance": _source(903),
        },
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert result.readiness.state is FilingReadiness.BLOCKED
    assert (
        "section_44ad_filing_cross_tie"
        in result.tax_audit_applicability.unresolved_conditions
    )
    assert result.section_44ad_filing_values is None


def test_44ad_for_unrelated_business_keeps_ordinary_trading_route():
    facts = _audit_facts(
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=False,
        section_44ad_other_business_turnover="0",
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert result.readiness.state is FilingReadiness.INDEPENDENTLY_FILING_READY
    assert result.section_44ad_filing_values is None
    assert any(
        delta.output_path.startswith("/ITR/ITR3/TradingAccount/")
        for delta in result.output_deltas
    )


def test_44ad_unrelated_business_turnover_is_excluded_from_44ab_a():
    facts = _audit_facts(
        other_business_turnover="20000000",
        aggregate_amounts_received="100",
        cash_receipts="6",
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=False,
        section_44ad_other_business_turnover="20000000",
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.NOT_REQUIRED
    )
    assert (
        "section_44AD_presumptive_business"
        in result.tax_audit_applicability.bases
    )


def test_missing_44ad_other_business_split_requires_human_review():
    facts = _audit_facts(
        other_business_turnover="20000000",
        aggregate_amounts_received="100",
        cash_receipts="6",
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=False,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        "section_44ad_other_business_turnover_split"
        in result.tax_audit_applicability.unresolved_conditions
    )


def test_independent_audit_basis_wins_when_44ad_split_is_missing():
    facts = _audit_facts(
        other_business_turnover="20000000",
        aggregate_amounts_received="100",
        cash_receipts="6",
        other_audit_obligation=True,
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=False,
    )
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert (
        "other_audit_obligation"
        in result.tax_audit_applicability.bases
    )
    assert (
        "section_44ad_other_business_turnover_split"
        in result.tax_audit_applicability.unresolved_conditions
    )


@pytest.mark.parametrize(
    "coverage",
    [None, True],
)
def test_unresolved_44ad_trading_route_makes_44ab_a_unknown(
    coverage,
):
    facts = _audit_facts(
        aggregate_amounts_received="100",
        cash_receipts="6",
        section_44ad_election="elected",
        section_44ad_eligibility_confirmed=True,
        section_44ad_presumptive_income_compliant=True,
        section_44ad_covers_trading_business=coverage,
        section_44ad_other_business_turnover=(
            "0" if coverage is True else None
        ),
    )
    ledger = _large_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert result.readiness.state is FilingReadiness.BLOCKED


def test_unknown_44ad_election_makes_44ab_a_unknown():
    facts = _audit_facts(
        aggregate_amounts_received="100",
        cash_receipts="6",
        section_44ad_election=None,
    )
    ledger = _large_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        "section_44ad_election"
        in result.tax_audit_applicability.unresolved_conditions
    )


def test_independent_audit_basis_wins_when_44ad_election_is_unknown():
    facts = _audit_facts(
        aggregate_amounts_received="100",
        cash_receipts="6",
        other_audit_obligation=True,
        section_44ad_election=None,
    )
    ledger = _large_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.REQUIRED
    )
    assert (
        "other_audit_obligation"
        in result.tax_audit_applicability.bases
    )


def test_auditor_turnover_disagreement_requires_human_review():
    facts = _audit_facts(auditor_trading_turnover="999")
    ledger = _single_intraday_ledger(facts)

    result = compute_trading_business_slice(ledger)

    assert (
        result.tax_audit_applicability.status
        is TaxAuditApplicabilityStatus.HUMAN_REVIEW_REQUIRED
    )
    assert (
        "auditor_trading_turnover_disagreement"
        in result.tax_audit_applicability.unresolved_conditions
    )


def test_broker_mismatch_reports_each_actionable_field():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "20",
                )
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="999",
                    expenses="20",
                    net_profit_loss="180",
                )
            ],
        )
    )

    with pytest.raises(TradingReconciliationError) as caught:
        compute_trading_business_slice(ledger)

    assert caught.value.blocker_codes == frozenset(
        {"BROKER_TRADING_TURNOVER_MISMATCH"}
    )
    (blocker,) = caught.value.blockers
    assert blocker.segment is TradingSegment.EQUITY_INTRADAY
    assert blocker.account_id == "broker-a"
    assert blocker.computed_amount == Decimal("200")
    assert blocker.observed_amount == Decimal("999")
    assert blocker.evidence_references == (
        "inputs/trading-20.json#item:20",
    )


def test_broker_reconciliation_is_account_local_not_segment_netting():
    ledger = load_trading_ledger(
        _ledger(
            trades=[
                _trade(
                    "broker-a-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "0",
                    account_id="broker-a",
                ),
                _trade(
                    "broker-b-profit",
                    2,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1100",
                    "0",
                    account_id="broker-b",
                ),
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="150",
                    gross_loss="0",
                    turnover="150",
                    expenses="0",
                    net_profit_loss="150",
                    account_id="broker-a",
                ),
                _summary(
                    21,
                    "equity_intraday",
                    gross_profit="150",
                    gross_loss="0",
                    turnover="150",
                    expenses="0",
                    net_profit_loss="150",
                    account_id="broker-b",
                ),
            ],
        )
    )

    with pytest.raises(TradingReconciliationError) as caught:
        compute_trading_business_slice(ledger)

    assert {
        blocker.account_id for blocker in caught.value.blockers
    } == {"broker-a", "broker-b"}
    assert caught.value.blocker_codes == frozenset(
        {
            "BROKER_TRADING_GROSS_PROFIT_MISMATCH",
            "BROKER_TRADING_TURNOVER_MISMATCH",
            "BROKER_TRADING_NET_RESULT_MISMATCH",
        }
    )


def _single_intraday_ledger(audit_facts):
    return load_trading_ledger(
        _ledger(
            audit_facts=audit_facts,
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1000",
                    "1200",
                    "20",
                )
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="200",
                    gross_loss="0",
                    turnover="200",
                    expenses="20",
                    net_profit_loss="180",
                )
            ],
        )
    )


def _large_intraday_ledger(
    audit_facts,
    *,
    accounting_basis="regular_books",
):
    return load_trading_ledger(
        _ledger(
            accounting_basis=accounting_basis,
            audit_facts=audit_facts,
            trades=[
                _trade(
                    "intraday-profit",
                    1,
                    "equity_intraday",
                    "long",
                    "1",
                    "20000001",
                    "0",
                )
            ],
            summaries=[
                _summary(
                    20,
                    "equity_intraday",
                    gross_profit="20000000",
                    gross_loss="0",
                    turnover="20000000",
                    expenses="0",
                    net_profit_loss="20000000",
                )
            ],
        )
    )


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
