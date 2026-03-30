"""
Faceless Video RAG System
=========================
Retrieval-Augmented Generation system for faceless video production specifications.
Provides accurate, type-specific production guidance for video generation.
"""

import os
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class VideoCategory(Enum):
    """Main categories of faceless video content."""
    HORROR_DARK = "horror_dark"
    STORYTELLING = "storytelling"
    EDUCATIONAL = "educational"
    MOTIVATION = "motivation"
    RELAXATION = "relaxation"
    LISTS_FACTS = "lists_facts"
    LIFESTYLE = "lifestyle"
    GAMING = "gaming"
    COMMENTARY = "commentary"
    PRODUCT_TECH = "product_tech"
    INTERACTIVE = "interactive"
    AI_NATIVE = "ai_native"


@dataclass
class VideoTypeSpec:
    """Complete specification for a video type."""
    type_id: str
    category: str
    description: str
    examples: List[str]
    
    # Pacing & Transitions
    pacing_style: str
    transition_effects: List[str]
    scene_duration_range: Tuple[int, int]  # (min_seconds, max_seconds)
    
    # Audio
    music_genre: str
    music_bpm_range: Tuple[int, int]
    music_volume_percent: Tuple[int, int]
    sound_effects: List[str]
    audio_mood: str
    
    # Visuals
    color_saturation: int  # -100 to +100
    color_contrast: str  # "low", "normal", "high", "very_high"
    color_temperature: str  # "cool", "neutral", "warm"
    visual_effects: List[str]
    stock_keywords_primary: List[str]
    stock_keywords_secondary: List[str]
    
    # Voice
    voice_persona: str
    voice_tone: str
    speech_rate_wpm: Tuple[int, int]
    elevenlabs_voices: List[str]
    
    # Font settings (with defaults)
    font_family: str = "Arial"  # Font for captions/text overlays
    font_size: int = 60  # Default font size
    font_style: str = "Bold"  # Bold, Regular, etc.
    voice_effects: List[str] = field(default_factory=list)
    
    # Structure
    structure_template: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    monetization_potential: str = "medium"  # low, medium, high, very_high
    production_difficulty: str = "medium"  # low, medium, high


