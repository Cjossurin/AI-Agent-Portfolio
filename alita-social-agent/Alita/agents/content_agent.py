# agents/content_agent.py
import os
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass
from anthropic import Anthropic
from dotenv import load_dotenv
from agents.rag_system import RAGSystem
from agents.marketing_intelligence_agent import MarketingIntelligenceAgent, ContentIdea
from agents.posting_agent import PostingAgent, ContentPost, PostingStatus
from agents.engagement_agent import EngagementAgent
from agents.client_profile_manager import ClientProfileManager, ClientProfile
from pathlib import Path
from utils.file_reader import load_texts_from_folder
import json
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Type aliases for better readability
ContentType = Literal["social_post", "caption", "email", "blog_post", "dm_response"]
Platform = Literal["facebook", "instagram", "linkedin", "twitter", "tiktok", "youtube", "blog", "email"]

@dataclass
class ContentRequest:
    """Represents a content generation request."""
    content_type: ContentType
    platform: Platform
    topic: Optional[str] = None
    context: Optional[str] = None
    tone: Optional[str] = None  # Override client's default tone if needed
    max_length: Optional[int] = None
    include_hashtags: bool = False
    include_cta: bool = False
    metadata: Optional[Dict] = None

@dataclass
class GeneratedContent:
    """Represents generated content with metadata."""
    content: str
    content_type: ContentType
    platform: Platform
    word_count: int
    char_count: int
    hashtags: Optional[List[str]] = None
    metadata: Optional[Dict] = None
    rag_sources: Optional[List[str]] = None

