"""Vintage Illustration Image Generator — dedicated Flux agent for the vintage_illustration style.

Uses text-only generation (fal-ai/flux-pro/v1.1) — no reference image blending.
Style is enforced entirely through the prompt template.
"""

import logging
import os
import time
from pathlib import Path

import fal_client
import requests
from prompt_templates import CHUCKY_VINTAGE_IMAGE_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

FLUX_MODEL_ID = "fal-ai/flux-pro/v1.1"
STYLE_NAME = "vintage_illustration"

MAX_RETRIES = 3
RETRY_DELAY = 5
API_TIMEOUT = 300

PROMPT_TEMPLATE = CHUCKY_VINTAGE_IMAGE_PROMPT_TEMPLATE


class VintageIllustrationImageGenerator:
    """Generates Flux images in the Vintage Horror Illustration style via text-only prompts."""

    def __init__(self):
        fal_key = os.getenv("FAL_AI_API_KEY")
        if not fal_key:
            raise EnvironmentError("FAL_AI_API_KEY is not set.")
        os.environ["FAL_KEY"] = fal_key

    def _enrich_prompt(self, prompt: str) -> str:
        """Apply the vintage horror style prompt template to the scene description."""
        return PROMPT_TEMPLATE.format(scene_prompt=prompt.strip())

    def generate_single_image(self, prompt: str, out_path: Path) -> str:
        """Generate one image via text-only Flux and save it. Returns the remote image URL."""
        enriched_prompt = self._enrich_prompt(prompt)
        fal_input: dict = {
            "prompt": enriched_prompt,
            "image_size": {"width": 1080, "height": 1920},
            "num_images": 1,
        }
        logger.info("  Text-only generation (vintage_illustration)")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("  Generating image \u2192 %s (attempt %d)", out_path.name, attempt)
                result = fal_client.subscribe(FLUX_MODEL_ID, arguments=fal_input, with_logs=False)
                image_url = result["images"][0]["url"]
                _download_file(image_url, out_path, min_size=50_000)
                logger.info("  \u2713 Image saved: %s", out_path)
                return image_url
            except (requests.exceptions.Timeout, TimeoutError) as exc:
                logger.warning("  Image attempt %d timed out: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
            except Exception as exc:
                logger.warning("  Image attempt %d failed: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise RuntimeError(f"Failed to generate image after {MAX_RETRIES} attempts: {out_path}")

    # ── Batch generation (full storyboard) ────────────────────────────

    def generate_images(self, storyboard_json: dict, case_id: str) -> list[dict]:
        """Generate images for all storyboard blocks. Returns list of result dicts."""
        blocks = storyboard_json.get("storyboard", [])
        if not blocks:
            raise ValueError("storyboard_json must contain a non-empty 'storyboard' array.")

        asset_dir = Path("assets") / f"case_{case_id}"
        asset_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Vintage illustration image generation — text-only")
        results: list[dict] = []

        for entry in blocks:
            bid = entry["block_id"]
            visual_prompt = entry.get("visual_prompt", "")
            image_path = asset_dir / f"{bid}_image.jpg"

            logger.info("── Block %d (vintage_illustration) ──", bid)
            image_url = self.generate_single_image(visual_prompt, image_path)
            results.append({
                "block_id": bid,
                "image_path": str(image_path),
                "image_url": image_url,
            })

        logger.info("Vintage illustration images complete for case_%s (%d blocks).", case_id, len(results))
        return results


# ── Download helper ───────────────────────────────────────────────────

def _download_file(url: str, out_path: Path, min_size: int = 0) -> None:
    """Download a file from a URL to a local path."""
    for dl_attempt in range(2):
        resp = requests.get(url, timeout=API_TIMEOUT)
        resp.raise_for_status()
        data = resp.content

        expected = resp.headers.get("Content-Length")
        if expected and len(data) < int(expected):
            logger.warning("Truncated download: got %d bytes, expected %s — retrying", len(data), expected)
            if dl_attempt == 0:
                continue

        with open(out_path, "wb") as f:
            f.write(data)

        if min_size and len(data) < min_size:
            logger.warning("Downloaded file %s is only %d bytes (min %d) — retrying", out_path.name, len(data), min_size)
            if dl_attempt == 0:
                continue

        return

    logger.warning("Download for %s below expectations after retry.", out_path.name)
