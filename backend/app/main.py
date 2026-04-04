import os
import re
import logging
from typing import Optional, Set
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Ensure these imports match the actual file paths and function names
from app.dependencies.auth import verify_user
from app.dependencies.rate_limit import RateLimitConfig, rate_limit
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.billing import RazorpayCreateOrderRequest, RazorpayVerifyRequest
from app.schemas.request import ContentRequest
from app.schemas.images import ImageGenerateRequest
from app.schemas.complete_post import CompletePostRequest
from app.services.ai_service import generate_social_content
from app.services.image_service import generate_openai_images, generate_placeholder_images
from app.services.razorpay_service import create_order as razorpay_create_order, get_razorpay_key_id, verify_signature
from app.services.subscriptions import (
    grant_pro,
    is_pro,
    link_order_to_user,
    get_user_for_order,
    get_image_usage,
    record_image_usage,
    init_schema,
    is_usage_db_configured,
)

logger = logging.getLogger("orcafind.api")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        environment=os.getenv("ENV", "development"),
        release=os.getenv("RELEASE", None),
    )

app = FastAPI(title="OrcaFind AI API")
app.add_middleware(RequestContextMiddleware)


@app.on_event("startup")
def _startup():
    try:
        init_schema()
    except Exception:
        # Never crash the API on startup due to transient DB connectivity.
        logger.exception("Startup: init_schema failed (DB unreachable).")

def _parse_csv_set(value: Optional[str], *, lowercase: bool = True) -> Set[str]:
    if not value:
        return set()
    items = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        items.append(item.lower() if lowercase else item)
    return set(items)


def _get_user_email(payload: dict) -> Optional[str]:
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
    if is_pro(user_id):
        return True
    email = _get_user_email(payload)
    return bool(email and email.strip().lower() in allowlist)


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
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}
origins = set(_parse_csv_set(os.getenv("CORS_ALLOW_ORIGINS"), lowercase=False)) | default_origins

# CORSMiddleware must be added first to handle preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_origin_regex=os.getenv("CORS_ALLOW_ORIGIN_REGEX"),
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

