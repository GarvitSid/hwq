"""Unit tests for parsers, over-match guards, and AT-3 / AT-7 paths (SRS 4.6, 8)."""

from hwq.exec.backend import load_fixture_backend
from hwq.facts import MemoryTopologyFact
from hwq.models import RawResult
from hwq.parse.dmidecode import parse_dmidecode_memory
from hwq.parse.lsblk import parse_lsblk
from hwq.parse.lscpu import parse_lscpu
from hwq.parse.lspci import parse_gpu_info
from hwq.parse.meminfo import parse_meminfo
from hwq.parse.sanitize import sanitize_text
from hwq.parse.system import parse_system_overview


def test_sanitize_text() -> None:
    """sanitize_text strips control characters and caps at max_len."""
    raw = "Intel\x00(R) Core\x07(TM)   \t\n i7 \x1b[31mCPU\x1b[0m"
    clean = sanitize_text(raw)
    assert "\x00" not in clean
    assert "\x07" not in clean
    assert clean.startswith("Intel (R) Core")

    # Length capping at 120
    long_str = "A" * 200
    assert len(sanitize_text(long_str)) == 120


def test_dmidecode_size_overmatch_guard() -> None:
    """FR-PARSE-2: Do not count Volatile Size, Cache Size, or Logical Size as module size."""
    raw_sample = """
Handle 0x0010, DMI type 16, 23 bytes
Physical Memory Array
	Maximum Capacity: 64 GB
	Number Of Devices: 1

Handle 0x0011, DMI type 17, 92 bytes
Memory Device
	Array Handle: 0x0010
	Volatile Size: 32 GB
	Cache Size: 64 MB
	Logical Size: 128 GB
	Size: 16 GB
	Form Factor: SODIMM
	Type: DDR4
	Speed: 3200 MT/s
"""
    env = parse_dmidecode_memory(raw_sample)
    assert env.status == "ok"
    assert isinstance(env.data, MemoryTopologyFact)
    assert len(env.data.devices) == 1

    device = env.data.devices[0]
    # Size must be 16 GB (17179869184 bytes), not 32 GB or 128 GB or 64 MB
    expected_bytes = 16 * 1024 * 1024 * 1024
    assert device.size_bytes == expected_bytes
    assert env.data.installed_bytes == expected_bytes


def test_dmidecode_no_module_installed() -> None:
    """Empty slots report size_bytes=None and do not inflate installed_bytes."""
    raw_sample = """
Handle 0x0010, DMI type 16, 23 bytes
Physical Memory Array
	Maximum Capacity: 32 GB
	Number Of Devices: 2

Handle 0x0011, DMI type 17, 92 bytes
Memory Device
	Size: No Module Installed
	Form Factor: SODIMM

Handle 0x0012, DMI type 17, 92 bytes
Memory Device
	Size: 8 GB
	Form Factor: SODIMM
"""
    env = parse_dmidecode_memory(raw_sample)
    assert env.status == "ok"
    assert env.data.slots_total == 2
    assert env.data.slots_used == 1
    assert env.data.slots_free == 1
    assert env.data.installed_bytes == 8 * 1024 * 1024 * 1024


def test_at3_nvme_plus_sata() -> None:
    """AT-3: 'Is my SSD NVMe?' on nvme-plus-sata produces correct per-disk answer with evidence."""
    backend = load_fixture_backend("nvme-plus-sata")
    spec = backend.entries["cmd:lsblk -J -b -d -o NAME,TYPE,SIZE,MODEL,ROTA,TRAN,RM,HOTPLUG"]
    file_content = (backend.fixture_dir / spec["file"]).read_text(encoding="utf-8")

    env = parse_lsblk(file_content)
    assert env.status == "ok"

    devs = {d.name: d for d in env.data.devices}
    assert "nvme0n1" in devs
    assert "sda" in devs

    nvme_dev = devs["nvme0n1"]
    assert nvme_dev.is_nvme is True
    assert nvme_dev.is_ssd is True
    assert nvme_dev.nvme_evidence is not None
    assert "nvme" in nvme_dev.nvme_evidence.lower()

    sata_dev = devs["sda"]
    assert sata_dev.is_nvme is False
    assert sata_dev.is_ssd is False  # rotational == True
    assert sata_dev.rotational is True


def test_at7_missing_binary() -> None:
    """AT-7: Missing binary yields FactEnvelope with status unavailable and caveat/reason."""
    raw_unavailable = RawResult(
        argv=("lspci", "-mm", "-nn"),
        exit_code=127,
        stdout="",
        stderr="lspci: command not found",
        status="unavailable",
    )
    env = parse_gpu_info(raw_unavailable)
    assert env.status == "unavailable"
    assert env.confidence == "low"
    assert "command not found" in (env.reason or "")
    assert len(env.data.devices) == 0


def test_parse_meminfo_nominal() -> None:
    """parse_meminfo extracts bytes correctly from /proc/meminfo."""
    sample = """MemTotal:        16384000 kB
MemFree:          8192000 kB
MemAvailable:    12288000 kB
SwapTotal:        4194304 kB
SwapFree:         4194304 kB
"""
    env = parse_meminfo(sample)
    assert env.status == "ok"
    assert env.data.total_bytes == 16384000 * 1024
    assert env.data.free_bytes == 8192000 * 1024
    assert env.data.available_bytes == 12288000 * 1024


def test_parse_lscpu_nominal() -> None:
    """parse_lscpu flattens JSON hierarchy and computes cores/threads."""
    sample = """{
   "lscpu": [
      {"field": "Architecture:", "data": "x86_64"},
      {"field": "Model name:", "data": "AMD Ryzen 7 5800X"},
      {"field": "CPU(s):", "data": "16"},
      {"field": "Thread(s) per core:", "data": "2"},
      {"field": "Core(s) per socket:", "data": "8"},
      {"field": "Socket(s):", "data": "1"}
   ]
}"""
    env = parse_lscpu(sample)
    assert env.status == "ok"
    assert env.data.architecture == "x86_64"
    assert env.data.model_name == "AMD Ryzen 7 5800X"
    assert env.data.cores == 8
    assert env.data.threads == 16


def test_parse_system_overview_nominal() -> None:
    """parse_system_overview consolidates DMI sysfs files and os-release."""
    dmi = {
        "sys_vendor": "Framework",
        "product_name": "Laptop 13",
        "bios_version": "03.04",
    }
    os_rel = 'PRETTY_NAME="Fedora Linux 39"\nID=fedora\nVERSION_ID="39"\n'
    kernel = "6.6.8-200.fc39.x86_64\n"

    env = parse_system_overview(dmi, os_release=os_rel, kernel_release=kernel)
    assert env.status == "ok"
    assert env.data.sys_vendor == "Framework"
    assert env.data.product_name == "Laptop 13"
    assert env.data.os_pretty_name == "Fedora Linux 39"
    assert env.data.kernel_release == "6.6.8-200.fc39.x86_64"
