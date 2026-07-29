from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from engine.bank_interest_ledger import (
    BankInterestEvidenceRow,
    BankInterestLedger,
    EvidenceType,
    InterestKind,
    OwnershipType,
    SourceProvenance,
)


@dataclass(frozen=True)
class ReconciliationBlocker:
    code: str
    message: str
    event_ids: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()


class BankReconciliationError(ValueError):
    def __init__(self, blockers: list[ReconciliationBlocker]):
        ordered = tuple(
            sorted(
                blockers,
                key=lambda blocker: (
                    blocker.code,
                    blocker.event_ids,
                    blocker.evidence_references,
                    blocker.message,
                ),
            )
        )
        self.blockers = ordered
        self.blocker_codes = frozenset(blocker.code for blocker in ordered)
        details = "; ".join(
            f"{blocker.code}: {blocker.message}" for blocker in ordered
        )
        super().__init__(f"Bank-interest reconciliation blocked: {details}")


@dataclass(frozen=True)
class AccountOwnershipTrace:
    account_id: str
    ownership: OwnershipType
    ownership_share: Decimal | None


@dataclass(frozen=True)
class ReconciledInterestEvent:
    event_id: str
    account_id: str
    interest_kind: InterestKind
    gross_interest: Decimal
    tds_amount: Decimal
    deductor_tan: str | None
    ownership: AccountOwnershipTrace
    sources: tuple[SourceProvenance, ...]


@dataclass(frozen=True)
class BankReconciliationResult:
    events: tuple[ReconciledInterestEvent, ...]
    blockers: tuple[ReconciliationBlocker, ...]


def inspect_bank_interest_reconciliation(
    ledger: BankInterestLedger,
) -> BankReconciliationResult:
    blockers: list[ReconciliationBlocker] = []
    evidence_rows = sorted(
        ledger.evidence_rows,
        key=lambda row: (
            row.event_id,
            row.evidence_type.value,
            row.provenance.sort_key(),
        ),
    )
    _check_duplicate_sources(evidence_rows, blockers)
    _check_account_metadata(evidence_rows, blockers)
    _check_duplicate_bank_anchors(evidence_rows, blockers)

    events: list[ReconciledInterestEvent] = []
    by_event: dict[str, list[BankInterestEvidenceRow]] = defaultdict(list)
    for row in evidence_rows:
        by_event[row.event_id].append(row)

    for event_id in sorted(by_event):
        event_rows = by_event[event_id]
        by_type: dict[EvidenceType, list[BankInterestEvidenceRow]] = defaultdict(list)
        for row in event_rows:
            by_type[row.evidence_type].append(row)
        for evidence_type, typed_rows in sorted(
            by_type.items(),
            key=lambda pair: pair[0].value,
        ):
            if len(typed_rows) > 1:
                blockers.append(
                    ReconciliationBlocker(
                        "DUPLICATE_EVIDENCE",
                        f"{event_id} has {len(typed_rows)} {evidence_type.value} rows",
                        (event_id,),
                        _evidence_refs(typed_rows),
                    )
                )

        bank_rows = by_type.get(EvidenceType.BANK_STATEMENT, [])
        if not bank_rows:
            blockers.append(
                ReconciliationBlocker(
                    "UNEXPLAINED_PORTAL_ENTRY",
                    f"{event_id} has AIS/26AS evidence without a bank anchor",
                    (event_id,),
                    _evidence_refs(event_rows),
                )
            )
            continue
        if len(bank_rows) != 1 or any(len(rows) > 1 for rows in by_type.values()):
            continue
        bank = bank_rows[0]

        if (
            bank.ownership is not OwnershipType.SELF
            or bank.ownership_share != Decimal("1")
        ):
            blockers.append(
                ReconciliationBlocker(
                    "OWNERSHIP_UNRESOLVED",
                    f"{event_id} account {bank.account_id} is not established as 100% self-owned",
                    (event_id,),
                    _evidence_refs((bank,)),
                )
            )

        for row in event_rows:
            if (
                row.account_id != bank.account_id
                or row.interest_kind is not bank.interest_kind
                or row.period_start != bank.period_start
                or row.period_end != bank.period_end
            ):
                blockers.append(
                    ReconciliationBlocker(
                        "EVENT_METADATA_MISMATCH",
                        f"{event_id} evidence maps to different accounts, kinds, or periods",
                        (event_id,),
                        _evidence_refs((bank, row)),
                    )
                )
            if row.gross_interest != bank.gross_interest:
                blockers.append(
                    ReconciliationBlocker(
                        "INTEREST_MISMATCH",
                        f"{event_id} bank amount {bank.gross_interest} does not match "
                        f"{row.evidence_type.value} amount {row.gross_interest}",
                        (event_id,),
                        _evidence_refs((bank, row)),
                    )
                )

        stated_tds = {
            row.tds_amount for row in event_rows if row.tds_amount is not None
        }
        if len(stated_tds) > 1:
            blockers.append(
                ReconciliationBlocker(
                    "TDS_MISMATCH",
                    f"{event_id} contains inconsistent TDS amounts",
                    (event_id,),
                    _evidence_refs(event_rows),
                )
            )
        stated_tans = {
            row.deductor_tan for row in event_rows if row.deductor_tan is not None
        }
        if len(stated_tans) > 1:
            blockers.append(
                ReconciliationBlocker(
                    "TAN_MISMATCH",
                    f"{event_id} contains inconsistent deductor TANs",
                    (event_id,),
                    _evidence_refs(event_rows),
                )
            )

        form_26as_rows = by_type.get(EvidenceType.FORM_26AS, [])
        positive_tds_reported = any(
            amount is not None and amount > 0
            for amount in (row.tds_amount for row in event_rows)
        )
        if positive_tds_reported and not form_26as_rows:
            blockers.append(
                ReconciliationBlocker(
                    "MISSING_26AS_CREDIT",
                    f"{event_id} reports TDS but has no Form 26AS credit",
                    (event_id,),
                    _evidence_refs(event_rows),
                )
            )
        if form_26as_rows:
            credit = form_26as_rows[0]
            tds_amount = credit.tds_amount or Decimal("0")
            tan = credit.deductor_tan
        else:
            tds_amount = Decimal("0")
            tan = None

        events.append(
            ReconciledInterestEvent(
                event_id=event_id,
                account_id=bank.account_id,
                interest_kind=bank.interest_kind,
                gross_interest=bank.gross_interest,
                tds_amount=tds_amount,
                deductor_tan=tan,
                ownership=AccountOwnershipTrace(
                    account_id=bank.account_id,
                    ownership=bank.ownership,
                    ownership_share=bank.ownership_share,
                ),
                sources=tuple(
                    sorted(
                        (row.provenance for row in event_rows),
                        key=SourceProvenance.sort_key,
                    )
                ),
            )
        )

    return BankReconciliationResult(
        events=tuple(sorted(events, key=lambda event: event.event_id)),
        blockers=tuple(
            sorted(
                blockers,
                key=lambda blocker: (
                    blocker.code,
                    blocker.event_ids,
                    blocker.evidence_references,
                    blocker.message,
                ),
            )
        ),
    )


