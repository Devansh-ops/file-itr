import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine.bank_interest import (
    BankReconciliationError,
    LedgerValidationError,
    LedgerVersionError,
    build_bank_interest_itr2_draft,
    compute_bank_interest_slice,
    load_bank_interest_ledger,
)
from engine.contracts import OfficialContractRegistry


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def _record(
    event_id,
    evidence_type,
    *,
    source_n,
    account_id="hdfc-savings",
    bank_name="HDFC Bank",
    account_last4="1234",
    ownership="self",
    ownership_share="1",
    interest_kind="savings",
    gross_interest="1250",
    tds_amount=None,
    deductor_tan=None,
    evidence_reference=None,
):
    return {
        "event_id": event_id,
        "evidence_type": evidence_type,
        "evidence_reference": evidence_reference or f"{evidence_type}:{event_id}",
        "account_id": account_id,
        "bank_name": bank_name,
        "account_last4": account_last4,
        "ownership": ownership,
        "ownership_share": ownership_share,
        "interest_kind": interest_kind,
        "period_start": "2025-04-01",
        "period_end": "2026-03-31",
        "gross_interest": gross_interest,
        "tds_amount": tds_amount,
        "deductor_tan": deductor_tan,
        "provenance": {
            "source_document": f"inputs/source-{source_n}.pdf",
            "source_sha256": f"{source_n:x}" * 64,
            "source_location": f"page:1/table:interest/row:{source_n}",
            "importer": "bank-interest-fixture",
            "importer_version": "1.0.0",
        },
    }


def _ledger(evidence_rows):
    return {
        "schema_version": "1.0",
        "assessment_year": "2026-27",
        "evidence_rows": evidence_rows,
    }


def _reconciled_records():
    return [
        _record("savings-1", "bank_statement", source_n=1),
        _record("savings-1", "ais", source_n=2),
        _record(
            "fd-1",
            "bank_statement",
            source_n=3,
            account_id="icici-fd",
            bank_name="ICICI Bank",
            account_last4="5678",
            interest_kind="term_deposit",
            gross_interest="5000",
            tds_amount="500",
            deductor_tan="DELA12345B",
        ),
        _record(
            "fd-1",
            "ais",
            source_n=4,
            account_id="icici-fd",
            bank_name="ICICI Bank",
            account_last4="5678",
            interest_kind="term_deposit",
            gross_interest="5000",
            tds_amount="500",
            deductor_tan="DELA12345B",
        ),
        _record(
            "fd-1",
            "form_26as",
            source_n=5,
            account_id="icici-fd",
            bank_name="ICICI Bank",
            account_last4="5678",
            interest_kind="term_deposit",
            gross_interest="5000",
            tds_amount="500",
            deductor_tan="DELA12345B",
        ),
        _record(
            "fd-2",
            "bank_statement",
            source_n=6,
            account_id="sbi-fd",
            bank_name="State Bank of India",
            account_last4="9012",
            interest_kind="term_deposit",
            gross_interest="3000",
        ),
    ]


def _base_itr2():
    return json.loads((FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8"))


def test_v1_ledger_validates_with_decimal_amounts_and_full_provenance():
    loaded = load_bank_interest_ledger(_ledger(_reconciled_records()))

    assert loaded.ledger.schema_version == "1.0"
    assert loaded.ledger.evidence_rows[0].gross_interest == Decimal("1250")
    assert loaded.ledger.evidence_rows[0].provenance.importer_version == "1.0.0"
    assert loaded.migrations == ()


def test_v0_1_ledger_migrates_explicitly_to_v1():
    legacy = {
        "schema_version": "0.1",
        "ay": "2026-27",
        "entries": [_record("savings-1", "bank_statement", source_n=1)],
    }

    loaded = load_bank_interest_ledger(legacy)

    assert loaded.ledger.schema_version == "1.0"
    assert loaded.ledger.assessment_year == "2026-27"
    assert loaded.migrations == ("bank-interest:0.1->1.0",)


def test_unknown_ledger_version_fails_loudly():
    with pytest.raises(LedgerVersionError, match="not supported"):
        load_bank_interest_ledger({"schema_version": "9.9", "evidence_rows": []})


def test_invalid_provenance_hash_is_a_ledger_validation_error():
    record = _record("savings-1", "bank_statement", source_n=1)
    record["provenance"]["source_sha256"] = "not-a-sha"

    with pytest.raises(LedgerValidationError, match="source_sha256"):
        load_bank_interest_ledger(_ledger([record]))


def test_multiple_accounts_compute_schedule_os_tds_trace_and_valid_itr2_draft():
    loaded = load_bank_interest_ledger(_ledger(_reconciled_records()))

    result = compute_bank_interest_slice(loaded.ledger)
    itr2_draft = build_bank_interest_itr2_draft(_base_itr2(), result)

    assert result.savings_interest == Decimal("1250")
    assert result.term_deposit_interest == Decimal("8000")
    assert result.total_interest == Decimal("9250")
    assert result.tds_claimed == Decimal("500")
    assert result.schedule_os["IncOthThanOwnRaceHorse"]["InterestGross"] == 9250
    assert result.schedule_os["IncOthThanOwnRaceHorse"]["IntrstFrmSavingBank"] == 1250
    assert result.schedule_os["IncOthThanOwnRaceHorse"]["IntrstFrmTermDeposit"] == 8000
    assert result.schedule_tds2["TotalTDSonOthThanSals"] == 500
    assert itr2_draft["ITR"]["ITR2"]["ScheduleTDS2"]["TDSOthThanSalaryDtls"] == [
        {
            "TDSCreditName": "S",
            "TANOfDeductor": "DELA12345B",
            "TDSSection": "94A",
            "TaxDeductCreditDtls": {
                "TaxDeductedOwnHands": 500,
                "TaxClaimedOwnHands": 500,
            },
            "GrossAmount": 5000,
            "HeadOfIncome": "OS",
            "AmtCarriedFwd": 0,
        }
    ]
    assert itr2_draft["ITR"]["ITR2"]["ScheduleOS"] == result.schedule_os
    OfficialContractRegistry.for_assessment_year("2026-27").validate(
        "ITR-2", itr2_draft
    )

    assert result.audit_trace
    for line in result.audit_trace:
        assert line.account_ownership
        assert line.sources
        for source in line.sources:
            assert source.source_location
            assert source.importer_version
            assert len(source.source_sha256) == 64


@pytest.mark.parametrize("invalid_itr2", ["not-an-object", []])
def test_itr2_draft_builder_blocks_a_non_object_itr2_base(invalid_itr2):
    filing_slice = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger(_reconciled_records())).ledger
    )

    with pytest.raises(BankReconciliationError) as caught:
        build_bank_interest_itr2_draft(
            {"ITR": {"ITR2": invalid_itr2}},
            filing_slice,
        )

    assert [blocker.code for blocker in caught.value.blockers] == [
        "INVALID_ITR2_BASE"
    ]


