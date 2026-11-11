#!/usr/bin/env python3
"""Prepare a checkout from the separately supplied participant ZIP (stdlib only)."""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import venv
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent.parent
ARCHIVES = (
    "01_2026-05-12_baseline.zip",
    "02_2026-05-19_recrawl.zip",
    "03_2026-06-09_recrawl.zip",
    "04_2026-08-27_rebaseline.zip",
    "05_2026-09-28_latest.zip",
)


def install_archives(kit: Path, destination: Path) -> None:
    """Validate all five nested archives before copying; never replace different local data."""
    if not kit.is_file():
        raise ValueError(f"Participant ZIP not found: {kit}. Use --kit /path/to/hackathon-knowledge-kit-participant.zip")
    payloads = {}
    try:
        with ZipFile(kit) as outer:
            for name in ARCHIVES:
                matches = [entry for entry in outer.infolist()
                           if PurePosixPath(entry.filename).parts[-2:] == ("snapshots_zip", name)]
                if len(matches) != 1:
                    raise ValueError(f"Participant ZIP must contain exactly one snapshots_zip/{name}")
                data = outer.read(matches[0])
                with ZipFile(io.BytesIO(data)) as inner:
                    manifest = f"{Path(name).stem}/manifest.json"
                    if manifest not in inner.namelist():
                        raise ValueError(f"{name} is missing {manifest}")
                    broken = inner.testzip()
                    if broken:
                        raise ValueError(f"{name} has a corrupt entry: {broken}")
                target = destination / name
                if target.exists() and (not target.is_file() or target.read_bytes() != data):
                    raise ValueError(f"Existing archive differs; left untouched: {target}")
                payloads[name] = data
    except BadZipFile as exc:
        raise ValueError(f"Invalid participant or snapshot ZIP: {exc}") from exc
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        target = destination / name
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path,
                        default=Path.home() / "Downloads/hackathon-knowledge-kit-participant.zip",
                        help="participant ZIP; defaults to ~/Downloads/hackathon-knowledge-kit-participant.zip")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.exit(1, "setup: run this script with python3.11\n")
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if environment.exists():
            if not python.is_file():
                raise ValueError(f"Existing environment is incomplete: {environment}")
            subprocess.run([str(python), "-c", "import sys; sys.exit(sys.version_info[:2] != (3, 11))"], check=True)
        install_archives(args.kit.expanduser(), ROOT / "snapshots_zip")
        if not environment.exists():
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--disable-pip-version-check",
                        "-r", str(ROOT / "submission/requirements.txt")], check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"setup: {exc}", file=sys.stderr)
        return 1
    print("Setup complete: five snapshot ZIPs and a Python 3.11 environment are ready.")
    print(f"From {ROOT}, run:")
    print("  .venv\\Scripts\\activate" if os.name == "nt" else "  . .venv/bin/activate")
    print("  python harness/run_eval.py --submission submission --eval eval/public_eval.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
