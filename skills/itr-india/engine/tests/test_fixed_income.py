from decimal import Decimal

import pytest

from engine.fixed_income import (
    FixedIncomeReconciliationError,
    FixedIncomeTaxBucket,
    compute_fixed_income_slice,
    load_fixed_income_ledger,
)


ISIN = "IN0000000001"


def _source(n):
    return {
        "source_document": f"inputs/fixed-income-{n}.json",
        "source_sha256": f"{n:064x}",
        "source_location": f"item:{n}",
        "importer": "fixed-income-fixture",
        "importer_version": "1.0.0",
    }


def _event(
    event_id,
    sequence,
    event_type,
    event_date,
    quantity,
    *,
    capital_component="0",
    interest_component="0",
    charges="0",
    tds="0",
    cash_settlement="0",
    stt="0",
    exchange_listed_on_event=None,
    settlement_breakdown=None,
    account_id="demat-a",
    to_account_id=None,
):
    if settlement_breakdown is None:
        if event_type in {"coupon", "transfer"}:
            settlement_breakdown = "not_applicable"
        elif Decimal(interest_component):
            settlement_breakdown = "clean_plus_accrued_interest"
        else:
            settlement_breakdown = "clean_capital_only"
    return {
        "event_id": event_id,
        "sequence": sequence,
        "event_type": event_type,
        "event_date": event_date,
        "account_id": account_id,
        "to_account_id": to_account_id,
        "isin": ISIN,
        "quantity": quantity,
        "capital_component": capital_component,
        "interest_component": interest_component,
        "deductible_charges": charges,
        "securities_transaction_tax": stt,
        "tds_withheld": tds,
        "cash_settlement": cash_settlement,
        "exchange_listed_on_event": exchange_listed_on_event,
        "settlement_breakdown": settlement_breakdown,
        "provenance": _source(sequence),
    }


def _observation(
    observation_id,
    event_id,
    evidence_type,
    *,
    gross_interest=None,
    tds=None,
    net_cash=None,
    source_number,
):
    return {
        "observation_id": observation_id,
        "event_id": event_id,
        "evidence_type": evidence_type,
        "gross_interest": gross_interest,
        "tds_withheld": tds,
        "net_cash_received": net_cash,
        "provenance": _source(source_number),
    }


def _ledger(
    *,
    events,
    observations,
    closing_quantity="0",
    net_cash_receipts="11740",
    instrument_kind="plain_bond",
    exchange_listed=True,
    unsupported_features=(),
    statutory_zero_coupon_bond=False,
    legal_form=None,
    account_summaries=None,
):
    if legal_form is None:
        legal_form = (
            "other_security"
            if instrument_kind == "government_security"
            else "bond_or_debenture"
        )
    if account_summaries is None:
        account_summaries = [
            {
                "account_id": "demat-a",
                "net_cash_receipts": net_cash_receipts,
                "closing_positions": [
                    {
                        "isin": ISIN,
                        "quantity": closing_quantity,
                        "provenance": _source(91),
                    }
                ],
                "provenance": _source(90),
            }
        ]
    return {
        "schema_version": "1.0",
        "assessment_year": "2026-27",
        "instruments": [
            {
                "isin": ISIN,
                "instrument_name": "Listed Plain Bond",
                "terms": {
                    "instrument_kind": instrument_kind,
                    "legal_form": legal_form,
                    "exchange_listed": exchange_listed,
                    "statutory_zero_coupon_bond": (
                        statutory_zero_coupon_bond
                    ),
                    "unsupported_features": list(unsupported_features),
                    "provenance": _source(20),
                },
            }
        ],
        "events": events,
        "receipt_observations": observations,
        "account_summaries": account_summaries,
    }


