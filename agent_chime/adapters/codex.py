"""Codex adapter for parsing notify events."""

import json
import logging
from typing import Any

from agent_chime.adapters.base import Adapter
from agent_chime.events import Event, EventType, Source

logger = logging.getLogger(__name__)

# Mapping from Codex event types to agent-chime events
CODEX_EVENT_MAP: dict[str, EventType] = {
    "agent-turn-complete": EventType.AGENT_YIELD,
}


class CodexAdapter(Adapter):
    """
    Adapter for Codex notify events.

    Codex passes event data as a JSON string in command-line arguments.

    Configuration example (~/.codex/config.toml):
    notify = ["agent-chime", "notify", "--source", "codex"]
    """

    @property
    def source(self) -> Source:
        return Source.CODEX

    def parse(
        self,
        stdin_data: str | None = None,
        argv_data: list[str] | None = None,
        explicit_event: str | None = None,
    ) -> tuple[Event | None, dict[str, Any]]:
        """
        Parse Codex notify data from command-line arguments.

        Expected JSON format (in argv[0]):
        {
            "type": "agent-turn-complete",
            "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
            "turn-id": "12345",
            "cwd": "/Users/example/project",
            "input-messages": ["Rename foo to bar and update callsites."],
            "last-assistant-message": "Rename complete and verified cargo build succeeds."
        }
        """
        if not argv_data:
            logger.warning("No argv data received from Codex")
            return None, {}

        # Codex passes JSON as first additional argument
        json_data = argv_data[0] if argv_data else ""

        try:
            payload = json.loads(json_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Codex JSON: {e}")
            return None, {}

        # Get the event type
        codex_type = payload.get("type", "")

        # Map to agent-chime event type
        event_type = CODEX_EVENT_MAP.get(codex_type)

        if event_type is None:
            logger.debug(f"Ignoring Codex event: {codex_type}")
            return None, payload

        # Extract summary from payload
        summary = payload.get("last-assistant-message")

        event = Event(
            event_type=event_type,
            source=Source.CODEX,
            summary=summary,
            context=payload,
        )

        return event, payload
