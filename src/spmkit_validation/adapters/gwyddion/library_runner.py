"""Sequential subprocess runner for the frozen Gwyddion-library helper."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import os
import platform
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import canonical_bundle_bytes

from .format import (
    GwyddionReferenceOutputError,
    strict_json_object,
    validate_reference_output,
)


@dataclass(frozen=True, slots=True)
class GwyddionLibraryExecutionResult:
    """Six preserved external-reference subprocess records and observations."""

    output_dir: Path
    helper_sha256: str
    started_at: str
    completed_at: str
    runs: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]
    observations: Mapping[str, Mapping[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "helper_sha256": self.helper_sha256,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "runs": [dict(item) for item in self.runs],
            "observations": {
                case_id: dict(values) for case_id, values in self.observations.items()
            },
        }


class GwyddionLibraryExecutionError(ValueError):
    """Raised before subprocess execution when frozen identity is not satisfied."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _regular(path: str | Path, label: str) -> Path:
    resolved = Path(path).resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise GwyddionLibraryExecutionError(f"{label} must be a regular file")
    return resolved


def _directory(path: str | Path, label: str) -> Path:
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_dir():
        raise GwyddionLibraryExecutionError(f"{label} must be a directory")
    return resolved


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _relative(path: Path, root: Path) -> str:
    return path.resolve(strict=True).relative_to(root).as_posix()


def _artifact(
    path: Path,
    root: Path,
    *,
    artifact_id: str,
    artifact_type: str,
    media_type: str,
    created_at: str,
    role: str,
    run_id: str | None = None,
    sources: list[str] | None = None,
    external_schema: dict[str, str] | None = None,
    producer: str = "spmkit-validation",
    producer_version: str | None = None,
) -> dict[str, Any]:
    digest, size = _hash(path)
    effective_version = producer_version or importlib.metadata.version("spmkit-validation")
    producer_record: dict[str, Any] = {"name": producer, "version": effective_version}
    if run_id:
        producer_record["run_id"] = run_id
    artifact = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "media_type": media_type,
        "relative_uri": _relative(path, root),
        "sha256": digest,
        "size_bytes": size,
        "created_at": created_at,
        "producer": producer_record,
        "regenerable": True,
        "generation_command": ["spmkit-gwyddion-roughness-reference"],
        "source_artifact_ids": sources or [],
        "scientific_role": role,
        "contains_sensitive_data": False,
        "limitations": [
            "Synthetic external-reference artifact; no signature or authenticity is asserted."
        ],
    }
    if external_schema is not None:
        artifact["external_schema"] = external_schema
    return artifact


