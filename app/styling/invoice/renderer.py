# app/styling/invoice/renderer.py
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader

# Footer stamping
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

DEFAULT_LOGO = (
    Path(__file__).resolve().parents[3]
    / "templates"
    / "email-assets"
    / "Mainline-Primary-Logo-Black.png"
)

PAGE_W, PAGE_H = letter

# Match Service Quote margins
M_L = 0.60 * inch
M_R = 0.60 * inch
M_T = 0.55 * inch
M_B = 0.55 * inch

FS = 9
FS_SM = 8
FS_XS = 7

# Table sizing
ROW_LINE_H = 10
ROW_PAD_Y = 8
TABLE_HDR_H = 18

# Header constants
HEADER_LOGO_H = 0.48 * inch
HEADER_RULE_W = 2.6
HEADER_TEXT_FS = 8
HEADER_LINE_H = 11
HEADER_RULE_GAP = 18
HEADER_BOTTOM_GAP = 0.18 * inch
INFO_COL_GAP = 0.30 * inch

# Footer
FOOTER_GREY = colors.HexColor("#6F6F6F")

# Colors
BLACK = colors.black
WHITE = colors.white
LIGHT_RULE = colors.HexColor("#D9D1CE")
GREY_TOTAL = colors.HexColor("#E6E6E6")
ORANGE = colors.HexColor("#D35B3A")


# ---------------- Helpers ----------------
def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _money(v: Any) -> str:
    if v is None or v == "":
        return "$0.00"
    try:
        n = float(str(v).replace("$", "").replace(",", "").strip())
        return f"${n:,.2f}"
    except Exception:
        return _s(v)


