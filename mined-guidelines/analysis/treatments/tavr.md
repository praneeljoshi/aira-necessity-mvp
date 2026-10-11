# TAVR (transcatheter aortic valve replacement): cross-payer analysis

Documents (profiles in `sourcing/analysis/profiles/`):

| Short name | File | Date |
|---|---|---|
| Florida Blue | `bcbsfl-02-33000-32-transcatheter-aortic-valve-replacement` (12 pp) | Revised 02/15/26 |
| Independent Health (IH) | `independent-health-transcatheter-aortic-valve-replacement-tavr` (6 pp) | Revised 11/1/2025 |
| Healthy Blue LA | `louisiana-carelon-transcatheter-heart-valve-procedures-surg-00121` (42 pp, draft with redline marks; library calls it Carelon, the text says Healthy Blue Medicaid, policy SURG.00121) | Last revision 08/11/2022 |
| UHC | `uhc-transcatheter-heart-valve-procedures` (40 pp, commercial and exchange) | Effective 07/01/2026 |

## What it is

TAVR threads a collapsible prosthetic valve through an artery (usually the femoral) to replace a severely stenosed aortic valve without open-heart surgery. Payers gate it on: confirmed severe aortic stenosis (by valve area, gradient or jet velocity), heart-failure-type symptoms (NYHA class II or higher), a heart-team judgment (cardiac surgeon plus cardiologist) about surgical risk or suitability, use of an FDA-approved valve for its labeled indication, and in some policies the hospital's and operators' volume and program structure (taken from the CMS National Coverage Determination 20.32). A second pathway covers "valve-in-valve" for a degenerated surgical bioprosthesis, which is usually gated on high surgical risk. Cerebral embolic protection devices used during TAVR are treated as investigational.

## Side by side

| Requirement | Florida Blue | Independent Health | Healthy Blue LA | UHC |
|---|---|---|---|---|
| Doc scope | Aortic only | Aortic only | Aortic, mitral TEER, pulmonary, tricuspid | Aortic, mitral, pulmonary, tricuspid, caval |
| Severe AS definition | One or more: AVA <= 1.0 cm2; AVAi <= 0.6 cm2/m2; mean gradient >= 40 mm Hg; peak velocity >= 4.0 m/s (stated "for the use of the SAPIEN or CoreValve devices") | One or more: AVA "less than <=1.0" cm2; AVAi <= 0.6; mean gradient > 40; Doppler jet > 4.0 | One of: AVA <= 0.8 cm2; AVAi <= 0.5; mean gradient > 40; peak velocity > 4.0 | One of: mean gradient >= 40; peak velocity >= 4.0; AVA <= 1.0 (no AVAi) |
| Low-flow / low-gradient | Not addressed | Not addressed | Not addressed | Case-by-case via ACC/AHA 2021 guideline after expert evaluation |
| Valve anatomy | "calcified aortic annulus"; no unicuspid or bicuspid valve | "calcified native aortic valve stenosis without severe aortic insufficiency" | "degenerative, native valve" | "calcific native aortic valve stenosis"; no bicuspid exclusion |
| Symptoms | NYHA II, III or IV | NYHA II, III or IV | NYHA II or greater | NYHA II or greater and "symptoms are due to aortic valve stenosis" |
| Ejection fraction | Not stated | EF > 20% | Not stated | Not stated |
| Surgical risk (native valve) | None required (risk categories defined in Notes but not used) | Heart team must find member inoperable (list truncated) | Age >= 65: any risk. Age < 65: intermediate or greater (predicted 30-day mortality >= 3%) "as determined by at least two physicians" | None required for native valve |
| Heart team / decision | None for native valve | Heart team with experienced cardiac surgeon and cardiologist | At least two physicians (risk) | Interventional cardiologist and experienced cardiothoracic surgeon determine appropriateness; shared decision-making with both |
| Valve-in-valve | Failed surgical bioprosthesis; NYHA II-IV; not operable per >= 2 cardiovascular specialists incl. cardiac surgeon, or increased risk (repeat sternotomy, congenital vascular anomalies, complex intrathoracic history) documented by >= 2 specialists | Not addressed | Failed bioprosthesis; STS >= 8% or >= 15% 30-day mortality, by at least two physicians | Failed bioprosthesis; high or prohibitive risk, PROM >= 8% |
| Device / label | FDA-approved system, approach consistent with labeling | Complete system with FDA PMA for its approved indication | FDA-approved device (device table in Background) | "performed according to FDA-labeled indications, contraindications, warnings, and precautions" |
| Contraindications | None listed (bicuspid is an inline exclusion) | Cannot tolerate anticoagulant/antiplatelet; active endocarditis or other active infection | None listed | None listed apart from FDA label |
| Facility / operator | None in doc (Medicare Advantage: NCD 20.32) | "meets the institutional requirements set forth in the CMS NCD" | None in doc | Center with on-site heart valve surgery and interventional cardiology, ICU, CMS volume rules (>= 50 AVR/yr incl >= 20 TAVR, or >= 100 per 2 yr incl >= 40 TAVR; >= 300 PCI/yr; 2 surgeons; 1 interventionalist) |
| Documentation | LOINC table: H&P, progress note, plan of treatment, labs, within 6 months of date of service | None; retrospective review | None | Points to "Medical Records Documentation Used for Reviews" (separate) |
| Authorization | Criteria in Position Statement | "Pre-authorization not required. Criteria utilized upon retro-review." | Medically necessary statement | Medical necessity statement |
| Cerebral embolic protection | Investigational (33370 flagged) | Silent | Silent in position statement; 33370 sits in the "may be medically necessary" code list | Unproven, not medically necessary |
| Repeat TAVR | None | None | None | None |
| Codes | CPT 33361-33370; LOINC | None | CPT, ICD-10 procedure (02RF3JH etc.), ICD-10 diagnosis "All diagnoses" | CPT incl. 33361-33370 and other valves |

