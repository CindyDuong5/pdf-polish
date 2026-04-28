# scripts/test_render_proposal.py

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.styling.proposal.renderer import render_proposal_pdf


PROPOSAL_TYPES = ["Service", "Inspection", "Project"]
PREPARED_BY_LIST = [
    "Nick Janevski",
    "Rob Felstead",
    "Sarah Caley",
    "Aidan Quinn",
]


def base_payload() -> dict:
    return {
        "proposal_number": "P-1001",
        "proposal_date": "2026-04-22",
        "proposal_type": "Service",

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
            "Complete the following fire and life safety work in accordance with "
            "applicable codes and standards."
        ),

        "included": "All Parts & Labor",

        "exclusions": (
            "- Job to be completed during regular hours 08:00-16:30 Monday to Friday\n"
            "- Additional charges may apply if access is not provided at the time of service"
        ),

        "subtotal": "3500.00",
        "tax_rate": "13",
        "tax": "455.00",
        "total": "3955.00",

        "items": [
            {
                "item": "Fire Alarm Inspection",
                "description": "- Inspect and test fire alarm system devices\n- Provide report and deficiency list",
                "price": "2200.00",
            },
            {
                "item": "Emergency Lighting Inspection",
                "description": "- Test emergency lights and exit signs\n- Report failed batteries or lamps",
                "price": "850.00",
            },
            {
                "item": "Fire Extinguisher Inspection",
                "description": "- Inspect extinguishers and apply service tags",
                "price": "450.00",
            },
        ],
    }


def safe_filename(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("-", "_")
    )


def main() -> None:
    out_dir = Path("tmp")
    out_dir.mkdir(parents=True, exist_ok=True)

    for proposal_type in PROPOSAL_TYPES:
        for prepared_by in PREPARED_BY_LIST:
            payload = deepcopy(base_payload())

            payload["proposal_type"] = proposal_type
            payload["prepared_by"] = prepared_by
            payload["proposal_number"] = f"P-{safe_filename(proposal_type)}-{safe_filename(prepared_by)}"
            payload["property_name"] = f"Cindy House - {proposal_type}"
            payload["scope_summary"] = (
                f"This is a test {proposal_type.lower()} proposal prepared by {prepared_by}. "
                "This file is used to confirm the correct cover, intro, process, content, "
                "testimonial, closing page, and page numbers."
            )

            pdf_bytes = render_proposal_pdf(payload)

            filename = f"{safe_filename(proposal_type)}_{safe_filename(prepared_by)}.pdf"
            out_path = out_dir / filename
            out_path.write_bytes(pdf_bytes)

            print(f"Wrote: {out_path.resolve()}")


if __name__ == "__main__":
    main()