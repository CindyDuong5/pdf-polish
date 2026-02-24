# app/styling/base.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Styler(Protocol):
    def style(self, input_pdf: Path, output_pdf: Path) -> None:
        ...


@dataclass(frozen=True)
class TemplatePaths:
    invoice_template: Path
    quote_template: Path
    job_template: Path