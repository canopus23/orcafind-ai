import logging
import os
import re

import sentry_sdk
import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.dependencies.auth import verify_user
from app.dependencies.rate_limit import RateLimitConfig, rate_limit
from app.middleware.request_context import RequestContextMiddleware
from app.schemas.billing import RazorpayCreateOrderRequest, RazorpayVerifyRequest
from app.schemas.complete_post import CompletePostRequest
from app.schemas.images import ImageGenerateRequest
from app.schemas.request import ContentRequest
from app.services.ai_service import (
    generate_linkedin_post,
    generate_social_content,
    generate_social_content_from_image,
)
from app.services.image_service import generate_openai_images, generate_placeholder_images
from app.services.razorpay_service import (
    create_order as razorpay_create_order,
)
from app.services.razorpay_service import (
    get_razorpay_key_id,
    verify_signature,
)
from app.services.subscriptions import (
    get_plan,
    get_plan_for_order,
    get_usage,
    get_user_for_order,
    grant_plan,
    has_paid_plan,
    init_schema,
    is_usage_db_configured,
    link_order_to_user,
    record_image_usage,
    record_usage,
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

@app.get("/entitlements")
async def entitlements(user=Depends(verify_user)):
    plan = get_effective_plan(user)
    admin = plan == "admin"
    premium = plan in {"starter", "pro", "business", "admin"}
    user_id = str(user.get("sub") or "user")

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
    except RuntimeError as e:
        # Most commonly: missing RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET.
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Billing is not configured on the server.",
                "request_id": request.state.request_id,
            },
        ) from e
    except Exception as e:
        # Fail with a safe upstream error. CORS + request_id header come from middleware.
        raise HTTPException(
            status_code=502,
            detail={"message": f"Razorpay error: {type(e).__name__}"},
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

    plan = get_plan_for_order(req.razorpay_order_id) or "pro"
    grant_plan(
        user_id=user_id,
        plan=plan,
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
    )
    return {"status": "ok", "plan": plan}

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
