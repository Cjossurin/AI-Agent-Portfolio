"""
AI Deep Research Tool for Faceless Video Production
====================================================
This script uses Google's Gemini Pro API to conduct comprehensive research
on faceless video production techniques, strategies, and best practices.

The research is organized into categories and generates detailed reports
that will be used to create optimized prompts for video generation.

SETUP INSTRUCTIONS:
1. Install the required library: pip install google-generativeai
2. Get your API key from: https://makersuite.google.com/app/apikey
3. Set your GEMINI_API_KEY in .env file

USAGE:
    python researcher.py                    # Research all categories
    python researcher.py --category horror  # Research specific category
    python researcher.py --resume          # Resume from last incomplete category
"""

import json
import time
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:
    print("❌ Error: google-generativeai library not installed")
    print("   Run: pip install google-generativeai")
    sys.exit(1)

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================
SCRIPT_DIR = Path(__file__).parent
SUBJECTS_FILE = SCRIPT_DIR / 'research_subjects.json'
REPORTS_DIR = SCRIPT_DIR / 'Research_Reports'
PROGRESS_FILE = SCRIPT_DIR / 'research_progress.json'

# Gemini API Configuration
API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
try:
    from utils.ai_config import GEMINI_FLASH
    MODEL_NAME = GEMINI_FLASH
except ImportError:
    MODEL_NAME = os.getenv('GEMINI_MODEL', 'models/gemini-2.0-flash-exp')

# Research Settings
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds
REQUEST_DELAY = 3  # seconds between requests to avoid rate limits

# ==================== HELPER FUNCTIONS ====================

def load_progress() -> Dict:
    """Load research progress from file"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Warning: Could not load progress file: {e}")
    return {"completed": [], "last_updated": None}


def save_progress(progress: Dict):
    """Save research progress to file"""
    progress["last_updated"] = datetime.now().isoformat()
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, indent=2, fp=f)
    except Exception as e:
        print(f"⚠️  Warning: Could not save progress: {e}")


def load_subjects() -> Optional[Dict]:
    """Load the research subject categories from JSON file"""
    if not SUBJECTS_FILE.exists():
        print(f"❌ Error: Could not find {SUBJECTS_FILE}")
        print(f"   Create this file with your research queries organized by category")
        return None
    
    try:
        with open(SUBJECTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Support both array and categorized formats
        if isinstance(data, list):
            # Legacy format - wrap in single category
            subjects = {"general": {"category": "general", "queries": data}}
        elif isinstance(data, dict):
            # Check if it's already categorized
            if all(isinstance(v, dict) and "queries" in v for v in data.values()):
                subjects = data
            else:
                # Assume it's a single category object
                subjects = {"research": data}
        else:
            print(f"❌ Error: Invalid format in {SUBJECTS_FILE}")
            return None
        
        total_queries = sum(len(cat.get("queries", [])) for cat in subjects.values())
        print(f"✅ Loaded {len(subjects)} categories with {total_queries} total queries")
        return subjects
        
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {SUBJECTS_FILE}")
        print(f"   {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading subjects: {e}")
        return None


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Create a safe filename from text"""
    # Remove invalid characters
    safe = ''.join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in text)
    # Remove multiple underscores/spaces
    safe = '_'.join(filter(None, safe.split()))
    # Limit length
    if len(safe) > max_length:
        safe = safe[:max_length].rsplit('_', 1)[0]
    return safe


