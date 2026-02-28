# app/styling/service_quote/renderer.py
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from app.styling.service_quote.parser import ServiceQuoteData


# =========================
# Page + layout constants (tuned to match V2)
# =========================

PAGE_MARGIN_L = 0.60 * inch
PAGE_MARGIN_R = 0.60 * inch
PAGE_MARGIN_T = 0.55 * inch
PAGE_MARGIN_B = 0.55 * inch

# Header
HEADER_LOGO_H = 0.48 * inch          # ✅ logo smaller
HEADER_RULE_W = 2.6
HEADER_TEXT_FS = 8
HEADER_LINE_H = 11
HEADER_RULE_GAP = 18                  # ✅ same bottom gap to underline for logo + text
HEADER_BOTTOM_GAP = 0.18 * inch      # extra gap under underline before info row

# Four-column info row
INFO_TOP_GAP = 0.18 * inch
INFO_COL_GAP = 0.30 * inch
INFO_LABEL_FS = 8
INFO_TEXT_FS = 8
INFO_LINE_H = 11
INFO_RULE_W = 0.9

# Extra gap between info underline and title
INFO_TO_TITLE_GAP = 0.36 * inch

# Title + description
TITLE_FS = 21
DESC_FS = 9
TITLE_GAP_BELOW = 0.16 * inch
DESC_GAP_BELOW = 0.18 * inch

# Items
ITEM_BAR_H = 0.32 * inch
ITEM_BAR_FS = 10
ITEM_PRICE_FS = 10
ITEM_BULLET_FS = 9
ITEM_BULLET_LINE_H = 13
ITEM_BLOCK_GAP = 0.16 * inch
ITEM_BAR_COLOR = colors.HexColor("#EEE8E6")

# ✅ Bullet dot bigger (drawn circle)
BULLET_R = 1.9  # points
BULLET_DOT_Y_NUDGE = 3.2

# Totals (V2-like)
TOTAL_LABEL_FS = 9
TOTAL_VALUE_FS = 9
TOTAL_RULE_W = 0.8
TOTAL_RULE_COLOR = colors.HexColor("#D9D1CE")
TOTAL_ORANGE = colors.HexColor("#D35B3A")
TOTAL_BAR_H = 0.36 * inch
TOTAL_LABEL_PAD = 125  # ✅ labels closer to values

# Footer (every page)
FOOTER_FS = 8
FOOTER_Y = 0.40 * inch

# Colors
LIGHT_RULE = colors.HexColor("#D9D1CE")   # lighter line like V2
FOOTER_GRAY = colors.HexColor("#6F6A67")  # lighter black for footer

# Page 2
P2_TOP_BLANK = 0.75 * inch  # ✅ bigger blank header space
P2_TITLE_FS = 12
P2_TEXT_FS = 11
P2_LINE_H = 18


@dataclass
class PageSpec:
    w: float
    h: float


@dataclass
class ItemBlock:
    price: str
    title: str
    bullets: List[str]


# =========================
# Basics
# =========================

def _clean(s: str) -> str:
    return (s or "").replace("\u00a0", " ").replace("\x00", "").strip()


def _money_str(x) -> str:
    try:
        if x is None or str(x).strip() == "":
            return ""
        return f"${float(str(x)):,.2f}"
    except Exception:
        return ""


def _wrap_text(text: str, font: str, size: int, max_w: float) -> List[str]:
    text = _clean(text)
    if not text:
        return []

    words = text.split()
    lines: List[str] = []
    cur = ""

    for w in words:
        test = (cur + " " + w).strip()
        if stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            if stringWidth(w, font, size) <= max_w:
                cur = w
            else:
                chunk = ""
                for ch in w:
                    t2 = chunk + ch
                    if stringWidth(t2, font, size) <= max_w:
                        chunk = t2
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk

    if cur:
        lines.append(cur)
    return lines


def _split_desc(desc: str) -> List[str]:
    desc = (desc or "").replace("\r", "\n")
    raw = [ln.strip() for ln in desc.split("\n")]
    return [ln for ln in raw if ln]


def _page_spec_from_template(template_pdf: Path) -> PageSpec:
    try:
        r = PdfReader(str(template_pdf))
        p0 = r.pages[0]
        return PageSpec(w=float(p0.mediabox.width), h=float(p0.mediabox.height))
    except Exception:
        w, h = letter
        return PageSpec(w=float(w), h=float(h))


