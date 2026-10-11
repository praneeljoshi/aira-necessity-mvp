# Florida Blue (BCBSFL) house template: batch 0 survey (29 documents)

Source: `sourcing/text/<treatment>/<stem>.txt` (pdftotext -layout) for the 29 documents in `sourcing/analysis/bcbsfl/batch0.txt`.
Ten documents were deep-profiled (JSON in `sourcing/analysis/profiles/`, all validated); the other 19 were read at heading level plus their full Position Statement.
Quotes are short and come from the document named; MCG numbers (e.g. 02-99221-17) identify the document.

Short version: every Florida Blue "Medical Coverage Guideline" (MCG) is the same 15-part shell. The only part that carries coverage logic is POSITION STATEMENT, and
it is written as prose with bullets, not as a numbered criteria set. Of 29 documents, 8 are one-paragraph "experimental or investigational for all indications"
statements, about 5 are catalogues or indication lists, and only about 10 contain nested criteria with real thresholds.

---

## 1. The template (what is identical in all 29)

### 1.1 Section order

Every document has this order (28 of 29 show all 11 headings as separate lines; the exception is 02-20000-22, see section 4):

| # | Block | Notes |
|---|---|---|
| 0 | Header lines: `<MCG number>`, `Original Effective Date: mm/dd/yy`, `Reviewed: mm/dd/yy`, `Revised: mm/dd/yy` | first 4 lines of the text |
| 1 | `Subject: <title>` | |
| 2 | All-caps disclaimer (see 1.2) | wraps differently per document |
| 3 | Navigation bar: "Position Statement / Billing/Coding / Reimbursement / Program Exceptions / Definitions / Related Guidelines / Other / References / Updates" | a hyperlink strip; becomes 3 lines of column-spaced words |
| 4 | `DESCRIPTION:` | background, FDA status, and "Summary and Analysis of Evidence" (25 of 29) |
| 5 | `POSITION STATEMENT:` | the only coverage logic |
| 6 | `BILLING/CODING INFORMATION:` with sub-blocks `CPT Coding:`, `HCPCS Coding:`, `ICD-10 Diagnosis Codes That Support Medical Necessity ...:`, `LOINC Codes:` | each sub-block optional |
| 7 | `REIMBURSEMENT INFORMATION:` | nearly always "Refer to section entitled POSITION STATEMENT." or "None applicable." |
| 8 | `PROGRAM EXCEPTIONS:` | FEP, SAO, Medicare Advantage lines, then step-therapy boilerplate |
| 9 | `DEFINITIONS:` | `Term: definition` per paragraph |
| 10 | `RELATED GUIDELINES:` | other MCG titles with numbers |
| 11 | `OTHER:` | statutes, synonyms, brand names, or "None applicable." |
| 12 | `REFERENCES:` | numbered bibliography; often half the file |
| 13 | `COMMITTEE APPROVAL:` | "approved by the Florida Blue Medical Policy and Coverage Committee on <date>" |
| 14 | `GUIDELINE UPDATE INFORMATION:` | dated change log, oldest first |

### 1.2 Fixed boilerplate (quote-for-quote identical, ignore for parsing)

- Disclaimer, e.g. 02-99221-17: "THIS MEDICAL COVERAGE GUIDELINE IS NOT AN AUTHORIZATION, CERTIFICATION, EXPLANATION OF BENEFITS, OR A GUARANTEE OF PAYMENT ... THIS MEDICAL COVERAGE GUIDELINE APPLIES TO ALL LINES OF BUSINESS UNLESS OTHERWISE NOTED IN THE PROGRAM EXCEPTIONS SECTION." Line breaks differ by document (27 of 29 contain the phrase "ALL LINES OF BUSINESS" on one line; in 2 it is wrapped).
- Step-therapy paragraph at the end of PROGRAM EXCEPTIONS (28 of 29; absent in 02-20000-36): "If this Medical Coverage Guideline contains a step therapy requirement, in compliance with Florida law 627.42393, members or providers may request a step therapy protocol exemption to this requirement if based on medical necessity." None of the 29 contains a step-therapy requirement, so this paragraph is noise.
- Reimbursement: "Refer to section entitled POSITION STATEMENT." (02-99221-17, 02-61000-35 uses "sections" plural; 02-56000-24: "Refer to section entitled POSITION STATEMENT and BILLING/CODING INFORMATION.").
- Committee approval sentence (02-99221-17): "This Medical Coverage Guideline (MCG) was approved by the Florida Blue Medical Policy and Coverage Committee on 05/28/26." Older wording in 02-56000-24: "approved by the BCBSF Medical Policy and Coverage Committee"; 02-61000-32 omits "Policy and": "Florida Blue Medical Coverage Committee".
- Empty sections: "None applicable." (most) or "None." (02-46000-01 OTHER), "None applicable" without a period (02-99221-17).

