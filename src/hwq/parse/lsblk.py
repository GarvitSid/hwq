"""Parser for lsblk JSON into StorageFact (SRS 4.6, FR-PARSE-3)."""

from __future__ import annotations

import json
from typing import Any

from hwq.facts import FactEnvelope, StorageDeviceFact, StorageFact
from hwq.models import RawResult
from hwq.parse.sanitize import sanitize_text


def _parse_bool(val: Any) -> bool:
    """Coerce boolean representations from JSON: bool, '0'/'1', 0/1."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "t")
    return False


def _parse_size(val: Any) -> int | None:
    """Coerce byte size from JSON int or numeric string."""
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def parse_lsblk(raw: RawResult | str) -> FactEnvelope[StorageFact]:
    """Parse lsblk JSON into FactEnvelope[StorageFact].

    Never raises (FR-PARSE-1).
    """
    source = ["cmd:lsblk -J -b -d -o NAME,TYPE,SIZE,MODEL,ROTA,TRAN,RM,HOTPLUG"]
    if isinstance(raw, RawResult):
        source = list(raw.argv)
        if raw.status != "ok":
            return FactEnvelope(
                tool="get_storage_devices",
                status=raw.status,
                reason=raw.stderr or f"lsblk failed with exit code {raw.exit_code}",
                source=source,
                confidence="low",
                data=StorageFact(),
            )
        text = raw.stdout
    else:
        text = str(raw)

    try:
        data = json.loads(text)
        blockdevices: list[dict[str, Any]] = []
        if isinstance(data, dict) and "blockdevices" in data:
            blockdevices = data["blockdevices"]

        devices: list[StorageDeviceFact] = []
        for dev in blockdevices:
            if not isinstance(dev, dict):
                continue
            name = str(dev.get("name", "")).strip()
            if not name:
                continue

            dev_type = sanitize_text(dev.get("type"))
            size_bytes = _parse_size(dev.get("size"))
            model = sanitize_text(dev.get("model"))
            rotational = _parse_bool(dev.get("rota")) if "rota" in dev else None
            transport = sanitize_text(dev.get("tran"))
            removable = _parse_bool(dev.get("rm"))
            hotplug = _parse_bool(dev.get("hotplug"))

            # Derive is_nvme (FR-PARSE-3, AT-3)
            is_nvme = False
            nvme_evidence: str | None = None
            if transport == "nvme":
                is_nvme = True
                nvme_evidence = "transport protocol is reported as 'nvme'"
            elif name.startswith("nvme"):
                is_nvme = True
                nvme_evidence = f"device name prefix '{name}' indicates an NVMe block device"

            # Derive is_ssd from non-rotational
            is_ssd = False
            confidence = "high"
            if rotational is False:
                is_ssd = True
                if removable or dev_type in ("loop", "rom", "zram"):
                    confidence = "medium"

            devices.append(
                StorageDeviceFact(
                    name=name,
                    device_type=dev_type,
                    size_bytes=size_bytes,
                    model=model,
                    rotational=rotational,
                    transport=transport,
                    removable=removable,
                    hotplug=hotplug,
                    is_ssd=is_ssd,
                    is_nvme=is_nvme,
                    nvme_evidence=nvme_evidence,
                    confidence=confidence,  # type: ignore[arg-type]
                )
            )

        return FactEnvelope(
            tool="get_storage_devices",
            status="ok",
            source=source,
            confidence="high",
            data=StorageFact(devices=devices),
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_storage_devices",
            status="error",
            reason=f"Failed parsing lsblk JSON: {exc}",
            source=source,
            confidence="low",
            data=StorageFact(),
        )
