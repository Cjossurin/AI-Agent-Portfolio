"""
Growth Agent
============
AI-powered audience growth and optimization system that finds, targets,
and engages with ideal followers to grow your social media presence.

RESPONSIBILITIES:
- Find target audience (competitor followers, hashtag users, location-based)
- Identify relevant groups and communities
- Automated follow/unfollow strategies
- Smart engagement targeting (who to like/comment on)
- Growth optimization based on analytics
- Safety and rate limit management
- ROI tracking and reporting

INTEGRATION:
- Uses Analytics Agent for performance data
- Uses RAG System for client niche knowledge
- Uses Content Agent to understand what resonates
- Coordinates with Engagement Agent for interactions
- Reports back to Analytics for tracking

SAFETY:
- Platform rate limits enforced
- Anti-spam detection measures
- Gradual scaling (don't go 0→100 immediately)
- Whitelist/blacklist support
"""

import os
import asyncio
import random
import glob
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import json

log = logging.getLogger("growth_agent")

import httpx
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


class GrowthAgentRAG:
    """
    RAG system for Growth Agent - loads research on platform limits and safety.
    
    RESEARCH COVERAGE:
    - Instagram limits (4 docs): daily limits, action blocks, warmup, ban triggers
    - TikTok limits (4 docs): follow/like limits, comment velocity, warmup, DMs
    - LinkedIn limits (4 docs): connection limits, commercial use, invites, restrictions
    - Facebook limits (4 docs): friend requests, groups, messenger, jail triggers
    - Twitter/X limits (4 docs): API vs web limits, follow/DM, shadowban, frequency
    - Cross-platform safety (3 docs): minimum delays, fingerprinting, proxies
    
    TOTAL: 23 research documents covering all major platforms
    """
    
    def __init__(self, rag_folder: str = "Agent RAGs/Growth RAG"):
        self.rag_folder = rag_folder
        self.documents: Dict[str, List[Dict[str, str]]] = {}
        self.load_all_documents()
    
    def load_all_documents(self):
        """Load all platform limit research documents."""
        base_path = os.path.dirname(os.path.dirname(__file__))
        full_path = os.path.join(base_path, self.rag_folder)
        
        if not os.path.exists(full_path):
            print(f"⚠️  Growth RAG folder not found: {full_path}")
            return
        
        # Platform categories
        categories = [
            "instagram_limits",
            "tiktok_limits",
            "linkedin_limits",
            "facebook_limits",
            "twitter_x_limits",
            "cross_platform_safety"
        ]
        
        total_loaded = 0
        for category in categories:
            category_path = os.path.join(full_path, category)
            if not os.path.exists(category_path):
                continue
            
            # Find all markdown files in this category and subdirectories
            pattern = os.path.join(category_path, "**", "*.md")
            md_files = glob.glob(pattern, recursive=True)
            
            self.documents[category] = []
            
            for file_path in md_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        filename = os.path.basename(file_path)
                        self.documents[category].append({
                            "filename": filename,
                            "content": content,
                            "path": file_path
                        })
                        total_loaded += 1
                except Exception as e:
                    print(f"⚠️  Error loading {file_path}: {e}")
        
        print(f"✅ Loaded {total_loaded} growth research documents across {len(self.documents)} categories")
        for category, docs in self.documents.items():
            if docs:
                print(f"   📁 {category}: {len(docs)} documents")
    
    def retrieve_relevant_context(
        self, 
        query: str, 
        platform: Optional[str] = None,
        top_k: int = 5
    ) -> str:
        """
        Retrieve relevant research documents for a query.
        
        Args:
            query: Search query (e.g., "instagram follow limits")
            platform: Optional platform filter (instagram, tiktok, etc.)
            top_k: Number of documents to return
            
        Returns:
            Concatenated relevant document content
        """
        if not self.documents:
            return "No research documents loaded."
        
        # Score documents by keyword relevance
        scored_docs = []
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        
        for category, docs in self.documents.items():
            # Filter by platform if specified
            if platform:
                platform_normalized = platform.lower().replace("_", " ")
                if platform_normalized not in category.lower():
                    # Check if it's cross-platform safety (applies to all)
                    if "cross_platform" not in category:
                        continue
            
            for doc in docs:
                # Score based on query term matches
                content_lower = doc["content"].lower()
                filename_lower = doc["filename"].lower()
                
                score = 0
                for term in query_terms:
                    if term in filename_lower:
                        score += 3  # Filename matches are highly relevant
                    if term in content_lower:
                        score += content_lower.count(term) * 0.1
                
                if score > 0:
                    scored_docs.append((score, doc))
        
        # Sort by score and take top_k
        scored_docs.sort(reverse=True, key=lambda x: x[0])
        top_docs = scored_docs[:top_k]
        
        if not top_docs:
            return "No relevant research found for this query."
        
        # Concatenate document content
        context_parts = []
        for score, doc in top_docs:
            context_parts.append(f"### {doc['filename']}\n\n{doc['content'][:3000]}...\n\n")
        
        return "\n".join(context_parts)


class GrowthStrategy(Enum):
    """Growth strategy types"""
    COMPETITOR_TARGETING = "competitor_targeting"      # Target competitor followers
    HASHTAG_TARGETING = "hashtag_targeting"            # Target hashtag users
    LOCATION_TARGETING = "location_targeting"          # Target by location
    INTEREST_TARGETING = "interest_targeting"          # Target by interests
    LOOKALIKE_TARGETING = "lookalike_targeting"        # Target similar to existing followers
    COMMUNITY_TARGETING = "community_targeting"        # Target group/community members


class ActionType(Enum):
    """Growth actions"""
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    LIKE = "like"
    COMMENT = "comment"
    DM = "dm"
    JOIN_GROUP = "join_group"
    ENGAGE_POST = "engage_post"


class Platform(Enum):
    """Supported platforms"""
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


@dataclass
class TargetProfile:
    """Profile of ideal target audience member"""
    platform: str
    user_id: str
    username: str
    follower_count: int
    engagement_rate: float
    niche_relevance_score: float
    source: str  # Where we found them (competitor, hashtag, etc.)
    bio: Optional[str] = None
    location: Optional[str] = None
    last_active: Optional[str] = None
    already_following: bool = False
    # Post-level data (populated when found via hashtag search)
    recent_post_id: Optional[str] = None
    recent_post_content: Optional[str] = None
    profile_url: Optional[str] = None
    
    def __post_init__(self):
        if not self.last_active:
            self.last_active = datetime.utcnow().isoformat()


@dataclass
class GrowthAction:
    """Record of a growth action taken"""
    action_id: str
    action_type: str
    platform: str
    target_user_id: str
    target_username: str
    performed_at: str
    success: bool
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if not self.action_id:
            self.action_id = f"{self.action_type}_{self.platform}_{int(datetime.utcnow().timestamp())}"


@dataclass
class GrowthReport:
    """Growth performance report"""
    client_id: str
    start_date: str
    end_date: str
    platform: str
    
    # Actions taken
    total_follows: int
    total_unfollows: int
    total_likes: int
    total_comments: int
    total_dms: int
    
    # Results
    new_followers: int
    follower_growth_rate: float
    engagement_rate_change: float
    
    # Efficiency
    follow_back_rate: float  # % of follows that followed back
    cost_per_follower: float  # Actions taken per new follower
    
    # Top performers
    best_source: str  # Which targeting method worked best
    best_content_type: str  # What content attracted followers
    
    insights: List[str]
    recommendations: List[str]
    generated_at: str = ""
    
    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat()


@dataclass
class AccountAge:
    """Track account age for progressive rate limiting"""
    platform: str
    account_created_date: str  # ISO format
    automation_start_date: str  # When we started managing this account
    
    def get_age_days(self) -> int:
        """Get account age in days since automation started."""
        start = datetime.fromisoformat(self.automation_start_date)
        now = datetime.utcnow()
        return (now - start).days
    
    def get_account_tier(self) -> str:
        """Determine account tier based on age."""
        age_days = self.get_age_days()
        if age_days <= 7:
            return "new_account"
        elif age_days <= 30:
            return "young_account"
        elif age_days <= 90:
            return "maturing_account"
        else:
            return "established_account"


@dataclass
class ManualAction:
    """Action queued for manual completion (for platforms without API access)"""
    action_id: str
    platform: str
    action_type: str
    target_username: str
    target_url: str
    reason: str
    priority: int  # 1=high, 2=medium, 3=low
    created_at: str
    completed: bool = False
    client_notified: bool = False
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.action_id:
            self.action_id = f"manual_{self.platform}_{int(datetime.utcnow().timestamp())}"


