"""Exercise the installed CLI on the deterministic example files."""

import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "examples/source.ome.tif"
for name, expected_exit, expected_z in [
    ("changed.ome.tif", 1, "changed"),
    ("unit-equivalent.ome.tif", 0, "same"),
    ("plain.tif", 2, "lost"),
]:
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "reticle",
            str(source),
            str(root / "examples" / name),
            "--format",
            "json",
        ],
        cwd=root.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != expected_exit:
        raise SystemExit(
            f"{name}: expected exit {expected_exit}, got {run.returncode}: {run.stderr}"
        )
    report = json.loads(run.stdout)
    pair = report["pairs"][0]
    if "error" in pair:
        raise SystemExit(pair["error"])
    axes = {axis["axis"]: axis["status"] for axis in pair["comparison"]["axes"]}
    assert axes == {"X": "same", "Y": "same", "Z": expected_z}, axes
    print(f"{name}: exit {run.returncode}; {axes}")
