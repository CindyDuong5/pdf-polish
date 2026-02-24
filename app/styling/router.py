# app/styling/route.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.styling.base import TemplatePaths
from app.styling.invoice.styler import InvoiceStyler
from app.styling.quote.styler import QuoteStyler
from app.styling.job.styler import JobStyler


def normalize_kind(kind: str | None) -> str:
    k = (kind or "").strip().lower()
    if k in ("invoice", "inv"):
        return "invoice"
    if k in ("quote", "proposal", "est", "estimate"):
        return "quote"
    if k in ("job", "report", "job_report", "jobreport"):
        return "job"
    return "job"  # safe default


class StylerRouter:
    """
    Single entry point for your worker:
      router.style(kind="invoice|quote|job", input_pdf=..., output_pdf=...)
    """

    def __init__(self, templates: TemplatePaths):
        self._invoice = InvoiceStyler(templates.invoice_template)
        self._quote = QuoteStyler(templates.quote_template)
        self._job = JobStyler(templates.job_template)

    def style(self, *, kind: str | None, input_pdf: Path, output_pdf: Path) -> None:
        k = normalize_kind(kind)
        if k == "invoice":
            return self._invoice.style(input_pdf, output_pdf)
        if k == "quote":
            return self._quote.style(input_pdf, output_pdf)
        return self._job.style(input_pdf, output_pdf)