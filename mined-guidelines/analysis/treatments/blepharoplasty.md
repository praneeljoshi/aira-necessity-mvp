# Blepharoplasty (and ptosis and brow surgery): how five payers gate it

Documents profiled (JSON in `sourcing/analysis/profiles/`):

| Payer | File | Version as printed | Size |
|---|---|---|---|
| Florida Blue (client) | `bcbsfl-02-65000-11-blepharoplasty-brow-surgical-procedures.pdf` | 02-65000-11, revised 05/15/25 | 8 pp |
| BCBS Massachusetts | `bcbsma-740-blepharoplasty-blepharoptosis-repair-and-brow-ptos.pdf` | Policy 740, no effective date printed, history to 5/2020 | 5 pp |
| Cigna | `cigna-0045-blepharoplasty-reconstructive-eyelid-surgery-and-b.pdf` | Coverage Policy 0045, effective 6/15/2026 | 13 pp |
| EmblemHealth | `emblem-blepharoplasty.pdf` | MG.MM.SU.10jC2, last review March 13, 2026 | 11 pp (about 6 pp of ICD-10 rows) |
| UnitedHealthcare | `uhc-mp-002-29-brow-ptosis-and-eyelid-repair.pdf` | MP.002.29, effective August 1, 2026 | 9 pp; blepharoplasty criteria are in InterQual, not in the PDF |

## What it is

Blepharoplasty removes excess skin, fat and muscle from the upper or lower eyelids (CPT 15820-15823). It is closely tied to ptosis repair (67901-67908, drooping lid margin) and brow lift (67900), and these are usually written in one policy. The core payer question is "functional or cosmetic": is the surgery treating a vision or eye-surface problem, or only appearance? Payers gate it on a patient complaint (trouble reading or driving, looking through the lashes), a superior visual field test done untaped and taped (taping simulates the surgical result), eyelid photographs, a margin reflex distance (MRD1, the distance from the corneal light reflex to the upper lid edge, often <= 2 mm for ptosis), or an etiology that is accepted without a field test (anophthalmic socket prosthesis problems, thyroid eye disease, nerve palsy, trauma, entropion/ectropion). Everything else is excluded as cosmetic.

## Side by side

