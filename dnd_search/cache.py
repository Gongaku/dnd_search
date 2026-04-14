"""Simple file-based HTTP response cache."""

import base64
import gzip
import hashlib
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "dnd-search"

# Bump this integer whenever the on-disk cache format changes (new keys,
# restructured content, etc.).  Any entry written under an older version is
# silently treated as a miss and overwritten.
CACHE_VERSION = 3

# TTLs — override via env vars (seconds).
# Raw HTML pages (keyed by bare URL) refresh weekly by default.
HTML_TTL = int(os.getenv("DND_CACHE_TTL", str(60 * 60 * 24 * 7)))
# Parsed detail blobs (keyed "prefix:url") are stable; refresh monthly.
DETAIL_TTL = int(os.getenv("DND_DETAIL_CACHE_TTL", str(60 * 60 * 24 * 30)))

# Maximum number of cache entries before prune() evicts the oldest ones.
MAX_ENTRIES = int(os.getenv("DND_CACHE_MAX_ENTRIES", "500"))


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{hashlib.md5(key.encode('utf-8')).hexdigest()}.json"


def _ttl_for(key: str) -> int:
    """Return the appropriate TTL based on whether this is a parsed-detail key."""
    return DETAIL_TTL if ":" in key else HTML_TTL


def get(key: str) -> str | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("v", 1) != CACHE_VERSION:
            logger.debug(f"Cache version mismatch for {key}, evicting")
            path.unlink(missing_ok=True)
            return None
        if time.time() - data["timestamp"] > _ttl_for(key):
            logger.debug(f"Cache expired for {key}")
            path.unlink(missing_ok=True)
            return None
        logger.debug(f"Cache hit for {key}")
        content = data["content"]
        if data.get("gz"):
            content = gzip.decompress(base64.b64decode(content)).decode("utf-8")
        return content
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def set(key: str, content: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(key)
    tmp = path.with_suffix(".tmp")
    try:
        compressed = base64.b64encode(gzip.compress(content.encode("utf-8"))).decode("ascii")
        tmp.write_text(
            json.dumps(
                {
                    "v": CACHE_VERSION,
                    "timestamp": time.time(),
                    "content": compressed,
                    "gz": True,
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
        logger.debug(f"Cached response for {key}")
    except OSError as e:
        logger.warning(f"Failed to write cache: {e}")
        tmp.unlink(missing_ok=True)


def prune() -> int:
    """Delete expired entries and, if still over MAX_ENTRIES, evict oldest first.

    Returns the number of files removed.
    """
    if not CACHE_DIR.exists():
        return 0
    now = time.time()
    removed = 0
    entries: list[tuple[float, Path]] = []  # (timestamp, path)

    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("v", 1) != CACHE_VERSION:
                f.unlink(missing_ok=True)
                removed += 1
                continue
            age = now - data["timestamp"]
            # Use the longer TTL conservatively — we don't know the original key.
            if age > HTML_TTL:
                f.unlink(missing_ok=True)
                removed += 1
            else:
                entries.append((data["timestamp"], f))
        except (json.JSONDecodeError, KeyError, OSError):
            f.unlink(missing_ok=True)
            removed += 1

    # Evict oldest entries if still over the size cap.
    if len(entries) > MAX_ENTRIES:
        entries.sort()  # ascending by timestamp → oldest first
        for _, f in entries[: len(entries) - MAX_ENTRIES]:
            f.unlink(missing_ok=True)
            removed += 1

    return removed


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
            data = json.loads(f.read_text(encoding="utf-8"))
            age = now - data["timestamp"]
            ages.append(age)
            total_bytes += f.stat().st_size
            if age > HTML_TTL:
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
