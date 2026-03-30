# Marketing Intelligence Agent - Usage Guide

## 🧠 Overview

The Marketing Intelligence Agent is the strategic brain of Alita. It generates content ideas and strategies using **real-time intelligence** from multiple sources.

---

## 🔧 Setup

### 1. API Keys Required

Add these to your `.env` file:

```env
# Marketing Intelligence APIs
NEWSAPI_KEY=your_newsapi_key_here
YOUTUBE_API_KEY=your_youtube_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

# Meta Graph API (you already have this)
INSTAGRAM_ACCESS_TOKEN=your_meta_access_token
```

### 2. Free Tier Limits

| API | Free Limit | Upgrade Cost |
|-----|------------|--------------|
| **NewsAPI** | 100 requests/day | $449/month (unlimited) |
| **YouTube Data API** | 10,000 quota units/day (~1,000 searches) | $0.0002/query after quota |
| **Tavily** | 1,000 searches/month | $20/month (10K searches) |
| **Meta Graph API** | Unlimited for owned pages | Free |

---

## 🚀 Usage Examples

### Basic: Generate Content Ideas

```python
from agents import MarketingIntelligenceAgent

# Initialize agent
agent = MarketingIntelligenceAgent(client_id="demo_client")

# Generate 5 content ideas
ideas = await agent.generate_content_ideas(
    niche="AI automation for small businesses",
    num_ideas=5,
    platforms=["instagram", "linkedin", "tiktok"]
)

# Access ideas
for idea in ideas:
    print(f"💡 {idea.topic}")
    print(f"   Angle: {idea.angle}")
    print(f"   Hooks: {idea.hooks}")
    print(f"   Platforms: {idea.recommended_platforms}")
```

### Advanced: Generate Weekly Strategy

```python
# Generate full weekly content strategy
strategy = await agent.generate_weekly_strategy(
    niche="AI automation for small businesses",
    posts_per_week=7,
    platforms=["instagram", "linkedin"],
    themes=["productivity tips", "AI myths", "success stories"]
)

# Access strategy details
print(f"📊 Content Mix: {strategy.content_mix}")
print(f"📅 {len(strategy.ideas)} ideas for {strategy.period}")

# Get ideas for specific days
monday_idea = strategy.ideas[0]
tuesday_idea = strategy.ideas[1]
```

### Campaign: Generate Campaign Ideas

```python
# Generate ideas for a specific campaign
campaign_ideas = await agent.generate_campaign_ideas(
    niche="AI automation",
    campaign_goal="Black Friday Sale - 50% off",
    duration_days=7,
    platforms=["instagram", "facebook", "tiktok"]
)

# All ideas will be optimized for conversions
for idea in campaign_ideas:
    print(f"💰 {idea.topic} | CTA: {idea.call_to_action}")
```

---

## 📡 Intelligence Sources

### 1. NewsAPI - Trending News

```python
# Get news intelligence
news = await agent.get_news_intelligence(
    niche="AI automation",
    max_results=5
)

# Returns:
# [
#   {
#     "title": "10 AI executives predict 2026...",
#     "description": "Industry leaders share insights...",
#     "source": "TechCrunch",
#     "url": "https://...",
#     "published": "2026-02-01T10:00:00Z"
#   }
# ]
```

### 2. YouTube Data API - Trending Videos

```python
# Get YouTube trends
videos = await agent.get_youtube_trends(
    keywords=["AI automation", "productivity hacks"],
    max_results=10
)

# Returns trending videos with titles, channels, descriptions
```

### 3. Tavily - Competitive Intelligence

```python
# Get competitive research
intel = await agent.get_competitive_intel(
    niche="AI automation",
    query="top performing posts in AI automation niche",
    max_results=5
)

# Returns competitor content, best practices, market gaps
```

### 4. Meta Graph API - Client Performance

```python
# Get client's own performance data
insights = await agent.get_meta_insights(
    page_id="673651702495432"  # Your Facebook Page ID
)

# Returns:
# {
#   "top_posts": [
#     {"message": "...", "engagement": 1250, "impressions": 5600}
#   ],
#   "total_posts_analyzed": 25
# }
```

### 5. Gather All Intelligence (Recommended)

