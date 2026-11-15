"""Parser for /proc/meminfo into MemorySummaryFact (SRS 4.6, 4.7)."""

from __future__ import annotations

import re

from hwq.facts import FactEnvelope, MemorySummaryFact
from hwq.models import RawResult

LINE_REGEX = re.compile(r"^([a-zA-Z0-9_()]+):\s*(\d+)(?:\s+kB)?")


def parse_meminfo(raw: RawResult | str) -> FactEnvelope[MemorySummaryFact]:
    """Parse /proc/meminfo raw text or RawResult into FactEnvelope[MemorySummaryFact].

    Never raises (FR-PARSE-1).
    """
    source = ["file:/proc/meminfo"]
    if isinstance(raw, RawResult):
        source = list(raw.argv)
        if raw.status != "ok":
            return FactEnvelope(
                tool="get_memory_summary",
                status=raw.status,
                reason=raw.stderr or f"Failed reading meminfo with exit code {raw.exit_code}",
                source=source,
                confidence="low",
                data=MemorySummaryFact(),
            )
        text = raw.stdout
    else:
        text = str(raw)

    try:
        data: dict[str, int] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = LINE_REGEX.match(line)
            if match:
                key, val_str = match.groups()
                # Values in meminfo are given in kB (1024 bytes)
                data[key] = int(val_str) * 1024

        total = data.get("MemTotal", 0)
        free = data.get("MemFree", 0)
        available = data.get("MemAvailable", free)
        swap_total = data.get("SwapTotal", 0)
        swap_free = data.get("SwapFree", 0)

        caveats: list[str] = []
        confidence = "high"
        if total == 0:
            caveats.append("MemTotal missing or zero in /proc/meminfo")
            confidence = "low"

        fact = MemorySummaryFact(
            total_bytes=total,
            free_bytes=free,
            available_bytes=available,
            swap_total_bytes=swap_total,
            swap_free_bytes=swap_free,
        )

        return FactEnvelope(
            tool="get_memory_summary",
            status="ok" if total > 0 else "partial",
            source=source,
            confidence=confidence,  # type: ignore[arg-type]
            caveats=caveats,
            data=fact,
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_memory_summary",
            status="error",
            reason=f"Failed parsing meminfo: {exc}",
            source=source,
            confidence="low",
            data=MemorySummaryFact(),
        )
