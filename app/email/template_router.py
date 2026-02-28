from __future__ import annotations

from pathlib import Path
from typing import Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"

_jinja = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def email_kind_for(doc_type: str | None) -> str:
    dt = (doc_type or "").upper()

    if "QUOTE" in dt:
        return "QUOTE"
    if "INVOICE" in dt:
        return "INVOICE"
    if "JOB" in dt or "REPORT" in dt:
        return "JOB_REPORT"
    return "GENERIC"

def template_for_kind(kind: str) -> str:
    if kind == "QUOTE":
        return "quote.html"
    if kind == "INVOICE":
        return "invoice.html"
    if kind == "JOB_REPORT":
        return "job_report.html"
    return "generic.html"

def render_html(template_name: str, context: dict) -> str:
    tpl = _jinja.get_template(template_name)
    return tpl.render(**context)

def build_subject(kind: str, doc_type: str | None, label: str) -> str:
    # You can tweak these anytime
    if kind == "QUOTE":
        return f"Quote {label} – Please Review"
    if kind == "INVOICE":
        return f"Invoice {label}"
    if kind == "JOB_REPORT":
        return f"Report {label}"
    return f"{doc_type or 'Document'} {label}"