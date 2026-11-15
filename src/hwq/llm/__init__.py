"""LLM client implementations (SRS 4.9)."""

from __future__ import annotations

from hwq.llm.base import LLMError, OllamaConnectionError, OllamaModelError, create_llm_client
from hwq.llm.ollama import OllamaClient
from hwq.llm.scripted import ScriptedClient

__all__ = [
    "LLMError",
    "OllamaClient",
    "OllamaConnectionError",
    "OllamaModelError",
    "ScriptedClient",
    "create_llm_client",
]
