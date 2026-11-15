"""Base definitions and exceptions for LLM clients (SRS 4.9, FR-LLM-1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hwq.config import Config
    from hwq.protocols import LLMClient


class LLMError(Exception):
    """Base exception for all LLM client errors."""


class OllamaConnectionError(LLMError):
    """Raised when Ollama server cannot be reached or connection fails."""


class OllamaModelError(LLMError):
    """Raised when the requested model is missing or lacks tool support."""


def create_llm_client(config: Config) -> LLMClient:
    """Instantiate an LLMClient based on the runtime configuration."""
    from hwq.llm.ollama import OllamaClient
    from hwq.llm.scripted import ScriptedClient

    if config.llm == "scripted" or config.demo:
        return ScriptedClient()
    return OllamaClient(url=config.ollama_url, model=config.ollama_model)
