"""Tests for hardware tools and registry (SRS 4.2, 5, AT-3, AT-8)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.facts import (
    CpuFact,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
    SystemOverviewFact,
)
from hwq.tools.cpu import CpuTool
from hwq.tools.gpu import GpuTool
from hwq.tools.memory import MemorySummaryTool, MemoryTopologyTool
from hwq.tools.storage import StorageTool
from hwq.tools.system import SystemTool


def test_tool_schemas_and_properties() -> None:
    cpu_tool = CpuTool()
    assert cpu_tool.name == "get_cpu_info"
    assert "architecture" in cpu_tool.description.lower()
    assert cpu_tool.parameters_schema["type"] == "object"

    storage_tool = StorageTool()
    assert storage_tool.name == "get_storage_devices"
    assert storage_tool.parameters_schema["type"] == "object"

    gpu_tool = GpuTool()
    assert gpu_tool.name == "get_gpu_info"

    mem_sum = MemorySummaryTool()
    assert mem_sum.name == "get_memory_summary"

    mem_top = MemoryTopologyTool()
    assert mem_top.name == "get_memory_topology"

    sys_tool = SystemTool()
    assert sys_tool.name == "get_system_overview"


def test_cpu_tool_execution() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")
    tool = CpuTool()
    env = tool.execute(backend)

    assert env.status == "ok"
    assert isinstance(env.data, CpuFact)
    assert env.data.model_name is not None
    assert env.data.cores == 4
    assert env.data.threads == 8


def test_memory_tools_execution() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")

    sum_tool = MemorySummaryTool()
    sum_env = sum_tool.execute(backend)
    assert sum_env.status == "ok"
    assert isinstance(sum_env.data, MemorySummaryFact)
    assert sum_env.data.total_bytes > 0

    top_tool = MemoryTopologyTool()
    top_env = top_tool.execute(backend)
    assert top_env.status == "ok"
    assert isinstance(top_env.data, MemoryTopologyFact)
    assert top_env.data.slots_used == 1
    assert top_env.data.slots_free == 1


def test_storage_tool_at3_nvme_plus_sata() -> None:
    """AT-3 'Is my SSD NVMe?' on nvme-plus-sata: correct per-disk answer with evidence."""
    backend = load_fixture_backend("nvme-plus-sata")
    tool = StorageTool()
    env = tool.execute(backend)

    assert env.status == "ok"
    assert isinstance(env.data, StorageFact)
    devices = {d.name: d for d in env.data.devices}

    assert "nvme0n1" in devices
    nvme_dev = devices["nvme0n1"]
    assert nvme_dev.is_nvme is True
    assert nvme_dev.is_ssd is True
    assert nvme_dev.nvme_evidence is not None

    assert "sda" in devices
    sda_dev = devices["sda"]
    assert sda_dev.is_nvme is False
    assert sda_dev.is_ssd is False
    assert sda_dev.transport == "sata"


def test_gpu_tool_at8_shared_memory() -> None:
    """AT-8 igpu-amd: 'How much video memory?' -> shared memory, no dedicated VRAM claimed."""
    backend = load_fixture_backend("igpu-amd")
    tool = GpuTool()
    env = tool.execute(backend)

    assert env.status == "ok"
    assert isinstance(env.data, GpuFact)
    assert len(env.data.devices) >= 1
    assert any(d.is_integrated for d in env.data.devices)
    # Check shared memory note is present in caveats
    assert any("shared system memory" in c.lower() for c in env.caveats)


def test_system_tool_execution() -> None:
    backend = load_fixture_backend("synthetic-8gb-1of2")
    tool = SystemTool()
    env = tool.execute(backend)

    assert env.status == "ok"
    assert isinstance(env.data, SystemOverviewFact)
    assert env.data.product_name is not None
