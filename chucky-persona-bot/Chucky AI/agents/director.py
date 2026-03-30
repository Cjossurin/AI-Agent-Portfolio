"""The Visual & Technical Director — Agent 3 of the Chucky AI pipeline.

Uses Anthropic Claude to transform narration blocks from Agent 2 into a
visual storyboard with Flux-ready image prompts and motion assignments.
Autonomously selects between two curated art styles (dark_comic and
vintage_illustration) based on the script's tone and narrative pacing.
"""

import json
import logging
import os
import random
import re
from pathlib import Path

import anthropic
from prompt_templates import (
    CHUCKY_DIRECTOR_STORYBOARD_PROMPT_TEMPLATE,
    CHUCKY_DIRECTOR_SYSTEM_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)

STYLE_HISTORY_FILE = Path("style_history.json")

# ── Art-style definitions ─────────────────────────────────────────────

VALID_STYLES = ("dark_comic", "vintage_illustration")

STYLE_MODIFIERS: dict[str, str] = {
    "dark_comic": (
        "Dark adult animation style, heavy uniform black contour lines, "
        "cell-shaded coloring, desaturated moody palette with deep teals "
        "and murky greens, selective colored accent lighting from glowing "
        "eyes and fire and atmospheric glow, dramatic "
        "single-source shadows, oversized bulging eyes with tiny pupils, "
        "exaggerated grotesque teeth and angular jawlines, painterly "
        "atmospheric backgrounds, cinematic horror composition, oppressive "
        "dread aesthetic."
    ),
    "vintage_illustration": (
        "Dark vintage horror illustration style, medium-weight black contour "
        "outlines, smooth cell-shaded coloring with painterly gradient washes, "
        "near-monochromatic desaturated palette of dark olive greens and muted "
        "ochre and deep teals and slate grays, strong chiaroscuro lighting from "
        "a single practical source, heavy vignetting, uncanny semi-realistic "
        "adult faces with angular features contrasted against grotesque "
        "puppet-like horror figures with oversized round glassy eyes and wide "
        "frozen grins, subtle aged-paper grain texture overlay, oppressive "
        "claustrophobic atmosphere, Japanese horror influence, environmental "
        "decay."
    ),
}

