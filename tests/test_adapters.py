"""Tests for CLI adapters."""

import json

import pytest

from agent_chime.adapters.base import get_adapter
from agent_chime.adapters.claude import ClaudeAdapter
from agent_chime.adapters.codex import CodexAdapter
from agent_chime.adapters.opencode import OpenCodeAdapter
from agent_chime.events import EventType, Source


class TestClaudeAdapter:
    """Tests for ClaudeAdapter."""

    def test_source(self):
        adapter = ClaudeAdapter()
        assert adapter.source == Source.CLAUDE

    def test_parse_stop_event(self):
        adapter = ClaudeAdapter()
        payload = json.dumps({
            "session_id": "abc123",
            "hook_event_name": "Stop",
            "reason": "Task completed successfully",
        })

        event, raw = adapter.parse(stdin_data=payload)

        assert event is not None
        assert event.event_type == EventType.AGENT_YIELD
        assert event.source == Source.CLAUDE
        assert event.summary == "Task completed successfully"

    def test_parse_notification_event(self):
        adapter = ClaudeAdapter()
        payload = json.dumps({
            "session_id": "abc123",
            "hook_event_name": "Notification",
        })

        event, raw = adapter.parse(stdin_data=payload)

        assert event is not None
        assert event.event_type == EventType.AGENT_YIELD

    def test_parse_pretooluse_askuserquestion(self):
        adapter = ClaudeAdapter()
        payload = json.dumps({
            "session_id": "abc123",
            "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion",
        })

        event, raw = adapter.parse(stdin_data=payload)

        assert event is not None
        assert event.event_type == EventType.DECISION_REQUIRED

    def test_parse_pretooluse_other_tool(self):
        adapter = ClaudeAdapter()
        payload = json.dumps({
            "session_id": "abc123",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
        })

        event, raw = adapter.parse(stdin_data=payload)

        # Should be ignored
        assert event is None

    def test_parse_decision_keywords_in_reason(self):
        adapter = ClaudeAdapter()
        payload = json.dumps({
            "session_id": "abc123",
            "hook_event_name": "Stop",
            "reason": "I need your decision on which approach to take",
        })

        event, raw = adapter.parse(stdin_data=payload)

        assert event is not None
        assert event.event_type == EventType.DECISION_REQUIRED

    def test_parse_no_stdin(self):
        adapter = ClaudeAdapter()
        event, raw = adapter.parse(stdin_data=None)
        assert event is None

    def test_parse_invalid_json(self):
        adapter = ClaudeAdapter()
        event, raw = adapter.parse(stdin_data="not json")
        assert event is None


class TestCodexAdapter:
    """Tests for CodexAdapter."""

    def test_source(self):
        adapter = CodexAdapter()
        assert adapter.source == Source.CODEX

    def test_parse_agent_turn_complete(self):
        adapter = CodexAdapter()
        payload = json.dumps({
            "type": "agent-turn-complete",
            "thread-id": "123-456",
            "last-assistant-message": "Done with the task.",
        })

        event, raw = adapter.parse(argv_data=[payload])

        assert event is not None
        assert event.event_type == EventType.AGENT_YIELD
        assert event.source == Source.CODEX
        assert event.summary == "Done with the task."

    def test_parse_no_argv(self):
        adapter = CodexAdapter()
        event, raw = adapter.parse(argv_data=None)
        assert event is None

    def test_parse_invalid_json(self):
        adapter = CodexAdapter()
        event, raw = adapter.parse(argv_data=["not json"])
        assert event is None

    def test_parse_unknown_event_type(self):
        adapter = CodexAdapter()
        payload = json.dumps({
            "type": "unknown-event",
        })

        event, raw = adapter.parse(argv_data=[payload])
        assert event is None


class TestOpenCodeAdapter:
    """Tests for OpenCodeAdapter."""

    def test_source(self):
        adapter = OpenCodeAdapter()
        assert adapter.source == Source.OPENCODE

    def test_parse_agent_yield(self):
        adapter = OpenCodeAdapter()
        event, raw = adapter.parse(explicit_event="AGENT_YIELD")

        assert event is not None
        assert event.event_type == EventType.AGENT_YIELD
        assert event.source == Source.OPENCODE

    def test_parse_decision_required(self):
        adapter = OpenCodeAdapter()
        event, raw = adapter.parse(explicit_event="DECISION_REQUIRED")

        assert event is not None
        assert event.event_type == EventType.DECISION_REQUIRED

    def test_parse_error_retry(self):
        adapter = OpenCodeAdapter()
        event, raw = adapter.parse(explicit_event="ERROR_RETRY")

        assert event is not None
        assert event.event_type == EventType.ERROR_RETRY

    def test_parse_no_event(self):
        adapter = OpenCodeAdapter()
        event, raw = adapter.parse(explicit_event=None)
        assert event is None

    def test_parse_unknown_event(self):
        adapter = OpenCodeAdapter()
        event, raw = adapter.parse(explicit_event="UNKNOWN_EVENT")
        assert event is None


class TestGetAdapter:
    """Tests for get_adapter function."""

    def test_get_claude_adapter(self):
        adapter = get_adapter(Source.CLAUDE)
        assert isinstance(adapter, ClaudeAdapter)

    def test_get_codex_adapter(self):
        adapter = get_adapter(Source.CODEX)
        assert isinstance(adapter, CodexAdapter)

    def test_get_opencode_adapter(self):
        adapter = get_adapter(Source.OPENCODE)
        assert isinstance(adapter, OpenCodeAdapter)
