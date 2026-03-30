"""
Email Marketing Agent - AI-powered bulk email campaign automation

This agent handles:
- Campaign strategy and planning (timing, frequency, audience)
- Email content generation (subject lines, body copy, CTAs)
- Audience segmentation and targeting
- Deliverability management (warmup, reputation, spam avoidance)
- Technical compliance (SPF/DKIM/DMARC, one-click unsubscribe)
- Performance optimization (A/B testing, send time optimization)

Key Features:
- Research-backed optimization from 22 Email Marketing RAG documents
- Campaign scoring and confidence evaluation
- Deliverability risk assessment
- Compliance validation
- Segmentation recommendations
- Subject line and content generation with best practices

Integration with EmailSupportAgent:
- EmailMarketingAgent: Outbound bulk campaigns (newsletters, promotions)
- EmailSupportAgent: Inbound customer support replies (1-to-1)
"""

import sys
# Windows UTF-8 fix: prevent cp1252 codec crash on emoji in print() calls
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import glob
from anthropic import Anthropic
from dotenv import load_dotenv

# Resend (email sending) - graceful fallback if not installed
# Free: 3,000 emails/month + 100/day | Paid: $20/mo for 50K
# Setup: https://resend.com/ -> get API key -> add RESEND_API_KEY to .env
try:
    import resend as resend_sdk
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False

# ===============================================
# PROMPT SYSTEM INTEGRATION
# ===============================================

# Load prompt system from Email Marketing RAG folder
try:
    import sys
    import importlib.util
    
    prompt_path = os.path.join("Agent RAGs", "Email Marketing RAG", "email_marketing_prompts.py")
    spec = importlib.util.spec_from_file_location("email_marketing_prompts", prompt_path)
    email_marketing_prompts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(email_marketing_prompts)
    
    get_prompt = email_marketing_prompts.get_prompt
    format_prompt = email_marketing_prompts.format_prompt
    
    print("✅ Email Marketing prompt system loaded")
except Exception as e:
    print(f"⚠️  Warning: Could not load Email Marketing prompt system: {str(e)}")
    print("    Continuing with fallback prompts")
    get_prompt = None
    format_prompt = None


# ===============================================
# EMAIL MARKETING RAG SYSTEM
# ===============================================

class EmailMarketingRAG:
    """
    RAG system for Email Marketing research documents.
    
    Loads 22 research documents across 5 categories:
    - performance_benchmarks_2025 (5 docs)
    - technical_compliance_limits (4 docs)
    - segmentation_logic (3 docs)
    - optimization_strategy (5 docs)
    - deliverability_and_warmup (5 docs)
    """
    
    def __init__(self, rag_folder: str = "Agent RAGs/Email Marketing RAG"):
        self.rag_folder = rag_folder
        self.documents = {
            "performance_benchmarks_2025": [],
            "technical_compliance_limits": [],
            "segmentation_logic": [],
            "optimization_strategy": [],
            "deliverability_and_warmup": []
        }
        self.load_all_documents()
    
    def load_all_documents(self):
        """Load all markdown files from Email Marketing RAG folders"""
        print("📧 Loading Email Marketing RAG documents...")
        
        for category in self.documents.keys():
            # Find all .md files in this category
            pattern = os.path.join(self.rag_folder, category, "**", "*.md")
            files = glob.glob(pattern, recursive=True)
            
            for filepath in files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        filename = os.path.basename(filepath)
                        self.documents[category].append({
                            "filename": filename,
                            "content": content,
                            "path": filepath
                        })
                except Exception as e:
                    print(f"⚠️  Error loading {filepath}: {str(e)}")
        
        # Print loading summary
        total_docs = sum(len(docs) for docs in self.documents.values())
        print(f"✅ Email Marketing RAG system loaded: {total_docs} documents across {len(self.documents)} categories")
        for category, docs in self.documents.items():
            if docs:
                print(f"   - {category}: {len(docs)} documents")
    
    def retrieve_relevant_context(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        top_k: int = 3
    ) -> str:
        """
        Retrieve most relevant research documents based on query.
        
        Args:
            query: Search query (e.g., "subject line length", "spam triggers")
            categories: Specific categories to search (None = all)
            top_k: Number of documents to return
        
        Returns:
            Concatenated text from top matching documents
        """
        if categories is None:
            categories = list(self.documents.keys())
        
        # Score documents by keyword matching
        scored_docs = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for category in categories:
            if category not in self.documents:
                continue
            
            for doc in self.documents[category]:
                score = 0
                content_lower = doc["content"].lower()
                filename_lower = doc["filename"].lower()
                
                # Filename match gets higher weight
                if any(word in filename_lower for word in query_words):
                    score += 3
                
                # Count keyword matches in content
                for word in query_words:
                    if len(word) > 3:  # Skip very short words
                        score += content_lower.count(word) * 0.1
                
                if score > 0:
                    scored_docs.append((score, doc))
        
        # Sort and return top-k
        scored_docs.sort(reverse=True, key=lambda x: x[0])
        top_docs = scored_docs[:top_k]
        
        if not top_docs:
            return "No relevant research documents found."
        
        result = []
        for score, doc in top_docs:
            result.append(f"=== {doc['filename']} ===\n{doc['content'][:3000]}")
        
        return "\n\n".join(result)


# ===============================================
# ENUMS
# ===============================================

