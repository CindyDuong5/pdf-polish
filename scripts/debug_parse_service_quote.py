# scripts/debug_parse_service_quote.py
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path

from app.styling.service_quote.parser import parse_service_quote


def _json_default(o):
    # handle Decimal cleanly in JSON output
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(f"Not JSON serializable: {type(o)}")


def main() -> None:
    pdf_path = Path("sample_inputs/Quote_1017_Cindy_Annual_Inspection.pdf")
    pdf_bytes = pdf_path.read_bytes()

    data = parse_service_quote(pdf_bytes)

    print("\n===== SERVICE QUOTE PARSE RESULT =====")
    if is_dataclass(data):
        payload = asdict(data)
    elif isinstance(data, dict):
        payload = data
    else:
        payload = getattr(data, "__dict__", {"value": str(data)})

    print(json.dumps(payload, indent=2, default=_json_default))

    # quick sanity checks
    print("\n===== SANITY CHECKS =====")
    print("quote_number:", payload.get("quote_number"))
    print("quote_date:", payload.get("quote_date"))
    print("company_name:", payload.get("company_name"))
    print("company_address:", payload.get("company_address"))
    print("property_name:", payload.get("property_name"))
    print("property_address:", payload.get("property_address"))
    print("total:", payload.get("total"))
    print("items_count:", len(payload.get("items") or []))
    if payload.get("items"):
        print("first_item:", payload["items"][0])


if __name__ == "__main__":
    main()