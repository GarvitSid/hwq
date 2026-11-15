"""Parser for lscpu JSON into CpuFact (SRS 4.6, FR-PARSE-4)."""

from __future__ import annotations

import json
from typing import Any

from hwq.facts import CpuFact, FactEnvelope
from hwq.models import RawResult
from hwq.parse.sanitize import sanitize_text


def _flatten_lscpu_entries(entries: list[dict[str, Any]], target: dict[str, str]) -> None:
    """Recursively flatten lscpu JSON entries into a flat dictionary (FR-PARSE-4)."""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        field = entry.get("field")
        data = entry.get("data")
        if field is not None and data is not None:
            # Strip trailing colon and normalize key
            clean_field = str(field).strip().rstrip(":").strip()
            target[clean_field] = str(data).strip()
        children = entry.get("children")
        if isinstance(children, list):
            _flatten_lscpu_entries(children, target)


def parse_lscpu(raw: RawResult | str) -> FactEnvelope[CpuFact]:
    """Parse lscpu -J raw text or RawResult into FactEnvelope[CpuFact].

    Never raises (FR-PARSE-1).
    """
    source = ["cmd:lscpu -J"]
    if isinstance(raw, RawResult):
        source = list(raw.argv)
        if raw.status != "ok":
            return FactEnvelope(
                tool="get_cpu_info",
                status=raw.status,
                reason=raw.stderr or f"lscpu failed with exit code {raw.exit_code}",
                source=source,
                confidence="low",
                data=CpuFact(),
            )
        text = raw.stdout
    else:
        text = str(raw)

    try:
        parsed_json = json.loads(text)
        flat_fields: dict[str, str] = {}

        if isinstance(parsed_json, dict) and "lscpu" in parsed_json:
            raw_entries = parsed_json["lscpu"]
            if isinstance(raw_entries, list):
                _flatten_lscpu_entries(raw_entries, flat_fields)

        arch = sanitize_text(flat_fields.get("Architecture"))
        model = sanitize_text(flat_fields.get("Model name"))

        sockets_raw = flat_fields.get("Socket(s)")
        sockets = int(sockets_raw) if sockets_raw and sockets_raw.isdigit() else None

        cores_per_socket_raw = flat_fields.get("Core(s) per socket")
        cores_per_socket = (
            int(cores_per_socket_raw)
            if cores_per_socket_raw and cores_per_socket_raw.isdigit()
            else None
        )

        cores: int | None = None
        if cores_per_socket is not None:
            cores = cores_per_socket * (sockets or 1)

        threads_raw = flat_fields.get("CPU(s)")
        threads = int(threads_raw) if threads_raw and threads_raw.isdigit() else None

        if cores is None and threads is not None:
            cores = threads

        min_mhz_raw = flat_fields.get("CPU min MHz")
        min_mhz: float | None = None
        if min_mhz_raw:
            try:
                min_mhz = float(min_mhz_raw)
            except ValueError:
                pass

        max_mhz_raw = flat_fields.get("CPU max MHz")
        max_mhz: float | None = None
        if max_mhz_raw:
            try:
                max_mhz = float(max_mhz_raw)
            except ValueError:
                pass

        flags_raw = flat_fields.get("Flags", "")
        flags = [f.strip() for f in flags_raw.split() if f.strip()]

        fact = CpuFact(
            architecture=arch,
            model_name=model,
            cores=cores,
            threads=threads,
            sockets=sockets,
            min_mhz=min_mhz,
            max_mhz=max_mhz,
            flags=flags,
        )

        return FactEnvelope(
            tool="get_cpu_info",
            status="ok",
            source=source,
            confidence="high",
            data=fact,
        )

    except Exception as exc:
        return FactEnvelope(
            tool="get_cpu_info",
            status="error",
            reason=f"Failed parsing lscpu JSON: {exc}",
            source=source,
            confidence="low",
            data=CpuFact(),
        )
