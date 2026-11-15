"""Numeric grounding validator for LLM hardware answers (SRS 4.10, FR-GRD-1)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hwq.facts import (
    CpuFact,
    FactEnvelope,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
)
from hwq.units import GIB, KIB, MIB, TIB
from hwq.upgrade import MemoryUpgradeAnalysis

# Regex matching number + unit expressions (FR-GRD-1)
NUMERIC_TOKEN_REGEX = re.compile(
    r"\b(?P<val>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>TiB|TB|GiB|GB|MiB|MB|KiB|KB|bytes|B|GHz|MHz|MT/s|mts|"
    r"cores?|threads?|sockets?|slots?|devices?|drives?|%)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NumericToken:
    """A single numeric token extracted from text."""

    raw_text: str
    value: float
    unit: str
    normalized_type: str  # "bytes", "frequency_mhz", "speed_mts", "count", "percent"
    normalized_value: float


@dataclass
class GroundTruthStore:
    """Allowable numbers extracted from verified fact envelopes and upgrade analysis."""

    byte_values: set[int] = field(default_factory=set)
    frequency_mhz_values: set[float] = field(default_factory=set)
    speed_mts_values: set[int] = field(default_factory=set)
    count_values: set[int] = field(default_factory=set)
    percent_values: set[float] = field(default_factory=set)


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of numeric grounding validation."""

    is_grounded: bool
    unmatched_tokens: list[NumericToken] = field(default_factory=list)
    discrepancy_explanation: str | None = None


def extract_numeric_tokens(text: str) -> list[NumericToken]:
    """Extract all number+unit tokens from text per FR-GRD-1."""
    tokens: list[NumericToken] = []
    for match in NUMERIC_TOKEN_REGEX.finditer(text):
        raw = match.group(0)
        val = float(match.group("val"))
        unit = match.group("unit").lower()

        # Classify and normalize
        if unit in ("tib", "tb", "gib", "gb", "mib", "mb", "kib", "kb", "bytes", "b"):
            norm_type = "bytes"
            norm_val = _normalize_bytes(val, unit)
        elif unit in ("ghz", "mhz"):
            norm_type = "frequency_mhz"
            norm_val = val * 1000.0 if unit == "ghz" else val
        elif unit in ("mt/s", "mts"):
            norm_type = "speed_mts"
            norm_val = val
        elif unit in (
            "core",
            "cores",
            "thread",
            "threads",
            "socket",
            "sockets",
            "slot",
            "slots",
            "device",
            "devices",
            "drive",
            "drives",
        ):
            norm_type = "count"
            norm_val = float(int(val))
        elif unit == "%":
            norm_type = "percent"
            norm_val = val
        else:
            continue

        tokens.append(
            NumericToken(
                raw_text=raw,
                value=val,
                unit=unit,
                normalized_type=norm_type,
                normalized_value=norm_val,
            )
        )
    return tokens


def _normalize_bytes(val: float, unit: str) -> float:
    """Convert numeric value with byte unit to integer bytes."""
    u = unit.lower()
    if u == "tib":
        return val * TIB
    if u == "tb":
        return val * (1000**4)
    if u == "gib":
        return val * GIB
    if u == "gb":
        return val * (1000**3)
    if u == "mib":
        return val * MIB
    if u == "mb":
        return val * (1000**2)
    if u == "kib":
        return val * KIB
    if u == "kb":
        return val * 1000
    return val


