# Payer medical-necessity guidelines: a field guide for the checker

This guide pulls together the guideline-analysis project. It is written for someone who is building a prior-authorization
checker and is new to payer medical policy. It answers four questions:

- What are these documents?
- How are they built?
- How much do they vary?
- What does that mean for a system that turns one guideline into an `all` / `any` / `not` tree, has a model judge each
  leaf against a chart, and has code compile the result?

The evidence behind it:

- 25 cross-payer treatment reports (`treatments/*.md`)
- three Florida Blue template surveys covering 87 more guidelines (`bcbsfl/batch*.md`)
- 143 structured document profiles (`profiles/*.json`, schema in `PROFILE.md`)
- regex signals for all 205 documents (`survey.json`)
- the library manifest

The counts in this guide come from scripts in `_scratch/` (`aggregate.py`, `aggregate2.py`, `textscan.py`). Claims that
mattered were checked against `sourcing/text/`.

The current model it is measured against is the hand-built Florida Blue varicose-vein tree
(`tests/fixtures/bcbsfl-02-33000-31.json`):

- 17 criteria and 4 scenarios, each scenario keyed by the CPT codes it governs.
- Each scenario is an `all` whose last child is an `any` of four indications. The fourth indication is itself an `all`
  of three leaves.
- A `scope` table tags each CPT as covered, non-covered or investigational.
- Leaf thresholds are `number`, `enum` (CEAP) or `duration_months`.

Keep that shape in mind. Most of this guide is about where real documents fit it and where they do not.

---

## 1. The corpus

**What was collected.**

- **Size.** 205 PDFs from 30 payers, covering 112 treatments and 3,533 pages. The median document is 10 pages; the
  longest is Cigna 0051 (bariatric surgery) at 111 pages.
- **Florida Blue.** Every one of the 112 treatments has a Florida Blue (BCBSFL) guideline, so Florida Blue accounts for
  112 of the 205 files.
- **Cross-payer sets.** 25 of those treatments were also sourced from 4 to 8 other payers. That gives 25 comparison sets
  and 93 non-Florida-Blue documents.
- **Payers.**
  - National commercial carriers: UnitedHealthcare (19 files across commercial, Medicare Advantage, Community Plan and
    Surest) and Cigna (13).
  - Other Blue plans: Michigan, Rhode Island, Massachusetts, Texas, Illinois, Montana, Excellus, Blue Shield of
    California, Premera.
  - Utilization-management vendors: Carelon (7) and Evolent (4).
  - Regional and Medicaid plans: Kaiser, Independent Health, Emblem, Fallon, Medica, Priority Health, Providence,
    Humana Healthy Horizons, Centene, Louisiana Healthcare Connections, MedStar, CareSource, Curative.
- **Provenance.** Each PDF has a sidecar JSON with the source URL, sha256 and retrieval date (2026-10-09). The sidecars
  are listed in `sourcing/library/manifest.json` and rendered in `sourcing/CATALOG.md`.
- **Text.** Every PDF was converted with `pdftotext -layout` into `sourcing/text/<treatment>/<stem>.txt`. All the
  analysis reads that text.

**How it was analysed.**

- **Treatment reports.** One worker per cross-payer treatment wrote a report comparing the documents side by side, with
  invented test cases that come out differently by payer.
- **Template surveys.** Three workers surveyed the other 87 Florida Blue guidelines in batches of 29, looking at the house
  template.
- **Profiles.** Workers wrote 143 profiles: 55 Florida Blue and 88 other. A profile records:
  - sections in order and where the criteria live
  - top-level logic, nesting depth, k-of-n groups and AND/OR ambiguities
  - requirement kinds, thresholds and time windows
  - external dependencies, definitions that change meaning, vague terms and extraction hazards
  - a 1-5 "fit to tree" score (1 = all/any/not expresses it cleanly; 5 = needs new constructs or human judgment)

**Limits you should know about.**

- **No Aetna.** Aetna publishes its Clinical Policy Bulletins as web pages, not PDFs. The fetcher (`grab.py`) takes only
  documents a payer serves as PDF, so Aetna is out.
- **No CMS documents.** There are no LCD PDFs and no NCDs in the corpus. LCDs live as HTML on the Medicare Coverage
  Database. Many documents point to an NCD or LCD, so that is a large blind spot for Medicare Advantage. The repo's
  `data/samples/` holds NCD 20.8.3, but that file is not part of this corpus.
- **Wrong documents in two slots.**
  - `cigna-0158` is filed under sleep-testing but is Cigna's *Surgical Treatments for Obstructive Sleep Apnea*. Its first
    lines say so, and it defers testing to a separate "Sleep Disordered Breathing" guideline. It is still useful under
    sleep-apnea-surgery.
  - `cigna-0551` is filed under facet-joint-injections but is *Anesthesia Services for Interventional Pain Management
    Procedures*. It decides when sedation is covered, not when a facet injection is. Cigna's own facet policy is not in
    the library.
- **Stale metadata.** The library metadata was often stale or wrong next to the PDF itself:
  - UHC-MA varicose veins: the file says MMP099.07 (2024); the PDF prints MMP099.11, effective 09/01/2026.
  - UHC-MA spinal cord stimulation: MMP368.11 vs MMP368.14.
  - UHC Ohio bariatric: CS007OH.D vs version E.
  - UHC epidural: the number ends in N in the file and O in print, and the dates differ.
  - Blue Shield CA ambulatory monitors: 2023 vs August 2026.
  - Fallon ICD: 2024 vs 2026.
  - BCBSM pneumatic compression: 2022 vs 2025.

  The 148 sidecars that were checked now carry a `printed_date` field recording what the PDF says. **Trust the printed
  text over the metadata.**
- **Old or expired documents.**
  - BCBS Texas prints "Policy End Date 12/31/2025".
  - BCBS Rhode Island varicose is from 2019-2021 and its LAA policy from 2020.
  - Independent Health knee is dated 2021.
  - UHC balloon sinuplasty and Centene PA balloon sinuplasty are from 2019.

  Some apparent cross-payer differences are just age.
- **Skewed scope.** Florida Blue is complete across the 112 treatments, but the other payers appear only for the 25
  comparison treatments. Those lean towards spine, pain injections, cardiac devices, sleep and plastic surgery. There are
  no drug or pharmacy policies. Several Medicaid documents are copies posted by the Louisiana Medicaid program, including
  vendor redlines.
- **Survey regex overcounts.** For example, it counts "ICD-10" whenever an update log says "ICD-10 codes added", even when
  the document has no ICD table. Use `survey.json` for rough signals only.

---

## 2. Primer: what a medical policy is and who writes it

**Medical necessity vs coverage.** A health plan pays for a service only if two things hold:

1. **The member's contract includes the benefit.** Some employer plans exclude bariatric surgery or infertility. This is
   decided by the contract.
2. **The service is "medically necessary" for this patient.** This is decided by the plan's medical policy, also called a
   coverage policy, medical coverage guideline or clinical guideline.

Every Florida Blue guideline opens with an all-caps disclaimer: "BENEFITS ARE DETERMINED BY THE GROUP CONTRACT ... THIS
MEDICAL COVERAGE GUIDELINE APPLIES TO ALL LINES OF BUSINESS UNLESS OTHERWISE NOTED IN THE PROGRAM EXCEPTIONS SECTION."
So the best a guideline can say is "medically necessary", never "covered". The checker answers the medical-necessity
question only.

**Prior authorization.** This is the process of asking the plan, before the service, whether it agrees the service is
medically necessary. The plan's reviewer, often a nurse working from a criteria set, compares the submitted records with
the policy. Your checker does that comparison on the provider's side, before submission. Some plans skip prior
authorization and review after the fact:

- Medica: "Prior authorization is not required" for PAP.
- Independent Health TAVR: "Pre-authorization not required. Criteria utilized upon retro-review."

The criteria are the same either way, but a "ready to submit" answer means something different.

**Who writes the criteria.** There are five main sources.

1. **The payer's own medical policy committee.** Florida Blue's guidelines are "approved by the Florida Blue Medical
   Policy and Coverage Committee". Blue plans often adapt reference policies from the Blue Cross Blue Shield Association
   (BCBSA). You can see the shared origin in the text:
   - Florida Blue cites BCBSA 7.01.124 for varicose veins.
   - Florida Blue, BCBS Illinois and BCBS Massachusetts cervical disc arthroplasty text matches almost word for word
     (BCBSA 7.01.108).
   - Florida Blue and Blue Shield CA cardiac monitoring share wording.
   - Florida Blue and BCBSM LAA closure share a skeleton.

   This is why Blue plans often agree with each other and disagree with UHC or Cigna.
2. **Utilization-management vendors.** A plan can hand whole service lines (imaging, musculoskeletal, pain, cardiology,
   sleep) to a vendor that writes and applies its own guidelines. In this corpus:
   - **Carelon** (formerly AIM, part of Elevance) and **Evolent** (formerly National Imaging Associates, NIA). Florida
     Blue's sleep-testing guideline says "FEP is excluded from the National Imaging Associates (NIA) review", so even
     Florida Blue sends some reviews to a vendor.
   - Cigna says "delegated vendor guidelines may be used" in some markets. Cigna's usual vendor, eviCore, is not in the
     corpus.
   - Blue Shield CA's SI-joint policy is Evolent's text adopted nearly verbatim (`BSC_EVO_1756`).

   Vendor guidelines also say the plan can override them: "If requested by a health plan, Carelon will review requests
   based on health plan medical policy/guidelines in lieu".
3. **CMS (Medicare).**
   - A **National Coverage Determination (NCD)** applies everywhere in traditional Medicare, for example NCD 20.4 for ICDs
     or NCD 20.34 for LAA closure.
   - A **Local Coverage Determination (LCD)** is written by a regional Medicare Administrative Contractor (MAC). Florida's
     MAC is First Coast Service Options (FCSO), so the Florida Blue varicose guideline cites "LCD L38720 / Article
     A58250 (First Coast)".
   - Medicare Advantage plans are expected to follow NCDs and LCDs. Carelon's text says its own criteria apply to MA only
     "where CMS criteria are not fully established".
4. **Proprietary criteria sets.** **InterQual** (Optum) and **MCG** (formerly Milliman Care Guidelines; MCG Health) sell
   licensed decision criteria. They are not public, so a policy that says "refer to InterQual" gives you nothing to read.
   UnitedHealthcare does this constantly:
   > "For medical necessity clinical coverage criteria, refer to the InterQual® Client Defined CP: Procedures, Endovenous
   > Ablation ..."

   Note the naming collision: **Florida Blue calls its own documents "MCGs" (Medical Coverage Guidelines). These have
   nothing to do with MCG Health.**
