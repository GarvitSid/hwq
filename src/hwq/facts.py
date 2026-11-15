"""Pydantic fact models and FactEnvelope contract (SRS 4.6, 4.7, 6.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

FactStatus = Literal["ok", "partial", "unavailable", "permission_denied", "timeout", "error"]
ConfidenceLevel = Literal["high", "medium", "low"]
PrivilegeLevel = Literal["unprivileged", "root_via_sudo"]


class FactEnvelope(BaseModel, Generic[T]):
    """Standard container envelope for all parsed hardware facts (SRS 6.1)."""

    model_config = ConfigDict(frozen=True)

    tool: str
    status: FactStatus
    reason: str | None = None
    source: list[str] = Field(default_factory=list)
    privilege: PrivilegeLevel = "unprivileged"
    collected_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    confidence: ConfidenceLevel = "high"
    caveats: list[str] = Field(default_factory=list)
    data: T | dict[str, Any] = Field(default_factory=dict)


class CpuFact(BaseModel):
    """CPU hardware facts parsed from lscpu."""

    model_config = ConfigDict(frozen=True)

    architecture: str | None = None
    model_name: str | None = None
    cores: int | None = None
    threads: int | None = None
    sockets: int | None = None
    min_mhz: float | None = None
    max_mhz: float | None = None
    flags: list[str] = Field(default_factory=list)


class MemorySummaryFact(BaseModel):
    """Volatile memory summary parsed from /proc/meminfo."""

    model_config = ConfigDict(frozen=True)

    total_bytes: int = 0
    free_bytes: int = 0
    available_bytes: int = 0
    swap_total_bytes: int = 0
    swap_free_bytes: int = 0


class MemoryDeviceFact(BaseModel):
    """Single memory module or slot facts parsed from dmidecode Type 17."""

    model_config = ConfigDict(frozen=True)

    locator: str | None = None
    bank: str | None = None
    size_bytes: int | None = None
    form_factor: str | None = None
    memory_type: str | None = None
    speed_mts: int | None = None
    manufacturer: str | None = None
    part_number: str | None = None


class MemoryTopologyFact(BaseModel):
    """Physical memory array and slot topology parsed from dmidecode Type 16 and 17."""

    model_config = ConfigDict(frozen=True)

    array_max_capacity_bytes: int | None = None
    slots_total: int | None = None
    slots_used: int = 0
    slots_free: int = 0
    installed_bytes: int = 0
    devices: list[MemoryDeviceFact] = Field(default_factory=list)


class StorageDeviceFact(BaseModel):
    """Single block device facts parsed from lsblk."""

    model_config = ConfigDict(frozen=True)

    name: str
    device_type: str | None = None
    size_bytes: int | None = None
    model: str | None = None
    rotational: bool | None = None
    transport: str | None = None
    removable: bool = False
    hotplug: bool = False
    is_ssd: bool = False
    is_nvme: bool = False
    nvme_evidence: str | None = None
    confidence: ConfidenceLevel = "high"


class StorageFact(BaseModel):
    """Collection of storage block devices."""

    model_config = ConfigDict(frozen=True)

    devices: list[StorageDeviceFact] = Field(default_factory=list)


class GpuDeviceFact(BaseModel):
    """GPU controller facts parsed from lspci and optional nvidia-smi."""

    model_config = ConfigDict(frozen=True)

    slot: str
    class_name: str
    vendor: str
    device_name: str
    is_integrated: bool = False
    vram_bytes: int | None = None
    driver_version: str | None = None


class GpuFact(BaseModel):
    """Collection of GPU controllers."""

    model_config = ConfigDict(frozen=True)

    devices: list[GpuDeviceFact] = Field(default_factory=list)


class SystemOverviewFact(BaseModel):
    """System, motherboard, BIOS, and OS information."""

    model_config = ConfigDict(frozen=True)

    sys_vendor: str | None = None
    product_name: str | None = None
    bios_vendor: str | None = None
    bios_version: str | None = None
    bios_date: str | None = None
    board_vendor: str | None = None
    board_name: str | None = None
    os_pretty_name: str | None = None
    os_id: str | None = None
    os_version_id: str | None = None
    kernel_release: str | None = None
