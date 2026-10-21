"""
pdf_service.py  —  PDF report generator (100% FREE using reportlab).

Generates a professional PDF report of leads with:
  - Summary header (product, region, total leads, score stats)
  - Lead table (title, phone, address, category, score, status)
  - Scatterplot score visualization (text-based bar chart)

Requires: reportlab  (add to requirements.txt)
"""

import logging
import io
from datetime import datetime

from reportlab.lib                import colors
from reportlab.lib.pagesizes      import A4
from reportlab.lib.styles         import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units          import cm
from reportlab.platypus           import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.enums          import TA_CENTER, TA_LEFT

logger = logging.getLogger("lead_gen.pdf")

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
DARK_BLUE   = colors.HexColor("#1E3A5F")
ACCENT_BLUE = colors.HexColor("#2C7BE5")
LIGHT_GRAY  = colors.HexColor("#F5F7FA")
MID_GRAY    = colors.HexColor("#94A3B8")
GREEN       = colors.HexColor("#22C55E")
AMBER       = colors.HexColor("#F59E0B")
RED_SOFT    = colors.HexColor("#EF4444")
WHITE       = colors.white


def _score_color(score: int):
    if score >= 70:
        return GREEN
    if score >= 50:
        return ACCENT_BLUE
    if score >= 35:
        return AMBER
    return RED_SOFT


def _score_bar(score: int, max_width: int = 20) -> str:
    """Create a simple ASCII bar chart for score."""
    filled = int((score / 100) * max_width)
    return "█" * filled + "░" * (max_width - filled)


def generate_leads_pdf(
    leads: list,
    product_name: str,
    region: str,
    description: str = "",
    score_summary: dict = None,
) -> bytes:
    """
    Generate a PDF report for a set of leads.

    Returns
    -------
    bytes — PDF file content (save to file or return as HTTP response)
    """
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles  = getSampleStyleSheet()
    story   = []

    # ------------------------------------------------------------------ #
    # Title Section
    # ------------------------------------------------------------------ #
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=DARK_BLUE,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=MID_GRAY,
        spaceAfter=2,
    )

    story.append(Paragraph("Lead Generation Report", title_style))
    story.append(Paragraph(
        f"Product: <b>{product_name}</b> &nbsp;|&nbsp; Region: <b>{region}</b> &nbsp;|&nbsp; "
        f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}",
        sub_style,
    ))
    if description:
        story.append(Paragraph(f"Description: {description}", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT_BLUE))
    story.append(Spacer(1, 0.4 * cm))

    # ------------------------------------------------------------------ #
    # Score Summary Cards
    # ------------------------------------------------------------------ #
    if score_summary:
        summary_data = [
            ["Total Leads", "Max Score", "Avg Score", "Min Score"],
            [
                str(len(leads)),
                str(score_summary.get("max", 0)),
                str(score_summary.get("avg", 0)),
                str(score_summary.get("min", 0)),
            ],
        ]
        summary_table = Table(summary_data, colWidths=[4 * cm] * 4)
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
            ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",    (0, 0), (-1, 0), 10),
            ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND",  (0, 1), (-1, 1), LIGHT_GRAY),
            ("FONTSIZE",    (0, 1), (-1, 1), 14),
            ("FONTNAME",    (0, 1), (-1, 1), "Helvetica-Bold"),
            ("TEXTCOLOR",   (0, 1), (-1, 1), DARK_BLUE),
            ("GRID",        (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [DARK_BLUE, LIGHT_GRAY]),
            ("TOPPADDING",  (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.6 * cm))

    # ------------------------------------------------------------------ #
    # Lead Table
    # ------------------------------------------------------------------ #
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=DARK_BLUE,
        spaceAfter=6,
    )
    story.append(Paragraph("All Leads", section_style))

    # Table header
    headers = ["#", "Business Name", "Phone", "Address", "Category", "Score", "Status"]
    col_widths = [0.8*cm, 4.5*cm, 3*cm, 4*cm, 2.8*cm, 1.5*cm, 2*cm]

    table_data = [headers]

    for i, lead in enumerate(leads, start=1):
        score   = lead.get("score", 0)
        address = (lead.get("address") or "N/A")[:35]
        table_data.append([
            str(i),
            (lead.get("title") or "N/A")[:30],
            lead.get("phone") or "N/A",
            address,
            (lead.get("category") or "N/A")[:20],
            str(score),
            lead.get("status", "new").upper(),
        ])

    lead_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Build table style
    ts = TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        # Data rows
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",         (0, 0), (0, -1), "CENTER"),   # # column
        ("ALIGN",         (5, 0), (5, -1), "CENTER"),   # score column
    ])

    # Color-code score cells
    for i, lead in enumerate(leads, start=1):
        score = lead.get("score", 0)
        ts.add("TEXTCOLOR", (5, i), (5, i), _score_color(score))
        ts.add("FONTNAME",  (5, i), (5, i), "Helvetica-Bold")

    lead_table.setStyle(ts)
    story.append(lead_table)
    story.append(Spacer(1, 0.8 * cm))

    # ------------------------------------------------------------------ #
    # Score Bar Chart (text-based)
    # ------------------------------------------------------------------ #
    story.append(Paragraph("Score Distribution", section_style))
    bar_style = ParagraphStyle(
        "Bar",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        spaceAfter=2,
    )
    for lead in leads[:10]:   # top 10
        title = (lead.get("title") or "N/A")[:25].ljust(25)
        bar   = _score_bar(lead.get("score", 0))
        story.append(Paragraph(
            f"{title}  {bar}  {lead.get('score', 0)}/100",
            bar_style,
        ))

    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info("PDF generated: %d bytes | %d leads", len(pdf_bytes), len(leads))
    return pdf_bytes
