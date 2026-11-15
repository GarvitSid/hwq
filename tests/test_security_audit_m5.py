"""Security audit tests for Milestone M5 (AGENTS.md, SRS 7, NFR-SEC-1..4, NFR-PRIV-1)."""

from __future__ import annotations

import ast
from pathlib import Path

from hwq.exec.allowlist import ALLOWED_COMMANDS, ALLOWED_FILES
from hwq.llm.ollama import OllamaClient
from hwq.prompts import is_out_of_scope
from hwq.tools.registry import ToolRegistry


def test_audit_no_forbidden_primitives_in_src() -> None:
    """Security audit: forbid shell=True, os.system, os.popen, eval, exec, pickle in src/."""
    src_dir = Path("src/hwq")
    forbidden_tokens = ["shell=True", "os.system", "os.popen", "eval(", "exec(", "pickle."]

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, (
                f"Forbidden security violation '{token}' found in {py_file}"
            )


def test_audit_only_dmidecode_is_privileged() -> None:
    """Security audit: only dmidecode -t memory may be privileged (AGENTS.md Rule 3)."""
    privileged_commands = [
        name for name, spec in ALLOWED_COMMANDS.items() if spec.privileged
    ]
    assert privileged_commands == ["memory_dmi"], (
        f"Only 'memory_dmi' may be privileged, found: {privileged_commands}"
    )
    dmi_spec = ALLOWED_COMMANDS["memory_dmi"]
    assert dmi_spec.argv == ("dmidecode", "-t", "memory")


def test_audit_no_sensitive_ids_in_allowlist() -> None:
    """Security audit: allowlist must never request serial numbers, UUIDs, or asset tags."""
    sensitive_keywords = ["serial", "uuid", "asset_tag"]

    for name, spec in ALLOWED_COMMANDS.items():
        for arg in spec.argv:
            for kw in sensitive_keywords:
                assert kw not in arg.lower(), (
                    f"Sensitive keyword '{kw}' found in allowed command '{name}': {spec.argv}"
                )

    for path in ALLOWED_FILES:
        for kw in sensitive_keywords:
            assert kw not in path.lower(), (
                f"Sensitive keyword '{kw}' found in allowed file path: {path}"
            )


def test_audit_stdlib_only_in_exec_and_snapshot() -> None:
    """Security audit: hwq.exec and hwq.snapshot must be 100% standard library (live USB rule)."""
    forbidden_modules = {"pydantic", "rich", "typer", "pytest", "hypothesis"}

    target_paths = [
        *Path("src/hwq/exec").glob("*.py"),
        Path("src/hwq/snapshot.py"),
    ]

    for py_file in target_paths:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_mod = alias.name.split(".")[0]
                    assert top_mod not in forbidden_modules, (
                        f"Non-stdlib import '{top_mod}' in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_mod = node.module.split(".")[0]
                    assert top_mod not in forbidden_modules, (
                        f"Non-stdlib import '{top_mod}' in {py_file}"
                    )


def test_audit_ollama_endpoint_pinned_to_localhost() -> None:
    """Security audit: Ollama endpoint strictly pinned to 127.0.0.1 (NFR-PRIV-1)."""
    client = OllamaClient(url="http://localhost:11434")
    assert client.endpoint == "http://127.0.0.1:11434/api/chat"
    assert "localhost" not in client.endpoint
    assert client.endpoint.startswith("http://127.0.0.1:11434")


def test_audit_tool_registry_rejects_arbitrary_commands() -> None:
    """Security audit: tool registry rejects any attempt to execute arbitrary commands."""
    registry = ToolRegistry()
    dangerous_names = [
        "system",
        "exec",
        "eval",
        "sh",
        "bash",
        "run",
        "subprocess",
        "os_system",
    ]
    for bad in dangerous_names:
        valid, _, err = registry.validate_tool_call(bad, {})
        assert valid is False
        assert f"Unknown tool '{bad}'" in (err or "")


def test_audit_out_of_scope_intent_filter() -> None:
    """Security audit: verify intent filter catches command execution requests."""
    destructive = [
        "delete my logs",
        "rm -rf /",
        "format disk",
        "run ls -la",
        "run bash script",
        "reboot now",
        "kill -9 1",
        "install malware",
    ]
    for q in destructive:
        assert is_out_of_scope(q) is True, f"Failed to filter dangerous query: '{q}'"