def conduct_research(query: str, category: str, model) -> Optional[str]:
    """
    Send a comprehensive research request to Gemini API with retry logic
    
    Args:
        query: The research query
        category: Category context for the research
        model: Configured Gemini model instance
    
    Returns:
        Research report text or None if failed
    """
    # Build context-aware prompt
    prompt = f"""You are an expert researcher specializing in faceless video content creation and social media strategy.

RESEARCH CATEGORY: {category.replace('_', ' ').title()}

RESEARCH QUERY:
{query}

TASK:
Provide an exhaustive, deeply researched report with actionable insights. This research will be used to create AI prompts for automated video production.

REQUIRED STRUCTURE:

## 1. Executive Summary
Brief overview and key insights (2-3 paragraphs)

## 2. Core Findings
- Main discoveries and principles
- Industry standards and benchmarks
- Platform-specific nuances (YouTube Shorts, TikTok, Instagram Reels)

## 3. Best Practices & Techniques
- Specific production techniques with exact parameters
- Audio settings (BPM, volume levels, sound effects)
- Visual specifications (color grading, saturation, effects)
- Pacing and timing (scene duration, transitions, cuts)
- Voice and narration (tone, speed, persona)

## 4. Real-World Examples
- Successful channels using these techniques
- Specific video examples with viewership data
- Analysis of what makes them effective

## 5. Technical Specifications
- Exact settings and parameters (numbers, percentages)
- Tools and software recommendations
- Workflow optimization tips

## 6. Common Mistakes & Pitfalls
- What to avoid
- Quality issues to watch for
- Algorithm penalties

## 7. Actionable Framework
Step-by-step implementation guide
- Pre-production checklist
- Production settings
- Post-production workflow

## 8. Metrics & KPIs
- Key performance indicators to track
- Benchmark data by niche
- Success criteria

## 9. Future Trends & Predictions
- Emerging patterns (2025-2026)
- Algorithm changes
- Technology advancements

## 10. Key Takeaways
Bulleted list of the most important insights

FORMAT REQUIREMENTS:
- Use markdown formatting (headers, bullets, bold, code blocks)
- Include specific numbers, percentages, and ranges
- Cite successful channels/creators when relevant
- Be precise with technical specifications
- Focus on actionable, implementable information

Length: Comprehensive (3000-5000 words minimum)"""

    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=8000,
                    temperature=0.7,
                    top_p=0.95,
                )
            )
            
            if response.text:
                return response.text
            else:
                raise Exception("Empty response from API")
                
        except Exception as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * retry_count  # Exponential backoff
                print(f"     ⚠️  Request failed (attempt {retry_count}/{MAX_RETRIES}): {str(e)[:100]}")
                print(f"     ⏳ Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                error_msg = f"""# Research Failed

**Category:** {category}
**Query:** {query}
**Error:** Failed after {MAX_RETRIES} attempts

Last error: {str(e)}

---
Generated: {datetime.now().isoformat()}
"""
                return error_msg
    
    return None


def save_report(category: str, query: str, content: str, index: int) -> bool:
    """
    Save research report to categorized directory
    
    Args:
        category: Category name for organizing reports
        query: The research query
        content: Report content
        index: Query index within category
    
    Returns:
        True if saved successfully
    """
    # Create category directory
    category_dir = REPORTS_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract topic from query (first 80 chars)
    topic = query[:80].split(':')[0].split('.')[0].strip()
    filename = f"{index:02d}_{sanitize_filename(topic)}.md"
    filepath = category_dir / filename
    
    try:
        # Add metadata header
        header = f"""---
Category: {category.replace('_', ' ').title()}
Query: {query}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

"""
        full_content = header + content
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        
        print(f"     ✅ Saved: {category}/{filename}")
        return True
        
    except Exception as e:
        print(f"     ❌ Error saving report: {e}")
        return False


def research_category(
    category: str,
    category_data: Dict,
    model,
    progress: Dict,
    skip_completed: bool = False
) -> Dict[str, int]:
    """
    Research all queries in a category
    
    Returns:
        Stats dict with success/failure counts
    """
    queries = category_data.get("queries", [])
    total = len(queries)
    
    print(f"\n{'='*70}")
    print(f"📚 Category: {category.replace('_', ' ').title()}")
    print(f"📝 Queries: {total}")
    print(f"{'='*70}\n")
    
    stats = {"success": 0, "failed": 0, "skipped": 0}
    
    for idx, query in enumerate(queries, 1):
        query_id = f"{category}_{idx}"
        
        # Skip if already completed
        if skip_completed and query_id in progress.get("completed", []):
            print(f"[{idx}/{total}] ⏭️  Skipping (already completed): {query[:60]}...")
            stats["skipped"] += 1
            continue
        
        print(f"[{idx}/{total}] 🔍 Researching: {query[:70]}...")
        
        # Conduct research
        result = conduct_research(query, category, model)
        
        if result and "Research Failed" not in result[:50]:
            # Save successful report
            if save_report(category, query, result, idx):
                stats["success"] += 1
                progress["completed"].append(query_id)
                save_progress(progress)
            else:
                stats["failed"] += 1
        else:
            stats["failed"] += 1
            # Still save failed report for debugging
            save_report(category, query, result or "No response", idx)
        
        # Delay between requests (except last)
        if idx < total:
            print(f"     ⏳ Waiting {REQUEST_DELAY}s before next request...\n")
            time.sleep(REQUEST_DELAY)
    
    return stats


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='AI Deep Research Tool for Faceless Video Production')
    parser.add_argument('--category', '-c', type=str, help='Research specific category only')
    parser.add_argument('--resume', '-r', action='store_true', help='Resume from last incomplete session')
    parser.add_argument('--list', '-l', action='store_true', help='List all available categories')
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🔬 AI Deep Research Tool - Faceless Video Production")
    print("="*70 + "\n")
    
    # Check API key
    if not API_KEY:
        print("❌ Error: Gemini API key not found!")
        print("   Set GEMINI_API_KEY or GOOGLE_API_KEY in your .env file")
        print("   Get your key from: https://makersuite.google.com/app/apikey")
        return 1
    
    # Configure Gemini API
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        print(f"✅ Connected to Gemini API ({MODEL_NAME})")
    except Exception as e:
        print(f"❌ Error configuring Gemini API: {e}")
        return 1
    
    # Load research subjects
    subjects = load_subjects()
    if not subjects:
        return 1
    
    # List categories if requested
    if args.list:
        print("\n📋 Available Categories:")
        for cat_name, cat_data in subjects.items():
            query_count = len(cat_data.get("queries", []))
            print(f"   • {cat_name}: {query_count} queries")
        return 0
    
    # Load progress
    progress = load_progress()
    skip_completed = args.resume
    
    if skip_completed:
        completed_count = len(progress.get("completed", []))
        print(f"📊 Resuming from previous session ({completed_count} queries already completed)")
    
    # Create reports directory
    REPORTS_DIR.mkdir(exist_ok=True)
    print(f"📁 Reports directory: {REPORTS_DIR}\n")
    
    # Filter categories if specified
    if args.category:
        if args.category not in subjects:
            print(f"❌ Error: Category '{args.category}' not found")
            print(f"   Available: {', '.join(subjects.keys())}")
            return 1
        subjects = {args.category: subjects[args.category]}
    
    # Process categories
    total_stats = {"success": 0, "failed": 0, "skipped": 0}
    start_time = time.time()
    
    for cat_name, cat_data in subjects.items():
        cat_stats = research_category(cat_name, cat_data, model, progress, skip_completed)
        
        # Update total stats
        for key in total_stats:
            total_stats[key] += cat_stats[key]
        
        # Summary for this category
        print(f"\n📊 Category '{cat_name}' complete:")
        print(f"   ✅ Successful: {cat_stats['success']}")
        print(f"   ❌ Failed: {cat_stats['failed']}")
        if cat_stats['skipped']:
            print(f"   ⏭️  Skipped: {cat_stats['skipped']}")
    
    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "="*70)
    print("🎉 Research Complete!")
    print("="*70)
    print(f"✅ Successful: {total_stats['success']}")
    print(f"❌ Failed: {total_stats['failed']}")
    if total_stats['skipped']:
        print(f"⏭️  Skipped: {total_stats['skipped']}")
    print(f"⏱️  Time: {elapsed/60:.1f} minutes")
    print(f"📁 Reports saved in: {REPORTS_DIR}")
    print("="*70 + "\n")
    
    return 0 if total_stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
