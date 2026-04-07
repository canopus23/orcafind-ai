import os
import re
import logging
from typing import Optional, Set
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from app.services.ai_service import generate_social_content, generate_social_content_from_image
from app.services.image_service import generate_openai_images, generate_placeholder_images
from app.services.razorpay_service import create_order as razorpay_create_order, get_razorpay_key_id, verify_signature
from app.services.subscriptions import (
    grant_pro,
    is_pro,
    link_order_to_user,
    get_user_for_order,
    get_image_usage,
    record_image_usage,
    get_usage,
    record_usage,
    init_schema,
    is_usage_db_configured,
)

logger = logging.getLogger("orcafind.api")

FREE_LIMITS = {
    "text_posts": 60,          # /repurpose/ runs per month
    "image_to_posts": 5,       # /repurpose/image runs per month
    "post_builder": 2,         # /posts/complete runs per month
    "image_generations": 8,    # total images per month (includes Post Builder images)
    "x_single_variants": 2,
    "x_thread_tweets_min": 4,
    "x_thread_tweets_max": 7,
}

PRO_LIMITS = {
    "text_posts": 2000,
    "image_to_posts": 200,
    "post_builder": 100,
    "image_generations": 200,
    "x_single_variants": 4,
    "x_thread_tweets_min": 4,
    "x_thread_tweets_max": 10,
}


def _limits_for(premium: bool) -> dict:
    return PRO_LIMITS if premium else FREE_LIMITS


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
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        environment=os.getenv("ENV", "development"),
        release=os.getenv("RELEASE", None),
    )

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

    limits = _limits_for(premium)
    env = os.getenv("ENV", "development").strip().lower()
    try:
        usage = get_usage(user_id) if not premium else {"text_used": 0, "vision_used": 0, "builder_used": 0, "image_used": 0}
        used_text = int(usage.get("text_used", 0)) if not premium else 0
        used_vision = int(usage.get("vision_used", 0)) if not premium else 0
        used_builder = int(usage.get("builder_used", 0)) if not premium else 0
        used_images = int(usage.get("image_used", 0)) if not premium else 0

        remaining_text = _remaining(int(limits["text_posts"]), used_text) if not premium else 10_000
        remaining_vision = _remaining(int(limits["image_to_posts"]), used_vision) if not premium else 10_000
        remaining_builder = _remaining(int(limits["post_builder"]), used_builder) if not premium else 10_000
        remaining_images = _remaining(int(limits["image_generations"]), used_images) if not premium else 10_000
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
            remaining_text = int(limits["text_posts"]) if not premium else 10_000
            remaining_vision = int(limits["image_to_posts"]) if not premium else 10_000
            remaining_builder = int(limits["post_builder"]) if not premium else 10_000
            remaining_images = int(limits["image_generations"]) if not premium else 10_000
    return {
        "plan": "admin" if admin else ("pro" if premium else "free"),
        "is_admin": admin,
        "is_premium": premium,
        "limits": {
            "x_single_variants": int(limits["x_single_variants"]),
            "x_thread_tweets_min": int(limits["x_thread_tweets_min"]),
            "x_thread_tweets_max": int(limits["x_thread_tweets_max"]),
            "text_posts_total": int(limits["text_posts"]) if not premium else 10_000,
            "text_posts_used": int(used_text),
            "text_posts_remaining": int(remaining_text),
            "image_to_posts_total": int(limits["image_to_posts"]) if not premium else 10_000,
            "image_to_posts_used": int(used_vision),
            "image_to_posts_remaining": int(remaining_vision),
            "post_builder_total": int(limits["post_builder"]) if not premium else 10_000,
            "post_builder_used": int(used_builder),
            "post_builder_remaining": int(remaining_builder),
            "image_generations_total": int(limits["image_generations"]) if not premium else 10_000,
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

    limits = _limits_for(premium)
    if not premium:
        if not is_usage_db_configured() and os.getenv("ENV", "development").strip().lower() in {"prod", "production"}:
            raise HTTPException(status_code=503, detail="Usage tracking is not configured")
        usage = get_usage(user_id)
        used = int(usage.get("image_used", 0))
        inc = 1
        if used + inc > int(limits["image_generations"]):
            raise _usage_error(feature="image_generations", limit=int(limits["image_generations"]), used=used)

    # Prefer OpenAI if configured; fall back to placeholder images for local/dev.
    images = None
    if os.getenv("OPENAI_API_KEY"):
        quality = "medium" if premium else "low"
        count = int(req.count)
        # Free plan: keep it to 1 image per request to control costs.
        if not premium:
            count = 1
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
            count=1 if not premium else req.count,
        )

    # Usage accounting (monthly).
    if not premium:
        record_image_usage(user_id, n=1)
    else:
        # Still record for Pro so the UI can show usage/remaining if desired later.
        record_image_usage(user_id, n=int(req.count or 1))
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
    user_id = str(user.get("sub") or "user")
    limits = _limits_for(premium)
    if not premium:
        usage = get_usage(user_id)
        used_builder = int(usage.get("builder_used", 0))
        used_images = int(usage.get("image_used", 0))
        if used_builder >= int(limits["post_builder"]):
            raise _usage_error(feature="post_builder", limit=int(limits["post_builder"]), used=used_builder)
        if used_images + 1 > int(limits["image_generations"]):
            raise _usage_error(feature="image_generations", limit=int(limits["image_generations"]), used=used_images)

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

    if not premium:
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
async def razorpay_create(req: RazorpayCreateOrderRequest, user=Depends(verify_user)):
    # Only Pro is currently billable.
    plan = (req.plan or "pro").strip().lower()
    if plan != "pro":
        raise HTTPException(status_code=400, detail="Unsupported plan")

    billing = (req.billing or "monthly").strip().lower()
    if billing not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Unsupported billing period")

    # Amounts are in the currency's minor unit (cents for USD).
    amount_minor = 29000 if billing == "yearly" else 2900  # $29/mo, $290/yr
    currency = "USD"

    user_id = str(user.get("sub") or "user")
    email = _get_user_email(user) or req.email or ""

    order = await razorpay_create_order(
        amount_paise=amount_minor,
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
        premium = is_admin_user(user) or is_premium_user(user)
        limits = _limits_for(premium)
        user_id = str(user.get("sub") or "user")
        if not premium:
            usage = get_usage(user_id)
            used = int(usage.get("text_used", 0))
            if used >= int(limits["text_posts"]):
                raise _usage_error(feature="text_posts", limit=int(limits["text_posts"]), used=used)
        result = generate_social_content(req.text, x_style=req.x_style, content_format=req.format, is_premium=premium)
        sections = _parse_sections(result)
        if not premium:
            record_usage(user_id, "text_used", n=1)
        return {"result": result, "sections": sections}
    except RuntimeError as e:
        msg = str(e or "")
        if "OPENAI_API_KEY" in msg:
            raise HTTPException(
                status_code=503,
                detail={"message": "AI provider is not configured (missing OPENAI_API_KEY).", "request_id": request.state.request_id},
            )
        logger.exception("Runtime error in /repurpose/ (request_id=%s)", request.state.request_id)
        raise HTTPException(
            status_code=500,
            detail={"message": "Internal Server Error during content generation.", "request_id": request.state.request_id},
        )
    except Exception as e:
        # Provide a safe, compact upstream error so production debugging doesn't require log access.
        raw = str(e or "").strip().replace("\n", " ")
        if len(raw) > 220:
            raw = raw[:217] + "..."
        logger.exception("Error in /repurpose/ (request_id=%s)", request.state.request_id)
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Upstream AI error: {type(e).__name__}: {raw}" if raw else f"Upstream AI error: {type(e).__name__}",
                "request_id": request.state.request_id,
            },
        )


