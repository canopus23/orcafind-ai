import hashlib
import hmac
import os
import uuid
from typing import Any, Dict, Optional

import httpx


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def get_razorpay_key_id() -> str:
    return _require_env("RAZORPAY_KEY_ID")


def get_razorpay_key_secret() -> str:
    return _require_env("RAZORPAY_KEY_SECRET")


def get_razorpay_api_base_url() -> str:
    return os.getenv("RAZORPAY_API_BASE_URL", "https://api.razorpay.com").rstrip("/")


async def create_order(
    *,
    amount_paise: int,
    currency: str,
    receipt: Optional[str],
    notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()

    payload: Dict[str, Any] = {
        "amount": int(amount_paise),
        "currency": currency,
        "receipt": receipt or f"rcpt_{uuid.uuid4().hex}",
        "payment_capture": 1,
    }
    if notes:
        payload["notes"] = notes

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url}/v1/orders",
            auth=(key_id, key_secret),
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def verify_signature(*, order_id: str, payment_id: str, signature: str) -> bool:
    key_secret = get_razorpay_key_secret()
    message = f"{order_id}|{payment_id}".encode("utf-8")
    digest = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")

