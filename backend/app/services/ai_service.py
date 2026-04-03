import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Renamed from generate_content to generate_social_content
def generate_social_content(text: str, x_style: str = "thread", content_format: str = "professional"):
    x_style_normalized = (x_style or "thread").strip().lower()
    if x_style_normalized not in {"single", "thread"}:
        x_style_normalized = "thread"

    format_normalized = (content_format or "professional").strip().lower()

    if x_style_normalized == "single":
        x_instructions = (
            "- Write ONE X/Twitter post.\n"
            "- Max 280 characters.\n"
            "- Strong hook, clear value, no filler.\n"
        )
    else:
        x_instructions = (
            "- Write an X/Twitter THREAD.\n"
            "- 4 to 7 tweets total.\n"
            "- Use numbering like 1/ , 2/ , ...\n"
            "- Tweet 1 must be a strong hook.\n"
        )

    prompt = f"""
You are a content strategist for SaaS founders and product marketers.

Style/format preference: {format_normalized}

Generate TWO outputs from the same source content.

Rules:
- Output MUST be exactly two sections with these exact headers (one time each):
  X:
  LinkedIn:
- Do NOT add any other headings.
- Keep the writing aligned to the requested style/format preference.

X requirements:
{x_instructions}

LinkedIn requirements:
- One LinkedIn post with clear formatting.
- Use short paragraphs and optional bullets where helpful.
- End with a practical CTA question.

Source content:
{text}
""".strip()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a concise, high-signal social content expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=650
    )

    return response.choices[0].message.content
