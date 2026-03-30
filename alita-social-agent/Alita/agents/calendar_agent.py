"""
Calendar Agent - Intelligent Content Scheduling & Timing Optimization

This agent uses platform-specific research and audience data to:
- Generate optimal posting schedules for multi-platform campaigns
- Recommend best times to post based on platform, niche, timezone, content type
- Ensure proper spacing between posts to avoid algorithm penalties
- Balance frequency across platforms for maximum engagement
- Apply platform-specific rules (minimum gaps, daily limits, best days)

The agent uses a RAG system loaded with extensive research on:
- Posting times by platform (Instagram, TikTok, LinkedIn, Facebook, Twitter, Threads, YouTube)
- Frequency recommendations (daily, weekly, by content type)
- Algorithm behavior (engagement velocity, content lifespan, penalties)
- Timezone optimization for global audiences
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from anthropic import Anthropic
import glob
import pytz
import sys


# ── Robust JSON extraction helper ──────────────────────────────────
def _extract_json_object(text: str) -> Optional[Dict]:
    """Extract a JSON *object* from Claude's response text.

    Pipeline:
      1. Strip markdown fences and XML analysis blocks.
      2. Try ``json.loads`` on the cleaned text.
      3. Find the outermost balanced ``{…}`` via brace-depth counting.
      4. Repair truncated JSON (unclosed strings/braces) and retry.
      5. Return ``None`` only if all attempts fail.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Strip markdown fences
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Strip <analysis>…</analysis> XML blocks
    cleaned = re.sub(r'<analysis>.*?</analysis>', '', cleaned, flags=re.DOTALL).strip()

    # Attempt 1 — direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 2 — balanced-brace extraction
    start_idx = cleaned.find('{')
    if start_idx == -1:
        return None

    depth = 0
    end_idx = -1
    in_str = False
    esc = False
    for i in range(start_idx, len(cleaned)):
        c = cleaned[i]
        if esc:
            esc = False
            continue
        if c == '\\':
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    if end_idx > start_idx:
        raw = cleaned[start_idx:end_idx]
        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Attempt 3 — repair truncated JSON (best-effort)
    raw_from_first = cleaned[start_idx:]
    raw_from_first = _repair_truncated(raw_from_first)
    try:
        return json.loads(raw_from_first)
    except json.JSONDecodeError:
        return None


def _repair_truncated(raw: str) -> str:
    """Close unclosed strings and braces so truncated JSON can be parsed."""
    raw = re.sub(r',\s*$', '', raw.rstrip())
    in_str = False
    esc = False
    opens: list = []
    for ch in raw:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ('{', '['):
            opens.append(ch)
        elif ch == '}' and opens and opens[-1] == '{':
            opens.pop()
        elif ch == ']' and opens and opens[-1] == '[':
            opens.pop()
    if in_str:
        raw += '"'
    for opener in reversed(opens):
        raw += ']' if opener == '[' else '}'
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    return raw

# Add Agent RAGs to path for prompt imports
agent_rags_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Agent RAGs", "Calender RAG")
if agent_rags_path not in sys.path:
    sys.path.insert(0, agent_rags_path)

try:
    from calendar_agent_prompts import get_prompt, format_prompt
    PROMPTS_AVAILABLE = True
except ImportError:
    PROMPTS_AVAILABLE = False
    print("⚠️  Prompt templates not found, using fallback prompts")

# Initialize Claude client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


@dataclass
class ScheduledPost:
    """Represents a scheduled post with all metadata"""
    content_id: str
    platform: str
    content_type: str  # "reel", "post", "story", "tweet", "thread", "video", "short"
    scheduled_time: datetime
    timezone: str
    niche: Optional[str] = None
    priority: int = 2  # 1=high, 2=medium, 3=low
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformConstraints:
    """Platform-specific posting constraints"""
    min_gap_hours: float
    max_posts_per_day: int
    recommended_weekly_frequency: Tuple[int, int]  # (min, max)
    best_days: List[str]
    avoid_days: List[str] = field(default_factory=list)
    peak_hours_start: int = 9  # 9 AM
    peak_hours_end: int = 21  # 9 PM


