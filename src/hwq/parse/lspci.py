"""Parser for lspci -mm -nn and optional nvidia-smi into GpuFact (SRS 4.6, FR-PARSE-5)."""

from __future__ import annotations

import re
from typing import Any

from hwq.facts import FactEnvelope, GpuDeviceFact, GpuFact
from hwq.models import RawResult
from hwq.parse.sanitize import sanitize_text

# Select VGA [0300], 3D [0302], and Display [0380] controllers
GPU_CLASS_REGEX = re.compile(r"\[(0300|0302|0380)\]|VGA|3D|Display", re.IGNORECASE)


def parse_gpu_info(
    lspci_raw: RawResult | str,
    nvidia_raw: RawResult | str | None = None,
) -> FactEnvelope[GpuFact]:
    """Parse lspci -mm -nn and optional nvidia-smi into FactEnvelope[GpuFact].

    Never raises (FR-PARSE-1).
    """
    source = ["cmd:lspci -mm -nn"]
    if isinstance(lspci_raw, RawResult):
        source = list(lspci_raw.argv)
        if lspci_raw.status != "ok":
            return FactEnvelope(
                tool="get_gpu_info",
                status=lspci_raw.status,
                reason=lspci_raw.stderr or f"lspci failed with exit code {lspci_raw.exit_code}",
                source=source,
                confidence="low",
                data=GpuFact(),
            )
        lspci_text = lspci_raw.stdout
    else:
        lspci_text = str(lspci_raw)

    try:
        # Parse optional nvidia-smi CSV if present
        nvidia_info: dict[str, Any] | None = None
        if nvidia_raw is not None:
            nv_text = nvidia_raw.stdout if isinstance(nvidia_raw, RawResult) else str(nvidia_raw)
            if nv_text.strip():
                parts = [p.strip() for p in nv_text.splitlines()[0].split(",")]
                if len(parts) >= 3:
                    nv_vram: int | None = None
                    try:
                        vram_mb = int(parts[1].split()[0])
                        nv_vram = vram_mb * 1024 * 1024
                    except (ValueError, IndexError):
                        pass
                    nvidia_info = {
                        "name": parts[0],
                        "vram_bytes": nv_vram,
                        "driver_version": parts[2],
                    }

        # Parse lspci -mm -nn records (separated by double newlines or Slot: lines)
        devices: list[GpuDeviceFact] = []
        blocks = re.split(r"(?=Slot:\s+|\n\s*\n)", lspci_text)

        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            record: dict[str, str] = {}
            for line in lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    record[key.strip()] = val.strip()

            class_str = record.get("Class", "")
            if not GPU_CLASS_REGEX.search(class_str):
                continue

            slot = record.get("Slot", "00:00.0")
            raw_vendor = record.get("Vendor", "Unknown")
            vendor = sanitize_text(raw_vendor) or "Unknown"
            raw_device = record.get("Device", "Unknown Graphics")
            device_name = sanitize_text(raw_device) or "Unknown Graphics"

            # Clean bracketed IDs from strings (e.g. 'TigerLake-LP GT2 [Iris Xe Graphics] [9a49]')
            clean_class_raw = re.sub(r"\[[0-9a-fA-F]+\]", "", class_str)
            clean_class = sanitize_text(clean_class_raw) or "VGA controller"

            # Determine if integrated
            lower_name = device_name.lower()
            lower_vendor = vendor.lower()
            is_integrated = False

            if "intel" in lower_vendor or "intel" in lower_name:
                is_integrated = True
            elif "amd" in lower_vendor or "radeon" in lower_name:
                if any(k in lower_name for k in ("vega", "cezanne", "renoir", "barcelo", "mobile")):
                    is_integrated = True
                elif "discrete" not in lower_name and "rx" not in lower_name:
                    is_integrated = True

            vram_bytes: int | None = None
            driver_version: str | None = None

            # If NVIDIA discrete GPU and we have nvidia-smi data, attach it
            if "nvidia" in lower_vendor or "nvidia" in lower_name:
                is_integrated = False
                if nvidia_info:
                    vram_bytes = nvidia_info.get("vram_bytes")
                    driver_version = nvidia_info.get("driver_version")

            devices.append(
                GpuDeviceFact(
                    slot=slot,
                    class_name=clean_class,
                    vendor=vendor,
                    device_name=device_name,
                    is_integrated=is_integrated,
                    vram_bytes=vram_bytes,
                    driver_version=driver_version,
                )
            )

        caveats: list[str] = []
        if not devices:
            caveats.append("No display or VGA controller devices detected in lspci.")

        return FactEnvelope(
            tool="get_gpu_info",
            status="ok" if devices else "partial",
            source=source,
            confidence="high" if devices else "low",
            caveats=caveats,
            data=GpuFact(devices=devices),
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_gpu_info",
            status="error",
            reason=f"Failed parsing lspci GPU info: {exc}",
            source=source,
            confidence="low",
            data=GpuFact(),
        )
