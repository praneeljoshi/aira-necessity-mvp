# Positive airway pressure (PAP) devices

Documents: Florida Blue 09-E0000-21 (rev 09/15/25), CareSource MM-1804 (Nevada Marketplace, eff 01/01/2026), Medica MP9239 (eff 06/01/2024), Providence Medicare MP53 (eff 6/1/2026). Profiles are in `sourcing/analysis/profiles/`.

## What it is

PAP devices (CPAP E0601, auto-titrating APAP billed as E0601, bi-level E0470 without backup rate, E0471 with backup rate) hold the airway open during sleep. This is a rental-first DME benefit: payers cover a trial period (typically 3 months), then require proof the patient actually uses it before continuing or purchasing. Payers gate on (1) a diagnostic sleep study showing OSA above an AHI/RDI/REI threshold (with symptoms if mild), (2) for bi-level, a failed CPAP trial or a non-OSA respiratory diagnosis with blood gas / oximetry numbers, and (3) objective adherence data (4 h/night on 70% of nights over 30 days).

## Side by side

| Requirement | Florida Blue | CareSource | Medica | Providence (Medicare) |
|---|---|---|---|---|
| Where criteria live | In the PDF, full text | Not in the PDF: "MCG Health clinical criteria" (ACG A-0431, A-0994) | In PDF (thresholds in Description) | Not in PDF: NCD 240.4, LCD L33718, L33800 |
| Diagnosis | OSA by diagnostic sleep test (PSG or HSAT) | per MCG (not shown) | OSAHS "following documented sleep study analysis" | OSA per NCD/LCD |
| AHI/RDI/REI threshold | >=15 any adult; 5 to <15 only if symptomatic | per MCG | >=15; or 5-14 with >=1 listed symptom | per NCD/LCD (not stated) |
| Symptom list for mild | EDS, impaired cognition, mood disorders, insomnia, HTN, IHD, stroke (7) | n/a | EDS, cognition, mood, insomnia, HTN, ischemic heart disease/CAD, stroke (7) | n/a |
| EDS definition | ESS >= 10 (Definitions section) | n/a | none | n/a |
| Pediatric | CPAP/APAP if AHI/RDI >=1.0, weight >=30 kg, adenotonsillectomy failed/contraindicated or must wait for dental/facial development | none | none | none |
| Initial period | 90 days / 3 months | 3 months (E0601/E0470); 6 months (E0471/E0472) | max 3 months rental | per LCD |
| Adherence for continued | >=4 h/night on 70% of nights, 30 consecutive days within first 3 months; evidence between day 31 and day 91 | same definition; months 4-13 (E0601/E0470); months 7-12 (E0471/E0472) with annual resubmission | "greater than four hours" and 70%; not an explicit coverage gate; month 4 must buy or return | per LCD |
| Bi-level (E0470) for OSA | CPAP tried and "proven ineffective or is not tolerated" | MCG | covered under same OSA criteria (no CPAP failure) | LCD L33718 |
| E0471 (backup rate) for OSA | Not medically necessary; denied with OSA ICD-10 codes | MCG and/or OAC | Listed as code, no separate rule | Not covered for primary OSA |
| Non-OSA bi-level | Detailed blocks: restrictive thoracic (PaCO2>=45 or SpO2<=88% x5 min or MIP<60/FVC<50%), severe COPD (PaCO2>=52 etc.), CSA (facility PSG), hypoventilation | MCG | Separate policy (not provided) | LCD L33800 |
| Switch CPAP to bi-level | Within 3 months: no new visit or sleep test. After 3 months: new face-to-face, no new sleep test, new 3-month trial | none | none | none |
| Failed trial | Face-to-face re-evaluation to re-qualify | none | none | none |
| Replacement | Nonfunctioning and out of warranty, or >5 years old; no upgrades | none | Covered when needed from normal wear; must buy | RUL 5 yrs; early only if lost/stolen/damaged/condition changed; must still use and benefit |
| Duplicate/travel device | Convenience, denied | none | Convenience, "generally" not covered | none |
| Accessories | Covered if device covered; quantity table (e.g., A7030 4/12 mo, A7028 24/12 mo) | none | Humidifier, supplies covered | Covered if base device covered |
| Investigational/non-covered | Nasal EPAP, oral pressure therapy, positional electrical devices, PAP cleaners | none | none | ULTepap A7049 not DME |
| Prior auth | Implied (authorization for 3 months; compliance confirmed then purchase) | Prior auth submitted annually for E0471/E0472 | "Prior authorization is not required" (retrospective review) | Not stated |
| Documentation | H&P, visit notes, sleep report with AHI/RDI, adherence download, signed order; supplier forms not accepted | Adherence documentation | Medical record review on request | Replacement incident documentation |

## Agreement and disagreement

Agree: the 4 h / 70% / 30-day adherence definition appears in Florida Blue, CareSource, and Medica (Medica says "greater than four hours", FL says "greater than or equal to 4"). All use a 3-month initial rental for CPAP. All treat duplicate/travel units as convenience. Medica's mild-OSA symptom list matches Florida Blue's nearly word for word.

