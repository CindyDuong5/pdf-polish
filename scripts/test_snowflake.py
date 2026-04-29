# scripts/test_snowflake.py
# scripts/test_snowflake.py
from __future__ import annotations

import json
import sys
from typing import Any

from app.services.snowflake import (
    get_snowflake_connection,
    get_proposal_by_opportunity_number,
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


def test_proposal_lookup(opportunity_number: str) -> dict:
    print(f"Testing proposal lookup for opportunity_number={opportunity_number!r}...")

    item = get_proposal_by_opportunity_number(opportunity_number)
    if not item:
        raise RuntimeError(f"No opportunity found for {opportunity_number!r}")

    _print_json("Proposal lookup result:", item)

    required_fields = [
        "proposal_number",
        "prepared_by",
        "customer_id",
        "customer_name",
        "customer_address",
        "property_id",
        "property_name",
        "property_address",
        "contact_name",
        "contact_email",
        "contact_phone",
    ]

    missing = [key for key in required_fields if key not in item]
    if missing:
        raise RuntimeError(f"Missing keys from proposal lookup: {missing}")

    if str(item["proposal_number"]).strip() != opportunity_number.strip():
        raise RuntimeError(
            f"Expected proposal_number to equal opportunity_number. "
            f"Got {item['proposal_number']!r}"
        )

    print("Proposal lookup OK")
    return item


def main() -> None:
    opportunity_number = sys.argv[1] if len(sys.argv) > 1 else ""

    if not opportunity_number:
        print("Usage:")
        print("  python -m scripts.test_snowflake <opportunity_number>")
        return

    print("=" * 80)
    print("SNOWFLAKE PROPOSAL LOOKUP TEST")
    print(f"opportunity_number = {opportunity_number!r}")
    print("=" * 80)

    test_connection()

    print("=" * 80)

    test_proposal_lookup(opportunity_number)

    print("=" * 80)
    print("Snowflake proposal lookup test passed.")


if __name__ == "__main__":
    main()