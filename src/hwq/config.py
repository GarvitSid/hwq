"""Configuration loader and resolution for hwq (SRS 3, FR-ARCH-1, FR-ARCH-2)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BackendChoice = Literal["auto", "linux", "replay"]
ResolvedBackend = Literal["linux", "replay"]
LLMChoice = Literal["ollama", "scripted"]

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3"


def resolve_backend(
    backend: BackendChoice,
    platform: str | None = None,
) -> ResolvedBackend:
    """Resolve backend choice to a concrete backend name.

    'auto' resolves to 'linux' if the host platform starts with 'linux',
    otherwise 'replay'.
    """
    plat = platform if platform is not None else sys.platform
    if backend == "auto":
        return "linux" if plat.startswith("linux") else "replay"
    if backend in ("linux", "replay"):
        return backend
    raise ValueError(f"Invalid backend '{backend}'. Expected one of: auto, linux, replay.")


class Config(BaseModel):
    """Runtime configuration for hwq."""

    model_config = ConfigDict(frozen=True)

    backend: BackendChoice = "auto"
    resolved_backend: ResolvedBackend = "replay"
    fixture: str | None = None
    llm: LLMChoice = "ollama"
    ollama_url: str = Field(default=DEFAULT_OLLAMA_URL)
    ollama_model: str = Field(default=DEFAULT_OLLAMA_MODEL)
    show_tools: bool = False
    demo: bool = False


def load_config(
    env: Mapping[str, str] | None = None,
    *,
    cli_backend: BackendChoice | None = None,
    cli_fixture: str | None = None,
    cli_llm: LLMChoice | None = None,
    cli_show_tools: bool | None = None,
    cli_demo: bool | None = None,
    platform: str | None = None,
) -> Config:
    """Load configuration from environment variables with CLI overrides.

    Precedence:
    1. Explicit CLI arguments.
    2. Environment variables (HWQ_*).
    3. Production defaults (backend='auto', llm='ollama').
    """
    env_vars = os.environ if env is None else env

    # Backend selection (FR-ARCH-1)
    backend_val: BackendChoice
    if cli_backend is not None:
        backend_val = cli_backend
    else:
        raw_env_backend = env_vars.get("HWQ_BACKEND", "auto").strip().lower()
        if raw_env_backend not in ("auto", "linux", "replay"):
            raise ValueError(
                f"Invalid HWQ_BACKEND '{raw_env_backend}'. Expected: auto, linux, replay."
            )
        backend_val = raw_env_backend  # type: ignore[assignment]

    # Fixture selection
    fixture_val: str | None
    if cli_fixture is not None:
        fixture_val = cli_fixture
    else:
        raw_fixture = env_vars.get("HWQ_FIXTURE", "").strip()
        fixture_val = raw_fixture if raw_fixture else None

    # LLM selection (FR-ARCH-2) - default is ALWAYS ollama
    llm_val: LLMChoice
    if cli_llm is not None:
        llm_val = cli_llm
    else:
        raw_env_llm = env_vars.get("HWQ_LLM", "ollama").strip().lower()
        if raw_env_llm not in ("ollama", "scripted"):
            raise ValueError(
                f"Invalid HWQ_LLM '{raw_env_llm}'. Expected: ollama, scripted."
            )
        llm_val = raw_env_llm  # type: ignore[assignment]

    # Demo mode flag
    demo_val = bool(cli_demo) if cli_demo is not None else (
        env_vars.get("HWQ_DEMO", "").strip().lower() in ("1", "true", "yes")
    )

    # Show tools flag
    show_tools_val = bool(cli_show_tools) if cli_show_tools is not None else (
        env_vars.get("HWQ_SHOW_TOOLS", "").strip().lower() in ("1", "true", "yes")
    )

    # If demo mode is active and not overridden, use replay and scripted LLM
    if demo_val:
        if cli_backend is None and "HWQ_BACKEND" not in env_vars:
            backend_val = "replay"
        if cli_llm is None and "HWQ_LLM" not in env_vars:
            llm_val = "scripted"
        if fixture_val is None:
            fixture_val = "synthetic-8gb-1of2"

    resolved = resolve_backend(backend_val, platform=platform)

    ollama_url = env_vars.get("HWQ_OLLAMA_URL", DEFAULT_OLLAMA_URL).strip()
    ollama_model = env_vars.get("HWQ_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()

    return Config(
        backend=backend_val,
        resolved_backend=resolved,
        fixture=fixture_val,
        llm=llm_val,
        ollama_url=ollama_url or DEFAULT_OLLAMA_URL,
        ollama_model=ollama_model or DEFAULT_OLLAMA_MODEL,
        show_tools=show_tools_val,
        demo=demo_val,
    )
