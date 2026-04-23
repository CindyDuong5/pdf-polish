# app/styling/proposal/template_picker.py
from __future__ import annotations

from pathlib import Path

from app.styling.proposal.utils import prepared_by_key, proposal_template_dir, proposal_type_key


TEMPLATE_DIR = proposal_template_dir()


def _must_exist(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Missing proposal template: {path}")
    return path


def _fallback(path: Path, fallback: Path) -> Path:
    return path if path.exists() else fallback


def get_cover_template(proposal_type: str) -> Path:
    filename = f"{proposal_type_key(proposal_type)}.pdf"
    return _must_exist(TEMPLATE_DIR / "covers" / filename)


def get_intro_template(prepared_by: str) -> Path:
    key = prepared_by_key(prepared_by)
    wanted = TEMPLATE_DIR / "intro" / f"{key}.pdf"
    fallback = TEMPLATE_DIR / "intro" / "nick.pdf"
    return _must_exist(_fallback(wanted, fallback))


def get_process_template(proposal_type: str) -> Path:
    filename = f"{proposal_type_key(proposal_type)}.pdf"
    return _must_exist(TEMPLATE_DIR / "process" / filename)


def get_testimonials_template() -> Path:
    return _must_exist(TEMPLATE_DIR / "testimonials" / "default.pdf")


def get_closing_template(prepared_by: str) -> Path:
    key = prepared_by_key(prepared_by)
    wanted = TEMPLATE_DIR / "closing" / f"{key}.pdf"
    fallback = TEMPLATE_DIR / "closing" / "nick.pdf"
    return _must_exist(_fallback(wanted, fallback))