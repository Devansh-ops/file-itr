# AY 2026–27 loss set-off and carry-forward

Research date: 2026-07-29
Scope: Resident individual, FY 2025–26 / AY 2026–27, supported capital,
intraday-speculation, and non-speculative F&O/business losses.

## Primary authorities

- [Income-tax Act section 70](https://www.incometaxindia.gov.in/w/section-70-55)
  permits a current short-term capital loss against income from any capital
  asset, while a current long-term capital loss can be used only against
  long-term capital gain.
- [Income-tax Act section 71](https://www.incometaxindia.gov.in/w/section-71-63)
  governs current-year inter-head set-off. Section 71(2A) prohibits business
  loss against salary; section 71(3) prohibits capital loss against another
  income head.
- [Income-tax Act section 72](https://www.incometaxindia.gov.in/w/section-72-128)
  permits brought-forward ordinary business loss only against profit of a
  business or profession, gives it priority over brought-forward depreciation
  and section 35(4) allowance, and limits it to eight succeeding assessment
  years.
- [Income-tax Act section 73](https://www.incometaxindia.gov.in/w/section-73-1)
  restricts speculation loss to speculation profit and limits carry-forward to
  four succeeding assessment years.
- [Income-tax Act section 74](https://www.incometaxindia.gov.in/w/section-74-63)
  permits brought-forward short-term capital loss against any capital gain,
  restricts brought-forward long-term capital loss to long-term capital gain,
  and limits both to eight succeeding assessment years.
- [Income-tax Act section 80](https://www.incometaxindia.gov.in/documents/20117/42998/Section-80_2026-05-05_11-51-34_8cd341_en.pdf/3393d817-0497-950d-4fa0-6ac04bba2679)
  makes a return under section 139(3) a condition for carrying forward the
  covered section 72, 73, 74, and 74A losses.
- [Income-tax Act section 139(3)](https://www.incometaxindia.gov.in/w/section-139)
  ties a loss return to the time allowed by section 139(1).
- [Income-tax Act section 115BBH](https://www.incometaxindia.gov.in/documents/20117/11892059/Section%2B-%2B115BBH_en_310100.pdf/585c890f-88ac-6c4e-e3d1-53c40b59b6f6)
  prohibits a VDA transfer loss from being set off under any provision and
  prohibits its carry-forward.
- The Income Tax Department's
  [2026 set-off and carry-forward guide](https://www.incometaxindia.gov.in/documents/20117/42998/Set-off-and-carry-forward-of-losses_2026-05-27_12-13-23_131dc8_en.pdf/6713bef0-2a75-75f8-a539-2b2aa9a128d7)
  confirms that intra-head adjustment precedes inter-head adjustment,
  current-year loss precedes brought-forward loss, ordinary business loss can
  absorb speculation profit, and the law prescribes no single target order
  where several eligible incomes are available.
- The vendored official `ITR-2` and `ITR-3` AY 2026–27 schemas and validation
  rule PDFs are the primary source for the JSON property names and schedule
  cross-ties.

## Supported statutory matrix

| Loss pool | Current-year eligible income | Brought-forward eligible income | Maximum succeeding AYs |
|---|---|---|---:|
| Short-term capital | Any supported STCG or LTCG | Any supported STCG or LTCG | 8 |
| Long-term capital | Supported LTCG only | Supported LTCG only | 8 |
| Ordinary/non-speculative business | First eligible business income; then eligible non-salary heads, including ordinary and DTAA-rate other-source income | Any supported business/profession profit, including speculation profit | 8 |
| Speculation business | Speculation profit only | Speculation profit only | 4 |
| VDA transfer loss | None | None | 0 |

The engine deliberately keeps each VDA gain and loss observation separate and
preserves its tax head. It sums positive VDA income into distinct protected
capital-gains and business-income section 115BBH buckets, records dead losses
for audit, and never creates a loss pool from either.

## Ordering

The deterministic order is:

1. Aggregate each current-year statutory income bucket without netting VDA
   gains and losses.
2. Apply current long-term capital losses to LTCG.
3. Apply current short-term capital losses to remaining STCG/LTCG.
4. Apply current ordinary business loss to speculation profit within Schedule
   BP.
5. Apply the remaining current ordinary business loss across eligible
   non-salary, non-protected heads through Schedule CYLA.
6. Apply brought-forward speculation loss oldest-first to remaining
   speculation profit.
7. Apply brought-forward ordinary business loss oldest-first to remaining
   business profit.
8. Apply brought-forward LTC loss oldest-first to remaining LTCG.
9. Apply brought-forward STC loss oldest-first to remaining STCG/LTCG.
10. Reconcile unused eligible balances into Schedule CFL.

Restricted pools are applied before flexible pools within the same head so a
flexible pool cannot consume the only income available to a restricted pool.
Current-year pools always precede brought-forward pools.

Where several targets are equally lawful, the statute does not prescribe one
mode and the Department says the taxpayer may use the most beneficial mode.
The engine therefore exposes an explicit target-order policy. Every policy must
be an exhaustive permutation of all eligible targets: it may reorder them, but
cannot silently omit a target and carry a loss while eligible income remains.
The default is deterministic and schedule-oriented. A later complete-liability
optimizer can select another exhaustive order after comparing actual tax.

## Evidence contract for prior-year losses

Each prior loss pool must state:

- the assessment year in which the loss originated;
- the statutory category and positive balance brought forward;
- the prior return filing date and the applicable section 139(1) due date;
- an evidence reference to the latest available Schedule CFL, ITR
  acknowledgement/intimation, or assessment record; and
- full source provenance.

Missing amount, filing date, due date, evidence reference, or provenance
blocks schedule generation and asks for human input. A supplied late return or
an expired pool also blocks the claim rather than being silently discarded.
Exceptional condonation, assessment-order, succession, or reorganisation
claims require a separate supported rule branch.

The aggregate schedule owner also requires a source-provenanced human coverage
fact confirming both (a) every supported current-income bucket, including
explicit zero/none categories, and (b) the complete prior-loss history,
including an explicit no-prior-loss answer. Without it, an omitted source is
indistinguishable from zero and schedule generation blocks.

If a current business/capital/speculation loss remains, the engine also
requires a human-provided current-return timeliness fact. `unknown` blocks.
`late` produces the current set-off computation but excludes the otherwise
unabsorbed covered loss from current Schedule CFL and records it as forfeited.

## Filing cross-ties

The filing slice owns the aggregate adjustment schedules, not the upstream
income schedules:

- Schedule CG `CurrYrLosses` records the current STCL/LTCL source-to-target
  matrix.
- Schedule BP `BusSetoffCurrYr` records current ordinary business loss applied
  to speculation income before CYLA.
- Schedule CYLA starts from the post-Schedule-CG/post-Schedule-BP income
  buckets and records current inter-head loss.
- Schedule BFLA starts from Schedule CYLA's ending values and records
  brought-forward set-off.
- Schedule CFL records each prior AY source pool, total prior pools, BFLA
  adjustments, current carryable loss, and the reconciled closing total.
- Part B-TI records current-year loss set-off, brought-forward loss set-off,
  gross total income, and current loss carried forward.

ITR values are recomputed from whole-rupee boundary amounts so every official
schedule equation stays exact. Source amounts and economic allocations remain
`Decimal` values in the audit result.

Because this slice owns complete replacement branches, projection first
reconciles the normalized post-intra-head income buckets to the upstream
Part B-TI source-income fields. Capital facts additionally require an existing
object-valued Schedule CG whose short- and long-term source totals match the
normalized capital inputs. `SumOfCGIncm`, `IncmFromVDATrnsf`, and
`TotScheduleCGFor23` must also reconcile. Schedule VDA must reconcile its
capital and, for ITR-3, business totals to those distinct normalized heads.
ITR-3 business facts additionally cross-check the upstream raw
ordinary/speculative Schedule-BP results, the business-head VDA amount at line
3g, their ordinary/speculative total, and
`BusSetoffCurrYr/LossSetOffOnBusLoss`. Part B-TI routes capital-head VDA to
`CapGains30Per115BBH` and business-head VDA to the special-rate business line
represented by `ProfIncome115BBF` in the AY 2026–27 JSON schema. A mismatch
blocks before aggregate Part B-TI fields are changed.

The projector also scans existing CYLA/BFLA/CFL data for nonzero unsupported
house-property, race-horse, specified-business, unabsorbed-depreciation, and
section 35(4) loss values. More generally, every nonzero existing leaf absent
from the generated form-specific path set blocks, including
`BrtFwdBusLoss` and `AdjustAccTax115BACAmt`. It cannot disappear merely because
the replacement model omits it. Each scalar value in the owned ITR-2 and ITR-3
output branches is represented once as a form-specific output delta and once as
an audit binding on the identical path. The binding retains current amount,
prior-loss, coverage-attestation, and return-timeliness evidence.
Every supplied attestation is validated even when its status is `unknown` or
no current residual remains. Complete normalized coverage with no capital/VDA
activity produces an explicit, audited removal delta for a stale Schedule CG
rather than letting an old `CurrYrLosses` matrix survive.

## Deliberate limits

This ticket does not support negative house-property or ordinary-other-source
inputs, race-horse loss, specified business under section 35AD, unabsorbed
depreciation, section 35(4) allowance, amalgamation/demerger/succession,
condonation, or concessional-regime loss adjustments. Those inputs block rather
than being forced into one of the supported capital or trading categories.
