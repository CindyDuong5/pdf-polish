# app/styling/invoice/styler.py

from __future__ import annotations

from pathlib import Path

from app.styling.common.template_stamp_renderer import TemplateStampRenderer, StampOptions


class InvoiceStyler:
    """
    Rough invoice restyler:
      - Stamps the original invoice PDF onto the invoice template.
      - Later you can tune scale/offset or replace with a true field renderer.
    """

    def __init__(self, template_pdf: Path):
        self.renderer = TemplateStampRenderer(
            template_pdf=template_pdf,
            options=StampOptions(
                template_as_background=True,
                stamp_scale=1.0,
                stamp_dx=0.0,
                stamp_dy=0.0,
                use_template_page_size=True,
            ),
        )

    def style(self, input_pdf: Path, output_pdf: Path) -> None:
        self.renderer.render(input_pdf, output_pdf)