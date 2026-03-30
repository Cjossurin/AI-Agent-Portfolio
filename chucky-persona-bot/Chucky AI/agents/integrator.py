"""The Media Integrator — Agent 4 of the Chucky AI pipeline.

Generates audio (ElevenLabs) and scare videos (Fal.ai Kling) from the
storyboard produced by Agent 3.  Image generation is handled by the
dedicated style agents (image_dark_comic / image_vintage).
"""

import base64
import logging
import mimetypes
import os
import time
from pathlib import Path

import fal_client
import requests
from elevenlabs import ElevenLabs
from prompt_templates import CHUCKY_KLING_SAFE_MOTION_PROMPT

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # "Adam" — swap for your preferred creepy voice
KLING_MODEL_ID = "fal-ai/kling-video/v1/standard/image-to-video"

KLING_SAFE_MOTION_PROMPT = CHUCKY_KLING_SAFE_MOTION_PROMPT

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
API_TIMEOUT = 300  # seconds — for download and API subscription calls


class MediaIntegrator:
    """Generates audio, images, and scare clips for each storyboard block."""

    def __init__(self, voice_id: str = DEFAULT_VOICE_ID):
        el_key = os.getenv("ELEVENLABS_API_KEY")
        if not el_key:
            raise EnvironmentError(
                "ELEVENLABS_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        fal_key = os.getenv("FAL_AI_API_KEY")
        if not fal_key:
            raise EnvironmentError(
                "FAL_AI_API_KEY is not set. "
                "Copy .env.example to .env and add your key."
            )

        # fal-client reads FAL_KEY from env
        os.environ["FAL_KEY"] = fal_key

        self.el_client = ElevenLabs(api_key=el_key)
        self.voice_id = voice_id

    # ── Directory setup ───────────────────────────────────────────────

    @staticmethod
    def setup_directories(case_id: str) -> Path:
        """Create and return the asset folder for this case."""
        asset_dir = Path("assets") / f"case_{case_id}"
        asset_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Asset directory ready: %s", asset_dir)
        return asset_dir

    # ── Core generation loop ──────────────────────────────────────────

    def generate_media(
        self,
        storyboard_json: dict,
        case_id: str,
        image_results: list[dict] | None = None,
    ) -> dict:
        """Loop through storyboard blocks and generate audio + scare videos.

        *image_results* is a list of ``{"block_id", "image_path", "image_url"}``
        dicts produced by the dedicated image agent.  When provided, skips
        image generation entirely.
        """
        blocks = storyboard_json.get("storyboard", [])
        if not blocks:
            raise ValueError("storyboard_json must contain a non-empty 'storyboard' array.")

        chosen_style = storyboard_json.get("chosen_style", "")
        asset_dir = self.setup_directories(case_id)

        # Index pre-generated images by block_id
        img_map: dict[int, dict] = {}
        if image_results:
            for img in image_results:
                img_map[img["block_id"]] = img

        manifest: list[dict] = []

        for entry in blocks:
            bid = entry["block_id"]
            audio_text = entry.get("audio_text", "")
            motion_type = entry.get("motion_type", "ken_burns_zoom_in")

            logger.info("── Block %d ──", bid)
            block_result: dict = {"block_id": bid, "motion_type": motion_type}

            # 1) Audio — ElevenLabs
            audio_path = asset_dir / f"{bid}_audio.mp3"
            if audio_text:
                self._generate_audio(audio_text, audio_path)
                block_result["audio_path"] = str(audio_path)
            else:
                logger.warning("Block %d has no audio_text — skipping audio.", bid)

            # 2) Image — provided by image agent
            if bid in img_map:
                block_result["image_path"] = img_map[bid]["image_path"]
                block_result["image_url"] = img_map[bid].get("image_url", "")
            else:
                logger.warning("Block %d: no pre-generated image found.", bid)

            # 3) Scare video — Kling image-to-video from the block's image
            image_path = Path(block_result.get("image_path", ""))
            if motion_type == "kling_i2v_scare" and image_path.is_file():
                video_path = asset_dir / f"{bid}_scare.mp4"
                image_data_uri = self.encode_local_image_to_data_uri(image_path)
                self._generate_scare_video(image_data_uri, out_path=video_path)
                block_result["video_path"] = str(video_path)

            manifest.append(block_result)

        result = {
            "case_id": case_id,
            "asset_dir": str(asset_dir),
            "blocks": manifest,
            "chosen_style": chosen_style,
        }
        logger.info("Media generation complete for case_%s.", case_id)
        return result

    # ── ElevenLabs TTS ────────────────────────────────────────────────

    def _generate_audio(self, text: str, out_path: Path) -> None:
        """Generate speech from text and save as MP3."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("  Generating audio → %s (attempt %d)", out_path.name, attempt)
                audio_iter = self.el_client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=text,
                    model_id="eleven_multilingual_v2",
                    output_format="mp3_44100_128",
                )
                with open(out_path, "wb") as f:
                    for chunk in audio_iter:
                        f.write(chunk)
                logger.info("  ✓ Audio saved: %s", out_path)
                return
            except (requests.exceptions.Timeout, TimeoutError) as exc:
                logger.warning("  Audio attempt %d timed out: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
            except Exception as exc:
                logger.warning("  Audio attempt %d failed: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise RuntimeError(f"Failed to generate audio after {MAX_RETRIES} attempts: {out_path}")

    # ── Image encoding helper ─────────────────────────────────────────

    @staticmethod
    def encode_local_image_to_data_uri(file_path: str | Path) -> str:
        """Read a local image file and return a base64 Data URI string.

        e.g. ``data:image/png;base64,iVBOR...``
        """
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime_type};base64,{b64}"

    # ── Fal.ai Kling scare video (image-to-video) ────────────────────

    def _generate_scare_video(self, image_url: str, out_path: Path) -> None:
        """Send a styled frame to Kling for Image-to-Video and save the clip."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("  Generating scare video → %s (attempt %d)", out_path.name, attempt)
                result = fal_client.subscribe(
                    KLING_MODEL_ID,
                    arguments={
                        "image_url": image_url,
                        "prompt": KLING_SAFE_MOTION_PROMPT,
                        "duration": "5",
                        "aspect_ratio": "9:16",
                    },
                    with_logs=False,
                )
                video_url = result["video"]["url"]
                self._download_file(video_url, out_path)
                logger.info("  ✓ Scare video saved: %s", out_path)
                return
            except (requests.exceptions.Timeout, TimeoutError) as exc:
                logger.warning("  Scare video attempt %d timed out: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
            except Exception as exc:
                logger.warning("  Scare video attempt %d failed: %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise RuntimeError(f"Failed to generate scare video after {MAX_RETRIES} attempts: {out_path}")

    # ── Download helper ───────────────────────────────────────────────

    @staticmethod
    def _download_file(url: str, out_path: Path, min_size: int = 0) -> None:
        """Download a file from a URL to a local path.

        If *min_size* > 0, retry once when the downloaded file is smaller
        than expected (catches truncated CDN responses).
        """
        for dl_attempt in range(2):
            resp = requests.get(url, timeout=API_TIMEOUT)
            resp.raise_for_status()
            data = resp.content

            # Check Content-Length header vs actual bytes
            expected = resp.headers.get("Content-Length")
            if expected and len(data) < int(expected):
                logger.warning(
                    "Truncated download: got %d bytes, expected %s — retrying",
                    len(data), expected,
                )
                if dl_attempt == 0:
                    continue

            with open(out_path, "wb") as f:
                f.write(data)

            # Minimum-size safety net for images
            if min_size and len(data) < min_size:
                logger.warning(
                    "Downloaded file %s is only %d bytes (min %d) — retrying",
                    out_path.name, len(data), min_size,
                )
                if dl_attempt == 0:
                    continue

            return

        logger.warning("Download for %s below expectations after retry.", out_path.name)
