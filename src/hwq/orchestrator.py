"""Orchestrator, agent loop, and numeric grounding validation (SRS 4.9, 4.10, FR-GRD-1..3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hwq.facts import FactEnvelope, MemorySummaryFact, MemoryTopologyFact
from hwq.grounding import GroundTruthStore, build_ground_truth, validate_numeric_grounding
from hwq.prompts import (
    OUT_OF_SCOPE_REFUSAL,
    build_grounding_correction_prompt,
    build_system_prompt,
    fence_hardware_data,
    is_out_of_scope,
)
from hwq.protocols import LLMClient, SystemBackend
from hwq.session import Session
from hwq.templates import build_template_answer
from hwq.tools.registry import ToolRegistry
from hwq.upgrade import MemoryUpgradeAnalysis, analyze_memory


class Orchestrator:
    """Agent loop orchestrator coordinating LLM, tools, session facts, and grounding checks."""

    def __init__(
        self,
        backend: SystemBackend,
        llm: LLMClient,
        tool_registry: ToolRegistry | None = None,
        max_rounds: int = 4,
    ) -> None:
        self.backend = backend
        self.llm = llm
        self.registry = tool_registry or ToolRegistry()
        self.max_rounds = max_rounds

        # Probe tool availability based on backend capabilities (FR-TOOL-4, AT-7)
        self.registry.probe_availability(self.backend)

    def run_turn(
        self,
        session: Session,
        query: str,
        *,
        on_tool_call: Callable[[str, str, str], None] | None = None,
    ) -> str:
        """Run a single interactive turn with the agent loop and numeric grounding validation."""
        # FR-LLM-5 & AT-5: Refuse out-of-scope requests in one sentence with no tool calls
        if is_out_of_scope(query):
            session.add_user_message(query)
            session.add_assistant_message(OUT_OF_SCOPE_REFUSAL)
            return OUT_OF_SCOPE_REFUSAL

        session.add_user_message(query)

        # Build context including fact index and unavailable tools (FR-CTX-2, FR-TOOL-4, AT-4, AT-7)
        fact_index = session.fact_store.get_index()
        system_prompt = build_system_prompt(fact_index)
        tool_definitions = self.registry.get_tool_definitions()

        # If any tools are unavailable, inform model in context (FR-TOOL-4, AT-7)
        unavail = self.registry.get_unavailable_tools_summary()
        if unavail:
            system_prompt += "\n\nUNAVAILABLE TOOLS ON THIS SYSTEM:\n" + "\n".join(
                f"- {u}" for u in unavail
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *session.messages,
        ]

        # Agent loop (FR-LLM-2: max 4 rounds)
        for _ in range(self.max_rounds):
            reply = self.llm.chat(
                messages=messages,
                tools=tool_definitions,
                options={"temperature": 0.2},
            )

            # If LLM returned text without tool calls, validate numeric grounding (FR-GRD-1)
            if not reply.tool_calls:
                draft_answer = reply.content or "No response generated."
                return self._finalize_with_grounding(session, query, draft_answer, messages)

            # Record assistant tool calls
            messages.append({
                "role": "assistant",
                "content": reply.content,
                "tool_calls": reply.tool_calls,
            })
            session.add_assistant_message(reply.content, tool_calls=reply.tool_calls)

            # Process all tool calls from this reply
            for call in reply.tool_calls:
                func = call.get("function", call)
                name = func.get("name", "")
                raw_args = func.get("arguments", {})

                # Validate tool call (FR-TOOL-3)
                is_valid, validated_args, err = self.registry.validate_tool_call(name, raw_args)
                if not is_valid:
                    error_msg = err or f"Invalid tool call for '{name}'."
                    messages.append({
                        "role": "tool",
                        "name": name,
                        "content": error_msg,
                    })
                    session.add_tool_result(name, error_msg)
                    continue

                # Check FactStore cache before executing (FR-CTX-1, AT-4)
                env: FactEnvelope[Any] | None = session.fact_store.get(name)
                if env is None:
                    env = self.registry.execute_tool(name, validated_args, self.backend)
                    session.fact_store.put(env)

                if on_tool_call:
                    on_tool_call(name, env.status, env.confidence)

                # Return tool results fenced in XML tags (SRS 4.6, NFR-SEC-4, AT-6)
                raw_json = env.model_dump_json(exclude_none=True)
                fenced_output = fence_hardware_data(name, raw_json, confidence=env.confidence)
                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": fenced_output,
                })
                session.add_tool_result(name, fenced_output)

        # Fallback if round limit reached without final text (FR-GRD-2)
        envelopes = session.fact_store.all_envelopes()
        _, analysis = self._get_ground_truth_and_analysis(session)
        fallback = build_template_answer(envelopes, query, analysis)
        msg = (
            "Reached maximum tool rounds without a final answer. "
            f"Here are the gathered facts:\n\n{fallback}"
        )
        session.add_assistant_message(msg)
        return msg

    def _finalize_with_grounding(
        self,
        session: Session,
        query: str,
        draft_answer: str,
        messages: list[dict[str, Any]],
    ) -> str:
        """Validate numeric grounding of draft answer; regenerate or fall back (FR-GRD-1/2)."""
        gt, analysis = self._get_ground_truth_and_analysis(session)
        grounding = validate_numeric_grounding(draft_answer, gt)

        if grounding.is_grounded:
            session.add_assistant_message(draft_answer)
            return draft_answer

        # Attempt 1: Regenerate once with explicit discrepancy explanation (FR-GRD-2)
        correction_prompt = build_grounding_correction_prompt(
            grounding.discrepancy_explanation or "ungrounded numbers detected"
        )
        retry_messages = [
            *messages,
            {"role": "assistant", "content": draft_answer},
            {"role": "user", "content": correction_prompt},
        ]

        tool_defs = self.registry.get_tool_definitions()
        retry_reply = self.llm.chat(
            messages=retry_messages,
            tools=tool_defs,
            options={"temperature": 0.2},
        )
        retry_answer = retry_reply.content or ""

        # Validate regenerated answer
        retry_grounding = validate_numeric_grounding(retry_answer, gt)
        if retry_grounding.is_grounded and retry_answer.strip():
            session.add_assistant_message(retry_answer)
            return retry_answer

        # Attempt 2 failed: Emit deterministic template answer built from facts (FR-GRD-2)
        envelopes = session.fact_store.all_envelopes()
        fallback_answer = build_template_answer(envelopes, query, analysis)
        session.add_assistant_message(fallback_answer)
        return fallback_answer

    def _get_ground_truth_and_analysis(
        self,
        session: Session,
    ) -> tuple[GroundTruthStore, MemoryUpgradeAnalysis | None]:
        """Compute memory upgrade analysis if memory facts are present, and extract ground truth."""
        envelopes = session.fact_store.all_envelopes()
        top_env = session.fact_store.get("get_memory_topology")
        sum_env = session.fact_store.get("get_memory_summary")

        analysis: MemoryUpgradeAnalysis | None = None
        if top_env or sum_env:
            typed_top = (
                top_env
                if top_env and isinstance(top_env.data, (MemoryTopologyFact, dict))
                else None
            )
            typed_sum = (
                sum_env
                if sum_env and isinstance(sum_env.data, (MemorySummaryFact, dict))
                else None
            )
            analysis = analyze_memory(typed_top, typed_sum)

        gt = build_ground_truth(envelopes, analysis)
        return gt, analysis
