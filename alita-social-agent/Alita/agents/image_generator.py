"""
Image Generator Agent
=====================
Standalone AI image generation agent with multi-API routing and RAG-powered
prompt enhancement.

Supported APIs (with quality-tier routing):
  - BUDGET:   DALL-E 3     ($0.04/image)  fast, reliable
  - STANDARD: Flux via fal.ai ($0.055/image) higher detail
  - PREMIUM:  Midjourney (GoAPI) ($0.08/image) artistic, supports --sref
  - TEXT:     Ideogram     ($0.02/image)  best for flyers, text overlays

RAG System:
  Loads knowledge from Agent RAGs/Image Generation RAG/ at startup to inform
  prompt engineering, platform optimisations, and model selection.

Usage:
    from agents.image_generator import ImageGeneratorAgent, ImageType, ImageQuality

    agent = ImageGeneratorAgent(client_id="demo_client")
    result = await agent.generate_image(
        prompt="A minimal coffee shop at sunrise",
        quality=ImageQuality.PREMIUM,
        platform="instagram_reel",
    )
    print(result.url)
"""

import os
import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class ImageType(Enum):
    """Intended content of the image — drives API selection."""
    TEXT     = "text"     # Flyers, quotes, text-heavy → Ideogram
    ARTISTIC = "artistic" # Photorealistic / high-art   → Midjourney
    GENERAL  = "general"  # Everything else             → DALL-E 3


class ImageQuality(Enum):
    """Quality / cost tier."""
    BUDGET   = "budget"   # DALL-E 3
    STANDARD = "standard" # Flux
    PREMIUM  = "premium"  # Midjourney (--sref support)


# =============================================================================
# DATA CLASS
# =============================================================================

@dataclass
class ImageResult:
    """Result returned from any generate_image call."""
    success: bool
    url: Optional[str] = None
    api_used: Optional[str] = None
    cost_estimate: float = 0.0
    generation_time_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "url": self.url,
            "api_used": self.api_used,
            "cost_estimate": self.cost_estimate,
            "generation_time_seconds": self.generation_time_seconds,
            "metadata": self.metadata,
            "error": self.error,
        }


# =============================================================================
# IMAGE GENERATION RAG
# =============================================================================

class ImageGenerationRAG:
    """
    Loads all .md and .txt knowledge files from
    Agent RAGs/Image Generation RAG/ recursively.

    Provides:
      - get_model_guidance(model)      → best-practice text for a specific API
      - get_platform_guidance(platform)→ platform-specific visual tips
      - get_all_knowledge()            → full concatenated knowledge string
    """

    def __init__(self, rag_dir: Optional[str] = None):
        base = Path(__file__).parent.parent
        self.rag_dir = Path(rag_dir) if rag_dir else base / "Agent RAGs" / "Image Generation RAG"
        self.documents: Dict[str, str] = {}   # relative_path → content
        self._load_all()

    def _load_all(self):
        """Recursively load every .md and .txt file in the RAG directory."""
        if not self.rag_dir.exists():
            logger.warning(f"Image Generation RAG directory not found: {self.rag_dir}")
            return
        count = 0
        for path in sorted(self.rag_dir.rglob("*")):
            if path.suffix.lower() in (".md", ".txt") and path.is_file():
                try:
                    rel = str(path.relative_to(self.rag_dir))
                    self.documents[rel] = path.read_text(encoding="utf-8")
                    count += 1
                except Exception as e:
                    logger.warning(f"Could not load RAG file {path}: {e}")
        logger.info(f"ImageGenerationRAG: loaded {count} knowledge file(s) from {self.rag_dir}")

    def get_model_guidance(self, model: str) -> str:
        """Return combined knowledge for a specific model keyword."""
        model_lower = model.lower()
        matches = []
        for key, content in self.documents.items():
            if model_lower in key.lower():
                matches.append(content)
        return "\n\n".join(matches)

    def get_platform_guidance(self, platform: str) -> str:
        """Return platform-specific visual strategy text."""
        platform_lower = platform.lower().replace(" ", "_").replace("-", "_")
        matches = []
        for key, content in self.documents.items():
            if platform_lower in key.lower():
                matches.append(content)
        return "\n\n".join(matches)

    def get_all_knowledge(self) -> str:
        """Return all loaded knowledge concatenated."""
        return "\n\n---\n\n".join(self.documents.values())

    @property
    def document_count(self) -> int:
        return len(self.documents)


# =============================================================================
# VISUAL REFERENCE CREATIVE STYLE RAG
# =============================================================================

