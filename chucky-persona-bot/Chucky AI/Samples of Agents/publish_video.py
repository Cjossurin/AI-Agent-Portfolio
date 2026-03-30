"""
Chucky AI — Video Publisher
Department of the Unknown

Publishes rendered video to social media platforms via the Zernio API (zernio.com).
Uses presigned-URL upload flow (supports up to 5 GB) then creates posts via JSON.
Reads SEO metadata from the pipeline output and attaches platform-specific captions.

Supported platforms: TikTok, YouTube Shorts, Instagram Reels, Facebook Reels, X/Twitter.

Usage:
  python publish_video.py --platform tiktok
  python publish_video.py --platform youtube
  python publish_video.py --platform all
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "agents" / "output"
VIDEO_DIR = PROJECT_ROOT / "video_engine" / "public"
SEO_METADATA_PATH = VIDEO_DIR / "seo_metadata.json"
DEFAULT_VIDEO_PATH = VIDEO_DIR / "final_short.mp4"

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Zernio API config (formerly Late / getlate.dev)
# ---------------------------------------------------------------------------
ZERNIO_API_BASE = "https://zernio.com/api/v1"
ZERNIO_PRESIGN_URL = f"{ZERNIO_API_BASE}/media/presign"
ZERNIO_POSTS_URL = f"{ZERNIO_API_BASE}/posts"
LATE_API_KEY = os.getenv("LATE_API_KEY", "")

# Account IDs from .env
ACCOUNT_IDS = {
    "tiktok": os.getenv("TIKTOK_ACCOUNT_ID", ""),
    "youtube": os.getenv("YOUTUBE_ACCOUNT_ID", ""),
    "instagram": os.getenv("IG_ACCOUNT_ID", ""),
    "facebook": os.getenv("FB_ACCOUNT_ID", ""),
    "x": os.getenv("X_ACCOUNT_ID", ""),
}

# Zernio API uses these platform names
PLATFORM_API_NAME = {
    "tiktok": "tiktok",
    "youtube": "youtube",
    "instagram": "instagram",
    "facebook": "facebook",
    "x": "twitter",
}

ALL_PLATFORMS = ["tiktok", "youtube", "instagram", "facebook", "x"]


def _load_seo_metadata() -> dict:
    """Load SEO metadata from video_engine/public/seo_metadata.json or fallback."""
    if SEO_METADATA_PATH.exists():
        return json.loads(SEO_METADATA_PATH.read_text(encoding="utf-8"))

    fallback_path = OUTPUT_DIR / "seo_metadata.json"
    if fallback_path.exists():
        return json.loads(fallback_path.read_text(encoding="utf-8"))

    full_path = OUTPUT_DIR / "full_concept_output.json"
    if full_path.exists():
        full_data = json.loads(full_path.read_text(encoding="utf-8"))
        seo_data = full_data.get("seo_metadata", {})
        if seo_data:
            return seo_data

    print("[ERROR] No SEO metadata found. Run the pipeline first.")
    print(f"  Checked: {SEO_METADATA_PATH}")
    print(f"  Checked: {fallback_path}")
    print(f"  Checked: {full_path}")
    sys.exit(1)


def _get_video_caption(platform: str, metadata: dict) -> str:
    """Extract the primary video caption for a given platform from SEO metadata."""
    if platform == "tiktok":
        return metadata.get("tiktok_metadata", {}).get("video_caption", "")
    elif platform == "youtube":
        yt = metadata.get("youtube_metadata", {})
        caption = yt.get("shorts_caption", "")
        tags = yt.get("tags", [])
        if tags:
            tag_str = " ".join(f"#{t.replace(' ', '')}" for t in tags[:10])
            caption = f"{caption}\n\n{tag_str}"
        return caption.strip()
    elif platform == "instagram":
        return metadata.get("instagram_metadata", {}).get("reels_caption", "")
    elif platform == "facebook":
        return metadata.get("facebook_metadata", {}).get("reels_caption", "")
    elif platform == "x":
        return metadata.get("x_twitter_metadata", {}).get("main_tweet", "")
    return ""


def _get_youtube_title(metadata: dict) -> str:
    """Extract YouTube video title from SEO metadata."""
    return metadata.get("youtube_metadata", {}).get("shorts_title", "")


def _get_platform_specific_data(platform: str, metadata: dict) -> dict:
    """Return Zernio platformSpecificData for short-form video on each platform."""
    if platform == "youtube":
        title = _get_youtube_title(metadata)
        data = {"visibility": "public", "madeForKids": False}
        if title:
            data["title"] = title[:100]
        return data
    elif platform == "instagram":
        return {"contentType": "reels", "shareToFeed": True}
    elif platform == "facebook":
        return {"contentType": "reel"}
    elif platform == "tiktok":
        return {
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "allow_comment": True,
            "allow_duet": True,
            "allow_stitch": True,
            "content_preview_confirmed": True,
            "express_consent_given": True,
        }
    return {}


def _upload_video_presigned(video_path: Path) -> str:
    """
    Upload video via Zernio presigned-URL flow (bypasses Vercel 4.5 MB limit).

    1. POST /v1/media/presign → get uploadUrl + publicUrl
    2. PUT file bytes to uploadUrl (direct to cloud storage)
    3. Return publicUrl for use in post creation
    """
    file_name = video_path.name
    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"  [1/2] Requesting presigned URL for {file_name} ({file_size_mb:.1f} MB)...")

    presign_resp = requests.post(
        ZERNIO_PRESIGN_URL,
        headers={
            "Authorization": f"Bearer {LATE_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"filename": file_name, "contentType": "video/mp4"},
        timeout=30,
    )

    if not presign_resp.ok:
        print(f"  [FAIL] Presign request — HTTP {presign_resp.status_code}")
        print(f"  Response: {presign_resp.text[:500]}")
        presign_resp.raise_for_status()

    presign_data = presign_resp.json()
    upload_url = presign_data["uploadUrl"]
    public_url = presign_data["publicUrl"]
    print(f"  Presigned URL obtained. Public URL: {public_url[:80]}...")

    print(f"  [2/2] Uploading {file_size_mb:.1f} MB to cloud storage...")
    with open(video_path, "rb") as f:
        upload_resp = requests.put(
            upload_url,
            headers={"Content-Type": "video/mp4"},
            data=f,
            timeout=600,
        )

    if not upload_resp.ok:
        print(f"  [FAIL] Upload — HTTP {upload_resp.status_code}")
        print(f"  Response: {upload_resp.text[:500]}")
        upload_resp.raise_for_status()

    print(f"  Upload complete.")
    return public_url


def publish_to_platforms(
    video_url: str,
    platforms: list[str],
    metadata: dict,
) -> dict:
    """
    Create a post on Zernio targeting one or more platforms.
    Uses JSON body with mediaItems referencing the pre-uploaded video URL.
    """
    # Build platforms array
    platform_entries = []
    for platform in platforms:
        account_id = ACCOUNT_IDS.get(platform, "")
        if not account_id:
            print(f"  [SKIP] No account ID for '{platform}'. Check .env.")
            continue

        api_name = PLATFORM_API_NAME.get(platform, platform)
        entry = {"platform": api_name, "accountId": account_id}

        psd = _get_platform_specific_data(platform, metadata)
        if psd:
            entry["platformSpecificData"] = psd

        platform_entries.append(entry)

    if not platform_entries:
        raise ValueError("No valid platform entries to publish.")

    # Use the first platform's caption as the main content
    # (Zernio uses content as the shared caption; platforms can override via customContent)
    caption = _get_video_caption(platforms[0], metadata)

    post_body = {
        "content": caption,
        "mediaItems": [{"type": "video", "url": video_url}],
        "platforms": platform_entries,
        "publishNow": True,
    }

    print(f"  Creating post on {', '.join(p.upper() for p in platforms)}...")
    print(f"  Caption preview: {caption[:80]}{'...' if len(caption) > 80 else ''}")

    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                ZERNIO_POSTS_URL,
                headers={
                    "Authorization": f"Bearer {LATE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=post_body,
                timeout=300,
            )
            break
        except requests.exceptions.ReadTimeout as e:
            last_err = e
            if attempt < 3:
                wait = 15 * attempt
                print(f"  ⏳ Read timeout (attempt {attempt}/3). Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    else:
        raise last_err  # type: ignore[misc]

    print(f"  Response status: {resp.status_code}")

    if not resp.ok:
        print(f"  [FAIL] Post creation — HTTP {resp.status_code}")
        print(f"  Response body: {resp.text[:500]}")
        resp.raise_for_status()

    result = resp.json()
    print(f"  Post created successfully.")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Chucky AI — Publish rendered video to social platforms via Zernio API",
    )
    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help=f"Path to the rendered .mp4 video file (default: {DEFAULT_VIDEO_PATH.name})",
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=["tiktok", "youtube", "instagram", "facebook", "x", "all"],
        default="all",
        help='Target platform (default: "all" — publishes to all 5 platforms)',
    )
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.exists():
        print(f"[ERROR] Video file not found: {video_path}")
        sys.exit(1)

    if not LATE_API_KEY or LATE_API_KEY.startswith("your-"):
        print("[ERROR] LATE_API_KEY is not set. Update your .env file.")
        sys.exit(1)

    metadata = _load_seo_metadata()

    if args.platform == "all":
        platforms = list(ALL_PLATFORMS)
    else:
        platforms = [args.platform]

    print("=" * 56)
    print("  Chucky AI — Video Publisher (Zernio API)")
    print("=" * 56)
    print(f"  Video:     {video_path.name}")
    print(f"  API Base:  {ZERNIO_API_BASE}")
    print(f"  Platforms: {', '.join(p.upper() for p in platforms)}\n")

    # Step 1: Upload video once via presigned URL
    print("--- Uploading Video ---")
    try:
        video_url = _upload_video_presigned(video_path)
    except Exception as e:
        print(f"  ❌ Video upload failed: {e}")
        sys.exit(1)
    print()

    # Step 2: Publish to each platform individually (separate captions per platform)
    results = {}
    for platform in platforms:
        print(f"--- Publishing to {platform.upper()} ---")
        try:
            result = publish_to_platforms(video_url, [platform], metadata)
            results[platform] = {"status": "success", "response": result}
            post_data = result.get("post", result)
            post_id = post_data.get("_id", post_data.get("id", "N/A"))
            print(f"  Post ID: {post_id}\n")
        except requests.HTTPError as e:
            results[platform] = {"status": "failed", "error": str(e)}
            print(f"  ❌ Skipping {platform.upper()} due to error.\n")
        except Exception as e:
            results[platform] = {"status": "failed", "error": str(e)}
            print(f"  ❌ {platform.upper()} failed: {e}\n")

    # Summary
    print("=" * 56)
    print("  PUBLISH SUMMARY")
    print("-" * 56)
    for platform, info in results.items():
        icon = "✅" if info["status"] == "success" else "❌"
        print(f"  {icon} {platform.upper()}: {info['status']}")
    print("=" * 56)


if __name__ == "__main__":
    main()
