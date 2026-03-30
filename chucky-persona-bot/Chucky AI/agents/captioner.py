"""The Captioner — Generates word-level timed captions for the Chucky AI pipeline.

Uses OpenAI Whisper to transcribe each narration audio file and extract
word-level timestamps, then groups words into 2–3 word caption chunks
with natural break points (never mid-sentence).
"""

import json
import logging
import os
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Grouping rules ────────────────────────────────────────────────────
MAX_WORDS_PER_GROUP = 3
MIN_WORDS_PER_GROUP = 2

# If the silence gap between two consecutive words exceeds this threshold,
# treat it as a sentence boundary and flush the current caption group.
SENTENCE_GAP_SEC = 0.4

# Punctuation that signals a natural break point
BREAK_PUNCTUATION = frozenset({".", "!", "?", ",", ";", ":", "—", "–", "…"})


class Captioner:
    """Transcribes narration audio and produces grouped word-level captions."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file for Whisper transcription."
            )
        self.client = OpenAI(api_key=api_key)

    # ── Public interface ──────────────────────────────────────────────

    def generate_captions(self, case_id: str, media_manifest: dict) -> list[dict]:
        """Run Whisper on each audio block, group words, return caption data.

        Returns a list of caption block objects, one per narration block:
        [
          {
            "blockId": 1,
            "captionGroups": [
              {
                "words": [
                  {"word": "Department", "start": 0.0, "end": 0.45},
                  {"word": "of", "start": 0.46, "end": 0.55},
                  {"word": "the", "start": 0.56, "end": 0.65}
                ],
                "start": 0.0,
                "end": 0.65
              },
              ...
            ]
          },
          ...
        ]
        """
        blocks = media_manifest.get("blocks", [])
        all_captions: list[dict] = []

        for block in blocks:
            bid = block["block_id"]
            audio_path = block.get("audio_path")

            if not audio_path or not Path(audio_path).exists():
                logger.warning("Block %d has no audio file — skipping captions.", bid)
                all_captions.append({"blockId": bid, "captionGroups": []})
                continue

            logger.info("Transcribing block %d for word-level captions...", bid)
            words = self._transcribe_words(audio_path)
            groups = self._group_words(words)
            all_captions.append({"blockId": bid, "captionGroups": groups})
            logger.info(
                "  Block %d: %d words → %d caption groups.", bid, len(words), len(groups)
            )

        # Persist to asset folder
        asset_dir = Path("assets") / f"case_{case_id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        out_path = asset_dir / "captions.json"
        out_path.write_text(
            json.dumps(all_captions, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Captions saved to %s", out_path)

        return all_captions

    # ── Whisper transcription ─────────────────────────────────────────

    def _transcribe_words(self, audio_path: str) -> list[dict]:
        """Call Whisper with word-level timestamp granularity."""
        with open(audio_path, "rb") as f:
            response = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )

        words: list[dict] = []
        for w in response.words:
            words.append({
                "word": w.word.strip(),
                "start": round(w.start, 3),
                "end": round(w.end, 3),
            })
        return words

    # ── Word grouping ─────────────────────────────────────────────────

    def _group_words(self, words: list[dict]) -> list[dict]:
        """Group words into 2–3 word chunks, breaking at natural boundaries.

        Rules:
        - Each group has 2–3 words (never more than 3).
        - Prefer breaking after punctuation (.,!?;:—).
        - If we hit 3 words, force a break regardless.
        - A trailing group of 1 word is allowed (can be dramatic).
        """
        if not words:
            return []

        groups: list[dict] = []
        current: list[dict] = []
        prev_end: float | None = None

        for word_data in words:
            # Detect sentence boundary via silence gap
            if prev_end is not None and current:
                gap = word_data["start"] - prev_end
                if gap >= SENTENCE_GAP_SEC:
                    groups.append(self._make_group(current))
                    current = []

            current.append(word_data)
            prev_end = word_data["end"]
            text = word_data["word"]

            # Does this word end with natural-break punctuation?
            ends_with_break = any(text.endswith(p) for p in BREAK_PUNCTUATION)

            should_break = False
            if len(current) >= MAX_WORDS_PER_GROUP:
                should_break = True
            elif len(current) >= MIN_WORDS_PER_GROUP and ends_with_break:
                should_break = True

            if should_break:
                groups.append(self._make_group(current))
                current = []

        # Flush remaining words
        if current:
            groups.append(self._make_group(current))

        return groups

    @staticmethod
    def _make_group(words: list[dict]) -> dict:
        return {
            "words": [
                {"word": w["word"], "start": w["start"], "end": w["end"]}
                for w in words
            ],
            "start": words[0]["start"],
            "end": words[-1]["end"],
        }
