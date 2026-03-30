# Faceless Video Generator - Script Generation Architecture

## Overview
The Faceless Video Generator now handles its own script generation internally, separate from the Content Creation Agent.

## Why This Change?

### Problem with External Script Generation
When external agents (Marketing/Content) wrote video scripts:
- ❌ No awareness of 2-3 sentence grouping requirement
- ❌ No understanding of audio-driven timing constraints  
- ❌ Scripts created awkward scene breaks and transitions
- ❌ No feedback loop between script structure and video quality

### Solution: Internal Script Generation
Faceless Generator now owns the complete video creation pipeline:
- ✅ Full control over script structure optimized for video
- ✅ Enforces 2-3 sentence grouping from the start
- ✅ Previews scene breaks BEFORE generating voiceover
- ✅ Tight coupling between script requirements and video output
- ✅ Platform-specific optimization (duration, style, pacing)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ MARKETING INTELLIGENCE AGENT                                │
│ • Generates content ideas                                   │
│ • Provides topics, angles, hooks                            │
│ • Strategic planning                                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ├──► content_type = "post/caption/thread"
                 │    ┌──────────────────────────────────────┐
                 │    │ CONTENT CREATION AGENT               │
                 │    │ • 86 prompt templates                │
                 │    │ • Text-based content                 │
                 │    │ • Instagram captions                 │
                 │    │ • Twitter threads                    │
                 │    │ • Blog posts                         │
                 │    │ • Email newsletters                  │
                 │    └──────────────────────────────────────┘
                 │
                 └──► content_type = "video"
                      ┌──────────────────────────────────────┐
                      │ FACELESS VIDEO GENERATOR             │
                      │ 1. generate_script()                 │
                      │    • Topic → Optimized script        │
                      │    • Hook + Body + CTA structure     │
                      │    • 2-3 sentence grouping           │
                      │    • Platform-specific duration      │
                      │ 2. generate_video()                  │
                      │    • Script → Visual production      │
                      │    • Voiceover with timing           │
                      │    • Scene transitions               │
                      │    • 3-tier system                   │
                      └──────────────────────────────────────┘
```

## New Workflow

### Option A: One-Step (Topic → Video)
```python
from agents.faceless_generator import FacelessGenerator, Platform, VideoTier

gen = FacelessGenerator(client_id="demo")

# Provide topic, get complete video
result = await gen.generate_video_from_topic(
    topic="Why 90% of startups fail",
    platform=Platform.INSTAGRAM_REEL,
    tier=VideoTier.STOCK_VIDEO
)
# Internally: generate_script() → generate_video()
```

### Option B: Two-Step (Script Review)
```python
# Step 1: Generate optimized script
script_result = await gen.generate_script(
    topic="Why 90% of startups fail",
    platform=Platform.INSTAGRAM_REEL,
    duration_target=45,
    style="engaging, educational"
)

# Review/edit script
print(script_result['script'])
print(f"Scenes: {script_result['scene_count']}")
print(f"Duration: ~{script_result['estimated_duration']}s")

# Step 2: Generate video with approved script
video_result = await gen.generate_video(
    script=script_result['script'],
    tier=VideoTier.STOCK_VIDEO,
    platform=Platform.INSTAGRAM_REEL
)
```

## Script Generation Features

### Input Parameters
```python
await gen.generate_script(
    topic: str,                        # Main topic/angle
    platform: Platform,                # Target platform
    duration_target: int = 60,         # Target seconds (30-90)
    style: str = "engaging, educational",  # Script tone
    include_hook: bool = True,         # Add attention hook
    include_cta: bool = True,          # Add call-to-action
    niche: Optional[str] = None        # Optional niche context
)
```

### Output Format
```python
{
    "script": str,              # Full script text
    "scenes": List[str],        # Script broken into scenes
    "estimated_duration": int,  # Estimated seconds
    "scene_count": int,         # Number of scenes (7-10 ideal)
    "word_count": int,          # Total words
    "hook": str,                # First scene (attention grab)
    "cta": str                  # Last scene (call-to-action)
}
```

### Script Structure
1. **Hook (Scene 1)**: 2-3 sentences, grabs attention in 3 seconds
   - Shocking statistic
   - Bold claim  
   - Provocative question

2. **Body (Scenes 2-6)**: 2-3 sentences each, delivers value
   - Problem explanation
   - Solution steps
   - Educational content
   - Story progression

3. **CTA (Scene 7)**: 2-3 sentences, clear action
   - What viewer should do
   - Follow/comment/share
   - Value proposition

### Platform-Specific Optimization

| Platform | Min | Max | Ideal | Style |
|----------|-----|-----|-------|-------|
| Instagram Reel | 15s | 90s | 45s | Short hooks, fast pacing |
| TikTok | 15s | 60s | 30s | Immediate hook, energetic |
| YouTube Short | 15s | 60s | 45s | Educational, storytelling |
| YouTube | 30s | 600s | 120s | Detailed, in-depth |

## Integration Examples

### From Marketing Agent
```python
from agents.marketing_intelligence_agent import MarketingAgent
from agents.faceless_generator import FacelessGenerator, Platform, VideoTier