```python
# Get intelligence from all sources in parallel
intelligence = await agent.gather_all_intelligence(
    niche="AI automation",
    keywords=["productivity", "AI tools", "automation"]
)

# Returns:
# {
#   "niche": "AI automation",
#   "news": [...],
#   "youtube_trends": [...],
#   "timestamp": "2026-02-01T12:00:00"
# }
```

---

## 🎯 Content Idea Output Format

Each `ContentIdea` contains:

```python
ContentIdea(
    idea_id="idea_demo_client_20260201_1",
    topic="5 AI Tools Under $50/Month",
    angle="Budget-friendly alternatives to expensive enterprise tools",
    format="carousel",  # post, reel, story, carousel, video, article, thread
    goal="conversions_sales",  # views_engagement, follower_growth, conversions_sales
    recommended_platforms=["instagram", "linkedin"],
    hooks=[
        "You don't need a $10K/month budget to use AI",
        "These 5 tools cost less than your Netflix subscription"
    ],
    keywords=["affordableAI", "smallbusinesstools", "budgetautomation"],
    priority="high",  # high, medium, low
    reasoning="Budget constraints are the #1 barrier for small businesses",
    estimated_engagement="high",
    best_posting_time="12:00 PM",
    media_type="image",
    call_to_action="Click link in bio for full tool breakdown",
    created_at="2026-02-01T12:00:00"
)
```

### Convert to Content Request

```python
# Feed into Content Creation Agent
content_request = idea.to_content_request()

# Returns:
# {
#   "platform": "instagram",
#   "content_type": "carousel",
#   "topic": "5 AI Tools Under $50/Month: Budget-friendly alternatives...",
#   "goal": "conversions_sales",
#   "hooks": ["You don't need a $10K/month budget...", ...],
#   "keywords": ["affordableAI", "smallbusinesstools", ...]
# }
```

---

## 💡 Intelligence-Powered Ideas

The agent automatically uses real-time intelligence to generate better ideas:

### Example: AI Automation Niche

**Without Intelligence:**
```
Topic: "5 AI Tools for Productivity"
Angle: Generic list of AI tools
Hooks: Standard productivity hooks
```

**With Intelligence (NewsAPI + YouTube):**
```
Topic: "AI Predictions for Small Business Owners in 2026"
Angle: Break down executive AI predictions into actionable steps
Hooks: "10 AI executives predict 2026... Here's what YOUR business needs to do TODAY"
Source: Based on actual news article from TechCrunch
```

### Real Test Results

```
📰 NewsAPI: Found 5 articles about AI automation
🎥 YouTube: Found 53 trending videos
💡 Generated Ideas:
   1. AI Predictions for 2026 (based on actual news)
   2. 5 AI Myths Killing Productivity (trending YouTube topic)
   3. Which AI Future Will Your Business Live In? (WEF article)
   4. How a Bakery Owner Saved 15 Hours/Week (success story pattern)
   5. The AI Power Stack Under $100/Month (news-inspired)
```

---

## 🔄 Integration with Other Agents

### 1. Content Creation Agent

```python
# Generate ideas
ideas = await marketing_agent.generate_content_ideas(niche="AI automation", num_ideas=5)

# Feed to Content Creation Agent
from content_agent import ContentCreationAgent
content_agent = ContentCreationAgent(client_id="demo_client")

for idea in ideas:
    request = idea.to_content_request()
    content = await content_agent.generate_content(**request)
    print(content)
```

### 2. Posting Agent

```python
# Generate weekly strategy
strategy = await marketing_agent.generate_weekly_strategy(niche="AI automation")

# Schedule posts for the week
from agents.posting_agent import PostingAgent
posting_agent = PostingAgent(client_id="demo_client")

for day, idea in enumerate(strategy.ideas):
    scheduled_time = datetime.now() + timedelta(days=day)
    # Convert idea to content, then post
```

### 3. RAG Knowledge System

```python
# Intelligence automatically feeds into RAG
intelligence = await agent.gather_all_intelligence(niche="AI automation", keywords=["productivity"])

# Add to knowledge base for future use
from agents.rag_system import RAGSystem
rag = RAGSystem()

for article in intelligence["news"]:
    rag.add_knowledge(
        text=f"{article['title']}: {article['description']}",
        client_id="demo_client",
        metadata={"source": "news", "date": article["published"]}
    )
```

