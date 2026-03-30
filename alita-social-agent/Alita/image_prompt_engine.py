"""
Image Prompt Knowledge Engine
==============================
Central system that loads all 48 image generation prompt formulas,
indexes them, and provides intelligent search/lookup by:
  - Target model (Flux 2, Midjourney v7, GPT Image 1.5)
  - Platform (Instagram, Facebook, LinkedIn, Threads, X/Twitter)
  - Category (architecture, semantics, model-specific, platform, iteration, formula)
  - Keyword / semantic concept

Usage:
    from image_prompt_engine import ImagePromptEngine
    engine = ImagePromptEngine()
    
    # Find formulas for Instagram + Midjourney
    results = engine.search(platform="instagram", model="midjourney")
    
    # Find formulas about lighting
    results = engine.search(keyword="volumetric lighting")
    
    # Get all platform formulas
    results = engine.get_by_category("platform_specific_prompt_strategies")
    
    # Get a specific formula's full data
    formula = engine.get_formula("Instagram Anachronistic Mashup")
"""

import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# ==================== CONFIGURATION ====================
PROMPTS_DIR = Path(__file__).parent / "image_generation_prompts"

CATEGORY_LABELS = {
    "prompt_architecture_foundations": "Prompt Architecture & Structure",
    "model_specific_prompt_optimization": "Model-Specific Optimization",
    "platform_specific_prompt_strategies": "Platform-Specific Strategies",
    "formula_implementation_real_world": "Real-World Formula Implementation",
    "prompt_iteration_refinement_strategies": "Iteration & Refinement",
    "semantic_keyword_research_taxonomies": "Semantic Keyword Taxonomies",
}

SUPPORTED_MODELS = ["Flux 2", "Midjourney v7", "GPT Image 1.5"]
SUPPORTED_PLATFORMS = ["instagram", "facebook", "linkedin", "threads", "x_twitter", "twitter"]


# ==================== FORMULA LOADER ====================

def _extract_dicts_from_file(filepath: Path) -> List[Dict]:
    """
    Extract all top-level dictionary assignments from a Python file.
    Uses exec() for maximum compatibility with complex nested dicts.
    """
    formulas = []
    content = filepath.read_text(encoding='utf-8')
    
    # Primary: exec the file and grab all dict variables
    try:
        namespace = {}
        exec(compile(content, str(filepath), 'exec'), namespace)
        for key, val in namespace.items():
            if not key.startswith('_') and isinstance(val, dict) and len(val) > 0:
                formulas.append({
                    "variable_name": key,
                    "data": val,
                    "source_file": str(filepath.name),
                    "source_path": str(filepath),
                })
        if formulas:
            return formulas
    except Exception:
        pass
    
    # Fallback: AST-based extraction with literal_eval
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                        try:
                            dict_str = ast.get_source_segment(content, node.value)
                            if dict_str:
                                value = ast.literal_eval(dict_str)
                                formulas.append({
                                    "variable_name": target.id,
                                    "data": value,
                                    "source_file": str(filepath.name),
                                    "source_path": str(filepath),
                                })
                        except (ValueError, SyntaxError):
                            pass
    except Exception as e:
        print(f"⚠️  Could not parse {filepath.name}: {e}")
    
    return formulas


def _extract_docstring_metadata(filepath: Path) -> Dict[str, str]:
    """Extract metadata from the module docstring."""
    meta = {}
    try:
        content = filepath.read_text(encoding='utf-8')
        # Find the docstring
        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if match:
            docstring = match.group(1)
            for line in docstring.strip().split('\n'):
                line = line.strip()
                if ':' in line:
                    key, _, value = line.partition(':')
                    key = key.strip().lower().replace(' ', '_')
                    meta[key] = value.strip()
    except Exception:
        pass
    return meta


# ==================== ENGINE ====================

