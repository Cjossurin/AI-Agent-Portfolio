"""
Abstract Prompt Templates (Alita)

Production-grade prompt bodies are intentionally excluded from source control.
Populate real prompts from a private .env, secret manager, or database layer.
"""

BASE_ALITA_PROMPT = "Internal proprietary prompt structure for {topic}."

DEFAULT_TEMPLATE = (
    "Internal proprietary prompt structure for {topic}. "
    "Brand voice: {client_voice}. Context: {rag_context}."
)

ALITA_ASSISTANT_SYSTEM_PROMPT = """
Internal proprietary assistant system prompt for Alita.
Use private secure prompt configuration in production.

Required runtime placeholders:
- {connected_platforms_block}
- {date}
- {business_name}
- {knowledge}
- {client_knowledge_block}
- {tone_style_block}
"""

_GENERIC_KEYS = [
    "post_views_engagement",
    "post_follower_growth",
    "post_conversions_sales",
    "caption_views_engagement",
    "caption_follower_growth",
    "caption_conversions_sales",
    "reel_views_engagement",
    "reel_follower_growth",
    "reel_conversions_sales",
    "story_views_engagement",
    "story_follower_growth",
    "story_conversions_sales",
    "article_views_engagement",
    "article_follower_growth",
    "article_conversions_sales",
    "ad_views_engagement",
    "ad_follower_growth",
    "ad_conversions_sales",
]


def _build_platform_templates(platform: str) -> dict:
    return {
        key: (
            f"Internal proprietary prompt structure for {platform} and {key}. "
            "Topic: {topic}. Brand voice: {client_voice}. Context: {rag_context}."
        )
        for key in _GENERIC_KEYS
    }


FACEBOOK_TEMPLATES = _build_platform_templates("facebook")
INSTAGRAM_TEMPLATES = _build_platform_templates("instagram")
LINKEDIN_TEMPLATES = _build_platform_templates("linkedin")
TWITTER_TEMPLATES = _build_platform_templates("twitter")
TIKTOK_TEMPLATES = _build_platform_templates("tiktok")
PINTEREST_TEMPLATES = _build_platform_templates("pinterest")
YOUTUBE_TEMPLATES = _build_platform_templates("youtube")
EMAIL_TEMPLATES = _build_platform_templates("email")
BLOG_TEMPLATES = _build_platform_templates("blog")

PROMPT_TEMPLATES = {
    "facebook": FACEBOOK_TEMPLATES,
    "instagram": INSTAGRAM_TEMPLATES,
    "linkedin": LINKEDIN_TEMPLATES,
    "twitter": TWITTER_TEMPLATES,
    "x": TWITTER_TEMPLATES,
    "tiktok": TIKTOK_TEMPLATES,
    "pinterest": PINTEREST_TEMPLATES,
    "youtube": YOUTUBE_TEMPLATES,
    "email": EMAIL_TEMPLATES,
    "blog": BLOG_TEMPLATES,
    "default": DEFAULT_TEMPLATE,
}


def get_prompt_template(platform: str, content_type: str, goal: str = None) -> str:
    platform = (platform or "default").lower().strip()
    content_type = (content_type or "post").lower().strip()

    if platform in ["x", "twitter/x"]:
        platform = "twitter"

    platform_templates = PROMPT_TEMPLATES.get(platform)
    if platform_templates is None:
        return DEFAULT_TEMPLATE
    if isinstance(platform_templates, str):
        return platform_templates

    template_key = f"{content_type}_{(goal or 'views_engagement').lower().strip()}"
    return platform_templates.get(template_key, DEFAULT_TEMPLATE)


def list_all_templates() -> dict:
    result = {}
    for platform, templates in PROMPT_TEMPLATES.items():
        if platform == "default":
            continue
        if isinstance(templates, dict):
            result[platform] = list(templates.keys())
    return result


def get_template_count() -> dict:
    counts = {}
    total = 0
    for platform, templates in PROMPT_TEMPLATES.items():
        if platform in ("default", "x"):
            continue
        if isinstance(templates, dict):
            counts[platform] = len(templates)
            total += len(templates)
    counts["total"] = total
    return counts
