"""OpenCode adapter for parsing plugin events."""

import logging
from typing import Any

from agent_chime.adapters.base import Adapter
from agent_chime.events import Event, EventType, Source

logger = logging.getLogger(__name__)


class OpenCodeAdapter(Adapter):
    """
    Adapter for OpenCode plugin events.

    OpenCode uses explicit event flags passed via command-line.
    The plugin handles event mapping and calls agent-chime with
    the appropriate --event flag.

    Plugin example (.opencode/plugin/agent-chime.js):
    export const AgentChimePlugin = async ({ $ }) => ({
        event: async ({ event }) => {
            const map = {
                "session.idle": "AGENT_YIELD",
                "permission.asked": "DECISION_REQUIRED",
                "session.error": "ERROR_RETRY"
            };
            if (map[event.type]) {
                await $`agent-chime notify --source opencode --event ${map[event.type]}`;
            }
        }
    });
    """

    @property
    def source(self) -> Source:
        return Source.OPENCODE

    def parse(
        self,
        stdin_data: str | None = None,
        argv_data: list[str] | None = None,
        explicit_event: str | None = None,
    ) -> tuple[Event | None, dict[str, Any]]:
        """
        Parse OpenCode event from explicit --event flag.

        OpenCode doesn't pass payload data to the command,
        so we rely on the explicit event type.
        """
        if not explicit_event:
            logger.warning("No explicit event specified for OpenCode")
            return None, {}

        # Parse event type
        try:
            event_type = EventType(explicit_event)
        except ValueError:
            logger.error(f"Unknown event type: {explicit_event}")
            return None, {}

        event = Event(
            event_type=event_type,
            source=Source.OPENCODE,
            summary=None,  # OpenCode doesn't pass context
            context={},
        )

        return event, {}