def reconcile_bank_interest(
    ledger: BankInterestLedger,
) -> tuple[ReconciledInterestEvent, ...]:
    result = inspect_bank_interest_reconciliation(ledger)
    if result.blockers:
        raise BankReconciliationError(list(result.blockers))
    return result.events


def _check_duplicate_sources(
    evidence_rows: list[BankInterestEvidenceRow],
    blockers: list[ReconciliationBlocker],
) -> None:
    by_source: dict[tuple[str, ...], list[BankInterestEvidenceRow]] = defaultdict(list)
    for row in evidence_rows:
        by_source[row.provenance.identity_key()].append(row)
    for duplicates in by_source.values():
        if len(duplicates) > 1:
            event_ids = tuple(sorted({row.event_id for row in duplicates}))
            blockers.append(
                ReconciliationBlocker(
                    "DUPLICATE_SOURCE",
                    "The same source location was imported more than once",
                    event_ids,
                    _evidence_refs(duplicates),
                )
            )


def _check_account_metadata(
    evidence_rows: list[BankInterestEvidenceRow],
    blockers: list[ReconciliationBlocker],
) -> None:
    by_account: dict[str, list[BankInterestEvidenceRow]] = defaultdict(list)
    for row in evidence_rows:
        by_account[row.account_id].append(row)
    for account_id, account_rows in sorted(by_account.items()):
        identities = {
            (
                row.bank_name,
                row.account_last4,
                row.ownership,
                row.ownership_share,
            )
            for row in account_rows
        }
        if len(identities) > 1:
            blockers.append(
                ReconciliationBlocker(
                    "ACCOUNT_METADATA_MISMATCH",
                    f"Account {account_id} has inconsistent identity or ownership metadata",
                    tuple(sorted({row.event_id for row in account_rows})),
                    _evidence_refs(account_rows),
                )
            )


def _check_duplicate_bank_anchors(
    evidence_rows: list[BankInterestEvidenceRow],
    blockers: list[ReconciliationBlocker],
) -> None:
    by_anchor: dict[tuple[str, str], list[BankInterestEvidenceRow]] = defaultdict(list)
    for row in evidence_rows:
        if row.evidence_type is EvidenceType.BANK_STATEMENT:
            by_anchor[(row.account_id, row.evidence_reference)].append(row)
    for duplicates in by_anchor.values():
        event_ids = tuple(sorted({row.event_id for row in duplicates}))
        if len(event_ids) > 1:
            blockers.append(
                ReconciliationBlocker(
                    "DUPLICATE_BANK_EVENT",
                    "One bank anchor is assigned to multiple economic event IDs",
                    event_ids,
                    _evidence_refs(duplicates),
                )
            )


def _evidence_refs(
    evidence_rows: Iterable[BankInterestEvidenceRow],
) -> tuple[str, ...]:
    return tuple(
        sorted({row.evidence_reference for row in evidence_rows})
    )