### 1.3 Position Statement phrasing

Three stock sentences carry nearly all the meaning:

| Phrase | Documents (of 29) | Meaning |
|---|---|---|
| "meets the definition of medical necessity" (also "meet") | 20 | covered, when the stated conditions hold |
| "is considered experimental or investigational" | 23 | not covered; always followed by a rationale sentence |
| "The evidence is insufficient to determine the effects of the technology on health outcomes." / "There is insufficient clinical evidence ..." | 14 / 7 | rationale, boilerplate, not testable |
| "does not meet the definition of medical necessity" | 6 | used for cosmetic or out-of-scope items, e.g. 02-10000-08, 02-12000-01, 02-12000-17, 02-10000-13 |

The document does NOT use a "not medically necessary" status for anything except cosmetic: everything unproven is "experimental or investigational".

---

## 2. How criteria are written

### 2.1 Structure and numbering

- There is no consistent numbering scheme. Real criteria use, depending on the author, any of:
  - plain bullets (glyphs lost or turned into spaces in pdftotext) with `AND` / `OR` at the end of lines (02-10000-08, 02-61000-24, 02-33000-33);
  - numbered levels `1.` / `A.` / bullet / en-dash: only orthognathic surgery 02-12000-17 ("Skeletal deformities, either A or B: A. One or more of the following skeletal deformities exists:");
  - roman numerals `I. II. III.`: only in nerve-allograft criteria inside 02-12000-01 ("when the criteria in one of the following categories I, II, or III are met");
  - statute-style `(1)` to `(6)` subsections: 02-38241-01 (autologous HCT, mirrors Florida Administrative Code 59B).
- Maximum nesting seen: 4 levels (02-12000-17, 02-38241-01 multiple-sclerosis block). Typical real criteria: 2 levels (a lead-in line plus bullets, sometimes one nested "ONE of the following").
- Nesting is signalled only by indentation. Bullet glyphs differ by level ("•", "o", "▪", "−", "-", "a.", "b."), and pdftotext does not preserve them reliably.

### 2.2 "And" / "or" / "one of the following"

The lead-in line declares the logic; trailing `AND` / `OR` on bullets repeat it, inconsistently.

| Pattern | Example | Reads as |
|---|---|---|
| "when ALL of the following criteria are met:" + bullets ending "AND" | 02-10000-08 (actinic keratosis): "when ALL of the following criteria are met: There are >=10 actinic keratoses ... AND Documented treatment failure using topical 5-fluorouracil ..., unless contraindicated." | all |
| "for ONE of the following situations:" + bullets ending ";" / "; OR" | 02-10000-08 acne surgery | any |
| "meets the definition of medical necessity for ONE of the following indications:" and OR only before the last bullet | 02-33000-22 (AAA): only the third bullet ends "OR" | any |
| "when ALL of the following are met" / "when all of the following are met" / "when both of the following are met" | 02-20000-22; 02-33000-25 | all (capitalisation of ALL/all not meaningful) |
| "defined as any one of the following:" | 02-20000-22 (high risk for fusion failure) | any |
| "for any of the following:" | 03-59800-01 (abortion): "Abortion may be eligible for coverage for any of the following:" | any (and "may") |
| a bulleted list with no lead-in at all and no connectors | 02-77371-01 | any (implied) |
| lower-case "and" inside prose | 02-12000-01: "... and the functional impairment is refractory to 3 months of continuous medical therapy ... and the procedure is expected to restore or improve the functional impairment." | all, but inside one sentence |
| mixed AND/OR at the same level | 02-99221-13 renal cell carcinoma: "when either of the following criteria is met: [A]; AND [B]; OR [C]." | ambiguous: (A AND B) OR C vs A AND (B OR C), and "either of" implies two options but three are given |
| "ONE of the following" nested in an ALL | 02-61000-24 Parkinson disease: "ALL of the following: A good response to levodopa; AND Motor complications ...; AND ONE of the following: a. A minimum score of 30 points ... OR b. Parkinson disease for at least 4 years." | clean nested tree |
| implicit AND (list with no connectors) | 02-33000-25 destination therapy (NYHA class, LVEF, then an OR bullet) | all; inner bullet has its own OR |

Conclusion: the lead-in sentence, not the line-ending connectors, is the reliable logic marker. The connectors at line ends are redundant at best and wrong at worst (see 02-38241-01 MS block, 02-99221-13 RCC).

### 2.3 Pathways ("meets ... for the following indications")

