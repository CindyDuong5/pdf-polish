# app/styling/proposal/assembler.py
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict

from pypdf import PdfReader, PdfWriter

from app.styling.proposal.content_pages import render_content_pages
from app.styling.proposal.overlay_cover import create_cover_overlay
from app.styling.proposal.page_number import add_page_numbers
from app.styling.proposal.template_picker import (
    get_closing_template,
    get_cover_template,
    get_intro_template,
    get_process_template,
    get_testimonials_template,
)


def _read_pdf(path_or_bytes: Any) -> PdfReader:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return PdfReader(BytesIO(path_or_bytes))
    return PdfReader(str(path_or_bytes))


def _append_all_pages(writer: PdfWriter, reader: PdfReader) -> int:
    count = 0
    for page in reader.pages:
        writer.add_page(page)
        count += 1
    return count


def _merge_cover_with_overlay(cover_path: str, overlay_bytes: bytes):
    cover_reader = _read_pdf(cover_path)
    overlay_reader = _read_pdf(overlay_bytes)

    page = cover_reader.pages[0]
    page.merge_page(overlay_reader.pages[0])
    return page


def build_proposal_pdf(fields: Dict[str, Any]) -> bytes:
    cover_path = get_cover_template(str(fields.get("proposal_type", "")))
    intro_path = get_intro_template(str(fields.get("prepared_by", "")))
    process_path = get_process_template(str(fields.get("proposal_type", "")))
    testimonials_path = get_testimonials_template()
    closing_path = get_closing_template(str(fields.get("prepared_by", "")))

    writer = PdfWriter()

    # Page 1 - cover + overlay fields
    cover_overlay = create_cover_overlay(fields)
    cover_page = _merge_cover_with_overlay(str(cover_path), cover_overlay)
    writer.add_page(cover_page)

    black_page_indexes: list[int] = []
    white_page_indexes: list[int] = []

    # Page 2 - intro
    _append_all_pages(writer, _read_pdf(intro_path))

    # Page 3 - process
    _append_all_pages(writer, _read_pdf(process_path))

    # Page 4..N - generated content pages
    content_start_index = len(writer.pages)
    content_pdf_bytes = render_content_pages(fields, start_page_number=4)
    content_page_count = _append_all_pages(writer, _read_pdf(content_pdf_bytes))

    black_page_indexes.extend(
        range(content_start_index, content_start_index + content_page_count)
    )

    # Testimonial page(s)
    testimonial_start_index = len(writer.pages)
    testimonial_page_count = _append_all_pages(writer, _read_pdf(testimonials_path))

    white_page_indexes.extend(
        range(testimonial_start_index, testimonial_start_index + testimonial_page_count)
    )

    # Closing page(s) - no page number overlay
    _append_all_pages(writer, _read_pdf(closing_path))

    out = BytesIO()
    writer.write(out)
    merged_bytes = out.getvalue()

    final_bytes = add_page_numbers(
        merged_bytes,
        start_at=4,
        black_page_indexes=black_page_indexes,
        white_page_indexes=white_page_indexes,
    )
    return final_bytes