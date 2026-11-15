"""Tests for numeric grounding validation (SRS 4.10, FR-GRD-1)."""

from __future__ import annotations

from hwq.facts import (
    CpuFact,
    FactEnvelope,
    MemoryTopologyFact,
    StorageDeviceFact,
    StorageFact,
)
from hwq.grounding import (
    build_ground_truth,
    extract_numeric_tokens,
    validate_numeric_grounding,
)
from hwq.units import GIB
from hwq.upgrade import MemoryUpgradeAnalysis


def test_extract_numeric_tokens() -> None:
    text = (
        "You have 16 GiB of RAM in 1 of 2 slots, with a maximum capacity of 64 GB. "
        "The CPU has 8 cores and 16 threads running at 2.40 GHz. The memory speed is 3200 MT/s."
    )
    tokens = extract_numeric_tokens(text)
    assert len(tokens) >= 7

    units = [t.unit for t in tokens]
    assert "gib" in units
    assert "slots" in units
    assert "gb" in units
    assert "cores" in units
    assert "threads" in units
    assert "ghz" in units
    assert "mt/s" in units


def test_grounding_accepts_valid_facts() -> None:
    envelopes = [
        FactEnvelope[CpuFact](
            tool="get_cpu_info",
            status="ok",
            data=CpuFact(cores=8, threads=16, max_mhz=2400.0),
        ),
        FactEnvelope[MemoryTopologyFact](
            tool="get_memory_topology",
            status="ok",
            data=MemoryTopologyFact(
                slots_total=2,
                slots_used=1,
                slots_free=1,
                installed_bytes=16 * GIB,
                array_max_capacity_bytes=64 * GIB,
            ),
        ),
    ]
    upgrade_analysis = MemoryUpgradeAnalysis(
        installed_bytes=16 * GIB,
        slots_total=2,
        slots_used=1,
        slots_free=1,
        max_capacity_bytes=64 * GIB,
        headroom_bytes=48 * GIB,
        per_slot_suggestion_bytes=32 * GIB,
        upgradeable=True,
        summary="You can upgrade by adding up to 32 GiB module per empty slot.",
    )

    gt = build_ground_truth(envelopes, upgrade_analysis)

    valid_draft = (
        "Your system has 16 GiB installed across 1 of 2 slots. Maximum capacity is 64 GiB. "
        "The CPU has 8 cores and 16 threads. You can upgrade with a 32 GiB module."
    )
    res = validate_numeric_grounding(valid_draft, gt)
    assert res.is_grounded is True
    assert len(res.unmatched_tokens) == 0


def test_grounding_rejects_hallucinated_numbers() -> None:
    """Grounding must reject a wrong number in a draft (FR-GRD-1)."""
    envelopes = [
        FactEnvelope[CpuFact](
            tool="get_cpu_info",
            status="ok",
            data=CpuFact(cores=8, threads=16),
        ),
        FactEnvelope[MemoryTopologyFact](
            tool="get_memory_topology",
            status="ok",
            data=MemoryTopologyFact(
                slots_total=2,
                slots_used=1,
                installed_bytes=16 * GIB,
                array_max_capacity_bytes=64 * GIB,
            ),
        ),
    ]
    gt = build_ground_truth(envelopes)

    # Hallucinated 32 GiB installed (real is 16 GiB) and 12 cores (real is 8)
    hallucinated_draft = "You have 32 GiB of installed RAM and a CPU with 12 cores."
    res = validate_numeric_grounding(hallucinated_draft, gt)

    assert res.is_grounded is False
    assert len(res.unmatched_tokens) == 2
    raw_unmatched = [t.raw_text for t in res.unmatched_tokens]
    assert "32 GiB" in raw_unmatched
    assert "12 cores" in raw_unmatched
    assert "Grounding failure" in (res.discrepancy_explanation or "")


def test_grounding_storage_tolerance() -> None:
    """A 256060514304-byte disk matches both 238 GiB and 256 GB within 0.5% tolerance."""
    disk_bytes = 256060514304
    envelopes = [
        FactEnvelope[StorageFact](
            tool="get_storage_devices",
            status="ok",
            data=StorageFact(
                devices=[StorageDeviceFact(name="nvme0n1", size_bytes=disk_bytes)]
            ),
        )
    ]
    gt = build_ground_truth(envelopes)

    # Both binary and decimal approximations pass 0.5% tolerance
    draft = "Drive nvme0n1 has a capacity of 238 GiB (about 256 GB)."
    res = validate_numeric_grounding(draft, gt)
    assert res.is_grounded is True
