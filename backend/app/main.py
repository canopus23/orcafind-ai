import os
from typing import Optional, Set
import asyncio
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Ensure these imports match the actual file paths and function names
from app.dependencies.auth import verify_user
from app.schemas.billing import RazorpayCreateOrderRequest, RazorpayVerifyRequest
from app.schemas.request import ContentRequest
from app.schemas.video import VideoShortsRequest
from app.services.ai_service import generate_social_content
from app.services.razorpay_service import create_order as razorpay_create_order, get_razorpay_key_id, verify_signature
from app.services.subscriptions import grant_pro, is_pro, link_order_to_user, get_user_for_order
from app.services.video_jobs import create_job, get_job as get_video_job, run_job

app = FastAPI(title="OrcaFind AI API")

def _parse_allowlist(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {email.strip().lower() for email in value.split(",") if email.strip()}


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
    allowlist = _parse_allowlist(os.getenv("PREMIUM_EMAIL_ALLOWLIST"))
    user_id = str(payload.get("sub") or "user")
    if is_pro(user_id):
        return True
    email = _get_user_email(payload)
    return bool(email and email.strip().lower() in allowlist)

# Define allowed origins explicitly for CORS with credentials.
# Browsers block wildcard "*" when an Authorization header is present.
origins = [
    "https://orcafind.com",
    "https://www.orcafind.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# CORSMiddleware must be added first to handle preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Required to allow Authorization headers
    allow_methods=["*"],    # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],    # Allows Content-Type, Authorization, etc.
)

@app.get("/")
async def root():
    return {"status": "online", "message": "OrcaFind API is operational"}

@app.get("/entitlements")
async def entitlements(user=Depends(verify_user)):
    premium = is_premium_user(user)
    return {
        "plan": "pro" if premium else "free",
        "is_premium": premium,
        "limits": {
            "x_single_variants": 4 if premium else 2,
            "x_thread_tweets_min": 4,
            "x_thread_tweets_max": 10 if premium else 7,
        },
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
async def repurpose_content(req: ContentRequest, user=Depends(verify_user)):
    """
    Protected endpoint. 'verify_user' will raise a 401 if the JWT is invalid.
    """
    try:
        # Input validation
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")
            
        # Process content via AI service
        premium = is_premium_user(user)
        result = generate_social_content(req.text, x_style=req.x_style, content_format=req.format, is_premium=premium)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        # Log the error to the server console for debugging
        print(f"Error in /repurpose/: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error during content generation")

@app.post("/video/shorts")
async def create_video_shorts(req: VideoShortsRequest, user=Depends(verify_user)):
    if not is_premium_user(user):
        raise HTTPException(status_code=403, detail="Premium subscription required")

    user_id = str(user.get("sub") or "user")
    job = await create_job(
        user_id=user_id,
        youtube_url=str(req.youtube_url),
        duration_seconds=req.duration_seconds,
        style=req.style,
        platform=req.platform,
        captions=req.captions,
    )

    asyncio.create_task(run_job(job.id))
    return job.to_dict()


@app.get("/video/shorts/{job_id}")
async def get_video_shorts(job_id: str, user=Depends(verify_user)):
    job = await get_video_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    user_id = str(user.get("sub") or "user")
    if job.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return job.to_dict()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
