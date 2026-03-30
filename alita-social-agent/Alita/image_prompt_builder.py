"""
Image Prompt Builder
=====================
AI-powered prompt generator that uses the 51 loaded formula knowledge base
to craft production-ready image generation prompts.

Takes a creative brief (platform, model, concept) and assembles an optimized
prompt using the best-matching formulas, keywords, and model parameters.

Usage:
    python image_prompt_builder.py --platform instagram --model "flux 2" --concept "luxury watch product shot"
    python image_prompt_builder.py --platform facebook --concept "impossible craftsmanship violin made of glass"
    python image_prompt_builder.py --interactive

Modes:
    1. Local (no API) — assembles prompts from formula templates
    2. AI-Enhanced (Claude API) — uses Claude to refine and optimize the prompt
"""

import os
import sys
import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from image_prompt_engine import ImagePromptEngine

load_dotenv()


# ==================== CONFIGURATION ====================

DEFAULT_MODEL = "flux 2"
DEFAULT_PLATFORM = "instagram"
DEFAULT_ASPECT_RATIOS = {
    "instagram": "4:5",
    "facebook": "1:1",
    "linkedin": "1.91:1",
    "threads": "4:5",
    "x_twitter": "16:9",
    "twitter": "16:9",
}

MODEL_DEFAULTS = {
    "flux 2": {
        "suffix": "",
        "quality_tags": "4K, photorealistic, intricate detail, subsurface scattering",
        "negative_prompt": "",
    },
    "midjourney v7": {
        "suffix": "--ar {aspect_ratio} --s {stylize} --style raw --v 7",
        "quality_tags": "8k, ultra-detailed, professional photography",
        "negative_prompt": "--no cartoon, anime, blurry, text, watermarks, low quality",
    },
    "gpt image 1.5": {
        "suffix": "",
        "quality_tags": "photorealistic, high detail, professional lighting",
        "negative_prompt": "",
    },
}


# ==================== PROMPT ASSEMBLY ====================

