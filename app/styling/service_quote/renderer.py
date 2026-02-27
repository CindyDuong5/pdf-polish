# app/styling/service_quote/renderer.py
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.styling.service_quote.parser import ServiceQuoteData, SQLine

# Header text blocks
HDR_CLIENT_X = 72
HDR_CLIENT_Y_TOP = 705
HDR_COMPANY_X = 245
HDR_COMPANY_Y_TOP = 705
HDR_PROPERTY_X = 420
HDR_PROPERTY_Y_TOP = 705

HDR_META_X = 72
HDR_META_Y_TOP = 610

# Totals (bottom-right block)
TOT_X_RIGHT = 555
TOT_SUB_Y = 135
TOT_TAX_Y = 120
TOT_TOTAL_Y = 105

# Item list area
X_LEFT = 72
X_RIGHT = 555
X_PRICE_RIGHT = 555
X_DESC_INDENT = 14

Y_START_FIRST = 520   # start y for first page item list
Y_BOTTOM = 170        # stop y for first page item list (spill below)

# Continuation page header (blank continuation pages)
CONT_HEADER_Y = 760
CONT_Y_START = 710
CONT_Y_BOTTOM = 70

# Fonts
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FS_HDR = 10
FS_META = 10
FS_ITEM = 10
FS_DESC = 9

LINE_GAP = 2
ITEM_GAP = 8


def _clean(s: str) -> str:
    return (s or "").replace("\u00a0", " ").replace("\x00", "").strip()


def _money_str(x) -> str:
    try:
        if x is None:
            return ""
        return f"${float(x):,.2f}"
    except Exception:
        return ""


def _wrap_text(text: str, font: str, font_size: int, max_width: float) -> List[str]:
    text = _clean(text)
    if not text:
        return []

    words = text.split()
    lines: List[str] = []
    cur = ""

    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, font_size) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)

            # Hard split long word if needed
            if stringWidth(w, font, font_size) <= max_width:
                cur = w
            else:
                chunk = ""
                for ch in w:
                    test2 = chunk + ch
                    if stringWidth(test2, font, font_size) <= max_width:
                        chunk = test2
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk

    if cur:
        lines.append(cur)

    return lines


def _split_description(desc: str) -> List[str]:
    desc = (desc or "").replace("\r", "\n")
    raw = [ln.strip() for ln in desc.split("\n")]
    return [ln for ln in raw if ln]


def _draw_multiline(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    lines: List[str],
    font: str,
    size: int,
    line_step: float,
) -> float:
    """
    Draw lines downward from y_top. Returns new y after drawing.
    """
    c.setFont(font, size)
    y = y_top
    for ln in lines:
        c.drawString(x, y, ln)
        y -= line_step
    return y


