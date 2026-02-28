# scripts/test_render_service_quote.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

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
    p1 = Path("sample_inputs/Quote_1017_Cindy_Annual_Inspection.pdf")
    if p1.exists():
        return p1

    folder = Path("sample_inputs")
    if folder.exists():
        for p in folder.glob("*.pdf"):
            if "Quote_1015" in p.name:
                return p
        for p in folder.glob("*.pdf"):
            return p

    return p1


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

        # annots_ref might be an IndirectObject -> resolve
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

            # Only widgets (form fields)
            if annot.get("/Subtype") != "/Widget":
                continue

            # Field name can be on the widget itself (/T) or on its parent (/Parent -> /T)
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

            # Value can be on widget (/V) or parent (/V)
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

    # ✅ Use your parser output, but DO NOT use the rendered PDF from styler.style()
    _out_bytes_unused, data = styler.style(original_bytes)

    # ----------------------------
    # ✅ Patch missing fields here
    # ----------------------------
    if not (data.client_name or "").strip():
        data.client_name = "Client Name"

    if not (data.client_phone or "").strip():
        data.client_phone = "000-000-0000"

    if not (data.client_email or "").strip():
        data.client_email = "name@email.com"

    if not (data.company_name or "").strip():
        data.company_name = "Company Name"

    if not (data.company_address or "").strip():
        data.company_address = "Address\nCity, Province XXX XXX"

    if not (data.property_name or "").strip():
        data.property_name = "Property Name"

    if not (data.property_address or "").strip():
        data.property_address = "Address\nCity, Province XXX XXX"

    if not (data.quote_description or "").strip():
        data.quote_description = (
            "This is a sample quote description to help visually test wrapping and spacing. "
            "Add more words here to see how it breaks into lines."
            "Add more words here to see how it breaks into lines."
            "Add more words here to see how it breaks into lines."
        )

    # ✅ Now render using patched data
    out_bytes = render_service_quote(template_path, data)

    out_path = Path("tmp/service_quote_draft.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    print("\n✅ Draft created:", out_path.resolve())

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
    print("quote_description:", (data.quote_description or "")[:140], "...")
    print("subtotal         :", data.subtotal)
    print("tax              :", data.tax)
    print("total            :", data.total)

    _print_fields_from_annots(out_path)

if __name__ == "__main__":
    main()