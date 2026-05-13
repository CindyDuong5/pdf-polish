# app/buildops_client.py
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BUILDOPS_BASE_URL", "https://public-api.live.buildops.com/v1")


def _env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


class BuildOpsClient:
    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.base_url = base_url or BASE_URL
        self.tenant_id = tenant_id or _env_required("BUILDOPS_TENANT_ID")
        self.client_id = client_id or _env_required("BUILDOPS_CLIENT_ID")
        self.client_secret = client_secret or _env_required("BUILDOPS_SECRET_KEY")
        self.timeout = timeout

        self._token: Optional[str] = None
        self._token_ts: float = 0.0

    def _get_token(self) -> str:
        url = f"{self.base_url}/auth/token"
        payload = {"clientId": self.client_id, "clientSecret": self.client_secret}

        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"No token in BuildOps response: {data}")

        self._token = token
        self._token_ts = time.time()
        return token

    def _auth_header(self) -> Dict[str, str]:
        if not self._token:
            self._get_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "tenantId": self.tenant_id,
            **self._auth_header(),
        }

    def _request(self, method: str, path: str, *, json: Any = None, params: Dict[str, Any] | None = None) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.base_url}{path}"

        def do_req() -> requests.Response:
            return requests.request(
                method,
                url,
                headers=self._headers(),
                json=json,
                params=params,
                timeout=self.timeout,
            )

        r = do_req()
        if r.status_code == 401:
            logger.warning("BuildOps 401; refreshing token and retrying once.")
            self._get_token()
            r = do_req()

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"BuildOps {method} {path} failed: {e} | {r.text[:500]}") from e

        return r.json() if r.text else None

    def get(self, path: str, *, params: Dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: Any = None, params: Dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json, params=params)

    # ---------------- Invoices ----------------
    def get_invoice_by_id(self, invoice_id: str) -> Dict[str, Any]:
        return self.get(f"/invoices/{invoice_id}")

    def lookup_invoice_id(self, invoice_number: str) -> str:
        from app.invoice_lookup import get_invoice_id_by_number  # local import avoids cycles
        return get_invoice_id_by_number(str(invoice_number).strip())

    def get_invoice_by_number(self, invoice_number: str) -> Dict[str, Any]:
        inv_id = self.lookup_invoice_id(invoice_number)
        return self.get_invoice_by_id(inv_id)


    # ---------------- Quotes ----------------
    def get_quotes(
        self,
        *,
        quote_number: str | int | None = None,
        page: int = 0,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }

        if quote_number:
            params["quote_number"] = str(quote_number).strip()

        return self.get("/quotes", params=params)

    def get_quote_by_number(self, quote_number: str | int) -> Dict[str, Any] | None:
        qn = str(quote_number or "").strip()
        if not qn:
            return None

        data = self.get_quotes(
            quote_number=qn,
            page=0,
            page_size=10,
        )

        items = data.get("items") or []

        for item in items:
            if str(item.get("quoteNumber") or "").strip() == qn:
                return item

        return items[0] if items else None

    def get_quote_property_customer_ids(
        self,
        quote_number: str | int,
    ) -> Dict[str, str]:
        quote = self.get_quote_by_number(quote_number)

        if not quote:
            return {
                "quote_id": "",
                "property_id": "",
                "customer_id": "",
            }

        property_id = str(
            quote.get("propertyId")
            or quote.get("property_id")
            or quote.get("property", {}).get("id")
            or ""
        ).strip()

        customer_id = str(
            quote.get("billingCustomerId")
            or quote.get("customerId")
            or quote.get("customer_id")
            or quote.get("billingCustomer", {}).get("id")
            or quote.get("customer", {}).get("id")
            or ""
        ).strip()

        # Fallback: quote has property_id but no customer_id.
        # Get customer_id from property detail.
        if property_id and not customer_id:
            try:
                prop = self.get_property_by_id(property_id)
                customer_id = str(
                    prop.get("customerId")
                    or prop.get("customer_id")
                    or prop.get("customer", {}).get("id")
                    or ""
                ).strip()
            except Exception as e:
                print("PROPERTY CUSTOMER LOOKUP FAILED:", e)

        return {
            "quote_id": str(quote.get("id") or "").strip(),
            "property_id": property_id,
            "customer_id": customer_id,
        }
    
    # ---------------- Properties ----------------
    def get_property_by_id(self, property_id: str) -> Dict[str, Any]:
        return self.get(f"/properties/{property_id}")

    # ---------------- Customers ----------------
    def get_customer_by_id(self, customer_id: str) -> Dict[str, Any]:
        return self.get(f"/customers/{customer_id}")

    # ---------------- Jobs ----------------
    def get_job_by_id(self, job_id: str) -> Dict[str, Any]:
        return self.get(f"/jobs/{job_id}")