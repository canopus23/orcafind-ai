import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

import httpx

_DEFAULT_TIMEOUT = float(os.getenv("DODO_PAYMENTS_HTTP_TIMEOUT_SECONDS", "60") or "60")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def get_dodo_payments_api_key() -> str:
    return _require_env("DODO_PAYMENTS_API_KEY")


def get_dodo_payments_environment() -> str:
    env = (os.getenv("DODO_PAYMENTS_ENVIRONMENT") or "live_mode").strip().lower()
    return "test_mode" if env in {"test", "test_mode", "sandbox"} else "live_mode"


def get_dodo_payments_api_base_url() -> str:
    override = (os.getenv("DODO_PAYMENTS_API_BASE_URL") or "").strip().rstrip("/")
    if override:
        return override
    env = get_dodo_payments_environment()
    return "https://test.dodopayments.com" if env == "test_mode" else "https://live.dodopayments.com"


def get_dodo_payments_webhook_key() -> str:
    return _require_env("DODO_PAYMENTS_WEBHOOK_KEY")


def _parse_dodo_error(response: httpx.Response) -> str:
    detail = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            code = str(data.get("code") or "").strip()
            msg = str(data.get("message") or "").strip()
            if code and msg:
                detail = f"{code}: {msg}"
            else:
                detail = msg or str(data)[:300]
        else:
            detail = str(data)[:300]
    except Exception:
        detail = (response.text or "").strip().replace("\n", " ")[:300]
    return detail


def _to_epoch_seconds(value: str | None) -> int | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        # Dodo uses ISO 8601 timestamps, usually with Z suffix.
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


async def create_checkout_session(
    *,
    product_id: str,
    email: str,
    return_url: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = get_dodo_payments_api_key()
    base_url = get_dodo_payments_api_base_url()

    payload: dict[str, Any] = {
        "product_cart": [{"product_id": product_id, "quantity": 1}],
        "customer": {"email": email},
        "return_url": return_url,
    }
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/checkouts",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            msg = f"Dodo Payments create_checkout_session failed (HTTP {response.status_code})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def fetch_subscription(*, subscription_id: str) -> dict[str, Any]:
    api_key = get_dodo_payments_api_key()
    base_url = get_dodo_payments_api_base_url()

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.get(
            f"{base_url}/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            msg = f"Dodo Payments fetch_subscription failed (HTTP {response.status_code})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def change_plan(
    *,
    subscription_id: str,
    product_id: str,
    proration_billing_mode: str = "difference_immediately",
    quantity: int = 1,
) -> dict[str, Any]:
    api_key = get_dodo_payments_api_key()
    base_url = get_dodo_payments_api_base_url()

    payload = {
        "product_id": product_id,
        "proration_billing_mode": proration_billing_mode,
        "quantity": int(quantity),
    }

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}/subscriptions/{subscription_id}/change-plan",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            msg = f"Dodo Payments change_plan failed (HTTP {response.status_code})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def cancel_subscription(
    *,
    subscription_id: str,
    cancel_at_next_billing_date: bool = True,
) -> dict[str, Any]:
    api_key = get_dodo_payments_api_key()
    base_url = get_dodo_payments_api_base_url()

    payload = {"cancel_at_next_billing_date": bool(cancel_at_next_billing_date)}

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.patch(
            f"{base_url}/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            msg = f"Dodo Payments cancel_subscription failed (HTTP {response.status_code})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


def verify_webhook_signature(*, body: bytes, webhook_id: str, webhook_timestamp: str, signature: str) -> bool:
    """
    Dodo Payments follows Standard Webhooks signature verification.

    Signed content: "{webhook-id}.{webhook-timestamp}.{raw_body}"
    Signature header: space-delimited list of "v1,<base64>" entries (rotation supported).
    """
    secret = get_dodo_payments_webhook_key()
    if not signature:
        return False

    body_text = body.decode("utf-8")
    signed_content = f"{webhook_id}.{webhook_timestamp}.{body_text}".encode("utf-8")

    # Standard Webhooks expects a base64 secret. Be permissive: if decoding fails, fall back
    # to using the raw string bytes as the HMAC key.
    key_bytes: bytes
    try:
        key_bytes = base64.b64decode(secret, validate=True)
    except Exception:
        key_bytes = secret.encode("utf-8")

    computed = hmac.new(key_bytes, signed_content, hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")

    # Signature header can include multiple signatures (secret rotation).
    parts = [p.strip() for p in str(signature).split(" ") if p.strip()]
    for part in parts:
        # Expected format: "v1,<sig>"
        if "," in part:
            _ver, sig = part.split(",", 1)
        else:
            sig = part
        if hmac.compare_digest(sig.strip(), computed_b64):
            return True
    return False


def subscription_period_from_payload(sub: dict[str, Any]) -> tuple[int | None, int | None]:
    start = _to_epoch_seconds(str(sub.get("previous_billing_date") or "") or None)
    end = _to_epoch_seconds(str(sub.get("next_billing_date") or "") or None)
    return start, end
