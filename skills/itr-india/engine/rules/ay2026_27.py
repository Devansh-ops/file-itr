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
_ITD_LOSS_GUIDE = (
    "https://www.incometaxindia.gov.in/documents/20117/42998/"
    "Set-off-and-carry-forward-of-losses_2026-05-27_12-13-23_131dc8_en.pdf/"
    "6713bef0-2a75-75f8-a539-2b2aa9a128d7"
)
_ITD_SECTION_70 = "https://www.incometaxindia.gov.in/w/section-70-55"
_ITD_SECTION_71 = "https://www.incometaxindia.gov.in/w/section-71-63"
_ITD_SECTION_72 = "https://www.incometaxindia.gov.in/w/section-72-128"
_ITD_SECTION_73 = "https://www.incometaxindia.gov.in/w/section-73-1"
_ITD_SECTION_74 = "https://www.incometaxindia.gov.in/w/section-74-63"
_ITD_SECTION_80 = (
    "https://www.incometaxindia.gov.in/documents/20117/42998/"
    "Section-80_2026-05-05_11-51-34_8cd341_en.pdf/"
    "3393d817-0497-950d-4fa0-6ac04bba2679"
)
_ITD_SECTION_115BBH = (
    "https://www.incometaxindia.gov.in/documents/20117/11892059/"
    "Section%2B-%2B115BBH_en_310100.pdf/"
    "585c890f-88ac-6c4e-e3d1-53c40b59b6f6"
)

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
    Rule(
        key="loss.current_year.priority",
        value=True,
        authority=(
            "Chapter VI ordering — current-year intra/inter-head losses "
            "precede brought-forward losses"
        ),
        source_primary=_ITD_LOSS_GUIDE,
        source_secondary=_ITD_SECTION_70,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.capital.short_term.targets",
        value=("short_term_capital_gain", "long_term_capital_gain"),
        authority=(
            "ss.70(2), 74(1)(a) — short-term capital loss may set off "
            "against income from any capital asset"
        ),
        source_primary=_ITD_SECTION_70,
        source_secondary=_ITD_SECTION_74,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.capital.long_term.targets",
        value=("long_term_capital_gain",),
        authority=(
            "ss.70(3), 74(1)(b) — long-term capital loss may set off "
            "only against long-term capital gain"
        ),
        source_primary=_ITD_SECTION_70,
        source_secondary=_ITD_SECTION_74,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.business.current_year.targets",
        value=(
            "business_income",
            "house_property_income",
            "capital_gain",
            "ordinary_other_sources",
            "dtaa_other_sources",
        ),
        authority=(
            "ss.70, 71(2A) — current ordinary business loss may set off "
            "within business and across eligible heads, but not salary"
        ),
        source_primary=_ITD_SECTION_71,
        source_secondary=_ITD_LOSS_GUIDE,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.business.brought_forward.targets",
        value=("non_speculative_business", "speculative_business"),
        authority=(
            "s.72(1) — brought-forward ordinary business loss sets off "
            "only against profits of a business or profession"
        ),
        source_primary=_ITD_SECTION_72,
        source_secondary=_ITD_LOSS_GUIDE,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.speculation.targets",
        value=("speculative_business",),
        authority=(
            "s.73 — speculation loss sets off only against speculation "
            "profit and carries for four succeeding assessment years"
        ),
        source_primary=_ITD_SECTION_73,
        source_secondary=_ITD_LOSS_GUIDE,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.vda.no_setoff_or_carry",
        value=True,
        authority=(
            "s.115BBH(2) — VDA transfer loss cannot be set off or "
            "carried forward"
        ),
        source_primary=_ITD_SECTION_115BBH,
        source_secondary=_ITD_LOSS_GUIDE,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
    Rule(
        key="loss.carry_forward.timely_return",
        value=(
            "ordinary_business",
            "speculation_business",
            "short_term_capital",
            "long_term_capital",
        ),
        authority=(
            "ss.80, 139(3) — covered business and capital losses require "
            "a return filed within the section 139(1) time"
        ),
        source_primary=_ITD_SECTION_80,
        source_secondary=_ITD_LOSS_GUIDE,
        effective_from=date(2025, 4, 1),
        effective_to=None,
        confidence=RuleConfidence.VERIFIED,
    ),
])
