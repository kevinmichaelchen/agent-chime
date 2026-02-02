"""Dynamic TTS model selection based on system resources."""

import logging
from dataclasses import dataclass
from enum import Enum

from agent_chime.system.detector import SystemDetector, SystemInfo
from agent_chime.tts.models import (
    MODELS,
    QUALITY_ORDER,
    ModelSpec,
    ModelTier,
    get_fallback_model,
    get_model_by_id,
)

logger = logging.getLogger(__name__)

# Memory buffer to leave available for the system
MEMORY_BUFFER_GB = 2.0


class SelectionMode(Enum):
    """Model selection modes."""

    AUTO = "auto"  # Automatic based on system resources
    MANUAL = "manual"  # User-specified model


@dataclass
class SelectionResult:
    """Result of model selection."""

    model: ModelSpec
    tier: ModelTier
    reason: str
    system_info: SystemInfo

    def __str__(self) -> str:
        return f"Selected {self.tier.value}: {self.model.model_id} ({self.reason})"


class ModelSelector:
    """Selects the optimal TTS model based on system resources."""

    def __init__(self, detector: SystemDetector | None = None) -> None:
        self.detector = detector or SystemDetector()

    def select(
        self,
        user_preference: str | None = None,
        mode: SelectionMode = SelectionMode.AUTO,
    ) -> SelectionResult:
        """
        Select the best model for the current system.

        Args:
            user_preference: User-specified model ID (optional)
            mode: Selection mode (auto or manual)

        Returns:
            SelectionResult with the chosen model and reasoning
        """
        system_info = self.detector.detect()
        usable_memory = max(0, system_info.available_memory_gb - MEMORY_BUFFER_GB)

        logger.info(
            f"System: {system_info.available_memory_gb:.1f}GB available, "
            f"{usable_memory:.1f}GB usable (with {MEMORY_BUFFER_GB}GB buffer), "
            f"Metal: {system_info.metal_available}"
        )

        # If user specified a model, try to use it
        if user_preference and mode == SelectionMode.MANUAL:
            result = self._try_user_preference(user_preference, system_info, usable_memory)
            if result:
                return result
            logger.warning(
                f"User-specified model '{user_preference}' cannot run on this system, "
                "falling back to auto selection"
            )

        # Auto-select: try models in quality order
        return self._auto_select(system_info, usable_memory)

    def _try_user_preference(
        self,
        model_id: str,
        system_info: SystemInfo,
        usable_memory: float,
    ) -> SelectionResult | None:
        """Try to use the user's preferred model if the system can run it."""
        model_info = get_model_by_id(model_id)
        if model_info is None:
            logger.warning(f"Unknown model ID: {model_id}")
            return None

        tier, spec = model_info
        if self._can_run(spec, system_info, usable_memory):
            return SelectionResult(
                model=spec,
                tier=tier,
                reason="user preference",
                system_info=system_info,
            )

        return None

    def _auto_select(
        self,
        system_info: SystemInfo,
        usable_memory: float,
    ) -> SelectionResult:
        """Auto-select the best model that fits system resources."""
        for tier in QUALITY_ORDER:
            spec = MODELS[tier]
            if self._can_run(spec, system_info, usable_memory):
                reason = self._get_selection_reason(spec, usable_memory, system_info)
                logger.info(f"Auto-selected {tier.value}: {reason}")
                return SelectionResult(
                    model=spec,
                    tier=tier,
                    reason=reason,
                    system_info=system_info,
                )

        # Ultimate fallback (should always succeed)
        fallback = get_fallback_model()
        logger.warning("Falling back to pocket-tts (resource constraints)")
        return SelectionResult(
            model=fallback,
            tier=ModelTier.POCKET,
            reason="fallback (resource constraints)",
            system_info=system_info,
        )

    def _can_run(
        self,
        spec: ModelSpec,
        system_info: SystemInfo,
        usable_memory: float,
    ) -> bool:
        """Check if a model can run on the current system."""
        # Check memory requirements
        if spec.estimated_memory_gb > usable_memory:
            logger.debug(
                f"{spec.model_id}: requires {spec.estimated_memory_gb}GB, "
                f"only {usable_memory:.1f}GB usable"
            )
            return False

        # Check Metal requirements
        if spec.requires_metal and not system_info.metal_available:
            logger.debug(f"{spec.model_id}: requires Metal, but not available")
            return False

        return True

    def _get_selection_reason(
        self,
        spec: ModelSpec,
        usable_memory: float,
        system_info: SystemInfo,
    ) -> str:
        """Generate a human-readable reason for the selection."""
        parts = []

        if spec.estimated_memory_gb <= usable_memory * 0.5:
            parts.append("plenty of RAM")
        elif spec.estimated_memory_gb <= usable_memory * 0.8:
            parts.append("sufficient RAM")
        else:
            parts.append("fits in RAM")

        if spec.requires_metal and system_info.metal_available:
            parts.append("Metal available")

        if not parts:
            return "meets requirements"

        return ", ".join(parts)


def auto_select_model(user_preference: str | None = None) -> SelectionResult:
    """Convenience function to auto-select a model."""
    selector = ModelSelector()
    mode = SelectionMode.MANUAL if user_preference else SelectionMode.AUTO
    return selector.select(user_preference=user_preference, mode=mode)
