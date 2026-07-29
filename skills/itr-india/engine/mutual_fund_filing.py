"""Filing projection and audit trace for reconciled mutual-fund gains."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping

from engine.mutual_fund_classification import FundClassificationAssessment
from engine.mutual_fund_ledger import MutualFundLedger
from engine.mutual_fund_reconciliation import MutualFundFifoResult
from engine.mutual_fund_types import (
    FundAuditLine,
    FundTaxBucket,
    MatchedFundDisposal,
    MutualFundBlocker,
    MutualFundSlice,
    freeze,
    merge_provenance,
)
from engine.readiness import (
    BlockerCategory,
    BlockerOverridePolicy,
    ComputationBasis,
    DecisionJournal,
    FilingBlocker,
    FilingComputationContext,
    FilingReadiness,
    assess_filing_readiness,
)


def build_mutual_fund_slice(
    ledger: MutualFundLedger,
    assessment: FundClassificationAssessment,
    fifo: MutualFundFifoResult,
    decision_journal: DecisionJournal,
) -> MutualFundSlice:
    filing_values = _filing_values(fifo.bucket_totals)
    output_amounts = _output_amounts(
        filing_values,
        fifo.matched_disposals,
    )
    context = FilingComputationContext.create(
        computation_basis=ComputationBasis.INDEPENDENT_EVIDENCE,
        normalized_input_sha256=sha256(
            ledger.model_dump_json().encode("utf-8")
        ).hexdigest(),
        output_amounts=output_amounts,
    )
    readiness = assess_filing_readiness(
        context=context,
        decision_journal=decision_journal,
        blockers=tuple(
            _filing_blocker(blocker, tuple(output_amounts))
            for blocker in assessment.blockers
        ),
    )
    return MutualFundSlice(
        classifications=assessment.classifications,
        classification_intervals=assessment.classification_intervals,
        bucket_totals=fifo.bucket_totals,
        independently_ready=(
            readiness.state
            is FilingReadiness.INDEPENDENTLY_FILING_READY
        ),
        blockers=assessment.blockers,
        research_manifest=assessment.research_manifest,
        matched_disposals=fifo.matched_disposals,
        closing_positions=fifo.closing_positions,
        filing_values=freeze(filing_values),
        audit_trace=_audit_trace(
            fifo.matched_disposals,
            fifo.bucket_totals,
        ),
        readiness=readiness,
        provisional_classifications=freeze({}),
        provisional_bucket_totals=freeze({}),
        provisional_matched_disposals=(),
        provisional_filing_values=freeze({}),
        applied_classification_decision_ids=(),
        classification_decision_findings=(),
    )


def _output_amounts(
    filing_values: Mapping[str, Any],
    matches: tuple[MatchedFundDisposal, ...],
) -> dict[str, Decimal]:
    schedule = filing_values["ScheduleCG"]
    output_amounts = {
        f"/ScheduleCG/{key}": amount
        for key, amount in schedule.items()
    }
    output_amounts["/MutualFund/UnclassifiedGain"] = sum(
        (
            match.gain
            for match in matches
            if match.tax_bucket is None
        ),
        Decimal("0"),
    )
    return output_amounts


def _filing_blocker(
    blocker: MutualFundBlocker,
    affected_outputs: tuple[str, ...],
) -> FilingBlocker:
    identity = json.dumps(
        {
            "code": blocker.code,
            "evidence_references": blocker.evidence_references,
            "message": blocker.message,
            "scheme_ids": blocker.scheme_ids,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    suffix = sha256(identity.encode("utf-8")).hexdigest()[:16]
    integrity_codes = {
        "CONFLICTING_PRIMARY_CLASSIFICATION_EVIDENCE",
        "INVALID_CLASSIFICATION_AVERAGING_METHOD",
    }
    category = (
        BlockerCategory.INTEGRITY_FAILURE
        if blocker.code in integrity_codes
        else BlockerCategory.EVIDENCE_GAP
    )
    return FilingBlocker(
        blocker_id=f"mutual-fund:{blocker.code.lower()}:{suffix}",
        code=blocker.code,
        message=blocker.message,
        category=category,
        override_policy=BlockerOverridePolicy.PROHIBITED,
        affected_outputs=affected_outputs,
        evidence_references=blocker.evidence_references,
    )


def _filing_values(
    totals: Mapping[FundTaxBucket, Decimal],
) -> dict[str, Any]:
    schedule = {
        "STCG111A": totals.get(
            FundTaxBucket.STCG_111A,
            Decimal("0"),
        ),
        "LTCG112A": totals.get(
            FundTaxBucket.LTCG_112A,
            Decimal("0"),
        ),
        "STCG50AA": totals.get(
            FundTaxBucket.STCG_50AA,
            Decimal("0"),
        ),
        "STCGOther": totals.get(
            FundTaxBucket.STCG_SLAB,
            Decimal("0"),
        ),
        "LTCG112": totals.get(
            FundTaxBucket.LTCG_112,
            Decimal("0"),
        ),
    }
    schedule["Total"] = sum(schedule.values(), Decimal("0"))
    return {"ScheduleCG": schedule}


def _audit_trace(
    matches: tuple[MatchedFundDisposal, ...],
    totals: Mapping[FundTaxBucket, Decimal],
) -> tuple[FundAuditLine, ...]:
    path_by_bucket = {
        FundTaxBucket.STCG_111A: "STCG111A",
        FundTaxBucket.LTCG_112A: "LTCG112A",
        FundTaxBucket.STCG_50AA: "STCG50AA",
        FundTaxBucket.STCG_SLAB: "STCGOther",
        FundTaxBucket.LTCG_112: "LTCG112",
    }
    lines: list[FundAuditLine] = []
    for bucket, amount in sorted(
        totals.items(),
        key=lambda item: item[0].value,
    ):
        bucket_matches = tuple(
            match for match in matches if match.tax_bucket is bucket
        )
        provenance = merge_provenance(
            *(
                match.source_provenance
                for match in bucket_matches
            )
        )
        lines.append(
            FundAuditLine(
                output_path=f"/ScheduleCG/{path_by_bucket[bucket]}",
                amount=amount,
                transformation=(
                    "account-local-fifo-then-statutory-fund-classification"
                ),
                acquisition_event_ids=tuple(
                    sorted(
                        {
                            match.acquisition_event_id
                            for match in bucket_matches
                        }
                    )
                ),
                disposal_event_ids=tuple(
                    sorted(
                        {
                            match.disposal_event_id
                            for match in bucket_matches
                        }
                    )
                ),
                evidence_references=tuple(
                    sorted(
                        {
                            reference
                            for match in bucket_matches
                            for reference in match.evidence_references
                        }
                    )
                ),
                source_provenance=provenance,
            )
        )
    return tuple(lines)
