"""
Faceless Video Style Loader
===========================
Loads and parses deep research prompts from the faceless_video_prompts/ folder.
These are production-ready templates with specific technical settings for different
faceless video styles (reddit storytelling, horror, educational, motivational, etc.)

The client selects a style category, and it gets applied to their business content.
Flow: Marketing Agent → Content Data → Style Application → Faceless Video Script

Usage:
    from agents.faceless_style_loader import FacelessStyleLoader
    
    loader = FacelessStyleLoader()
    
    # List available categories
    categories = loader.list_categories()
    
    # Get all styles in a category
    styles = loader.list_styles_by_category("reddit_storytelling")
    
    # Get a specific style's production specs
    style = loader.get_style("reddit_storytelling", "Reddit_Aita_Story_Narration")
    
    # Get the best style for shorts
    style = loader.get_best_style_for_platform("reddit_storytelling", "youtube_shorts")
"""

import os
import re
import ast
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FacelessStyle:
    """
    A faceless video production style loaded from research prompts.
    Contains all technical specs for video production.
    """
    template_name: str
    category: str
    file_path: str
    platform: str = "Multi-platform"
    video_type: str = "General"
    
    # Technical specifications
    technical_specs: Dict[str, Any] = field(default_factory=dict)
    audio_specs: Dict[str, Any] = field(default_factory=dict)
    visual_specs: Dict[str, Any] = field(default_factory=dict)
    pacing_structure: List[Dict[str, Any]] = field(default_factory=list)
    content_guidelines: List[str] = field(default_factory=list)
    platform_optimization: Dict[str, Any] = field(default_factory=dict)
    production_examples: List[Dict[str, Any]] = field(default_factory=list)
    ai_generation_prompts: List[Dict[str, Any]] = field(default_factory=list)
    
    # Raw data for advanced usage
    raw_spec: Dict[str, Any] = field(default_factory=dict)
    
    def get_audio_config(self) -> Dict[str, Any]:
        """Get audio configuration for video generation."""
        return {
            "voice_type": self.audio_specs.get("voice_type", "AI voice"),
            "voice_pacing": self.audio_specs.get("voice_pacing", "150-170 wpm"),
            "music": self.audio_specs.get("music", "ambient"),
            "sfx": self.audio_specs.get("sfx", []),
            "audio_levels": self.audio_specs.get("audio_levels", {
                "voice_db": -2.0,
                "music_db": -20.0,
                "sfx_db": -15.0
            }),
            "audio_effects": self.audio_specs.get("audio_effects", {})
        }
    
    def get_visual_config(self) -> Dict[str, Any]:
        """Get visual configuration for video generation."""
        return {
            "scene_duration": self.visual_specs.get("scene_duration", {"min": 3, "max": 5}),
            "transition_style": self.visual_specs.get("transition_style", "cut"),
            "text_overlay": self.visual_specs.get("text_overlay", {}),
            "visual_elements": self.visual_specs.get("visual_elements", []),
            "color_scheme": self.visual_specs.get("color_scheme", "neutral"),
            "color_grading": self.visual_specs.get("color_grading_specs", 
                            self.visual_specs.get("color_grading", {})),
            "overlays": self.visual_specs.get("overlays", [])
        }
    
    def get_pacing_config(self) -> List[Dict[str, Any]]:
        """Get pacing/timing structure for video."""
        if isinstance(self.pacing_structure, list) and self.pacing_structure:
            # Handle both dict format and string format
            if isinstance(self.pacing_structure[0], dict):
                return self.pacing_structure
            else:
                # Convert string format to structured format
                return [{"description": item} for item in self.pacing_structure]
        return [{"segment": "Full Video", "content": "Standard pacing"}]
    
    def get_content_guidelines(self) -> List[str]:
        """Get content creation guidelines."""
        return self.content_guidelines or []
    
    def get_platform_settings(self, platform: str) -> Dict[str, Any]:
        """Get platform-specific optimization settings."""
        platform_map = {
            "youtube_shorts": "youtube_shorts",
            "youtube": "youtube_long_form",
            "tiktok": "tiktok",
            "instagram_reels": "instagram_reels",
            "instagram": "instagram_reels",
        }
        platform_key = platform_map.get(platform.lower(), platform.lower())
        return self.platform_optimization.get(platform_key, {})
    
    def get_elevenlabs_settings(self) -> Dict[str, Any]:
        """Extract ElevenLabs-specific voice settings from audio specs."""
        audio = self.audio_specs
        voice_type = audio.get("voice_type", "")
        
        settings = {
            "voice_id": None,  # To be set by user/default
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
        
        # Parse voice recommendations from the spec
        if "ElevenLabs" in voice_type.lower() or "elevenlabs" in str(audio).lower():
            # Check for voice recommendations
            if "Adam" in voice_type:
                settings["recommended_voice"] = "Adam"
            elif "baritone" in voice_type.lower():
                settings["recommended_voice"] = "Antoni"  # ElevenLabs baritone
            elif "female" in voice_type.lower():
                settings["recommended_voice"] = "Rachel"
            else:
                settings["recommended_voice"] = "Josh"  # Default male
        
        return settings
    
    def get_script_writing_prompt(self) -> str:
        """Generate a system prompt for script writing based on this style."""
        guidelines = "\n".join(f"- {g}" for g in self.content_guidelines[:10])
        
        audio_desc = self.audio_specs.get("voice_type", "professional narrator")
        visual_desc = self.visual_specs.get("color_scheme", "cinematic")
        
        pacing_desc = ""
        for p in self.pacing_structure[:5]:
            if isinstance(p, dict):
                pacing_desc += f"- {p.get('segment', 'Segment')}: {p.get('content', p.get('timing', ''))}\n"
            else:
                pacing_desc += f"- {p}\n"
        
        return f"""You are a professional faceless video script writer specializing in {self.category.replace('_', ' ').title()} content.

STYLE: {self.template_name}
VIDEO TYPE: {self.video_type}
TARGET PLATFORM: {self.platform}

VOICE STYLE:
{audio_desc}

VISUAL STYLE:
{visual_desc}

PACING STRUCTURE:
{pacing_desc}

CONTENT GUIDELINES:
{guidelines}

Write scripts that are optimized for this specific faceless video style. 
- Include clear scene/timing markers
- Write for the specified voice pacing
- Structure content according to the pacing template
- Include hooks and retention techniques specific to this style
"""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "template_name": self.template_name,
            "category": self.category,
            "platform": self.platform,
            "video_type": self.video_type,
            "technical_specs": self.technical_specs,
            "audio_specs": self.audio_specs,
            "visual_specs": self.visual_specs,
            "pacing_structure": self.pacing_structure,
            "content_guidelines": self.content_guidelines,
            "platform_optimization": self.platform_optimization
        }


