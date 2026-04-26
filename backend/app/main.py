import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
except Exception:  # pragma: no cover - optional dependency
    sentry_sdk = None  # type: ignore[assignment]
    FastApiIntegration = None  # type: ignore[assignment]

from app.db import get_db_diagnostics, get_engine
from app.dependencies.auth import verify_user
from app.dependencies.rate_limit import RateLimitConfig, rate_limit
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.billing import (
    DodoCancelSubscriptionRequest,
    DodoChangePlanRequest,
    DodoCreateCheckoutSessionRequest,
    DodoSyncSubscriptionRequest,
    RazorpayCancelSubscriptionRequest,
    RazorpayChangePlanRequest,
    RazorpayCreateOrderRequest,
    RazorpayCreateSubscriptionRequest,
    RazorpayVerifyRequest,
    RazorpayVerifySubscriptionRequest,
)
from app.schemas.complete_post import CompletePostRequest
from app.schemas.images import ImageGenerateRequest
from app.schemas.request import ContentRequest
from app.services.ai_service import (
    generate_linkedin_post,
    generate_social_content,
    generate_social_content_from_image,
)
from app.services.dodo_service import (
    change_plan as dodo_change_plan,
    create_checkout_session as dodo_create_checkout_session,
    retrieve_subscription as dodo_retrieve_subscription,
    update_subscription as dodo_update_subscription,
    verify_webhook_signature as dodo_verify_webhook_signature,
)
from app.services.image_service import generate_openai_images, generate_placeholder_images
from app.services.razorpay_service import (
    cancel_scheduled_changes as razorpay_cancel_scheduled_changes,
)
from app.services.razorpay_service import (
    cancel_subscription as razorpay_cancel_subscription,
)
from app.services.razorpay_service import (
    create_order as razorpay_create_order,
)
from app.services.razorpay_service import (
    create_subscription as razorpay_create_subscription,
)
from app.services.razorpay_service import (
    fetch_plan as razorpay_fetch_plan,
)
from app.services.razorpay_service import (
    fetch_subscription as razorpay_fetch_subscription,
)
from app.services.razorpay_service import (
    get_razorpay_key_id,
    verify_signature,
    verify_subscription_signature,
    verify_webhook_signature,
)
from app.services.razorpay_service import (
    update_subscription as razorpay_update_subscription,
)
from app.services.subscriptions import (
    get_plan,
    get_plan_for_order,
    get_subscription_state,
    get_usage,
    get_user_for_order,
    get_user_for_subscription,
    grant_plan,
    has_paid_plan,
    init_schema,
    is_usage_db_configured,
    link_order_to_user,
    record_image_usage,
    record_usage,
    record_webhook_digest,
    set_scheduled_plan,
    upsert_subscription_state,
)

logger = logging.getLogger("orcafind.api")

PLAN_LIMITS = {
    "free": {
        "text_posts": 60,          # /repurpose/ runs per month
        "image_to_posts": 5,       # /repurpose/image runs per month
        "post_builder": 0,         # /posts/complete (includes images) is Pro-only
        "image_generations": 0,    # /images/generate is Pro-only
        "x_single_variants": 2,
        "x_thread_tweets_min": 4,
        "x_thread_tweets_max": 7,
    },
    # Paid plans (monthly).
    "starter": {
        "text_posts": 300,
        "image_to_posts": 25,
        "post_builder": 10,
        "image_generations": 25,
        "x_single_variants": 4,
        "x_thread_tweets_min": 4,
        "x_thread_tweets_max": 10,
    },
    "pro": {
        "text_posts": 1200,
        "image_to_posts": 120,
        "post_builder": 50,
        "image_generations": 120,
        "x_single_variants": 4,
        "x_thread_tweets_min": 4,
        "x_thread_tweets_max": 10,
    },
    "business": {
        "text_posts": 4000,
        "image_to_posts": 400,
        "post_builder": 200,
        "image_generations": 400,
        "x_single_variants": 4,
        "x_thread_tweets_min": 4,
        "x_thread_tweets_max": 10,
    },
}

PLAN_PRICES_INR_PAISE = {
    "starter": 49900,
    "pro": 149900,
    "business": 299900,
}

PLAN_TIER = {"free": 0, "starter": 1, "pro": 2, "business": 3}

_RAZORPAY_MAX_END_TIME = 4_765_046_400  # 2121-01-01T00:00:00Z (Razorpay validation window)


def _billing_currency() -> str:
    """
    Billing currency used for displaying prices and creating one-time Razorpay orders.

    Note: Razorpay *subscriptions* use the currency configured on the Razorpay Plan IDs.
    If you switch to USD, you must create USD Razorpay Plans and update the RAZORPAY_PLAN_ID_*
    env vars accordingly.
    """
    value = (os.getenv("BILLING_CURRENCY") or "INR").strip().upper()
    return value or "INR"


def _billing_prices_minor(currency: str) -> dict[str, int]:
    """
    Return plan prices in the currency's minor unit (paise for INR, cents for USD, etc.).

    For INR we default to PLAN_PRICES_INR_PAISE for backwards compatibility.
    For non-INR currencies, prices must be configured explicitly via env vars:
      BILLING_PRICE_STARTER_MINOR
      BILLING_PRICE_PRO_MINOR
      BILLING_PRICE_BUSINESS_MINOR
    """
    currency = (currency or "INR").strip().upper()
    out: dict[str, int] = {}
    missing: list[str] = []
    for plan in ("starter", "pro", "business"):
        env_key = f"BILLING_PRICE_{plan.upper()}_MINOR"
        raw = (os.getenv(env_key) or "").strip()
        if raw:
            out[plan] = int(raw)
            continue
        if currency == "INR":
            out[plan] = int(PLAN_PRICES_INR_PAISE[plan])
        else:
            missing.append(env_key)
    if missing:
        raise RuntimeError(
            "Missing billing price env vars for currency "
            f"{currency}: {', '.join(missing)}"
        )
    return out


