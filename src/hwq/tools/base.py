"""Base tool definitions and tool registry interface (SRS 4.2, 5, FR-TOOL-1..4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hwq.config import Config
from hwq.exec.backend import LinuxBackend, load_fixture_backend
from hwq.facts import FactEnvelope
from hwq.protocols import SystemBackend


def create_backend(config: Config) -> SystemBackend:
    """Create a SystemBackend instance based on configuration."""
    if config.resolved_backend == "linux":
        return LinuxBackend()
    if config.resolved_backend == "replay":
        fixture_name = config.fixture if config.fixture else "synthetic-8gb-1of2"
        return load_fixture_backend(fixture_name)
    raise ValueError(f"Unsupported resolved backend: {config.resolved_backend}")


class Tool(ABC):
    """Abstract base class for all hwq hardware inspection tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Canonical tool name as registered with LLM / orchestrator."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Natural-language description of what this tool inspects."""

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema dict for tool parameters (typed/enum parameters only)."""

    @abstractmethod
    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[Any]:
        """Execute the tool against a SystemBackend and return a typed FactEnvelope."""
