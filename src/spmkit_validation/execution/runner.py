"""Sequential black-box execution of an already verified frozen protocol."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import (
    LifecycleError,
    canonical_bundle_bytes,
    verify_frozen_snapshot,
)
from spmkit_validation.schemas import load_validation_bundle

from .ground_truth import MEASURANDS
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)


@dataclass(frozen=True, slots=True)
class CampaignExecutionResult:
    """Preserved records and artifacts from six sequential SUT invocations."""

    campaign_id: str
    output_dir: Path
    wheel_sha256: str
    wheel_size_bytes: int
    started_at: str
    completed_at: str
    runs: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]
    observations: Mapping[str, Mapping[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "wheel_sha256": self.wheel_sha256,
            "wheel_size_bytes": self.wheel_size_bytes,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "runs": [dict(run) for run in self.runs],
            "observations": {
                case_id: dict(values) for case_id, values in self.observations.items()
            },
        }


@dataclass(frozen=True, slots=True)
class InstalledSUTEnvironment:
    """One clean installed-wheel environment reusable by governed subprocesses."""

    executable: Path
    python_executable: Path
    wheel_sha256: str
    wheel_size_bytes: int
    installation: str
    installed_dependencies: tuple[str, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _safe_regular_file(path: Path, code: str, json_path: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    code,
                    json_path,
                    str(exc),
                )
            ]
        ) from exc
    if not stat.S_ISREG(mode):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    code,
                    json_path,
                    "path must resolve to a regular file",
                )
            ]
        )
    return resolved


def _strict_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON key {key!r}")
            document[key] = value
        return document

    try:
        value = json.loads(
            path.read_bytes(),
            parse_constant=reject_constant,
            object_pairs_hook=unique_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.OUTPUT,
                    "SUT.INVALID_MACHINE_JSON",
                    "/output",
                    str(exc),
                )
            ]
        ) from exc
    if not isinstance(value, dict):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.OUTPUT,
                    "SUT.INVALID_MACHINE_JSON",
                    "/output",
                    "machine-readable SUT output must be a JSON object",
                )
            ]
        )
    return value


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "EXECUTION.OUTPUT_ESCAPES_ARTIFACT_ROOT",
                    "/output_dir",
                    "execution output must remain below artifact_root",
                )
            ]
        ) from exc


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
    regenerable: bool = True,
    generation_command: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    digest, size = _hash_file(path)
    producer: dict[str, Any] = {"name": "spmkit-validation", "version": "0.1.3"}
    if run_id is not None:
        producer["run_id"] = run_id
    document: dict[str, Any] = {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "media_type": media_type,
        "relative_uri": _relative(path, root),
        "sha256": digest,
        "size_bytes": size,
        "created_at": created_at,
        "producer": producer,
        "regenerable": regenerable,
        "generation_command": generation_command
        if generation_command is not None
        else ["spmkit", "analyze"],
        "source_artifact_ids": sources or [],
        "scientific_role": role,
        "contains_sensitive_data": False,
        "limitations": limitations
        if limitations is not None
        else ["Black-box synthetic execution artifact; no producer authenticity is asserted."],
    }
    if external_schema is not None:
        document["external_schema"] = external_schema
    return document


def _validate_protocol_before_subprocess(
    protocol_bundle_path: Path,
    freeze_receipt_path: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    try:
        verification = verify_frozen_snapshot(
            protocol_bundle_path, freeze_receipt_path, artifact_root=artifact_root
        )
    except LifecycleError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "EXECUTION.PROTOCOL_NOT_VERIFIED",
                    "",
                    "; ".join(issue.description for issue in exc.issues),
                )
            ]
        ) from exc
    if verification.status != "SNAPSHOT_VALID" or verification.artifact_status != "PASS":
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "EXECUTION.PROTOCOL_NOT_VERIFIED",
                    "",
                    (
                        f"protocol verification is {verification.status}/"
                        f"{verification.artifact_status}"
                    ),
                )
            ]
        )
    bundle = load_validation_bundle(protocol_bundle_path)
    if bundle.get("campaign", {}).get("status") != "FROZEN":
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "EXECUTION.PROTOCOL_NOT_FROZEN",
                    "/campaign/status",
                    "campaign execution requires a verified FROZEN snapshot",
                )
            ]
        )
    return bundle


def install_sut_wheel_environment(
    wheel: Path,
    output_dir: Path,
    sut_version: str,
    *,
    test_dependencies: Sequence[str] = (),
) -> InstalledSUTEnvironment:
    """Install one declared wheel and exact test dependencies into Python 3.12."""

    wheel = _safe_regular_file(wheel, "EXECUTION.INVALID_WHEEL", "/sut_wheel")
    wheel_sha256, wheel_size = _hash_file(wheel)
    uv = shutil.which("uv")
    if uv is None:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "EXECUTION.UV_NOT_FOUND",
                    "",
                    "uv is required to create the clean Python 3.12 SUT environment",
                )
            ]
        )
    venv = output_dir / "sut-venv"
    create = subprocess.run(
        [uv, "venv", "--python", "3.12", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "EXECUTION.VENV_FAILED",
                    "",
                    create.stderr.strip() or "uv venv failed",
                )
            ]
        )
    install = subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--offline",
            "--python",
            str(venv / "bin" / "python"),
            str(wheel),
            *test_dependencies,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "EXECUTION.WHEEL_INSTALL_FAILED",
                    "",
                    install.stderr.strip() or "offline wheel install failed",
                )
            ]
        )
    executable = _safe_regular_file(
        venv / "bin" / "spmkit", "EXECUTION.SPMKIT_NOT_INSTALLED", "/sut_wheel"
    )
    installed = subprocess.run(
        [uv, "pip", "freeze", "--python", str(venv / "bin" / "python")],
        check=False,
        capture_output=True,
        text=True,
    )
    if installed.returncode != 0:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "EXECUTION.DEPENDENCY_CAPTURE_FAILED",
                    "",
                    installed.stderr.strip() or "uv pip freeze failed",
                )
            ]
        )
    dependencies = []
    for line in installed.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        name = value.partition(" @ ")[0]
        dependencies.append(f"spmkit=={sut_version}" if name == "spmkit" else value)
    python_executable = venv / "bin" / "python"
    _safe_regular_file(
        python_executable, "EXECUTION.PYTHON_NOT_INSTALLED", "/sut_wheel"
    )
    return InstalledSUTEnvironment(
        executable=executable,
        # Keep the venv entry path: resolving this symlink selects the base interpreter
        # and silently drops the venv's site-packages from isolated import probes.
        python_executable=python_executable.absolute(),
        wheel_sha256=wheel_sha256,
        wheel_size_bytes=wheel_size,
        installation="wheel-clean-venv",
        installed_dependencies=tuple(sorted(dependencies)),
    )


def _prepare_sut_environment(
    wheel: Path,
    output_dir: Path,
    override: str | Path | None,
    sut_version: str,
) -> InstalledSUTEnvironment:
    wheel_sha256, wheel_size = _hash_file(wheel)
    if override is not None:
        executable = _safe_regular_file(
            Path(override), "EXECUTION.INVALID_SUT_EXECUTABLE", "/sut_executable"
        )
        return InstalledSUTEnvironment(
            executable=executable,
            python_executable=Path(sys.executable).resolve(strict=True),
            wheel_sha256=wheel_sha256,
            wheel_size_bytes=wheel_size,
            installation="test-override",
            installed_dependencies=("fake-executable-test-override",),
        )
    return install_sut_wheel_environment(wheel, output_dir, sut_version)


def _scientific_environment(executable: Path) -> dict[str, str]:
    return {
        "PATH": str(executable.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "*",
        "no_proxy": "*",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _copy_exclusive(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("xb") as target_handle:
        while chunk := source_handle.read(1024 * 1024):
            target_handle.write(chunk)
        target_handle.flush()
        os.fsync(target_handle.fileno())


def _output_values(document: Mapping[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for measurand in MEASURANDS:
        value = document.get(measurand)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise CampaignExecutionError(
                [
                    execution_issue(
                        CampaignExecutionIssueCategory.OUTPUT,
                        "SUT.MEASURAND_MISSING",
                        f"/{measurand}",
                        "official output must contain a finite numeric measurand",
                    )
                ]
            )
        parsed = float(value)
        if not math.isfinite(parsed):
            raise CampaignExecutionError(
                [
                    execution_issue(
                        CampaignExecutionIssueCategory.OUTPUT,
                        "SUT.MEASURAND_NONFINITE",
                        f"/{measurand}",
                        "official output measurand must be finite",
                    )
                ]
            )
        values[measurand] = parsed
    if document.get("unit") != "m":
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.OUTPUT,
                    "SUT.UNIT_MISMATCH",
                    "/unit",
                    "official output must preserve the predeclared metre unit",
                )
            ]
        )
    return values


def execute_frozen_campaign(
    protocol_bundle_path: str | Path,
    freeze_receipt_path: str | Path,
    *,
    artifact_root: str | Path,
    sut_wheel: str | Path,
    output_dir: str | Path,
    sut_executable: str | Path | None = None,
    installed_environment: InstalledSUTEnvironment | None = None,
    timeout_seconds: float = 60.0,
) -> CampaignExecutionResult:
    """Verify-before-run, then execute exactly six protocol cases sequentially."""

    root = Path(artifact_root).resolve(strict=True)
    protocol = _validate_protocol_before_subprocess(
        Path(protocol_bundle_path), Path(freeze_receipt_path), root
    )
    wheel = _safe_regular_file(Path(sut_wheel), "EXECUTION.INVALID_WHEEL", "/sut_wheel")
    wheel_sha256, wheel_size = _hash_file(wheel)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    output_resolved = output.resolve(strict=True)
    try:
        output_resolved.relative_to(root)
    except ValueError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "EXECUTION.OUTPUT_ESCAPES_ARTIFACT_ROOT",
                    "/output_dir",
                    "execution output must be created below artifact_root",
                )
            ]
        ) from exc

    sut_version = protocol["campaign"]["system_under_test"]["version"]
    if installed_environment is not None and sut_executable is not None:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "EXECUTION.AMBIGUOUS_ENVIRONMENT",
                    "/installed_environment",
                    "installed_environment and sut_executable cannot both be supplied",
                )
            ]
        )
    sut_environment = installed_environment or _prepare_sut_environment(
        wheel, output_resolved, sut_executable, sut_version
    )
    if (
        sut_environment.wheel_sha256 != wheel_sha256
        or sut_environment.wheel_size_bytes != wheel_size
    ):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "EXECUTION.WHEEL_IDENTITY_MISMATCH",
                    "/sut_wheel",
                    "installed environment does not match the declared wheel bytes",
                )
            ]
        )
    executable = _safe_regular_file(
        sut_environment.executable,
        "EXECUTION.SPMKIT_NOT_INSTALLED",
        "/installed_environment/executable",
    )
    environment = _scientific_environment(executable)
    help_result = subprocess.run(
        [str(executable), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    if help_result.returncode != 0 or "analyze" not in help_result.stdout:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "EXECUTION.PUBLIC_CLI_UNAVAILABLE",
                    "",
                    "installed wheel does not expose the required analyze command",
                )
            ]
        )

    started_at = _now()
    wheel_copy = output_resolved / "sut-wheel.whl"
    _copy_exclusive(wheel, wheel_copy)
    environment_document = {
        "environment_version": "0.1.0",
        "python_requirement": "3.12",
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "locale": "C.UTF-8",
        "network_policy": "OFFLINE",
        "installation": sut_environment.installation,
        "wheel_sha256": wheel_sha256,
        "wheel_size_bytes": wheel_size,
        "sut_package_version": sut_version,
        "sut_commit": protocol["campaign"]["system_under_test"]["git_commit"],
        "command_contract": ["spmkit", "analyze", "--channel", "Z-Axis", "--level", "none"],
        "installed_dependencies": list(sut_environment.installed_dependencies),
    }
    environment_path = output_resolved / "environment.json"
    _write_exclusive(environment_path, canonical_bundle_bytes(environment_document))
    help_path = output_resolved / "spmkit-help.txt"
    _write_exclusive(help_path, help_result.stdout.encode("utf-8"))
    evidence: list[dict[str, Any]] = [
        _artifact(
            wheel_copy,
            root,
            artifact_id="artifact.execution.sut-wheel",
            artifact_type="INPUT",
            media_type="application/octet-stream",
            created_at=started_at,
            role="PROVENANCE",
            regenerable=False,
            generation_command=[],
        ),
        _artifact(
            environment_path,
            root,
            artifact_id="artifact.execution.environment",
            artifact_type="ENVIRONMENT_SNAPSHOT",
            media_type="application/json",
            created_at=started_at,
            role="PROVENANCE",
            sources=["artifact.execution.sut-wheel"],
            generation_command=["spmkit-validation", "campaign", "execute"],
        ),
        _artifact(
            help_path,
            root,
            artifact_id="artifact.execution.public-cli-help",
            artifact_type="LOG",
            media_type="text/plain",
            created_at=started_at,
            role="PROVENANCE",
            sources=["artifact.execution.sut-wheel"],
            generation_command=["spmkit", "--help"],
        ),
    ]
    input_artifacts = {
        artifact["artifact_id"]: artifact for artifact in protocol["evidence"]
    }
    datasets = {dataset["dataset_id"]: dataset for dataset in protocol["datasets"]}
    runs: list[dict[str, Any]] = []
    observations: dict[str, Mapping[str, float]] = {}
    scientific_cases = [
        case for case in protocol["cases"] if case["operation"]["name"] == "spmkit analyze"
    ]
    for case in scientific_cases:
        case_id = case["case_id"]
        dataset = datasets[case["dataset_id"]]
        input_id = next(
            artifact_id
            for artifact_id in dataset["provenance"]["source_artifact_ids"]
            if input_artifacts[artifact_id]["artifact_type"] == "INPUT"
        )
        locator = dataset["locator"]
        run_id = f"run.{case_id}"
        run_started = _now()
        case_output = output_resolved / "raw" / case_id
        case_output.mkdir(parents=True, exist_ok=False)
        recorded_command = [
            "spmkit",
            "analyze",
            locator,
            "--output",
            _relative(case_output, root),
            "--channel",
            "Z-Axis",
            "--level",
            "none",
        ]
        actual_command = [str(executable), *recorded_command[1:]]
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        exit_code: int | None = None
        stdout = ""
        stderr = ""
        try:
            completed = subprocess.run(
                actual_command,
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            if exit_code != 0:
                errors.append(
                    {
                        "code": "SUT_NONZERO_EXIT",
                        "message": f"spmkit exited with code {exit_code}",
                    }
                )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            errors.append(
                {
                    "code": "SUT_TIMEOUT",
                    "message": f"spmkit exceeded timeout {timeout_seconds} seconds",
                }
            )
        stdout_path = case_output / "stdout.txt"
        stderr_path = case_output / "stderr.txt"
        _write_exclusive(stdout_path, stdout.encode("utf-8"))
        _write_exclusive(stderr_path, stderr.encode("utf-8"))
        output_ids: list[str] = []
        stdout_id = f"artifact.stdout.{case_id}"
        stderr_id = f"artifact.stderr.{case_id}"
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
                    sources=[input_id],
                )
            )
            output_ids.append(artifact_id)

        stem = Path(locator).stem
        result_path = case_output / f"{stem}_roughness.json"
        csv_path = case_output / f"{stem}_roughness.csv"
        manifest_path = case_output / f"{stem}_run_manifest.json"
        if not errors:
            try:
                result_document = _strict_json(result_path)
                observations[case_id] = _output_values(result_document)
                _strict_json(manifest_path)
                if not csv_path.is_file():
                    raise CampaignExecutionError(
                        [
                            execution_issue(
                                CampaignExecutionIssueCategory.OUTPUT,
                                "SUT.MISSING_PUBLIC_OUTPUT",
                                "/output",
                                "documented roughness CSV was not produced",
                            )
                        ]
                    )
            except CampaignExecutionError as exc:
                errors.extend(
                    {"code": issue.code.replace(".", "_"), "message": issue.description}
                    for issue in exc.issues
                )

        manifest_id = f"artifact.run-manifest.{case_id}"
        if errors and not manifest_path.is_file():
            error_manifest = {
                "manifest_version": "0.1.0",
                "run_id": run_id,
                "status": "ERROR",
                "errors": errors,
                "exit_code": exit_code,
            }
            manifest_path = case_output / "harness-error-manifest.json"
            _write_exclusive(manifest_path, canonical_bundle_bytes(error_manifest))
            manifest_schema = {
                "name": "spmkit-validation.execution-error-manifest",
                "version": "0.1.0",
            }
        else:
            manifest_schema = {
                "name": "spmkit.core.export.RunManifest",
                "version": "1.0",
            }
        evidence.append(
            _artifact(
                manifest_path,
                root,
                artifact_id=manifest_id,
                artifact_type="MANIFEST",
                media_type="application/json",
                created_at=run_started,
                role="PROVENANCE",
                run_id=run_id,
                sources=[input_id],
                external_schema=manifest_schema,
            )
        )
        output_ids.append(manifest_id)
        if result_path.is_file():
            result_id = f"artifact.result-json.{case_id}"
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
                    sources=[input_id],
                )
            )
            output_ids.append(result_id)
        if csv_path.is_file():
            csv_id = f"artifact.result-csv.{case_id}"
            evidence.append(
                _artifact(
                    csv_path,
                    root,
                    artifact_id=csv_id,
                    artifact_type="TABLE",
                    media_type="text/csv",
                    created_at=run_started,
                    role="QUANTITATIVE_RESULT",
                    run_id=run_id,
                    sources=[input_id],
                )
            )
            output_ids.append(csv_id)
        run_finished = _now()
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
                    "channel": "Z-Axis",
                    "level": "none",
                    "output_contract": "roughness-json",
                    "exit_code": exit_code,
                },
                "seed": None,
                "environment": {
                    "environment_id": protocol["campaign"]["system_under_test"][
                        "environment_id"
                    ],
                    "platform": platform.system().lower(),
                    "operating_system": platform.system(),
                    "architecture": platform.machine(),
                    "python_version": "3.12",
                    "snapshot_artifact_id": "artifact.execution.environment",
                },
                "input_artifact_ids": [input_id],
                "output_artifact_ids": output_ids,
                "run_manifest_artifact_id": manifest_id,
                "execution_status": "ERROR" if errors else "COMPLETED",
                "errors": errors,
                "warnings": warnings,
            }
        )
    completed_at = _now()
    return CampaignExecutionResult(
        campaign_id=protocol["campaign"]["campaign_id"],
        output_dir=output_resolved,
        wheel_sha256=wheel_sha256,
        wheel_size_bytes=wheel_size,
        started_at=started_at,
        completed_at=completed_at,
        runs=tuple(runs),
        evidence=tuple(sorted(evidence, key=lambda item: item["artifact_id"])),
        observations=observations,
    )
