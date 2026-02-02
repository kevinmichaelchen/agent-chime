"""TTS components for agent-chime."""

from agent_chime.tts.broker import TTSBroker
from agent_chime.tts.models import MODELS, ModelSpec, ModelTier

# Lazy import for TTSProvider to avoid loading numpy at import time
def __getattr__(name: str):
    if name == "TTSProvider":
        from agent_chime.tts.provider import TTSProvider
        return TTSProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["TTSProvider", "TTSBroker", "ModelTier", "ModelSpec", "MODELS"]
