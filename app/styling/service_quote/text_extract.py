# app/styling/service_quote/text_extract.py
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Dict, Any

import fitz  # PyMuPDF


@dataclass
class Word:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int
    line: int
    word: int


def extract_words(pdf_bytes: bytes) -> List[Word]:
    """
    Extract every word token from the PDF, including coordinates.
    This is the most reliable base for parsing when PDFs have weird spacing.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: List[Word] = []

    for pno in range(doc.page_count):
        page = doc.load_page(pno)

        # Each word item: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        words = page.get_text("words")  # type: ignore

        for (x0, y0, x1, y1, w, block_no, line_no, word_no) in words:
            w = (w or "").strip()
            if not w:
                continue
            out.append(
                Word(
                    page=pno,
                    x0=float(x0),
                    y0=float(y0),
                    x1=float(x1),
                    y1=float(y1),
                    text=w,
                    block=int(block_no),
                    line=int(line_no),
                    word=int(word_no),
                )
            )

    return out


def words_to_text(words: List[Word]) -> str:
    """
    Convert word tokens back into readable text.
    Joins words by line ordering.
    """
    # sort by page, then y, then x
    words_sorted = sorted(words, key=lambda w: (w.page, round(w.y0, 1), w.x0))

    lines: List[str] = []
    current_key = None
    current_words: List[str] = []

    for w in words_sorted:
        key = (w.page, round(w.y0, 1))  # y grouping tolerance
        if current_key is None:
            current_key = key

        if key != current_key:
            if current_words:
                lines.append(" ".join(current_words))
            current_key = key
            current_words = [w.text]
        else:
            current_words.append(w.text)

    if current_words:
        lines.append(" ".join(current_words))

    return "\n".join(lines).strip()