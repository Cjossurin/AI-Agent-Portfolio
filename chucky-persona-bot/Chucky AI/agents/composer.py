"""The Remotion Composer & Trigger — Agent 6 of the Chucky AI pipeline.

Builds remotion_props.json from the media manifest and storyboard, then
invokes the Remotion CLI to render the final video.
"""

import json
import logging
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

import requests
from mutagen.mp3 import MP3
from PIL import Image as PILImage

from agents.image_dark_comic import DarkComicImageGenerator
from agents.image_vintage import VintageIllustrationImageGenerator

logger = logging.getLogger(__name__)

# Paths to shared ambient audio layers (place these in assets/shared/)
DRONE_AUDIO = "assets/shared/drone_audio.mp3"
VHS_STATIC = "assets/shared/vhs_static.mp3"

# Background music tracks — Kevin MacLeod (CC BY) horror scores
MUSIC_TRACKS = [
    "assets/shared/music/horror_music_01.mp3",
    "assets/shared/music/horror_music_02.mp3",
    "assets/shared/music/horror_music_03.mp3",
]

# Jump scare stingers (played when Kling scare video triggers)
SCARE_STINGERS = [
    "assets/shared/sfx_scare/scare_hit_01.mp3",
    "assets/shared/sfx_scare/scare_hit_02.mp3",
    "assets/shared/sfx_scare/scare_hit_03.mp3",
]

# Block transition whooshes (played at the start of each block after the first)
TRANSITION_WHOOSHES = [
    "assets/shared/sfx_transition/dark_whoosh_01.mp3",
    "assets/shared/sfx_transition/dark_whoosh_02.mp3",
    "assets/shared/sfx_transition/dark_whoosh_03.mp3",
]

