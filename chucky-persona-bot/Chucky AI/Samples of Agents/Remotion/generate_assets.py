"""
generate_assets.py — Asset Generator for Chucky AI Video Engine
Reads script_data.json, generates images (Fal.ai Flux) and audio (ElevenLabs TTS),
and saves them to video_engine/public/assets/ for Remotion to statically link.
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DATA_PATH = PROJECT_ROOT / "video_engine" / "public" / "script_data.json"
ASSETS_DIR = PROJECT_ROOT / "video_engine" / "public" / "assets"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")

FAL_KEY = os.getenv("FAL_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

if not FAL_KEY:
    sys.exit("❌ FAL_KEY not found in .env")
if not ELEVENLABS_API_KEY:
    sys.exit("❌ ELEVENLABS_API_KEY not found in .env")

# Fal.ai picks up FAL_KEY from env automatically
os.environ["FAL_KEY"] = FAL_KEY

# ElevenLabs — "Adam" voice: deep male narrator, good for horror
VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

with open(SCRIPT_DATA_PATH, "r", encoding="utf-8") as f:
    script_data = json.load(f)

scene_prompts = script_data["scene_prompts"]
print(f"🎬 Title: {script_data['title']}")
print(f"📦 {len(scene_prompts)} scenes to process")
print(f"📁 Assets directory: {ASSETS_DIR}\n")

# ---------------------------------------------------------------------------
# Generation Loop
# ---------------------------------------------------------------------------
import fal_client
from elevenlabs import ElevenLabs
from elevenlabs.types import VoiceSettings

el_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Slow, deliberate delivery for horror narration
HORROR_VOICE_SETTINGS = VoiceSettings(
    stability=0.7,
    similarity_boost=0.8,
    speed=0.85,
)

# ── Background Ambient Track (loopable, plays for full video) ────────────
ambient_path = ASSETS_DIR / "ambient_background.mp3"
if ambient_path.exists():
    print("🔊 ambient_background.mp3 already exists, skipping\n")
else:
    print("🔊 Generating loopable ambient background track...")
    try:
        sfx_iterator = el_client.text_to_sound_effects.convert(
            text="dark horror ambient drone, low frequency rumble, tension building atmosphere, industrial hum, unsettling background noise",
            duration_seconds=22.0,
            loop=True,
            prompt_influence=0.5,
        )
        with open(ambient_path, "wb") as af:
            for chunk in sfx_iterator:
                af.write(chunk)
        print(f"  ✅ ambient_background.mp3 generated (22s loop)\n")
    except Exception as e:
        print(f"  ❌ ambient_background.mp3 FAILED: {e}\n")

# ── Static Hiss Track (VHS/CRT overlay audio, loopable) ─────────────────
static_hiss_path = ASSETS_DIR / "static_hiss.mp3"
if static_hiss_path.exists():
    print("🔊 static_hiss.mp3 already exists, skipping\n")
else:
    print("🔊 Generating VHS static hiss track...")
    try:
        hiss_iterator = el_client.text_to_sound_effects.convert(
            text="TV static white noise, analog CRT hiss, VHS tape noise, continuous static",
            duration_seconds=22.0,
            loop=True,
            prompt_influence=0.6,
        )
        with open(static_hiss_path, "wb") as af:
            for chunk in hiss_iterator:
                af.write(chunk)
        print(f"  ✅ static_hiss.mp3 generated (22s loop)\n")
    except Exception as e:
        print(f"  ❌ static_hiss.mp3 FAILED: {e}\n")

for i, scene in enumerate(scene_prompts, 1):
    scene_id = scene["scene_id"]
    prompt = scene["flux_image_prompt"]
    tts_text = scene["elevenlabs_tts_text"]
    audio_direction = scene.get("audio_direction", "")

    print(f"--- Scene {i}/{len(scene_prompts)}: {scene_id} ---")

    # ── Image Generation (Fal.ai Flux) ──────────────────────────────────
    image_path = ASSETS_DIR / f"{scene_id}.jpg"
    if image_path.exists():
        print(f"  ⏭️  {scene_id}.jpg already exists, skipping image generation")
    else:
        try:
            result = fal_client.subscribe(
                "fal-ai/flux-pro",
                arguments={
                    "prompt": prompt,
                    "image_size": {"width": 1080, "height": 1920},
                    "num_images": 1,
                },
            )
            image_url = result["images"][0]["url"]
            img_response = requests.get(image_url, timeout=60)
            img_response.raise_for_status()
            image_path.write_bytes(img_response.content)
            print(f"  ✅ {scene_id}.jpg downloaded")
        except Exception as e:
            print(f"  ❌ {scene_id}.jpg FAILED: {e}")

    # ── Video Generation (Kling AI via fal.ai) ──────────────────────────
    video_path = ASSETS_DIR / f"{scene_id}.mp4"
    if video_path.exists():
        print(f"  ⏭️  {scene_id}.mp4 already exists, skipping video generation")
    elif not image_path.exists():
        print(f"  ⏭️  {scene_id}.mp4 skipped (no source image)")
    else:
        try:
            # Upload local image to fal for Kling ingestion
            image_url = fal_client.upload_file(str(image_path))
            duration = scene.get("duration_estimate_seconds", 5.0)
            kling_duration = "10" if duration > 7 else "5"

            print(f"  🎥 Generating {scene_id}.mp4 via Kling AI ({kling_duration}s)...")
            kling_result = fal_client.subscribe(
                "fal-ai/kling-video/v1.5/pro/image-to-video",
                arguments={
                    "image_url": image_url,
                    "prompt": "slow eerie zoom in, subtle breathing, minimal movement, terrifying stillness",
                    "duration": kling_duration,
                    "aspect_ratio": "9:16",
                },
            )
            video_url = kling_result["video"]["url"]
            vid_response = requests.get(video_url, timeout=120)
            vid_response.raise_for_status()
            video_path.write_bytes(vid_response.content)
            print(f"  ✅ {scene_id}.mp4 downloaded ({kling_duration}s clip)")
        except Exception as e:
            print(f"  ⚠️  {scene_id}.mp4 FAILED (will fall back to static image): {e}")

    # ── Narration Audio (ElevenLabs TTS) ─────────────────────────────────
    audio_path = ASSETS_DIR / f"{scene_id}.mp3"
    if not tts_text:
        print(f"  ⏭️  {scene_id}.mp3 skipped (no narration)")
    elif audio_path.exists():
        print(f"  ⏭️  {scene_id}.mp3 already exists, skipping audio generation")
    else:
        try:
            audio_iterator = el_client.text_to_speech.convert(
                voice_id=VOICE_ID,
                text=tts_text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                voice_settings=HORROR_VOICE_SETTINGS,
            )
            with open(audio_path, "wb") as af:
                for chunk in audio_iterator:
                    af.write(chunk)
            print(f"  ✅ {scene_id}.mp3 downloaded")
        except Exception as e:
            print(f"  ❌ {scene_id}.mp3 FAILED: {e}")

    # ── Scene Sound Effects (ElevenLabs SFX) ─────────────────────────────
    sfx_path = ASSETS_DIR / f"{scene_id}_sfx.mp3"
    duration = scene.get("duration_estimate_seconds", 10.0)
    sfx_duration = min(max(duration, 0.5), 22.0)  # clamp to API limits

    if sfx_path.exists():
        print(f"  ⏭️  {scene_id}_sfx.mp3 already exists, skipping SFX generation")
    elif audio_direction:
        try:
            sfx_iterator = el_client.text_to_sound_effects.convert(
                text=audio_direction,
                duration_seconds=sfx_duration,
                prompt_influence=0.4,
            )
            with open(sfx_path, "wb") as af:
                for chunk in sfx_iterator:
                    af.write(chunk)
            print(f"  ✅ {scene_id}_sfx.mp3 generated ({sfx_duration:.1f}s)")
        except Exception as e:
            print(f"  ❌ {scene_id}_sfx.mp3 FAILED: {e}")
    else:
        print(f"  ⏭️  {scene_id}_sfx.mp3 skipped (no audio direction)")

    print()

print("🏁 Asset generation complete!")
print(f"   Output: {ASSETS_DIR}")
print(f"   Files: {[p.name for p in ASSETS_DIR.glob('*')]}")