class CalendarAgentRAG:
    """RAG system for Calendar Agent - loads platform timing research"""
    
    def __init__(self, rag_base_path: str = "Agent RAGs/Calender RAG"):
        """Initialize RAG system by loading all platform documents"""
        self.rag_base_path = rag_base_path
        self.documents = {}
        self.load_all_documents()
    
    def load_all_documents(self):
        """Load all markdown documents from the Calendar RAG folder"""
        platforms = ["instagram", "facebook", "tiktok", "twitter_x", "linkedin", "threads", "youtube"]
        
        for platform in platforms:
            self.documents[platform] = []
            # Handle the nested folder structure (platform/platform/*.md)
            pattern = os.path.join(self.rag_base_path, platform, platform, "*.md")
            files = glob.glob(pattern)
            
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        filename = os.path.basename(file_path)
                        self.documents[platform].append({
                            "filename": filename,
                            "content": content,
                            "path": file_path
                        })
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")
        
        # Print summary
        total_docs = sum(len(docs) for docs in self.documents.values())
        print(f"📚 Calendar RAG System Loaded: {total_docs} documents across {len(platforms)} platforms")
        for platform, docs in self.documents.items():
            if docs:
                print(f"  - {platform}: {len(docs)} documents")
    
    def retrieve_relevant_context(self, query: str, platform: str, top_k: int = 3) -> str:
        """Retrieve most relevant documents for a query"""
        # Normalize twitter → twitter_x
        platform_key = "twitter_x" if platform.lower() in ("twitter", "twitter_x") else platform.lower()

        if platform_key not in self.documents or not self.documents[platform_key]:
            return f"No documents found for platform: {platform}"
        
        # Simple keyword matching (can be enhanced with embeddings later)
        platform_docs = self.documents[platform_key]
        scored_docs = []
        
        query_lower = query.lower()
        keywords = query_lower.split()
        
        for doc in platform_docs:
            score = 0
            content_lower = doc["content"].lower()
            
            # Score based on keyword matches
            for keyword in keywords:
                score += content_lower.count(keyword)
            
            # Bonus for title match
            if any(keyword in doc["filename"].lower() for keyword in keywords):
                score += 10
            
            scored_docs.append((score, doc))
        
        # Sort by score and get top_k
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored_docs[:top_k]
        
        # Combine content
        context = f"\n\n=== PLATFORM: {platform.upper()} ===\n\n"
        for score, doc in top_docs:
            context += f"--- Document: {doc['filename']} (Relevance: {score}) ---\n"
            context += doc["content"][:3000]  # Limit to 3000 chars per doc
            context += "\n\n"
        
        return context