VISUAL_PHILOSOPHIES: dict[str, str] = {
    "dark_comic": (
        "VISUAL PHILOSOPHY (derived from the reference images for this style):\n"
        "- COLOR: The palette is desaturated and moody — deep teals, murky greens, "
        "dark blues, sickly olive, muted ochre. Bright color appears ONLY as selective "
        "colored accents (glowing eyes, bioluminescent phenomena, distant fire or "
        "embers, emergency vehicle lights). Do NOT describe "
        "\"flat vibrant colors\" or \"clean vector art\" — this style uses gradient "
        "washes and atmospheric color grading.\n"
        "- LINES: Heavy, uniform black contour outlines on every shape — characters, "
        "objects, and architecture. Cell-shaded coloring within those outlines, NOT "
        "crosshatched, NOT photorealistic.\n"
        "- LIGHTING: Dramatic single-source lighting is mandatory in every frame — "
        "stage spotlights, colored environmental glow, overhead surgical lamps, moonlit rim-light. "
        "Heavy shadow casting. Atmospheric haze and fog overlays.\n"
        "- FACES: Oversized bulging eyes with tiny pupils or glowing irises. "
        "Exaggerated yellowed or rotting teeth. Enlarged heads with angular jawlines. "
        "This is pop-horror caricature, not realism.\n"
        "- ATMOSPHERE: Oppressive dread. Night scenes, environmental decay, atmospheric "
        "particles (snow, fog, haze, dust), dramatic colored light bleeding into shadows.\n"
        "- Every frame must feel like a still from a nightmare the viewer half-remembers. "
        "Composition should be unsettling: off-center subjects, too much negative space, "
        "or suffocating close-ups."
    ),
    "vintage_illustration": (
        "VISUAL PHILOSOPHY (derived from the reference images for this style):\n"
        "- COLOR: Near-monochromatic and deeply desaturated — dark olive greens, muted "
        "ochre and sepia, deep teals, slate grays. Warm amber tones appear ONLY from "
        "practical light sources (desk lamps, doorway glow, overhead fluorescents). "
        "There is NO neon, NO bright saturation, NO vibrant color of any kind. "
        "Do NOT describe \"neon accents\", \"vibrant colors\", or \"glowing signs\" — "
        "this style uses muted earth tones and atmospheric color grading only.\n"
        "- LINES: Medium-weight black contour outlines — clean, consistent, "
        "graphic-novel and manga-influenced linework. Smooth cell-shaded coloring with "
        "painterly gradient washes within the outlines. NOT crosshatched, NOT "
        "photorealistic, NOT vector-flat.\n"
        "- LIGHTING: Strong chiaroscuro with a single practical light source in every "
        "frame — overhead fluorescent tubes, window backlight, doorway rim-light, "
        "candlelight. Deep consuming shadows that swallow most of the frame. Heavy "
        "vignetting at the edges. No neon glow, no stage spotlights.\n"
        "- FACES: Two distinct modes that create uncanny valley tension. Adult human "
        "characters have semi-realistic proportions — angular jaw, prominent nose, "
        "simplified but believable features. Horror figures and entities have grotesque "
        "puppet-like distortion — oversized perfectly round glassy eyes, wide frozen "
        "toothy grins, doll-like proportions. The contrast between the two is the "
        "source of dread.\n"
        "- ATMOSPHERE: Oppressive, claustrophobic, and decayed. Predominantly night "
        "scenes. Environmental rot is visible everywhere — dirty tiles, cracked plaster, "
        "overgrown vegetation, rusted metal. Subtle aged-paper grain overlay on every "
        "frame. Japanese horror influence: figures crawling from impossible spaces, "
        "hair obscuring faces, limbs at wrong angles. Fog, dust motes, and shadow "
        "dominate the negative space.\n"
        "- Every frame must feel like a page from a cursed manga discovered in a "
        "flooded basement. Composition should be unsettling: subjects dwarfed by vast "
        "dark voids, extreme low or high angles, figures at the threshold of doorways, "
        "or suffocating close-ups of puppet-like faces."
    ),
}

# ── Category-aware subject grounding ──────────────────────────────────

_GROUNDING_RULES: dict[str, str] = {
    "real_world_unexplained": (
        "This is a REAL-WORLD MYSTERY with no supernatural element. Every visual "
        "must be grounded in reality. Depict actual subjects from the story: real "
        "people, real locations, real objects (aircraft, buildings, documents, "
        "landscapes, search teams, equipment). Do NOT invent monsters, zombies, "
        "supernatural creatures, tentacles, glowing eyes, or fantasy elements. "
        "Horror comes from atmosphere, emptiness, isolation, and the uncanny — "
        "not from fabricated creatures. Show the real dread: empty radar screens, "
        "vast featureless ocean, abandoned belongings, unanswered questions made "
        "visual through haunting compositions."
    ),
    "unexplained_broadcasts": (
        "This is about REAL SIGNAL ANOMALIES AND BROADCASTS. Depict real technology: "
        "TV screens, radio equipment, transmission towers, static-filled monitors, "
        "recording devices, control rooms. If the broadcast content describes a "
        "voice, figure, or entity, you may depict it — but ground the scene in "
        "the real equipment and setting first. Horror comes from corrupted signals, "
        "empty studios, unexplained patterns on screens, and the wrongness of "
        "technology behaving in impossible ways."
    ),
    "urban_legends": (
        "This covers URBAN LEGENDS AND THEIR ICONIC SUBJECTS. Depict whatever the "
        "legend is actually about — if the story is about Mothman, show Mothman; "
        "if it's about Spring-Heeled Jack, show Spring-Heeled Jack; if it's about "
        "a haunted location, show the location with its reported phenomena. The "
        "creature or entity IS the subject of the video, so render it boldly and "
        "dramatically. Do NOT substitute generic horror imagery — match the specific "
        "legend. Amplify dread through lighting, environment, and composition, but "
        "the subject itself should be unmistakably what the story describes."
    ),
    "historical_encounters": (
        "This covers HISTORICAL ENCOUNTERS with animals, nature, or strange "
        "phenomena. Depict the actual creatures or phenomena the story describes. "
        "If the story is about a sea serpent sighting, show a sea serpent. If it's "
        "about a plague of rats, show rats. If it's about a mysterious beast, show "
        "the beast as witnesses described it. Stay faithful to what the account "
        "reports — do NOT swap in unrelated monsters or generic zombies. Exaggerate "
        "atmosphere and mood, but keep the subject accurate to the source material."
    ),
    "vanishings_cryptids": (
        "This covers VANISHINGS AND CRYPTID ENCOUNTERS — two sub-types:\n"
        "• VANISHINGS: Keep imagery grounded — real people, real places, the eerie "
        "absence they left behind. Horror comes from what's missing, not from "
        "invented creatures.\n"
        "• CRYPTIDS: The cryptid IS the star of the video. If the story is about "
        "Bigfoot, show Bigfoot. If it's about the Kraken, show the Kraken. If it's "
        "about the Chupacabra, show the Chupacabra. Render the creature as the "
        "story describes it — dramatic, imposing, terrifying. Use atmospheric "
        "lighting and environment to amplify the horror, but do NOT hide the "
        "subject or make it generic. The audience came for THAT creature."
    ),
}

