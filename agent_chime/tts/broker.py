"""TTS broker for event-to-speech conversion."""

import logging
from typing import Any

from agent_chime.config import Config, EventConfig, NotificationMode
from agent_chime.events import Event, EventType, Source

logger = logging.getLogger(__name__)

# Maximum length for spoken summaries (characters)
MAX_SUMMARY_LENGTH = 200

# Truncation suffix
TRUNCATION_SUFFIX = " Check the screen for details."


class TTSBroker:
    """
    Converts events into text for TTS synthesis.

    Handles template expansion, summary extraction, and length limiting.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def get_text_for_event(self, event: Event, payload: dict[str, Any] | None = None) -> str | None:
        """
        Get the text to speak for an event.

        Args:
            event: The event to convert
            payload: Optional raw payload for summary extraction

        Returns:
            Text to speak, or None if the event is silent/disabled
        """
        event_config = self.config.get_event_config(event.event_type)

        if not event_config.enabled:
            logger.debug(f"Event {event.event_type.value} is disabled")
            return None

        if event_config.mode == NotificationMode.SILENT:
            logger.debug(f"Event {event.event_type.value} is silent")
            return None

        if event_config.mode == NotificationMode.EARCON:
            # Earcons don't need text
            return None

        # For TTS mode, determine what to speak
        if event_config.read_summary:
            summary = self._extract_summary(event, payload)
            if summary:
                return self._limit_length(summary)

        # Fallback to template
        return event_config.template or self._get_default_template(event.event_type)

    def should_play_earcon(self, event: Event) -> bool:
        """Check if an event should play an earcon."""
        event_config = self.config.get_event_config(event.event_type)
        return event_config.enabled and event_config.mode == NotificationMode.EARCON

    def _extract_summary(self, event: Event, payload: dict[str, Any] | None) -> str | None:
        """Extract a summary from the event or payload."""
        # First, check if the event has a summary
        if event.summary:
            return event.summary

        # No payload, no summary
        if not payload:
            return None

        # Source-specific extraction
        if event.source == Source.CLAUDE:
            return self._extract_claude_summary(payload)
        elif event.source == Source.CODEX:
            return self._extract_codex_summary(payload)
        elif event.source == Source.OPENCODE:
            return self._extract_opencode_summary(payload)

        return None

    def _extract_claude_summary(self, payload: dict[str, Any]) -> str | None:
        """Extract summary from Claude Code payload."""
        # Try the reason field first (for Stop events)
        if reason := payload.get("reason"):
            return reason

        # Could also try reading from transcript_path, but that requires file I/O
        # and may be too slow for real-time notifications
        if transcript_path := payload.get("transcript_path"):
            logger.debug(f"Transcript available at {transcript_path} but not reading for speed")

        return None

    def _extract_codex_summary(self, payload: dict[str, Any]) -> str | None:
        """Extract summary from Codex payload."""
        # Use the last assistant message
        return payload.get("last-assistant-message")

    def _extract_opencode_summary(self, payload: dict[str, Any]) -> str | None:
        """Extract summary from OpenCode payload."""
        # OpenCode doesn't pass much context via the explicit event flag
        # Could potentially read from session state if available
        return payload.get("summary")

    def _limit_length(self, text: str) -> str:
        """Limit text length for reasonable TTS duration."""
        if len(text) <= MAX_SUMMARY_LENGTH:
            return text

        # Truncate at word boundary
        truncated = text[:MAX_SUMMARY_LENGTH]
        last_space = truncated.rfind(" ")
        if last_space > MAX_SUMMARY_LENGTH // 2:
            truncated = truncated[:last_space]

        return truncated + TRUNCATION_SUFFIX

    def _get_default_template(self, event_type: EventType) -> str:
        """Get the default template for an event type."""
        defaults = {
            EventType.AGENT_YIELD: "Ready.",
            EventType.DECISION_REQUIRED: "I need your input.",
            EventType.ERROR_RETRY: "I hit an error. Please review.",
        }
        return defaults.get(event_type, "Notification.")


def get_earcon_name(event_type: EventType) -> str:
    """Get the earcon filename for an event type."""
    earcon_map = {
        EventType.AGENT_YIELD: "yield.wav",
        EventType.DECISION_REQUIRED: "decision.wav",
        EventType.ERROR_RETRY: "error.wav",
    }
    return earcon_map.get(event_type, "notification.wav")