## Agreement and disagreement

Agreement. All four require severe aortic stenosis measured by AVA, gradient or velocity (any one), NYHA class II or greater, native or valve-in-valve anatomy, and an FDA-approved device. All four lean on the CMS NCD (directly or through "FDA labeling" and "heart team").

Where Florida Blue is stricter:
- Bicuspid or unicuspid valve: only Florida Blue excludes. UHC says nothing and Healthy Blue says "native valve".
- Documentation: Florida Blue alone lists LOINC document types (H&P, progress note, plan of treatment, laboratory studies) within 6 months of the date of service.
- Valve-in-valve needs two cardiovascular specialists including a cardiac surgeon to document inoperability or increased risk; UHC and Healthy Blue use an STS >= 8% test.
- Versus UHC: UHC does not exclude bicuspid and does not demand a surgeon's documentation for a native-valve case beyond heart-team appropriateness.

Where Florida Blue is looser:
- Versus Healthy Blue LA: the AVA cut-off is <= 1.0 vs <= 0.8 cm2, AVAi <= 0.6 vs <= 0.5, and mean gradient >= 40 (inclusive) vs > 40, peak velocity >= 4.0 vs > 4.0. Healthy Blue also imposes an age/risk rule (under 65 needs intermediate or greater risk), and Florida Blue has no age or risk requirement for native valves.
- Versus Independent Health: IH requires the heart team to find the member inoperable and an EF > 20%, and rules out severe aortic insufficiency; Florida Blue has none of these.
- Versus UHC: no heart-team determination or shared decision-making conversation for native valves, and no facility/volume requirement (the volume rules are in UHC's definitions; Florida Blue defers to the NCD only for Medicare Advantage).
- Valve-in-valve: no STS threshold at all (Healthy Blue and UHC both use 8%), so a patient at lower STS risk qualifies if two specialists document that open redo surgery is risky.

Where Florida Blue is looser or stricter depending on reading: the Notes give FDA definitions of extreme, high, intermediate and low risk (STS >= 8%, 3-7%, < 3% or 4%) but the native-valve criteria never use them, so a low-risk patient appears to qualify. UHC does the same but requires a heart-team and shared decision conversation.

Unique requirements:
- Florida Blue: bicuspid exclusion; LOINC documentation panel; "calcified aortic annulus".
- Independent Health: EF > 20%; no severe aortic insufficiency; anticoagulation/antiplatelet tolerance; endocarditis/active infection; retro-review only.
- Healthy Blue LA: age >= 65 versus < 65 rule; AVAi <= 0.5 / AVA <= 0.8 (strictest); mitral, pulmonary conduit >= 16 mm; device table.
- UHC: shared decision-making; center ICU and volume; low-flow/low-gradient exception; "symptoms are due to aortic valve stenosis"; embolic protection explicitly unproven.

## Structure

- Florida Blue: a classic house format (Description, Evidence, Position Statement, Notes, Coding, Program Exceptions, Definitions). The criteria are in 1.5 pages; "Notes" holds severity thresholds and risk definitions that the position statement points at with "see notes below".
- Independent Health: a policy template with line-of-business checkboxes; one "Policy" section. The heading "Self-Funded:" precedes the definitions and criteria, and Medicaid and Essential Plan "cover TAVR utilizing the Commercial criteria above". Medicare Advantage is "Managed by Evolent". No codes.
- Healthy Blue LA: a 42-page policy covering all valve procedures, with position statement on pp.1-4 and a trial table, device approval table, definitions, three code groups (medically necessary, not medically necessary, investigational) and a revision log. The legal paragraph repeats on every page.
- UHC: one policy for all valves with per-valve sections in Coverage Rationale; facility requirements embedded as inline bullets plus a Definitions block copying the CMS NCD volume text; long clinical evidence.
- Logic shape: Florida Blue and UHC use an ALL list with a nested 1-of-3 for severity; Healthy Blue uses a nested ANY (4 severity) plus a 2-way age/risk split; IH is an ALL list (with a broken inner list).
- Delegation: Florida Blue MA to NCD 20.32; IH to the NCD for institutions and Evolent for MA; UHC to NCD/TVT Registry for volumes, ACC/AHA for LFLG cases, FDA label for everything.
- Codes: Florida Blue lists 33361-33369 plus 33370 flagged investigational. Only Healthy Blue maps codes into medically necessary / not medically necessary groups and includes ICD-10-PCS. IH has none.

## Problems for an automated checker

- Truncated list (IH). "Members with an ejection fraction >20% who have been examined by a heart team ... who find the member: 1. inoperable and in whom existing co-morbidities would not preclude the expected benefit ...; or" is followed directly by the FDA PMA bullet, so item 2 is missing and the branch logic cannot be reconstructed. The policy header "Self-Funded:" adds doubt about which line of business the criteria apply to.
- Redline residue (Healthy Blue LA). The key age/risk clause reads "Age 65 years or older with Lowany open surgical risk and 65 years of age or older; or" and "Age younger than 65 with Iintermediate or greater open surgical risk". Revision history confirms intent: age >= 65 any risk. Dates read "08/112/20221" and "12/29/202108/18/20 22".
- Strict vs inclusive thresholds are inconsistent between payers and within documents: "greater than 40" vs ">= 40"; IH "less than <=1.0". A checker that normalizes to >= will mis-judge borderline values (mean gradient exactly 40 mm Hg: Florida Blue yes, Healthy Blue no).
- Thresholds tied to a device. Florida Blue: "For the use of the SAPIEN or CoreValve devices, severe aortic stenosis is defined by ONE OR MORE" - the checker has to decide what happens with Evolut, Navitor or Portico.
- Orphaned definitions. Florida Blue Notes define extreme, high, intermediate and low risk but no criterion uses them. UHC defines "CMS Volume Requirements" in detail but the criterion says "Volume requirements consistent with the Centers for Medicare and Medicaid Services".
- "as determined by at least two physicians" (Healthy Blue) and "at least 2 cardiovascular specialists (including a cardiac surgeon)" (Florida Blue): need documentation of who said what; a single heart-team note may or may not count.
- Negative or hard-to-chart facts: "Member does not have unicuspid or bicuspid aortic valves" (needs echo or CT report statement); "calcified aortic annulus"; "without severe aortic insufficiency"; "symptoms are due to aortic valve stenosis" (causal attribution); "experienced cardiothoracic surgeon".
- Facility attributes (UHC): center ICU, on-site programs, institutional volumes. These belong to the hospital, not the patient chart, so the answer is INSUFFICIENT or must come from a separate provider registry.
- Process criteria: "Individual has engaged in a Shared Decision-Making conversation" needs a specific note; "case-by-case" LFLG exceptions are not decidable.
- Escape hatches: UHC LFLG note "will be considered on a case-by-case basis", Florida Blue "increased surgical risk ... complex intrathoracic surgical history" (open-ended).
- And/or inconsistency: Florida Blue "NYHA ... Class II,III or IV" (any), Healthy Blue "either ... or" on a four-item list, UHC "Peak aortic jet velocity of >= 4.0 m/s; or".
- Conflicting statements about codes: Healthy Blue lists 33370 (cerebral protection) as potentially medically necessary but the position statement is silent; Florida Blue and UHC say investigational/unproven.
- Page furniture: UHC page footers say "Page 1 of 2", "Page 2 of 3" ... "Page 39 of 40"; Healthy Blue's legal paragraph interrupts mid-list; Florida Blue's navigation bar sits above the text.
- Time reference: Florida Blue's LOINC "six months or fewer before starting date of service" is the only dated look-back; others set no recency for echo or heart-team notes.
- Retrospective use (IH): "Pre-authorization not required. Criteria utilized upon retro-review." means the same criteria run after the service, a different workflow.

## Test cases

Case 1: low-risk 58-year-old, borderline stenosis. Tricuspid aortic valve with calcification, AVA 0.9 cm2, AVAi 0.55, mean gradient 38 mm Hg, peak velocity 3.9 m/s, NYHA II, STS 2%, cardiac surgeon and interventional cardiologist agree and document a shared decision conversation, high-volume center.
- Florida Blue: approve. AVA <= 1.0 meets "one or more" criterion; NYHA II meets; no bicuspid; no risk or age requirement.
- UHC: approve if the heart-team and SDM documentation and center rules are met; AVA <= 1.0 satisfies the severity "one of".
- Healthy Blue LA: do not approve. AVA 0.9 > 0.8 and AVAi 0.55 > 0.5, gradient 38 < 40, velocity < 4.0, so criterion A fails; also under 65 with low risk fails C.2.
- Independent Health: do not approve. Requires the heart team to find the member inoperable; STS 2% does not support that.

Case 2: bicuspid valve, age 72. Bicuspid aortic valve with calcific severe AS, peak velocity 4.6 m/s, mean gradient 48 mm Hg, NYHA III, STS 3.5%, heart team documented.
- UHC: approve. Severity met, NYHA, heart team + SDM; no bicuspid exclusion (and "calcific native" is satisfied).
- Healthy Blue LA: approve. Age 65+ with any risk; "degenerative, native valve" (arguably includes bicuspid).
- Florida Blue: do not approve. "Member does not have unicuspid or bicuspid aortic valves."
- Independent Health: do not approve unless the heart team finds the member inoperable.

Case 3: valve-in-valve at moderate risk. A 76-year-old has a failed 21 mm surgical bioprosthesis with stenosis, NYHA III, STS 5%. Two cardiovascular specialists including a cardiac surgeon document previous CABG with patent left internal mammary graft behind the sternum (complex intrathoracic surgical history).
- Florida Blue: approve. "operable candidate but is considered at increased surgical risk for open surgery ... has a complex intrathoracic surgical history, as documented by at least 2 cardiovascular specialists (including a cardiac surgeon)". No STS cut-off.
- UHC: do not approve. Valve-in-valve requires "high or prohibitive surgical risk [PROM score of >= 8%]"; STS 5% fails.
- Healthy Blue LA: do not approve. "Society of Thoracic Surgeons operative risk score greater than or equal to 8% or at a 15% or greater risk of operative mortality".
- Independent Health: no valve-in-valve criteria, so not addressed.
