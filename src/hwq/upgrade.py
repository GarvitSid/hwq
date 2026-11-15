"""Memory upgrade advisor and installed vs usable analysis (SRS 4.7, FR-UPG-1..5, FR-MEM-1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hwq.facts import ConfidenceLevel, FactEnvelope, MemorySummaryFact, MemoryTopologyFact
from hwq.units import GIB, format_bytes

CANDIDATE_MODULE_SIZES_BYTES: list[int] = [
    128 * GIB,
    64 * GIB,
    32 * GIB,
    16 * GIB,
    8 * GIB,
    4 * GIB,
]


class MemoryUpgradeAnalysis(BaseModel):
    """Structured memory upgrade evaluation and capacity analysis."""

    model_config = ConfigDict(frozen=True)

    installed_bytes: int = 0
    usable_bytes: int | None = None
    slots_total: int | None = None
    slots_used: int = 0
    slots_free: int = 0
    max_capacity_bytes: int | None = None
    headroom_bytes: int | None = None
    per_slot_suggestion_bytes: int | None = None
    is_soldered: bool = False
    upgradeable: bool = False
    summary: str
    caveats: list[str] = Field(default_factory=list)
    installed_vs_usable_note: str | None = None
    confidence: ConfidenceLevel = "high"


def analyze_memory(
    topology_env: FactEnvelope[MemoryTopologyFact] | None,
    summary_env: FactEnvelope[MemorySummaryFact] | None,
) -> MemoryUpgradeAnalysis:
    """Analyze memory topology and summary to advise on memory upgrade options.

    Adheres strictly to FR-UPG-1 through FR-UPG-5, FR-MEM-1, AT-1, and AT-10:
    - Computes installed, slots_total, slots_free, max_capacity, and headroom.
    - Selects the largest candidate from {4, 8, 16, 32, 64, 128} GiB <= headroom / slots_free.
    - Evaluates soldered memory heuristic (no free slots or 'Row of chips' form factor).
    - Detects type 16 vs type 17 device count mismatch and lowers confidence.
    - Compares DMI installed memory vs /proc/meminfo MemTotal neutrally.
    """
    caveats: list[str] = []
    confidence: ConfidenceLevel = "high"

    # Usable bytes from meminfo
    usable_bytes: int | None = None
    if summary_env is not None and summary_env.status == "ok":
        if isinstance(summary_env.data, MemorySummaryFact):
            usable_bytes = summary_env.data.total_bytes
        elif isinstance(summary_env.data, dict) and "total_bytes" in summary_env.data:
            usable_bytes = int(summary_env.data["total_bytes"])

    # If DMI topology is unavailable / permission denied (AT-2 degraded mode)
    if topology_env is None or topology_env.status != "ok" or not topology_env.data:
        reason = topology_env.reason if topology_env else "DMI data not provided"
        usable_str = format_bytes(usable_bytes) if usable_bytes is not None else "Unknown"
        summary = (
            f"Usable system memory is {usable_str}. Maximum memory capacity and physical slot "
            f"count cannot be determined because DMI data is unavailable ({reason})."
        )
        if topology_env and topology_env.status == "permission_denied":
            caveats.append(
                "dmidecode requires root privileges. Run 'hwq doctor --print-sudoers' to "
                "configure a safe, pinned sudo rule."
            )
        elif topology_env and topology_env.status == "unavailable":
            caveats.append(
                "SMBIOS/DMI tables are not exposed by the system or hypervisor."
            )

        return MemoryUpgradeAnalysis(
            installed_bytes=0,
            usable_bytes=usable_bytes,
            slots_total=None,
            slots_used=0,
            slots_free=0,
            max_capacity_bytes=None,
            headroom_bytes=None,
            per_slot_suggestion_bytes=None,
            is_soldered=False,
            upgradeable=False,
            summary=summary,
            caveats=caveats,
            installed_vs_usable_note=None,
            confidence="low",
        )

    # Topology data is present
    top_data: MemoryTopologyFact
    if isinstance(topology_env.data, MemoryTopologyFact):
        top_data = topology_env.data
    else:
        top_data = MemoryTopologyFact.model_validate(topology_env.data)

    installed_bytes = top_data.installed_bytes
    max_cap_bytes = top_data.array_max_capacity_bytes
    slots_total = top_data.slots_total
    slots_used = top_data.slots_used
    slots_free = top_data.slots_free

    # FR-UPG-5: Check type 16 vs type 17 slot count mismatch
    num_type17_devices = len(top_data.devices)
    if slots_total is not None and num_type17_devices > 0 and slots_total != num_type17_devices:
        confidence = "low"
        caveats.append(
            f"Mismatch between memory array device count ({slots_total}) and detected physical "
            f"slots ({num_type17_devices}). Confidence lowered."
        )

    # FR-UPG-3: Always caveat that DMI does not expose per-slot limits
    caveats.append(
        "DMI data does not report per-slot maximum capacity limits; verify motherboard "
        "specifications before purchasing."
    )

    # FR-UPG-4: Check soldered-memory heuristic
    is_soldered = False
    for dev in top_data.devices:
        form = (dev.form_factor or "").lower()
        loc = (dev.locator or "").lower()
        mem_type = (dev.memory_type or "").lower()
        if "row of chips" in form or "onboard" in loc or "lpddr" in mem_type:
            is_soldered = True
            break

    # If no free slots remain
    if slots_free == 0:
        is_soldered = is_soldered or True

    # FR-UPG-1: Compute headroom
    headroom_bytes: int | None = None
    if max_cap_bytes is not None:
        headroom_bytes = max(0, max_cap_bytes - installed_bytes)

    # FR-UPG-2: Compute per_slot_suggestion
    per_slot_suggestion_bytes: int | None = None
    if slots_free > 0 and headroom_bytes is not None and headroom_bytes > 0:
        max_per_slot = headroom_bytes // slots_free
        for candidate in CANDIDATE_MODULE_SIZES_BYTES:
            if candidate <= max_per_slot:
                per_slot_suggestion_bytes = candidate
                break

    upgradeable = (slots_free > 0) and (headroom_bytes is not None and headroom_bytes > 0)

    # Summary text construction (AT-1)
    installed_str = format_bytes(installed_bytes)
    max_cap_str = format_bytes(max_cap_bytes) if max_cap_bytes is not None else "Unknown"

    if is_soldered and slots_free == 0:
        summary = (
            f"Installed memory is {installed_str} in {slots_used} of {slots_total or slots_used} "
            f"slot(s). No empty memory slots are available (memory may be soldered). "
            f"RAM upgrade is probably not possible without replacing existing modules or board."
        )
    elif upgradeable:
        sugg_str = (
            format_bytes(per_slot_suggestion_bytes)
            if per_slot_suggestion_bytes is not None
            else "standard"
        )
        headroom_str = (
            format_bytes(headroom_bytes) if headroom_bytes is not None else "unknown headroom"
        )
        summary = (
            f"Installed memory is {installed_str} using {slots_used} of {slots_total} slots "
            f"({slots_free} slot(s) free). Maximum capacity is {max_cap_str} (headroom: "
            f"{headroom_str}). You can upgrade by adding up to {sugg_str} module per empty slot."
        )
    else:
        summary = (
            f"Installed memory is {installed_str} in {slots_used} of {slots_total or slots_used} "
            f"slots. System is currently at or near maximum capacity ({max_cap_str})."
        )

    # FR-MEM-1 & AT-10: Installed vs usable explanation
    installed_vs_usable_note: str | None = None
    if usable_bytes is not None and installed_bytes > 0:
        usable_str = format_bytes(usable_bytes)
        diff_bytes = max(0, installed_bytes - usable_bytes)
        if diff_bytes > (100 * 1024 * 1024):  # meaningful difference > 100 MiB
            diff_str = format_bytes(diff_bytes)
            installed_vs_usable_note = (
                f"Installed memory is {installed_str}, while usable system memory (MemTotal) "
                f"is {usable_str}. The difference of ~{diff_str} is often reserved by "
                f"integrated graphics or hardware firmware."
            )

    return MemoryUpgradeAnalysis(
        installed_bytes=installed_bytes,
        usable_bytes=usable_bytes,
        slots_total=slots_total,
        slots_used=slots_used,
        slots_free=slots_free,
        max_capacity_bytes=max_cap_bytes,
        headroom_bytes=headroom_bytes,
        per_slot_suggestion_bytes=per_slot_suggestion_bytes,
        is_soldered=is_soldered,
        upgradeable=upgradeable,
        summary=summary,
        caveats=caveats,
        installed_vs_usable_note=installed_vs_usable_note,
        confidence=confidence,
    )