class VisualReferenceRAG:
    """
    Loads technical API knowledge from:
        Agent RAGs/Visual Reference Creative Style RAG/

    Five knowledge domains that inform prompt engineering:
      - dalle3_vision_limits/              → DALL-E prompt char limits, style injection
      - midjourney_style_reference_limits/ → --sref URL limits, --sw ranges (0-1000)
      - flux_api_limits/                   → T5 512-token limit, JSON vs. NL limits
      - video_style_anchoring/             → first-frame anchor best practices
      - imgbb_lifecycle_management/        → file size, expiration format, upload specs
    """

    def __init__(self, rag_dir: Optional[str] = None):
        base = Path(__file__).parent.parent
        self.rag_dir = (
            Path(rag_dir) if rag_dir
            else base / "Agent RAGs" / "Visual Reference Creative Style RAG"
        )
        self.documents: Dict[str, str] = {}
        self._load_all()

    def _load_all(self):
        if not self.rag_dir.exists():
            logger.warning(f"Visual Reference RAG directory not found: {self.rag_dir}")
            return
        count = 0
        for path in sorted(self.rag_dir.rglob("*")):
            if path.suffix.lower() in (".md", ".txt") and path.is_file():
                try:
                    rel = str(path.relative_to(self.rag_dir))
                    self.documents[rel] = path.read_text(encoding="utf-8")
                    count += 1
                except Exception as e:
                    logger.warning(f"Could not load Visual Ref RAG file {path}: {e}")
        logger.info(
            f"VisualReferenceRAG: loaded {count} knowledge file(s) from {self.rag_dir}"
        )

    def _get_domain(self, domain_keyword: str) -> str:
        matches = [
            content for key, content in self.documents.items()
            if domain_keyword.lower() in key.lower()
        ]
        return "\n\n".join(matches)

    def get_midjourney_guidance(self) -> str:
        return self._get_domain("midjourney")

    def get_dalle_guidance(self) -> str:
        return self._get_domain("dalle")

    def get_flux_guidance(self) -> str:
        return self._get_domain("flux")

    def get_imgbb_guidance(self) -> str:
        return self._get_domain("imgbb")

    def get_video_anchoring_guidance(self) -> str:
        return self._get_domain("video_style")

    @property
    def document_count(self) -> int:
        return len(self.documents)


# =============================================================================
# PROMPT TEMPLATES  (Metaprompt-derived, per-API)
# =============================================================================
#
# Each template encodes constraints from the Visual Reference Creative Style RAG:
#
#   DALL-E 3  — max ~4000 chars; text-only style injection (no visual refs via API)
#   Midjourney— --sref: ≤5 URLs, 4096 total chars; --sw: 0-1000, optimal 250-750
#   Flux      — T5 encoder 512 tokens (≈ 2000 chars English); rich NL best
#   ImgBB     — 32 MB Pro limit; expiration=int seconds (min 60, max 15552000)
#   Video     — style_fidelity 0.75-1.3; temporal_coherence 0.85 for consistency
#
# Prompt structure follows the Metaprompt XML pattern:
#   <Inputs>  {$VARIABLE} placeholders
#   <Instructions>  exact directive text injected into API calls

# --- Style extraction system prompt (sent to GPT-4o-mini vision) ---
_STYLE_EXTRACTION_SYSTEM = (
    "You are a visual style analyst for AI image generation. "
    "Analyze the provided reference image(s) and output a single line of "
    "comma-separated style descriptors covering: color palette (specific tones, "
    "saturation, contrast), lighting (quality, direction, mood), rendering style "
    "(photorealistic, cinematic, painterly, digital art, etc.), mood and atmosphere, "
    "and composition tendencies. "
    "Keep output under 120 words. Output ONLY the descriptor string — "
    "no preamble, no labels, no formatting."
)

_STYLE_EXTRACTION_USER = (
    "Analyze the reference image(s) and output a visual style descriptor "
    "suitable for AI image generation prompts."
)

# --- Midjourney style-weight map  (--sw parameter, range 0-1000) ---
# From RAG: default=100, optimal 250-750, overfitting >800
_MJ_SW_MAP: Dict[str, int] = {
    "subtle":   250,   # light style influence; subject driven by text prompt
    "balanced": 500,   # equal weight between --sref and text — recommended default
    "strong":   700,   # style is dominant; reference aesthetic clearly visible
    "override": 850,   # reference nearly fully controls the output aesthetic
}

# --- Video style anchor primer (appended when generating video first-frame) ---
_VIDEO_ANCHOR_PRIMER = (
    "Style-anchored from reference image. Maintain visual consistency: "
    "matching color palette, lighting quality, mood, and aesthetic. "
    "Temporal coherence active. First-frame style anchor."
)


