# AY 2026–27 intraday and F&O business (FY 2025–26)

Research date: 29 July 2026. Scope: an individual or HUF carrying on
Indian exchange trading as a business. This note covers same-day
non-delivery equity trading and eligible exchange-traded securities futures and
options. It does not decide whether delivery-based shares are investments or
stock-in-trade, and it does not cover foreign, OTC, crypto, commodity, currency,
or physically settled positions without the additional evidence identified
below.

The FY 2025–26 return is governed by the Income-tax Act, 1961 even though it is
filed in 2026. The Department expressly confirms that transition rule for AY
2026–27. [Income Tax Department AY 2026–27
FAQ](https://www.incometax.gov.in/iec/foportal/node/11724)

## Conclusions

1. **Ordinary intraday equity is speculative business.** Section 43(5) defines a
   speculative transaction as a purchase or sale contract for a commodity,
   including stocks and shares, settled otherwise than by actual delivery or
   transfer. Where those transactions constitute a business, section 28,
   Explanation 2 makes the speculation business distinct from every other
   business. [Income-tax Act, sections
   43(5)](https://www.incometaxindia.gov.in/w/section-43-21) and
   [28](https://www.incometaxindia.gov.in/w/section-28-58)
2. **An eligible securities derivative on a recognised stock exchange is
   non-speculative business.** The section 43(5)(d) exception is conditional:
   the transaction must be in a derivative under the Securities Contracts
   (Regulation) Act, be carried out electronically through a registered
   intermediary on a recognised exchange, and be supported by a time-stamped
   contract note containing the client identity and PAN. Notification 2/2006
   notified NSE and BSE for this purpose. [Section
   43(5)](https://www.incometaxindia.gov.in/documents/20117/42998/Section-43_2025-11-01_02-07-08_0093df_en.pdf/8fefdf0f-c9be-9e18-a6ba-c18f05b3ee89?t=1779867545512&version=1.0),
   [Notification
   2/2006](https://www.incometaxindia.gov.in/w/2-notification-2-date-of-issue-25/1/2006),
   and [Rule
   6DDA](https://www.incometaxindia.gov.in/documents/20117/11892059/Rule%2B-%2B6DDA_en.pdf/297f647a-af8a-81c0-509a-3a34e422789e?t=1766001068416&version=1.0)
3. **Tax-audit turnover is not contract notional and is not net P&L.** ICAI's
   Revised 2025 Guidance Note says speculative turnover is the total of
   favourable and unfavourable settlement differences. It applies the same
   absolute-difference basis to squared-off derivatives, adds the applicable
   option-sale premium without duplicating profit already represented by that
   premium, includes reverse-trade differences, defers an open position's
   turnover until actual square-off, and has a special rule for
   delivery-settled derivatives. These rules are professional guidance for
   section 44AB turnover; they do not determine the income head.
   [ICAI Guidance Note on Tax Audit under section 44AB (Revised 2025),
   paragraphs
   5.11–5.12](https://resource.cdn.icai.org/87317dtc-aps1808gn-tax-audit2025.pdf)
4. **P&L and turnover need separate deterministic computations.** Gross trade
   P&L is the signed economic result of each evidenced closing, expiry, or
   settlement. Tax-audit turnover is a non-negative measure produced from the
   ICAI rules. Brokerage, exchange charges, GST, stamp duty, and STT do not
   reduce this turnover measure; eligible charges reduce business income as
   separately evidenced expenses.
5. **STT can be a business expense.** Section 36(1)(xv) allows STT paid on a
   taxable securities transaction entered in the course of business when the
   corresponding income is included in profits and gains of business or
   profession. Other revenue expenditure must satisfy section 37's
   non-personal, non-capital, wholly-and-exclusively-for-business test. Thus an
   engine may deduct evidenced brokerage and exchange charges, but it must not
   assume that every broker debit is allowable or ignore GST input credit.
   [Income-tax Act, sections
   36(1)(xv)](https://www.incometaxindia.gov.in/w/section-36-56) and
   [37(1)](https://www.incometaxindia.gov.in/w/section-37-5)
6. **Intraday and F&O losses remain different tax categories.** A speculative
   loss can be set off only against speculation profit and carried forward for
   four assessment years. A non-speculative F&O business loss follows section
   72 and can be carried forward for eight assessment years; a current-year
   business loss cannot be set off against salary. Both carry-forwards require
   a timely section 139(3) loss return under section 80.
   [Income-tax Act, sections
   71(2A)](https://www.incometaxindia.gov.in/w/section-71-63),
   [72](https://www.incometaxindia.gov.in/w/section-72-49),
   [73](https://www.incometaxindia.gov.in/w/section-73-1),
   [80](https://www.incometaxindia.gov.in/w/section-80-68), and
   [139(3)](https://www.incometaxindia.gov.in/w/section-139-1)
7. **A broker trading summary is a reconciliation observation, not the
   normalized ledger.** It can support a provisional computation. Independent filing
   readiness requires source-provenanced economic events or an explicit human
   override under the repository's readiness rules.

## Classification decision table

| EVIDENCED contract outcome | Section 43(5) result | Business bucket |
|---|---|---|
| Equity buy and sell (or short sale and cover) closed without delivery | Speculative unless another statutory proviso is proved | Speculation business |
| Securities future or option satisfying every section 43(5)(d) eligible-transaction condition on a notified recognised exchange | Statutorily excluded from speculative transaction | Non-speculative business |
| Derivative with missing time-stamped contract note, client identity/PAN, intermediary registration, exchange, or recognition evidence | Eligibility exception is not proved | Filing blocker; do not silently call it non-speculative |
| OTC, foreign-exchange, foreign-market, commodity, currency, or another derivative outside this note | Additional statutory branch is needed | Unsupported classification blocker |
| Derivative resulting in delivery of the underlying | Derivative and underlying legs have different turnover/accounting consequences | Block until settlement, inventory/investment character, and both legs are evidenced |
| Same security bought intraday but carried to delivery, or sold from existing holdings | Not an ordinary squared-off intraday event | Route to delivery-based stock-in-trade/capital workflow; do not force into speculation |

The exchange exception is evidence-sensitive. Notification 2/2006 proves NSE
and BSE from 25 January 2006. Other exchanges or renamed/successor venues need a
primary notification with an effective period. A broker label such as “F&O” or
“exchange traded” cannot replace the section 43(5) contract-note conditions.

## Deterministic computation from normalized economic events

### Required event grain

Normalize executions into closed-contract economic events without discarding
their child fills. Each event must identify:

- taxpayer and broker account, exchange, segment, trading date, order and trade
  IDs, contract-note ID, execution time, settlement date, and source
  provenance;
- instrument class (`cash_equity_intraday`, `future`, `call_option`, or
  `put_option`), symbol/ISIN or exchange token, expiry, strike, option type,
  contract multiplier/lot size, and currency;
- opening side, closing side, matched quantity, entry and exit price or
  premium, and the matching method supplied by the broker/accounting records;
- settlement type (`square_off`, `cash_settlement`, `expiry_worthless`,
  `exercise`, `assignment`, or `physical_delivery`) and whether an underlying
  delivery occurred;
- gross signed settlement difference, option premium paid, option premium
  received, and each separately named charge; and
- bank/broker cash-ledger observations, broker trading summary observations, open-position
  observations, and year-end balances.

If raw fills need matching, use one versioned deterministic method within each
broker account and exact contract identity. Preserve the method and every
allocation. Tax law and the ICAI Guidance Note do not prescribe an execution
matching algorithm, so changing FIFO/weighted-average/broker matching is an
accounting-method change, not a harmless parser refactor. If the method cannot
reproduce the contract note or broker closed-position statement, block rather
than choose whichever result is tax-favourable.

### Gross trade P&L

Use signed decimal amounts at the source's precision. Round to whole rupees
only at the ITR filing boundary.

| Event | Gross trade P&L before charges |
|---|---|
| Long intraday equity closed | `matched_quantity × (sell_price - buy_price)` |
| Short intraday equity covered | `matched_quantity × (short_sale_price - cover_price)` |
| Long future closed/cash-settled | `quantity × multiplier × (exit_or_settlement_price - entry_price)` |
| Short future closed/cash-settled | The negative of the long formula |
| Long option sold | `sale_premium - purchased_premium`, at quantity × multiplier |
| Written option bought back | `written_premium - closeout_premium`, at quantity × multiplier |
| Long option expires worthless | Negative premium paid |
| Written option expires unexercised | Positive premium received |
| Exercise, assignment, or physical settlement | Preserve the derivative settlement difference and underlying acquisition/disposal separately; do not use a synthetic square-off |

For futures represented by daily mark-to-market cash flows, the closed
contract's economic P&L is the sum of its non-duplicative variation settlements.
Do not also add entry-to-exit P&L. An open year-end position has no section 44AB
turnover under the ICAI rule until it is actually squared off, but its
year-end accounting or tax valuation is a separate accounting-policy question.
The engine must block filing-ready P&L if that policy, prior-year treatment, or
opening carrying amount is missing.

### Tax-audit turnover

The following is a deterministic engineering expression of ICAI paragraph
5.11, not statutory text:

1. **Intraday equity:** turnover for each independently settled event is the
   absolute gross settlement difference. Annual intraday turnover is the sum;
   do not net profitable and loss-making events.
2. **Futures:** turnover is the sum of absolute favourable and unfavourable
   differences for contracts actually squared off/settled in the year.
3. **Options:** retain both the absolute difference and option-sale premium.
   Add sale premium and add an unfavourable difference; add a favourable
   difference only to the extent it is not already represented in the sale
   premium. This implements ICAI's instruction to include sale premium without
   separately re-including the profit already contained in it.
4. **Reverse trades:** include their difference once; do not add it both as a
   closed trade and again merely because it is labelled “reverse.”
5. **Open positions:** no turnover until the financial year of actual
   square-off.
6. **Delivery settlement:** include the derivative difference between trade
   and settlement price. If the taxpayer transfers an underlying held as
   stock-in-trade, its full sale value is additional business turnover.

For a simple option close, item 3 generally yields the larger of total premium
paid and premium received for the matched quantity:

| Option result | Premium/difference components | Tax-audit turnover |
|---|---|---|
| Buy for ₹20, sell for ₹50 | sale premium ₹50 includes ₹30 favourable difference | ₹50, not ₹80 |
| Buy for ₹50, sell for ₹20 | sale premium ₹20 plus ₹30 unfavourable difference | ₹50 |
| Write for ₹50, buy back for ₹20 | sale premium ₹50 includes ₹30 favourable difference | ₹50 |
| Write for ₹20, buy back for ₹50 | sale premium ₹20 plus ₹30 unfavourable difference | ₹50 |
| Buy for ₹50, expire worthless | ₹50 unfavourable difference, no sale premium | ₹50 |
| Write for ₹50, expire unexercised | ₹50 sale premium includes the profit | ₹50 |

ICAI provides the rule but no worked matching example in the Guidance Note.
Therefore retain the component calculation and the broker/auditor turnover
observation. A materially different auditor-approved option-turnover
methodology is a human-review item, not a silent normalization change.

### Expenses and net business result

Compute each bucket independently:

```text
gross trade P&L
- evidenced deductible STT
- evidenced brokerage and exchange/clearing charges
- other evidenced allowable business expenses allocated by a documented method
= net business profit or loss
```

Stamp duty, GST, interest, data subscriptions, depreciation, and shared
expenses require their own allowability and allocation evidence. Do not deduct
GST that was or will be claimed as input credit, personal expenses, capital
items, penalties, or charges belonging to investment transactions. Expenses do
not reduce ICAI tax-audit turnover.

An expense used once in the combined profit and loss account must not also be
deducted again in Schedule BP. Retain allocation between speculation and
non-speculation businesses so the distinct-business and loss rules remain
correct.

## Broker trading summary and cash reconciliation

Reconcile in this order:

1. deduplicate contract-note trades by broker account, exchange, segment, and
   exchange trade ID;
2. reproduce each closed event's quantity, gross P&L, and settlement from child
   fills;
3. sum gross P&L separately for intraday, futures, and options;
4. sum charges by statutory/accounting type, preserving unattributed charges;
5. compare the recomputed segment totals with the broker tax/realised trading
   summary;
6. reconcile daily settlement, premium, charge, margin, pay-in, payout, and
   withdrawal/deposit entries to the broker funds statement and bank anchors;
7. reconcile opening and closing positions to the prior-year closing and the
   next-year opening; and
8. reconcile tax-audit turnover to a broker/auditor observation without
   replacing the independent calculation.

The normalized ledger and broker observation may differ for legitimate reasons:
broker reports may use a different fill-matching method, include prior-period
charges, omit physically settled underlying legs, value open positions, or
present charges net of GST. Every difference needs an amount, reason, evidence,
and affected filing output. A broker trading summary alone can produce only a
provisional P&L and cannot independently establish trade-level turnover,
section 43(5) eligibility, or tax-audit applicability.

## Loss-category and carry-forward handoff

Keep these outputs separate for the complete-liability engine:

| Output | Current-year handoff | Carry-forward handoff |
|---|---|---|
| Intraday speculation profit | May absorb current/brought-forward speculation loss; a current non-spec business loss may also set off against it under the wider same-head rules | Not applicable |
| Intraday speculation loss | Cannot reduce F&O/non-spec business profit, salary, capital gains, or other-source income | Section 73 bucket, maximum four succeeding AYs |
| F&O non-spec business profit | Can absorb eligible current/brought-forward non-spec business loss | Not applicable |
| F&O non-spec business loss | Subject to Chapter VI set-off; specifically cannot reduce salary | Section 72 bucket, maximum eight succeeding AYs |

Section 73 does not bar a non-speculative business loss from setting off against
speculation profit; it bars the reverse use of a speculation loss. ICAI's
Revised 2025 Guidance Note states this expressly in paragraph 62.6.
[ICAI Guidance Note, paragraphs
62.1–62.9](https://resource.cdn.icai.org/87317dtc-aps1808gn-tax-audit2025.pdf)

For either carry-forward, retain the statutory return due date, actual filing
date/status, and prior-year loss schedule. If a timely section 139(3) return
cannot be established, do not emit a carry-forward amount as filing-ready.

## Section 44AB and 44AD audit decision

### Rules supplied by law

Section 44AB(a) requires a business tax audit when aggregate business sales,
turnover, or gross receipts **exceed ₹1 crore**. The threshold becomes **₹10
crore** only when both:

- cash receipts are not more than 5% of aggregate amounts received, including
  amounts received for sales/turnover/gross receipts; and
- cash payments are not more than 5% of aggregate payments made, including
  expenditure.

A non-account-payee cheque or bank draft is deemed cash. The tests aggregate
the taxpayer's businesses; trading turnover cannot be tested in isolation.
[Income-tax Act, section
44AB](https://www.incometaxindia.gov.in/documents/20117/11892059/Section%2B-%2B44AB_en_8cf1cc.pdf/2d0c4085-9682-5576-ee00-23985588b899?t=1765997029192&version=1.0)

Section 44AD is optional and must not be selected merely to avoid audit. Its
relevant conditions include:

- resident individual, HUF, or partnership firm other than an LLP;
- no disqualifying deduction and no excluded profession, commission/brokerage,
  agency, or section 44AE business;
- eligible-business turnover up to ₹2 crore, increased to ₹3 crore when cash
  receipts are not more than 5%; and
- deemed income generally at 8%, or 6% for qualifying receipts through
  prescribed banking/electronic modes within the statutory time.

Sections 30–38 deductions are treated as already allowed under section 44AD.
If an assessee declares under section 44AD and then exits within the following
five-assessment-year window, section 44AD(4) creates a five-year lockout.
Where that lockout applies and total income exceeds the maximum amount not
chargeable to tax, sections 44AD(5) and 44AB(e) require books and audit.
[Income-tax Act, section
44AD](https://www.incometaxindia.gov.in/w/section-44ad-34)

The Act does not exclude a trading business merely because its turnover is
computed from differences, but choosing section 44AD for intraday/F&O trading
can be professionally contentious and changes loss/expense treatment. Treat the
election as an explicit human tax decision supported by professional advice,
not an engine default.

### Exact facts required

No `required` or `not_required` result is safe without:

1. ICAI-method turnover for intraday and every F&O segment;
2. sales/turnover/gross receipts from every other business under its applicable
   method;
3. aggregate amounts received and their payment modes;
4. aggregate payments made and their payment modes;
5. identification of non-account-payee cheques/drafts as cash;
6. entity type, residency, and 44AD disqualifications;
7. current 44AD election and 6%/8% receipt split if elected;
8. section 44AD declaration history and any break during the relevant
   five-year window;
9. total income and the applicable maximum amount not chargeable to tax for the
   section 44AD(5) test;
10. any audit obligation under another clause or law; and
11. an auditor-approved option-turnover method where it differs from the
    component method above.

Margin deposits/withdrawals, premium flows, settlement pay-ins/payouts, and
broker netting must remain visible when constructing the aggregate
receipts/payments denominators. The Act's cash-ratio words are broader than
trading turnover. If the complete all-business cash-flow population is absent,
the enhanced ₹10 crore threshold is not proved.

### Audit outcome table

Apply every row; one `required` basis wins over a `not_required` basis.
Comparisons are exact before ITR whole-rupee rounding.

| Complete facts | Outcome |
|---|---|
| Aggregate business turnover > ₹10 crore | **Required** under section 44AB(a) |
| ₹1 crore < aggregate turnover ≤ ₹10 crore, and either cash-receipt or cash-payment ratio > 5% | **Required** under section 44AB(a) |
| ₹1 crore < aggregate turnover ≤ ₹10 crore, and both cash ratios ≤ 5% | **Not required under section 44AB(a)** |
| Aggregate turnover ≤ ₹1 crore | **Not required under section 44AB(a)** |
| Valid section 44AD election and income declared in accordance with section 44AD(1) | **Not required under section 44AB solely for that eligible presumptive business**, subject to another audit basis |
| Section 44AD(4) applies and total income exceeds the applicable amount not chargeable to tax | **Required** under section 44AB(e) |
| Section 44AD(4) applies but the total-income/basic-exemption comparison is missing | **Human review required** |
| Turnover, other-business totals, either cash population/mode, 44AD history/election, eligibility, or another audit basis is unresolved | **Human review required** |
| Broker and engine turnover differ materially, especially for option premium, expiry, reverse, or delivery settlement | **Human review required** |

“Not required” means only that the stated section 44AB basis is disproved from
complete facts. It is not an opinion that books, another statutory audit, or
other return schedules are unnecessary.

## AY 2026–27 ITR-3 filing fields

CBDT notified the AY 2026–27 ITR-3 in Notification 47/2026. The production JSON
schema was first released on 18 June 2026 and updated on 30 June 2026; the
current schema calls itself version 1.1 while its form/schema version values
remain `Ver1.0`. Use the downloaded official artifact as a versioned target,
not a remembered prior-year shape.
[CBDT Notification
47/2026](https://www.incometaxindia.gov.in/documents/d/guest/notification-no-47-2026-pdf),
[ITR-3 schema download
page](https://www.incometax.gov.in/iec/foportal/downloads/income-tax-returns?mobile-app=1),
[AY 2026–27 ITR-3 JSON schema
v1.1](https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-07/ITR-3_2026_Main_V1.1.json),
and [validation rules
v1.0](https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-06/CBDT_e-filing_ITR-3_Validation%20Rules_V1.0_AY%2026-27.pdf)

### Nature and audit

- `PartA_GEN2.NatOfBus.NatureOfBusiness[].Code`: `21009` for speculative
  trading, `21010` for futures and options trading, and `21011` for buying and
  selling shares where separately applicable.
- `PartA_GEN2.AuditInfo`: `TotalSalesExcOneCr`,
  `AgrOFAllAmtsRcvd`, `AgrOFAllPayMade`, `LiableSec44ABflg`,
  `Cndnfor44AB`, `BiiDetails.44AD`, `AuditAccountantFlg`,
  `AuditReportFurnishDate`, and `AckNum44AB`, with firm/auditor identifiers when
  required.
- The official validations require the cash-ratio answers for turnover between
  ₹1 crore and ₹10 crore and require Part A-BS and Part A-P&L when section 44AB
  audit applies.

The schema describes audit condition `bii` broadly as a taxpayer falling under
44AD/44ADA/44AE/44BB but not opting for presumptive income. The engine should
compute liability from the Act's exact conditions and map the confirmed result
to the schema; schema wording is not authority to expand section 44AB(e).

### Trading account and P&L

When regular books are maintained, the notified form has new explicit fields:

| Notified ITR-3 line | JSON field | Engine amount |
|---|---|---|
| Part A-Trading 12a, turnover from intraday trading | `TradingAccount.TurnoverIntradayTrd` | ICAI absolute-difference intraday turnover |
| Part A-Trading 12b, income from intraday trading | `TradingAccount.IncomeIntradayTrd` | Intraday trading income transferred to P&L |
| Part A-Trading 12c, turnover from Futures & Options trading | `TradingAccount.TurnoverFutureTrd` | ICAI F&O turnover; despite the singular JSON name, the form says Futures & Options |
| Part A-Trading 12d, income from Futures & Options trading | `TradingAccount.IncomeFutureTrd` | F&O trading income transferred to P&L |

Validation rules state that 12b cannot exceed 12a and 12d cannot exceed 12c,
and line 13 gross profit transferred from Trading Account includes lines 12,
12b, and 12d. Negative income is allowed by the JSON integer fields. Filing
values are whole rupees; retain decimal source and computed values in the audit
trail.

Eligible detailed expenses can flow through
`PARTA_PL.DebitsToPL.OtherExpensesDtls`/`OtherExpenses` and the
other named P&L expense fields, but the complete package must prevent double
deduction and retain the speculation/F&O allocation.

Where regular books are not maintained:

- speculative activity uses `PARTA_PL.TurnverFrmSpecActivity`,
  `GrossProfit`, `Expenditure`, and `NetIncomeFrmSpecActivity` (notified form
  line 65); and
- non-speculative business figures use the general
  `PARTA_PL.NoBooksOfAccPL` gross-receipt, gross-profit, expense, and net-profit
  fields.

The no-books fields are an ITR presentation route, not permission to derive
filing-ready numbers solely from a broker trading summary.

### Schedule BP and loss schedules

- `ITR3ScheduleBP.BusinessIncOthThanSpec.NetPLFromSpecBus` removes the
  speculative amount included in overall P&L. The notified form identifies it
  as Trading Account line 12b plus no-books speculative line 65(iv).
- `ITR3ScheduleBP.SpecBusinessInc` contains `NetPLFrmSpecBus`,
  `AdditionUs28to44DA`, `DeductUs28to44DA`, and
  `AdjustedPLFrmSpecuBus` for the separate speculation computation.
- Non-speculative F&O remains in
  `ITR3ScheduleBP.BusinessIncOthThanSpec` and its A37 result.
- `ScheduleCYLA` and `ScheduleBFLA` have separate
  `BusProfExclSpecProf` and `SpeculativeInc` branches.
- `ScheduleCFL`/`LossSummaryDetail` separately carry
  `BusLossOthThanSpecLossCF` and `LossFrmSpecBusCF`, with assessment year and
  filing date in prior-year detail.
- `PartB-TI.ProfBusGain` separately exposes `ProfGainNoSpecBus` and
  `ProfGainSpecBus`.

This filing slice should provide the computed trading amounts and field
provenance. Complete CYLA/BFLA/CFL population still depends on the taxpayer's
other income, brought-forward losses, filing history, and return due date.

## Law/guidance versus ledger facts

### Law or official professional guidance supplies

- the speculative definition and the section 43(5)(d) derivative exception;
- the time-stamped contract-note and recognised-exchange conditions;
- the distinct speculation-business rule;
- the ICAI tax-audit turnover method;
- the section 36(1)(xv) STT condition and general expense rule;
- the section 44AB thresholds and section 44AD eligibility/lockout rules;
- the four-year/eight-year loss buckets and timely-return requirement; and
- the AY 2026–27 ITR-3 schedule and schema fields.

### Source evidence must supply

- whether actual delivery occurred and the settlement outcome;
- exchange, segment, intermediary, contract-note time, UCC/client identity, PAN
  presence, and effective recognition evidence;
- executions, matching, multiplier, position direction, premiums, settlement
  differences, reverse trades, exercise/assignment, and underlying delivery;
- all charges, their statutory type, GST/credit treatment, and allocation;
- opening/closing positions and the taxpayer's consistently applied accounting
  method;
- broker trading summary/turnover and funds-ledger observations;
- every other business's turnover and the complete all-business
  receipts/payments populations with modes, including the portion of other
  business turnover covered by an elected section 44AD route;
- entity/residency, 44AD eligibility, election/history, total income, and
  applicable basic exemption;
- for a confirmed 44AD trading route, bank-mode, cash, and other-mode turnover
  plus the 6%, 8%, and total declared-income amounts required by Part A P&L,
  with source provenance for that human-confirmed fact set; and
- prior-year losses, actual filing dates, and due dates.

## Filing-readiness blockers

Block rather than guess when any of these remains unresolved:

- delivery versus non-delivery, intraday versus carry-forward, or business
  versus investment character;
- any section 43(5)(d) eligible-transaction fact or exchange recognition;
- duplicate/missing trades, broken fill matching, unknown lot multiplier, or
  inconsistent contract identity;
- unsupported commodity/currency/foreign/OTC derivative;
- open-position accounting, prior-year carrying value, or cross-year close;
- option expiry/exercise/assignment, reverse trade, or physical delivery that
  cannot be reproduced;
- gross P&L, charges, cash settlement, open positions, or broker trading
  summary
  mismatch;
- an expense's allowability, GST credit, business purpose, or allocation;
- ICAI tax-audit turnover disagreement or unavailable option-premium
  components;
- missing other-business turnover or incomplete cash receipts/payments and
  payment modes;
- an elected 44AD route without the split between covered other-business
  turnover and ordinary-business turnover;
- a required-audit result without aggregate all-business turnover for the ITR-3
  audit-information turnover band;
- a no-books F&O loss that cannot be represented by the non-negative
  `NoBooksOfAccPL.NetProfit` field;
- unresolved section 44AD election, eligibility, five-year history, total
  income, basic-exemption test, filing amounts, or filing cross-ties;
- unknown tax-audit obligation under another clause/law;
- attempted speculation/non-speculation loss netting before the complete
  Chapter VI handoff; or
- untimely/unknown return filing where a loss carry-forward is claimed.

The engine may produce clearly labelled provisional P&L from a broker trading
summary or incomplete ledger, but it must not call that result independently
filing-ready or issue a definitive `tax_audit_not_required` conclusion.