| Requirement kind | Florida Blue | BCBS Massachusetts | Cigna | EmblemHealth | UnitedHealthcare |
|---|---|---|---|---|---|
| Where criteria live | Position Statement, four sub-sections | Policy: Commercial, five sections | Coverage Policy, 5 procedure paragraphs | Guideline + Documentation sections | InterQual (external); only carve-outs in the PDF |
| Upper lid, function by vision | ANY-of indication list; vision item needs complaint + photos + field test | ALL: complaint; redundant skin on lashes OR significant dermatitis; field test | ANY-of; dermatochalasis item needs complaint + field test + photos | Open list (list "not meant to be all-inclusive"); complaint + photo + field test documentation | InterQual CP Blepharoplasty (>= 18 years) |
| Complaint | "difficulty reading or driving due to redundant skin overhanging ... or resting on the eyelashes" | "difficulty reading or driving due to upper eyelid skin drooping, looking through the eyelashes or seeing the upper eyelid skin" | same wording family | "Interference with vision or visual field ... Looking through the eyelashes" | Not in PDF |
| Visual field (blepharoplasty) | Untaped superior field <= 20 degrees AND taped increase >= 30% | Improve >= 20 degrees taped, OR obstruction limits upper field to within 30 degrees of fixation | Loss >= 20 degrees or 30%, corrected by >= 20 degrees or 30% with taping | Rest: within 30 degrees of fixation; taped improvement >= 12 degrees; Goldmann or programmable perimeter, 50-60 degrees tested | Not in PDF |
| Photographs | Front and side(s), straight gaze, showing skin overhanging margin or on lashes | Not required (removed 12/2015) | Preoperative frontal: corneal light reflex with head upright OR lid encroachment, plus findings consistent with field loss | Frontal canthus-to-canthus, head perpendicular; >= 1 of: margin <= 2 mm above light reflex, skin on lashes, prosthesis issue | Floppy eyelid: everted-lid photos; others not in PDF |
| Ptosis repair | ALL of 5: complaint; photos; field <= 20 degrees; taped increase >= 30%; MRD <= 2 mm | ALL of 2: complaint; field criterion (same OR as above); no MRD | ALL of 4: complaint; MRD1 <= 2.0 mm; field loss corrected by taping; photos; child <= 7: photos only | Congenital ptosis with amblyopia risk; photo margin <= 2 mm; field criterion | InterQual CP Ptosis Repair |
| Brow lift | BOTH: complaint of functional impairment; photos show brow below supraorbital rim. No field test criterion | Field criterion only (same OR) | ALL: complaint; field loss corrected with brow taping AND not correctable by lid surgery alone; full-face/lateral photos (brow below rim, consistent with field loss, attempts at brow elevation) | None (brow lift only appears in the cosmetic exclusion and CPT list) | Not named in the InterQual list; internal browpexy cosmetic |
| Lower lid | Corneal/conjunctival injury, irritation, tearing or pain due to ectropion, entropion or trichiasis | Defers to conjunctival irritation criteria "not discussed in this document"; otherwise cosmetic | ANY: metabolic/inflammatory edema unresponsive to medical management; entropion/epiblepharon with corneal injury; lid laxity with uncontrolled tearing; all with photos of functional impairment | Ectropion/entropion (visual fields not necessary), epiblepharon | InterQual Ectropion/Entropion |
| Etiology paths | Dermatitis unresponsive to conservative therapy; anophthalmic prosthesis; thyroid; nerve palsy; trauma/congenital | Prosthesis; trauma/tumor/surgery; thyroid; nerve palsy | Prosthesis; painful blepharospasm refractory to botulinum; thyroid/nerve palsy; trauma/tumor | Prosthesis; blepharospasm; epiblepharon; lagophthalmos (congenital too); thyroid exposure keratopathy; post-traumatic defects; blepharotomy | Lagophthalmos, lid retraction, thyroid eye disease, canthoplasty, floppy eyelid syndrome (each with its own criteria) |
| Age rules | None | <= 9 years: central vision obstruction severe enough for occlusion amblyopia; > 9 and adults: ANY-of paths | Ptosis child <= 7 | None | InterQual >= 18 only |
| Combination procedures | Not stated | "must meet the criteria for each procedure" | Each procedure plus 3 additional criteria | Not stated | "criteria for each individual procedure must be met" |
| Exemption when field test impossible | Yes: severe tremors, macular degeneration, deformities preventing sitting at the perimeter, glaucoma (examples) | None | None (field testing "generally not performed" in children <= 7) | Ectropion/entropion exempt | n/a |
| Cosmetic exclusion | "For cosmetic purposes or to correct deformities resulting from previous cosmetic surgery" or "Solely to improve appearance" | Appearance without functional signs; lower lid failing criteria is cosmetic | Absence of functional impairment or sole purpose of appearance | Solely cosmetic; appearance without functional signs | Cosmetic exclusion; internal browpexy always cosmetic |
| Codes | CPT 15820-15823, 67900-67908; no ICD-10 | CPT same; ICD-10-PCS procedure codes | CPT in per-procedure tables tied to "Considered Medically Necessary when criteria ... are met"; adds 67911 | CPT through 67924; about 180 ICD-10 diagnosis rows | CPT groups; 67961/67966 listed twice |
| Medicare / delegation | LCD L34028 reviewed; FEP/SAO own | LCD L34528 | Delegated vendors in "certain markets" | MCG may be used | InterQual |
| Prior authorization | Not stated | HMO/POS yes; PPO/Indemnity no | Plan-dependent | Not stated (clinical evidence must be submitted for preauthorization or post-payment review) | Not stated |

## Agreement and disagreement

Where payers align
- The cosmetic/functional line is the same everywhere: no coverage for appearance alone.
- A patient complaint of "difficulty reading or driving" and "looking through the eyelashes" appears in FL, BCBSMA, Cigna and Emblem.
- Taped versus untaped superior visual field is the objective test for upper lid and ptosis surgery (FL, BCBSMA, Cigna, Emblem).
- Etiology-based paths that skip the field test: anophthalmic prosthesis problems, thyroid eye disease sequelae, nerve palsy, trauma (all four).
- Ptosis MRD <= 2 mm (FL <= 2 mm, Cigna MRD1 <= 2.0 mm, Emblem photo margin <= 2 mm).

Where they differ
- Field-test thresholds are not comparable. FL measures the remaining field (<= 20 degrees) and the relative gain (>= 30%). BCBSMA offers an alternative (>= 20 degrees gain OR within 30 degrees of fixation). Cigna measures loss (>= 20 degrees or 30%). Emblem uses within 30 degrees at rest and >= 12 degrees gain. The same eye can pass one and fail another.
- Photos: FL front and side; Cigna frontal with a corneal light reflex rule; Emblem frontal with the head perpendicular; BCBSMA none (removed in 12/2015).
- Brow lift: FL needs no field test; BCBSMA needs only the field test; Cigna needs field test plus proof lid surgery alone cannot fix it; Emblem has no brow criteria.
- Lower lid is written out only by FL, Cigna and Emblem; BCBSMA defers.
- Age: BCBSMA <= 9 years amblyopia pathway; Cigna <= 7 for ptosis; FL and Emblem have no age rule in the criteria (Emblem lists "congenital ptosis with risk for amblyopia").
- Covered extras: blepharospasm (Cigna, Emblem), lagophthalmos (Emblem, UHC), eyelid retraction (Cigna, UHC, Emblem), floppy eyelid syndrome (UHC only), epiblepharon (Cigna, Emblem), dermatitis (FL only, removed by Emblem in 8/2023).
- Open versus closed: Emblem says its list is "not meant to be all-inclusive"; FL, BCBSMA, Cigna read as closed.
- UHC's real criteria are InterQual and cannot be compared from the PDF.

