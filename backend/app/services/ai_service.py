import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Renamed from generate_content to generate_social_content
def generate_social_content(
    text: str,
    x_style: str = "thread",
    content_format: str = "professional",
    is_premium: bool = False,
):
    x_style_normalized = (x_style or "thread").strip().lower()
    if x_style_normalized not in {"single", "thread"}:
        x_style_normalized = "thread"

    format_normalized = (content_format or "professional").strip().lower()
    premium_only_formats = {"launch", "story"}
    if (not is_premium) and (format_normalized in premium_only_formats):
        format_normalized = "professional"

    if x_style_normalized == "single":
        variant_count = 4 if is_premium else 2
        variants = "\n".join([f"  Variant {i}: <text>" for i in range(1, variant_count + 1)])
        x_instructions = (
            f"- Write {variant_count} DISTINCT X/Twitter post variations.\n"
            "- Each variation must be <= 280 characters.\n"
            "- Each variation must use a different hook angle and structure.\n"
            "- No filler. Clear value. Optional: 0-2 hashtags max.\n"
            "- Present exactly as:\n"
            f"{variants}\n"
            "- Keep each variant as formatted plain text (line breaks allowed).\n"
        )
    else:
        thread_min = 4
        thread_max = 10 if is_premium else 7
        x_instructions = (
            "- Write an X/Twitter THREAD.\n"
            f"- {thread_min} to {thread_max} tweets total.\n"
            "- Use numbering like 1/ , 2/ , ...\n"
            "- Tweet 1 must be a strong hook.\n"
            "- Separate tweets with a blank line for readability.\n"
        )

    prompt = f"""
You are a content strategist for SaaS founders and product marketers.

Style/format preference: {format_normalized}

Generate FOUR outputs from the same source content.

Rules:
- Output MUST be exactly four sections with these exact headers (one time each):
  X:
  LinkedIn:
- Instagram:
- Facebook:
- Do NOT add any other headings.
- Do NOT use code fences.
- Keep the writing aligned to the requested style/format preference.

X requirements:
{x_instructions}

LinkedIn requirements:
- One LinkedIn post with clear formatting.
- Use short paragraphs with intentional line breaks.
- If you use bullets, use hyphens with one point per line.
- Include a clear CTA question at the end.

Instagram requirements:
- One Instagram caption aligned to the same idea.
- Hook in the first line, then short lines.
- Include 5-12 relevant hashtags at the end.
- Optional: 0-3 emojis total (keep it professional, not spammy).
- End with a light CTA (save/share/comment).

Facebook requirements:
- One Facebook caption with a more conversational tone than LinkedIn.
- 1-2 short paragraphs plus one optional short bullet list (hyphens).
- No more than 0-3 hashtags.
- End with a question to drive comments.

Source content:
{text}
""".strip()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a concise, high-signal social content expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=950
    )

    return response.choices[0].message.content
