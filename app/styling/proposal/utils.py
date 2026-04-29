# app/styling/ proposal/utils.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def project_root() -> Path:
    # app/styling/proposal/utils.py -> pdf-polish/
    return Path(__file__).resolve().parents[3]


def proposal_template_dir() -> Path:
    return project_root() / "templates" / "proposal"


def normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def prepared_by_key(prepared_by: Any) -> str:
    text = normalize_key(prepared_by)
    if not text:
        return ""

    first = text.split()[0]

    if first == "nikola":
        return "nick"

    return first


def proposal_type_key(proposal_type: Any) -> str:
    key = normalize_key(proposal_type)
    if key in {"project", "service", "inspection"}:
        return key
    return "service"


def to_decimal(value: Any, default: str = "0.00") -> Decimal:
    try:
        raw = str(value if value is not None else default).replace(",", "").replace("$", "").strip()
        if not raw:
            raw = default
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def money(value: Any) -> str:
    return f"${to_decimal(value):,.2f}"


def service_label_for_proposal_type(proposal_type: Any) -> str:
    key = proposal_type_key(proposal_type)
    if key == "project":
        return "Project Quote"
    if key == "inspection":
        return "Inspection Quote"
    return "Service Quote"