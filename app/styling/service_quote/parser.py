# app/styling/service_quote/parser.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from app.styling.service_quote.text_extract import extract_words, words_to_text


@dataclass
class SQLine:
    name: str
    price: Optional[Decimal] = None
    description: str = ""


@dataclass
class ServiceQuoteData:
    client_name: str = ""
    client_phone: str = ""
    client_email: str = ""

    company_name: str = ""
    company_address: str = ""

    property_name: str = ""
    property_address: str = ""

    quote_number: str = ""
    quote_date: str = ""
    quote_description: str = ""

    items: List[SQLine] = field(default_factory=list)

    subtotal: str = ""
    tax: str = ""
    total: str = ""


LABEL_RE = re.compile(r"^(Attn|Phone|Email|Company|Address|Property|Date|Re|Estimate)\s*:?", re.I)


def _clean(s: str) -> str:
    return (s or "").replace("\u00a0", " ").replace("\x00", "").strip()


def _normalize_text(s: str) -> str:
    s = (s or "").replace("\u00a0", " ").replace("\x00", "")
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _between(text: str, left: str, right: str) -> str:
    m = re.search(
        re.escape(left) + r"\s*(.*?)\s*" + re.escape(right),
        text,
        flags=re.I | re.S,
    )
    return _clean(m.group(1)) if m else ""


def _after_same_line(text: str, label: str) -> str:
    m = re.search(re.escape(label) + r"\s*(.*)$", text, flags=re.I | re.M)
    return _clean(m.group(1)) if m else ""


