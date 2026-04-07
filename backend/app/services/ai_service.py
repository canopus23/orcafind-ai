import os
import base64
from typing import Optional
from openai import OpenAI

# Helper for Post Builder fallback when the 4-section output is malformed.
def generate_linkedin_post(
    text: str,
    content_format: str = "professional",
    is_premium: bool = False,
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    text_model = os.getenv("OPENAI_TEXT_MODEL", "").strip() or "gpt-4o-mini"
    client = OpenAI(api_key=api_key)

    format_normalized = (content_format or "professional").strip().lower()
    premium_only_formats = {"launch", "story"}
    if (not is_premium) and (format_normalized in premium_only_formats):
        format_normalized = "professional"

    prompt = f"""
You are a content strategist for SaaS founders and product marketers.

Style/format preference: {format_normalized}

Write ONE LinkedIn post based on the source content.

Rules:
- No headings.
- No code fences.
- Use short paragraphs with intentional line breaks.
- If you use bullets, use hyphens with one point per line.
- End with a clear CTA question.

Source content:
{text}
""".strip()

    response = client.chat.completions.create(
        model=text_model,
        messages=[
            {"role": "system", "content": "You are a concise, high-signal social content expert."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=450,
    )
    return response.choices[0].message.content


# Renamed from generate_content to generate_social_content
def generate_social_content(
    text: str,
    x_style: str = "thread",
    content_format: str = "professional",
    is_premium: bool = False,
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    # Safe low-cost default for production (override with OPENAI_TEXT_MODEL).
    text_model = os.getenv("OPENAI_TEXT_MODEL", "").strip() or "gpt-4o-mini"
    client = OpenAI(api_key=api_key)

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
  Instagram:
  Facebook:
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
        model=text_model,
        messages=[
            {"role": "system", "content": "You are a concise, high-signal social content expert."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=950
    )

    return response.choices[0].message.content


def generate_social_content_from_image(
    *,
    image_bytes: bytes,
    image_mime: str,
    user_prompt: str = "",
    x_style: str = "single",
    content_format: str = "professional",
    is_premium: bool = False,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    # Vision-capable, low-cost default. Override with OPENAI_VISION_MODEL if desired.
    model = os.getenv("OPENAI_VISION_MODEL", "").strip() or os.getenv("OPENAI_TEXT_MODEL", "").strip() or "gpt-4o-mini"
    client = OpenAI(api_key=api_key)

    x_style_normalized = (x_style or "single").strip().lower()
    if x_style_normalized not in {"single", "thread"}:
        x_style_normalized = "single"

    format_normalized = (content_format or "professional").strip().lower()
    premium_only_formats = {"launch", "story"}
    if (not is_premium) and (format_normalized in premium_only_formats):
        format_normalized = "professional"

    if x_style_normalized == "single":
        # Image-to-post should always return multiple options as requested.
        variant_count = 4 if is_premium else 3
        variants = "\n".join([f"  Variant {i}: <text>" for i in range(1, variant_count + 1)])
        x_instructions = (
            f"- Write {variant_count} DISTINCT X/Twitter post variations.\n"
            "- Each variation must be <= 280 characters.\n"
            "- Each variation must use a different hook angle and structure.\n"
            "- Keep it grounded in what the image shows. Do NOT hallucinate details.\n"
            "- Present exactly as:\n"
            f"{variants}\n"
        )
    else:
        thread_min = 4
        thread_max = 10 if is_premium else 7
        x_instructions = (
            "- Write an X/Twitter THREAD.\n"
            f"- {thread_min} to {thread_max} tweets total.\n"
            "- Use numbering like 1/ , 2/ , ...\n"
            "- Tweet 1 must be a strong hook.\n"
            "- Keep it grounded in what the image shows. Do NOT hallucinate details.\n"
            "- Separate tweets with a blank line for readability.\n"
        )

    extra = (user_prompt or "").strip()
    extra_block = f"\nUser request:\n{extra}\n" if extra else ""

    prompt = f"""
You are a content strategist for SaaS founders and product marketers.

You will be given an IMAGE. First, infer what the image is about (objects, scene, text if present, mood, and key takeaway).
Then write platform-ready social copy based on the image.

Style/format preference: {format_normalized}
{extra_block}
Rules:
- Output MUST be exactly four sections with these exact headers (one time each):
  X:
  LinkedIn:
  Instagram:
  Facebook:
- Do NOT add any other headings.
- Do NOT use code fences.
- Do NOT mention that you are an AI or that you analyzed an image.
- If the image lacks context, write broadly without making up specifics.

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
""".strip()

    safe_mime = (image_mime or "").strip().lower() or "image/png"
    if not safe_mime.startswith("image/"):
        safe_mime = "image/png"
    data_url = f"data:{safe_mime};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

    # Use the Responses API for multimodal input.
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        max_output_tokens=950,
    )

    return response.output_text
