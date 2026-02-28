# scripts/debug_template_acroform.py
from __future__ import annotations

from pathlib import Path
from pypdf import PdfReader


def main() -> None:
    template = Path("templates/Mainline-Service-Quote.pdf")
    r = PdfReader(str(template))

    root = r.trailer["/Root"].get_object()
    print("Has /AcroForm in template root?:", "/AcroForm" in root)

    acro = root.get("/AcroForm")
    print("AcroForm ref type:", type(acro))

    fields = r.get_fields() or {}
    print("Field count:", len(fields))
    print("Some field names:")
    for i, name in enumerate(sorted(fields.keys())):
        print(" ", name)
        if i >= 15:
            break


if __name__ == "__main__":
    main()