def test_repeated_computation_is_byte_deterministic():
    loaded = load_bank_interest_ledger(_ledger(_reconciled_records()))

    first = compute_bank_interest_slice(loaded.ledger)
    second = compute_bank_interest_slice(loaded.ledger)
    first_draft = build_bank_interest_itr2_draft(_base_itr2(), first)
    second_draft = build_bank_interest_itr2_draft(
        copy.deepcopy(_base_itr2()),
        second,
    )

    assert first.canonical_json() == second.canonical_json()
    assert json.dumps(first_draft, sort_keys=True) == json.dumps(
        second_draft,
        sort_keys=True,
    )


@pytest.mark.parametrize("evidence_type", ["bank_statement", "ais", "form_26as"])
def test_duplicate_evidence_for_an_event_blocks(evidence_type):
    records = _reconciled_records()
    original = next(
        record
        for record in records
        if record["event_id"] == "fd-1" and record["evidence_type"] == evidence_type
    )
    duplicate = copy.deepcopy(original)
    duplicate["provenance"]["source_sha256"] = "a" * 64
    duplicate["provenance"]["source_location"] = "page:2/duplicate"

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger(records + [duplicate])).ledger
        )

    assert "DUPLICATE_EVIDENCE" in exc.value.blocker_codes


def test_renaming_an_identical_source_does_not_hide_duplicate_import():
    bank = _record("savings-1", "bank_statement", source_n=1)
    ais = _record("savings-1", "ais", source_n=2)
    ais["provenance"].update(
        {
            "source_sha256": bank["provenance"]["source_sha256"],
            "source_location": bank["provenance"]["source_location"],
            "source_document": "inputs/renamed-copy.pdf",
        }
    )

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger([bank, ais])).ledger
        )

    assert "DUPLICATE_SOURCE" in exc.value.blocker_codes


def test_duplicate_bank_event_with_different_event_ids_blocks():
    original = _record(
        "savings-1",
        "bank_statement",
        source_n=1,
        evidence_reference="annual-interest:1234:2025-26",
    )
    duplicate = _record(
        "savings-copy",
        "bank_statement",
        source_n=2,
        evidence_reference="annual-interest:1234:2025-26",
    )

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger([original, duplicate])).ledger
        )

    assert "DUPLICATE_BANK_EVENT" in exc.value.blocker_codes


def test_distinct_bank_references_in_same_account_and_period_are_allowed():
    first = _record(
        "fd-1",
        "bank_statement",
        source_n=1,
        evidence_reference="deposit:one",
    )
    second = _record(
        "fd-2",
        "bank_statement",
        source_n=2,
        evidence_reference="deposit:two",
    )

    result = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger([first, second])).ledger
    )

    assert result.total_interest == Decimal("2500")


@pytest.mark.parametrize("evidence_type", ["ais", "form_26as"])
def test_unexplained_tax_portal_entry_without_bank_anchor_blocks(evidence_type):
    records = [
        _record(
            "unmatched-1",
            evidence_type,
            source_n=7,
            gross_interest="1000",
            tds_amount="100" if evidence_type == "form_26as" else None,
            deductor_tan="DELA12345B" if evidence_type == "form_26as" else None,
        )
    ]

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger(records)).ledger
        )

    assert "UNEXPLAINED_PORTAL_ENTRY" in exc.value.blocker_codes