def _razorpay_plan_id(plan: str) -> str:
    """
    Map our plan names to Razorpay Plan IDs (required for recurring subscriptions).
    Configure these in Railway:
    - RAZORPAY_PLAN_ID_STARTER
    - RAZORPAY_PLAN_ID_PRO
    - RAZORPAY_PLAN_ID_BUSINESS
    """
    p = (plan or "").strip().lower()
    env_key = {
        "starter": "RAZORPAY_PLAN_ID_STARTER",
        "pro": "RAZORPAY_PLAN_ID_PRO",
        "business": "RAZORPAY_PLAN_ID_BUSINESS",
    }.get(p)
    if not env_key:
        raise RuntimeError("Unsupported plan")
    value = (os.getenv(env_key) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {env_key}")
    return value


def _plan_from_razorpay_plan_id(plan_id: str | None) -> str | None:
    if not plan_id:
        return None
    plan_id = str(plan_id).strip()
    mapping = {
        (os.getenv("RAZORPAY_PLAN_ID_STARTER") or "").strip(): "starter",
        (os.getenv("RAZORPAY_PLAN_ID_PRO") or "").strip(): "pro",
        (os.getenv("RAZORPAY_PLAN_ID_BUSINESS") or "").strip(): "business",
    }
    return mapping.get(plan_id) or None


def _dodo_product_id(plan: str) -> str:
    """
    Map our plan names to Dodo Product IDs (subscription products).
    Env vars:
    - DODO_PRODUCT_ID_STARTER (or legacy: DODO_PLAN_ID_STARTER)
    - DODO_PRODUCT_ID_PRO (or legacy: DODO_PLAN_ID_PRO)
    - DODO_PRODUCT_ID_BUSINESS (or legacy: DODO_PLAN_ID_BUSINESS)
    """
    p = (plan or "").strip().lower()
    env_keys = {
        "starter": ("DODO_PRODUCT_ID_STARTER", "DODO_PLAN_ID_STARTER"),
        "pro": ("DODO_PRODUCT_ID_PRO", "DODO_PLAN_ID_PRO"),
        "business": ("DODO_PRODUCT_ID_BUSINESS", "DODO_PLAN_ID_BUSINESS"),
    }.get(p)
    if not env_keys:
        raise RuntimeError("Unsupported plan")
    for key in env_keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    raise RuntimeError(f"Missing required env var: {env_keys[0]}")


def _plan_from_dodo_product_id(product_id: str | None) -> str | None:
    if not product_id:
        return None
    pid = str(product_id).strip()
    mapping = {
        (os.getenv("DODO_PRODUCT_ID_STARTER") or os.getenv("DODO_PLAN_ID_STARTER") or "").strip(): "starter",
        (os.getenv("DODO_PRODUCT_ID_PRO") or os.getenv("DODO_PLAN_ID_PRO") or "").strip(): "pro",
        (
            os.getenv("DODO_PRODUCT_ID_BUSINESS")
            or os.getenv("DODO_PLAN_ID_BUSINESS")
            or ""
        ).strip(): "business",
    }
    return mapping.get(pid) or None


def _estimate_cycle_seconds(*, period: str, interval: int) -> int:
    # Razorpay plan periods are typically: daily, weekly, monthly, yearly.
    # For month/year we use conservative approximations to keep the computed end_time
    # inside Razorpay's accepted window.
    p = (period or "").strip().lower()
    step = max(1, int(interval or 1))
    if p == "daily":
        return 86_400 * step
    if p == "weekly":
        return 7 * 86_400 * step
    if p == "yearly":
        return 365 * 86_400 * step
    # monthly (and unknown): 30-day approximation.
    return 30 * 86_400 * step


def _parse_iso8601_to_epoch_seconds(value: str | None) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


async def _safe_total_count_for_plan(*, plan_id: str, requested: int) -> int:
    req = max(1, int(requested or 1))
    now = int(time.time())

    period = "monthly"
    interval = 1
    try:
        plan = await razorpay_fetch_plan(plan_id=plan_id)
        if isinstance(plan, dict):
            period = str(plan.get("period") or period)
            interval = int(plan.get("interval") or interval)
    except Exception:
        # If Razorpay plan fetch fails, keep the conservative fallback.
        pass

    cycle_seconds = _estimate_cycle_seconds(period=period, interval=interval)
    # Clamp total_count so Razorpay never computes an end_time beyond their accepted max.
    max_count = max(1, int((_RAZORPAY_MAX_END_TIME - now) // max(1, cycle_seconds)))
    return min(req, max_count)


def _limits_for_plan(plan: str) -> dict:
    return PLAN_LIMITS.get((plan or "free").strip().lower(), PLAN_LIMITS["free"])


def _remaining(limit: int, used: int) -> int:
    return max(0, int(limit) - int(used))


def _usage_error(*, feature: str, limit: int, used: int) -> HTTPException:
    return HTTPException(
        status_code=402,
        detail={
            "message": f"Limit reached for {feature}. Upgrade to Pro for more.",
            "feature": feature,
            "limit": int(limit),
            "used": int(used),
            "remaining": _remaining(limit, used),
        },
    )

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

if os.getenv("SENTRY_DSN"):
    if sentry_sdk and FastApiIntegration:
        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            integrations=[FastApiIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            environment=os.getenv("ENV", "development"),
            release=os.getenv("RELEASE", None),
        )
    else:
        logger.warning("SENTRY_DSN set but sentry-sdk is not installed; skipping Sentry init.")

app = FastAPI(title="OrcaFind AI API")
app.add_middleware(RequestContextMiddleware)

@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    # Always return JSON on unexpected errors. CORS headers are handled by CORSMiddleware.
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled server error (request_id=%s)", request_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "request_id": request_id},
    )


@app.get("/internal/db")
async def internal_db(user=Depends(verify_user)):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Forbidden")

    info = get_db_diagnostics()
    ok = False
    err = ""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ok = True
    except Exception as e:
        err = str(e or "").strip().replace("\n", " ")[:240]

    return {"ok": ok, "db": info, "error": err}

@app.on_event("startup")
def _startup():
    try:
        init_schema()
    except Exception:
        # Never crash the API on startup due to transient DB connectivity.
        logger.exception("Startup: init_schema failed (DB unreachable).")

def _parse_csv_set(value: str | None, *, lowercase: bool = True) -> set[str]:
    if not value:
        return set()
    items = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        items.append(item.lower() if lowercase else item)
    return set(items)


def _get_user_email(payload: dict) -> str | None:
    email = payload.get("email")
    if isinstance(email, str) and email:
        return email
    user_meta = payload.get("user_metadata") or {}
    if isinstance(user_meta, dict):
        meta_email = user_meta.get("email") or user_meta.get("preferred_email")
        if isinstance(meta_email, str) and meta_email:
            return meta_email
    return None


def is_premium_user(payload: dict) -> bool:
    allowlist = _parse_csv_set(os.getenv("PREMIUM_EMAIL_ALLOWLIST"), lowercase=True)
    user_id = str(payload.get("sub") or "user")
    if has_paid_plan(user_id):
        return True
    email = _get_user_email(payload)
    return bool(email and email.strip().lower() in allowlist)


def get_effective_plan(payload: dict) -> str:
    if is_admin_user(payload):
        return "admin"

    user_id = str(payload.get("sub") or "user")
    plan = (get_plan(user_id) or "").strip().lower()
    if plan in {"starter", "pro", "business"}:
        return plan

    # Allowlisted users behave like "pro" for now.
    allowlist = _parse_csv_set(os.getenv("PREMIUM_EMAIL_ALLOWLIST"), lowercase=True)
    email = _get_user_email(payload)
    if email and email.strip().lower() in allowlist:
        return "pro"

    return "free"


def is_admin_user(payload: dict) -> bool:
    """
    Admin users bypass paywalls/limits for testing.
    Configure via env:
    - ADMIN_EMAIL_ALLOWLIST: comma-separated emails
    - ADMIN_SUB_ALLOWLIST: optional comma-separated Supabase user IDs ("sub") for extra safety
    """
    sub_allowlist = _parse_csv_set(os.getenv("ADMIN_SUB_ALLOWLIST"), lowercase=False)
    user_id = str(payload.get("sub") or "")
    if user_id and user_id in sub_allowlist:
        return True

    email_allowlist = _parse_csv_set(os.getenv("ADMIN_EMAIL_ALLOWLIST"), lowercase=True)
    email = _get_user_email(payload)
    return bool(email and email.strip().lower() in email_allowlist)

# Define allowed origins explicitly for CORS.
# We always include the known production/local origins to avoid misconfiguration in env overrides.
default_origins = {
    "https://orcafind.com",
    "https://www.orcafind.com",
    "https://orcafind-api-staging.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
origins = set(_parse_csv_set(os.getenv("CORS_ALLOW_ORIGINS"), lowercase=False)) | default_origins
cors_allow_all = (os.getenv("CORS_ALLOW_ALL") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# CORS: keep this middleware as the outermost wrapper so preflight OPTIONS and error responses
# always include the required Access-Control-* headers. In Starlette/FastAPI, add_middleware()
# inserts at the beginning of the list, so the *last* add_middleware call becomes the outermost.
app.add_middleware(
    CORSMiddleware,
    # For bearer-token APIs (no cookies), it's safe to allow all origins.
    # This avoids a common production failure mode: missing/stripped CORS headers on edge errors.
    allow_origins=["*"] if cors_allow_all else list(origins),
    allow_origin_regex=None if cors_allow_all else os.getenv("CORS_ALLOW_ORIGIN_REGEX"),
    # We use Bearer tokens (Authorization header), not cookies.
    # Keeping credentials disabled avoids wildcard/CORS edge-cases.
    allow_credentials=False,
    # Be permissive on headers/methods so preflights don't fail due to unexpected headers.
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "online", "message": "OrcaFind API is operational"}


@app.get("/billing/catalog")
async def billing_catalog():
    """
    Public billing catalog for the frontend.

    This keeps the UI currency + amounts consistent with backend/Razorpay configuration.
    """
    currency = _billing_currency()
    try:
        prices = _billing_prices_minor(currency)
        configured = True
        error = None
    except Exception as e:
        # Don't crash public pages if billing isn't configured yet.
        configured = False
        error = str(e or "").strip()[:200]
        prices = {"starter": 0, "pro": 0, "business": 0}

    provider = (os.getenv("BILLING_PROVIDER") or "razorpay").strip().lower()
    if provider not in {"razorpay", "dodo"}:
        provider = "razorpay"

    return {
        "provider": provider,
        "currency": currency,
        "interval": "month",
        "configured": configured,
        "supports_upi": currency == "INR",
        "plans": {
            "free": {"label": "Free", "amount_minor": 0},
            "starter": {"label": "Starter", "amount_minor": int(prices["starter"])},
            "pro": {"label": "Pro", "amount_minor": int(prices["pro"])},
            "business": {"label": "Business", "amount_minor": int(prices["business"])},
        },
        "error": error,
    }


@app.get("/entitlements")
async def entitlements(user=Depends(verify_user)):
    return _build_entitlements_payload(user)


@app.post("/billing/dodo/checkout-session")
async def dodo_checkout_session_create(
    request: Request,
    req: DodoCreateCheckoutSessionRequest,
    user=Depends(verify_user),
):
    plan = (req.plan or "starter").strip().lower()
    if plan not in {"starter", "pro", "business"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    user_id = str(user.get("sub") or "user")
    email = _get_user_email(user) or (req.email or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Missing customer email")

    origin = (
        (request.headers.get("origin") or "").strip()
        or (os.getenv("FRONTEND_BASE_URL") or "").strip()
        or "https://orcafind.com"
    ).rstrip("/")
    return_url = (os.getenv("DODO_CHECKOUT_RETURN_URL") or "").strip() or (
        f"{origin}/checkout/?dodo_return=1"
    )
    cancel_url = (os.getenv("DODO_CHECKOUT_CANCEL_URL") or "").strip() or (
        f"{origin}/checkout/?dodo_cancel=1"
    )

    try:
        product_id = _dodo_product_id(plan)
        session = await dodo_create_checkout_session(
            product_id=product_id,
            quantity=1,
            customer_email=email,
            return_url=return_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id, "plan": plan, "email": email},
        )
    except RuntimeError as e:
        msg = str(e or "").strip()
        if msg.startswith("Missing required env var:"):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Billing is not configured on the server.",
                    "request_id": request.state.request_id,
                },
            ) from e
        raise HTTPException(
            status_code=502,
            detail={"message": msg or "Dodo error", "request_id": request.state.request_id},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Dodo error: {type(e).__name__}",
                "request_id": request.state.request_id,
            },
        ) from e

    return {
        "plan": plan,
        "session_id": session.get("session_id") or session.get("id"),
        "checkout_url": session.get("checkout_url") or session.get("url"),
    }


@app.post("/billing/dodo/subscription/sync")
async def dodo_subscription_sync(
    request: Request,
    req: DodoSyncSubscriptionRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")
    sub_id = (req.subscription_id or "").strip()
    if not sub_id:
        raise HTTPException(status_code=400, detail="Missing subscription_id")

    try:
        sub = await dodo_retrieve_subscription(subscription_id=sub_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": str(e), "request_id": request.state.request_id},
        ) from e

    product_id = sub.get("product_id") or (sub.get("product") or {}).get("product_id")
    plan = _plan_from_dodo_product_id(product_id) or "pro"
    status = str(sub.get("status") or "unknown").strip().lower()
    current_start = _parse_iso8601_to_epoch_seconds(sub.get("previous_billing_date"))
    current_end = _parse_iso8601_to_epoch_seconds(sub.get("next_billing_date"))
    cancel_at_next = bool(sub.get("cancel_at_next_billing_date"))

    customer_id = None
    customer = sub.get("customer")
    if isinstance(customer, dict):
        customer_id = customer.get("customer_id") or customer.get("id")

    upsert_subscription_state(
        user_id=user_id,
        provider="dodo",
        subscription_id=str(sub.get("subscription_id") or sub.get("id") or sub_id),
        customer_id=customer_id,
        plan=plan,
        status=status,
        current_period_start=current_start,
        current_period_end=current_end,
        cancel_at_cycle_end=cancel_at_next,
        scheduled_plan=None,
    )

    return {"status": "ok", "entitlements": _build_entitlements_payload(user)}


@app.post("/billing/dodo/subscription/change")
async def dodo_subscription_change(
    request: Request,
    req: DodoChangePlanRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")
    state = get_subscription_state(user_id) or {}
    sub_id = str(state.get("subscription_id") or "").strip()
    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription to update")

    target = (req.plan or "").strip().lower()
    if target not in {"starter", "pro", "business"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    try:
        product_id = _dodo_product_id(target)
        await dodo_change_plan(subscription_id=sub_id, product_id=product_id)
        sub = await dodo_retrieve_subscription(subscription_id=sub_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": str(e), "request_id": request.state.request_id},
        ) from e

    product_id = sub.get("product_id") or (sub.get("product") or {}).get("product_id")
    plan = _plan_from_dodo_product_id(product_id) or target
    status = str(sub.get("status") or "unknown").strip().lower()
    current_start = _parse_iso8601_to_epoch_seconds(sub.get("previous_billing_date"))
    current_end = _parse_iso8601_to_epoch_seconds(sub.get("next_billing_date"))
    cancel_at_next = bool(sub.get("cancel_at_next_billing_date"))

    customer_id = None
    customer = sub.get("customer")
    if isinstance(customer, dict):
        customer_id = customer.get("customer_id") or customer.get("id")

    upsert_subscription_state(
        user_id=user_id,
        provider="dodo",
        subscription_id=str(sub.get("subscription_id") or sub.get("id") or sub_id),
        customer_id=customer_id,
        plan=plan,
        status=status,
        current_period_start=current_start,
        current_period_end=current_end,
        cancel_at_cycle_end=cancel_at_next,
        scheduled_plan=None,
    )

    return {"status": "ok", "entitlements": _build_entitlements_payload(user)}


@app.post("/billing/dodo/subscription/cancel")
async def dodo_subscription_cancel(
    request: Request,
    req: DodoCancelSubscriptionRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")
    state = get_subscription_state(user_id) or {}
    sub_id = str(state.get("subscription_id") or "").strip()
    if not sub_id:
        raise HTTPException(status_code=400, detail="No subscription found")

    cancel_at_cycle_end = bool(req.cancel_at_cycle_end)
    if not cancel_at_cycle_end:
        raise HTTPException(
            status_code=400,
            detail="Immediate cancellation is not implemented. Use cancel_at_cycle_end=true.",
        )

    try:
        sub = await dodo_update_subscription(
            subscription_id=sub_id, cancel_at_next_billing_date=True
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": str(e), "request_id": request.state.request_id},
        ) from e

    product_id = sub.get("product_id") or (sub.get("product") or {}).get("product_id")
    plan = _plan_from_dodo_product_id(product_id) or (state.get("plan") or "pro")
    status = str(sub.get("status") or "unknown").strip().lower()
    current_start = _parse_iso8601_to_epoch_seconds(sub.get("previous_billing_date"))
    current_end = _parse_iso8601_to_epoch_seconds(sub.get("next_billing_date"))
    cancel_at_next = bool(sub.get("cancel_at_next_billing_date"))

    customer_id = None
    customer = sub.get("customer")
    if isinstance(customer, dict):
        customer_id = customer.get("customer_id") or customer.get("id")

    upsert_subscription_state(
        user_id=user_id,
        provider="dodo",
        subscription_id=str(sub.get("subscription_id") or sub.get("id") or sub_id),
        customer_id=customer_id,
        plan=str(plan),
        status=status,
        current_period_start=current_start,
        current_period_end=current_end,
        cancel_at_cycle_end=cancel_at_next,
        scheduled_plan=None,
    )

    return {
        "status": "ok",
        "cancel_at_cycle_end": bool(cancel_at_next),
        "entitlements": _build_entitlements_payload(user),
    }


@app.post("/billing/dodo/webhook")
async def dodo_webhook(request: Request):
    body = await request.body()
    webhook_id = (request.headers.get("webhook-id") or "").strip()
    webhook_timestamp = (request.headers.get("webhook-timestamp") or "").strip()
    webhook_signature = (request.headers.get("webhook-signature") or "").strip()

    if not dodo_verify_webhook_signature(
        body=body,
        webhook_id=webhook_id,
        webhook_timestamp=webhook_timestamp,
        webhook_signature=webhook_signature,
    ):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    digest = hashlib.sha256(body).hexdigest()
    if not record_webhook_digest(digest=digest, provider="dodo"):
        return {"status": "duplicate"}

    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    payload = data.get("data") or data.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    # subscription object may be nested under data.subscription in some events
    subscription = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload

    if isinstance(subscription, dict):
        sub_id = str(subscription.get("subscription_id") or subscription.get("id") or "").strip()
        if sub_id:
            user_id = get_user_for_subscription(sub_id)

            metadata = subscription.get("metadata") or {}
            if not user_id and isinstance(metadata, dict):
                user_id = str(metadata.get("user_id") or "") or None

            if user_id:
                product_id = subscription.get("product_id") or (subscription.get("product") or {}).get(
                    "product_id"
                )
                plan = _plan_from_dodo_product_id(product_id) or (
                    (get_subscription_state(user_id) or {}).get("plan") or "pro"
                )
                status = str(subscription.get("status") or "unknown").strip().lower()
                current_start = _parse_iso8601_to_epoch_seconds(subscription.get("previous_billing_date"))
                current_end = _parse_iso8601_to_epoch_seconds(subscription.get("next_billing_date"))
                cancel_at_next = bool(subscription.get("cancel_at_next_billing_date"))

                customer_id = None
                customer = subscription.get("customer")
                if isinstance(customer, dict):
                    customer_id = customer.get("customer_id") or customer.get("id")

                upsert_subscription_state(
                    user_id=user_id,
                    provider="dodo",
                    subscription_id=sub_id,
                    customer_id=customer_id,
                    plan=plan,
                    status=status,
                    current_period_start=current_start,
                    current_period_end=current_end,
                    cancel_at_cycle_end=cancel_at_next,
                    scheduled_plan=None,
                )

    return {"status": "ok"}


def _build_entitlements_payload(user: dict) -> dict:
    """
    Build the entitlements response payload.

    This is used by both /entitlements and billing endpoints so the UI can update
    immediately after a payment without an extra roundtrip.
    """
    plan = get_effective_plan(user)
    admin = plan == "admin"
    premium = plan in {"starter", "pro", "business", "admin"}
    user_id = str(user.get("sub") or "user")
    sub_state = get_subscription_state(user_id) or None

    limits = _limits_for_plan("business" if admin else plan)
    env = os.getenv("ENV", "development").strip().lower()
    try:
        usage = get_usage(user_id)
        used_text = int(usage.get("text_used", 0))
        used_vision = int(usage.get("vision_used", 0))
        used_builder = int(usage.get("builder_used", 0))
        used_images = int(usage.get("image_used", 0))

        remaining_text = 100_000 if admin else _remaining(int(limits["text_posts"]), used_text)
        remaining_vision = (
            100_000 if admin else _remaining(int(limits["image_to_posts"]), used_vision)
        )
        remaining_builder = (
            100_000 if admin else _remaining(int(limits["post_builder"]), used_builder)
        )
        remaining_images = (
            100_000 if admin else _remaining(int(limits["image_generations"]), used_images)
        )
    except Exception:
        # Fail closed in production if usage DB is misconfigured/unreachable.
        if (not premium) and env in {"prod", "production"}:
            used_text = int(limits["text_posts"])
            used_vision = int(limits["image_to_posts"])
            used_builder = int(limits["post_builder"])
            used_images = int(limits["image_generations"])
            remaining_text = 0
            remaining_vision = 0
            remaining_builder = 0
            remaining_images = 0
        else:
            used_text = 0
            used_vision = 0
            used_builder = 0
            used_images = 0
            remaining_text = int(limits["text_posts"])
            remaining_vision = int(limits["image_to_posts"])
            remaining_builder = int(limits["post_builder"])
            remaining_images = int(limits["image_generations"])
    return {
        "plan": plan,
        "is_admin": admin,
        "is_premium": premium,
        "subscription": (
            {
                "provider": sub_state.get("provider"),
                "status": sub_state.get("status"),
                "current_period_start": sub_state.get("current_period_start"),
                "current_period_end": sub_state.get("current_period_end"),
                "cancel_at_cycle_end": sub_state.get("cancel_at_cycle_end"),
                "scheduled_plan": sub_state.get("scheduled_plan"),
            }
            if sub_state
            else None
        ),
        "limits": {
            "x_single_variants": int(limits["x_single_variants"]),
            "x_thread_tweets_min": int(limits["x_thread_tweets_min"]),
            "x_thread_tweets_max": int(limits["x_thread_tweets_max"]),
            "text_posts_total": int(limits["text_posts"]) if not admin else 100_000,
            "text_posts_used": int(used_text),
            "text_posts_remaining": int(remaining_text),
            "image_to_posts_total": int(limits["image_to_posts"]) if not admin else 100_000,
            "image_to_posts_used": int(used_vision),
            "image_to_posts_remaining": int(remaining_vision),
            "post_builder_total": int(limits["post_builder"]) if not admin else 100_000,
            "post_builder_used": int(used_builder),
            "post_builder_remaining": int(remaining_builder),
            "image_generations_total": int(limits["image_generations"]) if not admin else 100_000,
            "image_generations_used": used_images,
            "image_generations_remaining": remaining_images,
        },
    }


@app.post("/images/generate")
async def generate_images(
    req: ImageGenerateRequest,
    user=Depends(verify_user),
    _rl=Depends(rate_limit(RateLimitConfig(limit=20, window_seconds=60, key_prefix="images"))),
):
    plan = get_effective_plan(user)
    admin = plan == "admin"
    premium = plan in {"starter", "pro", "business", "admin"}
    user_id = str(user.get("sub") or "user")

    # Product rule: AI image generation is Pro-only (and admin for testing).
    if (not admin) and (not premium):
        raise HTTPException(
            status_code=402,
            detail={
                "message": "AI image generation is available on Pro plans. Upgrade to unlock.",
                "feature": "image_generations",
            },
        )

    limits = _limits_for_plan("business" if admin else plan)
    if not admin:
        env = os.getenv("ENV", "development").strip().lower()
        if (not is_usage_db_configured()) and (env in {"prod", "production"}):
            raise HTTPException(status_code=503, detail="Usage tracking is not configured")
        usage = get_usage(user_id)
        used = int(usage.get("image_used", 0))
        inc = min(3, max(1, int(req.count or 1)))
        if used + inc > int(limits["image_generations"]):
            raise _usage_error(
                feature="image_generations",
                limit=int(limits["image_generations"]),
                used=used,
            )

    # Prefer OpenAI if configured; fall back to placeholder images for local/dev.
    images = None
    if os.getenv("OPENAI_API_KEY"):
        quality = "medium"
        count = min(3, max(1, int(req.count or 1)))
        images = generate_openai_images(
            brief=req.brief,
            style=req.style,
            aspect=req.aspect,
            count=count,
            quality=quality,
            user_id=user_id,
        )
    else:
        images = generate_placeholder_images(
            brief=req.brief,
            style=req.style,
            aspect=req.aspect,
            count=min(3, max(1, int(req.count or 1))),
        )

    # Usage accounting (monthly).
    if not admin:
        record_image_usage(user_id, n=min(3, max(1, int(req.count or 1))))
    return {"images": images}


def _parse_sections(result: str) -> dict:
    """
    Parse LLM output using stable headers:
      X:
      LinkedIn:
      Instagram:
      Facebook:
    Returns a dict with keys: x, linkedin, instagram, facebook (missing keys -> "").
    """
    text = (result or "").strip()
    out = {"x": "", "linkedin": "", "instagram": "", "facebook": ""}

    # Generic header scanner.
    # Allow optional text on the header line (models sometimes format as "LinkedIn: <text>").
    pattern = r"(?im)^(X|LinkedIn|Instagram|Facebook):\s*"
    matches = list(re.finditer(pattern, text))
    if not matches:
        # Fallback: try to split the older 2-section format.
        parts = re.split(r"(?i)linkedin:\s*", text, maxsplit=1)
        out["x"] = re.sub(r"(?is)^\s*x:\s*", "", parts[0] if parts else "").strip()
        out["linkedin"] = (parts[1] if len(parts) > 1 else "").strip()
        return out

    spans = []
    for idx, m in enumerate(matches):
        header = m.group(1)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        spans.append((header, start, end))

    for header, start, end in spans:
        chunk = text[start:end].strip()
        if header == "X":
            out["x"] = chunk
        elif header == "LinkedIn":
            out["linkedin"] = chunk
        elif header == "Instagram":
            out["instagram"] = chunk
        elif header == "Facebook":
            out["facebook"] = chunk

    return out


@app.post("/posts/complete")
async def complete_post(
    req: CompletePostRequest,
    user=Depends(verify_user),
    _rl=Depends(rate_limit(RateLimitConfig(limit=10, window_seconds=60, key_prefix="complete"))),
):
    plan = get_effective_plan(user)
    admin = plan == "admin"
    premium = plan in {"starter", "pro", "business", "admin"}
    user_id = str(user.get("sub") or "user")
    limits = _limits_for_plan("business" if admin else plan)
    if not admin:
        usage = get_usage(user_id)
        used_builder = int(usage.get("builder_used", 0))
        used_images = int(usage.get("image_used", 0))
        if used_builder >= int(limits["post_builder"]):
            raise _usage_error(
                feature="post_builder",
                limit=int(limits["post_builder"]),
                used=used_builder,
            )
        if used_images + 1 > int(limits["image_generations"]):
            raise _usage_error(
                feature="image_generations",
                limit=int(limits["image_generations"]),
                used=used_images,
            )

    result = generate_social_content(
        req.text,
        x_style=req.x_style,
        content_format=req.format,
        is_premium=premium,
    )
    sections = _parse_sections(result)
    x_text = sections.get("x", "").strip()
    linkedin_text = sections.get("linkedin", "").strip()
    instagram_text = sections.get("instagram", "").strip()
    facebook_text = sections.get("facebook", "").strip()
    if not linkedin_text:
        # Fallback: occasionally the model output doesn't conform to the 4-section format.
        # Generate LinkedIn alone to avoid failing the whole Post Builder request.
        linkedin_text = (
            generate_linkedin_post(req.text, content_format=req.format, is_premium=premium) or ""
        ).strip()
    if not linkedin_text:
        raise HTTPException(
            status_code=502,
            detail="LinkedIn output missing from generation result",
        )

    # Build a concise image brief if the user didn't provide one.
    image_brief = (req.image_brief or "").strip()
    if not image_brief:
        snippet = (req.text or "").strip().replace("\n", " ")
        if len(snippet) > 420:
            snippet = snippet[:417] + "..."
        image_brief = f"Create a clean social post cover image that matches this topic: {snippet}"

    images = None
    if os.getenv("OPENAI_API_KEY"):
        images = generate_openai_images(
            brief=image_brief,
            style=(req.image_style or "").strip() or "saas_minimal",
            aspect=req.image_aspect,
            count=1,
            quality="medium" if premium else "low",
            user_id=user_id,
        )
    else:
        images = generate_placeholder_images(
            brief=image_brief,
            style=(req.image_style or "").strip() or "saas_minimal",
            aspect=req.image_aspect,
            count=1,
        )

    if not admin:
        record_usage(user_id, "builder_used", n=1)
        record_image_usage(user_id, n=1)

    return {
        "x": x_text,
        "linkedin": linkedin_text,
        "instagram": instagram_text,
        "facebook": facebook_text,
        "images": images,
    }

@app.post("/billing/razorpay/order")
async def razorpay_create(
    request: Request,
    req: RazorpayCreateOrderRequest,
    user=Depends(verify_user),
):
    plan = (req.plan or "starter").strip().lower()
    if plan not in PLAN_PRICES_INR_PAISE:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    # For now we only offer monthly billing.
    billing = "monthly"

    # Amounts are in the currency's minor unit (paise for INR).
    amount_minor = int(PLAN_PRICES_INR_PAISE[plan])
    currency = "INR"

    user_id = str(user.get("sub") or "user")
    email = _get_user_email(user) or req.email or ""

    try:
        receipt = f"orcafind_{plan}_{billing}_{user_id}"
        if len(receipt) > 40:
            # Razorpay receipt max length is 40 chars.
            # Keep the suffix stable per-user but short.
            suffix = user_id.replace("-", "")[-10:] if user_id else "user"
            receipt = f"orc_{plan}_{billing}_{suffix}"

        order = await razorpay_create_order(
            amount_paise=amount_minor,
            currency=currency,
            receipt=receipt,
            notes={
                "user_id": user_id,
                "plan": plan,
                "billing": billing,
                "email": email,
            },
        )
    except RuntimeError as e:
        msg = str(e or "").strip()
        if msg.startswith("Missing required env var:"):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Billing is not configured on the server.",
                    "request_id": request.state.request_id,
                },
            ) from e

        raise HTTPException(
            status_code=502,
            detail={"message": msg or "Razorpay error", "request_id": request.state.request_id},
        ) from e
    except Exception as e:
        # Fail with a safe upstream error. CORS + request_id header come from middleware.
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Razorpay error: {type(e).__name__}",
                "request_id": request.state.request_id,
            },
        ) from e

    if order.get("id"):
        link_order_to_user(order.get("id"), user_id, plan=plan)

    return {
        "key_id": get_razorpay_key_id(),
        "order_id": order.get("id"),
        "amount": order.get("amount"),
        "currency": order.get("currency"),
        "plan": plan,
        "billing": billing,
        "prefill": {"email": email},
        "name": "OrcaFind AI",
        "description": "OrcaFind Pro Subscription",
    }


@app.post("/billing/razorpay/verify")
async def razorpay_verify(
    request: Request,
    req: RazorpayVerifyRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")

    order_user = get_user_for_order(req.razorpay_order_id)
    if order_user and order_user != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Forbidden: order is linked to a different user.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    try:
        ok = verify_signature(
            order_id=req.razorpay_order_id,
            payment_id=req.razorpay_payment_id,
            signature=req.razorpay_signature,
        )
    except RuntimeError as e:
        msg = str(e or "").strip()
        if msg.startswith("Missing required env var:"):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Billing is not configured on the server.",
                    "request_id": getattr(request.state, "request_id", None),
                },
            ) from e
        raise

    if not ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid payment signature.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    plan = get_plan_for_order(req.razorpay_order_id) or "pro"
    grant_plan(
        user_id=user_id,
        plan=plan,
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
    )
    # Ensure the subscription is actually persisted. If the DB is misconfigured/unreachable,
    # grant_plan() fails open (returns) and the UI would keep showing "free".
    persisted = (get_plan(user_id) or "").strip().lower()
    if persisted != plan:
        # Capture safe DB diagnostics so production debugging doesn't require log access.
        db_info = get_db_diagnostics()
        db_error = ""
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            db_error = str(e or "").strip().replace("\n", " ")[:240]

        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Subscription verified but could not be saved. "
                    "Check DATABASE_URL / DB connectivity "
                    "(and set DB_FORCE_IPV4=true for Supabase if needed)."
                ),
                "db": db_info,
                "db_error": db_error,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
    # Include entitlements so the frontend can update instantly without an extra
    # /entitlements fetch.
    return {
        "status": "ok",
        "plan": plan,
        "effective_plan": get_effective_plan(user),
        "entitlements": _build_entitlements_payload(user),
    }