def test_coupon_and_accrued_interest_are_separate_from_capital_gain():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "coupon",
                    2,
                    "coupon",
                    "2025-04-30",
                    "0",
                    interest_component="500",
                    tds="50",
                    cash_settlement="450",
                ),
                _event(
                    "sale",
                    3,
                    "sale",
                    "2025-05-02",
                    "10",
                    capital_component="11000",
                    interest_component="300",
                    charges="10",
                    cash_settlement="11290",
                    exchange_listed_on_event=True,
                ),
            ],
            observations=[
                _observation(
                    "coupon-bank",
                    "coupon",
                    "bank_statement",
                    net_cash="450",
                    source_number=30,
                ),
                _observation(
                    "coupon-26as",
                    "coupon",
                    "form_26as",
                    gross_interest="500",
                    tds="50",
                    source_number=31,
                ),
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11290",
                    source_number=32,
                ),
                _observation(
                    "sale-contract",
                    "sale",
                    "contract_note",
                    gross_interest="300",
                    net_cash="11290",
                    source_number=33,
                ),
            ],
        )
    )

    result = compute_fixed_income_slice(ledger)

    assert result.interest_income == Decimal("800")
    assert result.tds_credit == Decimal("50")
    assert result.cash_receipts == Decimal("11740")
    assert result.capital_gain_totals == {
        FixedIncomeTaxBucket.LTCG_112: Decimal("990")
    }
    (match,) = result.matched_disposals
    assert match.disposal_event_id == "sale"
    assert match.capital_proceeds == Decimal("11000")
    assert match.interest_component == Decimal("300")
    assert match.cost_basis == Decimal("10000")
    assert match.gain == Decimal("990")
    assert result.filing_values == {
        "ScheduleOS": {
            "InterestOnSecurities": Decimal("800"),
        },
        "ScheduleTDS2": {
            "FixedIncomeTDS": Decimal("50"),
        },
        "ScheduleCG": {
            "STCG50AA": Decimal("0"),
            "STCGOther": Decimal("0"),
            "LTCG112": Decimal("990"),
            "Total": Decimal("990"),
        },
    }
    assert {
        line.output_path for line in result.audit_trace
    } == {
        "/ScheduleOS/InterestOnSecurities",
        "/ScheduleTDS2/FixedIncomeTDS",
        "/ScheduleCG/LTCG112",
    }
    assert all(
        line.evidence_references for line in result.audit_trace
    )
    with pytest.raises(TypeError):
        result.filing_values["ScheduleCG"]["LTCG112"] = Decimal("0")


def test_tds_observation_mismatch_blocks_reconciliation():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "coupon",
                    2,
                    "coupon",
                    "2025-04-30",
                    "0",
                    interest_component="500",
                    tds="50",
                    cash_settlement="450",
                ),
            ],
            observations=[
                _observation(
                    "coupon-bank",
                    "coupon",
                    "bank_statement",
                    net_cash="450",
                    source_number=30,
                ),
                _observation(
                    "coupon-26as",
                    "coupon",
                    "form_26as",
                    gross_interest="500",
                    tds="40",
                    source_number=31,
                ),
            ],
            closing_quantity="10",
            net_cash_receipts="450",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert caught.value.blocker_codes == {"TDS_FORM26AS_MISMATCH"}


@pytest.mark.parametrize(
    ("instrument_kind", "exchange_listed", "expected_bucket"),
    [
        (
            "market_linked_debenture",
            True,
            FixedIncomeTaxBucket.STCG_50AA,
        ),
        ("plain_bond", False, FixedIncomeTaxBucket.STCG_50AA),
        (
            "government_security",
            False,
            FixedIncomeTaxBucket.LTCG_112,
        ),
    ],
)
def test_event_date_rules_route_section_50aa_and_ordinary_debt(
    instrument_kind,
    exchange_listed,
    expected_bucket,
):
    disposal_type = (
        "maturity"
        if instrument_kind == "government_security"
        else "redemption"
    )
    ledger = load_fixed_income_ledger(
        _ledger(
            instrument_kind=instrument_kind,
            exchange_listed=exchange_listed,
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2023-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "exit",
                    2,
                    disposal_type,
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=exchange_listed,
                ),
            ],
            observations=[
                _observation(
                    "exit-bank",
                    "exit",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            net_cash_receipts="11000",
        )
    )

    result = compute_fixed_income_slice(ledger)

    assert result.capital_gain_totals == {
        expected_bucket: Decimal("1000")
    }
    assert result.matched_disposals[0].tax_bucket is expected_bucket


def test_exactly_twelve_month_listed_holding_remains_short_term():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-08-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=True,
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            net_cash_receipts="11000",
        )
    )

    result = compute_fixed_income_slice(ledger)

    assert result.capital_gain_totals == {
        FixedIncomeTaxBucket.STCG_SLAB: Decimal("1000")
    }


