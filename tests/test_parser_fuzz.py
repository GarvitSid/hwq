"""Fuzz testing for parsers to guarantee FR-PARSE-1 (parsers never raise)."""

from hypothesis import given
from hypothesis import strategies as st

from hwq.facts import FactEnvelope
from hwq.parse import (
    parse_dmidecode_memory,
    parse_gpu_info,
    parse_lsblk,
    parse_lscpu,
    parse_meminfo,
    parse_system_overview,
    sanitize_text,
)


@given(st.text())
def test_fuzz_sanitize_text(val: str) -> None:
    """sanitize_text never raises on arbitrary strings and adheres to length bounds."""
    res = sanitize_text(val)
    if res is not None:
        assert len(res) <= 120


@given(st.text())
def test_fuzz_parse_meminfo(raw_text: str) -> None:
    """parse_meminfo never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_meminfo(raw_text)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_memory_summary"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")


@given(st.text())
def test_fuzz_parse_lscpu(raw_text: str) -> None:
    """parse_lscpu never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_lscpu(raw_text)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_cpu_info"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")


@given(st.text())
def test_fuzz_parse_lsblk(raw_text: str) -> None:
    """parse_lsblk never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_lsblk(raw_text)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_storage_devices"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")


@given(st.text())
def test_fuzz_parse_dmidecode_memory(raw_text: str) -> None:
    """parse_dmidecode_memory never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_dmidecode_memory(raw_text)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_memory_topology"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")


@given(st.text(), st.text())
def test_fuzz_parse_gpu_info(lspci_text: str, nvidia_text: str) -> None:
    """parse_gpu_info never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_gpu_info(lspci_text, nvidia_text)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_gpu_info"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")


@given(st.dictionaries(st.text(max_size=10), st.text(max_size=50)), st.text(), st.text())
def test_fuzz_parse_system_overview(dmi: dict[str, str], os_rel: str, kernel_rel: str) -> None:
    """parse_system_overview never raises on arbitrary input (FR-PARSE-1)."""
    env = parse_system_overview(dmi, os_rel, kernel_rel)
    assert isinstance(env, FactEnvelope)
    assert env.tool == "get_system_overview"
    assert env.status in ("ok", "partial", "unavailable", "permission_denied", "timeout", "error")
