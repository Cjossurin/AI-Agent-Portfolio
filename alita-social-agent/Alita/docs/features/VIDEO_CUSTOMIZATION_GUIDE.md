# Video Customization Guide

## Overview
The faceless video generator automatically configures captions and background music based on the production style template. You can also customize the voice used in your videos.

## ✨ Automatic Features (Template-Driven)

### Captions/Subtitles
- **Automatic Detection**: The system reads the style template's `subtitle_coverage` setting
- **When Enabled**: Template specifies "100% of speech" or "all" coverage
- **When Disabled**: Template specifies "none" or "no subtitles"
- **Style**: Karaoke-style word highlighting (current word in yellow, others in white)

### Background Music
- **Automatic Detection**: The system reads the style template's audio specifications
- **When Enabled**: Template specifies music type (e.g., "Epic Orchestral", "Lo-Fi", etc.)
- **When Disabled**: Template specifies "none", "no music", or "silent"
- **Volume**: Automatically set to 12% with voiceover ducking

## 🎤 Voice Selection

You can control which AI voice narrates your videos using the `voice_preference` parameter.

### Voice Presets

#### Male Voices
- **`male_deep`** - Adam: Deep, authoritative male voice (great for motivation)
- **`male_confident`** - Arnold: Confident, powerful male voice
- **`male_professional`** - Josh: Professional, clear male voice
- **`male_narrator`** - Bill: Classic narrator voice

#### Female Voices
- **`female_professional`** - Rachel: Professional, articulate female voice
- **`female_warm`** - Bella: Warm, friendly female voice

#### Auto Mode
- **`auto`** - Lets the style template recommend the best voice
  - Example: Motivational templates recommend Adam (deep male)
  - Example: Professional templates recommend Rachel
  - Falls back to Rachel if no recommendation

### How to Use

**In Python code:**
```python
config = {
    "business_name": "Your Business",
    "industry": "Your Industry",
    "content_goal": "growth",
    "style_category": "motivational_content",
    "platform": "youtube_shorts",
    "tier": "stock_video",
    "voice_preference": "male_deep",  # Choose your voice
    "music_style": "orchestral"
}

video_path = await generate_faceless_video_for_business(**config)
```

**Advanced: Use Specific ElevenLabs Voice ID:**
```python
"voice_preference": "pNInz6obpgDQGcFmaJgB"  # Adam's actual voice ID
```

## 📋 Example Configurations

### Motivational Video (Deep Male Voice)
```python
{
    "content_goal": "growth",
    "style_category": "motivational_content",
    "voice_preference": "male_deep",  # Adam
    # Captions: Yes (auto-detected from template)
    # Music: Yes (orchestral, auto-detected)
}
```

### Professional Explainer (Female Voice)
```python
{
    "content_goal": "engagement",
    "style_category": "educational_content",
    "voice_preference": "female_professional",  # Rachel
    # Captions: Yes (if template specifies)
    # Music: Depends on template
}
```

### Storytelling (Auto Voice Selection)
```python
{
    "content_goal": "engagement",
    "style_category": "reddit_storytelling",
    "voice_preference": "auto",  # Template recommends best voice
    # Captions: Yes (Reddit templates always use captions)
    # Music: Yes (lo-fi background)
}
```

## 🎯 Template Categories

Each category has optimized settings:

- **`motivational_content`** - Captions: Yes, Music: Orchestral, Voice: Deep Male
- **`reddit_storytelling`** - Captions: Yes (100%), Music: Lo-Fi, Voice: Calm
- **`educational_content`** - Captions: Optional, Music: Minimal, Voice: Professional
- **`luxury_lifestyle`** - Captions: Minimal, Music: Ambient, Voice: Sophisticated

## 💡 Pro Tips

1. **Trust Auto Mode**: The templates are researched for each niche
2. **Test Different Voices**: Try 2-3 presets to find your brand voice
3. **Match Voice to Content**:
   - Motivation/Inspiration → `male_deep` or `male_confident`
   - Professional/Business → `female_professional` or `male_professional`
   - Storytelling → `auto` (lets template decide)
   - Calm/Meditation → `female_warm`

4. **Captions are Platform-Specific**:
   - TikTok/Instagram Reels: Usually enabled (viewers watch without sound)
   - YouTube Shorts: Usually enabled
   - Long-form YouTube: May be disabled (viewer chooses)

## 🔧 Technical Details

### Voice IDs Reference
```python
VOICE_PRESETS = {
    "male_deep": "pNInz6obpgDQGcFmaJgB",      # Adam
    "male_confident": "VR6AewLTigWG4xSOukaG",  # Arnold
    "male_professional": "TxGEqnHWrfWFTfGW9XjX", # Josh
    "female_professional": "21m00Tcm4TlvDq8ikWAM", # Rachel
    "female_warm": "EXAVITQu4vr4xnSDxMaL",     # Bella
    "male_narrator": "pqHfZKP75CvOlQylNhV4",   # Bill
}
```

### How Templates Control Captions
```python
# From template file:
"text_overlay": {
    "subtitle_coverage": "100% of speech",  # → Captions: Yes
    # or
    "subtitle_coverage": "none",  # → Captions: No
}
```

### How Templates Control Music
```python
# From template file:
"audio_specs": {
    "music": "Epic Orchestral",  # → Music: Yes
    # or
    "music": "none",  # → Music: No
}
```

## ❓ FAQ

**Q: Can I override the template's caption/music settings?**
A: Currently, these are template-driven. You can modify the template file or create a custom template.

**Q: What if I want my own voice?**
A: You can clone your voice using ElevenLabs and use the voice ID directly in `voice_preference`.

**Q: How do I know which voice will be used in auto mode?**
A: The system logs show: `→ Voice ID: pNInz6obpgDQGcFmaJgB` during generation.

**Q: Can I change the music volume?**
A: Currently set to 12%. You can modify `music_volume=0.12` in the code (range: 0.0-1.0).