When one document covers several indications the Position Statement is a series of paragraphs, each of the form
"<Procedure> meets the definition of medical necessity <for/when> <indication and conditions>", followed by a final catch-all:
"... is considered experimental or investigational for all other indications." (02-33000-33, 02-61000-24, 02-40000-19, 02-65000-18). Only 02-20000-22 (bone growth stimulator) has no catch-all.
Sub-sections appear as unmarked plain lines (e.g. "Deep Brain Stimulation", "Responsive Neurostimulation", "Revision/Replacement" in 02-61000-24; "Ventricular Assist Devices" / "Total Artificial Hearts" in 02-33000-25; "Intracranial Arterial Disease" / "Extracranial Vertebral Artery Disease" in 02-61000-35).

### 2.4 Exclusions

No separate "exclusions" or "contraindications" section. Exclusions are one of: (a) an inline negative leaf ("Have no evidence of intracranial hemorrhage or arterial dissection", 02-61000-35), (b) a "None of the following ... are present" list (systemic sclerosis in 02-38241-01), (c) a "Potential contraindications ... (subject to the judgment of the transplant center) include:" list that is advisory not binding (02-40000-19), (d) a separate sentence declaring the use cosmetic or investigational.

### 2.5 Repeat / continuation / replacement

Rare. Handled in a sentence: 02-61000-24 "Revision or replacement of an implanted neurostimulator meets the definition of medical necessity when all of the criteria above ... are met, the device is not functioning, and is no longer under warranty or cannot be repaired."; 02-40000-19 "A small bowel/liver retransplant ... meets the definition of medical necessity after a failed primary ..."; 02-99221-13 "twelve months should have elapsed before a repeat ablation"; 02-10000-13 "If the member fails to respond to an initial course of laser therapy ... additional therapy does not meet the definition of medical necessity."; 02-56000-24 four ART cycles with review beyond.

### 2.6 What kinds of leaf appear

Diagnosis names; numeric thresholds with units (mm, cm, %, mL/min, points, days); named scales (UPDRS, NYHA, EDSS, Modified Rodnan, NIHSS, ASPECTS; usually with a cutoff, sometimes without: 02-61000-35); durations ("3 months of continuous medical therapy", "45 of the last 60 days"); prior-therapy failure ("failed 2 or more appropriate antiepileptic medications at therapeutic doses"); age bands; documentation lists (radiographs, photographs); device/FDA status ("FDA approved"); and a few non-chart leaves (benefit available, transplant centre is part of BMT CTN, committee/medical director review).

---

## 3. Codes, lines of business, dates, definitions

### 3.1 Codes

- BILLING/CODING lists CPT in all 29, HCPCS in about 13, ICD-10 "Diagnosis Codes That Support Medical Necessity" in 11 (01-91000-10, 02-10000-08, 02-10000-13, 02-20000-22, 02-33000-22, 02-46000-01, 02-54000-14, 02-61000-24, 02-61000-35, 02-65000-18, 03-59800-01), and a "LOINC Codes" documentation table in 8 (02-12000-01 has two). (Regex counts in `survey.json` over-count ICD-10 because the update log says "ICD-10 codes added" even when no table exists, e.g. 02-77371-01, 02-38241-01.)
- Codes are listed, not derived from criteria. Mapping happens only sometimes, and then as ICD-10 groups headed by CPT: 02-10000-08 "ICD-10 Diagnosis Codes That Support Medical Necessity for CPT codes 15780, 15781 ... : D48.5, L57.0" and "... for CPT codes 10040, 15788 & 15792: L70.0 - L70.9 Acne"; 03-59800-01 per-CPT diagnosis lists ("... Medical Necessity for 59820: O02.1"); 02-61000-35 "for codes 61635, 61645". Elsewhere a single ICD-10 list is not tied to any pathway (02-61000-24).
- Codes carry coverage status inline: "(Investigational)" or "(non-covered)" at the end of the descriptor (02-99221-17, 02-61000-35, 02-20000-36, 02-56000-24, 02-12000-17, 02-61000-32). Code-level carve-outs also appear: 02-10000-08 "(not covered for acne treatment)" on ultraviolet-light codes. Tag and Position Statement can disagree: 02-61000-35 tags 61630, 61640-61642 "(Investigational)" but not 61635 (stent with angioplasty) though the statement calls intracranial angioplasty with or without stenting for atherosclerotic disease investigational.
- Statements like "Codes may not be all inclusive." (02-77371-01), "(not all inclusive)" (02-56000-24) mean the code list cannot be the coverage rule.
- The LOINC table is useful for an evidence checker: it lists document types the payer may require, e.g. 02-33000-22: "The following information may be required documentation to support medical necessity: Physician history and physical, attending physician progress notes, plan of treatment, and laboratory studies." with a time-frame modifier "Include all data of the selected type that represents observations made six months or fewer before starting date of service for the claim". The text is identical on every row.

