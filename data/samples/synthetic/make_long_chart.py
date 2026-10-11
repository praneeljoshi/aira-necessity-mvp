"""Generate elena_ruiz_chart.pdf — a long (120+ page) synthetic chart for Phase 2 Gate 8 — and
elena_ruiz.expected.json, the ground truth with the page/visit where every buried fact sits.

Same visual shape as make_charts.py (reportlab, letter, same heading styles) but the record is a
merged multi-source chart: ~40 encounters over 3 years across vascular surgery, primary care,
dermatology, physical therapy and urgent care, with labs, imaging and a medication list that changes.
All patients and providers are fictional.      python make_long_chart.py
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
OUT_PDF = HERE / "elena_ruiz_chart.pdf"
OUT_JSON = HERE / "elena_ruiz.expected.json"

SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)
P = ParagraphStyle("p", parent=SS["BodyText"], fontSize=9.5, leading=12.5)
SM = ParagraphStyle("sm", parent=P, fontSize=8, textColor=colors.grey)

# ------------------------------------------------------------------ people and places (fictional)
PATIENT = {"name": "Elena Ruiz", "dob": "March 4, 1968", "mrn": "GCV-012877", "sex": "Female",
           "addr": "3318 W Azeele St, Tampa, FL 33609", "phone": "(813) 555-0172",
           "occupation": "Elementary school teacher (4th grade), Hillsborough County Public Schools"}
MEMBER_ID = "FLB771204936"

GULF = {"name": "GULF COAST VASCULAR SURGERY ASSOCIATES", "short": "Vascular Surgery",
        "addr": "2200 Bayshore Blvd, Suite 310 | Tampa, FL 33606 | (813) 555-0140 | NPI: 1987654321"}
PCP = {"name": "WESTCHASE FAMILY MEDICINE", "short": "Primary Care",
       "addr": "11970 Sheldon Rd, Suite 120 | Tampa, FL 33626 | (813) 555-0161 | NPI: 1750233419"}
DERM = {"name": "BAYSHORE DERMATOLOGY GROUP", "short": "Dermatology",
        "addr": "3100 W Kennedy Blvd, Suite 205 | Tampa, FL 33609 | (813) 555-0177 | NPI: 1639120084"}
PT = {"name": "TAMPA BAY PHYSICAL THERAPY & REHABILITATION", "short": "Physical Therapy",
      "addr": "4415 W Gandy Blvd | Tampa, FL 33611 | (813) 555-0188 | NPI: 1821456730"}
UC = {"name": "CARROLLWOOD URGENT CARE", "short": "Urgent Care",
      "addr": "14030 N Dale Mabry Hwy | Tampa, FL 33618 | (813) 555-0193 | NPI: 1407732915"}

VASC_MD = "Dr. Elena Vasquez, MD, FACS"
US_MD = "Dr. Thomas Reed, RVT / Dr. Elena Vasquez, MD"
PCP_MD = "Dr. Priya Raman, MD"
DERM_MD = "Dr. Marcus Bell, MD"
PT_DPT = "Kevin Nunes, PT, DPT"
UC_MD1 = "Dr. Anita Shah, MD"
UC_MD2 = "Luis Herrera, PA-C"
UC_MD3 = "Dr. Omar Siddiqui, DO"
RAD_MD = "Dr. Naomi Feld, MD (Radiology)"


def D(s: str) -> date:
    return date.fromisoformat(s)


def long(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def us(d: date) -> str:
    return d.strftime("%m/%d/%Y")


# ------------------------------------------------------------------ medication timeline (changes over 3 years)
# (start, stop-or-None, name, dose, frequency, indication)
MED_EVENTS = [
    ("2018-04-01", "2024-01-23", "Losartan", "50 mg", "Daily", "Hypertension"),
    ("2024-01-23", None,         "Losartan", "100 mg", "Daily", "Hypertension"),
    ("2016-02-01", "2024-10-15", "Levothyroxine", "50 mcg", "Daily", "Hypothyroidism"),
    ("2024-10-15", None,         "Levothyroxine", "75 mcg", "Daily", "Hypothyroidism"),
    ("2023-10-24", "2025-06-10", "Ibuprofen", "400 mg", "PRN", "Left leg aching"),
    ("2025-06-10", None,         "Acetaminophen", "500 mg", "PRN", "Left leg aching (NSAIDs held with anticoagulation; continued by preference)"),
    ("2024-01-09", "2024-01-16", "Amoxicillin-clavulanate", "875/125 mg", "BID x 7 days", "Acute bacterial sinusitis"),
    ("2024-05-21", "2026-01-20", "Atorvastatin", "20 mg", "Nightly", "Hyperlipidemia"),
    ("2026-01-20", None,         "Atorvastatin", "40 mg", "Nightly", "Hyperlipidemia"),
    ("2024-08-06", "2024-08-13", "Cephalexin", "500 mg", "QID x 7 days", "Cellulitis, right forearm"),
    ("2024-10-15", None,         "Cholecalciferol (Vitamin D3)", "2000 IU", "Daily", "Vitamin D insufficiency"),
    ("2024-11-12", "2025-02-11", "Triamcinolone 0.1% cream", "Topical", "BID PRN", "Hand dermatitis"),
    ("2025-01-14", "2025-01-21", "Benzonatate", "100 mg", "TID PRN x 7 days", "Cough, acute bronchitis"),
    ("2025-06-10", "2025-06-17", "Apixaban", "10 mg", "BID x 7 days (loading)", "Acute DVT, right calf"),
    ("2025-06-17", "2025-09-16", "Apixaban", "5 mg", "BID", "Acute DVT, right calf (3-month course)"),
    ("2025-12-09", "2025-12-12", "Ondansetron ODT", "4 mg", "Q8H PRN", "Nausea, viral gastroenteritis"),
    ("2026-02-17", "2026-03-17", "Cyclobenzaprine", "5 mg", "QHS PRN", "Lumbar muscle spasm"),
    ("2026-07-07", "2026-07-14", "Naproxen", "500 mg", "BID x 7 days", "Right ankle sprain"),
]


def meds_on(d: date) -> list[list[str]]:
    rows = []
    for start, stop, name, dose, freq, ind in MED_EVENTS:
        if D(start) <= d and (stop is None or d < D(stop)):
            rows.append([name, dose, freq, ind])
    return rows


def med_changes_between(a: date, b: date) -> list[str]:
    """Human-readable medication changes with a < date <= b."""
    out = []
    for start, stop, name, dose, freq, ind in MED_EVENTS:
        if a < D(start) <= b:
            out.append(f"STARTED {name} {dose} {freq} — {ind} ({us(D(start))})")
        if stop and a < D(stop) <= b:
            out.append(f"STOPPED {name} {dose} ({us(D(stop))})")
    return out


def allergies_on(d: date) -> str:
    return "No known drug allergies." if d < D("2024-08-13") else "Cephalexin — rash (08/2024, mild, non-urticarial)."


def dvt_history_line(d: date) -> str:
    if d < D("2025-06-10"):
        return "Denies any history of deep vein thrombosis, pulmonary embolism or superficial thrombophlebitis."
    if d < D("2025-09-16"):
        return "History of acute right posterior tibial (calf) vein DVT diagnosed 06/10/2025, currently on apixaban."
    return "History of right calf (posterior tibial vein) DVT 06/2025, treated with a 3-month course of apixaban, completed 09/16/2025."


# ------------------------------------------------------------------ templated note parts (the bulk of a real chart)
def vitals_for(d: date) -> list[tuple[str, str]]:
    k = d.toordinal()
    sbp, dbp = 124 + (k * 7) % 19, 76 + (k * 5) % 11
    hr, wt = 66 + (k * 3) % 17, 168 + (k * 11) % 9
    temp = 97.6 + ((k * 13) % 9) / 10
    return [("Blood Pressure", f"{sbp}/{dbp} mmHg, seated, left arm"), ("Heart Rate", f"{hr} bpm, regular"),
            ("Temperature", f"{temp:.1f} °F oral"), ("Respiratory Rate", f"{14 + k % 4} /min"),
            ("SpO2", f"{97 + k % 3}% on room air"), ("Weight", f"{wt} lb"), ("Height", "64 in"),
            ("BMI", f"{wt * 703 / 64 / 64:.1f} kg/m²"), ("Pain Score", f"{2 + (k * 7) % 5}/10")]


def ros_for(d: date, specialty: str) -> list[tuple[str, str]]:
    leg = ("Chronic left lower extremity aching, heaviness and evening swelling, followed by vascular surgery."
           if d >= D("2023-10-24") else "Reports left leg aching and tiredness by end of the day, several months.")
    heme = dvt_history_line(d)
    return [
        ("Constitutional", "Denies fever, chills, unintentional weight loss, night sweats. Energy at baseline."),
        ("Eyes", "Denies visual change, eye pain, discharge."),
        ("ENT", "Denies hearing loss, tinnitus, sore throat, sinus pressure unless noted in HPI."),
        ("Cardiovascular", "Denies chest pain, palpitations, orthopnea, PND, syncope."),
        ("Respiratory", "Denies dyspnea at rest, wheeze, hemoptysis. Cough only if noted in HPI."),
        ("Gastrointestinal", "Denies abdominal pain, nausea, vomiting, melena, hematochezia, change in bowel habit unless noted in HPI."),
        ("Genitourinary", "Denies dysuria, hematuria, frequency."),
        ("Musculoskeletal", "Joint complaints as noted in HPI; otherwise denies joint swelling, morning stiffness."),
        ("Extremities / Vascular", leg + " No claudication. No rest pain. No ulceration or bleeding from veins."),
        ("Skin", "Denies new rashes, non-healing wounds or ulcers unless noted in HPI."),
        ("Neurological", "Denies headache, focal weakness, numbness, dizziness."),
        ("Psychiatric", "Denies depressed mood, anxiety beyond situational stress. Sleep adequate except when leg cramps wake her."),
        ("Endocrine", "Hypothyroidism on replacement; denies heat/cold intolerance, polyuria, polydipsia."),
        ("Hematologic / Lymphatic", heme + " Denies easy bruising or bleeding."),
        ("Allergic / Immunologic", "Seasonal rhinitis in spring; no anaphylaxis history."),
    ]


def general_exam(d: date) -> list[tuple[str, str]]:
    return [
        ("General", "Well-appearing woman in no acute distress, alert, cooperative, ambulating independently."),
        ("HEENT", "Normocephalic, atraumatic. Pupils equal and reactive. Oropharynx clear. Neck supple, no thyromegaly."),
        ("Cardiovascular", "Regular rate and rhythm, no murmurs, rubs or gallops. Radial pulses 2+ bilaterally."),
        ("Respiratory", "Clear to auscultation bilaterally, no wheezes, rales or rhonchi. Normal effort."),
        ("Abdomen", "Soft, non-tender, non-distended, no organomegaly."),
        ("Skin", "Warm and dry. No rash unless noted. No open wounds."),
        ("Neurological", "Cranial nerves II–XII grossly intact. Strength 5/5 throughout. Gait normal."),
        ("Psychiatric", "Normal mood and affect, appropriate judgment and insight."),
    ]


def vascular_exam(d: date, left_leg: str) -> list[tuple[str, str]]:
    return general_exam(d)[:4] + [
        ("Left Lower Extremity", left_leg),
        ("Right Lower Extremity", "Scattered reticular veins lateral thigh. No varicosities, edema, pigmentation or ulceration. Calf soft, non-tender."
         + ("" if d < D("2025-06-10") else " Mild residual calf fullness after 06/2025 DVT, no tenderness along the posterior tibial veins.")),
        ("Pulses", "Femoral, popliteal, dorsalis pedis and posterior tibial pulses 2+ and symmetric bilaterally. Capillary refill < 2 seconds."),
        ("Neurological", "Sensation intact to light touch both feet. Motor 5/5."),
    ]


EDUCATION = {
    "Vascular Surgery": [
        "Elevate the legs above heart level for 15–20 minutes, 3–4 times daily, and at the end of the work day.",
        "Avoid prolonged standing in one place; shift weight, walk briefly, and flex the calves when standing is unavoidable.",
        "Walk 30 minutes daily; the calf muscle pump is the most effective natural treatment for venous congestion.",
        "Put compression stockings on first thing in the morning before swelling develops; remove at bedtime. Replace every 4–6 months as elastic wears.",
        "Call the office for sudden one-sided calf swelling, redness or warmth, chest pain or shortness of breath, or any bleeding from a vein.",
        "Maintain a healthy weight; each additional 10 lb increases venous pressure at the ankle.",
    ],
    "Primary Care": [
        "Take medications as prescribed. Bring all medication bottles to each visit for reconciliation.",
        "Home blood pressure log: measure seated, after 5 minutes of rest, morning and evening, 3 days per week. Bring the log.",
        "DASH-style diet, sodium under 2 g/day, limit alcohol to 1 drink/day or less.",
        "Fasting labs as ordered; nothing to eat or drink except water for 10–12 hours before the draw.",
        "Annual preventive services reviewed; see the health maintenance table in your patient portal.",
    ],
    "Dermatology": [
        "Daily broad-spectrum sunscreen SPF 30 or higher on exposed skin; reapply every 2 hours outdoors.",
        "Monthly self skin examination using the ABCDE rule; photograph any changing lesion and call the office.",
        "Bland emollient (petrolatum or ceramide cream) to hands twice daily; avoid fragranced soaps.",
        "Return sooner for any lesion that bleeds, grows, or does not heal within 4 weeks.",
    ],
    "Physical Therapy": [
        "Home exercise program as demonstrated; 1 set of 10–15 repetitions, twice daily, within a pain-free range.",
        "Ice 15 minutes after exercise if sore. Heat before stretching is acceptable.",
        "Pain that persists more than 2 hours after exercise means the dose was too high; reduce repetitions and inform the therapist.",
        "Wear supportive footwear; avoid barefoot walking on hard surfaces.",
    ],
    "Urgent Care": [
        "Return to urgent care or go to the emergency department for worsening symptoms, high fever, difficulty breathing, chest pain, or new confusion.",
        "Follow up with your primary care physician within 1–2 weeks. A copy of this visit has been sent to Dr. Priya Raman.",
        "Rest, fluids, and over-the-counter symptom relief as discussed. Complete the full course of any prescribed antibiotic.",
        "Work note provided on request.",
    ],
}


# ------------------------------------------------------------------ the 40 encounters
# Each: date, practice, md, type, cc, hpi (list of paragraphs; buried facts live in their own short paragraph),
# exam (list of (label, text)) or None for templated, ap (list of paragraphs), orders (list), optional table.
V = []


def visit(date_iso, practice, md, type_, cc, hpi, ap, exam=None, orders=(), table=None, cpt_icd=None):
    V.append({"date": D(date_iso), "practice": practice, "md": md, "type": type_, "cc": cc, "hpi": hpi,
              "exam": exam, "ap": ap, "orders": list(orders), "table": table, "codes": cpt_icd or []})


L_EARLY = ("Scattered reticular veins and a few small non-tortuous varicosities over the medial calf in the GSV distribution. "
           "Trace ankle edema at the end of the day per patient; none at rest this morning. No pigmentation, lipodermatosclerosis, "
           "eczema or ulceration. Calf soft, non-tender, Homans negative.")

# 1 -------------------------------------------------------------- m0
visit("2023-10-10", PCP, PCP_MD, "Annual Physical / Preventive Visit",
      "Annual physical. Also reports left leg aching and tiredness.",
      ["55-year-old female teacher presents for her annual preventive visit. Chronic problems: essential hypertension on losartan 50 mg, "
       "controlled on home readings 120s–130s/70s–80s; primary hypothyroidism on levothyroxine 50 mcg, last TSH 2.8 one year ago. "
       "She eats a mostly Mediterranean diet, does not smoke, drinks 2–3 glasses of wine per week, and walks most evenings.",
       "New complaint: for about 6 months the left leg has felt heavy and achy by the end of the school day. She stands and walks in the "
       "classroom for most of a 7-hour day. She has noticed a few visible veins on the inside of the left calf and some ankle puffiness in "
       "the evenings that is gone by morning. No pain at rest, no cramping yet, no skin changes. Family history: mother had varicose veins "
       "stripped in her 50s. Patient has had two pregnancies.",
       "Health maintenance: mammogram due; colonoscopy 2021 (normal, repeat 10 years); Pap/HPV 2022 normal; Tdap 2019; influenza vaccine today."],
      ["Essential hypertension, controlled. Continue losartan 50 mg daily. CMP and lipid panel today.",
       "Hypothyroidism. Continue levothyroxine 50 mcg. TSH today.",
       "Left lower extremity heaviness and aching with visible medial calf veins and evening ankle edema in a patient who stands all day; "
       "clinical picture consistent with early superficial venous insufficiency. Referral placed to Gulf Coast Vascular Surgery Associates "
       "(Dr. Vasquez) for evaluation. Advised elevation after work and walking.",
       "Preventive: influenza vaccine administered today. Screening mammogram ordered. Return 1 year or sooner as needed."],
      orders=["CMP, lipid panel, TSH, CBC — fasting", "Referral: Vascular Surgery (left leg varicose veins / venous insufficiency)",
              "Screening mammogram, bilateral", "Influenza vaccine, administered"],
      cpt_icd=[("99396", "Preventive visit, established, 40–64"), ("I10", "Essential hypertension"), ("E03.9", "Hypothyroidism"),
               ("I83.92", "Asymptomatic varicose veins of left lower extremity — referred for evaluation")])

# 2 -------------------------------------------------------------- m0 (no history of DVT)
visit("2023-10-24", GULF, VASC_MD, "New Patient Consult",
      "Left leg heaviness, aching and evening swelling; visible veins medial calf. Referred by Dr. Raman.",
      ["55-year-old female 4th-grade teacher referred by her PCP for approximately 6 months of progressive left lower extremity heaviness and "
       "aching that builds through the school day and is worst by late afternoon. Ankle swelling by evening, resolved by morning. Relieved by "
       "elevation and by sitting with the leg up for 20 minutes. Occasional itching over the medial calf. No night cramps yet. No ulcer, no "
       "bleeding, no redness along a vein. The right leg is asymptomatic.",
       "No personal history of deep vein thrombosis, pulmonary embolism, or superficial thrombophlebitis. No prior venous procedures, no "
       "prior sclerotherapy. No known clotting disorder. Two uncomplicated pregnancies. Does not smoke. Not on hormonal therapy.",
       "Risk factors: prolonged occupational standing, positive family history (mother), BMI 29. She has not tried compression stockings. "
       "She takes ibuprofen about twice a week for the aching.",
       "Functional impact at this time: she finishes the school day but 'collapses on the couch' and has reduced her evening walks from "
       "5 nights to 2–3 nights per week."],
      ["Symptomatic left lower extremity superficial venous insufficiency, suspected great saphenous vein distribution. CEAP clinical class "
       "C1–C2 on today's exam (reticular veins and small varicosities), Es, As, Pr pending duplex.",
       "Plan: lower extremity venous reflux duplex ultrasound, left, to assess the deep system, the saphenofemoral junction and the GSV for "
       "reflux. Conservative measures reviewed: leg elevation, calf exercise, weight management, ibuprofen PRN. Compression stockings "
       "discussed in principle; patient would like to see the ultrasound result first. Return after the duplex to review and set a plan."],
      exam=vascular_exam(D("2023-10-24"), L_EARLY),
      orders=["Lower extremity venous reflux duplex, left (CPT 93970/93971)", "Return visit after duplex"],
      cpt_icd=[("99204", "New patient visit, moderate complexity"), ("I83.92", "Varicose veins, left lower extremity"), ("R60.0", "Localized edema")])

# 3 -------------------------------------------------------------- m2 (2 mm)
visit("2023-12-05", GULF, VASC_MD, "Follow-Up (duplex review)",
      "Review of left leg venous duplex; ongoing heaviness.",
      ["Returns to review the 11/14/2023 left lower extremity venous duplex. Symptoms unchanged since October: heaviness and aching by "
       "mid-afternoon on teaching days, evening ankle swelling, better on weekends and when she elevates. Ibuprofen 400 mg two to three times "
       "per week. No new symptoms. No cramping, no skin change, no ulcer.",
       "Duplex (reviewed with patient): deep venous system patent and compressible, no DVT. Saphenofemoral junction with brief reflux of "
       "0.4 seconds on Valsalva, which is below the 0.5 second threshold used in this practice; GSV diameter 3.9 mm at the junction and 3.2 mm "
       "at mid-thigh. Small saphenous vein competent. No incompetent perforators."],
      ["Left lower extremity symptoms with early, sub-threshold GSV reflux on duplex. CEAP C2 (small varicosities), Ep, As, Pn/Pr borderline.",
       "No procedural indication at this time. Begin conservative management: leg elevation 3–4 times daily, daily walking, calf raises at the "
       "classroom desk, weight management, ibuprofen PRN. Compression stockings recommended again; patient prefers to try the other measures "
       "first through the holidays and will return in 2 months to be fitted if symptoms persist.",
       "Return 2 months. Repeat duplex in 1–2 years or sooner if symptoms progress."],
      exam=vascular_exam(D("2023-12-05"),
                         "Medial calf: cluster of three small varicosities in the GSV distribution, the largest measuring approximately 2 mm "
                         "in diameter, with surrounding reticular veins. Trace pitting edema at the medial malleolus at 2:40 pm. No "
                         "pigmentation, no eczema, no lipodermatosclerosis, no ulcer. Calf soft and non-tender."),
      orders=["Return 2 months"],
      cpt_icd=[("99213", "Established patient, low complexity"), ("I83.812", "Varicose veins of left lower extremity with pain")])

# 4 -------------------------------------------------------------- m3 urgent care
visit("2024-01-09", UC, UC_MD1, "Urgent Care Visit",
      "Facial pressure, nasal congestion and purulent drainage x 11 days.",
      ["55-year-old female with 11 days of nasal congestion, thick yellow-green drainage, left maxillary pressure and low-grade fever to 100.4 °F "
       "that improved after day 5 then worsened again on day 9 ('double worsening'). Tried oral pseudoephedrine, saline rinses and "
       "acetaminophen with partial relief. No dental pain, no visual change, no severe headache. Non-smoker. No recent antibiotics.",
       "Chronic issues stable; she mentions her vascular surgeon has her elevating the left leg for varicose veins; not a concern today."],
      ["Acute bacterial rhinosinusitis, left maxillary, meeting criteria for antibiotics (duration > 10 days with double worsening). "
       "Amoxicillin-clavulanate 875/125 mg BID x 7 days. Continue saline irrigation; intranasal fluticasone. Return if fever > 102 °F, "
       "periorbital swelling or no improvement in 72 hours.",
       "Follow up with PCP as scheduled."],
      exam=[("General", "Mildly uncomfortable, non-toxic."), ("HEENT", "Left maxillary sinus tenderness to percussion. Nasal mucosa erythematous "
            "and edematous with purulent discharge from the left middle meatus. Tympanic membranes normal. Oropharynx with post-nasal drip."),
            ("Neck", "No lymphadenopathy, no meningismus."), ("Lungs", "Clear bilaterally."), ("Cardiovascular", "Regular, no murmur.")],
      orders=["Amoxicillin-clavulanate 875/125 mg, #14, BID", "Fluticasone nasal spray OTC"],
      cpt_icd=[("99213", "Urgent care visit, low complexity"), ("J01.00", "Acute maxillary sinusitis")])

# 5 -------------------------------------------------------------- m3 PCP
visit("2024-01-23", PCP, PCP_MD, "Chronic Care Follow-Up (hypertension)",
      "Hypertension follow-up; home readings elevated.",
      ["Home blood pressure log over 3 weeks averages 142/88 (range 136–151 / 84–93), up from 120s–130s last year. She has gained 4 lb since "
       "October (holidays, less walking because her left leg aches by evening). No headache, chest pain or visual change. Takes losartan "
       "50 mg daily without missed doses. Sodium intake up with school cafeteria lunches. Sinusitis last month resolved with antibiotics.",
       "Left leg: continuing elevation and walking per vascular surgery; has not yet started compression stockings; has a follow-up with "
       "Dr. Vasquez next month."],
      ["Essential hypertension, above goal on home readings. Increase losartan to 100 mg daily. Repeat BMP in 2 weeks for potassium and "
       "creatinine. Reinforce DASH diet and sodium under 2 g. Home BP log, return 6–8 weeks.",
       "Hypothyroidism, stable, TSH 10/2023 was 3.1. Continue levothyroxine 50 mcg.",
       "Hyperlipidemia, newly flagged: LDL 158 on 10/2023 labs. Discussed lifestyle; recheck lipids in 4 months and decide on a statin.",
       "Varicose veins left leg — followed by vascular surgery."],
      orders=["BMP in 2 weeks", "Losartan 100 mg daily, #90"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I10", "Essential hypertension"), ("E78.5", "Hyperlipidemia")])

# 6 -------------------------------------------------------------- m4 (compression starts, dated)
visit("2024-02-13", GULF, VASC_MD, "Follow-Up (conservative management)",
      "Persistent left leg heaviness and evening swelling despite elevation and walking.",
      ["Returns 2 months after starting elevation, walking and calf exercises. She reports partial compliance with elevation (most evenings) "
       "and walking (3 nights per week). Symptoms persist: heaviness and aching by early afternoon on school days, evening ankle swelling "
       "that now sometimes leaves a sock line, and new intermittent night cramps in the left calf about once a week. Ibuprofen 2–3 times "
       "per week. No ulcer, no bleeding, no thrombophlebitis.",
       "She is now willing to try compression. She was measured by our fitter this morning (ankle circumference 23 cm, calf 38 cm) and "
       "fitted with knee-high graduated compression stockings, 20–30 mmHg, size medium-regular.",
       "Patient fitted today, February 13, 2024, with 20–30 mmHg graduated knee-high compression stockings for the left leg; instructed to "
       "wear them daily from morning until bedtime. Start date of compression therapy: 02/13/2024.",
       "She asks about the long term; we discussed that if a 3-month trial of compression plus the other measures does not control "
       "symptoms, and if reflux on repeat duplex meets threshold, endovenous ablation would be an option."],
      ["Symptomatic left lower extremity varicose veins / early superficial venous insufficiency, CEAP C2 with evening edema (C2–C3), "
       "conservative management.",
       "Compression therapy initiated today (20–30 mmHg graduated knee-high, daily) in addition to elevation, walking and ibuprofen PRN. "
       "Written stocking care instructions provided. Return in 3 months to assess response; sooner for new symptoms."],
      exam=vascular_exam(D("2024-02-13"),
                         "Medial calf varicosities in the GSV distribution, unchanged in extent from December. Mild pitting ankle edema at "
                         "1:15 pm. No pigmentation, no eczema, no ulcer. Calf soft, non-tender."),
      orders=["Graduated compression stockings, knee-high, 20–30 mmHg, left, 2 pairs (A6531)", "Return 3 months"],
      cpt_icd=[("99213", "Established patient, low complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 7–9 ------------------------------------------------------------ m5–m6 physical therapy (right knee)
PT_TABLE_HDR = ["Exercise", "Sets x Reps", "Load / Band", "Tolerance"]
visit("2024-03-19", PT, PT_DPT, "Physical Therapy Initial Evaluation",
      "Right anterior knee pain x 6 weeks, worse on stairs. Referred by Dr. Raman.",
      ["56-year-old female teacher with 6 weeks of right anterior knee pain, insidious onset after starting a stair-climbing program at school "
       "in January. Pain 4/10 on stairs and after prolonged sitting ('theater sign'), 1/10 at rest. No locking, giving way or effusion. "
       "Right knee X-ray 03/12/2024 reviewed: no fracture, mild patellofemoral joint space narrowing.",
       "Relevant history: left leg varicose veins managed by vascular surgery with compression stockings; patient wears a left knee-high "
       "stocking and asks that exercises not require removing it."],
      ["Patellofemoral pain syndrome, right, with hip abductor weakness and quadriceps inhibition. Plan: 2x/week for 6 weeks — hip and "
       "quadriceps strengthening, patellar mobilization, taping, home program. Goals: stairs pain-free (0–1/10) in 6 weeks, single-leg "
       "squat with neutral knee alignment."],
      exam=[("Observation", "Mild genu valgum on single-leg squat right; no effusion."), ("Range of Motion", "Right knee 0–135°, equal to left."),
            ("Strength", "Right hip abduction 4-/5, quadriceps 4/5, left 5/5 throughout."), ("Special Tests", "Patellar grind positive, McMurray negative, Lachman negative."),
            ("Palpation", "Tenderness medial patellar facet. No joint line tenderness."),
            ("Left Lower Extremity", "Wearing a 20–30 mmHg knee-high compression stocking per patient report; not removed for examination.")],
      table=(PT_TABLE_HDR, [["Clamshell", "3 x 12", "Green band", "No pain"], ["Straight leg raise", "3 x 10", "Body weight", "No pain"],
                            ["Wall sit 30 s", "3", "Body weight", "2/10"], ["Step-down 4 in", "2 x 8", "Body weight", "3/10"]]),
      cpt_icd=[("97161", "PT evaluation, low complexity"), ("97110", "Therapeutic exercise"), ("M22.2X1", "Patellofemoral disorder, right knee")])

visit("2024-04-02", PT, PT_DPT, "Physical Therapy Treatment (visit 3 of 12)",
      "Right knee pain, improving.",
      ["Reports stair pain down to 2/10. Doing the home program 5 days per week. No new complaints.",
       "Notes she keeps her left compression stocking on for sessions; no problems with it."],
      ["Progressing well. Advanced to lateral step-ups and single-leg balance. Continue 2x/week."],
      exam=[("Strength", "Right hip abduction 4/5, quadriceps 4+/5."), ("Observation", "Improved knee alignment on step-down.")],
      table=(PT_TABLE_HDR, [["Clamshell", "3 x 15", "Blue band", "No pain"], ["Lateral step-up 6 in", "3 x 10", "Body weight", "1/10"],
                            ["Single-leg balance", "3 x 30 s", "Foam pad", "No pain"], ["Bike warm-up", "8 min", "Level 3", "No pain"]]),
      cpt_icd=[("97110", "Therapeutic exercise"), ("97140", "Manual therapy"), ("M22.2X1", "Patellofemoral disorder, right knee")])

visit("2024-04-16", PT, PT_DPT, "Physical Therapy Treatment (visit 6 of 12)",
      "Right knee pain, nearly resolved.",
      ["Stair pain 0–1/10. Returned to full stair program at school. Home program adherence good.",
       "Patient comments that the left-leg compression stocking she wears daily for her vein condition is 'getting hot' as spring arrives "
       "but she is still putting it on each morning."],
      ["Goals met. Discharge to independent home program with written progression. Re-evaluate PRN."],
      exam=[("Strength", "Right hip abduction 5/5, quadriceps 5/5."), ("Functional", "Single-leg squat with neutral alignment, 10 reps pain-free.")],
      table=(PT_TABLE_HDR, [["Lateral step-up 8 in", "3 x 12", "Body weight", "0/10"], ["Single-leg RDL", "3 x 8", "10 lb", "0/10"],
                            ["Split squat", "3 x 10", "Body weight", "1/10"]]),
      cpt_icd=[("97110", "Therapeutic exercise"), ("M22.2X1", "Patellofemoral disorder, right knee")])

# 10 ------------------------------------------------------------- m7 PCP
visit("2024-05-21", PCP, PCP_MD, "Chronic Care Follow-Up (hypertension, lipids)",
      "Blood pressure recheck and lipid results.",
      ["Home BP log averages 128/80 on losartan 100 mg. BMP 02/2024: potassium 4.3, creatinine 0.82. No side effects. Fasting lipid panel "
       "05/14/2024: total cholesterol 238, LDL 161, HDL 52, triglycerides 128. 10-year ASCVD risk 8.9%. She finished physical therapy for "
       "the right knee with good result. Weight stable.",
       "Left leg: continues to follow with vascular surgery; wearing the compression stocking most days, says it is uncomfortable now that "
       "the weather is warm."],
      ["Essential hypertension, at goal on losartan 100 mg. Continue.",
       "Hyperlipidemia, LDL 161 despite 4 months of lifestyle change, intermediate risk. Shared decision: start atorvastatin 20 mg nightly. "
       "Lipids and hepatic panel in 8–12 weeks.",
       "Hypothyroidism, stable. Varicose veins, left — per vascular surgery.",
       "Return 3 months."],
      orders=["Atorvastatin 20 mg nightly, #90", "Lipid panel and hepatic function panel in 8–12 weeks"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I10", "Essential hypertension"), ("E78.5", "Hyperlipidemia")])

# 11 ------------------------------------------------------------- m9 dermatology (interruption)
visit("2024-07-16", DERM, DERM_MD, "New Patient — Full Skin Examination",
      "Annual skin check requested; several 'spots' on the face and back; itchy hands.",
      ["56-year-old female, Fitzpatrick type III, with extensive childhood sun exposure in Florida, no prior skin cancer, no family history "
       "of melanoma. Requests a full skin examination. Reports a rough scaly spot on the left temple present for several months and several "
       "raised brown 'barnacles' on the back. Also 3 months of dry, itchy, cracking skin on the dorsal hands and finger webs, worse with "
       "frequent hand-washing and classroom sanitizer.",
       "Review of lower extremities: she has varicose veins on the left leg followed by vascular surgery and was prescribed compression "
       "stockings earlier this year.",
       "She mentions she \"stopped wearing stockings for the summer\" — she took them off at the beginning of May because of the heat and "
       "has not worn them since; she plans to resume when school starts.",
       "Medications: losartan, levothyroxine, atorvastatin, ibuprofen PRN. No photosensitizing agents."],
      ["Actinic keratosis, left temple, solitary, 6 mm. Cryotherapy with liquid nitrogen, 2 freeze–thaw cycles, performed today.",
       "Seborrheic keratoses, back and chest, multiple, benign. Reassurance; no treatment.",
       "Irritant hand dermatitis. Emollient regimen, barrier technique, avoid sanitizer when soap and water are available. If no better in "
       "8 weeks, will add a mid-potency topical steroid.",
       "Left lower extremity: varicose veins without stasis dermatitis, pigmentation or ulcer on today's skin exam; defer management to "
       "vascular surgery; encouraged her to resume compression as planned.",
       "Return 4 months for hand dermatitis follow-up and AK site check; annual full skin exam thereafter."],
      exam=[("Skin — Face", "6 mm rough erythematous scaly papule left temple consistent with actinic keratosis. Solar lentigines bilateral cheeks."),
            ("Skin — Trunk", "Multiple 4–10 mm stuck-on waxy brown papules and plaques upper back and chest, seborrheic keratoses. No atypical nevi."),
            ("Skin — Hands", "Dorsal hands and finger webs with xerosis, fine scale, fissuring of the 3rd and 4th webs; no vesicles."),
            ("Skin — Lower Extremities", "Left medial calf varicosities, small, without hemosiderin pigmentation, eczema, atrophie blanche or "
             "ulceration. Mild ankle edema. Right leg unremarkable. Nails normal."),
            ("Lymph", "No cervical, axillary or inguinal adenopathy.")],
      orders=["Cryotherapy, 1 lesion (17000)", "Ceramide emollient OTC"],
      cpt_icd=[("99203", "New patient, low complexity"), ("17000", "Destruction premalignant lesion, first"), ("L57.0", "Actinic keratosis"), ("L82.1", "Seborrheic keratosis"), ("L24.9", "Irritant contact dermatitis")])

# 12 ------------------------------------------------------------- m10 urgent care
visit("2024-08-06", UC, UC_MD2, "Urgent Care Visit",
      "Red, warm, painful area on right forearm after insect bite 3 days ago.",
      ["56-year-old female with a mosquito bite on the right volar forearm 3 days ago, now with 5 x 4 cm area of spreading redness, warmth, "
       "and tenderness, and streaking 2 cm proximally. No fever, no purulence, no fluctuance. No diabetes. Tetanus up to date (2019). "
       "Scratched the bite repeatedly.",
       "Otherwise well. She notes she is back in the classroom pre-planning this week."],
      ["Non-purulent cellulitis, right forearm, with early lymphangitis. Cephalexin 500 mg QID x 7 days. Margins marked; elevate; warm "
       "compresses. Return in 48 hours if the redness extends beyond the marked line or if fever develops."],
      exam=[("General", "Afebrile, non-toxic."), ("Skin", "Right volar forearm: 5 x 4 cm erythema, warmth, induration around a central excoriated "
            "papule; 2 cm lymphangitic streak; no fluctuance or abscess."), ("Lymph", "No epitrochlear or axillary adenopathy."), ("Cardiovascular", "Regular rate, no murmur.")],
      orders=["Cephalexin 500 mg #28, QID x 7 days"],
      cpt_icd=[("99213", "Urgent care visit, low complexity"), ("L03.113", "Cellulitis of right upper limb"), ("W57.XXXA", "Insect bite")])

# 13 ------------------------------------------------------------- m11 vascular (restart, dated)
visit("2024-09-17", GULF, VASC_MD, "Follow-Up (conservative management)",
      "Left leg heaviness, aching and swelling, worse with return to school.",
      ["Patient returns later than planned (last seen 02/13/2024). She started 20–30 mmHg compression stockings on 02/13/2024 and wore "
       "them daily through April. She stopped wearing them at the beginning of May 2024 because of the heat and did not wear them through "
       "the summer. During the summer break, with less standing, symptoms were tolerable. Since the school year began in mid-August the "
       "heaviness, aching and evening ankle swelling are back and are worse than last spring; she now has night cramps 2–3 times per week "
       "and the leg 'throbs' by the last period. Ibuprofen 3–4 times per week.",
       "Functional impact: she sits on a stool to teach the last two periods, has stopped evening walks entirely on school days, and "
       "asked the principal to be excused from car-line duty, which requires 40 minutes of standing.",
       "No ulcer, no bleeding, no thrombophlebitis. No DVT. Cellulitis of the right forearm last month resolved; she developed a mild rash "
       "on cephalexin, now listed as an allergy.",
       "Compression therapy restarted today, 09/17/2024: 20–30 mmHg graduated knee-high stockings, left leg, daily from morning until "
       "bedtime, with a re-fitting (new pair dispensed, same size). She agrees to wear them without interruption, including the summer, "
       "and to keep a log.",
       "Discussed that for insurance purposes a continuous trial of at least 3 months is required and that the interrupted spring trial "
       "(02/13/2024 to early May 2024) does not count as a completed trial."],
      ["Symptomatic left lower extremity varicose veins and superficial venous insufficiency, CEAP C2–C3 (evening edema), with worsening "
       "symptoms after an interrupted compression trial.",
       "Compression therapy resumed today (restart date 09/17/2024), 20–30 mmHg graduated knee-high, daily, plus elevation, walking, "
       "ibuprofen PRN. Return 3 months with the compliance log. If symptoms persist at 3 months of uninterrupted compression, repeat "
       "the venous duplex and discuss endovenous ablation."],
      exam=vascular_exam(D("2024-09-17"),
                         "Medial calf and distal thigh varicosities in the GSV distribution, more prominent than in February; mild pitting "
                         "edema at the ankle at 3:30 pm. No pigmentation, eczema or ulcer. Calf soft, non-tender."),
      orders=["Graduated compression stockings, knee-high, 20–30 mmHg, left, 2 pairs (A6531)", "Return 3 months"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 14 ------------------------------------------------------------- m12 PCP annual
visit("2024-10-15", PCP, PCP_MD, "Annual Physical / Preventive Visit",
      "Annual physical.",
      ["Annual visit. Hypertension at goal on losartan 100 mg (home average 126/78). Lipids 08/2024 on atorvastatin 20 mg: LDL 96, ALT "
       "normal. TSH 09/2024: 5.9 (elevated) with free T4 low-normal, mild fatigue and cold intolerance. Vitamin D 09/2024: 22 ng/mL. "
       "Mammogram 11/2023 BI-RADS 1. Influenza vaccine today.",
       "Left leg: she restarted compression stockings on 09/17/2024 under vascular surgery and reports wearing them every day since; "
       "symptoms still present by late afternoon. Followed by Dr. Vasquez."],
      ["Hypothyroidism, under-replaced (TSH 5.9). Increase levothyroxine to 75 mcg daily; TSH in 8 weeks.",
       "Vitamin D insufficiency: cholecalciferol 2000 IU daily.", "Hypertension, at goal. Hyperlipidemia, at goal on atorvastatin 20 mg.",
       "Varicose veins left leg with chronic venous insufficiency, symptomatic, on compression per vascular surgery.",
       "Preventive: influenza vaccine given. Mammogram due 11/2024 — ordered. Return 6 months."],
      orders=["Levothyroxine 75 mcg daily, #90", "Cholecalciferol 2000 IU daily OTC", "TSH in 8 weeks", "Screening mammogram", "Influenza vaccine, administered"],
      cpt_icd=[("99396", "Preventive visit, established"), ("E03.9", "Hypothyroidism"), ("E55.9", "Vitamin D deficiency"), ("I10", "Essential hypertension")])

# 15 ------------------------------------------------------------- m13 derm
visit("2024-11-12", DERM, DERM_MD, "Follow-Up",
      "Hand dermatitis not improved; AK site check.",
      ["Hand dermatitis persists despite 4 months of emollients and barrier measures; worse with the school year. Itching interferes with "
       "grading papers. AK site on left temple healed without recurrence.",
       "She is wearing her left compression stocking today ('every day since September')."],
      ["Irritant hand dermatitis, persistent. Add triamcinolone 0.1% cream BID PRN to the hands for up to 2 weeks at a time; continue emollients.",
       "Actinic keratosis, left temple, resolved after cryotherapy. Return 9 months for annual full skin exam."],
      exam=[("Skin — Hands", "Dorsal hands with lichenified plaques, fissures 3rd/4th webs, no vesicles, no nail changes."),
            ("Skin — Face", "Left temple: faint hypopigmented macule at prior cryotherapy site; no residual AK."),
            ("Skin — Legs", "Left knee-high compression stocking in place; not removed.")],
      orders=["Triamcinolone 0.1% cream 30 g, BID PRN"],
      cpt_icd=[("99213", "Established patient, low complexity"), ("L24.9", "Irritant contact dermatitis")])

# 16 ------------------------------------------------------------- m14 vascular (3 months of run 2)
visit("2024-12-17", GULF, VASC_MD, "Follow-Up (3-month compression check)",
      "Left leg heaviness, aching, swelling and night cramps, unchanged on daily compression.",
      ["Three months since compression was restarted on 09/17/2024. Compliance log reviewed: stocking worn daily, 6–7 days per week, "
       "no missed weeks; she removes it at bedtime. Elevation most evenings, walking 2 nights per week. Ibuprofen 3 times per week.",
       "Symptoms are unchanged: aching and heaviness by early afternoon on every teaching day, visible ankle swelling by evening, night "
       "cramps 2 times per week. Compression 'helps a little in the morning' but by afternoon the leg aches regardless. No ulcer, no "
       "bleeding, no phlebitis.",
       "Functional impact unchanged from September: teaching from a stool, no evening walks on school days, excused from car-line duty."],
      ["Symptomatic left lower extremity superficial venous insufficiency, CEAP C3 (edema), with persistent symptoms after 3 months of "
       "uninterrupted 20–30 mmHg compression (09/17/2024 to 12/17/2024) plus elevation, exercise and NSAIDs; no improvement.",
       "Patient prefers to continue conservative management through the school year and revisit after summer, as she is the sole caregiver "
       "for her mother and cannot schedule a procedure now. Continue compression without interruption. Return 3 months. Repeat duplex "
       "before any procedure."],
      exam=vascular_exam(D("2024-12-17"),
                         "Medial calf and distal thigh varicosities in the GSV distribution, tortuous, unchanged from September. 1+ pitting "
                         "ankle edema at 2:00 pm despite the stocking being worn until the exam. No pigmentation, eczema or ulcer."),
      orders=["Continue compression 20–30 mmHg daily", "Return 3 months"],
      cpt_icd=[("99213", "Established patient, low complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 17 ------------------------------------------------------------- m15 urgent care (bronchitis, CXR)
visit("2025-01-14", UC, UC_MD3, "Urgent Care Visit",
      "Cough x 9 days, now productive, with chest tightness.",
      ["56-year-old non-smoker with 9 days of cough after an upper respiratory infection, now productive of yellow sputum, with chest "
       "tightness on coughing, no hemoptysis, low-grade fever to 100.1 °F on day 3 only, no dyspnea at rest. Many sick children in the "
       "classroom. No wheeze history, no asthma.",
       "Wearing a compression stocking on the left leg for varicose veins; denies calf pain or unilateral swelling beyond her usual."],
      ["Acute bronchitis, likely viral. Chest X-ray today without infiltrate (see report). Benzonatate 100 mg TID PRN x 7 days, honey, "
       "fluids, rest. No antibiotics indicated. Return for fever, dyspnea or symptoms beyond 3 weeks."],
      exam=[("General", "Afebrile, non-toxic, speaking full sentences."), ("Lungs", "Scattered rhonchi that clear with cough; no focal crackles, no wheeze. SpO2 98%."),
            ("Cardiovascular", "Regular, no murmur."), ("HEENT", "Mild pharyngeal erythema.")],
      orders=["Chest X-ray, PA and lateral (71046)", "Benzonatate 100 mg #21"],
      cpt_icd=[("99213", "Urgent care visit, low complexity"), ("71046", "Chest X-ray 2 views"), ("J20.9", "Acute bronchitis")])

# 18 ------------------------------------------------------------- m16 PCP
visit("2025-02-11", PCP, PCP_MD, "Chronic Care Follow-Up",
      "Thyroid recheck; blood pressure; medication refills.",
      ["TSH 12/2024 on levothyroxine 75 mcg: 2.4, fatigue improved. Home BP average 124/78. Hand dermatitis resolved with triamcinolone; "
       "stopped using it. Bronchitis last month resolved. Mammogram 11/2024 BI-RADS 2, benign.",
       "Left leg: wearing compression stocking daily since September per vascular surgery; still symptomatic by afternoon; she is deferring "
       "a procedure because she is caring for her mother."],
      ["Hypothyroidism, euthyroid on 75 mcg. Continue; TSH annually.", "Hypertension, at goal. Hyperlipidemia, at goal.",
       "Hand dermatitis resolved; triamcinolone discontinued from the medication list.",
       "Varicose veins/chronic venous insufficiency, left, symptomatic on compression — per vascular surgery. Refills sent. Return 6 months."],
      orders=["Losartan 100 mg #90", "Levothyroxine 75 mcg #90", "Atorvastatin 20 mg #90"],
      cpt_icd=[("99213", "Established patient, low complexity"), ("E03.9", "Hypothyroidism"), ("I10", "Essential hypertension")])

# 19 ------------------------------------------------------------- m17 vascular (6 months of run 2)
visit("2025-03-18", GULF, VASC_MD, "Follow-Up (conservative management)",
      "Persistent left leg symptoms on compression; discussion of ablation.",
      ["Six months of uninterrupted 20–30 mmHg compression (since 09/17/2024), log reviewed, daily use confirmed. Symptoms persist: aching "
       "and heaviness daily by early afternoon, evening ankle edema, night cramps 1–2 per week, new itching over the medial calf. Ibuprofen "
       "3 times per week. No ulcer, bleeding or phlebitis.",
       "ADLs: continues to teach from a stool, excused from standing duties, has not resumed evening walks, and reports she can no longer "
       "do her Saturday grocery and errand round without a mid-trip sit-down. She remains her mother's caregiver and asks to defer any "
       "procedure until after the summer when respite care is arranged."],
      ["Symptomatic left lower extremity superficial venous insufficiency, CEAP C3, persistent after 6 months of continuous compression "
       "and conservative measures without improvement.",
       "Endovenous ablation discussed in detail (radiofrequency vs laser, risks, benefits, alternatives); patient wishes to defer until "
       "fall 2025 for family reasons. Continue compression without interruption. Return 4 months. Repeat left venous reflux duplex to be "
       "ordered within 3 months of any planned procedure."],
      exam=vascular_exam(D("2025-03-18"),
                         "Tortuous varicosities medial calf and distal medial thigh in the GSV distribution. 1+ pitting ankle edema at "
                         "3:00 pm with stocking worn until arrival. Mild dry scale medial calf without pigmentation or eczema. No ulcer."),
      orders=["Continue compression 20–30 mmHg daily", "Return 4 months"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 20–21 ---------------------------------------------------------- m18–m19 PT (right shoulder)
visit("2025-04-22", PT, PT_DPT, "Physical Therapy Initial Evaluation",
      "Right shoulder pain with overhead reaching x 2 months. Referred by Dr. Raman.",
      ["57-year-old right-handed teacher with 2 months of right lateral shoulder pain reaching overhead to the whiteboard and lifting boxes "
       "during a classroom move. Night pain lying on the right side. No trauma, no numbness. Pain 5/10 with overhead reach, 1/10 at rest.",
       "Left compression stocking worn daily per vascular surgery; not relevant to today's treatment."],
      ["Right subacromial pain syndrome / rotator cuff tendinopathy with scapular dyskinesis. Plan 2x/week x 6 weeks: scapular stabilization, "
       "rotator cuff strengthening, posterior capsule stretching, postural training."],
      exam=[("Range of Motion", "Right shoulder flexion 160° (painful arc 90–120°), abduction 150°, ER 80°, IR to L1. Left full."),
            ("Strength", "Right supraspinatus 4/5 painful, ER 4/5, scapular retractors 4-/5."), ("Special Tests", "Hawkins-Kennedy positive, Neer positive, empty can painful, drop arm negative.")],
      table=(PT_TABLE_HDR, [["Scapular retraction", "3 x 15", "Red band", "No pain"], ["Sidelying ER", "3 x 12", "2 lb", "2/10"],
                            ["Sleeper stretch", "3 x 30 s", "—", "Stretch only"], ["Wall slides", "3 x 10", "Body weight", "1/10"]]),
      cpt_icd=[("97161", "PT evaluation, low complexity"), ("M75.41", "Impingement syndrome of right shoulder")])

visit("2025-05-06", PT, PT_DPT, "Physical Therapy Treatment (visit 4 of 12)",
      "Right shoulder pain, improving.",
      ["Overhead pain down to 2/10; night pain resolved. Home program 5–6 days per week.",
       "Mentions her left leg aches by the end of the school day despite her stocking; unrelated to today's treatment."],
      ["Progressing. Advanced rotator cuff loading; added overhead press pattern. Continue 2x/week."],
      exam=[("Range of Motion", "Right flexion 170°, painful arc diminished."), ("Strength", "Supraspinatus 4+/5, ER 4+/5.")],
      table=(PT_TABLE_HDR, [["Sidelying ER", "3 x 15", "3 lb", "1/10"], ["Prone Y/T/W", "3 x 10", "1 lb", "No pain"],
                            ["Overhead press", "3 x 10", "5 lb", "2/10"], ["Rows", "3 x 12", "Blue band", "No pain"]]),
      cpt_icd=[("97110", "Therapeutic exercise"), ("97140", "Manual therapy"), ("M75.41", "Impingement syndrome of right shoulder")])

# 22 ------------------------------------------------------------- m20 urgent care (calf DVT, treated)
visit("2025-06-10", UC, UC_MD1, "Urgent Care Visit",
      "Right calf pain and swelling x 2 days after a long car trip.",
      ["57-year-old female with 2 days of right calf pain and swelling that began the day after a 9-hour car drive back from Atlanta "
       "(school-break trip). Pain is a deep ache, worse walking, right calf visibly larger than the left. No chest pain, no dyspnea, no "
       "hemoptysis. No trauma. Not on hormonal therapy. Non-smoker. Family history: mother had varicose veins; no family history of clots.",
       "Of note, the LEFT leg is the one followed by vascular surgery for varicose veins (compression stocking worn daily); the current "
       "complaint is in the previously asymptomatic RIGHT leg. Wells score 3 (calf swelling > 3 cm, localized tenderness, recent "
       "immobilization): DVT likely.",
       "Same-day venous duplex of the right lower extremity obtained at Carrollwood Imaging: acute deep vein thrombosis of the right "
       "posterior tibial vein (calf), non-occlusive, proximal veins patent. See report.",
       "Treatment started today: apixaban 10 mg BID x 7 days, then 5 mg BID, planned duration 3 months (provoked distal DVT). First dose "
       "given in clinic. Ibuprofen stopped; acetaminophen for pain. PCP notified by phone and follow-up arranged in 1 week."],
      ["Acute provoked deep vein thrombosis, right posterior tibial vein (calf DVT), after prolonged travel. Hemodynamically stable, no "
       "features of PE. Treated: apixaban started today 06/10/2025 (10 mg BID x 7 days, then 5 mg BID for 3 months total). Avoid NSAIDs. "
       "Ambulate. Return precautions for chest pain, dyspnea, bleeding, or extension of swelling. Follow up with PCP 1 week; vascular "
       "surgery informed."],
      exam=[("General", "Afebrile, comfortable at rest, SpO2 98% RA, HR 78."),
            ("Right Lower Extremity", "Calf circumference 39.5 cm (left 36.0 cm, measured 10 cm below tibial tuberosity). Tenderness along the "
             "posterior tibial vein distribution; mild pitting edema at the ankle; no erythema; Homans equivocal. Pulses 2+."),
            ("Left Lower Extremity", "Compression stocking in place; medial calf varicosities; mild chronic ankle edema; no tenderness."),
            ("Lungs", "Clear."), ("Cardiovascular", "Regular rate, no murmur.")],
      orders=["Venous duplex, right lower extremity, STAT (93970)", "Apixaban 10 mg #14 then 5 mg #180", "CBC, BMP, PT/INR today"],
      cpt_icd=[("99214", "Urgent care visit, moderate complexity"), ("I82.451", "Acute embolism and thrombosis of right posterior tibial vein"), ("Z79.01", "Long-term anticoagulant use")])

# 23 ------------------------------------------------------------- m20 PCP DVT follow-up
visit("2025-06-17", PCP, PCP_MD, "Acute Follow-Up (DVT)",
      "One-week follow-up after right calf DVT diagnosed at urgent care.",
      ["Right calf pain and swelling improving on apixaban; no bleeding, no chest symptoms. Completed the 7-day loading dose today and "
       "transitions to 5 mg BID. Labs 06/10: hemoglobin 13.4, platelets 248, creatinine 0.80, INR 1.0. Provoked distal DVT after travel; "
       "no thrombophilia testing indicated. Vascular surgery (Dr. Vasquez) aware; her planned left GSV evaluation will proceed once "
       "anticoagulation is complete.",
       "Left leg: still wearing the compression stocking daily; symptoms unchanged."],
      ["Acute provoked right posterior tibial vein DVT, treated with apixaban; planned 3-month course through 09/16/2025. Compression "
       "stocking for the right leg optional for symptom relief. Repeat right LE duplex at end of therapy.",
       "Hypertension, hypothyroidism, hyperlipidemia stable. Return 3 months or sooner."],
      orders=["Apixaban 5 mg BID (continue)", "Right LE venous duplex in 3 months"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I82.451", "Acute DVT right posterior tibial vein"), ("Z79.01", "Long-term anticoagulant use")])

# 24 ------------------------------------------------------------- m21 vascular
visit("2025-07-15", GULF, VASC_MD, "Follow-Up (conservative management; interval DVT)",
      "Left leg symptoms persist on compression; interval right calf DVT.",
      ["Interval history: provoked right posterior tibial (calf) DVT on 06/10/2025 after a long car trip, diagnosed at urgent care, on "
       "apixaban 5 mg BID through mid-September. Right calf symptoms nearly resolved. The DVT was in the contralateral (right) leg; the "
       "left deep system was normal on the 11/2023 duplex and the right-leg duplex of 06/10/2025 noted patent proximal veins.",
       "Left leg: compression 20–30 mmHg worn daily without interruption since 09/17/2024 (10 months), log reviewed. Symptoms persist and "
       "are slightly worse during the summer heat even without school: aching and heaviness by mid-afternoon, evening ankle edema, "
       "itching medial calf, cramps 1–2 nights per week. Acetaminophen in place of ibuprofen while anticoagulated.",
       "She has arranged respite care for her mother starting October and would like to plan ablation of the left GSV for the fall, "
       "after anticoagulation is complete."],
      ["Symptomatic left lower extremity superficial venous insufficiency, CEAP C3, persistent after 10 months of uninterrupted "
       "compression. Candidate for endovenous ablation of the left GSV; plan after completion of apixaban (09/16/2025) and a normal "
       "right-leg follow-up duplex.",
       "Right calf DVT, provoked, on treatment — managed by PCP. Not a contraindication to left GSV ablation once anticoagulation is "
       "complete and the deep system is confirmed patent on pre-procedure duplex.",
       "Continue compression. Return 4 months; order a repeat left venous reflux duplex within 3 months of the planned procedure date."],
      exam=vascular_exam(D("2025-07-15"),
                         "Tortuous varicosities medial calf and distal medial thigh (GSV distribution), unchanged. 1+ pitting ankle edema. "
                         "Mild xerosis medial calf; no pigmentation, eczema, lipodermatosclerosis or ulcer."),
      orders=["Continue compression 20–30 mmHg daily", "Return 4 months"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)"), ("I82.451", "DVT right posterior tibial vein, on treatment")])

# 25 ------------------------------------------------------------- m22 derm annual
visit("2025-08-19", DERM, DERM_MD, "Annual Full Skin Examination",
      "Annual skin check; new spot on right shoulder.",
      ["Annual skin exam. New 5 mm pink pearly papule right shoulder, 3 months, bleeds with towel drying. Hands well controlled with "
       "emollients. On apixaban for a right calf DVT (06/2025) through mid-September — biopsy bleeding risk discussed; she prefers to "
       "proceed with a shave biopsy today with careful hemostasis.",
       "Legs: left varicose veins, wears compression daily; no leg skin complaints."],
      ["Suspected basal cell carcinoma, right shoulder: shave biopsy performed under local anesthesia, aluminum chloride hemostasis, "
       "pressure dressing; pathology pending. Will call with results and arrange ED&C or excision as appropriate after anticoagulation ends.",
       "Seborrheic keratoses, stable. Hand dermatitis, controlled. Left leg varicose veins without stasis skin changes. Return for results / 1 year."],
      exam=[("Skin — Right Shoulder", "5 mm pearly pink papule with telangiectasia and a rolled border; dermoscopy with arborizing vessels."),
            ("Skin — Trunk/Extremities", "Stable seborrheic keratoses. Left medial calf varicosities, no hemosiderin, eczema or ulcer. Compression stocking removed for exam and replaced."),
            ("Lymph", "No adenopathy.")],
      orders=["Shave biopsy, right shoulder (11102)", "Dermatopathology"],
      cpt_icd=[("99213", "Established patient"), ("11102", "Tangential biopsy of skin"), ("D48.5", "Neoplasm of uncertain behavior of skin")])

# 26 ------------------------------------------------------------- m23 PCP end of anticoagulation
visit("2025-09-16", PCP, PCP_MD, "Chronic Care Follow-Up (DVT completion)",
      "Completion of 3-month apixaban course; repeat duplex results.",
      ["Completes 3 months of apixaban today. Right LE venous duplex 09/12/2025: posterior tibial vein recanalized, no residual thrombus, "
       "proximal veins patent. No bleeding complications. Right calf asymptomatic. Shoulder biopsy 08/2025: nodular basal cell carcinoma, "
       "ED&C scheduled by dermatology in October now that anticoagulation is finished.",
       "Left leg symptoms persist on daily compression (one year next week); she plans to proceed with vascular surgery's recommendation "
       "for ablation this fall."],
      ["Provoked right calf DVT, completed treatment; apixaban discontinued today. Add Z86.718 (personal history of venous thrombosis) to "
       "the problem list. No indefinite anticoagulation (provoked, distal, resolved). Travel precautions reviewed.",
       "Hypertension, hypothyroidism, hyperlipidemia stable; annual labs next month. Return 1 month for annual physical."],
      orders=["Discontinue apixaban", "Annual fasting labs in 4 weeks"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("Z86.718", "Personal history of other venous thrombosis and embolism")])

# 27 ------------------------------------------------------------- m24 PCP annual
visit("2025-10-21", PCP, PCP_MD, "Annual Physical / Preventive Visit",
      "Annual physical.",
      ["Annual visit. Labs 10/14/2025 reviewed: CMP normal, LDL 88 on atorvastatin 20 mg, TSH 2.1, A1c 5.6, vitamin D 34. Hypertension at "
       "goal. BCC right shoulder treated with ED&C 10/07/2025 by dermatology, healing. Influenza and COVID vaccines today. Mammogram ordered.",
       "Left leg: compression stockings worn daily for over a year (since 09/17/2024); still symptomatic; vascular surgery visit next month "
       "to plan ablation."],
      ["Preventive visit; vaccines given; mammogram ordered. Chronic conditions stable; continue current medications.",
       "History of provoked right calf DVT, resolved. Varicose veins / CVI left leg, symptomatic on compression — per vascular surgery. Return 6 months."],
      orders=["Screening mammogram", "Influenza vaccine; COVID-19 vaccine, administered"],
      cpt_icd=[("99396", "Preventive visit, established"), ("I10", "Essential hypertension"), ("E03.9", "Hypothyroidism"), ("Z86.718", "History of venous thrombosis")])

# 28 ------------------------------------------------------------- m25 vascular
visit("2025-11-18", GULF, VASC_MD, "Follow-Up (pre-procedure planning)",
      "Left leg symptoms persist; planning endovenous ablation.",
      ["Fourteen months of uninterrupted 20–30 mmHg compression (since 09/17/2024) with elevation, walking and analgesics; log reviewed. "
       "Symptoms unchanged to worse: daily afternoon aching and heaviness, evening ankle edema, calf itching, cramps 2 nights per week. "
       "Anticoagulation for the right calf DVT completed 09/16/2025; follow-up right duplex 09/12/2025 showed recanalization.",
       "She wished to schedule ablation for December but her mother was hospitalized this month; she asks to defer again to spring 2026. "
       "ADL impact continues: stool teaching, excused from standing duties, errands split over two days."],
      ["Symptomatic left lower extremity superficial venous insufficiency, CEAP C3, failed conservative management > 12 months. Candidate "
       "for radiofrequency ablation of the left GSV. Patient defers to spring 2026 for family reasons. Continue compression. Return 4–5 "
       "months; repeat left venous reflux duplex to be scheduled within 3 months of the procedure date."],
      exam=vascular_exam(D("2025-11-18"),
                         "Tortuous varicosities medial calf and distal thigh, GSV distribution. 1+ pitting ankle edema at 1:45 pm. Mild "
                         "xerosis. No pigmentation, eczema or ulcer."),
      orders=["Continue compression 20–30 mmHg daily", "Return 4–5 months"],
      cpt_icd=[("99213", "Established patient"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 29 ------------------------------------------------------------- m26 urgent care
visit("2025-12-09", UC, UC_MD2, "Urgent Care Visit",
      "Vomiting and diarrhea x 36 hours.",
      ["57-year-old female with 36 hours of nausea, 4 episodes of non-bloody emesis and 6 watery non-bloody stools, low-grade fever, "
       "diffuse crampy abdominal pain. Several students with the same illness. Tolerating sips. No recent antibiotics, no travel.",
       "History of right calf DVT 06/2025, anticoagulation completed; no leg symptoms today beyond her chronic left leg aching."],
      ["Acute viral gastroenteritis with mild dehydration. Ondansetron ODT 4 mg Q8H PRN x 3 days, oral rehydration, BRAT diet advance as "
       "tolerated. Hold losartan for 48 hours while unable to keep fluids down. Return for blood in stool, inability to keep fluids, or "
       "fever > 102 °F."],
      exam=[("General", "Mildly dehydrated, non-toxic. HR 92, BP 112/70, T 99.4 °F."), ("Abdomen", "Soft, mild diffuse tenderness, hyperactive bowel sounds, no peritoneal signs."),
            ("Extremities", "No calf tenderness; left compression stocking in place.")],
      orders=["Ondansetron ODT 4 mg #9", "BMP today"],
      cpt_icd=[("99213", "Urgent care visit"), ("A08.4", "Viral intestinal infection, unspecified"), ("E86.0", "Dehydration")])

# 30 ------------------------------------------------------------- m27 PCP
visit("2026-01-20", PCP, PCP_MD, "Chronic Care Follow-Up (lipids)",
      "Lipid recheck; statin dose.",
      ["Fasting lipids 01/13/2026: LDL 112, up from 88 (less walking, holiday diet, admits inconsistent atorvastatin dosing over the "
       "holidays). Gastroenteritis in December resolved. BP at goal. Mother's health has stabilized.",
       "Left leg: daily compression continues; still symptomatic; ablation planned for spring with vascular surgery."],
      ["Hyperlipidemia, LDL above goal: increase atorvastatin to 40 mg nightly; lipids in 12 weeks; adherence counseling.",
       "Hypertension, hypothyroidism stable. History of DVT, resolved. Varicose veins left leg — per vascular surgery. Return 3 months."],
      orders=["Atorvastatin 40 mg nightly, #90", "Lipid panel in 12 weeks"],
      cpt_icd=[("99213", "Established patient"), ("E78.5", "Hyperlipidemia"), ("I10", "Essential hypertension")])

# 31–33 ---------------------------------------------------------- m28–m29 PT (low back)
visit("2026-02-17", PT, PT_DPT, "Physical Therapy Initial Evaluation",
      "Low back pain x 3 weeks after lifting a box of textbooks. Referred by Dr. Raman.",
      ["58-year-old teacher with 3 weeks of mechanical low back pain after lifting, 5/10 with flexion and prolonged sitting, no radiation "
       "below the knee, no numbness, no bowel/bladder change. Lumbar X-ray 02/10/2026: mild L4–L5 and L5–S1 degenerative disc disease, "
       "no fracture or spondylolisthesis. Cyclobenzaprine at night from PCP.",
       "Left leg varicose veins with daily compression stocking; left leg aching is chronic and separate from the back complaint."],
      ["Mechanical low back pain with lumbar degenerative disc disease, flexion-intolerant, with core and hip weakness. Plan 2x/week x 6 "
       "weeks: core stabilization, hip hinge training, extension-bias mobility, ergonomic lifting for the classroom."],
      exam=[("Observation", "Flattened lumbar lordosis, guarded flexion."), ("Range of Motion", "Lumbar flexion 50% painful, extension 75%, side-bend full."),
            ("Neurological", "SLR negative bilaterally, reflexes 2+ symmetric, strength 5/5, sensation intact."),
            ("Strength / Motor Control", "Prone plank 20 s, hip extension 4/5 bilaterally, poor hip-hinge pattern."),
            ("Left Lower Extremity", "Compression stocking in place; chronic varicosities noted; no neurological findings.")],
      table=(PT_TABLE_HDR, [["Prone press-up", "3 x 10", "—", "Centralizes"], ["Dead bug", "3 x 10", "Body weight", "No pain"],
                            ["Hip hinge w/ dowel", "3 x 10", "Dowel", "No pain"], ["Glute bridge", "3 x 12", "Body weight", "1/10"]]),
      cpt_icd=[("97161", "PT evaluation, low complexity"), ("M54.50", "Low back pain, unspecified"), ("M51.36", "Other intervertebral disc degeneration, lumbar region")])

visit("2026-03-03", PT, PT_DPT, "Physical Therapy Treatment (visit 4 of 12)",
      "Low back pain, improving.",
      ["Pain 2/10 with sitting, 3/10 with lifting. Sleeping better; cyclobenzaprine only twice this week. Home program daily.",
       "Keeps the left compression stocking on; reports the leg still swells by evening."],
      ["Progressing. Advanced core loading and added kettlebell deadlift pattern 15 lb. Continue 2x/week."],
      exam=[("Range of Motion", "Lumbar flexion 75%, mildly painful at end range."), ("Strength", "Prone plank 45 s, hip extension 4+/5.")],
      table=(PT_TABLE_HDR, [["Bird dog", "3 x 10", "Body weight", "No pain"], ["KB deadlift", "3 x 10", "15 lb", "2/10"],
                            ["Side plank", "3 x 20 s", "Body weight", "No pain"], ["Pallof press", "3 x 12", "Red band", "No pain"]]),
      cpt_icd=[("97110", "Therapeutic exercise"), ("97140", "Manual therapy"), ("M54.50", "Low back pain")])

visit("2026-03-17", PT, PT_DPT, "Physical Therapy Treatment (visit 8 of 12) — Discharge",
      "Low back pain, resolved.",
      ["Pain 0–1/10; lifting boxes with hinge technique without pain; off cyclobenzaprine. Home program adherence good."],
      ["Goals met. Discharge to independent home program. Lifting ergonomics handout for classroom. Re-evaluate PRN."],
      exam=[("Range of Motion", "Full, pain-free."), ("Strength", "Prone plank 60 s, hip extension 5/5.")],
      table=(PT_TABLE_HDR, [["KB deadlift", "3 x 10", "25 lb", "0/10"], ["Farmer carry", "3 x 40 m", "20 lb each", "0/10"],
                            ["Plank progression", "3 x 45 s", "Body weight", "0/10"]]),
      cpt_icd=[("97110", "Therapeutic exercise"), ("M54.50", "Low back pain")])

# 34 ------------------------------------------------------------- m30 vascular (5 mm)
visit("2026-04-14", GULF, VASC_MD, "Follow-Up (pre-procedure planning)",
      "Left leg symptoms persist; ready to schedule ablation.",
      ["Nineteen months of uninterrupted 20–30 mmHg compression (since 09/17/2024), log reviewed, worn every day including weekends and "
       "summer 2025. Symptoms persist and have progressed: aching and heaviness now by late morning on teaching days, ankle and lower calf "
       "edema every evening, itching medial calf, cramps 2–3 nights per week. Acetaminophen most days. No ulcer, no bleeding, no "
       "phlebitis. Low back pain resolved with PT.",
       "Her mother is now in assisted living and respite is arranged; she would like to schedule the procedure for the summer break.",
       "ADLs: teaches seated for most of the day, no evening walks, split errands, and now reports she had to leave a school field day "
       "early because she could not stand for the afternoon session."],
      ["Symptomatic left lower extremity superficial venous insufficiency with progressing varicosities, CEAP C3 (edema), symptoms "
       "unimproved after 19 months of continuous compression plus elevation, exercise and analgesics, with significant interference with "
       "work and daily activities.",
       "Plan: radiofrequency ablation of the left great saphenous vein (CPT 36475) targeted for summer 2026. Order repeat left lower "
       "extremity venous reflux duplex within 3 months of the procedure date (schedule for August). Pre-procedure clearance from PCP. "
       "Continue compression. Return after the duplex to finalize and submit prior authorization to Florida Blue."],
      exam=vascular_exam(D("2026-04-14"),
                         "Tortuous varicosities along the distal medial thigh and medial calf in the GSV distribution, more prominent than "
                         "at prior visits; the largest varicosity at the mid-medial calf now measures 5 mm in diameter on exam with a "
                         "tape and caliper. Several additional tributary varicosities 3–4 mm. 1+ pitting edema ankle and distal calf at "
                         "2:10 pm with stocking worn until arrival. Mild xerosis; no hemosiderin pigmentation, eczema, "
                         "lipodermatosclerosis or ulceration. Calf soft, non-tender."),
      orders=["Lower extremity venous reflux duplex, left, to be performed 08/2026 (93970/93971)", "PCP pre-procedure evaluation",
              "Continue compression 20–30 mmHg daily", "Return after duplex"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 35 ------------------------------------------------------------- m31 derm
visit("2026-05-12", DERM, DERM_MD, "Follow-Up (BCC site) / Skin Check",
      "Post-ED&C site check; new spot on nose.",
      ["ED&C site right shoulder 10/2025 well healed, no recurrence. New 3 mm pink macule nasal ala, 2 months; dermoscopy without "
       "concerning features — monitor. Hands controlled. Wears compression on the left leg daily; no leg skin complaints."],
      ["BCC right shoulder, status post ED&C, no recurrence. Nasal ala macule: photograph and recheck 3 months. Return 3 months / annual full exam 08/2026."],
      exam=[("Skin — Right Shoulder", "1.2 cm hypopigmented atrophic scar, no nodularity."), ("Skin — Nose", "3 mm pink macule left ala, no arborizing vessels."),
            ("Skin — Legs", "Left compression stocking in place; distal calf varicosities visible below cuff, no stasis change.")],
      cpt_icd=[("99213", "Established patient"), ("Z85.828", "Personal history of other malignant neoplasm of skin")])

# 36 ------------------------------------------------------------- m32 PCP
visit("2026-06-09", PCP, PCP_MD, "Chronic Care Follow-Up (lipids)",
      "Lipid recheck on atorvastatin 40 mg.",
      ["LDL 04/2026: 79 on atorvastatin 40 mg with consistent dosing. No myalgias; ALT normal. BP at goal. TSH 2.3.",
       "Left leg: daily compression continues; symptoms persist; vascular surgery is planning ablation with a duplex in August and asked "
       "for a pre-procedure evaluation, which we will do in September."],
      ["Hyperlipidemia at goal; continue atorvastatin 40 mg. Hypertension, hypothyroidism stable. History of DVT, resolved, no "
       "anticoagulation. Pre-procedure evaluation for left GSV ablation to be completed 09/2026. Return 3 months."],
      cpt_icd=[("99213", "Established patient"), ("E78.5", "Hyperlipidemia"), ("I10", "Essential hypertension")])

# 37 ------------------------------------------------------------- m33 urgent care (ankle sprain)
visit("2026-07-07", UC, UC_MD3, "Urgent Care Visit",
      "Right ankle injury stepping off a curb this morning.",
      ["58-year-old female inverted the right ankle stepping off a curb 4 hours ago; immediate lateral pain and swelling, able to bear "
       "weight for 4 steps with pain. No prior ankle injury. Ottawa ankle rules: tenderness at the lateral malleolus tip — X-ray obtained.",
       "History of right calf DVT 06/2025, treated; left leg varicose veins, compression stocking worn daily."],
      ["Right lateral ankle sprain, grade II (ATFL); X-ray negative for fracture (see report). RICE, lace-up ankle brace, naproxen 500 mg "
       "BID x 7 days with food, early range of motion. Return for inability to bear weight, numbness or worsening swelling. Follow up PCP "
       "if not improving in 2 weeks."],
      exam=[("Right Ankle", "Moderate lateral swelling and ecchymosis; tenderness ATFL and lateral malleolus tip; anterior drawer mild laxity "
            "with firm end point; talar tilt negative; neurovascularly intact; squeeze test negative."), ("Right Calf", "No calf tenderness or swelling."),
            ("Left Lower Extremity", "Compression stocking in place; chronic varicosities.")],
      orders=["X-ray right ankle, 3 views (73610)", "Naproxen 500 mg #14", "Lace-up ankle brace"],
      cpt_icd=[("99213", "Urgent care visit"), ("73610", "X-ray ankle 3 views"), ("S93.401A", "Sprain of unspecified ligament of right ankle, initial")])

# 38 ------------------------------------------------------------- m34 vascular pre-duplex
visit("2026-08-11", GULF, VASC_MD, "Follow-Up (procedure scheduling)",
      "Scheduling left GSV ablation; duplex pending.",
      ["Twenty-three months of uninterrupted compression (since 09/17/2024). Symptoms unchanged from April: aching and heaviness by late "
       "morning, evening edema, itching, cramps 2–3 nights per week; she was unable to stand through a 3-hour school registration "
       "event last week and had to sit at a side table. Ankle sprain last month resolved. Procedure date set for 10/2026 pending "
       "prior authorization; duplex scheduled 08/25/2026."],
      ["Symptomatic left lower extremity superficial venous insufficiency, CEAP C3, failed conservative management. Proceed with "
       "pre-procedure duplex 08/25/2026 and PCP clearance 09/2026; final visit 09/22/2026 to review and submit prior authorization."],
      exam=vascular_exam(D("2026-08-11"),
                         "Tortuous varicosities distal medial thigh and medial calf in the GSV distribution, unchanged from April. 1+ "
                         "pitting edema ankle and distal calf. No pigmentation, eczema or ulcer."),
      orders=["Lower extremity venous reflux duplex, left, 08/25/2026", "Return 09/22/2026"],
      cpt_icd=[("99213", "Established patient"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

# 39 ------------------------------------------------------------- m35 PCP pre-procedure
visit("2026-09-08", PCP, PCP_MD, "Pre-Procedure Evaluation",
      "Pre-procedure evaluation for left great saphenous vein radiofrequency ablation.",
      ["Requested by Dr. Vasquez for office-based radiofrequency ablation of the left GSV under tumescent local anesthesia, planned "
       "10/2026. Hypertension at goal, hypothyroidism euthyroid, hyperlipidemia at goal. Provoked right calf DVT 06/2025, treated and "
       "resolved, off anticoagulation since 09/16/2025 with a normal follow-up duplex. No bleeding disorder. Functional capacity > 4 "
       "METs (climbs two flights). No anesthesia history problems. Labs 09/01/2026: CBC and BMP normal.",
       "Left leg symptoms continue daily despite two years of compression; she reports she now sits for most of the teaching day and "
       "needs help with grocery shopping."],
      ["Low-risk office procedure in a patient with well-controlled chronic conditions: acceptable risk, no further testing needed. "
       "Continue all medications. History of provoked DVT noted; post-procedure ambulation and compression per vascular surgery; no "
       "peri-procedural anticoagulation indicated. Copy of this note to Gulf Coast Vascular Surgery Associates."],
      orders=["Clearance letter faxed to vascular surgery"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("Z01.818", "Encounter for other preprocedural examination")])

# 40 ------------------------------------------------------------- m35 vascular final (symptoms + ADL, duplex reviewed)
visit("2026-09-22", GULF, VASC_MD, "Follow-Up (duplex review; prior authorization)",
      "Review of 08/25/2026 left venous reflux duplex; persistent symptoms; prior authorization for RFA.",
      ["Returns to review the left lower extremity venous reflux duplex of 08/25/2026: great saphenous vein incompetent with "
       "saphenofemoral junction reflux of 2.1 seconds and axial reflux through the thigh and calf; GSV 7.2 mm at the SFJ and 5.8 mm at "
       "mid-thigh; deep system patent with no DVT or deep reflux; small saphenous competent; no incompetent perforators. PCP "
       "pre-procedure evaluation 09/08/2026 reviewed: cleared.",
       "Compression history for the prior authorization record: 20–30 mmHg graduated knee-high stockings first started 02/13/2024 and "
       "interrupted at the beginning of May 2024 (patient stopped for the summer); restarted 09/17/2024 and worn daily without "
       "interruption since 09/17/2024 (24 months as of today), documented at every visit, with elevation, walking and analgesics "
       "throughout.",
       "Symptoms today: aching and heaviness of the left leg every day beginning by late morning, visible swelling of the ankle and lower "
       "calf every evening, itching over the medial calf, night cramps 2–3 times per week. Acetaminophen most days. No improvement at "
       "any point during the 24 months of continuous compression; by her account the leg is worse than when the stockings were restarted.",
       "Activities of daily living: she cannot stand through a full teaching day and now teaches seated for most of it; she has given up "
       "evening walks and her Saturday volunteer shift at the farmers market; grocery shopping is done by her daughter because she cannot "
       "stand through the checkout line; she had to leave a school field day and a registration event early this year.",
       "No ulcer, no bleeding from a varicosity, no superficial thrombophlebitis. Contralateral provoked calf DVT 06/2025, treated and "
       "resolved; the left deep system is normal on the 08/25/2026 duplex."],
      ["Symptomatic chronic venous insufficiency of the left lower extremity due to great saphenous vein reflux (SFJ reflux 2.1 s, GSV 7.2 mm "
       "at SFJ) with varicosities up to 5 mm, CEAP clinical class C3 (varicose veins with edema), Ep, As, Pr.",
       "Persistent pain, swelling, itching and cramping attributed to saphenous reflux, significantly interfering with work and daily "
       "activities, after 24 months of continuous 20–30 mmHg compression (09/17/2024 to 09/22/2026) plus elevation, exercise and "
       "analgesics without improvement.",
       "Recommend endovenous radiofrequency ablation of the left great saphenous vein (CPT 36475). Risks, benefits and alternatives "
       "reviewed; patient wishes to proceed. Submit prior authorization to Florida Blue today. Continue compression until the procedure."],
      exam=vascular_exam(D("2026-09-22"),
                         "Tortuous varicosities distal medial thigh and medial calf in the GSV distribution, largest 5 mm (unchanged from "
                         "04/14/2026). 1+ pitting edema of the ankle and distal calf at 11:30 am with stocking worn until arrival. Mild "
                         "xerosis medial calf; no hemosiderin pigmentation, eczema, lipodermatosclerosis or ulceration. Calf soft, "
                         "non-tender; no cords."),
      orders=["Prior authorization: CPT 36475, left GSV, Florida Blue PPO", "RFA left GSV, office procedure suite, 10/2026 pending PA"],
      cpt_icd=[("99214", "Established patient, moderate complexity"), ("I83.812", "Varicose veins of left lower extremity with pain"), ("I87.2", "Venous insufficiency (chronic) (peripheral)")])

assert len(V) == 40, len(V)


# ------------------------------------------------------------------ imaging (chronological)
IMAGING = [
    {"date": D("2023-11-14"), "title": "Lower Extremity Venous Reflux Duplex Ultrasound — Left — November 14, 2023", "md": US_MD, "practice": GULF,
     "rows": [("Ordering Physician", VASC_MD), ("Indication", "Left leg heaviness, aching, evening edema; visible medial calf veins; evaluate for reflux"),
              ("Technique", "Standing and reverse Trendelenburg; compression, color and spectral Doppler; Valsalva and distal augmentation/release; 7–12 MHz linear transducer"),
              ("Deep System", "Common femoral, femoral, profunda, popliteal, posterior tibial and peroneal veins compressible with spontaneous, phasic, augmentable flow. No acute or chronic thrombus. No deep venous reflux."),
              ("Saphenofemoral Junction", "Brief retrograde flow 0.4 seconds with Valsalva (below the 0.5 second threshold for pathologic reflux)."),
              ("Great Saphenous Vein", "Diameter 3.9 mm at the SFJ, 3.2 mm mid-thigh, 2.8 mm at the knee. No sustained reflux in the thigh or calf segments (retrograde flow < 0.5 seconds)."),
              ("Small Saphenous Vein", "Competent. Diameter 2.4 mm. No reflux."), ("Perforators", "No incompetent perforators identified."),
              ("Tributaries", "Small reticular veins and tributaries medial calf, 1–2 mm.")],
     "interp": "No deep venous thrombosis. Borderline, sub-threshold saphenofemoral junction reflux (0.4 s) with a non-dilated great saphenous vein. No pathologic superficial or deep reflux by this laboratory's criteria (≥ 0.5 s). Correlate clinically; repeat if symptoms progress."},
    {"date": D("2023-11-21"), "title": "Screening Mammogram, Bilateral — November 21, 2023", "md": RAD_MD, "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Technique", "Digital breast tomosynthesis, CC and MLO views bilaterally"), ("Breast Density", "Scattered fibroglandular densities (B)"),
              ("Findings", "No masses, suspicious calcifications or architectural distortion. Stable compared with 2022."), ("Assessment", "BI-RADS 1 — Negative")],
     "interp": "Negative screening mammogram. Routine annual screening recommended."},
    {"date": D("2024-03-12"), "title": "X-Ray Right Knee, 3 Views — March 12, 2024", "md": RAD_MD, "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Indication", "Anterior knee pain x 6 weeks"), ("Findings", "No fracture or dislocation. Mild patellofemoral joint space narrowing with small osteophyte at the superior pole of the patella. Tibiofemoral compartments preserved. No effusion."),
              ("Soft Tissues", "Unremarkable.")],
     "interp": "Mild patellofemoral degenerative change. No acute abnormality."},
    {"date": D("2024-11-19"), "title": "Screening Mammogram, Bilateral — November 19, 2024", "md": RAD_MD, "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Technique", "Digital breast tomosynthesis"), ("Findings", "Stable 6 mm circumscribed oval mass left breast upper outer quadrant, present since 2022, consistent with a benign cyst/fibroadenoma. No suspicious findings."), ("Assessment", "BI-RADS 2 — Benign")],
     "interp": "Benign findings. Routine annual screening."},
    {"date": D("2025-01-14"), "title": "X-Ray Chest, PA and Lateral — January 14, 2025", "md": RAD_MD, "practice": UC,
     "rows": [("Ordering Provider", UC_MD3), ("Indication", "Cough x 9 days, chest tightness"), ("Findings", "Lungs clear without consolidation, effusion or pneumothorax. Heart size normal. Mediastinal contours normal. Bony thorax intact.")],
     "interp": "No acute cardiopulmonary process."},
    {"date": D("2025-06-10"), "title": "Venous Duplex Ultrasound, Right Lower Extremity — June 10, 2025", "md": "Carrollwood Imaging — Dr. Sanjay Mehta, MD (Radiology)", "practice": UC,
     "rows": [("Ordering Provider", UC_MD1), ("Indication", "Right calf pain and swelling after prolonged travel; rule out DVT"),
              ("Common Femoral / Femoral / Profunda", "Fully compressible, normal phasic flow, no thrombus."), ("Popliteal Vein", "Compressible, no thrombus."),
              ("Posterior Tibial Veins", "One of the paired posterior tibial veins is non-compressible with echogenic intraluminal material over a 6 cm segment in the proximal-to-mid calf; non-occlusive with partial flow around the thrombus. Findings consistent with acute thrombus."),
              ("Peroneal Veins", "Compressible, no thrombus."), ("Gastrocnemius / Soleal Veins", "Compressible."), ("Great Saphenous Vein (right)", "Compressible, no superficial thrombophlebitis.")],
     "interp": "Acute non-occlusive deep vein thrombosis of a right posterior tibial vein (isolated distal/calf DVT). No proximal DVT. Clinical correlation and treatment per ordering provider."},
    {"date": D("2025-09-12"), "title": "Venous Duplex Ultrasound, Right Lower Extremity — September 12, 2025", "md": "Carrollwood Imaging — Dr. Sanjay Mehta, MD (Radiology)", "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Indication", "Follow-up right posterior tibial vein DVT (06/10/2025) at completion of anticoagulation"),
              ("Deep System", "Common femoral, femoral, profunda and popliteal veins compressible without thrombus."),
              ("Posterior Tibial Veins", "Previously thrombosed posterior tibial vein now fully compressible with restored flow; no residual thrombus; minimal wall thickening."),
              ("Peroneal Veins", "Compressible.")],
     "interp": "Interval complete recanalization of the right posterior tibial vein DVT. No residual or new thrombus."},
    {"date": D("2025-11-04"), "title": "Screening Mammogram, Bilateral — November 4, 2025", "md": RAD_MD, "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Findings", "Stable benign left breast mass. No suspicious findings."), ("Assessment", "BI-RADS 2 — Benign")],
     "interp": "Benign. Routine annual screening."},
    {"date": D("2026-02-10"), "title": "X-Ray Lumbar Spine, 2 Views — February 10, 2026", "md": RAD_MD, "practice": PCP,
     "rows": [("Ordering Physician", PCP_MD), ("Indication", "Low back pain after lifting"), ("Findings", "Mild disc space narrowing at L4–L5 and L5–S1 with small anterior osteophytes. No fracture, spondylolisthesis or pars defect. Sacroiliac joints normal.")],
     "interp": "Mild lumbar degenerative disc disease. No acute abnormality."},
    {"date": D("2026-07-07"), "title": "X-Ray Right Ankle, 3 Views — July 7, 2026", "md": RAD_MD, "practice": UC,
     "rows": [("Ordering Provider", UC_MD3), ("Indication", "Inversion injury, lateral malleolus tenderness"), ("Findings", "No fracture or dislocation. Ankle mortise congruent. Lateral soft tissue swelling. No os trigonum or avulsion fragment.")],
     "interp": "No fracture. Lateral soft tissue swelling consistent with sprain."},
    {"date": D("2026-08-25"), "title": "Lower Extremity Venous Reflux Duplex Ultrasound — Left — August 25, 2026", "md": US_MD, "practice": GULF,
     "rows": [("Ordering Physician", VASC_MD), ("Indication", "Symptomatic varicose veins and chronic venous insufficiency, left leg, failed conservative management; pre-procedure mapping for GSV ablation"),
              ("Technique", "Standing; compression, color and spectral Doppler; Valsalva and distal augmentation/release; 7–12 MHz linear transducer; GSV mapped from SFJ to ankle"),
              ("Deep System", "Common femoral, femoral, profunda, popliteal, posterior tibial and peroneal veins compressible with normal phasic, augmentable flow. No acute or chronic thrombus. No deep venous reflux."),
              ("Saphenofemoral Junction", "Incompetent. Reflux 2.1 seconds with Valsalva."),
              ("Great Saphenous Vein", "Incompetent with axial reflux. Diameter 7.2 mm at the SFJ, 5.8 mm mid-thigh, 4.6 mm at the knee, 3.9 mm mid-calf. Reflux 1.4–1.9 seconds in the thigh segments and 1.1 seconds at the knee on augmentation release. Straight course, suitable for catheter access at the knee. Depth from skin 1.1 cm at mid-thigh."),
              ("Small Saphenous Vein", "Competent. Diameter 2.6 mm. No reflux."), ("Perforators", "No incompetent perforators (none ≥ 3.5 mm with outward flow > 0.5 s)."),
              ("Tributaries", "Dilated tortuous tributary varicosities medial calf arising from the GSV, 3–5 mm, largest 5 mm.")],
     "interp": "Left great saphenous vein incompetence with pathologic saphenofemoral junction reflux (2.1 s) and axial reflux through the thigh and calf; GSV 7.2 mm at the SFJ. No deep venous thrombosis and no deep venous reflux. Small saphenous and perforators competent. Findings consistent with symptomatic superficial venous insufficiency; anatomy suitable for endovenous thermal ablation. Interval progression compared with 11/14/2023 (previously 0.4 s, 3.9 mm)."},
]

# ------------------------------------------------------------------ labs
def lab(date_iso, ordered_by, practice, panels, note=""):
    return {"date": D(date_iso), "md": ordered_by, "practice": practice, "panels": panels, "note": note}


CBC = lambda hgb, plt, wbc: ("Complete Blood Count", [("WBC", f"{wbc}", "4.0–10.5 K/uL"), ("Hemoglobin", f"{hgb}", "11.5–15.5 g/dL"), ("Hematocrit", f"{hgb*3:.1f}", "35–45 %"),
                                                   ("MCV", "89", "80–100 fL"), ("Platelets", f"{plt}", "150–400 K/uL")])
CMP = lambda k, cr, glu, alt: ("Comprehensive Metabolic Panel", [("Sodium", "139", "135–145 mmol/L"), ("Potassium", f"{k}", "3.5–5.1 mmol/L"), ("Chloride", "103", "98–107 mmol/L"),
                                                              ("CO2", "25", "22–29 mmol/L"), ("BUN", "14", "7–20 mg/dL"), ("Creatinine", f"{cr}", "0.5–1.0 mg/dL"), ("eGFR", "> 90", "> 60 mL/min/1.73m²"),
                                                              ("Glucose, fasting", f"{glu}", "70–99 mg/dL"), ("Calcium", "9.4", "8.6–10.2 mg/dL"), ("Total Protein", "7.1", "6.4–8.3 g/dL"), ("Albumin", "4.3", "3.5–5.0 g/dL"),
                                                              ("AST", "22", "10–35 U/L"), ("ALT", f"{alt}", "7–35 U/L"), ("Alk Phos", "68", "38–126 U/L"), ("Total Bilirubin", "0.6", "0.2–1.2 mg/dL")])
LIPID = lambda tc, ldl, hdl, tg: ("Lipid Panel", [("Total Cholesterol", f"{tc}", "< 200 mg/dL"), ("LDL Cholesterol (calc)", f"{ldl}", "< 100 mg/dL"), ("HDL Cholesterol", f"{hdl}", "> 50 mg/dL"), ("Triglycerides", f"{tg}", "< 150 mg/dL"), ("Non-HDL", f"{tc-hdl}", "< 130 mg/dL")])
TSH = lambda v, ft4=None: ("Thyroid", [("TSH", f"{v}", "0.40–4.50 mIU/L")] + ([("Free T4", f"{ft4}", "0.8–1.8 ng/dL")] if ft4 else []))
A1C = lambda v: ("Hemoglobin A1c", [("HbA1c", f"{v}", "< 5.7 %")])
VITD = lambda v: ("Vitamin D", [("25-OH Vitamin D", f"{v}", "30–100 ng/mL")])
COAG = ("Coagulation", [("PT", "11.8", "11.0–13.5 s"), ("INR", "1.0", "0.8–1.2"), ("aPTT", "29", "25–35 s")])
BMP = lambda k, cr: ("Basic Metabolic Panel", [("Sodium", "138", "135–145 mmol/L"), ("Potassium", f"{k}", "3.5–5.1 mmol/L"), ("Chloride", "102", "98–107 mmol/L"), ("CO2", "24", "22–29 mmol/L"),
                                              ("BUN", "15", "7–20 mg/dL"), ("Creatinine", f"{cr}", "0.5–1.0 mg/dL"), ("Glucose", "94", "70–99 mg/dL"), ("Calcium", "9.3", "8.6–10.2 mg/dL")])

LABS = [
    lab("2023-10-10", PCP_MD, PCP, [CBC(13.6, 262, 6.1), CMP(4.1, 0.78, 92, 19), LIPID(236, 158, 51, 135), TSH(3.1)], "LDL above goal; flagged for follow-up."),
    lab("2024-02-06", PCP_MD, PCP, [BMP(4.3, 0.82)], "Post losartan increase; potassium and creatinine stable."),
    lab("2024-05-14", PCP_MD, PCP, [LIPID(238, 161, 52, 128), CMP(4.2, 0.80, 95, 21)], "Fasting. LDL 161 despite lifestyle change."),
    lab("2024-08-20", PCP_MD, PCP, [LIPID(171, 96, 54, 105), ("Hepatic Function", [("ALT", "24", "7–35 U/L"), ("AST", "21", "10–35 U/L")])], "On atorvastatin 20 mg x 12 weeks."),
    lab("2024-09-24", PCP_MD, PCP, [TSH(5.9, 0.9), VITD(22), CBC(13.2, 255, 5.8)], "TSH elevated; vitamin D insufficient."),
    lab("2024-12-10", PCP_MD, PCP, [TSH(2.4)], "After levothyroxine increase to 75 mcg."),
    lab("2025-06-10", UC_MD1, UC, [CBC(13.4, 248, 7.0), BMP(4.2, 0.80), COAG], "Baseline prior to apixaban."),
    lab("2025-10-14", PCP_MD, PCP, [CBC(13.5, 251, 5.9), CMP(4.2, 0.81, 96, 23), LIPID(160, 88, 55, 85), TSH(2.1), A1C(5.6), VITD(34)], "Annual labs."),
    lab("2025-12-09", UC_MD2, UC, [BMP(3.6, 0.92)], "Mild dehydration; potassium low-normal."),
    lab("2026-01-13", PCP_MD, PCP, [LIPID(188, 112, 53, 115)], "LDL up; adherence discussed."),
    lab("2026-04-21", PCP_MD, PCP, [LIPID(151, 79, 56, 80), ("Hepatic Function", [("ALT", "27", "7–35 U/L"), ("AST", "23", "10–35 U/L")]), TSH(2.3)], "On atorvastatin 40 mg."),
    lab("2026-09-01", PCP_MD, PCP, [CBC(13.7, 259, 6.3), BMP(4.3, 0.79), COAG], "Pre-procedure labs for left GSV ablation."),
]

# ------------------------------------------------------------------ problem list (as of the final visit) and chart-level tables
PROBLEMS = [
    ["I83.812", "Varicose veins of left lower extremity with pain", "2023", "Active"],
    ["I87.2", "Venous insufficiency (chronic) (peripheral), left", "2023", "Active"],
    ["I10", "Essential hypertension", "2018", "Active"],
    ["E03.9", "Hypothyroidism, unspecified", "2016", "Active"],
    ["E78.5", "Hyperlipidemia, unspecified", "2024", "Active"],
    ["E55.9", "Vitamin D insufficiency", "2024", "Active"],
    ["Z86.718", "Personal history of venous thrombosis (right posterior tibial vein DVT 06/2025, provoked, treated)", "2025", "Resolved"],
    ["Z85.828", "Personal history of basal cell carcinoma, right shoulder (ED&C 10/2025)", "2025", "Resolved"],
    ["L24.9", "Irritant contact dermatitis, hands", "2024", "Controlled"],
    ["M54.50", "Low back pain (lumbar DDD), resolved with PT", "2026", "Resolved"],
    ["M22.2X1", "Patellofemoral pain, right knee, resolved with PT", "2024", "Resolved"],
]


# ------------------------------------------------------------------ rendering
def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kv(rows, w1=1.7):
    t = Table([[Paragraph(f"<b>{esc(k)}</b>", P), Paragraph(esc(v), P)] for k, v in rows], colWidths=[w1 * inch, (6.5 - w1) * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def grid(header, rows, widths):
    data = [header] + [[Paragraph(esc(str(c)), P) for c in r] for r in rows]
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(0.8 * inch, 0.45 * inch, f"{PATIENT['name']} | MRN {PATIENT['mrn']} | DOB {PATIENT['dob']} | Florida Blue PPO {MEMBER_ID}")
    canvas.drawRightString(letter[0] - 0.8 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def encounter_flowables(i: int, v: dict, prev_date: date | None):
    d, pr = v["date"], v["practice"]
    s = []
    heading = f"Visit Date: {long(d)} | {v['type']}"
    assert len(heading) < 90, heading
    s.append(Paragraph(esc(heading), H2))
    s.append(kv([("Encounter", f"#{i} of 40"), ("Practice", f"{pr['name'].title()} — {pr['short']}"), ("Location", pr["addr"]),
                 ("Attending", v["md"]), ("Encounter Type", v["type"]),
                 ("Patient", f"{PATIENT['name']} | MRN {PATIENT['mrn']} | DOB {PATIENT['dob']} | Age {d.year - 1968 - (1 if (d.month, d.day) < (3, 4) else 0)}"),
                 ("Primary Care", PCP_MD), ("Payer", f"Florida Blue PPO — BlueOptions, member {MEMBER_ID}")]))
    s.append(Paragraph("<b>Chief Complaint:</b>", P)); s.append(Paragraph(esc(v["cc"]), P)); s.append(Spacer(1, 3))
    s.append(Paragraph("<b>History of Present Illness:</b>", P))
    for para in v["hpi"]:
        s.append(Paragraph(esc(para), P)); s.append(Spacer(1, 2))
    s.append(Paragraph("<b>Vital Signs:</b>", P)); s.append(kv(vitals_for(d)))
    s.append(Paragraph("<b>Review of Systems:</b>", P)); s.append(kv(ros_for(d, pr["short"])))
    s.append(Paragraph("<b>Physical Examination:</b>", P)); s.append(kv(v["exam"] or general_exam(d)))
    if v["table"]:
        hdr, rows = v["table"]
        s.append(Paragraph("<b>Treatment Log (today's session):</b>", P)); s.append(grid(hdr, rows, [2.0, 1.2, 1.5, 1.8]))
    s.append(Paragraph("<b>Assessment &amp; Plan:</b>", P))
    for n, para in enumerate(v["ap"], 1):
        s.append(Paragraph(f"{n}. {esc(para)}", P)); s.append(Spacer(1, 2))
    if v["orders"]:
        s.append(Paragraph("<b>Orders:</b>", P))
        for o in v["orders"]:
            s.append(Paragraph(f"• {esc(o)}", P))
    s.append(Paragraph("<b>Medication Reconciliation (active at this encounter):</b>", P))
    s.append(grid(["Medication", "Dose", "Frequency", "Indication"], meds_on(d), [1.8, 0.9, 1.3, 2.5]))
    changes = med_changes_between(prev_date, d) if prev_date else []
    if changes:
        s.append(Paragraph("<b>Changes since last encounter:</b>", P))
        for c in changes:
            s.append(Paragraph(f"• {esc(c)}", P))
    s.append(Paragraph(f"<b>Allergies:</b> {esc(allergies_on(d))}", P))
    s.append(Paragraph("<b>Patient Instructions / After Visit Summary:</b>", P))
    for e in EDUCATION[pr["short"]]:
        s.append(Paragraph(f"• {esc(e)}", P))
    if v["codes"]:
        s.append(Paragraph("<b>Encounter Coding:</b>", P)); s.append(grid(["Code", "Description"], v["codes"], [1.2, 5.3]))
    s.append(Paragraph(f"Electronically signed: {esc(v['md'])} — {long(d)} {8 + (d.toordinal() % 9)}:{(d.toordinal() * 7) % 60:02d}", SM))
    s.append(Paragraph(f"Copy to: {PCP_MD if pr is not PCP else 'chart'}; released to Gulf Coast Vascular Surgery Associates for prior authorization.", SM))
    s.append(PageBreak())
    return s


def build_pdf() -> None:
    doc = SimpleDocTemplate(str(OUT_PDF), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch, title="Elena Ruiz — Medical Chart", author=GULF["name"])
    s = []
    final = V[-1]["date"]
    s.append(Paragraph(GULF["name"], SS["Title"]))
    s.append(Paragraph(GULF["addr"], SM))
    s.append(Paragraph("PATIENT MEDICAL CHART — CONFIDENTIAL — FOR AUTHORIZED USE ONLY", SM))
    s.append(Paragraph(esc(f"Consolidated record compiled {long(final)} for prior authorization (Florida Blue PPO). Includes outside records "
                           "received from Westchase Family Medicine, Bayshore Dermatology Group, Tampa Bay Physical Therapy & Rehabilitation and "
                           "Carrollwood Urgent Care under signed release. Encounters are in chronological order."), SM))
    s.append(Paragraph("1. PATIENT DEMOGRAPHICS", H1))
    s.append(kv([("Patient Name", PATIENT["name"]), ("Date of Birth", PATIENT["dob"]), ("MRN", PATIENT["mrn"]), ("Age", "58 years"), ("Sex", PATIENT["sex"]),
                 ("Address", PATIENT["addr"]), ("Phone", PATIENT["phone"]), ("Occupation", PATIENT["occupation"]), ("Primary Care Physician", PCP_MD),
                 ("Emergency Contact", "Sofia Ruiz (daughter), (813) 555-0119")]))
    s.append(Paragraph("2. INSURANCE &amp; COVERAGE", H1)); s.append(Paragraph("Primary Insurance", H2))
    s.append(kv([("Payer", "Florida Blue (Blue Cross and Blue Shield of Florida)"), ("Plan Type", "PPO — BlueOptions"), ("Member ID", MEMBER_ID),
                 ("Group Number", "FL-55120-OPT"), ("Coverage Effective", "January 1, 2023"), ("Prior Auth Required", "Yes — Vein procedures"), ("Auth Contact", "1-800-555-0199")]))
    s.append(Paragraph("Secondary Insurance", H2)); s.append(Paragraph("None on file.", P))
    s.append(Paragraph("3. ACTIVE PROBLEM LIST", H1)); s.append(grid(["ICD-10", "Diagnosis", "Onset", "Status"], PROBLEMS, [0.9, 3.8, 0.8, 1.0]))
    s.append(Paragraph("4. CURRENT MEDICATIONS", H1)); s.append(Paragraph(esc(f"As of {long(final)}."), SM))
    s.append(grid(["Medication", "Dose", "Frequency", "Indication"], meds_on(final), [1.8, 0.9, 1.3, 2.5]))
    s.append(Paragraph("5. MEDICATION HISTORY", H1))
    s.append(grid(["Medication", "Dose", "Frequency", "Start", "Stop", "Indication"],
                  [[n, dz, f, us(D(a)), us(D(b)) if b else "—", ind] for a, b, n, dz, f, ind in sorted(MED_EVENTS, key=lambda e: e[0])], [1.5, 0.7, 1.0, 0.8, 0.8, 1.7]))
    s.append(Paragraph("6. ALLERGIES &amp; ADVERSE REACTIONS", H1)); s.append(Paragraph(esc(allergies_on(final)), P))
    s.append(PageBreak())
    s.append(Paragraph("7. ENCOUNTER NOTES — ALL SOURCES, CHRONOLOGICAL", H1))
    s.append(grid(["#", "Date", "Source", "Type"], [[str(i), us(v["date"]), v["practice"]["short"], v["type"]] for i, v in enumerate(V, 1)], [0.4, 0.9, 1.4, 3.8]))
    s.append(PageBreak())
    prev = None
    for i, v in enumerate(V, 1):
        s.extend(encounter_flowables(i, v, prev)); prev = v["date"]
    s.append(Paragraph("8. DIAGNOSTIC IMAGING &amp; TESTING REPORTS", H1))
    for im in IMAGING:
        s.append(Paragraph(esc(im["title"]), H2)); s.append(kv([("Performed At", f"{im['practice']['name'].title()} / affiliated imaging"), ("Patient", f"{PATIENT['name']} | MRN {PATIENT['mrn']}")] + list(im["rows"])))
        s.append(Paragraph(f"<b>Interpretation:</b> {esc(im['interp'])}", P))
        s.append(Paragraph(f"Electronically signed: {esc(im['md'])} — {long(im['date'])}", SM)); s.append(Spacer(1, 8))
    s.append(PageBreak())
    s.append(Paragraph("9. LABORATORY RESULTS", H1))
    for lb in LABS:
        s.append(Paragraph(esc(f"Laboratory Report — {long(lb['date'])}"), H2))
        s.append(kv([("Ordering Provider", lb["md"]), ("Practice", lb["practice"]["name"].title()), ("Collected", f"{long(lb['date'])} 07:{(lb['date'].toordinal() % 50) + 10} (fasting)"),
                     ("Performing Lab", "Tampa Bay Clinical Laboratories, CLIA 10D0999999"), ("Patient", f"{PATIENT['name']} | MRN {PATIENT['mrn']}")]))
        for name, rows in lb["panels"]:
            s.append(Paragraph(f"<b>{esc(name)}</b>", P))
            flagged = []
            for test, val, ref in rows:
                flag = ""
                m = re.match(r"^[<>]?\s*([\d.]+)", ref)
                try:
                    x = float(val.replace(">", "").strip())
                    if ref.startswith("<") and x >= float(ref[1:].split()[0]): flag = "H"
                    elif ref.startswith(">") and x <= float(ref[1:].split()[0]): flag = "L"
                    elif "–" in ref:
                        lo, hi = ref.split("–")[0], ref.split("–")[1].split()[0]
                        if x < float(lo): flag = "L"
                        elif x > float(hi): flag = "H"
                except ValueError:
                    pass
                flagged.append([test, val, ref, flag])
            s.append(grid(["Test", "Result", "Reference Range", "Flag"], flagged, [2.4, 1.2, 2.2, 0.7]))
        if lb["note"]:
            s.append(Paragraph(f"<b>Comment:</b> {esc(lb['note'])}", P))
        s.append(Paragraph(f"Reviewed: {esc(lb['md'])} — {long(lb['date'] + timedelta(days=1))}", SM)); s.append(Spacer(1, 8))
    s.append(PageBreak())
    s.append(Paragraph("10. PLANNED PROCEDURE", H1))
    s.append(kv([("Planned Procedure", "Endovenous radiofrequency ablation, left great saphenous vein"),
                 ("CPT", "36475 — Endovenous ablation therapy of incompetent vein, extremity, inclusive of all imaging guidance and monitoring, percutaneous, radiofrequency; first vein treated"),
                 ("Laterality", "Left"), ("Diagnosis", "I83.812, I87.2"), ("Surgeon", VASC_MD), ("Facility", "Gulf Coast Vascular Surgery Associates — office-based procedure suite"),
                 ("Payer", "Florida Blue PPO"), ("PA Status", "Pending — Submitted September 23, 2026")]))
    s.append(Paragraph("<b>Clinical Indication Summary:</b>", P))
    for b in ["Left GSV reflux (SFJ reflux 2.1 s, GSV 7.2 mm at SFJ) on duplex 08/25/2026; no DVT, no deep reflux.",
              "CEAP clinical class C3: varicose veins with edema. Varicosities up to 5 mm on exam 04/14/2026 and 09/22/2026.",
              "Persistent pain, swelling, itching and cramping attributed to saphenous reflux, documented at every vascular visit 2023–2026.",
              "Symptoms significantly interfere with work (teaches seated, excused from standing duties) and daily activities (errands, walking).",
              "Graduated compression 20–30 mmHg worn continuously from 09/17/2024 through 09/22/2026 (24 months) with elevation, exercise and analgesics, without improvement. An earlier trial (02/13/2024 to early May 2024) was interrupted by the patient.",
              "History of contralateral provoked calf DVT (06/2025), treated and resolved; left deep system normal."]:
        s.append(Paragraph(f"• {esc(b)}", P))
    s.append(Spacer(1, 8))
    s.append(Paragraph("This document is for clinical and administrative use only. Patient identifiers are fictional and created for demonstration purposes.", SM))
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT_PDF.name)


# ------------------------------------------------------------------ ground truth
def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("“", '"').replace("”", '"'))


def find_page(pages: list[str], anchor: str) -> int:
    a = norm(anchor)
    hits = [i + 1 for i, p in enumerate(pages) if a in p]
    if not hits:  # phrase split across a page boundary
        hits = [i + 1 for i in range(len(pages) - 1) if a in norm(pages[i] + " " + pages[i + 1])]
    assert len(hits) == 1, (anchor, hits)
    return hits[0]


def visit_index(date_iso: str) -> int:
    return next(i for i, v in enumerate(V, 1) if v["date"] == D(date_iso))


BURIED = [
    ("no_dvt_history_early", "2023-10-24", "Vascular new patient consult: explicit negative for DVT/PE/thrombophlebitis.",
     "No personal history of deep vein thrombosis"),
    ("varicosity_2mm_month2", "2023-12-05", "Vascular follow-up exam: largest varicosity approximately 2 mm (below the 3 mm threshold).",
     "approximately 2 mm in diameter"),
    ("duplex_subthreshold_month1", "2023-11-14", "First duplex: SFJ reflux 0.4 s, below the 0.5 s threshold; GSV 3.9 mm. Distractor for saphenous_reflux.",
     "Brief retrograde flow 0.4 seconds with Valsalva"),
    ("compression_start_run1_month4", "2024-02-13", "Visit 6 (month 4): compression 20–30 mmHg started, explicitly dated 02/13/2024.",
     "Start date of compression therapy: 02/13/2024"),
    ("compression_interruption_month9", "2024-07-16", "Dermatology note (month 9): patient 'stopped wearing stockings for the summer' at the beginning of May 2024.",
     'stopped wearing stockings for the summer'),
    ("compression_restart_run2_month11", "2024-09-17", "Vascular note (month 11): compression restarted, explicitly dated 09/17/2024.",
     "Compression therapy restarted today, 09/17/2024"),
    ("dvt_urgent_care_month20", "2025-06-10", "Urgent care note (month 20): acute right posterior tibial (calf) DVT diagnosed and treated with apixaban.",
     "acute deep vein thrombosis of the right posterior tibial vein"),
    ("varicosity_5mm_month30", "2026-04-14", "Vascular exam (month 30): largest varicosity now 5 mm — the value the 3 mm criterion must use (recency).",
     "measures 5 mm in diameter"),
    ("duplex_gsv_reflux_final", "2026-08-25", "Final-quarter duplex: SFJ reflux 2.1 s, GSV 7.2 mm at SFJ, no DVT.",
     "Reflux 2.1 seconds with Valsalva"),
    ("compression_continuous_final", "2026-09-22", "Final vascular visit: compression continuous since 09/17/2024, 24 months, no improvement.",
     "without interruption since 09/17/2024 (24 months as of today)"),
    ("symptoms_persist_final", "2026-09-22", "Final vascular visit: daily aching, heaviness, evening swelling, itching, cramps; no improvement on compression.",
     "No improvement at any point during the 24 months"),
    ("adl_impact_final", "2026-09-22", "Final vascular visit: cannot stand through a teaching day, gave up walks and volunteer shift, daughter shops.",
     "cannot stand through a full teaching day"),
]


def write_expected() -> dict:
    reader = PdfReader(str(OUT_PDF))
    pages = [norm(p.extract_text() or "") for p in reader.pages]
    facts = {}
    for fid, date_iso, desc, anchor in BURIED:
        page = find_page(pages, anchor)
        is_visit = any(v["date"] == D(date_iso) for v in V)
        src = next((f"Visit Date: {long(v['date'])} | {v['type']}" for v in V if v["date"] == D(date_iso)), None) \
            or next(im["title"] for im in IMAGING if im["date"] == D(date_iso))
        facts[fid] = {"description": desc, "date": date_iso, "encounter_index": visit_index(date_iso) if is_visit else None,
                      "source_heading": src, "page": page, "anchor": anchor}
    exp = {
        "chart": OUT_PDF.name, "generator": Path(__file__).name, "page_count": len(reader.pages), "encounters": len(V),
        "patient": {"name": PATIENT["name"], "dob": "1968-03-04", "mrn": PATIENT["mrn"]},
        "order": {"payer": "Florida Blue", "plan_type": "PPO", "cpt": ["36475"], "icd10": ["I83.812", "I87.2"], "laterality": "left",
                  "procedure_text": "Endovenous radiofrequency ablation, left great saphenous vein"},
        "guideline_id": "bcbsfl-02-33000-31", "pathway": "great_small_saphenous", "determination": "MET",
        "criteria": {
            "saphenous_reflux": {"status": "MET", "evidence": ["duplex_gsv_reflux_final"], "distractor": "duplex_subthreshold_month1",
                                 "note": "Use the 2026-08-25 duplex (2.1 s), not the 2023-11-14 duplex (0.4 s, sub-threshold)."},
            "ceap_c2_or_greater": {"status": "MET", "value": "C3", "evidence": ["adl_impact_final"], "note": "C3 (varicose veins with edema) stated at the final visit and from 2024-12-17 onward."},
            "varicosities_3mm": {"status": "MET", "value_mm": 5, "use_measurement_dated": "2026-04-14", "evidence": ["varicosity_5mm_month30"],
                                 "distractor": "varicosity_2mm_month2", "note": "Recency: the 2026-04-14 value (5 mm) governs, not the 2023-12-05 value (2 mm)."},
            "persistent_symptoms": {"status": "MET", "evidence": ["symptoms_persist_final"]},
            "symptoms_interfere_adl": {"status": "MET", "evidence": ["adl_impact_final"]},
            "compression_3_months": {"status": "MET", "run_that_meets": 2, "start": "2024-09-17", "end": "2026-09-22", "months": 24,
                                     "evidence": ["compression_restart_run2_month11", "compression_continuous_final"],
                                     "note": "MET only on the second run (restart 2024-09-17 → final visit 2026-09-22). The first run is interrupted and shorter than 3 months."},
            "venous_stasis_ulcer": {"status": "NOT_MET"}, "recurrent_thrombophlebitis": {"status": "NOT_MET"}, "variceal_hemorrhage": {"status": "NOT_MET"},
        },
        "compression_runs": [
            {"run": 1, "start": "2024-02-13", "end_approx": "2024-05-01", "months_approx": 2.5, "meets_3_months": False,
             "start_fact": "compression_start_run1_month4", "interruption_fact": "compression_interruption_month9",
             "note": "Stopped 'for the summer' at the beginning of May 2024 (dermatology 2024-07-16; confirmed by vascular 2024-09-17)."},
            {"run": 2, "start": "2024-09-17", "end": "2026-09-22", "months": 24, "meets_3_months": True,
             "start_fact": "compression_restart_run2_month11", "end_fact": "compression_continuous_final",
             "continuation_visits": ["2024-10-15", "2024-12-17", "2025-03-18", "2025-07-15", "2025-11-18", "2026-04-14", "2026-08-11", "2026-09-22"]},
        ],
        "varicosity_measurements": [{"date": "2023-12-05", "value_mm": 2, "fact": "varicosity_2mm_month2"}, {"date": "2026-04-14", "value_mm": 5, "fact": "varicosity_5mm_month30"},
                                    {"date": "2026-08-25", "value_mm": 5, "source": "duplex tributaries, largest 5 mm"}, {"date": "2026-09-22", "value_mm": 5, "source": "final exam, unchanged"}],
        "dvt": {"early_negative_fact": "no_dvt_history_early", "event_fact": "dvt_urgent_care_month20", "event_date": "2025-06-10", "laterality": "right",
                "treatment": "apixaban 2025-06-10 to 2025-09-16", "relevant_to_pathway": False,
                "note": "Irrelevant to great_small_saphenous (secondary_to_dvt only appears in perforator_veins) but must appear on the tape as separate dated facts."},
        "buried_facts": facts,
        "depth_expectations": {"compression_start_cited_should_be": "2024-09-17", "varicosity_value_used_should_be_mm": 5,
                               "duplex_cited_should_be": "2026-08-25", "wrong_answers": {"compression_start": "2024-02-13", "varicosity_mm": 2, "duplex": "2023-11-14"}},
    }
    OUT_JSON.write_text(json.dumps(exp, indent=2, ensure_ascii=False) + "\n")
    print("wrote", OUT_JSON.name, "pages:", len(reader.pages))
    return exp


if __name__ == "__main__":
    build_pdf()
    exp = write_expected()
    assert exp["page_count"] >= 120, exp["page_count"]
    for fid, f in exp["buried_facts"].items():
        print(f"  {fid:34s} {f['date']}  visit {str(f['encounter_index'] or '-'):>2s}  page {f['page']}")