@app.post("/repurpose/image")
async def repurpose_from_image(
    request: Request,
    image: UploadFile = File(...),
    prompt: str = Form(""),
    x_style: str = Form("single"),
    format: str = Form("professional"),
    user=Depends(verify_user),
    _rl=Depends(rate_limit(RateLimitConfig(limit=12, window_seconds=60, key_prefix="repurpose_image"))),
):
    """
    Accepts an image upload and generates X/LinkedIn posts plus IG/FB captions.
    Free users get a limited monthly quota; Pro users get higher limits.
    """
    premium = is_admin_user(user) or is_premium_user(user)
    limits = _limits_for(premium)
    user_id = str(user.get("sub") or "user")
    if not premium:
        usage = get_usage(user_id)
        used = int(usage.get("vision_used", 0))
        if used >= int(limits["image_to_posts"]):
            raise _usage_error(feature="image_to_posts", limit=int(limits["image_to_posts"]), used=used)

    if not image:
        raise HTTPException(status_code=400, detail="Image file is required")

    content_type = (image.content_type or "").strip().lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload a PNG, JPEG, or WebP image.")

    try:
        raw = await image.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")
        # 6MB guardrail to avoid huge payloads.
        if len(raw) > 6 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image is too large. Please upload a smaller file (max 6MB).")

        result = generate_social_content_from_image(
            image_bytes=raw,
            image_mime=content_type or "image/png",
            user_prompt=prompt,
            x_style=x_style,
            content_format=format,
            is_premium=premium,
        )
        sections = _parse_sections(result)
        if not premium:
            record_usage(user_id, "vision_used", n=1)
        return {"result": result, "sections": sections}
    except HTTPException:
        raise
    except RuntimeError as e:
        msg = str(e or "")
        if "OPENAI_API_KEY" in msg:
            raise HTTPException(
                status_code=503,
                detail={"message": "AI provider is not configured (missing OPENAI_API_KEY).", "request_id": request.state.request_id},
            )
        logger.exception("Runtime error in /repurpose/image (request_id=%s)", request.state.request_id)
        raise HTTPException(
            status_code=500,
            detail={"message": "Internal Server Error during image-based generation.", "request_id": request.state.request_id},
        )
    except Exception as e:
        raw_msg = str(e or "").strip().replace("\n", " ")
        if len(raw_msg) > 220:
            raw_msg = raw_msg[:217] + "..."
        logger.exception("Error in /repurpose/image (request_id=%s)", request.state.request_id)
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Upstream AI error: {type(e).__name__}: {raw_msg}" if raw_msg else f"Upstream AI error: {type(e).__name__}",
                "request_id": request.state.request_id,
            },
        )

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