---

## 📊 Cost Optimization Tips

### 1. Start with Free Tier

- NewsAPI: 100/day is plenty for development
- YouTube: 10K units/day = ~1,000 searches
- Tavily: 1,000/month free
- **Total: $0/month**

### 2. Upgrade When Needed

- **10 clients**: NewsAPI Business ($449/mo) for unlimited news
- **100+ clients**: Add SerpAPI ($250/mo) for search trends
- **Enterprise**: Custom pricing for all services

### 3. Cache Intelligence

```python
# Don't fetch news every time - cache for 24 hours
intelligence = await agent.gather_all_intelligence(niche="AI automation", keywords=["productivity"])

# Store in RAG or database
# Reuse for all content generation that day
```

---

## 🎯 Best Practices

### 1. Match Intelligence to Niche

```python
# B2B SaaS → LinkedIn + industry news
ideas = await agent.generate_content_ideas(
    niche="B2B SaaS marketing",
    platforms=["linkedin"],
    themes=["industry trends", "thought leadership"]
)

# Ecommerce → Instagram + trending products
ideas = await agent.generate_content_ideas(
    niche="sustainable fashion",
    platforms=["instagram", "tiktok"],
    themes=["product showcases", "behind the scenes"]
)
```

### 2. Use Themes to Guide Intelligence

```python
# Specific themes = better intelligence
ideas = await agent.generate_content_ideas(
    niche="AI automation",
    themes=["productivity tips", "AI myths debunked", "success stories"],
    num_ideas=3
)
# Result: Ideas directly tied to your themes + current trends
```

### 3. Leverage Campaign Mode

```python
# Campaign = conversion-focused + urgency
campaign = await agent.generate_campaign_ideas(
    niche="online courses",
    campaign_goal="New Year Sale - 40% off",
    duration_days=5
)
# All ideas will have CTAs, urgency, conversion focus
```

---

## 🚨 Troubleshooting

### "NewsAPI not configured"

- Check `.env` has `NEWSAPI_KEY=your_key_here`
- Verify key at https://newsapi.org/account
- Free tier: 100 requests/day

### "YouTube API quota exceeded"

- Default: 10,000 units/day
- Each search = ~10 units
- Reduce `max_results` parameter
- Cache results to reduce API calls

### "Tavily API error"

- Check `.env` has `TAVILY_API_KEY=your_key_here`
- Free tier: 1,000 searches/month
- Optional - agent works without it

### Intelligence not showing in ideas

- Agent needs at least 1 API configured
- Check console for "⚠️ API not configured" warnings
- Verify API keys are correct

---

## 📈 What's Next?

### Phase 1: Algorithm Intelligence (Deep Research)
Run these deep research queries and add to RAG:
1. "Instagram algorithm 2025: ranking factors and engagement signals"
2. "TikTok viral video patterns and formula breakdown"
3. "LinkedIn B2B content strategy: what posts perform best"
4. "Optimal posting times by platform and industry"

### Phase 2: Strategy Pattern Library
Add proven frameworks to RAG:
- Content pillar strategies (40% educational, 30% entertaining, etc.)
- Viral content patterns (hook formulas, storytelling arcs)
- Growth hacking playbooks (hashtag strategies, collaboration tactics)

### Phase 3: Industry Benchmarks
- Average engagement rates by industry
- Best-performing content types per niche
- Platform-specific performance metrics

---

## 🎓 Summary

**The Marketing Intelligence Agent now:**
- ✅ Fetches real-time news with NewsAPI
- ✅ Analyzes YouTube trends with YouTube Data API
- ✅ Performs competitive research with Tavily
- ✅ Pulls client performance from Meta Graph API
- ✅ Generates ideas based on actual trending topics
- ✅ Outputs structured ContentIdea objects
- ✅ Integrates with Content Creation + Posting Agents

**Cost: $0/month (free tiers) → $449/month (production)**

**Result: Content ideas that are current, relevant, and data-backed instead of generic.**