5. **State and federal law.** Laws reach into criteria:
   - Florida's step-therapy exemption statute (627.42393) appears in 107 of 112 Florida Blue documents.
   - Florida Administrative Code 59B drives the transplant indication lists.
   - The Women's Health and Cancer Rights Act (WHCRA) mandates post-mastectomy symmetry procedures.
   - Washington's Health Technology Clinical Committee limits appear in Evolent's knee guideline.

**Lines of business.** One payer sells several kinds of plan, and the rules can differ by plan:

- **Commercial:** employer group, individual, exchange or marketplace. Self-funded employers (ASO) may have their own
  plan documents.
- **Medicare Advantage (MA):** private plans that replace traditional Medicare. They are bound by NCDs and LCDs.
- **Medicaid:** state programs, usually run by managed-care plans such as Healthy Blue, Humana Healthy Horizons, LHCC,
  MedStar Family Choice and UHC Community Plan. They follow a state manual.
- **FEP (Federal Employee Program):** the Blue plan for federal employees. Its benefits and policies are set nationally,
  not by the local Blue.
- **SAO (State Account Organization):** Florida Blue's label for Florida state-employee accounts, which have their own
  guidelines.

**How it fits together (delegation chains).** The criteria for one member can sit three hops away from the document you
are reading:

- A Florida Blue commercial member is decided by the Florida Blue guideline.
- A Florida Blue FEP or SAO member: "Follow FEP guidelines." / "Follow SAO guidelines." The guideline does not apply.
- A Florida Blue MA member: the guideline only says an NCD or LCD "was reviewed". The binding criteria are presumably
  First Coast's LCD, which is not in the document.
- A UHC commercial member: the PDF points to InterQual, a licensed product.
- A UHC MA member: the PDF has a table of LCDs by MAC state, then falls back to the UHC commercial policy, which itself
  points to InterQual.
- An Independent Health MA member: "Managed by Evolent".
- A Healthy Blue Louisiana Medicaid member: Healthy Blue is an Elevance plan, and its document is a Carelon-family policy
  (SURG.00121).

The checker's design already says "the coordinator picks the guideline; the model only verifies it applies". That
verification has to understand this chain.

---

## 3. Anatomy of a guideline

### 3.1 Common parts across payers

Nearly every document has these parts, in some order:

- **Identity:** number, title and dates (original effective, reviewed, revised or effective, sometimes next review or end
  date).
- **Applicability:** lines of business and plans.
- **The coverage statement**, which holds the criteria.
- **Definitions.**
- **Documentation requirements.**
- **Codes:** CPT/HCPCS procedure codes, sometimes ICD-10 diagnosis codes, sometimes coverage tags per code.
- **Background or description**, including a summary of evidence.
- **References.**
- **Revision history.**

The coverage statement is usually short and the rest is long. Some examples of criteria length against document length:

| Document | Criteria | Whole document |
|---|---|---|
| Cigna bariatric | pp.2-8 | 111 pp |
| BCBSM LAA closure | 6 lines | 33 pp |
| BCBSTX HBOT | Table 1 on pp.3-4 plus Notes | 92 pp |
| Florida Blue lumbar fusion | about 80 lines | 982 lines |

The evidence sections are full of numbers that look like criteria but are not: "mean CHA2DS2-VASc 4.7", Cobb angles,
trial percentages. **An extractor that reads the whole PDF will pick up thresholds that no criterion states.**

### 3.2 The Florida Blue house template

All 112 Florida Blue guidelines share one rigid shell. The three surveys checked heading order across 87 documents:

- batch 1 and batch 2: 29/29 each
- batch 0: 28/29 (one heading is glued to the previous sentence)

The parts, in order:

0. **Header:** guideline number on line 1 (e.g. `02-33000-31`), then `Original Effective Date:`, `Reviewed:`,
   `Revised:` (sometimes `Next Review:`), then `Subject:`. Two quirks: the TMR file prints a clipped `02-33000-1`, and its
   filename carries a random token instead of the number.
1. The all-caps **disclaimer**, then a flattened hyperlink **navigation bar**. The nav bar looks like headings; drop it.
2. `DESCRIPTION:` covers the procedure, its FDA status and a "Summary and Analysis of Evidence". This is not criteria.
   It is sometimes 60-240 lines, and the Position Statement can start past line 200 (in-utero surgery).
3. `POSITION STATEMENT:` holds **all the coverage logic, almost always.** It is prose and bullets, not a numbered criteria
   set.
4. `BILLING/CODING INFORMATION:` contains:
   - CPT and HCPCS lists, with `(Investigational)` or `(non-covered)` tags at the end of some descriptors
   - in 41 of 112, an "ICD-10 Diagnosis Codes That Support Medical Necessity" list
   - in 41 of 112, a LOINC table of the document types the payer may ask for, with the same time-frame narrative on
     every row: "observations made six months or fewer before starting date of service"
5. `REIMBURSEMENT INFORMATION:` usually says "Refer to section entitled POSITION STATEMENT." **But in at least 10
   guidelines it holds a binding frequency cap the Position Statement never mentions:**

   | Guideline | Cap in Reimbursement Information |
   |---|---|
   | Hyperbaric oxygen | "limited to thirty (30) treatments within a 12 month period" |
   | Epidural injections | "62320 and 62321 in any combination are limited to eight (8) in twelve (12) months" |
   | SI joint injections | 3 per joint per 6 months |
   | Sleep testing | 2 in 12 months |
   | Nerve blocks | 4 in 6 months for 64400 |
   | Neurolysis | 2 per region per 12 months |
   | Trigger points | 4 in 30 days |
   | Excimer laser | 30 sessions in 6 months |
   | Oral appliances | 1 per 12 months |
   | Apligraf | 5 applications per ulcer |

   It can also hold a threshold table: reduction mammaplasty's Schnur sliding scale is in this section. It holds
   documentation and replacement rules too (gynecomastia, cochlear and bone-conduction devices, total-ankle revision).
6. `PROGRAM EXCEPTIONS:` is a fixed block:
   > Federal Employee Program (FEP): Follow FEP guidelines.
   > State Account Organization (SAO): Follow SAO guidelines.
   > Medicare Advantage products: No National Coverage Determination (NCD) and/or Local Coverage Determination (LCD) were
   > found ... [or] The following ... was reviewed ...

   The FEP line is in 111 of 112 documents (sleep testing words it differently), the SAO line in 112, and "no NCD/LCD
   found" in 51.

   This section **delegates whole lines of business; it never restates criteria.** It does not even say that the NCD or
   LCD overrides the Florida Blue text for MA, only that it was reviewed.

   It ends with the step-therapy paragraph, which appears even in documents that contain no step therapy. It is noise.
7. `DEFINITIONS:` is a `Term: definition` glossary. Most entries are harmless medical glosses, but some carry thresholds
   the Position Statement depends on:

   | Guideline | Definition that changes the criterion |
   |---|---|
   | PAP devices | excessive daytime sleepiness means Epworth ≥ 10 |
   | Bio-engineered skin | "Nonhealing- less than a 20% decrease in wound area with standard wound care for at least 2 weeks" |
   | Deep brain stimulation | "Disabling, medically unresponsive tremor: ... for at least 3 months before implant" (a duration the criteria never state) |
   | Site of service | "Poorly controlled diabetes mellitus: ... HbA1c ≥ 9%" |
   | Sleep apnea surgery | "clinically significant OSA" defined here, far from the criteria that cite it |

   Defined terms are not marked in the Position Statement. Nothing in bold or italics survives extraction.
8. `RELATED GUIDELINES:`, `OTHER:`, `REFERENCES:`, `COMMITTEE APPROVAL:`, `GUIDELINE UPDATE INFORMATION:`. OTHER can hold
   statute excerpts or FDA label indications that read like criteria but are not. The update log is a dated prose
   history.

**How a Florida Blue Position Statement talks.** Three stock verdict phrases carry nearly all the meaning:

- "meets the definition of medical necessity [when ALL of / for ONE of the following ...]"
- "does not meet the definition of medical necessity", used mostly for cosmetic or out-of-scope requests
- "is considered experimental or investigational", which appears in 84 of 112 documents and is always followed by a
  boilerplate rationale ("The evidence is insufficient to determine the effects of the technology on health outcomes.")

Most statements end with a closed-world catch-all, for example "Total ankle replacement is considered experimental or
investigational for all other indications". **Anything not matched by a covered paragraph is denied.**

**Florida Blue dates.**

- `Reviewed` equals the committee date (29/29 in batch 2).
- `Revised` is the effective date of this version. It is usually the 15th of the following month.
- **`Revised` does not mean the criteria changed.** It is often a quarterly coding update. Nerve blocks shows `Revised:
  10/01/26` with the log line "ICD-10 coding update".
- The update log and the current text can disagree:
  - The fusion guideline's log says bracing was deleted in 2018, but the current text still lists bracing.
  - The varicose log says cyanoacrylate "investigational position ... maintained" in 2020, but the current text covers
    it.

  Only the current Position Statement is authoritative.

### 3.3 How other payers differ

- **Cigna.**
  - The Coverage Policy is up front (2-8 pages), followed by long General Background and coding tables grouped by
    coverage status.
  - Capitalised quantifiers: "ALL of the following", "ANY of the following", "NONE of the following".
  - Per-device tables: hypoglossal nerve stimulation lists Inspire vs Genio with different age, AHI and BMI limits.
  - Background sometimes restates measurements as "recommended".
  - Watch for quantifier misuse. Cigna HBOT says "medically necessary first-line treatment for ALL of the following
    conditions" when it means any one of them.
