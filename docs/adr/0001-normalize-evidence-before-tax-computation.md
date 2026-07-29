---
status: accepted
---

# Normalize evidence before tax computation

Institution exports and broker summaries use incompatible categories and may
already contain opaque arithmetic. Parsers therefore produce a versioned,
institution-neutral normalized ledger with source provenance, and deterministic
engine code computes filing figures from that ledger. A source's final P&L may
support a provisional computation, but it does not replace independently
reconcilable event evidence unless a human explicitly overrides readiness.
