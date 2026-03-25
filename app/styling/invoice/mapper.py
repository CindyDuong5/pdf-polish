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
            # fallback: local time (shouldn't happen in your env)
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
    Customer payload shape you pasted:
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

        # "Toronto, ON M5T 1L9"
    city_line = ""
    if city and state:
        city_line = f"{city}, {state}"
    elif city:
        city_line = city
    elif state:
        city_line = state

    if zipcode:
        city_line = f"{city_line} {zipcode}".strip()

    # ✅ if country exists, keep it on the same line (append at end)
    if country:
        country = str(country).strip()
        if country:
            city_line = f"{city_line} {country}".strip()

    if city_line:
        lines.append(city_line)

    return lines


def _extract_customer_phone_email(customer: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Per your customer payload: phonePrimary + email
    """
    if not customer:
        return "", ""
    phone = (customer.get("phonePrimary") or "").strip()
    email = (customer.get("email") or "").strip()
    return phone, email


def _extract_property_name_and_address(property_obj: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """
    Property payload (per your sample) uses companyName for the display name.
    """
    if not property_obj:
        return "", []

    name = (
        property_obj.get("companyName")
        or property_obj.get("name")
        or property_obj.get("propertyName")
        or property_obj.get("displayName")
        or ""
    )

    # In your sample, property has "addresses": [ ... ]
    addr_obj = None
    addrs = property_obj.get("addresses")
    if isinstance(addrs, list) and addrs:
        # Prefer propertyAddress if present, else first
        for a in addrs:
            if (a or {}).get("addressType") == "propertyAddress":
                addr_obj = a
                break
        if not addr_obj:
            addr_obj = addrs[0]

    # Some APIs return property_obj["address"] instead
    if not addr_obj and isinstance(property_obj.get("address"), dict):
        addr_obj = property_obj["address"]

    lines = _format_address_lines(addr_obj)

    return str(name or "").strip(), lines

def _normalize_summary(summary: Any) -> str:
    """
    Keep line breaks from BuildOps, but normalize whitespace safely.
    """
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

        # Best source for invoice-specific paid amount
        if applied not in (None, ""):
            total += _to_float(applied)
        else:
            total += _to_float(payment_amount)

    return total

def map_buildops_invoice_to_pdf_data(
    invoice: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
    property_obj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize BuildOps invoice payload into a single dict for your invoice PDF renderer.

    Rules you specified:
      - Bill To name/address from addresses[billingAddress] (invoice preferred, else customer billingAddress)
      - Bill phone/email from customer: email + phonePrimary
      - Service Fee is sum(invoiceItems where lineItemType == "Fee")
      - Discount is sum(invoiceItems where lineItemType == "Discount") (shown as positive; renderer can add '-' sign)
      - Labor table: lineItemType == "LaborLineItem"
      - Everything else (except Fee/Discount) -> Parts/Materials table
      - Dates: issuedDate/dueDate epoch seconds -> formatted date
      - Totals: use BuildOps invoice totals as source of truth (no recompute)
    """

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
    # PROPERTY (prefer property endpoint; else invoice propertyAddress)
    # -------------------------
    prop_name, prop_lines = _extract_property_name_and_address(property_obj)

    invoice_property_addr = _pick_invoice_address(invoice, "propertyAddress")
    if not prop_lines:
        prop_lines = _format_address_lines(invoice_property_addr)

    if not prop_name:
        # You can change this later once property endpoint is stable
        # For now, best available display name:
        prop_name = (invoice_property_addr or {}).get("addressLine1") or invoice.get("customerName") or ""

    # -------------------------
    # INVOICE META
    # -------------------------
    invoice_number = str(invoice.get("invoiceNumber") or "").strip()
    issued_date = _fmt_date_from_epoch_seconds(invoice.get("issuedDate"))
    issued_date_iso = _iso_date_from_epoch_seconds(invoice.get("issuedDate"))
    due_date = _fmt_date_from_epoch_seconds(invoice.get("dueDate"))
    job_number = str(invoice.get("jobNumber") or "").strip()

    customer_name = str(invoice.get("customerName") or bill_client_name or "").strip()
    authorized_by = str(invoice.get("authorizedBy") or "").strip()
    po_number = str(invoice.get("customerProvidedPONumber") or "").strip()
    wo_number = str(invoice.get("customerProvidedWONumber") or "").strip()

    nte_val = _to_float(invoice.get("amountNotToExceed"))
    nte = _fmt_money(nte_val) if nte_val else ""

    # ✅ NEW
    invoice_summary = _normalize_summary(invoice.get("summary"))

    # -------------------------
    # ITEMS: labor / parts + adjustments
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

        # You can switch this later to item audit date if needed.
        line_date = issued_date_iso or issued_date

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

        # Default: treat as parts/materials/other line item
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
    # TOTALS (BuildOps is source of truth)
    # -------------------------
    subtotal = _to_float(invoice.get("subtotal"))
    taxable_subtotal = _to_float(invoice.get("taxableSubtotal"))
    tax_amount = _to_float(invoice.get("taxAmount"))
    total_amount = _to_float(invoice.get("totalAmount"))
    sales_tax_rate = _to_float(invoice.get("salesTaxRate"))  # typically "13"

    # Prefer top-level discount if present, else use Discount line item total
    top_level_discount = _to_float(invoice.get("discount"))
    discount_for_pdf = top_level_discount if top_level_discount != 0 else discount_total

    subtotal_after_discount_fees = subtotal + service_fee_total - discount_for_pdf

    # Payments
    amount_paid = _extract_amount_paid(invoice)
    balance = round(total_amount - amount_paid, 2)
    if abs(balance) < 0.005:
        balance = 0.0

    return {
        # Bill To
        "billClient_name": bill_client_name,
        "billClient_address_lines": bill_client_address_lines,
        "billClient_phone": bill_phone,
        "billClient_email": bill_email,

        # Invoice meta
        "invoice_number": invoice_number,
        "issued_date": issued_date,
        "issued_date_iso": issued_date_iso,
        "due_date": due_date,
        "job_number": job_number,
        "po_number": po_number,

        # Customer / Property block
        "customer_name": customer_name,
        "property_name": str(prop_name or "").strip(),
        "property_address_lines": prop_lines,
        "authorized_by": authorized_by,
        "customerProvidedWONumber": wo_number,
        "nte": nte,

        # ✅ NEW
        "invoice_summary": invoice_summary,

        # Tables
        "labor_rows": labor_rows,
        "parts_rows": parts_rows,

        # Totals (strings ready to print)
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