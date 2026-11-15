"""Tests for unit formatting and conversions (SRS 4.7, FR-UNIT-1, AT-9)."""

from __future__ import annotations

from hwq.units import (
    GIB,
    KIB,
    MIB,
    format_bytes,
    format_frequency,
    format_speed,
)


def test_format_bytes_none_and_zero() -> None:
    assert format_bytes(None) == "Unknown"
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"


def test_format_bytes_kib_and_mib() -> None:
    assert format_bytes(KIB) == "1 KiB"
    assert format_bytes(1536) == "1.5 KiB"
    assert format_bytes(MIB) == "1 MiB"
    assert format_bytes(int(2.5 * MIB)) == "2.5 MiB"


def test_format_bytes_gib_exact() -> None:
    assert format_bytes(8 * GIB) == "8 GiB"
    assert format_bytes(16 * GIB) == "16 GiB"
    assert format_bytes(64 * GIB) == "64 GiB"


def test_format_bytes_at9_acceptance() -> None:
    """AT-9 Units: a 256060514304-byte disk is presented as '238 GiB (about 256 GB)'."""
    disk_bytes = 256060514304
    formatted = format_bytes(disk_bytes, include_decimal=True)
    assert formatted == "238 GiB (about 256 GB)"


def test_format_bytes_large_disks() -> None:
    # 512 GB class disk (e.g. 512110190592 bytes)
    disk_512gb = 512110190592
    assert format_bytes(disk_512gb, include_decimal=True) == "477 GiB (about 512 GB)"

    # 1 TB class disk (e.g. 1000204886016 bytes)
    disk_1tb = 1000204886016
    assert format_bytes(disk_1tb, include_decimal=True) == "932 GiB (about 1 TB)"


def test_format_frequency() -> None:
    assert format_frequency(None) == "Unknown"
    assert format_frequency(800.0) == "800.0 MHz"
    assert format_frequency(3600.0) == "3.60 GHz (3600.0 MHz)"


def test_format_speed() -> None:
    assert format_speed(None) == "Unknown"
    assert format_speed(3200) == "3200 MT/s"
    assert format_speed(4266) == "4266 MT/s"
