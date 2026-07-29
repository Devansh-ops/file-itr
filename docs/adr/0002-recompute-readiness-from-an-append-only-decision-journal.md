---
status: accepted
---

# Recompute readiness from an append-only decision journal

Human judgment changes whether a computed result may be treated as filing-ready,
but it must not rewrite normalized evidence or deterministic totals. The engine
therefore keeps blockers and human decisions immutable, binds each acceptance to
the normalized-input and output-amount context, and recomputes readiness from
those facts. The decision journal is immutable and hash-chained so append order
and history integrity are externally verifiable. Eligible evidence risks may be
accepted with actor, timestamp, reason, evidence, and exact affected outputs;
integrity failures are always non-overridable. When evidence or amounts change,
old decisions remain visible but become stale instead of silently carrying
forward.