def test_amount_mismatch_between_bank_and_ais_blocks():
    records = _reconciled_records()
    ais = next(
        record
        for record in records
        if record["event_id"] == "savings-1" and record["evidence_type"] == "ais"
    )
    ais["gross_interest"] = "1300"

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger(records)).ledger
        )

    assert "INTEREST_MISMATCH" in exc.value.blocker_codes


def test_bank_reported_tds_without_26as_credit_blocks():
    records = [
        _record(
            "fd-1",
            "bank_statement",
            source_n=3,
            interest_kind="term_deposit",
            gross_interest="5000",
            tds_amount="500",
            deductor_tan="DELA12345B",
        )
    ]

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger(records)).ledger
        )

    assert "MISSING_26AS_CREDIT" in exc.value.blocker_codes


def test_26as_row_must_itself_confirm_claimed_tds_and_tan():
    bank = _record(
        "fd-1",
        "bank_statement",
        source_n=1,
        interest_kind="term_deposit",
        gross_interest="5000",
        tds_amount="500",
        deductor_tan="DELA12345B",
    )
    empty_26as = _record(
        "fd-1",
        "form_26as",
        source_n=2,
        interest_kind="term_deposit",
        gross_interest="5000",
        tds_amount=None,
        deductor_tan=None,
    )

    with pytest.raises(LedgerValidationError, match="Form 26AS"):
        load_bank_interest_ledger(_ledger([bank, empty_26as]))


def test_unresolved_joint_ownership_blocks():
    records = [
        _record(
            "savings-1",
            "bank_statement",
            source_n=1,
            ownership="joint_unresolved",
            ownership_share=None,
        )
    ]

    with pytest.raises(BankReconciliationError) as exc:
        compute_bank_interest_slice(
            load_bank_interest_ledger(_ledger(records)).ledger
        )

    assert "OWNERSHIP_UNRESOLVED" in exc.value.blocker_codes


def test_schedule_rounding_is_explicit_in_audit_trace():
    records = [
        _record(
            "savings-1",
            "bank_statement",
            source_n=1,
            gross_interest="1000.50",
        )
    ]

    result = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger(records)).ledger
    )
    total_line = next(
        line for line in result.audit_trace if line.output_path.endswith("/InterestGross")
    )

    assert result.schedule_os["IncOthThanOwnRaceHorse"]["InterestGross"] == 1001
    assert total_line.input_amount == Decimal("1000.50")
    assert total_line.amount == Decimal("1001")
    assert total_line.transformation == "largest-remainder-to-rounded-total-INR"


def test_cross_category_rounding_preserves_schedule_total_invariant():
    records = [
        _record(
            "savings-1",
            "bank_statement",
            source_n=1,
            gross_interest="0.50",
        ),
        _record(
            "fd-1",
            "bank_statement",
            source_n=2,
            account_id="hdfc-fd",
            account_last4="5678",
            interest_kind="term_deposit",
            gross_interest="0.50",
        ),
    ]

    result = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger(records)).ledger
    )
    income = result.schedule_os["IncOthThanOwnRaceHorse"]

    assert income["InterestGross"] == 1
    assert (
        income["IntrstFrmSavingBank"]
        + income["IntrstFrmTermDeposit"]
        + income["IntrstFrmOthers"]
        == income["InterestGross"]
    )


def test_every_nonzero_filing_amount_has_provenance_trace():
    result = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger(_reconciled_records())).ledger
    )
    traced_paths = {line.output_path for line in result.audit_trace}
    expected_paths = {
        "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/GrossIncChrgblTaxAtAppRate",
        "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/InterestGross",
        "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/IntrstFrmSavingBank",
        "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/IntrstFrmTermDeposit",
        "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/BalanceNoRaceHorse",
        "/ITR/ITR2/ScheduleOS/TotOthSrcNoRaceHorse",
        "/ITR/ITR2/ScheduleOS/IncChargeable",
        "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals",
        "/ITR/ITR2/ScheduleTDS2/TDSOthThanSalaryDtls/0"
        "/TaxDeductCreditDtls/TaxDeductedOwnHands",
        "/ITR/ITR2/ScheduleTDS2/TDSOthThanSalaryDtls/0"
        "/TaxDeductCreditDtls/TaxClaimedOwnHands",
        "/ITR/ITR2/ScheduleTDS2/TDSOthThanSalaryDtls/0/GrossAmount",
    }

    assert traced_paths == expected_paths
    assert all(line.account_ownership and line.sources for line in result.audit_trace)


def test_filing_slice_schedules_are_immutable():
    result = compute_bank_interest_slice(
        load_bank_interest_ledger(_ledger(_reconciled_records())).ledger
    )

    with pytest.raises(TypeError):
        result.schedule_os["IncChargeable"] = 0
    with pytest.raises(TypeError):
        result.schedule_os["IncOthThanOwnRaceHorse"]["InterestGross"] = 0
    with pytest.raises(TypeError):
        result.schedule_tds2["TDSOthThanSalaryDtls"][0]["GrossAmount"] = 0
