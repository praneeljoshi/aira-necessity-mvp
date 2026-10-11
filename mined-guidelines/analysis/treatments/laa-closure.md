# Left atrial appendage (LAA) closure: five payers compared

Documents (`sourcing/library/laa-closure/`): Florida Blue (BCBSFL) MCG 02-33000-36 (rev. 03/15/26); BCBS Michigan joint policy (effective 11/1/26); BCBS Rhode Island medical coverage policy (updated 07/16/2020); Louisiana Healthcare Connections LA.CP.MP.147 (rev. 07/24); Cigna 0469 "Atrial Fibrillation: Nonpharmacological Treatments" (eff. 11/15/2025). Profiles are in `sourcing/analysis/profiles/`.

## What it is

Percutaneous LAA closure (CPT 33340) places a plug (Watchman, Watchman FLX, Amplatzer Amulet) in the left atrial appendage through a catheter to prevent stroke in atrial fibrillation (AF) patients who would otherwise take lifelong anticoagulants. Payers gate it on three things: (1) the device must be FDA approved; (2) stroke risk, scored by CHADS2 or CHA2DS2-VASc; and (3) a reason the patient cannot or should not take long-term anticoagulation. They differ on how that third reason is written: a bleeding-risk score, a general "risks outweigh" judgement, a list of eleven examples, or a named non-reversible cause. All five say Lariat and Amplatzer Cardiac Plug are not covered.

## Side by side

| Requirement | Florida Blue | BCBS Michigan | BCBS Rhode Island | LHCC (Louisiana Medicaid) | Cigna |
|---|---|---|---|---|---|
| Structure | All-of, 2 bullets | All-of (inclusions), exclusions list | All-of, 3 bullets (commercial) | All-of A and B; B has 11 examples | All-of, 2 bullets, inside a 4-procedure policy |
| Device | FDA approved (Watchman, Amulet); Lariat, Amplatzer Cardiac Plug experimental | FDA approved (Watchman, Watchman FLX, Amulet); Lariat, Cardiac Plug E/I | FDA approved (e.g., Watchman); Lariat, Amplatzer NMN | Watchman, Watchman FLX, Amulet; others "not supported" | "U.S. FDA approved device" |
| Diagnosis | AF (stroke prevention) | AF | AF | Non-valvular AF, adults | Non-valvular AF |
| Stroke-risk score | CHADS2 >= 2 OR CHA2DS2-VASc >= 3 | CHADS2 or CHA2DS2-VASc, no cutoff | CHADS2 or CHA2DS2-VASc, no cutoff | CHADS2 or CHA2DS2-VASc, no cutoff | CHA2DS2-VASc >= 2 only |
| Anticoagulation | "systemic anticoagulation therapy is recommended" | same | same | "long-term anticoagulation therapy is recommended" | not required to be recommended |
| Why not anticoagulation | "long-term risks ... outweigh the risks of the device implantation (HAS-BLED score >= 3)" | "long term risks ... outweigh the risks of the device implantation", no score | same as Michigan | Contraindication or unacceptable high bleeding risk, including (not limited to) 11 listed items | Contraindication due to a nonreversible cause (e.g., untreatable AVM, recurrent duodenal ulcer, recurrent falls not felt to be treatable) |
| Bleeding score | HAS-BLED >= 3 (table in policy) | none in criteria (HAS-BLED >= 3 "high risk" in Background) | none | none | none |
| Exclusions | Other devices | Non-FDA devices; FDA devices in people not meeting criteria | Other devices | Other devices | Any other indication including hypertrophic cardiomyopathy NMN |
| Repeat / other | none | none | none | none | Peridevice leak closure (33999) EIU; surgical LAA closure (33267/33269) NMN unless with open cardiac surgery |
| Documentation | none stated | none | Prior authorization "recommended" via online tool | none | none |
| Provider/site | none | none | none | none | none |
| Medicare | NCD 20.34 reviewed | NCD 20.34 listed | BlueCHiP for Medicare: only in CMS-approved trial | n/a | NCD 20.34 listed |
| Age | none | none | none | adults | none |
| Currency | Rev. 03/15/26 | Eff. 11/1/26 | Updated 07/2020, names only Watchman | 07/24 | 11/15/2025 |