def _vcenter_baseline(bar_top: float, bar_h: float, font_size: float) -> float:
    """
    ReportLab text draws at baseline (not center).
    This puts baseline so the glyphs appear centered in the bar.
    """
    return bar_top - (bar_h / 2.0) - (font_size * 0.35)


# =========================
# Brand assets
# =========================

def _register_brand_assets(template_pdf: Path) -> tuple[str, str, Path | None]:
    fonts_dir = template_pdf.parent / "fonts"

    reg_font = fonts_dir / "PPNeueMontreal-Regular.otf"
    bold_font = fonts_dir / "PPNeueMontreal-Bold.otf"
    logo_path = fonts_dir / "Mainline-Primary-Logo-Black.png"

    font_regular = "Helvetica"
    font_bold = "Helvetica-Bold"

    try:
        if reg_font.exists():
            pdfmetrics.registerFont(TTFont("Mainline-Regular", str(reg_font)))
            font_regular = "Mainline-Regular"
        if bold_font.exists():
            pdfmetrics.registerFont(TTFont("Mainline-Bold", str(bold_font)))
            font_bold = "Mainline-Bold"
    except Exception:
        pass

    return font_regular, font_bold, (logo_path if logo_path.exists() else None)


# =========================
# Geometry helpers
# =========================

def _x0() -> float:
    return PAGE_MARGIN_L


def _x1(ps: PageSpec) -> float:
    return ps.w - PAGE_MARGIN_R


def _content_w(ps: PageSpec) -> float:
    return _x1(ps) - _x0()


# =========================
# Header / footer (V2)
# =========================