class CampaignType(Enum):
    """Types of email campaigns"""
    NEWSLETTER = "newsletter"
    PROMOTIONAL = "promotional"
    TRANSACTIONAL = "transactional"
    EDUCATIONAL = "educational"
    RE_ENGAGEMENT = "re_engagement"
    WELCOME_SERIES = "welcome_series"
    DRIP_CAMPAIGN = "drip_campaign"
    SEASONAL = "seasonal"
    PRODUCT_ANNOUNCEMENT = "product_announcement"
    EVENT_INVITATION = "event_invitation"


class CampaignGoal(Enum):
    """Primary goal of campaign"""
    SALES = "sales"
    ENGAGEMENT = "engagement"
    EDUCATION = "education"
    RETENTION = "retention"
    ACQUISITION = "acquisition"
    BRAND_AWARENESS = "brand_awareness"
    FEEDBACK = "feedback"


class AudienceSegment(Enum):
    """Audience segmentation categories"""
    ALL_SUBSCRIBERS = "all_subscribers"
    HIGHLY_ENGAGED = "highly_engaged"  # Opened/clicked in last 30 days
    MODERATELY_ENGAGED = "moderately_engaged"  # 30-60 days
    LOW_ENGAGEMENT = "low_engagement"  # 60-90 days
    AT_RISK = "at_risk"  # 90-120 days no engagement
    DORMANT = "dormant"  # 120+ days no engagement
    NEW_SUBSCRIBERS = "new_subscribers"  # < 30 days on list
    CUSTOMERS = "customers"  # Made purchase
    PROSPECTS = "prospects"  # No purchase yet
    VIP = "vip"  # High-value customers


class SendTimeStrategy(Enum):
    """Send time optimization strategies"""
    IMMEDIATE = "immediate"
    OPTIMAL_TIME = "optimal_time"  # Research-backed best time
    RECIPIENT_TIMEZONE = "recipient_timezone"  # Localized send
    ENGAGEMENT_BASED = "engagement_based"  # When user typically engages
    CUSTOM = "custom"  # Specific date/time


