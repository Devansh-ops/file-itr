# Intraday and F&O business — FY 2025–26 / AY 2026–27

Load this module when the user mentions intraday equity, futures, options,
derivatives, a broker trading summary, or tax audit—or when a supplied broker
document contains one of those items. This module covers Indian
exchange-traded equity intraday and eligible securities F&O. Foreign, OTC,
commodity, currency, physical-delivery, and unsupported exchange transactions
need a separate rule branch and must not be forced into this workflow.

## Classification and evidence

- Same-day equity settled without delivery is speculation business under
  section 43(5).
- A securities future or option is non-speculative only when the
  section 43(5)(d) conditions are evidenced: eligible derivative, electronic
  trade through a registered intermediary, recognised exchange, and a
  time-stamped contract note carrying the client identity and PAN.
- Missing exception evidence is a filing blocker, not permission to assume that
  a broker's `F&O` label proves non-speculative treatment.
- Exercise, assignment, physical delivery, an open position spanning years, or
  a trade carried to delivery requires the additional underlying and
  accounting evidence. Block rather than synthesize a square-off.

Preserve account, exchange, instrument/contract identity, side, quantity,
multiplier, dates, entry/exit premiums or values, settlement outcome, each
charge, child fills, matching method, and source provenance. Matching must be
deterministic within the broker account and exact contract identity.
The normalized event must retain execution prices, matched quantity, contract
multiplier, and child execution IDs; a supplied opening/closing result is not
trading detail. Each deductible charge is a separate source-provenanced
trading expense component.

## Compute P&L and turnover separately

For each closed economic event, compute signed gross P&L before charges:

- long: closing value less opening value;
- short: opening value less closing value;
- long option expiry: premium paid is a loss; and
- written option expiry: premium received is a profit.

Then subtract separately evidenced allowable business expenses. STT may be
deductible under section 36(1)(xv) when the corresponding securities
transaction is in the business and its income is included in business profits.
Brokerage and other charges still need section 37/business-purpose,
capital-versus-revenue, allocation, and GST input-credit checks. Never deduct
one expense in both P&L and Schedule BP.

Tax-audit turnover is not notional contract value and is not net P&L:

- intraday and futures: sum every absolute favourable and unfavourable
  settlement difference without annual netting;
- options: retain the option-sale premium and the signed difference, then add
  sale premium plus an unfavourable difference, or sale premium plus only the
  favourable difference not already represented by that premium; for a simple
  matched close this is generally the larger of premium paid and premium
  received; and
- expiry: a long option's lost premium or a written option's retained premium
  is turnover.

Keep the component calculation and any broker/auditor turnover observation. A
different auditor-approved options methodology requires human review and must
not silently replace the normalized computation. The governing professional
source is the [ICAI Revised 2025 Guidance Note on Tax Audit, paragraphs
5.11–5.12](https://resource.cdn.icai.org/87317dtc-aps1808gn-tax-audit2025.pdf).

## Reconcile before filing

Recompute contract-level quantity, gross P&L, turnover, expenses, and net result
and reconcile each broker account/segment summary. Also reconcile settlements,
premiums, charges, margin and funds-ledger movements, bank anchors, and
opening/closing positions. A mismatch needs its amount, evidence, explanation,
and affected output.

A broker trading summary may produce a clearly labelled provisional computation.
It does not replace trading detail. Do not create a filing-ready ITR draft from
summary-only evidence unless a named human records an explicit, hash-bound
acceptance of that evidence gap. Retain the blocker and accepted risk after the
override.

Keep speculative and non-speculative results separate. A speculation loss uses
the section 73 four-AY bucket; a non-speculative F&O business loss uses the
section 72 eight-AY bucket. Complete set-off and carry-forward still require
other income, brought-forward losses, filing dates, and the section 139(3)
timely-return facts.

## Tax-audit applicability

Assess all of the taxpayer's businesses together. Collect:

- trading turnover plus complete turnover/gross receipts from every other
  business;
- for any 44AD election covering another business, the exact covered portion
  within that other-business turnover;
- complete aggregate receipts and payments, with cash and non-account-payee
  items identified;
- any other audit obligation;
- the explicit section 44AD election, eligibility, income basis, and five-year
  history;
- when 44AD covers trading, bank-mode, cash, and other-mode turnover plus the
  separately declared 6%, 8%, and total presumptive-income figures with their
  own source provenance; and
- total income versus the applicable basic exemption when a section 44AD(4)
  lockout applies.

Apply every basis; one required basis wins:

- aggregate business turnover above ₹10 crore: audit required;
- above ₹1 crore through ₹10 crore: audit required if either complete cash
  ratio exceeds 5%, otherwise not required under section 44AB(a);
- up to ₹1 crore: not required under section 44AB(a);
- section 44AD(4) lockout plus total income above the basic exemption: required
  under section 44AB(e); and
- missing aggregate facts, unresolved 44AD facts/other audit basis, or an
  auditor-turnover disagreement: human review required.

Treat 44AD as an explicit human tax decision, not an automatic audit-avoidance
route. “Not required” disproves only the evaluated section 44AB basis; it is not
a statement that books or another legal audit are unnecessary.
Do not derive the six filing amounts from the election. Missing values, a
turnover mismatch, an income-component mismatch, or an amount below the
confirmed statutory percentage blocks the presumptive filing route for human
correction. Keep them together as one provenance-carrying section 44AD filing
fact set; use that evidence—not the broker trading summary—as the source for
the presumptive-income audit lines.
Likewise, do not include a 44AD-covered other business in the ordinary
section 44AB(a) turnover base. Require its explicit turnover split; if that
split is unavailable, return human review rather than guessing.

## AY 2026–27 filing handoff

Use ITR-3. Cross-tie the reconciled slice to:

- `TradingAccount.TurnoverIntradayTrd` and `IncomeIntradayTrd`;
- `TradingAccount.TurnoverFutureTrd` and `IncomeFutureTrd` for combined
  futures and options;
- `PARTA_PL` speculative/no-books fields as applicable;
- when a confirmed 44AD election covers trading,
  `PARTA_PL.NatOfBus44AD`, `PersumptiveInc44AD`, and the corresponding
  `ITR3ScheduleBP.BusinessIncOthThanSpec` section 44AD fields instead of the
  ordinary actual-result route;
- `ITR3ScheduleBP.SpecBusinessInc` and
  `BusinessIncOthThanSpec`;
- `PartA_GEN2.AuditInfo` only after applicability is definitive; and
- the distinct speculative/non-speculative branches in CYLA, BFLA, CFL, and
  Part B-TI when the complete-liability engine has the required other-income
  and loss-history facts.

Select an explicit trading accounting basis. A regular-books slice uses Part
A-Trading and its P&L transfer; a no-books slice uses the no-books speculative
and general-business P&L fields. These are mutually exclusive routes. Add the
slice to existing business figures—never replace unrelated values already in a
base return.

The AY 2026–27 no-books `NetProfit` field cannot represent an F&O loss. Block
that case and ask a human to resolve the accounting route; do not allow a
readiness override to force a negative amount into the field.

Round only at the official ITR boundary and retain decimal source/computed
values and provenance in the audit trace. Validate the draft against the
vendored AY 2026–27 ITR-3 schema before presenting it as filing-ready.