# =============================================================================
# IMAGE GENERATOR AGENT
# =============================================================================

class ImageGeneratorAgent:
    """
    Standalone Image Generator Agent.

    Generates single images on demand using a quality-tier routing system:
      BUDGET  → DALL-E 3  (fast, reliable fallback)
      STANDARD→ Flux       (higher quality)
      PREMIUM → Midjourney (artistic, supports client --sref brand refs)
      TEXT    → Ideogram   (text/flyer accuracy)

    Client reference images are loaded automatically from
    style_references/{client_id}/creative_prefs.json when use_for_images=true.
    """

    def __init__(self, client_id: str = "default_client"):
        self.client_id = client_id

        # API keys
        self.openai_api_key    = os.getenv("OPENAI_API_KEY", "")
        self.fal_api_key       = os.getenv("FAL_API_KEY", "")
        self.ideogram_api_key  = os.getenv("IDEOGRAM_API_KEY", "")
        self.goapi_api_key     = os.getenv("GOAPI_API_KEY", "")

        # Base URLs
        self.openai_base_url   = "https://api.openai.com/v1"
        self.ideogram_base_url = "https://api.ideogram.ai"
        self.goapi_base_url    = "https://api.goapi.ai/mj/v2"

        # Per-API availability flags
        self.apis_available = {
            "dalle":    bool(self.openai_api_key and not self.openai_api_key.startswith("your_")),
            "flux":     bool(self.fal_api_key    and not self.fal_api_key.startswith("your_")),
            "ideogram": bool(self.ideogram_api_key and not self.ideogram_api_key.startswith("your_")),
            "goapi":    bool(self.goapi_api_key  and not self.goapi_api_key.startswith("your_")),
        }

        # Running totals
        self.stats: Dict[str, Any] = {
            "images_generated": 0,
            "total_cost": 0.0,
            "api_calls": {"dalle": 0, "flux": 0, "ideogram": 0, "goapi": 0},
            "errors": 0,
        }

        # RAG systems — load knowledge at startup
        self.rag        = ImageGenerationRAG()
        self.visual_rag = VisualReferenceRAG()

        logger.info(
            f"ImageGeneratorAgent ready | client={client_id} | "
            f"APIs={[k for k,v in self.apis_available.items() if v]} | "
            f"GenRAG={self.rag.document_count} docs | "
            f"VisualRAG={self.visual_rag.document_count} docs"
        )

    # -------------------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # -------------------------------------------------------------------------

    async def generate_image(
        self,
        prompt: str,
        image_type: ImageType = ImageType.GENERAL,
        size: str = "1080x1080",
        platform: Optional[str] = None,
        style: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        quality: ImageQuality = ImageQuality.BUDGET,
        reference_images: Optional[List[str]] = None,
        use_client_references: bool = True,
    ) -> ImageResult:
        """
        Generate a single image.

        Args:
            prompt:               Main prompt describing the desired image.
            image_type:           TEXT / ARTISTIC / GENERAL — affects API routing.
            size:                 "WxH" string, e.g. "1080x1080", "1080x1920".
            platform:             Optional platform hint for RAG-enhanced prompts
                                  (e.g. "instagram_reel", "tiktok").
            style:                Optional extra style descriptor appended to prompt.
            negative_prompt:      Things to avoid. Defaults to faceless guidance.
            quality:              BUDGET / STANDARD / PREMIUM tier.
            reference_images:     Explicit list of image URLs to use as style refs.
            use_client_references:If True, auto-loads client brand ref images from
                                  style_references/{client_id}/creative_prefs.json
                                  when use_for_images toggle is ON.

        Returns:
            ImageResult with .url and metadata.
        """
        # ── Plan gate: check images_created quota + tier quality cap ──────
        try:
            from database.db import SessionLocal as _SL_img
            from database.models import ClientProfile as _CP_img
            from utils.plan_limits import check_limit as _chk, increment_usage as _inc
            from utils.ai_config import cap_image_quality as _cap_q
            _db_img = _SL_img()
            _prof = _db_img.query(_CP_img).filter(_CP_img.client_id == self.client_id).first()
            if _prof:
                _ok, _msg = _chk(_prof, "images_created")
                if not _ok:
                    _db_img.close()
                    return ImageResult(success=False, error=_msg, metadata={"blocked_by": "plan_limit"})
                # Cap quality to what the user's plan tier allows
                _tier = getattr(_prof, "plan_tier", "pro") or "pro"
                quality = _cap_q(quality, _tier)
            _db_img.close()
        except Exception as _e:
            logger.warning(f"Image plan-limit check failed: {_e}")

        start = datetime.now()

        # 1. Gather reference images
        refs = list(reference_images or [])
        if use_client_references and not refs:
            refs = self._load_client_reference_images()

        # 2. Extract visual style descriptor from reference images (STANDARD+ quality)
        style_descriptor = ""
        if refs and quality != ImageQuality.BUDGET and self.apis_available["dalle"]:
            style_descriptor = await self._extract_style_descriptor(refs)

        # 3. Build generic enhanced prompt (fallback / Ideogram)
        enhanced = self._build_prompt(prompt, style, platform, refs)

        # 4. Default negative prompt
        if not negative_prompt:
            negative_prompt = (
                "human faces, people faces, portraits, selfies, identifiable people, "
                "text, words, letters, numbers, watermarks, labels, titles, captions, "
                "typography, writing, signs, logos with text"
            )

        logger.info(
            f"Generating image | quality={quality.value} type={image_type.value} "
            f"size={size} refs={len(refs)} style_extracted={bool(style_descriptor)}"
        )

        # 5. Route to API with model-specific prompts
        result = await self._route(
            prompt, style, platform, enhanced,
            image_type, size, negative_prompt, quality, refs, style_descriptor,
        )

        # 5. Attach timing + metadata
        elapsed = (datetime.now() - start).total_seconds()
        result.generation_time_seconds = elapsed
        result.metadata.update({
            "original_prompt": prompt,
            "image_type": image_type.value,
            "quality": quality.value,
            "platform": platform,
            "reference_images_used": len(refs),
        })

        if result.success:
            self.stats["images_generated"] += 1
            # ── Increment images_created usage counter ──
            try:
                from database.db import SessionLocal as _SL_img2
                from database.models import ClientProfile as _CP_img2
                from utils.plan_limits import increment_usage as _inc2
                _db2 = _SL_img2()
                _p2 = _db2.query(_CP_img2).filter(_CP_img2.client_id == self.client_id).first()
                if _p2:
                    _inc2(_p2, "images_created", _db2)
                _db2.close()
            except Exception:
                pass
        else:
            self.stats["errors"] += 1

        return result

    # -------------------------------------------------------------------------
    # ROUTING
    # -------------------------------------------------------------------------

    async def _route(
        self,
        raw_prompt: str,
        style: Optional[str],
        platform: Optional[str],
        enhanced_prompt: str,
        image_type: ImageType,
        size: str,
        negative_prompt: str,
        quality: ImageQuality,
        reference_images: List[str],
        style_descriptor: str = "",
    ) -> ImageResult:
        """
        Route to the correct API and build model-specific prompts.

        Inputs:
          {$RAW_PROMPT}        — original unmodified user prompt
          {$STYLE_DESCRIPTOR}  — extracted from reference images via GPT-4o vision
          {$ENHANCED_PROMPT}   — generic prompt for fallback/Ideogram use

        Each API receives a prompt built for its specific encoder constraints:
          DALL-E  → _build_dalle_prompt()      (max 4000 chars, text-only style injection)
          Flux    → _build_flux_prompt()       (max 2000 chars for T5 512-token encoder)
          MJ/GoAPI→ _build_midjourney_text() + _build_midjourney_flags() (--sref + --sw)
        """
        # Build model-specific prompts from raw context
        dalle_prompt = self._build_dalle_prompt(raw_prompt, style, platform, style_descriptor)
        flux_prompt  = self._build_flux_prompt(raw_prompt, style, platform, style_descriptor)
        mj_text      = self._build_midjourney_text(raw_prompt, style, platform, style_descriptor)

        if quality == ImageQuality.PREMIUM:
            result = await self._generate_with_goapi(mj_text, size, negative_prompt, reference_images)
            if not result.success and self.apis_available["flux"]:
                result = await self._generate_with_flux(flux_prompt, size)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(dalle_prompt, size)

        elif quality == ImageQuality.STANDARD:
            result = await self._generate_with_flux(flux_prompt, size)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(dalle_prompt, size)

        elif image_type == ImageType.TEXT:
            result = await self._generate_with_ideogram(enhanced_prompt, size, negative_prompt)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(dalle_prompt, size)

        else:
            # BUDGET / GENERAL default
            result = await self._generate_with_dalle(dalle_prompt, size)
            if not result.success and self.apis_available["flux"]:
                result = await self._generate_with_flux(flux_prompt, size)

        return result

    # -------------------------------------------------------------------------
    # PROMPT BUILDERS  (model-aware)
    # -------------------------------------------------------------------------

    def _build_dalle_prompt(
        self,
        base_prompt: str,
        style: Optional[str],
        platform: Optional[str],
        style_descriptor: str = "",
    ) -> str:
        """
        Build DALL-E 3 prompt with visual-reference style injection.

        Inputs:
          {$BASE_PROMPT}       — core creative brief
          {$STYLE_DESCRIPTOR}  — extracted from reference images via GPT-4o vision
          {$PLATFORM}          — optional platform context hint

        Constraints (from Visual Reference Creative Style RAG):
          - DALL-E 3 hard limit: ~4000 chars
          - No visual reference attachment supported — style injected as text
          - Style descriptor from _extract_style_descriptor() replaces generic style
        """
        parts = [base_prompt]
        parts.append(
            "NO human faces, faceless, abstract human silhouettes only if people needed. "
            "CRITICAL: Do NOT include any text, words, letters, numbers, watermarks, "
            "labels, titles, captions, or typography anywhere in the image. "
            "The image must be purely visual with zero readable text."
        )

        if style_descriptor:
            parts.append(f"Visual reference style: {style_descriptor}")
        elif style:
            parts.append(f"Style: {style}")

        if platform:
            guidance = self.rag.get_platform_guidance(platform)
            if guidance:
                snippet = guidance[:150].strip().replace("\n", " ")
                parts.append(f"Platform: {snippet}")

        parts.append(
            "photorealistic quality, sharp focus, professional composition, high detail"
        )

        result = ". ".join(p.strip(".").strip() for p in parts if p)
        return result[:4000]  # DALL-E 3 hard cap

    def _build_flux_prompt(
        self,
        base_prompt: str,
        style: Optional[str],
        platform: Optional[str],
        style_descriptor: str = "",
    ) -> str:
        """
        Build Flux (fal.ai) prompt optimized for the T5 encoder.

        Inputs:
          {$BASE_PROMPT}       — core creative brief
          {$STYLE_DESCRIPTOR}  — extracted from reference images
          {$PLATFORM}          — optional platform hint

        Constraints (from Visual Reference Creative Style RAG):
          - T5 encoder: 512 token maximum (≈ 2000 chars of English)
          - Rich, dense natural language outperforms keyword stuffing
          - No explicit style_weight param on fal.ai /dev — inject via prompt text
        """
        parts = [base_prompt]
        parts.append(
            "NO human faces, faceless. "
            "CRITICAL: Do NOT include any text, words, letters, numbers, watermarks, "
            "labels, titles, or typography in the image. Purely visual, zero readable text."
        )

        if style_descriptor:
            parts.append(style_descriptor[:180])  # keep compact — tokens are precious
        elif style:
            parts.append(style)

        if platform:
            guidance = self.rag.get_platform_guidance(platform)
            if guidance:
                snippet = guidance[:100].strip().replace("\n", " ")
                parts.append(snippet)

        parts.append(
            "cinematic composition, professional photography, sharp focus, high detail"
        )

        result = ", ".join(p.strip(",").strip() for p in parts if p)
        return result[:2000]  # T5 encoder ≈512 tokens ≈2000 chars

    def _build_midjourney_text(
        self,
        base_prompt: str,
        style: Optional[str],
        platform: Optional[str],
        style_descriptor: str = "",
    ) -> str:
        """
        Build the text portion of a Midjourney prompt (flags added separately).

        Inputs:
          {$BASE_PROMPT}       — core creative brief
          {$STYLE_DESCRIPTOR}  — compact style hint (when no --sref available)
          {$PLATFORM}          — optional platform hint

        Constraints (from Visual Reference Creative Style RAG):
          - Total MJ prompt (text + flags) max 6000 chars
          - Keep text portion under 5000 to leave room for --sref + other flags
          - When --sref is active, style comes from the visual ref, not text
        """
        parts = [base_prompt]
        parts.append("NO human faces, faceless. No text, no words, no letters, no typography in the image.")

        # When --sref is active, style is injected visually — keep text compact
        if style_descriptor and len(style_descriptor) < 120:
            parts.append(style_descriptor)
        elif style and not style_descriptor:
            parts.append(style)

        if platform:
            platform_hint = platform.replace("_", " ").replace("-", " ")
            parts.append(f"optimized for {platform_hint}")

        result = ", ".join(p.strip(",").strip() for p in parts if p)
        return result[:5000]

    def _build_midjourney_flags(
        self,
        reference_images: List[str],
        style_strength: str = "balanced",
        ar: str = "1:1",
        negative_prompt: str = "",
        version: str = "6.1",
    ) -> str:
        """
        Build Midjourney CLI flags string with RAG-informed --sw weighting.

        Inputs:
          {$REFERENCE_IMAGES}  — list of public image URLs for --sref
          {$STYLE_STRENGTH}    — subtle / balanced / strong / override
          {$AR}                — aspect ratio string e.g. "16:9"
          {$NEGATIVE_PROMPT}   — concepts to exclude via --no

        Constraints (from Visual Reference Creative Style RAG):
          - --sref accepts 1–5 URLs; combined URL string ≤ 4096 chars
          - --sw range: 0–1000, default 100, optimal 250–750, overfitting > 800
            subtle=250 / balanced=500 / strong=700 / override=850
          - URL weighting via ::weight suffix (e.g. url::0.7) is supported
        """
        flags = [f"--ar {ar}", f"--v {version}"]

        if negative_prompt:
            flags.append(f"--no {negative_prompt}")

        if reference_images:
            urls = list(reference_images[:5])  # hard cap at 5
            # Enforce 4096-char combined URL budget
            while urls and sum(len(u) + 8 for u in urls) > 4000:
                urls = urls[:-1]

            if urls:
                sw = _MJ_SW_MAP.get(style_strength, _MJ_SW_MAP["balanced"])
                sref_str = " ".join(f"--sref {u}" for u in urls)
                flags.append(f"{sref_str} --sw {sw}")

        return " " + " ".join(flags)

    def _build_prompt(
        self,
        base_prompt: str,
        style: Optional[str],
        platform: Optional[str],
        reference_images: List[str],
    ) -> str:
        """
        Generic prompt builder — used as fallback for Ideogram and legacy callers.

        For model-specific prompt engineering, use:
          _build_dalle_prompt()      → DALL-E 3 (text-only style injection)
          _build_flux_prompt()       → Flux / fal.ai (T5 encoder aware)
          _build_midjourney_text()   → Midjourney text portion (--sref flags separate)
        """
        parts = [base_prompt]
        parts.append(
            "NO human faces, faceless, abstract human silhouettes only if people are needed. "
            "CRITICAL: Do NOT include any text, words, letters, numbers, watermarks, "
            "labels, titles, or typography in the image. Purely visual, zero readable text."
        )

        if style:
            parts.append(f"Style: {style}")

        if platform:
            guidance = self.rag.get_platform_guidance(platform)
            if guidance:
                snippet = guidance[:200].strip().replace("\n", " ")
                parts.append(f"Platform context: {snippet}")

        if reference_images:
            parts.append(
                "maintain visual consistency with brand reference style: "
                "matching color palette, mood, lighting, and aesthetic"
            )

        return ". ".join(p.strip(".").strip() for p in parts if p)

    # -------------------------------------------------------------------------
    # STYLE EXTRACTION  (GPT-4o-mini vision)
    # -------------------------------------------------------------------------

    async def _extract_style_descriptor(self, reference_images: List[str]) -> str:
        """
        Use GPT-4o-mini vision to extract a dense style descriptor from reference images.

        Inputs:
          {$REFERENCE_IMAGES}  — list of public image URLs (up to 3 analyzed)

        Output:
          Single-line comma-separated style descriptor suitable for injection into
          DALL-E 3, Flux, and Midjourney text prompts.

        Token cost: ~150-250 tokens per call (low detail mode, gpt-4o-mini).
        Returns empty string on failure — callers fall back to generic style text.
        """
        if not self.apis_available["dalle"] or not reference_images:
            return ""

        try:
            content: List[Dict[str, Any]] = [
                {"type": "text", "text": _STYLE_EXTRACTION_USER}
            ]
            for url in reference_images[:3]:  # cap at 3 for token efficiency
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url, "detail": "low"},  # low = fewer tokens
                })

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.openai_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": _STYLE_EXTRACTION_SYSTEM},
                            {"role": "user",   "content": content},
                        ],
                        "max_tokens": 200,
                        "temperature": 0.3,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        descriptor = data["choices"][0]["message"]["content"].strip()
                        logger.info(f"Style extracted from refs: {descriptor[:80]}...")
                        return descriptor
                    else:
                        logger.warning(f"Style extraction failed: {response.status}")
                        return ""
        except Exception as e:
            logger.warning(f"Style extraction exception: {e}")
            return ""

    # -------------------------------------------------------------------------
    # CLIENT REFERENCE IMAGES
    # -------------------------------------------------------------------------

    def _load_client_reference_images(self) -> List[str]:
        """
        Load the client's brand reference image URLs.
        Priority: PostgreSQL → style_references/{client_id}/creative_prefs.json.
        """
        # 1. Try PostgreSQL (survives Railway redeploys)
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            _db = SessionLocal()
            try:
                _prof = _db.query(_CP).filter(_CP.client_id == self.client_id).first()
                if _prof and getattr(_prof, "creative_preferences_json", None):
                    prefs = json.loads(_prof.creative_preferences_json)
                    if not prefs.get("use_for_images", False):
                        return []
                    return [img["url"] for img in prefs.get("reference_images", []) if img.get("url")]
            finally:
                _db.close()
        except Exception:
            pass
        # 2. File fallback
        prefs_path = Path("style_references") / self.client_id / "creative_prefs.json"
        if not prefs_path.exists():
            return []
        try:
            with open(prefs_path, encoding="utf-8") as f:
                prefs = json.load(f)
            if not prefs.get("use_for_images", False):
                return []
            return [img["url"] for img in prefs.get("reference_images", []) if img.get("url")]
        except Exception as e:
            logger.warning(f"Could not load client reference images: {e}")
            return []

    # -------------------------------------------------------------------------
    # API IMPLEMENTATIONS
    # -------------------------------------------------------------------------

    async def _generate_with_dalle(self, prompt: str, size: str) -> ImageResult:
        """Generate image using DALL-E 3 (OpenAI)."""
        if not self.apis_available["dalle"]:
            return ImageResult(success=False, error="OpenAI API not configured")

        try:
            width, height = map(int, size.split("x"))
            if width == height:
                dalle_size = "1024x1024"
            elif width > height:
                dalle_size = "1792x1024"
            else:
                dalle_size = "1024x1792"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.openai_base_url}/images/generations",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "dall-e-3",
                        "prompt": prompt,
                        "n": 1,
                        "size": dalle_size,
                        "quality": "standard",
                        "style": "vivid",
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        image_url = data.get("data", [{}])[0].get("url")
                        revised   = data.get("data", [{}])[0].get("revised_prompt")
                        self.stats["api_calls"]["dalle"] += 1
                        self.stats["total_cost"] += 0.04
                        return ImageResult(
                            success=True,
                            url=image_url,
                            api_used="dalle3",
                            cost_estimate=0.04,
                            metadata={"dall_e_size": dalle_size, "revised_prompt": revised},
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"DALL-E failed {response.status}: {error_text}")
                        return ImageResult(success=False, error=f"DALL-E error {response.status}")
        except Exception as e:
            logger.error(f"DALL-E exception: {e}")
            return ImageResult(success=False, error=str(e))

    async def _generate_with_flux(self, prompt: str, size: str) -> ImageResult:
        """Generate image using Flux via fal.ai."""
        if not self.apis_available["flux"]:
            return ImageResult(success=False, error="fal.ai API not configured")

        try:
            width, height = map(int, size.split("x"))
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://fal.run/fal-ai/flux/dev",
                    headers={
                        "Authorization": f"Key {self.fal_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "prompt": prompt,
                        "image_size": {"width": width, "height": height},
                        "num_inference_steps": 28,
                        "guidance_scale": 3.5,
                        "num_images": 1,
                        "enable_safety_checker": False,
                    },
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status in (200, 201):
                        data = await response.json()
                        image_url = data.get("images", [{}])[0].get("url")
                        if image_url:
                            self.stats["api_calls"]["flux"] += 1
                            self.stats["total_cost"] += 0.055
                            return ImageResult(
                                success=True,
                                url=image_url,
                                api_used="flux_dev",
                                cost_estimate=0.055,
                                metadata={"size": size, "steps": 28},
                            )
                        return ImageResult(success=False, error="Flux returned no image URL")
                    else:
                        error_text = await response.text()
                        logger.error(f"Flux failed {response.status}: {error_text}")
                        return ImageResult(success=False, error=f"Flux error {response.status}")
        except Exception as e:
            logger.error(f"Flux exception: {e}")
            return ImageResult(success=False, error=str(e))

    async def _generate_with_ideogram(
        self, prompt: str, size: str, negative_prompt: str
    ) -> ImageResult:
        """Generate image using Ideogram (best for text content)."""
        if not self.apis_available["ideogram"]:
            return ImageResult(success=False, error="Ideogram API not configured")

        try:
            width, height = map(int, size.split("x"))
            if width == height:
                aspect = "ASPECT_1_1"
            elif width > height:
                aspect = "ASPECT_16_9"
            else:
                aspect = "ASPECT_9_16"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ideogram_base_url}/generate",
                    headers={
                        "Api-Key": self.ideogram_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "image_request": {
                            "prompt": prompt,
                            "aspect_ratio": aspect,
                            "model": "V_2",
                            "magic_prompt_option": "AUTO",
                            "negative_prompt": negative_prompt,
                        }
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        image_url = data.get("data", [{}])[0].get("url")
                        self.stats["api_calls"]["ideogram"] += 1
                        self.stats["total_cost"] += 0.02
                        return ImageResult(
                            success=True,
                            url=image_url,
                            api_used="ideogram",
                            cost_estimate=0.02,
                            metadata={"aspect": aspect},
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"Ideogram failed {response.status}: {error_text}")
                        return ImageResult(success=False, error=f"Ideogram error {response.status}")
        except Exception as e:
            logger.error(f"Ideogram exception: {e}")
            return ImageResult(success=False, error=str(e))

    async def _generate_with_goapi(
        self,
        prompt: str,
        size: str,
        negative_prompt: str,
        reference_images: Optional[List[str]] = None,
    ) -> ImageResult:
        """Generate image using GoAPI (Midjourney) with optional --sref brand refs."""
        if not self.apis_available["goapi"]:
            return ImageResult(success=False, error="GoAPI not configured")

        try:
            width, height = map(int, size.split("x"))
            if width == height:
                ar = "1:1"
            elif width > height:
                ar = "16:9"
            else:
                ar = "9:16"

            # Build smart Midjourney flags (--sref + --sw from Visual Reference RAG)
            # --sw optimal range: 250-750; balanced=500 per RAG knowledge
            flags = self._build_midjourney_flags(
                reference_images=reference_images or [],
                style_strength="balanced",   # --sw 500 (optimal per RAG)
                ar=ar,
                negative_prompt=negative_prompt,
                version="6.1",
            )
            mj_prompt = f"{prompt}{flags}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.goapi_base_url}/imagine",
                    headers={
                        "X-API-Key": self.goapi_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "prompt": mj_prompt,
                        "process_mode": "fast",
                        "webhook_endpoint": "",
                        "webhook_secret": "",
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        task_id = data.get("task_id")
                        image_url = await self._goapi_poll_status(task_id)
                        if image_url:
                            self.stats["api_calls"]["goapi"] += 1
                            self.stats["total_cost"] += 0.05
                            return ImageResult(
                                success=True,
                                url=image_url,
                                api_used="goapi_midjourney",
                                cost_estimate=0.05,
                                metadata={"aspect_ratio": ar, "sref_count": len(reference_images or [])},
                            )
                        return ImageResult(success=False, error="GoAPI generation timed out")
                    else:
                        error_text = await response.text()
                        logger.error(f"GoAPI failed {response.status}: {error_text}")
                        return ImageResult(success=False, error=f"GoAPI error {response.status}")
        except Exception as e:
            logger.error(f"GoAPI exception: {e}")
            return ImageResult(success=False, error=str(e))

    async def _goapi_poll_status(
        self,
        task_id: str,
        timeout_seconds: int = 120,
        poll_interval: int = 5,
    ) -> Optional[str]:
        """Poll GoAPI until the Midjourney task finishes."""
        try:
            async with aiohttp.ClientSession() as session:
                elapsed = 0
                while elapsed < timeout_seconds:
                    async with session.post(
                        f"{self.goapi_base_url}/fetch",
                        headers={
                            "X-API-Key": self.goapi_api_key,
                            "Content-Type": "application/json",
                        },
                        json={"task_id": task_id},
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            status = data.get("status")
                            if status == "finished":
                                task_result = data.get("task_result", {})
                                return (
                                    task_result.get("image_url")
                                    or task_result.get("discord_image_url")
                                )
                            elif status == "failed":
                                logger.error(f"GoAPI task failed: {data}")
                                return None
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
            return None
        except Exception as e:
            logger.error(f"GoAPI poll exception: {e}")
            return None

    # -------------------------------------------------------------------------
    # UTILITIES
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return self.stats.copy()

    def get_rag_summary(self) -> Dict[str, Any]:
        return {
            "image_gen_rag": {
                "document_count": self.rag.document_count,
                "rag_dir": str(self.rag.rag_dir),
                "documents": list(self.rag.documents.keys()),
            },
            "visual_ref_rag": {
                "document_count": self.visual_rag.document_count,
                "rag_dir": str(self.visual_rag.rag_dir),
                "documents": list(self.visual_rag.documents.keys()),
            },
        }


# =============================================================================
# MODULE-LEVEL SINGLETON HELPER
# =============================================================================

_instance: Optional[ImageGeneratorAgent] = None

def get_image_generator(client_id: str = "default_client") -> ImageGeneratorAgent:
    """Return a cached ImageGeneratorAgent instance for the given client."""
    global _instance
    if _instance is None or _instance.client_id != client_id:
        _instance = ImageGeneratorAgent(client_id=client_id)
    return _instance
