# app/styling/common/template_stamp_renderer.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject


@dataclass(frozen=True)
class StampOptions:
    """
    template_as_background=True means:
      - template is the base page
      - original content is merged on top

    If False:
      - original is base
      - template is merged on top
    """
    template_as_background: bool = True

    # Transform applied to the original content BEFORE merging onto template
    stamp_scale: float = 1.0
    stamp_dx: float = 0.0  # points; +x right
    stamp_dy: float = 0.0  # points; +y up

    # If True, output page size follows the TEMPLATE page size.
    # If False, output page size follows ORIGINAL page size.
    use_template_page_size: bool = True


class TemplateStampRenderer:
    """
    Rough “restyle” renderer:
      - for each input page, combine with corresponding template page
      - repeats the last template page if template has fewer pages
      - allows crude transform of the original content (scale/translate)
    """

    def __init__(self, template_pdf: Path, options: StampOptions | None = None):
        self.template_pdf = template_pdf
        self.options = options or StampOptions()

    def render(self, input_pdf: Path, output_pdf: Path) -> None:
        src = PdfReader(str(input_pdf))
        tpl = PdfReader(str(self.template_pdf))
        out = PdfWriter()

        tpl_pages = tpl.pages
        tpl_len = len(tpl_pages)

        for i, src_page in enumerate(src.pages):
            tpl_page = tpl_pages[min(i, tpl_len - 1)]  # repeat last template page if needed
            composed = self._compose_page(tpl_page, src_page)
            out.add_page(composed)

        with open(output_pdf, "wb") as f:
            out.write(f)

    def _compose_page(self, tpl_page: PageObject, src_page: PageObject) -> PageObject:
        # Decide output size
        if self.options.use_template_page_size:
            out_w = float(tpl_page.mediabox.width)
            out_h = float(tpl_page.mediabox.height)
        else:
            out_w = float(src_page.mediabox.width)
            out_h = float(src_page.mediabox.height)

        # Create blank output base page
        base = PageObject.create_blank_page(width=out_w, height=out_h)

        # Copy template and original into temporary pages (avoid mutating reader pages)
        tpl_copy = PageObject.create_blank_page(
            width=float(tpl_page.mediabox.width),
            height=float(tpl_page.mediabox.height),
        )
        tpl_copy.merge_page(tpl_page)

        src_copy = PageObject.create_blank_page(
            width=float(src_page.mediabox.width),
            height=float(src_page.mediabox.height),
        )
        src_copy.merge_page(src_page)

        # Apply transform to original content if requested
        if (
            self.options.stamp_scale != 1.0
            or self.options.stamp_dx != 0.0
            or self.options.stamp_dy != 0.0
        ):
            # affine transform matrix: (a,b,c,d,e,f)
            # [a c e]
            # [b d f]
            # [0 0 1]
            src_copy.add_transformation(
                (
                    self.options.stamp_scale,
                    0,
                    0,
                    self.options.stamp_scale,
                    self.options.stamp_dx,
                    self.options.stamp_dy,
                )
            )

        # Compose in the chosen order
        if self.options.template_as_background:
            # base <- template <- original
            base.merge_page(tpl_copy)
            base.merge_page(src_copy)
        else:
            # base <- original <- template
            base.merge_page(src_copy)
            base.merge_page(tpl_copy)

        return base