## Agreement and disagreement

Where they agree
- FDA-approved device only; Lariat and Amplatzer Cardiac Plug excluded (all five, in some wording).
- Stroke risk measured by CHADS2 and/or CHA2DS2-VASc.
- A reason not to take long-term oral anticoagulation is required in some form.
- Code 33340 only.

Where they differ
- Score cutoffs: only Florida Blue (CHADS2 >= 2 or CHA2DS2-VASc >= 3) and Cigna (CHA2DS2-VASc >= 2) give numbers; Michigan, Rhode Island and LHCC leave "increased risk" undefined.
- The anticoagulation reason: Florida Blue operationalizes it as HAS-BLED >= 3, i.e. a numeric bleeding risk with no requirement of a true contraindication. LHCC and Cigna require a contraindication (LHCC includes "poor compliance or intolerance"; Cigna requires a nonreversible cause). Michigan and Rhode Island leave it to a "risks outweigh" judgement.
- Cigna is the narrowest on the reason (nonreversible cause), though the lowest on the stroke score (>= 2).
- Cigna also lists indications that are NMN for other cases (hypertrophic cardiomyopathy), and rules on surgical LAA closure and peridevice leak.
- Rhode Island is outdated and Medicare-split (trial only).

Florida Blue stricter or looser
- Stricter than Michigan, Rhode Island and LHCC on the score: they set no number, so any documented elevated score passes there; Florida Blue needs CHADS2 >= 2 or CHA2DS2-VASc >= 3.
- Stricter than Cigna on the stroke score (CHA2DS2-VASc >= 3 versus >= 2) when only CHA2DS2-VASc is used. But a CHADS2 of 2 alone passes Florida Blue, where CHA2DS2-VASc of 2 would not.
- Looser than Cigna and LHCC on the anticoagulation reason: Florida Blue accepts a high HAS-BLED score without any actual contraindication; Cigna requires a nonreversible contraindication; LHCC requires a contraindication or unacceptable bleeding risk with a documented cause.
- Stricter than LHCC in one way: HAS-BLED >= 3 is a hard number, where LHCC accepts any single example such as one prior bleed or poor compliance, even with HAS-BLED < 3.
- Florida Blue and Michigan share the same two-bullet skeleton (both derive from the BCBSA evidence-positioning-system text 2.02.26).

## Structure

- Layout: Florida Blue is a position statement with three score tables as footnotes. Michigan puts 6 lines of criteria in a 33-page document (30 pages of evidence). Rhode Island has criteria up front and a policy statement that refers back to "criteria above". LHCC is a one-page criteria block with a revision log. Cigna's LAA text is a 12-line paragraph in a 39-page policy that also covers ablation and surgery.
- Logic: all are all-of over two or three leaves. Only LHCC has a nested any-of (11 contraindication examples, open-ended). Florida Blue's "or" between scores is the only OR at the top.
- Delegation: Medicare NCD 20.34 (Florida Blue, Michigan, Cigna, Rhode Island for BlueCHiP); FDA approval status as an external fact; Cigna may use delegated vendor guidelines.
- Codes: 33340 everywhere; Cigna groups by status and names non-covered surgical and ablation codes.

## Problems for an automated checker

