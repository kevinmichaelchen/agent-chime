"""Claude Code adapter for parsing hook events."""

import json
import logging
from typing import Any

from agent_chime.adapters.base import Adapter
from agent_chime.events import Event, EventType, Source

logger = logging.getLogger(__name__)

# Mapping from Claude hook events to agent-chime events
CLAUDE_EVENT_MAP: dict[str, EventType] = {
    "Stop": EventType.AGENT_YIELD,
    "Notification": EventType.AGENT_YIELD,
}

# Keywords in reason that indicate a decision is needed
DECISION_KEYWORDS = [
    "need your",
    "waiting for",
    "choose",
    "select",
    "decision",
    "confirm",
    "approve",
]


class ClaudeAdapter(Adapter):
    """
    Adapter for Claude Code hook events.

    Claude Code passes event data via stdin as JSON.

    Hook configuration example (~/.claude/settings.json):
    {
        "hooks": {
            "Stop": [{"type": "command", "command": "agent-chime notify --source claude"}],
            "Notification": [{"type": "command", "command": "agent-chime notify --source claude"}]
        }
    }
    """

    @property
    def source(self) -> Source:
        return Source.CLAUDE

    def parse(
        self,
        stdin_data: str | None = None,
        argv_data: list[str] | None = None,
        explicit_event: str | None = None,
    ) -> tuple[Event | None, dict[str, Any]]:
        """
        Parse Claude Code hook data from stdin.

        Expected JSON format:
        {
            "session_id": "abc123",
            "transcript_path": "/path/to/transcript.txt",
            "cwd": "/current/working/dir",
            "hook_event_name": "Stop",
            "reason": "Task appears complete"
        }
        """
        if not stdin_data:
            logger.warning("No stdin data received from Claude Code")
            return None, {}

        try:
            payload = json.loads(stdin_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude Code JSON: {e}")
            return None, {}

        # Get the hook event name
        hook_event = payload.get("hook_event_name", "")

        # Map to agent-chime event type
        event_type = self._map_event_type(hook_event, payload)

        if event_type is None:
            logger.debug(f"Ignoring Claude Code event: {hook_event}")
            return None, payload

        # Extract summary from payload
        summary = self._extract_summary(payload)

        event = Event(
            event_type=event_type,
            source=Source.CLAUDE,
            summary=summary,
            context=payload,
        )

        return event, payload

    def _map_event_type(self, hook_event: str, payload: dict[str, Any]) -> EventType | None:
        """Map a Claude hook event to an agent-chime event type."""
        # Check for AskUserQuestion in PreToolUse
        if hook_event == "PreToolUse":
            tool_name = payload.get("tool_name", "")
            if tool_name == "AskUserQuestion":
                return EventType.DECISION_REQUIRED
            # Ignore other PreToolUse events
            return None

        # Standard mapping
        event_type = CLAUDE_EVENT_MAP.get(hook_event)

        # Check if Stop event indicates a decision is needed
        if event_type == EventType.AGENT_YIELD:
            reason = payload.get("reason", "").lower()
            if any(keyword in reason for keyword in DECISION_KEYWORDS):
                return EventType.DECISION_REQUIRED

        return event_type

    def _extract_summary(self, payload: dict[str, Any]) -> str | None:
        """Extract a summary from the Claude Code payload."""
        # Try reason field first
        if reason := payload.get("reason"):
            return reason

        # Could try to read transcript, but that's too slow for real-time
        return None