@pytest.mark.parametrize(
    "feature",
    [
        "defaulted",
        "restructured",
        "perpetual",
        "convertible",
        "basis_disputed",
    ],
)
def test_unsupported_instrument_outcomes_block_computation(feature):
    ledger = load_fixed_income_ledger(
        _ledger(
            unsupported_features=[feature],
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=True,
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            net_cash_receipts="11000",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert caught.value.blocker_codes == {
        f"UNSUPPORTED_{feature.upper()}"
    }


def test_unresolved_dirty_settlement_blocks_clean_price_gain():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11300",
                    cash_settlement="11300",
                    exchange_listed_on_event=True,
                    settlement_breakdown="unresolved_dirty",
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11300",
                    source_number=30,
                )
            ],
            net_cash_receipts="11300",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert caught.value.blocker_codes == {
        "UNRESOLVED_DIRTY_SETTLEMENT"
    }


def test_demat_transfer_carries_original_fifo_basis_and_holding_period():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2023-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "transfer",
                    2,
                    "transfer",
                    "2025-05-01",
                    "10",
                    account_id="demat-a",
                    to_account_id="demat-b",
                ),
                _event(
                    "sale",
                    3,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=True,
                    account_id="demat-b",
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            account_summaries=[
                {
                    "account_id": "demat-a",
                    "net_cash_receipts": "0",
                    "closing_positions": [],
                    "provenance": _source(90),
                },
                {
                    "account_id": "demat-b",
                    "net_cash_receipts": "11000",
                    "closing_positions": [],
                    "provenance": _source(91),
                },
            ],
        )
    )

    result = compute_fixed_income_slice(ledger)

    (match,) = result.matched_disposals
    assert match.account_id == "demat-b"
    assert match.acquisition_event_id == "purchase"
    assert match.cost_basis == Decimal("10000")
    assert match.tax_bucket is FixedIncomeTaxBucket.LTCG_112


def test_transfer_reorders_original_lots_in_destination_fifo():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "buy-older-source",
                    1,
                    "acquisition",
                    "2023-01-01",
                    "10",
                    capital_component="1000",
                    cash_settlement="1000",
                ),
                _event(
                    "buy-newer-destination",
                    2,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="2000",
                    cash_settlement="2000",
                    account_id="demat-b",
                ),
                _event(
                    "transfer",
                    3,
                    "transfer",
                    "2025-05-01",
                    "10",
                    charges="100",
                    cash_settlement="100",
                    account_id="demat-a",
                    to_account_id="demat-b",
                ),
                _event(
                    "sale",
                    4,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="3000",
                    cash_settlement="3000",
                    exchange_listed_on_event=True,
                    account_id="demat-b",
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="3000",
                    source_number=30,
                )
            ],
            account_summaries=[
                {
                    "account_id": "demat-a",
                    "net_cash_receipts": "0",
                    "closing_positions": [],
                    "provenance": _source(90),
                },
                {
                    "account_id": "demat-b",
                    "net_cash_receipts": "3000",
                    "closing_positions": [
                        {
                            "isin": ISIN,
                            "quantity": "10",
                            "provenance": _source(92),
                        }
                    ],
                    "provenance": _source(91),
                },
            ],
        )
    )

    result = compute_fixed_income_slice(ledger)

    (match,) = result.matched_disposals
    assert match.acquisition_event_id == "buy-older-source"
    assert match.cost_basis == Decimal("1100")
    assert result.closing_positions == {
        ("demat-b", ISIN): Decimal("10")
    }
    (capital_line,) = tuple(
        line
        for line in result.audit_trace
        if line.output_path == "/ScheduleCG/LTCG112"
    )
    assert capital_line.event_ids == (
        "buy-older-source",
        "sale",
        "transfer",
    )
    assert (
        "inputs/fixed-income-3.json#item:3"
        in capital_line.evidence_references
    )


def test_stt_reconciles_cash_but_is_not_deducted_from_section_50aa_gain():
    ledger = load_fixed_income_ledger(
        _ledger(
            instrument_kind="market_linked_debenture",
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10020",
                    stt="20",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    charges="10",
                    stt="20",
                    cash_settlement="10970",
                    exchange_listed_on_event=True,
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="10970",
                    source_number=30,
                )
            ],
            net_cash_receipts="10970",
        )
    )

    result = compute_fixed_income_slice(ledger)

    assert result.capital_gain_totals == {
        FixedIncomeTaxBucket.STCG_50AA: Decimal("990")
    }
    assert result.non_deductible_stt == Decimal("40")


