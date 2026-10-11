# Implantable cardioverter defibrillators (ICD): five payers compared

Documents: Florida Blue 02-33000-34 (rev. 05/15/26, 14 pp, also covers cardiac contractility modulation), BCBS Michigan joint BCBSM/BCN policy (eff. 5/1/26, 67 pp), Carelon Clinical Appropriateness Guidelines (eff. 11/17/2024, 12 pp, vendor), Cigna 0431 (eff. 7/15/2026, 42 pp), Fallon Health Clinical Coverage Criteria (eff. 09/01/2026, 10 pp). Profiles are in `sourcing/analysis/profiles/`.

## What it is

An ICD is an implanted device that watches the heart rhythm and shocks a life-threatening ventricular arrhythmia. It comes as transvenous (leads through a vein), subcutaneous (S-ICD, no vein), and substernal or extravascular (EV-ICD). Payers split the indications into secondary prevention (the person has survived cardiac arrest or sustained ventricular tachycardia) and primary prevention (high risk but no event yet). They gate primary prevention on a cardiac diagnosis, a low ejection fraction (LVEF), heart failure class (NYHA), time since heart attack or revascularization, a trial of guideline-directed medical therapy (GDMT), and sometimes expected survival. They gate the S-ICD on first qualifying for a transvenous ICD plus reasons to avoid leads. Replacement of an existing device has its own rule. Fallon, unlike the others, writes no clinical criteria and points to InterQual and Medicare's NCD 20.4.

## Side by side

