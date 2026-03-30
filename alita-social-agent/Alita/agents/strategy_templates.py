"""
Strategy Templates Library
===========================
Loads and provides access to research-driven strategy frameworks and prompts.

USAGE:
    from agents.strategy_templates import StrategyTemplates
    
    templates = StrategyTemplates()
    
    # Get a specific template
    template = templates.get_template("instagram_reel", "conversions_sales")
    
    # List available templates
    available = templates.list_templates()
    
    # Search templates by keyword
    results = templates.search_templates("engagement")

FOLDER STRUCTURE:
    knowledge_docs/strategy_templates/
    ├── Instagram reel_conversions_sales.txt
    ├── TikTok script_follower_growth.txt
    ├── LinkedIn post_views_engagement.txt
    └── ... (drop your prompt files here)

FILE NAMING CONVENTION:
    Format: {Platform} {content_type}_{goal}.txt
    Examples:
        - Instagram reel_conversions_sales.txt
        - Facebook post_views_engagement.txt
        - LinkedIn article_follower_growth.txt
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class StrategyTemplate:
    """Represents a single strategy template."""
    platform: str
    content_type: str
    goal: str
    prompt: str
    filename: str
    
    @property
    def key(self) -> str:
        """Unique key for this template."""
        return f"{self.platform.lower()}_{self.content_type.lower()}_{self.goal.lower()}"


class StrategyTemplates:
    """
    Manages loading and retrieval of strategy templates from files.
    
    Templates are loaded from: knowledge_docs/strategy_templates/
    """
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize the strategy templates manager.
        
        Args:
            templates_dir: Optional custom directory path. 
                          Defaults to knowledge_docs/strategy_templates/
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            # Default to knowledge_docs/strategy_templates relative to project root
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent
            self.templates_dir = project_root / "knowledge_docs" / "strategy_templates"
        
        self.templates: Dict[str, StrategyTemplate] = {}
        self._load_templates()
    
    def _parse_filename(self, filename: str) -> Optional[Tuple[str, str, str]]:
        """
        Parse filename to extract platform, content_type, and goal.
        
        Expected formats:
            - "Instagram reel_conversions_sales.txt"
            - "Facebook post_views_engagement.txt"
            - "TikTok script_follower_growth.txt"
        
        Returns:
            Tuple of (platform, content_type, goal) or None if parsing fails
        """
        # Remove file extension
        name = filename.replace('.txt', '').replace('.md', '')
        
        # Try to split on underscore to separate goal
        if '_' in name:
            # Split on last underscore to separate goal
            parts = name.rsplit('_', 1)
            if len(parts) == 2:
                prefix, goal = parts
                
                # Now split prefix to get platform and content_type
                # Handle multi-word platforms (e.g., "Instagram reel")
                prefix_parts = prefix.split()
                if len(prefix_parts) >= 2:
                    platform = prefix_parts[0]
                    content_type = ' '.join(prefix_parts[1:])
                    return (platform, content_type, goal)
        
        return None
    
    def _load_templates(self):
        """Load all template files from the templates directory."""
        if not self.templates_dir.exists():
            print(f"⚠️  Templates directory not found: {self.templates_dir}")
            print(f"📁 Creating directory...")
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            return
        
        template_files = list(self.templates_dir.glob('*.txt')) + list(self.templates_dir.glob('*.md')) + list(self.templates_dir.glob('*.py'))
        
        if not template_files:
            print(f"⚠️  No template files found in {self.templates_dir}")
            return
        
        loaded_count = 0
        for file_path in template_files:
            # Handle .py files differently - parse module docstring for metadata
            if file_path.suffix == '.py':
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Parse docstring for metadata
                    platform = "Multi-platform"
                    content_type = "strategy"
                    goal = "framework"
                    
                    # Try to extract from docstring
                    docstring_match = re.search(r'Platform:\s*(\S+)', content)
                    if docstring_match:
                        platform = docstring_match.group(1)
                    
                    content_type_match = re.search(r'Content Type:\s*(\S+)', content)
                    if content_type_match:
                        content_type = content_type_match.group(1)
                    
                    goal_match = re.search(r'Goal:\s*(\S+)', content)
                    if goal_match:
                        goal = goal_match.group(1)
                    
                    template = StrategyTemplate(
                        platform=platform,
                        content_type=content_type,
                        goal=goal,
                        prompt=content,  # Store entire file content
                        filename=file_path.name
                    )
                    
                    self.templates[template.key] = template
                    loaded_count += 1
                    
                except Exception as e:
                    print(f"❌ Error loading {file_path.name}: {e}")
            else:
                # Handle .txt and .md files
                parsed = self._parse_filename(file_path.name)
                if parsed:
                    platform, content_type, goal = parsed
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            prompt = f.read()
                        
                        template = StrategyTemplate(
                            platform=platform,
                            content_type=content_type,
                            goal=goal,
                            prompt=prompt,
                            filename=file_path.name
                        )
                        
                        self.templates[template.key] = template
                        loaded_count += 1
                        
                    except Exception as e:
                        print(f"❌ Error loading {file_path.name}: {e}")
                else:
                    print(f"⚠️  Could not parse filename: {file_path.name}")
        
        print(f"✅ Loaded {loaded_count} strategy templates from {self.templates_dir}")
    
    def get_template(self, platform: str, content_type: str, goal: str) -> Optional[str]:
        """
        Get a specific template prompt.
        
        Args:
            platform: Platform name (e.g., "Instagram", "TikTok")
            content_type: Content type (e.g., "reel", "post", "story")
            goal: Goal (e.g., "conversions_sales", "views_engagement", "follower_growth")
        
        Returns:
            Template prompt string or None if not found
        """
        key = f"{platform.lower()}_{content_type.lower()}_{goal.lower()}"
        template = self.templates.get(key)
        return template.prompt if template else None
    
    def get_template_by_key(self, key: str) -> Optional[str]:
        """
        Get template by full key.
        
        Args:
            key: Template key (e.g., "instagram_reel_conversions_sales")
        
        Returns:
            Template prompt string or None if not found
        """
        template = self.templates.get(key.lower())
        return template.prompt if template else None
    
    def list_templates(self, platform: Optional[str] = None, goal: Optional[str] = None) -> List[str]:
        """
        List all available template keys, optionally filtered.
        
        Args:
            platform: Optional platform filter
            goal: Optional goal filter
        
        Returns:
            List of template keys
        """
        keys = list(self.templates.keys())
        
        if platform:
            keys = [k for k in keys if k.startswith(platform.lower())]
        
        if goal:
            keys = [k for k in keys if k.endswith(goal.lower())]
        
        return sorted(keys)
    
    def search_templates(self, keyword: str) -> List[Tuple[str, StrategyTemplate]]:
        """
        Search templates by keyword in platform, content_type, goal, or prompt content.
        
        Args:
            keyword: Search term
        
        Returns:
            List of (key, StrategyTemplate) tuples matching the keyword
        """
        keyword_lower = keyword.lower()
        results = []
        
        for key, template in self.templates.items():
            if (keyword_lower in template.platform.lower() or
                keyword_lower in template.content_type.lower() or
                keyword_lower in template.goal.lower() or
                keyword_lower in template.prompt.lower()):
                results.append((key, template))
        
        return results
    
    def get_all_for_platform(self, platform: str) -> Dict[str, str]:
        """
        Get all templates for a specific platform.
        
        Args:
            platform: Platform name
        
        Returns:
            Dictionary mapping template keys to prompts
        """
        platform_lower = platform.lower()
        return {
            key: template.prompt
            for key, template in self.templates.items()
            if template.platform.lower() == platform_lower
        }
    
    def get_all_for_goal(self, goal: str) -> Dict[str, str]:
        """
        Get all templates for a specific goal.
        
        Args:
            goal: Goal name (e.g., "conversions_sales")
        
        Returns:
            Dictionary mapping template keys to prompts
        """
        goal_lower = goal.lower()
        return {
            key: template.prompt
            for key, template in self.templates.items()
            if template.goal.lower() == goal_lower
        }
    
    def get_strategy_dict(self, template_key: str, dict_name: Optional[str] = None) -> Optional[Dict]:
        """
        Extract a specific Python dictionary from a .py template file.
        
        Args:
            template_key: Template key (e.g., "multi-platform_content_pillars_strategy")
            dict_name: Optional dictionary name to extract (e.g., "COACHING_CONTENT_PILLARS_STRATEGY")
                      If None, returns the first dictionary found
        
        Returns:
            Parsed Python dictionary or None if not found/parsing failed
        """
        template = self.templates.get(template_key.lower())
        if not template or not template.filename.endswith('.py'):
            return None
        
        try:
            # Clean the content - remove markdown code fences
            content = template.prompt
            # Remove ```python and ``` markers
            content = re.sub(r'```python\s*\n', '', content)
            content = re.sub(r'```\s*\n', '', content)
            content = re.sub(r'```', '', content)
            
            # Execute the Python file content in a restricted namespace
            namespace = {}
            exec(content, namespace)
            
            # If specific dict requested, return it
            if dict_name:
                return namespace.get(dict_name)
            
            # Otherwise return the first dict that looks like a strategy (all caps name ending in _STRATEGY)
            for key, value in namespace.items():
                if isinstance(value, dict) and key.isupper() and '_STRATEGY' in key:
                    return value
            
            return None
            
        except Exception as e:
            print(f"❌ Error parsing dictionary from {template.filename}: {e}")
            return None
    
    def list_strategy_dicts(self, template_key: str) -> List[str]:
        """
        List all available strategy dictionaries in a .py template file.
        
        Args:
            template_key: Template key
        
        Returns:
            List of dictionary names found in the file
        """
        template = self.templates.get(template_key.lower())
        if not template or not template.filename.endswith('.py'):
            return []
        
        try:
            # Clean the content - remove markdown code fences
            content = template.prompt
            content = re.sub(r'```python\s*\n', '', content)
            content = re.sub(r'```\s*\n', '', content)
            content = re.sub(r'```', '', content)
            
            namespace = {}
            exec(content, namespace)
            
            dict_names = [
                key for key, value in namespace.items()
                if isinstance(value, dict) and key.isupper() and '_STRATEGY' in key
            ]
            
            return sorted(dict_names)
            
        except Exception as e:
            print(f"❌ Error parsing {template.filename}: {e}")
            return []
    
    def reload(self):
        """Reload all templates from disk (useful if files were added/modified)."""
        self.templates.clear()
        self._load_templates()
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get statistics about loaded templates.
        
        Returns:
            Dictionary with template statistics
        """
        platforms = set(t.platform for t in self.templates.values())
        content_types = set(t.content_type for t in self.templates.values())
        goals = set(t.goal for t in self.templates.values())
        
        return {
            "total_templates": len(self.templates),
            "platforms": sorted(list(platforms)),
            "content_types": sorted(list(content_types)),
            "goals": sorted(list(goals)),
            "platform_count": len(platforms),
            "content_type_count": len(content_types),
            "goal_count": len(goals)
        }


