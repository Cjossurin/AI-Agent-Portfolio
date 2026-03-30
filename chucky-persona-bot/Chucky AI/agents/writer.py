"""The Narrative Scriptwriter — Agent 2 of the Chucky AI pipeline.

Uses Anthropic Claude to transform research JSON from Agent 1 into a
horror narration script strictly under 60 seconds for YouTube Shorts.
"""

import json
import logging
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import anthropic
from prompt_templates import (
    CHUCKY_WRITER_PROMPT_TEMPLATE,
    CHUCKY_WRITER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = CHUCKY_WRITER_SYSTEM_PROMPT
SCRIPT_PROMPT_TEMPLATE = CHUCKY_WRITER_PROMPT_TEMPLATE


class NarrativeScriptwriter:
    """Transforms research JSON into a paced horror narration script via Claude."""

    def __init__(
        self,
        rag_dir: str | Path | None = None,
        model_name: str = "claude-sonnet-4-20250514",
    ):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name

        if rag_dir is None:
            rag_dir = (
                Path(__file__).resolve().parent.parent
                / "Agent RAGs"
                / "The Narrative Scriptwriter"
            )
        self.rag_dir = Path(rag_dir)

        self.pacing_context = self._load_pacing_rag()

    # ── RAG loading ───────────────────────────────────────────────────

    def _load_pacing_rag(self) -> str:
        """Read all .txt and .md files from the Scriptwriter RAG directory."""
        if not self.rag_dir.is_dir():
            logger.info("RAG directory not found at %s — skipping.", self.rag_dir)
            return ""

        fragments: list[str] = []
        for pattern in ("*.txt", "*.md"):
            for filepath in sorted(self.rag_dir.glob(pattern)):
                try:
                    text = filepath.read_text(encoding="utf-8").strip()
                    if text:
                        fragments.append(f"--- {filepath.name} ---\n{text}")
                except OSError as exc:
                    logger.warning("Could not read %s: %s", filepath, exc)

        if not fragments:
            logger.info(
                "No pacing RAG files found in %s — proceeding without structural reference.",
                self.rag_dir,
            )
            return ""

        logger.info(
            "Loaded pacing RAG from %d file(s) in %s.",
            len(fragments),
            self.rag_dir,
        )
        return "\n\n".join(fragments)

    # ── Duplicate-sentence detector ─────────────────────────────────

    @staticmethod
    def _count_script_words(script: dict) -> int:
        """Count total spoken words across all narration blocks, ignoring SSML tags."""
        import re as _re
        total = 0
        for block in script.get("narration_blocks", []):
            text = _re.sub(r"<[^>]+>", "", block.get("text", ""))
            total += len(text.split())
        return total

    @staticmethod
    def _check_duplicate_sentences(script: dict) -> list[tuple[str, str, float]]:
        """Return pairs of sentences that are suspiciously similar.

        Strips SSML tags, splits on sentence-ending punctuation, then
        compares every pair via SequenceMatcher.  Returns a list of
        (sent_a, sent_b, ratio) for pairs with ratio > 0.75.
        """
        ssml_re = re.compile(r"<[^>]+>")
        all_sentences: list[str] = []
        for block in script.get("narration_blocks", []):
            text = ssml_re.sub("", block.get("text", ""))
            # Split on sentence-ending punctuation
            for sent in re.split(r'(?<=[.!?])\s+', text):
                cleaned = sent.strip()
                if len(cleaned) > 10:
                    all_sentences.append(cleaned)

        dupes: list[tuple[str, str, float]] = []
        for i in range(len(all_sentences)):
            for j in range(i + 1, len(all_sentences)):
                ratio = SequenceMatcher(
                    None,
                    all_sentences[i].lower(),
                    all_sentences[j].lower(),
                ).ratio()
                if ratio > 0.75:
                    dupes.append((all_sentences[i], all_sentences[j], ratio))
        return dupes

    # ── Core script-writing function ──────────────────────────────────

    def write_script(self, research_json: dict) -> dict:
        """Accept research output from Agent 1 and return a narration script.

        Includes a post-processing check for duplicate sentences.  If any
        are found, the script is retried once.
        """
        if not research_json:
            raise ValueError("research_json must be a non-empty dict.")

        pacing_section = ""
        if self.pacing_context:
            pacing_section = (
                "<pacing_reference>\n"
                "The following is your structural, pacing, and horror formula "
                "reference. FOLLOW THIS GUIDANCE CLOSELY. Apply the 2-Second Hook "
                "Rule, use the SSML pause mechanics described, and model your "
                "output after the Master Script Templates provided.\n\n"
                f"{self.pacing_context}\n"
                "</pacing_reference>\n"
            )

        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            research_json=json.dumps(research_json, indent=2, ensure_ascii=False),
            pacing_section=pacing_section,
        )

        MAX_SCRIPT_ATTEMPTS = 2
        for attempt in range(MAX_SCRIPT_ATTEMPTS):
            message = self.client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = message.content[0].text

            # Response may contain <scratchpad>...</scratchpad> before the JSON.
            # Extract the JSON object from the response.
            json_match = re.search(
                r'\{[\s\S]*"case_title"[\s\S]*"narration_blocks"[\s\S]*\}',
                raw_text,
            )
            json_str = json_match.group() if json_match else raw_text

            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Claude returned invalid JSON:\n{raw_text}"
                ) from exc

            if "narration_blocks" not in result:
                raise RuntimeError(
                    f"Claude response missing 'narration_blocks':\n{raw_text}"
                )

            # Check word count — must be >= 130 words for a ~60s video
            total_words = self._count_script_words(result)
            if total_words < 130:
                logger.warning(
                    "Script too short: %d words (need ≥130). Retrying (attempt %d/%d).",
                    total_words, attempt + 1, MAX_SCRIPT_ATTEMPTS,
                )
                continue

            # Check for duplicate sentences
            dupes = self._check_duplicate_sentences(result)
            if not dupes:
                return result

            logger.warning(
                "Duplicate sentences detected (attempt %d/%d): %s",
                attempt + 1, MAX_SCRIPT_ATTEMPTS,
                [(a[:40], b[:40], f"{r:.2f}") for a, b, r in dupes],
            )

        # Accept the last result even with duplicates / word-count issues after all retries
        logger.warning("Accepting script after %d attempts.", MAX_SCRIPT_ATTEMPTS)
        return result
