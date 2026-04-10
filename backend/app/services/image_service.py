import base64
import datetime as _dt
import os
import uuid
from typing import Any

from openai import OpenAI

from app.services.r2_storage import (
    build_object_key,
    get_bucket_name,
    get_download_url,
    get_key_prefix,
    upload_bytes,
)


def _aspect_dimensions(aspect: str) -> tuple[int, int]:
    aspect = (aspect or "square").strip().lower()
    if aspect == "portrait":
        return 1024, 1280
    if aspect == "landscape":
        return 1280, 720
    return 1024, 1024


def _aspect_to_openai_size(aspect: str) -> str:
    aspect = (aspect or "square").strip().lower()
    if aspect == "portrait":
        return "1024x1536"
    if aspect == "landscape":
        return "1536x1024"
    return "1024x1024"


def _style_prompt(style: str) -> str:
    style = (style or "saas_minimal").strip().lower()
    if style == "realistic":
        return (
            "Photorealistic, natural lighting, shallow depth of field, "
            "premium product photography vibe, clean composition, no text."
        )
    if style == "abstract_gradient":
        return "Abstract gradient background, soft lighting, modern SaaS brand feel, no text."
    if style == "product_mock":
        return "Modern SaaS product mock scene, clean UI shapes, subtle depth, no readable UI text."
    if style == "illustration":
        return "Clean vector illustration, modern SaaS aesthetic, simple shapes, no text."
    # default: saas_minimal
    return (
        "Minimal SaaS cover art, geometric shapes, light background, "
        "brand accent #1367ff, no text."
    )


