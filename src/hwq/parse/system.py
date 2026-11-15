"""Parser for system, BIOS, and OS information into SystemOverviewFact (SRS 4.6, 5)."""

from __future__ import annotations

from collections.abc import Mapping

from hwq.facts import FactEnvelope, SystemOverviewFact
from hwq.models import RawResult
from hwq.parse.sanitize import sanitize_text


def _extract_text(val: RawResult | str | None) -> str:
    """Extract clean string from RawResult or string."""
    if val is None:
        return ""
    if isinstance(val, RawResult):
        return val.stdout if val.status == "ok" else ""
    return str(val)


def _parse_os_release(text: str) -> dict[str, str]:
    """Parse key=value pairs from /etc/os-release."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        clean_key = key.strip()
        clean_val = val.strip().strip('"').strip("'")
        fields[clean_key] = clean_val
    return fields


def parse_system_overview(
    dmi_files: Mapping[str, RawResult | str],
    os_release: RawResult | str | None = None,
    kernel_release: RawResult | str | None = None,
) -> FactEnvelope[SystemOverviewFact]:
    """Parse DMI sysfs files and OS release information into SystemOverviewFact.

    Never raises (FR-PARSE-1).
    """
    source = ["get_system_overview:dmi_sysfs", "file:/etc/os-release"]

    try:
        sys_vendor = sanitize_text(_extract_text(dmi_files.get("sys_vendor")))
        product_name = sanitize_text(_extract_text(dmi_files.get("product_name")))
        bios_vendor = sanitize_text(_extract_text(dmi_files.get("bios_vendor")))
        bios_version = sanitize_text(_extract_text(dmi_files.get("bios_version")))
        bios_date = sanitize_text(_extract_text(dmi_files.get("bios_date")))
        board_vendor = sanitize_text(_extract_text(dmi_files.get("board_vendor")))
        board_name = sanitize_text(_extract_text(dmi_files.get("board_name")))

        os_fields = _parse_os_release(_extract_text(os_release))
        os_pretty = sanitize_text(os_fields.get("PRETTY_NAME") or os_fields.get("NAME"))
        os_id = sanitize_text(os_fields.get("ID"))
        os_ver = sanitize_text(os_fields.get("VERSION_ID"))

        kernel = sanitize_text(_extract_text(kernel_release))

        fact = SystemOverviewFact(
            sys_vendor=sys_vendor,
            product_name=product_name,
            bios_vendor=bios_vendor,
            bios_version=bios_version,
            bios_date=bios_date,
            board_vendor=board_vendor,
            board_name=board_name,
            os_pretty_name=os_pretty,
            os_id=os_id,
            os_version_id=os_ver,
            kernel_release=kernel,
        )

        return FactEnvelope(
            tool="get_system_overview",
            status="ok",
            source=source,
            confidence="high",
            data=fact,
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_system_overview",
            status="error",
            reason=f"Failed parsing system overview: {exc}",
            source=source,
            confidence="low",
            data=SystemOverviewFact(),
        )
