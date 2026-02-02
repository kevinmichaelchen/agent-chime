"""Base adapter interface for CLI tools."""

from abc import ABC, abstractmethod
from typing import Any

from agent_chime.events import Event, Source


class Adapter(ABC):
    """
    Abstract base class for CLI tool adapters.

    Each adapter handles parsing input from a specific CLI tool
    and converting it to agent-chime events.
    """

    @property
    @abstractmethod
    def source(self) -> Source:
        """The source this adapter handles."""
        ...

    @abstractmethod
    def parse(
        self,
        stdin_data: str | None = None,
        argv_data: list[str] | None = None,
        explicit_event: str | None = None,
    ) -> tuple[Event | None, dict[str, Any]]:
        """
        Parse input data and return an event.

        Args:
            stdin_data: Data from stdin (if applicable)
            argv_data: Additional command-line arguments (if applicable)
            explicit_event: Explicitly specified event type (if applicable)

        Returns:
            Tuple of (Event or None, raw payload dict)
        """
        ...


def get_adapter(source: Source) -> Adapter:
    """Get the appropriate adapter for a source."""
    from agent_chime.adapters.claude import ClaudeAdapter
    from agent_chime.adapters.codex import CodexAdapter
    from agent_chime.adapters.opencode import OpenCodeAdapter

    adapters: dict[Source, type[Adapter]] = {
        Source.CLAUDE: ClaudeAdapter,
        Source.CODEX: CodexAdapter,
        Source.OPENCODE: OpenCodeAdapter,
    }

    adapter_class = adapters.get(source)
    if adapter_class is None:
        raise ValueError(f"No adapter for source: {source}")

    return adapter_class()
