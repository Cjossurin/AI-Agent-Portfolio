"""The SEO & Metadata Agent — Agent 5 of the Chucky AI pipeline.

Uses Anthropic Claude to generate optimised, platform-specific upload
metadata for short-form horror videos and saves the result into the
case asset folder.

Generates metadata for: YouTube Shorts, TikTok, Instagram Reels,
Facebook Reels, and X/Twitter.
"""

import json
import logging
import os
import re
from pathlib import Path

import anthropic
from prompt_templates import (
    CHUCKY_SEO_PROMPT_TEMPLATE,
    CHUCKY_SEO_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = CHUCKY_SEO_SYSTEM_PROMPT
METADATA_PROMPT_TEMPLATE = CHUCKY_SEO_PROMPT_TEMPLATE


class SEOMetadataAgent:
    """Generates optimised, platform-specific upload metadata for horror shorts."""

    def __init__(self, model_name: str = "claude-sonnet-4-20250514"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name

    # ── Core metadata generation ──────────────────────────────────────

    def generate_metadata(
        self,
        case_id: str,
        research_json: dict,
        script_json: dict,
    ) -> dict:
        """Generate platform-specific metadata, then save to assets."""
        if not research_json:
            raise ValueError("research_json must be a non-empty dict.")
        if not script_json:
            raise ValueError("script_json must be a non-empty dict.")

        prompt = METADATA_PROMPT_TEMPLATE.format(
            research_json=json.dumps(research_json, indent=2, ensure_ascii=False),
            script_json=json.dumps(script_json, indent=2, ensure_ascii=False),
        )

        message = self.client.messages.create(
            model=self.model_name,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text

        # Response may contain <scratchpad>...</scratchpad> before the JSON.
        json_match = re.search(
            r'\{[\s\S]*"title"[\s\S]*"hashtags"[\s\S]*\}',
            raw_text,
        )
        json_str = json_match.group() if json_match else raw_text

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Claude returned invalid JSON:\n{raw_text}"
            ) from exc

        # Validate top-level keys
        required_keys = {"title", "description", "hashtags"}
        missing = required_keys - result.keys()
        if missing:
            raise RuntimeError(
                f"Claude response missing required keys {missing}:\n{raw_text}"
            )

        # Validate title length
        if len(result["title"]) > 60:
            logger.warning(
                "Title exceeds 60 chars (%d) — truncating.", len(result["title"])
            )
            result["title"] = result["title"][:57] + "..."

        # Validate tweet length
        tweet = result.get("x_twitter_metadata", {}).get("main_tweet", "")
        if len(tweet) > 280:
            logger.warning(
                "Tweet exceeds 280 chars (%d) — truncating.", len(tweet)
            )
            result["x_twitter_metadata"]["main_tweet"] = tweet[:277] + "..."

        # Save to asset folder
        asset_dir = Path("assets") / f"case_{case_id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        out_path = asset_dir / "metadata.json"
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Metadata saved to %s", out_path)

        return result
