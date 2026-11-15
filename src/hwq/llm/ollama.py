"""Ollama API client using stdlib urllib (SRS 4.9, FR-LLM-1)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from hwq import __version__
from hwq.llm.base import OllamaConnectionError, OllamaModelError
from hwq.models import LLMReply


class OllamaClient:
    """Client for local Ollama server at 127.0.0.1:11434 (FR-LLM-1)."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:11434",
        model: str = "llama3",
        timeout_s: float = 30.0,
        num_ctx: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        # Enforce 127.0.0.1 over 'localhost' per FR-LLM-1
        normalized_url = url.replace("localhost", "127.0.0.1").rstrip("/")
        self.endpoint = f"{normalized_url}/api/chat"
        self.model = model
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx
        self.temperature = min(0.2, temperature)  # Enforce FR-LLM-3

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> LLMReply:
        """Send chat messages and tool definitions to Ollama /api/chat."""
        payload_options: dict[str, Any] = {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
        }
        if options:
            payload_options.update(options)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": payload_options,
        }
        if tools:
            payload["tools"] = tools

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"hwq/{__version__}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            if err.code == 404:
                raise OllamaModelError(
                    f"Model '{self.model}' not found on Ollama server. "
                    f"Run 'ollama pull {self.model}' or specify a different model via --llm."
                ) from err
            raise OllamaConnectionError(
                f"Ollama server returned HTTP {err.code}: {err_body}"
            ) from err
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {self.endpoint}. "
                f"Ensure Ollama is running ('ollama serve') or use 'hwq facts' for local facts."
            ) from err

        # Extract message and tool calls
        message = data.get("message", {})
        content = message.get("content")
        raw_tool_calls = message.get("tool_calls", [])

        normalized_calls: list[dict[str, Any]] = []
        for call in raw_tool_calls:
            # Handle standard format: {"function": {"name": ..., "arguments": ...}}
            func = call.get("function", call)
            name = func.get("name")
            if not name:
                continue

            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    # Keep raw string if malformed, tool validator will handle it
                    pass

            normalized_calls.append({
                "function": {
                    "name": name,
                    "arguments": args,
                }
            })

        return LLMReply(
            content=content,
            tool_calls=normalized_calls,
            raw=data,
        )
