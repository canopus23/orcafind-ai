import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ✅ CORS (important)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ OpenAI setup
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Usage tracking (simple)
usage_store = {}
FREE_LIMIT = 3


# ✅ Request model
class ContentRequest(BaseModel):
    text: str


@app.post("/repurpose")
def repurpose_content(req: ContentRequest, request: Request):
    user_ip = request.client.host

    # 🔒 Usage limit
    count = usage_store.get(user_ip, 0)

    if count >= FREE_LIMIT:
        raise HTTPException(status_code=403, detail="Free limit reached. Upgrade to continue.")

    usage_store[user_ip] = count + 1

    # 🧠 AI prompt
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