"""Audio renderer for playback via afplay."""

import logging
import subprocess
import tempfile
import threading
from pathlib import Path

from agent_chime.audio.cache import AudioCache
from agent_chime.events import EventType
from agent_chime.tts.broker import get_earcon_name

logger = logging.getLogger(__name__)


class PlaybackError(Exception):
    """Error during audio playback."""


class AudioRenderer:
    """
    Renders audio for playback using macOS afplay.

    Supports:
    - WAV playback from bytes
    - Streaming playback (progressive updates)
    - Earcon fallback
    - Volume control
    """

    def __init__(
        self,
        volume: float = 0.8,
        cache: AudioCache | None = None,
        earcons_dir: Path | None = None,
    ) -> None:
        self.volume = max(0.0, min(1.0, volume))
        self.cache = cache
        self.earcons_dir = earcons_dir or self._default_earcons_dir()

        self._current_process: subprocess.Popen | None = None
        self._temp_file: Path | None = None
        self._lock = threading.Lock()

    def _default_earcons_dir(self) -> Path:
        """Get the default earcons directory (bundled with package)."""
        # Try package directory first
        package_dir = Path(__file__).parent.parent.parent / "earcons"
        if package_dir.exists():
            return package_dir

        # Fall back to home directory
        return Path.home() / ".config" / "agent-chime" / "earcons"

    def play(self, audio: bytes, blocking: bool = True) -> None:
        """
        Play audio from WAV bytes.

        Args:
            audio: WAV audio bytes
            blocking: If True, wait for playback to complete
        """
        with self._lock:
            self._stop_current()

            # Write to temp file
            self._temp_file = Path(tempfile.mktemp(suffix=".wav"))
            self._temp_file.write_bytes(audio)

            self._play_file(self._temp_file, blocking=blocking)

    def play_streaming(self, audio: bytes) -> None:
        """
        Update audio during streaming playback.

        Writes updated audio to temp file. The player will read the
        growing file for progressive playback.

        Note: afplay doesn't support true streaming, so this just
        updates the file and restarts playback if needed.
        """
        with self._lock:
            if self._temp_file is None:
                # First chunk - start playback
                self._temp_file = Path(tempfile.mktemp(suffix=".wav"))

            self._temp_file.write_bytes(audio)

            # If not already playing, start
            if self._current_process is None or self._current_process.poll() is not None:
                self._play_file(self._temp_file, blocking=False)

    def play_earcon(self, event_type: EventType, blocking: bool = True) -> bool:
        """
        Play an earcon for the given event type.

        Args:
            event_type: The event type to get earcon for
            blocking: If True, wait for playback to complete

        Returns:
            True if earcon was played, False if not found
        """
        earcon_name = get_earcon_name(event_type)
        earcon_path = self.earcons_dir / earcon_name

        if not earcon_path.exists():
            logger.warning(f"Earcon not found: {earcon_path}")
            return False

        with self._lock:
            self._stop_current()
            self._play_file(earcon_path, blocking=blocking)

        return True

    def _play_file(self, path: Path, blocking: bool = True) -> None:
        """Play an audio file using afplay."""
        if not path.exists():
            raise PlaybackError(f"Audio file not found: {path}")

        cmd = ["afplay", "-v", str(self.volume), str(path)]

        try:
            if blocking:
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                self._current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except subprocess.CalledProcessError as e:
            raise PlaybackError(f"afplay failed: {e}") from e
        except FileNotFoundError:
            raise PlaybackError("afplay not found - this requires macOS")

    def _stop_current(self) -> None:
        """Stop any currently playing audio."""
        if self._current_process is not None:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._current_process.kill()
            self._current_process = None

        # Clean up temp file
        if self._temp_file is not None:
            try:
                self._temp_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._temp_file = None

    def stop(self) -> None:
        """Stop playback and clean up."""
        with self._lock:
            self._stop_current()

    def wait(self, timeout: float | None = None) -> bool:
        """
        Wait for current playback to complete.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if playback completed, False if timed out
        """
        if self._current_process is None:
            return True

        try:
            self._current_process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def __del__(self) -> None:
        """Clean up on destruction."""
        self.stop()


class AudioRendererPool:
    """
    Pool for reusing AudioRenderer instances.

    Maintains a single renderer to avoid resource conflicts.
    """

    _instance: "AudioRendererPool | None" = None
    _renderer: AudioRenderer | None = None

    @classmethod
    def get_instance(cls) -> "AudioRendererPool":
        """Get the singleton pool instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_renderer(
        self,
        volume: float = 0.8,
        cache: AudioCache | None = None,
        earcons_dir: Path | None = None,
    ) -> AudioRenderer:
        """Get or create an audio renderer."""
        if self._renderer is None:
            self._renderer = AudioRenderer(
                volume=volume,
                cache=cache,
                earcons_dir=earcons_dir,
            )
        else:
            # Update settings
            self._renderer.volume = volume
            if cache is not None:
                self._renderer.cache = cache
            if earcons_dir is not None:
                self._renderer.earcons_dir = earcons_dir

        return self._renderer

    def clear(self) -> None:
        """Stop and clear the renderer."""
        if self._renderer is not None:
            self._renderer.stop()
            self._renderer = None
