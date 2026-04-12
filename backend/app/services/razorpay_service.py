import hashlib
import hmac
import os
import uuid
from typing import Any

import httpx

_DEFAULT_TIMEOUT = float(os.getenv("RAZORPAY_HTTP_TIMEOUT_SECONDS", "60") or "60")


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


def get_razorpay_webhook_secret() -> str:
    return _require_env("RAZORPAY_WEBHOOK_SECRET")


def _parse_razorpay_error(response: httpx.Response) -> str:
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
    return detail


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

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/v1/orders",
            auth=(key_id, key_secret),
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
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


def verify_subscription_signature(*, subscription_id: str, payment_id: str, signature: str) -> bool:
    """
    Razorpay checkout signature for subscriptions uses: sha256(payment_id|subscription_id).
    """
    key_secret = get_razorpay_key_secret()
    message = f"{payment_id}|{subscription_id}".encode()
    digest = hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")


def verify_webhook_signature(*, body: bytes, signature: str) -> bool:
    secret = get_razorpay_webhook_secret()
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")


async def create_subscription(
    *,
    plan_id: str,
    total_count: int,
    quantity: int = 1,
    customer_notify: bool = True,
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()

    payload: dict[str, Any] = {
        "plan_id": plan_id,
        "total_count": int(total_count),
        "quantity": int(quantity),
        "customer_notify": 1 if customer_notify else 0,
    }
    if notes:
        payload["notes"] = notes

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/v1/subscriptions",
            auth=(key_id, key_secret),
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
            status = response.status_code
            msg = f"Razorpay create_subscription failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def update_subscription(
    *,
    subscription_id: str,
    plan_id: str,
    schedule_change_at: str,
) -> dict[str, Any]:
    """
    schedule_change_at: "now" | "cycle_end"
    """
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()
    payload = {"plan_id": plan_id, "schedule_change_at": schedule_change_at}

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.patch(
            f"{base_url}/v1/subscriptions/{subscription_id}",
            auth=(key_id, key_secret),
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
            status = response.status_code
            msg = f"Razorpay update_subscription failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def cancel_subscription(
    *,
    subscription_id: str,
    cancel_at_cycle_end: bool = True,
) -> dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()
    payload = {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0}

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/v1/subscriptions/{subscription_id}/cancel",
            auth=(key_id, key_secret),
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
            status = response.status_code
            msg = f"Razorpay cancel_subscription failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def cancel_scheduled_changes(*, subscription_id: str) -> dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/v1/subscriptions/{subscription_id}/cancel_scheduled_changes",
            auth=(key_id, key_secret),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
            status = response.status_code
            msg = f"Razorpay cancel_scheduled_changes failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def fetch_subscription(*, subscription_id: str) -> dict[str, Any]:
    key_id = get_razorpay_key_id()
    key_secret = get_razorpay_key_secret()
    base_url = get_razorpay_api_base_url()

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.get(
            f"{base_url}/v1/subscriptions/{subscription_id}",
            auth=(key_id, key_secret),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_razorpay_error(response)
            status = response.status_code
            msg = f"Razorpay fetch_subscription failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()
