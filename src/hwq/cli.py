"""CLI entrypoint for hwq (SRS 4.1, FR-CLI-1..6)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hwq import __version__
from hwq.config import BackendChoice, Config, LLMChoice, load_config
from hwq.exec.privilege import generate_sudoers_rule
from hwq.exec.probe import find_binary
from hwq.facts import (
    CpuFact,
    FactEnvelope,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
    SystemOverviewFact,
)
from hwq.llm import OllamaConnectionError, OllamaModelError, create_llm_client
from hwq.orchestrator import Orchestrator
from hwq.session import Session
from hwq.snapshot import take_snapshot
from hwq.tools.base import create_backend
from hwq.tools.cpu import CpuTool
from hwq.tools.gpu import GpuTool
from hwq.tools.memory import MemorySummaryTool, MemoryTopologyTool
from hwq.tools.storage import StorageTool
from hwq.tools.system import SystemTool
from hwq.units import format_bytes, format_frequency, format_speed
from hwq.upgrade import MemoryUpgradeAnalysis, analyze_memory

app = typer.Typer(
    name="hwq",
    help="Local Linux Hardware Q&A Assistant. Read-only, local facts & Q&A.",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"hwq version {__version__}")
        raise typer.Exit()


def _resolve_cli_backend(
    backend: str | None,
    fixture: str | None,
    current_default: BackendChoice,
) -> BackendChoice:
    if backend in ("auto", "linux", "replay"):
        return backend  # type: ignore[return-value]
    if fixture:
        return "replay"
    return current_default


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", help="Execution backend: auto, linux, replay."),
    ] = None,
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Fixture name or directory for replay backend."),
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="LLM client to use: ollama or scripted."),
    ] = None,
    show_tools: Annotated[
        bool,
        typer.Option("--show-tools", help="Print tool calls with status and confidence."),
    ] = False,
    demo: Annotated[
        bool,
        typer.Option("--demo", help="Run with scripted client and bundled demo fixture."),
    ] = False,
) -> None:
    """hwq: Local Linux Hardware Q&A Assistant.

    Run without subcommands to start the interactive session.
    """
    valid_backend: BackendChoice | None = None
    if backend is not None:
        if backend not in ("auto", "linux", "replay"):
            console.print(
                f"[red]Error:[/red] Invalid backend '{backend}'. Must be auto, linux, or replay."
            )
            raise typer.Exit(code=2)
        valid_backend = backend  # type: ignore[assignment]

    valid_llm: LLMChoice | None = None
    if llm is not None:
        if llm not in ("ollama", "scripted"):
            console.print(
                f"[red]Error:[/red] Invalid LLM client '{llm}'. Must be ollama or scripted."
            )
            raise typer.Exit(code=2)
        valid_llm = llm  # type: ignore[assignment]

    cfg = load_config(
        cli_backend=valid_backend,
        cli_fixture=fixture,
        cli_llm=valid_llm,
        cli_show_tools=show_tools if show_tools else None,
        cli_demo=demo if demo else None,
    )
    ctx.obj = cfg

    if ctx.invoked_subcommand is None:
        _run_repl(cfg)


def _run_repl(cfg: Config) -> None:
    """Interactive REPL with turn cancellation on Ctrl-C (SRS 4.1, FR-CLI-1)."""
    console.print(
        f"[bold green]hwq[/bold green] [dim]v{__version__}[/dim] "
        f"(backend: [cyan]{cfg.resolved_backend}[/cyan], llm: [yellow]{cfg.llm}[/yellow])"
    )
    console.print("[dim]Type your hardware question or 'exit' to quit.[/dim]\n")

    sys_backend = create_backend(cfg)
    llm_client = create_llm_client(cfg)
    orchestrator = Orchestrator(backend=sys_backend, llm=llm_client)
    session = Session()

    def on_tool(name: str, status: str, conf: str) -> None:
        if cfg.show_tools:
            console.print(
                f"[dim cyan]  [Tool] {name} -> status={status}, confidence={conf}[/dim cyan]"
            )

    while True:
        try:
            query = console.input("[bold green]hwq>[/bold green] ")
            query_clean = query.strip()
            if not query_clean:
                continue
            if query_clean.lower() in ("exit", "quit", ":q"):
                console.print("[dim]Goodbye![/dim]")
                break

            answer = orchestrator.run_turn(session, query_clean, on_tool_call=on_tool)
            console.print(f"\n{answer}\n")
        except KeyboardInterrupt:
            console.print("\n[yellow]Turn cancelled.[/yellow]\n")
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except (OllamaConnectionError, OllamaModelError) as err:
            console.print(f"\n[red]LLM Error:[/red] {err}\n")


def _render_cpu(env: FactEnvelope[CpuFact]) -> None:
    table = Table(title="CPU Hardware Facts", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    data = env.data if isinstance(env.data, CpuFact) else CpuFact.model_validate(env.data)
    table.add_row("Model", data.model_name or "Unknown")
    table.add_row("Architecture", data.architecture or "Unknown")
    table.add_row("Physical Cores", str(data.cores) if data.cores is not None else "Unknown")
    table.add_row("Logical Threads", str(data.threads) if data.threads is not None else "Unknown")
    table.add_row("Sockets", str(data.sockets) if data.sockets is not None else "Unknown")
    table.add_row("Min Frequency", format_frequency(data.min_mhz))
    table.add_row("Max Frequency", format_frequency(data.max_mhz))
    console.print(table)


def _render_memory(
    sum_env: FactEnvelope[MemorySummaryFact],
    top_env: FactEnvelope[MemoryTopologyFact],
    analysis: MemoryUpgradeAnalysis,
) -> None:
    sum_data = (
        sum_env.data
        if isinstance(sum_env.data, MemorySummaryFact)
        else MemorySummaryFact.model_validate(sum_env.data)
    )
    top_data = (
        top_env.data
        if isinstance(top_env.data, MemoryTopologyFact)
        else MemoryTopologyFact.model_validate(top_env.data)
    )

    # 1. Memory Usage Table
    usage_table = Table(title="Memory Usage & Summary", show_header=True, header_style="bold cyan")
    usage_table.add_column("Metric", style="bold")
    usage_table.add_column("Bytes")
    usage_table.add_column("Human Readable")

    usage_table.add_row("MemTotal", str(sum_data.total_bytes), format_bytes(sum_data.total_bytes))
    usage_table.add_row("MemFree", str(sum_data.free_bytes), format_bytes(sum_data.free_bytes))
    usage_table.add_row(
        "MemAvailable",
        str(sum_data.available_bytes),
        format_bytes(sum_data.available_bytes),
    )
    usage_table.add_row(
        "SwapTotal",
        str(sum_data.swap_total_bytes),
        format_bytes(sum_data.swap_total_bytes),
    )
    usage_table.add_row(
        "SwapFree",
        str(sum_data.swap_free_bytes),
        format_bytes(sum_data.swap_free_bytes),
    )
    console.print(usage_table)

    # 2. Physical Slots Table
    slots_table = Table(
        title="Physical Memory Slots (DMI)",
        show_header=True,
        header_style="bold cyan",
    )
    slots_table.add_column("Locator", style="bold")
    slots_table.add_column("Size")
    slots_table.add_column("Form Factor")
    slots_table.add_column("Type")
    slots_table.add_column("Speed")
    slots_table.add_column("Manufacturer")
    slots_table.add_column("Part Number")

    if top_env.status == "ok" and top_data.devices:
        for dev in top_data.devices:
            slots_table.add_row(
                dev.locator or "Slot",
                format_bytes(dev.size_bytes),
                dev.form_factor or "Unknown",
                dev.memory_type or "Unknown",
                format_speed(dev.speed_mts),
                dev.manufacturer or "Unknown",
                dev.part_number or "Unknown",
            )
        console.print(slots_table)
    else:
        status_msg = f"[yellow]DMI Topology unavailable ({top_env.status})[/yellow]"
        console.print(Panel(status_msg, title="Physical Slots"))

    # 3. Upgrade Advisor Panel
    advice_lines: list[str] = [
        f"[bold]Installed:[/bold] {format_bytes(analysis.installed_bytes)}",
        f"[bold]Slots Used:[/bold] {analysis.slots_used} of {analysis.slots_total or '?'}",
        f"[bold]Free Slots:[/bold] {analysis.slots_free}",
        f"[bold]Max Capacity:[/bold] {format_bytes(analysis.max_capacity_bytes)}",
        f"[bold]Headroom:[/bold] {format_bytes(analysis.headroom_bytes)}",
    ]
    if analysis.per_slot_suggestion_bytes:
        sugg = format_bytes(analysis.per_slot_suggestion_bytes)
        advice_lines.append(f"[bold green]Suggested Module:[/bold green] up to {sugg} per slot")

    advice_lines.append(f"\n[bold]Advisor Summary:[/bold]\n{analysis.summary}")

    if analysis.installed_vs_usable_note:
        advice_lines.append(f"\n[cyan]Memory Note:[/cyan] {analysis.installed_vs_usable_note}")

    if analysis.caveats:
        advice_lines.append("\n[dim]Caveats:[/dim]")
        for c in analysis.caveats:
            advice_lines.append(f"[dim]- {c}[/dim]")

    console.print(
        Panel("\n".join(advice_lines), title="Memory Upgrade Advisor", border_style="green")
    )


def _render_storage(env: FactEnvelope[StorageFact]) -> None:
    table = Table(
        title="Storage Block Devices",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Device", style="bold", no_wrap=True)
    table.add_column("Type", no_wrap=True)
    table.add_column("Capacity", no_wrap=True)
    table.add_column("Media", no_wrap=True)
    table.add_column("Transport", no_wrap=True)
    table.add_column("Model")
    table.add_column("Removable", no_wrap=True)

    data = (
        env.data if isinstance(env.data, StorageFact) else StorageFact.model_validate(env.data)
    )
    for dev in data.devices:
        media = "SSD" if dev.is_ssd else ("HDD" if dev.rotational else "Unknown")
        tran = dev.transport or ("nvme" if dev.is_nvme else "unknown")
        capacity = format_bytes(dev.size_bytes, include_decimal=True)
        table.add_row(
            dev.name,
            dev.device_type or "disk",
            capacity,
            media,
            tran,
            dev.model or "Unknown",
            "Yes" if dev.removable else "No",
        )
    console.print(table)


def _render_gpu(env: FactEnvelope[GpuFact]) -> None:
    table = Table(title="Graphics & GPU Controllers", show_header=True, header_style="bold cyan")
    table.add_column("Slot", style="bold")
    table.add_column("Vendor")
    table.add_column("Device Name")
    table.add_column("Type")
    table.add_column("VRAM")
    table.add_column("Driver")

    data = env.data if isinstance(env.data, GpuFact) else GpuFact.model_validate(env.data)
    for dev in data.devices:
        gpu_type = "Integrated" if dev.is_integrated else "Discrete"
        vram = format_bytes(dev.vram_bytes) if dev.vram_bytes else "Shared / Unreported"
        table.add_row(
            dev.slot,
            dev.vendor,
            dev.device_name,
            gpu_type,
            vram,
            dev.driver_version or "Unknown",
        )
    console.print(table)

    if env.caveats:
        for c in env.caveats:
            console.print(f"[dim cyan]Note: {c}[/dim cyan]")


def _render_system(env: FactEnvelope[SystemOverviewFact]) -> None:
    table = Table(title="System Overview", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    data = (
        env.data
        if isinstance(env.data, SystemOverviewFact)
        else SystemOverviewFact.model_validate(env.data)
    )
    table.add_row("Product Name", data.product_name or "Unknown")
    table.add_row("System Vendor", data.sys_vendor or "Unknown")
    mb_info = f"{data.board_vendor or ''} {data.board_name or ''}".strip() or "Unknown"
    table.add_row("Motherboard", mb_info)
    table.add_row(
        "BIOS",
        f"{data.bios_vendor or ''} {data.bios_version or ''} ({data.bios_date or ''})".strip()
        or "Unknown",
    )
    table.add_row("Operating System", data.os_pretty_name or "Unknown")
    table.add_row("Kernel Release", data.kernel_release or "Unknown")
    console.print(table)


@app.command()
def ask(
    ctx: typer.Context,
    question: Annotated[str, typer.Argument(help="Question about local hardware")],
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Override fixture for ask query."),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", help="Override backend: auto, linux, replay."),
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="Override LLM client: ollama or scripted."),
    ] = None,
    show_tools: Annotated[
        bool,
        typer.Option("--show-tools", help="Print tool calls with status and confidence."),
    ] = False,
) -> None:
    """Ask a single question about your Linux hardware and exit (SRS 4.1, FR-CLI-1)."""
    cfg: Config = ctx.obj
    if fixture is not None or backend is not None or llm is not None or show_tools:
        valid_llm: LLMChoice | None = None
        if llm in ("ollama", "scripted"):
            valid_llm = llm  # type: ignore[assignment]
        cfg = load_config(
            cli_backend=_resolve_cli_backend(backend, fixture or cfg.fixture, cfg.backend),
            cli_fixture=fixture if fixture else cfg.fixture,
            cli_llm=valid_llm if valid_llm is not None else cfg.llm,
            cli_show_tools=show_tools if show_tools else cfg.show_tools,
            cli_demo=cfg.demo,
        )

    sys_backend = create_backend(cfg)
    llm_client = create_llm_client(cfg)
    orchestrator = Orchestrator(backend=sys_backend, llm=llm_client)
    session = Session()

    def on_tool(name: str, status: str, conf: str) -> None:
        if cfg.show_tools:
            console.print(
                f"[dim cyan]  [Tool] {name} -> status={status}, confidence={conf}[/dim cyan]"
            )

    try:
        answer = orchestrator.run_turn(session, question, on_tool_call=on_tool)
        console.print(answer)
    except (OllamaConnectionError, OllamaModelError) as err:
        console.print(f"[red]LLM Error:[/red] {err}")
        console.print("[dim]Tip: run 'hwq facts' for local facts without an LLM.[/dim]")
        raise typer.Exit(code=1) from err


@app.command()
def facts(
    ctx: typer.Context,
    category: Annotated[
        str,
        typer.Argument(help="Fact category: cpu, memory, storage, gpu, system, or all"),
    ] = "all",
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output raw facts and analysis as JSON."),
    ] = False,
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Override fixture for facts inspection."),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", help="Override backend: auto, linux, replay."),
    ] = None,
) -> None:
    """Print typed hardware facts without using an LLM (SRS 4.1, FR-CLI-2)."""
    cfg: Config = ctx.obj
    if fixture is not None or backend is not None:
        cfg = load_config(
            cli_backend=_resolve_cli_backend(backend, fixture or cfg.fixture, cfg.backend),
            cli_fixture=fixture if fixture else cfg.fixture,
            cli_llm=cfg.llm,
        )

    cat = category.strip().lower()
    valid_categories = ("cpu", "memory", "storage", "gpu", "system", "all")
    if cat not in valid_categories:
        console.print(
            f"[red]Error:[/red] Invalid category '{category}'. "
            f"Must be one of: {', '.join(valid_categories)}"
        )
        raise typer.Exit(code=2)

    sys_backend = create_backend(cfg)
    results: dict[str, Any] = {}

    if cat in ("cpu", "all"):
        cpu_env = CpuTool().execute(sys_backend)
        results["cpu"] = cpu_env.model_dump()
        if not as_json:
            _render_cpu(cpu_env)

    if cat in ("memory", "all"):
        sum_env = MemorySummaryTool().execute(sys_backend)
        top_env = MemoryTopologyTool().execute(sys_backend)
        analysis = analyze_memory(top_env, sum_env)
        results["memory_summary"] = sum_env.model_dump()
        results["memory_topology"] = top_env.model_dump()
        results["memory_upgrade"] = analysis.model_dump()
        if not as_json:
            _render_memory(sum_env, top_env, analysis)

    if cat in ("storage", "all"):
        storage_env = StorageTool().execute(sys_backend)
        results["storage"] = storage_env.model_dump()
        if not as_json:
            _render_storage(storage_env)

    if cat in ("gpu", "all"):
        gpu_env = GpuTool().execute(sys_backend)
        results["gpu"] = gpu_env.model_dump()
        if not as_json:
            _render_gpu(gpu_env)

    if cat in ("system", "all"):
        sys_env = SystemTool().execute(sys_backend)
        results["system"] = sys_env.model_dump()
        if not as_json:
            _render_system(sys_env)

    if as_json:
        console.print_json(json.dumps(results, indent=2))


@app.command()
def doctor(
    ctx: typer.Context,
    print_sudoers: Annotated[
        bool,
        typer.Option("--print-sudoers", help="Print recommended sudoers drop-in rule and exit."),
    ] = False,
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Override fixture for doctor diagnostics."),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", help="Override backend: auto, linux, replay."),
    ] = None,
) -> None:
    """Check system tools, sudo privilege status, and Ollama connection (SRS 4.1, FR-CLI-3)."""
    cfg: Config = ctx.obj
    if fixture is not None or backend is not None:
        cfg = load_config(
            cli_backend=_resolve_cli_backend(backend, fixture or cfg.fixture, cfg.backend),
            cli_fixture=fixture if fixture else cfg.fixture,
            cli_llm=cfg.llm,
        )

    if print_sudoers:
        console.print(generate_sudoers_rule())
        return

    console.print(f"[bold]hwq Doctor[/bold] [dim]v{__version__}[/dim]\n")

    # 1. Backend Status
    backend_table = Table(title="1. Execution Backend", show_header=True, header_style="bold cyan")
    backend_table.add_column("Property", style="bold")
    backend_table.add_column("Status")
    backend_table.add_row("Configured Backend", cfg.backend)
    backend_table.add_row("Resolved Backend", f"[green]{cfg.resolved_backend}[/green]")
    if cfg.resolved_backend == "replay":
        fixture_name = cfg.fixture if cfg.fixture else "synthetic-8gb-1of2 (default)"
        backend_table.add_row("Replay Fixture", fixture_name)
    console.print(backend_table)
    console.print()

    # 2. Trusted Tool Probe
    tools_table = Table(
        title="2. System Tools (Trusted Paths)", show_header=True, header_style="bold cyan"
    )
    tools_table.add_column("Binary", style="bold")
    tools_table.add_column("Found")
    tools_table.add_column("Path / Status")

    probe_binaries = ["dmidecode", "lscpu", "lsblk", "lspci", "nvidia-smi"]
    dmi_path: str | None = None
    for b in probe_binaries:
        found_path = find_binary(b)
        if found_path:
            tools_table.add_row(b, "[green]Yes[/green]", str(found_path))
            if b == "dmidecode":
                dmi_path = str(found_path)
        else:
            tools_table.add_row(b, "[yellow]No[/yellow]", "[dim]Not found in trusted paths[/dim]")
    console.print(tools_table)
    console.print()

    # 3. Privilege / Sudo Rule Status
    sudo_table = Table(
        title="3. Privilege & Sudo Status", show_header=True, header_style="bold cyan"
    )
    sudo_table.add_column("Check", style="bold")
    sudo_table.add_column("Status")
    sudo_table.add_column("Notes")

    if cfg.resolved_backend == "replay":
        sys_backend = create_backend(cfg)
        top_env = MemoryTopologyTool().execute(sys_backend)
        if top_env.status == "ok":
            sudo_table.add_row(
                "dmidecode (Replay)",
                "[green]Available[/green]",
                "Fixture contains recorded privileged DMI data",
            )
        else:
            sudo_table.add_row(
                "dmidecode (Replay)",
                f"[yellow]{top_env.status}[/yellow]",
                top_env.reason or "Simulated permission denial in fixture",
            )
    else:
        # On real Linux
        if dmi_path:
            sudo_table.add_row(
                "dmidecode binary",
                "[green]Present[/green]",
                dmi_path,
            )
            # Check passwordless sudo access safely
            from hwq.exec.runner import run_command
            from hwq.models import CommandSpec
            test_spec = CommandSpec(
                argv=("sudo", "-n", dmi_path, "-t", "memory"),
                privileged=True,
                timeout_s=3.0,
            )
            res = run_command(test_spec)
            if res.status == "ok":
                sudo_table.add_row(
                    "Passwordless sudo rule",
                    "[green]Active[/green]",
                    "dmidecode runs without password",
                )
            else:
                sudo_table.add_row(
                    "Passwordless sudo rule",
                    "[yellow]Not Configured[/yellow]",
                    "Run 'hwq doctor --print-sudoers' to view recommended rule",
                )
        else:
            sudo_table.add_row(
                "dmidecode binary",
                "[yellow]Missing[/yellow]",
                "Install dmidecode or run in unprivileged degraded mode",
            )
    console.print(sudo_table)
    console.print()

    # 4. Ollama LLM Status
    ollama_table = Table(
        title="4. Local LLM Service (Ollama)", show_header=True, header_style="bold cyan"
    )
    ollama_table.add_column("Property", style="bold")
    ollama_table.add_column("Status")

    tags_url = f"{cfg.ollama_url.rstrip('/')}/api/tags"
    ollama_table.add_row("Configured Endpoint", cfg.ollama_url)
    ollama_table.add_row("Configured Model", cfg.ollama_model)

    try:
        req = urllib.request.Request(tags_url, headers={"User-Agent": f"hwq/{__version__}"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in body.get("models", [])]
                model_names = ", ".join(models) if models else "None"
                ollama_table.add_row("Connection", "[green]Reachable[/green]")
                ollama_table.add_row("Local Models", model_names)
            else:
                ollama_table.add_row("Connection", f"[yellow]HTTP {resp.status}[/yellow]")
    except Exception:
        ollama_table.add_row(
            "Connection",
            "[yellow]Unreachable[/yellow] ([dim]connection refused or timed out[/dim])",
        )
        ollama_table.add_row(
            "Note",
            "Start Ollama with 'ollama serve'. Run 'hwq facts' for facts without an LLM.",
        )
    console.print(ollama_table)


@app.command(name="eval")
def eval_cmd(
    ctx: typer.Context,
    live: Annotated[
        bool,
        typer.Option("--live", help="Use live Ollama LLM instead of scripted client"),
    ] = False,
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Override fixture for all test cases"),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option("--json", help="Output evaluation results as raw JSON"),
    ] = False,
) -> None:
    """Run golden evaluation suite verifying acceptance criteria (AT-1..AT-10)."""
    from hwq.eval import run_eval_suite
    from hwq.exec.backend import load_fixture_backend
    from hwq.llm.ollama import OllamaClient
    from hwq.llm.scripted import ScriptedClient
    from hwq.protocols import LLMClient

    cfg = load_config()
    llm: LLMClient = (
        OllamaClient(
            url=cfg.ollama_url,
            model=cfg.ollama_model,
        )
        if live
        else ScriptedClient()
    )

    backend = load_fixture_backend(fixture) if fixture else None
    report = run_eval_suite(backend_override=backend, llm_override=llm)

    if json_out:
        summary = {
            "passed_count": report.passed_count,
            "total_count": report.total_count,
            "all_passed": report.all_passed,
            "results": [
                {
                    "id": r.case.id,
                    "name": r.case.name,
                    "query": r.case.query,
                    "fixture": r.case.fixture,
                    "passed": r.passed,
                    "grounded": r.is_grounded,
                    "tools_called": r.tools_called,
                    "failure_reasons": r.failure_reasons,
                }
                for r in report.results
            ],
        }
        console.print(json.dumps(summary, indent=2))
        if not report.all_passed:
            raise typer.Exit(1)
        return

    table = Table(
        title="hwq Golden Evaluation Suite (AT-1..AT-10)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", style="bold", width=6)
    table.add_column("Case Name", width=36)
    table.add_column("Fixture", width=20)
    table.add_column("Tools Called", width=28)
    table.add_column("Grounded", justify="center", width=10)
    table.add_column("Status", justify="center", width=10)

    for r in report.results:
        status_str = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        grounded_str = "[green]YES[/green]" if r.is_grounded else "[red]NO[/red]"
        tools_str = ", ".join(r.tools_called) if r.tools_called else "[dim]None[/dim]"
        table.add_row(
            r.case.id,
            r.case.name,
            r.case.fixture,
            tools_str,
            grounded_str,
            status_str,
        )

    console.print(table)
    console.print()
    if report.all_passed:
        console.print(
            f"[bold green]Evaluation Succeeded:[/bold green] "
            f"{report.passed_count}/{report.total_count} cases passed."
        )
    else:
        console.print(
            f"[bold red]Evaluation Failed:[/bold red] "
            f"{report.passed_count}/{report.total_count} cases passed."
        )
        for r in report.results:
            if not r.passed:
                console.print(f"[red]• {r.case.id} ({r.case.name}):[/red]")
                for reason in r.failure_reasons:
                    console.print(f"  - {reason}")
        raise typer.Exit(1)


@app.command()
def snapshot(
    ctx: typer.Context,
    out: Annotated[
        str,
        typer.Option("--out", "-o", help="Target directory for recorded fixture files"),
    ],
) -> None:
    """Record raw system outputs into a fixture folder for offline replay."""
    out_path = take_snapshot(out)
    console.print(f"Snapshot recorded successfully to {out_path}")


if __name__ == "__main__":
    app()
