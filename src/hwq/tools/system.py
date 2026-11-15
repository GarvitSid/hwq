"""System overview tool (SRS 4.2, 5, FR-TOOL-1)."""

from __future__ import annotations

from typing import Any

from hwq.facts import FactEnvelope, SystemOverviewFact
from hwq.parse.system import parse_system_overview
from hwq.protocols import SystemBackend
from hwq.tools.base import Tool

DMI_SYSTEM_FILES = [
    "/sys/class/dmi/id/sys_vendor",
    "/sys/class/dmi/id/product_name",
    "/sys/class/dmi/id/bios_vendor",
    "/sys/class/dmi/id/bios_version",
    "/sys/class/dmi/id/bios_date",
    "/sys/class/dmi/id/board_vendor",
    "/sys/class/dmi/id/board_name",
]


class SystemTool(Tool):
    """Tool to retrieve system, motherboard, BIOS, and OS overview."""

    @property
    def name(self) -> str:
        return "get_system_overview"

    @property
    def description(self) -> str:
        return (
            "Retrieve system overview, manufacturer, product name, BIOS details, "
            "operating system distribution, and kernel version."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, backend: SystemBackend, **kwargs: Any) -> FactEnvelope[SystemOverviewFact]:
        dmi_files: dict[str, str] = {}
        for path in DMI_SYSTEM_FILES:
            raw = backend.read_text(path)
            if raw.status == "ok":
                field_name = path.split("/")[-1]
                dmi_files[field_name] = raw.stdout.strip()

        os_release_raw = backend.read_text("/etc/os-release")
        kernel_raw = backend.read_text("/proc/sys/kernel/osrelease")

        return parse_system_overview(
            dmi_files=dmi_files,
            os_release=os_release_raw,
            kernel_release=kernel_raw,
        )