def _to_float(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(str(v).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _display_row_date(v: Any) -> str:
    s = _s(v).strip()
    if not s:
        return ""

    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            dt = datetime.strptime(s, "%Y-%m-%d")
            return dt.strftime("%b %d, %Y")
    except Exception:
        pass

    return s


def _set_font(c: canvas.Canvas, fs: int, bold: bool = False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", fs)


def _draw_text(
    c: canvas.Canvas,
    x: float,
    y: float,
    s: str,
    fs: int = FS,
    bold: bool = False,
    color=BLACK,
):
    _set_font(c, fs, bold)
    c.setFillColor(color)
    c.drawString(x, y, s or "")
    c.setFillColor(BLACK)


def _draw_right(
    c: canvas.Canvas,
    x_right: float,
    y: float,
    s: str,
    fs: int = FS,
    bold: bool = False,
    color=BLACK,
):
    _set_font(c, fs, bold)
    c.setFillColor(color)
    w = stringWidth(s or "", c._fontname, fs)
    c.drawString(x_right - w, y, s or "")
    c.setFillColor(BLACK)


def _draw_center(
    c: canvas.Canvas,
    x_left: float,
    w: float,
    y: float,
    s: str,
    fs: int = FS,
    bold: bool = False,
    color=BLACK,
):
    _set_font(c, fs, bold)
    c.setFillColor(color)
    tw = stringWidth(s or "", c._fontname, fs)
    c.drawString(x_left + (w - tw) / 2.0, y, s or "")
    c.setFillColor(BLACK)


def _tokenize_for_wrap(text: str) -> List[str]:
    """
    Split text into tokens while preserving common separators so long values like:
    - emails
    - item codes
    - WO numbers
    - slash-separated references
    can wrap naturally.

    Example:
      abc-def/test@example.com
    becomes tokens that can break at -, /, @, ., _
    """
    if not text:
        return []

    raw_parts = re.split(r"(\s+)", text)
    tokens: List[str] = []

    for part in raw_parts:
        if not part:
            continue

        if part.isspace():
            tokens.append(part)
            continue

        subparts = re.split(r"([/@._\-])", part)
        for sp in subparts:
            if sp:
                tokens.append(sp)

    return tokens


def _wrap_lines(text: str, font: str, fs: int, max_w: float) -> List[str]:
    """
    Wrap text safely, including long tokens with no spaces.
    Falls back to character-level wrapping when a single token is still too wide.
    """
    text = (text or "").strip()
    if not text:
        return [""]

    tokens = _tokenize_for_wrap(text)
    if not tokens:
        return [""]

    lines: List[str] = []
    cur = ""

    def flush():
        nonlocal cur
        if cur:
            lines.append(cur.strip())
            cur = ""

    for tok in tokens:
        trial = (cur + tok) if cur else tok

        if stringWidth(trial, font, fs) <= max_w:
            cur = trial
            continue

        if cur:
            flush()

        # token itself too wide -> hard-wrap character by character
        if stringWidth(tok, font, fs) > max_w:
            piece = ""
            for ch in tok:
                trial_piece = piece + ch
                if piece and stringWidth(trial_piece, font, fs) > max_w:
                    lines.append(piece)
                    piece = ch
                else:
                    piece = trial_piece
            cur = piece
        else:
            cur = tok

    flush()
    return lines or [""]


def _wrap_paragraph_lines(text: str, fs: int, max_w: float, bold: bool = False) -> List[str]:
    font = "Helvetica-Bold" if bold else "Helvetica"
    out: List[str] = []
    for para in (text or "").split("\n"):
        para = para.strip()
        if not para:
            out.append("")
            continue
        out.extend(_wrap_lines(para, font, fs, max_w))
    return out


def _wrap_text_to_width(text: str, fs: int, max_w: float, bold: bool = False) -> List[str]:
    return _wrap_paragraph_lines(text or "", fs=fs, max_w=max_w, bold=bold)


def _hr(c: canvas.Canvas, x0: float, x1: float, y: float, lw: float = 1, col=BLACK):
    c.setLineWidth(lw)
    c.setStrokeColor(col)
    c.line(x0, y, x1, y)
    c.setStrokeColor(BLACK)


def _rect_fill(c: canvas.Canvas, x: float, y: float, w: float, h: float, col):
    c.setFillColor(col)
    c.rect(x, y, w, h, stroke=0, fill=1)
    c.setFillColor(BLACK)


def _vcenter_baseline(row_top: float, row_h: float, font_size: float) -> float:
    return row_top - (row_h / 2.0) - (font_size * 0.35)


def _compute_row_h(line_count: int) -> float:
    core = max(1, line_count) * ROW_LINE_H
    return max(ROW_LINE_H + ROW_PAD_Y, core + ROW_PAD_Y)


def _normalize_property_address(lines: List[str]) -> List[str]:
    raw = [str(x).strip() for x in (lines or []) if str(x).strip()]
    has_ca = any(ln.upper() == "CA" for ln in raw)
    cleaned = [ln for ln in raw if ln.upper() != "CA"]
    if has_ca and cleaned:
        last = cleaned[-1]
        if not last.upper().endswith(" CA"):
            cleaned[-1] = f"{last} CA"
    return cleaned


def _draw_multiline_block(
    c: canvas.Canvas,
    x: float,
    y_top: float,
    lines: List[str],
    fs: int = FS_XS,
    bold_first: bool = False,
    line_gap: float = 11,
    color=BLACK,
) -> float:
    y = y_top
    for i, line in enumerate(lines):
        is_bold = bold_first and i == 0
        _draw_text(c, x, y, line, fs=fs, bold=is_bold, color=color)
        y -= line_gap
    return y


def _draw_text_inline_segments(
    c: canvas.Canvas,
    x: float,
    y: float,
    segments: List[Tuple[str, bool]],
    fs: int = FS_XS,
    color=BLACK,
):
    cur_x = x
    for text, bold in segments:
        _set_font(c, fs, bold)
        c.setFillColor(color)
        c.drawString(cur_x, y, text)
        cur_x += stringWidth(text, c._fontname, fs)
    c.setFillColor(BLACK)


def _draw_wrapped_cell_left(
    c: canvas.Canvas,
    x_left: float,
    row_top: float,
    row_h: float,
    lines: List[str],
    fs: int = FS_XS,
):
    base = _vcenter_baseline(row_top, row_h, fs)
    n = max(1, len(lines))
    start_y = base + ((n - 1) * ROW_LINE_H) / 2.0
    yy = start_y
    for ln in (lines or [""]):
        _draw_text(c, x_left + 4, yy, ln, fs=fs)
        yy -= ROW_LINE_H


def _draw_wrapped_cell_top(
    c: canvas.Canvas,
    x_left: float,
    row_top: float,
    lines: List[str],
    fs: int = FS_XS,
    top_pad: float = 11,
):
    yy = row_top - top_pad
    for ln in (lines or [""]):
        _draw_text(c, x_left + 4, yy, ln, fs=fs)
        yy -= ROW_LINE_H


def _draw_summary_block(
    c: canvas.Canvas,
    x0: float,
    x1: float,
    y: float,
    summary_text: str,
) -> float:
    if not (summary_text or "").strip():
        return y

    _draw_text(c, x0, y, "Invoice Summary", fs=FS_SM, bold=True)
    y -= 14

    text_w = x1 - x0
    wrapped_lines: List[str] = []

    for raw_line in (summary_text or "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            wrapped_lines.append("")
            continue

        wrapped = _wrap_lines(raw_line, "Helvetica", FS_XS, text_w - 8)
        wrapped_lines.extend(wrapped if wrapped else [""])

    line_gap = 11
    for line in wrapped_lines:
        if line == "":
            y -= 6
        else:
            _draw_text(c, x0, y, line, fs=FS_XS)
            y -= line_gap

    y -= 6
    _hr(c, x0, x1, y, lw=0.9, col=LIGHT_RULE)
    y -= 18

    return y


def _draw_header_v2_invoice(c: canvas.Canvas, logo_path: str | None) -> float:
    x0 = M_L
    x1 = PAGE_W - M_R
    w = x1 - x0
    y_top = PAGE_H - M_T

    col_w = (w - 3 * INFO_COL_GAP) / 4.0
    c1 = x0
    c3 = x0 + 2 * (col_w + INFO_COL_GAP)
    c4 = x0 + 3 * (col_w + INFO_COL_GAP)

    logo_x0 = c1
    addr_x0 = c3
    cont_x0 = c4

    text_h = 3 * HEADER_LINE_H
    header_block_h = max(text_h, HEADER_LOGO_H)

    y_block_bottom = y_top - header_block_h
    y_rule = y_block_bottom - HEADER_RULE_GAP

    if logo_path:
        try:
            p = Path(logo_path)
            logger.info("Invoice logo path: %s exists=%s", p, p.exists())
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            scale = float(HEADER_LOGO_H) / float(ih) if ih else 1.0
            lw = iw * scale
            lh = ih * scale
            c.drawImage(img, logo_x0, y_block_bottom, width=lw, height=lh, mask="auto")
        except Exception:
            logger.exception("Failed to draw logo. logo_path=%r", logo_path)

    base = y_block_bottom + 2
    c.setFont("Helvetica-Bold", HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 2 * HEADER_LINE_H, "Mainline Fire Protection")
    c.setFont("Helvetica", HEADER_TEXT_FS)
    c.drawString(addr_x0, base + 1 * HEADER_LINE_H, "411 Bradwick Dr, Unit 12")
    c.drawString(addr_x0, base + 0 * HEADER_LINE_H, "Concord, ON, L4K 2P4 Canada")

    c.setFont("Helvetica", HEADER_TEXT_FS)
    c.drawString(cont_x0, base + 2 * HEADER_LINE_H, "416-305-0704")
    c.drawString(cont_x0, base + 1 * HEADER_LINE_H, "contact@mainlinefire.com")
    c.drawString(cont_x0, base + 0 * HEADER_LINE_H, "MainlineFire.com")

    c.setLineWidth(HEADER_RULE_W)
    c.setStrokeColor(BLACK)
    c.line(x0, y_rule, x1, y_rule)
    c.setStrokeColor(BLACK)

    return y_rule - HEADER_BOTTOM_GAP


# ---------------- Footer stamping ----------------
def _make_footer_overlay(page_num: int, page_count: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    footer_y = M_B * 0.55
    _draw_text(
        c,
        M_L,
        footer_y,
        "Thank you for choosing Mainline Fire Protection!",
        fs=FS_XS,
        color=FOOTER_GREY,
    )
    _draw_right(
        c,
        PAGE_W - M_R,
        footer_y,
        f"Page {page_num} of {page_count}",
        fs=FS_XS,
        color=FOOTER_GREY,
    )
    c.save()
    return buf.getvalue()


def _stamp_footer(pdf_bytes: bytes) -> bytes:
    r = PdfReader(io.BytesIO(pdf_bytes))
    w = PdfWriter()
    n = len(r.pages)

    for i, page in enumerate(r.pages, start=1):
        overlay_pdf = PdfReader(io.BytesIO(_make_footer_overlay(i, n)))
        overlay_page: PageObject = overlay_pdf.pages[0]
        page.merge_page(overlay_page)
        w.add_page(page)

    out = io.BytesIO()
    w.write(out)
    return out.getvalue()

# ------------------- Make PAID stamp --------------------
def _make_paid_overlay() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # Center of page
    cx = PAGE_W / 2
    cy = PAGE_H / 2

    c.saveState()

    # Move to center and rotate
    c.translate(cx, cy)
    c.rotate(35)

    # Use the same orange as Total
    c.setFillColor(ORANGE)

    # Make it watermark-like
    try:
        c.setFillAlpha(0.30)
    except Exception:
        # Some environments/reportlab builds may not support alpha.
        # If so, it will still render in orange, just without transparency.
        pass

    # Slightly smaller and better centered visually
    c.setFont("Helvetica-Bold", 96)
    c.drawCentredString(0, -10, "PAID")

    c.restoreState()
    c.save()
    return buf.getvalue()


def _stamp_paid(pdf_bytes: bytes) -> bytes:
    r = PdfReader(io.BytesIO(pdf_bytes))
    w = PdfWriter()

    overlay_pdf = PdfReader(io.BytesIO(_make_paid_overlay()))
    overlay_page: PageObject = overlay_pdf.pages[0]

    for page in r.pages:
        page.merge_page(overlay_page)
        w.add_page(page)

    out = io.BytesIO()
    w.write(out)
    return out.getvalue()

# ---------------- Renderer ----------------
def render_invoice_styled_draft(normalized: Dict[str, Any], logo_path: str | None = None) -> bytes:
    if not logo_path:
        logo_path = str(DEFAULT_LOGO)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    x0 = M_L
    x1 = PAGE_W - M_R
    content_w = x1 - x0

    # Respect UI hide flags for PDF section rendering only.
    # Totals below still use normalized subtotal/tax/total values,
    # so hiding a section does NOT change totals.
    hide_labor = _to_bool(normalized.get("hide_labor"))
    hide_parts = _to_bool(normalized.get("hide_parts"))

    # ===== Header =====
    y = _draw_header_v2_invoice(c, logo_path=logo_path)
    y -= 0.12 * inch

    # ===== Bill To + Invoice meta =====
    _draw_text(c, x0, y, "Bill To", fs=FS_SM, bold=True)
    y_left = y - 12

    bill_name = _s(normalized.get("billClient_name"))
    bill_lines = normalized.get("billClient_address_lines") or []

    bill_phone = _s(
        normalized.get("billClient_phone")
        or normalized.get("client_phone")
        or normalized.get("customer_phone")
    ).strip()
    bill_email = _s(
        normalized.get("billClient_email")
        or normalized.get("client_email")
        or normalized.get("customer_email")
    ).strip()

    right_col_x = x0 + content_w * 0.58

    meta_x = right_col_x
    bill_contact_x = x0 + content_w * 0.31

    bill_left_w = (bill_contact_x - x0) - 12
    bill_right_w = (meta_x - bill_contact_x) - 14

    left_lines: List[str] = []
    left_lines.extend(_wrap_text_to_width(bill_name, fs=FS_XS, max_w=bill_left_w))
    for ln in bill_lines[:4]:
        left_lines.extend(_wrap_text_to_width(_s(ln), fs=FS_XS, max_w=bill_left_w))

    right_lines: List[str] = []
    if bill_phone:
        right_lines.extend(_wrap_text_to_width(bill_phone, fs=FS_XS, max_w=bill_right_w))
    if bill_email:
        right_lines.extend(_wrap_text_to_width(bill_email, fs=FS_XS, max_w=bill_right_w))

    _draw_multiline_block(c, x0, y_left, left_lines or [""], fs=FS_XS, line_gap=11)
    _draw_multiline_block(c, bill_contact_x, y_left, right_lines or [""], fs=FS_XS, line_gap=11)

    block_lines = max(len(left_lines or [""]), len(right_lines or [""]))

    # Right side meta
    meta_y = y

    inv_no = _s(normalized.get("invoice_number"))
    issued = _s(normalized.get("issued_date"))
    due = _s(normalized.get("due_date"))
    job = _s(normalized.get("job_number"))
    po = _s(normalized.get("po_number"))
    total_due = _money(normalized.get("total"))

    _draw_text(c, meta_x, meta_y - 2, f"Invoice # {inv_no}", fs=12, bold=True)
    _draw_right(c, x1, meta_y - 2, issued, fs=FS_XS)

    meta_y -= 16
    _draw_text(c, meta_x, meta_y, "Job Number", fs=FS_XS)
    _draw_right(c, x1, meta_y, job, fs=FS_XS)

    meta_y -= 12
    _draw_text(c, meta_x, meta_y, "PO Number", fs=FS_XS)
    _draw_right(c, x1, meta_y, po, fs=FS_XS)

    meta_y -= 18
    _draw_text(c, meta_x, meta_y, "Total Due", fs=FS_SM, bold=True)
    _draw_right(c, x1, meta_y, total_due, fs=FS_SM, bold=True)

    meta_y -= 14
    _draw_text(c, meta_x, meta_y, "Due Date", fs=FS_XS)
    _draw_right(c, x1, meta_y, due, fs=FS_XS)

    y = min(y_left - (block_lines * 11), meta_y) - 14
    _hr(c, x0, x1, y, lw=0.9, col=LIGHT_RULE)
    y -= 16

    # ===== Customer / Property grid =====
    left_x = x0
    mid_x = x0 + content_w * 0.30
    right_x = right_col_x

    col_gap = 10
    left_w = (mid_x - left_x) - col_gap
    mid_w = (right_x - mid_x) - col_gap
    right_w = x1 - right_x

    # Row 1
    _draw_text(c, left_x, y, "Customer Name:", fs=FS_XS, bold=True)
    _draw_text(c, mid_x, y, "Property Name:", fs=FS_XS, bold=True)
    _draw_text(c, right_x, y, "Property Address:", fs=FS_XS, bold=True)

    row1_top = y - 11

    customer_lines = _wrap_text_to_width(_s(normalized.get("customer_name")), fs=FS_XS, max_w=left_w)
    property_name_lines = _wrap_text_to_width(_s(normalized.get("property_name")), fs=FS_XS, max_w=mid_w)

    prop_addr_raw = _normalize_property_address(normalized.get("property_address_lines") or [])
    property_addr_lines: List[str] = []
    for ln in prop_addr_raw[:4]:
        property_addr_lines.extend(_wrap_text_to_width(_s(ln), fs=FS_XS, max_w=right_w))

    _draw_multiline_block(c, left_x, row1_top, customer_lines or [""], fs=FS_XS, line_gap=11)
    _draw_multiline_block(c, mid_x, row1_top, property_name_lines or [""], fs=FS_XS, line_gap=11)
    _draw_multiline_block(c, right_x, row1_top, property_addr_lines or [""], fs=FS_XS, line_gap=11)

    row1_lines = max(
        len(customer_lines or [""]),
        len(property_name_lines or [""]),
        len(property_addr_lines or [""]),
    )
    y = row1_top - (row1_lines * 11) - 10

    # Row 2
    _draw_text(c, left_x, y, "Authorized by:", fs=FS_XS, bold=True)
    _draw_text(c, mid_x, y, "Customer WO:", fs=FS_XS, bold=True)
    _draw_text(c, right_x, y, "NTE:", fs=FS_XS, bold=True)

    row2_top = y - 11

    authorized_lines = _wrap_text_to_width(_s(normalized.get("authorized_by")), fs=FS_XS, max_w=left_w)
    wo_lines = _wrap_text_to_width(_s(normalized.get("customerProvidedWONumber")), fs=FS_XS, max_w=mid_w)
    nte_lines = _wrap_text_to_width(_s(normalized.get("nte")), fs=FS_XS, max_w=right_w)

    _draw_multiline_block(c, left_x, row2_top, authorized_lines or [""], fs=FS_XS, line_gap=11)
    _draw_multiline_block(c, mid_x, row2_top, wo_lines or [""], fs=FS_XS, line_gap=11)
    _draw_multiline_block(c, right_x, row2_top, nte_lines or [""], fs=FS_XS, line_gap=11)

    row2_lines = max(
        len(authorized_lines or [""]),
        len(wo_lines or [""]),
        len(nte_lines or [""]),
    )
    y = row2_top - (row2_lines * 11) - 10

    _hr(c, x0, x1, y, lw=0.9, col=LIGHT_RULE)
    y -= 18

    # ===== Pagination =====
    def new_page():
        nonlocal y
        c.showPage()
        y = _draw_header_v2_invoice(c, logo_path=logo_path) - 0.20 * inch

    def ensure_space(need_h: float):
        nonlocal y
        if y - need_h < (M_B + 0.35 * inch):
            new_page()

    # ===== Invoice Summary =====
    summary_text = _s(normalized.get("invoice_summary")).strip()
    if summary_text:
        est_lines: List[str] = []
        for raw_line in summary_text.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                est_lines.append("")
                continue
            est_lines.extend(_wrap_lines(raw_line, "Helvetica", FS_XS, content_w - 8))

        est_h = 14 + (len(est_lines) * 11) + 20
        ensure_space(est_h)
        y = _draw_summary_block(c, x0, x1, y, summary_text)

    # ===== Columns =====
    def build_cols_shared_fixed() -> tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        date_w = 0.82 * inch
        name_w = 1.05 * inch
        code_w = 0.95 * inch
        taxable_w = 0.60 * inch
        qty_w = 0.50 * inch
        unit_w = 0.78 * inch
        money_w = 0.82 * inch

        fixed_used = date_w + name_w + code_w + taxable_w + qty_w + unit_w + money_w
        min_desc = 1.90 * inch
        desc_w = content_w - fixed_used

        if desc_w < min_desc:
            deficit = min_desc - desc_w
            shrink_name = min(0.15 * inch, deficit)
            name_w -= shrink_name
            fixed_used = date_w + name_w + code_w + taxable_w + qty_w + unit_w + money_w
            desc_w = content_w - fixed_used

        labor_cols = [
            ("Date", date_w),
            ("Labor Name", name_w + code_w),
            ("Description", desc_w),
            ("Taxable", taxable_w),
            ("Hours", qty_w),
            ("Rate", unit_w),
            ("Price", money_w),
        ]

        parts_cols = [
            ("Date", date_w),
            ("Item Name", name_w),
            ("Item Code", code_w),
            ("Description", desc_w),
            ("Taxable", taxable_w),
            ("Qty", qty_w),
            ("Unit Price", unit_w),
            ("Price", money_w),
        ]
        return labor_cols, parts_cols

    labor_cols, parts_cols = build_cols_shared_fixed()

    LABOR_TAIL_LABELS = {"Taxable", "Hours", "Rate", "Price"}
    PARTS_TAIL_LABELS = {"Taxable", "Qty", "Unit Price", "Price"}
    NUMERIC_HEADER_LABELS = {"Hours", "Rate", "Qty", "Unit Price", "Price"}

    def draw_table_header(cols: List[Tuple[str, float]], y_top: float, tail_labels: set[str]):
        _rect_fill(c, x0, y_top - TABLE_HDR_H, content_w, TABLE_HDR_H, BLACK)
        x = x0
        for label, w in cols:
            if label == "":
                x += w
                continue

            if label in NUMERIC_HEADER_LABELS:
                _draw_right(c, x + w - 4, y_top - 12, label, fs=FS_XS, bold=True, color=WHITE)
                x += w
                continue

            if label in tail_labels:
                _set_font(c, FS_XS, bold=True)
                c.setFillColor(WHITE)
                tw = stringWidth(label, c._fontname, FS_XS)
                c.drawString(x + (w - tw) / 2.0, y_top - 12, label)
                c.setFillColor(BLACK)
            else:
                _draw_text(c, x + 4, y_top - 12, label, fs=FS_XS, bold=True, color=WHITE)

            x += w

    # ===== Labor =====
    labor_rows = [] if hide_labor else (normalized.get("labor_rows") or [])
    if labor_rows:
        _draw_text(c, x0, y, "Labor", fs=FS_SM, bold=True)
        y -= 12
        ensure_space(TABLE_HDR_H + 10)
        draw_table_header(labor_cols, y, LABOR_TAIL_LABELS)
        y -= TABLE_HDR_H

        labor_total_hours = 0.0
        labor_total_amt = 0.0

        for r in labor_rows:
            date_lines = _wrap_lines(_display_row_date(r.get("date")), "Helvetica", FS_XS, labor_cols[0][1] - 8)
            name_lines = _wrap_lines(_s(r.get("name")), "Helvetica", FS_XS, labor_cols[1][1] - 8)
            desc_lines = _wrap_lines(_s(r.get("description")), "Helvetica", FS_XS, labor_cols[2][1] - 8)

            row_line_count = max(
                len(date_lines),
                len(name_lines),
                len(desc_lines),
                1,
            )
            row_h = _compute_row_h(row_line_count)
            ensure_space(row_h + 8)

            row_top = y
            y_base = row_top - 11

            x = x0
            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=date_lines)
            x += labor_cols[0][1]

            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=name_lines)
            x += labor_cols[1][1]

            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=desc_lines)
            x += labor_cols[2][1]

            taxable = "Yes" if bool(r.get("taxable")) else "No"
            _draw_center(c, x, labor_cols[3][1], y_base, taxable, fs=FS_XS)
            x += labor_cols[3][1]

            hours = float(r.get("hours") or 0)
            rate = float(r.get("rate") or 0)
            amount = float(r.get("price") or 0)

            labor_total_hours += hours
            labor_total_amt += amount

            _draw_right(c, x + labor_cols[4][1] - 4, y_base, f"{hours:g}", fs=FS_XS)
            x += labor_cols[4][1]

            _draw_right(c, x + labor_cols[5][1] - 4, y_base, _money(rate), fs=FS_XS)
            x += labor_cols[5][1]

            _draw_right(c, x + labor_cols[6][1] - 4, y_base, _money(amount), fs=FS_XS)

            _hr(c, x0, x1, y - row_h, lw=0.6, col=LIGHT_RULE)
            y -= row_h

        ensure_space(24)
        _rect_fill(c, x0, y - 16, content_w, 16, GREY_TOTAL)

        x_desc_end = x0 + sum(w for _, w in labor_cols[:3])
        x_hours_end = x0 + sum(w for _, w in labor_cols[:5])
        x_table_end = x0 + sum(w for _, w in labor_cols)

        y_mid = y - 12
        _draw_right(c, x_desc_end - 6, y_mid, "Labor Total", fs=FS_XS, bold=True)
        _draw_right(c, x_hours_end - 6, y_mid, f"{labor_total_hours:g}", fs=FS_XS, bold=True)
        _draw_right(c, x_table_end - 4, y_mid, _money(labor_total_amt), fs=FS_XS, bold=True)

        y -= 22
        y -= 12

    # ===== Parts =====
    parts_rows = [] if hide_parts else (normalized.get("parts_rows") or [])
    if parts_rows:
        _draw_text(c, x0, y, "Parts & Materials", fs=FS_SM, bold=True)
        y -= 12
        ensure_space(TABLE_HDR_H + 10)
        draw_table_header(parts_cols, y, PARTS_TAIL_LABELS)
        y -= TABLE_HDR_H

        parts_total_qty = 0.0
        parts_total_amt = 0.0

        for r in parts_rows:
            date_lines = _wrap_lines(_display_row_date(r.get("date")), "Helvetica", FS_XS, parts_cols[0][1] - 8)
            name_lines = _wrap_lines(_s(r.get("name")), "Helvetica", FS_XS, parts_cols[1][1] - 8)
            code_lines = _wrap_lines(_s(r.get("code")), "Helvetica", FS_XS, parts_cols[2][1] - 8)
            desc_lines = _wrap_lines(_s(r.get("description")), "Helvetica", FS_XS, parts_cols[3][1] - 8)

            row_line_count = max(
                len(date_lines),
                len(name_lines),
                len(code_lines),
                len(desc_lines),
                1,
            )
            row_h = _compute_row_h(row_line_count)
            ensure_space(row_h + 8)

            row_top = y
            y_base = row_top - 11

            x = x0
            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=date_lines)
            x += parts_cols[0][1]

            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=name_lines)
            x += parts_cols[1][1]

            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=code_lines)
            x += parts_cols[2][1]

            _draw_wrapped_cell_top(c, x, row_top=row_top, lines=desc_lines)
            x += parts_cols[3][1]

            taxable = "Yes" if bool(r.get("taxable")) else "No"
            _draw_center(c, x, parts_cols[4][1], y_base, taxable, fs=FS_XS)
            x += parts_cols[4][1]

            qty = float(r.get("qty") or 0)
            unit_price = float(r.get("unit_price") or 0)
            amount = float(r.get("price") or 0)

            parts_total_qty += qty
            parts_total_amt += amount

            _draw_right(c, x + parts_cols[5][1] - 4, y_base, f"{qty:g}", fs=FS_XS)
            x += parts_cols[5][1]

            _draw_right(c, x + parts_cols[6][1] - 4, y_base, _money(unit_price), fs=FS_XS)
            x += parts_cols[6][1]

            _draw_right(c, x + parts_cols[7][1] - 4, y_base, _money(amount), fs=FS_XS)

            _hr(c, x0, x1, y - row_h, lw=0.6, col=LIGHT_RULE)
            y -= row_h

        ensure_space(24)
        _rect_fill(c, x0, y - 16, content_w, 16, GREY_TOTAL)

        x_desc_end = x0 + sum(w for _, w in parts_cols[:4])
        x_qty_end = x0 + sum(w for _, w in parts_cols[:6])
        x_table_end = x0 + sum(w for _, w in parts_cols)

        y_mid = y - 12
        _draw_right(c, x_desc_end - 6, y_mid, "Parts & Materials Total", fs=FS_XS, bold=True)
        _draw_right(c, x_qty_end - 6, y_mid, f"{parts_total_qty:g}", fs=FS_XS, bold=True)
        _draw_right(c, x_table_end - 4, y_mid, _money(parts_total_amt), fs=FS_XS, bold=True)

        y -= 28

    # ===== Totals block + Payment Options =====
    payment_title = "Payment Options:"

    summary_w = 3.25 * inch
    sx1 = x1
    sx0 = sx1 - summary_w

    payment_x0 = x0 + 2
    payment_w = (sx0 - payment_x0) - 14

    label_x = sx1 - 120
    value_x = sx1

    totals_row_h = 16
    bar_h = 18

    PAY_TITLE_FS = FS
    PAY_BODY_FS = FS_SM
    payment_line_gap = 11

    payment_render_lines: List[Tuple[List[Tuple[str, bool]], int]] = [
        ([(payment_title, True)], PAY_TITLE_FS),
        ([("Pay securely using the payment link in the invoice email", False)], PAY_BODY_FS),
        ([("Card payments are not accepted for invoices over $5,000", False)], PAY_BODY_FS),
        ([("E-Transfer:", True), (" accounting@mainlinefire.com", False)], PAY_BODY_FS),
        ([("EFT:", True), (" Transit 21642 • Institution 001 • Account 1001460", False)], PAY_BODY_FS),
        ([("HST Registration No.:", True), (" 812882488", False)], PAY_BODY_FS),
        ([("Please reference your invoice number with payment.", False)], PAY_BODY_FS),
        ([("Questions? Call 647-325-8577.", False)], PAY_BODY_FS),
    ]

    def wrap_inline_segments(
        segments: List[Tuple[str, bool]],
        fs: int,
        max_w: float,
    ) -> List[List[Tuple[str, bool]]]:
        out_lines: List[List[Tuple[str, bool]]] = []
        cur_line: List[Tuple[str, bool]] = []
        cur_text = ""

        def flush():
            nonlocal cur_line, cur_text
            if cur_line:
                out_lines.append(cur_line)
            cur_line = []
            cur_text = ""

        for seg_text, seg_bold in segments:
            words = seg_text.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                trial = cur_text + token
                font = "Helvetica-Bold" if seg_bold else "Helvetica"

                if not cur_text:
                    cur_line.append((token, seg_bold))
                    cur_text = token
                    continue

                if stringWidth(trial, font, fs) <= max_w:
                    cur_line.append((token, seg_bold))
                    cur_text += token
                else:
                    flush()
                    cur_line.append((word, seg_bold))
                    cur_text = word

        flush()
        return out_lines or [[]]

    wrapped_payment_lines: List[Tuple[List[Tuple[str, bool]], int]] = []
    for segs, fs_now in payment_render_lines:
        wrapped = wrap_inline_segments(segs, fs_now, payment_w)
        for line in wrapped:
            wrapped_payment_lines.append((line, fs_now))

    payment_h = len(wrapped_payment_lines) * payment_line_gap

    service_fee = _to_float(normalized.get("service_fee"))
    discount = _to_float(normalized.get("discount"))

    totals_rows: List[Tuple[str, str, bool, bool]] = []
    totals_rows.append(("Subtotal", _money(normalized.get("subtotal")), False, False))

    if service_fee != 0:
        totals_rows.append(("Service Fee", _money(service_fee), False, True))

    if discount != 0:
        totals_rows.append(("Discount", _money(discount), False, True))

    if service_fee != 0 or discount != 0:
        totals_rows.append((
            "Subtotal After Discount/Fees",
            _money(normalized.get("subtotal_after_discount_fees")),
            True,
            True,
        ))

    totals_rows.extend([
        ("Taxable Subtotal", _money(normalized.get("taxable_subtotal")), False, True),
        ("Sales Tax Rate", _s(normalized.get("sales_tax_rate")), False, True),
        ("Tax Amount", _money(normalized.get("tax_amount")), False, True),
    ])

    totals_h = (len(totals_rows) * totals_row_h) + bar_h + (2 * totals_row_h) + 20
    needed_h = max(payment_h, totals_h)

    if y - needed_h < (M_B + 0.35 * inch):
        new_page()

    # payment block
    payment_top = y - 10
    py = payment_top
    for segments, fs_now in wrapped_payment_lines:
        _draw_text_inline_segments(c, payment_x0, py, segments, fs=fs_now)
        py -= payment_line_gap

    # totals block
    def rule(y_line: float):
        _hr(c, sx0, sx1, y_line, lw=0.9, col=LIGHT_RULE)

    def totals_row(label: str, value: str, bold: bool = False, top_rule: bool = True):
        nonlocal y
        top = y
        bottom = y - totals_row_h

        if top_rule:
            rule(top)
        rule(bottom)

        baseline = bottom + (totals_row_h / 2.0) - (FS_XS * 0.35)
        _draw_right(c, label_x, baseline, label, fs=FS_XS, bold=bold)
        _draw_right(c, value_x, baseline, value, fs=FS_XS, bold=bold)

        y = bottom

    for label, value, bold, top_rule in totals_rows:
        totals_row(label, value, bold=bold, top_rule=top_rule)

    bottom = y - bar_h
    _rect_fill(c, sx0, bottom, (sx1 - sx0), bar_h, ORANGE)

    baseline = bottom + (bar_h / 2.0) - (FS_XS * 0.35)
    _draw_right(c, label_x, baseline, "Total", fs=FS_XS, bold=True, color=WHITE)
    _draw_right(c, value_x, baseline, _money(normalized.get("total")), fs=FS_XS, bold=True, color=WHITE)

    y = bottom - 6

    totals_row("Amount Paid", _money(normalized.get("amount_paid")))
    totals_row("Balance", _money(normalized.get("balance")), bold=True)

    payment_bottom = payment_top - payment_h
    y = min(y, payment_bottom) - 8

    c.save()
    pdf_no_footer = buf.getvalue()
    pdf_with_footer = _stamp_footer(pdf_no_footer)

    balance = _to_float(normalized.get("balance"))

    # Apply PAID stamp ONLY when fully paid
    if abs(balance) < 0.01:
        return _stamp_paid(pdf_with_footer)

    return pdf_with_footer