def execute_gwyddion_library_reference(
    protocol: Mapping[str, Any],
    *,
    artifact_root: str | Path,
    helper_executable: str | Path,
    gwyddion_library_dir: str | Path,
    gwyddion_module_dir: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = 60.0,
) -> GwyddionLibraryExecutionResult:
    """Run six fixed full-field helper invocations and preserve all failure states."""

    root = Path(artifact_root).resolve(strict=True)
    helper = _regular(helper_executable, "helper_executable")
    library_dir = _directory(gwyddion_library_dir, "gwyddion_library_dir")
    module_dir = _directory(gwyddion_module_dir, "gwyddion_module_dir")
    evidence_by_id = {item["artifact_id"]: item for item in protocol["evidence"]}
    frozen_helper = evidence_by_id.get("artifact.reference.helper-binary")
    helper_sha256, helper_size = _hash(helper)
    if not frozen_helper or (
        frozen_helper["sha256"] != helper_sha256
        or frozen_helper["size_bytes"] != helper_size
    ):
        raise GwyddionLibraryExecutionError("helper executable differs from frozen identity")
    expected_version = next(
        item["version"]
        for item in protocol["references"]
        if item["reference_id"] == "reference.external.gwyddion-library.roughness"
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve(strict=True)
    output.relative_to(root)
    started_at = _now()
    environment = {
        "PATH": f"{helper.parent}:/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(library_dir),
        "NO_PROXY": "*",
        "no_proxy": "*",
        "G_DEBUG": "fatal-criticals",
    }
    identity_document = {
        "display_environment_present": False,
        "gwyddion_version_expected": expected_version,
        "helper_sha256": helper_sha256,
        "helper_size_bytes": helper_size,
        "library_directory_disclosure": "OMITTED_FROM_VERSIONED_EVIDENCE",
        "locale": "C",
        "module_directory_disclosure": "OMITTED_FROM_VERSIONED_EVIDENCE",
        "network_policy": "OFFLINE",
        "preprocessing": {
            "filtering": "NONE",
            "leveling": "NONE",
            "masking": "NONE",
            "roi": "FULL_FIELD",
        },
    }
    identity_path = output / "gwyddion-environment.json"
    _write(identity_path, canonical_bundle_bytes(identity_document))
    identity_id = "artifact.execution.gwyddion-environment"
    evidence: list[dict[str, Any]] = [
        _artifact(
            identity_path,
            root,
            artifact_id=identity_id,
            artifact_type="ENVIRONMENT_SNAPSHOT",
            media_type="application/json",
            created_at=started_at,
            role="PROVENANCE",
            sources=["artifact.reference.helper-binary", "artifact.reference.gwyddion-identity"],
        )
    ]
    datasets = {item["dataset_id"]: item for item in protocol["datasets"]}
    runs: list[dict[str, Any]] = []
    observations: dict[str, Mapping[str, float]] = {}
    cases = [
        item
        for item in protocol["cases"]
        if item["reference_id"] == "reference.external.gwyddion-library.roughness"
    ]
    for case in cases:
        case_id = case["case_id"]
        dataset = datasets[case["dataset_id"]]
        input_id = next(
            item
            for item in dataset["provenance"]["source_artifact_ids"]
            if evidence_by_id[item]["artifact_type"] == "INPUT"
        )
        input_artifact = evidence_by_id[input_id]
        input_path = root / input_artifact["relative_uri"]
        run_id = f"run.gwyddion.{case_id}"
        run_started = _now()
        case_output = output / "raw" / case_id
        case_output.mkdir(parents=True, exist_ok=False)
        recorded_command = [
            "spmkit-gwyddion-roughness-reference",
            "--channel",
            "0",
            "--module-dir",
            "GWYDDION_MODULE_DIR",
            "--unit-z",
            "m",
            dataset["locator"],
        ]
        actual_command = [
            str(helper),
            "--channel",
            "0",
            "--module-dir",
            str(module_dir),
            "--unit-z",
            "m",
            str(input_path),
        ]
        stdout = b""
        stderr = b""
        exit_code: int | None = None
        errors: list[dict[str, str]] = []
        try:
            completed = subprocess.run(
                actual_command,
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
                env=environment,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
            if exit_code != 0:
                errors.append(
                    {
                        "code": "GWYDDION_NONZERO_EXIT",
                        "message": f"reference helper exited with code {exit_code}",
                    }
                )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
            errors.append(
                {
                    "code": "GWYDDION_TIMEOUT",
                    "message": f"reference helper exceeded {timeout_seconds} seconds",
                }
            )
        stdout_path = case_output / "gwyddion-stdout.txt"
        stderr_path = case_output / "gwyddion-stderr.txt"
        _write(stdout_path, stdout)
        _write(stderr_path, stderr)
        stdout_id = f"artifact.gwyddion-stdout.{case_id}"
        stderr_id = f"artifact.gwyddion-stderr.{case_id}"
        output_ids = [stdout_id, stderr_id]
        for path, artifact_id in ((stdout_path, stdout_id), (stderr_path, stderr_id)):
            evidence.append(
                _artifact(
                    path,
                    root,
                    artifact_id=artifact_id,
                    artifact_type="LOG",
                    media_type="text/plain",
                    created_at=run_started,
                    role="DIAGNOSTIC",
                    run_id=run_id,
                    sources=[input_id, "artifact.reference.helper-binary"],
                )
            )
        result_document: dict[str, Any] | None = None
        if not errors:
            try:
                result_document = validate_reference_output(
                    strict_json_object(stdout),
                    input_sha256=input_artifact["sha256"],
                    shape=tuple(dataset["public_metadata"]["shape"]),
                    unit_z="m",
                    channel=0,
                    expected_gwyddion_version=expected_version,
                )
                observations[case_id] = {
                    name: float(result_document[name]) for name in ("Sa", "Sq", "Sz")
                }
            except GwyddionReferenceOutputError as exc:
                errors.append({"code": "GWYDDION_MALFORMED_OUTPUT", "message": str(exc)})
        result_path = case_output / "gwyddion-output.json"
        if result_document is not None:
            _write(result_path, canonical_bundle_bytes(result_document))
            result_id = f"artifact.gwyddion-output.{case_id}"
            evidence.append(
                _artifact(
                    result_path,
                    root,
                    artifact_id=result_id,
                    artifact_type="OUTPUT",
                    media_type="application/json",
                    created_at=run_started,
                    role="QUANTITATIVE_RESULT",
                    run_id=run_id,
                    sources=[input_id, "artifact.reference.helper-binary"],
                    producer="Gwyddion libraries",
                    producer_version=expected_version,
                )
            )
            output_ids.append(result_id)
        run_finished = _now()
        run_document = {
            "command": recorded_command,
            "errors": errors,
            "exit_code": exit_code,
            "finished_at": run_finished,
            "gwyddion_version": (
                result_document.get("gwyddion_version") if result_document else None
            ),
            "helper_sha256": helper_sha256,
            "input_sha256": input_artifact["sha256"],
            "preprocessing": identity_document["preprocessing"],
            "run_id": run_id,
            "started_at": run_started,
            "status": "ERROR" if errors else "COMPLETED",
        }
        run_path = case_output / "gwyddion-run.json"
        _write(run_path, canonical_bundle_bytes(run_document))
        manifest_id = f"artifact.gwyddion-run.{case_id}"
        evidence.append(
            _artifact(
                run_path,
                root,
                artifact_id=manifest_id,
                artifact_type="MANIFEST",
                media_type="application/json",
                created_at=run_started,
                role="PROVENANCE",
                run_id=run_id,
                sources=[input_id, "artifact.reference.helper-binary"],
                external_schema={
                    "name": "spmkit-validation.gwyddion-library-run",
                    "version": "0.1.0",
                },
            )
        )
        output_ids.append(manifest_id)
        runs.append(
            {
                "run_id": run_id,
                "campaign_id": protocol["campaign"]["campaign_id"],
                "case_ids": [case_id],
                "run_type": "VALIDATION",
                "started_at": run_started,
                "finished_at": run_finished,
                "command": recorded_command,
                "parameters": {
                    "channel": 0,
                    "exit_code": exit_code,
                    "filtering": "none",
                    "leveling": "none",
                    "locale": "C",
                    "masking": "none",
                    "output_contract": "strict-json-v0.1.0",
                    "roi": "full-field",
                },
                "seed": None,
                "environment": {
                    "environment_id": "environment.phase01e.gwyddion-library",
                    "platform": platform.system().lower(),
                    "operating_system": platform.system(),
                    "architecture": platform.machine(),
                    "python_version": "NOT_USED_NATIVE_C_PROCESS",
                    "snapshot_artifact_id": identity_id,
                },
                "input_artifact_ids": [input_id, "artifact.reference.helper-binary"],
                "output_artifact_ids": output_ids,
                "run_manifest_artifact_id": manifest_id,
                "execution_status": "ERROR" if errors else "COMPLETED",
                "errors": errors,
                "warnings": [],
            }
        )
    completed_at = _now()
    return GwyddionLibraryExecutionResult(
        output_dir=output,
        helper_sha256=helper_sha256,
        started_at=started_at,
        completed_at=completed_at,
        runs=tuple(copy.deepcopy(runs)),
        evidence=tuple(sorted(evidence, key=lambda item: item["artifact_id"])),
        observations=copy.deepcopy(observations),
    )
