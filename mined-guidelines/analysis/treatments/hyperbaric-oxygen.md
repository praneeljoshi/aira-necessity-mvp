# Hyperbaric oxygen therapy (HBOT): cross-payer comparison

Documents (all in `sourcing/library/hyperbaric-oxygen/`, profiles in `sourcing/analysis/profiles/`):
Florida Blue 01-99180-01 (rev. 02/15/26, 10 pp), Cigna 0053 (5/15/2026, 39 pp), UHC 2026T0632J (5/1/2026, 25 pp), BCBSTX THE801.003 (10/15/2024, policy end date 12/31/2025, 92 pp), Blue Shield CA Promise PHP_2.01.04 (6/1/2026, 100 pp), Excellus 2.01.07 (7/16/2026, 27 pp), Priority Health 91151-R8 (9/1/2024, 10 pp), Medica MP9055 (10/01/2025, 3 pp).

## What it is

HBOT has the patient breathe near-100% oxygen inside a pressurized chamber (monoplace, or multiplace with mask/hood), so that the blood carries far more oxygen to hypoxic or infected tissue. It is billed per session by the attending physician (CPT 99183, plus facility G0277 per 30 minutes). Payers do not gate it on conservative therapy in general. They gate it on a closed list of diagnoses (carbon monoxide poisoning, decompression sickness, gas embolism, gas gangrene, crush injury, radiation necrosis, compromised grafts, refractory osteomyelitis, sudden hearing loss, severe blood-loss anemia, and so on), treat everything else as investigational, and attach a real clinical test to exactly one indication: the diabetic lower-extremity wound (Wagner grade 3 or higher, and no healing after 30 days of standard wound care). Most also declare "topical hyperbaric oxygen" (A4575 disposable bag/chamber) investigational. A second layer is utilization: a cap or review point on the number of treatments.

## Side by side

Cell text is abbreviated. "IC" = not covered because not listed ("all other situations"). "Inv" = named investigational / not medically necessary.

