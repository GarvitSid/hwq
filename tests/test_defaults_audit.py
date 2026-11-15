"""Defaults audit tests verifying production behavior when env vars are unset (SRS 4.3, M8)."""

from __future__ import annotations

from hwq.config import load_config
from hwq.exec.backend import LinuxBackend, ReplayBackend
from hwq.llm import create_llm_client
from hwq.llm.ollama import OllamaClient
from hwq.llm.scripted import ScriptedClient
from hwq.tools.base import create_backend


def test_defaults_audit_unset_env_linux() -> None:
    """When HWQ_BACKEND and HWQ_LLM are unset on Linux, production defaults are selected."""
    cfg = load_config(env={}, platform="linux")
    assert cfg.backend == "auto"
    assert cfg.resolved_backend == "linux"
    assert cfg.llm == "ollama"
    assert cfg.ollama_url == "http://127.0.0.1:11434"
    assert cfg.demo is False
    assert cfg.show_tools is False

    # Factory instantiation
    llm = create_llm_client(cfg)
    assert isinstance(llm, OllamaClient)
    assert "127.0.0.1:11434" in llm.endpoint

    backend = create_backend(cfg)
    assert isinstance(backend, LinuxBackend)


def test_defaults_audit_unset_env_non_linux() -> None:
    """When HWQ_BACKEND is unset on non-Linux platform, auto resolves safely to replay."""
    cfg = load_config(env={}, platform="win32")
    assert cfg.backend == "auto"
    assert cfg.resolved_backend == "replay"
    assert cfg.llm == "ollama"
    assert cfg.demo is False

    backend = create_backend(cfg)
    assert isinstance(backend, ReplayBackend)


def test_defaults_audit_demo_mode_gating() -> None:
    """Demo mode (--demo) forces scripted LLM and replay backend with default fixture."""
    cfg = load_config(env={}, cli_demo=True, platform="linux")
    assert cfg.demo is True
    assert cfg.backend == "replay"
    assert cfg.resolved_backend == "replay"
    assert cfg.llm == "scripted"
    assert cfg.fixture == "synthetic-8gb-1of2"

    llm = create_llm_client(cfg)
    assert isinstance(llm, ScriptedClient)

    backend = create_backend(cfg)
    assert isinstance(backend, ReplayBackend)


def test_defaults_audit_precedence() -> None:
    """CLI flags supersede environment variables, which supersede defaults."""
    # 1. Environment variables override defaults
    env = {
        "HWQ_BACKEND": "replay",
        "HWQ_FIXTURE": "no-sudo",
        "HWQ_LLM": "scripted",
        "HWQ_OLLAMA_URL": "http://127.0.0.1:9999",
        "HWQ_SHOW_TOOLS": "1",
    }
    cfg_env = load_config(env=env, platform="linux")
    assert cfg_env.backend == "replay"
    assert cfg_env.fixture == "no-sudo"
    assert cfg_env.llm == "scripted"
    assert cfg_env.ollama_url == "http://127.0.0.1:9999"
    assert cfg_env.show_tools is True

    # 2. CLI flags override environment variables
    cfg_cli = load_config(
        env=env,
        cli_backend="linux",
        cli_llm="ollama",
        cli_show_tools=False,
        platform="linux",
    )
    assert cfg_cli.backend == "linux"
    assert cfg_cli.resolved_backend == "linux"
    assert cfg_cli.llm == "ollama"
    assert cfg_cli.show_tools is False
