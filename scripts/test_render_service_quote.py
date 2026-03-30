# scripts/test_render_service_quote.py
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, Optional, List, Tuple

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
        data.quote_date = "Mar 30, 2026"


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


def _make_short_scope() -> str:
    return (
        "Scope of Work\n"
        "Annual fire alarm inspection.\n"
        "Annual emergency light inspection.\n"
        "Update logbook and submit report."
    )


def _make_long_scope() -> str:
    return "\n".join(
        [
            "Scope of Work",
            "a) Fire Alarm System",
            "• Monthly: Inspection of control panel, alarms, strobes, annunciators, supervisory points, and trouble signals.",
            "• Quarterly: Functional test of smoke detectors, heat detectors, duct detectors, pull stations, relays, monitor modules, and signal circuits.",
            "• Annual: Full system inspection, sensitivity review where applicable, sequence verification, battery test, and final certification.",
            "b) Sprinkler & Standpipe Systems",
            "• Monthly: Inspect valves, gauges, tamper switches, risers, leaks, signage, and obstructions.",
            "• Quarterly: Test waterflow switches, inspect hose cabinets, confirm accessibility, and review impairments.",
            "• Annual: Main drain test, trip testing where applicable, inspection of risers, valves, heads, FDCs, and standpipe accessories.",
            "c) Emergency Lighting & Exit Signs",
            "• Monthly: Functional testing of all battery units, remote heads, and exit signs.",
            "• Quarterly: Inspection of charging indicators, battery condition, lamp heads, and mounting condition.",
            "• Annual: Full discharge test, deficiency logging, and replacement recommendations for failed components.",
            "d) Portable Fire Extinguishers",
            "• Monthly: Visual inspection, pressure check, seal check, accessibility, and signage review.",
            "• Annual: Maintenance, tagging, and hydrostatic testing recommendations as required by code and manufacturer standards.",
            "e) Reporting & Recordkeeping",
            "• Maintain all inspection records.",
            "• Update the on-site fire safety logbook.",
            "• Submit a written report to the client representative within five business days.",
            "• Where deficiencies are identified, provide a supplementary report with recommendations and estimated pricing.",
        ]
    )


def _make_wrap_scope() -> str:
    return "\n".join(
        [
            "Scope of Work",
            "This line is intentionally very long to test whether normal paragraph wrapping behaves properly when a sentence keeps going across the page width without overlapping anything or getting cut off unexpectedly in the output PDF.",
            "This line contains long technical naming: FAACP-SUBBASEMENT-NORTH-TOWER-ANNUNCIATOR-EXPANSION-MODULE-REVISION-BETA-2026-CLIENT-REFERENCE-DO-NOT-TRUNCATE.",
            "This line contains a very long email and URL style string to test difficult wrapping behavior:",
            "firealarmservicedepartment.superlongalias.testing@mainlinefireprotection-example-domain.ca / https://mainlinefireprotection-example-domain.ca/service/very/long/path/for/testing/wrapping/behavior/in-renderer/output",
            "This line contains repeated code-like text:",
            "DEVICECODE_1234567890_1234567890_1234567890_1234567890_1234567890_1234567890",
            "Final note: the renderer should wrap cleanly and should not let text cross into the price area or outside the page margin.",
        ]
    )


def _make_long_exclusions() -> List[str]:
    return [
        "Job to be completed during regular hours 08:00-16:30 Monday to Friday unless otherwise approved in writing by the Client.",
        "Pricing is subject to parts availability, site access, shutdown coordination, and all quoted work being completed during the same scheduled attendance.",
        "Any concealed wiring issues, inaccessible devices, ceiling access equipment, tenant coordination, security escort requirements, or after-hours building premiums are excluded unless specifically stated otherwise.",
        "Deficiency repairs, replacement parts, re-inspection after third-party work, fire watch, engineering review, permit revisions, and monitoring provider charges are excluded from this quotation unless noted in the included scope.",
    ]


def _clone_item(item, *, name: Optional[str] = None, description: Optional[str] = None, price=None):
    copied = deepcopy(item)
    if name is not None:
        copied.name = name
    if description is not None:
        copied.description = description
    if price is not None:
        copied.price = price
    return copied


def _build_wrap_heavy_items(parsed_data) -> list:
    source_items = deepcopy(parsed_data.items or [])

    if not source_items:
        return []

    first = source_items[0]
    items = []

    items.append(
        _clone_item(
            first,
            name="Annual Fire Inspection Maintenance Contract - Very Long Item Title To Confirm Header Alignment And Text Behavior",
            description="\n".join(
                [
                    "Annual Fire Inspection (Fire Alarm, Standpipe, Emergency Lights, Fire Extinguishers, Fire Pump, Kitchen Suppression, Monitoring Interface, and Ancillary Devices).",
                    "This description line is intentionally long to make sure regular sentence wrapping still looks clean when the text width gets close to the margin and continues to another line.",
                    "FACP-NORTH-TOWER-LEVEL-P2-ANNUNCIATOR-EXPANSION-CIRCUIT-LOOP-CHECK-REFERENCE-12345678901234567890.",
                    "superlongpartsalias@mainlinefireprotection-example-domain.ca",
                    "DEVICECODE_ABCDEFGHIJKLMNOPQRSTUVWXYZ_1234567890_ABCDEFGHIJKLMNOPQRSTUVWXYZ_1234567890",
                ]
            ),
            price=5610.00,
        )
    )

    for i in range(2, 11):
        items.append(
            _clone_item(
                first,
                name=f"Service Line {i}",
                description="\n".join(
                    [
                        f"Inspection item {i} with enough text to wrap across multiple lines for layout testing.",
                        "Verify devices, record results, update logbook, and provide deficiency notes where applicable.",
                    ]
                ),
                price=0.00,
            )
        )

    return items


