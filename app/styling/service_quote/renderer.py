# app/styling/service_quote/renderer.py
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

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
HEADER_LOGO_H = 0.48 * inch
HEADER_RULE_W = 2.6
HEADER_TEXT_FS = 8
HEADER_LINE_H = 11
HEADER_RULE_GAP = 18
HEADER_BOTTOM_GAP = 0.18 * inch

# Four-column info row
INFO_TOP_GAP = 0.18 * inch
INFO_COL_GAP = 0.30 * inch
INFO_LABEL_FS = 8
INFO_TEXT_FS = 8
INFO_LINE_H = 11
INFO_RULE_W = 0.9

# Extra gap between info underline and title
INFO_TO_TITLE_GAP = 0.55 * inch

# Title + description
TITLE_FS = 22
DESC_FS = 9
TITLE_GAP_BELOW = 0.16 * inch
DESC_GAP_BELOW = 0.18 * inch

# Items
ITEM_BAR_H = 0.32 * inch
ITEM_BAR_FS = 10
ITEM_PRICE_FS = 10
ITEM_BULLET_FS = 9
ITEM_BULLET_LINE_H = 13
ITEM_BAR_COLOR = colors.HexColor("#EEE8E6")
ITEM_LIST_GAP_TOP = 14          # space under bar before first bullet
ITEM_BLOCK_GAP = 10             # space between item blocks (after last bullet)

# Bullet dot
BULLET_R = 1.9  # points
BULLET_DOT_Y_NUDGE = 3.2

# Totals
TOTAL_LABEL_FS = 9
TOTAL_VALUE_FS = 9
TOTAL_RULE_W = 0.8
TOTAL_RULE_COLOR = colors.HexColor("#D9D1CE")
TOTAL_ORANGE = colors.HexColor("#D35B3A")
TOTAL_BAR_H = 0.36 * inch
TOTAL_LABEL_PAD = 85

# Footer
FOOTER_FS = 8
FOOTER_Y = 0.40 * inch

# Colors
LIGHT_RULE = colors.HexColor("#D9D1CE")
FOOTER_GRAY = colors.HexColor("#6F6A67")

# Included / exclusions section typography
P2_TOP_BLANK = 0.20 * inch     # gap before "Included in Quote" when starting a fresh page
P2_TITLE_FS = 12
P2_TEXT_FS = 11
P2_LINE_H = 18
P2_AFTER_INCLUDED_GAP = 10     # extra gap after "All Parts & Labor"

# Alignment
RIGHT_PAD = 10  # one shared right edge for ALL prices/totals

# Pagination tuning
CONTENT_BOTTOM = FOOTER_Y + 0.95 * inch   # don't draw content below this
CONTINUED_TOP_GAP = 0.25 * inch           # gap below header on continued pages

# Conservative space estimates (for pre-pagination decisions)
TOTALS_HEIGHT_EST = 1.25 * inch


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
# Header / footer
# =========================

def _draw_header_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    logo_path: Path | None,
    font_regular: str,
    font_bold: str,
) -> float:
    """
    Returns y just below underline (minus HEADER_BOTTOM_GAP).
    """
    x0 = _x0()
    x1 = _x1(ps)
    w = x1 - x0
    y_top = ps.h - PAGE_MARGIN_T

    col_w = (w - 3 * INFO_COL_GAP) / 4.0
    c1 = x0
    c2 = c1 + col_w + INFO_COL_GAP
    c3 = c2 + col_w + INFO_COL_GAP
    c4 = c3 + col_w + INFO_COL_GAP

    logo_x0 = c1
    addr_x0 = c3
    cont_x0 = c4

    text_h = 3 * HEADER_LINE_H
    header_block_h = max(text_h, HEADER_LOGO_H)

    y_rule = y_top - (header_block_h + HEADER_RULE_GAP)
    y_block_bottom = y_rule + HEADER_RULE_GAP

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
                y_block_bottom,
                width=lw,
                height=lh,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    base = y_block_bottom + 2

    c.setFont(font_bold, HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 2 * HEADER_LINE_H, "Mainline Fire Protection")
    c.setFont(font_regular, HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 1 * HEADER_LINE_H, "411 Bradwick Dr, Unit 12")
    c.drawString(addr_x0, base + 0 * HEADER_LINE_H, "Concord, ON, L4K 2P4 Canada")

    c.setFont(font_regular, HEADER_TEXT_FS)
    c.drawString(cont_x0, base + 2 * HEADER_LINE_H, "416-305-0704")
    c.drawString(cont_x0, base + 1 * HEADER_LINE_H, "contact@mainlinefire.com")
    c.drawString(cont_x0, base + 0 * HEADER_LINE_H, "MainlineFire.com")

    c.setLineWidth(HEADER_RULE_W)
    c.line(x0, y_rule, x1, y_rule)

    return y_rule - HEADER_BOTTOM_GAP


