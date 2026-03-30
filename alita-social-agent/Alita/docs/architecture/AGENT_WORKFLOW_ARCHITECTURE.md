# Alita Agent Workflow Architecture

## Current Implementation ✅

### For YouTube Short Video Generation:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT REQUEST                                │
│               "I want a YouTube Short video"                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR LAYER                                 │
│              (generate_alita_video.py)                               │
│                                                                       │
│  Coordinates all agents and manages the workflow                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
         ┌─────────────────┴─────────────────┐
         │                                   │
         ▼                                   ▼
┌────────────────────┐           ┌────────────────────┐
│  CONTENT AGENT     │           │  STYLE LOADER      │
│                    │           │                    │
│ • Generate ideas   │           │ • Select template  │
│ • Create hooks     │           │ • Get audio specs  │
│ • Write CTA        │           │ • Get visual style │
└────────┬───────────┘           └─────────┬──────────┘
         │                                  │
         └──────────────┬───────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  CLAUDE AI      │
              │                 │
              │ • Write script  │
              │ • Optimize text │
              └────────┬────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │  VIDEO GENERATOR AGENT      │
         │  (FacelessGenerator)        │
         │                             │
         │ • Generate voiceover        │
         │ • Get stock footage/images  │
         │ • Assemble video (FFmpeg)   │
         │ • Add captions              │
         │ • Mix audio                 │
         └──────────────┬──────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │   FINAL VIDEO   │
              │  (MP4 file)     │
              └─────────────────┘
```

**Current Flow Breakdown:**

1. **Orchestrator** (`generate_alita_video.py`) receives request
2. **Content Agent** generates topic ideas, hooks, CTAs
3. **Style Loader** retrieves production templates (fonts, music, voice)
4. **Claude AI** writes the video script based on content idea
5. **Video Generator** creates the actual video file
6. **Output**: Video file ready for posting

**Missing:** Publishing/Posting automation (manual step)

---

## Your Proposed Architecture 🤔

### What You're Thinking:

```
CLIENT → Content Agent → Video Generator → Marketing Agent → Publishing Agent
```

**Issues with this flow:**
- ❌ Marketing Agent shouldn't be called by Video Generator
- ❌ Linear flow doesn't match actual dependencies
- ❌ Video Generator doesn't need marketing input

---

## Recommended Architecture ✅

### Complete End-to-End Workflow:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CLIENT REQUEST                                   │
│     "Create and post a YouTube Short about AI automation"            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  MAIN ORCHESTRATOR                                   │
│                  (main.py / webhook)                                 │
│                                                                       │
│  Coordinates: Content → Production → Marketing → Publishing          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  CONTENT   │  │   STYLE    │  │  MARKETING │
  │  AGENT     │  │  LOADER    │  │  INTEL     │
  │            │  │            │  │  AGENT     │
  │ Generate   │  │ Templates  │  │            │
  │ ideas,     │  │ for        │  │ Analyze    │
  │ hooks,     │  │ platform   │  │ audience,  │
  │ topics     │  │            │  │ timing,    │
  └─────┬──────┘  └─────┬──────┘  │ hashtags   │
        │               │          └─────┬──────┘
        └───────┬───────┘                │
                │                        │
                ▼                        │
       ┌─────────────────┐               │
       │  SCRIPT         │               │
       │  GENERATION     │               │
       │  (Claude AI)    │               │
       └────────┬────────┘               │
                │                        │
                ▼                        │
    ┌────────────────────────┐           │
    │  VIDEO GENERATOR       │           │
    │  (FacelessGenerator)   │           │
    │                        │           │
    │  • Voiceover           │           │
    │  • Visuals (tier)      │           │
    │  • Assembly            │           │
    │  • Captions            │           │
    └────────┬───────────────┘           │
             │                           │
             ▼                           │
    ┌─────────────────┐                  │
    │  FINAL VIDEO    │                  │
    │  (MP4 ready)    │                  │
    └────────┬────────┘                  │
             │                           │
             └────────┬──────────────────┘
                      │
                      ▼
         ┌─────────────────────────┐
         │   POSTING AGENT         │
         │                         │
         │  Uses marketing data:   │
         │  • Caption from script  │
         │  • Hashtags from intel  │
         │  • Optimal post time    │
         │                         │
         │  Posts to:              │
         │  • YouTube (Direct API) │
         │  • TikTok (Late API)    │
         │  • Instagram (Meta API) │
         └─────────────────────────┘
```

