"""Tests for LLM clients (OllamaClient, ScriptedClient, factory) (SRS 4.9, FR-LLM-1)."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from hwq.config import Config
from hwq.llm.base import OllamaConnectionError, OllamaModelError, create_llm_client
from hwq.llm.ollama import OllamaClient
from hwq.llm.scripted import ScriptedClient
from hwq.models import LLMReply


def test_ollama_client_endpoint_normalization() -> None:
    client = OllamaClient(url="http://localhost:11434")
    assert client.endpoint == "http://127.0.0.1:11434/api/chat"


def test_ollama_client_temperature_cap() -> None:
    client = OllamaClient(temperature=0.7)
    assert client.temperature <= 0.2


def test_ollama_client_chat_success() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {
            "role": "assistant",
            "content": "Here is the response.",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_cpu_info",
                        "arguments": {},
                    }
                }
            ],
        }
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = OllamaClient()
        reply = client.chat(
            messages=[{"role": "user", "content": "What CPU do I have?"}],
            tools=[],
        )

        assert reply.content == "Here is the response."
        assert len(reply.tool_calls) == 1
        assert reply.tool_calls[0]["function"]["name"] == "get_cpu_info"


def test_ollama_client_string_arguments_parsed() -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_cpu_info",
                        "arguments": "{}",
                    }
                }
            ],
        }
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = OllamaClient()
        reply = client.chat(messages=[], tools=[])
        assert reply.tool_calls[0]["function"]["arguments"] == {}


def test_ollama_client_connection_error() -> None:
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        client = OllamaClient()
        with pytest.raises(OllamaConnectionError, match="Failed to connect to Ollama"):
            client.chat(messages=[], tools=[])


def test_ollama_client_model_not_found() -> None:
    http_err = urllib.error.HTTPError(
        url="http://127.0.0.1:11434/api/chat",
        code=404,
        msg="Not Found",
        hdrs=MagicMock(),
        fp=MagicMock(read=lambda: b"model not found"),
    )
    with patch("urllib.request.urlopen", side_effect=http_err):
        client = OllamaClient(model="nonexistent-model")
        with pytest.raises(OllamaModelError, match="not found on Ollama server"):
            client.chat(messages=[], tools=[])


def test_scripted_client_canned_replies() -> None:
    client = ScriptedClient()
    canned = LLMReply(content="Canned answer", tool_calls=[])
    client.queue_reply(canned)

    reply = client.chat(messages=[{"role": "user", "content": "hello"}], tools=[])
    assert reply.content == "Canned answer"
    assert len(client.call_history) == 1


def test_scripted_client_rule_based() -> None:
    client = ScriptedClient()

    reply_cpu = client.chat(
        messages=[{"role": "user", "content": "Tell me about the CPU"}],
        tools=[],
    )
    assert reply_cpu.tool_calls[0]["function"]["name"] == "get_cpu_info"

    reply_gpu = client.chat(messages=[{"role": "user", "content": "and the GPU?"}], tools=[])
    assert reply_gpu.tool_calls[0]["function"]["name"] == "get_gpu_info"

    reply_refusal = client.chat(messages=[{"role": "user", "content": "delete my logs"}], tools=[])
    assert reply_refusal.tool_calls == []
    assert "cannot execute commands" in (reply_refusal.content or "")


def test_create_llm_client_factory() -> None:
    cfg_ollama = Config(llm="ollama")
    client_ollama = create_llm_client(cfg_ollama)
    assert isinstance(client_ollama, OllamaClient)

    cfg_scripted = Config(llm="scripted")
    client_scripted = create_llm_client(cfg_scripted)
    assert isinstance(client_scripted, ScriptedClient)

    cfg_demo = Config(demo=True)
    client_demo = create_llm_client(cfg_demo)
    assert isinstance(client_demo, ScriptedClient)