@app.get("/entitlements")
async def entitlements(user=Depends(verify_user)):
    admin = is_admin_user(user)
    premium = admin or is_premium_user(user)
    user_id = str(user.get("sub") or "user")

    free_image_limit = int(os.getenv("FREE_IMAGE_GENERATIONS_TOTAL", "20"))
    env = os.getenv("ENV", "development").strip().lower()
    try:
        used_images = get_image_usage(user_id) if not premium else 0
        remaining_images = max(0, free_image_limit - used_images) if not premium else 10_000
    except Exception:
        # Fail closed in production if usage DB is misconfigured/unreachable.
        if (not premium) and env in {"prod", "production"}:
            used_images = free_image_limit
            remaining_images = 0
        else:
            used_images = 0
            remaining_images = free_image_limit if not premium else 10_000
    return {
        "plan": "admin" if admin else ("pro" if premium else "free"),
        "is_admin": admin,
        "is_premium": premium,
        "limits": {
            "x_single_variants": 4 if premium else 2,
            "x_thread_tweets_min": 4,
            "x_thread_tweets_max": 10 if premium else 7,
            "image_generations_total": 10_000 if premium else free_image_limit,
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
    admin = is_admin_user(user)
    premium = admin or is_premium_user(user)
    user_id = str(user.get("sub") or "user")

    if not premium:
        env = os.getenv("ENV", "development").strip().lower()
        if env in {"prod", "production"} and not is_usage_db_configured():
            raise HTTPException(status_code=503, detail="Usage database is not configured. Set DATABASE_URL.")

        free_image_limit = int(os.getenv("FREE_IMAGE_GENERATIONS_TOTAL", "20"))
        try:
            used_images = get_image_usage(user_id)
        except Exception:
            raise HTTPException(status_code=503, detail="Usage database is unreachable. Please try again shortly.")
        if used_images + int(req.count) > free_image_limit:
            raise HTTPException(status_code=402, detail="Upgrade to Pro to generate more images")

    # Prefer OpenAI if configured; fall back to placeholder images for local/dev.
    images = None
    if os.getenv("OPENAI_API_KEY"):
        quality = "high" if premium else "low"
        images = generate_openai_images(
            brief=req.brief,
            style=req.style,
            aspect=req.aspect,
            count=req.count,
            quality=quality,
            user_id=user_id,
        )
    else:
        images = generate_placeholder_images(
            brief=req.brief,
            style=req.style,
            aspect=req.aspect,
            count=req.count,
        )
    if not premium:
        # Count-based accounting to match UI "count" selector.
        record_image_usage(user_id, n=req.count)
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
    pattern = r"(?im)^(X|LinkedIn|Instagram|Facebook):\\s*$"
    matches = list(re.finditer(pattern, text))
    if not matches:
        # Fallback: try to split the older 2-section format.
        parts = re.split(r"(?i)linkedin:\\s*", text, maxsplit=1)
        out["x"] = re.sub(r"(?is)^\\s*x:\\s*", "", parts[0] if parts else "").strip()
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
    admin = is_admin_user(user)
    premium = admin or is_premium_user(user)
    if not premium:
        raise HTTPException(status_code=402, detail="Upgrade to Pro to use Post Builder")

    user_id = str(user.get("sub") or "user")

    result = generate_social_content(
        req.text,
        x_style=req.x_style,
        content_format=req.format,
        is_premium=True,
    )
    sections = _parse_sections(result)
    x_text = sections.get("x", "").strip()
    linkedin_text = sections.get("linkedin", "").strip()
    instagram_text = sections.get("instagram", "").strip()
    facebook_text = sections.get("facebook", "").strip()
    if not linkedin_text:
        raise HTTPException(status_code=502, detail="LinkedIn output missing from generation result")

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
            quality="high",
            user_id=user_id,
        )
    else:
        images = generate_placeholder_images(
            brief=image_brief,
            style=(req.image_style or "").strip() or "saas_minimal",
            aspect=req.image_aspect,
            count=1,
        )

    return {
        "x": x_text,
        "linkedin": linkedin_text,
        "instagram": instagram_text,
        "facebook": facebook_text,
        "images": images,
    }

@app.post("/billing/razorpay/order")
async def razorpay_create(req: RazorpayCreateOrderRequest, user=Depends(verify_user)):
    # Only Pro is currently billable.
    plan = (req.plan or "pro").strip().lower()
    if plan != "pro":
        raise HTTPException(status_code=400, detail="Unsupported plan")

    billing = (req.billing or "monthly").strip().lower()
    if billing not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Unsupported billing period")

    # Amounts are in paise (INR).
    amount_paise = 149900 if billing == "yearly" else 149900 // 10  # 1499 INR monthly, 14990 INR yearly
    currency = "INR"

    user_id = str(user.get("sub") or "user")
    email = _get_user_email(user) or req.email or ""

    order = await razorpay_create_order(
        amount_paise=amount_paise,
        currency=currency,
        receipt=f"orcafind_{plan}_{billing}_{user_id}",
        notes={
            "user_id": user_id,
            "plan": plan,
            "billing": billing,
            "email": email,
        },
    )

    if order.get("id"):
        link_order_to_user(order.get("id"), user_id)

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
async def razorpay_verify(req: RazorpayVerifyRequest, user=Depends(verify_user)):
    user_id = str(user.get("sub") or "user")

    order_user = get_user_for_order(req.razorpay_order_id)
    if order_user and order_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not verify_signature(
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
        signature=req.razorpay_signature,
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    grant_pro(user_id=user_id, order_id=req.razorpay_order_id, payment_id=req.razorpay_payment_id)
    return {"status": "ok", "plan": "pro"}

@app.post("/repurpose/")
async def repurpose_content(
    req: ContentRequest,
    user=Depends(verify_user),
    _rl=Depends(rate_limit(RateLimitConfig(limit=30, window_seconds=60, key_prefix="repurpose"))),
):
    """
    Protected endpoint. 'verify_user' will raise a 401 if the JWT is invalid.
    """
    try:
        # Input validation
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")
            
        # Process content via AI service
        premium = is_admin_user(user) or is_premium_user(user)
        result = generate_social_content(req.text, x_style=req.x_style, content_format=req.format, is_premium=premium)
        sections = _parse_sections(result)
        return {"result": result, "sections": sections}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in /repurpose/")
        raise HTTPException(status_code=500, detail="Internal Server Error during content generation")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