---

## Corrected Workflow Explanation 📋

### For a YouTube Short Request:

**Phase 1: Planning & Strategy**
1. **Content Agent** generates content ideas
2. **Marketing Intelligence Agent** analyzes:
   - Best posting time for audience
   - Trending topics in niche
   - Optimal hashtags
   - Competitor analysis

**Phase 2: Production**
3. **Style Loader** selects production template
4. **Claude AI** writes optimized script
5. **Video Generator** creates video:
   - Tier selection (stock/images/animation)
   - Voiceover generation
   - Visual assembly
   - Caption rendering

**Phase 3: Publishing**
6. **Posting Agent** publishes to platform:
   - Uses video file from generator
   - Uses caption/hashtags from marketing
   - Posts via appropriate API (YouTube Direct)
   - Tracks posting success

---

## Key Architectural Principles ✅

### 1. Separation of Concerns
- **Content Agent** = Ideas & topics (WHAT to say)
- **Video Generator** = Production (HOW to present it)
- **Marketing Agent** = Strategy (WHEN/WHERE to post, hashtags)
- **Posting Agent** = Distribution (PUBLISH it)

### 2. Data Flow (Not Calling Pattern)
```
Content Agent ─────┐
                   ├──> Script ──> Video Generator ──> Video File ─┐
Marketing Agent ───┘                                                ├──> Posting Agent
                                                                    │
                        Caption + Hashtags + Timing ────────────────┘
```

Agents **don't call each other**. The orchestrator calls them in sequence and passes data.

### 3. Orchestrator Pattern
```python
# In main.py or orchestrator
async def create_and_post_video(request):
    # 1. Get content
    content = await content_agent.get_ideas(...)
    
    # 2. Get marketing intel (parallel with content)
    marketing = await marketing_agent.analyze(...)
    
    # 3. Generate script
    script = await generate_script(content)
    
    # 4. Create video
    video = await video_generator.generate(script, tier=request.tier)
    
    # 5. Post with marketing data
    result = await posting_agent.post(
        video=video,
        caption=script,
        hashtags=marketing.hashtags,
        scheduled_time=marketing.optimal_time
    )
    
    return result
```

---

## What Needs to Be Built 🔨

### Currently Missing:

1. **Main Orchestrator** (`main.py` is empty)
   - Needs to coordinate all agents
   - Handle client requests end-to-end
   - Manage workflow state

2. **Marketing Intelligence Integration**
   - Currently exists but not connected
   - Should provide hashtags, timing, trends
   - Runs parallel to content generation

3. **Posting Automation**
   - Posting Agent exists but not integrated
   - Needs to connect video output → platform APIs
   - Handle success/failure tracking

### Quick Fix - Add to generate_alita_video.py:

```python
# At the end of generate_faceless_video_for_business():

# Optional: Auto-post to platform
if auto_post:
    from agents.posting_agent import PostingAgent, ContentPost
    
    posting_agent = PostingAgent(client_id=client_id)
    
    post_result = await posting_agent.post_content(
        ContentPost(
            content=script,  # Caption is the script
            platform=platform.replace("_", ""),
            content_type="video",
            client_id=client_id,
            media_urls=[video_path]
        )
    )
    
    if post_result.success:
        print(f"✅ Posted to {platform}: {post_result.post_id}")
    else:
        print(f"❌ Posting failed: {post_result.error}")
```

---

## Summary 🎯

**Your Understanding:**
> Content Agent → Video Generator → Marketing Agent → Posting Agent

**Actual Architecture:**
> Orchestrator coordinates:
> - Content Agent (ideas) + Marketing Agent (strategy) → Data
> - Data → Script Generation (Claude)
> - Script → Video Generator (production)
> - Video + Marketing Data → Posting Agent (distribution)

**Key Difference:**
- Agents don't call each other
- Orchestrator calls them and passes data between them
- Marketing Agent provides data TO posting, not called BY video generator
- Linear flow, parallel data gathering

**What Makes Sense:**
✅ Content Agent generates ideas
✅ Video Generator makes video (with tier selection)
✅ Posting Agent handles distribution
❌ Video Generator calling Marketing Agent (unnecessary coupling)
✅ Orchestrator managing the whole flow
