# Style Injection System - Quick Start Guide

## ✅ What Was Implemented

Your bot now loads writing samples from files and mimics your tone/style automatically!

## 📁 Files Created/Updated

### New Files
1. **`utils/file_reader.py`** - Shared file extraction utilities (PDF, DOCX, TXT)
2. **`utils/__init__.py`** - Makes utils a proper Python package
3. **`style_references/README.md`** - Instructions for adding style samples

### Updated Files
1. **`ingest.py`** - Now uses shared utilities from `utils/file_reader.py`
2. **`agents/engagement_agent.py`** - Loads style samples on startup and injects into prompts
3. **`README.md`** - Added Style Injection documentation
4. **`.github/.instructions/copilot-instructions.md`** - Documented the new system

## 🚀 How to Use

### Method 1: Normalize Messy Chat Logs (Recommended)

If you have raw, unformatted chat exports:

```bash
# Step 1: Drop raw chat logs into raw_style_inputs/
# Examples: Facebook exports, Instagram DM screenshots, SMS logs

# Step 2: Run the normalizer
python normalize_style.py

# Step 3: Claude AI will clean and format your chats
# Output saved to: style_references/demo_client/normalized_samples.txt
```

### Method 2: Add Pre-Formatted Samples

If you already have clean writing samples:

```bash
# Drop your writing samples into style_references/
# Supported formats: .pdf, .docx, .txt

# Examples:
# - Export your Instagram DMs to PDF
# - Copy/paste past social media replies into a .txt file
# - Save email responses as .docx
```

### Step 2: Restart Your Bot
```bash
python webhook_receiver.py
```

The bot will:
- Load all files from `style_references/` on startup
- Analyze your tone, sentence length, and vocabulary
- Mimic your style in all responses

### Step 3: Test It
Send a DM to your Instagram bot and see if it sounds like you!

## 📊 Tips for Best Results

| Samples | Quality |
|---------|---------|
| 1-4 | Poor - not enough data |
| 5-9 | Basic - will try but may be off |
| 10-19 | Good - solid style matching |
| 20+ | Excellent - very accurate |

## 🧹 normalize_style.py - Chat Log Cleaner

### What It Does
Converts messy chat logs into perfectly formatted training data using Claude AI.

### Workflow
```
raw_style_inputs/           →  normalize_style.py  →  style_references/demo_client/
  chat_export.pdf                   (Claude AI)            normalized_samples.txt
  messenger_log.docx                                      (clean & formatted)
```

### How Claude Cleans Your Data
1. **Identifies speakers**: Determines who is the "Expert" (you) vs. the "Other Person"
2. **Extracts style**: Finds conversations that show your writing personality
3. **Formats consistently**: Outputs as `Context: [them] → My Reply: [you]`
4. **Removes noise**: Strips timestamps, formatting artifacts, system messages

### Example Transformation

**Before (Raw):**
```
[2:34 PM] John Smith: hey can u help??
[2:35 PM] You: Of course! Happy to help. What do you need? 😊
[2:36 PM] John Smith: pricing pls
[2:37 PM] You: Let me get that for you right away!
```

**After (Normalized):**
```
Context: can you help?
My Reply: Of course! Happy to help. What do you need? 😊

Context: pricing please
My Reply: Let me get that for you right away!
```

### Tips
- Include 10-20 conversations minimum
- Mix different situations (questions, complaints, compliments)
- The script can handle large files (PDFs with hundreds of messages)
- Run it multiple times - output is overwritten each time

---

## 🔧 Advanced: Per-Client Styles (Future)

When you add multi-client support, create subfolders:

```
style_references/
├── client_a/
│   └── client_a_style.pdf
├── client_b/
│   └── client_b_dms.txt
└── demo_client/  (default)
    └── my_style.pdf
```

The bot checks `style_references/{client_id}/` first, then falls back to the root folder.

## 🛠️ Technical Details

### Architecture
- **Load Time**: Once on startup (cached in memory)
- **Performance**: No per-message file I/O
- **Fallback**: If no files found, uses default neutral tone
- **Character Limit**: 800 max, aims for ~400

### File Processing
- Uses `pypdf` for PDFs (not PyPDF2)
- Extracts text from all pages/paragraphs
- Handles errors gracefully (continues if one file fails)

### System Prompt Injection
```
You are an AI Engagement Agent.

### STYLE & TONE INSTRUCTIONS
Analyze the following examples of past writing. You must mimic this tone, sentence length, and vocabulary exactly.

--- BEGIN STYLE SAMPLES ---
{your_writing_samples}
--- END STYLE SAMPLES ---

### CONSTRAINTS
- Keep responses under 800 characters maximum (aim for ~400 when possible).
- Do not be robotic - sound natural and conversational.
...
```

## 🎯 Next Steps

1. Export 10-20 of your past DM conversations to PDF
2. Drop them in `style_references/`
3. Restart the bot
4. Test and iterate!

---

**Questions?** Check `style_references/README.md` for more details.