Differ: only Florida Blue and (via CMS) Providence say E0471 is not for OSA. Only Florida Blue gives a full non-OSA bi-level table and pediatric criteria. Medica has no explicit adherence gate and does not require PA. CareSource uses 6 months initial for E0471/E0472.

Florida Blue stricter than others: requires a failed or not-tolerated CPAP trial for bi-level in OSA (Medica has none); adherence must be documented within a 31st-91st day window; a new face-to-face visit if switching after 3 months; supplier-generated forms rejected; accessory quantity caps; sleep study confirmation of AHI with a hard minimum. Florida Blue looser: a physician attestation of OSA can support replacement if the sleep test is gone; E0470 for OSA only needs "qualified health professional" documentation; AHI 5-14 accepts "evidence suggestive of" a symptom rather than documented diagnosis. Florida Blue vs Medica on replacement: Florida Blue needs nonfunctioning/out of warranty or >5 yrs; Medica covers "normal wear" without an age rule. Medica is looser on prior authorization.

Unique to Florida Blue: pediatric 30 kg rule, ASV and heart failure caution (LVEF <=45%), ICD-10 denial note on E0471, LOINC documentation table, accessory quantity table. Unique to CareSource: annual resubmission and separate 6/12 month schedule. Unique to Providence: RUL framing and reference to ULTepap as non-DME.

## Structure

Florida Blue: long, prose-and-bullets Position Statement with one block per device and diagnosis, then continued coverage, replacement, accessories, coding, reimbursement, documentation, definitions. Logic is pathways, each an `all` with one nested `any` (e.g., "A, B AND either criterion C or D"). Codes (HCPCS and ICD-10) are listed, tied loosely. Delegates sleep testing to MCG 01-95828-01, ventilators to 09-E0000-55, and Medicare Advantage to NCD 240.4/LCDs.

CareSource: a 3-page shell. All clinical criteria are delegated to MCG (proprietary, not in file); only rental-phase timeline and adherence definition exist. Medica: short coverage policy; the diagnostic thresholds are in the Description, not the coverage section. Providence: a router table that maps device x condition to CMS documents plus its own replacement rules.

## Problems for an automated checker

- Delegation: CareSource ("uses MCG Health clinical criteria") and Providence (NCD/LCD) cannot be evaluated from the PDF; the tree would contain an opaque leaf.
- Thresholds outside criteria: Medica puts AHI cutoffs in "Description"; FL puts EDS = ESS >= 10 in "Definitions". A parser reading only the criteria section misses them.
- "symptomatic or asymptomatic OSA" with the parenthetical "(evidence suggestive of excessive daytime sleepiness, impaired cognitive ability, ...)" - "suggestive of" is not a test. A chart rarely states ESS.
- Vague: "tried and proven ineffective or is not tolerated", "Significant improvement of the sleep-associated hypoventilation", "does not contribute significantly".
- And/or: "adenotonsillectomy has been unsuccessful or is contraindicated, or when definitive surgery is indicated but must wait complete dental and facial development"; "Nonfunctioning and out of warranty or Device is greater than five years old".
- Time-gated, stateful criteria: "no sooner than the 31st day but no later than the 91st day"; a switch before/after 3 months changes required evidence. The chart needs dates and device history.
- Adherence needs a device download; a clinic note rarely contains "70% of nights".
- Inconsistent: Medica "greater than four hours" vs FL "greater than or equal to 4".
- Criteria in NOTEs (ASV caution, pediatric AHI note) and a footnote that denies E0471 by ICD-10 code.
- Medica says prior auth is not required, so a checker "approving" has no meaning there; it is retrospective review.

## Test cases

1. 52-year-old, AHI 8 on home sleep test, no symptoms charted, no ESS. Florida Blue: NOT approved for E0601 (AHI 5 to <15 requires symptomatic OSA). Medica: NOT approved (needs 5-14 plus one of seven conditions). Add "hypertension" to the chart: both approve (HTN is on both lists). If chart says only "snores loudly", both deny.
2. 60-year-old OSA, AHI 28, CPAP never tried, physician requests E0470. Florida Blue: deny ("CPAP has been tried and proven ineffective or is not tolerated"). Medica: approve (BiPAP covered with a sleep study showing OSAHS, no CPAP trial). Providence/CMS routes to LCD L33718 (not in the file).
3. Existing E0601 owned, 4 years old, works but patient wants newer model; old sleep study unavailable. Florida Blue: deny (not nonfunctioning, under 5 yrs, and "upgrading technology does not meet"). Medica: approve only if "made necessary by normal wear" (not met). Providence: deny (RUL not reached, not lost/stolen/damaged). Same chart at 6 years old and working: Florida Blue approves (greater than five years, attestation accepted for missing sleep test); Providence requires the patient be regularly using it and device not meeting needs, so a fully functional device likely denied.
