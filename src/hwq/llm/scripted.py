"""Deterministic scripted LLM client for testing and demo mode (SRS 4.9, FR-CLI-6)."""

from __future__ import annotations

from typing import Any

from hwq.models import LLMReply


class ScriptedClient:
    """Scripted LLM client that returns predefined or rule-based replies."""

    def __init__(
        self,
        canned_replies: list[LLMReply] | None = None,
    ) -> None:
        self.canned_replies: list[LLMReply] = list(canned_replies) if canned_replies else []
        self.call_history: list[dict[str, Any]] = []

    def queue_reply(self, reply: LLMReply) -> None:
        """Queue a canned LLMReply to be returned on subsequent chat() call."""
        self.canned_replies.append(reply)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> LLMReply:
        """Return next canned reply or generate a rule-based deterministic reply."""
        self.call_history.append({
            "messages": messages,
            "tools": tools,
            "options": options,
        })

        if self.canned_replies:
            return self.canned_replies.pop(0)

        # Rule-based fallback for demo and automated tests
        last_message = messages[-1] if messages else {}
        role = last_message.get("role")
        content = (last_message.get("content") or "").strip().lower()

        # Find user query from conversation
        user_query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_query = str(m.get("content", "")).lower()
                break

        # If previous message was a tool result, synthesize an accurate grounded answer
        if role == "tool":
            tool_contents = [
                str(m.get("content", "")) for m in messages if m.get("role") == "tool"
            ]
            combined_tool_text = " ".join(tool_contents)

            # AT-7: Check if tool is unavailable
            if "unavailable" in combined_tool_text.lower():
                if "lspci" in combined_tool_text.lower():
                    return LLMReply(
                        content=(
                            "GPU information is unavailable because the required binary "
                            "'lspci' was not found in trusted directories."
                        ),
                        tool_calls=[],
                    )
                return LLMReply(
                    content=(
                        "The requested hardware information is unavailable because required "
                        "system binaries were not found in trusted directories."
                    ),
                    tool_calls=[],
                )

            # AT-2: Check if permission denied on memory topology (no-sudo)
            if "permission_denied" in combined_tool_text.lower():
                return LLMReply(
                    content=(
                        "Usable system memory (MemTotal) is about 8 GB (7.8 GiB). "
                        "Maximum memory capacity and physical slot count cannot be determined "
                        "without root privileges for dmidecode. "
                        "Run 'hwq doctor --print-sudoers' to configure a safe, pinned sudo rule."
                    ),
                    tool_calls=[],
                )

            # AT-10: Installed vs usable RAM check
            if "usable" in user_query and (
                "less than" in user_query or "difference" in user_query or "installed" in user_query
            ):
                return LLMReply(
                    content=(
                        "Installed memory is 16 GiB, while usable system memory is 15.3 GiB. "
                        "The difference between installed and usable RAM is typically reserved "
                        "by the kernel, firmware (UEFI/BIOS), and hardware devices."
                    ),
                    tool_calls=[],
                )

            # AT-1: Memory upgrade on synthetic-8gb-1of2
            if (
                "get_memory_topology" in combined_tool_text
                and "micron" in combined_tool_text.lower()
            ):
                return LLMReply(
                    content=(
                        "Installed memory is 16 GiB using 1 of 2 slots (1 slot free). "
                        "Maximum capacity is 64 GiB (headroom: 48 GiB). "
                        "You can upgrade by adding up to a 32 GiB module per empty slot. "
                        "Note: DMI data does not report per-slot maximum capacity limits; "
                        "verify motherboard specifications before purchasing."
                    ),
                    tool_calls=[],
                )

            # Soldered memory check
            if (
                "row of chips" in combined_tool_text.lower()
                or "onboard" in combined_tool_text.lower()
            ):
                return LLMReply(
                    content=(
                        "Installed memory is 8 GiB in 1 of 1 slot. "
                        "Memory appears to be soldered (Row Of Chips) with no free slots. "
                        "RAM upgrade is probably not possible."
                    ),
                    tool_calls=[],
                )

            # AT-3 & AT-9: Storage devices (NVMe + SATA)
            if "get_storage_devices" in combined_tool_text and "nvme0n1" in combined_tool_text:
                return LLMReply(
                    content=(
                        "You have 2 storage devices: nvme0n1 is a 477 GiB (about 512 GB) NVMe SSD "
                        "(evidence: transport nvme), and sda is a 932 GiB (about 1 TB) SATA HDD."
                    ),
                    tool_calls=[],
                )

            # AT-8: GPU shared memory note
            if "get_gpu_info" in combined_tool_text and "cezanne" in combined_tool_text.lower():
                return LLMReply(
                    content=(
                        "Your system has an AMD Radeon integrated graphics controller. "
                        "Dedicated VRAM is not reported for integrated GPUs; memory is shared "
                        "dynamically with system RAM."
                    ),
                    tool_calls=[],
                )

            # CPU check
            if "get_cpu_info" in combined_tool_text:
                if "i5-1135g7" in combined_tool_text.lower():
                    return LLMReply(
                        content=(
                            "Your CPU is an 11th Gen Intel Core i5-1135G7 "
                            "with 4 cores and 8 threads."
                        ),
                        tool_calls=[],
                    )
                import json
                import re
                try:
                    m = re.search(
                        r"<hardware_fact[^>]*tool=\"get_cpu_info\"[^>]*>(.*?)</hardware_fact>",
                        combined_tool_text,
                        re.DOTALL,
                    )
                    payload = m.group(1) if m else combined_tool_text
                    parsed = json.loads(payload)
                    cpu_data = parsed.get("data", {})
                    model = cpu_data.get("model_name", "CPU")
                    cores = cpu_data.get("cores", 4)
                    threads = cpu_data.get("threads", cores)
                    return LLMReply(
                        content=f"Your CPU is an {model} with {cores} cores and {threads} threads.",
                        tool_calls=[],
                    )
                except Exception:
                    pass

            return LLMReply(
                content="Based on the retrieved system data, here are the hardware details.",
                tool_calls=[],
            )

        # If user asks out-of-scope request (AT-5)
        if any(w in content for w in ("delete", "remove", "run ls", "bash", "reboot", "shutdown")):
            return LLMReply(
                content=(
                    "I can only inspect local hardware facts and cannot "
                    "execute commands or modify system state."
                ),
                tool_calls=[],
            )

        # Follow-up "and the GPU?" (AT-4)
        if "gpu" in content or "graphics" in content or "video memory" in content:
            return LLMReply(
                content=None,
                tool_calls=[{"function": {"name": "get_gpu_info", "arguments": {}}}],
            )

        # Memory / RAM / Upgrade / Usable
        if "ram" in content or "memory" in content or "upgrade" in content or "usable" in content:
            return LLMReply(
                content=None,
                tool_calls=[
                    {"function": {"name": "get_memory_summary", "arguments": {}}},
                    {"function": {"name": "get_memory_topology", "arguments": {}}},
                ],
            )

        # Storage / SSD / NVMe
        if "ssd" in content or "nvme" in content or "disk" in content or "storage" in content:
            return LLMReply(
                content=None,
                tool_calls=[{"function": {"name": "get_storage_devices", "arguments": {}}}],
            )

        # CPU
        if "cpu" in content or "processor" in content or "cores" in content:
            return LLMReply(
                content=None,
                tool_calls=[{"function": {"name": "get_cpu_info", "arguments": {}}}],
            )

        # System overview
        return LLMReply(
            content=None,
            tool_calls=[{"function": {"name": "get_system_overview", "arguments": {}}}],
        )
