"""TTS model definitions and registry."""

from dataclasses import dataclass
from enum import Enum


class ModelTier(Enum):
    """Model quality/resource tiers."""

    VOICE_DESIGN = "voice_design"  # Highest quality with emotion control (1.7B params)
    SPARK = "spark"  # High quality (0.5B params)
    SPARK_QUANTIZED = "spark_quantized"  # Quantized, smaller memory
    POCKET = "pocket"  # Fastest, smallest (~1GB memory)


@dataclass(frozen=True)
class ModelSpec:
    """Specification for a TTS model."""

    model_id: str
    estimated_memory_gb: float
    realtime_factor: float  # Higher = faster (e.g., 1.34x means faster than realtime)
    default_voice: str
    requires_metal: bool = False
    description: str = ""
    lang_code: str = "en"  # Language code for the model
    supports_instruct: bool = False  # Whether model supports emotion/style control via instruct
    default_instruct: str = ""  # Default instruct for emotion control

    @property
    def is_pocket(self) -> bool:
        """Check if this is a pocket-tts model."""
        return "pocket" in self.model_id.lower()

    @property
    def is_voice_design(self) -> bool:
        """Check if this is a VoiceDesign model with emotion control."""
        return self.supports_instruct


# Model registry ordered by quality (highest first)
MODELS: dict[ModelTier, ModelSpec] = {
    ModelTier.VOICE_DESIGN: ModelSpec(
        model_id="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
        estimated_memory_gb=7.0,
        realtime_factor=0.8,
        default_voice="",  # VoiceDesign uses instruct instead of voice
        requires_metal=True,
        description="Highest quality with emotion/style control via natural language",
        lang_code="en",
        supports_instruct=True,
        default_instruct="A calm, professional voice with clear enunciation",
    ),
    ModelTier.SPARK: ModelSpec(
        model_id="mlx-community/Spark-TTS-0.5B-bf16",
        estimated_memory_gb=3.0,
        realtime_factor=0.3,
        default_voice="",  # Spark doesn't require a voice parameter
        requires_metal=True,
        description="Best quality, requires ≥4GB available RAM",
        lang_code="en",
    ),
    ModelTier.SPARK_QUANTIZED: ModelSpec(
        model_id="mlx-community/Spark-TTS-0.5B-8bit",
        estimated_memory_gb=2.0,
        realtime_factor=0.3,
        default_voice="",  # Spark doesn't require a voice parameter
        requires_metal=True,
        description="Quantized version, smaller memory footprint",
        lang_code="en",
    ),
    ModelTier.POCKET: ModelSpec(
        model_id="mlx-community/pocket-tts",
        estimated_memory_gb=1.0,
        realtime_factor=1.34,
        default_voice="",  # pocket-tts doesn't require a voice parameter
        requires_metal=False,
        description="Fastest, smallest model (~1GB memory)",
        lang_code="en",
    ),
}

# Quality order for selection (try best first)
QUALITY_ORDER: list[ModelTier] = [
    ModelTier.VOICE_DESIGN,
    ModelTier.SPARK,
    ModelTier.SPARK_QUANTIZED,
    ModelTier.POCKET,
]


def get_model_by_id(model_id: str) -> tuple[ModelTier, ModelSpec] | None:
    """Find a model by its model_id string."""
    for tier, spec in MODELS.items():
        if spec.model_id == model_id:
            return tier, spec
    return None


def get_fallback_model() -> ModelSpec:
    """Get the ultimate fallback model (pocket-tts - smallest/fastest)."""
    return MODELS[ModelTier.POCKET]
