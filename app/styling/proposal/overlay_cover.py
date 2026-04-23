# app/styling/proposal/overlay_cover.py

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.styling.proposal.utils import safe_text


PAGE_WIDTH, PAGE_HEIGHT = letter  # 612 x 792 pt

# ── Colours ────────────────────────────────────────────────────────────────────
TEXT_COLOR = Color(0.10, 0.10, 0.10, alpha=1)

# ── Fonts ──────────────────────────────────────────────────────────────────────
PRIMARY_FONT = "Helvetica-Bold"
PRIMARY_SIZE = 9.0

SECONDARY_FONT = "Helvetica"
SECONDARY_SIZE = 9.0

BOTTOM_VALUE_FONT = "Helvetica-Bold"
BOTTOM_VALUE_SIZE = 9.0

# ── Layout constants ───────────────────────────────────────────────────────────
# Top row values
# Lower this a bit so there is more gap below the baked-in label
TOP_VALUE_Y = 138
TOP_LEADING_PRIMARY = 15
TOP_LEADING_SECONDARY = 13

# Bottom row values
BOT_VALUE_Y = 60

# Column X positions
# Pulled left so values align better under the baked-in labels
COL1_X = 46
COL2_X = 213
COL3_X = 378

# Maximum widths
COL1_W = 150
COL2_W = 150
COL3_W = 150


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    text = safe_text(text)
    if not text:
        return []

    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def _draw_wrapped_lines(
    c: canvas.Canvas,
    lines: List[str],
    x: float,
    y: float,
    font_name: str,
    font_size: float,
    color: Color,
    leading: float,
) -> float:
    c.setFillColor(color)
    c.setFont(font_name, font_size)

    for line in lines:
        c.drawString(x, y, line)
        y -= leading

    return y


def _draw_value_group(
    c: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    primary: str = "",
    secondary_lines: List[str] | None = None,
) -> float:
    secondary_lines = secondary_lines or []

    if safe_text(primary):
        wrapped = _wrap_text(primary, PRIMARY_FONT, PRIMARY_SIZE, width)
        y = _draw_wrapped_lines(
            c,
            wrapped,
            x,
            y,
            PRIMARY_FONT,
            PRIMARY_SIZE,
            TEXT_COLOR,
            TOP_LEADING_PRIMARY,
        )

    for raw in secondary_lines:
        raw = safe_text(raw)
        if not raw:
            continue

        wrapped = _wrap_text(raw, SECONDARY_FONT, SECONDARY_SIZE, width)
        y = _draw_wrapped_lines(
            c,
            wrapped,
            x,
            y,
            SECONDARY_FONT,
            SECONDARY_SIZE,
            TEXT_COLOR,
            TOP_LEADING_SECONDARY,
        )

    return y


def _split_address(raw: str) -> List[str]:
    raw = safe_text(raw)
    if not raw:
        return []

    if "\n" in raw:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) <= 1:
        return parts

    return [parts[0], ", ".join(parts[1:])]


# ── Public API ─────────────────────────────────────────────────────────────────

def create_cover_overlay(fields: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # Column 1 – Prepared For
    _draw_value_group(
        c,
        x=COL1_X,
        y=TOP_VALUE_Y,
        width=COL1_W,
        primary=safe_text(fields.get("contact_name")),
        secondary_lines=[
            safe_text(fields.get("contact_phone")),
            safe_text(fields.get("contact_email")),
        ],
    )

    # Column 2 – Company
    _draw_value_group(
        c,
        x=COL2_X,
        y=TOP_VALUE_Y,
        width=COL2_W,
        primary=safe_text(fields.get("customer_name")),
        secondary_lines=_split_address(fields.get("customer_address", "")),
    )

    # Column 3 – Property
    _draw_value_group(
        c,
        x=COL3_X,
        y=TOP_VALUE_Y,
        width=COL3_W,
        primary=safe_text(fields.get("property_name")),
        secondary_lines=_split_address(fields.get("property_address", "")),
    )

    # Bottom row
    c.setFillColor(TEXT_COLOR)
    c.setFont(BOTTOM_VALUE_FONT, BOTTOM_VALUE_SIZE)
    c.drawString(COL1_X, BOT_VALUE_Y, safe_text(fields.get("proposal_number", "")))
    c.drawString(COL2_X, BOT_VALUE_Y, safe_text(fields.get("proposal_date", "")))
    c.drawString(COL3_X, BOT_VALUE_Y, safe_text(fields.get("prepared_by", "")))

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes