# scripts/test_render_proposal.py
from __future__ import annotations

from pathlib import Path

from app.styling.proposal.renderer import render_proposal_pdf


def main() -> None:
    payload = {
        "proposal_number": "P-1001",
        "proposal_date": "2026-04-22",
        "proposal_type": "Project",
        "customer_id": "c8087404-6029-4bf9-954c-3dd9cb80f327",
        "customer_name": "Summerhill Property Management",
        "customer_address": "2600 Skymark Avenue, Mississauga, ON",
        "property_id": "7f897be0-7f59-4047-b84a-67b8c5e9235c",
        "property_name": "Cindy House",
        "property_address": "17 Knightsbridge Rd., Brampton, Ontario, L6T 3X9",
        "contact_name": "Cindy Test",
        "contact_email": "reneeb@summerhillcondos.com",
        "contact_phone": "123-456-7890",
        "prepared_by": "Nick Janevski",
        "scope_summary": (
            "Complete the Following Fire & Life Safety Inspections and Testing in "
            "Accordance with OFC, OBC, CAN/ULC-S536, NFPA 25, NFPA 10, CSA B64."
            "All work to be performed by licensed technicians with appropriate certifications and insurance."
            "Detailed inspection reports will be provided, including documentation of deficiencies and recommendations for corrective actions."
        ),
        "exclusions": (
            "- Job to be completed during regular hours 08:00-16:30 Monday to Friday\n"
            "- Pricing is subject to parts availability and all items being done concurrently\n"
            "- Additional charges may apply for repairs, re-inspections, after-hours work, or if access to devices is not provided at the time of service\n"
        ),
        "subtotal": "18450.00",
        "tax_rate": "13",
        "tax": "2398.50",
        "total": "20848.50",
        "items": [
            {
                "item": "Annual Fire Alarm Inspection",
                "description": (
                    "- Annual inspection and testing of fire alarm control panel, annunciator, initiating devices, "
                    "notification devices, power supplies, batteries, relays, and monitoring interfaces\n"
                    "- Verify operation of pull stations, smoke detectors, heat detectors, waterflow switches, tamper switches, "
                    "duct detectors, horn strobes, bells, speakers, and ancillary functions\n"
                    "- Provide testing documentation and deficiency report"
                ),
                "price": "2200.00",
            },
            {
                "item": "Monthly Emergency Lighting Inspection",
                "description": (
                    "- Monthly function test of emergency light units and exit signs\n"
                    "- Confirm lamp heads operate, charge indicators are functional, and units remain unobstructed\n"
                    "- Report failed batteries, lamps, and damaged housings"
                ),
                "price": "TBD",
            },
            {
                "item": "Annual Fire Extinguisher Inspection",
                "description": (
                    "- Inspect portable fire extinguishers throughout the property\n"
                    "- Verify gauge pressure, accessibility, hose condition, pins, seals, labels, cabinet condition, and mounting height\n"
                    "- Tag extinguishers and identify any units requiring recharge, hydrotest, or replacement"
                ),
                "price": "TBD",
            },
            {
                "item": "Monthly Fire Extinguisher Inspection",
                "description": (
                    "- Inspect portable fire extinguishers throughout the property\n"
                    "- Verify gauge pressure, accessibility, hose condition, pins, seals, labels, cabinet condition, and mounting height\n"
                    "- Tag extinguishers and identify any units requiring recharge, hydrotest, or replacement"
                ),
                "price": "1650.00",
            },
            {
                "item": "Monthly Fire Extinguisher Inspection",
                "description": (
                    "- Inspect portable fire extinguishers throughout the property\n"
                    "- Verify gauge pressure, accessibility, hose condition, pins, seals, labels, cabinet condition, and mounting height\n"
                    "- Tag extinguishers and identify any units requiring recharge, hydrotest, or replacement"
                ),
                "price": "1650.00",
            },
        ],
    }

    pdf_bytes = render_proposal_pdf(payload)

    out_path = Path("tmp/test_proposal.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pdf_bytes)

    print(f"Wrote: {out_path.resolve()}")


if __name__ == "__main__":
    main()