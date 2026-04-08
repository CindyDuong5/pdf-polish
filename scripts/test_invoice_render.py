# scripts/test_invoice_render.py
from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

print("ENV_PATH =", ENV_PATH)
print("BUILDOPS_TENANT_ID =", os.getenv("BUILDOPS_TENANT_ID"))

from app.buildops_client import BuildOpsClient
from app.styling.invoice.mapper import map_buildops_invoice_to_pdf_data
from app.styling.invoice.renderer import render_invoice_styled_draft


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _to_float(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(str(v).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0


def _recalc_totals(normalized: dict) -> dict:
    """
    Recalculate summary totals after forcing labor/parts rows on/off
    or overriding service fee / discount, so the PDF matches what is rendered.
    """
    labor_total = sum(_to_float(r.get("price")) for r in (normalized.get("labor_rows") or []))
    parts_total = sum(_to_float(r.get("price")) for r in (normalized.get("parts_rows") or []))
    service_fee = _to_float(normalized.get("service_fee"))
    discount = _to_float(normalized.get("discount"))
    tax_rate_raw = str(normalized.get("sales_tax_rate") or "13").replace("%", "").strip()
    tax_rate = (_to_float(tax_rate_raw) or 13.0) / 100.0

    taxable_subtotal = parts_total
    subtotal = labor_total + parts_total
    subtotal_after_discount_fees = subtotal + service_fee - discount
    tax_amount = round(taxable_subtotal * tax_rate, 2)
    total = round(subtotal_after_discount_fees + tax_amount, 2)
    amount_paid = _to_float(normalized.get("amount_paid"))
    balance = round(total - amount_paid, 2)

    normalized["subtotal"] = _money(subtotal)
    normalized["taxable_subtotal"] = _money(taxable_subtotal)
    normalized["subtotal_after_discount_fees"] = _money(subtotal_after_discount_fees)
    normalized["tax_amount"] = _money(tax_amount)
    normalized["total"] = _money(total)
    normalized["amount_paid"] = _money(amount_paid)
    normalized["balance"] = _money(balance)

    return normalized


def _expand_rows_for_multipage(normalized: dict, multiply_rows: int) -> dict:
    """
    Duplicate labor/parts rows so the rendered invoice spills onto multiple pages.

    Example:
      multiply_rows=3 -> original rows repeated 3 times
    """
    if multiply_rows <= 1:
        return normalized

    base_labor = [deepcopy(r) for r in (normalized.get("labor_rows") or [])]
    base_parts = [deepcopy(r) for r in (normalized.get("parts_rows") or [])]

    expanded_labor = []
    expanded_parts = []

    for i in range(multiply_rows):
        for row in base_labor:
            new_row = deepcopy(row)
            desc = str(new_row.get("description") or "").strip()
            if desc:
                new_row["description"] = f"{desc} (test set {i + 1})"
            expanded_labor.append(new_row)

        for row in base_parts:
            new_row = deepcopy(row)
            desc = str(new_row.get("description") or "").strip()
            if desc:
                new_row["description"] = f"{desc} (test set {i + 1})"
            expanded_parts.append(new_row)

    normalized["labor_rows"] = expanded_labor
    normalized["parts_rows"] = expanded_parts
    return normalized


def _apply_test_mode(
    normalized: dict,
    *,
    force_no_labor: bool = False,
    force_no_parts: bool = False,
    service_fee_override: Optional[float] = None,
    discount_override: Optional[float] = None,
    force_paid: bool = False,
    amount_paid_override: Optional[float] = None,
    multiply_rows: int = 1,
) -> dict:
    """
    Modify mapped invoice data for layout testing.

    force_no_labor=True           -> removes all labor rows
    force_no_parts=True           -> removes all parts rows
    service_fee_override=number   -> overrides service_fee
    discount_override=number      -> overrides discount
    force_paid=True               -> sets amount_paid = total and balance = 0
    amount_paid_override=number   -> sets a custom amount paid after totals recalc
    multiply_rows=N               -> repeats rows N times to force multi-page testing
    """
    if force_no_labor:
        normalized["labor_rows"] = []

    if force_no_parts:
        normalized["parts_rows"] = []

    if service_fee_override is not None:
        normalized["service_fee"] = _money(service_fee_override)

    if discount_override is not None:
        normalized["discount"] = _money(discount_override)

    normalized = _expand_rows_for_multipage(normalized, multiply_rows)
    normalized = _recalc_totals(normalized)

    total = _to_float(normalized.get("total"))

    if force_paid:
        normalized["amount_paid"] = _money(total)
        normalized["balance"] = _money(0.0)
        return normalized

    if amount_paid_override is not None:
        balance = round(total - amount_paid_override, 2)
        normalized["amount_paid"] = _money(amount_paid_override)
        normalized["balance"] = _money(balance)
        return normalized

    return normalized


def _build_normalized_invoice(invoice_number: str) -> dict:
    bo = BuildOpsClient()

    invoice = bo.get_invoice_by_number(invoice_number)

    customer = None
    customer_id = invoice.get("customerId") or invoice.get("billingCustomerId")
    if customer_id:
        customer = bo.get_customer_by_id(customer_id)

    prop = None
    property_id = invoice.get("propertyId") or invoice.get("customerPropertyId")
    if property_id and hasattr(bo, "get_property_by_id"):
        prop = bo.get_property_by_id(property_id)

    normalized = map_buildops_invoice_to_pdf_data(
        invoice,
        customer=customer,
        property_obj=prop,
    )
    return normalized


def _render_pdf(normalized: dict, output_name: str):
    logo_path = ROOT / "templates" / "email-assets" / "Mainline-Primary-Logo-Black.png"

    pdf_bytes = render_invoice_styled_draft(
        normalized,
        logo_path=str(logo_path) if logo_path.exists() else None,
    )

    out = ROOT / "tmp" / output_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)
    print("✅ wrote:", out)
    print("   labor rows =", len(normalized.get("labor_rows") or []))
    print("   parts rows =", len(normalized.get("parts_rows") or []))
    print("   total      =", normalized.get("total"))
    print("   amount_paid=", normalized.get("amount_paid"))
    print("   balance    =", normalized.get("balance"))


def main(
    invoice_number: str,
    *,
    force_no_labor: bool = False,
    force_no_parts: bool = False,
    service_fee_override: Optional[float] = None,
    discount_override: Optional[float] = None,
    force_paid: bool = False,
    amount_paid_override: Optional[float] = None,
    multiply_rows: int = 1,
):
    normalized = _build_normalized_invoice(invoice_number)

    normalized = _apply_test_mode(
        normalized,
        force_no_labor=force_no_labor,
        force_no_parts=force_no_parts,
        service_fee_override=service_fee_override,
        discount_override=discount_override,
        force_paid=force_paid,
        amount_paid_override=amount_paid_override,
        multiply_rows=multiply_rows,
    )

    suffix_parts = []
    if force_no_labor:
        suffix_parts.append("no-labor")
    if force_no_parts:
        suffix_parts.append("no-parts")
    if service_fee_override is not None:
        suffix_parts.append(f"service-fee-{service_fee_override:g}")
    if discount_override is not None:
        suffix_parts.append(f"discount-{discount_override:g}")
    if multiply_rows > 1:
        suffix_parts.append(f"rows-x{multiply_rows}")
    if force_paid:
        suffix_parts.append("paid")
    elif amount_paid_override is not None:
        suffix_parts.append(f"amount-paid-{amount_paid_override:g}")

    suffix = "-" + "-".join(suffix_parts) if suffix_parts else ""
    output_name = f"invoice-{invoice_number}-styled_draft{suffix}-test.pdf"

    _render_pdf(normalized, output_name)


def test_fee_discount_cases(
    invoice_number: str,
    *,
    force_no_labor: bool = False,
    force_no_parts: bool = False,
    force_paid: bool = False,
    multiply_rows: int = 1,
):
    """
    Render 4 PDFs to test totals block visibility:

    1) service fee = 0, discount = 0
    2) service fee > 0, discount = 0
    3) service fee = 0, discount > 0
    4) service fee > 0, discount > 0
    """
    base_normalized = _build_normalized_invoice(invoice_number)

    cases = [
        {"label": "fee-0_discount-0", "service_fee": 0.0, "discount": 0.0},
        {"label": "fee-25_discount-0", "service_fee": 25.0, "discount": 0.0},
        {"label": "fee-0_discount-25", "service_fee": 0.0, "discount": 25.0},
        {"label": "fee-25_discount-25", "service_fee": 25.0, "discount": 25.0},
    ]

    for case in cases:
        normalized = deepcopy(base_normalized)

        normalized = _apply_test_mode(
            normalized,
            force_no_labor=force_no_labor,
            force_no_parts=force_no_parts,
            service_fee_override=case["service_fee"],
            discount_override=case["discount"],
            force_paid=force_paid,
            multiply_rows=multiply_rows,
        )

        suffix_parts = [case["label"]]
        if force_no_labor:
            suffix_parts.append("no-labor")
        if force_no_parts:
            suffix_parts.append("no-parts")
        if multiply_rows > 1:
            suffix_parts.append(f"rows-x{multiply_rows}")
        if force_paid:
            suffix_parts.append("paid")

        suffix = "-".join(suffix_parts)
        output_name = f"invoice-{invoice_number}-styled_draft-{suffix}-test.pdf"

        _render_pdf(normalized, output_name)


if __name__ == "__main__":
    inv = sys.argv[1] if len(sys.argv) > 1 else "1013"
    args = [a.strip().lower() for a in sys.argv[2:]]
    args_set = set(args)

    def _read_float_flag(flag_name: str) -> Optional[float]:
        for i, arg in enumerate(args):
            if arg == flag_name and i + 1 < len(args):
                try:
                    return float(args[i + 1])
                except Exception:
                    raise ValueError(f"Invalid number passed after {flag_name}")
            if arg.startswith(flag_name + "="):
                try:
                    return float(arg.split("=", 1)[1])
                except Exception:
                    raise ValueError(f"Invalid number passed in {arg}")
        return None

    def _read_int_flag(flag_name: str, default: int = 1) -> int:
        for i, arg in enumerate(args):
            if arg == flag_name and i + 1 < len(args):
                try:
                    return max(1, int(args[i + 1]))
                except Exception:
                    raise ValueError(f"Invalid integer passed after {flag_name}")
            if arg.startswith(flag_name + "="):
                try:
                    return max(1, int(arg.split("=", 1)[1]))
                except Exception:
                    raise ValueError(f"Invalid integer passed in {arg}")
        return default

    service_fee_override = _read_float_flag("--service-fee")
    discount_override = _read_float_flag("--discount")
    amount_paid_override = _read_float_flag("--amount-paid")
    multiply_rows = _read_int_flag("--multiply-rows", default=1)
    force_paid = "--paid" in args_set

    if "--test-fee-discount-cases" in args_set:
        test_fee_discount_cases(
            inv,
            force_no_labor="--no-labor" in args_set,
            force_no_parts="--no-parts" in args_set,
            force_paid=force_paid,
            multiply_rows=multiply_rows,
        )
    else:
        main(
            inv,
            force_no_labor="--no-labor" in args_set,
            force_no_parts="--no-parts" in args_set,
            service_fee_override=service_fee_override,
            discount_override=discount_override,
            force_paid=force_paid,
            amount_paid_override=amount_paid_override,
            multiply_rows=multiply_rows,
        )