def _draw_header_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    page_no: int,
    total_pages: int,
    logo_path: Path | None,
    font_regular: str,
    font_bold: str,
) -> float:
    """
    ✅ Logo smaller + baseline aligned: logo bottom aligns to the same
    gap above the underline as the text blocks.
    """
    x0 = _x0()
    x1 = _x1(ps)
    w = x1 - x0
    y_top = ps.h - PAGE_MARGIN_T

    # 2:1:1 split
    col_w = (w - 3 * INFO_COL_GAP) / 4.0
    c1 = x0
    c2 = c1 + col_w + INFO_COL_GAP
    c3 = c2 + col_w + INFO_COL_GAP
    c4 = c3 + col_w + INFO_COL_GAP

    # Place header blocks aligned to columns:
    # - Logo stays on the left (spans first 2 columns visually)
    # - Address block aligns with "Property" column (c3)
    # - Contact block aligns with "Quote/Date" column (c4)
    logo_x0 = c1
    addr_x0 = c3
    cont_x0 = c4

    # We anchor the underline position from the top using text height.
    text_h = 3 * HEADER_LINE_H
    header_block_h = max(text_h, HEADER_LOGO_H)

    # underline y so that (underline + gap + header_block_h) fits under y_top nicely
    y_rule = y_top - (header_block_h + HEADER_RULE_GAP)
    y_block_bottom = y_rule + HEADER_RULE_GAP  # ✅ shared bottom for logo + last text line

    # Logo: bottom aligned to y_block_bottom
    if logo_path is not None:
        try:
            img = ImageReader(str(logo_path))
            iw, ih = img.getSize()
            scale = float(HEADER_LOGO_H) / float(ih) if ih else 1.0
            lw = iw * scale
            lh = ih * scale
            c.drawImage(
                img,
                logo_x0,
                y_block_bottom,  # ✅ bottom aligned
                width=lw,
                height=lh,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # Text blocks: last line baseline aligned near y_block_bottom
    # (small nudge up so it visually matches logo bottom)
    base = y_block_bottom + 2

    # Address block
    c.setFont(font_bold, HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 2 * HEADER_LINE_H, "Mainline Fire Protection")
    c.setFont(font_regular, HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 1 * HEADER_LINE_H, "411 Bradwick Dr, Unit 12")
    c.drawString(addr_x0, base + 0 * HEADER_LINE_H, "Concord, ON, L4K 2P4 Canada")

    # Contact block
    c.setFont(font_regular, HEADER_TEXT_FS)
    c.drawString(cont_x0, base + 2 * HEADER_LINE_H, "416-305-0704")
    c.drawString(cont_x0, base + 1 * HEADER_LINE_H, "contact@mainlinefire.com")
    c.drawString(cont_x0, base + 0 * HEADER_LINE_H, "MainlineFire.com")

    # thick underline
    c.setLineWidth(HEADER_RULE_W)
    c.line(x0, y_rule, x1, y_rule)

    return y_rule - HEADER_BOTTOM_GAP


def _draw_footer_v2(c: canvas.Canvas, ps: PageSpec, page_no: int, total_pages: int, font_regular: str) -> None:
    x0 = _x0()
    x1 = _x1(ps)
    xc = (x0 + x1) / 2.0

    c.setFillColor(FOOTER_GRAY)
    c.setFont(font_regular, FOOTER_FS)
    c.drawString(x0, FOOTER_Y, "Mainline Fire Protection")
    c.drawCentredString(xc, FOOTER_Y, "Toronto’s Fire Protection Company")
    c.drawRightString(x1, FOOTER_Y, f"Page {page_no} of {total_pages}")
    c.setFillColor(colors.black)


# =========================
# 4-column info row (wrap addresses)
# =========================

def _draw_info_row_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    data: ServiceQuoteData,
    font_regular: str,
    font_bold: str,
) -> float:
    x0 = _x0()
    x1 = _x1(ps)
    w = x1 - x0

    col_w = (w - 3 * INFO_COL_GAP) / 4.0
    c1 = x0
    c2 = c1 + col_w + INFO_COL_GAP
    c3 = c2 + col_w + INFO_COL_GAP
    c4 = c3 + col_w + INFO_COL_GAP

    y = y_top - INFO_TOP_GAP
    max_w = col_w - 6

    def label(x: float, txt: str) -> None:
        c.setFont(font_bold, INFO_LABEL_FS)
        c.drawString(x, y, txt)

    def text_lines_wrapped(x: float, raw_lines: List[str]) -> float:
        yy = y - INFO_LINE_H
        c.setFont(font_regular, INFO_TEXT_FS)
        for raw in raw_lines:
            raw = _clean(raw)
            if not raw:
                continue
            for ln in _wrap_text(raw, font_regular, INFO_TEXT_FS, max_w):
                c.drawString(x, yy, ln)
                yy -= INFO_LINE_H
        return yy

    # Attn
    label(c1, "Attn:")
    y1_end = text_lines_wrapped(c1, [data.client_name, data.client_phone, data.client_email])

    # Company
    label(c2, "Company:")
    y2_end = text_lines_wrapped(c2, [data.company_name, data.company_address])

    # Property
    label(c3, "Property:")
    y3_end = text_lines_wrapped(c3, [data.property_name, data.property_address])

    # Quote/Date: labels bold, values regular
    qn = _clean(data.quote_number)
    dt = _clean(data.quote_date)

    label_quote = "Quote #:"
    label_date = "Date:"
    pad = 4  # tight like V2

    c.setFont(font_bold, INFO_LABEL_FS)
    c.drawString(c4, y, label_quote)

    qx = c4 + stringWidth(label_quote, font_bold, INFO_LABEL_FS) + pad
    c.setFont(font_regular, INFO_TEXT_FS)
    if qn:
        c.drawString(qx, y, qn)

    c.setFont(font_bold, INFO_LABEL_FS)
    c.drawString(c4, y - INFO_LINE_H, label_date)

    dx = c4 + stringWidth(label_date, font_bold, INFO_LABEL_FS) + pad
    c.setFont(font_regular, INFO_TEXT_FS)
    if dt:
        c.drawString(dx, y - INFO_LINE_H, dt)

    y4_end = y - (2 * INFO_LINE_H) - 2

    # underline under the row (lighter like V2)
    y_bottom = min(y1_end, y2_end, y3_end, y4_end) - 8
    c.setStrokeColor(LIGHT_RULE)
    c.setLineWidth(INFO_RULE_W)
    c.line(x0, y_bottom, x1, y_bottom)
    c.setStrokeColor(colors.black)

    return y_bottom - INFO_TO_TITLE_GAP


# =========================
# Title + description
# =========================

