"""Generate synthetic patient charts as PDFs (same shape as robert_mitchell_chart_final.pdf).
All patients and providers are fictional.  python make_charts.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

HERE = Path(__file__).parent
SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)
P = ParagraphStyle("p", parent=SS["BodyText"], fontSize=9.5, leading=12.5)
SM = ParagraphStyle("sm", parent=P, fontSize=8, textColor=colors.grey)


def kv(rows):
    t = Table([[Paragraph(f"<b>{k}</b>", P), Paragraph(v, P)] for k, v in rows], colWidths=[1.7 * inch, 4.8 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def build(fname, practice, patient, insurance, problems, meds, visits, imaging, planned):
    doc = SimpleDocTemplate(str(HERE / fname), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    s = []
    s.append(Paragraph(practice["name"], SS["Title"]))
    s.append(Paragraph(practice["addr"], SM))
    s.append(Paragraph("PATIENT MEDICAL CHART — CONFIDENTIAL — FOR AUTHORIZED USE ONLY", SM))
    s.append(Paragraph("1. PATIENT DEMOGRAPHICS", H1)); s.append(kv(patient))
    s.append(Paragraph("2. INSURANCE &amp; COVERAGE", H1)); s.append(Paragraph("Primary Insurance", H2)); s.append(kv(insurance))
    s.append(Paragraph("Secondary Insurance", H2)); s.append(Paragraph("None on file.", P))
    s.append(Paragraph("3. ACTIVE PROBLEM LIST", H1))
    t = Table([["ICD-10", "Diagnosis", "Onset", "Status"]] + problems, colWidths=[0.9 * inch, 3.6 * inch, 1 * inch, 0.8 * inch])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey)])); s.append(t)
    s.append(Paragraph("4. CURRENT MEDICATIONS", H1))
    t = Table([["Medication", "Dose", "Frequency", "Indication"]] + meds, colWidths=[1.8 * inch, 1 * inch, 1 * inch, 2.5 * inch])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey)])); s.append(t)
    s.append(Paragraph("5. ALLERGIES &amp; ADVERSE REACTIONS", H1)); s.append(Paragraph("No known drug allergies.", P))
    s.append(Paragraph(f"6. VISIT NOTES — {practice['specialty'].upper()}", H1))
    for v in visits:
        s.append(Paragraph(f"Visit Date: {v['date']} | Attending: {v['md']} | Type: {v['type']}", H2))
        for label, body in v["sections"]:
            s.append(Paragraph(f"<b>{label}:</b>", P)); s.append(Paragraph(body, P)); s.append(Spacer(1, 3))
        s.append(Paragraph(f"Electronically signed: {v['md']} — {v['date']}", SM))
    s.append(Paragraph("7. DIAGNOSTIC IMAGING &amp; TESTING REPORTS", H1))
    for im in imaging:
        s.append(Paragraph(im["title"], H2)); s.append(kv(im["rows"]))
        s.append(Paragraph(f"<b>Interpretation:</b> {im['interp']}", P))
        s.append(Paragraph(f"Electronically signed: {im['md']} — {im['date']}", SM))
    s.append(Paragraph("8. PLANNED PROCEDURE", H1)); s.append(kv(planned["rows"]))
    s.append(Paragraph("<b>Clinical Indication Summary:</b>", P))
    for b in planned["summary"]:
        s.append(Paragraph(f"• {b}", P))
    s.append(Spacer(1, 8))
    s.append(Paragraph("This document is for clinical and administrative use only. Patient identifiers are fictional and created for demonstration purposes.", SM))
    doc.build(s)
    print("wrote", fname)


GULF = {"name": "GULF COAST VASCULAR SURGERY ASSOCIATES", "specialty": "Vascular Surgery",
        "addr": "2200 Bayshore Blvd, Suite 310 | Tampa, FL 33606 | (813) 555-0140 | NPI: 1987654321"}
MD = "Dr. Elena Vasquez, MD, FACS"
US_MD = "Dr. Thomas Reed, RVT / Dr. Elena Vasquez, MD"


def fl_ins(member):
    return [("Payer", "Florida Blue (Blue Cross and Blue Shield of Florida)"), ("Plan Type", "PPO — BlueOptions"),
            ("Member ID", member), ("Group Number", "FL-55120-OPT"), ("Coverage Effective", "January 1, 2025"),
            ("Prior Auth Required", "Yes — Vein procedures"), ("Auth Contact", "1-800-555-0199")]


# ------------------------------------------------------------------ 1. MET
build("maria_delgado_chart.pdf", GULF,
      [("Patient Name", "Maria Elena Delgado"), ("Date of Birth", "June 12, 1971"), ("MRN", "GCV-010442"), ("Age", "54 years"),
       ("Sex", "Female"), ("Address", "1410 Palmetto Ave, Tampa, FL 33605"), ("Primary Care Physician", "Dr. Samuel Ortiz, MD")],
      fl_ins("FLB442918733"),
      [["I83.813", "Varicose veins of bilateral lower extremities with pain", "2024", "Active"],
       ["I87.2", "Venous insufficiency (chronic) (peripheral)", "2024", "Active"],
       ["E66.9", "Obesity, unspecified (BMI 31)", "2019", "Active"]],
      [["Ibuprofen", "400 mg", "PRN", "Leg pain"], ["Losartan", "50 mg", "Daily", "Hypertension"]],
      [
          {"date": "March 18, 2025", "md": MD, "type": "New Patient Consult", "sections": [
              ("Chief Complaint", "Left leg aching, heaviness and swelling, worse by end of shift. Works 10-hour shifts as a hospital unit clerk, standing most of the day."),
              ("History of Present Illness", "54-year-old female with 18 months of progressive left lower extremity aching, heaviness, nocturnal cramping and ankle swelling. Symptoms worsen with prolonged standing and improve with elevation. Reports itching over medial calf with new brownish discoloration. Denies history of DVT, ulceration, bleeding from veins, or superficial thrombophlebitis. Symptoms now limit her ability to complete shifts; she has used 6 sick days in 3 months for leg pain and has stopped evening walks."),
              ("Physical Examination", "Left leg: prominent tortuous varicosities along the medial thigh and calf in the GSV distribution, largest cluster approx. 6 mm diameter on exam. Hyperpigmentation and mild eczematous change medial lower calf. 1+ pitting edema at ankle. No ulceration. Pulses 2+. Right leg: scattered reticular veins only."),
              ("Assessment & Plan", "Symptomatic chronic venous insufficiency, left leg, CEAP clinical class C4a (pigmentation/eczema). Order lower extremity venous reflux duplex. Begin conservative management: graduated compression stockings 20–30 mmHg daily, leg elevation, NSAIDs PRN, weight management counseling. Return 3 months to assess response."),
          ]},
          {"date": "July 22, 2025", "md": MD, "type": "Follow-Up", "sections": [
              ("Interval History", "Patient returns after 4 months of conservative therapy. Reports consistent daily use of 20–30 mmHg compression stockings since the March visit (confirms wearing them to work every shift), nightly elevation, and ibuprofen PRN. Symptoms unchanged to slightly worse: persistent aching and heaviness by mid-shift, ankle swelling every evening, nocturnal cramps 3–4 nights per week. Itching persists. She reports she cannot stand for a full shift without sitting breaks and has reduced her hours. Duplex reviewed below."),
              ("Physical Examination", "Unchanged varicosities medial left thigh and calf, 5–6 mm. Hyperpigmentation medial calf stable. 1+ edema. No ulcer."),
              ("Assessment & Plan", "Symptomatic left GSV reflux with CEAP C4a disease, failed 4 months of compression therapy and conservative measures. Symptoms significantly interfere with work and daily activities. Recommend endovenous radiofrequency ablation of the left great saphenous vein. Risks, benefits, alternatives discussed; patient wishes to proceed. Submit prior authorization to Florida Blue."),
          ]},
      ],
      [{"title": "Lower Extremity Venous Reflux Duplex Ultrasound — Left — March 25, 2025", "md": US_MD, "date": "March 25, 2025",
        "rows": [("Ordering Physician", MD), ("Indication", "Symptomatic varicose veins, left leg; evaluate for reflux"),
                 ("Deep System", "Common femoral, femoral, popliteal veins compressible, no DVT. No deep venous reflux."),
                 ("Great Saphenous Vein", "Incompetent. Reflux at saphenofemoral junction 2.4 seconds with Valsalva; reflux along thigh and calf segments 1.1–1.8 seconds on distal compression release. GSV diameter 7.8 mm at SFJ, 6.1 mm mid-thigh, 4.9 mm at knee."),
                 ("Small Saphenous Vein", "Competent. No reflux. Diameter 2.8 mm."),
                 ("Perforators", "One incompetent medial calf perforator, 3.4 mm, reflux 0.8 s."),
                 ("Tributaries", "Multiple dilated tributary varicosities medial calf, 4–6 mm.")],
        "interp": "Left great saphenous vein incompetence with significant axial reflux (>0.5 s) from the SFJ through the calf. No deep venous thrombosis or deep reflux. Findings consistent with symptomatic superficial venous insufficiency."}],
      {"rows": [("Planned Procedure", "Endovenous radiofrequency ablation, left great saphenous vein"), ("CPT", "36475 — Endovenous ablation therapy of incompetent vein, extremity, radiofrequency; first vein treated"),
                ("Laterality", "Left"), ("Diagnosis", "I83.813, I87.2"), ("Surgeon", MD), ("Facility", "Gulf Coast Vascular Surgery Associates — office-based procedure suite"),
                ("Payer", "Florida Blue PPO"), ("PA Status", "Pending — Submitted July 24, 2025")],
       "summary": ["Symptomatic left GSV reflux (SFJ reflux 2.4 s) on duplex 03/25/2025; no DVT.", "CEAP clinical class C4a: varicosities with pigmentation and eczema.",
                   "Varicosities 5–6 mm on exam; GSV 7.8 mm at SFJ.", "Conservative management with 20–30 mmHg compression, elevation and NSAIDs from 03/18/2025 through 07/22/2025 (4 months) without improvement.",
                   "Symptoms interfere with occupation (standing shifts) and daily activities."]})


# ------------------------------------------------------------------ 2. NOT COVERED (cosmetic / spider veins)
build("james_okafor_chart.pdf", GULF,
      [("Patient Name", "James Okafor"), ("Date of Birth", "February 2, 1984"), ("MRN", "GCV-010877"), ("Age", "41 years"),
       ("Sex", "Male"), ("Address", "88 Harbor Island Dr, Tampa, FL 33602"), ("Primary Care Physician", "Dr. Priya Nair, MD")],
      fl_ins("FLB771030522"),
      [["I78.1", "Nevus, non-neoplastic (telangiectasia of lower extremity)", "2025", "Active"]],
      [["None", "", "", ""]],
      [
          {"date": "August 5, 2025", "md": MD, "type": "New Patient Consult", "sections": [
              ("Chief Complaint", "Spider veins on both thighs; patient is bothered by their appearance before an upcoming beach wedding."),
              ("History of Present Illness", "41-year-old male, marathon runner, with 2 years of fine purple-red thread veins on the lateral thighs bilaterally. Denies pain, heaviness, swelling, itching, cramping, skin changes, ulceration, bleeding or thrombophlebitis. No history of DVT. Symptom-free with running up to 50 miles/week."),
              ("Physical Examination", "Bilateral lateral thigh telangiectasias and reticular veins, 0.5–1.5 mm. No truncal varicosities. No edema, no skin changes, no ulcer. Pulses 2+."),
              ("Assessment & Plan", "Telangiectasia / reticular veins, CEAP C1, asymptomatic. Discussed that this is a cosmetic concern. Patient requests sclerotherapy. Duplex ordered to exclude underlying reflux as a courtesy. Will submit to insurance at patient request; counseled that coverage is unlikely."),
          ]},
      ],
      [{"title": "Lower Extremity Venous Reflux Duplex Ultrasound — Bilateral — August 12, 2025", "md": US_MD, "date": "August 12, 2025",
        "rows": [("Indication", "Thigh telangiectasia; exclude saphenous reflux"), ("Deep System", "Normal bilaterally, no DVT."),
                 ("Great Saphenous Vein", "Competent bilaterally. No reflux. Diameter 3.1 mm right, 3.0 mm left."), ("Small Saphenous Vein", "Competent bilaterally."),
                 ("Perforators", "No incompetent perforators."), ("Tributaries", "No dilated tributaries.")],
        "interp": "No saphenous, perforator or deep venous reflux. Isolated telangiectasia without underlying venous insufficiency."}],
      {"rows": [("Planned Procedure", "Sclerotherapy of telangiectasia, bilateral thighs"), ("CPT", "36468 — Injection(s) of sclerosant for spider veins (telangiectasia), limb or trunk"),
                ("Laterality", "Bilateral"), ("Diagnosis", "I78.1"), ("Surgeon", MD), ("Payer", "Florida Blue PPO"), ("PA Status", "Pending")],
       "summary": ["Asymptomatic bilateral thigh telangiectasia, CEAP C1.", "No saphenous reflux on duplex 08/12/2025.", "Patient requests treatment for cosmetic reasons."]})


# ------------------------------------------------------------------ 3. INSUFFICIENT (compression mentioned, no duration)
build("linda_park_chart.pdf", GULF,
      [("Patient Name", "Linda Park"), ("Date of Birth", "November 30, 1962"), ("MRN", "GCV-011203"), ("Age", "62 years"),
       ("Sex", "Female"), ("Address", "5 Cypress Point Ct, Brandon, FL 33511"), ("Primary Care Physician", "Dr. Henry Kwon, MD")],
      fl_ins("FLB309118465"),
      [["I83.812", "Varicose veins of left lower extremity with pain", "2025", "Active"],
       ["I87.2", "Venous insufficiency (chronic) (peripheral)", "2025", "Active"], ["I10", "Essential hypertension", "2010", "Active"]],
      [["Amlodipine", "5 mg", "Daily", "Hypertension"], ["Acetaminophen", "500 mg", "PRN", "Leg pain"]],
      [
          {"date": "September 9, 2025", "md": MD, "type": "New Patient Consult", "sections": [
              ("Chief Complaint", "Left leg swelling and aching, several months."),
              ("History of Present Illness", "62-year-old female with left lower extremity aching, heaviness and evening ankle swelling for approximately 8 months. Worse with standing, better with elevation. Occasional night cramps. Denies ulceration, bleeding, or thrombophlebitis. No history of DVT. Her PCP recommended compression stockings earlier this year; patient reports she 'has been wearing them' but is unsure of the strength and does not remember exactly when she started."),
              ("Physical Examination", "Left leg: varicosities medial calf, largest approx. 4 mm. 2+ pitting edema to mid-calf. No skin changes, no ulcer. Pulses 2+. Right leg: normal."),
              ("Assessment & Plan", "Symptomatic varicose veins, left leg, with edema: CEAP C3. Order venous reflux duplex. Continue compression stockings; advised 20–30 mmHg. Return after duplex."),
          ]},
          {"date": "September 30, 2025", "md": MD, "type": "Follow-Up", "sections": [
              ("Interval History", "Duplex reviewed, below. Symptoms persist: aching and heaviness most days, ankle swelling by evening. Patient reports she is 'still wearing the stockings'. Symptoms make it hard to finish her usual errands and she has stopped her weekly bowling league."),
              ("Assessment & Plan", "Left GSV reflux, CEAP C3, symptomatic. Recommend endovenous laser ablation of the left GSV. Submit prior authorization."),
          ]},
      ],
      [{"title": "Lower Extremity Venous Reflux Duplex Ultrasound — Left — September 23, 2025", "md": US_MD, "date": "September 23, 2025",
        "rows": [("Indication", "Left leg varicose veins and edema; evaluate reflux"), ("Deep System", "No DVT. No deep venous reflux."),
                 ("Great Saphenous Vein", "Incompetent. SFJ reflux 1.6 seconds. GSV diameter 6.4 mm at SFJ, 5.2 mm mid-thigh."),
                 ("Small Saphenous Vein", "Competent."), ("Perforators", "No incompetent perforators."), ("Tributaries", "Dilated medial calf tributaries 3–4 mm.")],
        "interp": "Left great saphenous vein reflux with axial incompetence. No DVT."}],
      {"rows": [("Planned Procedure", "Endovenous laser ablation, left great saphenous vein"), ("CPT", "36478 — Endovenous ablation therapy of incompetent vein, extremity, laser; first vein treated"),
                ("Laterality", "Left"), ("Diagnosis", "I83.812, I87.2"), ("Surgeon", MD), ("Payer", "Florida Blue PPO"), ("PA Status", "Pending")],
       "summary": ["Left GSV reflux 1.6 s on duplex 09/23/2025.", "CEAP C3 with edema; varicosities approx. 4 mm.", "Symptomatic despite compression stockings.", "Symptoms limit daily activities."]})
