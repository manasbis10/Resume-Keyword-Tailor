from __future__ import annotations

import io
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate

from app.models import TailoredResume

FONT_DIR = Path(__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Resume", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Resume-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

INK = HexColor("#1c1915")
MUTED = HexColor("#5c564c")
RULE = HexColor("#c45c26")
PAPER = HexColor("#fbf7f0")


def build_resume_pdf(resume: TailoredResume) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"{resume.name or 'Resume'} — tailored",
    )

    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "Name",
        parent=styles["Title"],
        fontName="Resume-Bold",
        fontSize=22,
        leading=26,
        textColor=INK,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontName="Resume",
        fontSize=9.5,
        leading=12,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Resume-Bold",
        fontSize=11,
        leading=14,
        textColor=INK,
        spaceBefore=10,
        spaceAfter=3,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Resume",
        fontSize=10,
        leading=13,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    role_style = ParagraphStyle(
        "Role",
        parent=styles["Normal"],
        fontName="Resume-Bold",
        fontSize=10.5,
        leading=13,
        textColor=INK,
        spaceBefore=6,
        spaceAfter=0,
        keepWithNext=True,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="Resume",
        fontSize=9.5,
        leading=12,
        textColor=MUTED,
        spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        alignment=TA_LEFT,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=2,
    )

    story = []
    story.append(Paragraph(_esc(resume.name or "Resume"), name_style))
    if resume.contact:
        story.append(Paragraph(_esc(resume.contact), contact_style))
    story.append(HRFlowable(width="100%", thickness=1.4, color=RULE, spaceAfter=6))

    if resume.summary:
        story.append(Paragraph("SUMMARY", section_style))
        story.append(Paragraph(_esc(resume.summary), body_style))

    if resume.skills:
        story.append(Paragraph("SKILLS", section_style))
        story.append(Paragraph(_esc(" · ".join(resume.skills)), body_style))

    if resume.experience:
        story.append(Paragraph("EXPERIENCE", section_style))
        for job in resume.experience:
            headline = " · ".join(part for part in [job.title, job.company] if part)
            story.append(Paragraph(_esc(headline), role_style))
            meta = " · ".join(part for part in [job.dates, job.location] if part)
            if meta:
                story.append(Paragraph(_esc(meta), meta_style))
            for bullet in job.bullets:
                story.append(Paragraph(f"• {_esc(bullet)}", bullet_style))

    if resume.education:
        story.append(Paragraph("EDUCATION", section_style))
        for edu in resume.education:
            headline = " · ".join(part for part in [edu.degree, edu.school] if part)
            story.append(Paragraph(_esc(headline), role_style))
            meta = " · ".join(part for part in [edu.dates, edu.details] if part)
            if meta:
                story.append(Paragraph(_esc(meta), meta_style))

    for heading, lines in resume.extra_sections.items():
        if not heading or not lines:
            continue
        story.append(Paragraph(_esc(heading.upper()), section_style))
        for line in lines:
            story.append(Paragraph(f"• {_esc(line)}", bullet_style))

    def _paint(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(PAPER)
        canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=_paint, onLaterPages=_paint)
    return buffer.getvalue()


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
