"""Tests for TTS model definitions."""

import pytest

from agent_chime.tts.models import (
    MODELS,
    QUALITY_ORDER,
    ModelSpec,
    ModelTier,
    get_fallback_model,
    get_model_by_id,
)


class TestModelTier:
    """Tests for ModelTier enum."""

    def test_tiers_exist(self):
        assert ModelTier.POCKET.value == "pocket"
        assert ModelTier.SPARK.value == "spark"
        assert ModelTier.SPARK_QUANTIZED.value == "spark_quantized"


class TestModelSpec:
    """Tests for ModelSpec dataclass."""

    def test_spec_creation(self):
        spec = ModelSpec(
            model_id="test-model",
            estimated_memory_gb=1.0,
            realtime_factor=0.3,
            default_voice="test_voice",
        )
        assert spec.model_id == "test-model"
        assert spec.estimated_memory_gb == 1.0
        assert spec.realtime_factor == 0.3
        assert spec.default_voice == "test_voice"
        assert spec.requires_metal is False

    def test_is_pocket(self):
        pocket_spec = ModelSpec(
            model_id="mlx-community/pocket-tts",
            estimated_memory_gb=1.0,
            realtime_factor=1.34,
            default_voice="",
        )
        assert pocket_spec.is_pocket

        spark_spec = ModelSpec(
            model_id="mlx-community/Spark-TTS-0.5B-bf16",
            estimated_memory_gb=3.0,
            realtime_factor=0.3,
            default_voice="",
        )
        assert not spark_spec.is_pocket


class TestModels:
    """Tests for the model registry."""

    def test_all_tiers_have_models(self):
        for tier in ModelTier:
            assert tier in MODELS
            assert isinstance(MODELS[tier], ModelSpec)

    def test_quality_order_includes_all_tiers(self):
        for tier in ModelTier:
            assert tier in QUALITY_ORDER

    def test_quality_order_is_descending(self):
        # First should be highest quality (largest)
        assert QUALITY_ORDER[0] == ModelTier.SPARK
        # Last should be smallest/fastest
        assert QUALITY_ORDER[-1] == ModelTier.POCKET

    def test_pocket_is_fallback(self):
        pocket = MODELS[ModelTier.POCKET]
        assert not pocket.requires_metal
        assert pocket.estimated_memory_gb <= 1.0

    def test_spark_models_require_metal(self):
        assert MODELS[ModelTier.SPARK].requires_metal
        assert MODELS[ModelTier.SPARK_QUANTIZED].requires_metal


class TestGetModelById:
    """Tests for get_model_by_id function."""

    def test_find_pocket_model(self):
        result = get_model_by_id("mlx-community/pocket-tts")
        assert result is not None
        tier, spec = result
        assert tier == ModelTier.POCKET
        assert spec.model_id == "mlx-community/pocket-tts"

    def test_find_spark_model(self):
        result = get_model_by_id("mlx-community/Spark-TTS-0.5B-bf16")
        assert result is not None
        tier, spec = result
        assert tier == ModelTier.SPARK

    def test_unknown_model_returns_none(self):
        result = get_model_by_id("unknown/model")
        assert result is None


class TestGetFallbackModel:
    """Tests for get_fallback_model function."""

    def test_returns_pocket(self):
        fallback = get_fallback_model()
        assert fallback.model_id == "mlx-community/pocket-tts"
        assert not fallback.requires_metal
