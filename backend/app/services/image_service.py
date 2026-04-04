import base64
import datetime as _dt
from typing import Any, Dict, List, Tuple


def _aspect_dimensions(aspect: str) -> Tuple[int, int]:
    aspect = (aspect or "square").strip().lower()
    if aspect == "portrait":
        return 1024, 1280
    if aspect == "landscape":
        return 1280, 720
    return 1024, 1024


def _escape_xml(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def generate_placeholder_images(*, brief: str, style: str, aspect: str, count: int) -> List[Dict[str, Any]]:
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

    results: List[Dict[str, Any]] = []
    for i in range(int(count)):
        hue_a = (210 + i * 18) % 360
        hue_b = (165 + i * 22) % 360
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="hsl({hue_a} 88% 56%)" stop-opacity="0.95"/>
      <stop offset="1" stop-color="hsl({hue_b} 82% 50%)" stop-opacity="0.92"/>
    </linearGradient>
    <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="40"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="hsl(215 45% 96%)"/>
  <circle cx="{int(width*0.18)}" cy="{int(height*0.22)}" r="{int(min(width,height)*0.22)}" fill="url(#g)" filter="url(#blur)" opacity="0.9"/>
  <circle cx="{int(width*0.84)}" cy="{int(height*0.3)}" r="{int(min(width,height)*0.18)}" fill="hsl({hue_b} 90% 60%)" filter="url(#blur)" opacity="0.7"/>
  <circle cx="{int(width*0.66)}" cy="{int(height*0.86)}" r="{int(min(width,height)*0.24)}" fill="hsl({hue_a} 90% 56%)" filter="url(#blur)" opacity="0.55"/>
  <rect x="{int(width*0.07)}" y="{int(height*0.1)}" width="{int(width*0.86)}" height="{int(height*0.8)}" rx="44" fill="rgba(255,255,255,0.72)" stroke="rgba(15,35,76,0.10)"/>
  <text x="{int(width*0.12)}" y="{int(height*0.2)}" font-family="ui-sans-serif, system-ui" font-size="44" font-weight="800" fill="rgba(13,27,42,0.9)">OrcaFind AI</text>
  <text x="{int(width*0.12)}" y="{int(height*0.26)}" font-family="ui-sans-serif, system-ui" font-size="26" font-weight="700" fill="rgba(19,103,255,0.95)">{_escape_xml(style_label)}</text>
  <text x="{int(width*0.12)}" y="{int(height*0.36)}" font-family="ui-sans-serif, system-ui" font-size="30" font-weight="700" fill="rgba(13,27,42,0.78)">{_escape_xml(brief_line)}</text>
  <text x="{int(width*0.12)}" y="{int(height*0.80)}" font-family="ui-sans-serif, system-ui" font-size="22" font-weight="700" fill="rgba(96,112,138,0.88)">Option {i+1} · {seed}</text>
</svg>"""

        # Use SVG data URLs; browser will download as .png via the `download` attr name, but content is SVG.
        # This is acceptable as a placeholder; when you wire a provider, you'll get true PNGs.
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        data_url = f"data:image/svg+xml;base64,{b64}"
        results.append({"label": f"Option {i+1}", "data_url": data_url})

    return results

