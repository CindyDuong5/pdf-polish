# scripts/test_invoice_mapper.py
from __future__ import annotations

import json
import sys
from dotenv import load_dotenv

load_dotenv()

from app.buildops_client import BuildOpsClient
from app.styling.invoice.build_data import build_invoice_pdf_data_from_number
import app.styling.invoice.mapper as mapper_mod


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_invoice_mapper.py <invoice_number>")
        sys.exit(1)

    invoice_number = sys.argv[1].strip()

    print("USING MAPPER FILE:", mapper_mod.__file__)
    print(f"\n🔍 Fetching invoice data for invoice_number = {invoice_number}\n")

    bo = BuildOpsClient()
    data = build_invoice_pdf_data_from_number(bo, invoice_number)

    print("HAS invoice_summary:", "invoice_summary" in data)
    print("invoice_summary repr:", repr(data.get("invoice_summary")))

    print("\n================ NORMALIZED DATA ================\n")
    print(json.dumps(data, indent=2))
    print("\n=================================================\n")


if __name__ == "__main__":
    main()