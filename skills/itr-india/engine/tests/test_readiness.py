from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.bank_interest import (
    ReconciliationBlocker,
    bank_interest_filing_blockers,
)
from engine.readiness import (
    BlockerCategory,
    BlockerOverridePolicy,
    ComputationBasis,
    DecisionJournal,
    DecisionAction,
    FilingBlocker,
    FilingComputationContext,
    FilingReadiness,
    HumanDecision,
    assess_filing_readiness,
)


SCHEDULE_OS_OUTPUT = "/ITR/ITR2/ScheduleOS/IncOthThanOwnRaceHorse/InterestGross"
CONTEXT = FilingComputationContext.create(
    computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
    normalized_input_sha256="a" * 64,
    output_amounts={SCHEDULE_OS_OUTPUT: Decimal("1250")},
)
SUMMARY_CONTEXT = FilingComputationContext.create(
    computation_basis=ComputationBasis.SOURCE_SUMMARY_ONLY,
    normalized_input_sha256="b" * 64,
    output_amounts={SCHEDULE_OS_OUTPUT: Decimal("1250")},
)


def _blocker(
    *,
    blocker_id="bank-interest:missing-bank-anchor:event-1",
    category=BlockerCategory.EVIDENCE_GAP,
    override_policy=BlockerOverridePolicy.ELIGIBLE,
    affected_outputs=(SCHEDULE_OS_OUTPUT,),
):
    return FilingBlocker(
        blocker_id=blocker_id,
        code="MISSING_BANK_ANCHOR",
        message="AIS interest has no bank-issued evidence",
        category=category,
        override_policy=override_policy,
        affected_outputs=affected_outputs,
        evidence_references=("ais.json#/interest/0",),
    )


def _decision(blocker, *, context=CONTEXT, **overrides):
    values = {
        "decision_id": "decision-1",
        "blocker_id": blocker.blocker_id,
        "action": DecisionAction.ACCEPT_RISK,
        "actor": "Devansh Sehgal",
        "decided_at": datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc),
        "reason": "Bank statement is unavailable; AIS amount was checked manually.",
        "evidence_references": ("human-note.md#bank-interest-event-1",),
        "affected_outputs": blocker.affected_outputs,
        "context_fingerprint": context.fingerprint,
    }
    values.update(overrides)
    return HumanDecision(**values)


def _journal(*decisions):
    journal = DecisionJournal.empty("ay2026-27:test-taxpayer")
    for decision in decisions:
        journal = journal.append(decision)
    return journal


def test_readiness_states_are_distinct():
    independently_ready = assess_filing_readiness(
        context=CONTEXT,
        decision_journal=_journal(),
    )
    evidence_gap = _blocker()
    blocked = assess_filing_readiness(
        context=CONTEXT,
        blockers=(evidence_gap,),
        decision_journal=_journal(),
    )
    summary_limitation = _blocker(
        blocker_id="broker-pnl:summary-only",
        category=BlockerCategory.SOURCE_SUMMARY_LIMITATION,
    )
    provisional = assess_filing_readiness(
        context=SUMMARY_CONTEXT,
        blockers=(summary_limitation,),
        decision_journal=_journal(),
    )
    overridden = assess_filing_readiness(
        context=CONTEXT,
        blockers=(evidence_gap,),
        decision_journal=_journal(_decision(evidence_gap)),
    )

    assert independently_ready.state is FilingReadiness.INDEPENDENTLY_FILING_READY
    assert blocked.state is FilingReadiness.BLOCKED
    assert provisional.state is FilingReadiness.PROVISIONAL
    assert overridden.state is FilingReadiness.FILING_READY_BY_HUMAN_OVERRIDE


def test_accepted_risk_retains_original_blocker_and_decision_audit():
    blocker = _blocker()
    decision = _decision(blocker)

    assessment = assess_filing_readiness(
        context=CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(decision),
    )

    assert assessment.blockers == (blocker,)
    assert assessment.accepted_risks == (blocker,)
    assert assessment.active_blockers == ()
    assert assessment.decision_journal.decisions == (decision,)
    assert assessment.applied_decision_ids == ("decision-1",)
    assert assessment.decision_findings == ()
    assert blocker.message in assessment.canonical_json()
    assert decision.actor in assessment.canonical_json()


