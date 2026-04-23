# app/styling/proposal/content_pages.py
from __future__ import annotations

import os
from io import BytesIO
from typing import Any, Dict, List, Tuple

from reportlab.lib.colors import Color, black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.styling.proposal.utils import money, safe_text, service_label_for_proposal_type


# Match the baked-in template page size (7.5" x 10" = 540 x 720 pt),
# not the default US letter size. This keeps every page the same size
# when the PDFs are merged.
PAGE_WIDTH, PAGE_HEIGHT = 540, 720
CONTENT_PAGE_SIZE = (PAGE_WIDTH, PAGE_HEIGHT)

LEFT = 46
RIGHT = PAGE_WIDTH - 46
TOP = PAGE_HEIGHT - 42
BOTTOM = 44

# Palette tuned to match the reference screenshots.
ORANGE = Color(0.91, 0.43, 0.27, alpha=1)
DARK = Color(0.13, 0.13, 0.13, alpha=1)
MID = Color(0.45, 0.45, 0.45, alpha=1)
# Muted / "blur" gray used for the small "OUR SOLUTIONS" eyebrow label
# and the scope-summary paragraph (per reference PDF).
MUTED = Color(0.35, 0.35, 0.35, alpha=1)
LIGHT_LINE = Color(0.82, 0.82, 0.82, alpha=1)

# Footer icon path. Resolved at runtime; if not found we skip it cleanly.
ICON_CANDIDATES = [
    "templates/proposal/mainline-icon-300ppi.png",
    os.path.join(os.path.dirname(__file__), "templates", "proposal", "mainline-icon-300ppi.png"),
    os.path.join(
        os.path.dirname(__file__), "..", "..", "templates", "proposal", "mainline-icon-300ppi.png"
    ),
]


def _resolve_icon_path() -> str | None:
    for candidate in ICON_CANDIDATES:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------
def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    text = safe_text(text)
    if not text:
        return []

    out: List[str] = []

    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            out.append("")
            continue

        words = raw_line.split()
        current = ""

        for word in words:
            candidate = word if not current else f"{current} {word}"
            if stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    out.append(current)
                current = word

        if current:
            out.append(current)

    return out


def _split_bullets(text: str) -> List[str]:
    lines: List[str] = []
    for raw in safe_text(text).splitlines():
        raw = raw.strip()
        if raw:
            lines.append(raw)
    return lines


def _clean_bullet(line: str) -> str:
    text = line
    if text.startswith("- "):
        text = text[2:].strip()
    elif text.startswith("• "):
        text = text[2:].strip()
    return text


def _parse_price_value(value: Any) -> float | None:
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    cleaned = "".join(ch for ch in raw if ch in "0123456789.-")
    if not cleaned:
        return None

    try:
        return float(cleaned)
    except Exception:
        return None


def _format_item_price(value: Any) -> str:
    numeric = _parse_price_value(value)
    if numeric is not None:
        return money(numeric)

    raw = safe_text(value).strip()
    return raw


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _draw_orange_bullet(c: canvas.Canvas, x: float, y_baseline: float) -> None:
    """Draws a small filled orange circle used as the bullet marker."""
    c.setFillColor(ORANGE)
    c.setStrokeColor(ORANGE)
    # y_baseline is the text baseline; lift circle slightly to center on x-height.
    c.circle(x, y_baseline + 2.0, 1.2, stroke=0, fill=1)


def _draw_bulleted_line(
    c: canvas.Canvas,
    bullet_x: float,
    text_x: float,
    y: float,
    text: str,
    max_width: float,
    font_name: str = "Helvetica",
    font_size: int = 10,
    leading: int = 13,
) -> float:
    """
    Draws a single bullet with wrapped continuation text underneath,
    keeping the bullet aligned to the first line only.
    """
    wrapped = _wrap_text(text, font_name, font_size, max_width)
    if not wrapped:
        return y

    # First line: bullet + text
    _draw_orange_bullet(c, bullet_x, y)
    c.setFillColor(DARK)
    c.setFont(font_name, font_size)
    c.drawString(text_x, y, wrapped[0])
    y -= leading

    # Continuation lines (no bullet)
    for line in wrapped[1:]:
        c.drawString(text_x, y, line)
        y -= leading

    return y


