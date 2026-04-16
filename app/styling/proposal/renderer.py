# app/styling/proposal/renderer.py
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


LEFT = 40
RIGHT = 572
TOP = 752
BOTTOM = 50
LINE = 14


def _draw_wrapped_text(
    c: canvas.Canvas,
    text: str,
    x: int,
    y: int,
    max_chars: int = 95,
) -> int:
    if not text:
        return y

    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            y -= LINE
            continue

        while len(line) > max_chars:
            chunk = line[:max_chars]
            split_at = chunk.rfind(" ")
            if split_at <= 0:
                split_at = max_chars
            c.drawString(x, y, line[:split_at])
            y -= LINE
            line = line[split_at:].strip()

        if line:
            c.drawString(x, y, line)
            y -= LINE

    return y


def render_proposal_pdf(fields: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    y = TOP

    c.setFont("Helvetica-Bold", 18)
    c.drawString(LEFT, y, "PROPOSAL")
    y -= 28

    c.setFont("Helvetica", 10)
    c.drawString(LEFT, y, f"Proposal Number: {fields.get('proposal_number', '')}")
    c.drawRightString(RIGHT, y, f"Date: {fields.get('proposal_date', '')}")
    y -= 16

    c.drawString(LEFT, y, f"Proposal Type: {fields.get('proposal_type', '')}")
    c.drawRightString(RIGHT, y, f"Prepared By: {fields.get('prepared_by', '')}")
    y -= 26

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Prepared For")
    y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(LEFT, y, f"Contact Name: {fields.get('contact_name', '')}")
    y -= 14
    c.drawString(LEFT, y, f"Contact Email: {fields.get('contact_email', '')}")
    y -= 14
    c.drawString(LEFT, y, f"Contact Phone: {fields.get('contact_phone', '')}")
    y -= 22

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Company")
    y -= 16

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_text(c, fields.get("customer_name", ""), LEFT, y)
    y = _draw_wrapped_text(c, fields.get("customer_address", ""), LEFT, y)
    y -= 8

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Property")
    y -= 16

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_text(c, fields.get("property_name", ""), LEFT, y)
    y = _draw_wrapped_text(c, fields.get("property_address", ""), LEFT, y)
    y -= 8

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Scope Summary")
    y -= 16

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_text(c, fields.get("scope_summary", ""), LEFT, y)
    y -= 8

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Items")
    y -= 18

    c.setFont("Helvetica-Bold", 10)
    c.drawString(LEFT, y, "Item")
    c.drawString(160, y, "Description")
    c.drawRightString(RIGHT, y, "Price")
    y -= 14

    c.line(LEFT, y, RIGHT, y)
    y -= 12

    c.setFont("Helvetica", 10)
    for row in fields.get("items", []):
        item = str(row.get("item", "") or "")
        desc = str(row.get("description", "") or "")
        price = str(row.get("price", "") or "")

        if y < 100:
            c.showPage()
            y = TOP
            c.setFont("Helvetica-Bold", 10)
            c.drawString(LEFT, y, "Item")
            c.drawString(160, y, "Description")
            c.drawRightString(RIGHT, y, "Price")
            y -= 14
            c.line(LEFT, y, RIGHT, y)
            y -= 12
            c.setFont("Helvetica", 10)

        row_start_y = y
        c.drawString(LEFT, row_start_y, item[:22])
        desc_y = _draw_wrapped_text(c, desc, 160, row_start_y, max_chars=55)
        c.drawRightString(RIGHT, row_start_y, price)

        y = min(desc_y, row_start_y - LINE)

    y -= 12
    c.line(340, y, RIGHT, y)
    y -= 18

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(RIGHT, y, f"Subtotal: {fields.get('subtotal', '')}")
    y -= 14
    c.drawRightString(RIGHT, y, f"Tax ({fields.get('tax_rate', '')}%): {fields.get('tax', '')}")
    y -= 14
    c.drawRightString(RIGHT, y, f"Total: {fields.get('total', '')}")
    y -= 24

    c.setFont("Helvetica-Bold", 11)
    c.drawString(LEFT, y, "Exclusions")
    y -= 16

    c.setFont("Helvetica", 10)
    y = _draw_wrapped_text(c, fields.get("exclusions", ""), LEFT, y)

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes