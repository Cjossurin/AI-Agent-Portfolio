"""Generate horror SFX and background music using ElevenLabs Sound Generation API.

Run once to populate assets/shared/ with:
  - music/       → 3 horror background music tracks (~60s each, loopable)
  - sfx_scare/   → 3 jump scare stinger hits (~2s each)
  - sfx_transition/ → 3 dark whoosh transitions (~1.5s each)
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")
BASE_URL = "https://api.elevenlabs.io/v1/sound-generation"
SHARED_DIR = Path("assets/shared")

# ── Audio definitions ─────────────────────────────────────────────────

TRACKS = [
    # Background music — atmospheric horror for under narration
    {
        "dir": "music",
        "filename": "horror_tension_01.mp3",
        "text": "slow dark horror ambient music with deep bass drone and distant eerie piano notes creating dread and tension, cinematic soundtrack",
        "duration": 60.0,
    },
    {
        "dir": "music",
        "filename": "horror_tension_02.mp3",
        "text": "creepy minimalist horror background music with subtle strings and low rumbling bass, building unease, dark film score atmosphere",
        "duration": 60.0,
    },
    {
        "dir": "music",
        "filename": "horror_tension_03.mp3",
        "text": "ominous dark ambient horror music with reversed reverb pads and distant metallic scraping sounds, psychological horror soundtrack",
        "duration": 60.0,
    },
    # Scare stingers — short sharp hits for when Kling video plays
    {
        "dir": "sfx_scare",
        "filename": "scare_hit_01.mp3",
        "text": "loud sudden horror jump scare sound effect with deep bass impact hit and sharp metallic screech, very short and intense",
        "duration": 2.0,
    },
    {
        "dir": "sfx_scare",
        "filename": "scare_hit_02.mp3",
        "text": "horror jump scare stinger with distorted bass drop and eerie high pitched shriek, sudden violent impact sound",
        "duration": 2.0,
    },
    {
        "dir": "sfx_scare",
        "filename": "scare_hit_03.mp3",
        "text": "bone chilling horror scare sound effect with deep reverberating boom and unsettling dissonant tone, short sharp shock",
        "duration": 2.0,
    },
    # Transition whooshes — subtle dark swoosh between blocks
    {
        "dir": "sfx_transition",
        "filename": "dark_whoosh_01.mp3",
        "text": "dark cinematic whoosh transition sound effect with low frequency sweep and subtle ghostly whisper, smooth and eerie",
        "duration": 1.5,
    },
    {
        "dir": "sfx_transition",
        "filename": "dark_whoosh_02.mp3",
        "text": "deep dark swoosh sound effect with rumbling bass sweep and faint distant scream fading away, horror scene transition",
        "duration": 1.5,
    },
    {
        "dir": "sfx_transition",
        "filename": "dark_whoosh_03.mp3",
        "text": "ominous dark whoosh pass by sound effect with low wind sweep and subtle crackling static, cinematic horror transition",
        "duration": 1.5,
    },
]


def generate_sound(text: str, duration: float) -> bytes:
    """Call ElevenLabs Sound Generation API and return raw MP3 bytes."""
    resp = requests.post(
        BASE_URL,
        headers={
            "xi-api-key": API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "duration_seconds": duration,
            "prompt_influence": 0.3,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.content


def main():
    for track in TRACKS:
        out_dir = SHARED_DIR / track["dir"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / track["filename"]

        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"  SKIP (exists): {out_path}")
            continue

        print(f"  Generating: {out_path} ({track['duration']}s) ...")
        try:
            audio_bytes = generate_sound(track["text"], track["duration"])
            out_path.write_bytes(audio_bytes)
            size_kb = len(audio_bytes) / 1024
            print(f"  ✓ Saved: {out_path} ({size_kb:.0f} KB)")
        except Exception as exc:
            print(f"  ✗ Failed: {out_path} — {exc}")

        # Small delay to avoid rate limits
        time.sleep(1)

    print("\nDone! All audio files generated in assets/shared/")


if __name__ == "__main__":
    main()