# Hard ceiling for rendered video file size
MAX_FILE_SIZE_MB = 90
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class RemotionComposer:
    """Assembles Remotion props and triggers the CLI render."""

    def __init__(self, remotion_dir: str = "remotion-vhs"):
        self.remotion_dir = Path(remotion_dir)

    # ── Props builder ─────────────────────────────────────────────────

    def build_video(self, case_id: str, media_manifest: dict, captions: list | None = None) -> Path:
        """Build remotion_props.json and execute `npx remotion render`."""
        asset_dir = Path("assets") / f"case_{case_id}"
        if not asset_dir.is_dir():
            raise FileNotFoundError(f"Asset directory not found: {asset_dir}")

        blocks = media_manifest.get("blocks", [])
        if not blocks:
            raise ValueError("media_manifest must contain a non-empty 'blocks' array.")

        # Build the sequence entries from the manifest
        sequences: list[dict] = []
        for block in blocks:
            bid = block["block_id"]
            entry: dict = {
                "blockId": bid,
                "motionType": block.get("motion_type", "ken_burns_zoom_in"),
                "imagePath": block.get("image_path", "").replace("\\", "/"),
                "audioPath": block.get("audio_path", "").replace("\\", "/"),
            }

            # If this block has a scare video, include it
            if "video_path" in block:
                entry["videoPath"] = block["video_path"].replace("\\", "/")

            # Measure actual audio duration
            audio_file = Path(entry["audioPath"])
            if audio_file.is_file():
                try:
                    audio = MP3(str(audio_file))
                    entry["audioDurationSec"] = round(audio.info.length, 2)
                    logger.info("  Block %d audio duration: %.2fs", bid, entry["audioDurationSec"])
                except Exception as exc:
                    logger.warning("  Could not measure audio for block %d: %s", bid, exc)
                    entry["audioDurationSec"] = 12.0
            else:
                entry["audioDurationSec"] = 12.0

            sequences.append(entry)

        # Load captions from asset folder if not passed directly
        if captions is None:
            captions_path = asset_dir / "captions.json"
            if captions_path.is_file():
                captions = json.loads(captions_path.read_text(encoding="utf-8"))
                logger.info("Loaded captions from %s", captions_path)
            else:
                captions = []

        # Assemble the full props object
        chosen_style = media_manifest.get("chosen_style", "dark_comic")
        props = {
            "caseId": case_id,
            "chosenStyle": chosen_style,
            "sequences": sequences,
            "ambientLayers": {
                "droneAudio": DRONE_AUDIO,
                "vhsStatic": VHS_STATIC,
                "backgroundMusic": random.choice(MUSIC_TRACKS),
                "scareStinger": random.choice(SCARE_STINGERS),
                "transitionWhoosh": random.choice(TRANSITION_WHOOSHES),
            },
            "captions": captions,
            "effectsIntensity": "medium",
            "showTimestamp": True,
        }
        logger.info(
            "Audio layers: music=%s, stinger=%s, whoosh=%s",
            props["ambientLayers"]["backgroundMusic"],
            props["ambientLayers"]["scareStinger"],
            props["ambientLayers"]["transitionWhoosh"],
        )

        # Write to asset folder
        props_path = asset_dir / "remotion_props.json"
        props_path.write_text(
            json.dumps(props, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Remotion props written to %s", props_path)

        # Log total duration
        total_sec = sum(s.get("audioDurationSec", 12.0) for s in sequences)
        logger.info("Total audio duration: %.1fs across %d blocks", total_sec, len(sequences))

        # Render the video
        self._render(case_id, props_path)

        return props_path
    # ── FFmpeg two-pass compression ───────────────────────────────────────

    @staticmethod
    def _compress_to_limit(video_path: Path) -> None:
        """Re-encode *video_path* with FFmpeg two-pass to fit under MAX_FILE_SIZE_MB."""
        original_mb = video_path.stat().st_size / (1024 * 1024)
        logger.info(
            "Video is %.1f MB (limit %d MB) — running FFmpeg two-pass compression...",
            original_mb, MAX_FILE_SIZE_MB,
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

        # Target bitrate: reserve 128 kbps for audio, rest for video
        audio_bitrate_kbps = 128
        target_total_kbps = (MAX_FILE_SIZE_BYTES * 8) / duration_sec / 1000
        video_bitrate_kbps = int(target_total_kbps - audio_bitrate_kbps)
        video_bitrate_kbps = max(video_bitrate_kbps, 500)

        logger.info(
            "Duration: %.1fs — target video bitrate: %d kbps, audio: %d kbps",
            duration_sec, video_bitrate_kbps, audio_bitrate_kbps,
        )

        tmp_output = video_path.with_suffix(".compressed.mp4")
        passlog = video_path.with_suffix(".ffmpeg2pass")

        # Pass 1 — analysis only
        pass1_cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-c:v", "libx264", "-b:v", f"{video_bitrate_kbps}k",
            "-pass", "1", "-passlogfile", str(passlog),
            "-an", "-f", "null",
            "NUL" if os.name == "nt" else "/dev/null",
        ]
        logger.info("FFmpeg pass 1/2...")
        r1 = subprocess.run(pass1_cmd, capture_output=True, text=True)
        if r1.returncode != 0:
            logger.error("FFmpeg pass 1 failed:\n%s", r1.stderr)
            raise RuntimeError("FFmpeg two-pass compression failed on pass 1.")

        # Pass 2 — encode at computed bitrate
        pass2_cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-c:v", "libx264", "-b:v", f"{video_bitrate_kbps}k",
            "-pass", "2", "-passlogfile", str(passlog),
            "-c:a", "aac", "-b:a", f"{audio_bitrate_kbps}k",
            "-movflags", "+faststart",
            str(tmp_output),
        ]
        logger.info("FFmpeg pass 2/2...")
        r2 = subprocess.run(pass2_cmd, capture_output=True, text=True)
        if r2.returncode != 0:
            logger.error("FFmpeg pass 2 failed:\n%s", r2.stderr)
            raise RuntimeError("FFmpeg two-pass compression failed on pass 2.")

        # Replace original with compressed version
        compressed_mb = tmp_output.stat().st_size / (1024 * 1024)
        video_path.unlink()
        tmp_output.rename(video_path)

        # Clean up passlog files (use passlog.name so the glob only matches
        # files like  *_final.ffmpeg2pass-0.log*  and NOT  *_final.mp4)
        for f in video_path.parent.glob(f"{passlog.name}*"):
            f.unlink(missing_ok=True)

        logger.info(
            "✓ Compressed: %.1f MB → %.1f MB (saved %.0f%%)",
            original_mb, compressed_mb,
            (1 - compressed_mb / original_mb) * 100,
        )
    # ── Remotion CLI trigger ──────────────────────────────────────────

    def _sync_public_assets(self) -> None:
        """Copy assets/ into remotion-vhs/public/assets/ so staticFile() works."""
        src = Path("assets")
        dst = self.remotion_dir / "public" / "assets"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info("Synced assets → %s", dst)

    @staticmethod
    def _regenerate_image(out_path: Path, block_id: int, chosen_style: str = "dark_comic") -> bool:
        """Re-generate a missing/corrupt image via the dedicated style agent.

        Returns True if a valid image was written, False otherwise.
        """
        fallback_prompt = (
            "Dark, atmospheric horror illustration. Shadowy figure in an "
            "abandoned location, unsettling mood, cinematic lighting, "
            "portrait orientation, high detail"
        )

        try:
            if chosen_style == "vintage_illustration":
                agent = VintageIllustrationImageGenerator()
            else:
                agent = DarkComicImageGenerator()

            out_path.parent.mkdir(parents=True, exist_ok=True)
            agent.generate_single_image(fallback_prompt, out_path)

            # Verify the downloaded file
            with PILImage.open(out_path) as im:
                im.verify()
            logger.info("  \u2713 Re-generated image saved: %s (%d bytes)", out_path, out_path.stat().st_size)
            return True
        except Exception as exc:
            logger.warning("  Image re-generation failed: %s", exc)
            return False

    @staticmethod
    def _validate_assets(case_id: str) -> None:
        """Check that every block's image and audio exist and are non-trivial.

        If an image is missing, too small (< 50 KB for a 1080×1920 JPEG), or
        fails Pillow decoding, attempt to re-generate it via Flux. Only if
        Flux also fails, copy the previous block's image as a last resort.
        """
        asset_dir = Path("assets") / f"case_{case_id}"
        props_path = asset_dir / "remotion_props.json"
        if not props_path.is_file():
            return

        props = json.loads(props_path.read_text(encoding="utf-8"))
        chosen_style = props.get("chosenStyle", "dark_comic")
        prev_image: Path | None = None
        MIN_IMAGE_BYTES = 50_000  # 50 KB — a valid 1080×1920 JPEG is 200 KB+

        for seq in props.get("sequences", []):
            img = Path(seq.get("imagePath", ""))
            audio = Path(seq.get("audioPath", ""))

            if not audio.is_file():
                logger.warning("Block %s: audio missing — %s", seq["blockId"], audio)

            image_ok = False
            if img.is_file() and img.stat().st_size >= MIN_IMAGE_BYTES:
                # Verify the file is actually a decodable image
                try:
                    with PILImage.open(img) as im:
                        im.verify()
                    image_ok = True
                except Exception as exc:
                    logger.warning(
                        "Block %s: image failed Pillow verify (%s) — %s",
                        seq["blockId"], img, exc,
                    )

            if image_ok:
                prev_image = img
            else:
                logger.warning(
                    "Block %s: image missing/corrupt (%s) — attempting Flux re-generation",
                    seq["blockId"], img,
                )
                regenerated = RemotionComposer._regenerate_image(img, seq["blockId"], chosen_style)
                if regenerated:
                    prev_image = img
                elif prev_image and prev_image.is_file():
                    logger.warning(
                        "Block %s: Flux re-generation failed — last-resort copy from %s",
                        seq["blockId"], prev_image,
                    )
                    img.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(prev_image, img)
                else:
                    logger.error("Block %s: image missing, Flux failed, and no fallback available.", seq["blockId"])

    def _render(self, case_id: str, props_path: Path) -> None:
        """Invoke the Remotion CLI to render the final video."""
        self._validate_assets(case_id)
        self._sync_public_assets()

        out_dir = Path.cwd() / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"case_{case_id}_final.mp4"

        # Props were synced into remotion-vhs/public/assets/ — resolve
        # the path relative to the remotion working directory.
        synced_props = self.remotion_dir / "public" / "assets" / f"case_{case_id}" / "remotion_props.json"
        props_rel = synced_props.relative_to(self.remotion_dir).as_posix()

        out_file_str = f'"{out_file.resolve()}"'

        cmd = (
            f'npx remotion render RootComposition {out_file_str}'
            f' "--props={props_rel}"'
            f' --concurrency=1 --gl=angle --timeout=120000'
        )

        logger.info("Rendering video: %s", cmd)
        logger.info("Working directory: %s", self.remotion_dir)

        result = subprocess.run(
            cmd,
            cwd=str(self.remotion_dir),
            capture_output=True,
            text=True,
            shell=True,
        )

        if result.returncode != 0:
            logger.error("Remotion render STDERR:\n%s", result.stderr)
            raise RuntimeError(
                f"Remotion render failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

        logger.info("Remotion render STDOUT:\n%s", result.stdout)
        logger.info("✓ Final video: %s", out_file)

        # ── Post-render: enforce file-size ceiling ────────────────────
        if out_file.exists() and out_file.stat().st_size > MAX_FILE_SIZE_BYTES:
            self._compress_to_limit(out_file)