# ---------------------------------------------------------------------------
# Page chrome
# ---------------------------------------------------------------------------
def _draw_page_header(
    c: canvas.Canvas,
    property_name: str,
    proposal_type: str,
) -> float:
    """
    Header matching the reference:
      small orange "OUR SOLUTIONS" label,
      then large dark title "Service Quote for <Property>" with property in orange,
      then a thin light divider.
    """
    y = TOP

    # Small eyebrow label — muted gray, not bold (per reference PDF).
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(LEFT, y, "OUR SOLUTIONS")

    y -= 26

    # Large title. Split so property name renders in orange.
    title_prefix = f"{service_label_for_proposal_type(proposal_type)} for "
    title_property = property_name or "[Property Name]"

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(DARK)
    c.drawString(LEFT, y, title_prefix)
    prefix_w = stringWidth(title_prefix, "Helvetica-Bold", 22)

    c.setFillColor(ORANGE)
    c.drawString(LEFT + prefix_w, y, title_property)

    y -= 26
    return y


def _draw_page_footer(c: canvas.Canvas) -> None:
    """
    Footer matching the baked-in template pages (e.g. page 3 of the master
    proposal). Positions measured directly from the reference PDF:

      - Icon left edge at x ~= 17pt (sits in the left margin, BEFORE LEFT=46);
        bottom of icon at y ~= 13pt from bottom; icon height ~= 20pt.
      - "Mainline Fire Protection" text starts at x = LEFT (46pt) with its
        baseline at y ~= 22pt from bottom, matching the baseline of the
        page number stamped by page_number.py.
      - "MainlineFire.com" is right-aligned to x = RIGHT on the same baseline.
      - Text is rendered in pure black (the reference text is ~RGB(0,0,0),
        not the slightly lighter DARK we use for body copy).

    NOTE: the page number itself is intentionally NOT drawn here — it is
    stamped separately by page_number.py on the bottom-right. Drawing it
    here would duplicate it.
    """
    # Text baseline chosen to align with the page number that page_number.py
    # stamps at the same baseline on every page.
    text_baseline_y = 18

    # Icon geometry (measured from the reference baked template page 3).
    icon_x = 17
    icon_bottom_y = 13
    icon_size = 20

    icon_path = _resolve_icon_path()
    if icon_path:
        try:
            icon = ImageReader(icon_path)
            c.drawImage(
                icon,
                icon_x,
                icon_bottom_y,
                width=icon_size,
                height=icon_size,
                mask="auto",
                preserveAspectRatio=True,
            )
        except Exception:
            pass

    # Footer text in true black to match the reference.
    c.setFillColor(black)
    c.setFont("Helvetica", 9)

    # Left side: "Mainline Fire Protection" starts at LEFT, same column as body.
    c.drawString(LEFT, text_baseline_y, "Mainline Fire Protection")

    # Right side: "MainlineFire.com" right-aligned to RIGHT. page_number.py
    # stamps the page number further right of this, matching the other pages.
    c.drawRightString(RIGHT, text_baseline_y, "MainlineFire.com")


# ---------------------------------------------------------------------------
# Item block (boxed row with title bar + bullets + bottom divider)
# ---------------------------------------------------------------------------
def _draw_item_block(
    c: canvas.Canvas,
    item: Dict[str, Any],
    y: float,
) -> float:
    item_name = safe_text(item.get("item")) or "Item"
    description = safe_text(item.get("description"))
    price = _format_item_price(item.get("price"))

    title_font = "Helvetica-Bold"
    title_size = 11
    price_size = 11

    # Reserve space on the right for the price so the title can wrap.
    price_w = stringWidth(price, "Helvetica-Bold", price_size)
    title_max_width = (RIGHT - LEFT) - price_w - 16

    # Title (wrap to multiple lines if needed) + price on first line, right-aligned.
    # Per reference, there is NO top divider — only a single divider under the title.
    title_lines = _wrap_text(item_name, title_font, title_size, title_max_width) or [item_name]

    c.setFillColor(DARK)
    c.setFont(title_font, title_size)
    c.drawString(LEFT, y, title_lines[0])

    c.setFont("Helvetica-Bold", price_size)
    c.drawRightString(RIGHT, y, price)

    # Additional wrapped title lines
    for extra in title_lines[1:]:
        y -= 14
        c.setFont(title_font, title_size)
        c.drawString(LEFT, y, extra)

    y -= 10

    # Single divider under title block (only line in the item block)
    c.setStrokeColor(black)
    c.setLineWidth(0.6)
    c.line(LEFT, y, RIGHT, y)
    y -= 16

    # Description bullets
    bullet_lines = _split_bullets(description)
    if bullet_lines:
        for bullet in bullet_lines:
            text = _clean_bullet(bullet)
            y = _draw_bulleted_line(
                c,
                bullet_x=LEFT + 4,
                text_x=LEFT + 14,
                y=y,
                text=text,
                max_width=RIGHT - (LEFT + 14),
            )
    elif description:
        # Treat single blob as one bullet
        y = _draw_bulleted_line(
            c,
            bullet_x=LEFT + 4,
            text_x=LEFT + 14,
            y=y,
            text=description,
            max_width=RIGHT - (LEFT + 14),
        )

    y -= 20
    return y


