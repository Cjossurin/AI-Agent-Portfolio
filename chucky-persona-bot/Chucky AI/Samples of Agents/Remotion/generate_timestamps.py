"""
generate_timestamps.py — Whisper Word-Level Timestamp Generator
Transcribes each .mp3 in video_engine/public/assets/ using OpenAI Whisper-1,
saves word-level timestamps as [scene_id]_words.json for Remotion captions.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "video_engine" / "public" / "assets"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    sys.exit("❌ OPENAI_API_KEY not found in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------------------------------
# Find all .mp3 files
# ---------------------------------------------------------------------------
all_mp3 = sorted(ASSETS_DIR.glob("*.mp3"))
# Only transcribe narration files — skip SFX and ambient background
mp3_files = [
    f for f in all_mp3
    if "_sfx" not in f.stem and f.stem != "ambient_background"
]
if not mp3_files:
    sys.exit("❌ No narration .mp3 files found in " + str(ASSETS_DIR))

print(f"🎤 Found {len(mp3_files)} narration file(s) to transcribe (skipped {len(all_mp3) - len(mp3_files)} SFX/ambient)")
print(f"📁 Assets directory: {ASSETS_DIR}\n")

# ---------------------------------------------------------------------------
# Transcription Loop
# ---------------------------------------------------------------------------
for mp3_path in mp3_files:
    scene_id = mp3_path.stem
    output_path = ASSETS_DIR / f"{scene_id}_words.json"

    if output_path.exists():
        print(f"⏭️  {scene_id}_words.json already exists, skipping")
        continue

    print(f"🔊 Transcribing {mp3_path.name}...", end=" ", flush=True)

    try:
        with open(mp3_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )

        words = []
        for w in transcript.words:
            words.append({
                "word": w.word,
                "start": w.start,
                "end": w.end,
            })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(words, f, indent=2)

        print(f"✅ {len(words)} words → {scene_id}_words.json")

    except Exception as e:
        print(f"❌ FAILED: {e}")

print("\n🏁 Timestamp generation complete!")
print(f"   Files: {[p.name for p in ASSETS_DIR.glob('*_words.json')]}")
