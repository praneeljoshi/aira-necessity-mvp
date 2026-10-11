"""Generate linda_park_addendum.pdf — one addendum note for the Gate 9 append demo.
Same practice header and styles as make_charts.py. Fictional.      python make_park_addendum.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
SS = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=13, spaceBefore=10, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3)
P = ParagraphStyle("p", parent=SS["BodyText"], fontSize=9.5, leading=12.5)
SM = ParagraphStyle("sm", parent=P, fontSize=8, textColor=colors.grey)

GULF = {"name": "GULF COAST VASCULAR SURGERY ASSOCIATES",
        "addr": "2200 Bayshore Blvd, Suite 310 | Tampa, FL 33606 | (813) 555-0140 | NPI: 1987654321"}
MD = "Dr. Elena Vasquez, MD, FACS"


def kv(rows):
    t = Table([[Paragraph(f"<b>{k}</b>", P), Paragraph(v, P)] for k, v in rows], colWidths=[1.7 * inch, 4.8 * inch])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


doc = SimpleDocTemplate(str(HERE / "linda_park_addendum.pdf"), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                        topMargin=0.7 * inch, bottomMargin=0.7 * inch, title="Linda Park — Addendum 10/02/2025", author=GULF["name"])
s = [Paragraph(GULF["name"], SS["Title"]), Paragraph(GULF["addr"], SM),
     Paragraph("PATIENT MEDICAL CHART — CONFIDENTIAL — FOR AUTHORIZED USE ONLY", SM),
     Paragraph("ADDENDUM TO CHART", H1),
     kv([("Patient Name", "Linda Park"), ("Date of Birth", "November 30, 1962"), ("MRN", "GCV-011203"), ("Age", "62 years"), ("Sex", "Female"),
         ("Payer", "Florida Blue PPO — BlueOptions, member FLB309118465"), ("Primary Care Physician", "Dr. Henry Kwon, MD"),
         ("Addendum To", "Follow-Up visit of September 30, 2025 (Dr. Elena Vasquez)"), ("Reason", "Prior authorization — clarify compression therapy start date and duration")]),
     Paragraph("6. VISIT NOTES — VASCULAR SURGERY", H1),
     Paragraph(f"Visit Date: October 2, 2025 | Attending: {MD} | Type: Addendum", H2),
     Paragraph("<b>Addendum:</b>", P),
     Paragraph("This addendum is entered on October 2, 2025 to the follow-up note of September 30, 2025, after review of the primary care "
               "record received from Dr. Henry Kwon's office and telephone confirmation with the patient on October 1, 2025.", P), Spacer(1, 3),
     Paragraph("<b>Compression Therapy Start Date:</b>", P),
     Paragraph("Graduated compression stockings, 20–30 mmHg, knee-high, were begun on May 12, 2025 (05/12/2025). They were dispensed by the "
               "primary care office on that date and the patient confirms she has worn them daily, from morning until bedtime, from 05/12/2025 "
               "through the present without interruption. The strength is confirmed as 20–30 mmHg from the dispensing record.", P), Spacer(1, 3),
     Paragraph("<b>Symptom Status at the September 30, 2025 Visit:</b>", P),
     Paragraph("At the 09/30/2025 visit the patient's symptoms were unchanged from the 09/09/2025 consultation: left leg aching and heaviness "
               "most days and ankle swelling by evening, despite daily 20–30 mmHg compression from 05/12/2025 through 09/30/2025 (more than "
               "4 months), together with leg elevation and acetaminophen as needed. Symptoms have not improved with conservative management "
               "and continue to limit her daily activities as documented on 09/30/2025.", P), Spacer(1, 3),
     Paragraph("<b>Assessment:</b>", P),
     Paragraph("Symptomatic left great saphenous vein reflux, CEAP C3, unimproved after more than 3 months of 20–30 mmHg compression therapy "
               "(05/12/2025 to 09/30/2025). The recommendation for endovenous laser ablation of the left GSV (CPT 36478) stands; this "
               "addendum is submitted in support of the pending prior authorization to Florida Blue.", P), Spacer(1, 6),
     Paragraph(f"Electronically signed: {MD} — October 2, 2025 16:42", SM),
     Paragraph("Addendum entered after the original note was signed; the original note of September 30, 2025 is unchanged.", SM), Spacer(1, 8),
     Paragraph("This document is for clinical and administrative use only. Patient identifiers are fictional and created for demonstration purposes.", SM)]
doc.build(s)
print("wrote linda_park_addendum.pdf")
