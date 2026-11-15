"""Deterministic template fallback generator from verified hardware facts (SRS 4.10, FR-GRD-2)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hwq.facts import (
    CpuFact,
    FactEnvelope,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
    SystemOverviewFact,
)
from hwq.units import format_bytes, format_frequency
from hwq.upgrade import MemoryUpgradeAnalysis, analyze_memory


def build_template_answer(
    envelopes: Sequence[FactEnvelope[Any]],
    query: str = "",
    upgrade_analysis: MemoryUpgradeAnalysis | None = None,
) -> str:
    """Build a deterministic, 100% grounded natural language answer from fact envelopes."""
    q_lower = query.lower()

    # Index envelopes by tool name
    env_map: dict[str, FactEnvelope[Any]] = {e.tool: e for e in envelopes}

    # If memory / RAM / upgrade question
    is_memory_q = any(w in q_lower for w in ("ram", "memory", "upgrade", "dimm", "slot"))
    is_cpu_q = any(w in q_lower for w in ("cpu", "processor", "core", "thread", "ghz", "mhz"))
    is_storage_q = any(w in q_lower for w in ("ssd", "nvme", "disk", "storage", "drive", "hdd"))
    is_gpu_q = any(w in q_lower for w in ("gpu", "graphics", "video", "vram", "display"))
    is_system_q = any(w in q_lower for w in ("system", "bios", "motherboard", "os", "kernel"))

    # If specific category query, prioritize it
    sections: list[str] = []

    has_no_cat = not any((is_cpu_q, is_storage_q, is_gpu_q, is_system_q))
    if is_memory_q or (has_no_cat and "get_memory_topology" in env_map):
        mem_sec = _build_memory_section(env_map, upgrade_analysis)
        if mem_sec:
            sections.append(mem_sec)

    if is_cpu_q or (not sections and "get_cpu_info" in env_map):
        cpu_sec = _build_cpu_section(env_map)
        if cpu_sec:
            sections.append(cpu_sec)

    if is_storage_q or (not sections and "get_storage_devices" in env_map):
        storage_sec = _build_storage_section(env_map)
        if storage_sec:
            sections.append(storage_sec)

    if is_gpu_q or (not sections and "get_gpu_info" in env_map):
        gpu_sec = _build_gpu_section(env_map)
        if gpu_sec:
            sections.append(gpu_sec)

    if is_system_q or (not sections and "get_system_overview" in env_map):
        sys_sec = _build_system_section(env_map)
        if sys_sec:
            sections.append(sys_sec)

    if not sections:
        # Fallback across all available envelopes
        for sec in (
            _build_memory_section(env_map, upgrade_analysis),
            _build_cpu_section(env_map),
            _build_storage_section(env_map),
            _build_gpu_section(env_map),
            _build_system_section(env_map),
        ):
            if sec:
                sections.append(sec)

    if not sections:
        return "No hardware data available to answer the question."
    return "\n\n".join(sections)


def _build_memory_section(
    env_map: dict[str, FactEnvelope[Any]],
    upgrade_analysis: MemoryUpgradeAnalysis | None = None,
) -> str | None:
    top_env = env_map.get("get_memory_topology")
    sum_env = env_map.get("get_memory_summary")

    if top_env is None and sum_env is None:
        return None

    analysis = upgrade_analysis
    if analysis is None:
        typed_top: FactEnvelope[MemoryTopologyFact] | None = (
            top_env if top_env and isinstance(top_env.data, (MemoryTopologyFact, dict)) else None
        )
        typed_sum: FactEnvelope[MemorySummaryFact] | None = (
            sum_env if sum_env and isinstance(sum_env.data, (MemorySummaryFact, dict)) else None
        )
        analysis = analyze_memory(typed_top, typed_sum)

    lines: list[str] = [analysis.summary]

    if analysis.installed_vs_usable_note:
        lines.append(analysis.installed_vs_usable_note)

    if analysis.caveats:
        for c in analysis.caveats:
            lines.append(f"Note: {c}")

    return "\n".join(lines)


def _build_cpu_section(env_map: dict[str, FactEnvelope[Any]]) -> str | None:
    env = env_map.get("get_cpu_info")
    if env is None or env.status != "ok" or not isinstance(env.data, CpuFact):
        return None
    data = env.data

    model = data.model_name or "Unknown CPU"
    arch = data.architecture or "unknown architecture"
    cores = data.cores or "unknown"
    threads = data.threads or "unknown"

    freq_info = ""
    if data.max_mhz:
        freq_info = f" running up to {format_frequency(data.max_mhz)}"

    return f"CPU: {model} ({arch}, {cores} cores, {threads} threads{freq_info})."


def _build_storage_section(env_map: dict[str, FactEnvelope[Any]]) -> str | None:
    env = env_map.get("get_storage_devices")
    if env is None or env.status != "ok" or not isinstance(env.data, StorageFact):
        return None
    data = env.data
    if not data.devices:
        return "No storage block devices detected."

    disk_lines: list[str] = []
    for dev in data.devices:
        media = "SSD" if dev.is_ssd else ("HDD" if dev.rotational else "disk")
        tran = dev.transport or ("nvme" if dev.is_nvme else "sata")
        cap = format_bytes(dev.size_bytes, include_decimal=True)
        evidence = (
            f" (evidence: {dev.nvme_evidence})" if dev.is_nvme and dev.nvme_evidence else ""
        )
        disk_lines.append(
            f"- {dev.name}: {cap} {tran.upper()} {media} ({dev.model or 'generic'}){evidence}"
        )

    return "Storage Devices:\n" + "\n".join(disk_lines)


def _build_gpu_section(env_map: dict[str, FactEnvelope[Any]]) -> str | None:
    env = env_map.get("get_gpu_info")
    if env is None or env.status != "ok" or not isinstance(env.data, GpuFact):
        if env and env.status == "unavailable":
            return f"GPU information is unavailable: {env.reason or 'lspci tool not found'}."
        return None
    data = env.data
    if not data.devices:
        return "No GPU or display controllers detected."

    gpu_lines: list[str] = []
    has_integrated = False
    for dev in data.devices:
        gpu_type = "integrated" if dev.is_integrated else "discrete"
        if dev.is_integrated:
            has_integrated = True
        gpu_lines.append(f"- {dev.vendor} {dev.device_name} ({gpu_type} GPU on slot {dev.slot})")

    out = "Graphics / GPU:\n" + "\n".join(gpu_lines)
    if has_integrated:
        out += (
            "\nDedicated VRAM is not reported for integrated GPUs; "
            "memory is shared dynamically with system RAM."
        )
    return out


def _build_system_section(env_map: dict[str, FactEnvelope[Any]]) -> str | None:
    env = env_map.get("get_system_overview")
    if env is None or env.status != "ok" or not isinstance(env.data, SystemOverviewFact):
        return None
    data = env.data
    prod = data.product_name or data.sys_vendor or "Linux System"
    os_name = data.os_pretty_name or "Linux"
    kernel = f" (kernel {data.kernel_release})" if data.kernel_release else ""
    return f"System: {prod} running {os_name}{kernel}."