Florida Blue stricter than others
- Requires both an untaped field <= 20 degrees AND a taped gain >= 30% for the vision indication (BCBSMA offers an OR; Emblem requires only within 30 degrees plus 12 degrees of gain; Cigna's 20 degrees of loss from a normal 50-60 degree field is a milder remaining-field threshold).
- Requires front and side photos plus field testing (BCBSMA requires no photos).
- Requires MRD <= 2 mm AND field test AND photos for ptosis (BCBSMA needs only complaint plus field).
- Dermatitis item needs a documented onset, history, extent and discharge description.
- No blepharospasm, lagophthalmos, retraction or floppy eyelid indications (Cigna, Emblem, UHC cover them).

Florida Blue looser than others
- Brow lift needs only complaint and photos with the brow below the supraorbital rim; no field test and no "cannot be corrected by lid surgery alone" (Cigna).
- No rule for combined procedures (Cigna adds three criteria; BCBSMA and UHC require each procedure's criteria).
- Trauma/congenital defect and some etiologic items have no stated test.
- Explicit exemption when visual-field testing cannot be performed.
- No age restriction or prior-authorization conditions.
- No contraindication or active eye disease list (Cigna's background says dry eye and thyroid disease are contraindications to eyelid surgery).

Unique to one payer
- FL: documented chronic pretarsal dermatitis path; field-test exemption note; LOINC documentation table with a six-month look-back.
- BCBSMA: age <= 9 amblyopia path; product-specific prior authorization.
- Cigna: botulinum-refractory blepharospasm; brow lift requires "cannot be corrected by upper lid blepharoplasty or blepharoptosis repair alone"; combination rule; per-CPT cosmetic dagger notes.
- Emblem: perimeter type (Goldmann or programmable) and tested extent 50-60 degrees; 12-degree gain; lagophthalmos, epiblepharon, blepharotomy indications.
- UHC: InterQual delegation; internal browpexy always cosmetic; floppy eyelid syndrome checklist (everted-lid photos, giant papillary conjunctivitis, corneal findings).

## Structure

- Layout. FL, BCBSMA and Cigna are procedure-by-procedure (blepharoplasty, ptosis, brow, lower lid). Emblem is an indication list followed by a documentation spec. UHC is a router: a coverage rationale that names InterQual modules, then a handful of locally written criteria for uncommon procedures, followed by about three pages of clinical evidence.
- Logic. Mostly ANY-of etiologies over ALL-of measurement bundles. FL nests ANY (six indications) with one item carrying ALL (complaint + photos + field), and the field test has its own AND (before/after). BCBSMA embeds an OR inside an ALL list. Cigna nests ANY, ALL, BOTH and OR four deep. Emblem is flat. UHC's local criteria nest three deep (floppy eyelid syndrome: ALL of symptoms, exam with ALL/ONE-of sub-items, photos, conservative therapy, infection ruled out).
- Where criteria live. Cigna splits mixed content: the Coverage Policy has thresholds, but the General Background restates measurements as "recommended". UHC puts meaning in InterQual, which a PDF-only system cannot see. Emblem's threshold values are in the Documentation section, not the Guideline list. FL puts a footnote-style NOTE (test exemption) after the brow lift list.
- Delegation. UHC to InterQual; Emblem to MCG for operational use and LCA A51525 in references; Cigna to delegated vendors "in certain markets"; FL and BCBSMA to Medicare LCDs for Medicare Advantage (FL cites L34028; BCBSMA cites L34528 for a similarly named LCD, so the numbers disagree).
- Codes. CPT lists in all five; FL and BCBSMA no ICD-10 diagnosis codes; Emblem about 180 ICD-10 rows; BCBSMA ICD-10-PCS procedure codes; Cigna ties codes to criteria by table headings. No code-level rule changes coverage (except UHC's "may be cosmetic" note).

## Problems for an automated checker

- UHC cannot be checked from its own text. "For medical necessity clinical coverage criteria, refer to the InterQual CP: Procedures" and the link is invisible in extracted text. The note "The InterQual criteria below only apply to persons 18 years of age or older" has nothing below it.
- Mixed units in visual-field thresholds. FL: "Before taping, the superior visual field is 20 degrees or less, AND After taping, the superior visual field is increased 30% or more". The base for 30% is unstated. Cigna: "at least 20 degrees or 30%", both alternatives used for baseline and correction. A chart will typically say "superior field 25 degrees untaped, 40 taped" or "30% loss", and a checker must decide how to convert.
- Lead-in does not match list. FL: "to correct obstruction of central vision when performed to correct ANY of the following" includes prosthesis difficulty, thyroid disease and nerve palsy, which are not central-vision problems. Does the lead-in apply to each item?
- FL's visual-field NOTE ("If visual field testing is not completed as indicated above, the medical documentation must support evidence of the medical condition which prevents the performance of the test") turns a required measurement into an optional one; it appears after the brow lift list and is scoped ambiguously. Brow lift itself lists no field test, but the NOTE speaks as if it did.
- MRD definition mismatch (FL): the criterion measures to "the upper eyelid skin edge"; the Definitions measure to "the eyelid margin" from "the corneal light reflex or center of the pupil". Cigna says MRD1 is measured from the corneal light reflex "which approximates the center of the pupil". Charts may give MRD1 per eye; the criterion does not say which eye or whether both must pass.
- OR inside ALL (BCBSMA): "Upper field must improve by at least 20 degrees with eyelid taped compared to visual field with untaped lid, OR visual field obstruction by lid or brow must limit upper field to within 30 degrees of fixation." Used three times, so the same OR is a leaf in each tree.
- Photographs are criteria that need an image, not text. FL: "Photographs from the front and side(s) on the operative side(s) in straight gaze demonstrating redundant skin". Cigna: "findings consistent with visual field loss documented on visual field testing". A chart text can say "photos attached" but the system cannot verify the finding.
- Open or judgmental terms. FL: "unresponsive to conservative therapy such as education regarding hygiene, antibiotics, etc."; BCBSMA "significant dermatitis"; Cigna "severe physical deformity or disfigurement"; Emblem "list not meant to be all-inclusive", "Symptomatic redundant skin".
- Emblem's open list means no match is not NOT_MET.
- Emblem includes brow lift in its cosmetic exclusion sentence but gives no brow criteria.
- Emblem extraction: about 6 of 11 pages are ICD-10 rows, one per line with blank lines between, which will swamp any prompt.
- BCBSMA has no effective date and a "History" showing 5/2020 as latest; dating the document is a hazard.
- Procedure-specific counts: sidedness. Criteria are unilateral/bilateral but charts record right and left fields separately.
- Timing: FL's LOINC table says documentation should be "six months or fewer before starting date of service".
- Policy conflicts across payers on LCD numbers (L34028 vs L34528) show the Medicare cross-references cannot be followed from the PDFs.

## Test cases

1. Moderate field loss, 28 degrees untaped and 42 taped (BCBSMA and Emblem approve; Florida Blue does not). 61-year-old with dermatochalasis, complaints of difficulty driving and reading, redundant skin resting on the lashes in photos. Superior visual field is 28 degrees untaped, 42 degrees taped (gain 14 degrees, 50%). BCBSMA: "limit upper field to within 30 degrees of fixation" is true, so the OR is satisfied even though the gain is below 20 degrees. Emblem: within 30 degrees at rest and a gain of at least 12 degrees: met. FL: "Before taping, the superior visual field is 20 degrees or less": 28 degrees is not, so not met. Cigna: loss of about 22-32 degrees from a 50-60 degree norm and a 50% gain probably meets the percent branch, but "20 degrees or 30%" is ambiguous.

2. Isolated brow ptosis with no visual-field test (Florida Blue approves; BCBSMA and Cigna do not). 58-year-old reports looking through the lashes and seeing the upper lid skin; photos show the eyebrow below the supraorbital rim; no visual-field test done. FL brow lift: BOTH criteria (documented complaint; photographs show eyebrow below the supraorbital rim): met (the NOTE about untested fields is ambiguous). BCBSMA: brow lift requires the field criterion: not met. Cigna: requires field loss corrected by brow taping and proof lid surgery alone cannot fix it: not met. Emblem: no brow criteria. UHC: not in the PDF.

3. Congenital ptosis in an 8-year-old (BCBSMA and Emblem approve; Cigna and Florida Blue do not clearly). Child with unilateral congenital ptosis, MRD1 1.5 mm, lid covering the pupil in photographs, optometrist notes risk of amblyopia; visual fields cannot be done. BCBSMA: age <= 9 AND the intervention is meant to relieve central-vision obstruction "severe enough to produce occlusion amblyopia" in the physician's judgment: met. Emblem: "Congenital ptosis with risk for amblyopia": met. Cigna: the infant/child pathway stops at seven years, and the adult path requires visual-field loss: not met. FL: ptosis repair needs field testing before and after taping and the exemption note only covers conditions that prevent testing "may include" severe tremors, macular degeneration and similar; a child's inability to perform perimetry is not named. UHC: InterQual applies only at >= 18, and nothing in the PDF says what applies below that.