class DeliverabilityRisk(Enum):
    """Risk levels for deliverability issues"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ===============================================
# DATA CLASSES
# ===============================================

@dataclass
class EmailCampaign:
    """Campaign configuration and metadata"""
    campaign_id: str
    client_id: str
    campaign_type: CampaignType
    campaign_goal: CampaignGoal
    subject_line: str
    preview_text: Optional[str]
    body_html: Optional[str]
    body_text: Optional[str]
    from_name: str
    from_email: str
    reply_to_email: str
    target_segment: AudienceSegment
    send_time_strategy: SendTimeStrategy
    scheduled_send_time: Optional[datetime]
    created_at: datetime
    status: str = "draft"  # draft, scheduled, sending, sent, cancelled
    estimated_recipients: int = 0
    
    # A/B testing
    enable_ab_testing: bool = False
    ab_test_variants: Optional[List[Dict[str, str]]] = None
    ab_test_split: float = 0.5  # 50/50 split
    
    # Tracking
    utm_campaign: Optional[str] = None
    utm_source: Optional[str] = "email"
    utm_medium: Optional[str] = "email"
    
    # Deliverability settings
    warm_ip: bool = False
    warmup_limit: Optional[int] = None
    
    # Metadata
    tags: List[str] = field(default_factory=list)


@dataclass
class CampaignRecommendation:
    """AI-generated campaign recommendations"""
    recommended_subject_lines: List[Dict[str, Any]]  # [{subject, score, reasoning}, ...]
    recommended_send_times: List[Dict[str, Any]]  # [{day, hour, reasoning}, ...]
    recommended_segments: List[Dict[str, Any]]  # [{segment, expected_performance}, ...]
    content_recommendations: Dict[str, str]  # {aspect: recommendation}
    deliverability_assessment: Dict[str, Any]
    compliance_check: Dict[str, bool]
    overall_confidence: float  # 0.0-1.0
    estimated_performance: Dict[str, float]  # {open_rate, ctr, etc.}
    warnings: List[str]
    rag_context_used: List[str]
    processing_time_ms: int


@dataclass
class CampaignPerformance:
    """Campaign performance metrics"""
    campaign_id: str
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    converted_count: int
    bounced_count: int  # Hard + soft
    hard_bounced_count: int
    soft_bounced_count: int
    unsubscribed_count: int
    spam_complaint_count: int
    
    # Calculated metrics
    @property
    def open_rate(self) -> float:
        return (self.opened_count / self.delivered_count * 100) if self.delivered_count > 0 else 0.0
    
    @property
    def click_rate(self) -> float:
        return (self.clicked_count / self.delivered_count * 100) if self.delivered_count > 0 else 0.0
    
    @property
    def click_to_open_rate(self) -> float:
        return (self.clicked_count / self.opened_count * 100) if self.opened_count > 0 else 0.0
    
    @property
    def conversion_rate(self) -> float:
        return (self.converted_count / self.clicked_count * 100) if self.clicked_count > 0 else 0.0
    
    @property
    def bounce_rate(self) -> float:
        return (self.bounced_count / self.sent_count * 100) if self.sent_count > 0 else 0.0
    
    @property
    def unsubscribe_rate(self) -> float:
        return (self.unsubscribed_count / self.delivered_count * 100) if self.delivered_count > 0 else 0.0
    
    @property
    def spam_complaint_rate(self) -> float:
        return (self.spam_complaint_count / self.delivered_count * 100) if self.delivered_count > 0 else 0.0


# ===============================================
# EMAIL MARKETING AGENT
# ===============================================

class EmailMarketingAgent:
    """
    AI-powered Email Marketing Agent for bulk campaign automation.
    
    Key responsibilities:
    1. Campaign strategy and planning
    2. Subject line and content generation
    3. Audience segmentation recommendations
    4. Send time optimization
    5. Deliverability risk assessment
    6. Compliance validation
    7. A/B test recommendations
    8. Performance prediction
    """
    
    # Industry benchmarks (from RAG documents)
    BENCHMARK_OPEN_RATE = {
        "saas": 0.215,
        "ecommerce": 0.198,
        "finance": 0.241,
        "healthcare": 0.237,
        "nonprofit": 0.289,
        "b2b": 0.218,
        "default": 0.22
    }
    
    BENCHMARK_CTR = {
        "saas": 0.031,
        "ecommerce": 0.026,
        "finance": 0.038,
        "healthcare": 0.035,
        "nonprofit": 0.045,
        "b2b": 0.029,
        "default": 0.028
    }
    
    # Compliance requirements
    SPAM_COMPLAINT_THRESHOLD = 0.001  # 0.1% (Gmail/Yahoo enforce 0.3% max)
    HARD_BOUNCE_THRESHOLD = 0.005  # 0.5%
    UNSUBSCRIBE_THRESHOLD = 0.003  # 0.3%
    
    # Subject line constraints (research-backed)
    SUBJECT_LINE_MIN_LENGTH = 20
    SUBJECT_LINE_MAX_LENGTH = 50  # Mobile optimization (40 chars visible)
    SUBJECT_LINE_OPTIMAL_LENGTH = 41
    
    # Spam trigger words (sample - full list in RAG)
    SPAM_TRIGGER_WORDS = [
        "free", "guarantee", "no obligation", "winner", "click here",
        "act now", "limited time", "urgent", "cash", "$$", "$$$",
        "100% free", "risk-free", "no credit card", "cancel anytime",
        "congratulations", "you've been selected"
    ]
    
    # Optimal send times (research-backed for 2025)
    OPTIMAL_SEND_TIMES = {
        "b2b": [
            {"day": "Tuesday", "hour": 10, "reasoning": "Mid-morning when professionals check email"},
            {"day": "Wednesday", "hour": 14, "reasoning": "Post-lunch inbox clearing"},
            {"day": "Thursday", "hour": 10, "reasoning": "Late-week engagement peaks"}
        ],
        "b2c": [
            {"day": "Saturday", "hour": 11, "reasoning": "Weekend leisure browsing"},
            {"day": "Tuesday", "hour": 20, "reasoning": "Evening engagement on personal devices"},
            {"day": "Thursday", "hour": 19, "reasoning": "Pre-weekend shopping mindset"}
        ],
        "default": [
            {"day": "Tuesday", "hour": 10, "reasoning": "Universal high-engagement time"},
            {"day": "Thursday", "hour": 14, "reasoning": "Mid-week optimal window"}
        ]
    }
    
    def __init__(self, client_id: str, use_rag: bool = True):
        """
        Initialize Email Marketing Agent.
        
        Args:
            client_id: Unique identifier for client
            use_rag: Whether to load RAG research documents
        """
        self.client_id = client_id
        
        # Initialize Claude AI
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        self.claude = Anthropic(api_key=anthropic_key)
        from utils.ai_config import CLAUDE_SONNET, get_text_model
        self.sonnet_model = CLAUDE_SONNET
        self._tier = "pro"  # default; callers may override via set_tier()
        
        # Initialize RAG system
        self.rag = None
        if use_rag:
            try:
                self.rag = EmailMarketingRAG()
            except Exception as e:
                print(f"⚠️  Warning: Could not load Email Marketing RAG system: {str(e)}")
                print("    Continuing without RAG (recommendations will be less research-backed)")
        
        # Campaign tracking
        self.campaigns: Dict[str, EmailCampaign] = {}
        self.campaign_performance: Dict[str, CampaignPerformance] = {}
        
        print(f"✅ EmailMarketingAgent initialized for client: {client_id}")

    def set_tier(self, tier: str):
        """Set plan tier — switches model for all subsequent API calls."""
        from utils.ai_config import get_text_model
        self._tier = tier or "pro"
        self.sonnet_model = get_text_model(self._tier, complexity="complex")

    def plan_campaign(
        self,
        campaign_type: CampaignType,
        campaign_goal: CampaignGoal,
        target_segment: AudienceSegment,
        content_brief: str,
        client_knowledge: str = "",
        industry: str = "default"
    ) -> CampaignRecommendation:
        """
        Plan a campaign and generate AI recommendations.
        
        Args:
            campaign_type: Type of campaign (newsletter, promotional, etc.)
            campaign_goal: Primary goal (sales, engagement, etc.)
            target_segment: Audience segment to target
            content_brief: Brief description of campaign content/offer
            client_knowledge: Client-specific context (brand voice, products, etc.)
            industry: Industry for benchmark comparison
        
        Returns:
            CampaignRecommendation with AI-generated suggestions
        """
        start_time = datetime.now()
        
        print(f"\n📧 Planning {campaign_type.value} campaign with goal: {campaign_goal.value}")
        
        # Retrieve relevant RAG context
        rag_context = ""
        rag_sources = []
        if self.rag:
            query_parts = [
                campaign_type.value,
                campaign_goal.value,
                "subject line optimization",
                "send time",
                "segmentation"
            ]
            query = " ".join(query_parts)
            
            rag_context = self.rag.retrieve_relevant_context(
                query=query,
                top_k=5
            )
            rag_sources = ["performance_benchmarks", "optimization_strategy", "segmentation_logic"]
        
        # Generate subject line recommendations
        subject_lines = self._generate_subject_lines(
            campaign_type=campaign_type,
            campaign_goal=campaign_goal,
            content_brief=content_brief,
            rag_context=rag_context,
            client_knowledge=client_knowledge
        )
        
        # Determine optimal send times
        send_times = self._recommend_send_times(
            campaign_type=campaign_type,
            target_segment=target_segment,
            industry=industry,
            rag_context=rag_context
        )
        
        # Segment recommendations
        segment_recs = self._recommend_segments(
            campaign_type=campaign_type,
            campaign_goal=campaign_goal,
            rag_context=rag_context
        )
        
        # Content recommendations
        content_recs = self._generate_content_recommendations(
            campaign_type=campaign_type,
            campaign_goal=campaign_goal,
            content_brief=content_brief,
            rag_context=rag_context
        )
        
        # Deliverability assessment
        deliverability = self._assess_deliverability(
            campaign_type=campaign_type,
            subject_lines=subject_lines,
            rag_context=rag_context
        )
        
        # Compliance check
        compliance = self._check_compliance(rag_context=rag_context)
        
        # Overall confidence score
        confidence = self._calculate_confidence(
            subject_lines=subject_lines,
            deliverability=deliverability,
            compliance=compliance
        )
        
        # Estimate performance
        estimated_perf = self._estimate_performance(
            campaign_type=campaign_type,
            target_segment=target_segment,
            industry=industry,
            confidence=confidence
        )
        
        # Warnings
        warnings = self._generate_warnings(
            deliverability=deliverability,
            compliance=compliance,
            subject_lines=subject_lines
        )
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return CampaignRecommendation(
            recommended_subject_lines=subject_lines,
            recommended_send_times=send_times,
            recommended_segments=segment_recs,
            content_recommendations=content_recs,
            deliverability_assessment=deliverability,
            compliance_check=compliance,
            overall_confidence=confidence,
            estimated_performance=estimated_perf,
            warnings=warnings,
            rag_context_used=rag_sources,
            processing_time_ms=processing_time
        )
    
    def _generate_subject_lines(
        self,
        campaign_type: CampaignType,
        campaign_goal: CampaignGoal,
        content_brief: str,
        rag_context: str,
        client_knowledge: str
    ) -> List[Dict[str, Any]]:
        """Generate 3-5 subject line options with scoring"""
        
        # Use structured prompt system if available
        if get_prompt and format_prompt:
            try:
                template = get_prompt("subject_line")
                
                formatted_prompt = format_prompt(
                    template,
                    CAMPAIGN_TYPE=campaign_type.value,
                    CAMPAIGN_GOAL=campaign_goal.value,
                    CONTENT_BRIEF=content_brief[:1000],
                    TARGET_AUDIENCE="General audience",  # Will be enhanced with actual segment data
                    CLIENT_CONTEXT=client_knowledge[:800] if client_knowledge else "Not provided",
                    RESEARCH_CONTEXT=rag_context[:2000] if rag_context else "Not available"
                )
                
                response = self.claude.messages.create(
                    model=self.sonnet_model,
                    max_tokens=2000,
                    temperature=0.8,  # Higher for creativity
                    messages=[{"role": "user", "content": formatted_prompt}]
                )
                
                result_text = response.content[0].text.strip()
                subject_lines = json.loads(result_text)
                
                # Validate and enhance scoring
                for sl in subject_lines:
                    if "length" not in sl:
                        sl["length"] = len(sl["subject"])
                    if "optimal_length" not in sl:
                        sl["optimal_length"] = 20 <= sl["length"] <= 50
                    if "spam_triggers" not in sl:
                        sl["spam_triggers"] = self._detect_spam_triggers(sl["subject"])
                
                return subject_lines
                
            except Exception as e:
                print(f"⚠️  Error with structured prompt, falling back: {str(e)}")
        
        # Fallback to simple prompt if structured system unavailable
        prompt = f"""Generate 3 email subject lines for this campaign:

