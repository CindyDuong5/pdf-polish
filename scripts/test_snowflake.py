# scripts/test_snowflake.py
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from app.services.snowflake import (
    get_snowflake_connection,
    get_property_representatives,
    get_property_rep_email_suggestion,
    get_customer_representatives,
    get_customer_rep_email_suggestion,
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


def test_simple_query() -> None:
    print("Testing simple Snowflake query...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY_REPRESENTATIVE
                WHERE IS_DELETED = FALSE
                """
            )
            row = cur.fetchone()
            print("Simple query OK")
            _print_json(
                "Simple query result:",
                {"active_property_representative_count": row[0]},
            )
        finally:
            cur.close()
    finally:
        conn.close()


def summarize_reps(label: str, reps: List[Dict[str, Any]]) -> None:
    print(f"{label}: {len(reps)} rep(s)")
    if not reps:
        print("  No rows returned.")
        return

    for i, rep in enumerate(reps, start=1):
        print(
            f"  {i}. "
            f"name={rep.get('full_name')!r}, "
            f"email={rep.get('email_address')!r}, "
            f"role={rep.get('role')!r}"
        )


def test_property_representatives(property_id: str) -> None:
    print(f"Testing property representatives for property_id={property_id}...")
    reps = get_property_representatives(property_id)
    print("Property representatives query OK")
    summarize_reps("Property reps", reps)
    _print_json("Property rep raw payload:", reps)


def test_property_rep_email_suggestion(property_id: str) -> None:
    print(f"Testing property billing-contact suggestion for property_id={property_id}...")
    suggestion = get_property_rep_email_suggestion(property_id)
    print("Property rep email suggestion OK")
    _print_json("Property billing suggestion:", suggestion)


def test_customer_representatives(customer_id: str) -> None:
    print(f"Testing customer representatives for customer_id={customer_id}...")
    reps = get_customer_representatives(customer_id)
    print("Customer representatives query OK")
    summarize_reps("Customer reps", reps)
    _print_json("Customer rep raw payload:", reps)


def test_customer_rep_email_suggestion(customer_id: str) -> None:
    print(f"Testing customer billing-contact suggestion for customer_id={customer_id}...")
    suggestion = get_customer_rep_email_suggestion(customer_id)
    print("Customer rep email suggestion OK")
    _print_json("Customer billing suggestion:", suggestion)


def test_resolve_invoice_recipient_suggestion(
    property_id: Optional[str],
    customer_id: Optional[str],
) -> None:
    print(
        "Testing final invoice recipient resolution "
        f"(property_id={property_id!r}, customer_id={customer_id!r})..."
    )
    result = resolve_invoice_recipient_suggestion(
        property_id=property_id,
        customer_id=customer_id,
        primary_email=None,
    )
    print("Final invoice recipient resolution OK")
    _print_json("Resolved invoice recipient:", result)


def main() -> None:
    property_id = sys.argv[1] if len(sys.argv) > 1 else "7f897be0-7f59-4047-b84a-67b8c5e9235c"
    customer_id = sys.argv[2] if len(sys.argv) > 2 else None

    print("=" * 80)
    print("SNOWFLAKE TEST")
    print(f"property_id = {property_id}")
    print(f"customer_id = {customer_id}")
    print("=" * 80)

    try:
        test_connection()
    except Exception as e:
        print("FAILED: connection test")
        print(f"Error: {e}")
        return

    print("=" * 80)

    try:
        test_simple_query()
    except Exception as e:
        print("FAILED: simple query test")
        print(f"Error: {e}")
        return

    print("=" * 80)

    try:
        test_property_representatives(property_id)
    except Exception as e:
        print("FAILED: get_property_representatives")
        print(f"Error: {e}")
        return

    print("=" * 80)

    try:
        test_property_rep_email_suggestion(property_id)
    except Exception as e:
        print("FAILED: get_property_rep_email_suggestion")
        print(f"Error: {e}")
        return

    print("=" * 80)

    if customer_id:
        try:
            test_customer_representatives(customer_id)
        except Exception as e:
            print("FAILED: get_customer_representatives")
            print(f"Error: {e}")
            return

        print("=" * 80)

        try:
            test_customer_rep_email_suggestion(customer_id)
        except Exception as e:
            print("FAILED: get_customer_rep_email_suggestion")
            print(f"Error: {e}")
            return

        print("=" * 80)

    try:
        test_resolve_invoice_recipient_suggestion(property_id, customer_id)
    except Exception as e:
        print("FAILED: resolve_invoice_recipient_suggestion")
        print(f"Error: {e}")
        return

    print("=" * 80)
    print("All Snowflake tests passed.")


if __name__ == "__main__":
    main()