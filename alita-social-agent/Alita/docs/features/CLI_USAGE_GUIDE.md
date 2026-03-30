# Alita CLI - Image & Video Generation Guide

## How to Access Image Generation

### Step 1: Launch the CLI
```bash
python cli_interface.py
```

### Step 2: From the Main Menu, select option **7**
```
MAIN MENU
======================================================================

1. 📝 Start Content Workflow
2. 📚 Manage Knowledge Base
3. 🎨 Configure Style/Tone
4. 🔍 Query Deep Research
5. 🔔 Notification Settings
6. ℹ️  View Client Setup
7. 🎬 Faceless Video Generator     ← SELECT THIS
8. 🧵 Threads Management
9. ❌ Exit

Select option (1-9): 7
```

### Step 3: In the Faceless Video Generator submenu, select option **2**
```
🎬 FACELESS VIDEO GENERATOR
======================================================================

📡 API Status:
   Pexels (Stock Video): ✅
   Pixabay (Stock Video): ✅
   ElevenLabs (Voiceover): ✅
   DALL-E 3 (Images): ✅
   fal.ai (AI Animation): ✅
   FFmpeg (Assembly): ✅

🎯 Available Tiers: Tier 1 (Stock Video), Tier 2 (Generated Images), Tier 3 (AI Animation)

1. 🎥 Generate Video (enter script)
2. 🖼️  Generate Image              ← SELECT THIS
3. 📊 View Generation Stats
4. 🧪 Test APIs
5. ⬅️  Back to Main Menu

Select option (1-5): 2
```

### Step 4: Follow the prompts

#### 4a. Enter your prompt
```
🖼️  GENERATE FACELESS IMAGE
======================================================================

📝 Enter image prompt: A futuristic city skyline at sunset with flying cars
```

#### 4b. Choose size
```
📐 SELECT SIZE:

1. Square (1080x1080) - Instagram Feed
2. Portrait (1080x1920) - Stories/Reels
3. Landscape (1920x1080) - YouTube/Facebook

Select size (1-3) [default: 1]: 1
```

#### 4c. Choose quality tier
```
🎨 SELECT IMAGE QUALITY:
----------------------------------------------------------------------

1. 💰 Budget (DALL-E 3) - $0.04
   • Fast generation (~5-10s)
   • Good quality, reliable
   • Best for: Testing, quick content

2. ⭐ Standard (Flux) - $0.055
   • Balanced quality/cost
   • More detail and creativity
   • Best for: Regular posts, better visuals

3. 💎 Premium (Midjourney) - $0.05
   • Highest artistic quality
   • Professional-grade output
   • Best for: Hero images, brand showcase

Select quality (1-3) [default: 1]: 3
```

#### 4d. Choose image type
```
🎯 SELECT IMAGE TYPE:

1. General (default) - Balanced for any content
2. Artistic - Creative, stylized visuals
3. Text - Images with text/quotes (best with Ideogram)

Select type (1-3) [default: 1]: 2
```

#### 4e. Review and confirm
```
💵 ESTIMATED COST: $0.050
   Quality: premium
   Type: artistic
   Size: 1080x1080

🚀 Generate image? (yes/no): yes
```

#### 4f. Get your image!
```
🎨 Generating premium quality image (1080x1080)...

✅ Image generated!
🔗 URL: https://img.theapi.app/mj/xyz123.png
💰 Cost: $0.05
⏱️  Time: 45.2s
```

---

## Video Generation with Quality Tiers

### Access: Main Menu → Option 7 → Option 1

When generating videos with **Tier 2 (Generated Images)** or **Tier 3 (AI Animation)**, you'll be prompted to select image quality:

```
🎨 SELECT IMAGE QUALITY:
----------------------------------------------------------------------

1. 💰 Budget (DALL-E 3) - $0.04/image
   • Fast generation (~5-10s per image)
   • Good quality, reliable
   • Best for: Testing, high-volume content

2. ⭐ Standard (Flux) - $0.055/image
   • Balanced quality/cost
   • More detail than DALL-E
   • Best for: Regular content, better visuals

3. 💎 Premium (Midjourney) - $0.05/image
   • Highest artistic quality
   • Professional-grade images
   • Best for: Premium content, brand showcase

Select quality (1-3) [default: 1]:
```

**Note:** Quality selection only appears for Tier 2 & 3. Tier 1 (Stock Video) doesn't need it since it uses free Pexels/Pixabay footage.

---

## Quick Start Examples

### Generate a Quick Instagram Image
```bash
python cli_interface.py
# Select: 7 → 2 → "A serene beach at sunset" → 1 (Square) → 1 (Budget) → 1 (General) → yes
```

### Generate a Premium Hero Image
```bash
python cli_interface.py
# Select: 7 → 2 → "Professional workspace with MacBook" → 1 (Square) → 3 (Premium) → 2 (Artistic) → yes
```

### Generate a Video with Premium Images
```bash
python cli_interface.py
# Select: 7 → 1 → (provide script or generate) → 2 (Generated Images) → 3 (Premium) → ...
```

---

## Pro Tips

1. **Budget Quality** is perfect for:
   - Testing prompts
   - High-volume content generation
   - When speed matters more than perfection

2. **Standard Quality** is ideal for:
   - Regular social media posts
   - When you need better visuals than DALL-E
   - Balanced cost/quality projects

3. **Premium Quality** is best for:
   - Hero images for websites
   - Brand showcase content
   - When quality is paramount
   - Professional portfolios

4. **Style Consistency**: When generating videos, the system automatically captures the style from the first image and applies it to subsequent scenes for visual cohesion!

---

## API Requirements

Ensure these environment variables are set in your `.env`:

- `OPENAI_API_KEY` - For DALL-E 3 (Budget quality)
- `FAL_API_KEY` - For Flux (Standard quality)
- `GOAPI_API_KEY` - For Midjourney (Premium quality)

All three are already configured in your `.env` file! ✅
