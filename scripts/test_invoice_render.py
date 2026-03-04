# scripts/test_invoice_render.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

print("ENV_PATH =", ENV_PATH)
print("BUILDOPS_TENANT_ID =", os.getenv("BUILDOPS_TENANT_ID"))

from app.buildops_client import BuildOpsClient
from app.styling.invoice.mapper import map_buildops_invoice_to_pdf_data
from app.styling.invoice.renderer import render_invoice_styled_draft


def _fill_defaults(normalized: dict) -> dict:
    """
    Fill empty fields with sample data so the test PDF shows a "complete" layout.
    Does NOT overwrite real values.
    """
    def put(k: str, v):
        if normalized.get(k) in (None, "", [], {}):
            normalized[k] = v

    put("billClient_name", "Example Client Co.")
    put("billClient_address_lines", ["123 Example St", "Toronto, ON M5V 2T6 CA"])
    put("billClient_phone", "416-555-0101")
    put("billClient_email", "ap@example.com")

    put("invoice_number", "1013")
    put("issued_date", "Mar 02, 2026")
    put("due_date", "Apr 01, 2026")
    put("job_number", "1022")
    put("po_number", "PO-12345")

    put("customer_name", normalized.get("billClient_name") or "Example Client Co.")
    put("property_name", "Example Property Name")
    put("property_address_lines", ["123 Example St", "Toronto, ON M5V 2T6", "CA"])

    put("authorized_by", "Nick")
    put("customerProvidedWONumber", "WO-7788")
    put("nte", "$2,500.00")

    
    # -------------------------
    # Sample rows (append for testing)
    # -------------------------
    sample_labor = [
        {"date":"Mar 02, 2026","name":"Service Call","description":"Troubleshoot signal and confirm proper communications. Includes travel + diagnostics.","taxable":False,"hours":1.5,"rate":105.0,"price":157.50},
        {"date":"Mar 02, 2026","name":"Deficiency Repair","description":"Replace missing label and secure loose device mount. Verify device operation after repair.","taxable":False,"hours":2.0,"rate":105.0,"price":210.0},
        {"date":"Mar 03, 2026","name":"Programming","description":"Update zone description(s) and test system operation with end user.","taxable":False,"hours":1.0,"rate":105.0,"price":105.0},
    ]

    sample_parts = [
        {"date":"Mar 02, 2026","name":"Smoke Detector","code":"SD-200","description":"Photoelectric smoke detector replacement head.","taxable":True,"qty":2.0,"unit_price":48.50,"price":97.00},
        {"date":"Mar 02, 2026","name":"Module","code":"MOD-1","description":"Input module for monitoring device circuit (includes labeling & termination).","taxable":True,"qty":1.0,"unit_price":79.95,"price":79.95},
        {"date":"Mar 03, 2026","name":"Batteries","code":"BAT-12V","description":"12V sealed lead acid batteries (pair) for fire alarm panel standby power.","taxable":True,"qty":1.0,"unit_price":68.00,"price":68.00},
        {"date":"Mar 03, 2026","name":"Batteries","code":"BAT-12V","description":"12V sealed lead acid batteries (pair) for fire alarm panel standby power.","taxable":True,"qty":1.0,"unit_price":68.00,"price":68.00},
    ]

    normalized.setdefault("labor_rows", [])
    normalized.setdefault("parts_rows", [])

    # ✅ append instead of overwrite
    normalized["labor_rows"].extend(sample_labor)
    normalized["parts_rows"].extend(sample_parts)

    # Optional stress test:
    # normalized["labor_rows"] = normalized["labor_rows"] * 4
    # normalized["parts_rows"] = normalized["parts_rows"] * 4
    # totals (if mapper didn't compute them for some reason)
    put("subtotal", "$913.50")
    put("service_fee", "$5.00")
    put("discount", "$0.00")
    put("subtotal_after_discount_fees", "$918.50")
    put("taxable_subtotal", "$283.50")
    put("sales_tax_rate", "13%")
    put("tax_amount", "$36.86")
    put("total", "$955.36")
    put("amount_paid", "$0.00")
    put("balance", normalized.get("total") or "$955.36")

    return normalized

def main(invoice_number: str):
    bo = BuildOpsClient()

    invoice = bo.get_invoice_by_number(invoice_number)
    customer = bo.get_customer_by_id(invoice.get("customerId")) if invoice.get("customerId") else None
    prop = bo.get_property_by_id(invoice.get("propertyId")) if invoice.get("propertyId") else None

    normalized = map_buildops_invoice_to_pdf_data(invoice, customer=customer, property_obj=prop)
    normalized = _fill_defaults(normalized)

    logo_path = ROOT / "templates/fonts/Mainline-Primary-Logo-Black.png"
    pdf_bytes = render_invoice_styled_draft(
        normalized,
        logo_path=str(logo_path) if logo_path.exists() else None,
    )

    out = ROOT / f"tmp/invoice-{invoice_number}-styled_draft.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)
    print("✅ wrote:", out)


if __name__ == "__main__":
    inv = sys.argv[1] if len(sys.argv) > 1 else "1013"
    main(inv)