def _draw_header_overlay(page_w: float, page_h: float, data: ServiceQuoteData) -> bytes:
    """
    Draw header fields directly onto the template page.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # Client block
    client_lines = [
        _clean(data.client_name),
        _clean(data.client_phone),
        _clean(data.client_email),
    ]
    client_lines = [x for x in client_lines if x]
    _draw_multiline(c, HDR_CLIENT_X, HDR_CLIENT_Y_TOP, client_lines, FONT, FS_HDR, 14)

    # Company block
    company_lines = [
        _clean(data.company_name),
        _clean(data.company_address),
    ]
    company_lines = [x for x in company_lines if x]
    _draw_multiline(c, HDR_COMPANY_X, HDR_COMPANY_Y_TOP, company_lines, FONT, FS_HDR, 14)

    # Property block
    property_lines = [
        _clean(data.property_name),
        _clean(data.property_address),
    ]
    property_lines = [x for x in property_lines if x]
    _draw_multiline(c, HDR_PROPERTY_X, HDR_PROPERTY_Y_TOP, property_lines, FONT, FS_HDR, 14)

    # Quote meta
    meta_lines = []
    if data.quote_description:
        meta_lines.append(_clean(data.quote_description))
    if data.quote_number:
        meta_lines.append(f"Estimate #: {_clean(data.quote_number)}")
    if data.quote_date:
        meta_lines.append(f"Date: {_clean(data.quote_date)}")

    wrapped_meta: List[str] = []
    for ln in meta_lines:
        wrapped_meta.extend(_wrap_text(ln, FONT, FS_META, 470))

    _draw_multiline(c, HDR_META_X, HDR_META_Y_TOP, wrapped_meta, FONT, FS_META, 14)

    # Totals (right aligned)
    c.setFont(FONT, FS_HDR)
    if data.subtotal:
        c.drawRightString(TOT_X_RIGHT, TOT_SUB_Y, _clean(data.subtotal))
    if data.tax:
        c.drawRightString(TOT_X_RIGHT, TOT_TAX_Y, _clean(data.tax))
    if data.total:
        c.drawRightString(TOT_X_RIGHT, TOT_TOTAL_Y, _clean(data.total))

    # ✅ CRITICAL: ensure the PDF has at least one page
    c.showPage()
    c.save()

    buf.seek(0)
    return buf.getvalue()


def _item_block_lines(item: SQLine, desc_width: float) -> List[Tuple[str, str, int]]:
    """
    Returns draw instructions:
      ("name", text, fs) for item header lines (already wrapped)
      ("desc", text, fs) for description lines
    """
    lines: List[Tuple[str, str, int]] = []

    name = _clean(item.name) or "(Item)"
    name_wrapped = _wrap_text(name, FONT_BOLD, FS_ITEM, desc_width)
    for w in name_wrapped:
        lines.append(("name", w, FS_ITEM))

    desc_lines = _split_description(item.description)
    for dl in desc_lines:
        is_bullet = dl.startswith("-")
        dl2 = dl[1:].strip() if is_bullet else dl
        prefix = "• " if is_bullet else ""
        wrapped = _wrap_text(prefix + dl2, FONT, FS_DESC, desc_width)
        for w in wrapped:
            lines.append(("desc", w, FS_DESC))

    return lines


def _build_items_overlay_pages(
    page_w: float,
    page_h: float,
    data: ServiceQuoteData,
) -> List[bytes]:
    """
    Create one or more overlay pages that draw items with wrapping and overflow.
    Page 1 uses template coordinates. Extra pages are "continuation" blank pages.
    """
    overlays: List[bytes] = []

    price_col_gap = 120
    name_width = (X_RIGHT - price_col_gap) - X_LEFT
    desc_width = name_width - X_DESC_INDENT

    def new_canvas() -> Tuple[canvas.Canvas, io.BytesIO]:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_w, page_h))
        return c, buf

    def finish_page(c: canvas.Canvas, buf: io.BytesIO):
        # ✅ CRITICAL: ensure a page exists
        c.showPage()
        c.save()
        buf.seek(0)
        overlays.append(buf.getvalue())

    def draw_cont_header(c: canvas.Canvas):
        c.setFont(FONT_BOLD, 14)
        c.drawString(X_LEFT, CONT_HEADER_Y, "Service Quote (continued)")
        c.setFont(FONT, 10)
        meta = " / ".join([x for x in [_clean(data.quote_number), _clean(data.quote_date)] if x])
        if meta:
            c.drawRightString(X_RIGHT, CONT_HEADER_Y, meta)
        c.line(X_LEFT, CONT_HEADER_Y - 18, X_RIGHT, CONT_HEADER_Y - 18)

    items = data.items or []

    # Always return at least ONE overlay page (even if empty)
    if not items:
        c, buf = new_canvas()
        finish_page(c, buf)
        return overlays

    # Page 1
    c, buf = new_canvas()
    y = Y_START_FIRST
    y_bottom = Y_BOTTOM

    for item in items:
        price = _money_str(item.price)
        block = _item_block_lines(item, desc_width)

        # If no room for at least one header line, spill to new page
        min_needed = FS_ITEM + LINE_GAP
        if y - min_needed < y_bottom:
            finish_page(c, buf)
            c, buf = new_canvas()
            draw_cont_header(c)
            y = CONT_Y_START
            y_bottom = CONT_Y_BOTTOM

        # Draw item name lines (first line also draws price)
        first_name_line = True
        for kind, text, fs in block:
            if kind != "name":
                continue

            if y - (fs + LINE_GAP) < y_bottom:
                finish_page(c, buf)
                c, buf = new_canvas()
                draw_cont_header(c)
                y = CONT_Y_START
                y_bottom = CONT_Y_BOTTOM
                first_name_line = True

            c.setFont(FONT_BOLD, fs)
            c.drawString(X_LEFT, y, text)
            if first_name_line and price:
                c.drawRightString(X_PRICE_RIGHT, y, price)
            first_name_line = False
            y -= (fs + LINE_GAP)

        # Draw description lines
        for kind, text, fs in block:
            if kind != "desc":
                continue

            if y - (fs + LINE_GAP) < y_bottom:
                finish_page(c, buf)
                c, buf = new_canvas()
                draw_cont_header(c)
                y = CONT_Y_START
                y_bottom = CONT_Y_BOTTOM

            c.setFont(FONT, fs)
            c.drawString(X_LEFT + X_DESC_INDENT, y, text)
            y -= (fs + LINE_GAP)

        y -= ITEM_GAP

    finish_page(c, buf)
    return overlays


def render_service_quote(template_pdf: Path, data: ServiceQuoteData) -> bytes:
    """
    Render Service Quote draft using template as base page 1,
    then merge overlay PDFs for header + items.
    """
    base_reader = PdfReader(str(template_pdf))
    writer = PdfWriter()

    # Base: template first page
    writer.add_page(base_reader.pages[0])

    page_w = float(writer.pages[0].mediabox.width)
    page_h = float(writer.pages[0].mediabox.height)

    # Header overlay
    hdr_pdf = _draw_header_overlay(page_w, page_h, data)
    hdr_reader = PdfReader(io.BytesIO(hdr_pdf))
    if len(hdr_reader.pages) > 0:
        writer.pages[0].merge_page(hdr_reader.pages[0])

    # Items overlays
    item_overlays = _build_items_overlay_pages(page_w, page_h, data)

    # Merge items overlay for page 1 (only if exists)
    if item_overlays:
        ov0_reader = PdfReader(io.BytesIO(item_overlays[0]))
        if len(ov0_reader.pages) > 0:
            writer.pages[0].merge_page(ov0_reader.pages[0])

    # Add continuation pages if needed
    for i in range(1, len(item_overlays)):
        writer.add_blank_page(width=page_w, height=page_h)
        ov_reader = PdfReader(io.BytesIO(item_overlays[i]))
        if len(ov_reader.pages) > 0:
            writer.pages[i].merge_page(ov_reader.pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()