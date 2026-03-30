"""The Autonomous Brainstormer — Idea Generator for the Chucky AI pipeline.

Uses Anthropic Claude to pick a fresh, obscure topic for the next video,
consulting a local memory file (used_topics.json) so no topic is ever repeated.
Rotates through five story categories to ensure variety.
"""

import json
import logging
import os
import random
import re
from collections import Counter
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

HISTORY_FILE = Path("used_topics.json")

# ── Story categories (matching the five RAG research files) ───────────

STORY_CATEGORIES: dict[str, str] = {
    "real_world_unexplained": (
        "Real-world unexplained historical events and phenomena — mysterious "
        "deaths, impossible occurrences, objects or substances that defy "
        "explanation, cursed artifacts, mass hysteria events, or deeply strange "
        "government-documented cases."
    ),
    "unexplained_broadcasts": (
        "Unexplained broadcasts, internet mysteries, and signal anomalies — "
        "hijacked TV signals, mysterious number stations, unidentified "
        "transmissions, coded messages, lost media, or digital phenomena that "
        "were never explained."
    ),
    "urban_legends": (
        "Localized urban legends, haunted places, and cursed locations — "
        "region-specific folklore with real documented encounters, buildings "
        "or sites with persistent disturbing reports, or community-wide "
        "paranormal experiences tied to a specific place."
    ),
    "historical_encounters": (
        "Verified terrifying historical encounters with animals, nature, or "
        "the unknown — documented attacks by creatures behaving abnormally, "
        "swarms, infestations, environmental horrors, or encounters with "
        "unidentified beings that left physical evidence."
    ),
    "vanishings_cryptids": (
        "Famous historical vanishings and cryptid encounters — people or "
        "groups who disappeared under bizarre circumstances, or documented "
        "sightings of unidentified creatures with multiple witnesses and "
        "physical evidence."
    ),
}

CATEGORY_NAMES = list(STORY_CATEGORIES.keys())

# ── System prompt (category is injected at runtime) ───────────────────

SYSTEM_PROMPT_TEMPLATE = (
    "You are the Chief Archivist for a horror channel called 'Department of the "
    "Unknown' that produces 60–90 second short-form horror videos about real-world "
    "unexplained phenomena.\n\n"
    "Your sole task is to select ONE topic for the next video.\n\n"
    "CATEGORY CONSTRAINT:\n"
    "For this video you MUST select a topic that fits the following category:\n"
    "  «{category_name}» — {category_description}\n"
    "Do NOT pick a topic from a different category. Stay strictly within this one.\n\n"
    "TOPIC CRITERIA — the topic MUST also satisfy ALL of the following:\n"
    "1. It must be a REAL event, encounter, or phenomenon that actually happened "
    "or was widely documented.\n"
    "2. It must be HIGHLY OBSCURE — not mainstream topics like Bermuda Triangle, "
    "Bigfoot, Loch Ness Monster, Area 51, Mothman, Skinwalker Ranch, or the "
    "Amityville Horror. Dig deeper. Pick something most people have never heard of.\n"
    "3. It must be HISTORICALLY VERIFIABLE — there should be real newspaper "
    "articles, police reports, government files, or academic references that "
    "document it.\n"
    "4. It must be DEEPLY UNSETTLING — the kind of topic that lingers in someone's "
    "mind after hearing it. Prefer cases with eerie, unexplained details that have "
    "no satisfying resolution.\n\n"
    "DEDUPLICATION RULES:\n"
    "- You will be given a list of previously used topics. NEVER select any topic "
    "from that list.\n"
    "- Also avoid topics that are merely reworded versions of a used topic (e.g. if "
    "'Dyatlov Pass Incident' was used, do NOT pick 'Dyatlov Pass Mystery' or "
    "'The Dyatlov Pass Deaths').\n\n"
    "SELECTION PROCESS:\n"
    "Before making your selection, think through several candidate topics in a "
    "<scratchpad>. For each candidate, briefly note: (a) how well it fits the "
    "required category, (b) how obscure it is, (c) whether it overlaps with any "
    "used topic. Then pick the single best one.\n\n"
    "OUTPUT FORMAT:\n"
    "After your scratchpad reasoning, output ONLY a JSON object with a single key "
    "'selected_topic' containing just the topic name as a short, descriptive string "
    "(e.g. 'The Oakville Blobs of 1994', 'Hinterkaifeck Farm Murders'). "
    "Do NOT include any text outside the scratchpad and the JSON object."
)