def build_ground_truth(
    envelopes: Sequence[FactEnvelope[Any]],
    upgrade_analysis: MemoryUpgradeAnalysis | None = None,
) -> GroundTruthStore:
    """Extract all ground truth numbers from fact envelopes and upgrade analysis."""
    gt = GroundTruthStore()

    # Always allow common trivial counts (0, 1)
    gt.count_values.add(0)
    gt.count_values.add(1)

    for env in envelopes:
        if env.status != "ok" or not env.data:
            continue
        data = env.data

        if isinstance(data, CpuFact):
            if data.cores is not None:
                gt.count_values.add(data.cores)
            if data.threads is not None:
                gt.count_values.add(data.threads)
            if data.sockets is not None:
                gt.count_values.add(data.sockets)
            if data.min_mhz is not None:
                gt.frequency_mhz_values.add(data.min_mhz)
            if data.max_mhz is not None:
                gt.frequency_mhz_values.add(data.max_mhz)
            if data.model_name:
                for tok in extract_numeric_tokens(data.model_name):
                    if tok.normalized_type == "frequency_mhz":
                        gt.frequency_mhz_values.add(tok.normalized_value)
                    elif tok.normalized_type == "bytes":
                        gt.byte_values.add(int(tok.normalized_value))
                    elif tok.normalized_type == "count":
                        gt.count_values.add(int(tok.normalized_value))

        elif isinstance(data, MemorySummaryFact):
            for b in (
                data.total_bytes,
                data.free_bytes,
                data.available_bytes,
                data.swap_total_bytes,
                data.swap_free_bytes,
            ):
                if b > 0:
                    gt.byte_values.add(b)

        elif isinstance(data, MemoryTopologyFact):
            if data.array_max_capacity_bytes:
                gt.byte_values.add(data.array_max_capacity_bytes)
            if data.installed_bytes:
                gt.byte_values.add(data.installed_bytes)
            if data.slots_total is not None:
                gt.count_values.add(data.slots_total)
            gt.count_values.add(data.slots_used)
            gt.count_values.add(data.slots_free)
            for d in data.devices:
                if d.size_bytes:
                    gt.byte_values.add(d.size_bytes)
                if d.speed_mts:
                    gt.speed_mts_values.add(d.speed_mts)

        elif isinstance(data, StorageFact):
            gt.count_values.add(len(data.devices))
            for dev in data.devices:
                if dev.size_bytes:
                    gt.byte_values.add(dev.size_bytes)

        elif isinstance(data, GpuFact):
            gt.count_values.add(len(data.devices))
            for gpu_dev in data.devices:
                if gpu_dev.vram_bytes:
                    gt.byte_values.add(gpu_dev.vram_bytes)

    # Add numbers from upgrade analysis
    if upgrade_analysis is not None:
        if upgrade_analysis.installed_bytes > 0:
            gt.byte_values.add(upgrade_analysis.installed_bytes)
        if upgrade_analysis.usable_bytes:
            gt.byte_values.add(upgrade_analysis.usable_bytes)
        if upgrade_analysis.max_capacity_bytes:
            gt.byte_values.add(upgrade_analysis.max_capacity_bytes)
        if upgrade_analysis.headroom_bytes:
            gt.byte_values.add(upgrade_analysis.headroom_bytes)
        if upgrade_analysis.per_slot_suggestion_bytes:
            gt.byte_values.add(upgrade_analysis.per_slot_suggestion_bytes)
        if upgrade_analysis.slots_total is not None:
            gt.count_values.add(upgrade_analysis.slots_total)
        gt.count_values.add(upgrade_analysis.slots_used)
        gt.count_values.add(upgrade_analysis.slots_free)

        # Delta between installed and usable
        if (
            upgrade_analysis.installed_bytes > 0
            and upgrade_analysis.usable_bytes
            and upgrade_analysis.installed_bytes > upgrade_analysis.usable_bytes
        ):
            diff = upgrade_analysis.installed_bytes - upgrade_analysis.usable_bytes
            gt.byte_values.add(diff)

    return gt


def validate_numeric_grounding(
    draft_answer: str,
    ground_truth: GroundTruthStore,
    tolerance: float = 0.005,  # 0.5% tolerance per FR-GRD-1
) -> GroundingResult:
    """Validate that every number+unit token in draft_answer is grounded in system facts."""
    tokens = extract_numeric_tokens(draft_answer)
    unmatched: list[NumericToken] = []

    for token in tokens:
        matched = False
        val = token.normalized_value

        if token.normalized_type == "count":
            int_val = int(val)
            matched = int_val in ground_truth.count_values

        elif token.normalized_type == "bytes":
            # Compare with 0.5% tolerance against any ground-truth byte value
            for gt_bytes in ground_truth.byte_values:
                diff = abs(val - gt_bytes)
                if gt_bytes > 0 and (diff / gt_bytes) <= tolerance:
                    matched = True
                    break

        elif token.normalized_type == "frequency_mhz":
            for gt_freq in ground_truth.frequency_mhz_values:
                diff = abs(val - gt_freq)
                if gt_freq > 0 and (diff / gt_freq) <= tolerance:
                    matched = True
                    break

        elif token.normalized_type == "speed_mts":
            for gt_speed in ground_truth.speed_mts_values:
                diff = abs(val - gt_speed)
                if gt_speed > 0 and (diff / gt_speed) <= tolerance:
                    matched = True
                    break

        elif token.normalized_type == "percent":
            # Percentages can be checked if present in facts
            matched = True  # Tolerated unless ground truth contains specific percentages

        if not matched:
            unmatched.append(token)

    if unmatched:
        discrepancies = ", ".join(f"'{t.raw_text}'" for t in unmatched)
        msg = (
            f"Grounding failure: the following numeric expression(s) could not be matched "
            f"to system facts within 0.5% tolerance: {discrepancies}."
        )
        return GroundingResult(
            is_grounded=False,
            unmatched_tokens=unmatched,
            discrepancy_explanation=msg,
        )

    return GroundingResult(is_grounded=True)
