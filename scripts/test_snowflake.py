# scripts/test_snowflake.py
from __future__ import annotations

import json
import sys
from typing import Any

from app.services.snowflake import (
    get_snowflake_connection,
    get_proposal_by_opportunity_number,
    resolve_invoice_recipient_suggestion,
)


def _print_json(title: str, data: Any) -> None:
    print(title)
    print(json.dumps(data, indent=2, default=str))


def test_connection() -> None:
    print("Testing raw Snowflake connection...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    CURRENT_ACCOUNT(),
                    CURRENT_USER(),
                    CURRENT_ROLE(),
                    CURRENT_WAREHOUSE(),
                    CURRENT_DATABASE(),
                    CURRENT_SCHEMA()
                """
            )
            row = cur.fetchone()
            print("Connection OK")
            _print_json(
                "Connection context:",
                {
                    "current_account": row[0],
                    "current_user": row[1],
                    "current_role": row[2],
                    "current_warehouse": row[3],
                    "current_database": row[4],
                    "current_schema": row[5],
                },
            )
        finally:
            cur.close()
    finally:
        conn.close()


def _fetch_one(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0].lower() for d in cur.description]
            return dict(zip(cols, row))
        finally:
            cur.close()
    finally:
        conn.close()


def test_invoice_contact_lookup(invoice_number: str) -> dict[str, Any]:
    print(f"Testing invoice contact lookup for invoice_number={invoice_number!r}...")

    sql = """
    SELECT
        i.ID AS invoice_id,
        i.INVOICE_NUMBER,
        i.CUSTOMER_ID,
        c.NAME AS customer_name,
        i.PROPERTY_ID,
        p.NAME AS property_name,
        NULL AS billclient_email
    FROM BUILDOPS_OPERATIONAL_DATA.SHARE.INVOICE i
    LEFT JOIN BUILDOPS_OPERATIONAL_DATA.SHARE.CUSTOMER c
        ON c.ID = i.CUSTOMER_ID
       AND c.TENANT_ID = i.TENANT_ID
       AND c.IS_DELETED = FALSE
    LEFT JOIN BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY p
        ON p.ID = i.PROPERTY_ID
       AND p.TENANT_ID = i.TENANT_ID
       AND p.IS_DELETED = FALSE
    WHERE i.IS_DELETED = FALSE
      AND i.TENANT_ID = %s
      AND i.INVOICE_NUMBER = %s
    LIMIT 1
    """

    import os
    tenant_id = os.getenv("BUILDOPS_TENANT_ID", "").strip()
    if not tenant_id:
        raise RuntimeError("Missing BUILDOPS_TENANT_ID in .env")

    invoice = _fetch_one(sql, (tenant_id, invoice_number))
    if not invoice:
        raise RuntimeError(f"No invoice found for {invoice_number!r}")

    _print_json("Invoice row:", invoice)

    suggestion = resolve_invoice_recipient_suggestion(
        property_id=invoice.get("property_id"),
        customer_id=invoice.get("customer_id"),
        primary_email=invoice.get("billclient_email"),
    )

    _print_json("Resolved invoice contact suggestion:", suggestion)

    print("Invoice contact lookup OK")
    return {
        "invoice": invoice,
        "suggestion": suggestion,
    }


def test_proposal_lookup(opportunity_number: str) -> dict:
    print(f"Testing proposal lookup for opportunity_number={opportunity_number!r}...")

    item = get_proposal_by_opportunity_number(opportunity_number)
    if not item:
        raise RuntimeError(f"No opportunity found for {opportunity_number!r}")

    _print_json("Proposal lookup result:", item)
    print("Proposal lookup OK")
    return item


def main() -> None:
    number = sys.argv[1] if len(sys.argv) > 1 else "26-1151"
    mode = sys.argv[2] if len(sys.argv) > 2 else "invoice"

    print("=" * 80)
    print("SNOWFLAKE TEST")
    print(f"mode = {mode!r}")
    print(f"number = {number!r}")
    print("=" * 80)

    test_connection()

    print("=" * 80)

    if mode == "invoice":
        test_invoice_contact_lookup(number)
    elif mode == "proposal":
        test_proposal_lookup(number)
    else:
        raise RuntimeError("Mode must be either 'invoice' or 'proposal'")

    print("=" * 80)
    print("Snowflake test passed.")


if __name__ == "__main__":
    main()