"""Tests for TTS broker."""

import pytest

from agent_chime.config import Config, EventConfig, NotificationMode
from agent_chime.events import Event, EventType, Source
from agent_chime.tts.broker import (
    MAX_SUMMARY_LENGTH,
    TTSBroker,
    get_earcon_name,
)


class TestTTSBroker:
    """Tests for TTSBroker."""

    def test_get_text_for_agent_yield(self):
        broker = TTSBroker()
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )

        text = broker.get_text_for_event(event)

        assert text is not None
        assert text == "Ready."

    def test_get_text_for_decision_required(self):
        broker = TTSBroker()
        event = Event(
            event_type=EventType.DECISION_REQUIRED,
            source=Source.CLAUDE,
        )

        text = broker.get_text_for_event(event)

        assert text is not None
        assert text == "I need your input."

    def test_get_text_disabled_event(self):
        config = Config()
        config.events[EventType.AGENT_YIELD] = EventConfig(enabled=False)
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )

        text = broker.get_text_for_event(event)
        assert text is None

    def test_get_text_silent_event(self):
        config = Config()
        config.events[EventType.AGENT_YIELD] = EventConfig(
            enabled=True,
            mode=NotificationMode.SILENT,
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )

        text = broker.get_text_for_event(event)
        assert text is None

    def test_get_text_earcon_event(self):
        config = Config()
        config.events[EventType.ERROR_RETRY] = EventConfig(
            enabled=True,
            mode=NotificationMode.EARCON,
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.ERROR_RETRY,
            source=Source.OPENCODE,
        )

        # Should return None (earcons don't need text)
        text = broker.get_text_for_event(event)
        assert text is None

    def test_should_play_earcon(self):
        config = Config()
        config.events[EventType.ERROR_RETRY] = EventConfig(
            enabled=True,
            mode=NotificationMode.EARCON,
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.ERROR_RETRY,
            source=Source.OPENCODE,
        )

        assert broker.should_play_earcon(event) is True

    def test_should_not_play_earcon_for_tts(self):
        broker = TTSBroker()
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )

        assert broker.should_play_earcon(event) is False

    def test_read_summary_from_event(self):
        config = Config()
        config.events[EventType.AGENT_YIELD] = EventConfig(
            enabled=True,
            mode=NotificationMode.TTS,
            read_summary=True,
            template="Ready.",
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
            summary="Task completed successfully",
        )

        text = broker.get_text_for_event(event)
        assert text == "Task completed successfully"

    def test_read_summary_from_codex_payload(self):
        config = Config()
        config.events[EventType.AGENT_YIELD] = EventConfig(
            enabled=True,
            mode=NotificationMode.TTS,
            read_summary=True,
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CODEX,
        )
        payload = {
            "last-assistant-message": "Renamed all files successfully",
        }

        text = broker.get_text_for_event(event, payload)
        assert text == "Renamed all files successfully"

    def test_read_summary_from_claude_payload(self):
        config = Config()
        config.events[EventType.AGENT_YIELD] = EventConfig(
            enabled=True,
            mode=NotificationMode.TTS,
            read_summary=True,
        )
        broker = TTSBroker(config)

        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )
        payload = {
            "reason": "Finished implementing the feature",
        }

        text = broker.get_text_for_event(event, payload)
        assert text == "Finished implementing the feature"

    def test_truncate_long_summary(self):
        broker = TTSBroker()
        long_text = "A" * 500

        truncated = broker._limit_length(long_text)

        assert len(truncated) < len(long_text)
        assert "Check the screen" in truncated

    def test_short_summary_not_truncated(self):
        broker = TTSBroker()
        short_text = "Short message"

        result = broker._limit_length(short_text)
        assert result == short_text


class TestGetEarconName:
    """Tests for get_earcon_name function."""

    def test_agent_yield_earcon(self):
        assert get_earcon_name(EventType.AGENT_YIELD) == "yield.wav"

    def test_decision_required_earcon(self):
        assert get_earcon_name(EventType.DECISION_REQUIRED) == "decision.wav"

    def test_error_retry_earcon(self):
        assert get_earcon_name(EventType.ERROR_RETRY) == "error.wav"
