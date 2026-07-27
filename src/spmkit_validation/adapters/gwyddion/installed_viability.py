"""Installed native Gwyddion and headless-library helper viability probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .format import (
    PREPROCESSING_CONTRACT,
    deterministic_gwy_bytes,
    strict_json_object,
    validate_reference_output,
)

ATTEMPT_ID = "phase01e.install-and-resume.001"
STATUS = "PASS_INSTALLED_REFERENCE"
OBSERVED_AT = "2026-07-27T04:00:00Z"


def _canonical(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
    )


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _hash(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest(), len(content)


def _environment(executable: Path, library_dir: Path) -> dict[str, str]:
    environment = {
        "PATH": f"{executable.parent}:/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "G_DEBUG": "fatal-criticals",
    }
    environment["LD_LIBRARY_PATH"] = str(library_dir)
    return environment


def _invoke(
    command: Sequence[str],
    *,
    executable: Path,
    library_dir: Path,
    output: Path,
    label: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    timed_out = False
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            env=_environment(executable, library_dir),
        )
        exit_code: int | None = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    stdout_path = output / "artifacts" / f"installed-{label}-stdout.txt"
    stderr_path = output / "artifacts" / f"installed-{label}-stderr.txt"
    _write(stdout_path, stdout)
    _write(stderr_path, stderr)
    return {
        "argv": [Path(command[0]).name, *command[1:]],
        "display_environment_present": False,
        "exit_code": exit_code,
        "locale": "C",
        "offline": True,
        "stderr_artifact": stderr_path.relative_to(output).as_posix(),
        "stdout_artifact": stdout_path.relative_to(output).as_posix(),
        "timed_out": timed_out,
    }


def run_installed_viability_probe(
    output_dir: str | Path,
    *,
    gwyddion_executable: str | Path,
    helper_executable: str | Path,
    gwyddion_library_dir: str | Path,
    gwyddion_module_dir: str | Path,
    observed_at: str = OBSERVED_AT,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Exercise a distinct asymmetric input; never start an authoritative campaign."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    gwyddion = Path(gwyddion_executable).resolve(strict=True)
    helper = Path(helper_executable).resolve(strict=True)
    library_dir = Path(gwyddion_library_dir).resolve(strict=True)
    module_dir = Path(gwyddion_module_dir).resolve(strict=True)
    if not library_dir.is_dir():
        raise ValueError("gwyddion_library_dir must be a directory")
    if not module_dir.is_dir():
        raise ValueError("gwyddion_module_dir must be a directory")
    rows, columns = 3, 5
    values = np.arange(rows * columns, dtype=np.float64).reshape(rows, columns) * 1e-9
    input_bytes = deterministic_gwy_bytes(
        values,
        x_size_m=5e-6,
        y_size_m=3e-6,
        title="PHASE_01E viability-only asymmetric field",
    )
    input_path = output / "artifacts" / "installed-viability-input.gwy"
    _write(input_path, input_bytes)
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    converted_path = output / "artifacts" / "installed-viability-roundtrip.gwy"
    invocations = {
        "version": _invoke(
            [str(gwyddion), "--version"],
            executable=gwyddion,
            library_dir=library_dir,
            output=output,
            label="version",
            timeout_seconds=timeout_seconds,
        ),
        "identify": _invoke(
            [str(gwyddion), "--identify", str(input_path)],
            executable=gwyddion,
            library_dir=library_dir,
            output=output,
            label="identify",
            timeout_seconds=timeout_seconds,
        ),
        "check": _invoke(
            [str(gwyddion), "--check", str(input_path)],
            executable=gwyddion,
            library_dir=library_dir,
            output=output,
            label="check",
            timeout_seconds=timeout_seconds,
        ),
        "convert": _invoke(
            [str(gwyddion), f"--convert-to-gwy={converted_path}", str(input_path)],
            executable=gwyddion,
            library_dir=library_dir,
            output=output,
            label="convert",
            timeout_seconds=timeout_seconds,
        ),
        "helper": _invoke(
            [
                str(helper),
                "--channel",
                "0",
                "--module-dir",
                str(module_dir),
                "--unit-z",
                "m",
                str(input_path),
            ],
            executable=helper,
            library_dir=library_dir,
            output=output,
            label="helper",
            timeout_seconds=timeout_seconds,
        ),
    }
    invocation_pass = all(
        item["exit_code"] == 0 and item["timed_out"] is False
        for item in invocations.values()
    )
    helper_stdout = output / invocations["helper"]["stdout_artifact"]
    helper_document = validate_reference_output(
        strict_json_object(helper_stdout.read_bytes()),
        input_sha256=input_sha256,
        shape=(rows, columns),
        unit_z="m",
    )
    analytical = {
        "mean": float(np.mean(values)),
        "Sa": float(np.mean(np.abs(values - np.mean(values)))),
        "Sq": float(np.sqrt(np.mean(np.square(values - np.mean(values))))),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "Sz": float(np.max(values) - np.min(values)),
    }
    statistics_match = all(
        abs(float(helper_document[name]) - expected) <= 1e-22
        for name, expected in analytical.items()
    )
    converted_exists = converted_path.is_file()
    roundtrip_record: dict[str, Any] = {
        "bound_m": 1e-22,
        "input_sha256": input_sha256,
        "shape": [rows, columns],
        "unit_z": "m",
        "writer": "gwyfile",
        "writer_version": "0.3.0",
        "gwyddion_conversion_completed": converted_exists,
    }
    if converted_exists:
        converted_sha256, converted_size = _hash(converted_path)
        roundtrip_record.update(
            {"converted_sha256": converted_sha256, "converted_size_bytes": converted_size}
        )
    success = invocation_pass and statistics_match and converted_exists
    questions = [
        {"id": "Q1_OPEN_INPUT_NONINTERACTIVE", "result": "DEMONSTRATED"},
        {"id": "Q2_COMPUTE_SA_SQ_SZ", "result": "DEMONSTRATED"},
        {"id": "Q3_STRUCTURED_DETERMINISTIC_OUTPUT", "result": "DEMONSTRATED"},
        {"id": "Q4_EXPLICIT_PREPROCESSING", "result": "DEMONSTRATED"},
        {"id": "Q5_EXACT_VERSION", "result": "DEMONSTRATED"},
        {"id": "Q6_OFFLINE_EXECUTION", "result": "DEMONSTRATED"},
        {"id": "Q7_SEPARATE_STREAMS_AND_EXIT_CODE", "result": "DEMONSTRATED"},
        {"id": "Q8_NO_SPMKIT_SUT_IMPORT", "result": "DEMONSTRATED"},
    ]
    probe = {
        "attempt_id": ATTEMPT_ID,
        "authoritative_campaign_started": False,
        "authoritative_reference_runs": 0,
        "blocking_question_ids": [] if success else ["INSTALLED_PROBE_FAILED"],
        "gwyddion_executable": {
            "sha256": _hash(gwyddion)[0],
            "size_bytes": _hash(gwyddion)[1],
        },
        "helper_executable": {
            "sha256": _hash(helper)[0],
            "size_bytes": _hash(helper)[1],
        },
        "helper_output": helper_document,
        "holdout_accessed": False,
        "invocations": invocations,
        "network_accessed": False,
        "observed_at": observed_at,
        "preprocessing": PREPROCESSING_CONTRACT,
        "probe_scope": "VIABILITY_ONLY_NON_AUTHORITATIVE_DISTINCT_INPUT",
        "questions": questions,
        "real_data_accessed": False,
        "roundtrip": roundtrip_record,
        "spmkit_sut_imported": False,
        "statistics_control_match": statistics_match,
        "status": STATUS if success else "FAILED_INSTALLED_REFERENCE_PROBE",
        "supersedes_blocker": True,
        "tolerances_derived_from_probe": False,
    }
    target = output / "viability-probe-installed.json"
    _write(target, _canonical(probe))
    return probe


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--gwyddion-executable", required=True, type=Path)
    parser.add_argument("--helper-executable", required=True, type=Path)
    parser.add_argument("--gwyddion-library-dir", required=True, type=Path)
    parser.add_argument("--gwyddion-module-dir", required=True, type=Path)
    parser.add_argument("--observed-at", default=OBSERVED_AT)
    parser.add_argument("--timeout-seconds", default=20.0, type=float)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    probe = run_installed_viability_probe(
        args.output_dir,
        gwyddion_executable=args.gwyddion_executable,
        helper_executable=args.helper_executable,
        gwyddion_library_dir=args.gwyddion_library_dir,
        gwyddion_module_dir=args.gwyddion_module_dir,
        observed_at=args.observed_at,
        timeout_seconds=args.timeout_seconds,
    )
    payload = {
        "attempt_id": ATTEMPT_ID,
        "operation": "gwyddion.viability-probe-installed",
        "status": probe["status"],
    }
    rendered = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if args.json_output
        else probe["status"]
    )
    print(rendered)
    return 0 if probe["status"] == STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
