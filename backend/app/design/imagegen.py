"""Optional AI image generation (OpenAI Images API) for illustrations/artwork.

Off by default. Requires OPENAI_API_KEY. Every call is checked against the spending limits
first and recorded afterwards. Products using AI artwork are automatically given Etsy's
required AI-use disclosure in their listing.

Resolution note: image models return ~1-2 megapixels. At 300 DPI that only covers small prints,
so the QC engine flags any placement under 300 DPI. Use AI artwork for small pieces or add an
upscaling step before selling large prints.
"""
from __future__ import annotations

import base64
from pathlib import Path

from ..config import settings
from ..db import get_setting
from ..services import Budget, ExternalServiceError, http_request


class ImageGenNotConfigured(RuntimeError):
    pass


def available() -> bool:
    return bool(settings.openai_api_key)


def generate(prompt: str, out_path: Path, size: str = "1024x1536", quality: str = "high") -> dict:
    if not settings.openai_api_key:
        raise ImageGenNotConfigured("OPENAI_API_KEY is not set - AI artwork is disabled")
    cost = float(get_setting("budget").get("image_cost_usd", 0.07))
    Budget.check(cost, "AI image generation")
    safe_prompt = (prompt + ". Original artwork. No text, no logos, no brand names, no copyrighted characters, "
                   "no signatures, no watermarks.")
    resp = http_request("POST", "https://api.openai.com/v1/images/generations", timeout=180,
                        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                        json={"model": settings.openai_image_model, "prompt": safe_prompt, "size": size,
                              "quality": quality, "n": 1})
    if resp.status_code >= 400:
        raise ExternalServiceError(f"Image API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()["data"][0]
    raw = base64.b64decode(data["b64_json"]) if data.get("b64_json") else http_request("GET", data["url"]).content
    Path(out_path).write_bytes(raw)
    Budget.record("openai", "image", cost, note=prompt[:200])
    from PIL import Image
    with Image.open(out_path) as im:
        w, h = im.size
    return {"path": str(out_path), "px": [w, h], "cost_usd": cost, "prompt": safe_prompt, "model": settings.openai_image_model}
