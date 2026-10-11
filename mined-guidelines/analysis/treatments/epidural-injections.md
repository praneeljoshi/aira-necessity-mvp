# Epidural injections: how four payers gate them

Documents profiled (JSON in `sourcing/analysis/profiles/`):

| Payer | File | Version as printed | Size |
|---|---|---|---|
| Florida Blue (client) | `bcbsfl-02-61000-31-epidural-injections.pdf` | Policy 02-61000-31, revised 04/30/25 | 12 pp |
| Carelon (vendor) | `carelon-msk-interventional-pain-management.pdf` | Effective 04/14/2024, REDLINE copy posted by Louisiana Medicaid | 34 pp, epidurals pp.6-12 |
| Evolent (vendor) | `evolent-interventional-pain-management-guidelines.pdf` | CG 1750 and CG 1751, effective July 2026 | 102 pp, two epidural guidelines |
| UnitedHealthcare | `uhc-2026t0616n-epidural-steroid-injections-for-spinal-pain.pdf` | Effective 09/10/2026 (number printed 2026T0616O) | 14 pp, criteria on pp.1-2 |

Version caution: Carelon is a 2024 text; the others are 2025-2026. Differences may partly be age.

## What it is

An epidural steroid injection (ESI) puts corticosteroid, often with local anesthetic, into the epidural space around the spinal nerve roots, by an interlaminar or caudal route (CPT 62320-62323) or a transforaminal route (64479, 64480, 64483, 64484), usually under fluoroscopy. It is used for radicular (leg or arm) pain from disc herniation or stenosis after conservative care has not worked. Payers gate it on five things: (1) radicular pain or radiculopathy rather than axial back pain, (2) a minimum course of conservative care (4 weeks nearly everywhere), (3) imaging (or in one case electrodiagnostic) evidence of nerve root involvement, (4) image guidance, and (5) tight repeat rules: how much relief the last injection gave and for how long, intervals, and yearly caps per spinal region. Because ESIs are repeated, much of each policy is about injection history, not the current visit.

## Side by side

Columns: Florida Blue first. "Not stated" means the document says nothing (not that the payer permits it).

