## Common mistakes (invented text; each is a mistake measured before)

1. Scope named in the grant sentence [v1.1: 11 of 12 real false approvals]
   Text: "Gadget implantation meets the definition of medical necessity in adults with refractory gadget failure when
   ALL of the following are met: ..."
   Wrong: only the bullets below. Right: add `adult` ("in adults") and `refractory_gadget_failure` as conditions.
   Why: a chart that meets every bullet but is a child, or has a different condition, must not pass.

2. Device / FDA scope [v1.1: EVAR x3, cochlear x2, ankle revision]
   Text: "... using an FDA-approved gadget." Wrong: dropped as "describes the procedure". Right: condition
   `fda_device`, question "Is the planned device FDA-approved?".

3. Named items in a catch-all exclusion [v1.2 rebuild: EVAR, carotid]
   Text: "Gadget repair is considered experimental or investigational for all other indications, including gadget
   dissection and members ineligible for open repair."
   Wrong: the whole sentence set aside as a catch-all. Right: conditions `dissection` and `ineligible_open_repair`,
   each under NOT. Why: "including" names specific situations that are excluded.

4. Exclusion printed in another section [v1.1: PAP E0471 for OSA]
   Text (reimbursement section): "Device B does not meet the definition of medical necessity for sleep apnea."
   Wrong: only the indication's own lines. Right: `for_sleep_apnea` under NOT for a Device B order. Why: limitations
   apply wherever they are printed.

5. Cross-reference [v1.1 sleep repeat testing, hip resurfacing, cochlear batteries]
   Text: "Repeat testing meets ... when the member meets the criteria above and the first test was non-diagnostic."
   Wrong: one leaf "meets the criteria above". Right: the referenced criteria themselves (as a block) AND
   `first_test_nondiagnostic`.

6. Paired qualifiers [v1.1 lymphedema, cochlear, sleep neck size]
   Text: "limb volume difference > 10% (dominant limb) or > 7% (non-dominant limb)". Wrong: two free alternatives
   (>10% or >7%). Right: (dominant AND diff_gt_10) OR (non_dominant AND diff_gt_7).

7. Examples are not a closed list or a cutoff [v1.1 heart/lung, hip "eg, age 55 or younger"]
   Text: "end-stage disease including, but not limited to, A, B or C"; "likely to outlive the device (e.g., age 55 or
   younger)". Wrong: ANY(A, B, C); threshold age <= 55. Right: `end_stage_disease` with A, B, C in its question;
   `likely_to_outlive_device` with no threshold, "e.g., 55 or younger" in the question.

8. "Unless contraindicated" and "if any" [v1.1 spine "if any"]
   Text: "6 weeks of physical therapy (unless contraindicated)"; "management of behavioral issues, if any".
   Right: (pt_6_weeks OR pt_contraindicated); (NOT behavioral_issues OR behavioral_issues_managed).
   Wrong: pt_6_weeks alone; behavioral_issues_managed required always.

9. Do not prune clinical alternatives from the diagnosis code [swarm: TKA, revision arthroplasty, blepharoplasty]
   Text: "Revision is medically necessary for ONE of: loosening, infection, fracture, instability, ...". Order
   diagnosis: loosening. Wrong: keep only loosening. Right: keep the whole ANY; the chart decides. Prune only on what
   the order fixes (product/device code, procedure, side, age band).

10. Do not borrow another route's conditions [swarm: cochlear batteries, pediatric PAP]
    Text: "Batteries are covered when the criteria for the device are met." Wrong: also require the replacement-of-
    parts conditions. Right: the device criteria only (a cross-reference), nothing from neighbouring routes.

11. A literal condition that makes a route impossible [swarm: MSLT "no prior OSA" on the on-PAP route]
    Text: route A "for members treated for OSA ..."; a shared bullet "no OSA on prior evaluation". Wrong: require both.
    Right: leave the impossible one out of route A and say so in notes.

12. Documents that cannot exist before the procedure [swarm: gynecomastia pathology report]
    Text: "Required documentation: post-operative pathology report." Right: `answerable: false` (review item) or a
    note; never a chart condition that blocks readiness.

13. Do not mark a mixed condition unanswerable: split it [v1.2 smoke: tools-gpt-5.5 PAP]
    Text: "a prescription from a qualified health professional". Wrong: one leaf `prescription_qualified_hcp`,
    answerable=false (then no one checks the chart for a prescription). Right: `prescription_present` (answerable;
    the chart checks it) AND `prescriber_qualified` (answerable=false only if the chart truly can't show it).
    Rule: answerable=false only when no part of the condition can be shown by a chart.