class FacelessRAG:
    """
    RAG system for faceless video production specifications.
    Loads knowledge base and provides retrieval for video type specifications.
    """
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        """Initialize the RAG system with knowledge base."""
        if knowledge_base_path is None:
            # Default path relative to this file
            base_dir = Path(__file__).parent.parent
            knowledge_base_path = base_dir / "Agent RAGs" / "Faceless Video RAG" / "faceless_video_types.txt"
        
        self.knowledge_base_path = Path(knowledge_base_path)
        self.video_types: Dict[str, VideoTypeSpec] = {}
        self.raw_knowledge: str = ""
        self.sections: Dict[str, str] = {}
        
        # Load and parse knowledge base
        self._load_knowledge_base()
        self._parse_video_types()
        
        logger.info(f"FacelessRAG initialized with {len(self.video_types)} video types")
    
    def _load_knowledge_base(self):
        """Load the knowledge base from file."""
        if not self.knowledge_base_path.exists():
            logger.warning(f"Knowledge base not found at {self.knowledge_base_path}")
            return
        
        with open(self.knowledge_base_path, 'r', encoding='utf-8') as f:
            self.raw_knowledge = f.read()
        
        # Split into sections
        section_pattern = r'={80}\nSECTION \d+: (.+?)\n={80}\n'
        parts = re.split(section_pattern, self.raw_knowledge)
        
        # First part is header, then alternating section names and content
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                section_name = parts[i].strip()
                section_content = parts[i + 1].strip()
                self.sections[section_name] = section_content
        
        logger.info(f"Loaded {len(self.sections)} sections from knowledge base")
    
    def _parse_video_types(self):
        """Parse video type specifications from the knowledge base."""
        if "VIDEO TYPE DEFINITIONS AND SPECIFICATIONS" not in self.sections:
            logger.warning("Video type definitions section not found")
            return
        
        content = self.sections["VIDEO TYPE DEFINITIONS AND SPECIFICATIONS"]
        
        # Split by video type markers
        type_blocks = re.split(r'\n---\n', content)
        
        for block in type_blocks:
            if "## TYPE:" not in block:
                continue
            
            try:
                spec = self._parse_type_block(block)
                if spec:
                    self.video_types[spec.type_id] = spec
            except Exception as e:
                logger.warning(f"Failed to parse video type block: {e}")
    
    def _parse_type_block(self, block: str) -> Optional[VideoTypeSpec]:
        """Parse a single video type block into a VideoTypeSpec."""
        # Extract type ID
        type_match = re.search(r'## TYPE: (\w+)', block)
        if not type_match:
            return None
        
        type_id = type_match.group(1)
        
        # Extract category
        category_match = re.search(r'CATEGORY: (.+)', block)
        category = category_match.group(1).strip() if category_match else "unknown"
        
        # Extract description
        desc_match = re.search(r'DESCRIPTION: (.+)', block)
        description = desc_match.group(1).strip() if desc_match else ""
        
        # Extract examples
        examples_match = re.search(r'EXAMPLES: (.+)', block)
        examples = [e.strip() for e in examples_match.group(1).split(',')] if examples_match else []
        
        # Parse sections
        pacing = self._extract_section(block, "PACING_TRANSITIONS")
        audio = self._extract_section(block, "AUDIO")
        visuals = self._extract_section(block, "VISUALS")
        voice = self._extract_section(block, "VOICE")
        structure = self._extract_section(block, "STRUCTURE")
        
        # Parse specific values from sections
        return VideoTypeSpec(
            type_id=type_id,
            category=category,
            description=description,
            examples=examples,
            
            # Pacing
            pacing_style=self._extract_value(pacing, "style", "moderate"),
            transition_effects=self._extract_list(pacing, "transitions"),
            scene_duration_range=self._extract_range(pacing, "Scene duration", (5, 10)),
            
            # Audio
            music_genre=self._extract_value(audio, "Background", "ambient"),
            music_bpm_range=self._extract_range(audio, "BPM", (80, 100)),
            music_volume_percent=self._extract_range(audio, "Music volume", (15, 20)),
            sound_effects=self._extract_list(audio, "Sound effects"),
            audio_mood=self._extract_value(audio, "mood", "neutral"),
            
            # Visuals
            color_saturation=self._extract_saturation(visuals),
            color_contrast=self._extract_value(visuals, "contrast", "normal").lower(),
            color_temperature=self._extract_value(visuals, "temperature", "neutral").lower(),
            visual_effects=self._extract_list(visuals, "effects"),
            stock_keywords_primary=self._extract_keywords(visuals, "Stock keywords"),
            stock_keywords_secondary=self._extract_keywords(visuals, "secondary"),
            font_family=self._extract_value(visuals, "Text overlay font", "Arial"),
            font_size=self._extract_font_size(visuals),
            font_style=self._extract_value(visuals, "Font style", "Bold"),
            
            # Voice
            voice_persona=self._extract_value(voice, "Persona", "Narrator"),
            voice_tone=self._extract_value(voice, "Tone", "neutral"),
            speech_rate_wpm=self._extract_range(voice, "Speech rate", (150, 170)),
            elevenlabs_voices=self._extract_list(voice, "ElevenLabs voices"),
            voice_effects=self._extract_list(voice, "effects"),
            
            # Structure
            structure_template=self._parse_structure(structure)
        )
    
    def _extract_section(self, block: str, section_name: str) -> str:
        """Extract a named section from a block."""
        pattern = rf'### {section_name}:\n(.*?)(?=\n### |\n---|\Z)'
        match = re.search(pattern, block, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _extract_value(self, text: str, key: str, default: str = "") -> str:
        """Extract a value for a key from text."""
        pattern = rf'{key}[:\s]+([^,\n]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else default
    
    def _extract_list(self, text: str, key: str) -> List[str]:
        """Extract a comma-separated list for a key."""
        pattern = rf'{key}[:\s]+([^\n]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            items = match.group(1).split(',')
            return [item.strip() for item in items if item.strip()]
        return []
    
    def _extract_range(self, text: str, key: str, default: Tuple[int, int]) -> Tuple[int, int]:
        """Extract a numeric range (e.g., '80-100' or '5-10 seconds')."""
        pattern = rf'{key}[:\s]*(\d+)[-–to]+(\d+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return default
    
    def _extract_saturation(self, text: str) -> int:
        """Extract saturation value (can be negative)."""
        pattern = r'[Ss]aturation[:\s]*([+-]?\d+)'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        
        # Check for descriptive saturation
        if "desaturated" in text.lower():
            return -30
        elif "high saturation" in text.lower():
            return 20
        return 0
    
    def _extract_keywords(self, text: str, key: str) -> List[str]:
        """Extract stock video keywords."""
        pattern = rf'{key}[:\s]+([^\n]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            keywords = match.group(1).split(',')
            return [kw.strip() for kw in keywords if kw.strip()]
        return []
    
    def _extract_font_size(self, text: str) -> int:
        """Extract font size from visual specs."""
        pattern = r'[Ff]ont size[:\s]*(\d+)'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        return 60  # Default size
    
    def _parse_structure(self, text: str) -> Dict[str, str]:
        """Parse structure template into dict."""
        structure = {}
        # Match patterns like [0-5s] HOOK: description
        pattern = r'\[(\d+-\d+s?)\]\s*(\w+)[:\s]+(.+?)(?=\[|\Z)'
        matches = re.findall(pattern, text, re.DOTALL)
        for timing, section, description in matches:
            structure[section] = {
                "timing": timing,
                "description": description.strip()
            }
        return structure
    
    # =========================================================================
    # PUBLIC RETRIEVAL METHODS
    # =========================================================================
    
    def get_video_type(self, type_id: str) -> Optional[VideoTypeSpec]:
        """Get full specification for a video type."""
        return self.video_types.get(type_id)
    
    def get_all_video_types(self) -> List[str]:
        """Get list of all available video type IDs."""
        return list(self.video_types.keys())
    
    def get_types_by_category(self, category: str) -> List[VideoTypeSpec]:
        """Get all video types in a category."""
        return [
            spec for spec in self.video_types.values()
            if category.lower() in spec.category.lower()
        ]
    
    def search_video_types(self, query: str) -> List[Tuple[str, float]]:
        """
        Search video types by query string.
        Returns list of (type_id, relevance_score) tuples.
        """
        query_lower = query.lower()
        results = []
        
        for type_id, spec in self.video_types.items():
            score = 0.0
            
            # Check type_id match
            if query_lower in type_id.lower():
                score += 1.0
            
            # Check category match
            if query_lower in spec.category.lower():
                score += 0.8
            
            # Check description match
            if query_lower in spec.description.lower():
                score += 0.6
            
            # Check examples match
            for example in spec.examples:
                if query_lower in example.lower():
                    score += 0.4
                    break
            
            # Check keywords match
            all_keywords = spec.stock_keywords_primary + spec.stock_keywords_secondary
            for keyword in all_keywords:
                if query_lower in keyword.lower():
                    score += 0.3
                    break
            
            if score > 0:
                results.append((type_id, score))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def get_audio_spec(self, type_id: str) -> Dict[str, Any]:
        """Get audio specifications for a video type."""
        spec = self.video_types.get(type_id)
        if not spec:
            return {}
        
        return {
            "music_genre": spec.music_genre,
            "bpm_range": spec.music_bpm_range,
            "volume_percent": spec.music_volume_percent,
            "sound_effects": spec.sound_effects,
            "mood": spec.audio_mood
        }
    
    def get_visual_spec(self, type_id: str) -> Dict[str, Any]:
        """Get visual specifications for a video type."""
        spec = self.video_types.get(type_id)
        if not spec:
            return {}
        
        return {
            "saturation": spec.color_saturation,
            "contrast": spec.color_contrast,
            "temperature": spec.color_temperature,
            "effects": spec.visual_effects,
            "stock_keywords": spec.stock_keywords_primary + spec.stock_keywords_secondary,
            "text_overlay": {
                "font": {
                    "family": spec.font_family,
                    "size": spec.font_size,
                    "bold": "Bold" in spec.font_style or "bold" in spec.font_style.lower()
                }
            }
        }
    
    def get_voice_spec(self, type_id: str) -> Dict[str, Any]:
        """Get voice specifications for a video type."""
        spec = self.video_types.get(type_id)
        if not spec:
            return {}
        
        return {
            "persona": spec.voice_persona,
            "tone": spec.voice_tone,
            "speech_rate_wpm": spec.speech_rate_wpm,
            "recommended_voices": spec.elevenlabs_voices,
            "effects": spec.voice_effects
        }
    
    def get_pacing_spec(self, type_id: str) -> Dict[str, Any]:
        """Get pacing and transition specifications for a video type."""
        spec = self.video_types.get(type_id)
        if not spec:
            return {}
        
        return {
            "style": spec.pacing_style,
            "transitions": spec.transition_effects,
            "scene_duration": spec.scene_duration_range,
            "structure": spec.structure_template
        }
    
    def get_stock_keywords(self, type_id: str, scene_text: Optional[str] = None) -> List[str]:
        """
        Get stock video keywords for a video type.
        Optionally combines with scene-specific keywords.
        """
        spec = self.video_types.get(type_id)
        if not spec:
            return []
        
        keywords = spec.stock_keywords_primary.copy()
        
        # Add secondary keywords if not enough primary
        if len(keywords) < 5:
            keywords.extend(spec.stock_keywords_secondary[:5 - len(keywords)])
        
        return keywords
    
    def get_complete_spec(self, type_id: str) -> Dict[str, Any]:
        """Get complete production specification as a dictionary."""
        spec = self.video_types.get(type_id)
        if not spec:
            return {}
        
        return {
            "type_id": spec.type_id,
            "category": spec.category,
            "description": spec.description,
            "examples": spec.examples,
            "pacing": self.get_pacing_spec(type_id),
            "audio": self.get_audio_spec(type_id),
            "visuals": self.get_visual_spec(type_id),
            "voice": self.get_voice_spec(type_id),
            "structure": spec.structure_template
        }
    
    def query(self, question: str, type_id: Optional[str] = None) -> str:
        """
        Natural language query against the knowledge base.
        Returns relevant information as formatted text.
        """
        question_lower = question.lower()
        
        # Determine what aspect is being asked about
        aspect = None
        if any(word in question_lower for word in ["audio", "music", "sound", "bpm"]):
            aspect = "audio"
        elif any(word in question_lower for word in ["visual", "color", "image", "stock", "footage"]):
            aspect = "visuals"
        elif any(word in question_lower for word in ["voice", "narration", "speech", "tone"]):
            aspect = "voice"
        elif any(word in question_lower for word in ["pacing", "transition", "structure", "timing"]):
            aspect = "pacing"
        
        # If type specified, get specific info
        if type_id:
            spec = self.get_complete_spec(type_id)
            if not spec:
                return f"Video type '{type_id}' not found in knowledge base."
            
            if aspect:
                return json.dumps(spec.get(aspect, {}), indent=2)
            return json.dumps(spec, indent=2)
        
        # Otherwise, search for relevant types
        results = self.search_video_types(question)
        if results:
            response = f"Found {len(results)} relevant video types:\n\n"
            for type_id, score in results[:5]:
                spec = self.video_types[type_id]
                response += f"**{type_id}** (relevance: {score:.1f})\n"
                response += f"  Category: {spec.category}\n"
                response += f"  {spec.description[:100]}...\n\n"
            return response
        
        return "No relevant information found for your query."
    
    def get_production_guide(self, type_id: str) -> str:
        """
        Generate a complete production guide for a video type.
        Returns formatted text suitable for use as system prompt context.
        """
        spec = self.video_types.get(type_id)
        if not spec:
            return f"Unknown video type: {type_id}"
        
        guide = f"""
# PRODUCTION GUIDE: {spec.type_id.upper().replace('_', ' ')}

## Category
{spec.category}

## Description
{spec.description}

## Reference Channels
{', '.join(spec.examples)}

---

## PACING & TRANSITIONS
- **Style**: {spec.pacing_style}
- **Scene Duration**: {spec.scene_duration_range[0]}-{spec.scene_duration_range[1]} seconds
- **Transitions**: {', '.join(spec.transition_effects) if spec.transition_effects else 'Standard cuts'}

## AUDIO SPECIFICATIONS
- **Music Genre**: {spec.music_genre}
- **BPM Range**: {spec.music_bpm_range[0]}-{spec.music_bpm_range[1]}
- **Volume**: {spec.music_volume_percent[0]}-{spec.music_volume_percent[1]}% of narration
- **Mood**: {spec.audio_mood}
- **Sound Effects**: {', '.join(spec.sound_effects) if spec.sound_effects else 'Minimal'}

## VISUAL SPECIFICATIONS
- **Saturation**: {spec.color_saturation:+d}%
- **Contrast**: {spec.color_contrast}
- **Temperature**: {spec.color_temperature}
- **Effects**: {', '.join(spec.visual_effects) if spec.visual_effects else 'None'}
- **Stock Keywords**: {', '.join(spec.stock_keywords_primary)}

## VOICE SPECIFICATIONS
- **Persona**: {spec.voice_persona}
- **Tone**: {spec.voice_tone}
- **Speech Rate**: {spec.speech_rate_wpm[0]}-{spec.speech_rate_wpm[1]} WPM
- **Recommended Voices**: {', '.join(spec.elevenlabs_voices)}

## STRUCTURE TEMPLATE
"""
        if spec.structure_template:
            for section, details in spec.structure_template.items():
                if isinstance(details, dict):
                    guide += f"- **[{details.get('timing', '')}] {section}**: {details.get('description', '')}\n"
                else:
                    guide += f"- **{section}**: {details}\n"
        
        return guide


# =========================================================================
# SINGLETON INSTANCE
# =========================================================================

_rag_instance: Optional[FacelessRAG] = None

def get_faceless_rag() -> FacelessRAG:
    """Get or create the singleton RAG instance."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = FacelessRAG()
    return _rag_instance


# =========================================================================
# CONVENIENCE FUNCTIONS
# =========================================================================

def get_video_spec(type_id: str) -> Dict[str, Any]:
    """Quick access to video type specification."""
    return get_faceless_rag().get_complete_spec(type_id)

def get_stock_keywords(type_id: str) -> List[str]:
    """Quick access to stock video keywords."""
    return get_faceless_rag().get_stock_keywords(type_id)

def get_voice_settings(type_id: str) -> Dict[str, Any]:
    """Quick access to voice settings."""
    return get_faceless_rag().get_voice_spec(type_id)

def get_audio_settings(type_id: str) -> Dict[str, Any]:
    """Quick access to audio settings."""
    return get_faceless_rag().get_audio_spec(type_id)

def get_visual_settings(type_id: str) -> Dict[str, Any]:
    """Quick access to visual settings."""
    return get_faceless_rag().get_visual_spec(type_id)

def search_types(query: str) -> List[str]:
    """Search for video types matching a query."""
    results = get_faceless_rag().search_video_types(query)
    return [type_id for type_id, _ in results]


if __name__ == "__main__":
    # Test the RAG system
    rag = FacelessRAG()
    
    print("Available video types:")
    for type_id in rag.get_all_video_types():
        print(f"  - {type_id}")
    
    print("\n" + "="*50)
    print("Testing horror_storytelling spec:")
    print(rag.get_production_guide("horror_storytelling"))
