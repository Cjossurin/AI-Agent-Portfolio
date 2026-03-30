"""The Video Publisher — Agent 7 of the Chucky AI pipeline.

Publishes rendered video to social media platforms via the Zernio API (zernio.com).
Uses presigned-URL upload flow (supports up to 5 GB) then creates posts via JSON.
Reads platform-specific SEO metadata from the pipeline and attaches per-platform captions.

Supported platforms: TikTok, YouTube Shorts, Instagram Reels, Facebook Reels, X/Twitter.
"""

import json
import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from urllib3.util import connection as urllib3_connection

logger = logging.getLogger(__name__)

# ── Zernio API config ─────────────────────────────────────────────────
ZERNIO_API_BASE = "https://zernio.com/api/v1"
ZERNIO_PRESIGN_URL = f"{ZERNIO_API_BASE}/media/presign"
ZERNIO_POSTS_URL = f"{ZERNIO_API_BASE}/posts"

ALL_PLATFORMS = ("tiktok", "youtube", "instagram", "facebook", "x")

PLATFORM_API_NAME = {
    "tiktok": "tiktok",
    "youtube": "youtube",
    "instagram": "instagram",
    "facebook": "facebook",
    "x": "twitter",
}

# By default, do not retry Late API post creation unless explicitly configured.
MAX_RETRIES = int(os.getenv("LATE_API_MAX_RETRIES", "1"))
RETRY_DELAY = int(os.getenv("LATE_API_RETRY_DELAY", "15"))  # seconds

# R2 binary upload retries are safe to repeat (each presign call gives a fresh slot).
# These do NOT count against the Late API single-try rule.
UPLOAD_MAX_RETRIES = int(os.getenv("PUBLISH_UPLOAD_MAX_RETRIES", "3"))
UPLOAD_RETRY_DELAY = int(os.getenv("PUBLISH_UPLOAD_RETRY_DELAY", "20"))  # seconds

# TikTok file-size limit — Zernio's internal TikTok upload has a ~60s timeout
# which fails for large files.  We compress to 50 MB before uploading.
TIKTOK_MAX_SIZE_MB = 50
TIKTOK_MAX_SIZE_BYTES = TIKTOK_MAX_SIZE_MB * 1024 * 1024

# Status polling — Zernio publishes asynchronously so we poll until confirmed
POLL_INTERVAL = 10   # seconds between status checks
POLL_TIMEOUT = 300   # max seconds to wait for platform confirmation (5 min)