| Requirement kind | Florida Blue | Cigna 0053 | UHC | BCBSTX | BSC CA Promise | Excellus | Priority Health | Medica |
|---|---|---|---|---|---|---|---|---|
| Structure | Covered list (~19) + big investigational list; default-deny | First-line list (4), adjunctive list (~15), NMN list (~45); TOT separate | Covered list (17); default-deny | Table 1 diagnosis -> review-count rows (~25) + Notes 1-12 | Covered list (16); Medi-Cal manual supersedes | Covered list (18) + condition table + guidelines | Non-wound list (11), wound initial (4), wound adjunctive (diabetic) | Covered = "indications approved by UHMS Committee" (15) |
| Diabetic foot: diagnosis | Type 1 or 2 DM + wound due to diabetes | Wagner III+ diabetic ulcer of LE | "Diabetic lower extremity wounds" (no criteria) | Type 1/2 DM + LE wound due to DM | Same as FL | Same as FL | Same as FL | "Enhancement of healing in select problem wounds" |
| Diabetic foot: Wagner | grade 3 or higher | III or higher | none | grade-3 or higher | grade 3 or higher | grade 3 or higher | grade III or higher | none |
| Diabetic foot: conservative therapy / duration | no measurable healing after 30 days of "adequate course of standard wound therapy"; not defined | "failed standard wound therapy"; no duration | none | 30 days no healing; Note 12 defines standard care (vascular, nutrition, glucose, debridement, moist dressing, off-loading, infection) | 30 days no healing, undefined | 30 days; standard therapy "may include ANY of" the 7 components | "no measurable signs of healing for at least 30-days" + "failed an adequate course" | none |
| Thresholds elsewhere | none | ISSHL within 4 weeks of onset | chamber >= 1.4 ATA (definition) | burns 15-90% TBSA within 24 h; anemia shock SBP < 90 mmHg + 3 other signs | chamber > 1.4 ATA (guideline text); ISSHL steroid within 2 wk (salvage 1 mo) | ISSHL 30 dB over 3 frequencies; CO within 6 h; osteomyelitis >= 6 wk; tissue O2 < 30 mmHg (table) | chamber >= 2.0 ATA, ASME PVHO-1 / NFPA 99 hard-sided | ISSHL within 2 weeks of onset |
| Imaging / labs | none | none | none | none | none | audiogram for ISSHL; fundoscopy noted for CRAO (table) | none | none |
| Sudden hearing loss | Covered, no time limit | Within 4 weeks | Covered, no time limit | Covered (review after 5 tx) | With steroids within 2 wk or salvage within 1 mo | Covered; table says steroid within 2 wk / 1 mo | Covered, no time limit | Within 2 weeks |
| Central retinal artery occlusion | Not listed (IC) | Covered (adjunctive) | Covered | Inv ("within first 24 hours of diagnosis" listed under investigational) | Covered | Covered (added 6/2025) | Covered (added 9/2024) | Covered |
| Avascular necrosis | Inv (idiopathic femoral neck necrosis) | Covered | Covered | Inv | Inv | IC | IC | Covered |
| Acute thermal burns | Covered, no threshold | Only if inpatient hospitalization | 2nd/3rd degree | 2nd/3rd degree, 15-90% TBSA, within 24 h | Inv | Inv | not listed (IC) | Covered |
| Severe anemia | Profound anemia, exceptional blood loss, transfusion impossible or delayed | Exceptional blood loss, transfusion not an option | Severe, transfusion refused/delayed/unavailable | Refuses blood + shock, disorientation, ECG ischemia, ischemic gut | Same wording as FL | Same wording as FL | not listed | Severe anemia |
| Intracranial abscess | Covered | Covered | Covered | Covered (individual consideration) | Inv (intracranial abscess) | Inv | not listed | Covered |
| Refractory mycoses | Inv | Actinomycosis NMN | IC | Covered (selected) | Inv | Covered | Actinomycosis, only as adjunct | IC |
| Acute osteomyelitis | Inv | n/a | IC | Inv | Inv | Covered if refractory | n/a | IC |
| Acute cerebral edema / brown recluse bite | Inv | NMN | IC | Covered (individual consideration / after 5 tx) | Inv | Edema covered; bite Inv | n/a | IC |
| Topical oxygen | Inv for all indications (A4575 investigational); also limb-specific pressurization and ozone | Covered as adjunct for DFU failed optimal care (A4575) | Unproven for wounds | Inv with pressurization; topical O2 without pressure not addressed | Inv | Inv | Inv | Not covered (HTOT, CTOT) |
| Repeat / number of sessions | Reimbursement: 30 treatments / 12 months; more = medical review; measurable healing within any 30-day period | none | none | Review point per diagnosis (5, 10, 12, 20, 30 treatments; several "individual consideration") | none in criteria (UHMS counts in guidelines) | No continued coverage if no healing in any 30-day period; "should NOT require more than 40"; review column | none | none |
| Documentation | Initial assessment, H&P, visit notes, labs; wound location, size, bed, drainage; LOINC table | none | none | Needed if > 1 month or over count: 2 of (photos, consults, operative, office records); wound fields incl. Wagner, initial vs extension | none | Items I.A-F; weekly wound measurements, photos for advanced DFU; session logs | none | none |
| Provider / site rules | none (unit = one treatment regardless of time) | none | none | none | none | CMS physician certification, ACLS, 5-minute response, present at ascent/descent | Chamber standards (2.0 ATA, ASME) | none |
| Prior authorization | not stated | not stated | not stated | HCSC request form noted | Prior auth dept referenced | not stated | "may be required" | Not required; retrospective review |
| Delegation | Medicare Advantage -> NCD 20.29, 270.4; FEP/SAO own guidelines | Delegated vendor guidelines in some markets | Member benefit plan; InterQual may be used; dx codes in separate list | Member contract; Illinois mandates | Medi-Cal Provider Manual supersedes | CMS practitioner criteria | CMS for Medicare; Michigan Medicaid manual | UHMS Committee list |
| Codes | 99183, G0277, A4575; ICD-10 list "support medical necessity" | 99183, G0277, A4575 | 99183, A4575, E0446, G0277 | 99183, A4575, G0277 | 99183, A4575, E0446, G0277 | 99183, G0277, A4575 (E/I), E0446 (E/I); ICD-10 list | 99183, G0277, 0413; A4575, E0446 not covered; ICD-10 mapped by indication | 99183, A4575, E0446, G0277, rev 0413 |

## Agreement and disagreement

Where payers align. Every payer covers the core emergency and surgical set: acute carbon monoxide poisoning, decompression sickness, air/gas embolism, gas gangrene, crush injury/acute traumatic ischemia, compromised skin grafts and flaps, necrotizing soft tissue infection, refractory osteomyelitis, radiation necrosis (including the irradiated-jaw dental case), and the diabetic wound. Five payers (FL, BCBSTX, BSCA, Excellus, Priority) use nearly identical diabetic-wound language: diabetes, Wagner 3+, 30 days without healing despite standard care. All reject stroke, MS, autism, cerebral palsy, TBI, fibromyalgia and so on. All except Cigna class topical HBOT as investigational for every use.

