from datetime import date
from decimal import Decimal
from engine.rulebase import validate_rule
from engine.rules.ay2026_27 import TABLE


def test_every_rule_has_full_provenance():
    for r in TABLE.all():
        validate_rule(r)                       # raises if any field missing
        assert r.source_primary.startswith("http")
        assert r.source_secondary.startswith("http")
        assert r.effective_from is not None
        assert r.confidence in {"verified", "contested", "unsupported"}
        # Search-result URLs are not acceptable primaries — they can drift and
        # don't point at a stable statutory text. Primary must be a deep link.
        assert "/search" not in r.source_primary


def test_key_thresholds_present_and_correct():
    d = date(2025, 6, 1)
    assert TABLE.get("holding.listed_equity.lt_months", d).value == 12
    assert TABLE.get("holding.listed_nonequity.lt_months", d).value == 12
    assert TABLE.get("holding.other.lt_months", d).value == 24
    assert TABLE.get("s50aa.acquired_from", d).value == date(2023, 4, 1)
    assert TABLE.get("s115bbh.applies", d).value == Decimal("0.30")


def test_inferred_s50aa_rule_is_not_claimed_as_verified():
    rule = TABLE.get("s50aa.applies", date(2025, 6, 1))

    assert rule.confidence == "contested"
    assert "direct" in rule.confidence_note.lower()
