# app/styling/invoice/renderer.py
from __future__ import annotations

import io
from typing import Any, Dict, List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader

# Footer stamping
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject


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


def _wrap_lines(text: str, font: str, fs: int, max_w: float) -> List[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if stringWidth(trial, font, fs) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


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


def _compute_row_h(desc_line_count: int) -> float:
    core = max(1, desc_line_count) * ROW_LINE_H
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
            img = ImageReader(logo_path)
            iw, ih = img.getSize()
            scale = float(HEADER_LOGO_H) / float(ih) if ih else 1.0
            lw = iw * scale
            lh = ih * scale
            c.drawImage(img, logo_x0, y_block_bottom, width=lw, height=lh, mask="auto")
        except Exception:
            pass

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


# ---------------- Renderer ----------------
def render_invoice_styled_draft(normalized: Dict[str, Any], logo_path: str | None = None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    x0 = M_L
    x1 = PAGE_W - M_R
    content_w = x1 - x0

    # ===== Header =====
    y = _draw_header_v2_invoice(c, logo_path=logo_path)
    y -= 0.12 * inch

    # ===== Bill To + Invoice meta =====
    _draw_text(c, x0, y, "Bill To", fs=FS_SM, bold=True)
    y_left = y - 12

    bill_name = _s(normalized.get("billClient_name"))
    bill_lines = normalized.get("billClient_address_lines") or []

    # phone/email (from mapper keys)
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

    # ----- Bill To block (name/address left; phone/email right) -----
    _draw_text(c, x0, y_left, bill_name, fs=FS_XS)

    # ✅ phone/email column X should align with "Property Name" column below
    bill_contact_x = x0 + content_w * 0.34  # same as mid_x

    # Phone on same row as Client Name
    if bill_phone:
        _draw_text(c, bill_contact_x, y_left, bill_phone, fs=FS_XS)

    # Address lines (left column) start on next row
    for i, ln in enumerate(bill_lines[:4]):
        _draw_text(c, x0, y_left - (i + 1) * 11, _s(ln), fs=FS_XS)

    # Email on same row as Address Line 1
    if bill_email:
        _draw_text(c, bill_contact_x, y_left - 11, bill_email, fs=FS_XS)

    # Height for rule below bill-to/meta block
    left_line_count = 1 + min(4, len(bill_lines[:4]))  # name + address lines
    right_line_count = (1 if bill_phone else 0) + (1 if bill_email else 0)  # phone + email
    block_lines = max(left_line_count, right_line_count)

    # Right side meta
    meta_x = x0 + content_w * 0.52
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

    # ✅ divider line under whichever side is taller (bill-to vs meta)
    y = min(y_left - (block_lines * 11), meta_y) - 14
    _hr(c, x0, x1, y, lw=0.9, col=LIGHT_RULE)
    y -= 16

    # ===== Customer / Property grid =====
    left_x = x0
    mid_x = x0 + content_w * 0.34
    right_x = meta_x  # align Property Address with Invoice meta block

    _draw_text(c, left_x, y, "Customer Name:", fs=FS_XS, bold=True)
    _draw_text(c, left_x, y - 11, _s(normalized.get("customer_name")), fs=FS_XS)

    _draw_text(c, mid_x, y, "Property Name:", fs=FS_XS, bold=True)
    _draw_text(c, mid_x, y - 11, _s(normalized.get("property_name")), fs=FS_XS)

    _draw_text(c, right_x, y, "Property Address:", fs=FS_XS, bold=True)
    prop_lines = _normalize_property_address(normalized.get("property_address_lines") or [])
    for i, ln in enumerate(prop_lines[:4]):
        _draw_text(c, right_x, y - 11 - (i * 11), _s(ln), fs=FS_XS)

    block_h = 11 + max(1, min(4, len(prop_lines))) * 11
    y -= (block_h + 14)

    _draw_text(c, left_x, y, "Authorized by:", fs=FS_XS, bold=True)
    _draw_text(c, left_x, y - 11, _s(normalized.get("authorized_by")), fs=FS_XS)

    _draw_text(c, mid_x, y, "Customer WO:", fs=FS_XS, bold=True)
    _draw_text(c, mid_x, y - 11, _s(normalized.get("customerProvidedWONumber")), fs=FS_XS)

    _draw_text(c, right_x, y, "NTE:", fs=FS_XS, bold=True)
    _draw_text(c, right_x, y - 11, _s(normalized.get("nte")), fs=FS_XS)

    y -= 26
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

    # ===== Columns (ONE money column: Price) =====
    def build_cols_shared_fixed() -> tuple[List[Tuple[str, float]], List[Tuple[str, float]]]:
        date_w = 0.90 * inch
        name_w = 1.30 * inch
        code_w = 0.85 * inch
        taxable_w = 0.65 * inch
        qty_w = 0.55 * inch
        unit_w = 0.85 * inch

        # single money column, narrow so it sits closer to Rate/Unit Price
        money_w = 0.95 * inch

        fixed_used = date_w + name_w + code_w + taxable_w + qty_w + unit_w + money_w
        min_desc = 1.55 * inch
        desc_w = content_w - fixed_used

        if desc_w < min_desc:
            deficit = (min_desc - desc_w)
            min_name = 1.05 * inch
            min_code = 0.60 * inch

            shrink_name = min(deficit * 0.60, max(0.0, name_w - min_name))
            shrink_code = min(deficit * 0.40, max(0.0, code_w - min_code))

            name_w -= shrink_name
            code_w -= shrink_code

            fixed_used = date_w + name_w + code_w + taxable_w + qty_w + unit_w + money_w
            desc_w = max(min_desc, content_w - fixed_used)

        labor_cols = [
            ("Date", date_w),
            ("Labor Name", name_w),
            ("", code_w),  # spacer
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

    def draw_table_header(cols: List[Tuple[str, float]], y_top: float, tail_labels: set[str]):
        _rect_fill(c, x0, y_top - TABLE_HDR_H, content_w, TABLE_HDR_H, BLACK)
        x = x0
        for label, w in cols:
            if label == "":
                x += w
                continue

            # Right-align money header
            if label == "Price":
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

    def draw_wrapped_left(x_left: float, w: float, row_top: float, row_h: float, lines: List[str]):
        base = _vcenter_baseline(row_top, row_h, FS_XS)
        n = max(1, len(lines))
        start_y = base + ((n - 1) * ROW_LINE_H) / 2.0
        yy = start_y
        for ln in (lines or [""]):
            _draw_text(c, x_left + 4, yy, ln, fs=FS_XS)
            yy -= ROW_LINE_H

    # ===== Labor =====
    _draw_text(c, x0, y, "Labor", fs=FS_SM, bold=True)
    y -= 12
    ensure_space(TABLE_HDR_H + 10)
    draw_table_header(labor_cols, y, LABOR_TAIL_LABELS)
    y -= TABLE_HDR_H

    labor_rows = normalized.get("labor_rows") or []
    labor_total_hours = 0.0
    labor_total_amt = 0.0

    for r in labor_rows:
        desc_lines = _wrap_lines(_s(r.get("description")), "Helvetica", FS_XS, labor_cols[3][1] - 10)
        row_h = _compute_row_h(len(desc_lines))
        ensure_space(row_h + 8)

        row_top = y
        y_base = _vcenter_baseline(row_top, row_h, FS_XS)

        x = x0
        _draw_text(c, x + 4, y_base, _s(r.get("date")), fs=FS_XS); x += labor_cols[0][1]
        _draw_text(c, x + 4, y_base, _s(r.get("name")), fs=FS_XS); x += labor_cols[1][1]
        x += labor_cols[2][1]  # spacer

        draw_wrapped_left(x, labor_cols[3][1], row_top=row_top, row_h=row_h, lines=desc_lines); x += labor_cols[3][1]

        taxable = "Yes" if bool(r.get("taxable")) else "No"
        _draw_center(c, x, labor_cols[4][1], y_base, taxable, fs=FS_XS); x += labor_cols[4][1]

        hours = float(r.get("hours") or 0)
        rate = float(r.get("rate") or 0)
        amount = float(r.get("price") or 0)

        labor_total_hours += hours
        labor_total_amt += amount

        _draw_right(c, x + labor_cols[5][1] - 4, y_base, f"{hours:g}", fs=FS_XS); x += labor_cols[5][1]
        _draw_right(c, x + labor_cols[6][1] - 4, y_base, _money(rate), fs=FS_XS); x += labor_cols[6][1]
        _draw_right(c, x + labor_cols[7][1] - 4, y_base, _money(amount), fs=FS_XS)

        # underline spans full table width
        _hr(c, x0, x1, y - row_h, lw=0.6, col=LIGHT_RULE)
        y -= row_h

    # Labor total row (full width grey bar)
    ensure_space(24)
    _rect_fill(c, x0, y - 16, content_w, 16, GREY_TOTAL)

    x_desc_end = x0 + sum(w for _, w in labor_cols[:4])   # end of description block
    x_hours_end = x0 + sum(w for _, w in labor_cols[:6])  # through Hours column
    x_table_end = x0 + sum(w for _, w in labor_cols)      # equals x1

    y_mid = y - 12
    _draw_right(c, x_desc_end - 6, y_mid, "Labor Total", fs=FS_XS, bold=True)
    _draw_right(c, x_hours_end - 6, y_mid, f"{labor_total_hours:g}", fs=FS_XS, bold=True)
    _draw_right(c, x_table_end - 4, y_mid, _money(labor_total_amt), fs=FS_XS, bold=True)

    y -= 22
    y -= 12

    # ===== Parts =====
    _draw_text(c, x0, y, "Parts & Materials", fs=FS_SM, bold=True)
    y -= 12
    ensure_space(TABLE_HDR_H + 10)
    draw_table_header(parts_cols, y, PARTS_TAIL_LABELS)
    y -= TABLE_HDR_H

    parts_rows = normalized.get("parts_rows") or []
    parts_total_qty = 0.0
    parts_total_amt = 0.0

    for r in parts_rows:
        desc_lines = _wrap_lines(_s(r.get("description")), "Helvetica", FS_XS, parts_cols[3][1] - 10)
        row_h = _compute_row_h(len(desc_lines))
        ensure_space(row_h + 8)

        row_top = y
        y_base = _vcenter_baseline(row_top, row_h, FS_XS)

        x = x0
        _draw_text(c, x + 4, y_base, _s(r.get("date")), fs=FS_XS); x += parts_cols[0][1]
        _draw_text(c, x + 4, y_base, _s(r.get("name")), fs=FS_XS); x += parts_cols[1][1]
        _draw_text(c, x + 4, y_base, _s(r.get("code")), fs=FS_XS); x += parts_cols[2][1]

        draw_wrapped_left(x, parts_cols[3][1], row_top=row_top, row_h=row_h, lines=desc_lines); x += parts_cols[3][1]

        taxable = "Yes" if bool(r.get("taxable")) else "No"
        _draw_center(c, x, parts_cols[4][1], y_base, taxable, fs=FS_XS); x += parts_cols[4][1]

        qty = float(r.get("qty") or 0)
        unit_price = float(r.get("unit_price") or 0)
        amount = float(r.get("price") or 0)

        parts_total_qty += qty
        parts_total_amt += amount

        _draw_right(c, x + parts_cols[5][1] - 4, y_base, f"{qty:g}", fs=FS_XS); x += parts_cols[5][1]
        _draw_right(c, x + parts_cols[6][1] - 4, y_base, _money(unit_price), fs=FS_XS); x += parts_cols[6][1]
        _draw_right(c, x + parts_cols[7][1] - 4, y_base, _money(amount), fs=FS_XS)

        # underline spans full table width
        _hr(c, x0, x1, y - row_h, lw=0.6, col=LIGHT_RULE)
        y -= row_h

    # Parts total row (full width grey bar)
    ensure_space(24)
    _rect_fill(c, x0, y - 16, content_w, 16, GREY_TOTAL)

    x_desc_end = x0 + sum(w for _, w in parts_cols[:4])
    x_qty_end = x0 + sum(w for _, w in parts_cols[:6])
    x_table_end = x0 + sum(w for _, w in parts_cols)

    y_mid = y - 12
    _draw_right(c, x_desc_end - 6, y_mid, "Parts & Materials Total", fs=FS_XS, bold=True)
    _draw_right(c, x_qty_end - 6, y_mid, f"{parts_total_qty:g}", fs=FS_XS, bold=True)
    _draw_right(c, x_table_end - 4, y_mid, _money(parts_total_amt), fs=FS_XS, bold=True)

    # space before totals block
    y -= 28

    # ===== Totals block (all rules + orange bar are full width of totals block) =====
    summary_w = 3.25 * inch
    sx1 = x1
    sx0 = sx1 - summary_w

    label_x = sx1 - 120
    value_x = sx1

    row_h = 16
    bar_h = 18

    approx_rows = 9
    totals_h = (approx_rows * row_h) + bar_h + 20
    if y - totals_h < (M_B + 0.35 * inch):
        new_page()

    def rule(y_line: float):
        # full width of the totals block
        _hr(c, sx0, sx1, y_line, lw=0.9, col=LIGHT_RULE)

    def totals_row(label: str, value: str, bold: bool = False, top_rule: bool = True):
        nonlocal y
        top = y
        bottom = y - row_h

        if top_rule:
            rule(top)
        rule(bottom)

        baseline = bottom + (row_h / 2.0) - (FS_XS * 0.35)
        _draw_right(c, label_x, baseline, label, fs=FS_XS, bold=bold)
        _draw_right(c, value_x, baseline, value, fs=FS_XS, bold=bold)

        y = bottom

    totals_row("Subtotal", _money(normalized.get("subtotal")), top_rule=False)
    totals_row("Service Fee", _money(normalized.get("service_fee")))
    totals_row("Discount", _money(normalized.get("discount")))
    totals_row("Subtotal After Discount/Fees", _money(normalized.get("subtotal_after_discount_fees")), bold=True)
    totals_row("Taxable Subtotal", _money(normalized.get("taxable_subtotal")))
    totals_row("Sales Tax Rate", _s(normalized.get("sales_tax_rate")))
    totals_row("Tax Amount", _money(normalized.get("tax_amount")))

    # Orange total bar: full width of totals block
    top = y
    bottom = y - bar_h
    _rect_fill(c, sx0, bottom, (sx1 - sx0), bar_h, ORANGE)

    baseline = bottom + (bar_h / 2.0) - (FS_XS * 0.35)
    _draw_right(c, label_x, baseline, "Total", fs=FS_XS, bold=True, color=WHITE)
    _draw_right(c, value_x, baseline, _money(normalized.get("total")), fs=FS_XS, bold=True, color=WHITE)

    y = bottom - 6

    totals_row("Amount Paid", _money(normalized.get("amount_paid")))
    totals_row("Balance", _money(normalized.get("balance")), bold=True)

    c.save()
    pdf_no_footer = buf.getvalue()
    return _stamp_footer(pdf_no_footer)