def _draw_title_and_desc_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    data: ServiceQuoteData,
    font_regular: str,
    font_bold: str,
) -> float:
    x0 = _x0()

    who = _clean(data.company_name) or _clean(data.property_name) or _clean(data.client_name) or "Client"
    c.setFont(font_bold, TITLE_FS)
    c.drawString(x0, y_top, f"Service Quote for {who}")

    y = y_top - TITLE_FS - TITLE_GAP_BELOW

    desc = _clean(data.quote_description)
    if desc:
        c.setFont(font_regular, DESC_FS)
        max_w = _content_w(ps)
        for ln in _wrap_text(desc, font_regular, DESC_FS, max_w)[:2]:
            c.drawString(x0, y, ln)
            y -= 13
        y -= DESC_GAP_BELOW
    else:
        y -= 6

    return y


# =========================
# Items
# =========================

def _build_item_blocks(data: ServiceQuoteData) -> List[ItemBlock]:
    blocks: List[ItemBlock] = []
    for it in (data.items or []):
        title = _clean(it.name) or "(Item)"
        price = _money_str(it.price)

        bullets: List[str] = []
        for dl in _split_desc(it.description):
            dl = dl.lstrip("-").strip()
            if dl.startswith("•"):
                dl = dl[1:].strip()
            bullets.append(dl)

        blocks.append(ItemBlock(price=price, title=title, bullets=bullets))
    return blocks


def _draw_item_blocks_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    blocks: List[ItemBlock],
    y_top: float,
    font_regular: str,
    font_bold: str,
) -> float:
    x0 = _x0()
    x1 = _x1(ps)

    y = y_top
    for b in blocks:
        # gray bar
        c.setFillColor(ITEM_BAR_COLOR)
        c.rect(x0, y - ITEM_BAR_H, x1 - x0, ITEM_BAR_H, stroke=0, fill=1)

        # ✅ title + price vertically centered in the bar
        title_y = _vcenter_baseline(y, ITEM_BAR_H, ITEM_BAR_FS)
        c.setFillColor(colors.black)
        c.setFont(font_bold, ITEM_BAR_FS)
        c.drawString(x0 + 10, title_y, b.title)

        if b.price:
            c.setFont(font_bold, ITEM_PRICE_FS)
            c.drawRightString(x1 - 10, _vcenter_baseline(y, ITEM_BAR_H, ITEM_PRICE_FS), b.price)

        # bullets start just under bar
        y_b = (y - ITEM_BAR_H) - 10

        # ✅ bullets align vertically with consistent text start
        bullet_x = x0 + 30
        text_x = x0 + 44
        max_text_w = (x1 - text_x) - 10

        c.setFont(font_regular, ITEM_BULLET_FS)

        for raw in b.bullets:
            raw = _clean(raw)
            if not raw:
                continue

            wrapped = _wrap_text(raw, font_regular, ITEM_BULLET_FS, max_text_w)
            if not wrapped:
                continue

            # ✅ bigger bullet dot (drawn circle)
            c.setFillColor(colors.black)
            c.circle(bullet_x, y_b + BULLET_DOT_Y_NUDGE, BULLET_R, stroke=0, fill=1)
            c.setFillColor(colors.black)

            # first line
            c.drawString(text_x, y_b, wrapped[0])
            y_b -= ITEM_BULLET_LINE_H

            # continuation lines (no bullet)
            for cont in wrapped[1:]:
                c.drawString(text_x, y_b, cont)
                y_b -= ITEM_BULLET_LINE_H

        y = y_b - ITEM_BLOCK_GAP

    return y


# =========================
# Totals (right aligned, labels closer)
# =========================

def _draw_totals_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    data: ServiceQuoteData,
    font_regular: str,
    font_bold: str,
) -> float:
    x0 = _x0()
    x1 = _x1(ps)

    subtotal = _money_str(data.subtotal) if data.subtotal else ""
    tax = _money_str(data.tax) if data.tax else ""
    total = _money_str(data.total) if data.total else ""

    # top rule
    c.setStrokeColor(TOTAL_RULE_COLOR)
    c.setLineWidth(TOTAL_RULE_W)
    c.line(x0, y_top, x1, y_top)

    value_x = x1
    label_x = x1 - TOTAL_LABEL_PAD

    y = y_top - 18

    # Subtotal
    c.setFillColor(colors.black)
    c.setFont(font_regular, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y, "Subtotal")
    c.setFont(font_bold, TOTAL_VALUE_FS)
    c.drawRightString(value_x, y, subtotal)

    y -= 12
    c.line(x0, y, x1, y)

    # Tax
    y -= 14
    c.setFont(font_regular, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y, "Tax (13%)")
    c.setFont(font_bold, TOTAL_VALUE_FS)
    c.drawRightString(value_x, y, tax)

    y -= 12
    c.line(x0, y, x1, y)

    # Orange bar
    y -= (TOTAL_BAR_H - 6)
    c.setFillColor(TOTAL_ORANGE)
    c.rect(x0, y - 10, x1 - x0, TOTAL_BAR_H, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont(font_bold, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y + 3, "Quote Total")
    c.drawRightString(value_x - 2, y + 3, total)

    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)
    return y - 18