def test_integrity_failure_cannot_be_overridden():
    blocker = _blocker(
        blocker_id="ledger:duplicate-source",
        category=BlockerCategory.INTEGRITY_FAILURE,
        override_policy=BlockerOverridePolicy.PROHIBITED,
    )

    assessment = assess_filing_readiness(
        context=CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(_decision(blocker)),
    )

    assert assessment.state is FilingReadiness.BLOCKED
    assert assessment.active_blockers == (blocker,)
    assert assessment.accepted_risks == ()
    assert assessment.applied_decision_ids == ()
    assert [finding.code for finding in assessment.decision_findings] == [
        "NON_OVERRIDABLE_BLOCKER"
    ]


def test_integrity_failure_cannot_be_marked_override_eligible():
    with pytest.raises(ValueError, match="integrity failures"):
        _blocker(
            category=BlockerCategory.INTEGRITY_FAILURE,
            override_policy=BlockerOverridePolicy.ELIGIBLE,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"actor": " "}, "actor"),
        ({"reason": ""}, "reason"),
        ({"evidence_references": ()}, "evidence_references"),
        (
            {"decided_at": datetime(2026, 7, 29, 12, 30)},
            "timezone-aware",
        ),
        ({"affected_outputs": ()}, "affected_outputs"),
    ],
)
def test_human_decision_requires_complete_audit_fields(overrides, message):
    blocker = _blocker()

    with pytest.raises(ValueError, match=message):
        _decision(blocker, **overrides)


def test_decision_is_bound_to_the_recomputed_context_and_affected_outputs():
    blocker = _blocker()
    stale_context = _decision(blocker, context_fingerprint="c" * 64)
    wrong_outputs = _decision(
        blocker,
        decision_id="decision-2",
        affected_outputs=("/ITR/ITR2/ScheduleTDS2",),
    )

    assessment = assess_filing_readiness(
        context=CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(stale_context, wrong_outputs),
    )

    assert assessment.state is FilingReadiness.BLOCKED
    assert assessment.applied_decision_ids == ()
    assert [finding.code for finding in assessment.decision_findings] == [
        "AFFECTED_OUTPUTS_MISMATCH",
        "STALE_CONTEXT",
    ]


def test_decision_cannot_accept_an_output_absent_from_computation_context():
    blocker = _blocker()
    empty_context = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256="e" * 64,
        output_amounts={},
    )
    decision = _decision(blocker, context=empty_context)

    assessment = assess_filing_readiness(
        context=empty_context,
        blockers=(blocker,),
        decision_journal=_journal(decision),
    )

    assert assessment.state is FilingReadiness.BLOCKED
    assert assessment.active_blockers == (blocker,)
    assert assessment.applied_decision_ids == ()
    assert [finding.code for finding in assessment.decision_findings] == [
        "AFFECTED_OUTPUTS_NOT_COMPUTED"
    ]


def test_resolving_gap_with_new_evidence_makes_old_decision_stale_not_destructive():
    old_blocker = _blocker()
    old_decision = _decision(old_blocker)

    assessment = assess_filing_readiness(
        context=FilingComputationContext.create(
            computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
            normalized_input_sha256="c" * 64,
            output_amounts={SCHEDULE_OS_OUTPUT: Decimal("1250")},
        ),
        blockers=(),
        decision_journal=_journal(old_decision),
    )

    assert assessment.state is FilingReadiness.INDEPENDENTLY_FILING_READY
    assert assessment.decision_journal.decisions == (old_decision,)
    assert [finding.code for finding in assessment.decision_findings] == [
        "STALE_DECISION"
    ]


def test_source_summary_basis_requires_visible_summary_limitation():
    with pytest.raises(ValueError, match="SOURCE_SUMMARY_LIMITATION"):
        assess_filing_readiness(
            context=SUMMARY_CONTEXT,
            decision_journal=_journal(),
        )


def test_readiness_assessment_is_byte_deterministic():
    blocker = _blocker()
    decision = _decision(blocker)

    first = assess_filing_readiness(
        context=CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(decision),
    )
    second = assess_filing_readiness(
        context=CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(decision),
    )

    assert first.canonical_json() == second.canonical_json()


def test_context_fingerprint_binds_input_and_computed_output_amounts():
    first = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256="d" * 64,
        output_amounts={
            "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals": Decimal("500"),
            SCHEDULE_OS_OUTPUT: Decimal("9250"),
        },
    )
    same_content_different_order = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256="d" * 64,
        output_amounts={
            SCHEDULE_OS_OUTPUT: Decimal("9250"),
            "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals": Decimal("500"),
        },
    )
    changed_output = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256="d" * 64,
        output_amounts={
            SCHEDULE_OS_OUTPUT: Decimal("9251"),
            "/ITR/ITR2/ScheduleTDS2/TotalTDSonOthThanSals": Decimal("500"),
        },
    )

    assert first.fingerprint == same_content_different_order.fingerprint
    assert len(first.fingerprint) == 64
    assert changed_output.fingerprint != first.fingerprint


