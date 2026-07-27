"""Non-authoritative local viability probe for an external Gwyddion reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROBE_VERSION = "0.1.0"
BLOCKED_STATUS = "BLOCKED_GWYDDION_REFERENCE_CONTRACT"
DEFAULT_OBSERVED_AT = "2026-07-26T12:00:00Z"
DEFAULT_CANDIDATES = ("gwyddion", "gwyfile", "gwyconvert")


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical_bytes(document))
    os.replace(temporary, path)


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _probe_invocation(
    executable: Path,
    command_name: str,
    argument: str,
    output_dir: Path,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    label = "version" if argument == "--version" else "help"
    stdout_relative = f"artifacts/{command_name}-{label}-stdout.txt"
    stderr_relative = f"artifacts/{command_name}-{label}-stderr.txt"
    environment = {
        "PATH": f"{executable.parent}:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        completed = subprocess.run(
            [str(executable), argument],
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            env=environment,
        )
        exit_code: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        status = "CAPTURED"
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        status = "TIMEOUT"
        timed_out = True
    except OSError as exc:
        exit_code = None
        stdout = b""
        stderr = str(exc).encode("utf-8", errors="replace")
        status = "EXECUTION_ERROR"
        timed_out = False
    _write_bytes(output_dir / stdout_relative, stdout)
    _write_bytes(output_dir / stderr_relative, stderr)
    return {
        "argv": [command_name, argument],
        "display_environment_present": False,
        "exit_code": exit_code,
        "locale": "C.UTF-8",
        "status": status,
        "stderr_artifact": stderr_relative,
        "stdout_artifact": stdout_relative,
        "timed_out": timed_out,
    }


def _question(
    question_id: str,
    text: str,
    result: str,
    *,
    blocking: bool,
    evidence: Sequence[str] = (),
    limitation: str,
) -> dict[str, Any]:
    return {
        "blocking": blocking,
        "evidence": list(evidence),
        "id": question_id,
        "limitation": limitation,
        "question": text,
        "result": result,
    }


def run_viability_probe(
    output_dir: str | Path,
    *,
    candidate_names: Sequence[str] = DEFAULT_CANDIDATES,
    search_path: str | None = None,
    observed_at: str = DEFAULT_OBSERVED_AT,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Inventory local commands without running a scientific reference campaign."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    selected: tuple[str, Path] | None = None
    for command_name in candidate_names:
        resolved = shutil.which(command_name, path=search_path)
        if resolved is None:
            candidates.append(
                {
                    "available": False,
                    "command": command_name,
                    "help_probe": "NOT_RUN",
                    "version_probe": "NOT_RUN",
                }
            )
            continue
        executable = Path(resolved).resolve(strict=True)
        executable_sha256, executable_size = _hash_file(executable)
        version = _probe_invocation(
            executable,
            command_name,
            "--version",
            output,
            timeout_seconds=timeout_seconds,
        )
        help_record = _probe_invocation(
            executable,
            command_name,
            "--help",
            output,
            timeout_seconds=timeout_seconds,
        )
        candidates.append(
            {
                "available": True,
                "command": command_name,
                "executable_sha256": executable_sha256,
                "executable_size_bytes": executable_size,
                "help_probe": help_record,
                "path_disclosure": "OMITTED_FROM_VERSIONED_EVIDENCE",
                "version_probe": version,
            }
        )
        if selected is None:
            selected = (command_name, executable)

    found = selected is not None
    selected_record = next((item for item in candidates if item["available"]), None)
    version_captured = bool(
        selected_record
        and isinstance(selected_record["version_probe"], Mapping)
        and selected_record["version_probe"].get("status") == "CAPTURED"
        and selected_record["version_probe"].get("exit_code") == 0
    )
    invocation_evidence = (
        [
            selected_record["version_probe"]["stdout_artifact"],
            selected_record["version_probe"]["stderr_artifact"],
            selected_record["help_probe"]["stdout_artifact"],
            selected_record["help_probe"]["stderr_artifact"],
        ]
        if selected_record
        else []
    )
    scientific_limitation = (
        "A local command was found, but no non-interactive scientific input/output contract "
        "was demonstrated by this identity-only probe."
        if found
        else "No local Gwyddion command was discoverable, so the capability was not tested."
    )
    questions = [
        _question(
            "Q1_OPEN_INPUT_NONINTERACTIVE",
            "Can Gwyddion open the selected scientific format without human interaction?",
            "NOT_DEMONSTRATED",
            blocking=True,
            limitation=scientific_limitation,
        ),
        _question(
            "Q2_COMPUTE_SA_SQ_SZ",
            "Can Gwyddion compute Sa, Sq and Sz or governed equivalents?",
            "NOT_DEMONSTRATED",
            blocking=True,
            limitation=scientific_limitation,
        ),
        _question(
            "Q3_STRUCTURED_DETERMINISTIC_OUTPUT",
            "Can Gwyddion emit the values through structured deterministic output?",
            "NOT_DEMONSTRATED",
            blocking=True,
            limitation=scientific_limitation,
        ),
        _question(
            "Q4_EXPLICIT_PREPROCESSING",
            "Can preprocessing be fixed explicitly and recorded?",
            "NOT_DEMONSTRATED",
            blocking=True,
            limitation=scientific_limitation,
        ),
        _question(
            "Q5_EXACT_VERSION",
            "Can the exact Gwyddion version be recorded?",
            "DEMONSTRATED" if version_captured else "NOT_DEMONSTRATED",
            blocking=True,
            evidence=invocation_evidence[:2] if version_captured else (),
            limitation=(
                "Raw version stdout and stderr were preserved without interpreting them."
                if version_captured
                else "No successful local version invocation was available."
            ),
        ),
        _question(
            "Q6_OFFLINE_EXECUTION",
            "Can the scientific reference execute offline?",
            "NOT_DEMONSTRATED",
            blocking=False,
            limitation="No scientific reference invocation was performed.",
        ),
        _question(
            "Q7_SEPARATE_STREAMS_AND_EXIT_CODE",
            "Can stdout, stderr and exit code be preserved separately?",
            "DEMONSTRATED" if found else "NOT_DEMONSTRATED",
            blocking=False,
            evidence=invocation_evidence if found else (),
            limitation=(
                "Identity/help invocations only; this does not establish a scientific contract."
                if found
                else "No executable was available to invoke."
            ),
        ),
        _question(
            "Q8_NO_SPMKIT_SUT_IMPORT",
            "Can the probe avoid importing the SPM-Kit SUT?",
            "DEMONSTRATED",
            blocking=False,
            evidence=["probe-source-import-contract"],
            limitation="The validation harness is used; the SPM-Kit SUT package is not imported.",
        ),
    ]
    blocking_ids = [
        item["id"]
        for item in questions[:5]
        if item["result"] != "DEMONSTRATED"
    ]
    status = BLOCKED_STATUS if blocking_ids else "VIABLE_IDENTITY_ONLY"
    identity = {
        "candidate_commands": [item["command"] for item in candidates],
        "executable_sha256": (
            selected_record.get("executable_sha256") if selected_record else None
        ),
        "executable_size_bytes": (
            selected_record.get("executable_size_bytes") if selected_record else None
        ),
        "identity_status": "IDENTITY_CAPTURED" if found else "NOT_FOUND",
        "producer_is_third_party": None,
        "producer_name": "Gwyddion",
        "producer_organization": "NOT_VERIFIED",
        "reported_version": "PRESERVED_RAW" if version_captured else None,
        "selected_command": selected[0] if selected else None,
        "version_evidence": invocation_evidence[:2] if version_captured else [],
    }
    probe = {
        "authoritative_campaign_started": False,
        "authoritative_gwyddion_runs": 0,
        "blocking_question_ids": blocking_ids,
        "candidate_inventory": candidates,
        "gwyddion_identity": identity,
        "holdout_accessed": False,
        "network_accessed": False,
        "observed_at": observed_at,
        "phase": "PHASE_01E",
        "probe_scope": "VIABILITY_ONLY_NON_AUTHORITATIVE",
        "probe_version": PROBE_VERSION,
        "questions": questions,
        "real_data_accessed": False,
        "reference_values_observed": False,
        "spmkit_sut_imported": False,
        "status": status,
        "tolerances_derived": False,
    }
    blocker = {
        "authoritative_campaign_started": False,
        "blocker_code": BLOCKED_STATUS,
        "blocking_question_ids": blocking_ids,
        "claims_promoted": [],
        "gwyddion_runs": 0,
        "holdout_accessed": False,
        "level_3_claimed": False,
        "reason": (
            "No local Gwyddion executable or public related command was found; therefore "
            "non-interactive input, roughness calculation, structured output, preprocessing "
            "control and exact version identity cannot all be demonstrated."
            if not found
            else (
                "The local identity probe did not establish all mandatory scientific "
                "contract checks."
            )
        ),
        "real_data_accessed": False,
        "required_before_unblock": [
            "A real local Gwyddion executable with exact version identity.",
            "A public non-interactive input and preprocessing contract.",
            "Structured deterministic Sa, Sq and Sz output.",
        ],
        "spmkit_runs": 0,
        "status": BLOCKED_STATUS,
    }
    _write_json(output / "viability-probe.json", probe)
    _write_json(output / "gwyddion-identity.json", identity)
    if status == BLOCKED_STATUS:
        _write_json(output / "blocker.json", blocker)
    return probe


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--observed-at", default=DEFAULT_OBSERVED_AT)
    parser.add_argument("--timeout-seconds", default=10.0, type=float)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    probe = run_viability_probe(
        args.output_dir,
        observed_at=args.observed_at,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json_output:
        print(
            json.dumps(
                {
                    "blocking_question_ids": probe["blocking_question_ids"],
                    "operation": "gwyddion.viability-probe",
                    "output_dir": args.output_dir.as_posix(),
                    "status": probe["status"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(probe["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