- **UnitedHealthcare commercial.**
  - A 1-3 page Coverage Rationale, then Definitions, then "Applicable Codes" (listed "for reference purposes only ...
    does not imply ... covered"), then 10-25 pages of clinical evidence.
  - **10 of the 19 UHC-family profiles contain no criteria** and point to InterQual.
  - Thresholds often sit in Definitions that no criterion uses, which leaves orphan definitions. UHC varicose defines
    reflux as more than 0.5 s and a varicose vein as 3 mm or more, but never requires either.
- **UHC Medicare Advantage.** Router documents: a table of NCDs and LCDs by MAC and state, with fallback to commercial
  policy or InterQual.
- **Other Blues** (BCBSM, BCBSRI, BCBSMA, BCBSTX, Excellus, Blue Shield CA, Premera). BCBSA-derived and usually
  self-contained, but each has its own quirks:
  - Inclusions/Exclusions lists (BCBSM).
  - "Policy Guidelines" that hold definitions and sometimes criteria (Excellus, Blue Shield CA).
  - The same criteria written twice for MA and commercial (BCBSRI).
  - The Medicare LCD reproduced inside the commercial policy (BCBSM panniculectomy).
  - An Appendix A that repeats the old and new policy side by side (Blue Shield CA).
  - Policy end dates (BCBSTX).
- **Vendors (Carelon, Evolent).**
  - Multi-procedure compendia: Carelon spine is 66 pages; Evolent pain is a 102-page stack of eight guidelines.
  - A general framework ("General Clinical Guideline", "Patient Requirements") applies to every procedure, and specific
    blocks override it: "The specific requirements take precedence over any stated general requirement."
  - Definitions of conservative management, home exercise program and failure sit away from the criteria that use them.
  - The copies in this corpus were posted by Louisiana Medicaid as **redlines**, with deleted and inserted text fused
    together (see section 8).
- **Kaiser.** Short numbered criteria with a line-of-business table and a separate Exclusions section that includes
  social factors ("Lack of caregiver or unsuitable home situation") and routes to medical-director review.
- **Medicaid managed-care templates** (Centene, Humana, LHCC, MedStar). Outline-numbered (I.A.1.a.i), often with ICD-10
  lists tied to criteria. Older (Centene 2019).
- **Pure routers** (Fallon, Providence, CareSource, BCBSM MA HGNS). A page or two pointing to InterQual, MCG, NCDs or
  LCDs.

---

## 4. Kinds of documents, by what a checker can do with them

The fit-to-tree score summarises the 143 profiles:

| Fit score | 1 (clean) | 2 | 3 | 4 | 5 (new constructs / human) | Mean |
|---|---|---|---|---|---|---|
| All 143 | 6 | 49 | 62 | 10 | 16 | 2.87 |
| Florida Blue (55) | 4 | 18 | 28 | 3 | 2 | 2.65 |
| Others (88) | 2 | 31 | 34 | 7 | 14 | 3.00 |

**Florida Blue is the friendliest payer in the corpus for a tree.** It is self-contained, uses one template, and almost
never delegates. Even so, the typical Florida Blue document is a "3", meaning it needs some judgment calls. Sorted by
what the checker can do, documents fall into five kinds.

**A. Real criteria trees.** These have nested all/any logic over leaves with thresholds:

- the varicose fixture
- cervical and lumbar spine surgery
- facet, epidural and SI injections
- ICD, TAVR and LAA closure
- knee and hip arthroplasty and arthroscopy
- deep brain stimulation, cochlear implants, transmyocardial revascularization (TMR), in-utero fetal surgery, and
  manipulation under anesthesia (MUA)

In the 87 surveyed Florida Blue guidelines, about 38 are this kind. Add almost all of the 25 Florida Blue treatment
anchors, and **roughly 60 of the 112 Florida Blue documents** are trees, though many still need k-of-n, history or
judgment leaves. Most non-Florida-Blue documents that contain criteria are also this kind.

**B. Indication lists.** Here membership is the rule:

- Florida Blue SRS (12 + 9 diagnoses)
- SBRT (8 indications + 13 cancer sites)
- autologous HCT (about 40 named indications, statute-driven)
- liver, heart and lung transplant etiologies
- HBOT (about 19 covered indications, one with a real tree: diabetic wound, Wagner grade 3 or higher, 30 days without
  healing)

About 11 of the 87 surveyed fit here. The tree is an `any` over diagnosis leaves plus a closed-world default: not on the
list means not covered. The transplant documents add advisory contraindication lists "subject to the judgment of the
transplant center" and tiers such as "accepted" vs "probable" indications. Those are not hard NOT nodes.

**C. Blanket investigational.** The whole Position Statement is one sentence:

> "Bronchial thermoplasty for the treatment of asthma and all other indications is considered experimental or
> investigational." (02-30000-12)

**20 of the 87 surveyed Florida Blue guidelines (23%)** are this kind:

- subtalar arthroereisis, facet arthroplasty, breast ductoscopy, interspinous devices, occipital nerve stimulation,
  intradiscal annuloplasty, lysis of epidural adhesions, ductal lavage, and others

A further ~15 are narrow carve-outs: one covered clause and everything else investigational. Examples are islet
transplant (autologous, with pancreatectomy only), canaloplasty, whole-gland prostate cryoablation and frenectomy. For
blanket documents the right output is a constant ("not covered for any indication"), with no judge call.

**D. Delegated, pointer-only.** No criteria are in the file:

- **14 of the 88 non-Florida-Blue profiles (16%)**, all scored 5.
- Ten of them are UHC (InterQual): varicose veins, SCS, breast reduction, knee surgery, bariatric (Ohio Community Plan),
  brow/eyelid, SI joint, Surest spinal fusion, plus two UHC-MA routers.
- The other four:
  - Fallon ICD (InterQual + NCD 20.4)
  - CareSource PAP ("uses MCG Health clinical criteria")
  - Providence CPAP (NCD 240.4, LCDs)
  - BCBSM MA hypoglossal nerve stimulation (LCD per MAC)

Profiles name an external dependency of some kind in 142 of 143 documents:

| Dependency | Documents |
|---|---|
| Another policy | 112 |
| LCD | 47 |
| NCD | 44 |
| State law | 33 |
| Vendor | 22 |
| InterQual | 16 |
| MCG | 8 |

Usually the dependency is partial, for example "Medicare Advantage: see NCD". For Florida Blue it is almost always only
the MA and FEP/SAO hand-off.

**E. Benefit, payment and site-of-service rules.** These are not clinical-necessity criteria:

- **Florida Blue balloon sinuplasty (02-31000-01).** The entire policy is that dilation "is considered integral to ...
  FESS when performed at the same time and is not separately reimbursable", plus implant devices investigational. There
  are no clinical criteria, so stand-alone dilation is neither approved nor denied.
- **Florida Blue site-of-service review (08-00000-01).** It decides where the procedure is done (hospital outpatient vs
  ambulatory surgery center) from about 25 risk conditions, ASC access and a cost comparison.
- **Benefit-gated guidelines.** Infertility ("If the benefit for coverage for infertility treatment is available ..."),
  gender-affirmation and reconstructive surgery ("Some plans may exclude coverage ..."). The reconstructive one is a
  320-line catalogue of examples with "individual consideration" and "Medical Director review".

About 3-4 of the 112 Florida Blue documents are this kind.

---

## 5. Logic shapes

**Top level.** Most documents are pathways: several indications or procedures, each with its own `all` list. A typical
Florida Blue shape is:

> any(pathway_1 ... pathway_n) + "all other indications investigational"

Each pathway is all(leaves..., any(indications), not(contraindications)). The profiles' top-level field mentions
"pathway" in 83 documents and "all" in 87. The fixture's scenario-per-CPT-group design maps well onto this shape. The
hard part is that **no payer gives a CPT-to-pathway table.** The same code can fall under several blocks, and mapping a
code to its block is a judgment call:

- 36470/36471 can treat tributaries, perforators or truncal veins.
- 29880/29881 serve both meniscectomy and debridement.
- Facet codes 64490-64495 cover both diagnostic and therapeutic injections.

**Nesting depth.** Maximum depth per profile:

| Depth | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Documents | 4 | 16 | 27 | 61 | 29 | 6 |

Depth 3 is typical. Florida Blue never exceeded 4. The depth-5 cases are all non-Florida-Blue: Excellus SCS
(I.A.1.b.i), BCBSRI arthroplasty (pathway, ALL a-i, k-of-n, sub-lists), Excellus panniculectomy, and Carelon. The fixture
is depth 4.

**k-of-n.** "At least 2 of the following" appears **27 times in 20 documents (14%)**, counting only cases where 2 ≤ k < n.
Six of those documents are Florida Blue:

- reduction mammaplasty: "A minimum 6-week history of AT LEAST TWO OF THE FOLLOWING" 7 symptoms
- cervical spine fusion: 2 of 4 conservative modalities
- lumbar spine: 2 of 6 radiculopathy signs, and 2 of 4 treatments for 12 consecutive weeks
- hip arthroscopy: 2 of 6 conservative measures
- knee arthroscopy: 2 of 6 modalities, repeated three times in the meniscal block
- SI fusion: "a cluster of 3 provocative tests"

Elsewhere:

- Blue Shield CA/Evolent SI injections: 3 of 8 provocation tests; 4 of 5 inflammatory back pain features
- Excellus SCS CRPS (Budapest-style): symptoms in 3 of 4 categories, signs in 2 of 4
- BCBSRI arthroplasty: 2 of 4 pain features, 2 of 5 imaging findings, 2 of 4 infection labs
- Lamin A/C cardiomyopathy in BCBSM, Carelon and Cigna: 2 of 3 risk factors

1-of-n is common, but it is just `any`. Expanding 2-of-7 into `any` of all pairs gives 21 branches and breaks the
"cheapest path to MET" and confidence logic. k-of-n needs a real node (section 9).

**Exclusions** come in four forms:

1. **An inline negative leaf:** "not secondary to DVT", "Member does not have unicuspid or bicuspid aortic valves",
   "Have no evidence of intracranial hemorrhage".
2. **A "None of the following" list.** It can be a footnote, as in Florida Blue hip and knee: "There are no
   contraindications*", with the asterisk list after the criteria.
3. **A separate section:** Exclusions or Contraindications (Kaiser, Carelon, Evolent).
   - Carelon and Evolent split these into "absolute" and "relative" contraindications, where the relative ones often
     come with an "unless" clause.
   - Kaiser's Exclusions include social factors.
4. **A separate sentence declaring a variant cosmetic or investigational.** Florida Blue varicose:
   > "Sclerotherapy of isolated tributary veins without prior or concurrent treatment of saphenous veins" is
   > investigational.

   This kind of exclusion depends on what else is on the order, not on the chart.

**Repeat, continuation and replacement.** These rules are common in procedures that repeat or involve devices:

- **Injections.** Epidural, facet and SI injections are ruled by prior relief, intervals and caps:
  - prior relief: ≥ 50% relief, sometimes held for ≥ 6 weeks, 2 months or 3 months
  - intervals: 7 days, 14 days, 2 months
  - caps: 3, 4 or 6 per region per rolling 12 months
  - new-episode resets: 12 months at Carelon, 2 years at Evolent

  Evolent writes injections as a **state machine**: an initial phase of up to 3 injections with ≥ 30% relief, then a
  therapeutic phase with ≥ 50% for ≥ 2 months each.
- **Staged devices.** SCS is "trial, then permanent if ≥ 50% relief". PAP is "3-month rental, then adherence of ≥ 4 h on
  70% of nights in 30 consecutive days, evidenced between day 31 and day 91". HGNS and ICD replacement require
  "malfunctioning and out of warranty".
- **Revision surgery.** Bariatric revision requires complications or a 2-year weight-loss failure (Cigna). Knee and hip
  revision have indication lists.
- **A vacuous first-time rule.** Florida Blue facet therapeutic criteria require "at least 50% pain relief for at least
  three (3) months from the prior therapeutic injection". For a first therapeutic injection that leaf is undefined, and
  the document does not say whether it is vacuously met.

**History-dependent criteria.** Many leaves ask about the past, not today's visit:

- prior procedure dates:
  - "great or small saphenous veins had been previously eliminated (at least 3 months)"
  - "≥ 18 months post-operative" for panniculectomy
  - "fully healed" initial disc implant
- injection counts across providers in a rolling 12 months
- percent relief from a diary
- CPAP downloads
- weight stable for 3 or 6 months

Profiles list "prior procedure" as a requirement kind in 66 documents. These are the leaves where a chart is most often
silent.

**Scoring systems and graded scales.** Leaves often name a score:

- **Cardiac:** CHADS2, CHA2DS2-VASc and HAS-BLED (LAA closure, cardiac monitoring), NYHA class, CCS angina class, STS
  and EuroSCORE (TAVR, TMVR), LVEF.
- **Sleep:** Epworth Sleepiness Scale.
- **Wounds and plastics:** Wagner ulcer grade (HBOT), the Schnur sliding scale by body-surface area (reduction
  mammaplasty), the ASPS pannus grade.
- **Veins:** CEAP clinical class (varicose).
- **Joints and spine:** Kellgren-Lawrence and Outerbridge grades, Tönnis grade (hip), Cobb angle, Meyerding and Wiltse
  (spine), VAS, ODI and NDI pain and disability scores, Marx and Tegner activity scores, WOMAC.
- **Neurology and other:** UPDRS (DBS), Rutherford class and ankle pressures (SCS for limb ischemia), International
  Society of Lymphology stage, Tanner stage, ASA class and MELD (Cigna sedation).

Three things make scores hard:

1. **Charts rarely state them.** The value must be found in the chart or computed from its components.
2. **The policy may define them differently from the textbook.** Florida Blue's CHADS2 table and CHA2DS2-VASc table
   define hypertension differently, and Cigna lists CHA2DS2-VASc components without weights.
3. **The score may be an example, not a rule.** Cigna: "high thromboembolic risk (e.g., CHA2DS2-VASc score ≥ 2)".

**Age bands and population splits.**

- Centene sinus surgery: "> 18 years" vs "≤ 18 years", which puts an 18-year-old in the pediatric branch.
- BCBSMA blepharoplasty: an amblyopia pathway at ≤ 9 years.
- Cigna ptosis: a child pathway at ≤ 7.
- Bariatric adolescents: 11-17 at Cigna, 13-17 at Humana; Florida Blue uses Tanner 4-5 instead.
- HGNS Down syndrome pathway: 13-18 at Florida Blue and Cigna, 10-18 at UHC.
- Florida Blue autologous chondrocyte implantation: "Adolescents should be skeletally mature ..." and "Adults should be
  too young to be considered an appropriate candidate for total knee arthroplasty" sit in one ALL list. They are
  population-conditional, not both required.

**Derived negations.**

- Florida Blue sleep testing: "Unattended titration using APAP (E0601) meets the definition of medical necessity only
  when condition A is met and conditions B, C, and D are not."
- The same comorbidity list is a NOT for home testing and a positive for in-lab testing. It is copied six times with
  small drifts.
- Florida Blue lumbar fusion is "experimental or investigational if the sole indication is" disc herniation, so the
  checker must know that no other indication exists.

**Criteria scoped only by indentation.** Florida Blue hip arthroplasty:

> "Advanced joint disease ... AND o Pain or functional disability ... AND o Failure of at least 3 months ... No
> contraindications* to total hip arthroplasty for any indication above are present."

Only indentation shows that the two ANDs belong to the last indication while the contraindication line applies to all.
The same flat OR-then-AND layout appears in knee arthroplasty, cervical fusion and the varicose fixture's indication 4.
There, a flat reading would wrongly require 3 months of compression from an ulcer patient.

**Lead-in vs line-end connectors.** The lead-in sentence ("when ALL of the following ...", "for ONE of the following
...") is the reliable logic marker. The trailing `AND` / `OR` on bullets is redundant at best and wrong at worst:

- Florida Blue RFA of solid tumors: "when either of the following criteria is met: [A]; AND [B]; OR [C]". There are
  three items for "either", and the grouping is ambiguous.
- Florida Blue ICD: the list is headed "meet ONE of the following criteria", but the fifth bullet ends "OR" inside a
  nested list and the sixth has no connector.
- Florida Blue nerve blocks: "Intractable pain at rest, OR / Non-healing ulcers; AND / Severe peripheral artery disease,
  AND / ... OR / Previous revascularization has failed".
- Cigna HBOT: "ALL of the following conditions" over a list where any one condition qualifies.

Profiles flagged AND/OR ambiguity in **137 of 143 documents** (421 instances). This is the most common structural hazard
in the corpus.

---

## 6. Requirement vocabulary

How often each leaf kind appears, across the 143 profiles (a document can have many):

| Leaf kind | Documents | Typical form |
|---|---|---|
| Diagnosis | 102 | "intractable neuropathic pain of the trunk or limbs", "non-valvular AF" |
| Conservative therapy | 86 | "Failure of at least 6 weeks of conservative management that includes at least 2 of ..." |
| Measurement threshold | 83 | "varicosities at least 3 millimeters", "LVEF ≤ 35%" |
| Prior procedure / history | 66 | "previously eliminated (at least 3 months)", "Diagnostic injection provided at least 80% pain relief" |
| Symptom | 62 | "difficulty reading or driving due to redundant skin" |
| Documentation / photos | 56 (+16 "documentation") | "Photographs from the front and side(s)", LOINC document types |
| Imaging finding | 52 | "nerve root compression on MRI or CT-myelogram within the past 6 months" |
| Age | 42 | "≥ 18", "age 18-60", "e.g., age 54 or younger" |
| Provider / facility qualification | 37 | "board-certified sleep physician", "independent radiologist", CMS TAVR volume rules |
| Functional impairment | 33 | "significantly interfere with activities of daily living" |
| Duration (as a standalone leaf) | 25 | "pain for more than 3 months" |
| BMI / comorbidity | 26 | "BMI ≤ 35 kg/m2", "comorbidity refractory to medical management" |
| Lab value | 16 | "HbA1c < 8.1%", "ESR > 30", "total bilirubin above 3 mg/dL" |
| Psych / nutrition evaluation | 13 | "unequivocal clearance ... by a mental health provider" |
| Patient commitment | 11 | "capable of adhering to post-op diet", shared decision-making conversation |
| Site of service | 9 | ASC vs hospital outpatient |
| "Other" | 88 | device/FDA status, intent ("is being considered"), process steps, counts and caps |

The profiles recorded **680 numeric thresholds** in 128 documents and **316 time windows** in 108.

**Typical value ranges.**

- **Conservative care before a procedure.** The most frequent windows are 6 weeks (14 instances) and 3 months (10, plus
  4 "at least 3 months"), then 4 weeks, 30 days, 6 months, 12 weeks and 1 year. By procedure:
  - 4 weeks: epidurals (Florida Blue, UHC, Carelon) and lymphedema pumps (Cigna, BCBSM, MedStar)
  - 6 weeks: discectomy and laminectomy, SI injections, reduction mammaplasty, vertebroplasty, meniscectomy, cervical
    disc arthroplasty
  - 3 months: Florida Blue varicose compression, arthroplasty, Florida Blue facet, panniculectomy skin therapy, knee
    debridement
  - 6 months: lumbar disc arthroplasty; Excellus SCS ("six consecutive months")
  - 1 year: Florida Blue degenerative scoliosis
  - 30 days of wound care: HBOT diabetic foot
- **Composition of conservative care varies more than its length.** For the same epidural, Florida Blue requires
  prescription analgesics AND PT AND behavioral evaluation. UHC accepts any one of three modalities. Carelon wants PT
  plus one complementary therapy. Evolent wants one active plus one inactive modality.
- **Pain and function.**

  | Threshold | Where |
  |---|---|
  | VAS ≥ 4 | Florida Blue discectomy |
  | VAS ≥ 5 | Florida Blue lumbar disc arthroplasty |
  | ≥ 6/10 or "functional deficit" | Florida Blue and Evolent facet |
  | ≥ 3/10 with inability to do 2 ADLs | Carelon |
  | Undefined "moderate-to-severe" | Florida Blue epidural |
- **Response to an injection.**
  - ≥ 50% relief for repeats (near universal)
  - ≥ 80% from a diagnostic block (Florida Blue and Carelon facet)
  - ≥ 75% for surgical-planning SI blocks
  - ≥ 70% for denervation (Evolent)
  - durability of 6 weeks, 2 months or 3 months
- **Body measures.**
  - BMI 35/40 (bariatric), 27.5 for Asian patients at Cigna
  - BMI ceilings 32/35/40 for HGNS
  - BMI < 40 for arthroplasty (BCBSRI, Kaiser)
  - BMI ≤ 30 as a "significant weight loss" marker (Florida Blue and Excellus panniculectomy)
- **Organ function.** LVEF 30/35/40% (ICD); AHI 5/15 with symptoms (OSA), 15-65 or 15-100 for HGNS; HbA1c < 7.5 or
  < 8.1 (arthroplasty).
- **Documentation recency.** Florida Blue's LOINC tables require six months before the date of service. Imaging windows
  are 6 months (Florida Blue discectomy), 9 or 12 months (Carelon laminectomy) and 18 months (Carelon epidural).

**Inclusive vs strict comparisons.** Of 566 thresholds with an explicit operator, 381 are inclusive (≥, ≤) and 185
strict (>, <), about one in three. Payers copy each other's numbers but not their operators (section 8).

**Undefined judgment words.** Words like "significant", "failure" and "adequate" are themselves requirements. Every
profile flagged vague terms: 633 instances across all 143. The most common, by number of documents:

| Term | Documents |
|---|---|
| significant | 43 |
| severe | 35 |
| appropriate | 30 |
| functional | 22 |
| may | 17 |
| adequate | 15 |
| refractory | 13 |
| failed / failure | 25 |
| moderate | 11 |
| chronic | 11 |
| clinically significant | 9 |
| not limited to | 9 |
| optimal | 8 |
| e.g. | 8 |

Typical uses:

- Florida Blue SCS: "used as a last resort"
- Florida Blue cervical: "a dose sufficient to induce a therapeutic response"
- Florida Blue ICD: "the response to optimal medical therapy has been adequately determined"
- HBOT: "adequate course of standard wound therapy"
- "Failure" of conservative care, which no document defines with an outcome measure (Evolent comes closest)

---

## 7. Variance across payers for the same treatment

The same patient often gets different answers. Differences come in three flavours:

- **Thresholds:** the number moves.
- **Composition:** which items, and whether all or any are required.
- **Scope:** which indications exist at all.

The most instructive examples:

| Treatment | Requirement | Florida Blue | Others | Effect |
|---|---|---|---|---|
| Varicose veins | Conservative care | 3 months of compression, only for the symptom indication; ulcer, bleeding and thrombophlebitis need none | BCBSRI: 6 weeks of any conservative therapy (exercise, weight loss count) for every indication | 8 weeks of stockings: RI approves, FL does not. Active ulcer without compression: FL approves, RI does not |
| Bariatric surgery | BMI | ≥ 40, or 35-39.9 with a comorbidity "refractory to medical management"; T2DM at BMI < 35 investigational | Cigna ≥ 35 alone (27.5 Asian); 30-34.9 with a comorbidity. Humana: 30-34.9 with uncontrolled T2DM | BMI 37 with no comorbidity: Cigna yes, FL no. BMI 32.8 with T2DM: Cigna and Humana yes, FL no |
| Hypoglossal nerve stimulation | BMI / AHI | BMI ≤ 35; AHI 15-100 | UHC ≤ 40; Cigna Inspire ≤ 40, Genio ≤ 32; Kaiser < 35 and AHI 15-65 | BMI 37: UHC and Cigna yes, FL and Kaiser no. AHI 80: Kaiser no |
| Epidural steroid injection | Repeat injection | ≥ 50% relief or functional improvement, no duration; cap 6 per region per year (plus 8 per code family) | UHC and Carelon: ≥ 50% for ≥ 3 months, cap 4; Evolent ≥ 30% in the initial phase, ≥ 50% for 2 months later | 60% relief lasting 6 weeks: FL and Evolent yes; Carelon no; UHC's two branches (≤ 50% under 3 months, ≥ 50% for 3+ months) cover neither |
| Facet injection / medial branch block | Pain, care, diagnostic response | ≥ 6/10 or functional deficit; 3 months of unspecified conservative care; ≥ 80% diagnostic relief before a therapeutic injection | Carelon ≥ 3/10 + 2 ADLs, 6 weeks of PT plus one other therapy, therapeutic intra-articular generally not medically necessary; Evolent ≥ 50% | Medications only for 3 months: FL yes, Carelon and Evolent no |
| ICD (primary prevention) | LVEF, NYHA | ≤ 35%; nonischemic cardiomyopathy has no NYHA or age requirement | BCBSM prints "< 35%" (and "≤ 35%" elsewhere in the same document); Carelon ≤ 35%; all others need NYHA II-III for nonischemic | LVEF exactly 35%: BCBSM no. Nonischemic at NYHA I: FL only |
| LAA closure | Stroke and bleeding scores | CHADS2 ≥ 2 OR CHA2DS2-VASc ≥ 3, AND HAS-BLED ≥ 3 | Cigna CHA2DS2-VASc ≥ 2 plus a "nonreversible" anticoagulation contraindication; BCBSM, BCBSRI and LHCC give no cutoffs | CHA2DS2-VASc 2 with recurrent duodenal ulcers: Cigna yes, FL no |
| TAVR | Severity, valve anatomy | AVA ≤ 1.0 cm², mean gradient ≥ 40; bicuspid excluded; valve-in-valve has no STS cutoff | Healthy Blue LA AVA ≤ 0.8, gradient > 40, age/risk rule; UHC and Healthy Blue valve-in-valve need STS ≥ 8% | Bicuspid at 72: UHC and Healthy Blue yes, FL no. Valve-in-valve at STS 5%: FL yes, others no |
| Knee arthroplasty | Imaging, risk gates | Any single imaging finding; any 1 of 8 conservative modalities; no BMI, A1c or tobacco rule | BCBSRI: BMI < 40, A1c < 8.1, 4 weeks tobacco-free (hard). Kaiser: K-L grade 3-4, A1c < 7.5, PT sessions | BMI 44, smoker, A1c 9.0: FL yes, BCBSRI no |
| Blepharoplasty | Visual field | Untaped ≤ 20° AND taped gain ≥ 30% | BCBSMA gain ≥ 20° OR field within 30° of fixation; Emblem within 30° plus ≥ 12° gain; Cigna loss ≥ 20° or 30% | 28° untaped, 42° taped: BCBSMA and Emblem yes, FL no |
| HBOT | Indication scope | Central retinal artery occlusion not listed (closed world means investigational); any acute burn; sudden hearing loss with no time limit | Six payers cover CRAO; Cigna covers burns only inpatient, BCBSTX 15-90% of body surface; Cigna 4 weeks and Medica 2 weeks for hearing loss | CRAO: FL no, most others yes. Outpatient 8% burn: FL yes, Cigna and BCBSTX no |
| Reduction mammaplasty | Symptoms, resection weight | 2 of 7 symptoms; ≥ Schnur 22nd percentile, no alternative route | Cigna 1 symptom, Schnur OR > 1 kg; BCBSMA ≥ 500 g OR Schnur; TX needs ADL interference and age ≥ 18 | One symptom: Cigna yes, FL no. BSA 2.0 with 600 g: BCBSMA yes, FL no |
| Sleep testing | Epworth, home-test bar | Epworth ≥ 10; no BMI bar to home testing | BCBSM and Blue Shield CA Epworth > 10; UHC BMI ≥ 50 means in-lab study; BCBSM BMI > 33 and bicarbonate > 28 | Epworth exactly 10: FL yes, BCBSM no. BMI 52: UHC allows in-lab study, FL requires a home test |
| Vertebroplasty | Time | Failed conservative care for **at least** 6 weeks | UHC: **within** 4 months of onset (a maximum, not a minimum) | A 7-month-old fracture: FL yes, UHC no |

**Where Florida Blue sits.** Florida Blue is neither the strictest nor the most lenient payer. Its pattern is consistent:

- **Stricter than its peers:**
  - some single hard numbers: HGNS BMI 35, a 3-month compression trial, an 80% diagnostic facet block, 2 of 7 breast
    symptoms, a bicuspid exclusion, a 1-year wait for degenerative scoliosis
  - closed indication lists in HBOT
  - "all of" conservative-therapy menus for spine and unicompartmental knee replacement
- **Looser than its peers:**
  - it has none of the patient-optimization gates that newer policies add (BMI, A1c, tobacco for joint replacement)
  - repeat injections need no relief duration
  - several devices have no conservative-therapy duration (pneumatic pumps, SCS)
  - a few indications are accepted with only a clinician's "high risk" statement (ICD channelopathies, sarcoid)

Because Florida Blue derives from BCBSA reference text, it usually agrees with the other Blues on structure and differs
on one or two numbers. UHC and Cigna are where the structural differences live.

---

## 8. Problematic features, ranked by how badly they would hurt the checker

"Hurt" here means producing a confident wrong answer, not merely an INSUFFICIENT.

1. **Criteria delegated outside the document.**
   - *Example:* UHC varicose: "refer to the InterQual® Client Defined CP ..."; Fallon ICD; CareSource PAP.
   - *Frequency:* 16 profiles score 5, of which 14 have no criteria at all. Ten of 19 UHC documents. Every Florida Blue
     document delegates FEP/SAO and, implicitly, MA.
   - *Consequence:* the structurer will invent a tree from definitions or background. UHC's orphan "3 mm" and "0.5 s"
     definitions, or BCBSM's Description sentence "when conservative therapies or CPAP have failed", would become
     requirements that no rule states.
   - *Mitigation:* a document-level outcome **"criteria are not in this document"**, naming the target (InterQual
     product, MCG guideline, NCD/LCD number). The structurer should be allowed, and encouraged, to return it.
2. **AND/OR scope carried by indentation, and line-end connectors that contradict the lead-in.**
   - *Example:* Florida Blue hip, knee and cervical fusion; varicose indication 4; nerve blocks "OR ... AND ... AND ...
     OR".
   - *Frequency:* 137 of 143 profiles, 421 instances.
   - *Consequence:* a structurally wrong tree that still compiles and looks plausible. An ulcer patient fails for lack of
     compression; a contraindication list applies to only one branch.
   - *Mitigation:*
     - Read logic from lead-in quantifiers.
     - Rebuild indentation from PDF x-coordinates rather than text.
     - Keep `compare_guideline.py`-style human review for every new guideline.
     - Add tests where a branch-scoped AND matters (the ulcer case).
3. **Line-of-business mixing in one file.**
   - *Example:* Florida Blue Program Exceptions (FEP/SAO/MA); BCBSRI writes the criteria twice (MA and commercial);
     BCBSM panniculectomy reproduces the LCD inside the commercial policy with different timing (3 months / 6 months
     stable); Independent Health's criteria sit under a "Self-Funded:" heading; Evolent ticks line-of-business boxes;
     Fallon covers substernal ICDs for Medicare but not MassHealth.
   - *Frequency:* every Florida Blue document; among the others, BCBSRI, BCBSM, Independent Health and Fallon each mix two lines of business in one file.
   - *Consequence:* the right tree applied to the wrong member, or two sets merged into one tree.
   - *Mitigation:* a line-of-business gate before the Position Statement (section 9), and per-line criteria sets when a
     document has two.
4. **Criteria living outside the criteria section.**
   - *Examples:*
     - Reimbursement caps: 10+ Florida Blue documents.
     - Definitions: Epworth ≥ 10 (PAP), "Nonhealing" (bio-skin), the DBS 3-month duration.
     - Notes: Florida Blue TAVR severity "see notes below"; the HBOT Wagner scale in a footnote.
     - Footnotes: the Florida Blue epidural conservative-care definition, the facet "Pain assessment ... at baseline,
       and after each injection".
     - Policy Guidelines (Excellus' six-month duration, Blue Shield CA HSAT-first rule).
     - Background: Evolent defines "Conservative treatment*" pages after using it.
     - Medica PAP: AHI thresholds in the Description.
   - *Frequency:* 114 of 143 profiles flag definitions that change meaning; 42 flag footnotes.
   - *Consequence:* a tree that is too lenient, with missing leaves.
   - *Mitigation:* the structurer reads Definitions, Notes, footnotes and Reimbursement as criteria sources and tags each
     leaf with its source section. A per-guideline checklist asks "did you look at Reimbursement?".
5. **Redline PDFs.**
   - *Example:* Carelon spine: "within the past 126 months" is "6" deleted and "12" inserted; "may be is performed";
     "indicating suggesting". Healthy Blue LA TAVR: "Age 65 years or older with Lowany open surgical risk". Carelon
     facet: "Effective Date: 04/14/2024 04/09/2023", "© 20243". LHCC: "06/2307/24".
   - *Frequency:* 9 profiles (four Carelon files, Evolent knee, LHCC, Healthy Blue LA, two Blue Shield CA appendices).
     None are Florida Blue.
   - *Consequence:* the wrong number, invisibly. Any number in a redlined section could be the deleted value.
   - *Mitigation:* detect and refuse. Signals:
     - two dates on one effective-date line
     - fused digits ("20243", "126 months")
     - fused words that are not in a dictionary
     - a policy history that contradicts the body

     Ask for the clean copy, or read strike and underline colours from the PDF.
6. **Vague terms and judgment leaves.**
   - *Example:* "used as a last resort", "considered to be at high risk for sudden cardiac death", "adequate course of
     standard wound therapy", "subject to the judgment of the transplant center", "case by case".
   - *Frequency:* all 143 documents (633 instances).
   - *Consequence:* inconsistent MET/NOT_MET between runs, or the model accepting a bare clinician assertion.
   - *Mitigation:* tag a leaf as `judgment` in the tree. Such a leaf can be MET only by an explicit clinician statement
     in the chart. Otherwise it is INSUFFICIENT, and the ask quotes the guideline's words.
7. **Boundary operators drifting.**
   - *Examples:*
     - LVEF: BCBSM "< 35%" in one bullet and "≤ 35%" in another, against Carelon's "≤ 35%" in near-identical text.
     - Epworth "≥ 10" (Florida Blue) vs "> 10" (BCBSM).
     - TAVR gradient "≥ 40" vs "> 40".
     - CPAP use "≥ 4 h" (Florida Blue) vs "> 4 hours" (Cigna).
     - Kaiser "BMI < 40: if BMI is > 40" leaves exactly 40 uncovered.
     - UHC's epidural branches leave 60%-for-6-weeks uncovered.
   - *Frequency:* about one threshold in three is strict. Exact-boundary values are common in charts (LVEF 35, Epworth
     10).
   - *Consequence:* wrong answers at boundaries.
   - *Mitigation:* store the operator exactly as printed, never normalise it, and test at the boundary values.
8. **Stacked document copies and duplicated blocks.**
   - *Examples:*
     - Evolent knee: 84 pages holding a redline plus two final copies, which differ.
     - Blue Shield CA: Appendix A before/after tables.
     - Evolent pain: CG 1750 and 1751 repeat the same indications at different nesting.
     - Carelon: the General Information block repeated 11 times.
     - Florida Blue lumbar: the same conservative-care paragraph five times.
   - *Frequency:* 22 profiles.
   - *Consequence:* duplicate leaves, or the old version's criteria read as current.
   - *Mitigation:* detect repeated blocks and take the final copy. Treat "Appendix", "redline" and "before/after" as
     non-criteria.
9. **Typos and internal contradictions.**
   - *Examples:*
     - Florida Blue lumbar disc arthroplasty requires degeneration "at a single level" and later allows "one or two
       consecutive levels".
     - BCBSMA lists "progressive neurological deficit" as investigational and also uses it as a bypass.
     - Blue Shield CA knee: requires OA but its acute-event exception applies "in the absence of osteoarthritis".
     - Florida Blue ICD: "explanation" for "explantation".
     - Independent Health TAVR: a truncated list ("1. inoperable ...; or" with no item 2).
   - *Frequency:* 27 profiles flag typos; most treatment reports found at least one internal contradiction.
   - *Consequence:* an unsatisfiable or ambiguous leaf.
   - *Mitigation:* the structurer flags contradictions as a guideline-level review reason ("this guideline contradicts
     itself on X"). It must not silently pick one reading.
10. **Code lists inconsistent with the criteria.**
    - *Examples:*
      - Florida Blue intracranial endovascular tags 61630 and 61640-61642 investigational but not 61635, although the
        text calls the same therapy investigational.
      - Healthy Blue lists 33370 (cerebral protection) as potentially medically necessary while UHC and Florida Blue
        call it unproven.
      - Codes with no criteria at all: Florida Blue varicose S2202 and 37785.
      - Codes that mean different procedures under one number: diagnostic vs therapeutic facet.
      - ICD "support" lists with oddities: Florida Blue epidural lists Z79.01 (anticoagulant use) and a range typo
        "M51.14 - M54.17"; Florida Blue facet lists shoulder pain codes.
      - "Codes may not be all inclusive."
    - *Consequence:* the code gate says covered while the text says investigational, or the reverse.
    - *Mitigation:* treat code tags as one signal and the Position Statement as authority. Surface disagreements as a
      review reason. **Never infer criteria from ICD support lists.**
11. **Stale, future-dated or wrong documents.**
    - *Examples:* the Cigna 0158 and 0551 mis-files; BCBSTX's end date of 12/31/2025; BCBSRI 2019/2020; the metadata
      mismatches listed in section 1. Florida Blue headers where `Revised` predates `Reviewed` (frenectomy). Dates up to
      10/01/26, which is current here; BCBSM LAA was "effective 11/1/26" at retrieval.
    - *Consequence:* checking against the wrong rules.
    - *Mitigation:* take dates from the printed header and compare them to the update log. Show "version effective
      <date>" on every result. Reject documents whose title does not match the requested procedure; `verify_guideline`
      already does part of this.
12. **Private-use bullet glyphs.**
    - *Example:* Florida Blue bullets are U+F0B7, a private-use character that prints as nothing, or U+2022, sometimes
      mixed in one file. Second levels are a literal `o` or U+2212 `−`.
    - *Frequency:* private-use characters in 100 of 205 texts, 54 of them Florida Blue.
    - *Consequence:* lost list structure and merged bullets.
    - *Mitigation:* normalise the glyphs before structuring. Do not use them for depth.
13. **Homoglyphs in Florida Blue text.**
    - *Example:* Cyrillic and Greek look-alike letters inside English words: "vеrtеbrοplаstу", "hеаԁаchе", "VΝЅ",
      "kеrаtοϲoոսs", "RСC", "arrhуthmias".
    - *Frequency:* mixed-script words in 9 Florida Blue documents (nerve blocks 19 words, vertebroplasty 17, VNS 14,
      endothelial keratoplasty 6; single words in five more). **None are inside a Position Statement.** They sit in
      Description evidence quotes and references.
    - *Consequence:* low for criteria. They break text search and deduplication, and could slip into a label if a
      Description sentence were ever quoted.
    - *Mitigation:* NFKC normalisation plus a confusables map (Cyrillic а, е, о, р, с, у, Greek ο, Ν) before any string
      matching.

---

## 9. Implications for the checker's design

The current design is sound for the varicose fixture. The question is what breaks first as more guidelines arrive. The
recommendations below are grouped by whether **Florida Blue needs them** or only **generalising to other payers** needs
them.

### Required for Florida Blue

1. **A line-of-business gate before the Position Statement.** Every Florida Blue document says FEP and SAO "Follow
   ... guidelines" and names an NCD or LCD for MA. Make this a structured field on the guideline:
   `program_exceptions: {FEP: "delegated", SAO: "delegated", MA: {ncd/lcd ids, host}}`. Decide applicability from the
   order's plan type before judging:
   - FEP or SAO gives "this guideline doesn't apply" (it names the FEP or SAO rules).
   - MA with a named LCD gives "this guideline doesn't apply; Medicare Advantage follows LCD L38720".
   - MA with "no NCD/LCD found" proceeds, with a review reason saying the inference is unstated.

   The fixture already records the MA routing in `notes`; promote it to data.
2. **A guideline-level "investigational for all indications" outcome.** One in four surveyed Florida Blue documents is
   blanket investigational. Today `scope_gate` works per CPT. Add a guideline flag so these produce NOT_COVERED with no
   judge call, even when the code table lacks tags. Breast ductoscopy, for example, has no CPT code at all and uses the
   unlisted 19499.
3. **A closed-world default as an explicit rule.** "Considered experimental or investigational for all other
   indications" means a request that matches no pathway is a decision ("not covered as requested"), not INSUFFICIENT.
   Store it as a guideline flag and make the routing explicit. Indication-list documents (HBOT, SRS, transplant) depend
   on it. For example, HBOT for retinal artery occlusion is not a missing-evidence case.
4. **Treat Definitions, Notes, footnotes, Reimbursement and LOINC as criteria sources.**
   - Each leaf carries `source_section`.
   - Frequency caps from Reimbursement become a separate leaf class, `utilization_limit`, that counts prior services.
   - The LOINC six-month window becomes a recency rule on cited evidence. Code can check it from span dates, as
     `_check_duration` already does for durations.
5. **Read logic from lead-in quantifiers, not glyphs or line ends.** Put it in `prompts/structure_guideline.md`:
   - "ALL", "ONE", "at least N", "either", "both" in the lead-in decide the node.
   - Trailing AND/OR are checked against it, and a disagreement is reported, not resolved silently.
   - Indentation should come from PDF coordinates where available.
6. **A k-of-n node.** `{"type": "k_of", "k": 2, "children": [...]}`:
   - **MET** if at least k children are MET.
   - **NOT_MET** if MET plus INSUFFICIENT is less than k.
   - **INSUFFICIENT** otherwise.

   Confidence needs a rule. For MET, take the product of the k most confident MET children. "Misses" means the cheapest
   set of k − (#MET) INSUFFICIENT children. Florida Blue needs this node in six documents (reduction mammaplasty,
   cervical, lumbar, hip arthroscopy, knee arthroscopy, SI fusion). Expanding into `any` of combinations is not a good
   substitute: 21 branches for 2 of 7.
7. **History and prior-episode leaves that default to INSUFFICIENT with a precise ask.** Mark leaves as
   `history: true`. Examples:
   - prior injection relief percentage and duration
   - prior procedure date and outcome
   - injection count in a rolling window
   - weight stable for N months

   The judge must find a dated statement or return INSUFFICIENT. The ask names exactly what is needed: "date and percent
   relief of the last epidural injection". For first-time requests, the structurer must state whether a "subsequent"
   leaf applies, so that the facet case does not hit a vacuous leaf.
8. **Scenario selection by procedure, with mode.** Florida Blue facet and epidural (diagnostic, therapeutic,
   maintenance), knee arthroscopy (about 17 procedure blocks) and spine (5 families) all need the order's procedure
   text, not just the CPT, to pick the pathway. Let `detect_order` extract the mode (diagnostic vs therapeutic,
   initial vs repeat, levels, laterality). Let the guideline map pathways to procedure descriptions as well as codes.
9. **Score and computed leaves.** CHADS2, CHA2DS2-VASc, HAS-BLED, CEAP, Schnur by BSA, Wagner and NYHA appear in Florida
   Blue documents. Within "the model types no numbers":
   - a stated score in the chart is evidence, through the quoted span
   - a missing score is INSUFFICIENT with the ask "document the CHA2DS2-VASc score"

   Optionally, code computes the score from component leaves, each with a quote, using the guideline's own table. Store
   the guideline's table in the JSON; Florida Blue's tables differ from the textbook.
10. **Operators exactly as printed, with boundary tests.** The fixture's `{"op": "gte"}` is right. Add tests at exact
    boundaries (LVEF 35, Epworth 10, gradient 40).
11. **Order-level and intent leaves.** Some leaves are about the planned procedure, not the patient:
    - "performed with fluoroscopic guidance"
    - "not performed concurrently with superficial venous surgery"
    - "anterior retroperitoneal approach"
    - "FDA-approved device"
    - "discontinuation of anticoagulation is being considered"

    Mark them `order_attribute` and check them against the order or a surgeon attestation, not the chart. Otherwise they
    are always INSUFFICIENT and generate noise asks.
12. **Population-conditional pathways.** Adolescent vs adult (autologous chondrocyte implantation, bariatric), pediatric
    vs adult (ICD, sleep, PAP) and Down syndrome (HGNS) should be separate scenarios keyed by age, not leaves in one
    `all`.
13. **Contradiction and version review reasons.** A guideline that contradicts itself (lumbar 1 vs 2 levels), or whose
    `Revised` date disagrees with its update log, gets a review reason at ingest that is shown with every result.

### Needed to generalise beyond Florida Blue

14. **A "delegated: criteria not in this document" outcome.** It should name InterQual, MCG or the NCD/LCD. This is the
    right answer for 14 of 88 non-Florida-Blue documents and for most UHC files. It should look like NOT_APPLICABLE ("this
    guideline doesn't decide; it points to X"), not like a failed check.
15. **Redline and stacked-copy detection at ingest.** Refuse, or require a clean copy, when the signals in section 8
    fire.
16. **General-requirements inheritance.** For Carelon and Evolent, model a shared preamble node that every pathway
    includes, with explicit override when a specific block says otherwise ("PT optional", "waived").
17. **Staged and stateful criteria.** Evolent's initial and therapeutic phases, PAP day 31-91 adherence, SCS trial then
    permanent, and new-episode resets after 12 months or 2 years. Represent the stage as an input from the order ("this
    is injection 3 in the initial phase") with per-stage trees.
18. **Open lists.** "including but not limited to" becomes an `any` with an extra "other, clinician-justified" leaf.
    That leaf can only be MET by explicit justification and never makes the parent NOT_MET.
19. **Quantifier sanity checks.** Flag "ALL of the following" over lists of alternative diagnoses (Cigna HBOT). Flag
    "either" over three items.
20. **Facility and provider leaves.** CMS TAVR volumes, independent radiologist, board-certified reader and lymphedema
    specialist are provider-registry facts. Treat them like order attributes.
21. **Prior-auth-not-required flag.** Medica and Independent Health review after the service. The checker can still
    run, but "ready to submit" should read "meets criteria (retro review)".
22. **Per-line-of-business criteria sets inside one document.** Needed for BCBSRI and BCBSM.

**What not to change.** Several current decisions are vindicated by this corpus:

- **"Labels are the guideline's own words."** Vague terms and odd operators survive intact.
- **"The coordinator picks the guideline".** Lines of business and delegation make automatic matching unsafe.
- **"Silence is INSUFFICIENT".** History leaves would otherwise be NOT_MET.
- **The judge returns no numbers.** Score and duration leaves are where a typed number would drift.

---

## 10. A test-set plan

Fifteen documents and scenarios, chosen so that each exercises one construct or hazard. Charts are invented from the
workers' test cases. For each, write one chart per expected outcome and run it twice.

| # | Document (`sourcing/library/<treatment>/...`) | Scenario | Expected | Tests |
|---|---|---|---|---|
| 1 | `varicose-veins/bcbsfl-02-33000-31-...` (fixture) | Active venous ulcer (C6), GSV reflux, 6 mm, no compression trial | MET | `all` containing `any`; compression is only inside indication 4 |
| 2 | same | C3, daily aching, GSV 7 mm, 8 weeks of 20-30 mmHg stockings | NOT_MET / ask for 4 more weeks | Duration computed from dated notes |
| 3 | `epidural-injections/bcbsfl-02-61000-31-...` | L5 radiculopathy, OTC ibuprofen + home exercise for 6 weeks, MRI root compression | INSUFFICIENT/NOT_MET on Rx analgesic and PT legs | Footnote-defined conservative care; composition vs duration |
| 4 | `facet-joint-injections/bcbsfl-02-61000-30-...` | First therapeutic intra-articular injection after one MBB with 85% relief | MET, with "subsequent" leaf N/A | First-time vs repeat; ≥ 80% history leaf |
| 5 | `lumbar-spine-surgery/bcbsfl-02-20000-48-...` | L5-S1 herniation, VAS 6, 8 weeks of NSAIDs + gabapentin + ESI, no PT, no reason given | NOT_MET (PT leg) | Composition; Carelon would approve. Also a 2-level disc arthroplasty request → review (internal contradiction) |
| 6 | `sleep-testing/bcbsfl-01-95828-01-sleep-testing` | Epworth exactly 10, loud snoring, BMI 27, home test requested | MET | Inclusive boundary; category A and B logic |
| 7 | same | BMI 52, witnessed apneas, bicarbonate 25, in-lab study requested | NOT_MET (home test expected) | Derived negation; comorbidity list as NOT vs positive |
| 8 | `sleep-apnea-surgery/bcbsfl-02-40000-16-...` | HGNS: AHI 38, BMI 37, central 8%, CPAP residual AHI 22, DISE no concentric collapse | NOT_MET (BMI ≤ 35) | Threshold; also AHI 11 home test + HTN for UPPP → MET via the Definitions-held "clinically significant OSA" |
| 9 | `icd/bcbsfl-02-33000-34-...` | Ischemic CM, MI 8 months ago, NYHA II, LVEF exactly 35% | MET | Boundary; run the same chart against `bcbsm-implantable-cardioverter-defibrillators` → NOT_MET on "< 35%" |
| 10 | `laa-closure/bcbsfl-02-33000-36-...` | AF, HTN + DM, age 70 (CHADS2 2, CHA2DS2-VASc 3), HAS-BLED 2 | NOT_MET on HAS-BLED | Score leaves; OR between two scores; computed vs stated |
| 11 | `reduction-mammaplasty/bcbsfl-02-12000-11-...` | BSA 1.80, upper back pain only, 10 weeks of bra + NSAIDs, 450 g planned | NOT_MET (1 of the "AT LEAST TWO") | k-of-n node; Schnur table from Reimbursement |
| 12 | `knee-arthroscopy/bcbsfl-02-20000-65-...` | Acute bucket-handle tear, locked knee, K-L 0, no therapy yet | NOT_MET (6 weeks required) | Procedure-to-pathway selection; 2-of-6 menu |
| 13 | `tavr/bcbsfl-02-33000-32-...` | Bicuspid valve, velocity 4.6, NYHA III, age 72 | NOT_MET | `not` leaf from an inline exclusion; also mean gradient exactly 40 → MET |
| 14 | `hyperbaric-oxygen/bcbsfl-01-99180-01-...` | Retinal artery occlusion within 6 hours | Not covered (closed world) | Indication-list document; not-listed is a decision. Also diabetic foot Wagner 3 at 21 days → NOT_MET |
| 15 | `hip-arthroplasty/bcbsfl-02-20000-50-hip-arthroplasty` | Bone-on-bone OA, BMI 43, A1c 8.6, smoker, 4 months of NSAIDs + PT | MET | Footnote contraindications scoped to all branches; absence of optimization gates |

Add four document-level controls that need no chart:

- `subtalar-arthroereisis/bcbsfl-02-99221-17-...` must produce the blanket investigational outcome with no judge call.
- `balloon-sinuplasty/bcbsfl-02-31000-01-...` must produce "no clinical criteria in this guideline (payment/bundling
  rule)".
- `varicose-veins/uhc-2026t0447ss-...` must produce "delegated to InterQual".
- `epidural-injections/carelon-msk-interventional-pain-management.pdf` must be refused or flagged as a redline at ingest.

Cross-payer pairs worth keeping for regression, all from the reports:

- varicose: Florida Blue vs BCBSRI on the ulcer and 8-week cases
- epidural: Florida Blue vs UHC on the 60%-for-6-weeks case
- ICD: Florida Blue vs BCBSM at LVEF 35
- HGNS: Florida Blue vs UHC at BMI 37
- TAVR: Florida Blue vs UHC on bicuspid

They show that the same chart flips with the guideline, which is the property the product depends on.

---

## 11. Glossary

**Process and documents**

- **Medical policy / coverage policy / medical coverage guideline:** the payer's statement of when a service is
  medically necessary. Florida Blue calls them MCGs (Medical Coverage Guidelines). Not to be confused with MCG Health.
- **Prior authorization (PA, preauthorization, precertification):** asking the payer to agree before the service.
  **Retro(spective) review:** checking afterwards.
- **Utilization management (UM):** the payer's review function. It is often delegated to vendors.
- **Medical necessity vs benefit:** the policy decides necessity; the member contract decides whether the benefit
  exists.
- **Experimental / investigational (E/I), unproven, not medically necessary (NMN):** the payer's "no" categories.
  Florida Blue uses E/I for unproven technology and "does not meet the definition of medical necessity" for cosmetic or
  out-of-scope requests.
- **Cosmetic vs reconstructive / functional:** the core distinction for plastic surgery policies.
- **Step therapy:** requiring cheaper treatments first. Florida law 627.42393 allows exemptions.
- **Site of service:** where a procedure is done (hospital outpatient, ASC, office). It is sometimes reviewed
  separately.
- **Peer-to-peer:** the treating physician talks to the payer's reviewer after a non-approval.
- **Redline:** a document version showing deletions struck through and insertions underlined. When extracted to text,
  both appear.
- **Homoglyph:** a look-alike character from another alphabet, such as Cyrillic "а" for Latin "a".

**Payers, programs and lines of business**

- **Commercial, Exchange, Individual, Self-funded / ASO:** employer and individual plans. ASO plans are run by the payer
  but paid for by the employer, and may use their own plan documents.
- **Medicare Advantage (MA, Part C):** private plans replacing traditional Medicare; bound by NCDs and LCDs.
- **Medicaid:** state program, usually run through managed-care plans (MCOs). **MMP** is Medicare-Medicaid Plan; in UHC
  file names "MMP" is a policy prefix.
- **FEP:** Federal Employee Program, the Blue plan for federal employees with its own national policies.
- **SAO:** State Account Organization, Florida Blue's state-employee accounts with their own guidelines.
- **BCBSA:** Blue Cross Blue Shield Association. Its reference medical policies (e.g. 7.01.124) underlie many Blue
  plans' text.
- **WHCRA:** Women's Health and Cancer Rights Act of 1998, which mandates reconstruction and symmetry after mastectomy.
- **EPSDT:** Medicaid's pediatric benefit (Early and Periodic Screening, Diagnostic and Treatment).

**CMS**

- **NCD:** National Coverage Determination, a national Medicare rule (e.g. NCD 20.4 for ICDs).
- **LCD:** Local Coverage Determination, written by a MAC for its region (e.g. L38720 for varicose veins). An **LCA**
  (article) carries the billing and coding detail.
- **MAC:** Medicare Administrative Contractor. Florida's is **First Coast Service Options (FCSO)**. Others include
  Palmetto, Novitas, Noridian, WPS and CGS.
- **TVT Registry:** the national TAVR registry referenced by CMS volume rules.

**Vendors and criteria sets**

- **InterQual:** proprietary, licensed criteria (Optum/Change Healthcare). UHC points to it; "Client Defined" means a
  UHC-customised subset.
- **MCG:** proprietary, licensed criteria (MCG Health, formerly Milliman Care Guidelines). CareSource and Kaiser
  reference it.
- **Carelon:** Elevance's benefits-management vendor, formerly AIM Specialty Health.
- **Evolent:** formerly NIA (National Imaging Associates).
- **eviCore:** Cigna/Evernorth's vendor. Not in this corpus.
- **UHMS:** Undersea and Hyperbaric Medical Society, whose indication list Medica adopts for HBOT.

**Codes**

- **CPT:** procedure codes (e.g. 36475). **HCPCS Level II:** supplies, devices and some services (e.g. E0601 CPAP,
  S2202, G0277). **Category III (e.g. 0524T):** emerging-technology codes, often investigational.
- **ICD-10-CM:** diagnosis codes (e.g. I83.001-I83.899). **ICD-10-PCS:** inpatient procedure codes (e.g. 0RR30JZ).
- **LOINC:** observation and document codes. Florida Blue uses them in documentation tables (e.g. 28626-0, history and
  physical; 18805-2, time frame).

**Clinical terms by specialty**

- **Veins:** CEAP (Clinical-Etiology-Anatomy-Pathophysiology) class C0-C6 for venous disease. C2 is varicose veins,
  C3 edema, C4 skin changes, C5 healed ulcer, C6 active ulcer. GSV/SSV are the great and small saphenous veins.
  RFA/EVLA are radiofrequency and laser ablation. MOCA is mechanochemical ablation.
- **Sleep:**
  - AHI (apnea-hypopnea index, events per hour of sleep), RDI (respiratory disturbance index) and REI (respiratory event
    index, used for home tests).
  - ESS: Epworth Sleepiness Scale, 0-24.
  - PSG (in-lab polysomnography), HSAT (home sleep apnea test), MSLT/MWT (daytime sleepiness and wakefulness tests).
  - CPAP/APAP/BiPAP: positive airway pressure devices.
  - HGNS: hypoglossal nerve stimulation (e.g. Inspire). DISE: drug-induced sleep endoscopy. UPPP:
    uvulopalatopharyngoplasty.
- **Cardiac:**
  - NYHA class I-IV (heart-failure symptoms), LVEF (left ventricular ejection fraction), GDMT (guideline-directed
    medical therapy).
  - ICD / S-ICD / EV-ICD: transvenous, subcutaneous and extravascular defibrillators. CRT-D: resynchronization with a
    defibrillator.
  - TAVR (transcatheter aortic valve replacement), AVA (aortic valve area), STS score (surgical mortality risk).
  - LAA: left atrial appendage. CHADS2 and CHA2DS2-VASc (stroke risk in AF), HAS-BLED (bleeding risk).
  - MCOT (mobile cardiac telemetry), ILR (implantable loop recorder). CCS class: angina severity.
- **Spine and pain:**
  - ESI (epidural steroid injection), MBB (medial branch block), RFA (radiofrequency ablation) or RFN (radiofrequency
    neurotomy).
  - VAS: pain score, 0-10 or 0-100. ODI/NDI: Oswestry and Neck Disability Index. ADL/IADL: (instrumental) activities of
    daily living.
  - HEP: home exercise program.
  - FBSS: failed back surgery syndrome. CRPS: complex regional pain syndrome. SCS (spinal cord stimulation), DRG (dorsal
    root ganglion stimulation).
  - TDA (total disc arthroplasty), CDA (cervical disc arthroplasty).
  - Cobb angle (scoliosis), SVA (sagittal vertical axis), Meyerding and Wiltse (spondylolisthesis grade and type).
- **Joints:** K-L (Kellgren-Lawrence) grade 0-4 for osteoarthritis on X-ray; Outerbridge grade I-IV for cartilage on
  arthroscopy or MRI; Tönnis grade 0-3 for hip osteoarthritis; UKA/TKA for unicompartmental and total knee
  arthroplasty.
- **Wounds and plastics:**
  - Wagner grade 0-5 for diabetic foot ulcers. HBOT: hyperbaric oxygen therapy; ATA: atmospheres absolute.
  - Schnur sliding scale: minimum breast resection weight by body-surface area (BSA, via the Mosteller formula).
  - ASPS pannus grade 1-5.
  - MRD1: margin reflex distance, from the corneal light reflex to the upper lid.
  - Tanner stage: pubertal maturity, 1-5.
- **General:** BMI (body-mass index), HbA1c (3-month glucose average), ASA class (anesthesia risk), DME (durable medical
  equipment), RUL (reasonable useful lifetime, Medicare's 5-year DME replacement rule).

---

## Appendix: index of the source reports

**Treatment reports** (`sourcing/analysis/treatments/`):

| Report | One-line takeaway |
|---|---|
| `varicose-veins.md` | Florida Blue is the cleanest tree (the fixture); the compression trial sits only inside indication 4; UHC and UHC-MA are pure InterQual/LCD pointers. |
| `bariatric-surgery.md` | BMI cutoffs differ by a full class (40 vs 35 vs 30 + T2DM); Florida Blue adds Tanner staging for adolescents; UHC Ohio is all InterQual. |
| `balloon-sinuplasty.md` | Florida Blue has no clinical criteria, only a bundling rule; the others share a CRS/RARS shape but differ on drug durations (none, 3-4 weeks, 8 weeks). |
| `blepharoplasty.md` | Visual-field thresholds are not comparable across payers; criteria need photographs; Florida Blue's field-test exemption NOTE has ambiguous scope. |
| `cardiac-monitoring.md` | A device ladder (external, MCOT, ILR); "non-diagnostic" and future-intent leaves ("is being considered") are undecidable; Blue Shield CA has a redline appendix. |
| `cervical-spine-surgery.md` | Florida Blue, BCBSIL and BCBSMA disc arthroplasty text is near-identical (BCBSA); Florida Blue fusion grouping is indentation-only; Carelon is a redline. |
| `epidural-injections.md` | Repeat rules dominate; relief durations of 0, 2 or 3 months; UHC's branches leave a gap; caps live in Florida Blue's Reimbursement section. |
| `facet-joint-injections.md` | Florida Blue's 80% diagnostic gate and vacuous "subsequent" leaf; Carelon is a redline; Cigna 0551 is a sedation policy (wrong document). |
| `hip-arthroplasty.md` | Optimization gates (BMI, A1c, tobacco) at BCBSRI and Kaiser, none at Florida Blue; footnote contraindications scoped by indentation. |
| `hyperbaric-oxygen.md` | Indication lists with closed-world defaults; only the diabetic foot has a tree; Florida Blue's 30-treatment cap is in Reimbursement; Cigna's "ALL of" quantifier is inverted. |
| `icd.md` | Near-identical BCBSM and Carelon text with different comparators (< vs ≤); Florida Blue is lenient on nonischemic CM and channelopathies; Fallon delegates entirely. |
| `knee-arthroplasty.md` | Florida Blue accepts one imaging finding and one of eight modalities; BCBSRI has hard BMI/A1c/tobacco gates; the UKA conservative menu is all-of at Florida Blue. |
| `knee-arthroscopy.md` | About 17 procedure blocks with no code-to-block map; the Evolent PDF is three stacked copies; the 2-of-6 therapy menu is k-of-n. |
| `laa-closure.md` | Score leaves (CHADS2 OR CHA2DS2-VASc, HAS-BLED) defined by the policy's own tables; LHCC has an open contraindication list. |
| `lumbar-spine-surgery.md` | Carelon redline ("126 months"); Florida Blue disc arthroplasty contradicts itself on levels; conservative-care composition is the main difference. |
| `panniculectomy.md` | Florida Blue has three alternative symptom routes and a 3-month stable-weight rule against others' 6; BCBSM mixes LCD text into commercial criteria. |
| `pap-devices.md` | Rental-then-adherence staging (4 h / 70% / 30 days, days 31-91); thresholds in Definitions and Description; CareSource and Providence delegate. |
| `pneumatic-compression.md` | Device ladder with cross-references to earlier tiers; Florida Blue has no conservative duration where others need 4 weeks; "failure" is undefined everywhere. |
| `reduction-mammaplasty.md` | Schnur table lookup by BSA; Florida Blue 2-of-7 symptoms; alternative weight routes (500 g, 1 kg) at other payers. |
| `sacroiliac-joint-injections.md` | Provocation-test k-of-n at Blue Shield CA/Evolent and none at Florida Blue; UHC delegates; the Florida Blue cap is in Reimbursement. |
| `sleep-apnea-surgery.md` | HGNS rules are one family with different BMI and AHI ceilings; Florida Blue's OSA severity definitions overlap; the BCBSM file has no criteria. |
| `sleep-testing.md` | Derived negation (APAP only when A and not B, C, D); comorbidity lists copied with drift; Cigna 0158 is the wrong document. |
| `spinal-cord-stimulation.md` | Open vs closed diagnosis lists; trial-then-permanent staging; UHC commercial delegates; Excellus alone has objective CRPS, CLI and angina criteria. |
| `tavr.md` | Severity thresholds and operators differ; Florida Blue alone excludes bicuspid; facility volume leaves (UHC) are not chart facts; the Healthy Blue copy is a redline. |
| `vertebroplasty-kyphoplasty.md` | Minimum (≥ 6 weeks) vs maximum (≤ 4 months) time semantics; homoglyphs in the Florida Blue Description; BCBSTX expired. |

**Florida Blue template surveys** (`sourcing/analysis/bcbsfl/`):

| Survey | One-line takeaway |
|---|---|
| `batch0.md` (29 docs) | Fixed shell with logic only in the Position Statement; lead-in quantifiers are reliable and line-end AND/OR are not; 8 blanket investigational, about 10 real trees. |
| `batch1.md` (29 docs) | Same shell; Reimbursement sometimes holds rules; bullets are private-use glyphs; 8 not-covered-only, 16 with criteria, 4 whitelists, 1 site-of-service rule. |
| `batch2.md` (29 docs) | Verified heading order 29/29; `Revised` is often a coding-only change; caps in Reimbursement; constructs needed: closed-world fallback, lookup tables, population-conditional leaves, claims-history limits, reviewer-discretion leaves. |