# ---------------------------------------------------------------------------
# Totals block - orange bar for Quote Total
# ---------------------------------------------------------------------------
def _draw_totals_block(c: canvas.Canvas, fields: Dict[str, Any], y: float) -> float:
    subtotal = money(fields.get("subtotal"))
    tax_rate = safe_text(fields.get("tax_rate")) or "13"
    tax = money(fields.get("tax"))
    total = money(fields.get("total"))

    # Top divider for the totals region
    c.setStrokeColor(LIGHT_LINE)
    c.setLineWidth(0.6)
    c.line(LEFT, y + 6, RIGHT, y + 6)
    y -= 10

    # Right-aligned label / value columns
    value_x = RIGHT
    label_right_x = RIGHT - 110  # right edge of label column

    # --- Subtotal row (bold) ---
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(label_right_x, y, "Subtotal")
    c.drawRightString(value_x, y, subtotal)
    y -= 12

    # Divider between Subtotal and Tax
    c.setStrokeColor(LIGHT_LINE)
    c.setLineWidth(0.6)
    c.line(LEFT, y, RIGHT, y)
    y -= 14

    # --- Tax row (bold) ---
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(label_right_x, y, f"Tax ({tax_rate}%)")
    c.drawRightString(value_x, y, tax)
    y -= 12

    # --- Quote Total — full-width orange bar with white bold text ---
    # The bar is positioned so its top edge sits right under the Tax row,
    # covering the position where a divider line would otherwise go (per
    # reference: no visible divider between Tax and the orange bar).
    bar_height = 30
    bar_top = y
    bar_bottom = bar_top - bar_height

    c.setFillColor(ORANGE)
    c.setStrokeColor(ORANGE)
    c.rect(LEFT, bar_bottom, RIGHT - LEFT, bar_height, stroke=0, fill=1)

    text_baseline = bar_bottom + (bar_height / 2) - 4
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(label_right_x, text_baseline, "Quote Total")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(value_x, text_baseline, total)

    y = bar_bottom - 32
    return y


# ---------------------------------------------------------------------------
# Included in Quote
# ---------------------------------------------------------------------------
def _draw_included(c: canvas.Canvas, fields: Dict[str, Any], y: float) -> float:
    """
    Draws the 'Included in Quote' section if provided. If `included` is
    missing from fields, falls back to a sensible default of "All Parts & Labor"
    to match the reference screenshot.
    """
    included_raw = fields.get("included")
    if included_raw is None:
        included_lines = ["All Parts & Labor"]
    else:
        included_lines = _split_bullets(safe_text(included_raw))
        if not included_lines:
            return y

    c.setFillColor(DARK)
    c.setFont("Helvetica", 12)
    c.drawString(LEFT, y, "Included in Quote")
    y -= 16

    for line in included_lines:
        text = _clean_bullet(line)
        y = _draw_bulleted_line(
            c,
            bullet_x=LEFT + 4,
            text_x=LEFT + 14,
            y=y,
            text=text,
            max_width=RIGHT - (LEFT + 14),
        )

    y -= 20
    return y


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------
def _draw_exclusions(c: canvas.Canvas, exclusions: str, y: float) -> float:
    c.setFillColor(DARK)
    c.setFont("Helvetica", 12)
    c.drawString(LEFT, y, "Specific Exclusions")
    y -= 16

    lines = _split_bullets(exclusions)
    for line in lines:
        text = _clean_bullet(line)
        y = _draw_bulleted_line(
            c,
            bullet_x=LEFT + 4,
            text_x=LEFT + 14,
            y=y,
            text=text,
            max_width=RIGHT - (LEFT + 14),
        )
        # Slightly looser spacing between exclusion items to match reference
        y -= 3

    return y


