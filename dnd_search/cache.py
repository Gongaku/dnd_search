"""Simple file-based HTTP response cache."""

import hashlib
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "dnd-search"
DEFAULT_TTL = 60 * 60 * 24  # 24 hours


def _cache_path(url: str) -> Path:
    key = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def get(url: str) -> str | None:
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["timestamp"] > DEFAULT_TTL:
            logger.debug(f"Cache expired for {url}")
            path.unlink(missing_ok=True)
            return None
        logger.debug(f"Cache hit for {url}")
        return data["content"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def set(url: str, content: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url)
    try:
        path.write_text(json.dumps({"timestamp": time.time(), "content": content}))
        logger.debug(f"Cached response for {url}")
    except OSError as e:
        logger.warning(f"Failed to write cache: {e}")


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink(missing_ok=True)
        count += 1
    return count
