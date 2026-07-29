# AY 2026–27 bonds and fixed-income instruments (FY 2025–26)

Research date: 29 July 2026. Scope: an Indian resident individual holding instruments as investments, not as stock-in-trade. This note covers Central/State government securities, ordinary listed and unlisted bonds or debentures, and market-linked debentures (MLDs). It separates rules supplied by law from instrument and economic-event facts that the ledger must evidence.

## Conclusions

1. **Coupon is not capital gain.** “Interest on securities” includes interest on Central/State Government securities and on debentures or other securities for money issued by a local authority, company, or statutory corporation. If it is not business income, section 56 taxes it under “Income from other sources”; section 145 requires the assessee’s regularly employed cash or mercantile method. [Income-tax Act, sections 2(28B)](https://www.incometaxindia.gov.in/w/section-2-61), [56](https://www.incometaxindia.gov.in/w/section-56-62), and [145](https://www.incometaxindia.gov.in/w/section-145-9)
2. **Section 50AA overrides holding period for three relevant classes.** Every MLD is covered, with no acquisition-date or listing exception. An unlisted bond or unlisted debenture is covered when transferred, redeemed, or matured on or after 23 July 2024, regardless of acquisition date. The result is deemed short-term capital gain equal to full consideration less acquisition cost and eligible event expenses; STT is not deductible. [Income-tax Act, section 50AA](https://www.incometaxindia.gov.in/w/section-50aa-4), [Finance (No. 2) Act, 2024, section 21](https://incometaxindia.gov.in/Documents/Finance-No.2-Act-2024.pdf)
3. **The 1 April 2023 acquisition cut-off in section 50AA belongs to specified mutual-fund units, not to MLDs or unlisted bonds/debentures.** Likewise, 23 July 2024 is an event-date cut-off for unlisted bonds/debentures, not their acquisition date. This distinction must be explicit in the rule engine.
4. **Outside section 50AA, FY 2025–26 uses 12/24-month tests.** A listed security is long-term only when held for more than 12 months; an unlisted government security or other security is generally long-term after more than 24 months. The Department’s table gives a statutory zero-coupon bond a 12-month test whether listed or unlisted, but the later section 50AA text creates an unresolved collision for an unlisted bond; that case must block. Short-term gain is taxed at ordinary applicable rates. Long-term gain from a transfer in FY 2025–26 is generally taxed under section 112 at 12.5% without indexation. [Income Tax Department holding-period guide](https://wmstatic-prd.incometaxindia.gov.in/web/guest/w/introduction-8), [section 112](https://wmstatic-prd.incometaxindia.gov.in/web/guest/w/section-112-64)
5. **Preserve clean price and accrued interest, but do not automatically remove broken-period interest from a capital investor’s cost or sale consideration.** RBI explains the mechanics: clean price plus separately calculated accrued interest equals dirty price and total settlement consideration. The Supreme Court distinguishes investment from stock-in-trade and says broken-period interest denied as a revenue deduction is added to acquisition cost and recovered against sale proceeds; its 2024 judgment reiterates that an investment holding does not receive the business deduction. Thus, for this individual-investor workflow, using evidenced dirty acquisition cost and dirty disposal consideration is the reasoned default under section 48, while the clean/accrued components remain audit fields and the separately paid periodic coupon remains interest income. [RBI Government Securities Market primer, question 22](https://m.rbi.org.in/commonman/english/scripts/FAQs.aspx?Id=711), [Supreme Court, *Bank of Rajasthan Ltd. v. Commissioner of Income Tax*, 2024 INSC 781, paragraphs 18–22](https://api.sci.gov.in/supremecourt/2008/19950/19950_2008_6_1501_56387_Judgement_16-Oct-2024.pdf)
6. **TDS is a credit, not the tax classification or final liability.** For FY 2025–26, section 193 generally applies at 10% to resident interest on securities once aggregate section 193 interest exceeds ₹10,000 in the financial year. Interest on listed dematerialised company securities has had no blanket exemption since 1 April 2023. Government-security interest is generally exempt under section 193(iv), subject to the named taxable savings bonds and any notified security; the taxable-bond carve-out applies above ₹10,000. [Finance Act, 2025 amendment and memorandum](https://www.incometaxindia.gov.in/hi/w/section-56-102), [CBDT Circular 1/2024, paragraph 52](https://www.incometaxindia.gov.in/documents/20117/6507196/Circular-1-2024.pdf/a88097f3-169d-65fa-2232-0e8d47076331?t=1762868793763), [Finance (No. 2) Act, 2024 section 51](https://www.incometaxindia.gov.in/documents/20117/6476327/Finance_Bill-2024.pdf/d4230fc9-cdfd-6f4e-549c-6d54c832e131?t=1762782722087&version=1.0), [Income Tax Department AY 2026–27 TDS-rate table](https://www.incometaxindia.gov.in/documents/20117/42998/TDS-Rates_2026-01-20_02-48-40_a44c15_en.pdf/5ced020c-5670-ccab-840c-ab3eb62e8b84?download=true&t=1774009298333&version=1.0)

## Statutory decision table

The holding-period thresholds mean that the asset is long-term only when held for **more than** the stated period. Rates below exclude surcharge and cess.

| Instrument/event in FY 2025–26 | Classification rule | Tax bucket |
|---|---|---|
| MLD: sale, redemption, or maturity | Section 50AA applies regardless of acquisition date, holding period, or listing | Deemed STCG at ordinary applicable rates |
| Unlisted bond or unlisted debenture: sale, redemption, or maturity | Section 50AA applies because every FY 2025–26 event is after 23 July 2024 | Deemed STCG at ordinary applicable rates |
| Listed ordinary bond/debenture or listed government security outside MLD | Long-term only after more than 12 months | STCG at ordinary applicable rates; LTCG at 12.5% without indexation |
| Unlisted government or other security that is not legally a “bond or debenture” and is outside MLD | Long-term only after more than 24 months | STCG at ordinary applicable rates; LTCG at 12.5% without indexation |
| Listed statutory section 2(48) zero-coupon bond | Long-term only after more than 12 months | STCG at ordinary applicable rates; LTCG at 12.5% without indexation |
| Unlisted statutory zero-coupon or deep-discount bond | Apparent collision between later section 50AA’s “unlisted bond” rule and the Department’s generic zero-coupon holding-period table | Human/professional classification blocker; do not silently choose |
| Periodic coupon | Section 56 / section 145, unless it is business income or specifically exempt | Income from other sources at ordinary applicable rates |

The Income Tax Department’s AY 2026–27 capital-gains guide confirms that section 50AA covers transfer, redemption, and maturity of MLDs and unlisted bonds/debentures, and that its computation is consideration minus cost and eligible event expenditure. [Income Tax Department capital-gains guide, pages 14–15](https://wmstatic-prd.incometaxindia.gov.in/documents/20117/42998/Capital-Gain_2026-03-19_04-23-21_6cf0a8_en.pdf/e618991c-ac51-4d19-fbbc-bb18013f948d?t=1773980990558&version=1.0)

Section 50AA’s formula has no stated zero floor. An implementation should preserve a negative computed amount for the downstream capital-loss rules rather than silently clamp it to zero.

### Instrument tests, not product-name tests

- **Market-linked debenture:** section 50AA defines an MLD as a security, whatever its name, with an underlying debt principal component and returns linked to market returns on other securities or indices; it also includes an instrument classified or regulated by SEBI as an MLD. Retain the information memorandum and SEBI/stock-exchange classification. A name such as “principal protected note” cannot override the legal terms.
- **Unlisted bond/debenture:** retain legal form and listing status on the disposal/redemption/maturity date. Section 50AA says “unlisted bond or unlisted debenture,” not “all unlisted fixed income.” A government security, pass-through certificate, commercial paper, treasury bill, or deposit must not be put into this branch merely because it produces a fixed return.
- **Government securities:** RBI distinguishes dated coupon securities, Treasury Bills and Cash Management Bills issued at a discount, and STRIPS. The product subtype matters. In particular, RBI calls T-bills “zero coupon securities,” but that does not by itself make them a statutory **zero coupon bond** under section 2(48). [RBI Government Securities primer](https://m.rbi.org.in/commonman/english/scripts/FAQs.aspx?Id=711)
- **Statutory zero-coupon bond:** section 2(48) requires an eligible issuer, no payment or benefit before maturity/redemption, and a Central Government notification. A marketing label such as “zero coupon” or “deep discount” is insufficient without the notification. [Income-tax Act, section 2(48)](https://www.incometaxindia.gov.in/w/section-2-61), [example Notification 34/2025 for HUDCO](https://www.incometaxindia.gov.in/documents/20117/42998/NOTIFICATION-SO-1774E-%5BNO-342025FNO-30016422024-ITA-I%5D_2026-01-09_03-24-37_673de8_en.pdf/9fec7616-c9cf-5790-6f0d-895b3ba69bcd?t=1779870072678&version=1.0)
- **Tax-free or specially treated government instruments:** no TDS does not mean no income tax. Require the exact section 10(15) notification or other statutory exemption. Sovereign Gold Bonds, capital/inflation-indexed bonds, and instruments with product-specific exemptions must route to their own rule rather than the plain-bond default. [Income-tax Act, section 10(15)](https://www.incometaxindia.gov.in/w/section-10-56)

## Purchase, income, sale, redemption, and maturity

### Acquisition and cost

For a normal capital asset, section 48 starts from full value of consideration and deducts transfer expenditure and acquisition/improvement cost. The Department’s guide says reasonable expenses directly incurred to acquire an asset belong in actual cost, while transfer expenses are deducted at disposal. For a confirmed investment, broken-period interest paid as part of dirty acquisition consideration is capital cost rather than a current interest deduction; this differs from securities proved to be stock-in-trade. Preserve each component and fee rather than netting the cash amount so the rule engine can determine its side and eligibility. [Income Tax Department capital-gain computation guide](https://www.incometaxindia.gov.in/en/sale-of-shares), [Supreme Court 2024 INSC 781](https://api.sci.gov.in/supremecourt/2008/19950/19950_2008_6_1501_56387_Judgement_16-Oct-2024.pdf)

For dematerialised securities, use FIFO for identifying disposed lots. Preserve account-level movements and transfers so an inter-account transfer carries the original acquisition date and cost rather than fabricating a sale and repurchase. [Income Tax Department FIFO guidance](https://www.incometaxindia.gov.in/en/sale-of-shares)

### Coupon and accrued interest

RBI defines accrued interest as the broken-period coupon from the last coupon date through the day before settlement. The seller receives it in addition to the clean price; clean price plus accrued interest is the dirty price. For a security confirmed to be a capital investment:

1. retain `clean_price`, `accrued_interest`, and `dirty_settlement` separately when the source provides them;
2. reconcile `clean + accrued = dirty` at instrument face value and quantity;
3. use dirty purchase consideration in acquisition cost and dirty sale consideration in disposal proceeds;
4. route the actual periodic coupon to interest income, subject to the taxpayer’s regularly followed section 145 method; and
5. do not also deduct purchased accrued interest against coupon, which would mix investment and stock-in-trade treatment.

The Supreme Court ruling is primarily about banks and the availability of a business deduction. An official ITAT order records an assessee’s dirty-cost/consideration capital treatment but remands the issue to determine whether frequent dealing instead made the securities stock-in-trade; it is evidence of the classification risk, not a definitive retail-investor holding. [ITAT Chennai, *Sundaram Finance Ltd.*, ITA 72/73/285/286 of 2015, paragraph 9](https://itat.gov.in/public/files/upload/1568011887-ITA%2072%2C%2073%2C%20285%20%26%20286%20of%202015%20-%20Sundaram%20Finance.pdf) If the taxpayer treats the instrument as stock-in-trade, if the contract legally settles interest separately from transfer consideration, or if source records conflict, block this capital workflow for human/professional treatment. If only the evidenced dirty amount is available, capital computation can proceed, but clean/accrued reporting remains incomplete; never manufacture the split from coupon percentage alone.

### Redemption and maturity

Section 50AA expressly treats transfer, redemption, and maturity as covered events for MLDs and unlisted bonds/debentures. For other capital assets, section 2(47)’s transfer definition includes relinquishment and extinguishment of rights; preserve the issuer’s redemption/maturity statement and actual proceeds rather than assume face value. [Income-tax Act, section 2(47)](https://www.incometaxindia.gov.in/w/section-2-54)

A call, put, buyback, early redemption, or partial redemption may change event date, quantity, consideration, and accrued coupon. Those are source facts, not defaults supplied by tax law.

## Deep-discount, T-bills, and STRIPS

- RBI says Treasury Bills are short-term zero-coupon **securities** issued at a discount and redeemed at face value, and pay no interest. For an investor holding them as capital assets, treating the evidenced sale/maturity spread through the government-security capital-gain branch is a reasonable inference from those facts and the Department’s government-security holding-period table. It is not the section 2(48) statutory-zero-coupon branch unless the legal notification test is separately met.
- CBDT Circular 2/2002 addresses deep-discount bonds and STRIPS: it generally calls for annual market valuation/accrual, taxes the year’s accretion as interest/business income, and has special rules for an intermediate purchaser and sale between valuation dates. It also gave a limited option to small non-corporate investors holding deep-discount bonds up to aggregate face value of ₹1 lakh. Do not treat every discount instrument as ordinary capital appreciation without checking this circular and the taxpayer’s prior-year treatment. [CBDT Circular 2/2002](https://www.incometaxindia.gov.in/hi/w/2/2002-circular-no.-2/2002-dated-15-02-2002)
- A bond that actually satisfies section 2(48) is different: the Finance Act, 2005 explanatory circular says statutory zero-coupon bonds are not subject to annual accrual treatment and that Circular 2/2002 does not apply. [CBDT explanatory circular for Finance Act, 2005](https://www.incometaxindia.gov.in/documents/20117/14628360/ExplanatoryCircularFinanceAct2005-Compiled-Recast_2_.pdf/96027428-3563-b168-0386-408400394790)
- CBDT Circular 4/2004 says TDS on deep-discount-bond income is made under section 193/195 at redemption even where the holder declared income annually; this timing can create a mismatch between current TDS and income offered across years. It points holders who already offered annual accrual to section 197 relief. [CBDT Circular 4/2004](https://www.incometaxindia.gov.in/documents/20117/42998/42004-Circular-No-42004-dated-13-05-2004_2025-12-25_02-47-25_487507_en.pdf/42132d7f-7a63-e85c-271c-94ca7a8acf11?download=true&t=1774072903316&version=1.0)
- RBI describes STRIPS as separately tradable zero-coupon coupon and principal securities. Circular 2/2002 says stripping/reconstitution itself is not a transfer and applies the deep-discount treatment to the components. Preserve original security, strip/reconstitution event, allocated basis, annual values, and every component ISIN. [RBI STRIPS description](https://www.rbi.org.in/Commonperson/english/scripts/Notification.aspx?Id=1460)

Because “zero coupon security,” “deep-discount bond,” and section 2(48) “zero coupon bond” are overlapping but not identical concepts, an unevidenced mapping among them must block filing-ready output. A further unresolved collision exists for an **unlisted** statutory zero-coupon or deep-discount bond: section 50AA’s later text facially covers an “unlisted bond,” while the Department’s general table still shows the 12-month zero-coupon rule. Block rather than silently select a branch.

## TDS and reconciliation

### FY 2025–26 rules relevant to a resident individual

- Section 193 is the normal branch for “interest on securities.” Finance Act, 2025 inserted a ₹10,000 financial-year aggregate threshold from 1 April 2025; the official AY 2026–27 rate table gives 10% where PAN is furnished.
- The former no-TDS rule for listed dematerialised company securities was removed from 1 April 2023. Listed corporate-bond coupon is therefore not exempt merely because it is listed or held in demat.
- Central/State Government-security interest is generally within the proviso exemption, but section 193(iv)’s carve-out covers interest over ₹10,000 on 8% Savings (Taxable) Bonds, 2003, 7.75% Savings (Taxable) Bonds, 2018, Floating Rate Savings Bonds, 2020 (Taxable), or another notified government security. Retain the exact scheme/notification; “government bond” is not enough.
- Section 194A is for interest **other than** interest on securities. A payer’s section 194A reporting is evidence to reconcile, not authority to silently relabel a legal bond. It may indicate that the source is actually a deposit, loan, or another out-of-scope product. Finance Act, 2025 raised the general section 194A threshold to ₹10,000, the bank/co-operative/post-office threshold to ₹50,000, and the senior-citizen threshold to ₹1 lakh for FY 2025–26. [Finance Act, 2025 memorandum](https://www.incometaxindia.gov.in/documents/20117/6476586/memo-2025.pdf/f92f27e1-aa07-d24c-8776-2884c9bbac1c?t=1762782732359)

TDS does not convert coupon into capital gain, prove the gross taxable amount, or settle liability. Section 198 deems deducted tax part of income received, section 199 treats it as tax paid on the recipient’s behalf, and Rule 37BA generally gives credit for the assessment year in which the related income is assessable. [Sections 198](https://www.incometaxindia.gov.in/w/section-198-1) and [199](https://www.incometaxindia.gov.in/w/section-199-64), [Rule 37BA](https://wmstatic-prd.incometaxindia.gov.in/web/guest/w/rule-37ba)

### Reconciliation controls

Reconcile each payer/issuer and instrument against:

1. issuer/custodian coupon and redemption statement;
2. bank receipt and broker/RBI Retail Direct cash ledger;
3. Form 16A, which is the quarterly certificate for non-salary TDS;
4. Form 26AS for TDS/TCS credit; and
5. AIS/TIS for the broader reported information and any taxpayer feedback.

The Department says AIS accepts feedback, while Form 26AS from AY 2023–24 displays TDS/TCS data; it also advises taxpayers to reconcile TDS differences and explains that a deductor may need to revise its TDS return. [AIS FAQ](https://www.incometax.gov.in/iec/foportal/ais-faq), [Form 16A](https://wmstatic-prd.incometaxindia.gov.in/web/guest/w/form-16a), [tax-credit mismatch FAQ](https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/Tax%20Credit%20Mismatch%20-FAQ)

Block filing-ready output when gross interest, TDS, assessment year, PAN/TAN, or payer totals do not reconcile. A human may explain timing—especially deep-discount accrual versus redemption-year TDS—but the explanation and evidence must be retained.

## Defaults, restructurings, perpetuals, and convertibles

These cases must not use the ordinary sale/maturity happy path without human/source evidence:

- **Default or insolvency:** non-payment does not state whether a transfer or extinguishment occurred, what consideration accrued, whether interest remains due under the taxpayer’s accounting method, or what later recovery is principal versus interest. SEBI requires debt terms to define default and the debenture trustee to communicate and act on breach; the ledger needs the trustee notice, issuer/exchange disclosure, resolution plan/order, claim and recovery statement. [SEBI Debenture Trustee Master Circular, breach/default guidance](https://www.sebi.gov.in/sebi_data/attachdocs/may-2024/1715922862264.pdf)
- **Restructuring, rollover, haircut, or exchange:** these can alter principal, coupon, maturity, security, or the instrument received. SEBI treats changes in terms, rollover, redemption, and default as events requiring investor/trustee information. Do not infer whether the old right was modified, exchanged, extinguished, or merely continued. Preserve holder consent, revised term sheet, allocation of basis, and actual cash/securities received.
- **Perpetual/additional-tier instruments:** “perpetual” has no ordinary contractual maturity; calls and write-down/conversion triggers depend on issue terms and regulatory action. A projected call date must never be normalized as maturity. Require the information memorandum and actual issuer/regulator event.
- **Convertible bonds/debentures:** section 47(x) says conversion of a company bond/debenture/debenture-stock/deposit certificate into that company’s shares or debentures is not regarded as a transfer; section 49(2A) carries the relevant original cost into the resulting asset, and the Department states that the original holding period is considered. Other exchanges or cash components may differ. Preserve the conversion clause, date, ratio, cash, fractional treatment, and cost allocation. [Sections 47(x)](https://www.incometaxindia.gov.in/w/section-47-63) and [49(2A)](https://www.incometaxindia.gov.in/w/section-49-48), [Income Tax Department conversion guidance](https://www.incometaxindia.gov.in/en/sale-of-shares)
- **Disputed or missing basis:** section 50AA and section 48 both depend on cost and eligible event expenditure. A broker’s P&L or AIS estimate cannot invent cost for inherited, gifted, transferred, converted, restructured, or partially redeemed instruments. Block until the carryover/special basis is evidenced or a human records an explicit override.

The blocking rule is deliberate: SEBI requires the trust deed to specify default, holder rights, redemption, and conversion terms, so those outcomes are instrument-specific source facts rather than safe tax-engine defaults. [SEBI Debenture Trustee Regulations, Schedule IV](https://www.sebi.gov.in/acts/act062s4.html)

## What law supplies vs. what the ledger must retain

### Law supplies

- the definitions of interest on securities, MLD, and statutory zero-coupon bond;
- the section 50AA covered classes, computation, and effective dates;
- the 12-month/24-month holding thresholds outside section 50AA;
- ordinary-rate STCG and 12.5%-without-indexation LTCG buckets for FY 2025–26;
- the legal heads for coupon/interest versus capital gain;
- section 193/194A threshold and TDS-credit mechanics; and
- special non-transfer and carryover rules such as a qualifying conversion.

### Source evidence must supply

Retain, without destructive netting:

1. **Identity and legal form:** ISIN, issuer, exact instrument/security name, government-security subtype, bond/debenture/security legal form, MLD status and underlying, section 2(48) notification where claimed, secured/subordinated/perpetual/convertible flags.
2. **Terms effective for the event:** face value, issue and maturity dates, coupon/reset formula, frequency, day-count convention, record/ex dates, redemption premium/discount, put/call dates, conversion/write-down/default clauses, and amendments.
3. **Listing:** recognised exchange, listing/admission and delisting dates, and listing status on each disposal/redemption/maturity date.
4. **Lots:** account, trade/allotment and settlement dates, face/quantity, acquisition price, clean price, purchased accrued interest, acquisition fees, original/carryover basis, and provenance; preserve FIFO across account transfers.
5. **Income events:** coupon due, credited and paid dates; gross amount; separately evidenced accrued/broken-period interest; cash/mercantile method; and prior-year accruals.
6. **Capital events:** sale/redemption/maturity/call/put/partial event type and date, face/quantity extinguished, quoted clean proceeds, accrued interest, gross/dirty capital consideration, redemption premium, brokerage/fees/STT, and net cash.
7. **Tax reporting:** TDS section, gross base, rate, amount, TAN, certificate/quarter, Form 16A reference, 26AS/AIS/TIS amount and assessment year, and mismatch resolution.
8. **Exceptional events:** trustee/issuer/exchange default notice, court/NCLT or resolution-plan documents, holder vote/consent, restructuring terms, conversion allocation, recoveries and their principal/interest character, and the human decision.

## Filing-readiness blockers

Block rather than guess when any of these is unresolved:

- MLD versus plain debt, bond/debenture versus another security, or statutory zero-coupon status;
- listing status on the relevant event date;
- whether an unlisted government security is legally a bond within section 50AA;
- the unlisted statutory-zero-coupon/deep-discount interaction with section 50AA;
- section 50AA event date/type or event proceeds;
- acquisition date/cost, lot lineage, or partial-redemption allocation;
- dirty acquisition/disposal consideration, or a mismatch among clean price, accrued interest, and dirty settlement;
- coupon timing under the taxpayer’s accounting method;
- deep-discount/STRIPS prior-year accrual and basis;
- issuer, Form 16A, 26AS/AIS, bank, or ledger mismatch;
- default, restructuring, rollover, write-down, conversion, perpetual call, or disputed recovery; or
- investment versus stock-in-trade treatment.

The engine may produce a clearly labelled provisional computation from incomplete evidence, but these conditions prevent an independently filing-ready result.