| Requirement kind | Florida Blue | UnitedHealthcare | Carelon | Evolent |
|---|---|---|---|---|
| Structure | One Position Statement: "Diagnostic" list; "Therapeutic and maintenance" list; footnote defining conservative care | One all-of list of 4 criteria + limits block | General requirements + 3 pathways (therapeutic, repeat, diagnostic SNRB) | 4 purposes (acute, stenosis, FBSS/fibrosis, diagnostic) + Initial/Therapeutic phases |
| Clinical picture | "symptoms of radiculopathy" + "Persistent pain of moderate-to-severe intensity" | "Radicular Back Pain, as evidenced by history and physical examination" | Radicular pain, radiculopathy or lumbar neurogenic claudication "with associated functional impairment and completed physical exam" | Acute radicular pain <3 months; or stenosis with axial or radicular pain; or FBSS/epidural fibrosis |
| Pain / function severity | Moderate-to-severe, no number | Not stated | Pain >= 3/10 AND unable to do >= 2 ADLs/IADLs | Pain causing functional disability OR average pain >= 6/10 |
| Imaging | "demonstrated spinal nerve root compression on imaging" (any imaging, no recency) | "structural and/or functional nerve root involvement by imaging or electrodiagnostic studies" | MRI or CT: disc herniation with root compression (within 18 months) OR stenosis; lumbar initial ESI exempt if symptoms/exam "clearly diagnostic"; repeat waives if already met | No imaging criterion |
| Conservative care length | >= 4 weeks | >= 4 weeks | >= 4 weeks (2 weeks if "clear evidence of radiculopathy") | 2 weeks (acute pathway); 6 weeks within last 6 months (stenosis, FBSS) |
| Conservative care content | ALL of: Rx-strength analgesic/anti-inflammatory (or documented intolerance); >= 4 weeks PT incl. active exercise (or documented intolerance); evaluation/management of cognitive and behavioral issues if present | ANY ONE of: NSAID/acetaminophen; activity modification; PT or home exercise | PT (or supervised home program, or documented exception) AND at least one complementary (meds, adjunctive meds, or alternative therapy such as acupuncture, rest) | >= 1 active (PT, supervised HEP, chiropractic) AND >= 1 inactive (meds, injections, TENS/bracing); HEP needs plan plus follow-up on completion |
| "Failure" defined | "not responsive" | "unresponsive" | Completed full course AND worsening/no significant improvement on reevaluation AND more invasive therapy being considered | Meaningful improvement lacking, OR progression, OR documented medical reason unable to participate (office closures, inconvenience, unexplained noncompliance do not count) |
| Guidance | Fluoroscopy required; ultrasound investigational | Fluoroscopy or CT; ultrasound unproven | Fluoroscopy or CT unless contraindicated | Fluoroscopy "necessary" for transforaminal, "should be used" for caudal/interlaminar |
| Per-session limits | <= 2 vertebral levels per date of service | Not stated (cap counts sessions regardless of level) | One region per session; <= 2 transforaminal injections; 1 interlaminar/caudal; no combos with other spine procedures | <= 2 levels of transforaminal blocks per day (diagnostic); multi-region same day needs medical reason |
| Repeat: prior response | >= 50% pain relief OR functional improvement (no duration) | Returned pain/function loss AND either (>= 50% for >= 3 months) OR (<= 50% for < 3 months with reassessment of individual, site and technique) | >= 50% reduction + functional improvement for >= 3 months, imaging still correlates, ongoing conservative care | Initial phase: >= 30% relief or "significant" function; therapeutic phase: >= 50% or function for >= 2 months before each |
| Intervals | Diagnostic >= 7 days; therapeutic >= 14 days; maintenance >= 2 months | Not stated | Second injection after suboptimal response >= 2 weeks | Initial phase >= 2 weeks apart; other regions >= 7 days apart |
| Annual cap | <= 6 per region, rolling 12 months (all types); plus <= 8 per code family per 12 months | <= 4 sessions per region per "year" starting at first approved injection | <= 4 sessions per region, rolling 12 months; one extra one-time second injection exempt | Year 1: 6 per region (3 initial + 3 therapeutic); after: 4 per 12 months; 6 if special circumstances |
| New episode | Not stated | Not stated | Last injection >= 12 months ago = new (initial) | >= 2 years since last in region, or surgery/new pathology |
| Contraindications / exclusions | None listed | Spinal neoplasm, rapidly progressing neuro deficit, epidural abscess ("not limited to"); other indications unproven | Soft: malignancy suspicion, infection risk, anticoagulants, trauma; hard: cauda equina, abscess, hematoma, fracture < 6 wk, uncontrolled diabetes; excluded: isolated axial pain, myelopathy, neurolytic | Active systemic/spinal infection, skin infection, severe stenosis with intraspinal obstruction; excluded: post-op pain control, anesthesia |
| Diagnoses | ICD-10 "support medical necessity" list (radiculopathy, stenosis, disc disorders, postlaminectomy, postherpetic, Z79.01) | ICD-10 list by region ("reference only") | Prose only; no ICD list | Prose only; no ICD list |
| Documentation | LOINC document types, 6-month look-back | Standardized tools for symptoms and function; imaging reports; prior therapies with dates | Submit with request; imaging read by independent radiologist; cumulative steroid dose after 3 injections | H&P plus psychosocial and functional assessment; each injection separately authorized |
| Special | Injection before intrathecal drug-delivery trial is necessary; step-therapy exemption (Florida 627.42393) | Reassessment of technique after poor response | Dose ceilings (240 mg methylpred/triamcinolone, 36 mg betamethasone, 45 mg dexamethasone); diagnostic selective nerve root block pathway | Diagnostic transforaminal for surgical planning needs pre-op plan; CG 1751 covers intrathecal trials |

## Agreement and disagreement

Where payers agree
- 4 weeks is the common conservative-care threshold (FL, UHC, Carelon). Only Evolent allows less (2 weeks for acute radicular pain under 3 months) and Carelon allows 2 weeks when radiculopathy is clearly evidenced.
- Image-guided (fluoroscopy, CT) injection is required and ultrasound guidance is investigational/unproven (FL and UHC say so; Carelon and Evolent are silent on ultrasound but require fluoroscopy/CT).
- 50% pain relief is the shared benchmark for continuing.
- A per-region yearly ceiling of about 4-6 injections.
- Axial pain alone is not covered (FL by requiring radiculopathy; UHC by "radicular"; Carelon by explicit exclusion; Evolent by listing only radicular, stenosis, FBSS pathways).

Where they differ
- Conservative therapy composition: FL requires prescription analgesics AND PT AND behavioral evaluation; UHC accepts any one modality; Carelon wants PT plus a complementary item; Evolent wants one active plus one inactive. A patient treated with OTC NSAIDs and a home program can satisfy UHC and probably Carelon/Evolent but not obviously FL.
- Imaging: FL needs "imaging"; Carelon needs MRI/CT with 18-month recency; UHC accepts electrodiagnostic testing instead; Evolent never asks.
- Severity: FL "moderate-to-severe"; UHC none; Carelon 3/10 plus two ADLs; Evolent 6/10 or "functional disability". Four different standards.
- Durable response before repeat: FL no duration; UHC and Carelon 3 months; Evolent 2 months; Evolent also lets a lower 30% suffice during the initial series.
- Caps: 6 (FL), 4 (UHC, Carelon), 6 then 4 (Evolent). Year definitions differ (rolling 12 months vs 12 months from first approved injection).
- Intervals: only FL (7, 14 days, 2 months) and Evolent (2 weeks, 7 days) and Carelon (2 weeks, one case) state them; UHC does not.