| Requirement | Florida Blue | BCBS Michigan | Carelon | Cigna | Fallon |
|---|---|---|---|---|---|
| Where criteria live | Position Statement | Inclusion/Exclusion lists | Clinical Indications | Coverage Policy | Nowhere: delegated to InterQual (18+) and NCD 20.4 (Medicare) |
| Survival gate | Exclusion only: noncardiac disease with life expectancy under 1 year (investigational) | "survival with good functional status for more than one year is anticipated" for all inclusions | Same wording as BCBSM | None | In InterQual / NCD ("likelihood of survival less than one year" in NCD) |
| Ischemic, NYHA II-III | MI at least 40 days earlier, LVEF 35% or less | LVEF <35%, MI >40 days, despite GDMT, at least 90 days post-revascularization | LVEF <= 35%, MI >= 40 days, despite GDMT, 90 days post-revasc | Post-MI >= 40 days, no PCI/CABG in 90 days, LVEF <= 35%, despite GDMT | InterQual |
| Ischemic, NYHA I | LVEF 30% or less, MI 40 days earlier | LVEF <30% | LVEF <= 30% | LVEF <= 30% | InterQual |
| Ischemic with NSVT | Not a pathway | LVEF <40%, spontaneous NSVT, positive EP study over 96 hours post-MI | LVEF <= 40%, same | LVEF <= 40%, NSVT, inducible sustained VT/VF | InterQual |
| Early post-MI (under 40 days) | Investigational (acute MI under 40 days) | Not covered (>40 days required) | Not covered (>= 40 days required) | Covered: more than 48 hours and under 40 days (and/or revascularization under 90 days), LVEF <= 40%, NSVT and inducible VT; or post-MI needing pacemaker with LVEF <= 40% | InterQual |
| Revascularization | Investigational if CABG/PTCA in past 3 months or "candidates" | 90 days post-revasc if performed | 90 days post-revasc if performed | 90 days (late pathway) | InterQual |
| Nonischemic dilated cardiomyopathy | LVEF 35% or less after reversible causes excluded and "response to optimal medical therapy ... adequately determined" (no NYHA, no age, no duration) | Age 70 or younger "or otherwise supported by clinical scenario"; 90 days GDMT; LVEF <35%; NYHA II or III | Age 70 or younger; 90 days GDMT; LVEF <= 35%; NYHA II-III | At least 3 months GDMT, LVEF <= 35%, NYHA II-III (no age cap) | InterQual |
| NYHA IV | Investigational unless CRT-D eligible | Excluded unless CRT-D eligible; included only as outpatient awaiting transplant/VAD | Covered only as outpatient awaiting transplant/VAD | Not mentioned | Plan decides bridge-to-transplant |
| Hypertrophic cardiomyopathy | 1 or more major risk factor (family history under 50, LVH over 30 mm, NSVT at 120 bpm or more on 24-hour Holter, unexplained syncope) AND judged high risk by an experienced physician | Any of 9 findings (arrest, VT, syncope in 6 months, wall >30 mm, family SCD, apical aneurysm, LVEF <50%, LGE 15% age 19+, NSVT) | Same plus abnormal BP response / NSVT with a further factor | 1 or more of 8 risk factors (arrest, NSVT, family SCD, thickness >= 30 mm, BP drop, aneurysm, EF <50%, LGE) | InterQual |
| Channelopathies (LQTS, Brugada, SQT, CPVT) | Diagnosis and "considered to be at high risk for sudden cardiac death" (no event or symptom required) | Diagnosis plus event: arrest, VT/VF, syncope; LQTS/CPVT despite beta blocker | Same | Primary prevention with risk factors; Brugada incidental with inducible VT; CPVT with NSVT | InterQual |
| Cardiac sarcoid | Diagnosis and "high risk" | Arrest, LVEF <= 35% on GDMT, VT, pacemaker indication, or LVEF >35% with syncope/scar/inducible | Same, but LVEF >35% needs syncope or scar (no inducible-arrhythmia option) | Sustained VT, SCA, LVEF <= 35%, or LVEF >35% with syncope/scar/inducible | InterQual |
| Secondary prevention | One bullet: life-threatening event, reversible causes excluded | Arrest or sustained VT in structural heart disease; unexplained syncope variants | Same | 6 groups (arrest, VT with structural disease, genetic conditions, no structural disease, syncope variants) | InterQual |
| Children | 10 groups | 10 groups (same list) | Not addressed (S-ICD at <= 21) | 4 groups with z-score LVH | InterQual only for 18+ |
| S-ICD | Meets ICD criteria AND contraindication to transvenous (no vascular access; preserve access; prior explant) AND no brady pacing indication AND no ATP-responsive arrhythmia | Meets ICD criteria AND no pacing/CRT need AND no incessant VT AND at least one of: no venous access, immunocompromised, recurrent infection, endocarditis, younger age | Same; younger = <= 21 | Meets ICD criteria AND none of: symptomatic bradycardia, incessant VT, frequent VT terminated by ATP (no contraindication to leads needed) | InterQual (33270, 33271) |
| Substernal (EV-ICD) | Not addressed | Own criteria: ICD criteria, no pacing/CRT, one of the S-ICD reasons, plus exclusions (sternotomy, unipolar pacemaker, adhesions) | Codes listed, no criteria | Experimental for any indication | Covered for Medicare (NCD); investigational for MassHealth ACO/Community Care |
| Replacement | Malfunction, change in condition, battery depletion, generator end-of-life | End-of-life, or pocket open for another reason and within 3 years of end-of-life | Same | "Considered medically necessary" with no conditions | InterQual pulse generator replacement |
| Cardiac contractility modulation | Investigational for all indications (31 investigational codes) | Not addressed | Not addressed | Not addressed | Not addressed |
| Other devices | Wearable defibrillator in a related guideline | None | None | Home AED if ICD-eligible but not a candidate (E0617) | None |
| Documentation | H&P, progress note, medication lists, all within 6 months (LOINC table) | None | Clinical documentation, peer-to-peer if elements unmet | None | Prior authorization per code; records review |
| Medicare | NCD 20.4 reviewed | Restates NCD 20.4 | CMS criteria first | None | NCD 20.4; no LCD |

## Agreement and disagreement

