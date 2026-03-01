# app/security/quote_response_token.py
from __future__ import annotations

import os
import time
from typing import Literal, TypedDict

import jwt

Action = Literal["accept", "reject"]

class QuoteResponseClaims(TypedDict):
    doc_id: str
    action: Action
    exp: int
    iat: int

JWT_ALG = "HS256"
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days


def _get_secret() -> str:
    secret = os.getenv("QUOTE_RESPONSE_JWT_SECRET")
    if not secret:
        raise RuntimeError("Missing QUOTE_RESPONSE_JWT_SECRET")
    return secret


def make_token(doc_id: str, action: Action, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    now = int(time.time())
    payload: QuoteResponseClaims = {
        "doc_id": doc_id,
        "action": action,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALG)


def verify_token(token: str) -> QuoteResponseClaims:
    return jwt.decode(token, _get_secret(), algorithms=[JWT_ALG])