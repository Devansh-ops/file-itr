# itr-india tax engine

Deterministic, auditable Indian ITR computation engine. **Phase 1 (this build):**
input model + provenance-carrying rule-table + transaction-date-aware income
*bucketing* + audit trace + fail-loud scope. **No rate math, no set-off yet** —
those are Phases 2–3. Every statutory value is a `Rule` with a verified citation;
`buckets.py` classifies each income line into a tax-treatment bucket.

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

Install test dependencies and run tests:

```console
python -m pip install -r skills/itr-india/engine/requirements-dev.txt
pytest skills/itr-india/engine/tests -v
```
