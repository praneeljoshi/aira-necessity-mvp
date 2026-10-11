# Florida Blue (BCBSFL) house template: batch 1 survey

Scope: 29 Florida Blue Medical Coverage Guidelines (MCGs) listed in `sourcing/analysis/bcbsfl/batch1.txt`. Ten were deep-profiled (JSON in `sourcing/analysis/profiles/`); all 29 were skimmed by heading and Position Statement. Quotes are from `sourcing/text/<treatment>/<stem>.txt` (pdftotext -layout). Section names are quoted as printed.

Deep-profiled (10): heart transplant (02-33000-23), liver transplant (02-40000-20), lymphedema/lipedema (02-12000-18), hip arthroscopy (02-20000-55), minimally invasive fusion (02-61000-36), cochlear implants (02-69000-03), SBRT (02-77371-02), site of service (08-00000-01), TMVR (02-33000-35), facet arthroplasty (02-20000-37, representative of the "investigational for all indications" type).

## 1. The house template

### 1.1 Section order (all 29 documents)

Every one of the 29 documents has the same eleven headed sections in the same order (checked by regex allowing a leading form feed; the only apparent miss, lymphedema's DESCRIPTION, is indented by one space):

1. Header block (first line is the policy number, e.g. `02-33000-23`), then `Original Effective Date:`, `Reviewed:`, `Revised:`, optionally `Next Review:`
2. `Subject:` (can wrap onto two lines)
3. All-caps disclaimer paragraph
4. A hyperlink "navigation bar" (Position Statement | Billing/Coding | Reimbursement | Program Exceptions | Definitions | Related Guidelines | Other | References | Updates)
5. `DESCRIPTION:` (background, often with "Summary and Analysis of Evidence")
6. `POSITION STATEMENT:` (the coverage rules)
7. `BILLING/CODING INFORMATION:` (CPT/HCPCS, sometimes ICD-10, sometimes a LOINC documentation table)
8. `REIMBURSEMENT INFORMATION:`
9. `PROGRAM EXCEPTIONS:`
10. `DEFINITIONS:`
11. `RELATED GUIDELINES:`, `OTHER:`, `REFERENCES:`, `COMMITTEE APPROVAL:`, `GUIDELINE UPDATE INFORMATION:`

The coverage rules are therefore always in one place (Position Statement). Exceptions to that: documentation requirements for mastectomy for gynecomastia sit in Reimbursement Information ("Required Documentation"), and MRI use guidance for lymphedema sits in Billing/Coding.

### 1.2 Fixed boilerplate (safe to strip or recognise)

Disclaimer, on every document, verbatim in all 29:

> "THIS MEDICAL COVERAGE GUIDELINE IS NOT AN AUTHORIZATION, CERTIFICATION, EXPLANATION OF BENEFITS, OR A GUARANTEE OF PAYMENT ... THIS MEDICAL COVERAGE GUIDELINE APPLIES TO ALL LINES OF BUSINESS UNLESS OTHERWISE NOTED IN THE PROGRAM EXCEPTIONS SECTION."

Other repeated text:

- Reimbursement Information is often just "Refer to section entitled POSITION STATEMENT." (19 of 29 files) or "None applicable." (transplants).
- Step therapy paragraph in Program Exceptions: "If this Medical Coverage Guideline contains a step therapy requirement, in compliance with Florida law 627.42393, members or providers may request a step therapy protocol exemption ..." It appears even in documents that contain no step therapy at all. Do not treat it as a criterion.
- Evidence rationale after an investigational ruling, e.g. "The evidence is insufficient to determine the effects of the technology on health outcomes." (or "...results in an improvement in the net health outcome", or "Data in published medical literature are inadequate to permit scientific conclusions on long-term and net health outcomes"). Three phrasings, same function.
- LOINC documentation tables (8 of 29 files), identical columns: code 28626-0 for physician history and physical, time frame modifier 18805-2, narrative "Include all data of the selected type that represents observations made six months or fewer before starting date of service for the claim". This is a documentation-currency rule (six months), not a medical-necessity criterion.
- Transplant guidelines (heart, pancreas, liver) open the Position Statement with a Certificate of Medical Necessity paragraph, identical wording, and close with the same Florida statute excerpts in OTHER.
- Committee line: "This Medical Coverage Guideline (MCG) was approved by the Florida Blue Medical Policy and Coverage Committee on 07/24/25."

### 1.3 How the Position Statement is written

The unit of coverage is one sentence of the form:

> "<Procedure> meets the definition of medical necessity when ALL of the following criteria are met:" (cochlear, SI fusion, carotid, phrenic, hip, PDGF) or "... for <populations>" (TEM, uterine artery embolization).

Counts across the 29 files: "meets the definition of medical necessity" 35 times in 16 files; "does not meet the definition of medical necessity" 3 files; "considered experimental or investigational" 23 times in 18 files. The three verdicts are therefore: meets medical necessity / does not meet / experimental or investigational. A fourth appears in cosmetic cases: "considered cosmetic in nature and is generally a contract exclusion" (gynecomastia), which is a benefit exclusion rather than a medical necessity finding.

Almost every position statement ends with a catch-all that inverts the criteria:

> "Total ankle replacement is considered experimental or investigational for all other indications."

> "Transanal endoscopic microsurgery is considered investigational or experimental for the treatment of rectal tumors that do not meet the criteria noted above."

A parser can model that as: covered only if one of the stated pathways is met; the catch-all adds no extra tests. SBRT (the only exception among those read) has no catch-all.

### 1.4 Numbering, nesting and logic words

There is no fixed numbering scheme. What appears:

- Plain bullets (majority). Items are joined by a trailing `, AND` / `; AND` / `, OR` on the line, not by the lead-in alone. Example (hip arthroscopy): "Hip pain with loss of function present for at least 6 months, AND / Radiographic and MRI findings are inconclusive, AND / ...". Final bullet has no connective.
- Arabic numbers 1.-4. under an "ALL of the following" lead-in (prostatic urethral lift: items 1-4 with "and" before the last).
- Arabic numbers with OR between them for alternative indications (heart transplant "Accepted indications ... 1. ... OR 2. ... OR 3.").
- Roman/lettered/numbered outline for the longest rule (lymphedema: "I. ... A. ... 1. ... a."; lipedema I-X). Lead-ins state the quantifier: "must satisfy 'A' and 'B'", "must satisfy at least one", "NONE of the following contraindications exist".
- Second-level bullets use a different glyph or only extra indentation.

Quantifier phrases found (file counts): "ALL of the following" 9 files, "ONE of the following" 6, "any of the following" 5, "at least one/two" 2. "k of n" is expressed as "including at least 2 of the following" (hip arthroscopy: 2 of 6 conservative measures) or "cluster of 3 provocative tests" (SI fusion: 3 of 6).

The quantifier belongs to the lead-in, but the connective is also repeated on the lines. They can disagree in small ways (see 4).

### 1.5 Thresholds and time

Thresholds are inline with units and comparison words in the bullet itself ("Maximal VO2 ... <10 mL/kg/min", "alpha angle >50°", "BMI ≤ 35kg/m2"). Durations are inline: "at least 6 months", "at least 12 weeks", "3 consecutive months", "within 1-year". The same concept may be expressed differently in the same document (hip: "3 months" and "12 weeks").

### 1.6 Codes

- `CPT Coding:` / `HCPCS Coding:` as a two-column list (code, descriptor, wrapped). Often prefaced by one sentence ("Codes may not be all inclusive.").
- Not-covered codes are marked with `(investigational)` or `(Investigational)` at the end of the descriptor (lysis of epidural adhesions, facet arthroplasty, fusion, TMVR). This marker is the only code-level "carve-out" and is inconsistent: it is present in some documents and absent in others that also rule codes investigational (e.g. bladder neck suspension, photocoagulation have none).
- `ICD-10 Diagnosis Codes That Support Medical Necessity:` appears in 9 of 29 files (plus TMVR has two separate headings: "for T-TEER and TTVR" and "for TMVR and TMViVR"). These are lists of codes, not mapped to criteria; they are "support", not a requirement.
- Codes can be absent: "There is no specific CPT or HCPCS code for breast ductal lavage or suction; unlisted code 19499 may be used" and BMP "Codes 20930 or 20931 are sometimes reported".
- Site of service guideline: ~240 lines of CPT defines which procedures the rule applies to; it is a scope list.

### 1.7 Lines of business and Program Exceptions

Program Exceptions does not carve out criteria. It is a fixed four-line block:

> "Federal Employee Program (FEP): Follow FEP guidelines. / State Account Organization (SAO): Follow SAO guidelines. / Medicare Advantage products: No National Coverage Determination (NCD) and/or Local Coverage Determination (LCD) were found at the time of the last guideline reviewed date."

or, where a CMS rule exists, "The following National Coverage Determination (NCD) was reviewed on the last guideline reviewed date: Heart Transplants (260.9)". So: FEP and SAO are out of scope for this document entirely (use their own); Medicare Advantage is told only that an NCD/LCD was looked at, not what it says. The text never says that Florida Blue's criteria are replaced for Medicare Advantage members; a checker cannot compute an MA variant from this text. Phrasing varies: "Medicare Advantage", "Medicare Advantage products", "Medicare Advantage Products", "Medicare Advantage products:" with the sentence on the next line. The only line-of-business branch inside criteria is the site-of-service one: "For Medicare Advantage Members, procedure not on Medicare's ASC list of covered procedures."

Program Exceptions is also where dated Florida law is cited (step therapy). The 08/21/23 history entry "Update to Program Exceptions section" appears in many documents (cochlear, fusion, total ankle), i.e. a template-wide edit.

### 1.8 Dates and revision tracking

- Header: `Original Effective Date`, `Reviewed`, `Revised`. Format MM/DD/YY. `Revised` is the effective date and is usually the 15th (or 1st) of a month after `Reviewed`. 
- Some headers have `Next Review:` (3 files): a date (SBRT "07/22/27", rhinitis "05/27/27") or "No Longer Scheduled for Routine Review (NLR)" (BMP).
- Oddities: site of service has Original Effective Date 10/01/25 later than Reviewed 07/24/25 and no Revised line. Phrenic stimulation has Revised 10/01/26, seven months after Reviewed 02/26/26. Several documents have Reviewed/Revised dates in 2026 and the facet guideline's committee date is 08/27/26.
- End of document: `GUIDELINE UPDATE INFORMATION:` is a two-column table: date, then free text such as "Scheduled review. Position statement maintained. Updated references.", "Annual CPT/HCPCS coding update. Added 63032; revised 27278, 27279.", "Revision: deleted bracing as a requirement for minimally invasive sacroiliac joint fusion." This is the only place that records what changed in criteria, and only in prose. History in the fusion guideline says bracing was deleted as a requirement in 2018, while the current Position Statement lists "Bracing" under required nonoperative treatment; the history is not a reliable account of the current text.

### 1.9 Definitions

`DEFINITIONS:` is an alphabetical glossary: "Term: definition." Many documents say "No guideline specific definitions apply." / "None." / "No guideline related definitions apply." (three wordings). Most entries are anatomy or disease glosses with no effect on criteria (liver transplant: "Hepatectomy: excision of all or part of the liver"). A few change meaning of criteria:

- Cochlear: "Severe sensorineural hearing impairment: a bilateral hearing threshold of 70-90 decibels (dB)." and "Profound ... 90 decibels and above." (criteria independently set 70 dB).
- Site of service: "Poorly controlled diabetes mellitus: ... Hemoglobin A1c (HbA1c) ≥ 9%" and "Poorly controlled hypertension: ... ≥ 140 mmHg and/or ... ≥ 90 mmHg".
- TMVR: STS and EuroSCORE (point to online calculators).
- Pancreas transplant: "Hypoglycemia unawareness", "Labile insulin-dependent diabetes".
- Some defining happens inside the Position Statement via parentheses, brackets and footnotes ("advanced is defined as Tönnis grade 2 or 3"; TMVR "*[Moderate to severe or severe mitral regurgitation (MR) may be determined by: ...]").

So a parser must read Definitions, but cannot assume a defined term in Definitions is the only meaning: criteria often redefine the term inline.

## 2. One line per document (skim of all 29)

Format: stem short name (pages). Sections: all eleven in the standard order unless stated. Shape. Rough covered count.

| # | Document (pages) | Position Statement shape | Covered indications |
|---|---|---|---|
| 1 | Photocoagulation of macular drusen 01-92000-21 (7 pp) | Not-covered only: one sentence "considered experimental or investigational"; no codes exist | 0 |
| 2 | PDGF and platelet-rich plasma 02-10000-09 (8) | Criteria (ALL lists) for becaplermin: diabetic neuropathic ulcer (3 criteria), pressure ulcer (5); then investigational lists for other ulcers, PRP wound (1), PRP orthopedic (5 primary + 8 adjunctive uses) | 2 |
| 3 | Ductal lavage and suction collection 02-10000-14 (4) | Not-covered only | 0 |
| 4 | Mastectomy for gynecomastia 02-12000-14 (7) | One ALL list (4 bullets: post adolescent male, over 18, glandular not fatty tissue, not due to obesity/drugs/endocrine); cosmetic exclusion list; liposuction alone investigational; documentation in Reimbursement section | 1 |
| 5 | Lymphedema and lipedema surgery 02-12000-18 (16) | Table: 4 procedures x Roman-numeral criteria (I-III), lipedema I-X; ARM investigational | 4 |
| 6 | Unicondylar interpositional spacer 02-20000-26 (5) | Not-covered only | 0 |
| 7 | Bone morphogenetic protein 02-20000-32 (9) | Three alternative indications (OR), each needing "autograft not feasible*"; footnote; does-not-meet list | 3 |
| 8 | Facet arthroplasty 02-20000-37 (6) | Not-covered only | 0 |
| 9 | Hip arthroscopy / open repair 02-20000-55 (8) | Five pathways with ALL lists (diagnostic, operative with 8 OR indications, FAI with 7 criteria, microfracture, and exemptions for biopsy/infection/trauma) | ~5 pathways, ~11 indications |
| 10 | Surgical ablation for chronic rhinitis 02-31000-03 (6) | Not-covered only (header has Next Review) | 0 |
| 11 | Heart transplant 02-33000-23 (8) | CMN note; Adult accepted (3) and probable (3); pediatric accepted (2 with 3 and 7 sub-bullets); retransplant; contraindication list (advisory) | ~10 |
| 12 | Extracranial carotid angioplasty/stenting 02-33000-28 (7) | One ALL list (stenosis 50-99%, symptoms in 120 days, anatomic contraindication to endarterectomy); investigational for others and for angioplasty without stent | 1 |
| 13 | Transcatheter mitral valve repair 02-33000-35 (9) | Five device-specific paragraphs with footnotes carrying risk thresholds | 5 |
| 14 | Allogeneic pancreas transplant 02-40000-17 (8) | CMN note; three transplant types in one sentence each (after kidney; with kidney for ESRD; alone with 2 alternatives); retransplant; advisory contraindications | 4 |
| 15 | Liver transplant / liver-kidney 02-40000-20 (12) | CMN note; lettered A-G etiology list, HCC with ONE of 3 staging systems; PCLD, hilar CCA, hepatoblastoma; retransplant (5 reasons); combined; does-not-meet and investigational lists | ~30 |
| 16 | RF and microwave ablation of liver tumors 02-40000-23 (14) | Three procedures (RFA HCC, RFA metastases, microwave) each with inoperability plus size rule; investigational list | 4 |
| 17 | Transanal endoscopic microsurgery 02-45000-01 (5) | Two sentences: rectal adenomas; T1 adenocarcinoma with 4 criteria (ALL); other tumors investigational | 2 |
| 18 | Transvaginal RF bladder neck suspension 02-50000-16 (6) | Not-covered only (two technologies named) | 0 |
| 19 | Temporary prostatic urethral stents 02-54000-21 (9) | Prostatic urethral lift: numbered 1-4 ALL criteria; iTind investigational | 1 |
| 20 | Uterine artery occlusion 02-56000-26 (9) | Two indications (fibroids, postpartum hemorrhage) + one repeat embolization; others investigational; laparoscopic occlusion investigational | 3 |
| 21 | Intradiscal electrothermal annuloplasty 02-61000-20 (15) | Not-covered only (annuloplasty; basivertebral RF ablation) | 0 |
| 22 | Lysis of epidural adhesions 02-61000-28 (10) | Not-covered only; investigational tags beside five CPT codes | 0 |
| 23 | Phrenic nerve stimulation 02-61000-33 (5) | Two pathways: C3 quadriplegia / central alveolar hypoventilation; motor neuron disease with 3-item ALL list; "does not meet" list (2); investigational list (COPD, hiccups, infants) | 2 |
| 24 | Minimally invasive fusion techniques 02-61000-36 (23) | AxiaLIF investigational; open SI fusion any of 4; minimally invasive SI fusion 9-item ALL with sub-ALL lists; posterior SI and annular repair investigational | 2 pathways (5 rulings) |
| 25 | Cochlear implants 02-69000-03 (12) | Standard ALL (4), hybrid ALL (4 with nested thresholds), sequencing note, programming, replacement, upgrade | 4 |
| 26 | Stereotactic body radiotherapy 02-77371-02 (14) | No criteria: whitelist of 8 indications and 13 cancer sites for previously irradiated fields; no catch-all | ~21 listed |
| 27 | Total ankle replacement 02-99221-15 (7) | One sentence: skeletally mature, pain limiting ADLs, 6 months conservative treatment, ONE of 4, AND NO evidence of 6; revision rule | 1 (+revision) |
| 28 | Microwave ablation other than liver 02-99221-18 (6) | Pointer to liver guideline; lung tumors: unresectable and single tumor ≤3 cm; others investigational | 1 |
| 29 | Site of service review 08-00000-01 (17) | Any of ~25 conditions justifies hospital outpatient setting; any of 4 ASC-access reasons; comparative effectiveness (cost) analysis; applicable to ~200 CPTs | 1 rule (non-clinical) |

Shape counts (by my reading of the 29): 8 are purely not-covered (rows 1, 3, 6, 8, 10, 18, 21, 22). 11 have one or two real criteria blocks plus an investigational catch-all (4, 12, 17, 19, 20, 23, 27, 28, 16, 7, 2). 5 have multi-pathway criteria (5, 9, 13, 24, 25). 4 are indication whitelists or tiered lists with little testing logic (11, 14, 15, 26). 1 is a non-clinical site-of-service rule (29).

## 3. Mostly "investigational" lists versus real criteria

- Purely investigational: photocoagulation of drusen, ductal lavage, unicondylar spacer, facet arthroplasty, surgical ablation for rhinitis, transvaginal RF bladder neck suspension, intradiscal electrothermal annuloplasty (and basivertebral nerve ablation), lysis of epidural adhesions. For these a checker should return NOT_MET (not covered) without evaluating the chart. The wording is uniform: "is considered experimental or investigational for all indications."
- Real criteria with an investigational tail (the dominant form): total ankle, TEM, carotid stenting, uterine artery embolization, microwave non-liver, prostatic urethral lift, phrenic stimulation, hip arthroscopy, SI fusion, TMVR.
- Indication whitelists, not tests: SBRT; liver transplant etiologies; heart/pancreas transplant indications.
- Non-clinical: site of service (where, not whether).
- Mixed documents: PDGF/PRP, BMP, fusion, RFA contain both criteria and investigational halves for different products.

## 4. Variations from the template

- Section content varies, section order does not.
- Lymphedema: table layout with procedure names in a left column; description starts with a leading space.
- SBRT: Position Statement heading preceded by a form feed; header has `Next Review`; no catch-all investigational sentence.
- Header: `Next Review` in 3 of 29; site of service has no `Revised` and an Original Effective Date after Reviewed.
- Subject lines wrap (lymphedema, rhinitis).
- Bullet glyph differs by document: U+F0B7 (hip, heart, pancreas, carotid, TEM, uterine, fusion, cochlear, mastectomy, PDGF, BMP, RFA, microwave, site of service) versus U+2022 (liver, TMVR, phrenic, total ankle, SBRT; fusion has both).
- ICD-10 lists present in 9 of 29.
- Connectives: "AND" / "and" / ";" / none; "OR" at end of last bullet of a group; "and/or" used in TMVR and SI fusion.
- Reimbursement Information is sometimes substantive: gynecomastia documentation, cochlear replacement coverage, total ankle ("Reimbursement for the revision or replacement of a total ankle device is made only if the procedure was initially allowed.").
- Program Exceptions: gynecomastia lists two contradictory Medicare Advantage statements ("The following National Coverage Determinations (NCDs) was reviewed ... (L38914)" then "No National Coverage Determination (NCD) was found") and labels an LCD number as an NCD.
- Definitions wording: three variants of "none".
- Tiered recommendations: heart transplant "Accepted" vs "Probable" indications.
- Criteria in footnotes: BMP (*NOTE), TMVR (*, **, brackets), hip (** Tonnis scale).

## 5. Extraction hazards in the pdftotext output

- Bullets are private-use glyphs; strip or map U+F0B7 and U+2022 and 'o'. Second-level bullets are sometimes only indentation.
- Form feed (`\f`) page breaks: 11 of 201 major headings are immediately preceded by `\f`, defeating `^HEADING:` regexes. Lists continue across pages without any marker (heart transplant pediatric list continues on the next page).
- No running headers, footers or page numbers (checked on first/last line of each page), so none to strip; the navigation bar after the disclaimer is noise that looks like headings.
- Wrapped lines: bullets and definitions wrap with hanging indents; join lines before parsing connectives.
- Two-column table in lymphedema; indent varies per block; list lettering continues incorrectly (comorbidity items lettered D-L under C in the lymphovenous bypass block) and criteria letters mentioned in lead-ins ("must satisfy 'A', 'B', and 'C'") do not always match the lettered items.
- Footnote markers (`*`, `**`, `[ ]`) with the footnote text separated from the bullet; asterisk reused for different footnotes (TMVR).
- Description and References dominate size (fusion 23 pages: criteria ~80 lines of 982). Parse only from POSITION STATEMENT to BILLING/CODING.
- Evidence summaries in Description and (for site of service) inside the Position Statement contain "requires", "must", numbers that look like criteria.
- Typos: "cholangiocarcioma", "mestatic", "Lipidema", "Reonstructive", "Tonnis"/"Tönnis".
- Statutes in OTHER (transplants) are long and look like policy text.
- LOINC table: rows wrap and repeat the same sentence; not criteria.

## 6. What a parser can rely on, and what it must not

Can rely on:

- Section headings and their order (11 sections; allow optional `\f` and leading spaces).
- Coverage rules only in POSITION STATEMENT (with documented exceptions in Reimbursement / Billing).
- "meets the definition of medical necessity" starts a covered statement; "does not meet" and "experimental or investigational" are not-covered statements; "all other situations/indications" is a catch-all.
- Lead-in quantifiers (ALL / ONE / any / at least N of the following) for the list that follows.
- Dates in `MM/DD/YY` in header and update table; policy number is the first line.
- FEP and SAO text: always "Follow ... guidelines".

Must not rely on:

- Bullet glyph, indentation or numbering as nesting depth.
- Trailing AND/OR on lines as the only quantifier (it can disagree with, or be missing from, the lead-in).
- Letters or numbers cited in lead-ins matching actual items.
- Program Exceptions as a source of different criteria for Medicare Advantage; it only names the NCD/LCD.
- ICD-10 lists as criteria; they are "support" lists.
- `(investigational)` on code lines being complete.
- Definitions being the only definition (criteria define terms inline and thresholds can conflict).
- Update history agreeing with the current text.
- The Position Statement being all criteria: it can include submission instructions (CMN), notes about benefits ("subject to the member's benefit terms"), brand-name lists (investigational devices), advisory lists ("subject to the judgment of the transplant center") and evidence prose.
- A Position Statement always existing as one block (SBRT heading attachment, lymphedema as a table).

## 7. Implications for a criteria tree

- Most documents map to a top-level any over pathways, each an all of leaves, with a "none of" for contraindications. Hip arthroscopy and cochlear are the best fits; lymphedema fits but needs careful extraction.
- Eight documents are not-covered-only and need a fixed "not covered" outcome rather than leaves.
- Advisory lists (transplant contraindications) and tiered indications ('accepted' / 'probable') are not hard NOT nodes.
- Site of service is not a clinical question, needs facility facts (ASC availability, contract language), and its cost-based second step cannot be decided from a chart.
- Several leaves need measurements (VO2, volumetry, audiometry, STS score) most charts will not carry as discrete values; expect INSUFFICIENT.
