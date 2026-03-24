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


def _set_stress_value(normalized: dict, key: str, value):
    normalized[key] = value


def _append_stress_rows(normalized: dict, key: str, rows: list[dict]):
    existing = normalized.get(key) or []
    normalized[key] = existing + rows


def _fill_defaults(normalized: dict) -> dict:
    """
    Stress-test long layout fields, but keep invoice_number / job_number / po_number
    short so the top-right invoice meta block can be checked in a realistic layout.
    """

    # ------------------------------------------------------------------
    # Bill To / top section
    # ------------------------------------------------------------------
    _set_stress_value(
        normalized,
        "billClient_name",
        "Innovation, Science and Economic Development Canada - Spectrum Management Operations and Regional Compliance Division",
    )
    _set_stress_value(
        normalized,
        "billClient_address_lines",
        [
            "280 Slater Street West Suite 204, Attention: Accounts Payable and Procurement Administration Department",
            "Government of Canada Finance and Vendor Payment Coordination Centre",
            "Ottawa, Ontario K1A 0C8 Canada",
        ],
    )
    _set_stress_value(
        normalized,
        "billClient_phone",
        "416-305-0704 ext 245 / 647-325-8577 mobile / 1-800-555-0199 secondary contact line",
    )
    _set_stress_value(
        normalized,
        "billClient_email",
        "accounts.payable.invoice.processing.department@very-long-client-example-organization.ca",
    )

    # Keep these short for more realistic positioning test
    _set_stress_value(normalized, "invoice_number", "1013")
    _set_stress_value(normalized, "issued_date", "Mar 02, 2026")
    _set_stress_value(normalized, "due_date", "Apr 01, 2026")
    _set_stress_value(normalized, "job_number", "1022")
    _set_stress_value(normalized, "po_number", "PO-12345")

    # ------------------------------------------------------------------
    # Customer / property grid
    # ------------------------------------------------------------------
    _set_stress_value(
        normalized,
        "customer_name",
        "Innovation, Science and Economic Development Canada - Ontario Regional Operations Fire and Life Safety Program",
    )
    _set_stress_value(
        normalized,
        "property_name",
        "Aurora Research and Training Campus - Main Administration Building, East Mechanical Penthouse and Related Tenant Improvement Areas",
    )
    _set_stress_value(
        normalized,
        "property_address_lines",
        [
            "280 Slater Street West Suite 204 - Innovation, Science and Economic Development Canada Operations Centre",
            "North Service Yard Access Through Building Operations Security Checkpoint",
            "Aurora, Ontario L4G 2N9 CA",
        ],
    )
    _set_stress_value(
        normalized,
        "authorized_by",
        "Nicholas Karalekas, Operations Manager - Fire Alarm, Special Projects, Client Coordination and Field Authorization",
    )
    _set_stress_value(
        normalized,
        "customerProvidedWONumber",
        "WO-7788-ALTERNATE-REFERENCE-SITE-CONTACT-INTERNAL-TRACKING-2026-REV-B",
    )
    _set_stress_value(
        normalized,
        "nte",
        "$2,500.00 Not To Exceed without written authorization from customer project management representative",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _set_stress_value(
        normalized,
        "invoice_summary",
        (
            "50% Deposit invoice for proposal 1006 relating to fire alarm deficiency corrections, system investigation, device replacement, testing, verification and final closeout documentation.\n"
            "Department name: Building Operations, Compliance, Tenant Improvement and Project Delivery Group.\n"
            "Sprinkler / Fire Alarm Scope: Investigation, material replacement, re-labeling, verification, programming adjustments and post-repair system confirmation.\n"
            "Primary technician: Senior fire alarm technician assigned to coordinate field review, deficiency diagnosis and customer communication.\n"
            "Additional technicians: Additional field support may be required depending on access, shutdown coordination and site conditions.\n"
            "Visit Description: Design review, deficiency investigation, repair execution, material installation, testing, customer walkthrough and documentation completion."
        ),
    )

    # ------------------------------------------------------------------
    # Labor rows
    # ------------------------------------------------------------------
    stress_labor = [
        {
            "date": "Mar 02, 2026",
            "name": "Emergency Service Call - Fire Alarm Investigation and Communication Failure Troubleshooting",
            "description": "Troubleshoot fire alarm signal issue, confirm communication path, inspect panel history, verify monitoring connection status, review recent troubles with site contact and document all findings before recommending corrective action.",
            "taxable": False,
            "hours": 1.5,
            "rate": 105.0,
            "price": 157.50,
        },
        {
            "date": "Mar 02, 2026",
            "name": "Deficiency Repair - Device Mounting Correction, Label Replacement and Functional Verification",
            "description": "Replace missing device labeling, secure loose initiating device mounting hardware, confirm wiring termination integrity, re-test repaired components and verify restored operation after all corrective work is completed.",
            "taxable": False,
            "hours": 2.0,
            "rate": 105.0,
            "price": 210.0,
        },
        {
            "date": "Mar 03, 2026",
            "name": "Programming and Documentation Update for Zone Descriptions, Device Mapping and End User Review",
            "description": "Update zone descriptions, confirm panel text accuracy, review device labeling conventions, test revised programming functions and walk the end user through the final corrected operating condition.",
            "taxable": False,
            "hours": 1.0,
            "rate": 105.0,
            "price": 105.0,
        },
        {
            "date": "Mar 03, 2026",
            "name": "Follow-Up Site Review for Access Coordination, Additional Deficiency Confirmation and Client Communication",
            "description": "Attend site for follow-up inspection, coordinate with building representative for restricted area access, confirm scope of remaining deficiencies and prepare notes for quotation, invoicing and service history reference.",
            "taxable": False,
            "hours": 1.75,
            "rate": 105.0,
            "price": 183.75,
        },
        {
            "date": "Mar 04, 2026",
            "name": "Additional Site Attendance for System Retest, Client Walkthrough and Closeout Documentation Review",
            "description": "Return to site to perform final testing after corrective work, review outstanding concerns with the customer representative, confirm acceptance conditions and complete final job documentation for office processing.",
            "taxable": False,
            "hours": 2.25,
            "rate": 105.0,
            "price": 236.25,
        },
    ]

    # ------------------------------------------------------------------
    # Parts rows
    # ------------------------------------------------------------------
    stress_parts = [
        {
            "date": "Mar 02, 2026",
            "name": "Photoelectric Smoke Detector Replacement Head with Matching Base Compatibility",
            "code": "SD-200-PHOTOELECTRIC-SMOKE-DETECTOR-REPLACEMENT-ASSEMBLY",
            "description": "Replacement photoelectric smoke detector head supplied for compatible addressable system base, including labeling, installation, testing and verification of proper device response.",
            "taxable": True,
            "qty": 2.0,
            "unit_price": 48.50,
            "price": 97.00,
        },
        {
            "date": "Mar 02, 2026",
            "name": "Addressable Input Module for Monitoring Device Circuit and Field Interface",
            "code": "MOD-1-ADDRESSABLE-INPUT-MODULE-WITH-TERMINATION-HARDWARE",
            "description": "Input monitoring module provided for supervised field device circuit, including device addressing, circuit termination, mounting, labeling and post-installation functional confirmation.",
            "taxable": True,
            "qty": 1.0,
            "unit_price": 79.95,
            "price": 79.95,
        },
        {
            "date": "Mar 03, 2026",
            "name": "12V Sealed Lead Acid Standby Battery Set for Fire Alarm Control Panel",
            "code": "BAT-12V-STANDBY-POWER-SEALED-LEAD-ACID-REPLACEMENT-PAIR",
            "description": "Replacement standby batteries for fire alarm control panel backup power capacity, including removal of existing batteries, installation of new units and voltage confirmation.",
            "taxable": True,
            "qty": 1.0,
            "unit_price": 68.00,
            "price": 68.00,
        },
        {
            "date": "Mar 03, 2026",
            "name": "Remote Annunciator Identification Labels and Miscellaneous Installation Material Kit",
            "code": "LBL-KIT-REMOTE-ANNUNCIATOR-IDENTIFICATION-MISC-INSTALL-MATERIAL",
            "description": "Labeling material kit used for annunciator identification updates, device marking, minor fastening components and final presentation cleanup after repair completion.",
            "taxable": True,
            "qty": 3.0,
            "unit_price": 22.50,
            "price": 67.50,
        },
        {
            "date": "Mar 04, 2026",
            "name": "Notification Appliance Circuit Hardware and Wire Termination Accessories Package",
            "code": "NAC-HDW-TERM-ACCESSORY-PACK-FOR-FIELD-CORRECTION-WORK",
            "description": "Assorted field accessories used to complete notification appliance circuit corrections, secure wiring terminations, improve installation condition and support final testing.",
            "taxable": True,
            "qty": 2.0,
            "unit_price": 31.25,
            "price": 62.50,
        },
        {
            "date": "Mar 04, 2026",
            "name": "Extended Device Mounting Hardware, Backbox Accessories and Field Adjustment Components",
            "code": "DEVICE-MOUNT-BACKBOX-ADJUSTMENT-HARDWARE-FIELD-CORRECTION-KIT-LONG-CODE",
            "description": "Additional device mounting accessories and field correction materials used to complete alignment adjustments, secure mounting condition and support final verification on site.",
            "taxable": True,
            "qty": 4.0,
            "unit_price": 18.75,
            "price": 75.00,
        },
    ]

    normalized["labor_rows"] = []
    normalized["parts_rows"] = []
    _append_stress_rows(normalized, "labor_rows", stress_labor)
    _append_stress_rows(normalized, "parts_rows", stress_parts)

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------
    _set_stress_value(normalized, "subtotal", "$913.50")
    _set_stress_value(normalized, "service_fee", "$5.00")
    _set_stress_value(normalized, "discount", "$0.00")
    _set_stress_value(normalized, "subtotal_after_discount_fees", "$918.50")
    _set_stress_value(normalized, "taxable_subtotal", "$449.95")
    _set_stress_value(normalized, "sales_tax_rate", "13%")
    _set_stress_value(normalized, "tax_amount", "$58.49")
    _set_stress_value(normalized, "total", "$971.99")
    _set_stress_value(normalized, "amount_paid", "$0.00")
    _set_stress_value(normalized, "balance", "$971.99")

    return normalized


def main(invoice_number: str):
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
    normalized = _fill_defaults(normalized)

    logo_path = ROOT / "templates" / "email-assets" / "Mainline-Primary-Logo-Black.png"

    pdf_bytes = render_invoice_styled_draft(
        normalized,
        logo_path=str(logo_path) if logo_path.exists() else None,
    )

    out = ROOT / "tmp" / f"invoice-{invoice_number}-styled_draft-long-text-test.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)
    print("✅ wrote:", out)


if __name__ == "__main__":
    inv = sys.argv[1] if len(sys.argv) > 1 else "1013"
    main(inv)