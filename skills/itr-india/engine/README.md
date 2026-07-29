# itr-india tax engine

Deterministic, auditable Indian ITR computation engine. It combines versioned
normalized inputs, a provenance-carrying rule table, transaction-date-aware
income bucketing, filing-output audit traces, and fail-loud scope boundaries.
The implemented slices include reconciliation and statutory loss set-off; full
rate math and complete-return orchestration remain separate work. Every
statutory value is a `Rule` with a verified citation, and `buckets.py`
classifies each income line into a tax-treatment bucket.

AY 2026–27 ITR-2 and ITR-3 JSON Schemas are vendored under
`official_contracts/` with source URLs, release dates, and SHA-256 pins. The
registry verifies the local schema before every validation; the official
validation-rule PDFs are also vendored and verified by URL, release date,
version, and checksum.

Independent filing validation binds the contract to the authoritative AY rule
table and evaluates the rule keys recorded by the computation trace. Empty
rule-usage evidence, unknown rules, and used contested/unsupported rules block
readiness; unrelated rules do not.

The bank-interest filing slice in `bank_interest.py` accepts a versioned
normalized ledger, explicitly migrates the legacy v0.1 shape to v1.0, and
reconciles bank-statement, AIS, and Form 26AS evidence by economic event. It
blocks duplicates, unexplained portal entries, amount mismatches, missing 26AS
credits, and unresolved ownership before generating Schedule OS, Schedule
TDS2, an audit trace, and an ITR-2 draft.

`readiness.py` keeps provisional, blocked, independently filing-ready, and
filing-ready-by-human-override states distinct. Human acceptances live in an
immutable, hash-chained decision journal, retain their original blockers,
identify actor/time/reason/evidence/affected outputs, and are bound to a
deterministic computation-context value. Integrity failures and reconciliation
gaps that prevent safe computation remain non-overridable.

The bank-interest orchestration can safely compute a missing-26AS case without
claiming the absent TDS credit. It remains blocked until the evidence is fixed
or a human explicitly accepts filing the unchanged Schedule OS/TDS values
without that credit; the strict filing-slice API continues to fail closed.

`securities.py` accepts a versioned delivery-security ledger and runs FIFO
separately for each custody account and ISIN. Linked own-account transfers
preserve lot dates, cost, grandfathering attributes, and evidence; split and
bonus actions are supported while unknown actions fail closed. Broker gross
sales and closing positions must reconcile before the immutable Schedule CG and
112A slice or schema-validated ITR-2 draft is produced. Deductible charges and
non-deductible STT are reported separately.

`mutual_funds.py` classifies each FY 2025–26 disposal from the primary
portfolio evidence applicable on its date, then runs account-local FIFO across
folios and demat accounts. It distinguishes paid, not-paid, and unknown STT,
applies section 50AA acquisition-date rules, and carries classification,
listing, event, and account-summary provenance into the filing audit trace.
Missing or conflicting evidence remains visible in the research manifest and
readiness blockers. A typed human classification confirmation is retained in
the shared hash-chained decision journal and produces a separate provisional
bucket view; it never rewrites primary-evidence gains or clears the blocker.

`fixed_income.py` accepts a versioned normalized ledger for supported
government securities, ordinary bonds/debentures, and MLDs. It reconciles
coupon, accrued-interest, TDS, and bank observations; carries FIFO lots across
own-account transfers; applies event-date listing, holding-period, and section
50AA rules; and keeps non-deductible STT outside basis and transfer expense.
Unresolved dirty prices, evidence conflicts, exceptional instruments, and
zero-coupon/section-50AA collisions fail closed. Reconciled results project to
immutable Schedule OS/TDS2/CG values with source-linked audit lines.

`trading_business.py` accepts either normalized trading detail or broker trading
summary observations for Indian equity intraday and eligible exchange-traded
securities F&O. Detail recomputes signed trade P&L from execution prices,
matched quantity, and contract multiplier; separately aggregates
source-provenanced expense components; verifies section 43(5)(d) evidence; and
computes ICAI absolute-difference/options-premium turnover and distinct loss
categories before reconciling every broker
account/segment summary. The section 44AB/44AD assessment uses complete
all-business turnover and cash-flow facts and returns `required`,
`not_required`, or `human_review_required`; one mandatory basis wins. Missing
facts and auditor-turnover disagreements block an ITR-3 draft. Summary-only
results stay provisional until a hash-bound human acceptance applies. The
filing projection chooses one explicit regular-books/no-books route and adds to
rather than replaces an existing ITR-3 business computation. One typed output
delta collection drives both the readiness fingerprint and the JSON writes.
A human-confirmed section 44AD route requires explicit bank/cash/other turnover
and 6%/8%/total income amounts with their own provenance, then projects the
official presumptive fields; missing or non-cross-tying amounts and no-books
F&O losses block drafting. An elected 44AD route for another business also
requires its explicit share of other-business turnover; the 44AB(a) result
stays under human review when that split is missing.

`loss_setoff.py` consumes source-provenanced current income buckets and
prior-year loss pools after the capital and trading slices are reconciled. It
applies current capital/business restrictions before brought-forward pools,
uses restricted pools before flexible pools and prior pools oldest-first,
keeps VDA loss outside set-off/carry-forward, and blocks incomplete prior-return
or current timeliness evidence. A source-provenanced coverage fact must confirm
all supported current-income buckets and the complete prior-loss history, so an
omitted source cannot silently become zero. It emits cross-tied Schedule CG current-loss,
Schedule BP current-business, CYLA, BFLA, CFL, and Part B-TI values for ITR-2
or ITR-3 and validates mandatory target orders as exhaustive permutations.
Projection fails closed unless upstream Part B-TI source-income fields and, for
capital facts, all Schedule CG source/aggregate totals reconcile. ITR-3 raw
business results and the Schedule-BP current-business loss source must also
cross-tie. Nonzero unsupported or unmodelled loss paths are never replaced with
zero. Form-specific output deltas and audit bindings cover every scalar filing
value and retain the human coverage and return-timeliness evidence that
controls carry-forward. A no-capital recomputation also emits an audited
removal operation so stale Schedule CG data cannot survive changed inputs.

Install test dependencies and run tests:

```console
python -m pip install -r skills/itr-india/engine/requirements-dev.txt
pytest skills/itr-india/engine/tests -v
```