class IdeaGenerator:
    """Autonomously selects unique topics for the pipeline, with memory."""

    def __init__(self, model_name: str = "claude-sonnet-4-20250514"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = model_name

    # ── Memory ────────────────────────────────────────────────────────

    def _load_raw(self) -> dict:
        """Load the history file. Auto-migrates legacy list format."""
        if not HISTORY_FILE.is_file():
            return {"topics": [], "last_category": None}
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s — starting fresh.", HISTORY_FILE, exc)
            return {"topics": [], "last_category": None}

        # Legacy format: plain list of strings → migrate
        if isinstance(data, list):
            logger.info("Migrating used_topics.json from list to dict format.")
            migrated = {
                "topics": [
                    {"topic": t, "category": "real_world_unexplained"}
                    for t in data
                ],
                "last_category": "real_world_unexplained",
            }
            HISTORY_FILE.write_text(
                json.dumps(migrated, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return migrated

        return data

    def load_history(self) -> list[str]:
        """Load previously used topic names. Returns [] if no history."""
        return [entry["topic"] for entry in self._load_raw().get("topics", [])]

    def save_topic(self, topic: str, category: str | None = None) -> None:
        """Append *topic* (and its category) to the history file."""
        raw = self._load_raw()
        raw["topics"].append({
            "topic": topic,
            "category": category or "real_world_unexplained",
        })
        raw["last_category"] = category or "real_world_unexplained"
        HISTORY_FILE.write_text(
            json.dumps(raw, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(
            "Saved topic to history (%d total, cat=%s): %s",
            len(raw["topics"]), category, topic,
        )

    # ── Category rotation ─────────────────────────────────────────────

    def _pick_next_category(self) -> str:
        """Pick the least-used category (ties broken randomly)."""
        raw = self._load_raw()
        counts = Counter(
            entry.get("category", "real_world_unexplained")
            for entry in raw.get("topics", [])
        )
        # Find the minimum usage count (0 if a category was never used)
        min_count = min((counts.get(c, 0) for c in CATEGORY_NAMES), default=0)
        least_used = [c for c in CATEGORY_NAMES if counts.get(c, 0) == min_count]
        chosen = random.choice(least_used)
        logger.info(
            "Category rotation — counts: %s → chose '%s'",
            {c: counts.get(c, 0) for c in CATEGORY_NAMES},
            chosen,
        )
        return chosen

    # ── Topic generation ──────────────────────────────────────────────

    # ── Category validation ────────────────────────────────────────

    def _validate_category_fit(
        self, topic: str, category: str,
    ) -> bool:
        """Ask Claude whether *topic* genuinely fits *category*. Returns True/False."""
        check_prompt = (
            f"Does the following topic belong to the category "
            f"\"«{category}» — {STORY_CATEGORIES[category]}\"?\n\n"
            f"Topic: {topic}\n\n"
            f"Answer with ONLY a JSON object: {{\"fits\": true}} or {{\"fits\": false}}."
        )
        msg = self.client.messages.create(
            model=self.model_name,
            max_tokens=64,
            messages=[{"role": "user", "content": check_prompt}],
        )
        raw = msg.content[0].text
        m = re.search(r'\{[^{}]*"fits"[^{}]*\}', raw)
        if m:
            try:
                return json.loads(m.group()).get("fits", False) is True
            except json.JSONDecodeError:
                pass
        return False

    # ── Topic generation ──────────────────────────────────────────────

    def generate_topic(self, category_override: str | None = None) -> tuple[str, str]:
        """Ask Claude for one fresh topic. Returns (topic, category).

        If *category_override* is given (and valid), that category is used
        instead of the automatic least-used rotation.

        Includes a category-validation loop: if the returned topic doesn't
        fit the requested category, we retry with a stricter correction
        prompt (up to 2 retries).
        """
        used_topics = self.load_history()
        if category_override and category_override in STORY_CATEGORIES:
            category = category_override
            logger.info("Category override: %s", category)
        else:
            category = self._pick_next_category()
        MAX_CAT_RETRIES = 2

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            category_name=category,
            category_description=STORY_CATEGORIES[category],
        )

        if used_topics:
            user_msg = (
                "Here is the list of already-used topics. You MUST NOT select any "
                "of these, nor any close variation:\n\n"
                "<used_topics>\n"
                + json.dumps(used_topics, indent=2, ensure_ascii=False)
                + "\n</used_topics>\n\n"
                "Now use your <scratchpad> to brainstorm candidates, then output "
                "your final selection as a JSON object."
            )
        else:
            user_msg = (
                "No topics have been used yet — you have free rein.\n\n"
                "Use your <scratchpad> to brainstorm candidates, then output "
                "your final selection as a JSON object."
            )

        topic: str | None = None
        for attempt in range(1 + MAX_CAT_RETRIES):
            messages = [{"role": "user", "content": user_msg}]

            # On retries, add a correction turn
            if attempt > 0 and topic:
                messages = [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": f'{{"selected_topic": "{topic}"}}'},
                    {
                        "role": "user",
                        "content": (
                            f"The topic you selected ('{topic}') does NOT fit the "
                            f"required category «{category}». Pick a DIFFERENT topic "
                            f"that clearly belongs to: {STORY_CATEGORIES[category]}\n\n"
                            "Output ONLY a JSON object with 'selected_topic'."
                        ),
                    },
                ]

            message = self.client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            )

            raw_text = message.content[0].text

            json_match = re.search(r'\{[^{}]*"selected_topic"[^{}]*\}', raw_text)
            if not json_match:
                raise RuntimeError(
                    f"Could not find JSON in Claude response:\n{raw_text}"
                )

            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Claude returned invalid JSON:\n{json_match.group()}"
                ) from exc

            topic = result.get("selected_topic")
            if not topic:
                raise RuntimeError(
                    f"Claude response missing 'selected_topic':\n{raw_text}"
                )

            # Validate category fit
            if self._validate_category_fit(topic, category):
                logger.info(
                    "Brainstormer selected topic (attempt %d): %s (category: %s)",
                    attempt + 1, topic, category,
                )
                return topic, category

            logger.warning(
                "Topic '%s' failed category validation for '%s' (attempt %d/%d)",
                topic, category, attempt + 1, 1 + MAX_CAT_RETRIES,
            )

        # Accept the last topic even if validation failed after all retries
        logger.warning(
            "Accepting topic '%s' after %d failed category checks.",
            topic, 1 + MAX_CAT_RETRIES,
        )
        return topic, category  # type: ignore[return-value]
