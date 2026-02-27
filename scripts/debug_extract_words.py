# scripts/debug_extract_words.py
from __future__ import annotations

from pathlib import Path

from app.styling.service_quote.text_extract import extract_words, words_to_text


def main() -> None:
    pdf_path = Path("sample_inputs/Quote_1015_Annual_Repair_Quote_for_Cindy_.pdf")
    pdf_bytes = pdf_path.read_bytes()

    words = extract_words(pdf_bytes)
    print("WORDS COUNT:", len(words))

    # show first 200 words (raw tokens)
    for w in words[:200]:
        print(f"[p{w.page}] ({w.x0:.1f},{w.y0:.1f}) {w.text}")

    print("\n===== RECONSTRUCTED TEXT =====")
    print(words_to_text(words)[:2000])  # preview


if __name__ == "__main__":
    main()