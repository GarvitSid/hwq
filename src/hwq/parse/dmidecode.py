"""Parser for dmidecode Type 16 and Type 17 into MemoryTopologyFact (SRS 4.6, FR-PARSE-2)."""

from __future__ import annotations

import re

from hwq.facts import FactEnvelope, MemoryDeviceFact, MemoryTopologyFact, PrivilegeLevel
from hwq.models import RawResult
from hwq.parse.sanitize import sanitize_text

# Strict anchor on Size to ignore Volatile Size, Cache Size, Logical Size (FR-PARSE-2)
SIZE_STRICT_REGEX = re.compile(r"^\s*Size:\s*(.+)$", re.MULTILINE)
MAX_CAPACITY_REGEX = re.compile(r"^\s*Maximum Capacity:\s*(.+)$", re.MULTILINE)
NUM_DEVICES_REGEX = re.compile(r"^\s*Number Of Devices:\s*(\d+)", re.MULTILINE)
LOCATOR_REGEX = re.compile(r"^\s*Locator:\s*(.+)$", re.MULTILINE)
BANK_LOCATOR_REGEX = re.compile(r"^\s*Bank Locator:\s*(.+)$", re.MULTILINE)
FORM_FACTOR_REGEX = re.compile(r"^\s*Form Factor:\s*(.+)$", re.MULTILINE)
TYPE_REGEX = re.compile(r"^\s*Type:\s*(.+)$", re.MULTILINE)
SPEED_REGEX = re.compile(r"^\s*Speed:\s*(\d+)\s*(MT/s|MHz)?", re.MULTILINE)
MANUFACTURER_REGEX = re.compile(r"^\s*Manufacturer:\s*(.+)$", re.MULTILINE)
PART_NUMBER_REGEX = re.compile(r"^\s*Part Number:\s*(.+)$", re.MULTILINE)


def _parse_byte_size(size_str: str) -> int | None:
    """Parse DMI size string into bytes (e.g. '16 GB', '8192 MB', '1 TB')."""
    clean = size_str.strip().lower()
    if not clean or "no module" in clean or "unknown" in clean:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*([a-z]+)", clean)
    if not match:
        return None

    val_num = float(match.group(1))
    unit = match.group(2)

    multipliers = {
        "b": 1,
        "bytes": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
    }
    multiplier = multipliers.get(unit, 1024**3)
    return int(val_num * multiplier)


def parse_dmidecode_memory(raw: RawResult | str) -> FactEnvelope[MemoryTopologyFact]:
    """Parse dmidecode -t memory output into FactEnvelope[MemoryTopologyFact].

    Never raises (FR-PARSE-1).
    """
    source = ["cmd:dmidecode -t memory"]
    privilege: PrivilegeLevel = "root_via_sudo"

    if isinstance(raw, RawResult):
        source = list(raw.argv)
        if raw.status != "ok":
            return FactEnvelope(
                tool="get_memory_topology",
                status=raw.status,
                reason=raw.stderr or f"dmidecode failed with exit code {raw.exit_code}",
                source=source,
                privilege=privilege,
                confidence="low",
                data=MemoryTopologyFact(),
            )
        text = raw.stdout
    else:
        text = str(raw)

    try:
        # Split on Handle blocks
        blocks = re.split(r"(?=Handle\s+0x[0-9a-fA-F]+)", text)

        type16_blocks: list[str] = []
        type17_blocks: list[str] = []

        for block in blocks:
            if "DMI type 16" in block:
                type16_blocks.append(block)
            elif "DMI type 17" in block:
                type17_blocks.append(block)

        # Parse Type 16 Physical Memory Array
        array_max_capacity: int | None = None
        slots_total: int | None = None

        if type16_blocks:
            t16 = type16_blocks[0]
            max_cap_match = MAX_CAPACITY_REGEX.search(t16)
            if max_cap_match:
                array_max_capacity = _parse_byte_size(max_cap_match.group(1))

            num_dev_match = NUM_DEVICES_REGEX.search(t16)
            if num_dev_match:
                slots_total = int(num_dev_match.group(1))

        # Parse Type 17 Memory Devices
        devices: list[MemoryDeviceFact] = []
        installed_bytes = 0

        for t17 in type17_blocks:
            # Strictly anchor on Size: to ignore Volatile/Cache/Logical Size (FR-PARSE-2)
            size_match = SIZE_STRICT_REGEX.search(t17)
            size_bytes: int | None = None
            if size_match:
                size_bytes = _parse_byte_size(size_match.group(1))

            if size_bytes:
                installed_bytes += size_bytes

            locator_match = LOCATOR_REGEX.search(t17)
            locator = sanitize_text(locator_match.group(1)) if locator_match else None

            bank_match = BANK_LOCATOR_REGEX.search(t17)
            bank = sanitize_text(bank_match.group(1)) if bank_match else None

            ff_match = FORM_FACTOR_REGEX.search(t17)
            form_factor = sanitize_text(ff_match.group(1)) if ff_match else None

            type_match = TYPE_REGEX.search(t17)
            mem_type = sanitize_text(type_match.group(1)) if type_match else None

            speed_match = SPEED_REGEX.search(t17)
            speed_mts = int(speed_match.group(1)) if speed_match else None

            mfg_match = MANUFACTURER_REGEX.search(t17)
            mfg = sanitize_text(mfg_match.group(1)) if mfg_match else None

            part_match = PART_NUMBER_REGEX.search(t17)
            part = sanitize_text(part_match.group(1)) if part_match else None

            devices.append(
                MemoryDeviceFact(
                    locator=locator,
                    bank=bank,
                    size_bytes=size_bytes,
                    form_factor=form_factor,
                    memory_type=mem_type,
                    speed_mts=speed_mts,
                    manufacturer=mfg,
                    part_number=part,
                )
            )

        slots_used = sum(1 for d in devices if d.size_bytes is not None and d.size_bytes > 0)
        actual_slots = slots_total if slots_total is not None else len(devices)
        slots_free = max(0, actual_slots - slots_used)

        caveats: list[str] = []
        confidence = "high"

        # FR-UPG-5: Check mismatch between Type 16 device count and Type 17 entries
        if slots_total is not None and len(type17_blocks) != slots_total:
            caveats.append(
                f"DMI Type 16 specifies {slots_total} slots but {len(type17_blocks)} "
                "Type 17 memory device records were found."
            )
            confidence = "medium"

        if not type16_blocks and not type17_blocks:
            caveats.append("No DMI Type 16 or 17 memory records found.")
            confidence = "low"

        fact = MemoryTopologyFact(
            array_max_capacity_bytes=array_max_capacity,
            slots_total=actual_slots,
            slots_used=slots_used,
            slots_free=slots_free,
            installed_bytes=installed_bytes,
            devices=devices,
        )

        return FactEnvelope(
            tool="get_memory_topology",
            status="ok" if (type16_blocks or type17_blocks) else "partial",
            source=source,
            privilege=privilege,
            confidence=confidence,  # type: ignore[arg-type]
            caveats=caveats,
            data=fact,
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_memory_topology",
            status="error",
            reason=f"Failed parsing dmidecode memory: {exc}",
            source=source,
            privilege=privilege,
            confidence="low",
            data=MemoryTopologyFact(),
        )
