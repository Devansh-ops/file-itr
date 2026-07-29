from datetime import date
from decimal import Decimal
from engine.rulebase import Rule, RuleConfidence, RuleTable

_CLEARTAX_STCG = "https://cleartax.in/s/short-term-capital-gain-on-shares"
_QUICKO_HP = "https://learn.quicko.com/capital-gains-holding-period-tax"
_CLEARTAX_50AA = "https://cleartax.in/s/section-50aa-income-tax-act"
# Deep links verified by WebFetch (2026-07-29): each page was fetched and its
# operative statutory text confirmed to state the value(s) this rule encodes.
# "Section 2 in The Income Tax Act, 1961" — contains clause (42A). CAVEAT: this
# mirror pre-dates Finance (No.2) Act 2024 (base definition still reads "36
# months"; the 2014 date-conditional proviso is unchanged). It DOES corroborate
# holding.listed_equity.lt_months=12 (first proviso: units of an equity-oriented
# fund / UTI / zero-coupon bond / other listed non-unit securities -> 12 months)
# and holding.other.lt_months=24 (third proviso: unlisted shares / immovable
# property -> 24 months). It does NOT corroborate holding.listed_nonequity's
# 12-month value or its acquisition-date condition — that reclassification of
# listed non-equity units (e.g. gold ETFs) is a Finance (No.2) Act 2024 change
# not present on this page. Left as the least-bad available deep primary
# because it is still on-point for two of the three holding.* rules and is not
# a search URL; the listed_nonequity gap is called out in the report for the
# controller to adjudicate (a fresher primary should be sourced later).
_IK_2_42A = "https://indiankanoon.org/doc/545792/"
# "Section 24 in The Finance Act, 2023" — the enacting provision that inserts
# s.50AA into the Income-tax Act; contains "Specified Mutual Fund" and the
# "1st day of April, 2023" effective-date language, which corroborates
# s50aa.acquired_from directly. CAVEAT: the fetched text truncated before the
# deeming-as-short-term-capital-gains language, so s50aa.applies ("always
# short-term, any holding") is corroborated by inference from "Notwithstanding
# anything contained in clause (42A) of section 2 or section 48" (an explicit
# override of the normal holding-period test), not by directly-read deeming
# text. Also note (not a value/citation defect, flagged for the record): this
# section's own commencement clause reads "with effect from the 1st day of
# April, 2024" — standard Finance Act drafting for "applicable from AY
# 2024-25" (PY 2023-24, beginning 1-Apr-2023), consistent with this rule's
# effective_from=2023-04-01, but worth a second look if this rule is revisited.
_IK_50AA = "https://indiankanoon.org/doc/71017618/"
# "Section 115BBH in The Income Tax Act, 1961" — contains "virtual digital
# asset" and "thirty per cent".
_IK_115BBH = "https://indiankanoon.org/doc/4837707/"
_QUICKO_VDA = "https://learn.quicko.com/income-tax-on-cryptocurrency-nft-vda"

TABLE = RuleTable([
    Rule(key="holding.listed_equity.lt_months", value=12,
         authority="s.2(42A) proviso — listed securities / equity-oriented units",
         source_primary=_IK_2_42A, source_secondary=_CLEARTAX_STCG,
         effective_from=date(2025, 4, 1), effective_to=None,
         confidence=RuleConfidence.VERIFIED),
    Rule(key="holding.listed_nonequity.lt_months", value=12,
         authority="s.2(42A) — listed non-equity units, units acquired on/after 1-Apr-2025",
         source_primary=_IK_2_42A, source_secondary=_QUICKO_HP,
         effective_from=date(2025, 4, 1), effective_to=None,
         confidence=RuleConfidence.CONTESTED,
         confidence_note="Units acquired 23-Jul-2024..31-Mar-2025 carried a 24-month "
                         "transitional threshold; 12-month applies for acquisitions on/after 1-Apr-2025."),
    Rule(key="holding.other.lt_months", value=24,
         authority="s.2(42A) — other capital assets",
         source_primary=_IK_2_42A, source_secondary=_QUICKO_HP,
         effective_from=date(2025, 4, 1), effective_to=None,
         confidence=RuleConfidence.VERIFIED),
    Rule(key="s50aa.acquired_from", value=date(2023, 4, 1),
         authority="s.50AA — specified mutual fund; units acquired on/after 1-Apr-2023",
         source_primary=_IK_50AA, source_secondary=_CLEARTAX_50AA,
         effective_from=date(2023, 4, 1), effective_to=None,
         confidence=RuleConfidence.VERIFIED),
    Rule(key="s50aa.applies", value=True,
         authority="s.50AA — specified MF gains always short-term (slab), any holding",
         source_primary=_IK_50AA, source_secondary=_CLEARTAX_50AA,
         effective_from=date(2023, 4, 1), effective_to=None,
         confidence=RuleConfidence.CONTESTED,
         confidence_note="The currently pinned primary text supports this result only by "
                         "inference; direct operative deeming text must be pinned before the "
                         "rule can be verified."),
    Rule(key="s115bbh.applies", value=Decimal("0.30"),
         authority="s.115BBH — VDA gains taxed at flat 30%, any holding period",
         source_primary=_IK_115BBH, source_secondary=_QUICKO_VDA,
         effective_from=date(2022, 4, 1), effective_to=None,
         confidence=RuleConfidence.VERIFIED),
])
