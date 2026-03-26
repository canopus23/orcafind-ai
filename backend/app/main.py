import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from app.dependencies.auth import verify_user

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found")

client = OpenAI(api_key=api_key)

usage_store = {}
FREE_LIMIT = 6


class ContentRequest(BaseModel):
    text: str


def generate_content(text: str):
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
{text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a viral content expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400
    )

    return response.choices[0].message.content


def get_user_ip(request: Request):
    if request.client:
        return request.client.host
    return "anonymous"


def check_usage_limit(user_key: str):
    count = usage_store.get(user_key, 0)
    if count >= FREE_LIMIT:
        raise HTTPException(status_code=403, detail="Free limit reached")
    usage_store[user_key] = count + 1


@app.post("/repurpose/")
def repurpose_content(req: ContentRequest, request: Request):
    user = verify_user(request)
    user_id = user.get("sub")

    count = usage_store.get(user_id, 0)
    if count >= FREE_LIMIT:
        raise HTTPException(status_code=403, detail="Free limit reached")

    usage_store[user_id] = count + 1

    try:
        result = generate_content(req.text)
        return {"result": result}
    except Exception:
        raise HTTPException(status_code=500, detail="AI processing failed")

@app.get("/")
def root():
    return {"status": "running"}