def generate_openai_images(
    *,
    brief: str,
    style: str,
    aspect: str,
    count: int,
    quality: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """
    Generate real images via OpenAI Image API.
    Requires OPENAI_API_KEY set in environment.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing required env var: OPENAI_API_KEY")

    model = os.getenv("OPENAI_IMAGE_MODEL", "").strip() or "gpt-image-1.5"
    size = _aspect_to_openai_size(aspect)
    quality = (quality or "medium").strip().lower()
    if quality not in {"low", "medium", "high", "auto"}:
        quality = "medium"

    prompt = (
        "Create a post-ready social image.\n"
        f"Brief: {brief.strip()}\n"
        f"Style: {_style_prompt(style)}\n"
        "Constraints: no logos of other brands, no watermarks, "
        "no text unless explicitly requested.\n"
    )

    client = OpenAI(api_key=api_key)
    result = client.images.generate(
        model=model,
        prompt=prompt,
        n=int(count),
        size=size,
        quality=quality,
        output_format="png",
        user=str(user_id)[:128],
    )

    images: list[dict[str, Any]] = []
    for idx, item in enumerate(result.data or []):
        b64 = getattr(item, "b64_json", None) or (
            item.get("b64_json") if isinstance(item, dict) else None
        )
        if not b64:
            continue
        # Prefer storing to R2 if configured. Fall back to data URLs.
        url: str = ""
        try:
            # If R2 isn't configured this will raise, and we use the data URL fallback.
            png_bytes = base64.b64decode(b64)
            bucket = get_bucket_name()
            prefix = get_key_prefix()
            object_key = build_object_key(
                prefix, "images", user_id, uuid.uuid4().hex, extension="png"
            )
            upload_bytes(bucket=bucket, key=object_key, content=png_bytes, content_type="image/png")
            url = get_download_url(bucket=bucket, key=object_key)
        except Exception:
            url = ""

        payload: dict[str, Any] = {"label": f"Option {idx + 1}"}
        if url:
            payload["url"] = url
        else:
            payload["data_url"] = f"data:image/png;base64,{b64}"
        images.append(payload)
    if not images:
        raise RuntimeError("OpenAI image generation returned no images")
    return images


def _escape_xml(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def generate_placeholder_images(
    *, brief: str, style: str, aspect: str, count: int
) -> list[dict[str, Any]]:
    """
    Provider-agnostic fallback so the UI works without external image APIs.
    Returns PNG-like data URLs (actually SVG embedded as data URL for crisp rendering).
    """
    width, height = _aspect_dimensions(aspect)
    seed = _dt.datetime.utcnow().strftime("%Y%m%d%H%M")

    brief_line = brief.strip().replace("\n", " ")
    if len(brief_line) > 80:
        brief_line = brief_line[:77] + "..."

    style_label = (style or "saas_minimal").replace("_", " ").title()

    results: list[dict[str, Any]] = []
    for i in range(int(count)):
        hue_a = (210 + i * 18) % 360
        hue_b = (165 + i * 22) % 360
        min_dim = min(width, height)
        c1x, c1y, r1 = int(width * 0.18), int(height * 0.22), int(min_dim * 0.22)
        c2x, c2y, r2 = int(width * 0.84), int(height * 0.30), int(min_dim * 0.18)
        c3x, c3y, r3 = int(width * 0.66), int(height * 0.86), int(min_dim * 0.24)
        card_x, card_y = int(width * 0.07), int(height * 0.10)
        card_w, card_h = int(width * 0.86), int(height * 0.80)
        t1x, t1y = int(width * 0.12), int(height * 0.20)
        t2y, t3y, t4y = int(height * 0.26), int(height * 0.36), int(height * 0.80)

        svg_lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"',
            f'  viewBox="0 0 {width} {height}">',
            "  <defs>",
            '    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">',
            f'      <stop offset="0" stop-color="hsl({hue_a} 88% 56%)" stop-opacity="0.95"/>',
            f'      <stop offset="1" stop-color="hsl({hue_b} 82% 50%)" stop-opacity="0.92"/>',
            "    </linearGradient>",
            '    <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">',
            '      <feGaussianBlur stdDeviation="40"/>',
            "    </filter>",
            "  </defs>",
            '  <rect width="100%" height="100%" fill="hsl(215 45% 96%)"/>',
            f'  <circle cx="{c1x}" cy="{c1y}" r="{r1}"',
            '    fill="url(#g)" filter="url(#blur)" opacity="0.9"/>',
            f'  <circle cx="{c2x}" cy="{c2y}" r="{r2}"',
            f'    fill="hsl({hue_b} 90% 60%)" filter="url(#blur)" opacity="0.7"/>',
            f'  <circle cx="{c3x}" cy="{c3y}" r="{r3}"',
            f'    fill="hsl({hue_a} 90% 56%)" filter="url(#blur)" opacity="0.55"/>',
            f'  <rect x="{card_x}" y="{card_y}" width="{card_w}" height="{card_h}" rx="44"',
            '    fill="rgba(255,255,255,0.72)" stroke="rgba(15,35,76,0.10)"/>',
            f'  <text x="{t1x}" y="{t1y}" font-family="ui-sans-serif, system-ui"',
            '    font-size="44" font-weight="800" fill="rgba(13,27,42,0.9)">OrcaFind AI</text>',
            f'  <text x="{t1x}" y="{t2y}" font-family="ui-sans-serif, system-ui"',
            '    font-size="26" font-weight="700" fill="rgba(19,103,255,0.95)">'
            f"{_escape_xml(style_label)}</text>",
            f'  <text x="{t1x}" y="{t3y}" font-family="ui-sans-serif, system-ui"',
            '    font-size="30" font-weight="700" fill="rgba(13,27,42,0.78)">'
            f"{_escape_xml(brief_line)}</text>",
            f'  <text x="{t1x}" y="{t4y}" font-family="ui-sans-serif, system-ui"',
            '    font-size="22" font-weight="700" fill="rgba(96,112,138,0.88)">'
            f"Option {i + 1} · {seed}</text>",
            "</svg>",
        ]
        svg = "\n".join(svg_lines)

        # Use SVG data URLs; browser will download as .png via the `download` attr name,
        # but the content is SVG.
        # This is acceptable as a placeholder; when you wire a provider, you'll get true PNGs.
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        data_url = f"data:image/svg+xml;base64,{b64}"
        results.append({"label": f"Option {i + 1}", "data_url": data_url})

    return results
