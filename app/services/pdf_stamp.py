# app/services/pdf_stamp.py
from __future__ import annotations

import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def stamp_pdf(pdf_bytes: bytes, text_to_stamp: str) -> bytes:
    """
    Overlay a visible stamp on every page (MVP watermark).
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        overlay_buf = io.BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(w, h))

        # Big diagonal watermark
        c.saveState()
        c.setFont("Helvetica-Bold", 42)
        c.translate(w / 2, h / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, text_to_stamp)
        c.restoreState()

        # Small top-right label
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(w - 24, h - 24, text_to_stamp)

        c.save()
        overlay_buf.seek(0)

        overlay_reader = PdfReader(overlay_buf)
        overlay_page = overlay_reader.pages[0]

        page.merge_page(overlay_page)
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()