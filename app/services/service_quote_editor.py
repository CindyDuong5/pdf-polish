# app/services/service_quote_editor.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List

from app.styling.service_quote.parser import ServiceQuoteData, SQLine

HST_RATE = Decimal("0.13")


def _dec(s: Any) -> Decimal:
    t = str(s or "").replace("$", "").replace(",", "").strip()
    if not t:
        return Decimal("0.00")
    return Decimal(t).quantize(Decimal("0.01"))


def _money_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, Decimal):
        return str(x.quantize(Decimal("0.01")))
    return str(x).strip()


def service_quote_to_json(doc: ServiceQuoteData) -> dict:
    return {
        "client_name": doc.client_name or "",
        "client_phone": doc.client_phone or "",
        "client_email": doc.client_email or "",
        "company_name": doc.company_name or "",
        "company_address": doc.company_address or "",
        "property_name": doc.property_name or "",
        "property_address": doc.property_address or "",
        "quote_number": doc.quote_number or "",
        "quote_date": doc.quote_date or "",
        "quote_description": doc.quote_description or "",
        "items": [
            {"name": it.name or "", "price": _money_str(it.price), "description": it.description or ""}
            for it in (doc.items or [])
        ],
        "subtotal": str(doc.subtotal or ""),
        "tax": str(doc.tax or ""),
        "total": str(doc.total or ""),
    }


def normalize_service_quote_fields(fields: dict) -> dict:
    """
    Always compute subtotal/tax/total from item prices.
    (Frontend also computes, but backend enforces consistency.)
    """
    items = fields.get("items") or []
    subtotal = Decimal("0.00")
    for it in items:
        subtotal += _dec((it or {}).get("price"))

    tax = (subtotal * HST_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (subtotal + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    fields["subtotal"] = str(subtotal)
    fields["tax"] = str(tax)
    fields["total"] = str(total)

    return fields

def json_to_service_quote(j: dict) -> ServiceQuoteData:
    def dec_or_none(s: str | None) -> Decimal | None:
        if s is None:
            return None
        t = str(s).replace("$", "").replace(",", "").strip()
        if not t:
            return None
        return Decimal(t).quantize(Decimal("0.01"))

    items: List[SQLine] = []
    for x in (j.get("items") or []):
        items.append(
            SQLine(
                name=(x.get("name") or ""),
                price=dec_or_none(x.get("price")),
                description=(x.get("description") or ""),
            )
        )

    return ServiceQuoteData(
        client_name=j.get("client_name", "") or "",
        client_phone=j.get("client_phone", "") or "",
        client_email=j.get("client_email", "") or "",
        company_name=j.get("company_name", "") or "",
        company_address=j.get("company_address", "") or "",
        property_name=j.get("property_name", "") or "",
        property_address=j.get("property_address", "") or "",
        quote_number=j.get("quote_number", "") or "",
        quote_date=j.get("quote_date", "") or "",
        quote_description=j.get("quote_description", "") or "",
        items=items,
        subtotal=j.get("subtotal", "") or "",
        tax=j.get("tax", "") or "",
        total=j.get("total", "") or "",
    )