class VideoPublisher:
    """Uploads rendered video and publishes to social platforms via Zernio."""

    def __init__(self):
        self.api_key = os.getenv("LATE_API_KEY", "")
        if not self.api_key:
            raise EnvironmentError(
                "LATE_API_KEY is not set. "
                "Copy .env.example to .env and add your Zernio/Late API key."
            )

        self.account_ids = {
            "tiktok": os.getenv("TIKTOK_ACCOUNT_ID", ""),
            "youtube": os.getenv("YOUTUBE_ACCOUNT_ID", ""),
            "instagram": os.getenv("IG_ACCOUNT_ID", ""),
            "facebook": os.getenv("FB_ACCOUNT_ID", ""),
            "x": os.getenv("X_ACCOUNT_ID", ""),
        }

    # ── Publish ledger (duplicate prevention) ─────────────────────────

    @staticmethod
    def _ledger_path(case_id: str) -> Path:
        """Return the path to the publish ledger for a given case."""
        return Path("assets") / f"case_{case_id}" / "publish_ledger.json"

    @staticmethod
    def _load_ledger(ledger_path: Path) -> dict:
        """Load the publish ledger, or return empty dict if missing."""
        if ledger_path.exists():
            return json.loads(ledger_path.read_text(encoding="utf-8"))
        return {}

    @staticmethod
    def _save_ledger(ledger_path: Path, ledger: dict) -> None:
        """Persist the publish ledger to disk."""
        ledger_path.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Caption extraction (per platform) ─────────────────────────────

    @staticmethod
    def _get_caption(platform: str, metadata: dict) -> str:
        """Extract the video caption for a given platform from SEO metadata."""
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

    @staticmethod
    def _get_youtube_title(metadata: dict) -> str:
        return metadata.get("youtube_metadata", {}).get("shorts_title", "")

    @staticmethod
    def _get_platform_specific_data(platform: str, metadata: dict) -> dict:
        """Return Zernio platformSpecificData for each platform."""
        if platform == "youtube":
            title = metadata.get("youtube_metadata", {}).get("shorts_title", "")
            data: dict = {"visibility": "public", "madeForKids": False}
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

    # ── TikTok-specific compression ───────────────────────────────────

    @staticmethod
    def _compress_for_tiktok(video_path: Path) -> Path:
        """Create a smaller copy of *video_path* for TikTok (≤ TIKTOK_MAX_SIZE_MB).

        Returns the path to the compressed file.  If the original is already
        small enough, returns *video_path* unchanged.
        """
        size_mb = video_path.stat().st_size / (1024 * 1024)
        if size_mb <= TIKTOK_MAX_SIZE_MB:
            return video_path

        tiktok_path = video_path.with_name(
            video_path.stem + "_tiktok" + video_path.suffix
        )
        logger.info(
            "TikTok compression: %.1f MB → target %d MB", size_mb, TIKTOK_MAX_SIZE_MB,
        )

        # Probe duration
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True,
        )
        duration_sec = float(probe.stdout.strip())

        audio_kbps = 128
        total_kbps = (TIKTOK_MAX_SIZE_BYTES * 8) / duration_sec / 1000
        video_kbps = max(int(total_kbps - audio_kbps), 500)

        passlog = tiktok_path.with_suffix(".tt2pass")

        # Pass 1
        r1 = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-c:v", "libx264", "-b:v", f"{video_kbps}k",
                "-pass", "1", "-passlogfile", str(passlog),
                "-an", "-f", "null",
                "NUL" if os.name == "nt" else "/dev/null",
            ],
            capture_output=True, text=True,
        )
        if r1.returncode != 0:
            logger.error("TikTok FFmpeg pass 1 failed:\n%s", r1.stderr)
            raise RuntimeError("TikTok compression failed on pass 1.")

        # Pass 2
        r2 = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-c:v", "libx264", "-b:v", f"{video_kbps}k",
                "-pass", "2", "-passlogfile", str(passlog),
                "-c:a", "aac", "-b:a", f"{audio_kbps}k",
                "-movflags", "+faststart",
                str(tiktok_path),
            ],
            capture_output=True, text=True,
        )
        if r2.returncode != 0:
            logger.error("TikTok FFmpeg pass 2 failed:\n%s", r2.stderr)
            raise RuntimeError("TikTok compression failed on pass 2.")

        # Clean up passlog files
        for f in tiktok_path.parent.glob(f"{passlog.name}*"):
            f.unlink(missing_ok=True)

        compressed_mb = tiktok_path.stat().st_size / (1024 * 1024)
        logger.info(
            "✓ TikTok copy: %.1f MB → %.1f MB (target %d kbps)",
            size_mb, compressed_mb, video_kbps,
        )
        return tiktok_path

    # ── Presigned upload ──────────────────────────────────────────────

    def _upload_video(self, video_path: Path) -> str:
        """Upload video via Zernio presigned-URL flow. Returns the public URL.

        Retries the whole presign+PUT cycle up to UPLOAD_MAX_RETRIES times on
        transient SSL/connection failures.  Each presign call produces a fresh
        unique R2 path, so retrying is safe and creates no duplicates.
        """
        file_name = video_path.name
        file_size_mb = video_path.stat().st_size / (1024 * 1024)

        last_exc: Exception | None = None
        for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
            if attempt > 1:
                wait = UPLOAD_RETRY_DELAY * (attempt - 1)
                logger.info(
                    "Upload attempt %d/%d — waiting %ds before retry...",
                    attempt, UPLOAD_MAX_RETRIES, wait,
                )
                time.sleep(wait)

            logger.info(
                "Requesting presigned URL for %s (%.1f MB)... [attempt %d/%d]",
                file_name, file_size_mb, attempt, UPLOAD_MAX_RETRIES,
            )

            try:
                presign_resp = requests.post(
                    ZERNIO_PRESIGN_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"filename": file_name, "contentType": "video/mp4"},
                    timeout=30,
                )
                presign_resp.raise_for_status()

                presign_data = presign_resp.json()
                upload_url = presign_data["uploadUrl"]
                public_url = presign_data["publicUrl"]

                upload_host = (urlparse(upload_url).hostname or "").lower()
                force_ipv4 = (
                    os.getenv("PUBLISH_UPLOAD_FORCE_IPV4", "1") == "1"
                    and upload_host.endswith("cloudflarestorage.com")
                )

                # Some networks intermittently fail large IPv6 TLS uploads to R2.
                original_allowed_gai_family = None
                if force_ipv4:
                    original_allowed_gai_family = urllib3_connection.allowed_gai_family
                    urllib3_connection.allowed_gai_family = lambda: socket.AF_INET
                    logger.info(
                        "Upload network mode: forcing IPv4 for host %s", upload_host
                    )

                logger.info("Presigned URL obtained. Uploading %.1f MB...", file_size_mb)
                try:
                    with open(video_path, "rb") as f:
                        upload_resp = requests.put(
                            upload_url,
                            headers={"Content-Type": "video/mp4"},
                            data=f,
                            timeout=600,
                        )
                finally:
                    if original_allowed_gai_family is not None:
                        urllib3_connection.allowed_gai_family = original_allowed_gai_family

                upload_resp.raise_for_status()
                logger.info("Upload complete → %s", public_url[:80])
                return public_url

            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                logger.warning(
                    "Upload attempt %d/%d failed with transport error: %s",
                    attempt, UPLOAD_MAX_RETRIES, type(exc).__name__,
                )
                if attempt == UPLOAD_MAX_RETRIES:
                    raise

        raise RuntimeError(f"Upload failed after {UPLOAD_MAX_RETRIES} attempts: {last_exc}")

    # ── Post creation ─────────────────────────────────────────────────

    def _poll_post_status(self, post_id: str, platform: str) -> dict:
        """Poll Zernio until the platform post reaches a terminal state.

        Returns dict with keys: status ('published'|'failed'|'timeout'),
        platform_url, error_message.
        """
        url = f"{ZERNIO_POSTS_URL}/{post_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        api_name = PLATFORM_API_NAME.get(platform, platform)

        deadline = time.time() + POLL_TIMEOUT
        last_status = "unknown"

        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json().get("post", resp.json())
            except Exception as exc:
                logger.warning("Poll request failed: %s — will retry", exc)
                continue

            platforms_list = data.get("platforms", [])
            entry = None
            for p in platforms_list:
                if p.get("platform") == api_name:
                    entry = p
                    break

            if not entry:
                continue

            last_status = entry.get("status", "unknown")
            if last_status == "published":
                return {
                    "status": "published",
                    "platform_url": entry.get("platformPostUrl", ""),
                    "error_message": None,
                }
            if last_status == "failed":
                return {
                    "status": "failed",
                    "platform_url": "",
                    "error_message": entry.get("errorMessage", "Unknown error"),
                }

            logger.debug(
                "  %s still %s — waiting...", platform.upper(), last_status
            )

        logger.warning(
            "%s did not reach terminal state within %ds (last: %s)",
            platform.upper(), POLL_TIMEOUT, last_status,
        )
        return {
            "status": "timeout",
            "platform_url": "",
            "error_message": f"Timed out after {POLL_TIMEOUT}s (last status: {last_status})",
        }

    def _create_zernio_post(
        self,
        video_url: str,
        platform: str,
        metadata: dict,
    ) -> tuple[str, str, dict]:
        """POST to Zernio to create the platform post.

        Returns (post_id, platform_url, raw_response).
        *platform_url* is non-empty only when Zernio confirms synchronously.
        Does NOT poll — the caller handles async confirmation so that the
        ledger can be written before polling begins (duplicate prevention).
        """
        account_id = self.account_ids.get(platform, "")
        if not account_id:
            raise ValueError(
                f"No account ID for '{platform}'. "
                "Check your .env file for the matching _ACCOUNT_ID variable."
            )

        api_name = PLATFORM_API_NAME.get(platform, platform)
        entry: dict = {"platform": api_name, "accountId": account_id}

        psd = self._get_platform_specific_data(platform, metadata)
        if psd:
            entry["platformSpecificData"] = psd

        caption = self._get_caption(platform, metadata)

        post_body = {
            "content": caption,
            "mediaItems": [{"type": "video", "url": video_url}],
            "platforms": [entry],
            "publishNow": True,
        }

        logger.info(
            "Publishing to %s — caption: %s%s",
            platform.upper(),
            caption[:80],
            "..." if len(caption) > 80 else "",
        )

        resp = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    ZERNIO_POSTS_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=post_body,
                    timeout=300,
                )
                break
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as exc:
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * attempt
                    logger.warning(
                        "Connection error on attempt %d/%d (%s). Retrying in %ds...",
                        attempt, MAX_RETRIES, type(exc).__name__, wait,
                    )
                    time.sleep(wait)
                else:
                    raise
            except KeyboardInterrupt:
                # On Windows, ssl.read() can raise KeyboardInterrupt on a
                # connection reset/EINTR — treat it as a transient network error.
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * attempt
                    logger.warning(
                        "SSL connection interrupted on attempt %d/%d. Retrying in %ds...",
                        attempt, MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Platform post to {platform.upper()} failed after "
                        f"{MAX_RETRIES} attempts due to repeated SSL interrupts."
                    )

        resp.raise_for_status()
        result = resp.json()
        post_data = result.get("post", result)
        post_id = post_data.get("_id", post_data.get("id", "N/A"))

        # Extract synchronous platform_url if Zernio confirms immediately
        platform_entries = post_data.get("platforms", [])
        platform_url = ""
        if platform_entries and platform_entries[0].get("status") == "published":
            platform_url = platform_entries[0].get("platformPostUrl", "")

        return post_id, platform_url, result

    # ── Public interface ──────────────────────────────────────────────

    def publish(
        self,
        case_id: str,
        metadata: dict,
        video_path: str | Path | None = None,
        platforms: list[str] | None = None,
    ) -> dict:
        """Upload video once, then publish to each platform.

        Args:
            case_id:    Pipeline case identifier.
            metadata:   Platform-specific SEO metadata from Agent 5.
            video_path: Path to the rendered .mp4.  Defaults to
                        ``out/case_{case_id}_final.mp4``.
            platforms:  List of target platforms.  Defaults to all five.

        Returns:
            Dict mapping each platform to its publish status/response.
        """
        if video_path is None:
            video_path = Path("out") / f"case_{case_id}_final.mp4"
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(
                f"Rendered video not found: {video_path}. "
                "Run the Remotion render (Phase 6) first."
            )

        if platforms is None:
            platforms = list(ALL_PLATFORMS)

        # ── Load ledger & filter out already-published platforms ──────
        ledger_path = self._ledger_path(case_id)
        ledger = self._load_ledger(ledger_path)

        already_done = []
        remaining = []
        for p in platforms:
            entry = ledger.get(p)
            if entry and entry.get("status") == "published":
                already_done.append(p)
            else:
                remaining.append(p)

        if already_done:
            logger.info(
                "Skipping already-published platforms: %s (see publish_ledger.json)",
                ", ".join(p.upper() for p in already_done),
            )

        if not remaining:
            logger.info("All requested platforms already published. Nothing to do.")
            return {p: {"status": "skipped", "reason": "already published"}
                    for p in platforms}

        logger.info(
            "=== Publishing case_%s to %s ===",
            case_id,
            ", ".join(p.upper() for p in remaining),
        )

        # ── Step 1 — Upload once (re-use cached URL if available) ─────
        cached_url = ledger.get("_video_url", "")
        if cached_url:
            logger.info("Re-using previously uploaded video URL.")
            video_url = cached_url
        else:
            video_url = self._upload_video(video_path)
            ledger["_video_url"] = video_url
            self._save_ledger(ledger_path, ledger)

        # ── Step 1b — TikTok-specific compressed upload ──────────────
        tiktok_video_url = video_url  # default: same as other platforms
        tiktok_upload_error: str | None = None
        if "tiktok" in remaining:
            cached_tt_url = ledger.get("_tiktok_video_url", "")
            if cached_tt_url:
                logger.info("Re-using previously uploaded TikTok video URL.")
                tiktok_video_url = cached_tt_url
            else:
                tiktok_path: Path | None = None
                try:
                    tiktok_path = self._compress_for_tiktok(video_path)
                    if tiktok_path != video_path:
                        tiktok_video_url = self._upload_video(tiktok_path)
                        ledger["_tiktok_video_url"] = tiktok_video_url
                        self._save_ledger(ledger_path, ledger)
                except Exception as exc:
                    tiktok_upload_error = str(exc)
                    logger.error(
                        "TikTok media upload failed; continuing with other platforms: %s",
                        exc,
                    )
                finally:
                    # Always clean up temporary compressed output when created.
                    if tiktok_path and tiktok_path != video_path:
                        tiktok_path.unlink(missing_ok=True)
                        logger.info("Deleted temporary TikTok file: %s", tiktok_path.name)

        # ── Step 2 — Publish per platform (write ledger after each) ───
        results: dict = {}

        # Include skipped platforms in results
        for p in already_done:
            results[p] = {"status": "skipped", "reason": "already published"}

        publish_targets = list(remaining)
        if tiktok_upload_error:
            publish_targets = [p for p in publish_targets if p != "tiktok"]
            results["tiktok"] = {
                "status": "failed",
                "error": f"TikTok media upload failed before post creation: {tiktok_upload_error}",
            }

        for platform in publish_targets:
            try:
                # ── Duplicate guard ───────────────────────────────────────────
                # If a previous run created a Zernio post but crashed/timed-out
                # before we could confirm it, the ledger will have status="pending"
                # with the post_id already recorded.  Poll THAT post instead of
                # creating a new one — this is what prevents duplicate posts.
                pending = ledger.get(platform, {})
                if pending.get("status") == "pending":
                    post_id = pending.get("post_id", "")
                    if post_id:
                        logger.info(
                            "⏳ %s — Found pending post %s from a previous attempt, polling...",
                            platform.upper(), post_id,
                        )
                        poll_result = self._poll_post_status(post_id, platform)
                        if poll_result["status"] == "published":
                            ledger[platform] = {
                                "status": "published",
                                "post_id": post_id,
                                "platform_url": poll_result["platform_url"],
                                "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            }
                            self._save_ledger(ledger_path, ledger)
                            results[platform] = {"status": "success", "response": {"post_id": post_id}}
                            logger.info("✓ %s — confirmed published (recovered pending post)", platform.upper())
                            continue
                        elif poll_result["status"] == "failed":
                            # Post genuinely failed on the platform — clear it and retry fresh
                            logger.warning(
                                "%s pending post %s failed on the platform — retrying with a new post.",
                                platform.upper(), post_id,
                            )
                            del ledger[platform]
                            self._save_ledger(ledger_path, ledger)
                            # Fall through to _create_zernio_post below
                        else:
                            # Still unconfirmed after full poll window — refuse to create
                            # another post.  Operator must re-run to re-check.
                            logger.warning(
                                "%s post %s is still unconfirmed after polling — "
                                "refusing to create a duplicate. Re-run to re-check.",
                                platform.upper(), post_id,
                            )
                            results[platform] = {
                                "status": "pending",
                                "reason": (
                                    f"Unconfirmed post {post_id} already exists on Zernio. "
                                    "Re-run to re-check its status."
                                ),
                            }
                            continue

                # ── Create a new Zernio post ──────────────────────────────────
                url_for_platform = tiktok_video_url if platform == "tiktok" else video_url
                post_id, immediate_url, raw = self._create_zernio_post(
                    url_for_platform, platform, metadata,
                )

                # Write "pending" to the ledger IMMEDIATELY after Zernio accepts
                # the POST and BEFORE polling begins.  If the process crashes or
                # the poll times out, the next re-run finds this entry and polls
                # the existing post_id instead of creating a duplicate.
                ledger[platform] = {
                    "status": "pending",
                    "post_id": post_id,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                self._save_ledger(ledger_path, ledger)
                logger.info(
                    "  Ledger updated: %s → pending (post_id=%s)", platform.upper(), post_id,
                )

                # Synchronous confirmation — Zernio sometimes confirms immediately
                if immediate_url:
                    logger.info("✓ %s — Post ID: %s (confirmed immediately)", platform.upper(), post_id)
                    ledger[platform] = {
                        "status": "published",
                        "post_id": post_id,
                        "platform_url": immediate_url,
                        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                    self._save_ledger(ledger_path, ledger)
                    results[platform] = {"status": "success", "response": raw}
                    continue

                # Async confirmation — poll until the platform confirms
                logger.info(
                    "⏳ %s — Post created (ID: %s), polling for confirmation...",
                    platform.upper(), post_id,
                )
                poll_result = self._poll_post_status(post_id, platform)

                if poll_result["status"] == "published":
                    logger.info("✓ %s — confirmed published", platform.upper())
                    ledger[platform] = {
                        "status": "published",
                        "post_id": post_id,
                        "platform_url": poll_result["platform_url"],
                        "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                    self._save_ledger(ledger_path, ledger)
                    results[platform] = {"status": "success", "response": raw}

                elif poll_result["status"] == "failed":
                    # Post failed on the platform — remove pending so next retry creates fresh
                    del ledger[platform]
                    self._save_ledger(ledger_path, ledger)
                    raise RuntimeError(
                        f"{platform.upper()} publishing failed on the platform: "
                        f"{poll_result['error_message']}"
                    )
                else:
                    # Polling timed out — pending entry STAYS in the ledger so that
                    # the next re-run polls this post_id instead of creating a duplicate.
                    raise RuntimeError(
                        f"{platform.upper()} publishing did not confirm in time: "
                        f"{poll_result['error_message']}"
                    )

            except requests.HTTPError as exc:
                logger.error("✗ %s failed: %s", platform.upper(), exc)
                results[platform] = {"status": "failed", "error": str(exc)}
            except Exception as exc:
                logger.error("✗ %s failed: %s", platform.upper(), exc)
                results[platform] = {"status": "failed", "error": str(exc)}

        # Summary log
        for platform, info in results.items():
            if info["status"] == "skipped":
                logger.info("  ⊘ %s: SKIPPED (already published)", platform.upper())
            else:
                icon = "✓" if info["status"] == "success" else "✗"
                logger.info("  %s %s: %s", icon, platform.upper(), info["status"])

        return results
