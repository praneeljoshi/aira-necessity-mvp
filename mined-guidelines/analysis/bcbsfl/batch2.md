# Florida Blue (BCBSFL) house template, batch 2 survey

Scope: the 29 documents in `sourcing/analysis/bcbsfl/batch2.txt` (all BCBSFL "Medical Coverage Guidelines", MCGs). Ten were profiled in full
(`sourcing/analysis/profiles/`), all 29 were skimmed (headings plus Position Statement). Text is `pdftotext -layout` output in
`sourcing/text/<treatment>/<stem>.txt`; page numbers below come from form feeds in that text and match the PDFs.
Quotes are short and copied from the text; "p." is the PDF page. Where I infer something the document does not say, I say so.

Full profiles (fit score 1 = easy, 5 = needs new constructs):

| Profile | Why chosen | Score |
|---|---|---|
| `bcbsfl-02-10000-03-mohs-micrographic-surgery` | skin; five pathways, site x histology x host matrix | 3 |
| `bcbsfl-02-10000-11-bio-engineered-skin-...` | skin; 39 pages, product lookup plus ~257-name denylist | 3 |
| `bcbsfl-02-10000-19-breast-ductoscopy` | breast; whole policy is "investigational for all indications" | 1 |
| `bcbsfl-02-38240-01-allogeneic-hematopoietic-cell-transplantation` | heme; 20 pages, state-mandated numbered subsections, case-by-case clause | 4 |
| `bcbsfl-02-55900-01-gender-affirmation-surgery` | GU/gender; same A-G list repeated for six procedure groups | 2 |
| `bcbsfl-02-61000-29-nerve-block-injections` | pain/neuro; seven indications, mixed AND/OR, caps in Reimbursement | 3 |
| `bcbsfl-03-59000-16-in-utero-intrauterine-fetal-surgery` | fetal; gestational-age thresholds, exclusion list | 2 |
| `bcbsfl-02-65000-15-endothelial-keratoplasty-and-corneal-collagen-cros` | eye; two procedures in one policy, per-CPT ICD tables | 3 |
| `bcbsfl-76JEWFS1H2QN1TDP2IH-transmyocardial-revascularization-tmr` | cardiac; clean all-of with LVEF and 21-day window | 2 |
| `bcbsfl-02-20000-34-manipulation-under-anesthesia` | ortho; nested all-of three deep, joint-specific durations | 2 |

---

## 1. The house template

### 1.1 Section order (identical in all 29 documents)

I checked every document for the eleven headings below. All 29 contain all eleven, in this order, with no exceptions
(an "order_ok" test over line positions). Headings are upper case, end with a colon, and sit alone on a line.

| # | Heading as printed | Typical content |
|---|---|---|
| 0 | (header block, no heading) | guideline number, `Original Effective Date`, `Reviewed`, `Revised`, `Subject` |
| 0 | (disclaimer + nav bar, no heading) | fixed paragraph; a 3-row navigation table flattened to text |
| 1 | `DESCRIPTION:` | what the procedure is; often a literature digest headed `Summary and Analysis of Evidence:` |
| 2 | `POSITION STATEMENT:` | the coverage rules (the only place criteria live, see 1.3) |
| 3 | `BILLING/CODING INFORMATION:` | `CPT Coding:`, `HCPCS Coding:`, `ICD-10 Diagnosis Codes That Support Medical Necessity:` |
| 4 | `REIMBURSEMENT INFORMATION:` | usually a pointer; sometimes frequency limits, replacement rules, a LOINC documentation table |
| 5 | `PROGRAM EXCEPTIONS:` | FEP / SAO / Medicare Advantage / step-therapy paragraph |
| 6 | `DEFINITIONS:` | alphabetical `Term: definition` lines, or "None applicable." |
| 7 | `RELATED GUIDELINES:` | other MCG titles with their numbers, or "None applicable." |
| 8 | `OTHER:` | statute excerpts, alternate names, referral-letter checklist, or "None applicable." |
| 9 | `REFERENCES:` | numbered citations (1 to ~150, up to ~360 lines) |
| 10 | `COMMITTEE APPROVAL:` | one sentence with a date |
| 11 | `GUIDELINE UPDATE INFORMATION:` | dated change log, oldest first |