# ---------------------------------------------------------------------------
# Height estimation (for page-break planning)
# ---------------------------------------------------------------------------
def _estimate_item_height(item: Dict[str, Any]) -> float:
    item_name = safe_text(item.get("item")) or "Item"
    price = _format_item_price(item.get("price"))
    price_w = stringWidth(price, "Helvetica-Bold", 11)
    title_max_width = (RIGHT - LEFT) - price_w - 16
    title_lines = _wrap_text(item_name, "Helvetica-Bold", 11, title_max_width) or [item_name]

    desc = safe_text(item.get("description"))
    bullets = _split_bullets(desc) or ([desc] if desc else [])

    bullet_line_count = 0
    for bullet in bullets:
        text = _clean_bullet(bullet)
        wrapped = _wrap_text(text, "Helvetica", 10, RIGHT - (LEFT + 14))
        bullet_line_count += max(1, len(wrapped))

    # title first line + extra title lines*14 + gap(10)
    # + single divider + gap(12) + bullets*13 + trailing(10)
    return (
        12  # first title line
        + (len(title_lines) - 1) * 14
        + 10
        + 12
        + (bullet_line_count * 13)
        + 10
    )


def _estimate_totals_height() -> float:
    # top divider(10) + subtotal(12) + divider(14) + tax(12)
    # + bar(30) + trailing(22)
    return 10 + 12 + 14 + 12 + 30 + 22


def _estimate_included_height(fields: Dict[str, Any]) -> float:
    included_raw = fields.get("included")
    if included_raw is None:
        lines = ["All Parts & Labor"]
    else:
        lines = _split_bullets(safe_text(included_raw))
    if not lines:
        return 0
    line_count = 0
    for line in lines:
        text = _clean_bullet(line)
        wrapped = _wrap_text(text, "Helvetica", 10, RIGHT - (LEFT + 14))
        line_count += max(1, len(wrapped))
    return 16 + (line_count * 13) + 10


def _estimate_exclusions_height(exclusions: str) -> float:
    lines = _split_bullets(exclusions)
    line_count = 0
    for line in lines:
        text = _clean_bullet(line)
        wrapped = _wrap_text(text, "Helvetica", 10, RIGHT - (LEFT + 14))
        line_count += max(1, len(wrapped))
    return 16 + (line_count * 13) + (len(lines) * 3) + 10


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def render_content_pages(fields: Dict[str, Any], start_page_number: int = 4) -> bytes:
    """
    Generates the flowing content section:
      - service quote header
      - scope summary
      - line items (boxed rows)
      - subtotal / tax / orange Quote Total bar
      - Included in Quote
      - Specific Exclusions

    Returns a standalone PDF bytes object containing 1..N content pages.
    Page size matches the other template pages (540 x 720 pt).
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=CONTENT_PAGE_SIZE)

    property_name = safe_text(fields.get("property_name"))
    proposal_type = safe_text(fields.get("proposal_type"))
    scope_summary = safe_text(fields.get("scope_summary"))
    exclusions = safe_text(fields.get("exclusions"))
    items = fields.get("items", []) or []

    def new_page() -> float:
        _draw_page_footer(c)
        c.showPage()
        return _draw_page_header(c, property_name, proposal_type)

    y = _draw_page_header(c, property_name, proposal_type)

    # Scope summary — muted gray per reference (not solid black).
    if scope_summary:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        summary_lines = _wrap_text(scope_summary, "Helvetica", 10, RIGHT - LEFT)
        for line in summary_lines:
            if y < BOTTOM + 80:
                y = new_page()
                c.setFillColor(MUTED)
                c.setFont("Helvetica", 10)
            c.drawString(LEFT, y, line)
            y -= 13
        y -= 20

    # Items
    for item in items:
        needed = _estimate_item_height(item)
        if y - needed < BOTTOM + 40:
            y = new_page()
        y = _draw_item_block(c, item, y)

    # Totals (keep together with an extra buffer so the orange bar isn't split)
    totals_needed = _estimate_totals_height()
    if y - totals_needed < BOTTOM + 30:
        y = new_page()
    y = _draw_totals_block(c, fields, y)

    # Included in Quote
    included_needed = _estimate_included_height(fields)
    if included_needed and y - included_needed < BOTTOM + 20:
        y = new_page()
    y = _draw_included(c, fields, y)

    # Exclusions
    exclusion_needed = _estimate_exclusions_height(exclusions)
    if y - exclusion_needed < BOTTOM + 20:
        y = new_page()
    _draw_exclusions(c, exclusions, y)

    # Final page footer
    _draw_page_footer(c)

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes