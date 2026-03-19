import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# ✅ CORS (MUST be before routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all (for dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ OpenAI setup
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=api_key)

# ✅ Usage tracking (simple in-memory)
usage_store = {}
FREE_LIMIT = 6


# ✅ Request model
class ContentRequest(BaseModel):
    text: str


# 🚀 Main route
@app.post("/repurpose/")
def repurpose_content(req: ContentRequest, request: Request):
    # ✅ Safe IP detection
    user_ip = request.client.host if request.client else "anonymous"

    # 🔒 Usage limit check
    count = usage_store.get(user_ip, 0)

    if count >= FREE_LIMIT:
        raise HTTPException(
            status_code=403,
            detail="🚫 Free limit reached. Upgrade to continue."
        )

    # Increase usage count
    usage_store[user_ip] = count + 1

    # 🧠 AI Prompt
    prompt = f"""
You are an expert content creator.

Convert this into:

1. Twitter thread:
- Strong hook
- Max 6 tweets

2. LinkedIn post:
- Storytelling
- Clean formatting
- End with a question

Content:
{req.text}
"""

    try:
        # 🤖 OpenAI call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a viral content expert."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )

        output = response.choices[0].message.content

        return {"result": output}

    except Exception as e:
        print("❌ ERROR:", e)
        raise HTTPException(
            status_code=500,
            detail="❌ AI processing failed. Check API key or quota."
        )


# 🧪 Health check (optional but useful)
@app.get("/")
def root():
    return {"status": "OrcaFind AI running 🚀"}