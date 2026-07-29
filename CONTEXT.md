# Indian Income-tax Filing

This context turns taxpayer evidence into auditable Indian income-tax return
figures while keeping uncertainty and human decisions visible.

## Language

**Normalized ledger**:
A versioned, institution-neutral collection of economic facts that retains the
evidence behind every fact.
_Avoid_: Imported statement, combined report

**Economic event**:
One taxable or tax-credit-bearing occurrence to which observations from
different evidence sources refer.
_Avoid_: Row, record, transaction

**Evidence row**:
One source's observation of an economic event, including where and how that
observation was obtained.
_Avoid_: Economic event, final amount

**Source provenance**:
The source identity, content hash, source location, importer identity, and
importer version carried by an evidence row.
_Avoid_: Citation, filename

**Bank anchor**:
Bank-issued evidence that establishes a bank-interest economic event to which
AIS and Form 26AS observations may be reconciled.
_Avoid_: Primary row, winning value

**Account ownership**:
The taxpayer's declared share of an account and its income; unresolved joint
ownership is not an allocation.
_Avoid_: Account holder

**Reconciliation blocker**:
An unresolved duplicate, mismatch, missing explanation, ownership question, or
unsupported fact that prevents independent filing readiness.
_Avoid_: Warning, adjustment

**Decision journal**:
A hash-chained, append-only log spanning recomputations; each human risk
decision is bound to one computation context and names its actor, time, reason,
evidence, and affected outputs.
_Avoid_: Manual adjustment, edited total

**Readiness assessment**:
The deterministic result of evaluating computation basis, all original
blockers, and the decision journal as provisional, blocked, independently
filing-ready, or filing-ready by human override.
_Avoid_: Approval flag, final status

**Integrity failure**:
A duplicate, contradiction, invalid schema, broken invariant, or other defect
that must be corrected and recomputed and can never be accepted by override.
_Avoid_: Eligible risk, caveat

**Custody account**:
One demat or broker custody location whose security lots have an independent
FIFO queue.
_Avoid_: Portfolio-wide pool

**Tax lot**:
A quantity with one original acquisition date, cost basis, and evidence
lineage, including after an own-account transfer.
_Avoid_: Average cost, broker holding

**Linked own-account transfer**:
One non-disposal movement between the taxpayer's custody accounts that consumes
the source account's FIFO lots and recreates them in the destination without
changing their dates or basis.
_Avoid_: Sale and repurchase, fresh acquisition

**Filing slice**:
An auditable, deterministic subset of return schedules produced for one income
or credit domain; it is not a complete return.
_Avoid_: Filing package, final return

**Filing package**:
A complete return draft whose schedules, computation evidence, decisions, and
official-schema validation are associated with one another.
_Avoid_: Filing slice, JSON file
