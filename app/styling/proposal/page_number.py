# app/styling/proposal/page_number.py
from __future__ import annotations

from io import BytesIO
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas


# Match the baked-in template page size (7.5" x 10" = 540 x 720 pt).
# The overlay MUST be the same size as the underlying page, otherwise
# merge_page will misalign the number (this is why it was invisible on
# the 540x720 testimonial page when the overlay was letter-sized).
PAGE_WIDTH, PAGE_HEIGHT = 540, 720
OVERLAY_PAGE_SIZE = (PAGE_WIDTH, PAGE_HEIGHT)

BLACK = Color(0.05, 0.05, 0.05, alpha=1)
WHITE = Color(1, 1, 1, alpha=1)

# These coordinates match the baked-in "2" and "3" on the intro and
# process pages so generated numbers line up identically across the deck.
PAGE_NUM_X = PAGE_WIDTH - 20   # right edge of the number ~= 520
PAGE_NUM_Y = 20                # baseline 20 pt up from the bottom

FONT_NAME = "Helvetica"
FONT_SIZE = 8                  # matches the baked-in number size


def _number_overlay(page_number: int, color: Color) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=OVERLAY_PAGE_SIZE)

    c.setFillColor(color)
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawRightString(PAGE_NUM_X, PAGE_NUM_Y, str(page_number))

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def add_page_numbers(
    pdf_bytes: bytes,
    start_at: int = 1,
    black_page_indexes: Iterable[int] | None = None,
    white_page_indexes: Iterable[int] | None = None,
) -> bytes:
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()

    black_set = set(black_page_indexes or [])
    white_set = set(white_page_indexes or [])

    current_number = start_at

    for index, page in enumerate(reader.pages):
        color = None

        if index in black_set:
            color = BLACK
        elif index in white_set:
            color = WHITE

        if color is not None:
            overlay_bytes = _number_overlay(current_number, color)
            overlay_pdf = PdfReader(BytesIO(overlay_bytes))
            page.merge_page(overlay_pdf.pages[0])
            current_number += 1

        writer.add_page(page)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
