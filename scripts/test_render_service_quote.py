# scripts/test_render_service_quote.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from copy import deepcopy

from pypdf import PdfReader

from app.styling.service_quote.styler import ServiceQuoteStyler
from app.styling.service_quote.renderer import render_service_quote


def _guess_template_path() -> Path:
    candidates = [
        Path("templates/Mainline-Service-Quote-V2.pdf"),
        Path("templates/Mainline-Service-Quote.pdf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _guess_original_path() -> Path:
    preferred = [
        Path("sample_inputs/SERVICE_QUOTE_1084-2.pdf"),
        Path("sample_inputs/Quote_1017_Cindy_Annual_Inspection.pdf"),
    ]
    for p in preferred:
        if p.exists():
            return p

    folder = Path("sample_inputs")
    if folder.exists():
        for p in folder.glob("*.pdf"):
            if "SERVICE_QUOTE_1036" in p.name:
                return p
        for p in folder.glob("*.pdf"):
            if "Quote_1015" in p.name:
                return p
        for p in folder.glob("*.pdf"):
            return p

    return preferred[0]


def _norm(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _extract_widget_values(reader: PdfReader) -> Dict[str, str]:
    """
    Robustly extract form field values by scanning widget annotations on pages.
    Avoids PdfReader.get_fields() which can crash on slightly broken field trees.
    """
    out: Dict[str, str] = {}

    for page in reader.pages:
        annots_ref = page.get("/Annots")
        if not annots_ref:
            continue

        try:
            annots = annots_ref.get_object()
        except Exception:
            annots = annots_ref

        if not annots:
            continue

        for a_ref in annots:
            try:
                annot = a_ref.get_object()
            except Exception:
                annot = a_ref

            if not annot:
                continue

            if annot.get("/Subtype") != "/Widget":
                continue

            name: Optional[str] = None

            t = annot.get("/T")
            if t is not None:
                name = _norm(t)
            else:
                parent_ref = annot.get("/Parent")
                if parent_ref is not None:
                    try:
                        parent = parent_ref.get_object()
                    except Exception:
                        parent = parent_ref
                    if parent and parent.get("/T") is not None:
                        name = _norm(parent.get("/T"))

            if not name:
                continue

            val = annot.get("/V")
            if val is None:
                parent_ref = annot.get("/Parent")
                if parent_ref is not None:
                    try:
                        parent = parent_ref.get_object()
                    except Exception:
                        parent = parent_ref
                    if parent:
                        val = parent.get("/V")

            out[name] = _norm(val)

    return out


def _print_fields_from_annots(pdf_path: Path) -> None:
    r = PdfReader(str(pdf_path))

    wanted = [
        "ClientName",
        "ClientPhone",
        "ClientEmail",
        "CompanyName",
        "CompanyAddress",
        "PropertyName",
        "PropertyAddress",
        "QuoteNumber",
        "QuoteDate",
        "QuoteDescription",
        "SubTotal",
        "TaxTotal",
        "Total",
        "ItemName",
        "ItemPrice",
        "ItemDescription",
    ]

    values = _extract_widget_values(r)

    print("\n--- Output PDF field values (from /Annots widgets) ---")
    for name in wanted:
        if name not in values:
            print(f"{name:16} : (missing)")
        else:
            print(f"{name:16} : {values[name]}")


def _patch_basic_fields(data) -> None:
    if not (data.client_name or "").strip():
        data.client_name = "Client Name"

    if not (data.client_phone or "").strip():
        data.client_phone = "000-000-0000"

    if not (data.client_email or "").strip():
        data.client_email = "name@email.com"

    if not (data.company_name or "").strip():
        data.company_name = "Company Name"

    if not (data.company_address or "").strip():
        data.company_address = "123 Test Street, Toronto, ON M1M 1M1"

    if not (data.property_name or "").strip():
        data.property_name = "Property Name"

    if not (data.property_address or "").strip():
        data.property_address = "456 Sample Avenue, Toronto, ON M2M 2M2"

    if not (data.quote_number or "").strip():
        data.quote_number = "SQ-TEST-1001"

    if not (data.quote_date or "").strip():
        data.quote_date = "Mar 09, 2026"


def _print_exclusions(title: str, exclusions: list[str]) -> None:
    print(f"\n--- {title} ---")
    print("count:", len(exclusions))
    if not exclusions:
        print("(none)")
        return

    for i, ex in enumerate(exclusions, start=1):
        print(f"  {i}. {ex}")


def _print_quote_description(title: str, text: str) -> None:
    print(f"\n--- {title} ---")
    if not (text or "").strip():
        print("(empty)")
        return

    for i, ln in enumerate(text.splitlines(), start=1):
        print(f"  line {i}: {ln}")


def _render_case(template_path: Path, data, out_path: Path, label: str) -> None:
    out_bytes = render_service_quote(template_path, data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    print(f"\n✅ {label} created: {out_path.resolve()}")

    print("\n--- Extracted + patched data (used for render) ---")
    print("client_name      :", data.client_name)
    print("client_phone     :", data.client_phone)
    print("client_email     :", data.client_email)
    print("company_name     :", data.company_name)
    print("company_address  :", data.company_address)
    print("property_name    :", data.property_name)
    print("property_address :", data.property_address)
    print("quote_number     :", data.quote_number)
    print("quote_date       :", data.quote_date)

    _print_quote_description("quote_description passed into renderer", data.quote_description or "")

    print("subtotal         :", data.subtotal)
    print("tax              :", data.tax)
    print("total            :", data.total)

    _print_exclusions("specific_exclusions passed into renderer", data.specific_exclusions or [])

    _print_fields_from_annots(out_path)


def main() -> None:
    template_path = _guess_template_path()
    original_path = _guess_original_path()

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path.resolve()}")
    if not original_path.exists():
        raise FileNotFoundError(f"Original PDF not found: {original_path.resolve()}")

    print("Template :", template_path.resolve())
    print("Original :", original_path.resolve())

    original_bytes = original_path.read_bytes()

    styler = ServiceQuoteStyler(template_pdf=template_path)

    # Parse using your existing parser
    _out_bytes_unused, parsed_data = styler.style(original_bytes)

    print("\n===== PARSED DATA CHECK =====")
    print("quote_number     :", parsed_data.quote_number)
    print("quote_date       :", parsed_data.quote_date)
    print("company_name     :", parsed_data.company_name)
    print("property_name    :", parsed_data.property_name)
    print("subtotal         :", parsed_data.subtotal)
    print("tax              :", parsed_data.tax)
    print("total            :", parsed_data.total)

    _print_quote_description("parsed quote_description", parsed_data.quote_description or "")
    _print_exclusions("parsed specific_exclusions", parsed_data.specific_exclusions or [])

    # ----------------------------
    # CASE 1: Render with parsed exclusions
    # Uses the quote description parsed from sample input
    # ----------------------------
    data_parsed = deepcopy(parsed_data)
    _patch_basic_fields(data_parsed)

    out_path_1 = Path("tmp/service_quote_draft_with_parsed_exclusions.pdf")
    _render_case(
        template_path=template_path,
        data=data_parsed,
        out_path=out_path_1,
        label="Draft with parsed exclusions",
    )

    # ----------------------------
    # CASE 2: Render with fallback exclusions
    # Uses the same parsed quote description from sample input
    # Only exclusions are changed
    # ----------------------------
    data_fallback = deepcopy(parsed_data)
    _patch_basic_fields(data_fallback)
    data_fallback.specific_exclusions = []

    out_path_2 = Path("tmp/service_quote_draft_with_fallback_exclusions.pdf")
    _render_case(
        template_path=template_path,
        data=data_fallback,
        out_path=out_path_2,
        label="Draft with fallback exclusions",
    )

    print("\n===== DONE =====")
    print("Check these files visually:")
    print("  1.", out_path_1.resolve())
    print("  2.", out_path_2.resolve())
    print("\nExpected result:")
    print("  - both files should use the quote description parsed from the sample input")
    print("  - file 1 should show parsed exclusions from the source PDF")
    print("  - file 2 should show the 2 hardcoded fallback exclusions")


if __name__ == "__main__":
    main()