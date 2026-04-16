# app/styling/invoice/mapper.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    # py3.9+
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


TORONTO_TZ = ZoneInfo("America/Toronto") if ZoneInfo else None


def _to_float(v: Any) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _fmt_money(v: Any) -> str:
    n = _to_float(v)
    return f"${n:,.2f}"


def _fmt_date_from_epoch_seconds(v: Any) -> str:
    """
    BuildOps invoice fields like issuedDate/dueDate often come as epoch seconds string:
      "1772454684"
    Render in America/Toronto.
    """
    if v is None or v == "":
        return ""
    try:
        sec = int(str(v).strip())
        if TORONTO_TZ:
            dt = datetime.fromtimestamp(sec, tz=TORONTO_TZ)
        else:
            dt = datetime.fromtimestamp(sec)
        return dt.strftime("%b %d, %Y")
    except Exception:
        return ""


def _iso_date_from_epoch_seconds(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        sec = int(str(v).strip())
        if TORONTO_TZ:
            dt = datetime.fromtimestamp(sec, tz=TORONTO_TZ)
        else:
            dt = datetime.fromtimestamp(sec)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _pick_invoice_address(invoice: Dict[str, Any], address_type: str) -> Optional[Dict[str, Any]]:
    for a in (invoice.get("addresses") or []):
        if (a or {}).get("addressType") == address_type:
            return a
    return None


def _pick_customer_address(customer: Dict[str, Any], address_type: str) -> Optional[Dict[str, Any]]:
    """
    Customer payload shape:
      customer["addresses"]["items"] = [ { addressType: "billingAddress", ... } ]
    """
    addr = customer.get("addresses") or {}
    items = addr.get("items") or []
    for a in items:
        if (a or {}).get("addressType") == address_type:
            return a
    return None


def _format_address_lines(a: Optional[Dict[str, Any]]) -> List[str]:
    """
    Accepts either invoice address object or customer address object.
    """
    if not a:
        return []

    line1 = (a.get("addressLine1") or "").strip()
    line2 = (a.get("addressLine2") or "").strip()
    city = (a.get("city") or "").strip()
    state = (a.get("state") or "").strip()
    zipcode = (a.get("zipcode") or "").strip()
    country = (a.get("country") or "").strip()

    lines: List[str] = []
    if line1:
        lines.append(line1)
    if line2:
        lines.append(line2)

    city_line = ""
    if city and state:
        city_line = f"{city}, {state}"
    elif city:
        city_line = city
    elif state:
        city_line = state

    if zipcode:
        city_line = f"{city_line} {zipcode}".strip()

    if country:
        country = str(country).strip()
        if country:
            city_line = f"{city_line} {country}".strip()

    if city_line:
        lines.append(city_line)

    return lines


def _extract_customer_phone_email(customer: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not customer:
        return "", ""
    phone = (customer.get("phonePrimary") or "").strip()
    email = (customer.get("email") or "").strip()
    return phone, email


def _extract_property_name_and_address(property_obj: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]:
    if not property_obj:
        return "", []

    name = (
        property_obj.get("companyName")
        or property_obj.get("name")
        or property_obj.get("propertyName")
        or property_obj.get("displayName")
        or ""
    )

    addr_obj = None
    addrs = property_obj.get("addresses")
    if isinstance(addrs, list) and addrs:
        for a in addrs:
            if (a or {}).get("addressType") == "propertyAddress":
                addr_obj = a
                break
        if not addr_obj:
            addr_obj = addrs[0]

    if not addr_obj and isinstance(property_obj.get("address"), dict):
        addr_obj = property_obj["address"]

    lines = _format_address_lines(addr_obj)

    return str(name or "").strip(), lines


def _extract_snowflake_property_name_and_address(
    snowflake_property: Optional[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    if not snowflake_property:
        return "", []

    name = str(snowflake_property.get("property_name") or "").strip()

    line1 = str(snowflake_property.get("property_address") or "").strip()
    city = str(snowflake_property.get("property_city") or "").strip()
    state = str(snowflake_property.get("property_state") or "").strip()
    postal = str(snowflake_property.get("property_postal_code") or "").strip()
    country = str(snowflake_property.get("property_country") or "").strip()

    lines: List[str] = []
    if line1:
        lines.append(line1)

    city_line = ""
    if city and state:
        city_line = f"{city}, {state}"
    elif city:
        city_line = city
    elif state:
        city_line = state

    if postal:
        city_line = f"{city_line} {postal}".strip()

    if country:
        city_line = f"{city_line} {country}".strip()

    if city_line:
        lines.append(city_line)

    return name, lines


def _normalize_summary(summary: Any) -> str:
    if summary is None:
        return ""
    s = str(summary).replace("\r\n", "\n").replace("\r", "\n").strip()
    return s


def _extract_amount_paid(invoice: Dict[str, Any]) -> float:
    total = 0.0
    for p in (invoice.get("payments") or []):
        if not p:
            continue

        applied = p.get("appliedAmount")
        payment_amount = p.get("paymentAmount")

        if applied not in (None, ""):
            total += _to_float(applied)
        else:
            total += _to_float(payment_amount)

    return total


def map_buildops_invoice_to_pdf_data(
    invoice: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
    property_obj: Optional[Dict[str, Any]] = None,
    snowflake_property: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # -------------------------
    # BILL TO (invoice address preferred; fallback to customer)
    # -------------------------
    billing_addr = _pick_invoice_address(invoice, "billingAddress")
    if not billing_addr and customer:
        billing_addr = _pick_customer_address(customer, "billingAddress")

    bill_client_name = (billing_addr or {}).get("billTo") or invoice.get("customerName") or ""
    bill_client_address_lines = _format_address_lines(billing_addr)

    bill_phone, bill_email = _extract_customer_phone_email(customer)

    # -------------------------
    # PROPERTY
    # Priority:
    # 1. BuildOps property endpoint
    # 2. invoice propertyAddress
    # 3. Snowflake fallback
    # -------------------------
    prop_name, prop_lines = _extract_property_name_and_address(property_obj)

    invoice_property_addr = _pick_invoice_address(invoice, "propertyAddress")
    if not prop_lines:
        prop_lines = _format_address_lines(invoice_property_addr)

    sf_prop_name, sf_prop_lines = _extract_snowflake_property_name_and_address(snowflake_property)

    if not prop_name:
        prop_name = sf_prop_name

    if not prop_lines:
        prop_lines = sf_prop_lines

    if not prop_name:
        prop_name = (invoice_property_addr or {}).get("addressLine1") or invoice.get("customerName") or ""

    # -------------------------
    # INVOICE META
    # -------------------------
    invoice_number = str(invoice.get("invoiceNumber") or "").strip()
    issued_date = _fmt_date_from_epoch_seconds(invoice.get("issuedDate"))
    issued_date_iso = _iso_date_from_epoch_seconds(invoice.get("issuedDate"))
    due_date = _fmt_date_from_epoch_seconds(invoice.get("dueDate"))
    job_number = str(invoice.get("jobNumber") or "").strip()

    customer_name = str(
        invoice.get("customerName")
        or (snowflake_property or {}).get("customer_name")
        or bill_client_name
        or ""
    ).strip()

    authorized_by = str(invoice.get("authorizedBy") or "").strip()
    po_number = str(invoice.get("customerProvidedPONumber") or "").strip()
    wo_number = str(invoice.get("customerProvidedWONumber") or "").strip()

    nte_val = _to_float(invoice.get("amountNotToExceed"))
    nte = _fmt_money(nte_val) if nte_val else ""

    invoice_summary = _normalize_summary(invoice.get("summary"))

    # -------------------------
    # ITEMS
    # -------------------------
    labor_rows: List[Dict[str, Any]] = []
    parts_rows: List[Dict[str, Any]] = []

    service_fee_total = 0.0
    discount_total = 0.0

    items = invoice.get("invoiceItems") or []
    for it in items:
        if not it:
            continue

        t = it.get("lineItemType")
        amount = _to_float(it.get("amount"))
        qty = _to_float(it.get("quantity"))
        unit_price = _to_float(it.get("unitPrice"))
        taxable = bool(it.get("taxable"))

        # Use line-specific date if available, otherwise leave blank
        line_date = _iso_date_from_epoch_seconds(it.get("date")) or ""

        if t == "Fee":
            service_fee_total += amount
            continue

        if t == "Discount":
            discount_total += abs(amount)
            continue

        if t == "LaborLineItem":
            labor_rows.append(
                {
                    "date": line_date,
                    "name": str(it.get("name") or "").strip(),
                    "description": str(it.get("description") or "").strip(),
                    "taxable": taxable,
                    "hours": qty,
                    "rate": unit_price,
                    "price": amount,
                }
            )
            continue

        product = it.get("product") or {}
        parts_rows.append(
            {
                "date": line_date,
                "name": str(it.get("name") or "").strip(),
                "code": str(product.get("code") or "").strip(),
                "description": str(it.get("description") or "").strip(),
                "taxable": taxable,
                "qty": qty,
                "unit_price": unit_price,
                "price": amount,
            }
        )

    # -------------------------
    # TOTALS
    # -------------------------
    subtotal = _to_float(invoice.get("subtotal"))
    taxable_subtotal = _to_float(invoice.get("taxableSubtotal"))
    tax_amount = _to_float(invoice.get("taxAmount"))
    total_amount = _to_float(invoice.get("totalAmount"))
    sales_tax_rate = _to_float(invoice.get("salesTaxRate"))

    top_level_discount = _to_float(invoice.get("discount"))
    discount_for_pdf = top_level_discount if top_level_discount != 0 else discount_total

    subtotal_after_discount_fees = subtotal + service_fee_total - discount_for_pdf

    amount_paid = _extract_amount_paid(invoice)
    balance = round(total_amount - amount_paid, 2)
    if abs(balance) < 0.005:
        balance = 0.0

    return {
        "billClient_name": bill_client_name,
        "billClient_address_lines": bill_client_address_lines,
        "billClient_phone": bill_phone,
        "billClient_email": bill_email,

        "invoice_number": invoice_number,
        "issued_date": issued_date,
        "issued_date_iso": issued_date_iso,
        "due_date": due_date,
        "job_number": job_number,
        "po_number": po_number,

        "customer_name": customer_name,
        "property_name": str(prop_name or "").strip(),
        "property_address_lines": prop_lines,
        "authorized_by": authorized_by,
        "customerProvidedWONumber": wo_number,
        "nte": nte,

        "invoice_summary": invoice_summary,
        "hide_labor": False,
        "hide_parts": False,

        "labor_rows": labor_rows,
        "parts_rows": parts_rows,

        "subtotal": _fmt_money(subtotal),
        "service_fee": _fmt_money(service_fee_total),
        "discount": _fmt_money(discount_for_pdf),
        "subtotal_after_discount_fees": _fmt_money(subtotal_after_discount_fees),
        "taxable_subtotal": _fmt_money(taxable_subtotal),
        "sales_tax_rate": f"{sales_tax_rate:.0f}%",
        "tax_amount": _fmt_money(tax_amount),
        "total": _fmt_money(total_amount),
        "amount_paid": _fmt_money(amount_paid),
        "balance": _fmt_money(balance),
    }