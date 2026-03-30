"""The Anomaly Researcher — Agent 1 of the Chucky AI pipeline.

Uses Google Gemini to research paranormal / true-crime cases and return
structured JSON suitable for downstream script generation.
"""

import json
import logging
import os
import re
from pathlib import Path

from google import genai
from google.genai import types
from prompt_templates import (
    CHUCKY_RESEARCHER_SYSTEM_PROMPT,
    CHUCKY_RESEARCH_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = CHUCKY_RESEARCHER_SYSTEM_PROMPT
RESEARCH_PROMPT_TEMPLATE = CHUCKY_RESEARCH_PROMPT_TEMPLATE


class AnomalyResearcher:
    """Researches anomalous cases via Gemini, grounded by local RAG documents."""

    def __init__(
        self,
        rag_dir: str | Path | None = None,
        model_name: str = "gemini-2.5-flash",
    ):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

        if rag_dir is None:
            rag_dir = Path(__file__).resolve().parent.parent / "Agent RAGs" / "The Anomaly Researcher"
        self.rag_dir = Path(rag_dir)

        self.rag_context = self._load_rag_context()

    # ── RAG loading ───────────────────────────────────────────────────

    def _load_rag_context(self) -> str:
        """Read all .txt and .md files from the RAG directory."""
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
                "No .txt or .md files found in %s — proceeding without RAG context.",
                self.rag_dir,
            )
            return ""

        logger.info(
            "Loaded RAG context from %d file(s) in %s.",
            len(fragments),
            self.rag_dir,
        )
        return "\n\n".join(fragments)

    # ── Core research function ────────────────────────────────────────

    def research_case(self, topic: str) -> dict:
        """Send *topic* to Gemini and return a structured case dict."""
        if not topic or not topic.strip():
            raise ValueError("topic must be a non-empty string.")

        rag_section = ""
        if self.rag_context:
            rag_section = (
                "<archival_reference_material>\n"
                "The following is your PRIMARY SOURCE database. When the topic "
                "matches or relates to a catalogued case, extract factual timelines, "
                "anomalous evidence, witness accounts, and psychological dread "
                "analysis directly from this material. Treat these entries as "
                "verified departmental records.\n\n"
                f"{self.rag_context}\n"
                "</archival_reference_material>\n"
            )

        prompt = RESEARCH_PROMPT_TEMPLATE.format(
            topic=topic.strip(),
            rag_section=rag_section,
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
        raw_text = response.text

        # Response may contain <analysis>...</analysis> before the JSON.
        # Extract the JSON object from the response.
        json_match = re.search(
            r'\{[\s\S]*"case_name"[\s\S]*"key_details"[\s\S]*\}',
            raw_text,
        )
        json_str = json_match.group() if json_match else raw_text

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Gemini returned invalid JSON for topic '{topic}':\n{raw_text}"
            ) from exc

        expected_keys = {"case_name", "location", "year", "core_anomaly", "key_details"}
        missing = expected_keys - result.keys()
        if missing:
            raise RuntimeError(
                f"Gemini response missing required keys {missing}:\n{raw_text}"
            )

        return result