_DEFAULT_GROUNDING = (
    "Derive all visual subjects directly from the narration script. Depict "
    "exactly what the story is about — if it describes a creature, show that "
    "creature; if it describes a real-world event, show realistic imagery. "
    "Do NOT substitute unrelated monsters, zombies, or generic horror imagery "
    "for the actual topic. Every image should be unmistakably about THIS story."
)


def _build_grounding_constraint(category: str | None) -> str:
    """Return the subject-grounding paragraph for the given category."""
    if category and category in _GROUNDING_RULES:
        return _GROUNDING_RULES[category]
    return _DEFAULT_GROUNDING


# ── Prompt templates ──────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = CHUCKY_DIRECTOR_SYSTEM_PROMPT_TEMPLATE
STORYBOARD_PROMPT_TEMPLATE = CHUCKY_DIRECTOR_STORYBOARD_PROMPT_TEMPLATE
subtitles, watermarks, titles, or typography in any form. Describe ONLY \
visual scene elements.

After your scratchpad, output a JSON object with EXACTLY this structure:

{{{{
  "chosen_style": "<dark_comic OR vintage_illustration>",
  "storyboard": [
    {{{{
      "block_id": 1,
      "audio_text": "<narration text from this block, VERBATIM>",
      "visual_prompt": "<SUBJECT, ENVIRONMENT, COMPOSITION, LIGHTING, ATMOSPHERE — then append the style modifier string verbatim>",
      "motion_type": "<ken_burns_zoom_in | ken_burns_pan_right | ken_burns_slow_push | ken_burns_pan_left | kling_i2v_scare>"
    }}}},
    ...
  ]
}}}}

