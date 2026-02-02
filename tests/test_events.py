"""Tests for event handling."""

from datetime import datetime, timezone

import pytest

from agent_chime.events import (
    DEFAULT_PRIORITIES,
    Event,
    EventType,
    Priority,
    Source,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_exist(self):
        assert EventType.AGENT_YIELD.value == "AGENT_YIELD"
        assert EventType.DECISION_REQUIRED.value == "DECISION_REQUIRED"
        assert EventType.ERROR_RETRY.value == "ERROR_RETRY"


class TestPriority:
    """Tests for Priority enum."""

    def test_priorities_exist(self):
        assert Priority.LOW.value == "low"
        assert Priority.NORMAL.value == "normal"
        assert Priority.HIGH.value == "high"


class TestSource:
    """Tests for Source enum."""

    def test_sources_exist(self):
        assert Source.CLAUDE.value == "claude"
        assert Source.CODEX.value == "codex"
        assert Source.OPENCODE.value == "opencode"


class TestEvent:
    """Tests for Event dataclass."""

    def test_event_creation(self):
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )
        assert event.event_type == EventType.AGENT_YIELD
        assert event.source == Source.CLAUDE
        assert event.summary is None
        assert event.context == {}

    def test_event_with_summary(self):
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CODEX,
            summary="Task completed",
        )
        assert event.summary == "Task completed"

    def test_event_default_priority(self):
        # AGENT_YIELD should have normal priority
        yield_event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )
        assert yield_event.priority == Priority.NORMAL

        # DECISION_REQUIRED should have high priority
        decision_event = Event(
            event_type=EventType.DECISION_REQUIRED,
            source=Source.CLAUDE,
        )
        assert decision_event.priority == Priority.HIGH

    def test_event_custom_priority(self):
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
            priority=Priority.HIGH,
        )
        assert event.priority == Priority.HIGH

    def test_event_is_high_priority(self):
        high_event = Event(
            event_type=EventType.DECISION_REQUIRED,
            source=Source.CLAUDE,
        )
        assert high_event.is_high_priority

        normal_event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )
        assert not normal_event.is_high_priority

    def test_event_timestamp(self):
        before = datetime.now(timezone.utc)
        event = Event(
            event_type=EventType.AGENT_YIELD,
            source=Source.CLAUDE,
        )
        after = datetime.now(timezone.utc)
        assert before <= event.timestamp <= after


class TestDefaultPriorities:
    """Tests for default priority mapping."""

    def test_all_event_types_have_defaults(self):
        for event_type in EventType:
            assert event_type in DEFAULT_PRIORITIES

    def test_decision_required_is_high(self):
        assert DEFAULT_PRIORITIES[EventType.DECISION_REQUIRED] == Priority.HIGH

    def test_error_retry_is_high(self):
        assert DEFAULT_PRIORITIES[EventType.ERROR_RETRY] == Priority.HIGH

    def test_agent_yield_is_normal(self):
        assert DEFAULT_PRIORITIES[EventType.AGENT_YIELD] == Priority.NORMAL