class FacelessStyleLoader:
    """
    Loads faceless video production styles from the research prompts folder.
    
    These styles are comprehensive production templates generated from 
    deep research on successful faceless video channels.
    """
    
    def __init__(self, prompts_dir: Optional[str] = None):
        """
        Initialize the style loader.
        
        Args:
            prompts_dir: Path to faceless_video_prompts folder. 
                        Defaults to project root/faceless_video_prompts
        """
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            # Find the project root
            current = Path(__file__).parent.parent
            self.prompts_dir = current / "faceless_video_prompts"
        
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            self.prompts_dir = None
            self._styles_cache = {}
            self._categories = []
            return
        
        # Cache for loaded styles
        self._styles_cache: Dict[str, Dict[str, FacelessStyle]] = {}
        self._categories: List[str] = []
        
        # Load all categories
        self._load_categories()
        
        logger.info(f"FacelessStyleLoader initialized with {len(self._categories)} categories")
    
    def _load_categories(self):
        """Scan and load all available categories."""
        if not self.prompts_dir:
            return
            
        self._categories = []
        for item in self.prompts_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                self._categories.append(item.name)
                self._styles_cache[item.name] = {}
        
        self._categories.sort()
    
    def list_categories(self) -> List[str]:
        """List all available style categories."""
        return self._categories.copy()
    
    def list_styles_by_category(self, category: str) -> List[str]:
        """
        List all available styles within a category.
        
        Args:
            category: Category name (e.g., "reddit_storytelling")
            
        Returns:
            List of style names (filenames without extension)
        """
        if not self.prompts_dir:
            return []
            
        category_dir = self.prompts_dir / category
        if not category_dir.exists():
            logger.warning(f"Category not found: {category}")
            return []
        
        styles = []
        for file in category_dir.iterdir():
            if file.suffix == '.py' and not file.name.startswith('_'):
                styles.append(file.stem)
        
        return sorted(styles)
    
    def get_style(self, category: str, style_name: Optional[str] = None) -> Optional[FacelessStyle]:
        """
        Get a specific style from a category.
        
        Args:
            category: Category name (e.g., "reddit_storytelling")
            style_name: Specific style name, or None to get first/best style
            
        Returns:
            FacelessStyle object or None
        """
        if not self.prompts_dir:
            return None
            
        # Check cache first
        if category in self._styles_cache:
            if style_name and style_name in self._styles_cache[category]:
                return self._styles_cache[category][style_name]
        
        category_dir = self.prompts_dir / category
        if not category_dir.exists():
            return None
        
        # Find the file
        if style_name:
            file_path = category_dir / f"{style_name}.py"
            if not file_path.exists():
                # Try fuzzy match
                for f in category_dir.iterdir():
                    if style_name.lower() in f.stem.lower():
                        file_path = f
                        break
                else:
                    logger.warning(f"Style not found: {style_name} in {category}")
                    return None
        else:
            # Get first available style
            files = list(category_dir.glob("*.py"))
            if not files:
                return None
            file_path = files[0]
        
        # Parse and cache
        style = self._parse_style_file(file_path, category)
        if style:
            if category not in self._styles_cache:
                self._styles_cache[category] = {}
            self._styles_cache[category][style.template_name] = style
        
        return style
    
    def _parse_style_file(self, file_path: Path, category: str) -> Optional[FacelessStyle]:
        """
        Parse a style file and extract the production specs.
        
        The files contain Python dictionaries with all production settings.
        They may be wrapped in markdown code blocks (```python ... ```)
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # Remove markdown code block wrappers if present
            # Pattern: ```python ... ```
            if '```python' in content:
                # Extract content between ```python and ```
                import re
                code_blocks = re.findall(r'```python\s*(.*?)```', content, re.DOTALL)
                if code_blocks:
                    # Use the largest code block (the main spec)
                    content = max(code_blocks, key=len)
            
            # Find content between first { and matching }
            # This handles nested dicts
            start_idx = content.find('{')
            if start_idx == -1:
                logger.warning(f"No dict found in {file_path}")
                return None
            
            # Find matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(content[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            
            dict_str = content[start_idx:end_idx + 1]
            
            # Clean up the string for safe eval
            # Replace True/False/None with Python equivalents
            dict_str = dict_str.replace('true', 'True').replace('false', 'False')
            dict_str = dict_str.replace('null', 'None')
            
            # Try to safely evaluate
            try:
                spec = ast.literal_eval(dict_str)
            except (SyntaxError, ValueError) as e:
                # Try json parsing as fallback
                try:
                    # Convert Python dict syntax to JSON
                    json_str = dict_str.replace("'", '"')
                    json_str = re.sub(r'(\w+):', r'"\1":', json_str)
                    spec = json.loads(json_str)
                except:
                    logger.warning(f"Could not parse dict in {file_path}: {e}")
                    # Create minimal spec from file info
                    spec = {
                        "template_name": file_path.stem.replace('_', ' ').title(),
                        "category": category
                    }
            
            # Create FacelessStyle from spec
            return FacelessStyle(
                template_name=spec.get("template_name", file_path.stem.replace('_', ' ')),
                category=category,
                file_path=str(file_path),
                platform=spec.get("platform", "Multi-platform"),
                video_type=spec.get("video_type", "General"),
                technical_specs=spec.get("technical_specs", {}),
                audio_specs=spec.get("audio_specs", {}),
                visual_specs=spec.get("visual_specs", {}),
                pacing_structure=spec.get("pacing_structure", []),
                content_guidelines=spec.get("content_guidelines", []),
                platform_optimization=spec.get("platform_optimization", {}),
                production_examples=spec.get("production_examples", []),
                ai_generation_prompts=spec.get("ai_generation_prompts", []),
                raw_spec=spec
            )
            
        except Exception as e:
            logger.error(f"Error parsing style file {file_path}: {e}")
            return None
    
    def get_all_styles_in_category(self, category: str) -> List[FacelessStyle]:
        """Load and return all styles in a category."""
        styles = []
        for style_name in self.list_styles_by_category(category):
            style = self.get_style(category, style_name)
            if style:
                styles.append(style)
        return styles
    
    def get_best_style_for_platform(
        self, 
        category: str, 
        platform: str
    ) -> Optional[FacelessStyle]:
        """
        Get the best style in a category for a specific platform.
        
        Args:
            category: Style category (e.g., "reddit_storytelling")
            platform: Target platform (e.g., "youtube_shorts", "tiktok")
            
        Returns:
            FacelessStyle optimized for the platform
        """
        styles = self.get_all_styles_in_category(category)
        if not styles:
            return None
        
        # Score styles by platform optimization presence
        scored = []
        for style in styles:
            score = 0
            platform_settings = style.get_platform_settings(platform)
            if platform_settings:
                score += 10
                # Bonus for having detailed settings
                if "thumbnail" in platform_settings:
                    score += 2
                if "posting_time" in platform_settings:
                    score += 1
                if "optimization_focus" in platform_settings:
                    score += 1
            
            # Check if technical specs match platform
            tech = style.technical_specs
            if platform in ["youtube_shorts", "tiktok", "instagram_reels"]:
                if tech.get("aspect_ratio") == "9:16":
                    score += 5
                duration = tech.get("duration", {})
                if isinstance(duration, dict) and duration.get("max", 999) <= 60:
                    score += 3
            elif platform in ["youtube", "youtube_long_form"]:
                if tech.get("aspect_ratio") == "16:9":
                    score += 5
            
            scored.append((score, style))
        
        # Return highest scored
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None
    
    def search_styles(self, query: str) -> List[Tuple[str, str, FacelessStyle]]:
        """
        Search for styles matching a query.
        
        Args:
            query: Search term (e.g., "horror", "reddit", "motivational")
            
        Returns:
            List of (category, style_name, FacelessStyle) tuples
        """
        results = []
        query_lower = query.lower()
        
        for category in self._categories:
            # Check category name
            if query_lower in category.lower():
                for style_name in self.list_styles_by_category(category):
                    style = self.get_style(category, style_name)
                    if style:
                        results.append((category, style_name, style))
            else:
                # Check individual style names
                for style_name in self.list_styles_by_category(category):
                    if query_lower in style_name.lower():
                        style = self.get_style(category, style_name)
                        if style:
                            results.append((category, style_name, style))
        
        return results
    
    @property
    def total_styles(self) -> int:
        """Get total number of available styles."""
        count = 0
        for category in self._categories:
            count += len(self.list_styles_by_category(category))
        return count
    
    def get_category_summary(self) -> Dict[str, int]:
        """Get a summary of styles per category."""
        return {
            category: len(self.list_styles_by_category(category))
            for category in self._categories
        }


# Convenience function
def list_available_styles() -> Dict[str, List[str]]:
    """Quick function to list all available faceless video styles."""
    loader = FacelessStyleLoader()
    return {
        category: loader.list_styles_by_category(category)
        for category in loader.list_categories()
    }


# Category to friendly name mapping
CATEGORY_DISPLAY_NAMES = {
    "audio_music_sound": "🎵 Audio & Music",
    "educational_explainer": "📚 Educational",
    "facts_lists_countdown": "📊 Facts & Lists",
    "horror_dark_content": "👻 Horror & Dark",
    "lifestyle_aesthetic": "✨ Lifestyle",
    "monetization_strategy": "💰 Monetization",
    "motivational_content": "💪 Motivational",
    "platform_algorithm": "📈 Platform Growth",
    "reddit_storytelling": "📖 Reddit Stories",
    "self_help_psychology": "🧠 Self Help",
    "space_cosmic_science": "🌌 Space & Science",
    "technical_production": "🎬 Production",
    "transitions_pacing": "⚡ Transitions",
    "visual_style_effects": "🎨 Visual Effects",
    "voice_narration": "🎙️ Voice & Narration"
}


def get_category_display_name(category: str) -> str:
    """Get a friendly display name for a category."""
    return CATEGORY_DISPLAY_NAMES.get(category, category.replace('_', ' ').title())


if __name__ == "__main__":
    # Test the loader
    print("=" * 60)
    print("FACELESS STYLE LOADER TEST")
    print("=" * 60)
    
    loader = FacelessStyleLoader()
    
    print(f"\n📁 Total Styles: {loader.total_styles}")
    print(f"📂 Categories: {len(loader.list_categories())}")
    
    print("\n📋 Category Summary:")
    for category, count in loader.get_category_summary().items():
        display = get_category_display_name(category)
        print(f"   {display}: {count} styles")
    
    print("\n🔍 Testing Style Loading:")
    
    # Test reddit storytelling
    print("\n--- Reddit Storytelling ---")
    style = loader.get_style("reddit_storytelling")
    if style:
        print(f"   Template: {style.template_name}")
        print(f"   Platform: {style.platform}")
        audio = style.get_audio_config()
        print(f"   Voice: {audio.get('voice_type', 'N/A')[:60]}...")
        print(f"   Music: {audio.get('music', 'N/A')[:60]}...")
    
    # Test horror
    print("\n--- Horror Dark Content ---")
    style = loader.get_style("horror_dark_content")
    if style:
        print(f"   Template: {style.template_name}")
        visual = style.get_visual_config()
        print(f"   Color Scheme: {visual.get('color_scheme', 'N/A')}")
        print(f"   Transitions: {visual.get('transition_style', 'N/A')[:60]}...")
    
    # Test educational
    print("\n--- Educational Explainer ---")
    style = loader.get_style("educational_explainer")
    if style:
        print(f"   Template: {style.template_name}")
        pacing = style.get_pacing_config()
        print(f"   Pacing Segments: {len(pacing)}")
    
    # Test search
    print("\n🔎 Search Test (query='horror'):")
    results = loader.search_styles("horror")
    for cat, name, _ in results[:3]:
        print(f"   - {cat}/{name}")
    
    # Test platform optimization
    print("\n📱 Platform Optimization Test:")
    style = loader.get_best_style_for_platform("reddit_storytelling", "youtube_shorts")
    if style:
        print(f"   Best for YouTube Shorts: {style.template_name}")
        yt_settings = style.get_platform_settings("youtube_shorts")
        if yt_settings:
            print(f"   Optimal Duration: {yt_settings.get('optimal_duration', 'N/A')}")
    
    print("\n✅ Style Loader Test Complete")