Where they align:
- All of the policy-writing payers (Florida Blue, BCBSM, Carelon, Cigna) define the main ischemic pathway the same way: NYHA I with LVEF around 30% or less; NYHA II-III with LVEF around 35% or less; at least 40 days after MI; and a post-revascularization wait of 90 days (Florida Blue states 3 months only as an exclusion).
- All four require reversible causes to be excluded for arrest/VT survivors and use the same S-ICD idea: qualify for a transvenous ICD, then show that leads are a problem or pacing is not needed.
- Florida Blue's pediatric list and BCBSM's pediatric list are the same ten items. BCBSM and Carelon have near word-for-word identical adult lists; they differ in comparators (BCBSM prints < and >, Carelon prints <= and >=), in the 70-year NICM age limit ("or otherwise supported by clinical scenario" is only in BCBSM), and in the S-ICD age (Carelon's stray "<= 21").

Where they differ:
- NICM: Florida Blue has no NYHA class, no age limit, and no named duration. The others require NYHA II-III and 90 days or 3 months of GDMT.
- Channelopathies and sarcoid: Florida Blue accepts a diagnosis plus "high risk"; BCBSM and Carelon require a documented event.
- Early post-MI: only Cigna covers it. Florida Blue labels it investigational.
- S-ICD: Cigna needs no reason to avoid leads. Florida Blue needs a contraindication to transvenous leads. BCBSM/Carelon accept any one of five reasons, including youth.
- Replacement: Cigna covers it unconditionally; BCBSM/Carelon cap it at end-of-life or near-end-of-life; Florida Blue lists four reasons including "change in member's medical condition".
- Survival gate: BCBSM and Carelon apply it to every inclusion; Florida Blue only lists life expectancy under 1 year as an investigational override; Cigna omits it.

Unique to one payer: Florida Blue CCM investigational statement and LOINC documentation table; BCBSM substernal criteria and Lamin A/C sex criterion (shared with Carelon and Cigna); Cigna AED, myotonic dystrophy, Chagas, giant cell myocarditis, peripartum, amyloid, tetralogy of Fallot, syncope with LVEF <= 49% in NICM; Carelon the generic framework and repeat-therapy rules; Fallon the InterQual routing, per-code prior authorization column, and a different rule for EV-ICD by product.

Florida Blue stricter or looser:
- Looser than BCBSM/Carelon/Cigna for NICM (no NYHA class, no age, no duration) and for channelopathies and sarcoid (no event required).
- Looser than BCBSM/Carelon on the survival gate (it is not required for every approval).
- Stricter than Cigna for early post-MI (investigational) and for S-ICD (a contraindication to transvenous leads is required); stricter than Cigna on replacement (no unconditional approval).
- Stricter than BCBSM on substernal (silent, so there is no path) and than all others on cardiac contractility modulation (explicitly investigational, though no other payer addresses it).
- Different in kind: the investigational override list. A member who meets an inclusion but also had revascularization in the past 3 months is "experimental or investigational" under Florida Blue; BCBSM and Carelon build the same rule into the inclusions ("at least 90 days post revascularization").

## Structure

- Layout: Florida Blue and BCBSM put criteria first and a long rationale after, but BCBSM is 67 pages and Florida Blue 14; both open with a narrative before the criteria. Carelon is a vendor template with generic framework pages before the clinical indications. Cigna has a short coverage policy, then 30 pages of background. Fallon is a routing document.
- Logic shape: all but Fallon are pathways (any of N scenarios) with nested ANY/BOTH/EITHER lists; S-ICD and substernal are ALL lists over the transvenous pathways. Florida Blue uses a trailing negative list (the investigational paragraph) instead of inclusions with built-in waits. Cigna's S-ICD uses "NONE of the following".
- Delegation: Fallon to InterQual and NCD 20.4; Carelon says plans may substitute their own policy, and Medicare plans use CMS criteria first; Florida Blue to NCD 20.4 for Medicare Advantage, a CRT policy implied for NYHA IV, and a wearable-defibrillator guideline; BCBSM restates NCD 20.4 in a Government Regulations section; Cigna to related CRT and EP-study policies.
- Codes: Florida Blue lists 55 CPT codes with 31 marked investigational; BCBSM a code grid; Carelon CPT, HCPCS and an anesthesia code; Cigna short tables that omit generator codes yet cover replacement; Fallon a table with prior-authorization yes/no per code, including future-dated changes. None maps codes to criteria.

## Problems for an automated checker

- Florida Blue grouping: the adult list is "meet ONE of the following criteria", yet bullets end with "; OR", the fifth ends with "OR" inside a nested list, and bullet 6 has no connector. A parser might read the ion channelopathies as four separate pathways (correct) or merge them. The investigational paragraph ("do not meet the above criteria or have had ANY of the following") overrides inclusions with no stated precedence.
- Florida Blue "the response to optimal medical therapy has been adequately determined" and "considered to be at high risk for sudden cardiac death" are judgment leaves with no definition, no duration, and no test; the chart can only contain a clinician statement.
- Florida Blue "Members with a history of a life-threatening clinical event ... after reversible causes ... have been excluded" is grammatically a statement that members have been excluded.
- Florida Blue "history of need for explanation of a transvenous ICD" is a typo for explantation.
- BCBSM "in an individual <= 70 years of age or otherwise supported by clinical scenario" removes the age limit with an undefined escape; "which would typically allow" makes the 90-day GDMT period soft; "Syncope within the preceding 6 months or other reasonable time frame" likewise.
- BCBSM's "Primary Prevention" heading contains arrest and sustained-VT survivors, which are secondary-prevention events. A parser keyed on headings would mis-sort them. Its "Exclusions: ... Do not meet above criteria" is circular.
- BCBSM vs Carelon comparators differ (<35% vs <= 35%; >40 days vs >= 40 days). An LVEF of exactly 35% or an MI exactly 40 days earlier would get different answers from nearly identical text. Whether this is a transcription difference or intent cannot be determined from the documents.
- Carelon's S-ICD age bullet "Subcutaneous device is preferred due to younger age of patient Individual is <= 21 years of age" appears to fuse a redline deletion and insertion; the date line also prints "11/1710/20/2024".
- Cigna "Individual with unexplained syncope due to ANY of the following" lists diagnoses as causes of syncope, and "LVEF > 50%" in the no-structural-disease bullet leaves exactly 50% uncovered. "post-acute MI (> 48 hours and < 40 days) and/or revascularization (< 90 days)" has an and/or; and this pathway contradicts the 40-day rule in the other policies.
- Cigna "Replacement ... is considered medically necessary" has no conditions; its coding table omits the generator-only codes.
- Criteria a chart cannot show: expected survival over one year, "high risk", "reasonable time frame", "optimal medical therapy", whether reversible causes were "completely" excluded, and for Fallon the entire InterQual criteria set (proprietary, not in the PDF).
- Fallon yields an empty tree; a keyword extractor would instead pick up numbers from the EV-ICD trial summary (88%, 79%, 98.7%).

## Test cases

1. 58-year-old man, ischemic cardiomyopathy, MI 8 months ago, no revascularization within 6 months, on maximum GDMT, NYHA II, LVEF exactly 35%. Florida Blue: approves (LVEF of 35% or less, MI at least 40 days before). Carelon: approves (LVEF <= 35%). Cigna: approves (LVEF <= 35%). BCBSM: denies if the printed "<35%" is read literally (LVEF is not below 35%). This case tests the comparator difference rather than a clinical policy difference.
2. 66-year-old woman, nonischemic dilated cardiomyopathy, LVEF 30%, NYHA class I, on GDMT for 4 months, no arrest or VT. Florida Blue: approves (NICM, LVEF 35% or less, reversible causes excluded, medical therapy response determined; no NYHA requirement). BCBSM, Carelon, Cigna: deny (all require NYHA II or III with NICM). Fallon: InterQual not available to read.
3. 24-year-old with congenital long QT syndrome, never had syncope or arrest, on a beta blocker, no family history. Florida Blue: approves if the physician considers him high risk (diagnosis of congenital long QT syndrome plus "considered to be at high risk for sudden cardiac death"). BCBSM and Carelon: deny (need syncope or VT despite beta blockers, or survivor of cardiac arrest). Cigna: denies unless a risk factor exists (sudden cardiac arrest, family history, or compliance/intolerance of drugs).
4. 70-year-old with an indication for a transvenous ICD (meets criteria), good venous access, no infections, no pacing need, wants an S-ICD. Cigna: approves (met transvenous criteria and none of symptomatic bradycardia, incessant VT, or ATP-terminated VT). Florida Blue: denies (needs a contraindication to a transvenous ICD such as no vascular access). BCBSM and Carelon: deny (need at least one of inability to secure venous access, immunocompromise, recurrent infection, endocarditis, or youth).
5. 61-year-old, MI 30 days ago, LVEF 38%, NSVT on monitor, inducible sustained VT on EP study. Cigna: approves (post-MI under 40 days, LVEF <= 40%, NSVT and inducible VT). Florida Blue: investigational (acute MI under 40 days). BCBSM and Carelon: deny (MI at least 40 days required).
