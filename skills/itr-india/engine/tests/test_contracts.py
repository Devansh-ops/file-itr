import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.contracts import (
    OfficialContractRegistry,
    OfficialContractValidationError,
)
from engine.model import AssetClass, CapitalGainItem
from engine.rulebase import RuleReadinessError
from engine.rules.ay2026_27 import TABLE
from engine.trace import Trace, trace_bucketing


FIXTURES = Path(__file__).parent / "fixtures" / "contracts"


def test_ay2026_27_manifest_pins_official_itr2_and_itr3_contracts():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")

    assert {contract.form for contract in registry.contracts()} == {"ITR-2", "ITR-3"}
    for contract in registry.contracts():
        assert contract.schema_version == "1.1"
        assert contract.schema_release_date.isoformat() == "2026-06-30"
        assert contract.schema_source_url.startswith("https://www.incometax.gov.in/")
        assert contract.schema_sha256
        assert contract.validation_version == "1.0"
        assert contract.validation_source_url.startswith("https://www.incometax.gov.in/")
        assert contract.validation_sha256

    registry.verify_pins()


def test_validation_rule_artifact_pins_are_locally_verifiable():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")

    for contract in registry.contracts():
        contract.verify_validation_pin()


@pytest.mark.parametrize("form", ["ITR-2", "ITR-3"])
def test_minimal_official_fixture_validates_locally(form):
    registry = OfficialContractRegistry.for_assessment_year("2026-27")
    fixture = FIXTURES / f"{form.lower().replace('-', '')}-minimal.json"

    registry.validate(form, json.loads(fixture.read_text(encoding="utf-8")))


def test_payload_outside_official_contract_is_rejected():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")

    with pytest.raises(OfficialContractValidationError, match="UnexpectedPayload"):
        registry.validate("ITR-2", {"UnexpectedPayload": True})


def test_unpinned_assessment_year_fails_loudly():
    with pytest.raises(OfficialContractValidationError, match="not pinned"):
        OfficialContractRegistry.for_assessment_year("2025-26")


def test_invalid_assessment_year_cannot_control_manifest_path():
    with pytest.raises(OfficialContractValidationError, match="invalid format"):
        OfficialContractRegistry.for_assessment_year("../2026-27")


def test_non_object_manifest_uses_domain_error(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    with pytest.raises(OfficialContractValidationError, match="JSON object"):
        OfficialContractRegistry(manifest)


def test_filing_boundary_refuses_unverified_rule_used_by_computation():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")
    fixture = json.loads(
        (FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8")
    )
    item = CapitalGainItem(
        AssetClass.GOLD_ETF_LISTED,
        date(2025, 1, 1),
        date(2026, 5, 1),
        Decimal("20000"),
        Decimal("0"),
    )
    trace = trace_bucketing([item], TABLE, date(2025, 6, 1))

    with pytest.raises(RuleReadinessError, match="contested"):
        registry.validate_filing_package(
            "ITR-2",
            fixture,
            trace=trace,
            on=date(2025, 6, 1),
        )


def test_filing_boundary_refuses_empty_rule_usage_evidence():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")
    fixture = json.loads(
        (FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8")
    )

    with pytest.raises(RuleReadinessError, match="no rule usage evidence"):
        registry.validate_filing_package(
            "ITR-2",
            fixture,
            trace=Trace(),
            on=date(2025, 6, 1),
        )


def test_filing_boundary_ignores_unrelated_contested_rules():
    registry = OfficialContractRegistry.for_assessment_year("2026-27")
    fixture = json.loads(
        (FIXTURES / "itr2-minimal.json").read_text(encoding="utf-8")
    )
    item = CapitalGainItem(
        AssetClass.LISTED_EQUITY_STT,
        date(2024, 1, 1),
        date(2024, 11, 1),
        Decimal("30000"),
        Decimal("0"),
        stt_paid=True,
    )
    trace = trace_bucketing([item], TABLE, date(2025, 6, 1))

    registry.validate_filing_package(
        "ITR-2",
        fixture,
        trace=trace,
        on=date(2025, 6, 1),
    )
