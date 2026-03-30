"""
Media Upload Utilities — upload local files to temporary public hosts.

Used by the scheduler to get public URLs for generated video/image files
so they can be posted via Late API (which requires ``mediaUrls``).

Hosts tried (in order):
1. **Catbox.moe** — free, no auth, 200 MB limit, supports video
2. **file.io** — free, no auth, one-time download, 100 MB limit
"""

import os
import logging
import httpx
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


async def upload_to_catbox(file_path: str) -> Optional[str]:
    """
    Upload a file to catbox.moe (free anonymous hosting).

    Returns a public URL like ``https://files.catbox.moe/abc123.mp4``
    or ``None`` on failure.
    """
    if not os.path.isfile(file_path):
        logger.warning(f"upload_to_catbox: file not found: {file_path}")
        return None

    try:
        filename = os.path.basename(file_path)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        timeout = max(120.0, 120.0 + file_size_mb * 2)  # Scale with size
        logger.info(f"Uploading to catbox: {filename} ({file_size_mb:.1f} MB, timeout={timeout:.0f}s)")
        async with httpx.AsyncClient(timeout=timeout) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": (filename, f)},
                )
            if response.status_code == 200 and response.text.startswith("https://"):
                url = response.text.strip()
                logger.info(f"Uploaded to catbox: {url}")
                return url
            else:
                logger.warning(f"Catbox upload failed: {response.status_code} — {response.text[:200]}")
                return None
    except Exception as e:
        logger.warning(f"Catbox upload error: {e}")
        return None


async def upload_to_fileio(file_path: str) -> Optional[str]:
    """
    Upload a file to file.io (free, one-time download link).

    Returns a public URL or ``None`` on failure.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        filename = os.path.basename(file_path)
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    "https://file.io",
                    files={"file": (filename, f)},
                    data={"expires": "1d"},
                )
            data = response.json()
            if data.get("success") and data.get("link"):
                url = data["link"]
                logger.info(f"Uploaded to file.io: {url}")
                return url
            else:
                logger.warning(f"file.io upload failed: {data}")
                return None
    except Exception as e:
        logger.warning(f"file.io upload error: {e}")
        return None


async def upload_media_file(file_path: str) -> Optional[str]:
    """
    Upload a local media file and return a public URL.

    Tries multiple hosts in order until one succeeds.
    Returns ``None`` if all fail.
    """
    # Try catbox first (best for video — persistent URLs, 200 MB)
    url = await upload_to_catbox(file_path)
    if url:
        return url

    # Fallback: file.io (one-time download, but works in a pinch)
    url = await upload_to_fileio(file_path)
    if url:
        return url

    logger.error(f"All upload hosts failed for: {file_path}")
    return None