@app.post("/billing/razorpay/subscription")
async def razorpay_subscription_create(
    request: Request,
    req: RazorpayCreateSubscriptionRequest,
    user=Depends(verify_user),
):
    plan = (req.plan or "pro").strip().lower()
    if plan not in {"starter", "pro", "business"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    user_id = str(user.get("sub") or "user")
    email = _get_user_email(user) or req.email or ""
    plan_id = _razorpay_plan_id(plan)
    # Keep the subscription long-lived, but within Razorpay's end_time validation window.
    requested_total = int(os.getenv("RAZORPAY_SUBSCRIPTION_TOTAL_COUNT", "120"))
    total_count = await _safe_total_count_for_plan(plan_id=plan_id, requested=requested_total)

    try:
        sub = await razorpay_create_subscription(
            plan_id=plan_id,
            total_count=total_count,
            customer_notify=True,
            notes={"user_id": user_id, "plan": plan, "email": email},
        )
    except RuntimeError as e:
        msg = str(e or "").strip()
        raise HTTPException(
            status_code=502,
            detail={"message": msg or "Razorpay error", "request_id": request.state.request_id},
        ) from e

    subscription_id = str(sub.get("id") or "")
    if subscription_id:
        upsert_subscription_state(
            user_id=user_id,
            subscription_id=subscription_id,
            customer_id=sub.get("customer_id"),
            plan=plan,
            status=str(sub.get("status") or "created"),
            current_period_start=int(sub.get("current_start") or 0) or None,
            current_period_end=int(sub.get("current_end") or 0) or None,
            cancel_at_cycle_end=bool(int(sub.get("cancel_at_cycle_end") or 0)),
            scheduled_plan=None,
        )

    return {
        "key_id": get_razorpay_key_id(),
        "subscription_id": subscription_id,
        "plan": plan,
        "prefill": {"email": email},
        "name": "OrcaFind AI",
        "description": "OrcaFind Subscription",
    }


@app.post("/billing/razorpay/subscription/verify")
async def razorpay_subscription_verify(
    request: Request,
    req: RazorpayVerifySubscriptionRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")

    sub_user = get_user_for_subscription(req.razorpay_subscription_id)
    if sub_user and sub_user != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Forbidden: subscription is linked to a different user.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    if not verify_subscription_signature(
        subscription_id=req.razorpay_subscription_id,
        payment_id=req.razorpay_payment_id,
        signature=req.razorpay_signature,
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Invalid payment signature.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # Fetch the subscription from Razorpay so current_start/end and status are accurate.
    try:
        sub = await razorpay_fetch_subscription(subscription_id=req.razorpay_subscription_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"message": str(e), "request_id": request.state.request_id},
        ) from e

    plan = (
        _plan_from_razorpay_plan_id(sub.get("plan_id"))
        or (get_subscription_state(user_id) or {}).get("plan")
        or "pro"
    )
    upsert_subscription_state(
        user_id=user_id,
        subscription_id=str(sub.get("id") or req.razorpay_subscription_id),
        customer_id=sub.get("customer_id"),
        plan=str(plan),
        status=str(sub.get("status") or "active"),
        current_period_start=int(sub.get("current_start") or 0) or None,
        current_period_end=int(sub.get("current_end") or 0) or None,
        cancel_at_cycle_end=bool(int(sub.get("cancel_at_cycle_end") or 0)),
        scheduled_plan=(get_subscription_state(user_id) or {}).get("scheduled_plan"),
    )

    # Fail closed if verification worked but persistence did not. Otherwise the UI will keep
    # showing "free" and the user will get paywalled after a successful payment.
    persisted = (get_plan(user_id) or "").strip().lower()
    if persisted != str(plan).strip().lower():
        db_info = get_db_diagnostics()
        db_error = ""
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            db_error = str(e or "").strip().replace("\n", " ")[:240]

        raise HTTPException(
            status_code=503,
            detail={
                "message": (
                    "Subscription verified but could not be saved. "
                    "Check DATABASE_URL / DB connectivity "
                    "(and set DB_FORCE_IPV4=true for Supabase if needed)."
                ),
                "db": db_info,
                "db_error": db_error,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    return {"status": "ok", "plan": plan, "effective_plan": get_effective_plan(user)}


@app.post("/billing/razorpay/subscription/change")
async def razorpay_subscription_change(
    request: Request,
    req: RazorpayChangePlanRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")
    state = get_subscription_state(user_id) or {}
    sub_id = str(state.get("subscription_id") or "")
    if not sub_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No active subscription found for this account.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    target = (req.plan or "").strip().lower()
    if target not in {"starter", "pro", "business"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")

    current = str(state.get("plan") or "free").strip().lower()
    current_tier = PLAN_TIER.get(current, 0)
    target_tier = PLAN_TIER.get(target, 0)

    schedule_change_at = "now" if target_tier > current_tier else "cycle_end"
    plan_id = _razorpay_plan_id(target)

    try:
        # If a downgrade was scheduled earlier and the user upgrades, cancel the schedule first.
        if state.get("scheduled_plan") and schedule_change_at == "now":
            await razorpay_cancel_scheduled_changes(subscription_id=sub_id)
            set_scheduled_plan(user_id=user_id, scheduled_plan=None)

        await razorpay_update_subscription(
            subscription_id=sub_id,
            plan_id=plan_id,
            schedule_change_at=schedule_change_at,
        )
        sub = await razorpay_fetch_subscription(subscription_id=sub_id)
    except RuntimeError as e:
        msg = str(e or "").strip()
        # Razorpay limitation: subscriptions paid/created with UPI cannot be updated.
        # We surface a product-grade error so the UI can guide the user to cancel + re-subscribe.
        if "payment mode is upi" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "UPI_SUBSCRIPTION_UNCHANGEABLE",
                    "message": (
                        "Plan changes are not supported for subscriptions created with UPI. "
                        "Cancel your current subscription, then start a new subscription "
                        "on the desired plan (Card/NetBanking recommended)."
                    ),
                    "request_id": request.state.request_id,
                },
            ) from e
        raise HTTPException(
            status_code=502,
            detail={"message": msg, "request_id": request.state.request_id},
        ) from e

    if schedule_change_at == "cycle_end":
        set_scheduled_plan(user_id=user_id, scheduled_plan=target)
        scheduled = target
    else:
        set_scheduled_plan(user_id=user_id, scheduled_plan=None)
        scheduled = None

    plan = _plan_from_razorpay_plan_id(sub.get("plan_id")) or target
    upsert_subscription_state(
        user_id=user_id,
        subscription_id=str(sub.get("id") or sub_id),
        customer_id=sub.get("customer_id"),
        plan=plan,
        status=str(sub.get("status") or "active"),
        current_period_start=int(sub.get("current_start") or 0) or None,
        current_period_end=int(sub.get("current_end") or 0) or None,
        cancel_at_cycle_end=bool(int(sub.get("cancel_at_cycle_end") or 0)),
        scheduled_plan=scheduled,
    )

    return {
        "status": "ok",
        "current_plan": plan,
        "scheduled_plan": scheduled,
        "schedule_change_at": schedule_change_at,
        "entitlements": _build_entitlements_payload(user),
    }


@app.post("/billing/razorpay/subscription/cancel")
async def razorpay_subscription_cancel(
    request: Request,
    req: RazorpayCancelSubscriptionRequest,
    user=Depends(verify_user),
):
    user_id = str(user.get("sub") or "user")
    state = get_subscription_state(user_id) or {}
    sub_id = str(state.get("subscription_id") or "")
    if not sub_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No active subscription found for this account.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    requested_cycle_end = bool(req.cancel_at_cycle_end)
    tried_fallback = False
    try:
        sub = await razorpay_cancel_subscription(
            subscription_id=sub_id,
            cancel_at_cycle_end=requested_cycle_end,
        )
    except RuntimeError as e:
        msg = str(e or "").strip()
        # Idempotency: users can cancel a UPI mandate (or the subscription) outside our UI.
        # Razorpay then returns a 400 stating the subscription is already cancelled.
        # Treat that as success and sync our persisted subscription state.
        if "not cancellable" in msg.lower() and "cancelled status" in msg.lower():
            requested_cycle_end = False
            try:
                sub = await razorpay_fetch_subscription(subscription_id=sub_id)
            except Exception:
                sub = {"id": sub_id, "status": "cancelled", "cancel_at_cycle_end": 0}
        else:
        # Razorpay rejects "cancel_at_cycle_end" when the subscription never started a billing cycle
        # (e.g. status=created/authenticated). In that case, retry with immediate cancellation.
            if requested_cycle_end and "no billing cycle" in msg.lower():
                tried_fallback = True
                try:
                    sub = await razorpay_cancel_subscription(
                        subscription_id=sub_id,
                        cancel_at_cycle_end=False,
                    )
                    requested_cycle_end = False
                except RuntimeError as e2:
                    raise HTTPException(
                        status_code=502,
                        detail={"message": str(e2), "request_id": request.state.request_id},
                    ) from e2
            else:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": msg or "Razorpay error",
                        "request_id": request.state.request_id,
                    },
                ) from e

    upsert_subscription_state(
        user_id=user_id,
        subscription_id=str(sub.get("id") or sub_id),
        customer_id=sub.get("customer_id"),
        plan=str(state.get("plan") or "pro"),
        status=str(sub.get("status") or "cancelled"),
        current_period_start=int(sub.get("current_start") or 0) or None,
        current_period_end=int(sub.get("current_end") or 0) or None,
        cancel_at_cycle_end=bool(int(sub.get("cancel_at_cycle_end") or 0)),
        scheduled_plan=state.get("scheduled_plan"),
    )

    return {
        "status": "ok",
        "cancel_at_cycle_end": bool(requested_cycle_end),
        "fallback_to_immediate_cancel": bool(tried_fallback),
        "entitlements": _build_entitlements_payload(user),
    }


@app.post("/billing/razorpay/webhook")
async def razorpay_webhook(request: Request):
    body = await request.body()
    sig = (
        request.headers.get("X-Razorpay-Signature")
        or request.headers.get("x-razorpay-signature")
        or ""
    )
    if not sig or not verify_webhook_signature(body=body, signature=sig):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    digest = hashlib.sha256(body).hexdigest()
    if not record_webhook_digest(digest=digest, provider="razorpay"):
        return {"status": "duplicate"}

    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON") from e

    event = str(data.get("event") or "")
    payload = data.get("payload") or {}
    sub_entity = {}
    if isinstance(payload, dict):
        sub_entity = (payload.get("subscription") or {}).get("entity") or {}

    if isinstance(sub_entity, dict) and sub_entity.get("id"):
        sub_id = str(sub_entity.get("id"))
        user_id = get_user_for_subscription(sub_id)
        notes = sub_entity.get("notes") or {}
        if not user_id and isinstance(notes, dict):
            user_id = str(notes.get("user_id") or "") or None

        if user_id:
            plan = _plan_from_razorpay_plan_id(sub_entity.get("plan_id")) or (
                (get_subscription_state(user_id) or {}).get("plan") or "pro"
            )
            # If we previously stored a scheduled plan (cycle_end downgrade), keep it until
            # Razorpay updates the plan_id and we see subscription.updated/charged.
            scheduled = (get_subscription_state(user_id) or {}).get("scheduled_plan")
            if event in {"subscription.updated", "subscription.charged"}:
                has_sched = bool(sub_entity.get("has_scheduled_changes"))
                if not has_sched:
                    scheduled = None

            upsert_subscription_state(
                user_id=user_id,
                subscription_id=sub_id,
                customer_id=sub_entity.get("customer_id"),
                plan=plan,
                status=str(sub_entity.get("status") or "unknown"),
                current_period_start=int(sub_entity.get("current_start") or 0) or None,
                current_period_end=int(sub_entity.get("current_end") or 0) or None,
                cancel_at_cycle_end=bool(int(sub_entity.get("cancel_at_cycle_end") or 0)),
                scheduled_plan=scheduled,
            )

    return {"status": "ok"}

@app.post("/repurpose/")
async def repurpose_content(
    req: ContentRequest,
    request: Request,
    user=Depends(verify_user),
    _rl=Depends(rate_limit(RateLimitConfig(limit=30, window_seconds=60, key_prefix="repurpose"))),
):
    """
    Protected endpoint. 'verify_user' will raise a 401 if the JWT is invalid.
    """
    # Input validation
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    try:
        plan = get_effective_plan(user)
        admin = plan == "admin"
        premium = plan in {"starter", "pro", "business", "admin"}
        limits = _limits_for_plan("business" if admin else plan)
        user_id = str(user.get("sub") or "user")
        if not admin:
            usage = get_usage(user_id)
            used = int(usage.get("text_used", 0))
            if used >= int(limits["text_posts"]):
                raise _usage_error(feature="text_posts", limit=int(limits["text_posts"]), used=used)
        result = generate_social_content(
            req.text,
            x_style=req.x_style,
            content_format=req.format,
            is_premium=premium,
        )
        sections = _parse_sections(result)
        if not admin:
            record_usage(user_id, "text_used", n=1)
        return {"result": result, "sections": sections}
    except RuntimeError as e:
        msg = str(e or "")
        if "OPENAI_API_KEY" in msg:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "AI provider is not configured (missing OPENAI_API_KEY).",
                    "request_id": request.state.request_id,
                },
            ) from e
        logger.exception("Runtime error in /repurpose/ (request_id=%s)", request.state.request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal Server Error during content generation.",
                "request_id": request.state.request_id,
            },
        ) from e
    except Exception as e:
        # Provide a safe, compact upstream error so production debugging doesn't require log access.
        raw = str(e or "").strip().replace("\n", " ")
        if len(raw) > 220:
            raw = raw[:217] + "..."
        logger.exception("Error in /repurpose/ (request_id=%s)", request.state.request_id)
        upstream_msg = f"Upstream AI error: {type(e).__name__}"
        if raw:
            upstream_msg = f"{upstream_msg}: {raw}"
        raise HTTPException(
            status_code=502,
            detail={"message": upstream_msg, "request_id": request.state.request_id},
        ) from e


