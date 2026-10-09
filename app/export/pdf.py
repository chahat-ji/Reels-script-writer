"""
app/export/pdf.py
Hollywood standard screenplay PDF generator.

Formats screenplays with:
- Standard 12pt Courier typography
- Industry margins (1.5" left for binding, 1.0" right/top/bottom)
- Precise element indentation (Character 3.7", Parenthetical 3.1", Dialogue 2.5")
- Slugline bolding, button right-alignment, and page numbering
"""

from pathlib import Path
import re
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.core.config import console, settings
from app.core.database import get_db_session
from app.generation.parser import parse_screenplay_elements
from app.models.schema import Script, Style


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically inject page numbers (e.g. '1.') at top-right.
    Standard screenplay convention: Page numbers appear on top-right margin from page 2 onwards.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self.setFont("Courier", 10)
                self.drawRightString(letter[0] - 72, letter[1] - 36, f"{self._pageNumber}.")
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


def sanitize_text_for_pdf(text: str) -> str:
    """
    Clean text for standard Courier rendering:
    - Replaces Rupee symbol with 'Rs.'
    - Escapes XML characters (&, <, >)
    - Strips emojis and unsupported non-Latin characters
    """
    if not text:
        return ""
    t = text.replace("₹", "Rs. ")
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Strip emojis and control characters
    t = re.sub(r"[^\x00-\x7F]+", "", t)
    return t.strip()


def export_screenplay_to_pdf(script_id: str, output_path: Optional[Path] = None) -> Path:
    """
    Export a generated screenplay from SQLite to a professional Hollywood PDF.

    Args:
        script_id: Unique script identifier.
        output_path: Optional custom destination path. Defaults to data/exports/{script_id}.pdf.

    Returns:
        Path to the generated PDF file.
    """
    with get_db_session() as session:
        script = session.query(Script).filter_by(script_id=script_id).first()
        if not script:
            raise ValueError(f"Script with id '{script_id}' not found.")

        style = session.query(Style).filter_by(style_id=script.style_id).first()
        creator_name = style.name if (style and style.name) else script.style_id

        premise = script.premise
        raw_text = script.script_text
        created_str = script.created_at.strftime("%B %d, %Y") if script.created_at else "N/A"

    dest_path = output_path or (settings.exports_dir / f"{script_id}.pdf")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Document setup with standard Hollywood margins (72 pt = 1 inch)
    # Left: 1.5 in (108 pt), Right: 1.0 in (72 pt), Top: 1.0 in (72 pt), Bottom: 1.0 in (72 pt)
    doc = SimpleDocTemplate(
        str(dest_path),
        pagesize=letter,
        leftMargin=108,
        rightMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    styles = getSampleStyleSheet()

    # Custom Screenplay Paragraph Styles
    style_title = ParagraphStyle(
        "SP_Title",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=14,
        leading=18,
        alignment=1,  # Centered
        spaceAfter=4,
    )

    style_meta = ParagraphStyle(
        "SP_Meta",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=9,
        leading=13,
        alignment=1,  # Centered
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=14,
    )

    style_slugline = ParagraphStyle(
        "SP_Slugline",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=12,
        leading=14.4,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    style_action = ParagraphStyle(
        "SP_Action",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=12,
        leading=14.4,
        spaceBefore=3,
        spaceAfter=6,
    )

    # Indentation calibrated for printable area (432 pt wide)
    style_character = ParagraphStyle(
        "SP_Character",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=12,
        leading=14.4,
        leftIndent=150,
        spaceBefore=8,
        spaceAfter=1,
        keepWithNext=True,
    )

    style_parenthetical = ParagraphStyle(
        "SP_Parenthetical",
        parent=styles["Normal"],
        fontName="Courier-Oblique",
        fontSize=12,
        leading=14.4,
        leftIndent=110,
        rightIndent=110,
        spaceBefore=1,
        spaceAfter=2,
        keepWithNext=True,
    )

    style_dialogue = ParagraphStyle(
        "SP_Dialogue",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=12,
        leading=14.4,
        leftIndent=72,
        rightIndent=72,
        spaceBefore=1,
        spaceAfter=6,
    )

    style_button = ParagraphStyle(
        "SP_Button",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=12,
        leading=14.4,
        alignment=2,  # Right-aligned
        spaceBefore=16,
        spaceAfter=10,
    )

    story = []

    # Title header block
    story.append(Paragraph(f"SCREENPLAY: {sanitize_text_for_pdf(script_id.upper())}", style_title))
    story.append(
        Paragraph(
            f"Creator Style: {sanitize_text_for_pdf(creator_name)} | Date: {created_str}<br/>"
            f"Premise: \"{sanitize_text_for_pdf(premise)}\"",
            style_meta,
        )
    )
    story.append(Spacer(1, 10))

    # Parse and build story flowables
    elements = parse_screenplay_elements(raw_text)

    for el in elements:
        raw_val = el.get("text", "")
        clean_val = sanitize_text_for_pdf(raw_val)

        if not clean_val and el.get("type") != "blank":
            continue

        el_type = el.get("type")

        if el_type == "slugline":
            story.append(Paragraph(clean_val.upper(), style_slugline))
        elif el_type == "character":
            story.append(Paragraph(clean_val.upper(), style_character))
        elif el_type == "parenthetical":
            story.append(Paragraph(clean_val, style_parenthetical))
        elif el_type == "dialogue":
            story.append(Paragraph(clean_val, style_dialogue))
        elif el_type == "action":
            story.append(Paragraph(clean_val, style_action))
        elif el_type == "button":
            story.append(Paragraph(clean_val.upper(), style_button))
        elif el_type == "blank":
            story.append(Spacer(1, 6))

    # Build PDF using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)

    console.print(f"[bold green]✓ Screenplay PDF Generated:[/bold green] [cyan]{dest_path}[/cyan]")
    return dest_path