# Marketing agent generates idea
marketing = MarketingAgent(client_id="demo")
ideas = await marketing.generate_content_ideas(
    niche="digital marketing",
    num_ideas=5
)

video_idea = [i for i in ideas if i.content_type == "video"][0]

# Faceless generator creates optimized script + video
gen = FacelessGenerator(client_id="demo")
script = await gen.generate_script(
    topic=video_idea.angle,
    platform=video_idea.platform,
    niche=video_idea.niche
)

video = await gen.generate_video(
    script=script['script'],
    tier=VideoTier.STOCK_VIDEO,
    platform=video_idea.platform
)
```

### From CLI
```python
# Option 1: AI-generate script
choice = "1"  # User selects AI generation
topic = input("Video topic: ")

script_result = await gen.generate_script(
    topic=topic,
    platform=Platform.INSTAGRAM_REEL
)

# Option 2: User provides script
choice = "2"
script = input("Enter your script: ")

# Both paths converge to video generation
video = await gen.generate_video(
    script=script if choice == "2" else script_result['script'],
    tier=VideoTier.STOCK_VIDEO
)
```

## Quality Improvements

### Before (External Scripting)
```
Script: "Here are 5 tips for social media success. First, post consistently..."
↓
Issues:
- Too many sentences per scene (5+ sentences)
- Awkward visual breaks mid-thought
- No hook structure
- Duration unpredictable
```

### After (Internal Scripting)
```
Hook: 95% of businesses quit social media within 6 months.
They blame the algorithm. But that's not the real reason.
---
Body: Most people post random content without strategy.
They expect results overnight. When nothing happens, they quit.
---
CTA: Stop posting random content and start serving your audience.
Follow for proven strategies that actually work!
↓
Results:
✅ Perfect 2-3 sentence grouping
✅ Smooth visual transitions
✅ Clear hook-body-CTA structure
✅ Predictable duration (±5s)
```

## Key Principles

1. **Separation of Concerns**
   - Content Agent = text posts (captions, threads, blogs)
   - Faceless Generator = video scripts + production

2. **Domain Expertise**
   - Video scripts have unique constraints (timing, scene breaks, audio sync)
   - Faceless Generator understands these constraints
   - Content Agent doesn't need to

3. **Quality First**
   - Script writer knows the medium
   - Optimizes for video-specific requirements
   - Tighter feedback loop

4. **Cost Optimization**
   - Cheap script generation ($0.01-0.03 per script)
   - Client can review/iterate before expensive video production
   - No wasted video generation on bad scripts

## Testing

Run integration tests:
```bash
python test_faceless_integration.py
```

This demonstrates:
- Script generation with various topics
- Integration with Marketing Agent ideas
- Separation from Content Agent
- Complete workflow (idea → script → video)

## Migration Notes

**Old Code (external script):**
```python
# DON'T DO THIS ANYMORE
script = await content_agent.generate_content(
    content_type="video_script",
    topic="startup tips"
)
video = await faceless_gen.generate_video(script=script)
```

**New Code (internal script):**
```python
# DO THIS
script = await faceless_gen.generate_script(
    topic="startup tips",
    platform=Platform.INSTAGRAM_REEL
)
video = await faceless_gen.generate_video(
    script=script['script'],
    tier=VideoTier.STOCK_VIDEO
)
```

## Summary

✅ **Faceless Generator** = Video scripts + video production  
✅ **Content Agent** = Text posts (captions, threads, blogs)  
✅ **Marketing Agent** = Strategic ideas for both  

This architecture ensures video scripts are optimized for the medium while maintaining clean separation of concerns across the agent ecosystem.