def _money_decimal(s: str) -> Decimal:
    s = (s or "").replace("$", "").replace(",", "").strip()
    return Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_postal_token(tok: str) -> bool:
    """
    Accept either full Canadian postal code (A1A1A1) or the common split tail (1A1),
    because this PDF often splits "M4K 1P3" into "M4K" + "1P3" on the next line.
    """
    t = _clean(tok).replace(" ", "").upper()
    return bool(re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", t) or re.fullmatch(r"\d[A-Z]\d", t))


def _join_tokens(tokens: list[str]) -> str:
    return _clean(" ".join([_clean(t) for t in tokens if _clean(t)]))


def _find_first(words, predicate):
    xs = [w for w in words if predicate(w)]
    if not xs:
        return None
    return sorted(xs, key=lambda w: (w.page, w.y0, w.x0))[0]


def _extract_address_by_columns(words, which: str) -> str:
    """
    Extract address from word tokens using a simple column split (x threshold).
    Adds a safety-net:
      - if the address line ends with a 3-char prefix like "M4K"
      - and the next line contains a postal-tail like "1P3"
      - append the postal tail.
    Ignores next-line junk (labels, long sentences, etc.).

    ✅ IMPORTANT FIX:
    The column boundary must be far enough right so company address tokens like "ON" (x≈256)
    remain in the left column. For this PDF, right-column labels start around x≈310,
    so we use x_threshold=300.
    """
    x_threshold = 300.0  # ✅ was too low at 250; that mis-classified "ON" + "M4K" into the right column
    want_right = (which == "property")

    def in_col(w) -> bool:
        return (w.x0 >= x_threshold) if want_right else (w.x0 < x_threshold)

    # Find the Address: label for the target column
    label = _find_first(words, lambda w: w.text.strip().lower() == "address:" and in_col(w))
    if not label:
        return ""

    page = label.page
    y0 = label.y0

    # Same-line content to the right of "Address:"
    same_line = [
        w for w in words
        if w.page == page and in_col(w) and abs(w.y0 - y0) < 1.5 and w.x0 > label.x1
    ]
    same_line = sorted(same_line, key=lambda w: w.x0)
    line_text = _join_tokens([w.text for w in same_line])

    if not line_text:
        return ""

    # Determine the next line y in this column
    col_words_after = [w for w in words if w.page == page and in_col(w) and w.y0 > y0 + 3]
    if not col_words_after:
        return line_text

    next_y = min(col_words_after, key=lambda w: w.y0).y0
    next_line = [w for w in words if w.page == page and in_col(w) and abs(w.y0 - next_y) < 1.5]
    next_line = sorted(next_line, key=lambda w: w.x0)

    # --- Safety-net cleanup ---
    next_line_text = _join_tokens([w.text for w in next_line])

    # 1) Ignore next line if it starts with a label (Address:, Property:, etc.)
    if next_line_text and LABEL_RE.match(next_line_text):
        return line_text

    # 2) Only consider postal-ish tokens on next line (e.g., "1P3" or "M4K1P3")
    postal_parts = [w.text for w in next_line if _is_postal_token(w.text)]
    if not postal_parts:
        return line_text

    postal_joined = _join_tokens(postal_parts)
    if not postal_joined:
        return line_text

    # 3) Append only if line ends with 3-char prefix like "M4K" and tail isn't already included
    if re.search(r"\b[A-Z]\d[A-Z]$", line_text.upper()) and postal_joined.upper() not in line_text.upper():
        return _clean(f"{line_text} {postal_joined}")

    # If we already have a full postal code somewhere, don't append anything
    if re.search(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", line_text.upper()):
        return line_text

    return line_text


def parse_service_quote(pdf_bytes: bytes) -> ServiceQuoteData:
    """
    Service Quote parser using word-based extraction (PyMuPDF via text_extract.py).
    """
    words = extract_words(pdf_bytes)
    text = _normalize_text(words_to_text(words))

    data = ServiceQuoteData(items=[])

    # Header fields (anchors)
    data.client_name = _between(text, "Attn:", "Date:")
    data.client_phone = _between(text, "Phone:", "Re:")
    data.client_email = _between(text, "Email:", "Estimate")

    data.quote_date = _after_same_line(text, "Date:")

    m = re.search(r"Estimate\s*#\s*:\s*([A-Za-z0-9\-]+)", text, flags=re.I)
    if m:
        data.quote_number = _clean(m.group(1))

    # Company/Property names:
    # "Company: <company> Property: <property>"
    m = re.search(r"Company\s*:\s*(?P<company>.*?)\s+Property\s*:\s*(?P<prop>[^\n]+)", text, flags=re.I)
    if m:
        data.company_name = _clean(m.group("company"))
        data.property_name = _clean(m.group("prop"))
    else:
        data.company_name = _after_same_line(text, "Company:")
        data.property_name = _after_same_line(text, "Property:")

    # ✅ Addresses from word tokens (column-aware) + safety-net postal append
    data.company_address = _extract_address_by_columns(words, "company")
    data.property_address = _extract_address_by_columns(words, "property")

    # Scope of work (keep blank if empty)
    m = re.search(r"SCOPE OF WORK\s*(?P<scope>.*?)\bSPECIFIC INCLUSIONS\b", text, flags=re.I | re.S)
    if m:
        scope = _clean(m.group("scope"))
        scope = re.sub(r"\n{2,}", "\n", scope).strip()
        data.quote_description = scope or ""

    # Items + bullet descriptions under SPECIFIC INCLUSIONS
    body = ""
    m = re.search(r"SPECIFIC INCLUSIONS\s*(?P<body>.*?)\bQUALIFICATIONS\b", text, flags=re.I | re.S)
    if m:
        body = m.group("body") or ""

    lines = [_clean(x) for x in body.splitlines() if _clean(x)]

    item_header = re.compile(r"^(?P<name>.+?)\s+\$?\s*(?P<amt>[0-9,]+\.[0-9]{2})\s*$")
    bullet = re.compile(r"^\-\s*(?P<txt>.+)$")

    current: Optional[SQLine] = None
    for line in lines:
        mh = item_header.match(line)
        if mh:
            if current:
                current.description = current.description.strip()
                data.items.append(current)

            current = SQLine(
                name=_clean(mh.group("name")),
                price=_money_decimal(mh.group("amt")),
                description="",
            )
            continue

        mb = bullet.match(line)
        if mb and current:
            txt = _clean(mb.group("txt"))
            if txt:
                current.description += txt + "\n"

    if current:
        current.description = current.description.strip()
        data.items.append(current)

    # Total (from "Total Proposal ... $6,843.37")
    m = re.search(r"Total Proposal.*?\$\s*(?P<amt>[0-9,]+\.[0-9]{2})", text, flags=re.I)
    if m:
        data.total = str(_money_decimal(m.group("amt")))

    # Compute subtotal/tax/total from items (13% HST)
    if data.items:
        subtotal = sum((x.price or Decimal("0.00")) for x in data.items)
        tax = (subtotal * Decimal("0.13")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = (subtotal + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        data.subtotal = str(subtotal)
        data.tax = str(tax)
        if not data.total:
            data.total = str(total)

    return data