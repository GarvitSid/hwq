"""Hardware tool definitions and registry (SRS 4.2, 5, FR-TOOL-1)."""

from __future__ import annotations

from hwq.tools.base import Tool, create_backend
from hwq.tools.cpu import CpuTool
from hwq.tools.gpu import GpuTool
from hwq.tools.memory import MemorySummaryTool, MemoryTopologyTool
from hwq.tools.storage import StorageTool
from hwq.tools.system import SystemTool


def get_all_tools() -> list[Tool]:
    """Return an instantiated list of all supported hardware tools."""
    return [
        SystemTool(),
        CpuTool(),
        MemorySummaryTool(),
        MemoryTopologyTool(),
        StorageTool(),
        GpuTool(),
    ]


__all__ = [
    "CpuTool",
    "GpuTool",
    "MemorySummaryTool",
    "MemoryTopologyTool",
    "StorageTool",
    "SystemTool",
    "Tool",
    "create_backend",
    "get_all_tools",
]
