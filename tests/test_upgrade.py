"""Tests for memory upgrade advisor and installed vs usable analysis (SRS 4.7, AT-1/2/10)."""

from __future__ import annotations

from hwq.exec.backend import load_fixture_backend
from hwq.facts import FactEnvelope, MemorySummaryFact, MemoryTopologyFact
from hwq.parse.dmidecode import parse_dmidecode_memory
from hwq.parse.meminfo import parse_meminfo
from hwq.units import GIB
from hwq.upgrade import analyze_memory


def test_upgrade_advisor_at1_synthetic_8gb_1of2() -> None:
    """AT-1 RAM upgrade on 8gb-1of2: states 1 of 2 slots used, 64 GiB max, up to 32 GiB module."""
    backend = load_fixture_backend("synthetic-8gb-1of2")
    from hwq.exec.allowlist import ALLOWED_COMMANDS

    raw_dmi = backend.run(ALLOWED_COMMANDS["memory_dmi"])
    top_env = parse_dmidecode_memory(raw_dmi)

    raw_mem = backend.read_text("/proc/meminfo")
    mem_env = parse_meminfo(raw_mem)

    analysis = analyze_memory(top_env, mem_env)

    # 1 of 2 slots used, 1 free slot
    assert analysis.slots_total == 2
    assert analysis.slots_used == 1
    assert analysis.slots_free == 1
    assert analysis.installed_bytes == 16 * GIB
    assert analysis.max_capacity_bytes == 64 * GIB
    assert analysis.headroom_bytes == 48 * GIB

    # Headroom is 48 GiB, 1 free slot => suggestion is 32 GiB module
    assert analysis.per_slot_suggestion_bytes == 32 * GIB
    assert analysis.upgradeable is True
    assert not analysis.is_soldered

    # Check caveat about DMI not reporting per-slot limits (FR-UPG-3)
    assert any("per-slot" in c.lower() for c in analysis.caveats)

    # Check summary content contains key facts
    assert "1 of 2 slots" in analysis.summary
    assert "64 GiB" in analysis.summary
    assert "32 GiB" in analysis.summary


def test_upgrade_advisor_soldered_8gb_no_free_slots() -> None:
    """Soldered memory with no free slots -> upgrade probably not possible (FR-UPG-4)."""
    backend = load_fixture_backend("soldered-8gb-no-free-slots")
    from hwq.exec.allowlist import ALLOWED_COMMANDS

    raw_dmi = backend.run(ALLOWED_COMMANDS["memory_dmi"])
    top_env = parse_dmidecode_memory(raw_dmi)
    raw_mem = backend.read_text("/proc/meminfo")
    mem_env = parse_meminfo(raw_mem)

    analysis = analyze_memory(top_env, mem_env)

    assert analysis.slots_total == 1
    assert analysis.slots_used == 1
    assert analysis.slots_free == 0
    assert analysis.is_soldered is True
    assert analysis.upgradeable is False
    assert analysis.per_slot_suggestion_bytes is None
    assert "soldered" in analysis.summary.lower()


def test_upgrade_advisor_at2_no_sudo_degraded_mode() -> None:
    """AT-2 on no-sudo: gives usable RAM, says max and slots cannot be determined, explains fix."""
    backend = load_fixture_backend("no-sudo")
    from hwq.exec.allowlist import ALLOWED_COMMANDS

    raw_dmi = backend.run(ALLOWED_COMMANDS["memory_dmi"])
    top_env = parse_dmidecode_memory(raw_dmi)
    assert top_env.status == "permission_denied"

    raw_mem = backend.read_text("/proc/meminfo")
    mem_env = parse_meminfo(raw_mem)

    analysis = analyze_memory(top_env, mem_env)

    assert analysis.slots_total is None
    assert analysis.max_capacity_bytes is None
    assert analysis.upgradeable is False
    assert "cannot be determined" in analysis.summary
    assert any("hwq doctor --print-sudoers" in c for c in analysis.caveats)


def test_upgrade_advisor_at10_installed_vs_usable() -> None:
    """AT-10: 8 GiB installed vs ~5.9 GiB MemTotal explained without inventing cause."""
    top_env = FactEnvelope[MemoryTopologyFact](
        tool="get_memory_topology",
        status="ok",
        data=MemoryTopologyFact(
            array_max_capacity_bytes=16 * GIB,
            slots_total=2,
            slots_used=1,
            slots_free=1,
            installed_bytes=8 * GIB,  # 8 GiB = 8589934592 B
        ),
    )
    # MemTotal ~ 5.9 GiB = 6334976000 B
    mem_env = FactEnvelope[MemorySummaryFact](
        tool="get_memory_summary",
        status="ok",
        data=MemorySummaryFact(
            total_bytes=6334976000,
            free_bytes=2000000000,
            available_bytes=3000000000,
        ),
    )

    analysis = analyze_memory(top_env, mem_env)
    assert analysis.installed_vs_usable_note is not None
    assert "8 GiB" in analysis.installed_vs_usable_note
    assert "5.9 GiB" in analysis.installed_vs_usable_note
    # Explain without asserting single definitive cause (integrated graphics or firmware)
    assert "often reserved by integrated graphics or" in analysis.installed_vs_usable_note
