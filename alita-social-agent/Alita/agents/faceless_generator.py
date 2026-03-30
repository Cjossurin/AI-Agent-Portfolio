"""
Faceless Video & Image Generator Agent
======================================
Generates faceless videos and images for social media content using a 3-tier system.

VIDEO GENERATION TIERS:
  - Tier 1: Stock Video (Pexels/Pixabay) - Real footage, FREE
  - Tier 2: Generated Images + Ken Burns - Unique visuals, zoom/pan effects
  - Tier 3: AI Animation (Kling/Wan via fal.ai) - AI-animated images

IMAGE GENERATION:
  - Ideogram: Best for text/flyers
  - GoAPI (Midjourney): Artistic quality
  - DALL-E 3: General backup

VOICEOVER:
  - ElevenLabs: AI voice generation with timestamps

Integrates with:
- Marketing Intelligence Agent (auto-generate media for content ideas)
- Content Creation Agent (auto-request media for posts)
- Content Calendar Agent (batch generation for scheduled posts)
"""

import os
import asyncio
import aiohttp
import json
import logging
import subprocess
import tempfile
import shutil
import re
from typing import Dict, Any, Optional, List, Literal, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Import RAG system for video type specifications
try:
    from agents.faceless_rag import FacelessRAG, get_faceless_rag
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("FacelessRAG not available - video type optimization disabled")

# Import Style Loader for deep research prompts
try:
    from agents.faceless_style_loader import (
        FacelessStyleLoader, 
        FacelessStyle, 
        list_available_styles,
        get_category_display_name,
        CATEGORY_DISPLAY_NAMES
    )
    STYLE_LOADER_AVAILABLE = True
except ImportError:
    STYLE_LOADER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("FacelessStyleLoader not available - deep research prompts disabled")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VideoTier(Enum):
    """Video generation tiers."""
    STOCK_VIDEO = "stock_video"       # Tier 1: Real Pexels/Pixabay footage
    GENERATED_IMAGES = "generated"    # Tier 2: AI images + Ken Burns
    AI_ANIMATION = "ai_animation"     # Tier 3: AI-animated images (Kling/Wan)


class ImageType(Enum):
    """Types of images that can be generated."""
    TEXT = "text"           # Flyers, quotes, text-heavy graphics → Ideogram
    ARTISTIC = "artistic"   # High-quality artistic/photorealistic → GoAPI (Midjourney)
    GENERAL = "general"     # General purpose images → DALL-E 3


class ImageQuality(Enum):
    """Quality tiers for Tier 2 (Generated Images) videos."""
    BUDGET = "budget"       # DALL-E 3: $0.04/image, fast
    STANDARD = "standard"   # Flux: $0.055/image, better quality
    PREMIUM = "premium"     # Midjourney: $0.08/image, highest quality


class VideoStyle(Enum):
    """Video styles for generation."""
    ENERGETIC = "energetic"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    EDUCATIONAL = "educational"
    STORYTELLING = "storytelling"


class VideoType(Enum):
    """
    Faceless video content types with specific production requirements.
    Each type has optimized settings for pacing, audio, visuals, and voice.
    """
    # Horror & Dark
    HORROR_STORYTELLING = "horror_storytelling"
    TRUE_CRIME = "true_crime"
    ICEBERG_EXPLAINER = "iceberg_explainer"
    TWO_SENTENCE_HORROR = "two_sentence_horror"
    
    # Storytelling
    REDDIT_STORIES = "reddit_stories"
    AFRICAN_FOLKTALES = "african_folktales"
    
    # Educational
    EDUCATIONAL_EXPLAINER = "educational_explainer"
    BOOK_SUMMARY = "book_summary"
    FINANCE_BUSINESS = "finance_business"
    QUICK_FACTS = "quick_facts"
    TOP_10_COUNTDOWN = "top_10_countdown"
    SPACE_COSMIC = "space_cosmic"
    
    # Motivation
    MOTIVATIONAL = "motivational"
    STOICISM_MOTIVATION = "stoicism_motivation"
    SELF_HELP = "self_help"
    DARK_PSYCHOLOGY = "dark_psychology"
    
    # Lifestyle
    ASMR_RELAXATION = "asmr_relaxation"
    COOKING_RECIPE = "cooking_recipe"
    SILENT_AESTHETIC_VLOG = "silent_aesthetic_vlog"
    OLD_MONEY_LUXURY = "old_money_luxury"
    
    # Tech
    AI_TOOLS_TUTORIAL = "ai_tools_tutorial"
    
    # Default/Generic
    GENERAL = "general"


class AspectRatio(Enum):
    """Supported aspect ratios for video/image generation."""
    PORTRAIT = "9:16"       # Instagram Reels, TikTok, Stories
    LANDSCAPE = "16:9"      # YouTube, Facebook
    SQUARE = "1:1"          # Instagram Feed, Facebook


class Platform(Enum):
    """Supported social media platforms."""
    INSTAGRAM_REEL = "instagram_reel"
    INSTAGRAM_STORY = "instagram_story"
    INSTAGRAM_FEED = "instagram_feed"
    TIKTOK = "tiktok"
    YOUTUBE_SHORT = "youtube_short"
    YOUTUBE = "youtube"
    FACEBOOK_STORY = "facebook_story"
    FACEBOOK_FEED = "facebook_feed"


# Platform to aspect ratio mapping
PLATFORM_ASPECT_RATIOS = {
    Platform.INSTAGRAM_REEL: AspectRatio.PORTRAIT,
    Platform.INSTAGRAM_STORY: AspectRatio.PORTRAIT,
    Platform.INSTAGRAM_FEED: AspectRatio.SQUARE,
    Platform.TIKTOK: AspectRatio.PORTRAIT,
    Platform.YOUTUBE_SHORT: AspectRatio.PORTRAIT,
    Platform.YOUTUBE: AspectRatio.LANDSCAPE,
    Platform.FACEBOOK_STORY: AspectRatio.PORTRAIT,
    Platform.FACEBOOK_FEED: AspectRatio.LANDSCAPE,
}


@dataclass
class GeneratedMedia:
    """Result of media generation."""
    success: bool
    media_type: str  # "video" or "image"
    url: Optional[str] = None
    local_path: Optional[str] = None
    api_used: Optional[str] = None
    tier_used: Optional[str] = None
    generation_time_seconds: float = 0.0
    cost_estimate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "media_type": self.media_type,
            "url": self.url,
            "local_path": self.local_path,
            "api_used": self.api_used,
            "tier_used": self.tier_used,
            "generation_time_seconds": self.generation_time_seconds,
            "cost_estimate": self.cost_estimate,
            "metadata": self.metadata,
            "error": self.error
        }


@dataclass
class ContentIdea:
    """Content idea from Marketing Intelligence Agent."""
    topic: str
    angle: str
    hooks: List[str]
    platform: Platform
    content_type: str  # "video", "image", "carousel"
    niche: Optional[str] = None
    target_audience: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Reference Image Helpers (client creative style settings)
# ─────────────────────────────────────────────────────────────────────────────

def get_client_reference_images(client_id: str, mode: str = "images") -> List[str]:
    """
    Load reference image URLs for a client, respecting their per-mode toggle.

    Args:
        client_id: Client's slug ID (e.g. "cool_cruise_co")
        mode: "images" to check use_for_images toggle,
              "videos" to check use_for_videos toggle

    Returns:
        List of public image URLs (empty list if disabled or no images).
    """
    from pathlib import Path as _Path
    import json as _json

    # 1. Try PostgreSQL (survives Railway redeploys)
    try:
        from database.db import SessionLocal
        from database.models import ClientProfile as _CP
        _db = SessionLocal()
        try:
            _prof = _db.query(_CP).filter(_CP.client_id == client_id).first()
            if _prof and getattr(_prof, "creative_preferences_json", None):
                prefs = _json.loads(_prof.creative_preferences_json)
                toggle_key = "use_for_images" if mode == "images" else "use_for_videos"
                if not prefs.get(toggle_key, False):
                    return []
                return [img["url"] for img in prefs.get("reference_images", []) if img.get("url")]
        finally:
            _db.close()
    except Exception:
        pass

    # 2. File fallback
    prefs_path = _Path("style_references") / client_id / "creative_prefs.json"
    if not prefs_path.exists():
        return []
    try:
        with open(prefs_path) as _f:
            prefs = _json.load(_f)
        toggle_key = "use_for_images" if mode == "images" else "use_for_videos"
        if not prefs.get(toggle_key, False):
            return []
        return [img["url"] for img in prefs.get("reference_images", []) if img.get("url")]
    except Exception:
        return []


