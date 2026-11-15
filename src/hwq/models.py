"""Core execution and LLM data models (stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Status mapping per SRS FR-EXEC-3: ok, unavailable, permission_denied, timeout, error
ExecutionStatus = Literal["ok", "unavailable", "permission_denied", "timeout", "error"]


@dataclass(frozen=True)
class CommandSpec:
    """Specification of an allowed command to execute."""

    argv: tuple[str, ...]
    privileged: bool = False
    timeout_s: float = 5.0
    max_bytes: int = 1_048_576  # 1 MiB

    def __post_init__(self) -> None:
        if isinstance(self.argv, list):
            # Enforce immutable tuple for argv
            object.__setattr__(self, "argv", tuple(self.argv))
        if not self.argv or not all(isinstance(a, str) and a for a in self.argv):
            raise ValueError("CommandSpec.argv must be a non-empty sequence of non-empty strings")
        if self.timeout_s <= 0:
            raise ValueError("CommandSpec.timeout_s must be positive")
        if self.max_bytes <= 0:
            raise ValueError("CommandSpec.max_bytes must be positive")


@dataclass(frozen=True)
class RawResult:
    """Raw result returned by a SystemBackend."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    status: ExecutionStatus
    duration_s: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.argv, list):
            object.__setattr__(self, "argv", tuple(self.argv))


@dataclass
class LLMReply:
    """Response returned by an LLMClient."""

    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None