### 3.2 Program Exceptions and lines of business

Fixed three-line pattern in all 29:

1. "Federal Employee Program (FEP): Follow FEP guidelines."
2. "State Account Organization (SAO): Follow SAO guidelines."
3. "Medicare Advantage products: ..." in one of two forms:
   - "No National Coverage Determination (NCD) and/or Local Coverage Determination (LCD) was found at the time of the last guideline reviewed date." (15 of 29: 02-12000-17, 02-20000-30, 02-20000-36, 02-20000-41, 02-30000-12, 02-33000-22, 02-33000-33, 02-40000-22, 02-40000-26, 02-46000-01, 02-61000-06, 02-65000-18, 02-77371-01, 02-99221-13, 02-99221-17);
   - "The following National Coverage Determination (NCD) was reviewed on the last guideline reviewed date: <title> (<number>) located at cms.gov." (14 of 29, e.g. 03-59800-01 "Abortion, (140.1)"; 02-61000-24 NCDs 160.7 and 160.24; 02-56000-24 cites Medicare Benefit Policy Manual 20.1).

What this does and does not do: it never restates a different criteria set for Medicare Advantage, FEP or SAO. FEP and SAO are pure delegation (these members are governed by someone else's rules, the Florida Blue criteria do not apply). Medicare Advantage is only an acknowledgement that a CMS NCD/LCD was looked at; it does not say the NCD overrides the position statement, nor which prevails. So the exceptions carve out lines of business as a whole, not individual criteria, and the checker must treat "line of business is FEP/SAO" as "this guideline does not decide". Grammar varies ("was/were found", "review/reviewed date", "Medicare Advantage Products" capital P), so match with fuzzy patterns.

Benefit dependence is stated in notes at the top of the Position Statement, not in Program Exceptions: 02-56000-24 "Coverage for infertility is subject to the member's benefit terms, limitations and maximums."; 02-12000-01 "Some plans may exclude coverage for reconstructive surgery and cosmetic surgery."; 03-59800-01 "Refer to member's/subscriber's contract benefits. Coverage is subject to the state law limitations."; 02-12000-17 "*NOTE: Per Florida statute: ...". The disclaimer already says benefits are determined by the group contract, so any "covered" outcome from this guideline is only "medically necessary", never "covered".

### 3.3 Dates and revision tracking

- Header: `Original Effective Date`, `Reviewed`, `Revised` (mm/dd/yy, two-digit year). `Reviewed` equals the committee approval date in 28 of 29. `Revised` is the 15th of the next month in almost every case (e.g. 02-99221-17 reviewed 05/28/26, revised 06/15/26): treat `Revised` as the effective date of this version.
- Exceptions: 02-38241-01 has Reviewed 01/22/26, Revised 09/15/26 and committee approval 08/27/26 (header review date is stale; the later revision reflects a position-statement change: log row "Revision: Position statements and references updated."); 02-56000-24 has Revised 10/01/26 that is a quarterly CPT/HCPCS update after a 05/28/26 review, so Revised is not always a criteria change.
- `GUIDELINE UPDATE INFORMATION` is a table (date, description), 13 to 100 rows (100 in 02-12000-01). Typical rows: "Annual review: Position statement maintained; references updated." and "Review; no change in position statement. Updated references." The first row is "New Medical Coverage Guideline." (or "reformatted"). Some logs hold information found nowhere else: 02-77371-01 row 03/15/21 "Deleted Karnofsky Performance Scale" explains why the current text says only "good performance status".
- Nothing marks superseded wording; no redlines or strikethrough in these 29.

### 3.4 Definitions

DEFINITIONS is `Term: definition` per paragraph (some docs use a hyphen: "Alberta Stroke Program Early CT (ASPECTs) score- https://..." in 02-61000-35, where the definition is only a URL). Most definitions are glossary (anatomy, procedure descriptions) and carry no coverage meaning. A few definitions change a criterion:
- 02-61000-24 "Disabling, medically unresponsive tremor: tremor causes significant limitation in daily activities and inadequate control by maximal dosage of medication for at least 3 months before implant." (adds a 3-month duration the Position Statement never states);
- 02-33000-25 "Destination therapy: the use of a ventricular assist device (VAD) for long-term, permanent support in those who are not candidates for transplant.";
- 03-59800-01 "Missed abortion: an empty gestational sac ... prior to completion of 20 weeks 0 days gestation.";
- 02-99221-13 "Unresectable: a property of a tumor where it is unable to be removed surgically.".
The Position Statement does not flag defined terms (no bold or italics survive), so a parser must test every defined term against the statement text.

---

## 4. Variations from the template

1. Heading glued to text: 02-20000-22 (EBGS): the DESCRIPTION's last sentence runs into the heading in extraction, "...healing of nonunion fractures.POSITION STATEMENT:". Position of the heading line is therefore unreliable; match "POSITION STATEMENT:" anywhere in a line.
2. Missing lead-in: 02-77371-01 (SRS). The Position Statement's first list is bare diagnoses (Acoustic neuromas ... Uveal melanoma) with no "meets the definition" sentence. Rendering the PDF page confirms the sentence is not on the page. Only the second list has a lead-in ("SRS to treat a previously irradiated field meets the definition of medical necessity for the following indications:").
3. Prefixed instruction blocks: 02-38241-01 and 02-40000-19 begin POSITION STATEMENT with a "Certificate of Medical Necessity" submission instruction (steps 1-3: "Click the link Bone Marrow/Stem Cell Transplant under Certificates of Medical Necessity ...") before any criteria.
4. Position Statement contains other things: a "Summary of Evidence:" of four study paragraphs and example lists (02-12000-01, 320 lines); a note limiting scope ("Note: This policy does not address cranial or spinal procedures." 02-20000-30; "Note: For Stereotactic Body Radiotherapy, refer to ... 02-77371-02."); a statute preamble (02-12000-17).
5. Criteria outside the Position Statement: 02-12000-17 DESCRIPTION quotes AAOMS indications A-D with different numbers ("two or more standard deviations") than the Position Statement; 02-20000-22 DESCRIPTION mentions "younger than age 60" (AANS/CNS) which is not a criterion; 02-33000-25 OTHER lists FDA label indications per device (e.g. Heart Assist 5 Pediatric: "BSA >= 0.7 m2 and < 1.5 m2") that read like criteria but are labelled illustrative; 02-38241-01 OTHER excerpts Florida Statute 627.4236 that justifies the first list.
6. Benefit-conditional guidelines: 02-56000-24 "If the benefit for coverage for infertility treatment is available and there is documentation of infertility for at least one year's duration, the following indications meet the definition of medical necessity".
7. "May" rather than "meets": 03-59800-01 "Abortion may be eligible for coverage for any of the following".
8. No step-therapy paragraph: 02-20000-36.
9. Footnote carrying criteria: 02-61000-35 "*(Flow-diverting stents are indicated for ... a size of 10 mm or more and a neck diameter of 4 mm or more ...)".
10. Individual-consideration language where criteria would be: 02-12000-01 "Congenital anomalies ... are reviewed for individual consideration"; "Fat grafting ... as a stand-alone procedure requires Medical Director review"; 02-38241-01 "the appropriateness of bone marrow transplantation may be determined on a case by case basis".
11. Stale cross-references: 02-12000-01 RELATED GUIDELINES lists "Orthognathic Surgery, 02-12000-15" and "Prophylactic Mastectomy, 02-12000-15" (orthognathic is 02-12000-17) and cites Dermabrasion as "02-12000-08" while its own number is 02-10000-08; 02-12000-17 lists TMJ as "02/20000-12". MCG numbers in prose are not a reliable join key; titles are better.

---

## 5. Real criteria vs "investigational / not medically necessary" lists

Counts below are over the 29 batch-0 documents.

**A. Blanket "experimental or investigational" (no coverage path), 8:**
02-20000-30 computer-assisted navigation (orthopedic), 02-20000-36 interspinous/interlaminar devices, 02-20000-41 surgery for occipital neuralgia/headache, 02-30000-12 bronchial thermoplasty, 02-40000-26 irreversible electroporation, 02-61000-06 occipital nerve stimulation, 02-61000-32 percutaneous discectomy, 02-99221-17 subtalar arthroereisis.
Quote: "Bronchial thermoplasty for the treatment of asthma and all other indications is considered experimental or investigational." (02-30000-12). One to three sentences each. The only variation is the list of named variants (02-61000-32 names automated discectomy, laser, Deuk Laser, nucleoplasty, ...; 02-20000-41 lists 7 intervention types).

**B. Narrow positive carve-out inside an otherwise investigational policy, 6:**
02-65000-18 canaloplasty for POAG (viscocanalostomy investigational), 02-46000-01 HRA for suspicious lesion/dysplasia (screening investigational), 01-91000-10 RFA for Barrett's with HGD, or LGD confirmed "by two pathologists" (cryoablation and non-dysplastic Barrett's investigational), 02-33000-22 EVAR (4 size/rupture indications; non-FDA stents and smaller aneurysms investigational), 02-54000-14 whole-gland prostate cryoablation (initial or salvage), 02-40000-22 cryoablation of liver tumors ("non-resectable, OR ... poor candidate for surgery").

