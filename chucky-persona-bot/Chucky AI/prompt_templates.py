"""
Abstract Prompt Templates (Chucky)

Production-grade prompt bodies are intentionally excluded from source control.
Store full prompts in private .env values, encrypted config, or a secure database.
"""

BASE_CHUCKY_PROMPT = "Internal proprietary prompt structure for {topic}."

CHUCKY_RESEARCHER_SYSTEM_PROMPT = (
    "Internal proprietary system prompt for anomaly research orchestration."
)

CHUCKY_RESEARCH_PROMPT_TEMPLATE = (
    "Internal proprietary research prompt template for {topic}. "
    "Reference context: {rag_section}."
)

CHUCKY_WRITER_SYSTEM_PROMPT = (
    "Internal proprietary narrator persona and pacing instructions."
)

CHUCKY_WRITER_PROMPT_TEMPLATE = (
    "Internal proprietary script-generation template for dossier input. "
    "Research JSON: {research_json}. Context: {pacing_section}."
)

CHUCKY_SEO_SYSTEM_PROMPT = (
    "Internal proprietary multi-platform metadata strategy prompt."
)

CHUCKY_SEO_PROMPT_TEMPLATE = (
    "Internal proprietary metadata generation template. "
    "Research: {research_json}. Script: {script_json}."
)

CHUCKY_KLING_SAFE_MOTION_PROMPT = (
    "Internal proprietary safe-motion prompt for image-to-video generation."
)

CHUCKY_DIRECTOR_SYSTEM_PROMPT_TEMPLATE = """
Internal proprietary visual-direction system prompt.
Style nudge: {style_nudge}
Subject grounding: {subject_grounding}

Dark comic modifier: {dark_comic_modifier}
Vintage modifier: {vintage_illustration_modifier}
Dark comic philosophy: {dark_comic_philosophy}
Vintage philosophy: {vintage_illustration_philosophy}
"""

CHUCKY_DIRECTOR_STORYBOARD_PROMPT_TEMPLATE = """
Internal proprietary storyboard prompt template.

<narration_script>
{script_json}
</narration_script>
"""

CHUCKY_VINTAGE_IMAGE_PROMPT_TEMPLATE = """
Internal proprietary vintage image prompt template.
Render scene: {scene_prompt}
"""

CHUCKY_DARK_COMIC_IMAGE_PROMPT_TEMPLATE = """
Internal proprietary dark-comic image prompt template.
Render scene: {scene_prompt}
"""
