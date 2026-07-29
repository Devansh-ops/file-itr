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

Install test dependencies and run tests:

```console
python -m pip install -r skills/itr-india/engine/requirements-dev.txt
pytest skills/itr-india/engine/tests -v
```
