from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from spmkit_validation.adapters.gwyddion.library_runner import (
    GwyddionLibraryExecutionError,
    execute_gwyddion_library_reference,
)


def _fake_helper(directory: Path, mode: str = "success") -> Path:
    path = directory / f"fake-gwyddion-{mode}"
    path.write_text(
        f"""#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import time

mode = {mode!r}
if os.environ.get("LC_ALL") != "C" or "DISPLAY" in os.environ:
    raise SystemExit(19)
if mode == "timeout":
    time.sleep(2)
if mode == "nonzero":
    print("external failure", file=sys.stderr)
    raise SystemExit(9)
input_path = sys.argv[-1]
digest = hashlib.sha256(open(input_path, "rb").read()).hexdigest()
document = {{
    "schema": "spmkit-gwyddion-reference-output/0.1.0",
    "status": "COMPLETED",
    "producer": "Gwyddion libraries",
    "gwyddion_version": "2.71",
    "helper_version": "0.1.0",
    "input_sha256": digest,
    "channel": 0,
    "shape": [2, 2],
    "axis_order": "ROW_Y_COLUMN_X",
    "unit_z": "m",
    "unit_source": "GWYDDION_DATA_FIELD",
    "preprocessing": {{
        "leveling": "NONE", "filtering": "NONE", "masking": "NONE", "roi": "FULL_FIELD"
    }},
    "mean": 0.0, "Sa": 1.0, "Sq": 1.0, "min": -1.0, "max": 1.0, "Sz": 2.0
}}
mutations = {{
    "unsupported-version": ("gwyddion_version", "2.70"),
    "unit-mismatch": ("unit_z", "nm"),
    "hash-mismatch": ("input_sha256", "0"*64),
    "orientation-mismatch": ("axis_order", "COLUMN_X_ROW_Y"),
}}
if mode in mutations:
    key, value = mutations[mode]
    document[key] = value
if mode == "preprocessing-mismatch":
    document["preprocessing"]["leveling"] = "PLANE"
if mode == "malformed":
    print("{{not-json")
else:
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _protocol(root: Path, helper: Path) -> dict[str, object]:
    input_path = root / "input.gwy"
    input_path.write_bytes(b"GWYP-test-input")
    helper_content = helper.read_bytes()
    return {
        "campaign": {"campaign_id": "campaign.test"},
        "references": [
            {
                "reference_id": "reference.external.gwyddion-library.roughness",
                "version": "2.71",
            }
        ],
        "evidence": [
            {
                "artifact_id": "artifact.reference.helper-binary",
                "artifact_type": "INPUT",
                "relative_uri": "unused",
                "sha256": hashlib.sha256(helper_content).hexdigest(),
                "size_bytes": len(helper_content),
            },
            {
                "artifact_id": "artifact.reference.gwyddion-identity",
                "artifact_type": "REFERENCE_EXPORT",
                "relative_uri": "unused-identity",
                "sha256": "1" * 64,
                "size_bytes": 1,
            },
            {
                "artifact_id": "artifact.input.case.test",
                "artifact_type": "INPUT",
                "relative_uri": "input.gwy",
                "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "size_bytes": input_path.stat().st_size,
            },
        ],
        "datasets": [
            {
                "dataset_id": "dataset.test",
                "locator": "input.gwy",
                "provenance": {"source_artifact_ids": ["artifact.input.case.test"]},
                "public_metadata": {"shape": [2, 2]},
            }
        ],
        "cases": [
            {
                "case_id": "case.test",
                "dataset_id": "dataset.test",
                "reference_id": "reference.external.gwyddion-library.roughness",
            }
        ],
    }


def _execute(tmp_path: Path, mode: str = "success", timeout: float = 1.0):
    helper = _fake_helper(tmp_path, mode)
    library = tmp_path / "lib"
    modules = tmp_path / "modules"
    library.mkdir()
    modules.mkdir()
    protocol = _protocol(tmp_path, helper)
    return execute_gwyddion_library_reference(
        protocol,
        artifact_root=tmp_path,
        helper_executable=helper,
        gwyddion_library_dir=library,
        gwyddion_module_dir=modules,
        output_dir=tmp_path / "execution",
        timeout_seconds=timeout,
    )


def test_batch_invocation_preserves_strict_output_and_streams(tmp_path: Path) -> None:
    result = _execute(tmp_path)

    assert len(result.runs) == 1
    assert result.runs[0]["execution_status"] == "COMPLETED"
    assert result.runs[0]["parameters"]["exit_code"] == 0
    assert result.observations["case.test"] == {"Sa": 1.0, "Sq": 1.0, "Sz": 2.0}
    case_dir = result.output_dir / "raw/case.test"
    assert json.loads((case_dir / "gwyddion-output.json").read_text())["status"] == "COMPLETED"
    assert json.loads((case_dir / "gwyddion-run.json").read_text())["input_sha256"]
    assert (case_dir / "gwyddion-stdout.txt").read_text().startswith("{")
    assert (case_dir / "gwyddion-stderr.txt").read_bytes() == b""


@pytest.mark.parametrize(
    "mode",
    [
        "unsupported-version",
        "malformed",
        "unit-mismatch",
        "hash-mismatch",
        "orientation-mismatch",
        "preprocessing-mismatch",
    ],
)
def test_machine_contract_mismatch_is_preserved_as_error(tmp_path: Path, mode: str) -> None:
    result = _execute(tmp_path, mode)

    assert result.runs[0]["execution_status"] == "ERROR"
    assert result.runs[0]["errors"][0]["code"] == "GWYDDION_MALFORMED_OUTPUT"
    assert result.observations == {}


def test_nonzero_exit_is_not_converted_to_pass(tmp_path: Path) -> None:
    result = _execute(tmp_path, "nonzero")

    assert result.runs[0]["execution_status"] == "ERROR"
    assert result.runs[0]["parameters"]["exit_code"] == 9
    assert result.runs[0]["errors"][0]["code"] == "GWYDDION_NONZERO_EXIT"


def test_timeout_is_preserved_without_observation(tmp_path: Path) -> None:
    result = _execute(tmp_path, "timeout", timeout=0.01)

    assert result.runs[0]["execution_status"] == "ERROR"
    assert result.runs[0]["parameters"]["exit_code"] is None
    assert result.runs[0]["errors"][0]["code"] == "GWYDDION_TIMEOUT"
    assert result.observations == {}


def test_missing_or_changed_helper_is_rejected_before_invocation(tmp_path: Path) -> None:
    helper = _fake_helper(tmp_path)
    protocol = _protocol(tmp_path, helper)
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o755)
    library = tmp_path / "lib"
    modules = tmp_path / "modules"
    library.mkdir()
    modules.mkdir()

    with pytest.raises(GwyddionLibraryExecutionError, match="frozen identity"):
        execute_gwyddion_library_reference(
            protocol,
            artifact_root=tmp_path,
            helper_executable=helper,
            gwyddion_library_dir=library,
            gwyddion_module_dir=modules,
            output_dir=tmp_path / "execution",
        )


def test_fake_helper_contains_no_spmkit_import(tmp_path: Path) -> None:
    helper = _fake_helper(tmp_path)

    assert b"import spmkit" not in helper.read_bytes()
    assert os.access(helper, os.X_OK)
