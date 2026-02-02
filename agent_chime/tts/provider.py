"""TTS provider with model management and fallback chain."""

import io
import logging
import tempfile
import wave
from pathlib import Path
from typing import Any

from agent_chime.system.model_selector import ModelSelector, SelectionResult
from agent_chime.tts.models import MODELS, ModelSpec, ModelTier, get_fallback_model

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """Error during TTS synthesis."""


class TTSProvider:
    """
    TTS provider using mlx-audio's generate_audio function.

    Fallback order: primary model → kokoro → earcon (handled by caller)
    """

    def __init__(
        self,
        model_id: str | None = None,
        voice: str | None = None,
        stream: bool = True,
        streaming_interval: float = 0.5,
    ) -> None:
        self.model_id = model_id
        self.voice = voice
        self.stream = stream
        self.streaming_interval = streaming_interval

        self._selected_result: SelectionResult | None = None
        self._model_spec: ModelSpec | None = None

    @property
    def current_model(self) -> ModelSpec | None:
        """Get the currently selected model spec."""
        return self._model_spec

    @property
    def sample_rate(self) -> int:
        """Get the sample rate (most models use 16000)."""
        return 16000

    def _select_model(self) -> None:
        """Select the best model based on system resources."""
        if self._model_spec is not None:
            return

        from agent_chime.system.model_selector import SelectionMode

        selector = ModelSelector()
        # Use MANUAL mode if user specified a model
        mode = SelectionMode.MANUAL if self.model_id else SelectionMode.AUTO
        self._selected_result = selector.select(user_preference=self.model_id, mode=mode)
        self._model_spec = self._selected_result.model

        logger.info(f"Selected TTS model: {self._model_spec.model_id}")

    def _get_voice(self) -> str | None:
        """Get the voice to use, either user-specified or model default."""
        if self.voice:
            return self.voice
        if self._model_spec and self._model_spec.default_voice:
            return self._model_spec.default_voice
        return None

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to WAV audio bytes.

        Args:
            text: Text to synthesize

        Returns:
            WAV audio as bytes
        """
        self._select_model()
        assert self._model_spec is not None

        voice = self._get_voice()
        logger.debug(f"Synthesizing: '{text}' with model '{self._model_spec.model_id}'")

        try:
            return self._generate_with_model(text, self._model_spec, voice)
        except Exception as e:
            logger.error(f"Synthesis failed with {self._model_spec.model_id}: {e}")

            # Try fallback to Kokoro if not already
            fallback = get_fallback_model()
            if self._model_spec.model_id != fallback.model_id:
                logger.info(f"Falling back to {fallback.model_id}")
                try:
                    self._model_spec = fallback
                    return self._generate_with_model(text, fallback, fallback.default_voice)
                except Exception as e2:
                    raise TTSError(f"Failed with fallback model: {e2}") from e

            raise TTSError(f"Synthesis failed: {e}") from e

    def _generate_with_model(
        self,
        text: str,
        model_spec: ModelSpec,
        voice: str | None,
    ) -> bytes:
        """Generate audio using mlx-audio's generate_audio function."""
        try:
            from mlx_audio.tts.generate import generate_audio
        except ImportError as e:
            raise TTSError("mlx-audio not installed") from e

        # Create a temp file for output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = Path(f.name)
            file_prefix = str(output_path.with_suffix(""))

        try:
            # Build kwargs for generate_audio
            kwargs: dict[str, Any] = {
                "text": text,
                "model": model_spec.model_id,
                "file_prefix": file_prefix,
                "verbose": False,
                "play": False,
                "lang_code": model_spec.lang_code,
            }

            # Add voice if specified and model supports it
            if voice:
                kwargs["voice"] = voice

            # Call generate_audio
            generate_audio(**kwargs)

            # Read the generated file
            # generate_audio appends _000 to the file prefix
            actual_output = Path(f"{file_prefix}_000.wav")
            if not actual_output.exists():
                # Try without the suffix
                actual_output = output_path
                if not actual_output.exists():
                    raise TTSError(f"Output file not found: {actual_output}")

            audio_bytes = actual_output.read_bytes()

            # Clean up
            actual_output.unlink(missing_ok=True)

            return audio_bytes

        except Exception as e:
            # Clean up on error
            output_path.unlink(missing_ok=True)
            Path(f"{file_prefix}_000.wav").unlink(missing_ok=True)
            raise

    def synthesize_stream(self, text: str):
        """
        Synthesize text to WAV audio bytes.

        Note: mlx-audio's streaming is file-based, so we just return
        the full audio as a single chunk for now.

        Args:
            text: Text to synthesize

        Yields:
            WAV audio bytes (single chunk)
        """
        audio = self.synthesize(text)
        yield audio


class TTSProviderPool:
    """
    Pool of TTS providers for reuse.

    Maintains a single provider instance to avoid repeated model loading.
    """

    _instance: "TTSProviderPool | None" = None
    _provider: TTSProvider | None = None

    @classmethod
    def get_instance(cls) -> "TTSProviderPool":
        """Get the singleton pool instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_provider(
        self,
        model_id: str | None = None,
        voice: str | None = None,
        stream: bool = True,
    ) -> TTSProvider:
        """Get or create a TTS provider with the specified settings."""
        # If we have a provider with matching settings, return it
        if self._provider is not None:
            if (
                self._provider.model_id == model_id
                and self._provider.voice == voice
                and self._provider.stream == stream
            ):
                return self._provider

        # Create new provider
        self._provider = TTSProvider(
            model_id=model_id,
            voice=voice,
            stream=stream,
        )
        return self._provider

    def clear(self) -> None:
        """Clear the pool."""
        self._provider = None
