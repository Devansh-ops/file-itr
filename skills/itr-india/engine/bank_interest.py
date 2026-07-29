"""Public facade for the provenance-backed bank-interest filing slice."""

from engine.bank_interest_filing import (
    AuditTraceLine,
    BankInterestSlice,
    build_bank_interest_itr2_draft,
    build_bank_interest_slice,
)
from engine.bank_interest_ledger import (
    BankInterestEvidenceRow,
    BankInterestLedger,
    EvidenceType,
    InterestKind,
    LedgerValidationError,
    LedgerVersionError,
    LoadedBankInterestLedger,
    OwnershipType,
    SourceProvenance,
    load_bank_interest_ledger,
)
from engine.bank_interest_reconciliation import (
    BankReconciliationError,
    ReconciliationBlocker,
    reconcile_bank_interest,
)


def compute_bank_interest_slice(ledger: BankInterestLedger) -> BankInterestSlice:
    return build_bank_interest_slice(reconcile_bank_interest(ledger))


__all__ = [
    "AuditTraceLine",
    "BankInterestEvidenceRow",
    "BankInterestLedger",
    "BankInterestSlice",
    "BankReconciliationError",
    "EvidenceType",
    "InterestKind",
    "LedgerValidationError",
    "LedgerVersionError",
    "LoadedBankInterestLedger",
    "OwnershipType",
    "ReconciliationBlocker",
    "SourceProvenance",
    "build_bank_interest_itr2_draft",
    "compute_bank_interest_slice",
    "load_bank_interest_ledger",
]
