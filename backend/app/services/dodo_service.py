import base64
import hashlib
import hmac
import os
import time
from typing import Any

import httpx

_DEFAULT_TIMEOUT = float(os.getenv("DODO_HTTP_TIMEOUT_SECONDS", "60") or "60")
_DEFAULT_TOLERANCE_SECONDS = int(os.getenv("DODO_WEBHOOK_TOLERANCE_SECONDS", "300") or "300")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def get_dodo_api_key() -> str:
    return _require_env("DODO_PAYMENTS_API_KEY")


def get_dodo_api_base_url() -> str:
    # Default to test; override in production.
    return os.getenv("DODO_PAYMENTS_API_BASE_URL", "https://test.dodopayments.com").rstrip("/")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_dodo_api_key()}"}


def _path(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip() or default


def _parse_dodo_error(response: httpx.Response) -> str:
    detail = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            detail = str(data.get("message") or data.get("error") or data)[:300]
        else:
            detail = str(data)[:300]
    except Exception:
        detail = (response.text or "").strip().replace("\n", " ")[:300]
    return detail


async def create_checkout_session(
    *,
    product_id: str,
    quantity: int,
    customer_email: str,
    return_url: str,
    cancel_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Creates a hosted checkout session for subscriptions.

    Note: Dodo API paths can differ by SDK/version. If needed, override via env:
      - DODO_CREATE_CHECKOUT_PATH (default: /checkouts)
    """
    base_url = get_dodo_api_base_url()
    create_path = _path("DODO_CREATE_CHECKOUT_PATH", "/checkouts")
    payload: dict[str, Any] = {
        "product_cart": [{"product_id": product_id, "quantity": int(quantity)}],
        "customer": {"email": customer_email},
        "return_url": return_url,
    }
    if cancel_url:
        payload["cancel_url"] = cancel_url
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}{create_path}",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            status = response.status_code
            msg = f"Dodo create_checkout_session failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def retrieve_subscription(*, subscription_id: str) -> dict[str, Any]:
    base_url = get_dodo_api_base_url()
    template = _path("DODO_GET_SUBSCRIPTION_PATH_TEMPLATE", "/subscriptions/{subscription_id}")
    path = template.format(subscription_id=subscription_id)
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.get(f"{base_url}{path}", headers=_auth_headers())
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            status = response.status_code
            msg = f"Dodo retrieve_subscription failed (HTTP {status})"
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
    base_url = get_dodo_api_base_url()
    template = _path(
        "DODO_CHANGE_PLAN_PATH_TEMPLATE", "/subscriptions/{subscription_id}/change-plan"
    )
    path = template.format(subscription_id=subscription_id)
    payload: dict[str, Any] = {
        "product_id": product_id,
        "quantity": int(quantity),
        "proration_billing_mode": proration_billing_mode,
    }
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.post(
            f"{base_url}{path}",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            status = response.status_code
            msg = f"Dodo change_plan failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


async def update_subscription(
    *,
    subscription_id: str,
    cancel_at_next_billing_date: bool | None = None,
) -> dict[str, Any]:
    base_url = get_dodo_api_base_url()
    template = _path("DODO_UPDATE_SUBSCRIPTION_PATH_TEMPLATE", "/subscriptions/{subscription_id}")
    path = template.format(subscription_id=subscription_id)
    payload: dict[str, Any] = {}
    if cancel_at_next_billing_date is not None:
        payload["cancel_at_next_billing_date"] = bool(cancel_at_next_billing_date)
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        response = await client.patch(
            f"{base_url}{path}",
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _parse_dodo_error(response)
            status = response.status_code
            msg = f"Dodo update_subscription failed (HTTP {status})"
            if detail:
                msg = f"{msg}: {detail}"
            raise RuntimeError(msg) from exc
        return response.json()


def _decode_webhook_secret(secret: str) -> bytes:
    s = (secret or "").strip()
    if s.startswith("whsec_"):
        s = s[len("whsec_") :]
    try:
        return base64.b64decode(s)
    except Exception as exc:
        raise RuntimeError("Invalid Dodo webhook secret (expected base64 or whsec_*)") from exc


def verify_webhook_signature(
    *,
    body: bytes,
    webhook_id: str,
    webhook_timestamp: str,
    webhook_signature: str,
    tolerance_seconds: int = _DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """
    Dodo uses the Standard Webhooks (Svix-compatible) signature headers:
    - webhook-id
    - webhook-timestamp (unix seconds)
    - webhook-signature (space-delimited, entries like "v1,<base64sig>")
    """
    secret = _decode_webhook_secret(_require_env("DODO_PAYMENTS_WEBHOOK_KEY"))
    msg_id = (webhook_id or "").strip()
    ts = (webhook_timestamp or "").strip()
    sig_header = (webhook_signature or "").strip()
    if not msg_id or not ts or not sig_header:
        return False

    try:
        ts_int = int(ts)
    except Exception:
        return False
    if tolerance_seconds > 0:
        now = int(time.time())
        if abs(now - ts_int) > int(tolerance_seconds):
            return False

    payload_str = body.decode("utf-8", errors="replace")
    signed = f"{msg_id}.{ts}.{payload_str}".encode("utf-8")
    digest = hmac.new(secret, signed, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")

    for part in sig_header.split():
        version, _, candidate = part.partition(",")
        if version != "v1":
            continue
        if hmac.compare_digest(candidate, expected):
            return True
    return False

