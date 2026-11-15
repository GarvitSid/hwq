"""Standalone system snapshot recorder (SRS 4.5, FR-BE-4).

This module must remain stdlib-only so it can run on bare live USB environments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hwq.exec.backend import LinuxBackend, RecordingBackend, record_all_allowlisted


def take_snapshot(
    out_dir: Path | str,
    name: str = "snapshot",
    *,
    synthetic: bool = False,
) -> Path:
    """Take a full snapshot of local Linux hardware facts into a fixture folder."""
    target_dir = Path(out_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    backend = LinuxBackend()
    recorder = RecordingBackend(
        backend=backend,
        out_dir=target_dir,
        fixture_name=name,
        synthetic=synthetic,
    )

    record_all_allowlisted(recorder)
    return target_dir


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for python -m hwq.snapshot."""
    parser = argparse.ArgumentParser(
        prog="python -m hwq.snapshot",
        description="Record read-only Linux hardware outputs into a fixture directory.",
    )
    parser.add_argument(
        "--out",
        "-o",
        required=True,
        help="Target directory path for the snapshot fixture folder.",
    )
    parser.add_argument(
        "--name",
        "-n",
        default="snapshot",
        help="Name identifier for the fixture recorded in index.json.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Mark index.json as synthetic.",
    )

    args = parser.parse_args(argv)

    try:
        out_path = take_snapshot(args.out, name=args.name, synthetic=args.synthetic)
        sys.stdout.write(f"Snapshot recorded successfully to {out_path}\n")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Snapshot error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