BLOCK-BY-BLOCK GUIDELINES:
- "chosen_style" MUST be the first key in the root JSON — set it to the style \
you selected in your scratchpad.
- One storyboard entry per block_id in the script. Do not skip or merge blocks.
- visual_prompt: Paint a vivid scene using the 6-part structure (Subject, \
Environment, Composition, Lighting, Atmosphere, Style Modifier). Every prompt \
MUST end with the style modifier string copied verbatim from the system \
instructions. Do NOT mention text, captions, or typography anywhere.
- CRITICAL — SUBJECT MUST MATCH NARRATION: The SUBJECT in every visual_prompt \
must be directly extracted from that block's audio_text. Read the narration for \
that block and identify the most visual concrete element — that IS your subject. \
If the narration describes a creature, that creature is the subject. If it \
describes a location, that location is the subject. If it describes a person \
doing something, that person and action is the subject. Never use a generic \
stand-in when the narration gives you a specific subject.
- Do NOT describe visual traits that contradict the VISUAL PHILOSOPHY for your \
chosen style — always re-check the style rules before finalizing prompts.
- All blocks EXCEPT the very last one use a ken_burns motion type. Vary the \
ken_burns type across blocks for visual dynamism.
- The very LAST block uses "kling_i2v_scare" — this is the climactic payoff. \
Design its visual for maximum impact when animated, but keep it animation-safe: \
single clear subject, stable anatomy, no walking/running cycles, no duplicate \
figures, and motion driven by camera move, lighting flicker, atmosphere drift, \
or subtle facial/head motion. The scare lands hardest \
when the viewer has context and emotional investment from the preceding blocks.

