"""Tests for configuration handling."""

import json
import tempfile
from pathlib import Path

import pytest

from agent_chime.config import (
    Config,
    EventConfig,
    NotificationMode,
    TTSConfig,
)
from agent_chime.events import EventType


class TestTTSConfig:
    """Tests for TTSConfig dataclass."""

    def test_defaults(self):
        config = TTSConfig()
        assert config.model is None
        assert config.selection_mode == "auto"
        assert config.voice is None
        assert config.stream is True
        assert config.streaming_interval == 0.5

    def test_from_dict(self):
        data = {
            "model": "mlx-community/pocket-tts",
            "selection_mode": "manual",
            "voice": "alba",
            "stream": False,
        }
        config = TTSConfig.from_dict(data)
        assert config.model == "mlx-community/pocket-tts"
        assert config.selection_mode == "manual"
        assert config.voice == "alba"
        assert config.stream is False


class TestEventConfig:
    """Tests for EventConfig dataclass."""

    def test_defaults(self):
        config = EventConfig()
        assert config.enabled is True
        assert config.mode == NotificationMode.TTS
        assert config.read_summary is False
        assert config.template == ""

    def test_from_dict(self):
        data = {
            "enabled": False,
            "mode": "earcon",
            "read_summary": True,
            "template": "Test template",
        }
        config = EventConfig.from_dict(data)
        assert config.enabled is False
        assert config.mode == "earcon"
        assert config.read_summary is True
        assert config.template == "Test template"


class TestConfig:
    """Tests for Config dataclass."""

    def test_defaults(self):
        config = Config()
        assert config.volume == 0.8
        assert isinstance(config.tts, TTSConfig)

    def test_default_event_configs(self):
        config = Config()

        # All event types should have configs
        for event_type in EventType:
            event_config = config.get_event_config(event_type)
            assert event_config is not None
            assert event_config.enabled is True

    def test_agent_yield_config(self):
        config = Config()
        yield_config = config.get_event_config(EventType.AGENT_YIELD)
        assert yield_config.template == "Ready."
        assert yield_config.read_summary is True

    def test_decision_required_config(self):
        config = Config()
        decision_config = config.get_event_config(EventType.DECISION_REQUIRED)
        assert decision_config.template == "I need your input."
        assert decision_config.read_summary is False

    def test_error_retry_config(self):
        config = Config()
        error_config = config.get_event_config(EventType.ERROR_RETRY)
        assert error_config.mode == NotificationMode.EARCON

    def test_from_dict(self):
        data = {
            "tts": {
                "model": "test-model",
                "voice": "test-voice",
            },
            "volume": 0.5,
            "events": {
                "AGENT_YIELD": {
                    "enabled": False,
                    "template": "Custom template",
                },
            },
        }
        config = Config.from_dict(data)
        assert config.tts.model == "test-model"
        assert config.tts.voice == "test-voice"
        assert config.volume == 0.5

        yield_config = config.get_event_config(EventType.AGENT_YIELD)
        assert yield_config.enabled is False
        assert yield_config.template == "Custom template"

    def test_to_dict(self):
        config = Config()
        data = config.to_dict()

        assert "tts" in data
        assert "volume" in data
        assert "events" in data
        assert "AGENT_YIELD" in data["events"]

    def test_load_and_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Create config
            config = Config()
            config.volume = 0.6
            config.save(config_path)

            # Load it back
            loaded = Config.load(config_path)
            assert loaded.volume == 0.6

    def test_load_missing_file(self):
        config = Config.load(Path("/nonexistent/config.json"))
        # Should return defaults
        assert config.volume == 0.8

    def test_validate_valid_config(self):
        config = Config()
        issues = config.validate()
        assert len(issues) == 0

    def test_validate_invalid_volume(self):
        config = Config(volume=1.5)
        issues = config.validate()
        assert any("Volume" in issue for issue in issues)

    def test_validate_manual_mode_without_model(self):
        config = Config()
        config.tts.selection_mode = "manual"
        config.tts.model = None
        issues = config.validate()
        assert any("Manual" in issue for issue in issues)
