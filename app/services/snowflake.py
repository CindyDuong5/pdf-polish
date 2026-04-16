# app/services/snowflake.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Set

from dotenv import load_dotenv
import snowflake.connector
from cryptography.hazmat.primitives import serialization

load_dotenv(".env")

IGNORED_REP_EMAILS: Set[str] = {
    "inbox@mainlinefire.com",
}

BILLING_ROLE_KEYWORDS = (
    "bill",
    "billing",
    "invoice",
    "invoicing",
    "account",
    "accounting",
    "accountant",
)

PROPERTY_FALLBACK_MESSAGE = (
    "There is no billing contact under Property level. Using the billing contact under Customer level."
)

NO_BILLING_CONTACT_MESSAGE = (
    "No billing contact found under Property level or Customer level. "
    "Please manually enter the email address to send the invoice to."
)


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _load_private_key_bytes() -> bytes:
    key_path = _get_required_env("SNOWFLAKE_PRIVATE_KEY_PATH")
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", "").strip() or None

    with open(key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=passphrase.encode() if passphrase else None,
        )

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_snowflake_connection():
    return snowflake.connector.connect(
        account=_get_required_env("SNOWFLAKE_ACCOUNT"),
        user=_get_required_env("SNOWFLAKE_USER"),
        private_key=_load_private_key_bytes(),
        warehouse=_get_required_env("SNOWFLAKE_WAREHOUSE"),
        database=_get_required_env("SNOWFLAKE_DATABASE"),
        schema=_get_required_env("SNOWFLAKE_SCHEMA"),
        role=_get_required_env("SNOWFLAKE_ROLE"),
    )