def test_source_summary_can_become_ready_only_by_visible_human_override():
    blocker = _blocker(
        blocker_id="broker-pnl:summary-only",
        category=BlockerCategory.SOURCE_SUMMARY_LIMITATION,
    )

    assessment = assess_filing_readiness(
        context=SUMMARY_CONTEXT,
        blockers=(blocker,),
        decision_journal=_journal(_decision(blocker, context=SUMMARY_CONTEXT)),
    )

    assert assessment.state is FilingReadiness.FILING_READY_BY_HUMAN_OVERRIDE
    assert assessment.accepted_risks == (blocker,)


@pytest.mark.parametrize(
    "invalid_basis",
    ["independent_evidence", None],
)
def test_readiness_rejects_untyped_computation_basis(invalid_basis):
    with pytest.raises(ValueError, match="computation_basis"):
        FilingComputationContext.create(
            computation_basis=invalid_basis,
            normalized_input_sha256="a" * 64,
            output_amounts={},
        )


@pytest.mark.parametrize(
    ("code", "expected_category", "expected_policy"),
    [
        (
            "INTEREST_MISMATCH",
            BlockerCategory.INTEGRITY_FAILURE,
            BlockerOverridePolicy.PROHIBITED,
        ),
        (
            "MISSING_26AS_CREDIT",
            BlockerCategory.EVIDENCE_GAP,
            BlockerOverridePolicy.ELIGIBLE,
        ),
    ],
)
def test_bank_reconciliation_gaps_map_to_safe_override_policies(
    code,
    expected_category,
    expected_policy,
):
    raw = ReconciliationBlocker(
        code=code,
        message="Bank-interest reconciliation needs attention",
        event_ids=("interest-1",),
        evidence_references=("bank-statement:interest-1",),
    )

    (structured,) = bank_interest_filing_blockers((raw,))

    assert structured.category is expected_category
    assert structured.override_policy is expected_policy
    assert structured.evidence_references == ("bank-statement:interest-1",)
    assert structured.affected_outputs
    assert structured.blocker_id.startswith(f"bank-interest:{code.lower()}:")


def test_unknown_bank_blocker_code_fails_loudly():
    with pytest.raises(ValueError, match="Unsupported bank-interest blocker code"):
        bank_interest_filing_blockers(
            (ReconciliationBlocker("NEW_UNCLASSIFIED_GAP", "Unknown"),)
        )


def test_context_rejects_duplicate_paths_after_normalization():
    with pytest.raises(ValueError, match="Duplicate normalized output path"):
        FilingComputationContext.create(
            computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
            normalized_input_sha256="a" * 64,
            output_amounts=(
                (SCHEDULE_OS_OUTPUT, Decimal("1250")),
                (f" {SCHEDULE_OS_OUTPUT} ", Decimal("9999")),
            ),
        )


def test_decision_journal_is_immutable_append_only_and_hash_chained():
    blocker = _blocker()
    first_decision = _decision(blocker)
    second_decision = _decision(
        blocker,
        decision_id="decision-2",
        decided_at=datetime(2026, 7, 29, 13, 0, tzinfo=timezone.utc),
    )
    empty = DecisionJournal.empty("ay2026-27:test-taxpayer")

    first_revision = empty.append(first_decision)
    second_revision = first_revision.append(second_decision)

    assert empty.decisions == ()
    assert first_revision.decisions == (first_decision,)
    assert second_revision.decisions == (first_decision, second_decision)
    assert second_revision.entries[1].previous_entry_sha256 == (
        first_revision.history_sha256
    )
    assert second_revision.history_sha256 != first_revision.history_sha256
    assert second_revision.verify_history() is True


def test_decision_journal_rejects_broken_history():
    blocker = _blocker()
    journal = _journal(_decision(blocker))
    broken_entry = journal.entries[0].with_previous_entry_sha256("f" * 64)

    with pytest.raises(ValueError, match="history chain"):
        DecisionJournal(
            journal_id=journal.journal_id,
            entries=(broken_entry,),
        )
