# Loss set-off and carry-forward — FY 2025–26 / AY 2026–27

Load this module when any current-year source is negative, the user mentions a
loss or carry-forward, a prior ITR/Schedule CFL contains a balance, or the
return includes capital, intraday, or F&O losses.

## Ask for the complete loss history

For every prior loss, ask for the latest ITR Schedule CFL or assessment record
showing the loss, the original assessment year, category, remaining amount,
return filing date, and applicable due date. Preserve the source provenance.
Do not accept a broker's current-year P&L as proof of a brought-forward loss.

Also ask the human to confirm that every supported current-income bucket has
been covered—including explicit zero/none answers—and that the prior-loss
history is complete, including an explicit “no prior losses” answer. Preserve
that coverage attestation with source provenance. Without it, omission cannot
be distinguished from zero and the aggregate schedules must block.

If the amount, category, origin AY, filing date, due date, or evidence is
missing, stop schedule generation and ask the human. Do not invent a zero,
silently ignore the pool, or assume the return was timely.

## Apply the statutory matrix

- Current short-term capital loss can absorb any supported current capital
  gain. Current long-term capital loss can absorb only LTCG.
- Current ordinary/non-speculative business loss first absorbs eligible
  business income. Any remainder can absorb eligible income under another head,
  including ordinary and DTAA-rate other-source income, but never salary or a
  protected income such as section 115BBH VDA income.
- Speculation loss can absorb only speculation profit.
- A VDA transfer loss cannot absorb another VDA gain or any other income and
  cannot be carried forward. Preserve whether each VDA amount is taxed under
  the capital-gains or business-income head; both are protected, but they
  project to different return fields.
- Brought-forward short-term capital loss can absorb any current capital gain;
  brought-forward long-term capital loss remains LTCG-only.
- Brought-forward ordinary business loss can absorb only current business or
  profession profit. Brought-forward speculation loss remains
  speculation-profit-only.

Current-year losses are applied before brought-forward losses. Within each
restricted head, use the more restricted pool before the flexible pool and use
brought-forward pools oldest-first.

The law does not prescribe one target order when several targets are equally
eligible. Keep the target order explicit and exhaustive. Reordering is allowed;
skipping an eligible target so a loss carries forward is not.

## Carry-forward eligibility

- Ordinary business, STCL, and LTCL: at most eight succeeding assessment
  years.
- Speculation business: at most four succeeding assessment years.
- Covered business and capital losses require a loss return within the section
  139(1) time through sections 139(3) and 80.
- VDA loss: no carry-forward.

If current covered losses remain, ask whether the AY 2026–27 return is or will
be filed within its applicable due date. Treat `unknown` as a blocker. A
confirmed late return can still be computed, but the otherwise unabsorbed
covered current loss must not be placed in Schedule CFL.

## Cross-tie the schedules

Use the deterministic engine rather than editing totals:

1. Schedule CG `CurrYrLosses` — current capital loss matrix.
2. Schedule BP `BusSetoffCurrYr` — current ordinary business loss used against
   speculation profit.
3. Schedule CYLA — current inter-head adjustments.
4. Schedule BFLA — brought-forward adjustments after CYLA.
5. Schedule CFL — prior pools, BFLA use, current carryable loss, closing total.
6. Part B-TI — current loss set-off, brought-forward set-off, gross total
   income, and loss carried forward.

Each schedule must start from the previous schedule's ending buckets. Mandatory
set-off cannot be bypassed with a hand-edited Schedule CFL number.

Before projecting, reconcile every normalized income bucket to the corresponding
Part B-TI source-income field already populated by the upstream salary, house
property, business, capital-gain, and other-source slices. When capital facts
exist, also require an object at `ScheduleCGFor23` and reconcile its short- and
long-term source totals, `SumOfCGIncm`, VDA income, and total Schedule-CG income
before replacing `CurrYrLosses`. Reconcile Schedule VDA's
`TotIncCapGain` and, for ITR-3, `TotIncBusiness` to the separately normalized
VDA heads. For ITR-3, also reconcile the raw non-speculative and speculative
source results, the business-head VDA value at Schedule BP line 3g
(`IncRecCredPLOthHeadDtls/115BBH`), the ordinary/speculative total, and the
ordinary-business loss source before replacing `BusSetoffCurrYr`. Part B-TI
must keep capital-head VDA under `CapGains30Per115BBH` and business-head VDA
under its special-rate business line (`ProfIncome115BBF` in the AY 2026–27
JSON schema). A missing or mismatched upstream branch blocks; the loss slice
must not make a schema-valid but semantically contradictory complete return.

The loss slice owns the generated CYLA, BFLA, and CFL branches. Before replacing
them, reject any nonzero unsupported house-property, race-horse,
specified-business, unabsorbed-depreciation, or section 35(4) loss value. Do not
erase an unsupported balance by writing zero. Reject every nonzero existing
CYLA/BFLA/CFL leaf that the form-specific output model will not reproduce,
including regime-transition fields such as `BrtFwdBusLoss` and
`AdjustAccTax115BACAmt`. Every scalar value written to an ITR-2 or ITR-3 path
must have a form-specific output delta and an audit line with the same exact
path, projected value, rule keys, and source lineage.

Retain the human coverage attestation and current-return timeliness attestation,
including both evidence references and source provenance, in the result and in
every filing-output audit binding. These facts decide whether Schedule CFL is
complete and whether a current residual loss survives.

Validate every supplied attestation even when its status is `unknown` or the
current computation happens to leave no residual loss. When complete normalized
coverage shows no capital/VDA activity, emit and audit an explicit removal of a
stale `ScheduleCGFor23` branch so an older current-year-loss matrix cannot
survive recomputation.

## Human-review boundaries

Block and ask for specialist review for section 35AD specified business,
unabsorbed depreciation/section 35(4), race-horse loss, succession or
reorganisation, condonation of a late loss return, assessed amounts that differ
from the latest Schedule CFL, or another category the engine does not support.
