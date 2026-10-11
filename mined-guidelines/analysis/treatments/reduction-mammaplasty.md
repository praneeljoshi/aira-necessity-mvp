# Reduction mammaplasty (CPT 19318)

Documents: Florida Blue 02-12000-11 (rev 09/15/25), BCBS Massachusetts 703, BCBS Texas SUR716.012 (effective 12/01/2024, end date 12/31/2025), Cigna 0152 (eff 11/15/2025), UnitedHealthcare MP.004.32 (eff 06/01/2026).

## What it is

Surgical removal of breast tissue and skin to relieve symptoms of macromastia (breast hypertrophy). Payers treat it as cosmetic by default and cover it only as reconstructive/functional when the patient has documented physical symptoms (back, neck, shoulder pain, bra-strap grooving, intertrigo, nerve symptoms) that did not respond to conservative care, and often when the planned resection weight clears the Schnur Sliding Scale (22nd percentile for the patient's body surface area). Reduction of the opposite breast for symmetry after cancer surgery is a separate, usually covered indication (WHCRA).

## Side by side

| Requirement | Florida Blue | BCBS MA | BCBS TX | Cigna | UHC |
|---|---|---|---|---|---|
| Criteria in the PDF? | Yes | Yes | Yes | Yes | No: InterQual "Reduction Mammaplasty, Female / Adolescent" |
| Age | None stated | Under 18 needs Tanner IV/V (ages 15-18) AND (stable height 6 mo OR puberty complete on wrist x-ray) | >=18 | >=18 or completed breast growth | InterQual (adolescent version) |
| Symptoms | At least 2 of 7: back pain, neck pain, shoulder pain, paresthesias of hands/arms, headache, intertrigo, bra-strap shoulder grooving | Shoulder/neck/back pain (with shoulder grooving documented) OR recurrent/chronic intertrigo resistant to topical treatment | One of: upper back/neck/shoulder pain "long-standing in duration and increasing in intensity", OR persistent nonseasonal submammary intertrigo, OR ulnar nerve paresthesia; AND symptoms interfere with ADLs | At least 1 of: shoulder/upper back/neck pain and/or ulnar nerve palsy (no other etiology), OR intertrigo, dermatitis, eczema, hidradenitis | InterQual |
| Exam / photo | Photos not required initially; may be requested | none stated | Significant shoulder grooving or ulceration, obvious hypertrophy, exam consistent; photo documentation required | Preoperative photographs confirm significant hypertrophy and grooving/intertrigo if stated | InterQual |
| Conservative therapy and duration | "minimum 6-week history" and unresponsive; e.g. bra, analgesia, NSAIDs, PT, exercises, heat/cold | >=6 weeks; appropriate support bra, exercises, heat/cold, NSAIDs/muscle relaxants; intertrigo: topical | Failure of >=6 weeks of: PT with home exercise, OR support bra, OR local hygiene/topical (for intertrigo) | "unresponsive to medical management" (no duration) | InterQual |
| Weight threshold | Planned grams per breast at or above 22nd percentile Schnur by BSA (Mosteller) | >=500 g per breast OR Schnur if planned <500 g (table stops at BSA 1.90) | Greater than 22nd percentile; breast tissue not fat; 5th-22nd gray zone case by case | Above 22nd percentile Schnur OR more than 1 kg per breast regardless of BSA | InterQual |
| Post-op check | Letter of explanation if less removed than planned | none | Final determination may use pathology report | none | none |
| Symmetry after cancer | Medically necessary after mastectomy (non-diseased/contralateral); "may" meet after lumpectomy/radiation | not addressed | Staged reduction before nipple-sparing mastectomy/lumpectomy | Contralateral symmetry after mastectomy or lumpectomy; staged reduction/mastopexy before nipple-sparing mastectomy | WHCRA: all plans cover |
| Liposuction | Adjunct included; sole procedure investigational | none | With or without ultrasound: experimental | Integral when adjunct; sole method unproven | none |
| Repeat surgery | none | Not medically necessary unless complications of initial surgery | none | none | none |
| Exclusions | Cosmetic; correction of prior cosmetic surgery; other indications investigational | Other indications investigational | Psychosocial symptoms or appearance | Psychological symptoms alone, appearance, inverted nipple correction, dog-ear excision | Plan exclusion common |
| Documentation | Symptoms and duration, height/weight, anticipated grams per breast, conservative therapy and response | "well-documented clinical symptoms" | Photos, H&P | Photos | Medical records per UHC guideline |
| Prior auth | not stated | Required: HMO/POS outpatient and all inpatient; not for PPO/indemnity outpatient | not stated | not stated | not stated |

## Agreement and disagreement

Agree: nearly all use the 6-week conservative-care idea (FL, MA, TX), the Schnur 22nd-percentile BSA table (same numbers in FL, MA, TX, Cigna), and treat psychosocial indication and appearance as non-covered. All treat liposuction alone as investigational/unproven. FL, Cigna and TX recognize post-cancer symmetry.

Differ: Symptoms count (FL needs 2 of 7; TX needs ADL interference; Cigna and MA need 1). Weight rule: MA's 500 g alternative and Cigna's 1 kg alternative do not exist in FL or TX. Age: FL has none, others require 18 or maturity evidence. Repeat surgery only MA. Pathology check only TX. UHC gives no criteria.

Florida Blue stricter than others: it needs two symptoms where Cigna, MA and TX each accept one qualifying symptom; and its Schnur threshold has no alternative route. Cigna accepts more than 1 kg per breast regardless of BSA, and MA accepts a flat 500 g, which is lower than FL's table at BSA 1.95 and above (575 g and up). Florida Blue looser: no age or maturity rule, no ADL-interference requirement, photographs only on request, grooving is one of seven symptoms rather than required, a broad list of conservative measures with no specific modality mandated (TX requires PT, bra, or hygiene failure), no pathology check, no repeat-surgery restriction. FL counts headache and paresthesias toward the two.

Unique to one payer: MA Tanner/wrist x-ray; TX nerve and ADL language, pathology; Cigna 1 kg route, photographs as a criterion, hidradenitis/eczema; FL "headache" symptom.

## Structure

FL: prose Position Statement, bulleted "at least two of" list, then numeric threshold via a table in the Reimbursement section; MA: age block then symptoms then weight, in a short policy with a truncated table; TX: numbered 1-2 with lettered sub-items and NOTES 1-3 after the criteria carrying rules; Cigna: bulleted ALL list with an either/or threshold and a coding table grouped by coverage status; UHC: a benefit statement plus delegation to InterQual (proprietary) and WHCRA text. Codes: all use CPT 19318; UHC lists ICD-10-CM N62 and N65.1; MA lists ICD-10-PCS excision codes; Cigna groups CPTs by status.

## Problems for an automated checker

- Prospective vs retrospective: the Schnur criterion is "grams of breast tissue planned to be removed" (FL) but TX and FL notes allow review of actual removal ("may be asked to provide a letter", "post-operative pathology report"). A prior-auth chart has only the plan.
- Computation: BSA via Mosteller from height/weight, then table lookup by interpolation; MA's table stops at 1.90 m2; FL and TX tables skip values (1.35 steps of 0.05) so BSA between rows needs a rule that is not stated.
- Vague: "unresponsive to conservative therapy", "unresponsive to medical management", "significant breast hypertrophy", "Obvious breast hypertrophy", "long-standing in duration and increasing in intensity", "well-documented clinical symptoms".
- Ambiguous grouping: FL "A minimum 6-week history of AT LEAST TWO OF THE FOLLOWING that are unresponsive..."; TX 2.d "Failure of at least 6-weeks of conservative measures including: ... or ... or"; MA "This includes documentation of the presence of shoulder grooving".
- Advisory wording inside criteria: MA "the surgeon should follow the below Schnur sliding scale, which suggests".
- Criteria a chart cannot show: photographs interpreted as "significant hypertrophy", pathology report on surgery not yet performed, "no other etiology has been found on appropriate evaluation" (Cigna).
- "may meet the definition" (FL lumpectomy/radiation) is not decidable.
- TX document ends 12/31/2025: version control; MA document's current date unclear.
- UHC: the real test is in InterQual and the plan benefit exclusion, so the same chart can fail for a non-clinical reason.

## Test cases

1. 17-year-old, Tanner IV, 66 in and 190 lb (BSA about 2.0 m2, Schnur 22nd percentile 628 g), shoulder pain and bra-strap grooving for 8 weeks despite bra and NSAIDs, planned 800 g per breast. Florida Blue: approve (2 of 7 symptoms, 6 weeks, 800 g at or above 628 g, no age rule). BCBS TX: deny (requires age 18 or older). Cigna: deny unless breast growth is documented complete. BCBS MA: not yet approvable, needs stable height for 6 months or wrist-radiograph puberty completion in addition to Tanner IV.
2. 34-year-old, BSA 1.80 (threshold 441 g), upper back pain only, 10 weeks of bra and NSAIDs failed, planned 450 g per breast, photos show hypertrophy. Florida Blue: deny (only one of the symptoms; "AT LEAST TWO OF THE FOLLOWING"). Cigna: approve (one symptom unresponsive to medical management, photos, 450 g above 441 g). BCBS TX: needs shoulder grooving or ulceration and ADL interference documented; if grooving is absent, deny.
3. 40-year-old, BSA 2.0 (threshold 628 g), back pain and shoulder grooving for 3 months despite PT, planned 600 g per breast. Florida Blue: deny (below the 22nd percentile line). BCBS TX: deny or gray-zone review (between 5th and 22nd percentile). Cigna: deny (below Schnur and under 1 kg). BCBS MA: approve (at least 500 g per breast, symptoms with grooving documented).
