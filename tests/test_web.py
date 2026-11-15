"""Tests for the hwq web server and Render deployment endpoints (FR-CLI-1)."""

from __future__ import annotations

import io
import json
from http import HTTPStatus
from typing import Any, cast
from unittest.mock import MagicMock

from hwq.config import Config
from hwq.web import make_handler


def test_web_handler_healthz() -> None:
    cfg = Config(backend="replay", fixture="synthetic-8gb-1of2", llm="scripted")
    handler_cls = make_handler(cfg)

    handler = cast(Any, handler_cls.__new__(handler_cls))
    handler.wfile = io.BytesIO()
    handler.path = "/healthz"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_GET()
    handler.send_response.assert_called_with(HTTPStatus.OK)
    handler.send_header.assert_called_with("Content-Type", "application/json")


def test_web_handler_index_html() -> None:
    cfg = Config(backend="replay", fixture="synthetic-8gb-1of2", llm="scripted")
    handler_cls = make_handler(cfg)

    handler = cast(Any, handler_cls.__new__(handler_cls))
    handler.wfile = io.BytesIO()
    handler.path = "/"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_GET()
    handler.send_response.assert_called_with(HTTPStatus.OK)
    handler.send_header.assert_called_with("Content-Type", "text/html; charset=utf-8")
    output = handler.wfile.getvalue().decode()
    assert "hwq" in output
    assert "Hardware Assistant" in output


def test_web_handler_facts_api() -> None:
    cfg = Config(backend="replay", fixture="synthetic-8gb-1of2", llm="scripted")
    handler_cls = make_handler(cfg)

    handler = cast(Any, handler_cls.__new__(handler_cls))
    handler.wfile = io.BytesIO()
    handler.path = "/api/facts"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_GET()
    handler.send_response.assert_called_with(HTTPStatus.OK)
    facts_json = json.loads(handler.wfile.getvalue().decode())
    assert "get_cpu_info" in facts_json


def test_web_handler_ask_api() -> None:
    cfg = Config(backend="replay", fixture="synthetic-8gb-1of2", llm="scripted")
    handler_cls = make_handler(cfg)

    payload = json.dumps({"question": "What CPU do I have?"}).encode()
    handler = cast(Any, handler_cls.__new__(handler_cls))
    handler.wfile = io.BytesIO()
    handler.rfile = io.BytesIO(payload)
    handler.headers = {"Content-Length": str(len(payload))}
    handler.path = "/api/ask"
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_POST()
    handler.send_response.assert_called_with(HTTPStatus.OK)
    resp = json.loads(handler.wfile.getvalue().decode())
    assert resp.get("status") == "ok"
    assert "CPU" in resp.get("answer", "")
