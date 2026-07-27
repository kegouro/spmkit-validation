from __future__ import annotations

from pathlib import Path

import pytest

from spmkit_validation.execution import prepare_synthetic_roughness_campaign
from spmkit_validation.lifecycle import freeze_bundle

FREEZE_TIME = "2026-07-26T08:02:00Z"


@pytest.fixture
def frozen_protocol(tmp_path: Path):
    prepared = prepare_synthetic_roughness_campaign(tmp_path / "campaign")
    frozen = freeze_bundle(
        prepared.bundle_path,
        prepared.output_dir,
        tmp_path / "snapshots",
        frozen_at=FREEZE_TIME,
    )
    return prepared, frozen


def write_fake_spmkit(path: Path, *, mode: str = "success") -> Path:
    source = f'''#!/usr/bin/python3
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

if "--help" in sys.argv:
    print("Usage: spmkit [OPTIONS] COMMAND [ARGS]...\\n  analyze")
    raise SystemExit(0)
if {mode!r} == "timeout":
    time.sleep(2)
if {mode!r} == "failure":
    print("synthetic failure", file=sys.stderr)
    raise SystemExit(9)
input_path = Path(sys.argv[2])
output = Path(sys.argv[sys.argv.index("--output") + 1])
output.mkdir(parents=True, exist_ok=True)
stem = input_path.stem
if ".flat." in stem:
    result = {{"Sa": 0.0, "Sq": 0.0, "Sz": 0.0, "unit": "m"}}
elif ".checkerboard." in stem:
    result = {{"Sa": 1e-9, "Sq": 1e-9, "Sz": 2e-9, "unit": "m"}}
else:
    result = {{"Sa": 2e-9, "Sq": 5 ** 0.5 * 1e-9, "Sz": 6e-9, "unit": "m"}}
(output / f"{{stem}}_roughness.json").write_text(json.dumps(result), encoding="utf-8")
with (output / f"{{stem}}_roughness.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["key", "value"])
    writer.writerows(result.items())
manifest = {{
    "schema_version": "1.0",
    "input_file": input_path.name,
    "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    "status": "OK",
}}
(output / f"{{stem}}_run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
print("human Sa=999 Sq=999 Sz=999")
'''
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o100)
    return path
