from pathlib import Path

from app.styling.base import TemplatePaths
from app.styling.router import StylerRouter


def main():
    templates = TemplatePaths(
        invoice_template=Path("templates/Mainline-Invoice.pdf"),
        quote_template=Path("templates/Mainline-Service-Quote.pdf"),
        job_template=Path("templates/Mainline-Job-Report.pdf"),
    )

    router = StylerRouter(templates)

    Path("out").mkdir(exist_ok=True)

    tests = [
        ("invoice", Path("sample_inputs/sample_invoice.pdf"), Path("out/invoice_styled.pdf")),
        ("quote", Path("sample_inputs/sample_quote.pdf"), Path("out/quote_styled.pdf")),
        ("job", Path("sample_inputs/sample_job.pdf"), Path("out/job_styled.pdf")),
    ]

    for kind, inp, outp in tests:
        if not inp.exists():
            print(f"[SKIP] missing input: {inp}")
            continue
        print(f"[RUN] {kind}: {inp} -> {outp}")
        router.style(kind=kind, input_pdf=inp, output_pdf=outp)
        print(f"[OK] wrote {outp}")

    print("\nDone. Open the PDFs in /out to review.")


if __name__ == "__main__":
    main()