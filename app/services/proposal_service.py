# app/services/proposal_service.py
from __future__ import annotations

from typing import Any, Dict

from app.styling.proposal.renderer import render_proposal_pdf


def build_proposal_document(fields: Dict[str, Any]) -> bytes:
    return render_proposal_pdf(fields)