Heading variants a parser must tolerate: the Position Statement heading is `POSITION STATEMENT` with no colon in the cryoablation
document (`bcbsfl-02-99221-12`, line 106); `BILLING/CODING INFORMATION:` is sometimes followed directly by prose instead of a code table (ductoscopy, p.1: "There is no
specific CPT or HCPCS code for breast ductoscopy; unlisted code 19499 may be used."); the nav bar prints in three different layouts.

### 1.2 Fixed boilerplate (verbatim, appears in every document)

Disclaimer, directly under the header (p.1 of Mohs; identical in all 29 apart from line wrapping):

> THIS MEDICAL COVERAGE GUIDELINE IS NOT AN AUTHORIZATION, CERTIFICATION, EXPLANATION OF BENEFITS, OR A GUARANTEE OF PAYMENT, NOR DOES IT SUBSTITUTE FOR OR CONSTITUTE MEDICAL ADVICE. ALL MEDICAL DECISIONS ARE SOLELY THE RESPONSIBILITY OF THE PATIENT AND PHYSICIAN. BENEFITS ARE DETERMINED BY THE GROUP CONTRACT, MEMBER BENEFIT BOOKLET, AND/OR INDIVIDUAL SUBSCRIBER CERTIFICATE IN EFFECT AT THE TIME SERVICES WERE RENDERED. THIS MEDICAL COVERAGE GUIDELINE APPLIES TO ALL LINES OF BUSINESS UNLESS OTHERWISE NOTED IN THE PROGRAM EXCEPTIONS SECTION.

The last sentence is the only line-of-business statement outside Program Exceptions. It also means every Position Statement is
conditional on benefits: the contract decides first.

Nav bar (text of the three rows): `Position Statement | Billing/Coding | Reimbursement | Program Exceptions | Definitions | Related Guidelines` then `Other | References | Updates`. Note the nav bar says "Updates" and
the section is `GUIDELINE UPDATE INFORMATION:`.

Program Exceptions, three fixed first lines (the FEP and SAO lines are verbatim in all 29; the Medicare Advantage line varies, see 1.5):

> Federal Employee Program (FEP): Follow FEP guidelines.
> State Account Organization (SAO): Follow SAO guidelines.
> Medicare Advantage products: No National Coverage Determination (NCD) and/or Local Coverage Determination (LCD) were found at the time of the last guideline reviewed date.

Step-therapy paragraph, last item of Program Exceptions (28 of 29; absent from the January 2025 Mohs revision):

> If this Medical Coverage Guideline contains a step therapy requirement, in compliance with Florida law 627.42393, members or providers may request a step therapy protocol exemption to this requirement if based on medical necessity. The process for requesting a protocol exemption can be found at Coverage Protocol Exemption Request.

It appears even in documents with no step therapy and no medical-necessity criteria at all (ductoscopy, p.2). Ductoscopy repeats it a second
time inside BILLING/CODING (`627.42393` occurs twice in that file).

Reimbursement default (15 of 29): "Refer to section entitled POSITION STATEMENT." Others: "None applicable." (4), "None." (1), "Refer to sections entitled POSITION STATEMENT and PROGRAM EXCEPTIONS." (VNS), plus 6 that carry real content (Mohs, bio-skin, trigger point, nerve block, neurolysis, BAHA; see 1.3).

Committee line: "This Medical Coverage Guideline (MCG) was approved by the Florida Blue Medical Policy and Coverage Committee on 01/23/25." One document uses `&` for `and` (EK/CXL, `Medical Policy & Coverage Committee`).

### 1.3 Where criteria live

Almost always only in `POSITION STATEMENT:`. Exceptions I found in the 29:

- Frequency caps and per-product limits sit in REIMBURSEMENT INFORMATION, not the Position Statement: nerve blocks ("**64400: Total number of injections is limited to four (4) injections in six (6) months.", p.7), neurolysis ("limited to two (2) facet neurolysis procedures per region, every 12 months"), bio-engineered skin ("Apligraf® is limited to five (5) applications per ulcer", p.28), trigger point injections (also repeated in the PS bullet "Injections do not exceed 4 in 30 days or 6 in 6 months, per anatomic location").
- Bone-conduction hearing aids put replacement rules in Reimbursement: "may be covered for any one of the following: When the existing device cannot be repaired; OR ...".
- A "Certificate of Medical Necessity" submission block opens the Position Statement of six transplant documents (lung, heart-lung, allogeneic HCT, small bowel, islet, kidney). It is process, with its own `1. 2. 3.` steps, not criteria.
- Documentation requests ("The following information may be required documentation to support medical necessity: ...") come with a LOINC table in 9 of 29 documents, in three different places: end of the Position Statement (MUA, EK/CXL), inside REIMBURSEMENT INFORMATION (Mohs, trigger point, nerve block, neurolysis), inside BILLING/CODING (HCT, cryoablation, in-utero). All rows use time-frame code 18805-2 ("Include all data of the selected type that represents observations made six months or fewer before starting date of service for the claim.").
- The Description is not criteria, but contains the evidence digest the criteria are built on, and in a few documents a definition the criteria silently rely on (gender dysphoria per DSM-5-TR, `bcbsfl-02-55900-01`, p.1).

### 1.4 How criteria are written

Lead sentence idioms (these are very regular and good anchors):

- Positive: `<service> meets the definition of medical necessity when|for|in ...` (Mohs; TMR; MUA).
- Positive with a conjunction count: `when ALL of the following [criteria] are met` (ACI, trigger point, TMR, gender, neurolysis "all of the following are met") or `for ONE of the following indications:` (Mohs, bio-engineered skin, prophylactic breast reconstruction ADM) or `at least ONE of the following` (nerve block plantar fasciitis).
- Negative: `does not meet the definition of medical necessity` (Mohs exclusion list, small bowel "who are able to tolerate TPN", collagen dressing "wounds with heavy exudate").
- Not covered as unproven: `is considered experimental or investigational` + a rationale sentence. This is the dominant negative form.
- Rationale sentences are formulaic and carry no rule: "The evidence is insufficient to determine the effects of the technology on health outcomes." / "There is insufficient clinical evidence to permit conclusions on net health outcomes." / "Data in published medical literature are inadequate to permit scientific conclusions on long-term and net health outcomes."
- Catch-all: `... for all other indications` / `in all other situations` (lung transplant: "considered experimental or investigational in all other situations") / `including but not limited to`. Coverage is therefore closed-world by default: anything not matched by the covered paragraphs is investigational.

Numbering, nesting and connectors (observed forms):

| Form | Example | Documents |
|---|---|---|
| Unlettered bullets, each a leaf, with trailing `AND` / `OR` (or `;`) | TMR: "Documentation of reversible ischemia; / Left ventricular ejection fraction greater than 30%; / ... ; AND" | TMR, trigger point, ACI (no tokens), in-utero, cryoablation |
| Capital letters `A.`-`G.` | Mohs A-E pathways; gender A-G requirements | Mohs, gender |
| Arabic numerals `1.`-`6.` | HCT: "1. Upon the recommendation of the Bone Marrow Transplant Panel ..." | HCT only in batch 2 (statute-derived) |
| Indication headings as plain lines ending in a colon | "Complex regional pain syndrome (CRPS):", "Pancreatic cancer:" | nerve block |
| Second level `o`, third level `-` / U+2212 | MUA shoulder: three levels (•, o, −) | MUA, neurolysis, EK/CXL, lap RFA |

Depth never exceeded three. The counts of "k of n" are almost always k = 1 ("ONE of the following") or all-of; the only explicit numeric k I saw is "at least ONE of the following".

Connector conventions:

- `ALL of the following ... AND` : upper-case `AND` at the end of each bullet except the last (TMR bullet 4: "...within the last 21 days; AND"). The `AND` is often missing on some bullets (trigger point: "Conservative therapy ... fails or is not feasible" has none; ACI bullets have none).
- `OR` in upper case at the end of a bullet in an any-of list (prophylactic mastectomy: "Lobular carcinoma in situ; OR / A known BRCA1 or BRCA2 mutation; OR ..."; BAHA conditions; breast ADM).
- Lower-case `and/or` and `or` inside bullets (small bowel, MUA "Analgesics and/or corticosteroids, unless contraindicated, AND"), so case does not separate structural from inline connectors.
- Mixed AND/OR at one level with no parentheses, relying on semicolons and indentation. Worst case, nerve block "Ischemic limb pain": "Intractable pain at rest, OR / Non-healing ulcers; AND / Severe peripheral artery disease, AND / Patient is not a candidate for revascularization, OR / Previous revascularization has failed".
- The final `AND` on the last item of an OR sub-list binds to the whole sub-list (EK/CXL cross-linking: "A decrease ≥0.1 mm ... , AND / Conservative treatment such as spectacle correction ... has failed"), which is only visible from indentation, not from the connectors.
- Conditional bullets inside an ALL list: ACI says "meets the definition of medical necessity when ALL of the following are met" and then lists both "Adolescents should be skeletally mature ..." and "Adults should be too young to be considered an appropriate candidate for total knee arthroplasty ..."; they are population-conditional, not simultaneously required.
- Soft verbs inside criteria lists: "should", "is recommended", "may be defined as": prophylactic mastectomy "High risk of breast cancer may be defined as one or more of the following" and "It is recommended that candidates ... consider undergoing counseling"; in-utero MMC "should be counseled in a nondirective fashion" is the last bullet of an AND list but is advice. Format gives no way to tell requirements from advice.

Thresholds are written inline with unit words and sometimes symbols: "at least 50% reduction", "≥0.1 mm", "greater than 30%", "less than 26 weeks", "4 in 30 days or 6 in 6 months, per anatomic location". Durations: "at least 6 weeks", "3 months", "one-month period", "within the last 21 days".

### 1.5 Program Exceptions and lines of business

What the section does and does not do:

- FEP and SAO lines are a pure hand-off: "Follow FEP guidelines." / "Follow SAO guidelines." Criteria in the document are therefore not the criteria for those members; the document never says what they are. A checker needs the member's line of business before it can use any Position Statement.
- Medicare Advantage is a list of CMS sources that were "reviewed" (NCD/LCD/Article numbers with the host site), e.g. Mohs: "Local Coverage Determination (LCD): Mohs Micrographic Surgery (MMS) (L33689); and Local Coverage Article: Billing and Coding ... (A57767) located at fcso.com." or "No National Coverage Determination (NCD) and/or Local Coverage Determination (LCD) were found at the time of the last guideline reviewed date." The text never says that the CMS rule overrides the MCG. That is the implication (Medicare rules govern MA), but it is not stated. In 14 of 29 documents the MA line says no NCD/LCD was found, so the MCG criteria apply to MA members by default (an inference, not stated).
- No Program Exception restates criteria or alters a threshold. No codes are carved out by line of business. Codes carve out only by an inline tag: `(Investigational)` (11 of 29; 364 occurrences in bio-engineered skin alone), `(investigational if performed for treatment of chronic pelvic/perineal pain)` (nerve block), `(non-covered)` (HCT's S2150).
- The label wording varies: `Medicare Advantage products:` (20), `Medicare Advantage:` (5), `Medicare Advantage Products:` (4). Sometimes a line break follows the colon (EK/CXL, TMR, BAHA).
- Geographic split of the host: some link to `fcso.com` (First Coast Service Options, the Florida MAC), others `cms.gov`, one `cgsmedicare.com`.
- Other limitations of scope are written into the Position Statement: gender surgery "Coverage may be governed by state or federal mandates"; EK/CXL "Refer to member contract. Refractive surgery and related complications may be excluded by some contracts."
- In transplant documents, state law reaches into criteria: HCT cites "Chapter 59-B of the Florida Administrative Code [(1) – (6)]" and reproduces Florida Statute 627.4236, 765.523, 627.64197, 627.65736, 641.31075 under OTHER (the lung document prints 641.31077 for the same paragraph; the numbers disagree between files, so do not match on statute number).

### 1.6 Dates and revision tracking

Header lines (all 29 documents):

```
02-10000-03
Original Effective Date: 05/15/02
Reviewed: 01/23/25
Revised: 02/15/25
Subject: Mohs Micrographic Surgery
```

Regularities I verified across all 29:

- `Reviewed` always equals the date in COMMITTEE APPROVAL (29 of 29).
- `Revised` equals the last dated entry of GUIDELINE UPDATE INFORMATION in 27 of 29. Exceptions: frenectomy (`Revised: 03/15/24` but the log ends `03/15/25  Review: Position statements maintained; references updated.`, so the header Revised is stale, and it is earlier than `Reviewed: 02/27/25`) and in-utero (log last entry written `08/15/2025`, four-digit year, matching 08/15/25 in the header).
- `Revised` is often a coding-only change after the committee date, e.g. nerve block `Reviewed: 01/22/26`, `Revised: 10/01/26`, last log line "10/01/26  ICD-10 coding update. Codes M72.20-M72.22 added; code M72.2 deleted." So `Revised` does not mean the Position Statement changed; the log says what changed. The same for bio-engineered skin (Revised 10/01/26) and gender (Revised 10/01/26: "ICD-10 coding update").
- `Reviewed`/`Revised` can both be in the 2026 calendar year and later than a 2025 date (current date in this run is 2026-10-09; the latest `Revised` seen is 10/01/26), so a document may be dated "in the future" relative to a stale copy of the policy; compare to what the library file says, not to today.
- Log entries: date at left in `MM/DD/YY` (one `MM/DD/YYYY`), a keyword (`Review`, `Scheduled review`, `Annual review`, `Revision`, `Annual CPT/HCPCS coding update`, `Update to Program Exceptions section`, `New Medical Coverage Guideline`) then a semicolon list of what changed ("Position statements maintained; references updated"). Entries wrap with a hanging indent. Counts range from 10 to 77 entries. A parser can use the keywords to tell whether a revision touched criteria ("Revised position statement") or only codes/references.
- The guideline number on line 1 (`02-10000-03`) is a stable key (family `01`, `02`, `03`, `09` seen; other documents cite each other by it under RELATED GUIDELINES, e.g. "Neurolysis/Ablation, 02-61000-34"). It is truncated in the TMR file (`02-33000-1`) and the PDF filename carries a random token instead of the number (`bcbsfl-76JEWFS1H2QN1TDP2IH-...`), so the number cannot always be taken from the filename.
- The log is also a source of historical criteria. Example, in-utero p.9: "05/15/06 ... Deleted statement; refer coverage requests for in utero fetal surgery to Medical Director for approval", yet the current Position Statement begins "NOTE: Refer coverage requests for in utero fetal surgery to the Medical Director for approval." with no later entry reinstating it. The log and the current text can disagree.

### 1.7 Definitions

- Format: `Term: definition` lines, mostly alphabetical, sometimes with blank lines between entries (EK/CXL, TMR) and sometimes without. Empty-case phrasing: "No guideline specific definitions apply." (8), "None applicable." (2).
- 19 of 29 have entries. Most are medical glossary text lifted from NCI or a dictionary and do not change the criteria (Mohs: "Basal Cell Carcinoma: Cancer that begins in the lower part of the epidermis"). A few are load-bearing:
  - TMR: "Class III angina: Canadian Cardiovascular Society (CCS) functional classification for angina: Marked limitation of ordinary activity. Angina when walking one or two blocks on the level..." (the Position Statement uses "class III or IV angina").
  - Bio-engineered skin: "Nonhealing- less than a 20% decrease in wound area with standard wound care for at least 2 weeks." (used as the definition of nonhealing diabetic ulcers).
  - In-utero: "Oligohydramnios: ... the presence of less than 300ml of amniotic fluid at term." (the criterion says "Progressive oligohydramnios").
  - Frenectomy distinguishes partial and complete ankyloglossia.
- Terms that decide coverage but are not defined: Mohs "healthy or immunocompromised", "aggressive"; nerve block "failed conservative treatment"; gender "persistent", "well controlled"; HCT "appropriate candidate". Definitions are defined for medical terms, not for the policy's own judgment words.
- Terms are not marked in the Position Statement text (no italics or bold survive extraction), so a parser cannot tell which words in a criterion have a Definitions entry without matching the glossary.

---

## 2. Variations from the template

1. Position Statement opens with process text rather than criteria: Certificate of Medical Necessity block (6 transplant docs); "NOTE: Mohs micrographic surgery requires the physician to function in two separate, but distinct capacities" (Mohs); "NOTE: Coverage for gender affirmation surgery is subject to the member’s benefit terms" (gender); "NOTE: This guideline is not applicable to cryosurgical ablation of solid tumors of the liver or prostate" and "This guideline is limited to treatment in adults (age 18 years and older)" (cryoablation, which therefore has a scope statement as the first criterion).
2. Description carries evidence, sometimes 60-180 lines, in 12+ docs (lung, nerve block, in-utero, MUA, ductoscopy, bio-engineered skin, VNS, neurolysis...). The Position Statement may start well past line 100 (lung line 88, in-utero line 205, ACI line 178).
3. Multiple services in one document: bio-engineered skin (7 service groups), EK + CXL + topography + refractive exclusions, HCT (cord blood collection, tandem transplant, RIC), nerve blocks (7 indications), gender surgery (6 procedure groups), neurolysis (facet + trigeminal).
4. Truncated or odd headers: no Subject on one line, Subject wrapped across two lines (frenectomy, HCT, EK/CXL, bio-skin), guideline number clipped (TMR), stale `Revised` (frenectomy).
5. Reimbursement section holding substantive rules (see 1.3), Program Exceptions with extra NCD paragraphs and CGS vs FCSO hosts, and BILLING/CODING that includes LOINC (in-utero) or a prose-only coding statement (ductoscopy).
6. Billing/ICD shape: no ICD-10 table at all (HCT, MUA, in-utero, ductoscopy, lung, kidney...), one flat ICD table, or several keyed to a CPT code (EK/CXL: "ICD-10 Diagnosis Codes That Support Medical Necessity For Endothelial Keratoplasty (CPT code 65756, 65757)" and a second table "For CPT Code 0402T"). Code tags `(Investigational)` appear inside the code table in 11 docs.
7. Decision structure beyond any/all: reimbursement-style caps, product-list lookup (bio-skin), state-law cross-references and trial gating (HCT), device-specific numeric thresholds (BAHA: 45/55/65 dB by named device), "contraindications (subject to the judgment of the transplant center)" lists (lung, heart-lung, small bowel, kidney).
8. Typos that matter to a text parser: "individuals" misspelled "inividuals" (islet), "may be considered meets the definition" (in-utero MMC), "documentation of failure conservative medical management" (MUA), stray "multiple" glued to a heading sentence (HCT), "ICD-10 ... That Support edical Necessity" (frenectomy), "Z87.8901- Z87.893" vs the update note "Z89.8901 - Z87.893" (gender).

---

## 3. Real criteria vs "investigational/not medically necessary" lists

Classification of the 29 by what the Position Statement does (details in section 4):

- Blanket investigational, nothing to evaluate (4): breast ductoscopy, thumb basal joint arthroscopy, partial left ventriculectomy / surgical ventricular restoration, plugs for fistula repair. Position Statement is 2-7 lines. Always NOT MET on any chart ("considered experimental or investigational for all indications").
- Single narrow covered indication, everything else investigational (6): islet transplantation (autologous only, adjunct to pancreatectomy for chronic pancreatitis), frenectomy (feeding difficulty or articulation), VNS (medically refractory seizures), kidney transplant (ESRD diagnosis), endovascular stent graft (3 conditions), prophylactic mastectomy. These look like criteria but are one-clause rules; the checker's work is the diagnosis match.
- Mostly investigational by weight (3): bio-engineered skin (~257 named products investigational vs ~30 product-indication pairs covered), VNS (9 named conditions + stimulation variants investigational vs 1 covered), HCT (a long investigational list vs 25+ covered diseases).
- Real multi-criterion logic (all-of / any-of / nested), usable as a tree (12): Mohs, ACI, trigger point injections, MUA, gender surgery, nerve blocks, neurolysis/ablation, TMR, in-utero fetal surgery, EK/CXL, bone conduction hearing aids, laparoscopic/transcervical RFA for fibroids, LITT, cryoablation (kidney/lung).
- Judgment-delegated (4 transplant docs): lung, heart-lung, small bowel, kidney: "carefully selected individuals with irreversible, progressively disabling, end-stage pulmonary disease ... unresponsive to maximum medical therapy" plus "Potential contraindications ... (subject to the judgment of the transplant center)". The contraindication list is a NOT-list whose entries are themselves undefined.

Also note: inside "real criteria" documents the investigational list matters. Trigger point injections: the covered rule is an all-of with a quantity cap, but imaging guidance and dry needling are explicitly investigational, so a request for the injection "with ultrasound guidance" fails despite meeting the clinical criteria.

---

## 4. One line per document (all 29)

Format: number, topic; sections; shape of the Position Statement; rough count of covered indications. "Sections: 11/11 + header" means all eleven headings above, in order, plus the header/disclaimer/nav (true of all 29, so not repeated). Lines = Position Statement text lines; pages = PDF pages.

1. 02-10000-03 Mohs micrographic surgery (8 pp, PS 76 lines): lettered pathways A-E, ONE of; then a long "does not meet" list. About 5 covered pathways (A-E; roughly 35 listed tumor, site or host items); exclusions enumerate site x histology x size.
2. 02-10000-11 Bio-engineered skin and soft tissue substitutes; amniotic membrane/fluid (39 pp, PS 348 lines, 31 of the 39 pages are References + code lists): indication paragraphs each followed by a product bullet list; then "All other ... investigational, including, but not limited to" ~257 product bullets; collagen dressing criteria. Covered: 3 breast-reconstruction conditions (ONE of), DFU 10 products, VLU 2 products, DEB 1, burns 3, human amniotic membrane 8 products, collagen dressing: roughly 7 indication paragraphs, ~30 product-indication pairs.
3. 02-10000-19 Breast ductoscopy (4 pp, PS 2 lines): blanket investigational. 0 covered.
4. 02-12000-15 Prophylactic mastectomy (6 pp, PS ~28 lines): two covered statements (high risk of breast cancer; extensive mammographic abnormalities where biopsy is impossible); "High risk ... may be defined as one or more of the following" with 6 OR-bullets (LCIS; BRCA1/2; other gene; Li-Fraumeni/Cowden/Bannayan-Riley-Ruvalcaba or first-degree relative; lifetime risk "about 20% or greater"; chest radiation between 10 and 30 years of age); counseling "recommended"; contralateral prophylactic mastectomy otherwise investigational. 2 covered.
5. 02-20000-17 Autologous chondrocyte implantation (9 pp, PS 35 lines): one "ALL of the following are met" list of 6 bullets (two are age-population conditional, 15 years / < 55 years, plus lesion size >= 1.5 cm2, Outerbridge grade II or less, normal alignment); ACI for other joints and synthetic scaffolds (AGILI-C) investigational; footnote ("***Outerbridge Arthroscopic Grading System") holds the grade definitions. 1 covered (knee).
6. 02-20000-28 Trigger point injections (10 pp, PS 19 lines): ALL of 5 bullets (regional pain, spot tenderness in a palpable taut band, restricted ROM, 6 weeks conservative therapy "fails or is not feasible", cap "4 in 30 days or 6 in 6 months, per anatomic location"); imaging guidance and dry needling (20560, 20561) investigational. 1 covered.
7. 02-20000-34 Manipulation under anesthesia (7 pp, PS 66 lines incl. LOINC table): 4 covered bullets, shoulder with nested ALL-of (3 deep); four investigational statements (spinal MUA, other joints, serial sessions, multi-joint for chronic pain). 4 covered.
8. 02-20000-38 Thumb basal joint arthroscopy (4 pp, PS 3 lines): blanket investigational for diagnosis/staging of thumb basal joint arthritis. 0 covered.
9. 02-30000-10 Lung and lobar lung transplant (8 pp, PS 35 lines; Description 64 lines of evidence): CMN block; 3 covered (lung "for carefully selected individuals"; lobar; retransplant "in individuals who meet criteria for lung transplantation"); "all other situations" investigational; 9 potential contraindications "subject to the judgment of the transplant center". Statute excerpts in OTHER. 3 covered, criteria are qualitative.
10. 02-33000-18 Partial left ventriculectomy and surgical ventricular restoration (7 pp, PS 3 lines): two blanket investigational statements. 0 covered.
11. 02-33000-24 Heart and lung transplant (8 pp, PS 42 lines): CMN block; covered for "end-stage cardiac and pulmonary disease including, but not limited to, one of the following conditions" (7 bullets), plus retransplant; contraindication list (7); all others investigational. 7 listed conditions + retransplant; open list.
12. 02-33000-29 Endovascular stent grafts, thoracic aorta (6 pp, PS 16 lines): 3 covered conditions (descending thoracic aortic aneurysm "according to FDA-approved specifications"; acute, complicated type B dissection; traumatic tears), 2 investigational (uncomplicated dissection; ascending/arch). 3 covered.
13. 02-38240-01 Allogeneic HCT (20 pp, PS 161 lines): numbered 1-6 state-mandated subsections, extra "also meets" indications, case-by-case paragraph, investigational list, cord blood statements. 12 + 3 + 4 diseases mandated, 4 added, 6 open examples ("not described in the preceding lists ... case by case"), ~11 investigational groups. About 25 covered indications.
14. 02-40000-18 Isolated small bowel transplant (6 pp, PS 41 lines): cadaveric transplant when intestinal failure AND long-term TPN dependency with severe complications (3 sub-bullets: multiple prolonged hospitalizations, progressive liver failure with "total bilirubin above 3 mg/dL", inability to maintain venous access); living donor only when cadaveric unavailable; retransplant; "does not meet ... for adults and children with intestinal failure who are able to tolerate TPN"; 7 contraindications. 3 covered.
15. 02-40000-21 Islet transplantation (7 pp, PS 21 lines): CMN block; autologous islet "as an adjunct to a total or near total pancreatectomy in inividuals with chronic pancreatitis" covered; all other conditions (including allogeneic) investigational. 1 covered.
16. 02-40000-25 Frenectomy or frenotomy for ankyloglossia (4 pp, PS 8 lines): covered "when newborn feeding difficulties or childhood and adolescent articulation problems are present"; "surgical correction of ankyloglossia to resolve speech pathology" investigational. 1 covered (two triggers). Header `Revised` stale.
17. 02-45000-02 Plugs for fistula repair (4 pp, PS 2 lines): biosynthetic plugs investigational for anal fistulas; CPT 46707 tagged "(Investigational)". 0 covered.
18. 02-50300-01 Kidney transplant (6 pp, PS 29 lines): CMN block; transplant for "a physician-confirmed diagnosis of end-stage renal disease"; retransplant; all others investigational; 7 contraindications. 2 covered, simplest transplant policy.
19. 02-55900-01 Gender affirmation surgery (7 pp, PS 88 lines): six procedure groups, each "meets ... when ALL of the following are met" A-G (age >= 18, capacity, documented dysphoria, no contraindications, mental health "well controlled", 12 months hormones, letter); aesthetic exclusion list. 6 covered groups.
20. 02-56000-30 Laparoscopic and percutaneous techniques for uterine fibroids (7 pp, PS 26 lines): RFA (Acessa laparoscopic < 10 cm, Sonata transcervical 7 cm) when ALL of 3 (ultrasound evidence + size; uterine-sparing desire or ineligible for alternatives; at least 1 of 5 symptoms); other myolysis investigational; age >= 18. 1 covered procedure (2 devices).
21. 02-61000-22 Vagus nerve stimulation (14 pp, PS 29 lines): covered for "medically refractory seizures, defined as seizures that occur despite therapeutic levels of antiepileptic drugs ..." (definition inline); investigational for 9 listed conditions "including but not limited to", VBLOC and transcutaneous VNS. 1 covered.
22. 02-61000-29 Nerve block injections (16 pp, PS 66 lines): 7 indications with nested AND/OR; 7 investigational nerve blocks; imaging guidance covered; effectiveness exclusion. 7 covered (+ imaging).
23. 02-61000-34 Neurolysis/ablation (16 pp, PS 40 lines): facet joint RF (all of 7, with a nested OR for blocks and a note "*NOTE") and trigeminal RF (all of 2); all other methods/nerves investigational; caps in Reimbursement. 2 covered.
24. 02-65000-15 Endothelial keratoplasty and corneal collagen cross-linking (11 pp, PS 77 lines): EK for endothelial dysfunction "including but not limited to" 6; CXL epi-off any-of 4 measurements AND conservative failure; topography and refractive list not eligible; LOINC table in PS. 2 services; 6+ diagnoses.
25. 02-69000-06 Implantable bone-conduction hearing aids (7 pp, PS 31 lines): FDA-approved device AND conductive/mixed loss AND one of 4 conditions AND audiologic thresholds (45/55/65 dB by device); bilateral symmetry rule; single-sided deafness alternative to CROS; replacement rules in Reimbursement. 2 covered.
26. 02-99221-12 Cryoablation of kidney and lung tumors (8 pp, PS 25 lines): renal cell carcinoma <= 4 cm with 1 of 2 conditions (GFR < 60, or not a surgical candidate); lung cancer with 1 of 2; others investigational. 2 covered.
27. 02-99221-16 Interstitial laser therapy (LITT) (10 pp, PS 28 lines): epilepsy (disabling seizures despite two or more drug regimens AND accessible foci); brain tumors or radiation necrosis (any-of 3 THEN all-of multidisciplinary plan AND trained neurosurgeon); all others investigational. 2 covered; the second mixes OR and AND at one level.
28. 03-59000-16 In utero fetal surgery (11 pp, PS 52 lines): 4 covered procedures each with ALL conditions incl. gestational-age cutoffs; MMC exclusion list; CDH tracheal occlusion and heart defects investigational; Medical Director approval NOTE. 4 covered.
29. 76JEWFS1H2QN1TDP2IH TMR (5 pp, PS 23 lines): standalone all-of 5 + adjunct to CABG; percutaneous investigational. 2 covered.

---

## 5. Extraction hazards in the pdftotext output

1. Bullet glyphs: three kinds inside this single payer and sometimes mixed in one file. `•` (bio-skin 286, nerve block 28, gender 15 ...), the private-use character U+F0B7 which most terminals print as nothing (Mohs 36, HCT 49, in-utero 25, EK/CXL 18, TMR 5 ...; LITT has 1 `•` and 7 U+F0B7), and no glyph at all (gender's lettered A-G lines, Mohs B-E letters, thumb arthroscopy). Sub-levels are a literal `o` and (MUA only) U+2212 `−`. A parser must normalise these before counting nesting.
2. Indentation is the only structure and it is unreliable: Mohs pathway A is indented but B-E begin at the left margin; page breaks (form feed `\f`) split lists mid-item (HCT between "(5)" items, in-utero MMC list between "fetal magnetic resonance imaging; AND" and "Normal karyotype; AND"); indentation can change after a page break.
3. No running headers or footers survive in the text (I checked page tops and bottoms), so there are no page-number lines to strip, but page text starts in the middle of a sentence or list.
4. Connector tokens are not reliable (see 1.4): missing on some bullets, inconsistent position (end of the penultimate bullet vs end of every bullet), `AND` and `OR` sometimes at the end of a bullet that is a header of a nested list.
5. Footnote markers carry meaning: bio-skin `*`, `**`, `***`, `****` after product names mean banked tissue, FDA PMA, 510(k) and HDE; EK/CXL `**` after "corneal ectasia" points to a contract caveat; neurolysis `*NOTE:`; ACI `***Outerbridge Arthroscopic Grading System` defines grades. Removing asterisks removes content.
6. Tables flatten: CPT/ICD tables become `code  descriptor` lines with hanging indents that wrap; multiple ICD ranges per line (`C50.411 – C50.519` spanning categories; "M79.671, 672 – M79.674, 675"); a lone `(Investigational)` tag on the next line detaches from its code (bio-skin: 364 tags). The nav-bar table and LOINC table (4 columns) flatten to word soup; the same sentence "Include all data of the selected type that represents observations made six months or fewer before starting date of service for the claim" repeats per row.
7. Description "Summary and Analysis of Evidence" and Reference lists are large and contain coverage-like words ("meets", "medically necessary") in quoted studies; they must be excluded from criteria parsing. References run to 150 entries; the update log to 77 entries.
8. Boilerplate repeats in every file and can match criteria queries (the step-therapy paragraph, the disclaimer "APPLIES TO ALL LINES OF BUSINESS").
9. Headings are plain text lines; inline indication headings (nerve block "Plantar fasciitis and other neuritis of the foot:") look the same as body sentences. In gender surgery the stray word "Other" sits on its own line before the cosmetic exclusion list.
10. Cross-references by position, not by id: Mohs "listed above (A)", "listed above (B)"; HCT "in addition to coverage mandated in subsection (1) above", "[except as noted in subsection (2) above]" (item 5 cites "subsection (5)" while the trial definition is item 6).
11. Repeated text blocks: Mohs, surgeon-pathologist NOTE appears in Description, Position Statement and Reimbursement; gender A-G lists are copied six times with small deltas.
12. Typos and odd symbols: ® ™ in product names; curly quotes in "Medicare Advantage"-adjacent text; "Mohs’" vs "Mohs"; lone words from conversion ("multiple" in HCT).
13. Update log dates are `MM/DD/YY`, once `MM/DD/YYYY`; log lines continue on wrapped lines with a different indent.

---

## 6. What a parser can rely on, and what it must not

Can rely on (verified across the 29):

- The eleven headings, upper case with a trailing colon, always present and in the same order. Splitting the text on them yields clean sections. (Position Statement heading may lack the colon: handle both.)
- Line 1 is the guideline number (may be clipped), then `Original Effective Date:`, `Reviewed:`, `Revised:`, `Subject:` (Subject can wrap to line 2).
- `Reviewed` equals the committee-approval date. The last log date is the effective revision date in nearly all cases (verify against `Revised`, which can be stale).
- The phrases `meets the definition of medical necessity`, `does not meet the definition of medical necessity`, `considered experimental or investigational` mark the polarity of a rule. The sentence structure `X meets ... when|for|in ... :` followed by a list is the criteria block; the list lead-in names the connector (`ALL`, `ONE`, `at least ONE`, `one or more`).
- FEP and SAO exceptions are always "Follow ... guidelines." and the Medicare Advantage line always names either NCD/LCD identifiers or "No National Coverage Determination ... found".
- `Reimbursement Information` is the place to look for numeric frequency/application limits and replacement rules, and `(Investigational)` / `(non-covered)` tags in code tables mean non-coverage.
- A blanket sentence "experimental or investigational for all indications" means a constant result (4 such docs here).

Must not rely on:

- Indentation or bullet glyph for nesting depth (three glyph classes, missing glyphs, shifted margins).
- `AND`/`OR` tokens for tree structure: absent, misplaced, mixed case, and unparenthesised AND/OR at one level.
- The numbering scheme: letters in Mohs/gender, numbers in HCT, plain bullets elsewhere; cross-references can be wrong.
- ICD-10 and CPT tables to select criteria: they are flat support lists, sometimes absent, sometimes split by CPT, never mapped to specific criteria except by CPT-keyed ICD tables in EK/CXL and one HCPCS code per procedure in the in-utero document.
- The Description for criteria or definitions, even when it contains a definition the criteria use (DSM-5-TR in gender surgery).
- `Revised` meaning "criteria changed".
- File name for the guideline number, or for the title (filenames are truncated, e.g. `...disorders-of-the-tho`).
- Soft-verb lines inside a criteria list ("should", "recommended", "may be defined as") being requirements: they sit in the same list format as requirements.
- Program Exceptions for criteria content: they never restate criteria; for FEP/SAO they replace them entirely, for Medicare Advantage they point to CMS documents the MCG does not reproduce.
- Any assumption that an uncovered indication is explicitly listed: the covered-list-plus-"all other" pattern means absence from the covered list is the denial, and "including but not limited to" lists are examples.

---

## 7. Implications for the criteria-tree design (from this batch)

- Leaf judgments here are mostly diagnosis/age/threshold/duration/document checks; but each policy also needs a line-of-business gate (FEP/SAO/MA) and a "benefits determined by contract" gate before the tree is meaningful.
- Four constructs beyond all/any/not showed up repeatedly: (a) closed-world fallback ("all other situations" = not met), (b) product/disease lookup tables as leaves (bio-skin, HCT, Mohs sites, EK diagnoses), (c) population-conditional leaves inside an ALL (ACI adolescent vs adult), (d) quantity/frequency limits evaluated against claims history, held in the Reimbursement section. A fifth: reviewer-discretion leaves ("subject to the judgment of the transplant center", "case by case", "appropriate candidate") that should return INSUFFICIENT or a human flag rather than MET/NOT_MET.
- Best candidates for early tree tests from this batch (cleanest logic, numeric thresholds): TMR (fit 2), in-utero fetal surgery (2), manipulation under anesthesia (2), gender affirmation surgery (2), trigger point injections, LITT, cryoablation. Hardest: HCT (4), bio-engineered skin (3, mostly because of lookup size), nerve blocks (3, ambiguous AND/OR).