# Convenience function for quick access
_global_templates = None

def get_templates() -> StrategyTemplates:
    """Get the global StrategyTemplates instance (singleton pattern)."""
    global _global_templates
    if _global_templates is None:
        _global_templates = StrategyTemplates()
    return _global_templates


# CLI for testing and inspection
if __name__ == "__main__":
    import sys
    
    templates = StrategyTemplates()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "list":
            print("\n📋 Available Templates:")
            for key in templates.list_templates():
                print(f"  - {key}")
        
        elif command == "stats":
            stats = templates.get_stats()
            print("\n📊 Template Statistics:")
            print(f"  Total Templates: {stats['total_templates']}")
            print(f"  Platforms ({stats['platform_count']}): {', '.join(stats['platforms'])}")
            print(f"  Content Types ({stats['content_type_count']}): {', '.join(stats['content_types'])}")
            print(f"  Goals ({stats['goal_count']}): {', '.join(stats['goals'])}")
        
        elif command == "search" and len(sys.argv) > 2:
            keyword = sys.argv[2]
            results = templates.search_templates(keyword)
            print(f"\n🔍 Search results for '{keyword}':")
            for key, template in results:
                print(f"  - {key}")
        
        elif command == "get" and len(sys.argv) > 2:
            key = sys.argv[2]
            prompt = templates.get_template_by_key(key)
            if prompt:
                print(f"\n📄 Template: {key}")
                print("=" * 80)
                print(prompt)
            else:
                print(f"❌ Template not found: {key}")
        
        else:
            print("Usage:")
            print("  python strategy_templates.py list           - List all templates")
            print("  python strategy_templates.py stats          - Show statistics")
            print("  python strategy_templates.py search <word>  - Search templates")
            print("  python strategy_templates.py get <key>      - Get specific template")
    
    else:
        # Default: show stats
        stats = templates.get_stats()
        print("\n📊 Strategy Templates Library")
        print("=" * 80)
        print(f"📁 Directory: {templates.templates_dir}")
        print(f"📋 Total Templates: {stats['total_templates']}")
        print(f"\n🎯 Platforms: {', '.join(stats['platforms'])}")
        print(f"📝 Content Types: {', '.join(stats['content_types'])}")
        print(f"🎪 Goals: {', '.join(stats['goals'])}")
        print("\nRun with 'list' to see all template keys")
