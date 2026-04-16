# app/styling/invoice/build_data.py
from __future__ import annotations

from typing import Any, Dict

from app.invoice_lookup import get_invoice_id_by_number
from app.services.snowflake import get_property_details_for_customer
from app.styling.invoice.mapper import map_buildops_invoice_to_pdf_data


def build_invoice_pdf_data_from_number(bo, invoice_number: str) -> Dict[str, Any]:
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

    snowflake_property = None
    if billing_customer_id and prop_id:
        try:
            snowflake_property = get_property_details_for_customer(
                customer_id=str(billing_customer_id).strip(),
                property_id=str(prop_id).strip(),
            )
        except Exception as e:
            print(
                f"[invoice build] Snowflake property lookup failed "
                f"for customer_id={billing_customer_id}, property_id={prop_id}: {e}"
            )

    normalized = map_buildops_invoice_to_pdf_data(
        invoice,
        customer=customer,
        property_obj=property_obj,
        snowflake_property=snowflake_property,
    )

    # Make ids available downstream for recipient resolution
    normalized["customerPropertyId"] = prop_id
    normalized["billingCustomerId"] = billing_customer_id

    # Existing BuildOps invoice metadata
    normalized["buildops_invoice_id"] = invoice_id
    normalized["buildops_invoice_number"] = str(invoice_number).strip()

    return normalized