Where Florida Blue is stricter.
- CRAO: not on FL's list, so investigational by default; Cigna, UHC, BSCA, Excellus, Priority and Medica cover it. (BCBSTX also lists it as investigational.)
- Avascular necrosis: FL names "idiopathic femoral neck necrosis" as investigational; Cigna, UHC and Medica cover avascular necrosis.
- Topical oxygen: Cigna covers it for a diabetic foot ulcer that failed optimal care; FL calls topical HBOT, limb-specific pressurization and ozone investigational for all indications.
- Refractory mycoses: FL investigational; BCBSTX and Excellus cover; Priority covers actinomycosis.
- Acute cerebral edema and brown recluse bites: FL investigational; BCBSTX covers both, Excellus covers cerebral edema.
- Acute refractory osteomyelitis: FL investigational; Excellus covers.
- A numeric session cap that no one else prints as a rule: 30 treatments per 12 months (Reimbursement Information), plus a "measurable signs of healing within any 30-day period" documentation rule. Only BCBSTX (review counts per diagnosis) and Excellus (40 treatments, 30-day healing) approach this.

Where Florida Blue is looser.
- Diabetic wounds vs UHC and Medica: they state no Wagner grade or duration. Relative to Cigna, FL adds an explicit 30-day interval.
- ISSHL: FL has no time window; Cigna (4 weeks), Medica (2 weeks), BSCA (steroid + 2 weeks / 1 month) do.
- Thermal burns: FL covers any "acute thermal burn injury"; Cigna needs inpatient hospitalization, BCBSTX 15-90% TBSA within 24 hours, BSCA and Excellus do not cover.
- Intracranial abscess: FL covers; BSCA and Excellus list intra-/intracranial abscess as investigational.
- Documentation: FL asks for physician notes and labs "may be required" when over the cap; Excellus and BCBSTX specify more.
- Provider and site: FL has none; Excellus imports CMS supervision and ACLS rules; Priority specifies a 2.0 ATA hard-sided chamber.

Unique to one payer: BCBSTX's anemia symptom checklist (SBP < 90 mmHg and three more signs), burn TBSA and 24-hour window, venous stasis ulcer coverage after failed venous surgery, decubitus ulcers and brown recluse bites; Excellus's per-condition pressure/selection/duration table and CMS practitioner rules; Priority's chamber specification and indication-keyed ICD-10 map; Medica's no prior authorization with retrospective denial; BSCA's Medi-Cal supersession and EPSDT language; FL's LOINC documentation table, per-session unit rule and ozone/limb-specific exclusions; Cigna's TOT coverage and "first-line vs adjunctive" labels.

## Structure

- Shape is the same everywhere: a list of indications, each its own pathway (any-of), plus a not-listed-means-investigational default. Only one indication (the diabetic wound) has a nested all-of of three leaves, depth 2. Excellus nests a further any-of (standard wound therapy components a-g) and a second-level list in the SSNHL timing.
- Criteria location: FL pp.1-3 (Position Statement) with caps and documentation in Reimbursement Information; Cigna pp.2-4 of 39; UHC p.1-2 of 25; BCBSTX Table 1 pp.3-4 and Notes pp.4-7 of 92; BSCA Policy Statement pp.1-3 of 100 (plus Policy Guidelines that read as criteria); Excellus pp.1-10 of 27 (Policy Statement and Guideline table); Priority Section I pp.1-2 plus technical standard in Section IV; Medica p.1 pointing to a list in Description p.2.
- Table-driven: BCBSTX Table 1 (diagnosis -> review count) and Excellus Policy Guideline IV (5 columns). Everyone else is prose lists.
- Delegation: FL to CMS NCDs for Medicare Advantage and to FEP/SAO guidelines; UHC to a separate diagnosis code list and member plan (InterQual mentioned in boilerplate); BSCA to Medi-Cal manuals (which it says have no clinical guideline, so the policy applies); Medica to the UHMS committee list; Priority to CMS and Michigan Medicaid; Excellus to CMS for practitioner rules.
- Codes: all list 99183 and G0277; ICD-10 appears in FL, Excellus, Priority. Priority maps ICD-10 under each indication; FL and Excellus list them as unmapped ranges. UHC points to an external list. Others have no ICD-10.

