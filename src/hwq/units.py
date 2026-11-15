"""Unit conversion and formatting (SRS 4.7, FR-UNIT-1, AT-9).

Stdlib-only module for deterministic arithmetic and presentation formatting.
"""

from __future__ import annotations

KIB = 1024
MIB = 1024**2
GIB = 1024**3
TIB = 1024**4

KB = 1000
MB = 1000**2
GB = 1000**3
TB = 1000**4


def format_bytes(
    num_bytes: int | None,
    *,
    include_decimal: bool = False,
) -> str:
    """Format byte count into human-readable binary units (and optional decimal approximation).

    Conforms to FR-UNIT-1:
    - Always presents binary units (B, KiB, MiB, GiB, TiB).
    - When include_decimal is True (recommended for storage), appends decimal equivalent
      such as '238 GiB (about 256 GB)'.

    Examples:
        format_bytes(256060514304, include_decimal=True) -> '238 GiB (about 256 GB)'
        format_bytes(8589934592) -> '8 GiB'
    """
    if num_bytes is None:
        return "Unknown"
    if num_bytes < 0:
        return f"{num_bytes} B"

    if num_bytes < KIB:
        return f"{num_bytes} B"

    if num_bytes < MIB:
        val = num_bytes / KIB
        binary_str = f"{val:.0f} KiB" if val.is_integer() else f"{val:.1f} KiB"
        return binary_str

    if num_bytes < GIB:
        val = num_bytes / MIB
        binary_str = f"{val:.0f} MiB" if val.is_integer() else f"{val:.1f} MiB"
        return binary_str

    if num_bytes < TIB:
        val_gib = num_bytes / GIB
        if val_gib.is_integer():
            binary_str = f"{int(val_gib)} GiB"
        elif include_decimal:
            # When pairing with decimal approximation (e.g. disk sizes), round binary GiB
            binary_str = f"{round(val_gib)} GiB"
        else:
            binary_str = f"{val_gib:.1f} GiB"

        if include_decimal:
            decimal_str = _format_decimal_disk(num_bytes)
            return f"{binary_str} (about {decimal_str})"
        return binary_str

    # >= 1 TiB
    val_tib = num_bytes / TIB
    if val_tib.is_integer():
        binary_str = f"{int(val_tib)} TiB"
    elif include_decimal:
        # For large disks (e.g. 1 TB disk reporting 931 GiB), present as GiB or TiB
        val_gib = round(num_bytes / GIB)
        binary_str = f"{val_gib} GiB"
    else:
        binary_str = f"{val_tib:.2f} TiB"

    if include_decimal:
        decimal_str = _format_decimal_disk(num_bytes)
        return f"{binary_str} (about {decimal_str})"
    return binary_str


def _format_decimal_disk(num_bytes: int) -> str:
    """Format decimal disk capacity approximation (e.g. '256 GB' or '1 TB')."""
    if num_bytes >= TB:
        val_tb = num_bytes / TB
        rounded_tb = round(val_tb)
        if rounded_tb > 0 and abs(val_tb - rounded_tb) / rounded_tb < 0.05:
            return f"{rounded_tb} TB"
        return f"{val_tb:.1f} TB"

    val_gb = num_bytes / GB
    rounded_gb = round(val_gb)
    if rounded_gb > 0 and abs(val_gb - rounded_gb) / rounded_gb < 0.05:
        return f"{rounded_gb} GB"
    return f"{val_gb:.1f} GB"


def format_frequency(mhz: float | None) -> str:
    """Format clock frequency in MHz or GHz."""
    if mhz is None:
        return "Unknown"
    if mhz >= 1000.0:
        ghz = mhz / 1000.0
        return f"{ghz:.2f} GHz ({mhz:.1f} MHz)"
    return f"{mhz:.1f} MHz"


def format_speed(mts: int | None) -> str:
    """Format memory transfer rate in MT/s."""
    if mts is None:
        return "Unknown"
    return f"{mts} MT/s"