@app.post("/repurpose/image")
async def repurpose_from_image(
    request: Request,
    image: UploadFile = File(...),
    prompt: str = Form(""),
    x_style: str = Form("single"),
    format: str = Form("professional"),
    user=Depends(verify_user),
    _rl=Depends(
        rate_limit(RateLimitConfig(limit=12, window_seconds=60, key_prefix="repurpose_image"))
    ),
):
    """
    Accepts an image upload and generates X/LinkedIn posts plus IG/FB captions.
    Free users get a limited monthly quota; Pro users get higher limits.
    """
    plan = get_effective_plan(user)
    admin = plan == "admin"
    premium = plan in {"starter", "pro", "business", "admin"}
    limits = _limits_for_plan("business" if admin else plan)
    user_id = str(user.get("sub") or "user")
    if not admin:
        usage = get_usage(user_id)
        used = int(usage.get("vision_used", 0))
        if used >= int(limits["image_to_posts"]):
            raise _usage_error(
                feature="image_to_posts",
                limit=int(limits["image_to_posts"]),
                used=used,
            )

    if not image:
        raise HTTPException(status_code=400, detail="Image file is required")

    content_type = (image.content_type or "").strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PNG, JPEG, or WebP image.",
        )

    try:
        raw = await image.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        # 6MB guardrail to avoid huge payloads.
        if len(raw) > 6 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="Image is too large. Please upload a smaller file (max 6MB).",
            )

        result = generate_social_content_from_image(
            image_bytes=raw,
            image_mime=content_type or "image/png",
            user_prompt=prompt,
            x_style=x_style,
            content_format=format,
            is_premium=premium,
        )
        sections = _parse_sections(result)
        if not admin:
            record_usage(user_id, "vision_used", n=1)
        return {"result": result, "sections": sections}
    except HTTPException:
        raise
    except RuntimeError as e:
        msg = str(e or "")
        if "OPENAI_API_KEY" in msg:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "AI provider is not configured (missing OPENAI_API_KEY).",
                    "request_id": request.state.request_id,
                },
            ) from e
        logger.exception(
            "Runtime error in /repurpose/image (request_id=%s)",
            request.state.request_id,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Internal Server Error during image-based generation.",
                "request_id": request.state.request_id,
            },
        ) from e
    except Exception as e:
        raw_msg = str(e or "").strip().replace("\n", " ")
        if len(raw_msg) > 220:
            raw_msg = raw_msg[:217] + "..."
        logger.exception("Error in /repurpose/image (request_id=%s)", request.state.request_id)
        upstream_msg = f"Upstream AI error: {type(e).__name__}"
        if raw_msg:
            upstream_msg = f"{upstream_msg}: {raw_msg}"
        raise HTTPException(
            status_code=502,
            detail={"message": upstream_msg, "request_id": request.state.request_id},
        ) from e

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