def _draw_footer_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    page_no: int,
    total_pages: int,
    font_regular: str
) -> None:
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
# First-page sections (info row, title/desc)
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

    label(c1, "Attn:")
    y1_end = text_lines_wrapped(c1, [data.client_name, data.client_phone, data.client_email])

    label(c2, "Company:")
    y2_end = text_lines_wrapped(c2, [data.company_name, data.company_address])

    label(c3, "Property:")
    y3_end = text_lines_wrapped(c3, [data.property_name, data.property_address])

    qn = _clean(data.quote_number)
    dt = _clean(data.quote_date)

    label_quote = "Quote #:"
    label_date = "Date:"
    pad = 4

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

    y_bottom = min(y1_end, y2_end, y3_end, y4_end) - 8
    c.setStrokeColor(LIGHT_RULE)
    c.setLineWidth(INFO_RULE_W)
    c.line(x0, y_bottom, x1, y_bottom)
    c.setStrokeColor(colors.black)

    return y_bottom - INFO_TO_TITLE_GAP


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
# Items (build, estimate, draw)
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


def _estimate_block_height(ps: PageSpec, b: ItemBlock, font_regular: str) -> float:
    x0 = _x0()
    x1 = _x1(ps)

    text_x = x0 + 28
    max_text_w = (x1 - text_x) - 10

    h = ITEM_BAR_H
    h += ITEM_LIST_GAP_TOP

    line_count = 0
    for raw in b.bullets:
        raw = _clean(raw)
        if not raw:
            continue
        wrapped = _wrap_text(raw, font_regular, ITEM_BULLET_FS, max_text_w)
        line_count += max(1, len(wrapped))

    if line_count > 0:
        h += line_count * ITEM_BULLET_LINE_H
    else:
        h += ITEM_BULLET_LINE_H * 0.6

    h += ITEM_BLOCK_GAP
    return float(h)


def _draw_item_block_at_y(
    c: canvas.Canvas,
    ps: PageSpec,
    b: ItemBlock,
    y: float,
    font_regular: str,
    font_bold: str,
) -> float:
    x0 = _x0()
    x1 = _x1(ps)

    c.setFillColor(ITEM_BAR_COLOR)
    c.rect(x0, y - ITEM_BAR_H, x1 - x0, ITEM_BAR_H, stroke=0, fill=1)

    title_y = _vcenter_baseline(y, ITEM_BAR_H, ITEM_BAR_FS)
    c.setFillColor(colors.black)
    c.setFont(font_bold, ITEM_BAR_FS)
    c.drawString(x0 + 10, title_y, b.title)

    if b.price:
        c.setFont(font_bold, ITEM_PRICE_FS)
        c.drawRightString(x1 - RIGHT_PAD, _vcenter_baseline(y, ITEM_BAR_H, ITEM_PRICE_FS), b.price)

    y_b = (y - ITEM_BAR_H) - ITEM_LIST_GAP_TOP
    bullet_x = x0 + 10
    text_x = x0 + 28
    max_text_w = (x1 - text_x) - 10

    c.setFont(font_regular, ITEM_BULLET_FS)

    for raw in b.bullets:
        raw = _clean(raw)
        if not raw:
            continue
        wrapped = _wrap_text(raw, font_regular, ITEM_BULLET_FS, max_text_w)
        if not wrapped:
            continue

        c.setFillColor(colors.black)
        c.circle(bullet_x, y_b + BULLET_DOT_Y_NUDGE, BULLET_R, stroke=0, fill=1)
        c.setFillColor(colors.black)

        c.drawString(text_x, y_b, wrapped[0])
        y_b -= ITEM_BULLET_LINE_H
        for cont in wrapped[1:]:
            c.drawString(text_x, y_b, cont)
            y_b -= ITEM_BULLET_LINE_H

    return y_b - ITEM_BLOCK_GAP


# =========================
# Totals
# =========================

def _draw_totals_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    data: ServiceQuoteData,
    font_regular: str,
    font_bold: str,
) -> float:
    """
    Draw totals starting at y_top, returns y cursor AFTER totals.
    """
    x0 = _x0()
    x1 = _x1(ps)

    subtotal = _money_str(data.subtotal) if data.subtotal else ""
    tax = _money_str(data.tax) if data.tax else ""
    total = _money_str(data.total) if data.total else ""

    c.setStrokeColor(TOTAL_RULE_COLOR)
    c.setLineWidth(TOTAL_RULE_W)
    c.line(x0, y_top, x1, y_top)

    value_x = x1 - RIGHT_PAD
    label_x = value_x - TOTAL_LABEL_PAD

    y = y_top - 18

    c.setFillColor(colors.black)
    c.setFont(font_regular, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y, "Subtotal")
    c.setFont(font_bold, TOTAL_VALUE_FS)
    c.drawRightString(value_x, y, subtotal)

    y -= 12
    c.line(x0, y, x1, y)

    y -= 14
    c.setFont(font_regular, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y, "Tax (13%)")
    c.setFont(font_bold, TOTAL_VALUE_FS)
    c.drawRightString(value_x, y, tax)

    y -= 12
    c.line(x0, y, x1, y)

    y -= (TOTAL_BAR_H - 6)
    c.setFillColor(TOTAL_ORANGE)
    c.rect(x0, y - 10, x1 - x0, TOTAL_BAR_H, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont(font_bold, TOTAL_LABEL_FS)
    c.drawRightString(label_x, y + 3, "Quote Total")
    c.drawRightString(value_x, y + 3, total)
    c.drawRightString(value_x - 0.35, y + 3, total)

    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    return y - 18


# =========================
# Included / exclusions section (can be appended after totals)
# =========================

def _included_exclusions_lines(font_regular: str, ps: PageSpec) -> Tuple[str, str, List[str], float]:
    """
    Returns (heading1, included_line, exclusions_lines, max_w)
    """
    x0 = _x0()
    x1 = _x1(ps)
    text_x = x0 + 16
    max_w = (x1 - text_x) - 10
    heading1 = "Included in Quote"
    included_line = "All Parts & Labor"
    exclusions = [
        "Job to be completed during regular hours 08:00-16:30 Monday to Friday",
        "Pricing is subject to parts availability and all items being done concurrently",
    ]
    return heading1, included_line, exclusions, max_w


def _estimate_included_exclusions_height(ps: PageSpec, font_regular: str) -> float:
    """
    Estimate vertical height needed for the Included/Exclusions section.
    """
    _, _, exclusions, max_w = _included_exclusions_lines(font_regular, ps)

    h = 0.0
    # "Included in Quote" heading
    h += P2_LINE_H
    # included bullet line
    h += P2_LINE_H
    # extra gap after included bullet
    h += P2_AFTER_INCLUDED_GAP

    # "Specific Exclusions" heading
    h += P2_LINE_H

    # each exclusion: wrapped lines
    for ex in exclusions:
        lines = _wrap_text(ex, font_regular, P2_TEXT_FS, max_w)
        h += max(1, len(lines)) * P2_LINE_H

    return float(h)


def _draw_included_exclusions_section_v2(
    c: canvas.Canvas,
    ps: PageSpec,
    y_top: float,
    font_regular: str,
) -> float:
    """
    Draw the Included/Exclusions section starting at y_top.
    Returns new y cursor after drawing.
    """
    x0 = _x0()
    x1 = _x1(ps)
    y = y_top

    bullet_x = x0
    text_x = x0 + 16
    max_w = (x1 - text_x) - 10

    c.setFillColor(colors.black)

    # Heading 1
    c.setFont(font_regular, P2_TITLE_FS)
    c.drawString(x0, y, "Included in Quote")
    y -= P2_LINE_H

    # Included bullet
    c.setFont(font_regular, P2_TEXT_FS)
    c.circle(bullet_x, y + 4, BULLET_R, stroke=0, fill=1)
    c.drawString(text_x, y, "All Parts & Labor")
    y -= P2_LINE_H

    y -= P2_AFTER_INCLUDED_GAP

    # Heading 2
    c.setFont(font_regular, P2_TITLE_FS)
    c.drawString(x0, y, "Specific Exclusions")
    y -= P2_LINE_H

    exclusions = [
        "Job to be completed during regular hours 08:00-16:30 Monday to Friday",
        "Pricing is subject to parts availability and all items being done concurrently",
    ]

    c.setFont(font_regular, P2_TEXT_FS)
    for ex in exclusions:
        lines = _wrap_text(ex, font_regular, P2_TEXT_FS, max_w)
        if not lines:
            continue

        c.circle(bullet_x, y + 4, BULLET_R, stroke=0, fill=1)
        c.drawString(text_x, y, lines[0])
        y -= P2_LINE_H

        for cont in lines[1:]:
            c.drawString(text_x, y, cont)
            y -= P2_LINE_H

    return y


# =========================
# Pagination helpers (no drawing)
# =========================

def _calc_header_bottom_y(ps: PageSpec) -> float:
    y_top = ps.h - PAGE_MARGIN_T
    text_h = 3 * HEADER_LINE_H
    header_block_h = max(text_h, HEADER_LOGO_H)
    y_rule = y_top - (header_block_h + HEADER_RULE_GAP)
    return y_rule - HEADER_BOTTOM_GAP


def _calc_first_page_items_y(ps: PageSpec, data: ServiceQuoteData, font_regular: str) -> float:
    """
    Compute y where items start on page 1 (after header + info + title + desc).
    """
    x0 = _x0()
    x1 = _x1(ps)
    w = x1 - x0
    col_w = (w - 3 * INFO_COL_GAP) / 4.0

    header_bottom = _calc_header_bottom_y(ps)

    # info row
    y = header_bottom - INFO_TOP_GAP
    max_w = col_w - 6

    def wrapped_lines_count(lines: List[str]) -> int:
        cnt = 0
        for raw in lines:
            raw = _clean(raw)
            if not raw:
                continue
            cnt += len(_wrap_text(raw, font_regular, INFO_TEXT_FS, max_w))
        return cnt

    attn_lines = wrapped_lines_count([data.client_name, data.client_phone, data.client_email])
    comp_lines = wrapped_lines_count([data.company_name, data.company_address])
    prop_lines = wrapped_lines_count([data.property_name, data.property_address])

    def col_end(lines_count: int) -> float:
        yy = y - INFO_LINE_H
        yy -= lines_count * INFO_LINE_H
        return yy

    y1_end = col_end(attn_lines)
    y2_end = col_end(comp_lines)
    y3_end = col_end(prop_lines)
    y4_end = y - (2 * INFO_LINE_H) - 2

    y_bottom = min(y1_end, y2_end, y3_end, y4_end) - 8
    y_after_info = y_bottom - INFO_TO_TITLE_GAP

    # title + desc
    y_title_top = y_after_info
    y_after_title = y_title_top - TITLE_FS - TITLE_GAP_BELOW

    desc = _clean(data.quote_description)
    if desc:
        max_w_desc = _content_w(ps)
        desc_lines = _wrap_text(desc, font_regular, DESC_FS, max_w_desc)[:2]
        y_after_desc = y_after_title - (len(desc_lines) * 13) - DESC_GAP_BELOW
        return y_after_desc

    return y_after_title - 6


def _paginate_item_blocks(
    ps: PageSpec,
    blocks: List[ItemBlock],
    first_page_y_start: float,
    continued_page_y_start: float,
    font_regular: str,
) -> Tuple[List[List[ItemBlock]], List[float]]:
    pages: List[List[ItemBlock]] = []
    end_ys: List[float] = []

    cur_page: List[ItemBlock] = []
    y = first_page_y_start

    for b in blocks:
        need_h = _estimate_block_height(ps, b, font_regular)

        if (y - need_h) < CONTENT_BOTTOM and cur_page:
            pages.append(cur_page)
            end_ys.append(y)
            cur_page = []
            y = continued_page_y_start

        cur_page.append(b)
        y -= need_h

    if cur_page or not pages:
        pages.append(cur_page)
        end_ys.append(y)

    return pages, end_ys


# =========================
# Main render
# =========================

def render_service_quote(template_pdf: Path, data: ServiceQuoteData) -> bytes:
    ps = _page_spec_from_template(template_pdf)
    font_regular, font_bold, logo_path = _register_brand_assets(template_pdf)

    blocks = _build_item_blocks(data)

    # --- Pre-calc y starts ---
    first_items_y = _calc_first_page_items_y(ps, data, font_regular)
    continued_content_y = _calc_header_bottom_y(ps) - CONTINUED_TOP_GAP  # top content start under header for continued pages

    item_pages, _ = _paginate_item_blocks(
        ps,
        blocks,
        first_page_y_start=first_items_y,
        continued_page_y_start=continued_content_y,
        font_regular=font_regular,
    )

    # --- Pre-check: do totals fit on last items page? ---
    totals_need_own_page = False
    if item_pages:
        y_est = continued_content_y if (len(item_pages) > 1) else first_items_y
        for b in item_pages[-1]:
            y_est -= _estimate_block_height(ps, b, font_regular)

        if (y_est - TOTALS_HEIGHT_EST) < CONTENT_BOTTOM:
            totals_need_own_page = True

    included_h_est = _estimate_included_exclusions_height(ps, font_regular)

    # --- Pre-check: does Included/Exclusions fit RIGHT AFTER totals on the same page? ---
    included_need_own_page = False
    if totals_need_own_page:
        # totals page starts at continued_content_y, then we go down by totals height
        y_after_totals_est = continued_content_y - TOTALS_HEIGHT_EST
        # we also want a tiny gap before starting the section
        y_after_totals_est -= P2_TOP_BLANK
        if (y_after_totals_est - included_h_est) < CONTENT_BOTTOM:
            included_need_own_page = True
    else:
        # totals start at y_est (right after last item)
        y_after_totals_est = y_est - TOTALS_HEIGHT_EST
        y_after_totals_est -= P2_TOP_BLANK
        if (y_after_totals_est - included_h_est) < CONTENT_BOTTOM:
            included_need_own_page = True

    total_pages = (
        len(item_pages)
        + (1 if totals_need_own_page else 0)
        + (1 if included_need_own_page else 0)
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(ps.w, ps.h))

    page_no = 1

    # ---- Draw item pages ----
    for idx, page_blocks in enumerate(item_pages):
        y = _draw_header_v2(c, ps, logo_path=logo_path, font_regular=font_regular, font_bold=font_bold)

        if idx == 0:
            y = _draw_info_row_v2(c, ps, y_top=y, data=data, font_regular=font_regular, font_bold=font_bold)
            y = _draw_title_and_desc_v2(c, ps, y_top=y, data=data, font_regular=font_regular, font_bold=font_bold)
        else:
            y = y - CONTINUED_TOP_GAP

        cur_y = y

        for b in page_blocks:
            need_h = _estimate_block_height(ps, b, font_regular)
            if (cur_y - need_h) < CONTENT_BOTTOM:
                _draw_footer_v2(c, ps, page_no=page_no, total_pages=total_pages, font_regular=font_regular)
                c.showPage()
                page_no += 1

                cur_y = _draw_header_v2(c, ps, logo_path=logo_path, font_regular=font_regular, font_bold=font_bold)
                cur_y = cur_y - CONTINUED_TOP_GAP

            cur_y = _draw_item_block_at_y(c, ps, b, y=cur_y, font_regular=font_regular, font_bold=font_bold)

        is_last_items_page = (idx == len(item_pages) - 1)

        if is_last_items_page and (not totals_need_own_page):
            # Totals right after last item
            # Safety: if totals actually don't fit, push to next page
            if (cur_y - TOTALS_HEIGHT_EST) < CONTENT_BOTTOM:
                _draw_footer_v2(c, ps, page_no=page_no, total_pages=total_pages, font_regular=font_regular)
                c.showPage()
                page_no += 1

                cur_y = _draw_header_v2(c, ps, logo_path=logo_path, font_regular=font_regular, font_bold=font_bold)
                cur_y = cur_y - CONTINUED_TOP_GAP
                # now totals are on "totals page"
                totals_need_own_page = True
                included_need_own_page = included_need_own_page or True  # conservative
                # NOTE: total_pages precomputed; this safety case is rare if estimates are sane.

            cur_y = _draw_totals_v2(c, ps, y_top=cur_y, data=data, font_regular=font_regular, font_bold=font_bold)

            # ✅ NEW: Put Included/Exclusions right after Quote Total if it fits
            y_section_top = cur_y - P2_TOP_BLANK
            if not included_need_own_page and (y_section_top - included_h_est) >= CONTENT_BOTTOM:
                _draw_included_exclusions_section_v2(c, ps, y_top=y_section_top, font_regular=font_regular)

        _draw_footer_v2(c, ps, page_no=page_no, total_pages=total_pages, font_regular=font_regular)
        c.showPage()
        page_no += 1

    # ---- Totals page (if needed) ----
    totals_page_cursor_after = None
    if totals_need_own_page:
        y = _draw_header_v2(c, ps, logo_path=logo_path, font_regular=font_regular, font_bold=font_bold)
        y = y - CONTINUED_TOP_GAP  # top content start
        totals_page_cursor_after = _draw_totals_v2(c, ps, y_top=y, data=data, font_regular=font_regular, font_bold=font_bold)

        # Try Included/Exclusions right after totals on this totals page (if allowed)
        y_section_top = totals_page_cursor_after - P2_TOP_BLANK
        if not included_need_own_page and (y_section_top - included_h_est) >= CONTENT_BOTTOM:
            _draw_included_exclusions_section_v2(c, ps, y_top=y_section_top, font_regular=font_regular)

        _draw_footer_v2(c, ps, page_no=page_no, total_pages=total_pages, font_regular=font_regular)
        c.showPage()
        page_no += 1

    # ---- Included/Exclusions page (only if it did NOT fit after totals) ----
    if included_need_own_page:
        y = _draw_header_v2(c, ps, logo_path=logo_path, font_regular=font_regular, font_bold=font_bold)
        y = y - CONTINUED_TOP_GAP
        y2 = y - P2_TOP_BLANK
        _draw_included_exclusions_section_v2(c, ps, y_top=y2, font_regular=font_regular)

        _draw_footer_v2(c, ps, page_no=page_no, total_pages=total_pages, font_regular=font_regular)
        c.showPage()
        page_no += 1

    c.save()
    buf.seek(0)
    return buf.getvalue()