## Problems for an automated checker

- Capitalized quantifiers with the opposite of the logical meaning: Cigna "medically necessary first-line treatment for ALL of the following conditions" and "not medically necessary for ANY of the following conditions". Parsing ALL as all-of makes the list unsatisfiable.
- "Adequate course of standard wound therapy" (FL, BSCA, BCBSTX, Excellus), "failed standard wound therapy" (Cigna), "optimal standard of care": FL's Definitions section is "None"; BCBSTX Note 12 and Excellus list components, but Excellus says "which may include ANY of the following", so none is required. A chart rarely records "adequate".
- "No measurable signs of healing after 30 days": needs two dated measurements and an interval; the policy gives no percent-area threshold. Priority phrases the same idea two ways in one section ("at least 30-days of treatment" and "failed an adequate course").
- FL reimbursement cap: "limited to thirty (30) treatments within a 12 month period" is a count across claims over a year, not chart evidence, and it sits outside the Position Statement.
- Default-deny: "considered experimental or investigational in all other situations" means a not-listed diagnosis is NOT_MET rather than INSUFFICIENT; the checker must treat "not on list" as a decision.
- Indication names are not diagnoses a chart states: "Acute arterial insufficiency", "Acute traumatic ischemia (eg, crush injuries, reperfusion injury, compartment syndrome)", "Chronic refractory osteomyelitis", "Compromised skin graft and flap", "Profound anemia with exceptional blood loss: only when blood transfusion is impossible or must be delayed". "Refractory", "compromised", "progressive" (BSCA admits "No definition of 'progressive' was identified") need clinician judgement.
- Conditions that are time-critical (CO within 6 hours, ISSHL 2 or 4 weeks, burns within 24 hours) need dated onset and dated treatment; many charts only give a visit date.
- Soft modal language in Excellus Policy Guidelines ("should", "recommended", "Most patients should NOT require more than 40 treatments") and BSCA's non-binding "clinical input" (a 24-hour CRAO window described then disclaimed) cannot be told apart from criteria by layout.
- Extraction: Priority's sub-items i-iv appear indented under "compromised skin grafts" though they are separate indications; Excellus's table rows break across pages with repeated headers; BCBSTX Table 1 has blank review counts for the postoperative foot row and cell bullets inside rows; BSCA repeats the whole policy in Appendix A before/after columns; FL's footnoted Wagner scale sits inside a bullet; Medica's covered list is in Description, not Coverage Policy; UHC's diagnosis list is not in the PDF.
- Version risk: BCBSTX prints "Policy End Date 12/31/2025"; Excellus changed CRAO/ISSHL status in 2025; Cigna moved TOT to covered 9/15/2025; FL's history refers to criteria (CRAO 2011, continuation 2009) no longer in the text.

## Test cases

1. Diabetic foot ulcer, 3 weeks of care. 62-year-old with type 2 diabetes, Wagner grade 3 plantar ulcer with osteomyelitis, debrided and off-loaded, followed for 21 days with no area reduction. Cigna would approve (Wagner III or higher "that have failed standard wound therapy"; no duration stated), as would UHC ("Diabetic lower extremity wounds", no criteria). Florida Blue, BCBSTX, BSCA, Excellus and Priority would not, because criterion c requires "no measurable signs of healing after 30 days of an adequate course of standard wound therapy" (Priority: "at least 30-days").
2. Central retinal artery occlusion. 70-year-old with painless monocular vision loss, fundoscopy-confirmed CRAO, presenting within 6 hours. Cigna ("central retinal artery occlusion" adjunctive), UHC, BSCA, Excellus, Priority and Medica would approve. Florida Blue would not: CRAO is not on its covered list and "considered experimental or investigational in all other situations". BCBSTX also lists acute retinal artery insufficiency as investigational.
3. Outpatient burn. 34-year-old with second-degree burns over 8% of body surface treated as an outpatient, within 24 hours. Florida Blue would approve ("Acute thermal burn injury", no extent or setting). UHC would approve ("Thermal burns, second or third degree"). Cigna would not (needs "requiring inpatient hospitalization"), BCBSTX would not (needs "15% to 90% of total body surface"), BSCA and Excellus would not (acute thermal burns listed investigational).
4. (Extra) Sudden hearing loss at 6 weeks, no steroids. Florida Blue and UHC approve (no time limit); Cigna (within four weeks), Medica (within two weeks) and BSCA (steroid within 2 weeks, salvage 1 month) would not.