class ImagePromptBuilder:
    """
    Builds production-ready image generation prompts using the formula knowledge base.
    """
    
    def __init__(self):
        self.engine = ImagePromptEngine()
        self._claude_client = None
    
    def _get_claude_client(self):
        """Lazy-load Claude client."""
        if self._claude_client is None:
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._claude_client = anthropic.Anthropic(api_key=api_key)
                else:
                    print("⚠️  No ANTHROPIC_API_KEY found — using local-only mode")
            except ImportError:
                print("⚠️  anthropic library not installed — using local-only mode")
        return self._claude_client
    
    def build_prompt(self,
                     concept: str,
                     platform: str = DEFAULT_PLATFORM,
                     model: str = DEFAULT_MODEL,
                     style: Optional[str] = None,
                     lighting: Optional[str] = None,
                     composition: Optional[str] = None,
                     aspect_ratio: Optional[str] = None,
                     use_ai: bool = False) -> Dict:
        """
        Build a complete image generation prompt.
        
        Args:
            concept: The creative concept/idea (e.g., "luxury watch on volcanic sand")
            platform: Target platform (instagram, facebook, linkedin, threads, x_twitter)
            model: Target AI model (flux 2, midjourney v7, gpt image 1.5)
            style: Optional style override (e.g., "cinematic", "editorial")
            lighting: Optional lighting override (e.g., "golden hour", "volumetric")
            composition: Optional composition override (e.g., "macro shot", "low angle")
            aspect_ratio: Override aspect ratio
            use_ai: If True, use Claude to refine the prompt
        
        Returns:
            Dict with prompt, metadata, and alternative suggestions
        """
        platform = platform.lower().replace(" ", "_").replace("/", "_")
        model_lower = model.lower().strip()
        
        # 1. Find matching formulas
        formulas = self._find_best_formulas(concept, platform, model_lower)
        
        # 2. Extract keywords and structure from matched formulas
        keywords = self._extract_relevant_keywords(formulas, concept)
        
        # 3. Get model-specific parameters
        model_config = self._get_model_config(model_lower)
        
        # 4. Determine aspect ratio
        ar = aspect_ratio or DEFAULT_ASPECT_RATIOS.get(platform, "1:1")
        
        # 5. Assemble the prompt
        if use_ai and self._get_claude_client():
            result = self._build_with_ai(concept, platform, model_lower, formulas, keywords, model_config, ar, style, lighting, composition)
        else:
            result = self._build_local(concept, platform, model_lower, formulas, keywords, model_config, ar, style, lighting, composition)
        
        return result
    
    def _find_best_formulas(self, concept: str, platform: str, model: str) -> List[Dict]:
        """Find the most relevant formulas for this request."""
        # Platform-specific formulas
        platform_formulas = self.engine.search(platform=platform, limit=5)
        
        # Model-specific formulas
        model_formulas = self.engine.search(model=model, limit=5)
        
        # Keyword-based formulas from concept
        concept_words = concept.lower().split()
        keyword_formulas = []
        for word in concept_words:
            if len(word) > 4:  # Skip short words
                results = self.engine.search(keyword=word, limit=3)
                keyword_formulas.extend(results)
        
        # Architecture formulas (always useful)
        arch_formulas = self.engine.search(category="prompt_architecture", limit=3)
        
        # Deduplicate by formula name
        seen = set()
        combined = []
        for f in platform_formulas + model_formulas + keyword_formulas + arch_formulas:
            if f["formula_name"] not in seen:
                seen.add(f["formula_name"])
                combined.append(f)
        
        return combined[:10]
    
    def _extract_relevant_keywords(self, formulas: List[Dict], concept: str) -> Dict[str, List[str]]:
        """Extract relevant semantic keywords from matched formulas."""
        keywords = {
            "lighting": [],
            "composition": [],
            "style": [],
            "quality": [],
            "mood": [],
            "material": [],
            "recommended_phrases": [],
        }
        
        for formula in formulas:
            data = formula["data"]
            
            # From semantic_keywords
            sem = data.get("semantic_keywords", {})
            if isinstance(sem, dict):
                for key, vals in sem.items():
                    if not isinstance(vals, list):
                        continue
                    key_lower = key.lower()
                    if "light" in key_lower:
                        keywords["lighting"].extend([str(v) for v in vals[:5]])
                    elif "compos" in key_lower or "camera" in key_lower or "angle" in key_lower:
                        keywords["composition"].extend([str(v) for v in vals[:5]])
                    elif "style" in key_lower or "aesthetic" in key_lower:
                        keywords["style"].extend([str(v) for v in vals[:5]])
                    elif "quality" in key_lower or "modifier" in key_lower:
                        keywords["quality"].extend([str(v) for v in vals[:5]])
                    elif "mood" in key_lower or "emotion" in key_lower:
                        keywords["mood"].extend([str(v) for v in vals[:5]])
                    elif "material" in key_lower or "texture" in key_lower:
                        keywords["material"].extend([str(v) for v in vals[:5]])
            
            # From model_params recommended_phrases
            params = data.get("model_params", {})
            if isinstance(params, dict):
                for model_name, model_data in params.items():
                    if isinstance(model_data, dict):
                        phrases = model_data.get("recommended_phrases", [])
                        keywords["recommended_phrases"].extend([str(p) for p in phrases[:5]])
                    elif isinstance(model_data, list):
                        keywords["recommended_phrases"].extend([str(p) for p in model_data[:5]])
        
        # Deduplicate
        for key in keywords:
            keywords[key] = list(dict.fromkeys(keywords[key]))[:10]
        
        return keywords
    
    def _get_model_config(self, model: str) -> Dict:
        """Get model-specific configuration."""
        for key, config in MODEL_DEFAULTS.items():
            if model in key or key in model:
                return config
        return MODEL_DEFAULTS.get("flux 2", {})
    
    def _build_local(self, concept, platform, model, formulas, keywords, model_config, aspect_ratio, style, lighting, composition) -> Dict:
        """Build prompt using local formula templates (no API)."""
        
        # Select best keywords
        lighting_choice = lighting or (keywords["lighting"][0] if keywords["lighting"] else "dramatic cinematic lighting")
        composition_choice = composition or (keywords["composition"][0] if keywords["composition"] else "medium shot, shallow depth of field")
        style_choice = style or (keywords["style"][0] if keywords["style"] else "cinematic, photorealistic")
        quality_tags = model_config.get("quality_tags", "4K, high detail")
        
        # Build the core prompt following the universal structure:
        # [Subject] + [Action/State] + [Context] + [Camera/Composition] + [Lighting] + [Style/Aesthetic] + [Quality]
        prompt_parts = [
            concept,
            composition_choice,
            lighting_choice,
            style_choice,
            quality_tags,
        ]
        
        core_prompt = ", ".join(prompt_parts)
        
        # Add model-specific suffix
        suffix = model_config.get("suffix", "")
        if suffix:
            suffix = suffix.format(
                aspect_ratio=aspect_ratio,
                stylize="200",
            )
            core_prompt += f" {suffix}"
        
        # Add negative prompt if applicable
        negative = model_config.get("negative_prompt", "")
        if negative:
            core_prompt += f" {negative}"
        
        # Build alternatives
        alternatives = self._generate_alternatives(concept, keywords, model_config, aspect_ratio)
        
        # Get example prompts from matched formulas
        example_prompts = []
        for formula in formulas[:3]:
            examples = self.engine.get_example_prompts(formula["id"])
            example_prompts.extend(examples)
        
        return {
            "prompt": core_prompt,
            "model": model,
            "platform": platform,
            "aspect_ratio": aspect_ratio,
            "alternatives": alternatives[:3],
            "matched_formulas": [f["formula_name"] for f in formulas[:5]],
            "keywords_used": keywords,
            "example_prompts": example_prompts[:3],
            "mode": "local",
        }
    
    def _generate_alternatives(self, concept, keywords, model_config, aspect_ratio) -> List[str]:
        """Generate alternative prompt variations."""
        alternatives = []
        
        # Variation 1: Different lighting
        if len(keywords["lighting"]) > 1:
            alt = f"{concept}, {keywords['composition'][0] if keywords['composition'] else 'wide shot'}, {keywords['lighting'][1]}, {model_config.get('quality_tags', '')}"
            alternatives.append(alt)
        
        # Variation 2: Different mood
        if keywords["mood"]:
            alt = f"{concept}, {keywords['mood'][0]}, {keywords['lighting'][0] if keywords['lighting'] else 'natural lighting'}, {model_config.get('quality_tags', '')}"
            alternatives.append(alt)
        
        # Variation 3: Recommended phrase mashup
        if keywords["recommended_phrases"]:
            phrases = ", ".join(keywords["recommended_phrases"][:3])
            alt = f"{concept}, {phrases}"
            alternatives.append(alt)
        
        return alternatives
    
    def _build_with_ai(self, concept, platform, model, formulas, keywords, model_config, aspect_ratio, style, lighting, composition) -> Dict:
        """Use Claude to build an optimized prompt."""
        client = self._get_claude_client()
        if not client:
            return self._build_local(concept, platform, model, formulas, keywords, model_config, aspect_ratio, style, lighting, composition)
        
        # Build context from formulas
        formula_context = []
        for f in formulas[:5]:
            data = f["data"]
            ps = data.get("prompt_structure", {})
            core = ps.get("core_formula", "") if isinstance(ps, dict) else ""
            example = ps.get("example_prompt", "") if isinstance(ps, dict) else ""
            formula_context.append(f"""
Formula: {f['formula_name']}
Core Structure: {core}
Example: {example}
""")
        
        # Build keyword context
        keyword_text = "\n".join([
            f"- {cat}: {', '.join(kws[:5])}"
            for cat, kws in keywords.items() if kws
        ])
        
        system_prompt = """You are an expert AI image generation prompt engineer specializing in Flux 2, Midjourney v7, and GPT Image 1.5.

Your job is to craft production-ready image prompts that are:
1. Optimized for the target model's architecture
2. Platform-appropriate for maximum engagement
3. Technically precise with camera, lighting, and composition specs
4. Emotionally resonant with the right mood and atmosphere

RULES:
- Output ONLY the prompt text, nothing else
- Follow the structure: [Subject] + [Action/State] + [Context] + [Camera/Composition] + [Lighting] + [Style/Aesthetic] + [Quality Modifiers]
- Use specific technical terms (lens specs, lighting types, color temperatures)
- Keep it 30-60 words for Flux 2, 40-80 words for Midjourney
- Include model-specific parameters at the end"""
        
        user_msg = f"""Create an optimized image generation prompt for:

CONCEPT: {concept}
PLATFORM: {platform}
MODEL: {model}
ASPECT RATIO: {aspect_ratio}
{f'STYLE: {style}' if style else ''}
{f'LIGHTING: {lighting}' if lighting else ''}
{f'COMPOSITION: {composition}' if composition else ''}

RELEVANT FORMULAS:
{''.join(formula_context)}

AVAILABLE KEYWORDS:
{keyword_text}

MODEL CONFIG:
Quality Tags: {model_config.get('quality_tags', '')}
Suffix: {model_config.get('suffix', '')}
Negative: {model_config.get('negative_prompt', '')}

Generate:
1. PRIMARY PROMPT (best version)
2. ALTERNATIVE 1 (different mood/lighting)
3. ALTERNATIVE 2 (different composition/style)

Format each on its own line, labeled."""

        try:
            # Use Haiku for cost efficiency
            haiku_model = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")
            
            response = client.messages.create(
                model=haiku_model,
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            )
            
            ai_text = response.content[0].text.strip()
            
            # Parse the response
            lines = [l.strip() for l in ai_text.split('\n') if l.strip()]
            primary = ""
            alts = []
            
            for line in lines:
                # Remove labels
                clean = re.sub(r'^(PRIMARY PROMPT|ALTERNATIVE \d|[123][\.\)]\s*)', '', line).strip()
                clean = re.sub(r'^[:\-]\s*', '', clean).strip()
                if not primary and clean:
                    primary = clean
                elif clean and clean != primary:
                    alts.append(clean)
            
            if not primary:
                primary = ai_text
            
            return {
                "prompt": primary,
                "model": model,
                "platform": platform,
                "aspect_ratio": aspect_ratio,
                "alternatives": alts[:3],
                "matched_formulas": [f["formula_name"] for f in formulas[:5]],
                "keywords_used": keywords,
                "ai_raw_response": ai_text,
                "mode": "ai_enhanced",
                "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            }
        except Exception as e:
            print(f"⚠️  AI enhancement failed: {e}. Falling back to local mode.")
            return self._build_local(concept, platform, model, formulas, keywords, model_config, aspect_ratio, style, lighting, composition)
    
    def interactive(self):
        """Interactive prompt builder session."""
        print("\n" + "="*60)
        print("🎨 Image Prompt Builder — Interactive Mode")
        print("="*60)
        print(f"📦 {len(self.engine.formulas)} formulas loaded")
        print(f"🤖 Models: Flux 2, Midjourney v7, GPT Image 1.5")
        print(f"📱 Platforms: Instagram, Facebook, LinkedIn, Threads, X/Twitter")
        print(f"Type 'quit' to exit\n")
        
        while True:
            concept = input("🎯 Concept: ").strip()
            if concept.lower() in ('quit', 'exit', 'q'):
                break
            
            platform = input(f"📱 Platform [{DEFAULT_PLATFORM}]: ").strip() or DEFAULT_PLATFORM
            model = input(f"🤖 Model [{DEFAULT_MODEL}]: ").strip() or DEFAULT_MODEL
            use_ai = input("🧠 Use AI enhancement? [y/N]: ").strip().lower() == 'y'
            
            print("\n⏳ Building prompt...\n")
            result = self.build_prompt(concept=concept, platform=platform, model=model, use_ai=use_ai)
            
            print(f"{'='*60}")
            print(f"✅ PRIMARY PROMPT ({result['mode']})")
            print(f"{'='*60}")
            print(f"\n{result['prompt']}\n")
            
            if result.get("alternatives"):
                print(f"📋 ALTERNATIVES:")
                for i, alt in enumerate(result["alternatives"], 1):
                    print(f"   {i}. {alt[:120]}...")
            
            if result.get("matched_formulas"):
                print(f"\n📐 Matched Formulas:")
                for f in result["matched_formulas"][:3]:
                    print(f"   • {f[:70]}")
            
            print(f"\n📏 Aspect Ratio: {result['aspect_ratio']}")
            print(f"{'='*60}\n")


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Image Prompt Builder")
    parser.add_argument('--concept', '-c', type=str, help='Creative concept')
    parser.add_argument('--platform', '-p', type=str, default=DEFAULT_PLATFORM, help='Target platform')
    parser.add_argument('--model', '-m', type=str, default=DEFAULT_MODEL, help='Target AI model')
    parser.add_argument('--style', type=str, help='Style override')
    parser.add_argument('--lighting', type=str, help='Lighting override')
    parser.add_argument('--composition', type=str, help='Composition override')
    parser.add_argument('--ar', type=str, help='Aspect ratio override')
    parser.add_argument('--ai', action='store_true', help='Use Claude AI enhancement')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()
    
    builder = ImagePromptBuilder()
    
    if args.interactive:
        builder.interactive()
        return
    
    if not args.concept:
        # Default to interactive
        builder.interactive()
        return
    
    result = builder.build_prompt(
        concept=args.concept,
        platform=args.platform,
        model=args.model,
        style=args.style,
        lighting=args.lighting,
        composition=args.composition,
        aspect_ratio=args.ar,
        use_ai=args.ai,
    )
    
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"🎨 Image Prompt ({result['mode']})")
        print(f"{'='*60}")
        print(f"\n{result['prompt']}\n")
        
        if result.get("alternatives"):
            print(f"📋 Alternatives:")
            for i, alt in enumerate(result["alternatives"], 1):
                print(f"   {i}. {alt}")
        
        print(f"\n📏 {result['model'].title()} | {result['platform'].title()} | {result['aspect_ratio']}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
