"""Architecture and compliance tests (FR-ARCH-3, AGENTS.md rules)."""

import ast
from pathlib import Path

import pytest

from hwq.exec.privilege import generate_sudoers_rule, validate_sudoers_rule


def get_src_files() -> list[Path]:
    src_dir = Path(__file__).resolve().parent.parent / "src"
    return list(src_dir.rglob("*.py"))


def test_no_machine_specific_branches() -> None:
    """FR-ARCH-3: No machine-specific branches anywhere (e.g. if vendor == ...)."""
    forbidden_terms = ["sys_vendor ==", "product_name ==", "board_vendor =="]
    for py_file in get_src_files():
        content = py_file.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in content, (
                f"Forbidden machine-specific branch in {py_file.name}: {term}"
            )


def test_no_forbidden_execution_calls_in_src() -> None:
    """Security rule: No shell=True, os.system, eval, exec, pickle in src/."""
    forbidden_calls = {"system", "popen", "eval", "exec"}
    for py_file in get_src_files():
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # check plain eval(), exec()
                if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                    pytest.fail(f"Forbidden call '{func.id}' in {py_file}")
                # check os.system, os.popen
                if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                    if isinstance(func.value, ast.Name) and func.value.id == "os":
                        pytest.fail(f"Forbidden call 'os.{func.attr}' in {py_file}")
            # check keyword arguments for shell=True
            if isinstance(node, ast.keyword) and node.arg == "shell":
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    pytest.fail(f"Forbidden shell=True in {py_file}")
            # check pickle import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "pickle":
                        pytest.fail(f"Forbidden pickle import in {py_file}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] == "pickle":
                    pytest.fail(f"Forbidden pickle from-import in {py_file}")


def test_exec_modules_are_stdlib_only() -> None:
    """AGENTS.md: hwq.exec.* and hwq.snapshot must be stdlib-only."""
    allowed_internal = {"hwq.models", "hwq.protocols", "hwq.exec"}
    exec_dir = Path(__file__).resolve().parent.parent / "src" / "hwq" / "exec"
    if not exec_dir.exists():
        return

    import sys
    stdlib_modules = sys.stdlib_module_names

    for py_file in exec_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert (
                        root in stdlib_modules or alias.name.startswith("hwq")
                    ), f"Non-stdlib import '{alias.name}' in {py_file.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    is_allowed = (
                        root in stdlib_modules
                        or any(node.module.startswith(p) for p in allowed_internal)
                        or node.level > 0  # relative import
                    )
                    assert is_allowed, f"Non-stdlib from-import '{node.module}' in {py_file.name}"


def test_sudoers_output_linter() -> None:
    """Security rule: Generated sudoers rule has no wildcard and pinned path."""
    rule = generate_sudoers_rule("testuser", "/usr/sbin/dmidecode")
    assert validate_sudoers_rule(rule) is True
    assert "*" not in rule
    assert "?" not in rule
    assert rule.endswith("/usr/sbin/dmidecode -t memory")
