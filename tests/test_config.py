"""Tests for configuration resolution and loading."""

import pytest

from hwq.config import load_config, resolve_backend


def test_resolve_backend_auto_on_linux() -> None:
    """Auto backend resolves to linux when on linux."""
    assert resolve_backend("auto", platform="linux") == "linux"
    assert resolve_backend("auto", platform="linux2") == "linux"


def test_resolve_backend_auto_on_non_linux() -> None:
    """Auto backend resolves to replay on win32 and darwin."""
    assert resolve_backend("auto", platform="win32") == "replay"
    assert resolve_backend("auto", platform="darwin") == "replay"


def test_resolve_backend_explicit() -> None:
    """Explicit backend choices are respected."""
    assert resolve_backend("linux", platform="win32") == "linux"
    assert resolve_backend("replay", platform="linux") == "replay"


def test_resolve_backend_invalid() -> None:
    """Invalid backend names raise ValueError."""
    with pytest.raises(ValueError, match="Invalid backend"):
        resolve_backend("unknown")  # type: ignore[arg-type]


def test_load_config_defaults(clean_env: pytest.MonkeyPatch) -> None:
    """Default config has backend=auto, llm=ollama, demo=False."""
    cfg = load_config({}, platform="linux")
    assert cfg.backend == "auto"
    assert cfg.resolved_backend == "linux"
    assert cfg.llm == "ollama"
    assert cfg.fixture is None
    assert cfg.demo is False
    assert cfg.show_tools is False


def test_load_config_env_overrides() -> None:
    """Environment variables configure backend, fixture, and llm."""
    env = {
        "HWQ_BACKEND": "replay",
        "HWQ_FIXTURE": "synthetic-8gb-1of2",
        "HWQ_LLM": "scripted",
        "HWQ_SHOW_TOOLS": "1",
    }
    cfg = load_config(env, platform="linux")
    assert cfg.backend == "replay"
    assert cfg.resolved_backend == "replay"
    assert cfg.fixture == "synthetic-8gb-1of2"
    assert cfg.llm == "scripted"
    assert cfg.show_tools is True


def test_load_config_cli_overrides_env() -> None:
    """CLI flags take precedence over environment variables."""
    env = {
        "HWQ_BACKEND": "replay",
        "HWQ_FIXTURE": "env-fixture",
        "HWQ_LLM": "scripted",
    }
    cfg = load_config(
        env,
        cli_backend="linux",
        cli_fixture="cli-fixture",
        cli_llm="ollama",
        platform="linux",
    )
    assert cfg.backend == "linux"
    assert cfg.resolved_backend == "linux"
    assert cfg.fixture == "cli-fixture"
    assert cfg.llm == "ollama"


def test_load_config_invalid_env_backend() -> None:
    """Invalid HWQ_BACKEND in env raises ValueError."""
    with pytest.raises(ValueError, match="Invalid HWQ_BACKEND"):
        load_config({"HWQ_BACKEND": "invalid"})


def test_load_config_invalid_env_llm() -> None:
    """Invalid HWQ_LLM in env raises ValueError."""
    with pytest.raises(ValueError, match="Invalid HWQ_LLM"):
        load_config({"HWQ_LLM": "invalid"})


def test_load_config_demo_defaults() -> None:
    """Demo mode defaults to replay backend, synthetic fixture, and scripted LLM."""
    cfg = load_config({}, cli_demo=True, platform="linux")
    assert cfg.demo is True
    assert cfg.resolved_backend == "replay"
    assert cfg.llm == "scripted"
    assert cfg.fixture == "synthetic-8gb-1of2"
