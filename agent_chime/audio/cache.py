"""LRU audio cache for synthesized speech."""

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_MAX_SIZE_MB = 100
DEFAULT_MAX_ENTRIES = 1000


@dataclass
class CacheEntry:
    """Metadata for a cached audio file."""

    path: Path
    text: str
    voice: str
    model: str
    size_bytes: int
    created_at: float
    last_accessed: float


class AudioCache:
    """
    LRU cache for synthesized audio files.

    Keyed by (text, voice, model) and stored at ~/.cache/agent-chime/
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        max_size_mb: int = DEFAULT_MAX_SIZE_MB,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        self.cache_dir = cache_dir or Path.home() / ".cache" / "agent-chime"
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_entries = max_entries

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # In-memory index of cache entries
        self._index: dict[str, CacheEntry] = {}
        self._load_index()

    def _cache_key(self, text: str, voice: str, model: str) -> str:
        """Generate a cache key from synthesis parameters."""
        content = f"{text}|{voice}|{model}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{key}.wav"

    def get(self, text: str, voice: str, model: str) -> bytes | None:
        """
        Get cached audio if available.

        Args:
            text: The synthesized text
            voice: The voice used
            model: The model used

        Returns:
            WAV bytes if cached, None otherwise
        """
        key = self._cache_key(text, voice, model)
        entry = self._index.get(key)

        if entry is None:
            return None

        if not entry.path.exists():
            # File was deleted externally
            del self._index[key]
            return None

        # Update access time
        entry.last_accessed = time.time()

        try:
            return entry.path.read_bytes()
        except OSError as e:
            logger.warning(f"Failed to read cache entry {key}: {e}")
            return None

    def put(self, text: str, voice: str, model: str, audio: bytes) -> None:
        """
        Cache synthesized audio.

        Args:
            text: The synthesized text
            voice: The voice used
            model: The model used
            audio: The WAV audio bytes
        """
        key = self._cache_key(text, voice, model)
        path = self._cache_path(key)

        # Evict if necessary before adding
        self._evict_if_needed(len(audio))

        try:
            path.write_bytes(audio)
            self._index[key] = CacheEntry(
                path=path,
                text=text,
                voice=voice,
                model=model,
                size_bytes=len(audio),
                created_at=time.time(),
                last_accessed=time.time(),
            )
            logger.debug(f"Cached audio for '{text[:30]}...' ({len(audio)} bytes)")
        except OSError as e:
            logger.warning(f"Failed to cache audio: {e}")

    def _evict_if_needed(self, new_size: int) -> None:
        """Evict oldest entries if cache is full."""
        current_size = sum(e.size_bytes for e in self._index.values())

        # Check entry count
        while len(self._index) >= self.max_entries:
            self._evict_oldest()

        # Check size
        while current_size + new_size > self.max_size_bytes and self._index:
            evicted_size = self._evict_oldest()
            current_size -= evicted_size

    def _evict_oldest(self) -> int:
        """Evict the least recently accessed entry. Returns size of evicted entry."""
        if not self._index:
            return 0

        # Find LRU entry
        oldest_key = min(self._index, key=lambda k: self._index[k].last_accessed)
        entry = self._index[oldest_key]

        try:
            entry.path.unlink(missing_ok=True)
        except OSError:
            pass

        del self._index[oldest_key]
        logger.debug(f"Evicted cache entry {oldest_key}")
        return entry.size_bytes

    def _load_index(self) -> None:
        """Load existing cache entries from disk."""
        self._index.clear()

        if not self.cache_dir.exists():
            return

        for path in self.cache_dir.glob("*.wav"):
            try:
                stat = path.stat()
                key = path.stem

                # We don't have the original text/voice/model, so store placeholders
                self._index[key] = CacheEntry(
                    path=path,
                    text="",
                    voice="",
                    model="",
                    size_bytes=stat.st_size,
                    created_at=stat.st_ctime,
                    last_accessed=stat.st_atime,
                )
            except OSError:
                continue

        logger.debug(f"Loaded {len(self._index)} cache entries")

    def clear(self) -> None:
        """Clear all cache entries."""
        for entry in self._index.values():
            try:
                entry.path.unlink(missing_ok=True)
            except OSError:
                pass

        self._index.clear()
        logger.info("Cache cleared")

    @property
    def size_bytes(self) -> int:
        """Get total size of cached files in bytes."""
        return sum(e.size_bytes for e in self._index.values())

    @property
    def entry_count(self) -> int:
        """Get number of cached entries."""
        return len(self._index)

    def stats(self) -> dict[str, int | float]:
        """Get cache statistics."""
        return {
            "entries": self.entry_count,
            "size_bytes": self.size_bytes,
            "size_mb": self.size_bytes / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "max_entries": self.max_entries,
        }