Campaign Type: {campaign_type.value}
Goal: {campaign_goal.value}
Content: {content_brief}

Client Context: {client_knowledge[:500] if client_knowledge else "Not provided"}

Research Context: {rag_context[:1000] if rag_context else "Not available"}

Requirements:
- Length: 20-50 characters (optimal: 41)
- Mobile-optimized (first 30-40 chars most important)
- Avoid spam trigger words (free, guarantee, act now, etc.)
- Create urgency without being pushy
- Personalize when possible
- Test different emotional appeals

Return JSON array:
[
  {{"subject": "...", "length": 35, "score": 0.85, "reasoning": "Why this works", "emotional_appeal": "curiosity", "spam_risk": "low"}},
  ...
]

JSON only, no preamble:"""
        
        try:
            response = self.claude.messages.create(
                model=self.sonnet_model,
                max_tokens=1500,
                temperature=0.8,  # Higher for creativity
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            subject_lines = json.loads(result_text)
            
            # Validate and score
            for sl in subject_lines:
                sl["length"] = len(sl["subject"])
                sl["optimal_length"] = 20 <= sl["length"] <= 50
                sl["spam_triggers"] = self._detect_spam_triggers(sl["subject"])
            
            return subject_lines
            
        except Exception as e:
            print(f"⚠️  Error generating subject lines: {str(e)}")
            return [{
                "subject": "Important update from us",
                "length": 26,
                "score": 0.5,
                "reasoning": "Fallback subject line",
                "emotional_appeal": "neutral",
                "spam_risk": "low",
                "optimal_length": True,
                "spam_triggers": []
            }]
    
    def _recommend_send_times(
        self,
        campaign_type: CampaignType,
        target_segment: AudienceSegment,
        industry: str,
        rag_context: str
    ) -> List[Dict[str, Any]]:
        """Recommend optimal send times based on research"""
        
        # Determine audience type
        audience_type = "b2b" if "b2b" in industry.lower() else "b2c"
        
        # Get research-backed send times
        base_times = self.OPTIMAL_SEND_TIMES.get(audience_type, self.OPTIMAL_SEND_TIMES["default"])
        
        # Adjust for segment
        if target_segment == AudienceSegment.AT_RISK or target_segment == AudienceSegment.DORMANT:
            # Re-engagement campaigns: test different times
            base_times = [
                {"day": "Saturday", "hour": 11, "reasoning": "Weekend for dormant users (leisure time)"},
                {"day": "Wednesday", "hour": 19, "reasoning": "Evening catch-up time"}
            ]
        
        return base_times
    
    def _recommend_segments(
        self,
        campaign_type: CampaignType,
        campaign_goal: CampaignGoal,
        rag_context: str
    ) -> List[Dict[str, Any]]:
        """Recommend audience segments for this campaign"""
        
        recommendations = []
        
        if campaign_goal == CampaignGoal.RETENTION:
            recommendations.append({
                "segment": AudienceSegment.HIGHLY_ENGAGED.value,
                "expected_open_rate": 0.35,
                "expected_ctr": 0.05,
                "reasoning": "Highly engaged users are most likely to continue engagement"
            })
            recommendations.append({
                "segment": AudienceSegment.MODERATELY_ENGAGED.value,
                "expected_open_rate": 0.25,
                "expected_ctr": 0.03,
                "reasoning": "Keep moderately engaged users active"
            })
        
        elif campaign_goal == CampaignGoal.SALES:
            recommendations.append({
                "segment": AudienceSegment.PROSPECTS.value,
                "expected_open_rate": 0.22,
                "expected_ctr": 0.028,
                "reasoning": "Convert prospects with compelling offer"
            })
            recommendations.append({
                "segment": AudienceSegment.CUSTOMERS.value,
                "expected_open_rate": 0.30,
                "expected_ctr": 0.04,
                "reasoning": "Upsell/cross-sell to existing customers"
            })
        
        elif campaign_type == CampaignType.RE_ENGAGEMENT:
            recommendations.append({
                "segment": AudienceSegment.AT_RISK.value,
                "expected_open_rate": 0.12,
                "expected_ctr": 0.015,
                "reasoning": "Last chance to re-engage before dormancy"
            })
            recommendations.append({
                "segment": AudienceSegment.DORMANT.value,
                "expected_open_rate": 0.08,
                "expected_ctr": 0.01,
                "reasoning": "Win-back campaign for dormant subscribers"
            })
        
        else:
            recommendations.append({
                "segment": AudienceSegment.ALL_SUBSCRIBERS.value,
                "expected_open_rate": 0.22,
                "expected_ctr": 0.028,
                "reasoning": "Broadcast to full list"
            })
        
        return recommendations
    
    def _generate_content_recommendations(
        self,
        campaign_type: CampaignType,
        campaign_goal: CampaignGoal,
        content_brief: str,
        rag_context: str
    ) -> Dict[str, str]:
        """Generate content structure recommendations"""
        
        recommendations = {
            "email_length": "150-300 words for optimal CTR (research-backed)",
            "cta_placement": "Primary CTA above fold, secondary CTA at bottom",
            "design": "Single-column mobile-first layout, large tap targets (44x44px min)",
            "personalization": "Use recipient name in opening, reference past behavior if available",
            "formatting": "Short paragraphs (2-3 lines), bullet points for scannability",
            "images": "1-3 images max, always include alt text, <100KB each",
            "links": "3-5 links total, clear link text (avoid 'click here')",
            "preview_text": "50-100 characters, complement subject line, don't repeat it"
        }
        
        if campaign_goal == CampaignGoal.SALES:
            recommendations["urgency"] = "Include time-limited offer or scarcity element"
            recommendations["social_proof"] = "Add customer testimonial or stat"
        
        return recommendations
    
    def _assess_deliverability(
        self,
        campaign_type: CampaignType,
        subject_lines: List[Dict[str, Any]],
        rag_context: str
    ) -> Dict[str, Any]:
        """Assess deliverability risks"""
        
        risk_factors = []
        risk_level = DeliverabilityRisk.LOW
        
        # Check subject lines for spam triggers
        for sl in subject_lines:
            if sl.get("spam_triggers"):
                risk_factors.append(f"Subject line contains spam triggers: {', '.join(sl['spam_triggers'])}")
                risk_level = DeliverabilityRisk.MEDIUM
        
        return {
            "risk_level": risk_level.value,
            "risk_factors": risk_factors,
            "authentication_required": ["SPF", "DKIM", "DMARC (p=quarantine or p=reject)"],
            "recommendations": [
                "Implement one-click unsubscribe header (RFC 8058)",
                "Maintain spam complaint rate below 0.1%",
                "Monitor sender reputation via Google Postmaster Tools",
                "Ensure hard bounce rate stays below 0.5%"
            ]
        }
    
    def _check_compliance(self, rag_context: str) -> Dict[str, bool]:
        """Check compliance requirements"""
        
        return {
            "has_unsubscribe_link": True,  # Will validate in actual implementation
            "has_physical_address": True,
            "has_one_click_unsubscribe_header": False,  # Needs implementation
            "spf_configured": False,  # Needs validation
            "dkim_configured": False,
            "dmarc_configured": False,
            "can_spam_compliant": True,
            "gdpr_compliant": True
        }
    
    def _calculate_confidence(
        self,
        subject_lines: List[Dict[str, Any]],
        deliverability: Dict[str, Any],
        compliance: Dict[str, bool]
    ) -> float:
        """Calculate overall confidence score (0.0-1.0)"""
        
        score = 0.7  # Base score
        
        # Subject line quality
        avg_sl_score = sum(sl.get("score", 0.5) for sl in subject_lines) / len(subject_lines)
        score += (avg_sl_score - 0.5) * 0.2
        
        # Deliverability risk
        if deliverability["risk_level"] == "low":
            score += 0.1
        elif deliverability["risk_level"] == "high":
            score -= 0.2
        
        # Compliance
        compliance_rate = sum(1 for v in compliance.values() if v) / len(compliance)
        score += (compliance_rate - 0.5) * 0.1
        
        return min(max(score, 0.0), 1.0)
    
    def _estimate_performance(
        self,
        campaign_type: CampaignType,
        target_segment: AudienceSegment,
        industry: str,
        confidence: float
    ) -> Dict[str, float]:
        """Estimate campaign performance based on benchmarks"""
        
        base_open_rate = self.BENCHMARK_OPEN_RATE.get(industry, self.BENCHMARK_OPEN_RATE["default"])
        base_ctr = self.BENCHMARK_CTR.get(industry, self.BENCHMARK_CTR["default"])
        
        # Adjust for segment
        segment_multiplier = {
            AudienceSegment.HIGHLY_ENGAGED: 1.5,
            AudienceSegment.MODERATELY_ENGAGED: 1.1,
            AudienceSegment.LOW_ENGAGEMENT: 0.8,
            AudienceSegment.AT_RISK: 0.5,
            AudienceSegment.DORMANT: 0.3,
            AudienceSegment.NEW_SUBSCRIBERS: 1.3,
            AudienceSegment.CUSTOMERS: 1.4,
            AudienceSegment.VIP: 1.6
        }.get(target_segment, 1.0)
        
        # Adjust for confidence
        confidence_multiplier = 0.7 + (confidence * 0.6)  # 0.7-1.3 range
        
        estimated_open = base_open_rate * segment_multiplier * confidence_multiplier
        estimated_ctr = base_ctr * segment_multiplier * confidence_multiplier
        
        return {
            "open_rate": round(estimated_open, 4),
            "click_rate": round(estimated_ctr, 4),
            "click_to_open_rate": round((estimated_ctr / estimated_open * 100) if estimated_open > 0 else 0, 2),
            "conversion_rate": round(estimated_ctr * 0.5, 4),  # Rough estimate
            "unsubscribe_rate": 0.0015,  # 0.15%
            "spam_complaint_rate": 0.0005  # 0.05%
        }
    
    def _generate_warnings(
        self,
        deliverability: Dict[str, Any],
        compliance: Dict[str, bool],
        subject_lines: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate warnings for potential issues"""
        
        warnings = []
        
        # Deliverability warnings
        if deliverability["risk_level"] in ["high", "critical"]:
            warnings.append(f"⚠️  High deliverability risk: {', '.join(deliverability.get('risk_factors', []))}")
        
        # Compliance warnings
        if not compliance.get("has_one_click_unsubscribe_header"):
            warnings.append("⚠️  One-click unsubscribe header not configured (required by Gmail/Yahoo 2025)")
        
        if not all([compliance.get("spf_configured"), compliance.get("dkim_configured"), compliance.get("dmarc_configured")]):
            warnings.append("⚠️  Email authentication incomplete (SPF, DKIM, DMARC required)")
        
        # Subject line warnings
        for sl in subject_lines:
            if not sl.get("optimal_length"):
                warnings.append(f"⚠️  Subject line '{sl['subject'][:30]}...' is not optimal length (20-50 chars)")
        
        return warnings
    
    def _detect_spam_triggers(self, text: str) -> List[str]:
        """Detect spam trigger words in text"""
        text_lower = text.lower()
        triggers = []
        
        for word in self.SPAM_TRIGGER_WORDS:
            if word in text_lower:
                triggers.append(word)
        
        return triggers
    
    def get_campaign_stats(self) -> Dict[str, Any]:
        """Get overall campaign statistics"""
        
        total_campaigns = len(self.campaigns)
        sent_campaigns = sum(1 for c in self.campaigns.values() if c.status == "sent")
        
        return {
            "total_campaigns": total_campaigns,
            "sent_campaigns": sent_campaigns,
            "draft_campaigns": sum(1 for c in self.campaigns.values() if c.status == "draft"),
            "scheduled_campaigns": sum(1 for c in self.campaigns.values() if c.status == "scheduled")
        }

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Send a single email through the client's connected email account
        (Gmail / Microsoft / IMAP-SMTP) via the unified email service.

        Falls back to Resend if no client email is connected and RESEND_API_KEY is set.
        """
        # ── Try unified email service first (client's own mailbox) ──
        try:
            import asyncio
            from utils.email_service import send_email as _svc_send

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        _svc_send(
                            self.client_id,
                            to_email=to_email,
                            subject=subject,
                            body=text_body or html_body,
                            html_body=html_body,
                        )
                    ).result()
            else:
                result = asyncio.run(
                    _svc_send(
                        self.client_id,
                        to_email=to_email,
                        subject=subject,
                        body=text_body or html_body,
                        html_body=html_body,
                    )
                )
            if result.get("ok"):
                print(f"✅ Email sent via client mailbox | To: {to_email}")
                return {"status": "sent", "message_id": result.get("message_id"), "error": None}
            # If service returned an error, log but continue to fallback
            print(f"⚠️  email_service.send_email returned error: {result.get('error')}")
        except Exception as svc_err:
            print(f"⚠️  email_service.send_email failed: {svc_err}")

        # ── Fallback: Resend API ────────────────────────────────────
        resend_key = os.getenv("RESEND_API_KEY", "")
        sender_email = from_email or os.getenv("EMAIL_FROM_ADDRESS", "")
        sender_name = from_name or "Team"

        if not sender_email:
            return {"status": "error", "message_id": None, "error": "No connected email and no from_email provided."}

        if not _RESEND_AVAILABLE:
            print(f"⚠️  Resend not installed. [SIMULATED] Would send to: {to_email}")
            return {"status": "simulated", "message_id": None, "error": "resend not installed"}

        if not resend_key:
            print(f"⚠️  RESEND_API_KEY not set → [DRAFT] To: {to_email} | Subject: {subject}")
            return {"status": "draft", "message_id": None, "error": "RESEND_API_KEY not configured"}

        try:
            resend_sdk.api_key = resend_key
            if not text_body:
                import re as _re
                text_body = _re.sub(r'<[^>]+>', '', html_body).strip()
            params: Dict[str, Any] = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "text": text_body,
                "reply_to": reply_to or sender_email,
            }
            if tags:
                params["tags"] = tags
            result = resend_sdk.Emails.send(params)
            msg_id = result.get("id") or result.get("message_id", "unknown")
            print(f"✅ Email sent via Resend | ID: {msg_id} | To: {to_email}")
            return {"status": "sent", "message_id": msg_id, "error": None}
        except Exception as e:
            print(f"❌ Resend send failed: {e}")
            return {"status": "error", "message_id": None, "error": str(e)}

    def send_campaign_live(
        self,
        recipients: List[Dict[str, str]],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        campaign_tag: Optional[str] = None,
        batch_size: int = 50,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Send a marketing campaign to a list of recipients.

        Primary path: uses the client's connected email (Gmail / Microsoft / IMAP)
        via the unified email service. Falls back to Resend if no client email is
        connected and RESEND_API_KEY is set.
        """
        import time

        results = {
            "total_recipients": len(recipients),
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
            "message_ids": [],
            "dry_run": dry_run,
        }

        if dry_run:
            for r in recipients:
                print(f"   [DRY RUN] Would send to: {r.get('email', '?')}")
            results["sent"] = len(recipients)
            return results

        # ── Try unified email_service.send_campaign_batch first ─────
        try:
            import asyncio
            from utils.email_service import send_campaign_batch as _batch

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    svc_result = pool.submit(
                        asyncio.run,
                        _batch(
                            self.client_id,
                            recipients=recipients,
                            subject=subject,
                            body=text_body or re.sub(r'<[^>]+>', '', html_body).strip(),
                            html_body=html_body,
                        )
                    ).result()
            else:
                svc_result = asyncio.run(
                    _batch(
                        self.client_id,
                        recipients=recipients,
                        subject=subject,
                        body=text_body or re.sub(r'<[^>]+>', '', html_body).strip(),
                        html_body=html_body,
                    )
                )
            if svc_result.get("ok"):
                results["sent"] = svc_result.get("sent", 0)
                results["failed"] = svc_result.get("failed", 0)
                results["errors"] = svc_result.get("errors", [])
                print(f"✅ Campaign sent via client mailbox — {results['sent']} sent, {results['failed']} failed")
                return results
            print(f"⚠️  email_service batch returned error: {svc_result.get('error')}")
        except Exception as svc_err:
            print(f"⚠️  email_service batch failed: {svc_err}")

        # ── Fallback: Resend API ────────────────────────────────────
        resend_key = os.getenv("RESEND_API_KEY", "")
        sender_email = from_email or os.getenv("EMAIL_FROM_ADDRESS", "")
        sender_name = from_name or "Team"

        if not sender_email:
            results["errors"].append("No connected email and no from_email provided.")
            return results

        if not _RESEND_AVAILABLE:
            results["skipped"] = len(recipients)
            results["errors"].append("resend package not installed")
            return results

        if not resend_key:
            results["skipped"] = len(recipients)
            results["errors"].append("RESEND_API_KEY not configured")
            return results

        resend_sdk.api_key = resend_key
        print(f"\n📧 Sending campaign via Resend to {len(recipients)} recipients")

        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            for recipient in batch:
                to_email = recipient.get("email", "")
                to_name = recipient.get("name", "")
                if not to_email:
                    results["skipped"] += 1
                    continue
                try:
                    personalized_subject = subject
                    if to_name and "{name}" in subject:
                        personalized_subject = subject.replace("{name}", to_name.split()[0])
                    personalized_html = html_body
                    if to_name:
                        personalized_html = html_body.replace("{{first_name}}", to_name.split()[0])
                        personalized_html = personalized_html.replace("{{name}}", to_name)
                    params: Dict[str, Any] = {
                        "from": f"{sender_name} <{sender_email}>",
                        "to": [to_email if not to_name else f"{to_name} <{to_email}>"],
                        "subject": personalized_subject,
                        "html": personalized_html,
                        "text": text_body or re.sub(r'<[^>]+>', '', html_body).strip(),
                        "reply_to": sender_email,
                    }
                    if campaign_tag:
                        params["tags"] = [{"name": "campaign", "value": campaign_tag}]
                    result = resend_sdk.Emails.send(params)
                    results["sent"] += 1
                    results["message_ids"].append(result.get("id", "unknown"))
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"{to_email}: {str(e)}")
            if i + batch_size < len(recipients):
                time.sleep(0.5)

        print(f"{'✅' if results['failed'] == 0 else '⚠️'} Campaign: Sent {results['sent']} | Failed {results['failed']}")
        return results