class FacelessGenerator:
    """
    Faceless Video & Image Generator Agent.
    
    3-Tier Video Generation:
    - Tier 1: Stock Video (Pexels/Pixabay) - FREE real footage
    - Tier 2: Generated Images + Ken Burns - Unique AI visuals with zoom/pan
    - Tier 3: AI Animation (Kling/Wan) - AI-animated images with motion
    
    Image Generation:
    - Ideogram: Text-accurate images (flyers, quotes)
    - GoAPI (Midjourney): High-quality artistic images
    - DALL-E 3: General purpose images
    """
    
    def __init__(self, client_id: str = "default_client"):
        """Initialize the Faceless Generator with API credentials."""
        self.client_id = client_id
        
        # Stock Video APIs (Tier 1)
        self.pexels_api_key = os.getenv("PEXELS_API_KEY")
        self.pixabay_api_key = os.getenv("PIXABAY_API_KEY")
        
        # Voiceover API
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        
        # AI Animation API (Tier 3)
        self.fal_api_key = os.getenv("FAL_API_KEY")
        
        # Image Generation APIs (Tier 2)
        self.ideogram_api_key = os.getenv("IDEOGRAM_API_KEY")
        self.goapi_api_key = os.getenv("GOAPI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # API Endpoints
        self.pexels_base_url = "https://api.pexels.com/videos"
        self.pixabay_base_url = "https://pixabay.com/api/videos"
        self.elevenlabs_base_url = "https://api.elevenlabs.io/v1"
        self.fal_base_url = "https://queue.fal.run"
        self.ideogram_base_url = "https://api.ideogram.ai"
        self.goapi_base_url = "https://api.goapi.ai/mj/v2"
        self.openai_base_url = "https://api.openai.com/v1"
        
        # Temp directory for video assembly
        self.temp_dir = Path(tempfile.gettempdir()) / "faceless_generator"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Output directory for final videos
        self.output_dir = Path("storage/generated_media")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self.stats = {
            "videos_generated": 0,
            "images_generated": 0,
            "total_cost": 0.0,
            "api_calls": {
                "pexels": 0,
                "pixabay": 0,
                "elevenlabs": 0,
                "fal": 0,
                "ideogram": 0,
                "goapi": 0,
                "dalle": 0,
                "flux": 0
            },
            "tier_usage": {
                "stock_video": 0,
                "generated_images": 0,
                "ai_animation": 0
            },
            "errors": 0
        }
        
        # Initialize RAG system for video type specifications
        self.rag = None
        if RAG_AVAILABLE:
            try:
                self.rag = get_faceless_rag()
                logger.info(f"RAG system initialized with {len(self.rag.get_all_video_types())} video types")
            except Exception as e:
                logger.warning(f"Failed to initialize RAG system: {e}")
        
        # Initialize Style Loader for deep research production prompts
        self.style_loader = None
        if STYLE_LOADER_AVAILABLE:
            try:
                self.style_loader = FacelessStyleLoader()
                logger.info(f"Style Loader initialized with {self.style_loader.total_styles} styles in {len(self.style_loader.list_categories())} categories")
            except Exception as e:
                logger.warning(f"Failed to initialize Style Loader: {e}")
        
        # Check API availability
        self._check_api_availability()
    
    def _check_api_availability(self):
        """Check which APIs are available based on configured keys."""
        self.apis_available = {
            # Tier 1: Stock Video
            "pexels": bool(self.pexels_api_key and not self.pexels_api_key.startswith("your_")),
            "pixabay": bool(self.pixabay_api_key and not self.pixabay_api_key.startswith("your_")),
            # Voiceover
            "elevenlabs": bool(self.elevenlabs_api_key and not self.elevenlabs_api_key.startswith("your_")),
            # Tier 3: AI Animation
            "fal": bool(self.fal_api_key and not self.fal_api_key.startswith("your_")),
            # Tier 2: Image Generation
            "ideogram": bool(self.ideogram_api_key and not self.ideogram_api_key.startswith("your_")),
            "goapi": bool(self.goapi_api_key and not self.goapi_api_key.startswith("your_")),
            "dalle": bool(self.openai_api_key and not self.openai_api_key.startswith("your_"))
        }
        
        # Check FFmpeg availability
        self._ffmpeg_exe = self._find_ffmpeg()
        self.apis_available["ffmpeg"] = self._ffmpeg_exe is not None
        
        logger.info(f"API Availability: {self.apis_available}")
        
        available_tiers = []
        if self.apis_available["pexels"] or self.apis_available["pixabay"]:
            available_tiers.append("Tier 1 (Stock Video)")
        if self.apis_available["dalle"] or self.apis_available["ideogram"] or self.apis_available["goapi"]:
            available_tiers.append("Tier 2 (Generated Images)")
        if self.apis_available["fal"]:
            available_tiers.append("Tier 3 (AI Animation)")
        
        logger.info(f"Available Tiers: {available_tiers}")
    
    def _find_ffmpeg(self) -> Optional[str]:
        """Return the path to ffmpeg, or None if unavailable."""
        # Try system ffmpeg first
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                return "ffmpeg"
        except FileNotFoundError:
            pass
        # Fallback: imageio-ffmpeg bundled binary
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
            if path and os.path.isfile(path):
                logger.info(f"Using imageio-ffmpeg bundled binary: {path}")
                return path
        except Exception:
            pass
        return None

    def _check_ffmpeg(self) -> bool:
        return self._ffmpeg_exe is not None
    
    # =========================================================================
    # RAG SYSTEM METHODS - Video Type Specifications
    # =========================================================================
    
    def get_video_type_spec(self, video_type: VideoType) -> Dict[str, Any]:
        """
        Get production specifications for a video type from RAG system.
        
        Returns specs for: audio, visuals, voice, pacing, structure
        """
        if not self.rag:
            return {}
        
        return self.rag.get_complete_spec(video_type.value)
    
    def get_audio_settings(self, video_type: VideoType) -> Dict[str, Any]:
        """Get audio/music settings for a video type."""
        if not self.rag:
            return {
                "music_genre": "ambient",
                "bpm_range": (80, 100),
                "volume_percent": (15, 20),
                "sound_effects": [],
                "mood": "neutral"
            }
        return self.rag.get_audio_spec(video_type.value)
    
    def get_visual_settings(self, video_type: VideoType) -> Dict[str, Any]:
        """Get visual/color grading settings for a video type."""
        if not self.rag:
            return {
                "saturation": 0,
                "contrast": "normal",
                "temperature": "neutral",
                "effects": [],
                "stock_keywords": []
            }
        return self.rag.get_visual_spec(video_type.value)
    
    def get_voice_settings(self, video_type: VideoType) -> Dict[str, Any]:
        """Get voice/narration settings for a video type."""
        if not self.rag:
            return {
                "persona": "Narrator",
                "tone": "neutral",
                "speech_rate_wpm": (150, 170),
                "recommended_voices": ["Adam", "Josh"],
                "effects": []
            }
        return self.rag.get_voice_spec(video_type.value)
    
    def get_pacing_settings(self, video_type: VideoType) -> Dict[str, Any]:
        """Get pacing and transition settings for a video type."""
        if not self.rag:
            return {
                "style": "moderate",
                "transitions": ["cut"],
                "scene_duration": (5, 10),
                "structure": {}
            }
        return self.rag.get_pacing_spec(video_type.value)
    
    def get_stock_keywords_for_type(self, video_type: VideoType) -> List[str]:
        """Get optimized stock video keywords for a video type."""
        if not self.rag:
            return []
        return self.rag.get_stock_keywords(video_type.value)
    
    def get_production_guide(self, video_type: VideoType) -> str:
        """Get full production guide for a video type (for prompts/context)."""
        if not self.rag:
            return f"No production guide available for {video_type.value}"
        return self.rag.get_production_guide(video_type.value)
    
    def list_available_video_types(self) -> List[str]:
        """List all available video types in RAG system."""
        if not self.rag:
            return [vt.value for vt in VideoType]
        return self.rag.get_all_video_types()
    
    # =========================================================================
    # STYLE LOADER METHODS - Deep Research Production Prompts
    # =========================================================================
    
    def list_style_categories(self) -> List[str]:
        """
        List all available faceless video style categories.
        
        Categories include: reddit_storytelling, horror_dark_content, 
        educational_explainer, motivational_content, etc.
        """
        if not self.style_loader:
            return []
        return self.style_loader.list_categories()
    
    def list_styles_in_category(self, category: str) -> List[str]:
        """
        List all styles available within a category.
        
        Args:
            category: Category name (e.g., "reddit_storytelling")
        """
        if not self.style_loader:
            return []
        return self.style_loader.list_styles_by_category(category)
    
    def get_style(
        self, 
        category: str, 
        style_name: Optional[str] = None
    ) -> Optional['FacelessStyle']:
        """
        Get a specific production style from the deep research prompts.
        
        Args:
            category: Style category (e.g., "reddit_storytelling", "horror_dark_content")
            style_name: Specific style name, or None to get the first/default style
            
        Returns:
            FacelessStyle object with complete production specs
        """
        if not self.style_loader:
            return None
        return self.style_loader.get_style(category, style_name)
    
    def get_style_for_platform(
        self, 
        category: str, 
        platform: str
    ) -> Optional['FacelessStyle']:
        """
        Get the best style in a category optimized for a specific platform.
        
        Args:
            category: Style category (e.g., "reddit_storytelling")
            platform: Target platform (e.g., "youtube_shorts", "tiktok", "instagram_reels")
            
        Returns:
            FacelessStyle object optimized for the platform
        """
        if not self.style_loader:
            return None
        return self.style_loader.get_best_style_for_platform(category, platform)
    
    def search_styles(self, query: str) -> List[tuple]:
        """
        Search for styles matching a query across all categories.
        
        Args:
            query: Search term (e.g., "horror", "reddit", "motivational")
            
        Returns:
            List of (category, style_name, FacelessStyle) tuples
        """
        if not self.style_loader:
            return []
        return self.style_loader.search_styles(query)
    
    def get_style_categories_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get a summary of all style categories with display names and counts.
        
        Returns:
            Dict with category info: display_name, style_count
        """
        if not self.style_loader:
            return {}
        
        result = {}
        for category in self.style_loader.list_categories():
            display_name = get_category_display_name(category) if STYLE_LOADER_AVAILABLE else category
            result[category] = {
                "display_name": display_name,
                "style_count": len(self.style_loader.list_styles_by_category(category))
            }
        return result
    
    def get_script_prompt_for_style(self, style: 'FacelessStyle') -> str:
        """
        Get a system prompt for script writing based on a style.
        
        This prompt can be passed to the content agent or Claude to 
        generate scripts that match the style's specifications.
        
        Args:
            style: FacelessStyle object from get_style()
            
        Returns:
            System prompt string for AI script generation
        """
        if style is None:
            return "You are a professional video script writer."
        return style.get_script_writing_prompt()
    
    def apply_style_to_content(
        self, 
        content_data: Dict[str, Any], 
        style_category: str,
        platform: str = "youtube_shorts"
    ) -> Dict[str, Any]:
        """
        Apply a faceless video style to content from the Marketing Intelligence Agent.
        
        This is the main method for combining business content with a faceless video style.
        
        Flow:
        1. Marketing Agent generates content data (topic, angle, hooks, target audience)
        2. Client selects a style category (e.g., "reddit_storytelling", "horror_dark_content")
        3. This method applies the style's production specs to the content
        4. Returns enhanced content ready for script generation
        
        Args:
            content_data: Content from Marketing Intelligence Agent containing:
                - topic: str
                - angle: str  
                - hooks: List[str]
                - target_audience: str (optional)
                - niche: str (optional)
                - key_points: List[str] (optional)
            style_category: Faceless video style category
            platform: Target platform for optimization
            
        Returns:
            Enhanced content dict with style specs applied:
                - original content fields
                - style_name: str
                - style_category: str
                - audio_config: Dict
                - visual_config: Dict
                - pacing_config: List
                - content_guidelines: List[str]
                - platform_settings: Dict
                - script_prompt: str (system prompt for AI)
                - elevenlabs_settings: Dict
        """
        # Get the best style for the platform
        style = self.get_style_for_platform(style_category, platform)
        
        if not style:
            # Fallback to default style in category
            style = self.get_style(style_category)
        
        if not style:
            logger.warning(f"Style category not found: {style_category}")
            return {
                **content_data,
                "style_applied": False,
                "error": f"Style category '{style_category}' not found"
            }
        
        # Build enhanced content
        enhanced = {
            # Original content
            **content_data,
            
            # Style metadata
            "style_applied": True,
            "style_name": style.template_name,
            "style_category": style_category,
            "platform": platform,
            
            # Production configurations
            "audio_config": style.get_audio_config(),
            "visual_config": style.get_visual_config(),
            "pacing_config": style.get_pacing_config(),
            "content_guidelines": style.get_content_guidelines(),
            "platform_settings": style.get_platform_settings(platform),
            
            # AI generation helpers
            "script_prompt": style.get_script_writing_prompt(),
            "elevenlabs_settings": style.get_elevenlabs_settings(),
            
            # Technical specs
            "technical_specs": style.technical_specs
        }
        
        # Add style-specific visual keywords for stock footage search
        visual_elements = style.visual_specs.get("visual_elements", [])
        if visual_elements:
            enhanced["stock_video_keywords"] = visual_elements[:5]
        
        logger.info(f"Applied style '{style.template_name}' to content for {platform}")
        return enhanced

    # =========================================================================
    # TIER 1: STOCK VIDEO (Pexels/Pixabay)
    # =========================================================================
    
    async def search_stock_videos(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "portrait"
    ) -> List[Dict[str, Any]]:
        """Search for stock videos from Pexels and Pixabay."""
        videos = []
        
        # Try Pexels first
        if self.apis_available["pexels"]:
            pexels_videos = await self._search_pexels(query, per_page, orientation)
            videos.extend(pexels_videos)
        
        # Fallback to Pixabay if needed
        if len(videos) < per_page and self.apis_available["pixabay"]:
            pixabay_videos = await self._search_pixabay(query, per_page - len(videos), orientation)
            videos.extend(pixabay_videos)
        
        return videos
    
    async def _search_pexels(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "portrait"
    ) -> List[Dict[str, Any]]:
        """Search Pexels for stock videos."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.pexels_base_url}/search"
                headers = {"Authorization": self.pexels_api_key}
                params = {
                    "query": query,
                    "per_page": per_page,
                    "orientation": orientation
                }
                
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.stats["api_calls"]["pexels"] += 1
                        
                        videos = []
                        for video in data.get("videos", []):
                            # Get the best quality file
                            video_files = video.get("video_files", [])
                            best_file = max(
                                video_files,
                                key=lambda x: x.get("height", 0),
                                default={}
                            )
                            
                            videos.append({
                                "id": video.get("id"),
                                "url": best_file.get("link"),
                                "width": best_file.get("width"),
                                "height": best_file.get("height"),
                                "duration": video.get("duration"),
                                "source": "pexels",
                                "thumbnail": video.get("image")
                            })
                        
                        return videos
                    else:
                        error_text = await response.text()
                        logger.error(f"Pexels search failed: {response.status} - {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Pexels search error: {str(e)}")
            return []
    
    async def _search_pixabay(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "vertical"
    ) -> List[Dict[str, Any]]:
        """Search Pixabay for stock videos."""
        # Map orientation
        if orientation == "portrait":
            orientation = "vertical"
        elif orientation == "landscape":
            orientation = "horizontal"
        
        # Pixabay requires per_page between 3-200
        per_page = max(3, min(per_page, 200))
        
        try:
            async with aiohttp.ClientSession() as session:
                url = self.pixabay_base_url
                params = {
                    "key": self.pixabay_api_key,
                    "q": query,
                    "per_page": per_page
                }
                # Only add orientation if it's a valid value
                if orientation in ["vertical", "horizontal"]:
                    params["orientation"] = orientation
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.stats["api_calls"]["pixabay"] += 1
                        
                        videos = []
                        for hit in data.get("hits", []):
                            # Get the large video
                            videos_data = hit.get("videos", {})
                            large = videos_data.get("large", {})
                            
                            videos.append({
                                "id": hit.get("id"),
                                "url": large.get("url"),
                                "width": large.get("width"),
                                "height": large.get("height"),
                                "duration": hit.get("duration"),
                                "source": "pixabay",
                                "thumbnail": hit.get("userImageURL")
                            })
                        
                        return videos
                    else:
                        error_text = await response.text()
                        logger.error(f"Pixabay search failed: {response.status} - {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Pixabay search error: {str(e)}")
            return []
    
    async def download_video(self, url: str, filename: str) -> Optional[str]:
        """Download a video from URL to temp directory."""
        try:
            filepath = self.temp_dir / filename
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(filepath, "wb") as f:
                            f.write(await response.read())
                        return str(filepath)
            return None
        except Exception as e:
            logger.error(f"Video download error: {str(e)}")
            return None
    
    async def _download_image(self, url: str, filename: str) -> Optional[str]:
        """Download an image from URL to temp directory."""
        try:
            filepath = self.temp_dir / filename
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(filepath, "wb") as f:
                            f.write(await response.read())
                        return str(filepath)
            return None
        except Exception as e:
            logger.error(f"Image download error: {str(e)}")
            return None
    
    # =========================================================================
    # VOICEOVER: ElevenLabs (with timestamps for audio-driven timing)
    # =========================================================================
    
    async def generate_voiceover(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",  # Rachel - default voice
        model_id: str = "eleven_multilingual_v2"
    ) -> Optional[Dict[str, Any]]:
        """Generate voiceover using ElevenLabs API with word-level timestamps."""
        if not self.apis_available["elevenlabs"]:
            logger.warning("ElevenLabs API not configured")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use the endpoint that returns timestamps
                url = f"{self.elevenlabs_base_url}/text-to-speech/{voice_id}/with-timestamps"
                headers = {
                    "xi-api-key": self.elevenlabs_api_key,
                    "Content-Type": "application/json"
                }
                payload = {
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract audio and timestamps
                        audio_base64 = data.get("audio_base64", "")
                        alignment = data.get("alignment", {})
                        characters = alignment.get("characters", [])
                        character_start_times = alignment.get("character_start_times_seconds", [])
                        character_end_times = alignment.get("character_end_times_seconds", [])
                        
                        # Save audio to temp file
                        audio_path = self.temp_dir / f"voiceover_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                        import base64
                        with open(audio_path, "wb") as f:
                            f.write(base64.b64decode(audio_base64))
                        
                        # Calculate actual duration from timestamps
                        actual_duration = character_end_times[-1] if character_end_times else len(text) / 15
                        
                        # Build word timing data for scene synchronization
                        word_timings = self._extract_word_timings(
                            characters, character_start_times, character_end_times
                        )
                        
                        self.stats["api_calls"]["elevenlabs"] += 1
                        
                        # Estimate cost (~$0.30/1000 chars for multilingual v2)
                        cost = len(text) / 1000 * 0.30
                        self.stats["total_cost"] += cost
                        
                        return {
                            "audio_path": str(audio_path),
                            "text": text,
                            "duration": actual_duration,
                            "word_timings": word_timings,
                            "cost": cost
                        }
                    else:
                        # Fallback to regular endpoint without timestamps
                        logger.warning("Timestamps endpoint failed, using regular TTS")
                        return await self._generate_voiceover_simple(text, voice_id, model_id)
        except Exception as e:
            logger.error(f"ElevenLabs error: {str(e)}")
            # Fallback to simple generation
            return await self._generate_voiceover_simple(text, voice_id, model_id)
    
    def _extract_word_timings(
        self,
        characters: List[str],
        start_times: List[float],
        end_times: List[float]
    ) -> List[Dict[str, Any]]:
        """Extract word-level timings from character-level data."""
        if not characters or not start_times or not end_times:
            return []
        
        word_timings = []
        current_word = ""
        word_start = None
        
        for i, char in enumerate(characters):
            if char == " " or char in ".!?,;:":
                if current_word:
                    word_timings.append({
                        "word": current_word,
                        "start_time": word_start,
                        "end_time": end_times[i-1] if i > 0 else end_times[i]
                    })
                    current_word = ""
                    word_start = None
            else:
                if word_start is None:
                    word_start = start_times[i]
                current_word += char
        
        # Don't forget the last word
        if current_word and word_start is not None:
            word_timings.append({
                "word": current_word,
                "start_time": word_start,
                "end_time": end_times[-1]
            })
        
        return word_timings
    
    async def _generate_voiceover_simple(
        self,
        text: str,
        voice_id: str,
        model_id: str
    ) -> Optional[Dict[str, Any]]:
        """Simple voiceover generation without timestamps (fallback)."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.elevenlabs_base_url}/text-to-speech/{voice_id}"
                headers = {
                    "xi-api-key": self.elevenlabs_api_key,
                    "Content-Type": "application/json"
                }
                payload = {
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75
                    }
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        audio_path = self.temp_dir / f"voiceover_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                        with open(audio_path, "wb") as f:
                            f.write(await response.read())
                        
                        self.stats["api_calls"]["elevenlabs"] += 1
                        cost = len(text) / 1000 * 0.30
                        self.stats["total_cost"] += cost
                        
                        # Get actual duration using ffprobe
                        duration = await self._get_audio_duration(str(audio_path))
                        
                        return {
                            "audio_path": str(audio_path),
                            "text": text,
                            "duration": duration or len(text) / 15,
                            "word_timings": [],  # No timestamps available
                            "cost": cost
                        }
                    return None
        except Exception as e:
            logger.error(f"ElevenLabs simple error: {str(e)}")
            return None
    
    async def _get_audio_duration(self, audio_path: str) -> Optional[float]:
        """Get actual audio duration using ffmpeg."""
        try:
            cmd = [
                self._ffmpeg_exe or "ffmpeg",
                "-i", audio_path,
                "-f", "null", "-"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            # ffmpeg prints duration to stderr
            import re as _re_dur
            match = _re_dur.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', result.stderr)
            if match:
                h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
                return h * 3600 + m * 60 + s
            return None
        except Exception:
            return None
    
    async def get_elevenlabs_voices(self) -> List[Dict[str, Any]]:
        """Get available voices from ElevenLabs."""
        if not self.apis_available["elevenlabs"]:
            return []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.elevenlabs_base_url}/voices"
                headers = {"xi-api-key": self.elevenlabs_api_key}
                
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [
                            {
                                "voice_id": v.get("voice_id"),
                                "name": v.get("name"),
                                "category": v.get("category")
                            }
                            for v in data.get("voices", [])
                        ]
                    return []
        except Exception as e:
            logger.error(f"ElevenLabs voices error: {str(e)}")
            return []
    
    # =========================================================================
    # TIER 3: AI ANIMATION (fal.ai - Kling/Wan)
    # =========================================================================
    
    async def animate_image(
        self,
        image_url: str,
        prompt: str = "",
        duration: int = 5,
        model: str = "kling",  # "kling" or "wan"
        aspect_ratio: str = "16:9",
        motion_strength: float = 0.8,
        guidance_scale: float = 7.5,
        fps: int = 24
    ) -> Optional[Dict[str, Any]]:
        """Animate an image using fal.ai (Kling or Wan) with advanced parameters."""
        if not self.apis_available["fal"]:
            logger.warning("fal.ai API not configured")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                # Select model endpoint - USE LATEST VERSIONS
                if model == "kling":
                    # Try to use latest Kling version
                    endpoint = "fal-ai/kling-video/v1.6/standard/image-to-video"  # TODO: Update to v2.0/v3.0 when available
                    cost_per_sec = 0.07
                else:  # wan
                    endpoint = "fal-ai/wan/v2.1/image-to-video"
                    cost_per_sec = 0.05
                
                url = f"{self.fal_base_url}/{endpoint}"
                headers = {
                    "Authorization": f"Key {self.fal_api_key}",
                    "Content-Type": "application/json"
                }
                
                # Enhanced payload with advanced parameters
                payload = {
                    "image_url": image_url,
                    "prompt": self._enhance_animation_prompt(prompt) if prompt else "cinematic camera movement, natural motion, high quality, photorealistic",
                    "duration": str(duration),
                    "aspect_ratio": aspect_ratio,
                    "motion_strength": motion_strength,
                    "guidance_scale": guidance_scale,
                    "fps": fps
                }
                
                # Remove None values
                payload = {k: v for k, v in payload.items() if v is not None}
                
                logger.info(f"🎬 Submitting ENHANCED animation job to fal.ai ({model}) - {duration}s, {aspect_ratio}")
                logger.info(f"   Motion: {motion_strength}, Guidance: {guidance_scale}, FPS: {fps}")
                
                # Submit job
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        request_id = data.get("request_id")
                        
                        if request_id:
                            # Poll for completion
                            result = await self._poll_fal_status(request_id, endpoint)
                            
                            if result:
                                self.stats["api_calls"]["fal"] += 1
                                cost = duration * cost_per_sec
                                self.stats["total_cost"] += cost
                                self.stats["tier_usage"]["ai_animation"] += 1
                                
                                video_url = result.get("video", {}).get("url")
                                return {
                                    "video_url": video_url,
                                    "duration": duration,
                                    "model": model,
                                    "cost": cost,
                                    "motion_strength": motion_strength,
                                    "guidance_scale": guidance_scale,
                                    "fps": fps
                                }
                        else:
                            # Synchronous response
                            video_url = data.get("video", {}).get("url")
                            if video_url:
                                self.stats["api_calls"]["fal"] += 1
                                cost = duration * cost_per_sec
                                self.stats["total_cost"] += cost
                                return {
                                    "video_url": video_url,
                                    "duration": duration,
                                    "model": model,
                                    "cost": cost
                                }
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"fal.ai failed: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"fal.ai error: {str(e)}")
            return None
    
    def _enhance_animation_prompt(self, prompt: str) -> str:
        """Enhance animation prompt with cinematic details for better quality."""
        # Base cinematic instructions
        cinematic_base = "cinematic camera movement, smooth motion, high quality, photorealistic, detailed"
        
        # Motion type keywords
        if any(word in prompt.lower() for word in ["landscape", "nature", "mountain", "ocean", "sky"]):
            motion_style = "gentle camera push, natural environmental motion, soft dynamics"
        elif any(word in prompt.lower() for word in ["city", "urban", "street", "building"]):
            motion_style = "dynamic tracking shot, urban movement, architectural parallax"
        elif any(word in prompt.lower() for word in ["person", "character", "figure"]):
            motion_style = "subtle character animation, natural human movement, portrait dynamics"
        elif any(word in prompt.lower() for word in ["abstract", "particle", "energy"]):
            motion_style = "fluid abstract motion, particle dynamics, energy flow"
        else:
            motion_style = "natural scene dynamics, cinematic movement"
        
        # Combine for enhanced prompt
        enhanced = f"{prompt}, {motion_style}, {cinematic_base}"
        
        # Ensure not too long (fal.ai has limits)
        if len(enhanced) > 500:
            enhanced = enhanced[:497] + "..."
        
        return enhanced
    
    async def _poll_fal_status(
        self,
        request_id: str,
        endpoint: str,
        timeout_seconds: int = 900,
        poll_interval: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Poll fal.ai for job completion with progress updates."""
        try:
            async with aiohttp.ClientSession() as session:
                status_url = f"https://queue.fal.run/{endpoint}/requests/{request_id}/status"
                result_url = f"https://queue.fal.run/{endpoint}/requests/{request_id}"
                headers = {"Authorization": f"Key {self.fal_api_key}"}
                
                elapsed = 0
                last_status = None
                
                while elapsed < timeout_seconds:
                    async with session.get(status_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            status = data.get("status")
                            
                            # Show progress only when status changes
                            if status != last_status:
                                logger.info(f"🎬 fal.ai: {status} ({elapsed}s elapsed)")
                                last_status = status
                            
                            if status == "COMPLETED":
                                # Get result
                                async with session.get(result_url, headers=headers) as result_response:
                                    if result_response.status == 200:
                                        logger.info(f"✅ Animation complete ({elapsed}s total)")
                                        return await result_response.json()
                            elif status in ["FAILED", "CANCELLED"]:
                                logger.error(f"❌ fal.ai job {status}: {data}")
                                return None
                    
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                
                logger.error(f"⏱️ fal.ai job timed out after {timeout_seconds}s")
                return None
        except Exception as e:
            logger.error(f"💥 fal.ai poll error: {str(e)}")
            return None
    
    # =========================================================================
    # IMAGE GENERATION (Ideogram, GoAPI/Midjourney, DALL-E)
    # =========================================================================
    
    async def generate_image(
        self,
        prompt: str,
        image_type: ImageType = ImageType.GENERAL,
        size: str = "1080x1080",
        platform: Optional[Platform] = None,
        style: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        quality: ImageQuality = ImageQuality.BUDGET,
        reference_images: Optional[List[str]] = None,
    ) -> GeneratedMedia:
        """
        Generate a faceless image using quality-tiered APIs.

        Quality Tiers:
        - BUDGET: DALL-E 3 ($0.04/image, fast, good quality)
        - STANDARD: Flux ($0.055/image, better quality, more detail)
        - PREMIUM: Midjourney ($0.08/image, highest quality, artistic)

        Args:
            reference_images: Optional list of public image URLs to use as visual
                              style references. Midjourney uses --sref; other APIs
                              receive a style descriptor appended to the prompt.
        """
        start_time = datetime.now()

        # Add faceless requirement to prompt
        enhanced_prompt = self._enhance_prompt_for_faceless(prompt, style)

        # Inject reference image style guidance for non-Midjourney APIs
        if reference_images:
            ref_note = (
                "maintain visual consistency with the brand reference style: "
                "matching color palette, mood, lighting, and aesthetic"
            )
            enhanced_prompt = f"{enhanced_prompt}. {ref_note}"

        # Default negative prompt for faceless content
        if not negative_prompt:
            negative_prompt = "human faces, people faces, portraits, selfies, identifiable people"

        logger.info(f"Generating image: type={image_type.value}, quality={quality.value}, size={size}"
                    + (f", {len(reference_images)} ref image(s)" if reference_images else ""))

        # Route to appropriate API based on quality tier and image type
        if quality == ImageQuality.PREMIUM:
            # Premium: Midjourney (best quality) — supports --sref natively
            result = await self._generate_with_goapi(enhanced_prompt, size, negative_prompt,
                                                      reference_images=reference_images)
            if not result.success and self.apis_available["flux"]:
                result = await self._generate_with_flux(enhanced_prompt, size)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(enhanced_prompt, size)

        elif quality == ImageQuality.STANDARD:
            # Standard: Flux (balanced quality/cost)
            result = await self._generate_with_flux(enhanced_prompt, size)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(enhanced_prompt, size)

        elif image_type == ImageType.TEXT:
            # Text-focused: Ideogram
            result = await self._generate_with_ideogram(enhanced_prompt, size, negative_prompt)
            if not result.success and self.apis_available["dalle"]:
                result = await self._generate_with_dalle(enhanced_prompt, size)

        else:
            # Budget: DALL-E 3 (default, reliable)
            result = await self._generate_with_dalle(enhanced_prompt, size)
            if not result.success and self.apis_available["flux"]:
                result = await self._generate_with_flux(enhanced_prompt, size)
        
        # Calculate generation time
        generation_time = (datetime.now() - start_time).total_seconds()
        result.generation_time_seconds = generation_time
        result.metadata["platform"] = platform.value if platform else None
        result.metadata["image_type"] = image_type.value
        result.metadata["quality"] = quality.value
        result.metadata["original_prompt"] = prompt
        
        if result.success:
            self.stats["images_generated"] += 1
            self.stats["tier_usage"]["generated_images"] += 1
        else:
            self.stats["errors"] += 1
        
        return result
    
    def _enhance_prompt_for_faceless(self, prompt: str, style: Optional[str] = None) -> str:
        """Enhance prompt to ensure faceless output."""
        faceless_instructions = "NO human faces, faceless, abstract human silhouettes only if people are needed"
        enhanced = f"{prompt}. {faceless_instructions}"
        if style:
            enhanced = f"{enhanced}. Style: {style}"
        return enhanced
    
    def _create_enhanced_animation_prompt(self, scene_text: str, video_type: Optional[VideoType] = None) -> str:
        """Create detailed animation prompts for higher quality results."""
        
        # Base scene analysis
        scene_lower = scene_text.lower()
        
        # Camera movement based on content
        if any(word in scene_lower for word in ["landscape", "mountain", "ocean", "forest", "nature"]):
            camera = "slow dolly forward, revealing depth and scale"
        elif any(word in scene_lower for word in ["city", "urban", "building", "street"]):
            camera = "dynamic tracking shot with urban parallax"
        elif any(word in scene_lower for word in ["close", "detail", "focus"]):
            camera = "subtle push-in with shallow depth of field"
        elif any(word in scene_lower for word in ["sky", "clouds", "horizon"]):
            camera = "gentle pan across vast scenery"
        else:
            camera = "cinematic dolly movement with natural flow"
        
        # Motion style based on video type
        if video_type == VideoType.MOTIVATIONAL:
            motion_style = "inspiring upward motion, golden lighting, heroic perspective"
        elif video_type == VideoType.HORROR_STORYTELLING:
            motion_style = "subtle ominous movement, dramatic shadows, tension building"
        elif video_type == VideoType.EDUCATIONAL_EXPLAINER:
            motion_style = "clean smooth motion, professional lighting, clear focus"
        elif video_type == VideoType.REDDIT_STORIES:
            motion_style = "dynamic engaging movement, vibrant energy, captivating flow"
        else:
            motion_style = "natural realistic motion, balanced lighting, professional quality"
        
        # Quality enhancers
        quality_terms = [
            "photorealistic detail",
            "cinematic lighting",
            "smooth natural motion",
            "high production value",
            "professional cinematography",
            "4K quality"
        ]
        
        # Combine elements
        enhanced_prompt = f"{scene_text}. {camera}, {motion_style}, {', '.join(quality_terms[:3])}"
        
        # Ensure reasonable length
        if len(enhanced_prompt) > 400:
            enhanced_prompt = enhanced_prompt[:397] + "..."
        
        return enhanced_prompt
    
    async def _generate_with_ideogram(
        self,
        prompt: str,
        size: str,
        negative_prompt: str
    ) -> GeneratedMedia:
        """Generate image using Ideogram API (best for text/flyers)."""
        if not self.apis_available["ideogram"]:
            return GeneratedMedia(
                success=False,
                media_type="image",
                error="Ideogram API not configured"
            )
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.ideogram_base_url}/generate"
                headers = {
                    "Api-Key": self.ideogram_api_key,
                    "Content-Type": "application/json"
                }
                
                # Parse size to aspect ratio
                width, height = map(int, size.split("x"))
                if width == height:
                    aspect = "ASPECT_1_1"
                elif width > height:
                    aspect = "ASPECT_16_9"
                else:
                    aspect = "ASPECT_9_16"
                
                payload = {
                    "image_request": {
                        "prompt": prompt,
                        "aspect_ratio": aspect,
                        "model": "V_2",
                        "magic_prompt_option": "AUTO",
                        "negative_prompt": negative_prompt
                    }
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        image_url = data.get("data", [{}])[0].get("url")
                        
                        self.stats["api_calls"]["ideogram"] += 1
                        self.stats["total_cost"] += 0.02
                        
                        return GeneratedMedia(
                            success=True,
                            media_type="image",
                            url=image_url,
                            api_used="ideogram",
                            tier_used="generated_images",
                            cost_estimate=0.02,
                            metadata={"size": size, "aspect": aspect}
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"Ideogram failed: {response.status} - {error_text}")
                        return GeneratedMedia(
                            success=False,
                            media_type="image",
                            error=f"Ideogram API error: {response.status}"
                        )
        except Exception as e:
            logger.error(f"Ideogram error: {str(e)}")
            return GeneratedMedia(success=False, media_type="image", error=str(e))
    
    async def _generate_with_goapi(
        self,
        prompt: str,
        size: str,
        negative_prompt: str,
        reference_images: Optional[List[str]] = None,
    ) -> GeneratedMedia:
        """Generate image using GoAPI (Midjourney) for artistic images.

        When reference_images are supplied, they are passed as --sref style
        references so Midjourney adopts their colour palette and aesthetic.
        """
        if not self.apis_available["goapi"]:
            return GeneratedMedia(
                success=False,
                media_type="image",
                error="GoAPI not configured"
            )

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.goapi_base_url}/imagine"
                headers = {
                    "X-API-Key": self.goapi_api_key,
                    "Content-Type": "application/json"
                }

                width, height = map(int, size.split("x"))
                if width == height:
                    ar = "1:1"
                elif width > height:
                    ar = "16:9"
                else:
                    ar = "9:16"

                # Build style-reference flags (up to 3 images)
                sref_flags = ""
                if reference_images:
                    sref_flags = " " + " ".join(
                        f"--sref {u}" for u in reference_images[:3]
                    ) + " --sw 100"

                mj_prompt = f"{prompt} --ar {ar} --no {negative_prompt} --v 6{sref_flags}"
                
                payload = {
                    "prompt": mj_prompt,
                    "process_mode": "fast",
                    "webhook_endpoint": "",
                    "webhook_secret": ""
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        task_id = data.get("task_id")
                        
                        image_url = await self._goapi_poll_status(task_id)
                        
                        if image_url:
                            self.stats["api_calls"]["goapi"] += 1
                            self.stats["total_cost"] += 0.05
                            
                            return GeneratedMedia(
                                success=True,
                                media_type="image",
                                url=image_url,
                                api_used="goapi_midjourney",
                                tier_used="generated_images",
                                cost_estimate=0.05,
                                metadata={"size": size, "aspect_ratio": ar}
                            )
                        else:
                            return GeneratedMedia(
                                success=False,
                                media_type="image",
                                error="GoAPI generation timed out"
                            )
                    else:
                        error_text = await response.text()
                        logger.error(f"GoAPI failed: {response.status} - {error_text}")
                        return GeneratedMedia(
                            success=False,
                            media_type="image",
                            error=f"GoAPI error: {response.status}"
                        )
        except Exception as e:
            logger.error(f"GoAPI error: {str(e)}")
            return GeneratedMedia(success=False, media_type="image", error=str(e))
    
    async def _goapi_poll_status(
        self,
        task_id: str,
        timeout_seconds: int = 120,
        poll_interval: int = 5
    ) -> Optional[str]:
        """Poll GoAPI for image generation status."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.goapi_base_url}/fetch"
                headers = {
                    "X-API-Key": self.goapi_api_key,
                    "Content-Type": "application/json"
                }
                
                elapsed = 0
                while elapsed < timeout_seconds:
                    payload = {"task_id": task_id}
                    async with session.post(url, headers=headers, json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            status = data.get("status")
                            
                            if status == "finished":
                                task_result = data.get("task_result", {})
                                return task_result.get("image_url") or task_result.get("discord_image_url")
                            elif status == "failed":
                                logger.error(f"GoAPI task failed: {data}")
                                return None
                    
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval
                
                return None
        except Exception as e:
            logger.error(f"GoAPI poll error: {str(e)}")
            return None
    
    async def _generate_with_dalle(
        self,
        prompt: str,
        size: str
    ) -> GeneratedMedia:
        """Generate image using DALL-E 3 (OpenAI)."""
        if not self.apis_available["dalle"]:
            return GeneratedMedia(
                success=False,
                media_type="image",
                error="OpenAI API not configured"
            )
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.openai_base_url}/images/generations"
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }
                
                width, height = map(int, size.split("x"))
                if width == height:
                    dalle_size = "1024x1024"
                elif width > height:
                    dalle_size = "1792x1024"
                else:
                    dalle_size = "1024x1792"
                
                payload = {
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": dalle_size,
                    "quality": "standard",
                    "style": "vivid"
                }
                
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        image_url = data.get("data", [{}])[0].get("url")
                        revised_prompt = data.get("data", [{}])[0].get("revised_prompt")
                        
                        self.stats["api_calls"]["dalle"] += 1
                        self.stats["total_cost"] += 0.04
                        
                        return GeneratedMedia(
                            success=True,
                            media_type="image",
                            url=image_url,
                            api_used="dalle3",
                            tier_used="generated_images",
                            cost_estimate=0.04,
                            metadata={
                                "size": dalle_size,
                                "revised_prompt": revised_prompt
                            }
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"DALL-E failed: {response.status} - {error_text}")
                        return GeneratedMedia(
                            success=False,
                            media_type="image",
                            error=f"DALL-E API error: {response.status}"
                        )
        except Exception as e:
            logger.error(f"DALL-E error: {str(e)}")
            return GeneratedMedia(success=False, media_type="image", error=str(e))
    
    async def _generate_with_flux(
        self,
        prompt: str,
        size: str
    ) -> GeneratedMedia:
        """Generate image using Flux via fal.ai."""
        if not self.apis_available["fal"]:
            return GeneratedMedia(
                success=False,
                media_type="image",
                error="fal.ai API not configured"
            )
        
        try:
            async with aiohttp.ClientSession() as session:
                # Use synchronous endpoint for faster image generation
                url = "https://fal.run/fal-ai/flux/dev"
                headers = {
                    "Authorization": f"Key {self.fal_api_key}",
                    "Content-Type": "application/json"
                }
                
                width, height = map(int, size.split("x"))
                
                payload = {
                    "prompt": prompt,
                    "image_size": {
                        "width": width,
                        "height": height
                    },
                    "num_inference_steps": 28,
                    "guidance_scale": 3.5,
                    "num_images": 1,
                    "enable_safety_checker": False
                }
                
                logger.info(f"Calling Flux API...")
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status in [200, 201]:
                        data = await response.json()
                        image_url = data.get("images", [{}])[0].get("url")
                        
                        if image_url:
                            self.stats["api_calls"]["flux"] += 1
                            self.stats["total_cost"] += 0.055
                            
                            return GeneratedMedia(
                                success=True,
                                media_type="image",
                                url=image_url,
                                api_used="flux_dev",
                                tier_used="generated_images",
                                cost_estimate=0.055,
                                metadata={"size": size, "steps": 28, "generator": "flux"}
                            )
                        else:
                            logger.error(f"Flux returned no image URL: {data}")
                            return GeneratedMedia(
                                success=False,
                                media_type="image",
                                error="Flux generation returned no image"
                            )
                    else:
                        error_text = await response.text()
                        logger.error(f"Flux failed: {response.status} - {error_text}")
                        return GeneratedMedia(
                            success=False,
                            media_type="image",
                            error=f"Flux API error: {response.status}"
                        )
        except Exception as e:
            logger.error(f"Flux error: {str(e)}")
            return GeneratedMedia(success=False, media_type="image", error=str(e))
    
    # =========================================================================
    # VIDEO GENERATION (3-Tier System)
    # =========================================================================
    
    async def generate_script(
        self,
        topic: str,
        platform: Platform = Platform.INSTAGRAM_REEL,
        duration_target: int = 60,
        style: str = "engaging, educational",
        include_hook: bool = True,
        include_cta: bool = True,
        niche: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate optimized video script for faceless video production.
        
        This is specifically designed for faceless videos with:
        - Hook + Body + CTA structure
        - Proper sentence grouping (2-3 sentences per scene)
        - Duration targeting (30-90 seconds)
        - Platform-specific optimization
        
        Args:
            topic: Main topic/angle for the video
            platform: Target platform (affects length, style)
            duration_target: Target duration in seconds (30-90)
            style: Script style (e.g., "engaging, educational", "storytelling", "energetic")
            include_hook: Add attention-grabbing hook at start
            include_cta: Add call-to-action at end
            niche: Optional niche context for better script
        
        Returns:
            {
                "script": str,  # Full script text
                "scenes": List[str],  # Script broken into scenes
                "estimated_duration": int,  # Estimated seconds
                "scene_count": int,
                "word_count": int,
                "hook": str,  # First scene (if include_hook)
                "cta": str  # Last scene (if include_cta)
            }
        """
        from anthropic import Anthropic
        
        # Initialize Claude
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Platform-specific constraints
        platform_constraints = {
            Platform.INSTAGRAM_REEL: {"min": 15, "max": 90, "ideal": 45},
            Platform.TIKTOK: {"min": 15, "max": 60, "ideal": 30},
            Platform.YOUTUBE_SHORT: {"min": 15, "max": 60, "ideal": 45},
            Platform.YOUTUBE: {"min": 30, "max": 600, "ideal": 120},
        }
        
        constraints = platform_constraints.get(platform, {"min": 30, "max": 90, "ideal": 60})
        duration_target = max(constraints["min"], min(duration_target, constraints["max"]))
        
        # Calculate target word count (average speech rate: 150 words/minute)
        target_words = int((duration_target / 60) * 150)
        
        # Build prompt
        niche_context = f"Niche: {niche}\n" if niche else ""
        
        prompt = f"""Generate a faceless video script for the following:

Topic: {topic}
{niche_context}Platform: {platform.value}
Target Duration: {duration_target} seconds (~{target_words} words)
Style: {style}
Include Hook: {include_hook}
Include CTA: {include_cta}

CRITICAL REQUIREMENTS:
1. Write EXACTLY {target_words} words (±10%)
2. Group into 2-3 sentence scenes (each scene becomes one visual)
3. Each sentence must be SHORT (10-20 words max) for natural pacing
4. Use simple, direct language - no complex vocabulary
5. First scene MUST grab attention in 3 seconds
6. Last scene MUST have clear call-to-action

STRUCTURE:
- Hook (1 scene, 2-3 sentences): Grab attention with shocking stat/question/bold claim
- Body (5-7 scenes, 2-3 sentences each): Deliver value, tell story, educate
- CTA (1 scene, 2-3 sentences): Clear action for viewer to take

SCENE FORMATTING:
Separate each scene with "---" on its own line.

Example:
Did you know 90% of startups fail in their first year? The reason isn't what you think. It's not about money.

---

Most founders obsess over the product. They build in isolation for months. Then they launch to crickets.

---

The real killer is building something nobody wants. You need to validate BEFORE you build. Talk to 100 potential customers first.

---

If they won't pay now, they won't pay later. Save yourself years of wasted effort. Follow for more startup truth bombs!

NOW WRITE THE SCRIPT:"""

        try:
            response = client.messages.create(
                model=os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=2000,
                temperature=0.8,
                messages=[{"role": "user", "content": prompt}]
            )
            
            script_text = response.content[0].text.strip()
            
            # Parse scenes
            scenes = [s.strip() for s in script_text.split("---") if s.strip()]
            
            # Extract hook and CTA
            hook = scenes[0] if scenes else ""
            cta = scenes[-1] if len(scenes) > 1 else ""
            
            # Calculate stats
            word_count = len(script_text.split())
            estimated_duration = int((word_count / 150) * 60)  # 150 words/min
            
            logger.info(f"Script generated: {len(scenes)} scenes, {word_count} words, ~{estimated_duration}s")
            
            return {
                "script": script_text,
                "scenes": scenes,
                "estimated_duration": estimated_duration,
                "scene_count": len(scenes),
                "word_count": word_count,
                "hook": hook,
                "cta": cta,
                "platform": platform.value,
                "topic": topic
            }
            
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            return {
                "script": "",
                "scenes": [],
                "estimated_duration": 0,
                "scene_count": 0,
                "word_count": 0,
                "error": str(e)
            }
    
    async def generate_video(
        self,
        script: str,
        tier: VideoTier = VideoTier.STOCK_VIDEO,
        style: VideoStyle = VideoStyle.PROFESSIONAL,
        aspect_ratio: AspectRatio = AspectRatio.PORTRAIT,
        platform: Optional[Platform] = None,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        include_captions: bool = True,
        include_music: bool = False,
        music_url: Optional[str] = None,
        music_volume: float = 0.15,
        niche: Optional[str] = None,
        video_type: Optional[VideoType] = None,
        image_quality: ImageQuality = ImageQuality.BUDGET,
        client_id: Optional[str] = None,
    ) -> GeneratedMedia:
        """
        Generate a faceless video using the specified tier.
        
        Tiers:
        - STOCK_VIDEO: Real Pexels/Pixabay footage (FREE)
        - GENERATED_IMAGES: AI images + Ken Burns zoom/pan
        - AI_ANIMATION: AI-animated images (Kling/Wan via fal.ai)
        
        Args:
            script: Video script text
            tier: Video quality tier
            style: Visual style
            aspect_ratio: Video aspect ratio
            platform: Target platform (auto-sets aspect_ratio)
            voice_id: ElevenLabs voice ID
            include_captions: Add word-highlighting subtitles
            include_music: Add background music
            music_url: URL to background music file (MP3)
            music_volume: Music volume (0.0-1.0), default 0.15
            niche: Topic/niche for better visual matching (e.g., "AI automation", "fitness")
            video_type: VideoType for RAG-optimized production settings
            image_quality: Quality tier for generated images (Budget/Standard/Premium)
                          Only applies to GENERATED_IMAGES and AI_ANIMATION tiers
        """
        # ── Plan gate: check videos_created quota ─────────────────────────
        _resolved_cid = client_id or self.client_id
        try:
            from database.db import SessionLocal as _SL_vid
            from database.models import ClientProfile as _CP_vid
            from utils.plan_limits import check_limit as _chk_v, increment_usage as _inc_v
            _db_vid = _SL_vid()
            _prof = _db_vid.query(_CP_vid).filter(_CP_vid.client_id == _resolved_cid).first()
            if _prof:
                _ok, _msg = _chk_v(_prof, "videos_created")
                if not _ok:
                    _db_vid.close()
                    return GeneratedMedia(success=False, media_type="video", error=_msg)
            _db_vid.close()
        except Exception as _e:
            logger.warning(f"Video plan-limit check failed: {_e}")

        start_time = datetime.now()
        
        # Auto-set aspect ratio based on platform
        if platform:
            aspect_ratio = PLATFORM_ASPECT_RATIOS.get(platform, aspect_ratio)
        
        # Get RAG specifications if video_type provided
        type_spec = None
        if video_type and self.rag:
            type_spec = self.get_video_type_spec(video_type)
            if type_spec:
                logger.info(f"Using RAG specs for video type: {video_type.value}")
                # Override music volume from RAG if not explicitly set
                if include_music and music_volume == 0.15:
                    audio_spec = type_spec.get("audio", {})
                    vol_range = audio_spec.get("volume_percent", (15, 20))
                    music_volume = vol_range[0] / 100  # Use lower bound
                    logger.info(f"RAG audio volume: {music_volume:.0%}")
        
        logger.info(f"Generating video: tier={tier.value}, aspect_ratio={aspect_ratio.value}, type={video_type.value if video_type else 'general'}")
        
        # Warn about AI animation costs and time
        if tier == VideoTier.AI_ANIMATION:
            estimated_scenes = max(1, len(script.split('.')) - 1)  # Rough estimate
            estimated_cost = estimated_scenes * 0.14  # 2-second clips at $0.07/sec
            estimated_time = estimated_scenes * 8  # ~8 minutes per clip
            
            logger.warning(f"⚠️ AI ANIMATION TIER SELECTED")
            logger.warning(f"   Estimated scenes: {estimated_scenes}")
            logger.warning(f"   Estimated cost: ~${estimated_cost:.2f} (2-second clips)")
            logger.warning(f"   Estimated time: ~{estimated_time} minutes")
            logger.warning(f"   💡 Consider STOCK_VIDEO (free) or GENERATED_IMAGES (~$0.03/scene)")
        
        # Generate voiceover FIRST to get accurate timing
        voiceover = await self.generate_voiceover(script, voice_id)
        if not voiceover:
            logger.warning("Failed to generate voiceover, proceeding without audio")
            voiceover = {"audio_path": None, "cost": 0, "duration": 0, "word_timings": []}
        else:
            logger.info(f"Voiceover generated: {voiceover.get('duration', 0):.1f}s duration")
        
        # Split script into scenes using voiceover timing for accuracy
        scenes = self._script_to_scenes(script, voiceover, niche=niche, video_type=video_type)
        logger.info(f"Script split into {len(scenes)} scenes (smart grouping)")
        
        # Generate visuals based on tier
        # Load client reference images for Tier 2 / Tier 3 (has no effect on stock video)
        _ref_images: List[str] = []
        if client_id and tier != VideoTier.STOCK_VIDEO:
            _ref_images = get_client_reference_images(client_id, mode="videos")
            if _ref_images:
                logger.info(f"Using {len(_ref_images)} client reference image(s) for video style")

        if tier == VideoTier.STOCK_VIDEO:
            visuals = await self._generate_stock_video_visuals(scenes, aspect_ratio, video_type=video_type)
        elif tier == VideoTier.GENERATED_IMAGES:
            visuals = await self._generate_image_visuals(scenes, aspect_ratio, video_type=video_type,
                                                          image_quality=image_quality,
                                                          reference_images=_ref_images or None)
        else:  # AI_ANIMATION
            visuals = await self._generate_animated_visuals(scenes, aspect_ratio, video_type=video_type,
                                                             image_quality=image_quality)
        
        if not visuals:
            return GeneratedMedia(
                success=False,
                media_type="video",
                error=f"Failed to generate visuals for tier: {tier.value}"
            )
        
        # Check if FFmpeg is available for video assembly
        if not self.apis_available["ffmpeg"]:
            # Return visuals without assembly
            return GeneratedMedia(
                success=True,
                media_type="video",
                api_used=f"tier_{tier.value}",
                tier_used=tier.value,
                metadata={
                    "visuals": visuals,
                    "audio_path": voiceover.get("audio_path"),
                    "note": "FFmpeg not installed - visuals generated but not assembled"
                },
                cost_estimate=voiceover.get("cost", 0)
            )
        
        # Assemble video with FFmpeg
        video_path = await self._assemble_video(
            visuals=visuals,
            audio_path=voiceover.get("audio_path"),
            aspect_ratio=aspect_ratio,
            include_captions=include_captions,
            script=script,
            voiceover_data=voiceover,
            include_music=include_music,
            music_url=music_url,
            music_volume=music_volume
        )
        
        if not video_path:
            return GeneratedMedia(
                success=False,
                media_type="video",
                error="Failed to assemble video with FFmpeg"
            )
        
        # Calculate generation time and cost
        generation_time = (datetime.now() - start_time).total_seconds()
        
        self.stats["videos_generated"] += 1
        self.stats["tier_usage"][tier.value if tier.value != "generated" else "generated_images"] += 1

        # ── Increment videos_created usage counter ──
        try:
            from database.db import SessionLocal as _SL_vid2
            from database.models import ClientProfile as _CP_vid2
            from utils.plan_limits import increment_usage as _inc_vid2
            _db_v2 = _SL_vid2()
            _p_v2 = _db_v2.query(_CP_vid2).filter(_CP_vid2.client_id == _resolved_cid).first()
            if _p_v2:
                _inc_vid2(_p_v2, "videos_created", _db_v2)
            _db_v2.close()
        except Exception:
            pass
        
        return GeneratedMedia(
            success=True,
            media_type="video",
            local_path=video_path,
            api_used=f"tier_{tier.value}",
            tier_used=tier.value,
            generation_time_seconds=generation_time,
            cost_estimate=voiceover.get("cost", 0) + (0 if tier == VideoTier.STOCK_VIDEO else 0.05 * len(scenes)),
            metadata={
                "script_length": len(script),
                "scene_count": len(scenes),
                "tier": tier.value,
                "style": style.value,
                "aspect_ratio": aspect_ratio.value,
                "platform": platform.value if platform else None,
                "voice_id": voice_id,
                "captions": include_captions
            }
        )
    
    def _script_to_scenes(
        self,
        script: str,
        voiceover_data: Optional[Dict[str, Any]] = None,
        niche: Optional[str] = None,
        video_type: Optional[VideoType] = None
    ) -> List[Dict[str, Any]]:
        """
        Split script into scenes with SMART GROUPING (2-3 sentences per visual).
        Uses audio timestamps for precise timing when available.
        Generates niche-relevant keywords for better stock video matching.
        Uses video_type from RAG for optimized scene duration settings.
        """
        sentences = re.split(r'[.!?]+', script)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Get scene duration settings from RAG if video_type provided
        min_scene_duration = 5  # seconds
        max_scene_duration = 13  # seconds
        
        if video_type and self.rag:
            pacing = self.get_pacing_settings(video_type)
            scene_range = pacing.get("scene_duration", (5, 10))
            min_scene_duration = scene_range[0]
            max_scene_duration = scene_range[1]
            logger.info(f"RAG scene duration for {video_type.value}: {min_scene_duration}-{max_scene_duration}s")
        
        # Convert seconds to character counts (~15 chars per second at normal pace)
        MIN_CHARS_PER_SCENE = int(min_scene_duration * 15)  # ~80 chars for 5s
        MAX_CHARS_PER_SCENE = int(max_scene_duration * 15)  # ~200 chars for 13s
        MAX_SENTENCES_PER_SCENE = 3
        
        # Smart grouping: 2-3 sentences per scene for smoother visuals
        grouped_scenes = []
        group = []
        group_chars = 0
        
        for sentence in sentences:
            sentence_chars = len(sentence)
            
            # Check if adding this sentence would exceed limits
            if group and (
                len(group) >= MAX_SENTENCES_PER_SCENE or
                group_chars + sentence_chars > MAX_CHARS_PER_SCENE
            ):
                # Save current group and start new one
                grouped_scenes.append(group)
                group = [sentence]
                group_chars = sentence_chars
            else:
                group.append(sentence)
                group_chars += sentence_chars
        
        # Don't forget the last group
        if group:
            grouped_scenes.append(group)
        
        # Build scene objects with timing
        scenes = []
        word_timings = voiceover_data.get("word_timings", []) if voiceover_data else []
        total_audio_duration = voiceover_data.get("duration", 0) if voiceover_data else 0
        
        cumulative_chars = 0
        total_script_chars = sum(len(s) for s in sentences)
        
        for i, sentence_group in enumerate(grouped_scenes):
            combined_text = ". ".join(sentence_group)
            group_chars = len(combined_text)
            
            # Calculate timing based on audio data or estimate
            if total_audio_duration > 0 and total_script_chars > 0:
                # Proportional timing based on character count
                start_ratio = cumulative_chars / total_script_chars
                end_ratio = (cumulative_chars + group_chars) / total_script_chars
                
                scene_start = start_ratio * total_audio_duration
                scene_end = end_ratio * total_audio_duration
                duration = scene_end - scene_start
            else:
                # Estimate: ~15 chars per second
                duration = max(3, group_chars / 15)
                scene_start = None
                scene_end = None
            
            cumulative_chars += group_chars
            
            # Generate niche-relevant search keywords using AI (with video_type context)
            keywords = self._generate_visual_keywords(combined_text, niche, video_type)
            
            scenes.append({
                "index": i,
                "text": combined_text,
                "sentences": sentence_group,
                "keywords": keywords,
                "niche": niche,
                "video_type": video_type.value if video_type else None,
                "duration": duration,
                "start_time": scene_start,
                "end_time": scene_end,
                "char_count": group_chars
            })
        
        logger.info(f"Grouped {len(sentences)} sentences into {len(scenes)} scenes")
        return scenes
    
    def _generate_visual_keywords(
        self,
        scene_text: str,
        niche: Optional[str] = None,
        video_type: Optional[VideoType] = None
    ) -> str:
        """
        Generate niche-relevant search keywords for stock video/image search.
        Uses Claude to understand context and generate visually-searchable terms.
        Incorporates RAG stock keywords when video_type is provided.
        
        Args:
            scene_text: The scene's text content
            niche: Optional niche/topic (e.g., "AI automation", "fitness", "real estate")
            video_type: Optional VideoType for RAG-based keyword enhancement
        
        Returns:
            Search keywords optimized for stock video/image libraries
        """
        from anthropic import Anthropic
        
        # Get RAG stock keywords if video_type provided
        rag_keywords = []
        if video_type and self.rag:
            rag_keywords = self.get_stock_keywords_for_type(video_type)
            logger.info(f"RAG keywords for {video_type.value}: {rag_keywords[:5]}")
        
        try:
            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            
            niche_context = f"The overall video niche/topic is: {niche}" if niche else "No specific niche provided."
            
            # Include RAG keywords as guidance
            rag_context = ""
            if rag_keywords:
                rag_context = f"\nRECOMMENDED KEYWORDS FOR THIS VIDEO TYPE: {', '.join(rag_keywords[:8])}\nPrioritize these keywords when relevant to the scene."
            
            response = client.messages.create(
                model=os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001"),  # Fast and cheap for keyword generation
                max_tokens=100,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": f"""Generate 3-5 stock video search keywords for this scene.

SCENE TEXT: "{scene_text}"

{niche_context}
{rag_context}

RULES:
1. Keywords must be VISUALLY SEARCHABLE on Pexels/Pixabay
2. Focus on concrete visuals that represent the CONCEPT (not literal words)
3. Include the niche context in keyword selection
4. Prefer: people, actions, technology, nature, business settings
5. Avoid: abstract concepts, emotions, numbers, statistics

EXAMPLES:
- "90% of startups fail" → "entrepreneur working laptop startup office"
- "social media marketing" → "person smartphone social media marketing team"
- "fitness transformation" → "gym workout exercise fitness training"
- "AI automation business" → "robot artificial intelligence technology office"
- "real estate investing" → "house property keys real estate agent"

Return ONLY the keywords, space-separated, no explanation:"""
                }]
            )
            
            keywords = response.content[0].text.strip()
            
            # Clean up - remove any punctuation, ensure reasonable length
            keywords = re.sub(r'[^\w\s]', '', keywords)
            keywords = ' '.join(keywords.split()[:6])  # Max 6 words
            
            if not keywords or len(keywords) < 5:
                # Fallback to basic extraction with niche prefix
                return self._fallback_keywords(scene_text, niche, video_type)
            
            logger.info(f"AI keywords for scene: {keywords}")
            return keywords
            
        except Exception as e:
            logger.warning(f"AI keyword generation failed: {e}, using fallback")
            return self._fallback_keywords(scene_text, niche, video_type)
    
    def _fallback_keywords(
        self,
        scene_text: str,
        niche: Optional[str] = None,
        video_type: Optional[VideoType] = None
    ) -> str:
        """Fallback keyword extraction when AI is unavailable."""
        words = scene_text.lower().split()
        stopwords = {
            "this", "that", "with", "from", "have", "will", "your", "they",
            "been", "were", "being", "their", "there", "here", "what", "when",
            "about", "more", "some", "just", "like", "make", "know", "take",
            "then", "than", "them", "these", "those", "into", "over", "also",
            "percent", "100", "most", "people", "first", "year", "years"
        }
        keywords = [w for w in words if len(w) > 3 and w not in stopwords][:4]
        
        # Prepend RAG keywords if video_type provided
        if video_type and self.rag:
            rag_keywords = self.get_stock_keywords_for_type(video_type)[:2]
            keywords = rag_keywords + keywords
        # Or prepend niche keywords if available
        elif niche:
            niche_words = niche.lower().split()[:2]
            keywords = niche_words + keywords
        
        result = " ".join(keywords[:5]) if keywords else "professional business office technology"
        return result
    
    async def _generate_stock_video_visuals(
        self,
        scenes: List[Dict[str, Any]],
        aspect_ratio: AspectRatio,
        video_type: Optional[VideoType] = None
    ) -> List[Dict[str, Any]]:
        """Generate visuals using stock videos from Pexels/Pixabay."""
        orientation = "portrait" if aspect_ratio == AspectRatio.PORTRAIT else "landscape"
        visuals = []
        
        for scene in scenes:
            logger.info(f"Searching stock videos for: {scene['keywords']}")
            videos = await self.search_stock_videos(
                query=scene["keywords"],
                per_page=3,  # Get more options for better matching
                orientation=orientation
            )
            
            if videos:
                video = videos[0]  # Take best match
                # Download the video
                filename = f"scene_{scene['index']}_{datetime.now().strftime('%H%M%S')}.mp4"
                local_path = await self.download_video(video["url"], filename)
                
                visuals.append({
                    "type": "video",
                    "path": local_path,
                    "url": video["url"],
                    "duration": scene["duration"],
                    "source": video["source"],
                    "scene_text": scene["text"],
                    "video_type": video_type.value if video_type else None
                })
            else:
                # Fallback to generated image if no stock found
                logger.warning(f"No stock video found for: {scene['keywords']}, using generated image")
                size = "1080x1920" if aspect_ratio == AspectRatio.PORTRAIT else "1920x1080"
                if aspect_ratio == AspectRatio.SQUARE:
                    size = "1080x1080"
                    
                image = await self.generate_image(
                    prompt=scene["text"],
                    image_type=ImageType.GENERAL,
                    size=size
                )
                if image.success:
                    visuals.append({
                        "type": "image",
                        "url": image.url,
                        "duration": scene["duration"],
                        "source": "generated_fallback",
                        "scene_text": scene["text"],
                        "video_type": video_type.value if video_type else None
                    })
        
        return visuals
    
    async def _generate_image_visuals(
        self,
        scenes: List[Dict[str, Any]],
        aspect_ratio: AspectRatio,
        video_type: Optional[VideoType] = None,
        image_quality: ImageQuality = ImageQuality.BUDGET,
        reference_images: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate visuals using AI-generated images.

        When reference_images are provided, they are forwarded to generate_image()
        so the client's visual style is maintained across all video frames.
        """
        size = "1080x1920" if aspect_ratio == AspectRatio.PORTRAIT else "1920x1080"
        if aspect_ratio == AspectRatio.SQUARE:
            size = "1080x1080"
        
        visuals = []
        
        # Get visual style from RAG if video_type provided
        style_suffix = "professional, clean, modern, cohesive color palette, cinematic lighting"
        if video_type and self.rag:
            visual_spec = self.get_visual_settings(video_type)
            effects = visual_spec.get("effects", [])
            temp = visual_spec.get("temperature", "neutral")
            if effects:
                style_suffix = f"{', '.join(effects[:3])}, {temp} tones, cinematic"
        
        # Style consistency: track first image's style
        style_anchor = None
        
        for i, scene in enumerate(scenes):
            logger.info(f"Generating image {i+1}/{len(scenes)} ({image_quality.value} quality): {scene['text'][:50]}...")
            
            # Build prompt with style consistency
            prompt = f"{scene['text']}. {style_suffix}"
            if style_anchor and i > 0:
                # Inject style anchor for consistency
                prompt = f"{scene['text']}. Style: {style_anchor}. {style_suffix}"
            
            image = await self.generate_image(
                prompt=prompt,
                image_type=ImageType.GENERAL,
                size=size,
                quality=image_quality,
                reference_images=reference_images if reference_images else None,
            )
            
            if image.success:
                # Capture style anchor from first image's revised prompt
                if i == 0 and image.metadata.get('revised_prompt'):
                    # Extract key style elements from DALL-E's revised prompt
                    revised = image.metadata.get('revised_prompt', '')
                    # Take last 50 chars as style descriptor
                    style_anchor = revised.split('.')[-1].strip()[:100] if '.' in revised else revised[:100]
                    logger.info(f"🎨 Style anchor set: {style_anchor[:50]}...")
                
                visuals.append({
                    "type": "image",
                    "url": image.url,
                    "duration": scene["duration"],
                    "source": image.api_used,
                    "quality": image_quality.value,
                    "scene_text": scene["text"],
                    "video_type": video_type.value if video_type else None
                })
        
        return visuals
    
    async def _generate_animated_visuals(
        self,
        scenes: List[Dict[str, Any]],
        aspect_ratio: AspectRatio,
        video_type: Optional[VideoType] = None,
        image_quality: ImageQuality = ImageQuality.BUDGET
    ) -> List[Dict[str, Any]]:
        """Generate visuals using AI-animated images (Kling/Wan) - BATCH MODE."""
        size = "1080x1920" if aspect_ratio == AspectRatio.PORTRAIT else "1920x1080"
        if aspect_ratio == AspectRatio.SQUARE:
            size = "1080x1080"
        
        # Get visual style from RAG if video_type provided
        style_suffix = "professional, clean, modern, cohesive color palette, cinematic lighting"
        if video_type and self.rag:
            visual_spec = self.get_visual_settings(video_type)
            effects = visual_spec.get("effects", [])
            temp = visual_spec.get("temperature", "neutral")
            if effects:
                style_suffix = f"{', '.join(effects[:3])}, {temp} tones, cinematic"
        
        # STEP 1: Generate all images first with quality tier
        logger.info(f"📸 Generating {len(scenes)} images ({image_quality.value} quality)...")
        
        # Generate first image to establish style anchor
        first_image = await self.generate_image(
            prompt=f"{scenes[0]['text']}. {style_suffix}",
            image_type=ImageType.GENERAL,
            size=size,
            quality=image_quality
        )
        
        # Extract style anchor from first image
        style_anchor = None
        if first_image.success and first_image.metadata.get('revised_prompt'):
            revised = first_image.metadata.get('revised_prompt', '')
            style_anchor = revised.split('.')[-1].strip()[:100] if '.' in revised else revised[:100]
            logger.info(f"🎨 Style anchor for animation: {style_anchor[:50]}...")
        
        # Generate remaining images with style consistency
        remaining_tasks = [
            self.generate_image(
                prompt=f"{scene['text']}. Style: {style_anchor}. {style_suffix}" if style_anchor else f"{scene['text']}. {style_suffix}",
                image_type=ImageType.GENERAL,
                size=size,
                quality=image_quality
            )
            for scene in scenes[1:]
        ]
        
        remaining_images = await asyncio.gather(*remaining_tasks) if remaining_tasks else []
        images = [first_image] + list(remaining_images)
        
        # STEP 2: Submit all animation jobs with ENHANCED parameters
        logger.info(f"🎬 Submitting {len(images)} ENHANCED animation jobs to fal.ai...")
        animation_tasks = []
        for i, (scene, image) in enumerate(zip(scenes, images)):
            if image.success and image.url:
                # Determine aspect ratio from scene context
                aspect_ratio = "9:16" if aspect_ratio == AspectRatio.PORTRAIT else "16:9"
                if aspect_ratio == AspectRatio.SQUARE:
                    aspect_ratio = "1:1"
                
                # Enhanced animation prompt based on scene content
                animation_prompt = self._create_enhanced_animation_prompt(scene['text'], video_type)
                
                # Longer duration for better quality (but higher cost)
                animation_duration = min(5, max(3, int(scene["duration"])))  # 3-5 seconds for quality
                
                task = self.animate_image(
                    image_url=image.url,
                    prompt=animation_prompt,
                    duration=animation_duration,
                    model="kling",
                    aspect_ratio=aspect_ratio,
                    motion_strength=0.85,  # Higher motion for more dynamic videos
                    guidance_scale=8.0,    # Higher guidance for better prompt adherence
                    fps=30                 # Higher FPS for smoother motion
                )
                animation_tasks.append((i, task, scene, image))
                logger.info(f"   Scene {i+1}: {animation_duration}s, {aspect_ratio}, enhanced prompt")
            else:
                animation_tasks.append((i, None, scene, image))
        
        # STEP 3: Wait for all animations with ENHANCED parameters
        logger.info(f"⏳ Processing ENHANCED animations in parallel (5-15 minutes)...")
        visuals = [None] * len(scenes)  # Pre-allocate to maintain order
        
        for i, task, scene, image in animation_tasks:
            if task:
                animated = await task
                if animated and animated.get("video_url"):
                    visuals[i] = {
                        "type": "video",
                        "url": animated["video_url"],
                        "duration": scene["duration"],
                        "source": "ai_animation_kling_enhanced",
                        "scene_text": scene["text"],
                        "motion_strength": animated.get("motion_strength", 0.8),
                        "fps": animated.get("fps", 24)
                    }
                    logger.info(f"✅ Scene {i+1}/{len(scenes)} animated successfully (Enhanced Quality)")
                else:
                    logger.warning(f"⚠️ Scene {i+1} animation failed, using static image")
                    visuals[i] = {
                        "type": "image",
                        "url": image.url,
                        "duration": scene["duration"],
                        "source": "fallback_static",
                        "scene_text": scene["text"]
                    }
            else:
                # Use static image (image generation failed)
                if image.success and image.url:
                    visuals[i] = {
                        "type": "image",
                        "url": image.url,
                        "duration": scene["duration"],
                        "source": "generated_fallback",
                        "scene_text": scene["text"]
                    }
                else:
                    logger.error(f"❌ Scene {i+1}/{len(scenes)} failed completely")
        
        # Filter out None values (failed scenes)
        return [v for v in visuals if v is not None]
    
    async def _assemble_video(
        self,
        visuals: List[Dict[str, Any]],
        audio_path: Optional[str],
        aspect_ratio: AspectRatio,
        include_captions: bool,
        script: str,
        voiceover_data: Optional[Dict[str, Any]] = None,
        include_music: bool = False,
        music_url: Optional[str] = None,
        music_volume: float = 0.15
    ) -> Optional[str]:
        """
        Assemble final video using FFmpeg with:
        - Crossfade transitions between clips
        - Consistent Ken Burns effect
        - Color grading for visual continuity
        - Audio fade in/out at transitions
        - Word-highlighting subtitles (optional)
        - Background music (optional)
        """
        if not self.apis_available["ffmpeg"]:
            logger.error("FFmpeg not available")
            return None
        
        try:
            output_filename = f"final_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            output_path = self.output_dir / output_filename
            
            # Get dimensions based on aspect ratio
            if aspect_ratio == AspectRatio.PORTRAIT:
                width, height = 1080, 1920
            elif aspect_ratio == AspectRatio.LANDSCAPE:
                width, height = 1920, 1080
            else:
                width, height = 1080, 1080
            
            # Download and prepare all media files
            prepared_clips = []
            for i, visual in enumerate(visuals):
                duration = visual["duration"]
                
                if visual.get("path"):
                    source_path = visual["path"]
                elif visual.get("url"):
                    ext = "mp4" if visual["type"] == "video" else "jpg"
                    filename = f"visual_{i}.{ext}"
                    if ext == "mp4":
                        source_path = await self.download_video(visual["url"], filename)
                    else:
                        source_path = await self._download_image(visual["url"], filename)
                else:
                    continue
                
                if not source_path:
                    continue
                
                # Prepare clip with consistent formatting
                clip_path = await self._prepare_clip(
                    source_path=source_path,
                    duration=duration,
                    width=width,
                    height=height,
                    clip_index=i,
                    total_clips=len(visuals)
                )
                
                if clip_path:
                    prepared_clips.append({
                        "path": clip_path,
                        "duration": duration
                    })
            
            if not prepared_clips:
                logger.error("No clips prepared for assembly")
                return None
            
            logger.info(f"Assembling {len(prepared_clips)} clips with crossfade transitions...")
            
            # CRITICAL: Account for crossfade time reduction
            # Crossfades reduce total duration because clips overlap
            # Example: 8 clips × 8s = 64s, but with 7 crossfades × 0.5s = 64s - 3.5s = 60.5s
            crossfade_duration = 0.5
            num_transitions = len(prepared_clips) - 1 if len(prepared_clips) > 1 else 0
            crossfade_time_loss = num_transitions * crossfade_duration
            
            # Check if video will be too short AFTER crossfades
            if audio_path and num_transitions > 0:
                audio_duration = await self._get_audio_duration(audio_path)
                if audio_duration:
                    clips_total_duration = sum(c["duration"] for c in prepared_clips)
                    expected_final_duration = clips_total_duration - crossfade_time_loss
                    
                    if expected_final_duration < audio_duration:
                        # Need to extend clips to compensate for crossfade loss + audio length
                        shortfall = audio_duration - expected_final_duration
                        
                        # Distribute extension across ALL clips proportionally (not just last one)
                        # This prevents the last scene from being unnaturally long
                        extension_per_clip = shortfall / len(prepared_clips)
                        
                        for clip in prepared_clips:
                            clip["duration"] += extension_per_clip
                        
                        logger.info(f"Extended all clips by {extension_per_clip:.2f}s each to compensate for crossfades ({crossfade_time_loss:.1f}s loss) and match audio ({audio_duration:.1f}s)")
            
            # Use xfade for smooth transitions between clips
            if len(prepared_clips) == 1:
                # Single clip - no transitions needed
                final_video = prepared_clips[0]["path"]
            else:
                # Multiple clips - apply crossfade transitions
                final_video = await self._apply_crossfade_transitions(
                    clips=prepared_clips,
                    width=width,
                    height=height,
                    crossfade_duration=0.5  # 0.5 second crossfade
                )
            
            if not final_video:
                logger.error("Failed to create transitions")
                return None
            
            # Add audio with fade in/out
            if audio_path and os.path.exists(audio_path):
                final_with_audio = await self._add_audio_with_fades(
                    video_path=final_video,
                    audio_path=audio_path,
                    output_path=str(output_path),
                    fade_duration=0.3  # 0.3 second audio fade
                )
                if not final_with_audio:
                    logger.error("Failed to add audio")
                    return None
                
                current_video = final_with_audio
            else:
                # No audio - just copy the video
                shutil.copy(final_video, output_path)
                current_video = str(output_path)
            
            # Add word-highlighting subtitles if requested
            if include_captions and voiceover_data and voiceover_data.get("word_timings"):
                subtitle_path = str(output_path).replace(".mp4", "_with_subs.mp4")
                subtitle_video = await self._add_word_highlighting_subtitles(
                    video_path=current_video,
                    word_timings=voiceover_data["word_timings"],
                    output_path=subtitle_path,
                    width=width,
                    height=height
                )
                if subtitle_video and os.path.exists(subtitle_video):
                    current_video = subtitle_video
                    logger.info("Subtitles added successfully")
            
            # Add background music if requested
            if include_music and music_url:
                music_path = str(output_path).replace(".mp4", "_with_music.mp4")
                music_video = await self._add_background_music(
                    video_path=current_video,
                    audio_path=audio_path,
                    output_path=music_path,
                    music_url=music_url,
                    music_volume=music_volume
                )
                if music_video and os.path.exists(music_video):
                    current_video = music_video
                    logger.info("Background music added successfully")
            
            # Ensure final video is at the expected output path
            if current_video != str(output_path):
                shutil.copy(current_video, output_path)
            
            logger.info(f"Video assembled successfully: {output_path}")
            return str(output_path)
                
        except Exception as e:
            logger.error(f"Video assembly error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _prepare_clip(
        self,
        source_path: str,
        duration: float,
        width: int,
        height: int,
        clip_index: int,
        total_clips: int
    ) -> Optional[str]:
        """
        Prepare a clip with consistent formatting:
        - Scale to target dimensions
        - Apply Ken Burns effect (for images)
        - Apply color grading for consistency
        - Trim to exact duration
        """
        try:
            output_path = self.temp_dir / f"prepared_clip_{clip_index}_{datetime.now().strftime('%H%M%S%f')}.mp4"
            
            is_image = source_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
            
            # Consistent Ken Burns parameters based on clip position
            # Alternate between zoom-in and zoom-out for variety
            if clip_index % 2 == 0:
                # Zoom in (1.0 to 1.15)
                zoom_start, zoom_end = 1.0, 1.15
            else:
                # Zoom out (1.15 to 1.0)
                zoom_start, zoom_end = 1.15, 1.0
            
            # Calculate pan direction based on position
            pan_directions = ['center', 'left', 'right', 'up', 'down']
            pan_dir = pan_directions[clip_index % len(pan_directions)]
            
            if is_image:
                # Image: Apply Ken Burns zoom/pan effect
                frames = int(duration * 30)  # 30 fps
                
                # Build zoompan filter with smooth motion
                if pan_dir == 'center':
                    x_expr = f"(iw-ow)/2"
                    y_expr = f"(ih-oh)/2"
                elif pan_dir == 'left':
                    x_expr = f"(iw-ow)*(1-on/{frames})"
                    y_expr = f"(ih-oh)/2"
                elif pan_dir == 'right':
                    x_expr = f"(iw-ow)*(on/{frames})"
                    y_expr = f"(ih-oh)/2"
                elif pan_dir == 'up':
                    x_expr = f"(iw-ow)/2"
                    y_expr = f"(ih-oh)*(1-on/{frames})"
                else:  # down
                    x_expr = f"(iw-ow)/2"
                    y_expr = f"(ih-oh)*(on/{frames})"
                
                zoom_expr = f"'{zoom_start}+(({zoom_end}-{zoom_start})*on/{frames})'"
                
                filter_complex = (
                    f"scale={width*2}:{height*2}:force_original_aspect_ratio=decrease,"
                    f"pad={width*2}:{height*2}:(ow-iw)/2:(oh-ih)/2,"
                    f"zoompan=z={zoom_expr}:x='{x_expr}':y='{y_expr}':d={frames}:s={width}x{height}:fps=30,"
                    f"eq=saturation=1.05:contrast=1.02,"  # Slight color boost for consistency
                    f"format=yuv420p"
                )
                
                cmd = [
                    self._ffmpeg_exe, "-y",
                    "-loop", "1",
                    "-i", source_path,
                    "-t", str(duration),
                    "-vf", filter_complex,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "20",
                    "-r", "30",
                    str(output_path)
                ]
            else:
                # Video: Scale, trim, and apply color grading
                # If source video is shorter than needed, loop it
                filter_complex = (
                    f"loop=loop=-1:size=32767,"  # Loop video if needed
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                    f"eq=saturation=1.05:contrast=1.02,"  # Match image color grading
                    f"fps=30,"
                    f"format=yuv420p"
                )
                
                cmd = [
                    self._ffmpeg_exe, "-y",
                    "-stream_loop", "-1",  # Loop input if shorter than duration
                    "-i", source_path,
                    "-t", str(duration),
                    "-vf", filter_complex,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "20",
                    "-an",  # Remove audio from clip (we'll add voiceover later)
                    str(output_path)
                ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0 and output_path.exists():
                return str(output_path)
            else:
                logger.error(f"Clip preparation failed: {result.stderr[:500]}")
                return None
                
        except Exception as e:
            logger.error(f"Clip preparation error: {str(e)}")
            return None
    
    async def _apply_crossfade_transitions(
        self,
        clips: List[Dict[str, Any]],
        width: int,
        height: int,
        crossfade_duration: float = 0.5
    ) -> Optional[str]:
        """
        Apply smooth crossfade transitions between all clips.
        Uses FFmpeg xfade filter for professional dissolve effects.
        """
        try:
            if len(clips) < 2:
                return clips[0]["path"] if clips else None
            
            # Build inputs
            inputs = []
            for clip in clips:
                inputs.extend(["-i", clip["path"]])
            
            # Build xfade filter chain
            # Each xfade combines two streams into one
            filter_parts = []
            current_stream = "[0:v]"
            
            for i in range(1, len(clips)):
                next_stream = f"[{i}:v]"
                output_stream = f"[v{i}]" if i < len(clips) - 1 else "[vout]"
                
                # Calculate offset (when the transition starts)
                # Account for previous crossfades shortening the video
                offset = sum(c["duration"] for c in clips[:i]) - (crossfade_duration * i)
                offset = max(0.1, offset)  # Ensure positive offset
                
                # Use dissolve transition for smooth blending
                filter_parts.append(
                    f"{current_stream}{next_stream}xfade=transition=dissolve:duration={crossfade_duration}:offset={offset:.2f}{output_stream}"
                )
                
                current_stream = output_stream
            
            filter_complex = ";".join(filter_parts)
            
            output_path = self.temp_dir / f"crossfade_{datetime.now().strftime('%H%M%S%f')}.mp4"
            
            cmd = [
                self._ffmpeg_exe, "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-r", "30",
                str(output_path)
            ]
            
            logger.info("Applying crossfade transitions...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0 and output_path.exists():
                return str(output_path)
            else:
                logger.warning(f"Crossfade failed, falling back to concat: {result.stderr[:300]}")
                # Fallback to simple concatenation
                return await self._simple_concat(clips)
                
        except Exception as e:
            logger.error(f"Crossfade error: {str(e)}")
            return await self._simple_concat(clips)
    
    async def _simple_concat(self, clips: List[Dict[str, Any]]) -> Optional[str]:
        """Simple concatenation fallback without transitions."""
        try:
            concat_file = self.temp_dir / "concat.txt"
            with open(concat_file, "w") as f:
                for clip in clips:
                    f.write(f"file '{clip['path']}'\n")
            
            output_path = self.temp_dir / f"concat_{datetime.now().strftime('%H%M%S%f')}.mp4"
            
            cmd = [
                self._ffmpeg_exe, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                return str(output_path)
            return None
        except Exception:
            return None
    
    async def _add_audio_with_fades(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        fade_duration: float = 0.3
    ) -> Optional[str]:
        """
        Add audio to video with fade in at start and fade out at end.
        This creates smooth audio transitions instead of abrupt starts/stops.
        """
        try:
            # Get audio duration for fade out timing
            audio_duration = await self._get_audio_duration(audio_path)
            if not audio_duration:
                audio_duration = 60  # Default fallback
            
            fade_out_start = max(0, audio_duration - fade_duration)
            
            # Audio filter: fade in at start, fade out at end
            audio_filter = f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_out_start:.2f}:d={fade_duration}"
            
            # CRITICAL: Use audio duration as master (don't cut it off)
            # If video is shorter, last frame will freeze
            # If audio is shorter, video will be cut
            cmd = [
                self._ffmpeg_exe, "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "libx264",  # Need to re-encode to extend if needed
                "-af", audio_filter,
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(audio_duration),  # Use audio duration as master
                output_path
            ]
            
            logger.info("Adding audio with fade effects...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0 and Path(output_path).exists():
                logger.info(f"Audio added successfully")
                return output_path
            else:
                logger.error(f"Audio merge failed: {result.stderr[:300]}")
                # Fallback: just copy video without audio effects
                shutil.copy(video_path, output_path)
                return output_path
                
        except Exception as e:
            logger.error(f"Audio merge error: {str(e)}")
            return None
    
    async def _add_word_highlighting_subtitles(
        self,
        video_path: str,
        word_timings: List[Dict[str, Any]],
        output_path: str,
        width: int = 1080,
        height: int = 1920
    ) -> Optional[str]:
        """
        Add word-by-word highlighting subtitles using ElevenLabs timestamps.
        Creates karaoke-style captions where current word is highlighted in yellow.
        
        Approach: Generate ASS subtitle file for precise word-level styling.
        """
        try:
            if not word_timings:
                logger.warning("No word timings available for subtitles")
                return video_path
            
            # Group words into lines (max 3 words per line for readability)
            lines = []
            current_line = []
            
            for i, word_data in enumerate(word_timings):
                current_line.append(word_data)
                
                # Start new line after 3 words or at punctuation
                if len(current_line) >= 3 or word_data["word"].rstrip('.,!?') != word_data["word"]:
                    lines.append(current_line)
                    current_line = []
            
            if current_line:
                lines.append(current_line)
            
            # Get font configuration from RAG or use defaults
            font_family = "Arial"  # Default
            font_size = 60  # Default
            font_bold = -1  # Bold by default
            
            # Note: video_type not available in this context, using defaults
            logger.info(f"Using default font: {font_family}, size {font_size}")
            
            # Create ASS subtitle file for precise word-level styling
            ass_content = f"""[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{font_bold},0,0,0,100,100,0,0,1,3,0,2,10,10,100,1
Style: Highlight,{font_family},{font_size},&H0000FFFF,&H000000FF,&H00000000,&H80000000,{font_bold},0,0,0,100,100,0,0,1,3,0,2,10,10,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            
            def format_time(seconds: float) -> str:
                """Convert seconds to ASS time format (H:MM:SS.cc)"""
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                cs = int((seconds % 1) * 100)
                return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
            
            # Generate dialogue lines with karaoke effect
            for line_words in lines:
                if not line_words:
                    continue
                
                line_start = line_words[0]["start_time"]
                line_end = line_words[-1]["end_time"]
                
                # For each word timing, create a subtitle event showing the whole line
                # with the current word highlighted
                for word_idx, current_word in enumerate(line_words):
                    word_start = current_word["start_time"]
                    word_end = current_word["end_time"]
                    
                    # Build the line with inline color tags
                    # {\c&H00FFFF&} = yellow (BGR format)
                    # {\c&HFFFFFF&} = white
                    parts = []
                    for idx, w in enumerate(line_words):
                        word_text = w["word"].upper().replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
                        if idx == word_idx:
                            # Current word in yellow
                            parts.append("{\\c&H00FFFF&}" + word_text + "{\\c&HFFFFFF&}")
                        else:
                            parts.append(word_text)
                    
                    line_text = " ".join(parts)
                    
                    # Add dialogue event
                    start_time = format_time(word_start)
                    end_time = format_time(word_end)
                    ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{line_text}\n"
            
            # Write ASS file - put it in same directory as video for simpler path handling
            video_dir = Path(video_path).parent
            ass_path = video_dir / "subtitles.ass"
            with open(ass_path, 'w', encoding='utf-8') as f:
                f.write(ass_content)
            
            logger.info(f"Created ASS subtitle file with {len(word_timings)} words at {ass_path}")
            
            # Apply subtitles using FFmpeg
            # Change working directory to video location for simpler path handling
            original_cwd = os.getcwd()
            os.chdir(video_dir)
            
            try:
                video_name = Path(video_path).name
                output_name = Path(output_path).name
                
                cmd = [
                    self._ffmpeg_exe, "-y",
                    "-i", video_name,
                    "-vf", "subtitles=subtitles.ass",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "20",
                    "-c:a", "copy",
                    output_name
                ]
                
                logger.info(f"Adding word-highlighting subtitles ({len(word_timings)} words)...")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
            finally:
                os.chdir(original_cwd)  # Always restore original directory
            
            if result.returncode == 0 and Path(output_path).exists():
                logger.info("Word-highlighting subtitles added successfully")
                # Clean up ASS file
                try:
                    os.remove(ass_path)
                except:
                    pass
                return output_path
            else:
                logger.error(f"Subtitle rendering failed: {result.stderr[:500]}")
                return video_path  # Return original if subtitles fail
                
        except Exception as e:
            logger.error(f"Subtitle error: {str(e)}")
            return video_path
    
    async def _add_background_music(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        music_url: Optional[str] = None,
        music_volume: float = 0.15,
        sound_effects: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[str]:
        """
        Add background music and sound effects to video with voiceover.
        
        Args:
            video_path: Path to video with voiceover
            audio_path: Path to voiceover audio (for ducking reference)
            output_path: Output path
            music_url: URL to background music (if None, uses stock music)
            music_volume: Music volume (0.0-1.0), default 0.15 for subtle background
            sound_effects: List of {"url": str, "time": float, "volume": float}
        
        Mix Strategy:
            - Voiceover: 100% volume (main audio)
            - Music: 15% volume, ducked to 5% when voiceover is active
            - Sound effects: 30% volume at specific timestamps
        """
        try:
            # Download background music if provided
            music_path = None
            if music_url:
                logger.info(f"Music URL provided: {music_url}")
                music_path = await self._download_audio(music_url, "background_music.mp3")
            else:
                # Use free stock music from Pixabay Music Library or local fallback
                # For now, skip music if no URL provided
                logger.info("No background music URL provided, skipping music")
                return video_path
            
            if not music_path or not os.path.exists(music_path):
                logger.warning(f"Music file not available at: {music_path}")
                return video_path
            
            logger.info(f"Music file ready at: {music_path}")
            
            # Build audio filter for mixing
            # [0:a] = voiceover from video
            # [1:a] = background music (looped if needed)
            
            # Get voiceover duration to loop music if needed
            voice_duration = await self._get_audio_duration(audio_path)
            logger.info(f"Voice duration for music loop: {voice_duration:.1f}s")
            
            # Audio filter complex - SIMPLER version for better compatibility:
            # 1. Loop music to match video duration
            # 2. Reduce music volume
            # 3. Mix with original audio using amerge + pan
            # Using a simpler approach without sidechaincompress for better compatibility
            
            audio_filter = (
                f"[1:a]aloop=loop=-1:size=2e+09,atrim=duration={voice_duration},"
                f"volume={music_volume}[music];"
                f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[mixed]"
            )
            
            cmd = [
                self._ffmpeg_exe, "-y",
                "-i", video_path,
                "-i", music_path,
                "-filter_complex", audio_filter,
                "-map", "0:v",
                "-map", "[mixed]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", str(voice_duration),  # Use voice duration as master
                output_path
            ]
            
            logger.info(f"Adding background music (volume: {music_volume*100:.0f}%)...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0 and Path(output_path).exists():
                logger.info("Background music added successfully")
                return output_path
            else:
                logger.error(f"Music mixing failed: {result.stderr[:500]}")
                return video_path
                
        except Exception as e:
            logger.error(f"Background music error: {str(e)}")
            return video_path
    
    async def _download_audio(self, url: str, filename: str) -> Optional[str]:
        """Download audio file from URL."""
        try:
            output_path = self.temp_dir / filename
            logger.info(f"Downloading audio from: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(output_path, 'wb') as f:
                            f.write(content)
                        file_size = os.path.getsize(output_path)
                        logger.info(f"Audio downloaded successfully: {filename} ({file_size/1024:.1f} KB)")
                        return str(output_path)
                    else:
                        logger.error(f"Audio download failed - HTTP {response.status}")
                        return None
        except asyncio.TimeoutError:
            logger.error(f"Audio download timed out: {url}")
            return None
        except Exception as e:
            logger.error(f"Audio download error: {str(e)}")
            return None
    
    async def _image_to_video(
        self,
        image_path: str,
        duration: float,
        width: int,
        height: int
    ) -> Optional[str]:
        """Legacy method - now handled by _prepare_clip for consistency."""
        # Delegate to _prepare_clip with default parameters
        return await self._prepare_clip(
            source_path=image_path,
            duration=duration,
            width=width,
            height=height,
            clip_index=0,
            total_clips=1
        )
    
    # =========================================================================
    # AGENT INTEGRATION METHODS
    # =========================================================================
    
    async def generate_media_for_content_idea(
        self,
        content_idea: ContentIdea,
        video_tier: VideoTier = VideoTier.STOCK_VIDEO  # Default to cheapest tier
    ) -> GeneratedMedia:
        """
        Generate media for a content idea from Marketing Intelligence Agent.
        Default tier is STOCK_VIDEO (FREE) - upgrade to AI_ANIMATION for premium.
        """
        logger.info(f"Generating media for content idea: {content_idea.topic}")
        
        if content_idea.content_type == "video":
            script = self._content_idea_to_script(content_idea)
            return await self.generate_video(
                script=script,
                tier=video_tier,
                style=VideoStyle.ENERGETIC,
                platform=content_idea.platform
            )
        elif content_idea.content_type == "carousel":
            return await self.generate_carousel_images(
                topic=content_idea.topic,
                slides=content_idea.hooks,
                platform=content_idea.platform
            )
        else:
            return await self.generate_image(
                prompt=f"{content_idea.topic}: {content_idea.angle}",
                image_type=ImageType.GENERAL,
                platform=content_idea.platform
            )
    
    def _content_idea_to_script(self, content_idea: ContentIdea) -> str:
        """Convert a content idea into a video script."""
        hook = content_idea.hooks[0] if content_idea.hooks else content_idea.topic
        
        script = f"{hook}. "
        script += f"Let me tell you about {content_idea.topic}. "
        script += f"{content_idea.angle}. "
        
        for i, point in enumerate(content_idea.hooks[1:], 1):
            script += f"Point {i}: {point}. "
        
        script += "Follow for more tips like this!"
        
        return script
    
    async def generate_carousel_images(
        self,
        topic: str,
        slides: List[str],
        platform: Platform = Platform.INSTAGRAM_FEED,
        style: str = "professional, clean, modern"
    ) -> GeneratedMedia:
        """Generate multiple images for a carousel post."""
        logger.info(f"Generating carousel with {len(slides)} slides for: {topic}")
        
        images = []
        for i, slide_text in enumerate(slides):
            prompt = f"Slide {i+1} of carousel about '{topic}': {slide_text}. {style}"
            
            result = await self.generate_image(
                prompt=prompt,
                image_type=ImageType.TEXT,
                size="1080x1080",
                platform=platform
            )
            
            if result.success:
                images.append({
                    "slide_number": i + 1,
                    "text": slide_text,
                    "url": result.url,
                    "api_used": result.api_used
                })
        
        return GeneratedMedia(
            success=len(images) > 0,
            media_type="carousel",
            tier_used="generated_images",
            metadata={
                "topic": topic,
                "total_slides": len(slides),
                "generated_slides": len(images),
                "images": images
            },
            cost_estimate=len(images) * 0.02
        )
    
    async def generate_media_for_post(
        self,
        post_content: str,
        content_type: str,
        platform: Platform,
        video_tier: VideoTier = VideoTier.STOCK_VIDEO,  # Default to cheapest tier
        slides: Optional[List[str]] = None
    ) -> GeneratedMedia:
        """Generate media for a post from Content Creation Agent."""
        logger.info(f"Generating {content_type} for {platform.value}")
        
        if content_type in ["video", "reel", "story"]:
            return await self.generate_video(
                script=post_content,
                tier=video_tier,
                platform=platform
            )
        elif content_type == "carousel" and slides:
            return await self.generate_carousel_images(
                topic=post_content,
                slides=slides,
                platform=platform
            )
        else:
            return await self.generate_image(
                prompt=post_content,
                image_type=ImageType.GENERAL,
                platform=platform
            )
    
    async def batch_generate_for_calendar(
        self,
        calendar_entries: List[Dict[str, Any]],
        video_tier: VideoTier = VideoTier.STOCK_VIDEO
    ) -> List[GeneratedMedia]:
        """
        Batch generate media for Content Calendar Agent.
        """
        logger.info(f"Batch generating media for {len(calendar_entries)} calendar entries")
        
        results = []
        for entry in calendar_entries:
            content_type = entry.get("content_type", "image")
            platform = Platform(entry.get("platform", "instagram_feed"))
            
            if content_type == "video":
                result = await self.generate_video(
                    script=entry.get("script", entry.get("topic", "")),
                    tier=video_tier,
                    platform=platform
                )
            else:
                result = await self.generate_image(
                    prompt=entry.get("topic", ""),
                    platform=platform
                )
            
            result.metadata["calendar_date"] = entry.get("date")
            result.metadata["calendar_day"] = entry.get("day")
            results.append(result)
        
        return results
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get generation statistics."""
        return {
            **self.stats,
            "apis_available": self.apis_available,
            "client_id": self.client_id
        }
    
    def reset_stats(self):
        """Reset generation statistics."""
        self.stats = {
            "videos_generated": 0,
            "images_generated": 0,
            "total_cost": 0.0,
            "api_calls": {
                "pexels": 0,
                "pixabay": 0,
                "elevenlabs": 0,
                "fal": 0,
                "ideogram": 0,
                "goapi": 0,
                "dalle": 0
            },
            "tier_usage": {
                "stock_video": 0,
                "generated_images": 0,
                "ai_animation": 0
            },
            "errors": 0
        }
    
    def get_available_apis(self) -> Dict[str, bool]:
        """Get which APIs are available."""
        return self.apis_available
    
    def get_available_tiers(self) -> List[str]:
        """Get which video tiers are available."""
        tiers = []
        if self.apis_available["pexels"] or self.apis_available["pixabay"]:
            tiers.append("stock_video")
        if self.apis_available["dalle"] or self.apis_available["ideogram"] or self.apis_available["goapi"]:
            tiers.append("generated_images")
        if self.apis_available["fal"]:
            tiers.append("ai_animation")
        return tiers
    
    async def test_apis(self) -> Dict[str, Any]:
        """Test all configured APIs."""
        results = {}
        
        # Test Pexels
        if self.apis_available["pexels"]:
            logger.info("Testing Pexels API...")
            videos = await self.search_stock_videos("nature", per_page=1)
            results["pexels"] = {"success": len(videos) > 0, "videos_found": len(videos)}
        
        # Test Pixabay
        if self.apis_available["pixabay"]:
            logger.info("Testing Pixabay API...")
            videos = await self._search_pixabay("nature", per_page=1)
            results["pixabay"] = {"success": len(videos) > 0, "videos_found": len(videos)}
        
        # Test ElevenLabs
        if self.apis_available["elevenlabs"]:
            logger.info("Testing ElevenLabs API...")
            voices = await self.get_elevenlabs_voices()
            results["elevenlabs"] = {"success": len(voices) > 0, "voices_found": len(voices)}
        
        # Test DALL-E
        if self.apis_available["dalle"]:
            logger.info("Testing DALL-E 3...")
            result = await self._generate_with_dalle(
                "A simple blue abstract background, no faces",
                "1024x1024"
            )
            results["dalle"] = {"success": result.success, "error": result.error}
        
        # Test fal.ai (just check auth, don't generate)
        if self.apis_available["fal"]:
            results["fal"] = {"success": True, "note": "API key configured - animation available"}
        
        # Test FFmpeg
        results["ffmpeg"] = {
            "success": self.apis_available["ffmpeg"],
            "note": "Video assembly available" if self.apis_available["ffmpeg"] else "Install FFmpeg for video assembly"
        }
        
        return results
    
    def cleanup_temp_files(self):
        """Clean up temporary files."""
        try:
            shutil.rmtree(self.temp_dir)
            self.temp_dir.mkdir(exist_ok=True)
            logger.info("Temp files cleaned up")
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")


# Convenience functions
async def generate_faceless_video(
    script: str,
    tier: str = "stock_video",  # Default to cheapest (FREE)
    platform: str = "instagram_reel",
    client_id: str = "default_client"
) -> GeneratedMedia:
    """
    Quick function to generate a faceless video.
    
    Tiers (in order of cost):
    - 'stock_video': FREE - Real Pexels/Pixabay footage
    - 'generated': ~$0.04/image - AI images with Ken Burns
    - 'ai_animation': ~$0.35/5sec - AI-animated images (Kling/Wan)
    """
    generator = FacelessGenerator(client_id)
    return await generator.generate_video(
        script=script,
        tier=VideoTier(tier),
        platform=Platform(platform)
    )


async def generate_faceless_image(
    prompt: str,
    image_type: str = "general",
    size: str = "1080x1080",
    client_id: str = "default_client"
) -> GeneratedMedia:
    """Quick function to generate a faceless image."""
    generator = FacelessGenerator(client_id)
    return await generator.generate_image(
        prompt=prompt,
        image_type=ImageType(image_type),
        size=size
    )


# Main for testing
if __name__ == "__main__":
    async def main():
        generator = FacelessGenerator()
        
        print("=" * 60)
        print("FACELESS GENERATOR - 3-TIER VIDEO SYSTEM")
        print("=" * 60)
        print(f"\nAPIs Available: {generator.get_available_apis()}")
        print(f"Available Tiers: {generator.get_available_tiers()}")
        print()
        
        # Test APIs
        print("Testing APIs...")
        results = await generator.test_apis()
        for api, result in results.items():
            status = "✅" if result.get("success") else "❌"
            print(f"  {api}: {status} - {result}")
        
        print()
        print(f"Stats: {generator.get_stats()}")
    
    asyncio.run(main())
