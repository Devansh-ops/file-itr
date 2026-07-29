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

**Filing slice**:
An auditable, deterministic subset of return schedules produced for one income
or credit domain; it is not a complete return.
_Avoid_: Filing package, final return

**Filing package**:
A complete return draft whose schedules, computation evidence, decisions, and
official-schema validation are associated with one another.
_Avoid_: Filing slice, JSON file
