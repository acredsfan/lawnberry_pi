"""Utilities for working with cached camera frames shared across services."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CACHE_PATH = Path(os.getenv("LAWNBERY_CAMERA_CACHE_PATH", "/var/lib/lawnberry/camera/latest.jpg"))
META_PATH = Path(
    os.getenv("LAWNBERY_CAMERA_META_PATH", str(CACHE_PATH.with_suffix(".json")))
)


async def load_cached_frame() -> Optional[Tuple[bytes, Dict[str, Any]]]:
    """Load the most recent cached camera frame if available.

    Returns a tuple of raw JPEG bytes and associated metadata dictionary.
    """

    try:
        frame_bytes = await asyncio.to_thread(CACHE_PATH.read_bytes)
    except FileNotFoundError:
        return None
    except Exception:
        return None

    metadata: Dict[str, Any] = {}
    try:
        meta_text = await asyncio.to_thread(META_PATH.read_text, encoding="utf-8")
        metadata = json.loads(meta_text)
    except FileNotFoundError:
        metadata = {}
    except json.JSONDecodeError:
        metadata = {}
    except Exception:
        metadata = {}

    return frame_bytes, metadata


def get_cache_mtime() -> Optional[float]:
    """Return last modification time of cached frame, if present."""

    try:
        return CACHE_PATH.stat().st_mtime
    except FileNotFoundError:
        return None
    except Exception:
        return None

