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

**Statutory fund classification**:
The tax category established from a fund's evidenced portfolio composition and
legal thresholds for the relevant period, independent of its marketing name.
_Avoid_: Scheme category, fund name

**Primary classification evidence**:
An AIS/SFT observation or period-specific AMC, SEBI, or AMFI source that states
the portfolio facts needed to derive a statutory fund classification.
_Avoid_: Search result, scheme name, remembered category

**Taxable switch**:
One linked redemption from an outgoing mutual-fund scheme and acquisition into
an incoming scheme; only the outgoing leg is a disposal.
_Avoid_: Transfer, rebalance

**Fixed-income capital component**:
The portion of acquisition or disposal consideration attributable to the
security itself after separately evidenced coupon or accrued interest is
removed.
_Avoid_: Dirty consideration, total settlement

**Fixed-income interest component**:
Coupon or accrued interest attributable to the holding period, kept outside a
security's capital-gain proceeds and basis.
_Avoid_: Sale premium, capital component

**Receipt observation**:
One source's view of gross interest, tax withheld, or net cash for a
fixed-income economic event, reconciled before filing readiness.
_Avoid_: Economic event, final receipt

**Trading detail**:
Normalized contract-level or settlement-level facts from which business
profit, turnover, and expenses can be recomputed independently.
_Avoid_: Broker P&L, trading summary

**Derivative eligibility evidence**:
The time-stamped contract-note, client/PAN, intermediary, electronic-trade,
exchange-recognition, and source-provenance facts that establish the section
43(5)(d) exception for one F&O economic event.
_Avoid_: F&O label, recognised-exchange flag

**Trading expense component**:
One source-provenanced charge with a statutory/accounting type and evidenced
business deductibility, aggregated only after trade matching.
_Avoid_: Broker charges, expense total

**Trading accounting basis**:
The explicit regular-books or no-books route that selects mutually exclusive
AY 2026–27 ITR-3 business fields without changing the economic result.
_Avoid_: Filing mode, books flag

**Broker trading summary**:
A broker's segment-level observation of gross profit, gross loss, turnover,
expenses, and net result, used to reconcile rather than replace trading detail.
_Avoid_: Trading detail, final result

**Trading turnover**:
The segment-specific tax-audit turnover derived under the applicable
absolute-difference and options-premium rules; it is not securities notional
value or account cash flow.
_Avoid_: Contract value, sale proceeds

**Tax-audit applicability assessment**:
A deterministic `required`, `not_required`, or `human_review_required` result
that retains the threshold facts and unresolved conditions behind it.
_Avoid_: Audit flag, recommendation

**Section 44AD filing facts**:
Human-confirmed bank-mode, cash, and other-mode turnover plus the 6%,
8%, and total declared-income amounts needed to cross-tie Part A P&L and
Schedule BP without inventing a rate split, retained with their own source
provenance.
_Avoid_: Presumptive estimate, automatic 44AD election

**Filing slice**:
An auditable, deterministic subset of return schedules produced for one income
or credit domain; it is not a complete return.
_Avoid_: Filing package, final return

**Filing package**:
A complete return draft whose schedules, computation evidence, decisions, and
official-schema validation are associated with one another.
_Avoid_: Filing slice, JSON file
