"""Tests for deterministic template fallback generator (SRS 4.10, AT-1, AT-2, AT-3, AT-8, AT-10)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.templates import build_template_answer
from hwq.tools.cpu import CpuTool
from hwq.tools.gpu import GpuTool
from hwq.tools.memory import MemorySummaryTool, MemoryTopologyTool
from hwq.tools.storage import StorageTool


def test_template_at1_synthetic_8gb_1of2() -> None:
    """AT-1 RAM upgrade on 8gb-1of2: states 1 of 2 slots used, 64 GiB max, up to 32 GiB module."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    mem_env = MemorySummaryTool().execute(backend)
    top_env = MemoryTopologyTool().execute(backend)

    ans = build_template_answer([mem_env, top_env], query="Can I upgrade my RAM?")
    assert "1 of 2 slots" in ans
    assert "64 GiB" in ans
    assert "32 GiB" in ans
    assert "per-slot" in ans.lower()  # DMI caveat


def test_template_at2_no_sudo_degraded_mode() -> None:
    """AT-2 RAM question on no-sudo: gives usable RAM, states slots unknown, explains fix."""
    backend = load_fixture_backend("no-sudo")
    mem_env = MemorySummaryTool().execute(backend)
    top_env = MemoryTopologyTool().execute(backend)

    ans = build_template_answer([mem_env, top_env], query="How much RAM can I upgrade to?")
    assert "cannot be determined" in ans
    assert "hwq doctor --print-sudoers" in ans


def test_template_at3_nvme_plus_sata() -> None:
    """AT-3 'Is my SSD NVMe?' on nvme-plus-sata: correct per-disk answer with evidence."""
    backend = load_fixture_backend("nvme-plus-sata")
    storage_env = StorageTool().execute(backend)

    ans = build_template_answer([storage_env], query="Is my SSD NVMe?")
    assert "nvme0n1" in ans
    assert "NVME SSD" in ans
    assert "evidence" in ans.lower()
    assert "sda" in ans
    assert "SATA" in ans


def test_template_at8_gpu_shared_memory() -> None:
    """AT-8 igpu-amd: 'How much video memory?' -> shared memory, no dedicated VRAM claimed."""
    backend = load_fixture_backend("igpu-amd")
    gpu_env = GpuTool().execute(backend)

    ans = build_template_answer([gpu_env], query="How much video memory?")
    assert "shared" in ans.lower()
    assert "dedicated vram is not reported" in ans.lower()


def test_template_cpu() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")
    cpu_env = CpuTool().execute(backend)

    ans = build_template_answer([cpu_env], query="What CPU do I have?")
    assert "i5-1135G7" in ans
    assert "4 cores" in ans
    assert "8 threads" in ans