def _extract_footer_labels(pdf_path: Path) -> Tuple[int, List[str]]:
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)

    labels: List[str] = []
    pat = re.compile(r"Page\s+\d+\s+of\s+\d+", re.IGNORECASE)

    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        matches = pat.findall(text)
        if matches:
            labels.append(matches[-1])
        else:
            labels.append(f"(missing on page {idx})")

    return page_count, labels


def _check_footer_totals(pdf_path: Path) -> bool:
    page_count, labels = _extract_footer_labels(pdf_path)

    print("\n--- Footer page check ---")
    print("actual page count:", page_count)

    ok = True
    for idx, label in enumerate(labels, start=1):
        expected = f"Page {idx} of {page_count}"
        good = label == expected
        if not good:
            ok = False
        print(f"  page {idx}: found={label!r} expected={expected!r} -> {'OK' if good else 'MISMATCH'}")

    return ok


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
    footer_ok = _check_footer_totals(out_path)
    print("\nfooter check     :", "PASS" if footer_ok else "FAIL")


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

    cases = []

    # CASE 1: Parsed data as-is
    data_parsed = deepcopy(parsed_data)
    _patch_basic_fields(data_parsed)
    cases.append(
        (
            "parsed_exclusions",
            "Draft with parsed exclusions",
            data_parsed,
            Path("tmp/service_quote_case_1_parsed_exclusions.pdf"),
        )
    )

    # CASE 2: Fallback exclusions
    data_fallback = deepcopy(parsed_data)
    _patch_basic_fields(data_fallback)
    data_fallback.specific_exclusions = []
    cases.append(
        (
            "fallback_exclusions",
            "Draft with fallback exclusions",
            data_fallback,
            Path("tmp/service_quote_case_2_fallback_exclusions.pdf"),
        )
    )

    # CASE 3: Short scope
    data_short_scope = deepcopy(parsed_data)
    _patch_basic_fields(data_short_scope)
    data_short_scope.quote_description = _make_short_scope()
    cases.append(
        (
            "short_scope",
            "Draft with short scope of work",
            data_short_scope,
            Path("tmp/service_quote_case_3_short_scope.pdf"),
        )
    )

    # CASE 4: Long scope
    data_long_scope = deepcopy(parsed_data)
    _patch_basic_fields(data_long_scope)
    data_long_scope.quote_description = _make_long_scope()
    cases.append(
        (
            "long_scope",
            "Draft with long scope of work",
            data_long_scope,
            Path("tmp/service_quote_case_4_long_scope.pdf"),
        )
    )

    # CASE 5: Long scope + long exclusions
    data_long_scope_long_ex = deepcopy(parsed_data)
    _patch_basic_fields(data_long_scope_long_ex)
    data_long_scope_long_ex.quote_description = _make_long_scope()
    data_long_scope_long_ex.specific_exclusions = _make_long_exclusions()
    cases.append(
        (
            "long_scope_long_exclusions",
            "Draft with long scope and long exclusions",
            data_long_scope_long_ex,
            Path("tmp/service_quote_case_5_long_scope_long_exclusions.pdf"),
        )
    )

    # CASE 6: Wrap stress test in scope
    data_wrap_scope = deepcopy(parsed_data)
    _patch_basic_fields(data_wrap_scope)
    data_wrap_scope.quote_description = _make_wrap_scope()
    cases.append(
        (
            "wrap_scope",
            "Draft with wrap stress test in scope",
            data_wrap_scope,
            Path("tmp/service_quote_case_6_wrap_scope.pdf"),
        )
    )

    # CASE 7: Wrap stress test in items
    data_wrap_items = deepcopy(parsed_data)
    _patch_basic_fields(data_wrap_items)
    data_wrap_items.quote_description = _make_short_scope()
    data_wrap_items.items = _build_wrap_heavy_items(parsed_data)
    data_wrap_items.specific_exclusions = _make_long_exclusions()
    cases.append(
        (
            "wrap_items",
            "Draft with wrap stress test in item descriptions",
            data_wrap_items,
            Path("tmp/service_quote_case_7_wrap_items.pdf"),
        )
    )

    print("\n===== RENDER CASES =====")
    for key, label, data, out_path in cases:
        print(f"\n==================== {key} ====================")
        _render_case(
            template_path=template_path,
            data=data,
            out_path=out_path,
            label=label,
        )

    print("\n===== DONE =====")
    print("Check these files visually:")
    for _, label, _, out_path in cases:
        print(f"  - {label}: {out_path.resolve()}")

    print("\nWhat to verify:")
    print("  - footer total matches actual page count on every page")
    print("  - short scope does not create awkward gaps")
    print("  - long scope paginates cleanly")
    print("  - long exclusions move to a new page only when needed")
    print("  - very long text wraps cleanly and does not overlap price or margins")
    print("  - long item descriptions stay inside the content width")


if __name__ == "__main__":
    main()