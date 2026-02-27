# app/styling/service_quote/styler.py
from __future__ import annotations

from pathlib import Path

from app.styling.service_quote.parser import parse_service_quote, ServiceQuoteData
from app.styling.service_quote.renderer import render_service_quote


class ServiceQuoteStyler:
    def __init__(self, template_pdf: Path):
        self.template_pdf = template_pdf

    def style(self, original_pdf_bytes: bytes) -> tuple[bytes, ServiceQuoteData]:
        data = parse_service_quote(original_pdf_bytes)
        out = render_service_quote(self.template_pdf, data)
        return out, data