class CalendarAgent:
    """Intelligent content scheduling agent with RAG-powered timing optimization"""
    
    # Default platform constraints (will be overridden by RAG insights)
    DEFAULT_CONSTRAINTS = {
        "instagram": PlatformConstraints(
            min_gap_hours=3.0,
            max_posts_per_day=4,
            recommended_weekly_frequency=(4, 7),
            best_days=["Tuesday", "Wednesday", "Thursday"],
            peak_hours_start=10,
            peak_hours_end=21
        ),
        "tiktok": PlatformConstraints(
            min_gap_hours=4.0,
            max_posts_per_day=5,
            recommended_weekly_frequency=(14, 28),  # 2-4 per day
            best_days=["Monday", "Tuesday", "Friday", "Saturday"],
            peak_hours_start=6,
            peak_hours_end=23
        ),
        "facebook": PlatformConstraints(
            min_gap_hours=6.0,
            max_posts_per_day=2,
            recommended_weekly_frequency=(5, 10),
            best_days=["Tuesday", "Wednesday", "Thursday"],
            avoid_days=["Saturday"],
            peak_hours_start=9,
            peak_hours_end=14
        ),
        "linkedin": PlatformConstraints(
            min_gap_hours=12.0,
            max_posts_per_day=2,
            recommended_weekly_frequency=(3, 5),
            best_days=["Tuesday", "Wednesday", "Thursday"],
            avoid_days=["Saturday", "Sunday"],
            peak_hours_start=7,
            peak_hours_end=17
        ),
        "twitter": PlatformConstraints(
            min_gap_hours=2.0,
            max_posts_per_day=8,
            recommended_weekly_frequency=(14, 35),  # 2-5 per day
            best_days=["Tuesday", "Wednesday", "Thursday"],
            peak_hours_start=9,
            peak_hours_end=18
        ),
        "threads": PlatformConstraints(
            min_gap_hours=3.0,
            max_posts_per_day=4,
            recommended_weekly_frequency=(7, 14),  # 1-2 per day
            best_days=["Tuesday", "Wednesday", "Thursday"],
            peak_hours_start=9,
            peak_hours_end=21
        ),
        "youtube": PlatformConstraints(
            min_gap_hours=24.0,
            max_posts_per_day=1,
            recommended_weekly_frequency=(2, 7),
            best_days=["Thursday", "Friday", "Saturday", "Sunday"],
            peak_hours_start=14,
            peak_hours_end=20
        )
    }
    
    def __init__(self, client_id: str, rag_system: Optional[CalendarAgentRAG] = None,
                 profile=None):
        """
        Initialize Calendar Agent

        Args:
            client_id:  Unique identifier for the client
            rag_system: Optional RAG system instance (will create if not provided)
            profile:    Optional ClientProfile ORM object.  When supplied the agent
                        knows the client’s plan tier and post quota so it can cap
                        the schedule it generates and warn when limits are near.
        """
        self.client_id = client_id
        self.rag = rag_system or CalendarAgentRAG()
        self.schedule: List[ScheduledPost] = []

        # ── Plan / quota awareness ───────────────────────────────────
        self.plan_tier       = "free"
        self.posts_limit     = 5      # free default
        self.posts_used      = 0
        self.posts_remaining = -1     # -1 means unlimited

        if profile is not None:
            try:
                from utils.plan_limits import check_post_schedule_limit
                allowed, used, limit, _ = check_post_schedule_limit(profile)
                self.plan_tier       = getattr(profile, "plan_tier", "free") or "free"
                self.posts_limit     = limit
                self.posts_used      = used
                self.posts_remaining = (limit - used) if limit != -1 else -1
            except Exception as e:
                print(f"⚠️  CalendarAgent: could not load quota for {client_id}: {e}")

        # ── Connected platform awareness ─────────────────────────────
        # Discover which platforms the client has actually linked so the
        # agent (and callers) never blindly schedule for disconnected channels.
        try:
            from utils.connected_platforms import get_connected_platforms
            self.connected_platforms: List[str] = get_connected_platforms(client_id)
        except Exception as _cp_err:
            print(f"⚠️  CalendarAgent: could not load connected platforms for {client_id}: {_cp_err}")
            self.connected_platforms = []

        print(f"📅 Calendar Agent initialized for client: {client_id}")
        if self.connected_platforms:
            print(f"   Connected platforms: {', '.join(self.connected_platforms)}")
        else:
            print(f"   Connected platforms: none detected (will use caller-supplied list)")
        if profile is not None:
            if self.posts_remaining == -1:
                print(f"   Plan: {self.plan_tier} — unlimited posts")
            else:
                print(f"   Plan: {self.plan_tier} — {self.posts_remaining} posts remaining this month ({self.posts_used}/{self.posts_limit} used)")

    def get_connected_platforms(self) -> List[str]:
        """Return the list of platforms this client currently has connected."""
        return list(self.connected_platforms)
    
    def get_platform_constraints(self, platform: str) -> PlatformConstraints:
        """Get constraints for a specific platform"""
        return self.DEFAULT_CONSTRAINTS.get(platform.lower(), self.DEFAULT_CONSTRAINTS["instagram"])
    
    async def get_optimal_posting_times(
        self,
        platform: str,
        timezone: str,
        niche: Optional[str] = None,
        content_type: Optional[str] = None,
        account_goal: str = "growth"  # "growth", "maintenance", "aggressive"
    ) -> Dict[str, Any]:
        """
        Get AI-powered optimal posting times based on RAG research
        
        Args:
            platform: Social media platform
            timezone: Client's timezone (e.g., "America/New_York", "UTC")
            niche: Optional industry/niche (e.g., "fitness", "tech", "fashion")
            content_type: Optional content type (e.g., "reel", "carousel", "story")
            account_goal: Account goal (growth, maintenance, aggressive)
        
        Returns:
            Dict with recommended times, frequency, and insights
        """
        # Retrieve relevant context from RAG
        query = f"best times to post {content_type or ''} frequency {account_goal} {niche or ''}"
        context = self.rag.retrieve_relevant_context(query, platform.lower(), top_k=3)
        
        # Build prompt using structured template
        if PROMPTS_AVAILABLE:
            prompt_template = get_prompt("optimal_times")
            prompt = format_prompt(
                prompt_template,
                platform_research=context,
                platform_name=platform,
                timezone=timezone,
                niche=niche or "general",
                content_type=content_type or "general post",
                account_goal=account_goal
            )
        else:
            # Fallback prompt if templates not available
            prompt = f"""You are an expert social media scheduling strategist. Based on the research below, provide optimal posting recommendations.

PLATFORM: {platform}
TIMEZONE: {timezone}
NICHE: {niche or "general"}
CONTENT TYPE: {content_type or "general post"}
ACCOUNT GOAL: {account_goal}

RESEARCH CONTEXT:
{context}

Provide recommendations in JSON format:
{{
    "recommended_times": [
        {{"day": "Monday", "time": "10:00", "priority": "high"}},
        {{"day": "Tuesday", "time": "14:00", "priority": "medium"}}
    ],
    "posting_frequency": {{
        "posts_per_week": 5,
        "posts_per_day_max": 2,
        "min_gap_hours": 4.0
    }},
    "best_days": ["Tuesday", "Wednesday", "Thursday"],
    "avoid_days": ["Saturday"],
    "optimal_windows": [
        {{"start": "09:00", "end": "12:00", "label": "Morning Peak"}},
        {{"start": "17:00", "end": "20:00", "label": "Evening Peak"}}
    ],
    "insights": [
        "Post during lunch hours (12-2 PM) for maximum engagement",
        "Avoid posting after 9 PM on weekdays",
        "Reels perform better in evening hours (7-10 PM)"
    ],
    "algorithm_notes": "Instagram algorithm prioritizes content posted when followers are most active. Initial engagement in first 30-90 minutes determines reach."
}}

Return ONLY the JSON, no other text."""
        
        try:
            response = client.messages.create(
                model=os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            recommendations = _extract_json_object(response.content[0].text)
            if recommendations:
                return recommendations

            print(f"⚠️ Could not extract JSON from Claude response — retrying with explicit instruction")
            # One retry with a stronger nudge
            retry_resp = client.messages.create(
                model=os.getenv("CLAUDE_SONNET_MODEL", "claude-sonnet-4-5-20250929"),
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "{"},
                ]
            )
            retry_text = "{" + retry_resp.content[0].text
            recommendations = _extract_json_object(retry_text)
            if recommendations:
                return recommendations

            print(f"⚠️ Retry also failed — using platform defaults")
            return self._get_fallback_recommendations(platform)
                
        except Exception as e:
            print(f"❌ Error getting optimal times: {e}")
            return self._get_fallback_recommendations(platform)
    
    def _get_fallback_recommendations(self, platform: str) -> Dict[str, Any]:
        """Fallback recommendations if Claude fails"""
        constraints = self.get_platform_constraints(platform)
        return {
            "recommended_times": [
                {"day": "Tuesday", "time": "10:00", "priority": "high"},
                {"day": "Wednesday", "time": "14:00", "priority": "high"},
                {"day": "Thursday", "time": "12:00", "priority": "medium"}
            ],
            "posting_frequency": {
                "posts_per_week": constraints.recommended_weekly_frequency[0],
                "posts_per_day_max": constraints.max_posts_per_day,
                "min_gap_hours": constraints.min_gap_hours
            },
            "best_days": constraints.best_days,
            "avoid_days": constraints.avoid_days,
            "insights": [f"Using default recommendations for {platform}"]
        }
    
    async def generate_weekly_schedule(
        self,
        platforms: List[str],
        content_types: Dict[str, List[str]],  # {platform: [content_types]}
        timezone: str = "America/New_York",
        niche: Optional[str] = None,
        start_date: Optional[datetime] = None,
        posts_remaining: int = -1,  # -1 = use self.posts_remaining (from profile)
    ) -> List[ScheduledPost]:
        """
        Generate a complete weekly posting schedule across multiple platforms.

        The schedule is automatically capped by the client’s plan quota:
        * posts_remaining=-1 uses the value loaded from the profile at __init__
        * Pass an explicit posts_remaining to override (useful for tests).
        * If the cap is 0 the method returns an empty list with a warning.
        Mid-month plan upgrades are handled transparently — because
        check_post_schedule_limit() always reads the current plan_tier from the
        profile, the remaining quota increases immediately after an upgrade.
        """
        # Resolve effective cap
        if posts_remaining == -1:
            cap = self.posts_remaining   # loaded from profile at __init__
        else:
            cap = posts_remaining

        if cap == 0:
            print("⚠️  CalendarAgent: monthly post quota exhausted — no posts scheduled.")
            return []

        if cap != -1:
            print(f"\n📊 Post quota: {self.posts_used} used, {cap} remaining this month.")
        else:
            print(f"\n📊 Post quota: unlimited")

        if start_date is None:
            # Default to next Monday
            today = datetime.now(pytz.timezone(timezone))
            days_ahead = 0 - today.weekday()  # Monday is 0
            if days_ahead <= 0:
                days_ahead += 7
            start_date = today + timedelta(days=days_ahead)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        schedule = []
        content_id_counter = 1
        total_added = 0

        print(f"\n📅 Generating weekly schedule starting {start_date.strftime('%Y-%m-%d')}")
        print(f"🌍 Timezone: {timezone}")
        print(f"📱 Platforms: {', '.join(platforms)}")

        for platform in platforms:
            if cap != -1 and total_added >= cap:
                print(f"  ⏹️  Quota cap ({cap}) reached — skipping {platform} and remaining platforms.")
                break

            print(f"\n  Analyzing {platform.upper()}...")

            # Get optimal times for this platform
            types = content_types.get(platform, ["post"])
            for content_type in types:
                if cap != -1 and total_added >= cap:
                    print(f"    ⏹️  Quota cap reached — stopping content-type loop.")
                    break

                recommendations = await self.get_optimal_posting_times(
                    platform=platform,
                    timezone=timezone,
                    niche=niche,
                    content_type=content_type
                )

                # Respect quota: cap posts_per_week if needed
                raw_ppw            = recommendations["posting_frequency"]["posts_per_week"]
                if cap != -1:
                    available          = cap - total_added
                    posts_per_week     = min(raw_ppw, available)
                    if posts_per_week < raw_ppw:
                        print(f"    ℹ️  {platform}/{content_type}: reduced from {raw_ppw} to {posts_per_week} posts/week (quota)")
                else:
                    posts_per_week     = raw_ppw

                recommended_times = recommendations["recommended_times"]
                print(f"    - {content_type}: {posts_per_week} posts/week")

                for i in range(posts_per_week):
                    if cap != -1 and total_added >= cap:
                        break

                    # Cycle through recommended times
                    time_rec = recommended_times[i % len(recommended_times)]
                    day_name = time_rec["day"]
                    time_str = time_rec["time"]

                    # Calculate the date
                    day_offset = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(day_name)
                    post_date  = start_date + timedelta(days=day_offset)

                    # Parse time
                    hour, minute = map(int, time_str.split(":"))
                    post_datetime = post_date.replace(hour=hour, minute=minute)

                    # Create scheduled post
                    post = ScheduledPost(
                        content_id=f"{self.client_id}_{platform}_{content_id_counter:03d}",
                        platform=platform,
                        content_type=content_type,
                        scheduled_time=post_datetime,
                        timezone=timezone,
                        niche=niche,
                        priority=1 if time_rec["priority"] == "high" else 2,
                        metadata={
                            "recommendations": recommendations,
                            "day_name":   day_name,
                            "time_label": time_str,
                            "plan_tier":  self.plan_tier,
                            "quota_cap":  cap,
                        }
                    )

                    schedule.append(post)
                    content_id_counter += 1
                    total_added        += 1

        # Sort by scheduled time
        schedule.sort(key=lambda x: x.scheduled_time)

        remaining_after = (cap - total_added) if cap != -1 else -1
        print(f"\n✅ Generated {len(schedule)} scheduled posts")
        if cap != -1:
            print(f"   {remaining_after} post slot(s) still available this month.")
        return schedule
    
    def visualize_schedule(self, schedule: List[ScheduledPost]):
        """Print a human-readable schedule"""
        print("\n" + "="*80)
        print(f"📅 WEEKLY POSTING SCHEDULE - {self.client_id}")
        print("="*80)
        
        # Group by day
        by_day = {}
        for post in schedule:
            day = post.scheduled_time.strftime("%A, %B %d")
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(post)
        
        for day, posts in by_day.items():
            print(f"\n📆 {day}")
            print("-" * 80)
            for post in posts:
                time_str = post.scheduled_time.strftime("%I:%M %p")
                priority_emoji = "🔴" if post.priority == 1 else "🟡" if post.priority == 2 else "🔵"
                print(f"  {time_str} {priority_emoji} {post.platform:12s} | {post.content_type:15s} | {post.content_id}")
        
        print("\n" + "="*80)
        
        # Summary
        print("\n📊 SUMMARY BY PLATFORM")
        print("-" * 80)
        platform_counts = {}
        for post in schedule:
            platform_counts[post.platform] = platform_counts.get(post.platform, 0) + 1
        
        for platform, count in sorted(platform_counts.items()):
            print(f"  {platform:12s}: {count} posts")
        
        print(f"\n  TOTAL: {len(schedule)} posts")
    
    def export_schedule_json(self, schedule: List[ScheduledPost], filename: str):
        """Export schedule to JSON file"""
        data = []
        for post in schedule:
            data.append({
                "content_id": post.content_id,
                "platform": post.platform,
                "content_type": post.content_type,
                "scheduled_time": post.scheduled_time.isoformat(),
                "timezone": post.timezone,
                "niche": post.niche,
                "priority": post.priority,
                "day_name": post.scheduled_time.strftime("%A"),
                "time_label": post.scheduled_time.strftime("%I:%M %p"),
                "metadata": post.metadata
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"✅ Schedule exported to {filename}")
    
    def validate_schedule(self, schedule: List[ScheduledPost]) -> Dict[str, List[str]]:
        """
        Validate schedule against platform constraints
        
        Returns:
            Dict with warnings and errors
        """
        warnings = []
        errors = []
        
        # Group by platform
        by_platform = {}
        for post in schedule:
            if post.platform not in by_platform:
                by_platform[post.platform] = []
            by_platform[post.platform].append(post)
        
        for platform, posts in by_platform.items():
            constraints = self.get_platform_constraints(platform)
            
            # Sort by time
            posts.sort(key=lambda x: x.scheduled_time)
            
            # Check daily limits
            by_day = {}
            for post in posts:
                day = post.scheduled_time.date()
                if day not in by_day:
                    by_day[day] = []
                by_day[day].append(post)
            
            for day, day_posts in by_day.items():
                if len(day_posts) > constraints.max_posts_per_day:
                    errors.append(
                        f"{platform}: {len(day_posts)} posts on {day} exceeds limit of {constraints.max_posts_per_day}"
                    )
            
            # Check minimum gaps
            for i in range(len(posts) - 1):
                time_diff = (posts[i+1].scheduled_time - posts[i].scheduled_time).total_seconds() / 3600
                if time_diff < constraints.min_gap_hours:
                    warnings.append(
                        f"{platform}: Only {time_diff:.1f}h gap between posts on {posts[i].scheduled_time.strftime('%Y-%m-%d %H:%M')} and {posts[i+1].scheduled_time.strftime('%H:%M')} (min: {constraints.min_gap_hours}h)"
                    )
        
        return {"warnings": warnings, "errors": errors}


# Example usage
async def main():
    """Test the Calendar Agent with RAG system"""
    
    print("\n" + "="*80)
    print("🤖 CALENDAR AGENT - PRODUCTION TEST")
    print("="*80)
    
    # Initialize RAG system
    print("\n1️⃣  Loading RAG System...")
    rag = CalendarAgentRAG()
    
    # Initialize agent
    print("\n2️⃣  Initializing Calendar Agent...")
    agent = CalendarAgent(client_id="demo_client", rag_system=rag)
    
    # Test 1: Get optimal times for Instagram
    print("\n3️⃣  TEST 1: Get optimal posting times for Instagram")
    print("-" * 80)
    recommendations = await agent.get_optimal_posting_times(
        platform="instagram",
        timezone="America/New_York",
        niche="fitness",
        content_type="reel",
        account_goal="growth"
    )
    print(json.dumps(recommendations, indent=2))
    
    # Test 2: Generate weekly schedule
    print("\n4️⃣  TEST 2: Generate multi-platform weekly schedule")
    print("-" * 80)
    schedule = await agent.generate_weekly_schedule(
        platforms=["instagram", "tiktok", "linkedin"],
        content_types={
            "instagram": ["reel", "carousel"],
            "tiktok": ["video"],
            "linkedin": ["post"]
        },
        timezone="America/New_York",
        niche="AI automation"
    )
    
    # Visualize
    agent.visualize_schedule(schedule)
    
    # Test 3: Validate schedule
    print("\n5️⃣  TEST 3: Validate schedule")
    print("-" * 80)
    validation = agent.validate_schedule(schedule)
    
    if validation["errors"]:
        print("❌ ERRORS:")
        for error in validation["errors"]:
            print(f"  - {error}")
    else:
        print("✅ No errors found")
    
    if validation["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in validation["warnings"]:
            print(f"  - {warning}")
    else:
        print("✅ No warnings")
    
    # Test 4: Export schedule
    print("\n6️⃣  TEST 4: Export schedule to JSON")
    print("-" * 80)
    agent.export_schedule_json(schedule, "demo_weekly_schedule.json")
    
    print("\n" + "="*80)
    print("✅ CALENDAR AGENT TEST COMPLETE")
    print("="*80)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