class ContentCreationAgent:
    """
    Content Creation Agent - Generates multi-format, client-specific content.
    
    Capabilities:
    - Social media posts (Facebook, Instagram, LinkedIn, Twitter, TikTok)
    - Email campaigns
    - Blog posts
    - Captions and CTAs
    - Single and batch content generation
    - RAG-powered context awareness
    - Client voice matching
    """
    
    def __init__(self, client_id: str = "demo_client"):
        """
        Initialize Content Creation Agent.
        
        Args:
            client_id: Unique identifier for the client
        """
        self.client_id = client_id
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.rag = RAGSystem()
        
        # Load client profile (niche, platforms, tone, etc.)
        self.profile_manager = ClientProfileManager()
        self.client_profile: Optional[ClientProfile] = self.profile_manager.get_client_profile(client_id)
        
        # Initialize other agents for integrated workflow
        self.marketing_agent = MarketingIntelligenceAgent(client_id=client_id)
        self.posting_agent = PostingAgent(client_id=client_id)
        self.engagement_agent = EngagementAgent(client_id=client_id)
        
        # Load voice/style context for this client
        self.style_context = self._load_style_references(client_id)
        
        # Load Claude model configuration from central ai_config
        from utils.ai_config import CLAUDE_HAIKU, CLAUDE_SONNET
        self.haiku_model = CLAUDE_HAIKU
        self.sonnet_model = CLAUDE_SONNET
        self.default_model = os.getenv("CLAUDE_DEFAULT_MODEL", "haiku")
        
        # Platform-specific character limits
        self.platform_limits = {
            "twitter": 280,
            "instagram": 2200,
            "facebook": 63206,
            "linkedin": 3000,
            "tiktok": 2200,
            "youtube": 5000,
            "blog": None,  # No strict limit
            "email": None   # No strict limit
        }
        
        print(f"✅ Content Creation Agent ready for {client_id}")
        if self.client_profile:
            niche_name = self.client_profile.niche.value if hasattr(self.client_profile.niche, 'value') else self.client_profile.niche
            print(f"🎯 Client Niche: {niche_name}")
            print(f"📱 Platforms: {', '.join(self.client_profile.platforms)}")
            print(f"📅 Posting Frequency: {self.client_profile.posting_frequency}/week")
        if self.style_context:
            print(f"🎨 Loaded style references for {client_id}")
    
    def _load_style_references(self, client_id: str) -> str:
        """Load client-specific style references for voice matching."""
        # Try client-specific folder first
        client_folder = Path("style_references") / client_id
        if client_folder.exists():
            style_text = load_texts_from_folder(str(client_folder))
            if style_text:
                return style_text
        
        # Fallback to root style_references folder
        root_folder = Path("style_references")
        if root_folder.exists():
            style_text = load_texts_from_folder(str(root_folder))
            if style_text:
                return style_text
        
        return ""
    
    def _select_model(self, content_type: ContentType, topic_complexity: str = "simple", tier: str = "pro") -> str:
        """
        Select appropriate Claude model based on plan tier, content type and complexity.
        
        Args:
            content_type: Type of content being generated
            topic_complexity: "simple" or "complex"
            tier: Plan tier ("free", "starter", "growth", "pro")
        
        Returns:
            Model identifier string
        """
        from utils.ai_config import get_text_model

        # Always use default if set to sonnet
        if self.default_model == "sonnet":
            return self.sonnet_model
        
        # Determine task complexity for tier-based selection
        complex_types = ["blog_post", "email"]
        if content_type in complex_types or topic_complexity == "complex":
            complexity = "complex"
        else:
            complexity = "simple"

        model = get_text_model(tier, complexity)
        print(f"{'📊' if complexity == 'complex' else '⚡'} Using {model} for {content_type} (tier={tier})")
        return model
    
    async def generate_content(
        self,
        request: ContentRequest,
        use_rag: bool = True,
        tier: str = "pro",
    ) -> GeneratedContent:
        """
        Generate single piece of content based on request.
        
        Args:
            request: ContentRequest with generation parameters
            use_rag: Whether to query RAG system for context
        
        Returns:
            GeneratedContent object with generated text and metadata
        """
        print(f"\n🎨 Generating {request.content_type} for {request.platform}...")
        
        # Gather context from RAG if enabled
        rag_context = ""
        rag_sources = []
        if use_rag and request.topic:
            print("🔍 Querying knowledge base...")
            relevant_info = self.rag.search(query=request.topic, client_id=self.client_id, limit=3, score_threshold=0.5)
            if not relevant_info:
                # Fallback: search by business name
                biz_name = getattr(self.client_profile, "business_name", "") if self.client_profile else ""
                if biz_name:
                    relevant_info = self.rag.search(query=biz_name, client_id=self.client_id, limit=3, score_threshold=0.5)
            if relevant_info:
                rag_context = "\n".join([f"- {info['text']}" for info in relevant_info])
                rag_sources = [info.get('source', 'Unknown') for info in relevant_info]
                print(f"📚 Found {len(relevant_info)} relevant knowledge items")
        
        # Build style section if available
        style_section = ""
        if self.style_context:
            style_section = f"""
### STYLE & VOICE MATCHING
You must write in this client's unique voice and style. Study these examples:

--- CLIENT WRITING SAMPLES ---
{self.style_context}
--- END SAMPLES ---

Mimic the tone, vocabulary, sentence structure, and personality shown above.
"""
        
        # Get platform-specific limit
        char_limit = self.platform_limits.get(request.platform)
        if request.max_length:
            char_limit = min(char_limit, request.max_length) if char_limit else request.max_length
        
        # Build content generation prompt
        prompt = self._build_generation_prompt(
            request=request,
            rag_context=rag_context,
            style_section=style_section,
            char_limit=char_limit
        )
        
        # Select appropriate model (tier-aware)
        model = self._select_model(request.content_type, tier=tier)
        
        # Generate content
        print("🤖 Generating content with Claude...")
        response = self.claude_client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        generated_text = response.content[0].text.strip()
        
        # Extract hashtags if present
        hashtags = None
        if request.include_hashtags and "#" in generated_text:
            hashtags = [tag.strip() for tag in generated_text.split() if tag.startswith("#")]
        
        # Create result object
        result = GeneratedContent(
            content=generated_text,
            content_type=request.content_type,
            platform=request.platform,
            word_count=len(generated_text.split()),
            char_count=len(generated_text),
            hashtags=hashtags,
            metadata=request.metadata,
            rag_sources=rag_sources if rag_sources else None
        )
        
        print(f"✅ Generated {result.word_count} words ({result.char_count} chars)")
        return result
    
    def _build_generation_prompt(
        self,
        request: ContentRequest,
        rag_context: str,
        style_section: str,
        char_limit: Optional[int]
    ) -> str:
        """Build the prompt for content generation."""
        
        # Base system prompt
        prompt = f"""You are a professional content creator specializing in {request.platform} content.
{style_section}
### CONTENT REQUIREMENTS
- Content Type: {request.content_type}
- Platform: {request.platform}
- Topic: {request.topic or 'General brand content'}
"""
        
        # Add character limit if applicable
        if char_limit:
            prompt += f"- Maximum Length: {char_limit} characters\n"
        
        # Add tone guidance (use niche tone if available)
        tone = request.tone
        if not tone and self.client_profile:
            tone = self.client_profile.tone
        if not tone:
            tone = "professional yet approachable"
        prompt += f"- Tone: {tone}\n"
        
        # Add content pillars if available
        if self.client_profile and self.client_profile.content_pillars:
            prompt += f"- Content Pillars: {self.client_profile.content_pillars}\n"
        
        # Add hashtag requirement (use niche keywords if available)
        if request.include_hashtags:
            if self.client_profile and self.client_profile.keywords:
                prompt += f"- Include 3-5 relevant hashtags from these keywords: {', '.join(self.client_profile.keywords[:10])}\n"
            else:
                prompt += "- Include relevant hashtags (3-5)\n"
        
        # Add CTA requirement
        if request.include_cta:
            prompt += "- Include a clear call-to-action\n"
        
        # Add RAG context if available
        if rag_context:
            prompt += f"""
### KNOWLEDGE BASE CONTEXT
Use the following information to create accurate, informative content:

{rag_context}
"""
        
        # Add additional context if provided
        if request.context:
            prompt += f"""
### ADDITIONAL CONTEXT
{request.context}
"""
        
        # Add platform-specific guidelines
        prompt += self._get_platform_guidelines(request.platform)
        
        # Final instructions
        prompt += """
### INSTRUCTIONS
Generate engaging, high-quality content that:
1. Matches the client's voice and style perfectly
2. Fits the platform's format and best practices
3. Uses information from the knowledge base when relevant
4. Stays within character limits
5. Includes hashtags and/or CTA if requested

Output only the final content, ready to post. Do not include explanations or meta-commentary.
"""
        
        return prompt
    
    def _get_platform_guidelines(self, platform: Platform) -> str:
        """Get platform-specific content guidelines."""
        guidelines = {
            "facebook": """
### FACEBOOK GUIDELINES
- Conversational and engaging tone
- Ask questions to drive comments
- Use emojis sparingly
- Links are OK
- Ideal length: 40-80 words
""",
            "instagram": """
### INSTAGRAM GUIDELINES
- Visual-first mentality (assume image/video present)
- Emojis and line breaks for readability
- Hashtags at the end or in first comment
- First 125 characters are crucial (preview)
- Ideal length: 138-150 characters
""",
            "linkedin": """
### LINKEDIN GUIDELINES
- Professional yet personable
- Value-driven content
- Industry insights and thought leadership
- Minimal emojis
- Ideal length: 150-250 words
""",
            "twitter": """
### TWITTER GUIDELINES
- Concise and punchy
- Hook in first 10 words
- Use threads for longer content
- 1-2 hashtags max
- Ideal length: 100-280 characters
""",
            "tiktok": """
### TIKTOK GUIDELINES
- Casual, authentic tone
- Trending language OK
- Hooks for video captions
- Multiple hashtags encouraged
- Ideal length: 100-150 characters
""",
            "email": """
### EMAIL GUIDELINES
- Clear subject line strategy
- Scannable format (short paragraphs)
- Strong CTA
- Personalization when possible
- Ideal length: 50-125 words
""",
            "blog": """
### BLOG POST GUIDELINES
- Clear structure (intro, body, conclusion)
- Subheadings for scannability
- SEO-friendly
- Conversational yet informative
- Ideal length: 600-1200 words
"""
        }
        
        return guidelines.get(platform, "")
    
    async def generate_batch(
        self,
        requests: List[ContentRequest],
        use_rag: bool = True
    ) -> List[GeneratedContent]:
        """
        Generate multiple pieces of content in batch.
        
        Args:
            requests: List of ContentRequest objects
            use_rag: Whether to use RAG for context
        
        Returns:
            List of GeneratedContent objects
        """
        print(f"\n📦 Batch generating {len(requests)} pieces of content...")
        
        results = []
        for i, request in enumerate(requests, 1):
            print(f"\n--- Content {i}/{len(requests)} ---")
            try:
                content = await self.generate_content(request, use_rag=use_rag)
                results.append(content)
            except Exception as e:
                print(f"❌ Error generating content {i}: {e}")
                # Continue with remaining items
                continue
        
        print(f"\n✅ Successfully generated {len(results)}/{len(requests)} pieces of content")
        return results

    async def generate_batch_for_calendar(
        self,
        platform: str,
        pieces_info: List[dict],
        niche: Optional[str] = None,
        use_rag: bool = True,
    ) -> List[dict]:
        """
        Generate content for multiple calendar pieces in ONE Claude call.
        Reduces API calls from O(N) per platform to O(1) per platform batch.

        Args:
            platform: Target platform
            pieces_info: List of dicts with keys:
                - piece_id: unique identifier
                - content_type: e.g. "reel", "post", "carousel", "story"
                - topic: suggested topic/hook (optional)
                - seeded_idea: full seeded idea dict (optional)
            niche: Client niche (uses client profile if not provided)
            use_rag: Whether to enrich prompt with RAG context

        Returns:
            List of dicts: [{piece_id, topic, content_type, caption, hashtags, content_notes}]
        """
        if not pieces_info:
            return []

        if not niche and self.client_profile:
            niche_value = self.client_profile.niche.value if hasattr(self.client_profile.niche, "value") else self.client_profile.niche
            niche = niche_value.replace("_", " ")
        elif not niche:
            niche = "general business"

        # One RAG query for the full batch
        rag_hints = ""
        if use_rag:
            try:
                sample_topic = next(
                    (p.get("topic") or (p.get("seeded_idea") or {}).get("title", "")
                     for p in pieces_info if p.get("topic") or p.get("seeded_idea")),
                    niche
                )
                # Try specific topic first; fall back to niche; use permissive threshold
                biz_name = ""
                if self.client_profile:
                    biz_name = getattr(self.client_profile, "business_name", "") or ""
                for _q in [sample_topic, biz_name, niche]:
                    if not _q:
                        continue
                    _r = self.rag.search(query=_q, client_id=self.client_id, limit=3, score_threshold=0.5)
                    if _r:
                        rag_hints = "\n".join([f"- {r['text'][:300]}" for r in _r])
                        break
            except Exception:
                pass

        style_section = ""
        if self.style_context:
            style_section = f"VOICE & STYLE — write in the client's unique tone and vocabulary:\n{self.style_context[:600]}\n"

        tone = "professional yet approachable"
        if self.client_profile and getattr(self.client_profile, "tone", None):
            tone = self.client_profile.tone

        # Per-content-type format guidance
        ct_guidance = {
            "reel":       "Short punchy hook (grabs in 1s), 150-300 char caption, trend-driven energy",
            "story":      "Casual 1-2 sentences, include a question or poll prompt, very conversational",
            "carousel":   "Educational '5 ways to...' style, caption teases all slides, 300-500 chars",
            "thread":     "Start with 🧵 Thread:, hook first tweet, outline 3-5 key points",
            "tweet":      "Under 240 chars, punchy insight/question/stat, no filler",
            "article":    "Thought-leadership, 3 short paragraphs with clear insight, 400-700 chars",
            "video":      "Hook line + 2-3 content points for description, 200-400 chars",
            "shorts":     "One punchy hook + 2 lines of context, TikTok-style energy, short",
            "post":       "Story-driven or value-driven caption, 200-400 chars, end with CTA or question",
            "newsletter": "Subject-line worthy: informative + intriguing, 300-600 chars",
        }

        # Build numbered piece list for prompt
        pieces_list = ""
        for i, p in enumerate(pieces_info, 1):
            ct = p.get("content_type", "post")
            topic_hint = p.get("topic") or ""
            if not topic_hint and p.get("seeded_idea"):
                si = p["seeded_idea"]
                topic_hint = si.get("title") or si.get("topic") or si.get("hook") or ""
            guidance = ct_guidance.get(ct, ct_guidance["post"])
            hint_part = f', topic_hint="{topic_hint}"' if topic_hint else ""
            pieces_list += f"  {i}. content_type={ct}{hint_part} | format: {guidance}\n"

        hashtag_note = ""
        if platform.lower() in ["instagram", "tiktok", "threads"]:
            kw_str = ""
            if self.client_profile and getattr(self.client_profile, "keywords", None):
                kw_str = f" (prefer: {', '.join(self.client_profile.keywords[:6])})"
            hashtag_note = f'  "hashtags": "3-5 relevant hashtags{kw_str}",'
        else:
            hashtag_note = '  "hashtags": "",'

        platform_char_limits = {
            "twitter": 240, "instagram": 2200, "facebook": 5000,
            "linkedin": 2000, "tiktok": 2200, "youtube": 3000, "threads": 500
        }
        char_limit = platform_char_limits.get(platform.lower(), 2000)

        pillars_note = ""
        if self.client_profile and getattr(self.client_profile, "content_pillars", None):
            pillars = self.client_profile.content_pillars
            if isinstance(pillars, list):
                pillars = ", ".join(pillars[:4])
            pillars_note = f"Content pillars: {pillars}\n"

        rag_section = f"Brand context from knowledge base:\n{rag_hints}" if rag_hints else ""

        prompt = f"""You are a professional {platform} content creator. Generate {len(pieces_info)} unique social media posts.

Platform: {platform}
Niche/Industry: {niche}
Tone: {tone}
Max caption characters: {char_limit}
{pillars_note}{style_section}
{rag_section}
Posts to generate (respect content_type and topic_hint for each):
{pieces_list}
Return ONLY a valid JSON array with exactly {len(pieces_info)} objects in the same order:
[
  {{
    "piece_number": 1,
    "topic": "concise topic title (5-10 words)",
    "content_type": "same content_type as requested",
    "caption": "full ready-to-post caption",
    {hashtag_note}
    "content_notes": "brief format note"
  }},
  ...
]
JSON only. No markdown fences, no explanation."""

        try:
            response = self.claude_client.messages.create(
                model=self.haiku_model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0].strip()
            items = json.loads(raw)
        except Exception as exc:
            logger.error(f"generate_batch_for_calendar parse error ({platform}): {exc}")
            return []

        results = []
        for i, item in enumerate(items):
            if i < len(pieces_info):
                results.append({
                    "piece_id":      pieces_info[i]["piece_id"],
                    "topic":         item.get("topic", ""),
                    "content_type":  item.get("content_type", pieces_info[i].get("content_type", "post")),
                    "caption":       item.get("caption", ""),
                    "hashtags":      item.get("hashtags", ""),
                    "content_notes": item.get("content_notes", ""),
                })
        return results

    async def generate_week_of_posts(
        self,
        platforms: Optional[List[Platform]] = None,
        posts_per_day: Optional[int] = None,
        topics: Optional[List[str]] = None
    ) -> List[GeneratedContent]:
        """
        Generate a week's worth of social media posts based on client's niche.
        
        Args:
            platforms: Platforms to generate for (uses niche platforms if not provided)
            posts_per_day: Number of posts per day per platform (uses niche frequency if not provided)
            topics: Optional list of topics to cover (uses content pillars if not provided)
        
        Returns:
            List of GeneratedContent for the week
        """
        # Use niche-specific platforms if available
        if not platforms and self.client_profile:
            platforms = self.client_profile.platforms
        elif not platforms:
            platforms = ["instagram", "facebook"]  # fallback
        
        # Use niche-specific posting frequency if available
        if not posts_per_day and self.client_profile:
            # Convert weekly frequency to daily (rounded)
            posts_per_day = max(1, round(self.client_profile.posting_frequency / 7))
        elif not posts_per_day:
            posts_per_day = 1  # fallback
        
        # Use content pillars as topics if not provided
        if not topics and self.client_profile and self.client_profile.content_pillars:
            # content_pillars is a list of strings
            if isinstance(self.client_profile.content_pillars, list):
                topics = self.client_profile.content_pillars
            else:
                topics = [pillar.strip() for pillar in self.client_profile.content_pillars.split(',')]
        
        days = 7
        total_posts = len(platforms) * posts_per_day * days
        
        print(f"\n📅 Generating {total_posts} posts for a week...")
        print(f"   Platforms: {', '.join(platforms)}")
        print(f"   Posts per day: {posts_per_day}")
        if topics:
            print(f"   Topics: {', '.join(topics[:3])}...")
        
        requests = []
        
        for day in range(days):
            for platform in platforms:
                for post_num in range(posts_per_day):
                    # Cycle through topics if provided
                    topic = None
                    if topics:
                        topic_index = (day * posts_per_day + post_num) % len(topics)
                        topic = topics[topic_index]
                    
                    request = ContentRequest(
                        content_type="social_post",
                        platform=platform,
                        topic=topic,
                        include_hashtags=platform in ["instagram", "tiktok", "twitter"],
                        include_cta=True,
                        metadata={
                            "day": day + 1,
                            "post_number": post_num + 1
                        }
                    )
                    requests.append(request)
        
        return await self.generate_batch(requests)
    
    # =========================================================================
    # INTEGRATED AGENT METHODS
    # =========================================================================
    
    async def get_content_ideas(
        self,
        niche: Optional[str] = None,
        num_ideas: int = 5,
        platforms: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        themes: Optional[List[str]] = None
    ) -> List[ContentIdea]:
        """
        Get content ideas from Marketing Intelligence Agent.
        
        Args:
            niche: Client's business niche (uses client profile if not provided)
            num_ideas: Number of ideas to generate
            platforms: Target platforms (uses niche platforms if not provided)
            content_types: Content goals (e.g., ["growth", "sales", "engagement"])
                          - "growth" → follower_growth
                          - "sales" → conversions_sales
                          - "engagement" → views_engagement
            themes: Content themes to explore (uses content pillars if not provided)
        
        Returns:
            List of ContentIdea objects with hooks, angles, keywords
        """
        # Use niche from client profile if not provided
        if not niche and self.client_profile:
            niche_value = self.client_profile.niche.value if hasattr(self.client_profile.niche, 'value') else self.client_profile.niche
            niche = niche_value.replace('_', ' ')
        elif not niche:
            niche = "general business"
        
        # Use niche platforms if not provided
        if not platforms and self.client_profile:
            platforms = self.client_profile.platforms
        
        # Use content pillars as themes if not provided
        if not themes and self.client_profile and self.client_profile.content_pillars:
            # content_pillars is a list of strings
            if isinstance(self.client_profile.content_pillars, list):
                themes = self.client_profile.content_pillars
            else:
                themes = [pillar.strip() for pillar in self.client_profile.content_pillars.split(',')]
        
        print(f"\n💡 Requesting {num_ideas} content ideas from Marketing Intelligence Agent...")
        print(f"   Niche: {niche}")
        print(f"   Platforms: {platforms or 'auto-select'}")
        print(f"   Content types: {content_types or 'all'}")
        if themes:
            print(f"   Themes: {', '.join(themes[:3])}...")
        
        # Map content_types to goals
        goal_mapping = {
            "growth": "follower_growth",
            "sales": "conversions_sales",
            "engagement": "views_engagement"
        }
        
        goals = None
        if content_types:
            goals = [goal_mapping.get(ct, ct) for ct in content_types]
        
        ideas = await self.marketing_agent.generate_content_ideas(
            niche=niche,
            num_ideas=num_ideas,
            platforms=platforms,
            goals=goals,
            themes=themes
        )
        
        print(f"✅ Received {len(ideas)} content ideas")
        return ideas
    
    async def generate_from_idea(
        self,
        idea: ContentIdea,
        use_rag: bool = True
    ) -> GeneratedContent:
        """
        Generate content from a ContentIdea object.
        
        Args:
            idea: ContentIdea from Marketing Intelligence Agent
            use_rag: Whether to use RAG for additional context
        
        Returns:
            GeneratedContent ready for posting
        """
        print(f"\n🎨 Generating content from idea: {idea.topic}")
        
        # Map ContentIdea to ContentRequest
        platform_map = {
            "instagram": "instagram",
            "facebook": "facebook",
            "linkedin": "linkedin",
            "twitter": "twitter",
            "tiktok": "tiktok",
            "youtube": "youtube"
        }
        
        platform = platform_map.get(
            idea.recommended_platforms[0] if idea.recommended_platforms else "instagram",
            "instagram"
        )
        
        # Build context from idea
        context = f"""
Angle: {idea.angle}
Hooks to use: {', '.join(idea.hooks[:2]) if idea.hooks else 'None'}
Keywords: {', '.join(idea.keywords[:3]) if idea.keywords else 'None'}
Goal: {idea.goal}
Call to Action: {idea.call_to_action or 'Engage with audience'}

Reasoning: {idea.reasoning}
"""
        
        request = ContentRequest(
            content_type="social_post",
            platform=platform,
            topic=idea.topic,
            context=context,
            include_hashtags=platform in ["instagram", "tiktok"],
            include_cta=True,
            metadata={
                "idea_id": idea.idea_id,
                "priority": idea.priority,
                "estimated_engagement": idea.estimated_engagement
            }
        )
        
        return await self.generate_content(request, use_rag=use_rag)
    
    async def post_content(
        self,
        content: GeneratedContent,
        media_urls: Optional[List[str]] = None,
        scheduled_time: Optional[str] = None
    ) -> Dict:
        """
        Post generated content using Posting Agent.
        
        Args:
            content: GeneratedContent to post
            media_urls: Optional media URLs to attach
            scheduled_time: Optional scheduled time for posting
        
        Returns:
            Posting result dictionary
        """
        print(f"\n📤 Posting content to {content.platform}...")
        
        # Create ContentPost object
        post = ContentPost(
            content=content.content,
            platform=content.platform,
            content_type=content.content_type,
            client_id=self.client_id,
            media_urls=media_urls,
            scheduled_time=scheduled_time
        )
        
        # Post via Posting Agent
        result = await self.posting_agent.post_content(post)
        
        if result.status == "published" or result.status == "success":
            print(f"✅ Successfully posted to {content.platform}")
        elif result.status == "manual_required":
            print(f"📋 Queued for manual posting to {content.platform}")
        else:
            print(f"⚠️ Posting status: {result.status}")
        
        return {
            "status": result.status,
            "platform": result.platform,
            "post_id": result.post_id,
            "error": result.error,
            "posted_at": result.timestamp
        }
    
    async def generate_engagement_reply(
        self,
        message: str,
        sender_id: str = "unknown",
        platform: str = "instagram",
        cross_channel_context: str = "",
    ) -> str:
        """
        Generate engagement reply using Engagement Agent.
        
        Args:
            message: Message/comment to reply to
            sender_id: ID of the sender
            platform: Platform where engagement is happening
            cross_channel_context: Pre-formatted cross-channel history from
                                   CrossChannelMemory.get_context_for_prompt().
                                   Injected into the system prompt so the agent
                                   can maintain continuity across channels.
        
        Returns:
            Generated reply text
        """
        print(f"\n💬 Generating reply for {platform} engagement...")
        
        # respond_to_message signature: (message, client_id, sender_id, thread_id, use_memory, cross_channel_context)
        # Use sender_id as thread_id so per-session conversation memory persists per-user
        reply = self.engagement_agent.respond_to_message(
            message=message,
            client_id=self.client_id,
            sender_id=sender_id,
            thread_id=f"{platform}:{sender_id}",
            use_memory=True,
            cross_channel_context=cross_channel_context,
        )
        
        print(f"✅ Generated reply ({len(reply)} chars)")
        return reply
    
    async def create_and_post_workflow(
        self,
        niche: Optional[str] = None,
        num_posts: int = 1,
        mode: str = "automatic",
        platforms: Optional[List[str]] = None,
        content_types: Optional[List[str]] = None,
        themes: Optional[List[str]] = None,
        media_urls: Optional[List[str]] = None,
        auto_post: bool = True
    ) -> Dict:
        """
        Complete workflow with automatic or manual modes.
        
        Args:
            niche: Client's business niche (uses client profile if not provided)
            num_posts: Number of posts to create
            mode: "automatic" (post right away) or "manual" (review before posting)
            platforms: Target platforms (uses niche platforms if not provided)
            content_types: Content goals (e.g., ["growth", "sales", "engagement"])
                          - "growth" → follower_growth
                          - "sales" → conversions_sales
                          - "engagement" → views_engagement
            themes: Content themes to explore (uses content pillars if not provided)
            media_urls: Optional media to attach
            auto_post: In manual mode, whether to auto-post selected ideas
        
        Returns:
            Dictionary with results and ideas (for manual mode filtering)
        """
        # Use niche from client profile if not provided
        if not niche and self.client_profile:
            niche_value = self.client_profile.niche.value if hasattr(self.client_profile.niche, 'value') else self.client_profile.niche
            niche = niche_value.replace('_', ' ')
        elif not niche:
            niche = "general business"
        
        # Use niche platforms if not provided
        if not platforms and self.client_profile:
            platforms = self.client_profile.platforms
        
        # Use content pillars as themes if not provided
        if not themes and self.client_profile and self.client_profile.content_pillars:
            # content_pillars is a list of strings
            if isinstance(self.client_profile.content_pillars, list):
                themes = self.client_profile.content_pillars
            else:
                themes = [pillar.strip() for pillar in self.client_profile.content_pillars.split(',')]
        
        print(f"\n🚀 Starting {mode.UPPER()} content workflow...")
        print(f"   Niche: {niche}")
        print(f"   Posts: {num_posts}")
        print(f"   Platforms: {platforms or 'auto-select'}")
        print(f"   Content types: {content_types or 'all'}")
        if themes:
            print(f"   Themes: {', '.join(themes[:3])}...")
        
        # Step 1: Get content ideas from Marketing Intelligence Agent
        ideas = await self.get_content_ideas(
            niche=niche,
            num_ideas=num_posts,
            platforms=platforms,
            content_types=content_types,
            themes=themes
        )
        
        results = {
            "mode": mode,
            "total_ideas": len(ideas),
            "ideas": [],
            "posts": []
        }
        
        # For manual mode, return ideas for client review
        if mode == "manual":
            print(f"\n📋 MANUAL MODE: Review ideas below and select which to post")
            print("="*70)
            
            for i, idea in enumerate(ideas, 1):
                # Map goal back to content type for display
                goal_to_type = {
                    "views_engagement": "engagement",
                    "follower_growth": "growth",
                    "conversions_sales": "sales"
                }
                content_type = goal_to_type.get(idea.goal, idea.goal)
                
                idea_info = {
                    "index": i - 1,
                    "topic": idea.topic,
                    "angle": idea.angle,
                    "format": idea.format,
                    "platforms": idea.recommended_platforms,
                    "content_type": content_type,
                    "hooks": idea.hooks[:1] if idea.hooks else [],
                    "priority": idea.priority,
                    "idea_object": idea
                }
                results["ideas"].append(idea_info)
                
                print(f"\n{i}. {idea.topic}")
                print(f"   Angle: {idea.angle}")
                print(f"   Format: {idea.format}")
                print(f"   Platforms: {', '.join(idea.recommended_platforms)}")
                print(f"   Content Type: {content_type}")
                print(f"   Priority: {idea.priority}")
                print(f"   Hook: {idea.hooks[0] if idea.hooks else 'N/A'}")
            
            print("\n\n💡 In manual mode, use these indices to select ideas:")
            print("   selected = [ideas[0], ideas[2], ideas[4]]  # Your selections")
            print("   for idea in selected: await agent.generate_from_idea(idea)\n")
            
            return results
        
        # AUTOMATIC MODE
        else:
            print(f"\n🤖 AUTOMATIC MODE: Generating and posting all ideas...")
            
            # Step 2: Generate and post each idea
            for i, idea in enumerate(ideas, 1):
                print(f"\n{'='*60}")
                print(f"Processing Idea {i}/{len(ideas)}: {idea.topic}")
                print(f"{'='*60}")
                
                try:
                    # Generate content from idea
                    content = await self.generate_from_idea(idea)
                    
                    # Post content
                    post_result = await self.post_content(
                        content=content,
                        media_urls=media_urls
                    )
                    
                    post_info = {
                        "idea": idea.topic,
                        "content": content.content,
                        "platform": content.platform,
                        "posting_result": post_result
                    }
                    results["posts"].append(post_info)
                    
                except Exception as e:
                    print(f"❌ Error processing idea {i}: {e}")
                    results["posts"].append({
                        "idea": idea.topic,
                        "error": str(e)
                    })
            
            print(f"\n✅ Workflow complete: {len(results['posts'])} posts processed")
            return results
    
    # =========================================================================
    # CLIENT NICHE MANAGEMENT
    # =========================================================================
    
    def setup_client_niche(
        self,
        client_name: str,
        niche: str,
        business_description: Optional[str] = None
    ) -> ClientProfile:
        """
        Set up a new client with their chosen niche.
        
        Args:
            client_name: Client's business name
            niche: Client's business niche (e.g., "travel_agency", "fitness_coaching")
            business_description: Optional description for voice matching
        
        Returns:
            Created ClientProfile
        """
        print(f"\n🎯 Setting up client: {client_name}")
        print(f"   Niche: {niche}")
        
        if not business_description:
            business_description = f"A {niche.replace('_', ' ')} business"
        
        # Create client profile
        profile = self.profile_manager.create_client_profile(
            client_id=self.client_id,
            client_name=client_name,
            niche=niche,
            business_description=business_description
        )
        
        # Update this agent's profile reference
        self.client_profile = profile
        
        print(f"✅ Client profile created!")
        print(f"   Platforms: {', '.join(profile.platforms)}")
        print(f"   Posting Frequency: {profile.posting_frequency}/week")
        print(f"   Tone: {profile.tone}")
        print(f"   Content Pillars: {profile.content_pillars}")
        
        return profile
    
    def get_available_niches(self) -> Dict[str, List[str]]:
        """
        Get all available niches organized by category.
        
        Returns:
            Dictionary of categories and their niches
        """
        from agents.client_profile_manager import ClientNiche
        
        categories = {
            "Business & Professional": [],
            "Health & Wellness": [],
            "Creative & Entertainment": [],
            "E-commerce & Retail": [],
            "Travel & Hospitality": [],
            "Education & Training": [],
            "Technology & SaaS": [],
            "Lifestyle & Personal": [],
            "Other": []
        }
        
        # Map niches to categories
        category_mapping = {
            "Business & Professional": [
                "business_coaching", "executive_coaching", "career_coaching",
                "consulting", "accounting", "legal_services", "real_estate",
                "insurance", "financial_advisor"
            ],
            "Health & Wellness": [
                "fitness_coaching", "personal_training", "yoga_instructor",
                "nutrition_coaching", "mental_health", "wellness_brand",
                "medical_practice", "dental_practice"
            ],
            "Creative & Entertainment": [
                "content_creator", "influencer", "photographer", "videographer",
                "musician", "artist", "writer", "podcaster"
            ],
            "E-commerce & Retail": [
                "ecommerce_fashion", "ecommerce_beauty", "ecommerce_tech",
                "ecommerce_home", "dropshipping", "handmade_products"
            ],
            "Travel & Hospitality": [
                "travel_agency", "hotel", "restaurant", "cafe",
                "event_planning", "tourism"
            ],
            "Education & Training": [
                "online_courses", "tutoring", "language_teacher",
                "skill_training", "educational_content"
            ],
            "Technology & SaaS": [
                "saas_b2b", "saas_b2c", "app_developer",
                "tech_support", "digital_agency"
            ],
            "Lifestyle & Personal": [
                "lifestyle_blogger", "parenting", "dating_coach",
                "relationship_coach", "motivational_speaker", "life_coach"
            ],
            "Other": [
                "nonprofit", "local_business", "franchise",
                "automotive", "pet_services", "home_services"
            ]
        }
        
        # Fill categories
        for category, niche_list in category_mapping.items():
            categories[category] = niche_list
        
        return categories

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_content_agent():
        """Test the Content Creation Agent with integrated workflow."""
        print("\n🧪 Testing Content Creation Agent with Integrated Agents...\n")
        
        agent = ContentCreationAgent(client_id="demo_client")
        
        # Add some test knowledge
        agent.rag.add_knowledge(
            text="We offer life coaching for executives focused on leadership, productivity, and work-life balance.",
            client_id="demo_client"
        )
        
        # Test 1: Get content ideas from Marketing Intelligence Agent
        print("\n=== TEST 1: Get Content Ideas ===")
        ideas = await agent.get_content_ideas(
            niche="life coaching for executives",
            num_ideas=2,
            platforms=["instagram", "linkedin"],
            themes=["productivity", "leadership"]
        )
        
        for i, idea in enumerate(ideas, 1):
            print(f"\n💡 IDEA {i}: {idea.topic}")
            print(f"   Angle: {idea.angle}")
            print(f"   Format: {idea.format}")
            print(f"   Platforms: {', '.join(idea.recommended_platforms)}")
            print(f"   Hooks: {idea.hooks[0] if idea.hooks else 'N/A'}")
        
        # Test 2: Generate content from an idea
        print("\n\n=== TEST 2: Generate Content from Idea ===")
        if ideas:
            content = await agent.generate_from_idea(ideas[0])
            print("\n📱 GENERATED CONTENT:")
            print("="*60)
            print(content.content)
            print("="*60)
            print(f"Stats: {content.word_count} words, {content.char_count} chars")
        
        # Test 3: Generate engagement reply
        print("\n\n=== TEST 3: Generate Engagement Reply ===")
        comment = "This is exactly what I needed! How can I learn more about your coaching programs?"
        reply = await agent.generate_engagement_reply(
            message=comment,
            sender_id="user_123",
            platform="instagram"
        )
        print("\n💬 COMMENT:")
        print(f"   {comment}")
        print("\n↩️  GENERATED REPLY:")
        print(f"   {reply}")
        
        # Test 4: Complete workflow (ideas → generate → queue for posting)
        print("\n\n=== TEST 4: Complete Workflow (without actual posting) ===")
        print("Note: Posting will queue for manual posting since APIs may not be configured")
        
        # For demo, we'll just show the workflow steps without actual posting
        workflow_ideas = await agent.get_content_ideas(
            niche="life coaching for executives",
            num_ideas=1,
            platforms=["instagram"]
        )
        
        if workflow_ideas:
            content = await agent.generate_from_idea(workflow_ideas[0])
            print(f"\n✅ Generated content for: {workflow_ideas[0].topic}")
            print(f"   Platform: {content.platform}")
            print(f"   Length: {content.char_count} chars")
            print(f"\n   Content preview: {content.content[:100]}...")
            
            # Note: Uncomment to actually post (requires API credentials)
            # post_result = await agent.post_content(content)
            # print(f"\n📤 Posting result: {post_result}")
        
        print("\n\n✅ All tests complete!")
        print("\n📋 Available workflow methods:")
        print("   - get_content_ideas() - Get ideas from Marketing Intelligence Agent")
        print("   - generate_from_idea() - Generate content from ContentIdea")
        print("   - post_content() - Post via Posting Agent")
        print("   - generate_engagement_reply() - Generate replies via Engagement Agent")
        print("   - create_and_post_workflow() - Complete end-to-end workflow")
    
    # Run tests
    asyncio.run(test_content_agent())