1. OR between two scores in Florida Blue: "CHADS2 score* ( ≥ 2), or CHA2DS2-VASc score** ( ≥ 3)". A patient can pass on one and fail on the other; the checker must compute both and the tables define hypertension, diabetes and age differently (CHADS2 "any history of a hypertension diagnosis"; CHA2DS2-VASc "resting BP > 140/90 mmHg on at least 2 occasions or current antihypertensive pharmacologic treatment").
2. Scores are computed values. Chart rarely states "CHA2DS2-VASc = 4". The checker must derive it from components, or accept a stated number; the Florida Blue tables give age >= 75 as +1 in CHADS2 but +2 in CHA2DS2-VASc, and CHADS2 has no 65-74 band.
3. Cigna's footnote lists CHA2DS2-VASc components with "age greater than or equal to 65" and no weights, so the score cannot be reconstructed from the policy.
4. "systemic anticoagulation therapy is recommended" is a clinician recommendation. Charts may document that the patient is on anticoagulation, or that it is contraindicated, which is the opposite fact.
5. "The long-term risks of systemic anticoagulation outweigh the risks of the device implantation (HAS-BLED score*** ≥ 3)": is HAS-BLED >= 3 the definition, or merely an example? Michigan and Rhode Island omit the parenthesis.
6. HAS-BLED has components that mirror contraindications, but inputs such as "Labile INR (therapeutic time in range < 60%)" and "alcohol more than 8 drinks per week" are rarely charted; silence yields INSUFFICIENT even if the score is likely >= 3.
7. LHCC: "including, but not limited to:" makes the list of 11 examples open, so the checker cannot decide NOT_MET; items like "Severe high blood pressure", "Recent trauma or surgery" and "Poor compliance" carry no thresholds.
8. Cigna "nonreversible cause" and "not felt to be treatable" are clinical judgments, and "recurrent falls" needs a falls history.
9. Definitions: "non-valvular" AF appears in Cigna and LHCC but is undefined; Florida Blue says only "atrial fibrillation".
10. Version hazards: Michigan's criteria carry effective date 11/1/26 (later than today). Rhode Island dated 2020 names only Watchman. Florida Blue's update log says the CHADS2 and CHA2DS2-VASc requirement was set to >=3 in 07/2021, then CHADS2 to >=2 in 11/2022; the current text is the only authority.
11. LHCC header and copyright carry merged redline text ("06/2307/24", "20222023").
12. Cigna wraps LAAC inside an ablation policy; a parser that reads the whole file pulls in ablation criteria such as "athlete ... >45 metabolic equivalent-hours" which are not relevant.
13. The evidence sections of Michigan and Cigna contain many scores (mean CHA2DS2-VASc 4.7, HAS-BLED 3.1) that look like thresholds.
14. Typo in Florida Blue: "when the all of the following criteria are met".

## Test cases

Case A: 70-year-old man with AF, hypertension and diabetes (CHA2DS2-VASc 3: HTN 1, DM 1, age 65-74 1; CHADS2 2: HTN, DM), HAS-BLED 2, on apixaban without bleeding, prefers to avoid lifelong anticoagulation.
- Florida Blue: stroke bullet passes (CHADS2 2). Bleeding bullet fails: HAS-BLED 2 < 3. Not approved.
- Cigna: CHA2DS2-VASc 3 >= 2 but no nonreversible contraindication to OAC. Not approved.
- LHCC: no listed contraindication; "poor compliance or intolerance" absent. Not approved.
- Michigan/Rhode Island: could be approved only if the reviewer accepts "risks outweigh" from physician preference; weakest criteria.

Case B: 66-year-old woman with AF, CHA2DS2-VASc 2 (age 65-74 and female), CHADS2 0, two GI bleeds on warfarin, HAS-BLED 4, recurrent duodenal ulcers not curable.
- Cigna: CHA2DS2-VASc >= 2 passes; "recurrent duodenal ulcer" is the named example of a nonreversible cause. Approve.
- Florida Blue: CHADS2 0 fails (needs >= 2) and CHA2DS2-VASc 2 fails (needs >= 3). Not approved despite HAS-BLED 4.
- LHCC: recurrent bleeding qualifies for B, but A needs an "increased risk" stated with a score; no cutoff, so likely approved.

Case C: 78-year-old with AF, prior TIA, CHA2DS2-VASc 5, history of recurrent falls with injury, HAS-BLED 3, patient is non-adherent to warfarin.
- Florida Blue: approve (score high, HAS-BLED 3).
- LHCC: approve (recurrent falls, poor compliance).
- Cigna: approve only if the falls are documented as not treatable; "poor compliance" alone is not a nonreversible cause. Otherwise not.