class ImagePromptEngine:
    """
    Central knowledge engine for all image generation prompt formulas.
    Loads, indexes, and provides intelligent access to 48 prompt formulas.
    """
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self.formulas: List[Dict] = []
        self._index_by_model: Dict[str, List[int]] = {}
        self._index_by_platform: Dict[str, List[int]] = {}
        self._index_by_category: Dict[str, List[int]] = {}
        self._index_by_name: Dict[str, int] = {}
        self._keyword_cache: Dict[str, List[str]] = {}
        
        self._load_all()
        self._build_indexes()
    
    def _load_all(self):
        """Load all formula files from all category directories."""
        loaded_structured = 0
        loaded_text = 0
        errors = 0
        
        for category_dir in sorted(self.prompts_dir.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith('_'):
                continue
            
            category = category_dir.name
            
            for py_file in sorted(category_dir.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                
                # Extract metadata from docstring
                meta = _extract_docstring_metadata(py_file)
                
                # Try to extract structured dicts first
                extracted = _extract_dicts_from_file(py_file)
                
                if extracted:
                    # We got structured data
                    for entry in extracted:
                        data = entry["data"]
                        if not isinstance(data, dict):
                            continue
                        if not any(k in data for k in ('formula_name', 'prompt_structure', 'semantic_keywords', 'model_params')):
                            continue
                        
                        formula_record = {
                            "id": len(self.formulas),
                            "variable_name": entry["variable_name"],
                            "formula_name": data.get("formula_name", entry["variable_name"]),
                            "research_area": data.get("research_area", meta.get("research_area", "")),
                            "formula_type": data.get("formula_type", meta.get("formula_type", "")),
                            "category": category,
                            "category_label": CATEGORY_LABELS.get(category, category),
                            "source_file": entry["source_file"],
                            "source_path": entry["source_path"],
                            "target_models": data.get("target_models", []),
                            "data": data,
                            "structured": True,
                        }
                        self.formulas.append(formula_record)
                        loaded_structured += 1
                else:
                    # No valid dict — load as text-based formula
                    text_record = self._load_as_text_formula(py_file, category, meta)
                    if text_record:
                        self.formulas.append(text_record)
                        loaded_text += 1
                    else:
                        errors += 1
        
        total = loaded_structured + loaded_text
        print(f"📦 ImagePromptEngine: Loaded {total} formulas "
              f"({loaded_structured} structured, {loaded_text} text-parsed, {errors} errors)")
    
    def _load_as_text_formula(self, filepath: Path, category: str, meta: Dict) -> Optional[Dict]:
        """
        Parse a file as raw text to extract formula info even from truncated files.
        This handles the 36 files whose Python dicts were truncated.
        """
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Extract formula_name
            name_match = re.search(r'"formula_name"\s*:\s*"([^"]+)"', content)
            formula_name = name_match.group(1) if name_match else filepath.stem.replace('_', ' ')
            
            # Extract target_models
            models_match = re.search(r'"target_models"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            target_models = []
            if models_match:
                target_models = re.findall(r'"([^"]+)"', models_match.group(1))
            
            # Extract research_area
            area_match = re.search(r'"research_area"\s*:\s*"([^"]+)"', content)
            research_area = area_match.group(1) if area_match else meta.get("research_area", "")
            
            # Extract formula_type
            type_match = re.search(r'"formula_type"\s*:\s*"([^"]+)"', content)
            formula_type = type_match.group(1) if type_match else meta.get("formula_type", "")
            
            # Extract core_formula
            core_match = re.search(r'"core_formula"\s*:\s*"([^"]+)"', content)
            core_formula = core_match.group(1) if core_match else ""
            
            # Extract example prompts
            example_prompts = re.findall(r'"example_prompt"\s*:\s*"([^"]+)"', content)
            
            # Extract all keyword lists
            keyword_lists = re.findall(r'"([^"]+)"', content)
            # Filter to meaningful keywords (3+ chars, not common dict keys)
            skip_keys = {'formula_name', 'research_area', 'formula_type', 'target_models',
                        'prompt_structure', 'core_formula', 'components', 'name', 'weight',
                        'position', 'description', 'examples', 'variables', 'model_params',
                        'strength', 'weakness', 'optimal_keywords', 'parameter_settings',
                        'guidance_scale', 'steps', 'sampler', 'other_params', 'recommended_phrases',
                        'semantic_keywords', 'platform_optimization', 'real_examples',
                        'a_b_testing', 'constraints', 'implementation_guide', 'performance_metrics',
                        'Primary', 'Secondary', 'Tertiary', 'True', 'False', 'N/A'}
            filtered_keywords = [kw for kw in keyword_lists 
                               if len(kw) > 3 and kw not in skip_keys and not kw.startswith('{')]
            
            # Extract recommended phrases per model
            model_phrases = {}
            for model in ["Flux 2", "Midjourney", "GPT Image"]:
                model_section = re.search(
                    rf'"{re.escape(model)}[^"]*"\s*:\s*\{{(.*?)(?:\}}\s*,|\}}\s*\}})', 
                    content, re.DOTALL
                )
                if model_section:
                    phrases = re.findall(r'"([^"]{10,})"', model_section.group(1))
                    if phrases:
                        model_phrases[model] = phrases[:10]
            
            # Build a pseudo-data dict from text parsing
            data = {
                "formula_name": formula_name,
                "research_area": research_area,
                "formula_type": formula_type,
                "target_models": target_models,
                "prompt_structure": {
                    "core_formula": core_formula,
                    "example_prompt": example_prompts[0] if example_prompts else "",
                },
                "semantic_keywords": {
                    "extracted_keywords": filtered_keywords[:50],
                },
                "model_params": model_phrases,
                "_raw_text": content,
                "_text_parsed": True,
            }
            
            return {
                "id": len(self.formulas),
                "variable_name": filepath.stem,
                "formula_name": formula_name,
                "research_area": research_area,
                "formula_type": formula_type,
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "source_file": filepath.name,
                "source_path": str(filepath),
                "target_models": target_models,
                "data": data,
                "structured": False,
            }
        except Exception as e:
            print(f"⚠️  Could not text-parse {filepath.name}: {e}")
            return None
    
    def _build_indexes(self):
        """Build lookup indexes for fast searching."""
        for i, formula in enumerate(self.formulas):
            # Index by model
            for model in formula.get("target_models", []):
                model_key = model.lower().strip()
                self._index_by_model.setdefault(model_key, []).append(i)
            
            # Index by platform (detect from formula name, source file, or category)
            name_lower = (formula["formula_name"] + " " + formula["source_file"]).lower()
            for platform in SUPPORTED_PLATFORMS:
                if platform.replace("_", " ") in name_lower or platform.replace("_", "") in name_lower:
                    self._index_by_platform.setdefault(platform, []).append(i)
            
            # Index by category
            self._index_by_category.setdefault(formula["category"], []).append(i)
            
            # Index by name (lowercased, simplified)
            name_key = re.sub(r'[^a-z0-9]+', '_', formula["formula_name"].lower()).strip('_')
            self._index_by_name[name_key] = i
            
            # Cache keywords
            data = formula["data"]
            keywords = []
            if "semantic_keywords" in data and isinstance(data["semantic_keywords"], dict):
                for key, vals in data["semantic_keywords"].items():
                    if isinstance(vals, list):
                        keywords.extend([str(v).lower() for v in vals])
                    elif isinstance(vals, str):
                        keywords.append(vals.lower())
            self._keyword_cache[str(i)] = keywords
        
        print(f"   📊 Indexed: {len(self._index_by_model)} models, "
              f"{len(self._index_by_platform)} platforms, "
              f"{len(self._index_by_category)} categories")
    
    # ==================== QUERY METHODS ====================
    
    def search(self, 
               platform: Optional[str] = None,
               model: Optional[str] = None, 
               category: Optional[str] = None,
               keyword: Optional[str] = None,
               limit: int = 10) -> List[Dict]:
        """
        Search formulas by platform, model, category, or keyword.
        Multiple filters are AND-combined.
        """
        candidate_ids = set(range(len(self.formulas)))
        
        # Filter by platform
        if platform:
            platform_key = platform.lower().replace(" ", "_").replace("/", "_")
            # Normalize twitter/x
            if platform_key in ("x", "twitter", "x_twitter"):
                platform_ids = set()
                for pk in ("x_twitter", "twitter"):
                    platform_ids.update(self._index_by_platform.get(pk, []))
                candidate_ids &= platform_ids
            else:
                candidate_ids &= set(self._index_by_platform.get(platform_key, []))
        
        # Filter by model
        if model:
            model_key = model.lower().strip()
            # Fuzzy match
            matched = set()
            for idx_model, ids in self._index_by_model.items():
                if model_key in idx_model or idx_model in model_key:
                    matched.update(ids)
            candidate_ids &= matched
        
        # Filter by category
        if category:
            cat_key = category.lower().replace(" ", "_")
            matched = set()
            for idx_cat, ids in self._index_by_category.items():
                if cat_key in idx_cat or idx_cat in cat_key:
                    matched.update(ids)
            candidate_ids &= matched
        
        # Filter by keyword
        if keyword:
            kw_lower = keyword.lower()
            matched = set()
            for idx in candidate_ids:
                formula = self.formulas[idx]
                # Search in formula name, keywords cache, and data keys
                searchable = (
                    formula["formula_name"].lower() + " " +
                    formula.get("research_area", "").lower() + " " +
                    formula.get("formula_type", "").lower() + " " +
                    " ".join(self._keyword_cache.get(str(idx), []))
                )
                if kw_lower in searchable:
                    matched.add(idx)
            candidate_ids = matched
        
        results = [self.formulas[i] for i in sorted(candidate_ids)]
        return results[:limit]
    
    def get_by_category(self, category: str) -> List[Dict]:
        """Get all formulas in a category."""
        return self.search(category=category, limit=100)
    
    def get_by_model(self, model: str) -> List[Dict]:
        """Get all formulas optimized for a specific model."""
        return self.search(model=model, limit=100)
    
    def get_by_platform(self, platform: str) -> List[Dict]:
        """Get all formulas for a specific platform."""
        return self.search(platform=platform, limit=100)
    
    def get_formula(self, name: str) -> Optional[Dict]:
        """Get a specific formula by name (fuzzy match)."""
        name_key = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        
        # Exact match
        if name_key in self._index_by_name:
            return self.formulas[self._index_by_name[name_key]]
        
        # Partial match
        for key, idx in self._index_by_name.items():
            if name_key in key or key in name_key:
                return self.formulas[idx]
        
        return None
    
    def get_prompt_structure(self, formula_id: int) -> Optional[Dict]:
        """Extract just the prompt structure from a formula."""
        if 0 <= formula_id < len(self.formulas):
            return self.formulas[formula_id]["data"].get("prompt_structure")
        return None
    
    def get_model_params(self, formula_id: int, model: str = None) -> Optional[Dict]:
        """Extract model-specific parameters from a formula."""
        if 0 <= formula_id < len(self.formulas):
            params = self.formulas[formula_id]["data"].get("model_params", {})
            if model:
                # Fuzzy match model name
                for key in params:
                    if model.lower() in key.lower():
                        return params[key]
            return params
        return None
    
    def get_semantic_keywords(self, formula_id: int) -> Optional[Dict]:
        """Extract semantic keywords from a formula."""
        if 0 <= formula_id < len(self.formulas):
            return self.formulas[formula_id]["data"].get("semantic_keywords")
        return None
    
    def get_all_keywords_flat(self) -> List[str]:
        """Get a flat list of ALL unique keywords across all formulas."""
        all_kw = set()
        for keywords in self._keyword_cache.values():
            all_kw.update(keywords)
        return sorted(all_kw)
    
    def get_example_prompts(self, formula_id: int) -> List[str]:
        """Extract example prompts from a formula."""
        examples = []
        if 0 <= formula_id < len(self.formulas):
            data = self.formulas[formula_id]["data"]
            
            # Check prompt_structure.example_prompt
            ps = data.get("prompt_structure", {})
            if isinstance(ps, dict):
                ep = ps.get("example_prompt")
                if isinstance(ep, str):
                    examples.append(ep)
                elif isinstance(ep, dict):
                    examples.extend([str(v) for v in ep.values() if isinstance(v, str)])
            
            # Check real_examples
            re_data = data.get("real_examples")
            if isinstance(re_data, list):
                for ex in re_data:
                    if isinstance(ex, dict):
                        prompt = ex.get("prompt") or ex.get("example_prompt") or ex.get("full_prompt")
                        if prompt:
                            examples.append(str(prompt))
                    elif isinstance(ex, str):
                        examples.append(ex)
        
        return examples
    
    def summary(self) -> Dict:
        """Return a summary of the loaded knowledge base."""
        models = {}
        platforms = {}
        categories = {}
        
        for formula in self.formulas:
            for model in formula.get("target_models", []):
                models[model] = models.get(model, 0) + 1
            cat = formula["category_label"]
            categories[cat] = categories.get(cat, 0) + 1
        
        for platform, ids in self._index_by_platform.items():
            platforms[platform] = len(ids)
        
        return {
            "total_formulas": len(self.formulas),
            "categories": categories,
            "models": models,
            "platforms": platforms,
            "total_unique_keywords": len(self.get_all_keywords_flat()),
        }
    
    def print_summary(self):
        """Print a formatted summary."""
        s = self.summary()
        print(f"\n{'='*60}")
        print(f"🎨 Image Prompt Knowledge Engine")
        print(f"{'='*60}")
        print(f"📦 Total Formulas: {s['total_formulas']}")
        print(f"🔑 Unique Keywords: {s['total_unique_keywords']}")
        print(f"\n📂 By Category:")
        for cat, count in s['categories'].items():
            print(f"   • {cat}: {count}")
        print(f"\n🤖 By Model:")
        for model, count in s['models'].items():
            print(f"   • {model}: {count}")
        print(f"\n📱 By Platform:")
        for platform, count in s['platforms'].items():
            print(f"   • {platform.replace('_', '/').title()}: {count}")
        print(f"{'='*60}\n")
    
    def to_rag_chunks(self, chunk_size: int = 3000) -> List[Dict[str, str]]:
        """
        Convert all formulas into RAG-ready text chunks with metadata.
        Used by ingest_image_prompts.py to load into the vector store.
        """
        chunks = []
        
        for formula in self.formulas:
            data = formula["data"]
            
            # Build a rich text representation
            text_parts = [
                f"# {formula['formula_name']}",
                f"Category: {formula['category_label']}",
                f"Type: {formula.get('formula_type', 'N/A')}",
                f"Models: {', '.join(formula.get('target_models', []))}",
                "",
            ]
            
            # Add prompt structure
            ps = data.get("prompt_structure", {})
            if isinstance(ps, dict):
                core = ps.get("core_formula", "")
                if core:
                    text_parts.append(f"## Core Formula\n{core}\n")
                
                components = ps.get("components", [])
                if components:
                    text_parts.append("## Components")
                    for comp in components:
                        if isinstance(comp, dict):
                            text_parts.append(f"- {comp.get('name', '')}: {comp.get('description', '')} (Weight: {comp.get('weight', 'N/A')})")
                            examples = comp.get('examples', [])
                            if examples:
                                text_parts.append(f"  Examples: {', '.join(str(e) for e in examples[:3])}")
                        elif isinstance(comp, str):
                            text_parts.append(f"- {comp}")
                    text_parts.append("")
                
                example = ps.get("example_prompt")
                if example:
                    if isinstance(example, str):
                        text_parts.append(f"## Example Prompt\n{example}\n")
                    elif isinstance(example, dict):
                        for k, v in example.items():
                            text_parts.append(f"## Example ({k})\n{json.dumps(v, indent=2) if isinstance(v, (dict, list)) else v}\n")
            
            # Add model params summary
            model_params = data.get("model_params", {})
            if model_params:
                text_parts.append("## Model-Specific Optimization")
                for model_name, params in model_params.items():
                    if isinstance(params, dict):
                        strength = params.get("strength", "")
                        weakness = params.get("weakness", "")
                        text_parts.append(f"\n### {model_name}")
                        if strength:
                            text_parts.append(f"Strength: {strength}")
                        if weakness:
                            text_parts.append(f"Weakness: {weakness}")
                        
                        phrases = params.get("recommended_phrases", [])
                        if phrases:
                            text_parts.append(f"Key Phrases: {', '.join(str(p) for p in phrases[:5])}")
                text_parts.append("")
            
            # Add semantic keywords
            sem = data.get("semantic_keywords", {})
            if isinstance(sem, dict):
                text_parts.append("## Semantic Keywords")
                for kw_cat, kw_list in sem.items():
                    if isinstance(kw_list, list):
                        text_parts.append(f"- {kw_cat}: {', '.join(str(k) for k in kw_list[:8])}")
                text_parts.append("")
            
            # Add A/B testing insights
            ab = data.get("a_b_testing", {})
            if isinstance(ab, (dict, list)):
                text_parts.append("## A/B Testing Insights")
                if isinstance(ab, dict):
                    for test_name, test_data in ab.items():
                        if isinstance(test_data, dict):
                            text_parts.append(f"- {test_name}: {test_data.get('result', test_data.get('winner', str(test_data)[:100]))}")
                        else:
                            text_parts.append(f"- {test_name}: {str(test_data)[:100]}")
                text_parts.append("")
            
            full_text = '\n'.join(text_parts)
            
            # Chunk if needed
            if len(full_text) <= chunk_size:
                chunks.append({
                    "text": full_text,
                    "formula_name": formula["formula_name"],
                    "category": formula["category"],
                    "source_file": formula["source_file"],
                    "models": formula.get("target_models", []),
                })
            else:
                # Split into chunks
                for i in range(0, len(full_text), chunk_size):
                    chunk_text = full_text[i:i + chunk_size]
                    chunks.append({
                        "text": chunk_text,
                        "formula_name": formula["formula_name"],
                        "category": formula["category"],
                        "source_file": formula["source_file"],
                        "models": formula.get("target_models", []),
                        "chunk_index": i // chunk_size,
                    })
        
        return chunks


# ==================== CLI TEST ====================

if __name__ == "__main__":
    engine = ImagePromptEngine()
    engine.print_summary()
    
    # Demo searches
    print("🔍 Demo: Instagram formulas")
    for r in engine.search(platform="instagram"):
        print(f"   • {r['formula_name'][:80]}")
    
    print("\n🔍 Demo: Flux 2 formulas")
    for r in engine.search(model="flux 2"):
        print(f"   • {r['formula_name'][:80]}")
    
    print("\n🔍 Demo: Keyword 'volumetric lighting'")
    for r in engine.search(keyword="volumetric"):
        print(f"   • {r['formula_name'][:80]}")
    
    print("\n🔍 Demo: LinkedIn + Midjourney")
    for r in engine.search(platform="linkedin", model="midjourney"):
        print(f"   • {r['formula_name'][:80]}")
    
    print(f"\n📊 RAG chunks: {len(engine.to_rag_chunks())}")
