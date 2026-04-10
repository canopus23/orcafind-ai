import hashlib
import hmac
import os
import uuid
from typing import Any

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
    receipt: str | None,
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()

    payload: dict[str, Any] = {
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
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                data = response.json()
                if isinstance(data, dict):
                    err = data.get("error")
                    if isinstance(err, dict):
                        code = str(err.get("code") or "").strip()
                        desc = str(err.get("description") or "").strip()
                        detail = f"{code}: {desc}".strip(": ").strip()
                    if not detail:
                        detail = str(data)[:300]
                else:
                    detail = str(data)[:300]
            except Exception:
                detail = (response.text or "").strip().replace("\n", " ")[:300]

            status = response.status_code
            msg = f"Razorpay create_order failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc

        return response.json()


def verify_signature(*, order_id: str, payment_id: str, signature: str) -> bool:
    key_secret = get_razorpay_key_secret()
    message = f"{order_id}|{payment_id}".encode()
    digest = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")
