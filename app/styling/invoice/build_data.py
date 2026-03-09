# app/styling/invoice/build_data.py
from __future__ import annotations

from typing import Any, Dict

from app.invoice_lookup import get_invoice_id_by_number
from app.styling.invoice.mapper import map_buildops_invoice_to_pdf_data


def build_invoice_pdf_data_from_number(bo, invoice_number: str) -> Dict[str, Any]:
    """
    bo must expose:
      - get_invoice_by_id(invoice_id)
      - get_customer_by_id(customer_id)
      - optionally get_property_by_id(property_id)
    """
    invoice_id = get_invoice_id_by_number(invoice_number)

    invoice = bo.get_invoice_by_id(invoice_id)

    customer = None
    billing_customer_id = invoice.get("billingCustomerId")
    if billing_customer_id:
        customer = bo.get_customer_by_id(billing_customer_id)

    property_obj = None
    prop_id = invoice.get("customerPropertyId")
    if prop_id and hasattr(bo, "get_property_by_id"):
        property_obj = bo.get_property_by_id(prop_id)

    normalized = map_buildops_invoice_to_pdf_data(
        invoice,
        customer=customer,
        property_obj=property_obj,
)

    # ✅ IMPORTANT: store BuildOps invoice id so we can request payment link later
    normalized["buildops_invoice_id"] = invoice_id
    normalized["buildops_invoice_number"] = str(invoice_number).strip()

    return normalized