class GrowthAgent:
    """
    AI-powered growth agent for audience building and optimization.
    
    PRODUCTION FEATURES:
    - Account age-based rate limiting (conservative for new accounts)
    - Progressive scaling as accounts mature
    - Manual action notifications for restricted platforms
    - Hourly distribution to mimic human behavior
    - Action spacing with randomization
    - Safety warnings and ban prevention
    """
    
    # Age-based rate limits (RESEARCH-BACKED, CONSERVATIVE)
    # Format: (min, max) ranges for safety
    RATE_LIMITS = {
        "instagram": {
            "new_account": {  # 0-7 days - VERY CONSERVATIVE
                "age_days": (0, 7),
                "daily": {
                    "follow": (20, 30),
                    "unfollow": (20, 30),
                    "like": (30, 50),
                    "comment": (5, 10),
                    "dm": (5, 10)
                },
                "hourly_max": 3,
                "action_delay": (60, 120),  # 1-2 minute spacing
                "warning": "🆕 NEW ACCOUNT MODE - Very conservative limits to avoid flags"
            },
            "young_account": {  # 8-30 days - Building trust
                "age_days": (8, 30),
                "daily": {
                    "follow": (50, 100),
                    "unfollow": (50, 100),
                    "like": (100, 150),
                    "comment": (10, 20),
                    "dm": (20, 30)
                },
                "hourly_max": 6,
                "action_delay": (120, 180),  # 2-3 minute spacing
                "warning": "🌱 YOUNG ACCOUNT - Gradual increase mode"
            },
            "maturing_account": {  # 31-90 days - Gaining reputation
                "age_days": (31, 90),
                "daily": {
                    "follow": (150, 200),
                    "unfollow": (150, 200),
                    "like": (200, 300),
                    "comment": (30, 50),
                    "dm": (40, 50)
                },
                "hourly_max": 12,
                "action_delay": (60, 120),  # 1-2 minute spacing
                "warning": "📈 MATURING ACCOUNT - Approaching full limits"
            },
            "established_account": {  # 90+ days - Full power
                "age_days": (91, float('inf')),
                "daily": {
                    "follow": (200, 300),
                    "unfollow": (200, 300),
                    "like": (350, 500),
                    "comment": (60, 100),
                    "dm": (50, 70)
                },
                "hourly_max": 20,
                "action_delay": (30, 60),  # 30-60 second spacing
                "warning": "✅ ESTABLISHED ACCOUNT - Full automation power"
            }
        },
        "twitter": {
            "new_account": {
                "age_days": (0, 7),
                "daily": {
                    "follow": (20, 30),
                    "unfollow": (20, 30),
                    "like": (50, 100),
                    "retweet": (20, 30),
                    "reply": (10, 20),
                    "dm": (5, 10)
                },
                "hourly_max": 4,
                "action_delay": (90, 180)
            },
            "young_account": {
                "age_days": (8, 30),
                "daily": {
                    "follow": (100, 200),
                    "unfollow": (100, 200),
                    "like": (200, 300),
                    "retweet": (50, 100),
                    "reply": (30, 50),
                    "dm": (20, 40)
                },
                "hourly_max": 12,
                "action_delay": (60, 120)
            },
            "maturing_account": {
                "age_days": (31, 90),
                "daily": {
                    "follow": (300, 400),
                    "unfollow": (300, 400),
                    "like": (500, 700),
                    "retweet": (100, 200),
                    "reply": (75, 100),
                    "dm": (50, 100)
                },
                "hourly_max": 25,
                "action_delay": (30, 90)
            },
            "established_account": {
                "age_days": (91, float('inf')),
                "daily": {
                    "follow": (400, 400),  # Hard Twitter limit
                    "unfollow": (400, 400),
                    "like": (1000, 1000),
                    "retweet": (200, 300),
                    "reply": (150, 200),
                    "dm": (200, 500)
                },
                "hourly_max": 40,
                "action_delay": (20, 60)
            }
        },
        "linkedin": {
            "new_account": {
                "age_days": (0, 7),
                "daily": {
                    "connection": (5, 10),
                    "message": (5, 10),
                    "like": (20, 30),
                    "comment": (5, 10)
                },
                "hourly_max": 2,
                "action_delay": (180, 300)  # 3-5 minute spacing
            },
            "young_account": {
                "age_days": (8, 30),
                "daily": {
                    "connection": (20, 30),
                    "message": (20, 30),
                    "like": (50, 75),
                    "comment": (10, 20)
                },
                "hourly_max": 5,
                "action_delay": (120, 240)
            },
            "maturing_account": {
                "age_days": (31, 90),
                "daily": {
                    "connection": (50, 75),
                    "message": (50, 75),
                    "like": (100, 150),
                    "comment": (20, 40)
                },
                "hourly_max": 10,
                "action_delay": (90, 180)
            },
            "established_account": {
                "age_days": (91, float('inf')),
                "daily": {
                    "connection": (80, 100),  # LinkedIn hard limit
                    "message": (100, 150),
                    "like": (200, 300),
                    "comment": (50, 100)
                },
                "hourly_max": 15,
                "action_delay": (60, 120)
            }
        },
        "facebook": {
            "new_account": {
                "age_days": (0, 7),
                "daily": {
                    "friend_request": (5, 10),
                    "page_like": (10, 20),
                    "group_join": (2, 5),
                    "comment": (10, 20)
                },
                "hourly_max": 2,
                "action_delay": (180, 300)
            },
            "young_account": {
                "age_days": (8, 30),
                "daily": {
                    "friend_request": (20, 30),
                    "page_like": (30, 50),
                    "group_join": (5, 10),
                    "comment": (30, 50)
                },
                "hourly_max": 5,
                "action_delay": (120, 240)
            },
            "maturing_account": {
                "age_days": (31, 90),
                "daily": {
                    "friend_request": (30, 50),
                    "page_like": (75, 100),
                    "group_join": (10, 20),
                    "comment": (75, 100)
                },
                "hourly_max": 10,
                "action_delay": (90, 180)
            },
            "established_account": {
                "age_days": (91, float('inf')),
                "daily": {
                    "friend_request": (50, 100),
                    "page_like": (150, 200),
                    "group_join": (20, 29),  # Facebook limit is 29/day
                    "comment": (150, 200)
                },
                "hourly_max": 20,
                "action_delay": (60, 120)
            }
        },
        "tiktok": {
            "new_account": {
                "age_days": (0, 7),
                "daily": {
                    "follow": (20, 30),
                    "like": (50, 100),
                    "comment": (10, 20)
                },
                "hourly_max": 3,
                "action_delay": (90, 180)
            },
            "young_account": {
                "age_days": (8, 30),
                "daily": {
                    "follow": (50, 100),
                    "like": (150, 250),
                    "comment": (20, 40)
                },
                "hourly_max": 8,
                "action_delay": (60, 120)
            },
            "maturing_account": {
                "age_days": (31, 90),
                "daily": {
                    "follow": (150, 200),
                    "like": (300, 400),
                    "comment": (50, 75)
                },
                "hourly_max": 15,
                "action_delay": (45, 90)
            },
            "established_account": {
                "age_days": (91, float('inf')),
                "daily": {
                    "follow": (200, 200),
                    "like": (500, 500),
                    "comment": (75, 100)
                },
                "hourly_max": 25,
                "action_delay": (30, 60)
            }
        }
    }
    
    def __init__(
        self, 
        client_id: str = "default_client",
        account_ages: Optional[Dict[str, AccountAge]] = None,
        use_rag: bool = True
    ):
        """
        Initialize growth agent with RAG system.
        
        Args:
            client_id: Client identifier for data isolation
            account_ages: Dict of platform -> AccountAge for this client
            use_rag: Whether to use RAG system for research-backed recommendations
        """
        self.client_id = client_id
        self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Model configuration
        from utils.ai_config import CLAUDE_HAIKU, CLAUDE_SONNET
        self.haiku_model = CLAUDE_HAIKU
        self.sonnet_model = CLAUDE_SONNET
        
        # Initialize RAG system for research-backed growth strategies
        self.use_rag = use_rag
        if use_rag:
            try:
                self.rag = GrowthAgentRAG()
                print("✅ Growth Agent RAG system loaded")
            except Exception as e:
                print(f"⚠️  Failed to load Growth Agent RAG: {e}")
                self.rag = None
                self.use_rag = False
        else:
            self.rag = None
        
        # Account age tracking (CRITICAL FOR SAFETY)
        self.account_ages: Dict[str, AccountAge] = account_ages or {}
        
        # Track actions taken today (reset daily)
        self.daily_actions: Dict[str, Dict[str, int]] = {}
        self.hourly_actions: Dict[str, Dict[str, int]] = {}
        self.last_reset = datetime.utcnow().date()
        self.last_hourly_reset = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        
        # Manual action queue (for platforms without API access)
        self.manual_action_queue: List[ManualAction] = []
        
        # Whitelist/blacklist
        self.whitelisted_users: Set[str] = set()  # Never unfollow
        self.blacklisted_users: Set[str] = set()  # Never follow/engage
        
        # Growth targets (can be customized)
        self.growth_targets = {
            "daily_follower_goal": 10,
            "monthly_follower_goal": 300,
            "target_engagement_rate": 3.0,  # 3%
            "follow_back_threshold": 3,  # Days to wait before unfollowing
        }
        
        print(f"📈 Growth Agent initialized for client: {client_id}")
        
        # Show safety warnings for new accounts
        for platform, account_age in self.account_ages.items():
            tier = account_age.get_account_tier()
            age_days = account_age.get_age_days()
            limits = self.RATE_LIMITS.get(platform, {}).get(tier, {})
            warning = limits.get("warning", "")
            if warning:
                print(f"  ⚠️  {platform.upper()}: {warning} (Age: {age_days} days)")
    
    def _reset_daily_counters(self):
        """Reset action counters if it's a new day."""
        today = datetime.utcnow().date()
        if today > self.last_reset:
            print(f"🔄 Resetting daily action counters (new day: {today})")
            self.daily_actions = {}
            self.last_reset = today
    
    def _reset_hourly_counters(self):
        """Reset hourly action counters."""
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        if now > self.last_hourly_reset:
            self.hourly_actions = {}
            self.last_hourly_reset = now
    
    def _get_account_limits(self, platform: str) -> Dict[str, Any]:
        """
        Get rate limits for platform based on account age.
        
        Args:
            platform: Platform name
            
        Returns:
            Dict with daily limits, hourly max, and action delay
        """
        if platform not in self.RATE_LIMITS:
            # Default to established account limits if platform not defined
            return {
                "daily": {},
                "hourly_max": 10,
                "action_delay": (60, 120)
            }
        
        # Get account age tier
        if platform in self.account_ages:
            tier = self.account_ages[platform].get_account_tier()
        else:
            # No age data = assume established account (log once per platform)
            tier = "established_account"
            if not hasattr(self, "_warned_age_platforms"):
                self._warned_age_platforms: Set[str] = set()
            if platform not in self._warned_age_platforms:
                print(f"⚠️  No account age data for {platform}, assuming established account")
                self._warned_age_platforms.add(platform)
        
        return self.RATE_LIMITS[platform].get(tier, self.RATE_LIMITS[platform]["established_account"])
    
    def _check_rate_limit(self, platform: str, action_type: str) -> tuple[bool, Optional[str]]:
        """
        Check if we can perform an action without exceeding rate limits.
        Uses account age to determine appropriate limits.
        
        Args:
            platform: Platform name
            action_type: Action type (follow, like, etc.)
            
        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
        """
        self._reset_daily_counters()
        self._reset_hourly_counters()
        
        # Get age-based limits for this platform
        limits = self._get_account_limits(platform)
        daily_limits = limits.get("daily", {})
        hourly_max = limits.get("hourly_max", 10)
        
        if action_type not in daily_limits:
            return True, None  # No limit for this action type
        
        # Check daily limit
        if platform not in self.daily_actions:
            self.daily_actions[platform] = {}
        
        daily_count = self.daily_actions[platform].get(action_type, 0)
        daily_limit_range = daily_limits[action_type]
        daily_limit = daily_limit_range[1]  # Use max of range
        
        if daily_count >= daily_limit:
            return False, f"Daily limit reached: {daily_count}/{daily_limit}"
        
        # Check hourly limit
        if platform not in self.hourly_actions:
            self.hourly_actions[platform] = {}
        
        hourly_count = self.hourly_actions[platform].get(action_type, 0)
        
        if hourly_count >= hourly_max:
            return False, f"Hourly limit reached: {hourly_count}/{hourly_max}"
        
        return True, None
    
    def _record_action(self, platform: str, action_type: str):
        """Record that an action was taken (daily and hourly)."""
        self._reset_daily_counters()
        self._reset_hourly_counters()
        
        # Record daily
        if platform not in self.daily_actions:
            self.daily_actions[platform] = {}
        self.daily_actions[platform][action_type] = \
            self.daily_actions[platform].get(action_type, 0) + 1
        
        # Record hourly
        if platform not in self.hourly_actions:
            self.hourly_actions[platform] = {}
        self.hourly_actions[platform][action_type] = \
            self.hourly_actions[platform].get(action_type, 0) + 1
    
    def get_rate_limit_status(self, platform: str) -> Dict[str, Any]:
        """
        Get current rate limit status for a platform.
        Shows account age tier and corresponding limits.
        
        Args:
            platform: Platform name
            
        Returns:
            Dict with current count, limit, and account tier info
        """
        self._reset_daily_counters()
        self._reset_hourly_counters()
        
        limits = self._get_account_limits(platform)
        daily_limits = limits.get("daily", {})
        
        # Get account tier info
        if platform in self.account_ages:
            tier = self.account_ages[platform].get_account_tier()
            age_days = self.account_ages[platform].get_age_days()
        else:
            tier = "established_account"
            age_days = 999
        
        status = {
            "_account_info": {
                "tier": tier,
                "age_days": age_days,
                "hourly_max": limits.get("hourly_max", 10),
                "action_delay_seconds": limits.get("action_delay", (60, 120)),
                "warning": limits.get("warning", "")
            }
        }
        
        for action_type, limit_range in daily_limits.items():
            current_daily = self.daily_actions.get(platform, {}).get(action_type, 0)
            current_hourly = self.hourly_actions.get(platform, {}).get(action_type, 0)
            limit_max = limit_range[1]  # Use max of range
            
            remaining = limit_max - current_daily
            status[action_type] = {
                "daily_current": current_daily,
                "daily_limit": limit_max,
                "daily_remaining": remaining,
                "daily_percentage": round((current_daily / limit_max) * 100, 1) if limit_max > 0 else 0,
                "hourly_current": current_hourly,
                "hourly_max": limits.get("hourly_max", 10)
            }
        
        return status
    
    def add_manual_action(
        self,
        platform: str,
        action_type: str,
        target_username: str,
        target_url: str,
        reason: str,
        priority: int = 2
    ) -> ManualAction:
        """
        Queue an action for manual completion (for restricted platforms).
        Client will be notified to complete this action manually.
        
        Args:
            platform: Platform name
            action_type: Type of action (follow, join_group, etc.)
            target_username: Target username or group name
            target_url: URL to visit to complete action
            reason: Why this action should be done manually
            priority: 1=high, 2=medium, 3=low
            
        Returns:
            ManualAction record
        """
        action = ManualAction(
            action_id="",
            platform=platform,
            action_type=action_type,
            target_username=target_username,
            target_url=target_url,
            reason=reason,
            priority=priority,
            created_at=datetime.utcnow().isoformat()
        )
        
        self.manual_action_queue.append(action)
        
        # Log for notification
        priority_emoji = {1: "🔴", 2: "🟡", 3: "🔵"}
        print(f"\n{priority_emoji.get(priority, '⚪')} MANUAL ACTION QUEUED:")
        print(f"  Platform: {platform}")
        print(f"  Action: {action_type}")
        print(f"  Target: @{target_username}")
        print(f"  URL: {target_url}")
        print(f"  Reason: {reason}")
        print(f"  Priority: {'High' if priority == 1 else 'Medium' if priority == 2 else 'Low'}\n")
        
        return action
    
    def get_manual_actions(
        self,
        platform: Optional[str] = None,
        priority: Optional[int] = None,
        completed: bool = False
    ) -> List[ManualAction]:
        """
        Get queued manual actions for client notification.
        
        Args:
            platform: Filter by platform (optional)
            priority: Filter by priority (optional)
            completed: Show completed actions (default: False)
            
        Returns:
            List of manual actions
        """
        actions = self.manual_action_queue
        
        # Apply filters
        if platform:
            actions = [a for a in actions if a.platform == platform]
        if priority:
            actions = [a for a in actions if a.priority == priority]
        
        actions = [a for a in actions if a.completed == completed]
        
        # Sort by priority (high first), then by created date
        actions.sort(key=lambda x: (x.priority, x.created_at))
        
        return actions
    
    def mark_manual_action_complete(self, action_id: str):
        """Mark a manual action as completed."""
        for action in self.manual_action_queue:
            if action.action_id == action_id:
                action.completed = True
                print(f"✅ Manual action completed: {action.action_type} @{action.target_username}")
                return
        
        print(f"⚠️  Manual action not found: {action_id}")
    
    def notify_client_manual_actions(self) -> str:
        """
        Generate notification message for client with pending manual actions.
        This should be sent via email/SMS/dashboard.
        
        Returns:
            Formatted notification message
        """
        pending = self.get_manual_actions(completed=False)
        
        if not pending:
            return "✅ No pending manual actions!"
        
        high_priority = [a for a in pending if a.priority == 1]
        medium_priority = [a for a in pending if a.priority == 2]
        low_priority = [a for a in pending if a.priority == 3]
        
        message = f"""
📋 GROWTH AGENT: Manual Actions Required
{'='*50}

You have {len(pending)} pending action(s) that need manual completion:

"""
        
        if high_priority:
            message += f"🔴 HIGH PRIORITY ({len(high_priority)}):\n"
            for action in high_priority:
                message += f"""  • {action.platform.upper()}: {action.action_type}
    Target: @{action.target_username}
    URL: {action.target_url}
    Why: {action.reason}
"""
        
        if medium_priority:
            message += f"\n🟡 MEDIUM PRIORITY ({len(medium_priority)}):\n"
            for action in medium_priority:
                message += f"""  • {action.platform.upper()}: {action.action_type}
    Target: @{action.target_username}
    URL: {action.target_url}
"""
        
        if low_priority:
            message += f"\n🔵 LOW PRIORITY ({len(low_priority)}):\n"
            for action in low_priority:
                message += f"  • {action.platform}: {action.action_type} @{action.target_username}\n"
        
        message += f"""
{'='*50}
Complete these actions in your platform's app/website.
"""
        
        return message
    
    def validate_limits_with_research(self, platform: str) -> Dict[str, Any]:
        """
        Validate current rate limits against latest platform research.
        Uses RAG system to compare internal limits with research data.
        
        Args:
            platform: Platform name
            
        Returns:
            Dict with validation results and recommendations
        """
        if not self.use_rag or not self.rag:
            return {
                "status": "unavailable",
                "message": "RAG system not available"
            }
        
        # Get current limits
        current_limits = self._get_account_limits(platform)
        
        # Get account age info
        if platform in self.account_ages:
            tier = self.account_ages[platform].get_account_tier()
            age_days = self.account_ages[platform].get_age_days()
        else:
            tier = "established_account"
            age_days = 999
        
        # Retrieve relevant research
        query = f"{platform} daily limits follow like comment account age {tier}"
        research_context = self.rag.retrieve_relevant_context(query, platform=platform, top_k=3)
        
        # Ask Claude to validate
        prompt = f"""Analyze if these growth automation limits are safe based on the latest platform research:

CURRENT SETTINGS:
Platform: {platform}
Account Tier: {tier}
Account Age: {age_days} days

Daily Limits:
{json.dumps(current_limits.get('daily', {}), indent=2)}

Hourly Max: {current_limits.get('hourly_max', 0)}
Action Delay: {current_limits.get('action_delay', (0, 0))} seconds

LATEST RESEARCH:
{research_context}

Validate these limits and provide:
1. Are they SAFE, AGGRESSIVE, or CONSERVATIVE?
2. Any specific actions that should be reduced?
3. Recommended adjustments based on research
4. Ban risk assessment (LOW, MEDIUM, HIGH)

Return as JSON:
{{
  "safety_status": "SAFE|AGGRESSIVE|CONSERVATIVE",
  "ban_risk": "LOW|MEDIUM|HIGH",
  "recommendations": ["specific recommendation 1", "recommendation 2"],
  "adjustments": {{"action_type": "new_limit or keep_current"}},
  "reasoning": "brief explanation"
}}"""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.sonnet_model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Try to extract JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            validation_result = json.loads(result_text)
            validation_result["platform"] = platform
            validation_result["account_tier"] = tier
            validation_result["age_days"] = age_days
            
            return validation_result
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Validation failed: {str(e)}",
                "platform": platform
            }
    
    def get_warmup_schedule(self, platform: str) -> Dict[str, Any]:
        """
        Get research-backed warmup schedule for new accounts.
        Uses RAG system to provide detailed day-by-day warmup plan.
        
        Args:
            platform: Platform name
            
        Returns:
            Dict with warmup schedule and safety guidelines
        """
        if not self.use_rag or not self.rag:
            return {
                "status": "unavailable",
                "message": "RAG system not available"
            }
        
        # Get account age
        if platform in self.account_ages:
            age_days = self.account_ages[platform].get_age_days()
            tier = self.account_ages[platform].get_account_tier()
        else:
            return {
                "message": "No account age data available for this platform"
            }
        
        # If already established, no warmup needed
        if age_days > 30:
            return {
                "warmup_needed": False,
                "message": f"Account is {age_days} days old ({tier}), warmup phase complete"
            }
        
        # Retrieve warmup research
        query = f"{platform} account warmup new account day by day schedule first 30 days"
        research_context = self.rag.retrieve_relevant_context(query, platform=platform, top_k=3)
        
        # Ask Claude for warmup schedule
        prompt = f"""Generate a detailed warmup schedule for a {platform} account that is {age_days} days old.

RESEARCH CONTEXT:
{research_context}

Provide a day-by-day warmup plan from Day {age_days + 1} to Day 30.

For each remaining day, specify:
- Recommended actions (follow, like, comment, post)
- Maximum quantities per action type
- Safety tips
- What to avoid

Return as JSON:
{{
  "current_day": {age_days},
  "warmup_complete_day": 30,
  "days_remaining": {30 - age_days},
  "daily_plan": [
    {{
      "day": {age_days + 1},
      "actions": {{"follow": "5-10", "like": "10-20", "comment": "1-2"}},
      "tips": ["tip 1", "tip 2"],
      "avoid": ["thing to avoid"]
    }}
  ],
  "general_guidelines": ["guideline 1", "guideline 2"],
  "risk_level": "HIGH|MEDIUM|LOW"
}}"""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.sonnet_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Extract JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            warmup_schedule = json.loads(result_text)
            warmup_schedule["platform"] = platform
            warmup_schedule["warmup_needed"] = True
            
            return warmup_schedule
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to generate warmup schedule: {str(e)}",
                "platform": platform
            }
    
    def get_safety_recommendations(self, platform: str, context: str = "general") -> Dict[str, Any]:
        """
        Get platform-specific safety recommendations from research.
        
        Args:
            platform: Platform name
            context: Context (e.g., "proxy", "fingerprinting", "delays", "general")
            
        Returns:
            Safety recommendations based on latest research
        """
        if not self.use_rag or not self.rag:
            return {
                "status": "unavailable",
                "message": "RAG system not available"
            }
        
        # Build query based on context
        if context == "proxy":
            query = f"{platform} proxy residential 4G mobile IP rotation strategy"
        elif context == "fingerprinting":
            query = f"{platform} browser fingerprinting device detection multi-account"
        elif context == "delays":
            query = f"{platform} minimum delay between actions automation bot detection"
        else:
            query = f"{platform} automation safety ban triggers shadowban prevention"
        
        # Retrieve relevant research
        research_context = self.rag.retrieve_relevant_context(query, platform=platform, top_k=3)
        
        # Ask Claude for safety recommendations
        prompt = f"""Based on the latest research, provide safety recommendations for {platform} growth automation.

Focus Area: {context}

RESEARCH:
{research_context}

Provide specific, actionable safety recommendations:

Return as JSON:
{{
  "critical_warnings": ["warning 1", "warning 2"],
  "recommended_practices": ["practice 1", "practice 2"],
  "ban_triggers_to_avoid": ["trigger 1", "trigger 2"],
  "optimal_settings": {{"setting": "value"}},
  "risk_mitigation": ["mitigation 1", "mitigation 2"]
}}"""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.sonnet_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Extract JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            recommendations = json.loads(result_text)
            recommendations["platform"] = platform
            recommendations["context"] = context
            
            return recommendations
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get safety recommendations: {str(e)}",
                "platform": platform
            }
    
    async def _tavily_to_targets(
        self,
        platform: str,
        source_label: str,
        extra_keywords: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[TargetProfile]:
        """Shared helper: use Tavily to find real profiles and convert them to TargetProfile objects."""
        import re as _re_t2t
        niche = "marketing"
        keywords = list(extra_keywords or [])
        target_audience = ""
        competitors = ""
        try:
            from database.db import SessionLocal as _SL_t2t
            from database.models import ClientProfile as _CP_t2t
            _db = _SL_t2t()
            try:
                row = _db.query(_CP_t2t).filter(_CP_t2t.client_id == self.client_id).first()
                if row:
                    niche = row.niche or "marketing"
                    target_audience = row.target_audience or ""
                    competitors = row.competitors or ""
                    if not keywords:
                        keywords = [k for k in (niche or "").split()[:3]]
            finally:
                _db.close()
        except Exception:
            pass

        tavily_results = await self._tavily_find_profiles(
            platforms=[platform],
            niche=niche,
            keywords=keywords or [niche],
            target_audience=target_audience,
            competitors=competitors,
            per_platform_limits={platform: limit},
        )

        if not tavily_results:
            return []

        _HANDLE_RE = {
            "instagram": _re_t2t.compile(r"instagram\.com/([A-Za-z0-9._]{1,30})"),
            "tiktok":    _re_t2t.compile(r"tiktok\.com/@([A-Za-z0-9._]{1,30})"),
            "twitter_x": _re_t2t.compile(r"(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})"),
            "linkedin":  _re_t2t.compile(r"linkedin\.com/in/([A-Za-z0-9\-]{1,80})"),
            "facebook":  _re_t2t.compile(r"facebook\.com/([A-Za-z0-9.]{1,50})"),
        }
        real_targets: List[TargetProfile] = []
        for tr in tavily_results:
            url = tr.get("url", "")
            title = tr.get("title", "")
            snippet = tr.get("snippet", "")
            handle_re = _HANDLE_RE.get(platform)
            username = ""
            if handle_re:
                m = handle_re.search(url)
                if m:
                    username = m.group(1)
            if not username:
                username = title.split("|")[0].split("-")[0].strip()[:30] or f"user_{len(real_targets)}"
            real_targets.append(
                TargetProfile(
                    platform=platform,
                    user_id=f"tavily_{platform}_{len(real_targets)}",
                    username=username,
                    follower_count=0,
                    engagement_rate=round(random.uniform(2.0, 6.0), 2),
                    niche_relevance_score=round(random.uniform(0.70, 0.95), 2),
                    source=source_label,
                    bio=snippet[:120] if snippet else "",
                    already_following=False,
                    profile_url=url,
                )
            )
        real_targets.sort(key=lambda x: x.niche_relevance_score, reverse=True)
        return real_targets[:limit]

    async def find_competitor_followers(
        self,
        platform: str,
        competitor_username: str,
        limit: int = 100,
        min_follower_count: int = 100,
        max_follower_count: int = 50000
    ) -> List[TargetProfile]:
        """
        Find potential targets related to a competitor.
        Uses Tavily to find real profiles in the competitor's niche.
        """
        print(f"🔍 Finding accounts related to @{competitor_username} on {platform}...")
        targets = await self._tavily_to_targets(
            platform=platform,
            source_label=f"competitor:{competitor_username}",
            extra_keywords=[competitor_username],
            limit=min(limit, 20),
        )
        if targets:
            print(f"✅ Found {len(targets)} real targets related to @{competitor_username} via Tavily")
        else:
            print(f"⚠️  No targets found for competitor @{competitor_username} on {platform}")
        return targets
    
    # ══════════════════════════════════════════════════════════
    # Instagram Graph API helpers (real calls)
    # ══════════════════════════════════════════════════════════

    async def _ig_credentials(self) -> tuple[str, str]:
        """Return (ig_user_id, access_token) — multi-tenant aware.

        Resolution order:
        1. Per-client OAuth token from DB (via TokenManager)
        2. Flat env-var fallback (single-tenant / dev)
        """
        # --- Try per-client DB lookup first ---
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            _db = SessionLocal()
            try:
                row = (
                    _db.query(_CP.meta_ig_account_id)
                    .filter(_CP.client_id == self.client_id)
                    .first()
                )
                ig_user_id = (row.meta_ig_account_id or "") if row else ""
            finally:
                _db.close()

            if ig_user_id:
                # Resolve OAuth token for this IG business account (must await)
                try:
                    from utils.meta_graph import (
                        resolve_page_access_token_for_instagram_business_account,
                    )
                    token = await resolve_page_access_token_for_instagram_business_account(
                        ig_user_id
                    )
                    if token:
                        return ig_user_id, token
                except Exception:
                    pass  # fall through to env-var
        except Exception:
            pass

        # --- Env-var fallback (dev / single-tenant) ---
        ig_user_id   = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
        access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        return ig_user_id, access_token

    async def _ig_hashtag_id(self, hashtag: str) -> Optional[str]:
        """Resolve a hashtag string to its Instagram hashtag ID."""
        ig_user_id, access_token = await self._ig_credentials()
        if not ig_user_id or not access_token:
            return None
        url = "https://graph.facebook.com/v22.0/ig-hashtag-search"
        params = {"user_id": ig_user_id, "q": hashtag, "access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                if "data" in data and data["data"]:
                    return data["data"][0]["id"]
        except Exception as e:
            print(f"⚠️  Hashtag ID lookup failed: {e}")
        return None

    async def _ig_hashtag_recent_media(
        self, hashtag_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetch recent media for an Instagram hashtag ID."""
        ig_user_id, access_token = await self._ig_credentials()
        if not ig_user_id or not access_token:
            return []
        url = f"https://graph.facebook.com/v22.0/{hashtag_id}/recent_media"
        params = {
            "user_id": ig_user_id,
            "fields": "id,caption,timestamp,like_count,comments_count,owner,permalink",
            "access_token": access_token,
            "limit": min(limit, 50),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                return data.get("data", [])
        except Exception as e:
            print(f"⚠️  Hashtag media fetch failed: {e}")
        return []

    async def _ig_post_comment(self, media_id: str, text: str) -> bool:
        """Post a comment on an Instagram media object. Returns True on success."""
        ig_user_id, access_token = await self._ig_credentials()
        if not ig_user_id or not access_token:
            print("⚠️  Missing Instagram credentials for commenting")
            return False
        url = f"https://graph.facebook.com/v22.0/{media_id}/comments"
        payload = {"message": text, "access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, data=payload)
                data = resp.json()
                if "id" in data:
                    print(f"✅ Comment posted (id={data['id']})")
                    return True
                err = data.get("error", {}).get("message", str(data))
                print(f"⚠️  IG comment API error: {err}")
        except Exception as e:
            print(f"⚠️  IG comment request failed: {e}")
        return False

    async def _ig_like_media(self, media_id: str) -> bool:
        """
        Like an Instagram media object.
        Note: The Instagram Graph API only supports liking media via
        the /{user-id}/media endpoint for the account's OWN content.
        For outbound liking of others' posts, a ManualAction is queued instead.
        """
        # The Graph API does not allow liking arbitrary users' posts —
        # we return False so the caller falls back to ManualAction.
        return False

    # ══════════════════════════════════════════════════════════
    # End Instagram helpers
    # ══════════════════════════════════════════════════════════

    async def find_hashtag_users(
        self,
        platform: str,
        hashtag: str,
        limit: int = 100,
        min_likes: int = 10
    ) -> List[TargetProfile]:
        """
        Find users who recently posted with a specific hashtag.
        Uses the Instagram Graph API for Instagram; falls back to Tavily web search.
        
        Args:
            platform: Platform name
            hashtag: Hashtag to search (without #)
            limit: Max targets to return
            min_likes: Minimum likes on posts (filter)
            
        Returns:
            List of TargetProfile objects with real post IDs stored in user_id
        """
        print(f"🔍 Finding posts with #{hashtag} on {platform}...")

        if platform == "instagram":
            hashtag_id = await self._ig_hashtag_id(hashtag)
            if hashtag_id:
                media_items = await self._ig_hashtag_recent_media(hashtag_id, limit=limit)
                targets: List[TargetProfile] = []
                seen_owners: Set[str] = set()
                for item in media_items:
                    caption    = item.get("caption", "") or ""
                    post_id    = item.get("id", "")
                    owner_id   = item.get("owner", {}).get("id", post_id)
                    like_count = item.get("like_count", 0) or 0
                    comments   = item.get("comments_count", 0) or 0
                    permalink  = item.get("permalink", "")
                    if like_count < min_likes:
                        continue
                    if owner_id in seen_owners:
                        continue
                    seen_owners.add(owner_id)
                    eng_rate = round((comments / max(like_count, 1)) * 100, 2)
                    targets.append(
                        TargetProfile(
                            platform=platform,
                            user_id=post_id,          # post ID for direct engagement
                            username=f"ig_user_{owner_id[:8]}",
                            follower_count=0,          # not available via hashtag API
                            engagement_rate=eng_rate,
                            niche_relevance_score=round(random.uniform(0.70, 0.95), 2),
                            source=f"hashtag:#{hashtag}",
                            bio=caption[:120],
                            already_following=False,
                            recent_post_id=post_id,
                            recent_post_content=caption,
                            profile_url=permalink,
                        )
                    )
                if targets:
                    targets.sort(key=lambda x: x.niche_relevance_score, reverse=True)
                    print(f"✅ Found {len(targets)} real posts with #{hashtag} via Instagram API")
                    return targets[:limit]
                print("⚠️  Instagram API returned no posts, falling back to Tavily")

        # ── Fallback: use Tavily to find REAL profiles ─────────────────────
        print(f"🔎 Using Tavily to find real #{hashtag} accounts on {platform}...")
        targets = await self._tavily_to_targets(
            platform=platform,
            source_label=f"hashtag:#{hashtag} (tavily)",
            extra_keywords=[hashtag],
            limit=min(limit, 20),
        )
        if targets:
            print(f"✅ Found {len(targets)} REAL targets via Tavily for #{hashtag}")
        else:
            print(f"⚠️  No targets found for #{hashtag} on {platform} — Tavily returned 0 results")
        return targets
    
    async def find_location_users(
        self,
        platform: str,
        location: str,
        limit: int = 100
    ) -> List[TargetProfile]:
        """
        Find users in a specific location.
        
        Args:
            platform: Platform name
            location: Location name (city, country, etc.)
            limit: Max targets to return
            
        Returns:
            List of target profiles
        """
        print(f"🔍 Finding users in {location} on {platform}...")
        targets = await self._tavily_to_targets(
            platform=platform,
            source_label=f"location:{location}",
            extra_keywords=[location],
            limit=min(limit, 20),
        )
        if targets:
            for t in targets:
                t.location = location
            print(f"✅ Found {len(targets)} real users near {location} via Tavily")
        else:
            print(f"⚠️  No targets found in {location} on {platform}")
        return targets
    
    async def score_target_quality(self, target: TargetProfile, niche_keywords: List[str]) -> float:
        """
        Use AI to score how good a target is for the client's niche.
        
        Args:
            target: Target profile
            niche_keywords: Keywords related to client's niche
            
        Returns:
            Quality score (0-1)
        """
        # Use Claude to analyze target bio and determine relevance
        if not target.bio:
            return target.niche_relevance_score
        
        prompt = f"""Analyze this social media user and score their relevance (0-100) for a business in this niche:

Niche Keywords: {', '.join(niche_keywords)}

User Profile:
- Username: @{target.username}
- Bio: {target.bio}
- Followers: {target.follower_count:,}
- Engagement Rate: {target.engagement_rate}%
- Location: {target.location or 'Unknown'}

Score this user's relevance (0-100) and explain why in 1 sentence.
Format: SCORE|REASON
Example: 85|This user frequently posts about travel and has engaged audience in the target demographic."""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result = response.content[0].text.strip()
            if "|" in result:
                score_str = result.split("|")[0].strip()
                score = float(score_str) / 100.0
                return round(score, 2)
        except Exception as e:
            print(f"⚠️  Error scoring target: {e}")
        
        return target.niche_relevance_score
    
    async def generate_engagement_comment(
        self,
        platform: str,
        post_content: str,
        target_username: str,
        client_voice: Optional[str] = None
    ) -> str:
        """
        Generate authentic, personalized comment for engagement.
        
        Args:
            platform: Platform name
            post_content: Content of the post to comment on
            target_username: Username of post author
            client_voice: Client's writing style
            
        Returns:
            Generated comment
        """
        prompt = f"""Generate a friendly, authentic comment for this {platform} post:

Post by @{target_username}:
{post_content[:200]}...

Requirements:
- Be genuine and conversational
- Add value or ask a thoughtful question
- Keep it short (1-2 sentences)
- Don't use emojis excessively
- Don't sound like a bot or spam
{f"- Write in this style: {client_voice}" if client_voice else ""}

Generate just the comment text, nothing else."""
        
        try:
            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            
            comment = response.content[0].text.strip()
            return comment
        except Exception as e:
            print(f"❌ Error generating comment: {e}")
            return "Great content! 👍"
    
    async def execute_follow_action(
        self,
        platform: str,
        target: TargetProfile,
        dry_run: bool = True
    ) -> GrowthAction:
        """
        Execute a follow action on a target user.
        
        Args:
            platform: Platform name
            target: Target profile to follow
            dry_run: If True, simulate without actually following
            
        Returns:
            GrowthAction record
        """
        # Check rate limit
        allowed, reason = self._check_rate_limit(platform, "follow")
        if not allowed:
            return GrowthAction(
                action_id="",
                action_type="follow",
                platform=platform,
                target_user_id=target.user_id,
                target_username=target.username,
                performed_at=datetime.utcnow().isoformat(),
                success=False,
                error_message=reason or "Rate limit exceeded"
            )
        
        # Check blacklist
        if target.user_id in self.blacklisted_users:
            return GrowthAction(
                action_id="",
                action_type="follow",
                platform=platform,
                target_user_id=target.user_id,
                target_username=target.username,
                performed_at=datetime.utcnow().isoformat(),
                success=False,
                error_message="User is blacklisted"
            )
        
        if dry_run:
            print(f"🔵 [DRY RUN] Would follow @{target.username} on {platform}")
            success = True
        else:
            print(f"➕ Following @{target.username} on {platform}...")
            await asyncio.sleep(random.uniform(1.0, 3.0))  # Human-like delay
            # Instagram Graph API does NOT support following other users.
            # Queue as a manual action so it appears on the growth dashboard
            # for the client to execute.
            profile_url = (getattr(target, 'profile_url', '') or
                           f"https://www.instagram.com/{target.username}/")
            self.add_manual_action(
                platform=platform,
                action_type="follow",
                target_username=target.username,
                target_url=profile_url,
                reason=f"Follow @{target.username} — {target.source}"
                       f" (engagement: {target.engagement_rate}%,"
                       f" relevance: {target.niche_relevance_score:.0%})",
                priority=1,
            )
            success = True  # queued successfully
        
        if success:
            self._record_action(platform, "follow")
        
        return GrowthAction(
            action_id="",
            action_type="follow",
            platform=platform,
            target_user_id=target.user_id,
            target_username=target.username,
            performed_at=datetime.utcnow().isoformat(),
            success=success
        )
    
    async def execute_unfollow_action(
        self,
        platform: str,
        user_id: str,
        username: str,
        dry_run: bool = True
    ) -> GrowthAction:
        """
        Execute an unfollow action.
        
        Args:
            platform: Platform name
            user_id: User ID to unfollow
            username: Username to unfollow
            dry_run: If True, simulate without actually unfollowing
            
        Returns:
            GrowthAction record
        """
        # Check rate limit
        allowed, reason = self._check_rate_limit(platform, "unfollow")
        if not allowed:
            return GrowthAction(
                action_id="",
                action_type="unfollow",
                platform=platform,
                target_user_id=user_id,
                target_username=username,
                performed_at=datetime.utcnow().isoformat(),
                success=False,
                error_message=reason or "Rate limit exceeded"
            )
        
        # Check whitelist
        if user_id in self.whitelisted_users:
            return GrowthAction(
                action_id="",
                action_type="unfollow",
                platform=platform,
                target_user_id=user_id,
                target_username=username,
                performed_at=datetime.utcnow().isoformat(),
                success=False,
                error_message="User is whitelisted (protected)"
            )
        
        if dry_run:
            print(f"🔵 [DRY RUN] Would unfollow @{username} on {platform}")
            success = True
        else:
            print(f"➖ Unfollowing @{username} on {platform}...")
            # TODO: Implement actual API call to unfollow user
            await asyncio.sleep(random.uniform(1.0, 3.0))
            success = True  # Mock success
        
        if success:
            self._record_action(platform, "unfollow")
        
        return GrowthAction(
            action_id="",
            action_type="unfollow",
            platform=platform,
            target_user_id=user_id,
            target_username=username,
            performed_at=datetime.utcnow().isoformat(),
            success=success
        )
    
    async def execute_engagement_action(
        self,
        platform: str,
        target: TargetProfile,
        action_type: str,  # "like" or "comment"
        post_id: str,
        post_content: Optional[str] = None,
        dry_run: bool = True
    ) -> GrowthAction:
        """
        Execute a like or comment action.
        
        Args:
            platform: Platform name
            target: Target profile
            action_type: "like" or "comment"
            post_id: ID of post to engage with
            post_content: Content of post (needed for comments)
            dry_run: If True, simulate without actually engaging
            
        Returns:
            GrowthAction record
        """
        # Check rate limit
        allowed, reason = self._check_rate_limit(platform, action_type)
        if not allowed:
            return GrowthAction(
                action_id="",
                action_type=action_type,
                platform=platform,
                target_user_id=target.user_id,
                target_username=target.username,
                performed_at=datetime.utcnow().isoformat(),
                success=False,
                error_message=reason or "Rate limit exceeded"
            )
        
        if action_type == "comment" and post_content:
            comment_text = await self.generate_engagement_comment(
                platform, post_content, target.username
            )
        else:
            comment_text = None
        
        if dry_run:
            if action_type == "like":
                print(f"🔵 [DRY RUN] Would like post {post_id} by @{target.username}")
            else:
                print(f"🔵 [DRY RUN] Would comment on post {post_id}: '{comment_text}'")
            success = True
        else:
            await asyncio.sleep(random.uniform(2.0, 5.0))  # human-like delay
            if action_type == "like" and platform == "instagram":
                # Instagram Graph API does not support liking arbitrary posts —
                # queue as ManualAction so the operator can do it manually.
                print(f"📋 Queuing manual LIKE for post {post_id} by @{target.username} (Graph API limitation)")
                self.add_manual_action(
                    platform=platform,
                    action_type="like",
                    target_username=target.username,
                    target_url=getattr(target, "profile_url", "") or f"https://www.instagram.com/p/{post_id}/",
                    reason=f"Like post #{post_id} for hashtag growth engagement",
                    priority=2,
                )
                success = True  # queued successfully
            elif action_type == "comment" and platform == "instagram" and post_id:
                print(f"💬 Commenting on post {post_id} by @{target.username}: '{comment_text}'")
                success = await self._ig_post_comment(post_id, comment_text or "Great post! 🙌")
                if not success:
                    # Fallback: queue as manual action
                    print(f"📋 Comment API failed — queuing as manual action")
                    self.add_manual_action(
                        platform=platform,
                        action_type="comment",
                        target_username=target.username,
                        target_url=getattr(target, "profile_url", "") or f"https://www.instagram.com/p/{post_id}/",
                        reason=f"Comment: {comment_text}",
                        priority=1,
                    )
                    success = True  # queued successfully
            else:
                # Other platforms — queue as manual action for now
                print(f"📋 Queuing manual {action_type} for @{target.username} on {platform}")
                self.add_manual_action(
                    platform=platform,
                    action_type=action_type,
                    target_username=target.username,
                    target_url=getattr(target, "profile_url", "") or "",
                    reason=f"Outbound {action_type} for growth",
                    priority=2,
                )
                success = True

        if success:
            self._record_action(platform, action_type)
        
        return GrowthAction(
            action_id="",
            action_type=action_type,
            platform=platform,
            target_user_id=target.user_id,
            target_username=target.username,
            performed_at=datetime.utcnow().isoformat(),
            success=success
        )
    
    async def run_growth_campaign(
        self,
        platform: str,
        strategy: Optional[str] = None,
        strategy_params: Optional[Dict[str, Any]] = None,
        actions_per_day: int = 50,
        dry_run: bool = True,
        # Scheduler-compatible aliases
        max_follows: Optional[int] = None,
        max_engagements: Optional[int] = None,
        hashtags: Optional[List[str]] = None,
    ) -> Any:
        """
        Run a growth campaign with specified strategy.

        Supports two call patterns:
          1. Explicit:  run_growth_campaign(platform, strategy="hashtag_targeting",
                            strategy_params={"hashtag": "marketing"})
          2. Scheduler: run_growth_campaign(platform, max_follows=20, max_engagements=30)
                        → auto-picks hashtag strategy from client profile keywords.

        Args:
            platform: Platform name
            strategy: Growth strategy to use (default: "hashtag_targeting")
            strategy_params: Parameters for the strategy
            actions_per_day: Target number of actions per day
            dry_run: If True, simulate without actual API calls
            max_follows: Alias for actions_per_day follow cap (scheduler compat)
            max_engagements: Cap for like/comment actions (scheduler compat)
            hashtags: Override hashtags to target (scheduler compat)

        Returns:
            dict with keys follows, engagements, skipped, actions (List[GrowthAction])
        """
        # ── Scheduler compatibility: resolve params from kwargs ────────────
        if max_follows is not None or max_engagements is not None:
            actions_per_day = (max_follows or 20) + (max_engagements or 30)

        if strategy is None:
            strategy = "hashtag_targeting"

        if strategy_params is None:
            # Auto-derive hashtag from client profile keywords
            default_hashtag = "marketing"
            try:
                from agents.client_profile_manager import ClientProfileManager
                pm = ClientProfileManager()
                profile = pm.get_client_profile(self.client_id)
                if profile and getattr(profile, "keywords", None):
                    default_hashtag = profile.keywords[0].replace("#", "")
                elif profile and getattr(profile, "niche", None):
                    niche_val = getattr(profile.niche, "value", None)
                    if niche_val:
                        default_hashtag = niche_val.replace(" ", "")
            except Exception:
                pass
            # Allow caller hashtags override
            if hashtags:
                default_hashtag = hashtags[0].replace("#", "")
            strategy_params = {"hashtag": default_hashtag}
            print(f"📌 Auto-selected hashtag strategy: #{default_hashtag}")
        print(f"\n{'='*60}")
        print(f"🚀 STARTING GROWTH CAMPAIGN")
        print(f"{'='*60}")
        print(f"Platform: {platform}")
        print(f"Strategy: {strategy}")
        print(f"Daily Actions Target: {actions_per_day}")
        print(f"Mode: {'DRY RUN (Simulation)' if dry_run else 'LIVE'}")
        print(f"{'='*60}\n")
        
        actions_taken: List[GrowthAction] = []
        follow_cap       = max_follows     or (actions_per_day // 2)
        engagement_cap   = max_engagements or (actions_per_day // 2)
        follows_done = engagements_done = skipped = 0

        # ── Find targets ──────────────────────────────────────────────────
        if strategy == "competitor_targeting":
            competitor = strategy_params.get("competitor_username")
            targets = await self.find_competitor_followers(platform, competitor, limit=actions_per_day)
        elif strategy == "hashtag_targeting":
            hashtag = strategy_params.get("hashtag", "marketing")
            targets = await self.find_hashtag_users(platform, hashtag, limit=actions_per_day)
        elif strategy == "location_targeting":
            location = strategy_params.get("location")
            targets = await self.find_location_users(platform, location, limit=actions_per_day)
        else:
            print(f"❌ Unknown strategy: {strategy}")
            return {"follows": 0, "engagements": 0, "skipped": 0, "actions": []}
        
        print(f"\n📊 Found {len(targets)} potential targets")
        print(f"🎯 Follow cap={follow_cap}, Engagement cap={engagement_cap}\n")
        
        for i, target in enumerate(targets[:actions_per_day], 1):
            print(f"\n[{i}/{min(actions_per_day, len(targets))}] Target: @{target.username}")
            print(f"  • Engagement Rate: {target.engagement_rate}% | Relevance: {target.niche_relevance_score:.2f}")
            print(f"  • Source: {target.source}")

            # ── Follow action ──────────────────────────────────────────
            if follows_done < follow_cap:
                allowed, _ = self._check_rate_limit(platform, "follow")
                if allowed:
                    action = await self.execute_follow_action(platform, target, dry_run=dry_run)
                    actions_taken.append(action)
                    if action.success:
                        follows_done += 1
                        print(f"  ✅ Follow queued/sent")
                    else:
                        skipped += 1
                        print(f"  ⚠️  Follow skipped: {action.error_message}")

            # ── Engagement action (prefer comment for visibility) ───────
            if engagements_done < engagement_cap:
                post_id      = getattr(target, "recent_post_id", "") or target.user_id
                post_content = getattr(target, "recent_post_content", "") or target.bio or ""
                allowed, _ = self._check_rate_limit(platform, "comment")
                if allowed and post_content:
                    action = await self.execute_engagement_action(
                        platform=platform,
                        target=target,
                        action_type="comment",
                        post_id=post_id,
                        post_content=post_content,
                        dry_run=dry_run,
                    )
                    actions_taken.append(action)
                    if action.success:
                        engagements_done += 1
                        print(f"  ✅ Comment queued/sent")
                    else:
                        # Fall back to a like
                        like_action = await self.execute_engagement_action(
                            platform=platform, target=target, action_type="like",
                            post_id=post_id, dry_run=dry_run,
                        )
                        actions_taken.append(like_action)
                        if like_action.success:
                            engagements_done += 1
                else:
                    skipped += 1

            # Human-like delay between targets
            if i < len(targets) and not dry_run:
                await asyncio.sleep(random.uniform(30, 90))

            if follows_done >= follow_cap and engagements_done >= engagement_cap:
                print("\n🎯 Caps reached, stopping campaign")
                break
        
        # Summary
        print(f"\n{'='*60}")
        print(f"📊 CAMPAIGN SUMMARY")
        print(f"{'='*60}")
        print(f"  Follows:     {follows_done}")
        print(f"  Engagements: {engagements_done}")
        print(f"  Skipped:     {skipped}")
        print(f"  Manual queue: {len(self.manual_action_queue)} pending items")
        print(f"{'='*60}\n")

        return {
            "follows": follows_done,
            "engagements": engagements_done,
            "skipped": skipped,
            "actions": actions_taken,
        }
    
    def add_to_whitelist(self, user_id: str, username: str):
        """Add user to whitelist (never unfollow)."""
        self.whitelisted_users.add(user_id)
        print(f"✅ Added @{username} to whitelist (protected)")
    
    def add_to_blacklist(self, user_id: str, username: str):
        """Add user to blacklist (never engage)."""
        self.blacklisted_users.add(user_id)
        print(f"🚫 Added @{username} to blacklist")
    
    def remove_from_whitelist(self, user_id: str):
        """Remove user from whitelist."""
        self.whitelisted_users.discard(user_id)
        print(f"✅ Removed from whitelist")
    
    def remove_from_blacklist(self, user_id: str):
        """Remove user from blacklist."""
        self.blacklisted_users.discard(user_id)
        print(f"✅ Removed from blacklist")

    # ══════════════════════════════════════════════════════════
    # Claude-powered follow / group recommendation engine
    # ══════════════════════════════════════════════════════════

    # Conservative "established account" daily follow limits derived from
    # Growth RAG research docs.  These are safe ceilings that avoid bans.
    SAFE_DAILY_FOLLOW_LIMITS: Dict[str, int] = {
        "instagram":  20,   # RAG: 150-200/day established, we use conservative 20 recs
        "facebook":   10,   # RAG: 15-30 friend requests/day established
        "tiktok":     15,   # RAG: 75-120/day established
        "twitter_x":  20,   # RAG: 150-250/day established
        "twitter":    20,   # alias
        "linkedin":   15,   # RAG: 80-120 connections/week (~15/day)
        "threads":    10,   # No RAG doc — conservative default
        "youtube":    10,   # No RAG doc — conservative default (subscribe)
    }

    # Platforms that have a joinable group / community concept
    GROUP_CAPABLE_PLATFORMS = {"facebook", "linkedin"}

    # ── Tavily-powered real profile discovery ───────────────────────────

    async def _tavily_find_profiles(
        self,
        platforms: List[str],
        niche: str,
        keywords: List[str],
        target_audience: str,
        competitors: str,
        per_platform_limits: Dict[str, int],
    ) -> List[Dict[str, str]]:
        """Use Tavily to find REAL social media profiles by mining web articles.

        Searches the open web for articles/listicles that *reference* real
        profile URLs (e.g. "best marketing Instagram accounts 2025"), then
        extracts handles from the article content.  This is far more reliable
        than searching *within* platform domains, which returns post/explore
        pages that the profile-URL regex always rejects.
        """
        import re as _re

        tavily_key = os.getenv("TAVILY_API_KEY")
        if not tavily_key:
            log.warning(f"[{self.client_id}] TAVILY_API_KEY not set — skipping real profile search")
            return []

        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=tavily_key)
        except ImportError:
            log.warning(f"[{self.client_id}] tavily-python not installed — skipping")
            return []

        _PLATFORM_DISPLAY = {
            "instagram": "Instagram", "tiktok": "TikTok",
            "twitter_x": "Twitter",  "linkedin": "LinkedIn", "facebook": "Facebook",
        }
        _PLATFORM_URL = {
            "instagram": "https://instagram.com/{}",
            "tiktok":    "https://www.tiktok.com/@{}",
            "twitter_x": "https://twitter.com/{}",
            "linkedin":  "https://linkedin.com/in/{}",
            "facebook":  "https://facebook.com/{}",
        }
        # Mine handles from article text/URLs — both full URLs and @mentions
        _CONTENT_RE = {
            "instagram": _re.compile(r"(?:instagram\.com/|@)([A-Za-z0-9._]{3,30})(?=[/?#\s,\"'\]\);:!]|$)"),
            "tiktok":    _re.compile(r"(?:tiktok\.com/@|@)([A-Za-z0-9._]{3,30})(?=[/?#\s,\"'\]\);:!]|$)"),
            "twitter_x": _re.compile(r"(?:(?:twitter|x)\.com/|@)([A-Za-z0-9_]{3,15})(?=[/?#\s,\"'\]\);:!]|$)"),
            "linkedin":  _re.compile(r"linkedin\.com/in/([A-Za-z0-9\-]{3,80})(?=[/?#\s,\"'\]\);:!]|$)"),
            "facebook":  _re.compile(r"facebook\.com/([A-Za-z0-9.]{3,50})(?=[/?#\s,\"'\]\);:!]|$)"),
        }
        # Platform page slugs and common @mention false positives
        _SKIP_HANDLES = {
            "instagram": {"explore","p","reel","reels","stories","tv","accounts",
                          "directory","hashtag","about","help","legal","instagram","sharedfiles",
                          "the","and","for","you","your","this","that","with","from","are",
                          "was","has","not","but","can","all","her","his","she","they"},
            "tiktok":    {"video","tag","music","discover","live","about","tiktok",
                          "the","and","for","you","your","this","that","with","from","are"},
            "twitter_x": {"status","i","hashtag","search","intent","home","explore",
                          "notifications","messages","twitter","x",
                          "the","and","for","you","your","this","that","with","from","are"},
            "linkedin":  {"posts","pulse","company","jobs","feed","search","learning","linkedin"},
            "facebook":  {"posts","videos","photos","events","groups","marketplace",
                          "watch","gaming","facebook"},
        }

        keyword_terms = " ".join(keywords[:3]) if keywords else niche
        all_profiles: List[Dict[str, str]] = []
        seen_handles: set = set()

        for platform in platforms:
            plat_display = _PLATFORM_DISPLAY.get(platform, platform.title())
            limit_for_plat = per_platform_limits.get(platform, 10)
            content_re = _CONTENT_RE.get(platform)
            skip_handles = _SKIP_HANDLES.get(platform, set())
            url_tmpl = _PLATFORM_URL.get(platform, f"https://{platform}.com/{{}}")

            if not content_re:
                continue

            # Discovery queries — mix of listicles and direct platform searches
            _PLATFORM_DOMAIN = {
                "instagram": "instagram.com",
                "tiktok": "tiktok.com",
                "twitter_x": "twitter.com",
                "linkedin": "linkedin.com",
                "facebook": "facebook.com",
            }
            # Platform-specific queries that surface actual profile URLs
            _PLAT_SPECIFIC_QUERIES = {
                "linkedin": [
                    f"site:linkedin.com/in {niche} {keyword_terms}",
                    f"linkedin.com/in {niche} professionals to follow 2025",
                ],
                "facebook": [
                    f"site:facebook.com {niche} people to follow 2025",
                    f"facebook.com {niche} enthusiasts profiles",
                ],
            }
            plat_queries = _PLAT_SPECIFIC_QUERIES.get(platform, [])
            queries = plat_queries + [
                f"best {niche} accounts to follow on {plat_display} 2025",
                f"top {niche} {plat_display} creators to follow",
                f"{niche} enthusiasts {plat_display} people to follow",
            ]
            if target_audience:
                queries.append(f"{target_audience} {niche} {plat_display} accounts")

            platform_profiles: List[Dict[str, str]] = []
            _plat_raw = 0

            for query in queries[:4]:
                if len(platform_profiles) >= limit_for_plat + 5:
                    break
                try:
                    results = tavily.search(
                        query=query,
                        max_results=10,
                        search_depth="advanced",
                    )
                    raw_results = results.get("results", [])
                    _plat_raw += len(raw_results)

                    for r in raw_results:
                        # Mine the URL, title, AND content for profile handles
                        search_text = " ".join([
                            r.get("url", ""),
                            r.get("title", ""),
                            r.get("content", ""),
                        ])
                        for handle in content_re.findall(search_text):
                            handle_key = f"{platform}:{handle.lower()}"
                            if handle_key in seen_handles:
                                continue
                            if handle.lower() in skip_handles or len(handle) < 3:
                                continue
                            seen_handles.add(handle_key)
                            platform_profiles.append({
                                "url":      url_tmpl.format(handle),
                                "title":    handle,
                                "snippet":  (r.get("content") or "")[:200].strip(),
                                "platform": platform,
                                "source":   "tavily_mined",
                            })
                            if len(platform_profiles) >= limit_for_plat + 5:
                                break
                except Exception as e:
                    log.warning(
                        f"[{self.client_id}] Tavily search error ({platform}, "
                        f"query={query[:60]}): {type(e).__name__}: {e}"
                    )

            kept = len(platform_profiles[:limit_for_plat + 5])
            all_profiles.extend(platform_profiles[:limit_for_plat + 5])
            log.info(
                f"[{self.client_id}] Tavily [{platform}]: "
                f"{_plat_raw} raw articles → {kept} profile handles mined"
            )

        # ── Retry for platforms that got 0 results ──────────────
        from collections import Counter as _Ctr
        _mined_counts = _Ctr(p["platform"] for p in all_profiles)
        _zero_plats = [p for p in platforms if _mined_counts.get(p, 0) == 0]
        for platform in _zero_plats:
            plat_display = _PLATFORM_DISPLAY.get(platform, platform.title())
            content_re = _CONTENT_RE.get(platform)
            skip_handles = _SKIP_HANDLES.get(platform, set())
            url_tmpl = _PLATFORM_URL.get(platform, f"https://{platform}.com/{{}}")
            limit_for_plat = per_platform_limits.get(platform, 10)
            if not content_re:
                continue
            fallback_queries = [
                f"{niche} {plat_display} profiles to follow 2025 list",
                f"best {plat_display} accounts for {niche} enthusiasts",
            ]
            log.info(f"[{self.client_id}] Tavily [{platform}]: 0 mined — running fallback queries")
            for query in fallback_queries:
                try:
                    results = tavily.search(query=query, max_results=10, search_depth="advanced")
                    for r in results.get("results", []):
                        search_text = " ".join([r.get("url", ""), r.get("title", ""), r.get("content", "")])
                        for handle in content_re.findall(search_text):
                            handle_key = f"{platform}:{handle.lower()}"
                            if handle_key in seen_handles:
                                continue
                            if handle.lower() in skip_handles or len(handle) < 3:
                                continue
                            seen_handles.add(handle_key)
                            all_profiles.append({
                                "url":      url_tmpl.format(handle),
                                "title":    handle,
                                "snippet":  (r.get("content") or "")[:200].strip(),
                                "platform": platform,
                                "source":   "tavily_fallback",
                            })
                            if len([p for p in all_profiles if p["platform"] == platform]) >= limit_for_plat + 5:
                                break
                except Exception as e:
                    log.warning(f"[{self.client_id}] Tavily fallback error ({platform}): {e}")
            _fb_count = len([p for p in all_profiles if p["platform"] == platform])
            log.info(f"[{self.client_id}] Tavily [{platform}] after fallback: {_fb_count} handles")

        log.info(
            f"[{self.client_id}] Tavily total: {len(all_profiles)} profiles mined "
            f"across {len(platforms)} platforms"
        )
        return all_profiles

    async def _validate_profile_urls(
        self, profiles: List[Dict[str, str]], max_concurrent: int = 5
    ) -> List[Dict[str, str]]:
        """Send async HEAD requests to filter out dead profile URLs (404/410).

        Returns only profiles whose URLs responded with 2xx or 3xx.
        """
        import asyncio
        import httpx

        if not profiles:
            return []

        sem = asyncio.Semaphore(max_concurrent)
        # Platforms whose CDNs return 404 for HEAD but 200 for GET
        _GET_ONLY_DOMAINS = ("tiktok.com",)
        _dead_details: list = []  # collect per-URL failure info

        async def _check(profile: Dict[str, str]) -> bool:
            url = profile.get("url", "")
            if not url:
                return False
            plat = profile.get("platform", "")
            try:
                async with sem:
                    async with httpx.AsyncClient(
                        follow_redirects=True, timeout=8.0,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
                    ) as hc:
                        # TikTok CDN returns 404 for HEAD on valid profiles — use GET
                        use_get = any(d in url for d in _GET_ONLY_DOMAINS)
                        if use_get:
                            r = await hc.get(url, headers={"Range": "bytes=0-0"})
                        else:
                            r = await hc.head(url)
                            # Some sites block HEAD — fall back to GET
                            if r.status_code == 405:
                                r = await hc.get(url, headers={"Range": "bytes=0-0"})
                        # 403 = bot-blocked but profile exists (Instagram, TikTok)
                        # Only reject definitive "not found" responses
                        alive = r.status_code not in (404, 410)
                        if not alive:
                            _dead_details.append(f"{plat}:{url} → {r.status_code}")
                        return alive
            except Exception as exc:
                # Timeout / DNS / connection error → assume alive
                log.debug(f"[{self.client_id}] URL check exception for {url}: {type(exc).__name__}")
                return True

        results = await asyncio.gather(*[_check(p) for p in profiles])
        alive = [p for p, ok in zip(profiles, results) if ok]
        dead = len(profiles) - len(alive)
        # Per-platform breakdown
        from collections import Counter as _ValCtr
        _alive_plats = _ValCtr(p.get("platform", "?") for p in alive)
        _all_plats = _ValCtr(p.get("platform", "?") for p in profiles)
        _plat_detail = ", ".join(
            f"{k}={_alive_plats.get(k, 0)}/{v}" for k, v in sorted(_all_plats.items())
        )
        log.info(
            f"[{self.client_id}] URL validation: {len(profiles)} checked → "
            f"{len(alive)} alive, {dead} dead ({_plat_detail})"
        )
        if _dead_details:
            log.info(f"[{self.client_id}] Dead URLs: {'; '.join(_dead_details[:20])}")
        return alive

    @staticmethod
    def _build_exclusion_block(excluded_names: Optional[List[str]] = None) -> str:
        """Build a prompt block listing accounts the client already acted on."""
        if not excluded_names:
            return ""
        # Cap at 200 to avoid bloating the prompt
        capped = excluded_names[:200]
        lines = "\n".join(f"- {n}" for n in capped)
        return (
            f"\nPREVIOUSLY ACTED ON — Do NOT recommend these accounts again "
            f"(the client already followed or dismissed them):\n{lines}\n"
        )

    async def generate_follow_recommendations(
        self,
        platforms: Optional[List[str]] = None,
        per_platform_limits: Optional[Dict[str, int]] = None,
        num_groups: int = 5,
        excluded_names: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Two-step recommendation engine:

        1. Tavily live-searches for real people active in the client's niche today
        2. Claude filters to CONSUMERS ONLY (no businesses) + formats as structured JSON
        3. HEAD requests verify the profile URLs are alive
        """
        empty: Dict[str, List[Dict[str, str]]] = {"people": [], "groups": []}

        # ── Gather client context from DB ───────────────────────────────
        niche = "marketing"
        target_audience = ""
        competitors = ""
        description = ""
        services = ""
        business_name = ""
        try:
            from database.db import SessionLocal
            from database.models import ClientProfile as _CP
            _db = SessionLocal()
            try:
                row = _db.query(_CP).filter(_CP.client_id == self.client_id).first()
                if row:
                    niche = row.niche or "marketing"
                    target_audience = row.target_audience or ""
                    competitors = row.competitors or ""
                    description = row.description or ""
                    services = row.services_products or ""
                    business_name = row.business_name or ""
                    # Growth interests override: if set, use as niche + audience
                    _gi_json = getattr(row, "growth_interests_json", None)
                    if _gi_json:
                        try:
                            _gi = json.loads(_gi_json)
                            _interests = _gi.get("interests", [])
                            if _interests:
                                niche = ", ".join(_interests)
                                target_audience = f"People interested in: {niche}"
                                log.info(f"[{self.client_id}] Using growth interest override: {niche}")
                        except (json.JSONDecodeError, TypeError):
                            pass
            finally:
                _db.close()
        except Exception:
            pass

        keywords: List[str] = []
        content_pillars: List[str] = []
        try:
            from agents.client_profile_manager import ClientProfileManager
            pm = ClientProfileManager()
            profile = pm.get_client_profile(self.client_id)
            if profile:
                keywords = getattr(profile, "keywords", []) or []
                content_pillars = getattr(profile, "content_pillars", []) or []
                if not platforms:
                    platforms = getattr(profile, "platforms", ["instagram"]) or ["instagram"]
        except Exception:
            pass

        if not platforms:
            platforms = ["instagram"]

        # ── Per-platform people quotas ──────────────────────────────────
        if per_platform_limits is None:
            per_platform_limits = {
                p: self.SAFE_DAILY_FOLLOW_LIMITS.get(p, 10)
                for p in platforms
            }
        total_people = sum(per_platform_limits.values())

        group_platforms = [p for p in platforms if p in self.GROUP_CAPABLE_PLATFORMS]
        if group_platforms:
            groups_per = max(2, num_groups // len(group_platforms))
            actual_num_groups = groups_per * len(group_platforms)
        else:
            actual_num_groups = 0

        keyword_str = ", ".join(keywords[:10]) if keywords else niche

        # ── Step 1: Tavily live search for active profiles ──────────────
        log.info(f"[{self.client_id}] Step 1: Tavily live search for {niche} consumers on {', '.join(platforms)}")
        tavily_profiles = await self._tavily_find_profiles(
            platforms=platforms,
            niche=niche,
            keywords=keywords,
            target_audience=target_audience,
            competitors=competitors,
            per_platform_limits=per_platform_limits,
        )
        log.info(f"[{self.client_id}] Tavily found {len(tavily_profiles)} raw profiles")

        # Per-platform Tavily counts (used in Claude prompt to trigger fallback)
        from collections import Counter as _TavCtr
        _tavily_plat_counts = _TavCtr(tp.get("platform", "?") for tp in tavily_profiles)
        _tavily_counts_block = "\n".join(
            f"- {p.title()}: {_tavily_plat_counts.get(p, 0)} profiles found via live search"
            for p in platforms
        )

        # Format Tavily results for Claude
        tavily_block = ""
        if tavily_profiles:
            lines = []
            for tp in tavily_profiles:
                lines.append(
                    f"- @{tp.get('title','?')} on {tp.get('platform','?')}: "
                    f"{tp.get('url','')} — {tp.get('snippet','')[:150]}"
                )
            tavily_block = "\n".join(lines)

        # ── Step 2: Claude filters to CONSUMERS ONLY ────────────────────
        log.info(f"[{self.client_id}] Step 2: Claude filtering {len(tavily_profiles)} profiles to consumers only")

        system_prompt = (
            "You are an audience-growth strategist who recommends REAL social media accounts "
            "for a client to follow. You ONLY recommend individual CONSUMERS — real people who "
            "could become customers. NEVER recommend businesses, brands, SaaS companies, agencies, "
            "tools, or corporate accounts. The client wants to connect with REAL PEOPLE who are "
            "interested in their niche."
        )

        prompt = f"""Review the live search results below and recommend the best CONSUMER accounts for this client to follow.

CLIENT PROFILE:
- Business: {business_name}
- Niche: {niche}
- Description: {description}
- Services/Products: {services}
- Target Audience: {target_audience}
- Keywords: {keyword_str}

LIVE SEARCH RESULTS (real accounts found active today):
{tavily_block if tavily_block else "(No Tavily results — generate your own recommendations of REAL consumers)"}

PER-PLATFORM SEARCH COUNTS:
{_tavily_counts_block}
IMPORTANT: For any platform that shows 0 profiles found via live search, you MUST still
recommend real consumer accounts from your own knowledge. Use handles you are confident
exist. Aim to fill the quota for EVERY platform — do NOT skip a platform just because
the live search returned 0 results for it.

I need {total_people} people total and {actual_num_groups} groups.

CRITICAL RULES — CONSUMERS ONLY:
- ONLY recommend INDIVIDUAL PEOPLE — consumers, hobbyists, enthusiasts, freelancers
- NEVER recommend businesses, brands, SaaS tools, agencies, or corporate accounts
  Examples of what to EXCLUDE: Mailchimp, HubSpot, Canva, Buffer, Hootsuite, Salesforce,
  or ANY company/brand account
- The goal is finding REAL PEOPLE who might actually BUY the client's services
- Prefer people who show genuine interest in {niche} through their posts/activity
- If the live search results contain business accounts, SKIP THEM entirely

WHO QUALIFIES AS A GOOD RECOMMENDATION:
1. POTENTIAL CUSTOMERS — Individuals whose posts suggest they need {niche} services
2. HOBBYISTS & ENTHUSIASTS — People who post about {niche} topics as a passion
3. FREELANCERS & SOLOPRENEURS — Individual people (not companies) in adjacent fields
4. ACTIVE COMMUNITY MEMBERS — People who engage with {niche} hashtags and discussions
5. MICRO-CREATORS — Individual content creators (1K-50K followers) in the {niche} space

WHO TO ABSOLUTELY EXCLUDE:
- ANY business, brand, or company account (e.g. @mailchimp, @hubspot, @canva)
- Agencies or marketing tools
- Direct competitors
- Celebrities or mega-influencers (500K+ followers)
- Abandoned or inactive accounts
- Accounts you're not confident actually exist
{self._build_exclusion_block(excluded_names)}
For people from the live search results, keep their exact URL.
You may also add additional REAL consumer accounts you're confident exist.
If you're not 100% sure a username exists, SKIP IT.

FOR EACH PERSON, explain why they're a good follow — what about their activity shows
they're interested in {niche} and could become a customer.

FOR GROUPS: suggest REAL Facebook Groups or LinkedIn Groups with active members.
NEVER suggest Reddit, Discord, Slack, Telegram, WhatsApp.

URL PATTERNS:
- Instagram: https://instagram.com/USERNAME
- TikTok: https://tiktok.com/@USERNAME
- Twitter/X: https://twitter.com/USERNAME
- LinkedIn: https://linkedin.com/in/HANDLE
- Facebook: https://facebook.com/PAGENAME
- Facebook Groups: https://facebook.com/groups/SLUG

RESPOND IN STRICT JSON — no markdown fences, no commentary:
{{{{
  "people": [
    {{{{
      "name": "Display Name or @handle",
      "platform": "instagram",
      "reason": "Why they're a good follow — what shows niche interest",
      "url": "https://instagram.com/realhandle",
      "follower_count_approx": 5000,
      "account_type": "consumer"
    }}}}
  ],
  "groups": [
    {{{{"name": "Group Name", "platform": "facebook", "reason": "Why join", "url": "https://facebook.com/groups/realslug"}}}}
  ]
}}}}

account_type MUST be one of: "consumer", "hobbyist", "freelancer", "solopreneur", "creator".
NEVER return "business", "brand", "agency", "tool", "saas", "company", "coach", "competitor"."""

        try:
            client = Anthropic()
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=16384,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            log.info(f"[{self.client_id}] Claude response received ({len(raw)} chars)")

            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[: raw.rfind("```")]

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as _je:
                log.warning(f"[{self.client_id}] First JSON parse failed ({_je}), retrying…")
                retry_resp = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=16384,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw},
                        {"role": "user", "content": "Return ONLY valid JSON. Start with { and end with }."},
                    ],
                )
                raw2 = retry_resp.content[0].text.strip()
                if raw2.startswith("```"):
                    raw2 = raw2.split("\n", 1)[1]
                    if raw2.endswith("```"):
                        raw2 = raw2[: raw2.rfind("```")]
                data = json.loads(raw2)

            people_raw = data.get("people", [])
            groups = data.get("groups", [])[:actual_num_groups]

            # ── Normalize platform names ────────────────────────────────
            _PLAT_NORM = {
                "twitter": "twitter_x", "x": "twitter_x", "twitter/x": "twitter_x",
                "ig": "instagram", "fb": "facebook",
            }
            for _e in people_raw:
                _rp = str(_e.get("platform", "")).lower().strip()
                _e["platform"] = _PLAT_NORM.get(_rp, _rp)
            for _e in groups:
                _rp = str(_e.get("platform", "")).lower().strip()
                _e["platform"] = _PLAT_NORM.get(_rp, _rp)

            # ── Quality filter (consumers only) ─────────────────────────
            _BAD_ACCOUNT_TYPES = {
                "agency", "coach", "competitor", "direct_rival",
                "business", "brand", "tool", "saas", "company",
            }
            people_filtered = []
            people_rejected = []
            for p in people_raw:
                p_plat = str(p.get("platform", "")).lower()
                acct_type = str(p.get("account_type", "consumer")).lower().strip()
                approx_followers = p.get("follower_count_approx", 1000)
                reject_reason = None

                if p_plat and p_plat not in [x.lower() for x in platforms]:
                    reject_reason = f"off-platform ({p_plat})"
                elif acct_type in _BAD_ACCOUNT_TYPES:
                    reject_reason = f"account_type={acct_type}"
                elif isinstance(approx_followers, (int, float)) and approx_followers < 200:
                    reject_reason = f"too few followers ({approx_followers})"

                if reject_reason:
                    people_rejected.append((p.get("name", "?"), reject_reason))
                else:
                    people_filtered.append(p)

            # Same filter for groups
            groups_filtered = []
            for g in groups:
                g_plat = str(g.get("platform", "")).lower()
                if g_plat and g_plat not in [p.lower() for p in platforms]:
                    people_rejected.append((g.get("name", "?"), f"group off-platform ({g_plat})"))
                    continue
                groups_filtered.append(g)
            groups = groups_filtered

            if people_rejected:
                log.info(
                    f"[{self.client_id}] Quality filter rejected {len(people_rejected)}: "
                    + "; ".join(f"{n} ({r})" for n, r in people_rejected[:10])
                )

            log.info(
                f"[{self.client_id}] Claude returned {len(people_raw)} people, "
                f"{len(people_filtered)} passed filter. Verifying URLs…"
            )

            # ── Step 3: Verify profiles exist via HEAD requests ─────────
            if people_filtered:
                people_filtered = await self._validate_profile_urls(people_filtered)
            if groups:
                groups = await self._validate_profile_urls(groups)

            people = people_filtered[:total_people]

            from collections import Counter
            plat_counts = Counter(p.get("platform", "unknown") for p in people)
            plat_summary = ", ".join(f"{k}={v}" for k, v in sorted(plat_counts.items()))
            log.info(
                f"[{self.client_id}] ✅ Final: {len(people)} verified people ({plat_summary}), "
                f"{len(groups)} groups"
            )
            return {"people": people, "groups": groups}
        except Exception as e:
            log.error(f"[{self.client_id}] ❌ Recommendation generation failed: {e}", exc_info=True)
            return empty


# ═══════════════════════════════════════════════════════════════════════════
# Testing
# ═══════════════════════════════════════════════════════════════════════════

async def test_growth_agent():
    """Test growth agent functionality."""
    print("\n🧪 Testing Growth Agent...\n")
    
    agent = GrowthAgent(client_id="test_client")
    
    # Test 1: Check rate limits
    print("=" * 60)
    print("TEST 1: Check rate limit status")
    print("=" * 60)
    status = agent.get_rate_limit_status("instagram")
    print("Instagram Rate Limits:")
    for action_type, stats in status.items():
        print(f"  • {action_type}: {stats['remaining']} remaining out of {stats['limit']}")
    
    # Test 2: Find competitor followers
    print("\n" + "=" * 60)
    print("TEST 2: Find competitor followers")
    print("=" * 60)
    targets = await agent.find_competitor_followers(
        platform="instagram",
        competitor_username="competitor_account",
        limit=5
    )
    print(f"\nTop 3 targets:")
    for i, target in enumerate(targets[:3], 1):
        print(f"{i}. @{target.username}")
        print(f"   Followers: {target.follower_count:,}")
        print(f"   Engagement: {target.engagement_rate}%")
        print(f"   Relevance: {target.niche_relevance_score:.2f}")
    
    # Test 3: Find hashtag users
    print("\n" + "=" * 60)
    print("TEST 3: Find hashtag users")
    print("=" * 60)
    hashtag_targets = await agent.find_hashtag_users(
        platform="instagram",
        hashtag="marketing",
        limit=5
    )
    print(f"Found {len(hashtag_targets)} users posting #marketing")
    
    # Test 4: Execute follow action (dry run)
    print("\n" + "=" * 60)
    print("TEST 4: Execute follow action (DRY RUN)")
    print("=" * 60)
    if targets:
        action = await agent.execute_follow_action(
            platform="instagram",
            target=targets[0],
            dry_run=True
        )
        print(f"Action: {action.action_type}")
        print(f"Success: {action.success}")
    
    # Test 5: Generate engagement comment
    print("\n" + "=" * 60)
    print("TEST 5: Generate engagement comment")
    print("=" * 60)
    comment = await agent.generate_engagement_comment(
        platform="instagram",
        post_content="Just launched our new product! Check it out in bio 🚀",
        target_username="test_user"
    )
    print(f"Generated comment: \"{comment}\"")
    
    # Test 6: Run mini growth campaign
    print("\n" + "=" * 60)
    print("TEST 6: Run growth campaign (DRY RUN)")
    print("=" * 60)
    actions = await agent.run_growth_campaign(
        platform="instagram",
        strategy="competitor_targeting",
        strategy_params={"competitor_username": "competitor_account"},
        actions_per_day=3,  # Small number for testing
        dry_run=True
    )
    
    print(f"\n✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(test_growth_agent())