Requirements unique to one payer
- FL: cognitive/behavioral evaluation; "maintenance" injection category with its own interval; second cap per code family (8 in 12 months); LOINC document types; Z79.01 (anticoagulant use) in the supporting-diagnosis list; intrathecal-pump pre-trial indication; <= 2 vertebral levels per date.
- UHC: electrodiagnostic studies accepted in place of imaging; poor-response branch requiring technique reassessment; Radicular Back Pain defined by dermatome pattern.
- Carelon: ADL-count severity, 18-month imaging recency, independent-radiologist read, cumulative steroid dose, FDA Safe Use Initiative expectation, diagnostic selective nerve root block criteria.
- Evolent: pain-duration pathways (< 3 months), HEP follow-up documentation, 2-year new-episode rule, per-injection authorization.

Florida Blue stricter than others
- Prescription-strength analgesic AND PT AND behavioral management, all required (UHC: any one; Carelon: PT + one of several; Evolent: one active + one inactive; Evolent's acute pathway needs only 2 weeks and no active therapy).
- Requires imaging-demonstrated nerve root compression (Evolent has no imaging criterion; UHC accepts electrodiagnostics).
- Fixed intervals (14 days therapeutic, 2 months maintenance) and a <= 2 level limit (UHC states none).
- Eight per code family per 12 months stacked on six per region.

Florida Blue looser than others
- No numeric pain score or ADL requirement (Carelon 3/10 + 2 ADLs; Evolent 6/10).
- Repeat injection requires only "at least 50% pain relief or improvement in functional status", no duration (UHC and Carelon 3 months; Evolent 2 months).
- Annual cap of 6 per region versus 4 for UHC and Carelon.
- No contraindication list at all; no imaging recency; no steroid dose limit; no 12-month/2-year new-episode concept; diagnostic series needs only a 7-day gap.
- Escape hatches: "inability to tolerate" medication or PT is accepted in the chart.

## Structure

- Layout. FL is the shortest and flattest: one Position Statement, a footnote, then code lists and a reimbursement section. UHC is a 1.5-page criteria block in front of 10 pages of evidence. Carelon is a general-requirements section plus procedure-specific blocks inside a 34-page multi-procedure document, with specific rules overriding general ones ("The specific requirements take precedence over any stated general requirement"). Evolent is a phase model in two near-duplicate guidelines (1750 and 1751) inside a 102-page compilation.
- Logic shape. FL: pathways by injection category, each all-of; two "or documentation of inability" escapes per conservative item. UHC: all-of with a single any-of (conservative care) and a separate conditional for subsequent injections. Carelon: pathways with inheritance from general requirements; k-of-n in imaging (either of two) and complementary care (any of three); unless-clauses that swap thresholds. Evolent: four indication pathways, then a state machine (initial phase, therapeutic phase) driven by injection counts.
- Where criteria live. FL splits them: clinical rules in the Position Statement, caps in Reimbursement. Carelon and Evolent put definitions (conservative management, HEP, session, region) in General Information/Background after or before the criteria that use them. UHC puts meaning-bearing terms in Definitions (Radicular Back Pain, Conservative Therapy).
- Delegation. FL: Medicare Advantage defers to LCD L33906; FEP and SAO follow their own guidelines. Carelon: plan may substitute its own policy; peer-to-peer fallback. Evolent: Medicare criteria first, Evolent supplements. UHC: other UHC policies and a separate Medical Records Documentation document.
- Codes. All four list the same CPT set (UHC and FL omit 62324-62327 and neurolytic codes; Carelon lists them). FL and UHC add ICD-10 tables; Carelon and Evolent do not. Only FL has code-family caps. No document ties ICD codes to specific criteria.

## Problems for an automated checker

- Prior-injection history is the main input and is rarely in a single chart. FL's "At least 7 days between diagnostic injections", "At least 2 months between maintenance injections" and "No more than 6 injections ... per region ... in a rolling 12 month period" require injection dates from other providers and other payers. UHC's year is "the 12-month period starting from the date of service of the first approved injection", which only the payer knows.
- Procedure facts that exist only after the procedure: "Performed with fluoroscopic guidance" (FL) and "performed under fluoroscopic or computed tomography guidance" (UHC) are intents at authorization time; a chart cannot show them, so they will often be INSUFFICIENT.
- Percent relief and function: "at least 50% pain relief or improvement in functional status" (FL), "as measured by validated measurement tools" (UHC, no tool named), "significant documented functional improvement" (Evolent). Charts usually say "good relief".
- Hidden gap in UHC: its two repeat branches are "<= 50% ... for less than 3 months" and ">= 50% ... for 3 or more months". Sixty percent relief lasting six weeks fits neither. Exactly 50% fits both.
- Mixed severity wording inside Evolent: "moderate to severe pain causing functional disability or average pain level >= 6". The "or functional disability" lets narrative bypass the number.
- "Inability" escapes: FL "documentation in the medical record of inability to tolerate physical therapy/active exercise"; Evolent explicitly rules out "Closure of medical or therapy offices, patient inconvenience, or noncompliance without explanation". A checker must judge a reason, not find a fact.
- Open lists: UHC "include but are not limited to" for contraindications; Evolent "special circumstances (e.g., ...)".
- Redline hazard (Carelon): the PDF is a redline; extracted text mixes deleted and inserted words ("nerve rootneural elements", "glucocorticoidscorticosteroids", cover "Effective Date: 04/14/2024 04/09/2023"). Any extractor will ingest struck-through criteria as live text unless it uses the PDF's formatting.
- Footnotes carry criteria: FL's asterisk defines conservative management after the therapeutic list; Carelon's `*` and `**` define imaging exemption and "clear evidence of radiculopathy" (sensory change, weakness, "where applicable, positive nerve root irritation sign").
- Duplicate guidelines in Evolent: CG 1750 and CG 1751 repeat the same indications. In 1750 the failed-back-surgery conservative-care line is printed at the same level as the pathways, so a parser may treat it as a fifth pathway; in 1751 it is nested.
- Definitions of "Diagnostic" differ: FL "diagnostic epidural injections" are the first therapeutic-intent injections; Carelon and Evolent mean selective nerve root block or surgical-planning blocks. A model that sees "diagnostic" will confuse them.
- "Conservative" definition conflicts inside UHC: criterion says any one of three; the Definitions say "an appropriate combination of medication ... in addition to physical therapy, spinal manipulation therapy, cognitive behavior therapy, or other interventions". The Definitions block is generic, but a model could import it.
- Carelon's "Evidence of EITHER ... Nerve root compression secondary to herniated disc (advanced imaging should be performed within the previous 18 months)" applies recency only to herniation, and uses "should".
- FL's ICD-10 table has an apparent typo "M51.14 - M54.17" and a split range "M50.120 -" / "M50.123"; FL lists Z79.01 (anticoagulant use) as supporting necessity, which no clinician would treat as a reason for an injection.
- Policy-number and date mismatches between metadata and PDF (UHC printed number ends O, file ends N; UHC effective date 09/10/2026 vs library 2026-06-01).

## Test cases

1. Over-the-counter care only (UHC approves; Florida Blue does not). 52-year-old with six weeks of right L5 radicular pain, 7/10, MRI with L4-5 disc herniation compressing the L5 root. Treated with OTC ibuprofen and a home exercise program taught by the physician. UHC: radicular pain evidenced; unresponsive to pharmacotherapy "or" home exercise for >= 4 weeks (any one suffices); imaging shows involvement; fluoroscopy planned: met. FL: footnote needs "prescription-strength analgesics at a dose sufficient to induce a therapeutic response" (or documented intolerance) AND 4 weeks of physical therapy "including active exercise" (a home program is not clearly PT) AND management of behavioral issues if present, so a checker should flag the analgesic and PT legs.

2. Relief that faded at six weeks (Florida Blue and Evolent approve; UHC and Carelon do not). 60-year-old with lumbar radiculopathy had a transforaminal ESI six weeks ago with 60% relief, pain now returning, requesting a second injection. FL therapeutic: prior injection gave "at least 50% pain relief" and it is more than 14 days: met (count is below 6). Evolent initial phase: up to 3 injections "no sooner than 2 weeks apart" with "at least 30% pain relief": met. UHC: relief was > 50% but for less than 3 months, which falls in neither branch (and the first branch is for <= 50%). Carelon: "at least a 50% reduction in pain with functional improvement of at least 3 months' duration" not met.

3. Electrodiagnostic evidence, no MRI (UHC and Evolent approve; Florida Blue and Carelon do not). 68-year-old with pacemaker not cleared for MRI, five weeks of cervical radicular pain 8/10 with EMG confirming C7 radiculopathy, treated for the full five weeks with prescription NSAID and PT. UHC: "imaging or electrodiagnostic studies" met. Evolent: acute pathway (< 3 months, 2 weeks of conservative care) and no imaging criterion: met (pain 8/10 >= 6). FL: needs "demonstrated spinal nerve root compression on imaging": not met. Carelon: needs MRI or CT showing compression; the lumbar-only exemption does not apply to a cervical case.