Return ONLY the <scratchpad> followed by the JSON object. No other text.
"""


ANIMATION_SAFE_FINAL_SHOT = (
    "Animation-safe final shot: one dominant subject with a clear silhouette, "
    "static or near-static full-body pose, no walking or running, no duplicate "
    "figures, no mirrored twins, stable anatomy, and movement implied through "
    "camera push-in, lighting flicker, drifting fog, or subtle head/eye motion."
)


class VisualTechnicalDirector:
    """Converts narration script into a visual storyboard with image prompts."""

    def __init__(
        self,
        ref_dir: str | Path | None = None,
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

        if ref_dir is None:
            ref_dir = (
                Path(__file__).resolve().parent.parent / "Reference Library"
            )
        self.ref_dir = Path(ref_dir)

    # ── Style helpers ─────────────────────────────────────────────────

    def _resolve_style(self, video_style: str) -> tuple[str, str]:
        """Return (style_modifier, visual_philosophy) for the given style."""
        if video_style not in VALID_STYLES:
            raise ValueError(
                f"Invalid video_style '{video_style}'. "
                f"Must be one of: {', '.join(VALID_STYLES)}"
            )
        modifier = STYLE_MODIFIERS[video_style]
        philosophy = VISUAL_PHILOSOPHIES[video_style]
        return modifier, philosophy

    # ── Style history tracking ────────────────────────────────────────

    @staticmethod
    def _load_style_history() -> list[str]:
        """Load the list of previously chosen styles."""
        if not STYLE_HISTORY_FILE.is_file():
            return []
        try:
            data = json.loads(STYLE_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    @staticmethod
    def _save_style_choice(style: str) -> None:
        """Append style to history file."""
        history = VisualTechnicalDirector._load_style_history()
        history.append(style)
        STYLE_HISTORY_FILE.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Style history updated (%d total): %s", len(history), style)

    def _build_style_nudge(self) -> tuple[str, str]:
        """Pick a style randomly for auto mode and return a matching mandate."""
        chosen = random.choice(VALID_STYLES)
        nudge = (
            f'RANDOM STYLE SELECTION: For this video, the pipeline randomly chose "{chosen}". '
            f'You MUST use "{chosen}" style for this video. This is the active auto-selection '
            f'for variety. Set chosen_style to "{chosen}" and use its style modifier and '
            f'visual philosophy exclusively.'
        )
        logger.info("Random auto-style selected: %s", chosen)
        return nudge, chosen

    # ── Core storyboard function ──────────────────────────────────────

    def create_storyboard(
        self,
        script_json: dict,
        force_style: str | None = None,
        category: str | None = None,
    ) -> dict:
        """Accept script output from Agent 2 and return a visual storyboard.

        The art style is chosen autonomously by Claude based on the
        script's tone and pacing.  The returned dict contains a
        ``chosen_style`` key alongside the ``storyboard`` array.

        If *force_style* is provided (and is in VALID_STYLES), the style
        is locked to that value — Claude's autonomous selection is overridden.
        *category* (e.g. 'real_world_unexplained') adds subject-grounding
        rules so visuals match the topic's reality level.
        """
        if not script_json or "narration_blocks" not in script_json:
            raise ValueError(
                "script_json must contain a 'narration_blocks' key."
            )

        # Auto mode randomly selects one of the two styles unless explicitly overridden.
        style_nudge, mandated_style = self._build_style_nudge()

        # Force-style override (from UI manual mode)
        if force_style and force_style in VALID_STYLES:
            style_nudge = (
                f'MANDATORY: You MUST use "{force_style}" style for this video. '
                f"This is a direct user override — no other style is acceptable."
            )
            mandated_style = force_style
            logger.info("Force-style override active: %s", force_style)

        subject_grounding = _build_grounding_constraint(category)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            dark_comic_modifier=STYLE_MODIFIERS["dark_comic"],
            vintage_illustration_modifier=STYLE_MODIFIERS["vintage_illustration"],
            dark_comic_philosophy=VISUAL_PHILOSOPHIES["dark_comic"],
            vintage_illustration_philosophy=VISUAL_PHILOSOPHIES["vintage_illustration"],
            style_nudge=style_nudge,
            subject_grounding=subject_grounding,
        )

        prompt = STORYBOARD_PROMPT_TEMPLATE.format(
            script_json=json.dumps(script_json, indent=2, ensure_ascii=False),
        )

        message = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = message.content[0].text

        # Response may contain <scratchpad>...</scratchpad> before the JSON.
        json_match = re.search(
            r'\{[\s\S]*"chosen_style"[\s\S]*"storyboard"[\s\S]*\}',
            raw_text,
        )
        json_str = json_match.group() if json_match else raw_text

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Claude returned invalid JSON:\n{raw_text}"
            ) from exc

        if "storyboard" not in result:
            raise RuntimeError(
                f"Claude response missing 'storyboard':\n{raw_text}"
            )

        # Validate and resolve the style Claude chose
        chosen_style = result.get("chosen_style", "")
        if chosen_style not in VALID_STYLES:
            logger.warning(
                "Claude returned invalid chosen_style '%s' — defaulting to 'dark_comic'.",
                chosen_style,
            )
            chosen_style = "dark_comic"
            result["chosen_style"] = chosen_style

        # Hard override: rotation mandate or explicit --style flag
        if mandated_style and mandated_style in VALID_STYLES:
            if chosen_style != mandated_style:
                logger.warning(
                    "Claude ignored style mandate — chose '%s' but '%s' was required. Overriding.",
                    chosen_style, mandated_style,
                )
            chosen_style = mandated_style
            result["chosen_style"] = mandated_style

        style_modifier, _ = self._resolve_style(chosen_style)
        logger.info("Director auto-selected style: %s", chosen_style)

        # Persist style choice for rotation tracking
        self._save_style_choice(chosen_style)

        # Post-process: guarantee style modifier and motion rules
        blocks = result["storyboard"]
        last_idx = len(blocks) - 1
        for i, entry in enumerate(blocks):
            vp = entry.get("visual_prompt", "")

            # Enforce style modifier is present
            if style_modifier not in vp:
                vp = f"{vp.rstrip(', ')}, {style_modifier}"

            entry["visual_prompt"] = vp

            # Enforce motion rules: only the LAST block gets kling_i2v_scare
            is_last = i == last_idx
            if is_last:
                entry["motion_type"] = "kling_i2v_scare"

                # Make the climactic image-to-video shot easier for Kling to animate cleanly.
                if ANIMATION_SAFE_FINAL_SHOT not in vp:
                    if style_modifier in vp:
                        vp = vp.replace(
                            style_modifier,
                            f"{ANIMATION_SAFE_FINAL_SHOT}, {style_modifier}",
                            1,
                        )
                    else:
                        vp = f"{vp.rstrip(', ')}, {ANIMATION_SAFE_FINAL_SHOT}"
                    entry["visual_prompt"] = vp
            elif entry.get("motion_type") == "kling_i2v_scare":
                entry["motion_type"] = "ken_burns_zoom_in"

        return result
