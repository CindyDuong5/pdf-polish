# app/stylign/job/styler.py
from __future__ import annotations

from pathlib import Path

from app.styling.common.template_stamp_renderer import TemplateStampRenderer, StampOptions


class JobStyler:
    """
    Rough job/report restyler:
      - Stamps original job PDF onto job template PDF.
      - Upgrade later when you have consistent report formats.
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