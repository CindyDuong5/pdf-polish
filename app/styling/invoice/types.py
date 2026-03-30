# app/styling/invoice/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class PartyBlock:
  name: str = ""
  addr1: str = ""
  addr2: str = ""
  city_prov_postal: str = ""
  country: str = ""

@dataclass
class InvoiceMeta:
  invoice_number: str = ""
  invoice_date: str = ""     # already formatted like "Jan 01, 2026"
  job_number: str = ""
  po_number: str = ""
  total_due: str = ""        # formatted currency
  due_date: str = ""
  phone: str = ""
  email: str = ""

@dataclass
class LaborRow:
  date: str
  labor_name: str
  description: str
  taxable: str              # "Yes"/"No"
  hours: str
  rate: str                 # "$110.00"
  price: str                # "$440.00"

@dataclass
class PartRow:
  date: str
  item_name: str
  item_code: str
  description: str
  taxable: str              # "Yes"/"No"
  qty: str
  unit_price: str
  price: str

@dataclass
class Totals:
  subtotal: str
  service_fee: str
  discount: str
  subtotal_after_discount_fees: str  # IMPORTANT: subtotal + service_fee - discount
  taxable_subtotal: str
  sales_tax_rate_name: str           # e.g. "H - 13%"
  tax_amount: str
  total: str
  amount_paid: str
  balance: str

@dataclass
class InvoiceData:
  bill_to: PartyBlock
  meta: InvoiceMeta

  customer_name: str = ""
  property_name: str = ""
  property_address1: str = ""
  property_address2: str = ""
  property_city_prov_postal: str = ""

  authorized_by: str = ""
  customer_wo: str = ""
  nte: str = ""

  # ✅ NEW
  invoice_summary: str = ""
  hide_labor: bool = False
  hide_parts: bool = False
  labor: List[LaborRow] = field(default_factory=list)
  parts: List[PartRow] = field(default_factory=list)
  totals: Optional[Totals] = None