# ===============================================
# TESTING
# ===============================================

if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    print("=" * 60)
    print("EMAIL MARKETING AGENT - TESTING")
    print("=" * 60)
    
    # Initialize agent
    agent = EmailMarketingAgent(
        client_id="test_client",
        use_rag=True
    )
    
    print("\n" + "=" * 60)
    print("TEST 1: Newsletter Campaign Planning")
    print("=" * 60)
    
    recommendation = agent.plan_campaign(
        campaign_type=CampaignType.NEWSLETTER,
        campaign_goal=CampaignGoal.ENGAGEMENT,
        target_segment=AudienceSegment.HIGHLY_ENGAGED,
        content_brief="Monthly product updates and industry insights for SaaS customers",
        client_knowledge="B2B SaaS company selling project management software to mid-market",
        industry="saas"
    )
    
    print(f"\n✅ Campaign planned successfully!")
    print(f"   Overall Confidence: {recommendation.overall_confidence:.2f}")
    print(f"   Processing Time: {recommendation.processing_time_ms}ms")
    
    print(f"\n📝 Recommended Subject Lines ({len(recommendation.recommended_subject_lines)}):")
    for i, sl in enumerate(recommendation.recommended_subject_lines, 1):
        print(f"   {i}. \"{sl['subject']}\" (score: {sl.get('score', 0):.2f}, length: {sl['length']})")
        print(f"      Reasoning: {sl.get('reasoning', 'N/A')[:80]}...")
    
    print(f"\n🕐 Recommended Send Times ({len(recommendation.recommended_send_times)}):")
    for st in recommendation.recommended_send_times:
        print(f"   - {st['day']} at {st['hour']}:00 - {st['reasoning']}")
    
    print(f"\n📊 Estimated Performance:")
    for metric, value in recommendation.estimated_performance.items():
        if isinstance(value, float):
            print(f"   - {metric}: {value:.2%}")
    
    print(f"\n🚨 Warnings ({len(recommendation.warnings)}):")
    for warning in recommendation.warnings:
        print(f"   {warning}")
    
    print(f"\n⚙️  Deliverability Assessment:")
    print(f"   Risk Level: {recommendation.deliverability_assessment['risk_level'].upper()}")
    print(f"   Required: {', '.join(recommendation.deliverability_assessment['authentication_required'])}")
    
    print("\n" + "=" * 60)
    print("TEST 2: Promotional Campaign")
    print("=" * 60)
    
    promo_rec = agent.plan_campaign(
        campaign_type=CampaignType.PROMOTIONAL,
        campaign_goal=CampaignGoal.SALES,
        target_segment=AudienceSegment.PROSPECTS,
        content_brief="Limited-time 30% discount on annual plans, expires in 48 hours",
        client_knowledge="E-commerce company selling online courses",
        industry="ecommerce"
    )
    
    print(f"\n✅ Promotional campaign planned!")
    print(f"   Overall Confidence: {promo_rec.overall_confidence:.2f}")
    print(f"   Estimated Open Rate: {promo_rec.estimated_performance['open_rate']:.2%}")
    print(f"   Estimated CTR: {promo_rec.estimated_performance['click_rate']:.2%}")
    
    print(f"\n📝 Top Subject Line:")
    if promo_rec.recommended_subject_lines:
        top_sl = promo_rec.recommended_subject_lines[0]
        print(f"   \"{top_sl['subject']}\"")
        print(f"   Emotional Appeal: {top_sl.get('emotional_appeal', 'N/A')}")
        print(f"   Spam Risk: {top_sl.get('spam_risk', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("TEST 3: Campaign Statistics")
    print("=" * 60)
    
    stats = agent.get_campaign_stats()
    print(f"\nTotal Campaigns: {stats['total_campaigns']}")
    print(f"Sent: {stats['sent_campaigns']}")
    print(f"Draft: {stats['draft_campaigns']}")
    print(f"Scheduled: {stats['scheduled_campaigns']}")
    
    print("\n" + "=" * 60)
    print("✅ TESTING COMPLETE")
    print("=" * 60)
