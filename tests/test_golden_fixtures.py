"""Golden fixture tests: every synthetic fixture raw file parses cleanly (SRS 4.6, 6.2)."""

from hwq.exec.backend import discover_fixtures, load_fixture_backend
from hwq.facts import (
    CpuFact,
    FactEnvelope,
    GpuFact,
    MemorySummaryFact,
    MemoryTopologyFact,
    StorageFact,
    SystemOverviewFact,
)
from hwq.parse import (
    parse_dmidecode_memory,
    parse_gpu_info,
    parse_lsblk,
    parse_lscpu,
    parse_meminfo,
    parse_system_overview,
)


def test_golden_parsers_over_all_fixtures() -> None:
    """Run every relevant parser across all 7 synthetic fixtures and verify typed contracts."""
    fixtures = discover_fixtures()
    assert len(fixtures) >= 7

    for name, fixture_dir in fixtures.items():
        backend = load_fixture_backend(fixture_dir)

        # 1. lscpu
        if "cmd:lscpu -J" in backend.entries:
            raw_file = fixture_dir / backend.entries["cmd:lscpu -J"]["file"]
            env = parse_lscpu(raw_file.read_text(encoding="utf-8"))
            assert isinstance(env, FactEnvelope)
            assert isinstance(env.data, CpuFact)
            assert env.status == "ok"
            assert env.data.architecture is not None

        # 2. meminfo
        if "file:/proc/meminfo" in backend.entries:
            raw_file = fixture_dir / backend.entries["file:/proc/meminfo"]["file"]
            env_mem = parse_meminfo(raw_file.read_text(encoding="utf-8"))
            assert isinstance(env_mem, FactEnvelope)
            assert isinstance(env_mem.data, MemorySummaryFact)
            assert env_mem.status == "ok"
            assert env_mem.data.total_bytes > 0

        # 3. lsblk
        lsblk_key = "cmd:lsblk -J -b -d -o NAME,TYPE,SIZE,MODEL,ROTA,TRAN,RM,HOTPLUG"
        if lsblk_key in backend.entries:
            raw_file = fixture_dir / backend.entries[lsblk_key]["file"]
            env_storage = parse_lsblk(raw_file.read_text(encoding="utf-8"))
            assert isinstance(env_storage, FactEnvelope)
            assert isinstance(env_storage.data, StorageFact)
            assert env_storage.status == "ok"
            assert len(env_storage.data.devices) > 0

        # 4. dmidecode
        dmi_key = "cmd:dmidecode -t memory"
        if dmi_key in backend.entries:
            raw_file = fixture_dir / backend.entries[dmi_key]["file"]
            entry_info = backend.entries[dmi_key]
            text = raw_file.read_text(encoding="utf-8")
            env_dmi = parse_dmidecode_memory(text)
            assert isinstance(env_dmi, FactEnvelope)
            assert isinstance(env_dmi.data, MemoryTopologyFact)
            if entry_info.get("status") == "ok":
                assert env_dmi.status in ("ok", "partial")

        # 5. lspci
        lspci_key = "cmd:lspci -mm -nn"
        if lspci_key in backend.entries:
            raw_file = fixture_dir / backend.entries[lspci_key]["file"]
            nv_key = (
                "cmd:nvidia-smi --query-gpu=name,memory.total,driver_version"
                " --format=csv,noheader,nounits"
            )
            nv_text = None
            if nv_key in backend.entries:
                nv_file = fixture_dir / backend.entries[nv_key]["file"]
                nv_text = nv_file.read_text(encoding="utf-8")

            env_gpu = parse_gpu_info(raw_file.read_text(encoding="utf-8"), nv_text)
            assert isinstance(env_gpu, FactEnvelope)
            assert isinstance(env_gpu.data, GpuFact)
            assert env_gpu.status == "ok"
            assert len(env_gpu.data.devices) > 0

        # 6. system overview (on synthetic-8gb-1of2)
        if name == "synthetic-8gb-1of2":
            dmi_dict = {}
            for dmi_field in ("product_name", "sys_vendor"):
                k = f"file:/sys/class/dmi/id/{dmi_field}"
                if k in backend.entries:
                    dmi_dict[dmi_field] = (fixture_dir / backend.entries[k]["file"]).read_text(
                        encoding="utf-8"
                    )
            os_rel = None
            if "file:/etc/os-release" in backend.entries:
                os_rel = (fixture_dir / backend.entries["file:/etc/os-release"]["file"]).read_text(
                    encoding="utf-8"
                )
            kernel_rel = None
            if "file:/proc/sys/kernel/osrelease" in backend.entries:
                kernel_rel = (
                    fixture_dir / backend.entries["file:/proc/sys/kernel/osrelease"]["file"]
                ).read_text(encoding="utf-8")

            env_sys = parse_system_overview(dmi_dict, os_rel, kernel_rel)
            assert isinstance(env_sys, FactEnvelope)
            assert isinstance(env_sys.data, SystemOverviewFact)
            assert env_sys.status == "ok"
            assert env_sys.data.product_name == "Inspiron 15 3511"
            assert env_sys.data.sys_vendor == "Dell Inc."