**C. Real criteria sets with thresholds or nesting, about 10:**
02-12000-17 orthognathic, 02-61000-24 DBS/RNS, 02-99221-13 RFA of solid tumors, 02-33000-25 VAD/TAH, 02-61000-35 intracranial endovascular, 02-33000-33 transcatheter pulmonary valve, 02-40000-19 small bowel/liver/multivisceral transplant, 02-20000-22 bone growth stimulator, 02-10000-13 excimer laser, 02-10000-08 dermabrasion/peel/acne surgery.

**D. Indication lists (membership is the rule), 3:**
02-77371-01 SRS (12 + 9 diagnoses), 02-38241-01 autologous HCT (about 40 named indications, 8 with nested criteria; statute-defined; 3 tiers: covered, covered only inside a clinical trial, covered at BMT CTN centres), 03-59800-01 abortion (4 situations, state-law qualified).

**E. Catalogue / router, benefit-dependent, 2:**
02-12000-01 reconstructive vs cosmetic (an "examples" encyclopedia that mostly says "Refer to ..." with only brachioplasty/lifts, keloids and nerve allograft having criteria), 02-56000-24 infertility (benefit gate, 1-year duration, 4 ART cycles, 6 investigational techniques).

---

## 6. One line per document

Key: PS shape: **B** = blanket not-covered; **B+** = narrow covered carve-out then not covered; **C** = nested criteria (all/any); **L** = indication list; **P** = pathways (several indications, each with own criteria); **R** = router/catalogue; **D** = delegated. Codes: C=CPT, H=HCPCS, I=ICD-10 table, L=LOINC table. All have the 11 standard headings plus header, subject, disclaimer, nav bar unless noted; every document has the same PE trio (FEP, SAO, MA).

