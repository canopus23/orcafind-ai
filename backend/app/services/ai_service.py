import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Renamed from generate_content to generate_social_content
def generate_social_content(text: str):
    prompt = f"""
    Convert this into:
    1. Twitter thread (max 6 tweets, strong hook)
    2. LinkedIn post (storytelling + clean formatting)

    Content:
    {text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a viral content expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )

    return response.choices[0].message.content