"""Simple file-based HTTP response cache."""

import gzip
import hashlib
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "dnd-search"
# Override with DND_CACHE_TTL env var (seconds). Default: 7 days.
DEFAULT_TTL = int(os.getenv("DND_CACHE_TTL", str(60 * 60 * 24 * 7)))


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{hashlib.md5(key.encode()).hexdigest()}.json"


def get(key: str) -> str | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["timestamp"] > DEFAULT_TTL:
            logger.debug(f"Cache expired for {key}")
            path.unlink(missing_ok=True)
            return None
        logger.debug(f"Cache hit for {key}")
        content = data["content"]
        if data.get("gz"):
            content = gzip.decompress(bytes.fromhex(content)).decode()
        return content
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def set(key: str, content: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    try:
        compressed = gzip.compress(content.encode()).hex()
        path.write_text(
            json.dumps({"timestamp": time.time(), "content": compressed, "gz": True})
        )
        logger.debug(f"Cached response for {key}")
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


def stats() -> dict:
    """Return cache statistics: entry count, expired count, disk usage, age range."""
    if not CACHE_DIR.exists():
        return {"count": 0, "expired": 0, "bytes": 0, "oldest_age": 0, "newest_age": 0}
    now = time.time()
    count = expired = total_bytes = 0
    ages: list[float] = []
    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            age = now - data["timestamp"]
            ages.append(age)
            total_bytes += f.stat().st_size
            if age > DEFAULT_TTL:
                expired += 1
            count += 1
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return {
        "count": count,
        "expired": expired,
        "bytes": total_bytes,
        "oldest_age": max(ages) if ages else 0,
        "newest_age": min(ages) if ages else 0,
    }