# =========================
# Page 2: Included / exclusions
# =========================

def _draw_included_exclusions_page_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    font_regular: str,
    font_bold: str,
) -> None:
    """
    ✅ Bigger blank header space
    ✅ Headings less bold (use regular font)
    ✅ Content aligned vertically like V2
    """
    x0 = _x0()
    x1 = _x1(ps)
    y = y_top

    # headings: less bold (regular)
    c.setFillColor(colors.black)
    c.setFont(font_regular, P2_TITLE_FS)
    c.drawString(x0, y, "Included in Quote")
    y -= P2_LINE_H

    # bullet item
    c.setFont(font_regular, P2_TEXT_FS)
    c.circle(x0 + 20, y + 4, BULLET_R, stroke=0, fill=1)
    c.drawString(x0 + 34, y, "All Parts & Labor")
    y -= (P2_LINE_H + 10)

    c.setFont(font_regular, P2_TITLE_FS)
    c.drawString(x0, y, "Specific Exclusions")
    y -= P2_LINE_H

    c.setFont(font_regular, P2_TEXT_FS)
    exclusions = [
        "Job to be completed during regular hours 08:00-16:30 Monday to Friday",
        "Pricing is subject to parts availability and all items being done concurrently",
    ]

    text_x = x0 + 34
    max_w = (x1 - text_x) - 10

    for ex in exclusions:
        lines = _wrap_text(ex, font_regular, P2_TEXT_FS, max_w)
        if not lines:
            continue

        c.circle(x0 + 20, y + 4, BULLET_R, stroke=0, fill=1)
        c.drawString(text_x, y, lines[0])
        y -= P2_LINE_H

        for cont in lines[1:]:
            c.drawString(text_x, y, cont)
            y -= P2_LINE_H


# =========================
# Main render
# =========================

def render_service_quote(template_pdf: Path, data: ServiceQuoteData) -> bytes:
    ps = _page_spec_from_template(template_pdf)
    font_regular, font_bold, logo_path = _register_brand_assets(template_pdf)

    blocks = _build_item_blocks(data)

    total_pages = 2
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(ps.w, ps.h))

    # ---------- Page 1 ----------
    y = _draw_header_v2(
        c,
        ps,
        page_no=1,
        total_pages=total_pages,
        logo_path=logo_path,
        font_regular=font_regular,
        font_bold=font_bold,
    )

    y = _draw_info_row_v2(c, ps, y_top=y, data=data, font_regular=font_regular, font_bold=font_bold)
    y = _draw_title_and_desc_v2(c, ps, y_top=y, data=data, font_regular=font_regular, font_bold=font_bold)

    y = _draw_item_blocks_v2(c, ps, blocks, y_top=y, font_regular=font_regular, font_bold=font_bold)

    # totals near bottom, but above footer
    y_totals_top = max(y, FOOTER_Y + 0.95 * inch)
    _draw_totals_v2(c, ps, y_top=y_totals_top, data=data, font_regular=font_regular, font_bold=font_bold)

    _draw_footer_v2(c, ps, page_no=1, total_pages=total_pages, font_regular=font_regular)

    c.showPage()

    # ---------- Page 2 ----------
    # NO HEADER on page 2
    y2 = ps.h - PAGE_MARGIN_T - P2_TOP_BLANK
    _draw_included_exclusions_page_v2(c, ps, y_top=y2, font_regular=font_regular, font_bold=font_bold)
    _draw_footer_v2(c, ps, page_no=2, total_pages=total_pages, font_regular=font_regular)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()