def test_unlisted_government_security_uses_evidenced_legal_form():
    ledger = load_fixed_income_ledger(
        _ledger(
            instrument_kind="government_security",
            legal_form="bond_or_debenture",
            exchange_listed=False,
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2023-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "maturity",
                    2,
                    "maturity",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=False,
                ),
            ],
            observations=[
                _observation(
                    "maturity-bank",
                    "maturity",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            net_cash_receipts="11000",
        )
    )

    result = compute_fixed_income_slice(ledger)

    assert result.capital_gain_totals == {
        FixedIncomeTaxBucket.STCG_50AA: Decimal("1000")
    }


def test_unlisted_statutory_zero_coupon_bond_conflict_blocks():
    ledger = load_fixed_income_ledger(
        _ledger(
            instrument_kind="plain_bond",
            exchange_listed=False,
            statutory_zero_coupon_bond=True,
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2023-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "maturity",
                    2,
                    "maturity",
                    "2025-08-01",
                    "10",
                    capital_component="11000",
                    cash_settlement="11000",
                    exchange_listed_on_event=False,
                ),
            ],
            observations=[
                _observation(
                    "maturity-bank",
                    "maturity",
                    "bank_statement",
                    net_cash="11000",
                    source_number=30,
                )
            ],
            net_cash_receipts="11000",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert caught.value.blocker_codes == {
        "UNLISTED_ZERO_COUPON_50AA_CLASSIFICATION_CONFLICT"
    }


@pytest.mark.parametrize(
    ("extra_observation", "expected_code"),
    [
        (
            _observation(
                "coupon-bank-conflict",
                "coupon",
                "bank_statement",
                net_cash="440",
                source_number=32,
            ),
            "CASH_OBSERVATION_CONFLICT",
        ),
        (
            _observation(
                "coupon-26as-conflict",
                "coupon",
                "form_26as",
                gross_interest="500",
                tds="40",
                source_number=33,
            ),
            "TDS_FORM26AS_CONFLICT",
        ),
    ],
)
def test_conflicting_receipt_sources_block_even_when_one_matches(
    extra_observation,
    expected_code,
):
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "coupon",
                    2,
                    "coupon",
                    "2025-04-30",
                    "0",
                    interest_component="500",
                    tds="50",
                    cash_settlement="450",
                ),
            ],
            observations=[
                _observation(
                    "coupon-bank",
                    "coupon",
                    "bank_statement",
                    net_cash="450",
                    source_number=30,
                ),
                _observation(
                    "coupon-26as",
                    "coupon",
                    "form_26as",
                    gross_interest="500",
                    tds="50",
                    source_number=31,
                ),
                extra_observation,
            ],
            closing_quantity="10",
            net_cash_receipts="450",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert expected_code in caught.value.blocker_codes


def test_source_only_accrued_interest_cannot_remain_in_capital_proceeds():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "sale",
                    2,
                    "sale",
                    "2025-08-01",
                    "10",
                    capital_component="11300",
                    cash_settlement="11300",
                    exchange_listed_on_event=True,
                ),
            ],
            observations=[
                _observation(
                    "sale-bank",
                    "sale",
                    "bank_statement",
                    net_cash="11300",
                    source_number=30,
                ),
                _observation(
                    "sale-contract",
                    "sale",
                    "contract_note",
                    gross_interest="300",
                    net_cash="11300",
                    source_number=31,
                ),
            ],
            net_cash_receipts="11300",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert "INTEREST_OBSERVATION_MISMATCH" in (
        caught.value.blocker_codes
    )


def test_source_only_form26as_tds_cannot_be_omitted_from_event():
    ledger = load_fixed_income_ledger(
        _ledger(
            events=[
                _event(
                    "purchase",
                    1,
                    "acquisition",
                    "2024-01-01",
                    "10",
                    capital_component="10000",
                    cash_settlement="10000",
                ),
                _event(
                    "coupon",
                    2,
                    "coupon",
                    "2025-04-30",
                    "0",
                    interest_component="500",
                    cash_settlement="500",
                ),
            ],
            observations=[
                _observation(
                    "coupon-bank",
                    "coupon",
                    "bank_statement",
                    net_cash="500",
                    source_number=30,
                ),
                _observation(
                    "coupon-26as",
                    "coupon",
                    "form_26as",
                    gross_interest="500",
                    tds="50",
                    source_number=31,
                ),
            ],
            closing_quantity="10",
            net_cash_receipts="500",
        )
    )

    with pytest.raises(FixedIncomeReconciliationError) as caught:
        compute_fixed_income_slice(ledger)

    assert "TDS_FORM26AS_MISMATCH" in caught.value.blocker_codes
