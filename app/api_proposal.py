# app/api_proposal.py
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import SessionLocal
from app.services.snowflake import (
    search_active_customers_by_name,
    get_properties_for_customer,
    get_proposal_by_opportunity_number,
)
from app.services.proposal_service import build_proposal_document
from app.storage.s3_storage import get_storage

router = APIRouter(prefix="/api/proposals", tags=["proposals"])
logger = logging.getLogger(__name__)


class ProposalItemIn(BaseModel):
    item: str = ""
    description: str = ""
    price: str = ""


class ProposalFieldsIn(BaseModel):
    proposal_number: str = ""
    proposal_date: str = ""
    proposal_type: str = ""

    customer_id: str = ""
    customer_name: str = ""
    customer_address: str = ""

    property_id: str = ""
    property_name: str = ""
    property_address: str = ""

    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""

    prepared_by: str = ""
    scope_summary: str = ""
    exclusions: str = ""

    subtotal: str = ""
    tax_rate: str = ""
    tax: str = ""
    total: str = ""

    items: List[ProposalItemIn] = Field(default_factory=list)


class BuildProposalRequest(BaseModel):
    fields: ProposalFieldsIn


def _styled_draft_key_for(doc_id: str) -> str:
    return f"styled_draft/proposals/{doc_id}.pdf"


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)

    text_value = str(value).strip()
    if not text_value:
        return Decimal(default)

    cleaned = text_value.replace("$", "").replace(",", "")

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _money_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _normalize_proposal_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    f = dict(fields or {})

    proposal_number = str(f.get("proposal_number") or "").strip()
    contact_email = str(f.get("contact_email") or "").strip() or None
    customer_name = str(f.get("customer_name") or "").strip() or None
    property_address = str(f.get("property_address") or "").strip() or None
    property_name = str(f.get("property_name") or "").strip() or None

    raw_items = f.get("items") or []
    normalized_items: List[Dict[str, Any]] = []

    numeric_item_found = False
    computed_subtotal = Decimal("0.00")

    for row in raw_items:
        item = str((row or {}).get("item") or "").strip()
        description = str((row or {}).get("description") or "").strip()

        raw_price = (row or {}).get("price")
        price_decimal = _to_decimal(raw_price, "0").quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        raw_price_text = str(raw_price or "").strip()
        if raw_price_text:
            try:
                Decimal(raw_price_text.replace("$", "").replace(",", ""))
                numeric_item_found = True
            except Exception:
                pass

        computed_subtotal += price_decimal

        normalized_items.append(
            {
                "item": item,
                "description": description,
                "price": raw_price_text,
            }
        )

    subtotal_input = _to_decimal(f.get("subtotal"), "0")
    tax_rate = _to_decimal(f.get("tax_rate"), "13")
    if tax_rate <= 0:
        tax_rate = Decimal("13")

    if numeric_item_found:
        subtotal = computed_subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        subtotal = subtotal_input.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    tax = (subtotal * tax_rate / Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    total = (subtotal + tax).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    f["items"] = normalized_items
    f["subtotal"] = _money_str(subtotal)
    f["tax_rate"] = _money_str(tax_rate).rstrip("0").rstrip(".") if "." in _money_str(tax_rate) else _money_str(tax_rate)
    f["tax"] = _money_str(tax)
    f["total"] = _money_str(total)

    # Make proposal behave like quote in the rest of the system
    f["quote_number"] = proposal_number
    f["client_email"] = contact_email or ""
    f["client_name"] = customer_name or ""
    f["company_name"] = customer_name or ""
    f["property_name"] = property_name or ""
    f["property_address"] = property_address or ""
    f["doc_label"] = "Proposal"
    f["doc_type"] = "PROJECT_QUOTE"

    return f


@router.get("/customers/search")
def api_search_customers(
    q: str = Query(..., min_length=1, description="Partial customer name"),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        items = search_active_customers_by_name(q, limit=limit)
        return {
            "ok": True,
            "query": q,
            "count": len(items),
            "items": items,
        }
    except Exception as e:
        logger.exception("Customer search failed")
        raise HTTPException(status_code=500, detail=f"Customer search failed: {e}")


@router.get("/customers/{customer_id}/properties")
def api_get_customer_properties(customer_id: str):
    customer_id = (customer_id or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    try:
        items = get_properties_for_customer(customer_id)
        return {
            "ok": True,
            "customer_id": customer_id,
            "count": len(items),
            "items": items,
        }
    except Exception as e:
        logger.exception("Property lookup failed")
        raise HTTPException(status_code=500, detail=f"Property lookup failed: {e}")

@router.get("/opportunity/{opportunity_number}")
def api_get_proposal_opportunity(opportunity_number: str):
    opportunity_number = (opportunity_number or "").strip()
    if not opportunity_number:
        raise HTTPException(status_code=400, detail="opportunity_number is required")

    try:
        item = get_proposal_by_opportunity_number(opportunity_number)
        if not item:
            raise HTTPException(
                status_code=404,
                detail=f"Opportunity #{opportunity_number} was not found",
            )

        return {
            "ok": True,
            "item": item,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Opportunity proposal lookup failed")
        raise HTTPException(
            status_code=500,
            detail=f"Opportunity proposal lookup failed: {e}",
        )

@router.post("/build")
def api_build_proposal(payload: BuildProposalRequest):
    try:
        storage = get_storage()

        raw_fields = payload.fields.model_dump()
        fields = _normalize_proposal_fields(raw_fields)

        proposal_number = str(fields.get("proposal_number") or "").strip()

        if not proposal_number:
            raise HTTPException(
                status_code=400,
                detail="Proposal number is required. Please load an opportunity first.",
            )
        
        pdf_bytes = build_proposal_document(fields)

        doc_id = str(uuid4())
        draft_key = _styled_draft_key_for(doc_id)
        storage.upload_pdf_bytes(draft_key, pdf_bytes)

        proposal_number = proposal_number or None
        customer_name = str(fields.get("customer_name") or "").strip() or None
        customer_email = str(fields.get("contact_email") or "").strip() or None
        property_address = str(fields.get("property_address") or "").strip() or None

        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO public.documents (
                        id,
                        doc_type,
                        status,
                        customer_name,
                        customer_email,
                        property_address,
                        quote_number,
                        original_s3_key,
                        styled_draft_s3_key,
                        extracted_fields,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        'PROJECT_QUOTE',
                        'DRAFT',
                        :customer_name,
                        :customer_email,
                        :property_address,
                        :quote_number,
                        :original_s3_key,
                        :styled_draft_s3_key,
                        CAST(:extracted_fields AS jsonb),
                        now(),
                        now()
                    )
                    """
                ),
                {
                    "id": doc_id,
                    "customer_name": customer_name,
                    "customer_email": customer_email,
                    "property_address": property_address,
                    "quote_number": proposal_number,
                    "original_s3_key": draft_key,
                    "styled_draft_s3_key": draft_key,
                    "extracted_fields": json.dumps(fields),
                },
            )
            db.commit()

        url = storage.presign_get_url(
            key=draft_key,
            expires_seconds=3600,
            download_filename=f"PROPOSAL_{proposal_number or doc_id}.pdf",
            inline=True,
        )

        return {
            "ok": True,
            "doc_id": doc_id,
            "doc_type": "PROJECT_QUOTE",
            "proposal_number": proposal_number,
            "quote_number": proposal_number,
            "styled_draft_s3_key": draft_key,
            "original_s3_key": draft_key,
            "url": url,
            "fields": fields,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Proposal build failed")
        raise HTTPException(
            status_code=500,
            detail=f"Proposal build failed: {type(e).__name__}: {e}",
        )