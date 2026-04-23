# app/styling/proposal/renderer.py
from __future__ import annotations

from typing import Any, Dict

from app.styling.proposal.assembler import build_proposal_pdf


def render_proposal_pdf(fields: Dict[str, Any]) -> bytes:
    return build_proposal_pdf(fields)