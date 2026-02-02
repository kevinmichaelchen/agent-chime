"""Configuration management for agent-chime."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_chime.events import EventType

logger = logging.getLogger(__name__)

# Default config locations
CONFIG_PATHS = [
    Path.home() / ".config" / "agent-chime" / "config.json",
    Path.home() / ".agent-chime.json",
]


class NotificationMode:
    """Notification modes for events."""

    TTS = "tts"
    EARCON = "earcon"
    SILENT = "silent"


@dataclass
class EventConfig:
    """Configuration for a specific event type."""

    enabled: bool = True
    mode: str = NotificationMode.TTS
    read_summary: bool = False
    template: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventConfig":
        return cls(
            enabled=data.get("enabled", True),
            mode=data.get("mode", NotificationMode.TTS),
            read_summary=data.get("read_summary", False),
            template=data.get("template", ""),
        )


@dataclass
class TTSConfig:
    """TTS provider configuration."""

    model: str | None = None  # None means auto-select
    selection_mode: str = "auto"  # "auto" or "manual"
    voice: str | None = None  # None means use model default
    stream: bool = True
    streaming_interval: float = 0.5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TTSConfig":
        return cls(
            model=data.get("model"),
            selection_mode=data.get("selection_mode", "auto"),
            voice=data.get("voice"),
            stream=data.get("stream", True),
            streaming_interval=data.get("streaming_interval", 0.5),
        )


# Default event configurations
DEFAULT_EVENT_CONFIGS: dict[EventType, EventConfig] = {
    EventType.AGENT_YIELD: EventConfig(
        enabled=True,
        mode=NotificationMode.TTS,
        read_summary=True,
        template="Ready.",
    ),
    EventType.DECISION_REQUIRED: EventConfig(
        enabled=True,
        mode=NotificationMode.TTS,
        read_summary=False,
        template="I need your input.",
    ),
    EventType.ERROR_RETRY: EventConfig(
        enabled=True,
        mode=NotificationMode.EARCON,
        read_summary=False,
        template="I hit an error. Please review.",
    ),
}


@dataclass
class Config:
    """Main configuration for agent-chime."""

    tts: TTSConfig = field(default_factory=TTSConfig)
    volume: float = 0.8
    events: dict[EventType, EventConfig] = field(default_factory=dict)
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "agent-chime")
    earcons_dir: Path | None = None

    def __post_init__(self) -> None:
        # Fill in any missing event configs with defaults
        for event_type, default_config in DEFAULT_EVENT_CONFIGS.items():
            if event_type not in self.events:
                self.events[event_type] = default_config

    def get_event_config(self, event_type: EventType) -> EventConfig:
        """Get configuration for a specific event type."""
        return self.events.get(event_type, DEFAULT_EVENT_CONFIGS.get(event_type, EventConfig()))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from a dictionary."""
        tts = TTSConfig.from_dict(data.get("tts", {}))

        events: dict[EventType, EventConfig] = {}
        events_data = data.get("events", {})
        for event_name, event_data in events_data.items():
            try:
                event_type = EventType(event_name)
                events[event_type] = EventConfig.from_dict(event_data)
            except ValueError:
                logger.warning(f"Unknown event type in config: {event_name}")

        cache_dir = Path(data["cache_dir"]) if data.get("cache_dir") else None
        earcons_dir = Path(data["earcons_dir"]) if data.get("earcons_dir") else None

        return cls(
            tts=tts,
            volume=data.get("volume", 0.8),
            events=events,
            cache_dir=cache_dir or Path.home() / ".cache" / "agent-chime",
            earcons_dir=earcons_dir,
        )

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Load configuration from file or return defaults."""
        if path:
            paths_to_try = [path]
        else:
            paths_to_try = CONFIG_PATHS

        for config_path in paths_to_try:
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        data = json.load(f)
                    logger.info(f"Loaded config from {config_path}")
                    return cls.from_dict(data)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to load config from {config_path}: {e}")

        logger.info("Using default configuration")
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Convert config to a dictionary."""
        return {
            "tts": {
                "model": self.tts.model,
                "selection_mode": self.tts.selection_mode,
                "voice": self.tts.voice,
                "stream": self.tts.stream,
                "streaming_interval": self.tts.streaming_interval,
            },
            "volume": self.volume,
            "events": {
                event_type.value: {
                    "enabled": config.enabled,
                    "mode": config.mode,
                    "read_summary": config.read_summary,
                    "template": config.template,
                }
                for event_type, config in self.events.items()
            },
            "cache_dir": str(self.cache_dir),
            "earcons_dir": str(self.earcons_dir) if self.earcons_dir else None,
        }

    def save(self, path: Path | None = None) -> None:
        """Save configuration to file."""
        save_path = path or CONFIG_PATHS[0]
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved config to {save_path}")

    def validate(self) -> list[str]:
        """Validate the configuration and return any issues."""
        issues: list[str] = []

        if not 0 <= self.volume <= 1:
            issues.append(f"Volume {self.volume} should be between 0 and 1")

        if self.tts.selection_mode not in ("auto", "manual"):
            issues.append(f"Unknown selection_mode: {self.tts.selection_mode}")

        if self.tts.selection_mode == "manual" and not self.tts.model:
            issues.append("Manual selection mode requires a model to be specified")

        for event_type, config in self.events.items():
            if config.mode not in (NotificationMode.TTS, NotificationMode.EARCON, NotificationMode.SILENT):
                issues.append(f"Unknown mode '{config.mode}' for event {event_type.value}")

        return issues