| MCG | Title | PS shape | Rough covered indications | Codes | Notes |
|---|---|---|---|---|---|
| 01-91000-10 | Endoscopic RFA / cryosurgical ablation (Barrett's) | B+ | 2 (HGD; LGD confirmed by 2 pathologists) | C I | 14-line PS; cryoablation investigational |
| 02-10000-08 | Dermabrasion, chemical peel, salabrasion, acne surgery | P, C | 3 (AK with >=10 lesions + failed 5-FU/imiquimod; acne peel after failed antibiotic therapy; acne surgery ONE of 3) | C H I | ICD mapped per CPT group; cosmetic lists |
| 02-10000-13 | Excimer laser (dermatology) | P | 3 (localized plaque psoriasis mild-moderate after 2-month trial; moderate-severe; vitiligo after 2-month trial) | C I L | "NOTE" re no further courses after non-response |
| 02-12000-01 | Reconstructive vs cosmetic surgery | R | dozens of example procedures; ~3 with criteria | C H L | 320-line PS; includes evidence summary; LOINC x2 |
| 02-12000-17 | Orthognathic surgery | C (3-part ALL, 4 deep) | 1 procedure family + cleft orthodontics | C | statute notes; real mm thresholds |
| 02-20000-22 | Invasive electrical bone growth stimulator | P | 2 (nonunion appendicular; spinal fusion adjunct high risk) | C H I | PS heading glued to DESCRIPTION; no "all other" statement; ICD list uses suffix shorthand |
| 02-20000-30 | Computer-assisted navigation (orthopedic) | B | 0 | C H | "does not address cranial or spinal" |
| 02-20000-36 | Interspinous / interlaminar devices | B | 0 | C H | 19 pages, 240-line DESCRIPTION; no step-therapy paragraph |
| 02-20000-41 | Surgery for occipital neuralgia / headache | B | 0 | C | lists 7 intervention types |
| 02-30000-12 | Bronchial thermoplasty | B | 0 | C | 3-line PS |
| 02-33000-22 | Endovascular stent grafts for AAA | B+ (any of 4) | 4 (>5 cm; 4-5 cm +0.5 cm in 6 months; twice normal infrarenal; ruptured) | C I L | thresholds; OR only before last bullet |
| 02-33000-25 | Total artificial hearts / VADs | P, C | ~6 (VAD bridge, post-cardiotomy, destination therapy; percutaneous VAD x3; RVAD; TAH) | C H | NYHA, LVEF, 45 of 60 days; OTHER = FDA label lists |
| 02-33000-33 | Transcatheter pulmonary valve | P | 2 sets (4 alternatives; Melody/Ensemble: conduit >=16 mm + dysfunction) | C | gradient >=35 mm Hg |
| 02-38241-01 | Autologous hematopoietic cell transplantation | L + P | ~40 named (8 with sub-criteria incl. SSc and MS) | C H L | statute-driven; CMN instruction block first; deepest nesting |
| 02-40000-19 | Small bowel / liver / multivisceral transplant | C (6-item ALL) | 1 + retransplant | C H | contraindications "subject to the judgment of the transplant center" |
| 02-40000-22 | Cryoablation of liver tumors | C (any of 2) | 1 | C L | 2-bullet PS; "criteria are met: ... OR" |
| 02-40000-26 | Irreversible electroporation (IRE) | B | 0 | C | 4 non-covered tags |
| 02-46000-01 | High-resolution anoscopy | B+ | 1 (suspicious lesion OR dysplasia on prior cytology/biopsy) | C I | screening investigational |
| 02-54000-14 | Whole-gland cryoablation of prostate | B+ (any of 2) | 1 (initial or salvage after radiotherapy; T1/T2, FDA device) | C I | |
| 02-56000-24 | Infertility | R (benefit-gated list) | ~6 services + 4 ART cycles | C H | 1-year duration; 6 investigational techniques; revised 10/01/26 (code update) |
| 02-61000-06 | Occipital nerve stimulation | B | 0 | C | |
| 02-61000-24 | Deep brain stimulation / responsive neurostimulation | P | ~6 (thalamic uni/bilateral; GPi/STN Parkinson; dystonia age >=7; RNS; revision) | C H I L | UPDRS 30; 3 seizures/month; definitions add 3-month duration |
| 02-61000-32 | Automated percutaneous / laser discectomy | B | 0 | C H | 6 code tags |
| 02-61000-35 | Endovascular procedures, intracranial arterial | P | 3 (stent for wide-neck aneurysm; flow diverter; mechanical embolectomy ALL of 5) | C I | footnote criteria; scale names without cutoffs |
| 02-65000-18 | Viscocanalostomy / canaloplasty | B+ | 1 (canaloplasty for POAG) | C I | two procedures, one covered |
| 02-77371-01 | Stereotactic radiosurgery, intracranial | L | 12 + 9 (re-irradiation) | C H L | list 1 has no lead-in sentence (source defect); Karnofsky removed 2021 |
| 02-99221-13 | RFA of solid tumors (other than liver) | P | 5 | C L | mixed AND/OR in RCC; liver delegated to 02-40000-23 |
| 02-99221-17 | Subtalar arthroereisis | B | 0 | C H | one sentence; all codes "(Investigational)" |
| 03-59800-01 | Abortion | L (state-law qualified) | 4 situations | C H I | "may be eligible"; MA lists NCD 140.1; CPT-specific ICD lists |

---

## 7. Extraction hazards seen in pdftotext -layout output

1. Navigation-bar text between disclaimer and DESCRIPTION appears as column-spaced words ("Position  Billing/Coding  Reimbursement  Program ...") on 3 lines. Looks like a heading list; drop it.
2. Heading detection must be tolerant: headings are all-caps with colon, but can be indented one space (` COMMITTEE APPROVAL:`) and in one document are glued to the preceding sentence (02-20000-22). Do not require the heading to start the line.
3. Page breaks are form-feed characters only. There are no running headers or footers or page numbers in these PDFs, so lists are not interrupted by header noise, but a list can break mid-item across a form feed, and indentation can shift by one space on the next page (02-12000-01, 02-38241-01).
4. Indentation is the only hierarchy signal. The bullet glyph is a different character at different levels or disappears (02-99221-13); 'o', '▪', '−', '-', '•' mix in one list (02-38241-01). A bare "AND" or "OR" can sit alone at column 0 between groups (02-38241-01 MS block).
5. Line-end connectors ("; AND", "; OR", "OR") are partly redundant, sometimes contradict the lead-in ("either of the following" with three bullets), and the last list item may carry no connector at all.
6. Descriptor wrapping: CPT/HCPCS/ICD rows wrap to 2-8 lines (02-33000-22 has 8-line descriptors); the code is only on the first line. Descriptor text can contain "(Investigational)" on the last wrapped line.
7. ICD-10 tables: ranges with en-dash and inconsistent spacing ("G20.A1- G20.C", "O03.0 – O03.2"), codes with missing characters ("M8008XK, P"), 7th-character suffix shorthand ("S52.001G,J;" and "(G suffix only)"), repeated rows (02-20000-22 "M84.40XK, P" twice), and trailing semicolons.
8. LOINC tables repeat the same 4-line modifier narrative on every row; they inflate repeated-line counts and are not criteria.
9. DESCRIPTION and Position Statement can contain study summaries with numbers (e.g. "BMI preferably <30kg/m2" in 02-12000-01 Summary of Evidence; "younger than age 60" in 02-20000-22 DESCRIPTION): numbers near the word "criteria" are not necessarily criteria.
10. Footnote asterisks carry criteria (02-61000-35); parenthetical e.g. lists carry thresholds ("e.g., wide-neck aneurysm of 4 mm or more, or sack-to-neck ratio less than 2:1").
11. Sub-headings inside the Position Statement are unmarked lines (see 2.3).
12. Ligature and unicode: "≥", "≤", "<" without spaces ("<2.2"), "µ", "−" (minus sign, not hyphen), curly quotes and apostrophes; typos in drug and policy names; missing spaces ("GynecomastiaRefer").
13. Date format is mm/dd/yy; the Update table loses indentation partway through in some documents (02-99221-17 rows from 06/15/22).
14. Two columns/tables do not occur in Position Statements here; only coding tables are tabular. (Reading order is therefore safe for criteria text.)

---

## 8. What a parser can rely on, and what it must not rely on

**Can rely on**
- The 11 headings and their order, as uppercase tokens with a trailing colon (search anywhere in the line, one document glues one to text).
- That coverage logic lives in POSITION STATEMENT, bounded by the next "BILLING/CODING INFORMATION:" heading (or "REIMBURSEMENT INFORMATION:"). Section boundaries are well enough defined to extract it. Exception: criteria also hide in DEFINITIONS (3-month duration) and, rarely, footnotes or a Note before the list.
- Stock sentences: "meets the definition of medical necessity", "is considered experimental or investigational", "does not meet the definition of medical necessity". Use them as clause boundaries and as status labels. An "experimental or investigational for all other indications" sentence ends the pathways.
- Capitalised ALL / ONE / any one of the following as the logic of the list that follows (the lead-in sentence, not the line-end connectors).
- Header dates in mm/dd/yy and the three-field header; `Revised` = effective version date; committee date = `Reviewed`.
- PROGRAM EXCEPTIONS is boilerplate: FEP and SAO "Follow ... guidelines" in all 29; the step-therapy paragraph can be dropped.
- Numeric thresholds are written with units next to the number in the same sentence.
- LOINC tables define the document types the payer wants (a ready-made evidence checklist) with a six-month window.

**Must not rely on**
- Any numbering style, bullet glyph, or nesting level; indentation must be reconstructed and verified, and lead-in sentences have to be parsed to assign logic.
- The trailing AND / OR on bullets (inconsistent, sometimes contradicting).
- The presence of a lead-in sentence (02-77371-01 has none) or of a catch-all "all other indications" (02-20000-22 has none).
- That "meets the definition of medical necessity" means covered: benefit terms, contract exclusions, member FEP/SAO status, and state law can override (see 3.2); the guideline says so itself in the disclaimer.
- Codes as the rule: they are "not all inclusive", sometimes tagged contrary to the statement, and ICD-10 lists are mapped to CPT groups only in a few documents. Do not infer criteria from codes or vice versa.
- The Description and Summary and Analysis of Evidence (evidence, not criteria; may state different numbers).
- Defined terms being flagged in the criteria; test each defined term against the text.
- Vague clinical judgments having a test: "good performance status", "optimal medical management", "not a surgical candidate", "appropriate candidate", "individual consideration", "medical director review", "case by case" have no objective definition and must resolve to INSUFFICIENT or a human.
- MCG cross-reference numbers (wrong in 02-12000-01 and 02-12000-17).
- That "Reviewed" and "Revised" always move together (02-38241-01) or that "Revised" is a position change (02-56000-24).
- OTHER being empty: it contains statutes (02-12000-17, 02-38241-01), FDA label indications (02-33000-25) and product names, all non-binding or mandate-bearing text a human may need.

---

## 9. Profiles written (10)

`sourcing/analysis/profiles/` (stems as in batch0.txt):
bcbsfl-02-99221-17-subtalar-arthroereisis (blanket investigational, fit 1),
bcbsfl-02-77371-01-stereotactic-radiosurgery-intracranial (indication list with missing lead-in, fit 2),
bcbsfl-02-12000-17-orthognathic-surgery (3-part ALL with mm thresholds, fit 3),
bcbsfl-02-61000-24-deep-brain-stimulation-and-responsive-neurostimula (pathways with scales, fit 3),
bcbsfl-02-99221-13-radiofrequency-ablation-of-solid-tumors-other-than (pathways, ambiguous AND/OR, fit 3),
bcbsfl-02-61000-35-endovascular-procedures-for-intracranial-arterial (three body-system pathways, fit 3),
bcbsfl-02-33000-25-total-artificial-hearts-and-implantable-ventricula (device pathways, fit 3),
bcbsfl-02-56000-24-infertility (benefit-gated, cycle limits, fit 3),
bcbsfl-02-38241-01-autologous-hematopoietic-cell-transplantation (about 40 indications, deepest nesting, fit 4),
bcbsfl-02-12000-01-reconstructive-surgery-cosmetic-surgery (catalogue, fit 5).