def _execute_query(sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
        finally:
            cur.close()
    finally:
        conn.close()


# =========================================================
# Proposal lookup helpers
# =========================================================

def search_active_customers_by_name(name: str, limit: int = 50) -> List[Dict[str, Any]]:
    search = (name or "").strip()
    if not search:
        return []

    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        safe_limit = 50

    safe_limit = max(1, min(safe_limit, 100))

    sql = f"""
    SELECT
        id                    AS customer_id,
        name                  AS customer_name,
        customer_code,
        type                  AS customer_type,

        billing_address_line1 AS address,
        billing_city          AS city,
        billing_state         AS state,
        CONCAT_WS(', ',
            NULLIF(billing_address_line1, ''),
            NULLIF(billing_city, ''),
            NULLIF(billing_state, '')
        )                     AS full_address,

        email,
        phone_primary,
        phone_alternate

    FROM BUILDOPS_OPERATIONAL_DATA.SHARE.CUSTOMER
    WHERE LOWER(name) LIKE LOWER(%s)
      AND is_active = TRUE
      AND is_deleted = FALSE
    ORDER BY name ASC
    LIMIT {safe_limit}
    """

    return _execute_query(sql, (f"%{search}%",))


def get_properties_for_customer(customer_id: str) -> List[Dict[str, Any]]:
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return []

    sql = """
    SELECT
        c.id                    AS customer_id,
        c.name                  AS customer_name,

        cp.id                   AS property_id,
        cp.name                 AS property_name,

        cp.address_line1        AS property_address,
        cp.city                 AS property_city,
        cp.state                AS property_state,
        cp.postal_code          AS property_postal_code,
        cp.country              AS property_country,
        CONCAT_WS(', ',
            NULLIF(cp.address_line1, ''),
            NULLIF(cp.city, ''),
            NULLIF(cp.state, ''),
            NULLIF(cp.postal_code, '')
        )                       AS property_full_address

    FROM BUILDOPS_OPERATIONAL_DATA.SHARE.CUSTOMER c

    LEFT JOIN (
        SELECT
            p.customer_id,
            p.id,
            p.name,
            p.address_line1,
            p.address_line2,
            p.city,
            p.state,
            p.postal_code,
            p.country
        FROM BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY p
        WHERE p.is_deleted = FALSE
          AND p.is_active = TRUE

        UNION

        SELECT
            pc.customer_id,
            p.id,
            p.name,
            p.address_line1,
            p.address_line2,
            p.city,
            p.state,
            p.postal_code,
            p.country
        FROM BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY_CUSTOMERS pc
        JOIN BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY p
            ON p.id = pc.property_id
        WHERE pc.is_deleted = FALSE
          AND p.is_deleted = FALSE
          AND p.is_active = TRUE
    ) cp ON cp.customer_id = c.id

    WHERE c.id = %s
      AND c.is_deleted = FALSE

    ORDER BY cp.name ASC
    """

    rows = _execute_query(sql, (customer_id,))
    return [row for row in rows if row.get("property_id")]


def get_property_details_for_customer(
    customer_id: str,
    property_id: str,
) -> Optional[Dict[str, Any]]:
    customer_id = (customer_id or "").strip()
    property_id = (property_id or "").strip()

    if not customer_id or not property_id:
        return None

    rows = get_properties_for_customer(customer_id)
    for row in rows:
        if str(row.get("property_id") or "").strip() == property_id:
            return row

    return None

# =========================================================
# Existing invoice recipient helpers
# =========================================================

def get_customer_representatives(customer_id: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT
        cr.CUSTOMER_ID,
        c.NAME AS CUSTOMER_NAME,
        cr.ID AS REPRESENTATIVE_ID,
        cr.FULL_NAME,
        cr.FIRST_NAME,
        cr.LAST_NAME,
        cr.EMAIL_ADDRESS,
        cr.PHONE_MOBILE,
        cr.ROLE
    FROM BUILDOPS_OPERATIONAL_DATA.SHARE.CUSTOMER_REPRESENTATIVE cr
    LEFT JOIN BUILDOPS_OPERATIONAL_DATA.SHARE.CUSTOMER c
        ON cr.CUSTOMER_ID = c.ID
    WHERE cr.IS_DELETED = FALSE
      AND cr.CUSTOMER_ID = %s
    ORDER BY cr.FULL_NAME
    """
    return _execute_query(sql, (customer_id,))


def get_property_representatives(property_id: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT
        pr.PROPERTY_ID,
        p.NAME AS PROPERTY_NAME,
        p.ADDRESS_LINE1,
        p.CITY,
        p.STATE,
        pr.ID AS REPRESENTATIVE_ID,
        pr.FULL_NAME,
        pr.EMAIL_ADDRESS,
        pr.PHONE_MOBILE,
        pr.ROLE
    FROM BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY_REPRESENTATIVE pr
    LEFT JOIN BUILDOPS_OPERATIONAL_DATA.SHARE.PROPERTY p
        ON pr.PROPERTY_ID = p.ID
    WHERE pr.IS_DELETED = FALSE
      AND pr.PROPERTY_ID = %s
    ORDER BY pr.FULL_NAME
    """
    return _execute_query(sql, (property_id,))


def _clean_rep_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def _clean_role(role: Optional[str]) -> str:
    return (role or "").strip().lower()


def _is_allowed_rep_email(email: Optional[str]) -> bool:
    cleaned = _clean_rep_email(email)
    return bool(cleaned) and cleaned not in IGNORED_REP_EMAILS


def _role_matches_billing(role: Optional[str]) -> bool:
    cleaned = _clean_role(role)
    if not cleaned:
        return False
    return any(keyword in cleaned for keyword in BILLING_ROLE_KEYWORDS)


def _dedupe_emails(emails: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for email in emails:
        cleaned = _clean_rep_email(email)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _filter_billing_reps(reps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for rep in reps:
        email = _clean_rep_email(rep.get("email_address"))
        role = rep.get("role")

        if not _is_allowed_rep_email(email):
            continue
        if not _role_matches_billing(role):
            continue
        if email in seen:
            continue

        seen.add(email)
        out.append(rep)

    return out


def _build_email_suggestion(
    reps: List[Dict[str, Any]],
    primary_email: Optional[str] = None,
) -> Dict[str, Any]:
    emails = _dedupe_emails(
        [
            _clean_rep_email(rep.get("email_address"))
            for rep in reps
            if _is_allowed_rep_email(rep.get("email_address"))
        ]
    )

    primary = _clean_rep_email(primary_email)

    if _is_allowed_rep_email(primary) and primary in emails:
        to_email = primary
        cc_emails = [e for e in emails if e != primary]
    elif _is_allowed_rep_email(primary):
        to_email = primary
        cc_emails = emails
    elif emails:
        to_email = emails[0]
        cc_emails = emails[1:]
    else:
        to_email = ""
        cc_emails = []

    return {
        "to": to_email,
        "cc": cc_emails,
        "all_emails": emails,
        "items": reps,
    }


def get_customer_rep_email_suggestion(
    customer_id: str,
    primary_email: Optional[str] = None,
) -> Dict[str, Any]:
    reps = get_customer_representatives(customer_id)
    billing_reps = _filter_billing_reps(reps)
    suggestion = _build_email_suggestion(billing_reps, primary_email=primary_email)

    return {
        "customer_id": customer_id,
        **suggestion,
    }


def get_property_rep_email_suggestion(
    property_id: str,
    primary_email: Optional[str] = None,
) -> Dict[str, Any]:
    reps = get_property_representatives(property_id)
    billing_reps = _filter_billing_reps(reps)
    suggestion = _build_email_suggestion(billing_reps, primary_email=primary_email)

    return {
        "property_id": property_id,
        **suggestion,
    }


def resolve_invoice_recipient_suggestion(
    *,
    property_id: Optional[str],
    customer_id: Optional[str],
    primary_email: Optional[str] = None,
) -> Dict[str, Any]:
    property_id = (property_id or "").strip()
    customer_id = (customer_id or "").strip()

    property_result: Dict[str, Any] = {
        "property_id": property_id,
        "to": "",
        "cc": [],
        "all_emails": [],
        "items": [],
    }
    customer_result: Dict[str, Any] = {
        "customer_id": customer_id,
        "to": "",
        "cc": [],
        "all_emails": [],
        "items": [],
    }

    if property_id:
        property_result = get_property_rep_email_suggestion(
            property_id,
            primary_email=primary_email,
        )
        if property_result["to"]:
            return {
                "source": "property",
                "message": "",
                "to": property_result["to"],
                "cc": property_result["cc"],
                "all_emails": property_result["all_emails"],
                "items": property_result["items"],
                "property_result": property_result,
                "customer_result": customer_result,
            }

    if customer_id:
        customer_result = get_customer_rep_email_suggestion(
            customer_id,
            primary_email=primary_email,
        )
        if customer_result["to"]:
            return {
                "source": "customer",
                "message": PROPERTY_FALLBACK_MESSAGE,
                "to": customer_result["to"],
                "cc": customer_result["cc"],
                "all_emails": customer_result["all_emails"],
                "items": customer_result["items"],
                "property_result": property_result,
                "customer_result": customer_result,
            }

    return {
        "source": "manual",
        "message": NO_BILLING_CONTACT_MESSAGE,
        "to": "",
        "cc": [],
        "all_emails": [],
        "items": [],
        "property_result": property_result,
        "customer_result": customer_result,
    }