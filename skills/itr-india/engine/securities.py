"""Public facade for multi-demat delivery-security computation."""

from engine.securities_fifo import (
    MatchedDisposal,
    SecurityBlocker,
    SecurityFifoResult,
    SecurityReconciliationError,
    reconcile_security_fifo,
)
from engine.securities_filing import (
    DeliverySecuritySlice,
    SecurityAuditLine,
    build_delivery_security_itr2_draft,
    build_delivery_security_slice,
)
from engine.securities_ledger import (
    BrokerAccountSummary,
    ClosingPosition,
    SecurityDefinition,
    SecurityEvent,
    SecurityEventType,
    SecurityLedger,
    SecurityLedgerError,
    TaxTreatment,
    load_security_ledger,
)


def compute_delivery_security_slice(
    ledger: SecurityLedger,
) -> DeliverySecuritySlice:
    return build_delivery_security_slice(reconcile_security_fifo(ledger))


__all__ = [
    "BrokerAccountSummary",
    "ClosingPosition",
    "DeliverySecuritySlice",
    "MatchedDisposal",
    "SecurityBlocker",
    "SecurityAuditLine",
    "SecurityDefinition",
    "SecurityEvent",
    "SecurityEventType",
    "SecurityFifoResult",
    "SecurityLedger",
    "SecurityLedgerError",
    "SecurityReconciliationError",
    "TaxTreatment",
    "build_delivery_security_itr2_draft",
    "compute_delivery_security_slice",
    "load_security_ledger",
]
