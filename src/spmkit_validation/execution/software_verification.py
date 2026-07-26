"""Strict installed-wheel SOFTWARE_TEST execution and JUnit evidence."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from spmkit_validation.lifecycle import canonical_bundle_bytes

from .cumulative_protocol import (
    PYTEST_ENTRYPOINT_ID,
    SOFTWARE_CASE_ID,
    SOFTWARE_TEST_RUN_ID,
    SUITE_ARCHIVE_ID,
    SUITE_MANIFEST_ID,
    WHEEL_POLICY_ID,
)
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssue,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .runner import (
    InstalledSUTEnvironment,
    _artifact,
    _hash_file,
    _now,
    _safe_regular_file,
    _scientific_environment,
    _strict_json,
    _validate_protocol_before_subprocess,
    _write_exclusive,
)

JUNIT_ARTIFACT_ID = "artifact.software-test.junit"
IMPORT_PROBE_ARTIFACT_ID = "artifact.software-test.import-probe"
CLI_PROBE_ARTIFACT_ID = "artifact.software-test.cli-probe"
SOFTWARE_STDOUT_ARTIFACT_ID = "artifact.software-test.stdout"
SOFTWARE_STDERR_ARTIFACT_ID = "artifact.software-test.stderr"
SOFTWARE_ENVIRONMENT_ARTIFACT_ID = "artifact.software-test.environment"
SOFTWARE_RUN_RECORD_ARTIFACT_ID = "artifact.software-test.run-record"

_IMPORT_PROBE_SCRIPT = r'''import importlib.metadata
import json
import pathlib
import site
import sys

import spmkit

module = pathlib.Path(spmkit.__file__).resolve()
origin = None
for candidate in site.getsitepackages():
    root = pathlib.Path(candidate).resolve()
    try:
        relative = module.relative_to(root)
    except ValueError:
        continue
    origin = "site-packages/" + relative.as_posix()
    break
document = {
    "probe_version": "0.1.0",
    "status": "PASS" if origin is not None else "FAIL",
    "distribution_version": importlib.metadata.version("spmkit"),
    "module_origin": origin,
    "resolved_inside_site_packages": origin is not None,
    "resolved_inside_source_checkout": False,
    "isolated_mode": bool(sys.flags.isolated),
    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
}
print(json.dumps(document, sort_keys=True, separators=(",", ":")))
'''


@dataclass(frozen=True, slots=True)
class JUnitSummary:
    """Counts derived from testcase elements and checked against suite attributes."""

    tests: int
    passed: int
    failures: int
    errors: int
    skips: int

    @property
    def successful(self) -> bool:
        return self.tests > 0 and self.failures == 0 and self.errors == 0

    def to_dict(self) -> dict[str, int]:
        return {
            "tests": self.tests,
            "passed": self.passed,
            "failures": self.failures,
            "errors": self.errors,
            "skips": self.skips,
        }


@dataclass(frozen=True, slots=True)
class SoftwareTestExecutionResult:
    """One governed software run plus exact local evidence declarations."""

    run: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    junit_summary: JUnitSummary | None
    import_probe: Mapping[str, Any]
    cli_probe: Mapping[str, Any]
    started_at: str
    completed_at: str
    wheel_sha256: str
    suite_manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": dict(self.run),
            "junit_summary": (
                self.junit_summary.to_dict() if self.junit_summary is not None else None
            ),
            "import_probe": dict(self.import_probe),
            "cli_probe": dict(self.cli_probe),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "wheel_sha256": self.wheel_sha256,
            "suite_manifest_sha256": self.suite_manifest_sha256,
        }


def _software_issue(code: str, path: str, description: str) -> CampaignExecutionIssue:
    return execution_issue(CampaignExecutionIssueCategory.EXECUTION, code, path, description)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _count_attribute(suite: ElementTree.Element, name: str) -> int:
    value = suite.get(name)
    if value is None or not value.isdigit():
        raise CampaignExecutionError(
            [_software_issue("JUNIT.INVALID_COUNT", f"/@{name}", "count must be an integer")]
        )
    return int(value)


def parse_junit_xml(path: str | Path) -> JUnitSummary:
    """Parse finite JUnit status strictly without reading terminal summaries."""

    junit_path = _safe_regular_file(Path(path), "JUNIT.FILE_INVALID", "/junit")
    raw = junit_path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise CampaignExecutionError(
            [_software_issue("JUNIT.UNSAFE_XML", "/junit", "DOCTYPE and ENTITY are forbidden")]
        )
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise CampaignExecutionError(
            [_software_issue("JUNIT.INVALID_XML", "/junit", str(exc))]
        ) from exc
    root_name = _local_name(root.tag)
    if root_name == "testsuite":
        suites = [root]
    elif root_name == "testsuites":
        suites = [child for child in root if _local_name(child.tag) == "testsuite"]
    else:
        suites = []
    if not suites:
        raise CampaignExecutionError(
            [_software_issue("JUNIT.INVALID_ROOT", "/junit", "expected testsuite(s) root")]
        )

    declared = {
        name: sum(_count_attribute(suite, name) for suite in suites)
        for name in ("tests", "failures", "errors", "skipped")
    }
    testcases = [
        element
        for suite in suites
        for element in suite.iter()
        if _local_name(element.tag) == "testcase"
    ]
    failures = 0
    errors = 0
    skips = 0
    for testcase in testcases:
        statuses = {_local_name(child.tag) for child in testcase}
        present = statuses.intersection({"failure", "error", "skipped"})
        if len(present) > 1:
            raise CampaignExecutionError(
                [
                    _software_issue(
                        "JUNIT.CONTRADICTORY_TESTCASE",
                        "/junit/testcase",
                        "one testcase cannot have multiple terminal states",
                    )
                ]
            )
        failures += "failure" in present
        errors += "error" in present
        skips += "skipped" in present
    derived = {
        "tests": len(testcases),
        "failures": failures,
        "errors": errors,
        "skipped": skips,
    }
    if declared != derived:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "JUNIT.COUNT_MISMATCH",
                    "/junit",
                    f"declared counts {declared!r} differ from testcase counts {derived!r}",
                )
            ]
        )
    passed = derived["tests"] - failures - errors - skips
    return JUnitSummary(derived["tests"], passed, failures, errors, skips)


def validate_import_probe(document: Mapping[str, Any]) -> None:
    """Reject any probe that does not prove an isolated site-packages import."""

    origin = document.get("module_origin")
    valid_origin = (
        isinstance(origin, str)
        and origin.startswith("site-packages/")
        and ".." not in PurePosixPath(origin).parts
        and not PurePosixPath(origin).is_absolute()
    )
    if not (
        document.get("status") == "PASS"
        and document.get("resolved_inside_site_packages") is True
        and document.get("resolved_inside_source_checkout") is False
        and document.get("isolated_mode") is True
        and valid_origin
    ):
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.IMPORT_ORIGIN_INVALID",
                    "/import_probe",
                    "spmkit must resolve from isolated environment site-packages",
                )
            ]
        )


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = _strict_json(path)
    except CampaignExecutionError as exc:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.SUITE_MANIFEST_INVALID",
                    "/software-test-suite-manifest",
                    issue.description,
                )
                for issue in exc.issues
            ]
        ) from exc
    return manifest


def _git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def _extract_exact_suite(
    archive_path: Path,
    workspace: Path,
    manifest: Mapping[str, Any],
) -> None:
    expected = {record["path"]: record for record in manifest.get("files", [])}
    if not expected:
        raise CampaignExecutionError(
            [_software_issue("SOFTWARE_TEST.SUITE_EMPTY", "/files", "suite has no files")]
        )
    with tarfile.open(fileobj=BytesIO(archive_path.read_bytes()), mode="r:") as archive:
        seen: set[str] = set()
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise CampaignExecutionError(
                    [
                        _software_issue(
                            "SOFTWARE_TEST.UNSAFE_ARCHIVE_PATH",
                            "/source_archive",
                            "suite archive path is unsafe",
                        )
                    ]
                )
            if member.isdir():
                continue
            if not member.isfile() or member.name not in expected:
                raise CampaignExecutionError(
                    [
                        _software_issue(
                            "SOFTWARE_TEST.ARCHIVE_CONTENT_MISMATCH",
                            "/source_archive",
                            "suite archive contains undeclared or non-regular content",
                        )
                    ]
                )
            source = archive.extractfile(member)
            if source is None:
                raise CampaignExecutionError(
                    [
                        _software_issue(
                            "SOFTWARE_TEST.ARCHIVE_READ_FAILED",
                            "/source_archive",
                            member.name,
                        )
                    ]
                )
            content = source.read()
            record = expected[member.name]
            if (
                hashlib.sha256(content).hexdigest() != record.get("sha256")
                or len(content) != record.get("size_bytes")
                or _git_blob_id(content) != record.get("git_blob")
            ):
                raise CampaignExecutionError(
                    [
                        _software_issue(
                            "SOFTWARE_TEST.EXPORTED_FILE_MISMATCH",
                            f"/files/{member.name}",
                            "exported file differs from the predeclared Git object",
                        )
                    ]
                )
            destination = workspace.joinpath(*relative.parts)
            _write_exclusive(destination, content)
            seen.add(member.name)
    if seen != set(expected):
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.ARCHIVE_CONTENT_MISMATCH",
                    "/source_archive",
                    "suite archive is missing predeclared files",
                )
            ]
        )


def _probe_import(
    environment: InstalledSUTEnvironment,
    workspace: Path,
    process_environment: Mapping[str, str],
) -> tuple[dict[str, Any], int, str]:
    completed = subprocess.run(
        [str(environment.python_executable), "-I", "-c", _IMPORT_PROBE_SCRIPT],
        cwd=workspace,
        env=dict(process_environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    try:
        document = json.loads(completed.stdout)
        if not isinstance(document, dict):
            raise ValueError("probe root is not an object")
        validate_import_probe(document)
    except (json.JSONDecodeError, ValueError, CampaignExecutionError) as exc:
        document = {
            "probe_version": "0.1.0",
            "status": "ERROR",
            "exit_code": completed.returncode,
            "resolved_inside_site_packages": False,
            "resolved_inside_source_checkout": False,
            "isolated_mode": True,
            "module_origin": None,
            "error": str(exc),
        }
    return document, completed.returncode, completed.stderr


def _probe_cli(
    environment: InstalledSUTEnvironment,
    workspace: Path,
    process_environment: Mapping[str, str],
) -> dict[str, Any]:
    completed = subprocess.run(
        [str(environment.executable), "--help"],
        cwd=workspace,
        env=dict(process_environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    available = completed.returncode == 0 and "analyze" in completed.stdout
    return {
        "probe_version": "0.1.0",
        "status": "PASS" if available else "FAIL",
        "command": ["spmkit", "--help"],
        "exit_code": completed.returncode,
        "analyze_command_present": "analyze" in completed.stdout,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }


def _artifact_by_id(protocol: Mapping[str, Any], artifact_id: str) -> Mapping[str, Any]:
    try:
        return next(item for item in protocol["evidence"] if item["artifact_id"] == artifact_id)
    except StopIteration as exc:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.PROTOCOL_ARTIFACT_MISSING",
                    "/evidence",
                    f"required artifact {artifact_id!r} is absent",
                )
            ]
        ) from exc


def execute_software_test(
    protocol_bundle_path: str | Path,
    freeze_receipt_path: str | Path,
    *,
    artifact_root: str | Path,
    sut_wheel: str | Path,
    installed_environment: InstalledSUTEnvironment,
    output_dir: str | Path,
    timeout_seconds: float = 120.0,
) -> SoftwareTestExecutionResult:
    """Verify the snapshot, then run the exact exported suite against site-packages."""

    root = Path(artifact_root).resolve(strict=True)
    protocol = _validate_protocol_before_subprocess(
        Path(protocol_bundle_path), Path(freeze_receipt_path), root
    )
    if not any(case["case_id"] == SOFTWARE_CASE_ID for case in protocol["cases"]):
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.CASE_NOT_FROZEN",
                    "/cases",
                    "the frozen protocol does not contain the software verification case",
                )
            ]
        )
    wheel = _safe_regular_file(Path(sut_wheel), "SOFTWARE_TEST.WHEEL_INVALID", "/sut_wheel")
    wheel_sha256, wheel_size = _hash_file(wheel)
    if (
        wheel_sha256 != installed_environment.wheel_sha256
        or wheel_size != installed_environment.wheel_size_bytes
    ):
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.WHEEL_IDENTITY_MISMATCH",
                    "/sut_wheel",
                    "installed environment does not match the declared wheel",
                )
            ]
        )
    suite_artifact = _artifact_by_id(protocol, SUITE_ARCHIVE_ID)
    manifest_artifact = _artifact_by_id(protocol, SUITE_MANIFEST_ID)
    entrypoint_artifact = _artifact_by_id(protocol, PYTEST_ENTRYPOINT_ID)
    manifest_path = root / manifest_artifact["relative_uri"]
    archive_path = root / suite_artifact["relative_uri"]
    entrypoint_path = root / entrypoint_artifact["relative_uri"]
    suite_manifest = _read_manifest(manifest_path)
    if suite_manifest.get("sut_commit") != protocol["campaign"]["system_under_test"][
        "git_commit"
    ]:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.SUITE_COMMIT_MISMATCH",
                    "/software-test-suite-manifest/sut_commit",
                    "suite commit differs from the frozen SUT commit",
                )
            ]
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    resolved_output = output.resolve(strict=True)
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.OUTPUT_ESCAPES_ARTIFACT_ROOT",
                    "/output_dir",
                    "software-test output must remain below artifact_root",
                )
            ]
        ) from exc
    workspace = resolved_output / "workspace"
    workspace.mkdir()
    _extract_exact_suite(archive_path, workspace, suite_manifest)
    _write_exclusive(workspace / "pytest-entrypoint.py", entrypoint_path.read_bytes())

    process_environment = _scientific_environment(installed_environment.executable)
    process_environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    started_at = _now()
    import_probe, import_exit, import_stderr = _probe_import(
        installed_environment, workspace, process_environment
    )
    cli_probe = _probe_cli(installed_environment, workspace, process_environment)
    import_path = resolved_output / "import-probe.json"
    cli_path = resolved_output / "cli-probe.json"
    _write_exclusive(import_path, canonical_bundle_bytes(import_probe))
    _write_exclusive(cli_path, canonical_bundle_bytes(cli_probe))

    recorded_command = list(suite_manifest.get("logical_command", []))
    expected_prefix = ["python", "pytest-entrypoint.py"]
    if recorded_command[:2] != expected_prefix or not recorded_command:
        raise CampaignExecutionError(
            [
                _software_issue(
                    "SOFTWARE_TEST.COMMAND_NOT_PREDECLARED",
                    "/logical_command",
                    "suite manifest command is not the supported pytest entrypoint",
                )
            ]
        )
    stdout = ""
    stderr = ""
    pytest_exit: int | None = None
    junit_summary: JUnitSummary | None = None
    errors: list[dict[str, str]] = []
    if import_probe.get("status") != "PASS" or import_exit != 0:
        errors.append(
            {
                "code": "SOFTWARE_TEST_IMPORT_FAILED",
                "message": import_stderr.strip() or "isolated installed-wheel import failed",
            }
        )
    if cli_probe.get("status") != "PASS":
        errors.append(
            {
                "code": "SOFTWARE_TEST_CLI_PROBE_FAILED",
                "message": "installed wheel public CLI probe failed",
            }
        )
    junit_path = workspace / "junit.xml"
    if not errors:
        actual_command = [str(installed_environment.python_executable), *recorded_command[1:]]
        try:
            completed = subprocess.run(
                actual_command,
                cwd=workspace,
                env=process_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            pytest_exit = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            errors.append(
                {
                    "code": "SOFTWARE_TEST_TIMEOUT",
                    "message": f"pytest exceeded timeout {timeout_seconds} seconds",
                }
            )
        if junit_path.is_file():
            try:
                junit_summary = parse_junit_xml(junit_path)
            except CampaignExecutionError as exc:
                errors.extend(
                    {
                        "code": issue.code.replace(".", "_"),
                        "message": issue.description,
                    }
                    for issue in exc.issues
                )
        else:
            errors.append(
                {"code": "JUNIT_MISSING", "message": "pytest did not produce JUnit XML"}
            )
        if pytest_exit != 0:
            errors.append(
                {
                    "code": "SOFTWARE_TEST_NONZERO_EXIT",
                    "message": f"pytest exited with code {pytest_exit}",
                }
            )
        if junit_summary is not None and not junit_summary.successful:
            errors.append(
                {
                    "code": "SOFTWARE_TEST_JUNIT_FAILURE",
                    "message": (
                        f"JUnit failures={junit_summary.failures} errors={junit_summary.errors}"
                    ),
                }
            )

    stdout_path = resolved_output / "stdout.txt"
    stderr_path = resolved_output / "stderr.txt"
    _write_exclusive(stdout_path, stdout.encode())
    _write_exclusive(stderr_path, stderr.encode())
    environment_document = {
        "environment_version": "0.1.0",
        "python_requirement": "3.12",
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "locale": "C.UTF-8",
        "network_policy": "OFFLINE",
        "installation": installed_environment.installation,
        "wheel_sha256": wheel_sha256,
        "wheel_size_bytes": wheel_size,
        "installed_dependencies": list(installed_environment.installed_dependencies),
        "pythonpath_present": False,
        "pytest_plugin_autoload": False,
    }
    environment_path = resolved_output / "environment.json"
    _write_exclusive(environment_path, canonical_bundle_bytes(environment_document))
    completed_at = _now()
    run_record = {
        "software_test_run_record_version": "0.1.0",
        "run_id": SOFTWARE_TEST_RUN_ID,
        "status": "ERROR" if errors else "COMPLETED",
        "command": recorded_command,
        "exit_code": pytest_exit,
        "started_at": started_at,
        "completed_at": completed_at,
        "wheel_sha256": wheel_sha256,
        "test_suite_manifest_sha256": manifest_artifact["sha256"],
        "junit": junit_summary.to_dict() if junit_summary is not None else None,
        "import_probe_status": import_probe.get("status"),
        "cli_probe_status": cli_probe.get("status"),
        "errors": errors,
    }
    run_record_path = resolved_output / "software-test-run.json"
    _write_exclusive(run_record_path, canonical_bundle_bytes(run_record))

    sources = [SUITE_MANIFEST_ID, SUITE_ARCHIVE_ID, "artifact.execution.sut-wheel"]
    limitations = [
        "Selected installed-wheel non-GUI software suite; not a complete SUT test suite."
    ]
    evidence: list[dict[str, Any]] = [
        _artifact(
            import_path,
            root,
            artifact_id=IMPORT_PROBE_ARTIFACT_ID,
            artifact_type="REPORT",
            media_type="application/json",
            created_at=started_at,
            role="PROVENANCE",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=["artifact.execution.sut-wheel"],
            generation_command=["python", "-I", "-c", "<installed-wheel-import-probe>"],
            limitations=limitations,
        ),
        _artifact(
            cli_path,
            root,
            artifact_id=CLI_PROBE_ARTIFACT_ID,
            artifact_type="REPORT",
            media_type="application/json",
            created_at=started_at,
            role="PROVENANCE",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=["artifact.execution.sut-wheel"],
            generation_command=["spmkit", "--help"],
            limitations=limitations,
        ),
        _artifact(
            stdout_path,
            root,
            artifact_id=SOFTWARE_STDOUT_ARTIFACT_ID,
            artifact_type="LOG",
            media_type="text/plain",
            created_at=started_at,
            role="DIAGNOSTIC",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=sources,
            generation_command=recorded_command,
            limitations=limitations,
        ),
        _artifact(
            stderr_path,
            root,
            artifact_id=SOFTWARE_STDERR_ARTIFACT_ID,
            artifact_type="LOG",
            media_type="text/plain",
            created_at=started_at,
            role="DIAGNOSTIC",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=sources,
            generation_command=recorded_command,
            limitations=limitations,
        ),
        _artifact(
            environment_path,
            root,
            artifact_id=SOFTWARE_ENVIRONMENT_ARTIFACT_ID,
            artifact_type="ENVIRONMENT_SNAPSHOT",
            media_type="application/json",
            created_at=started_at,
            role="PROVENANCE",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=["artifact.execution.sut-wheel"],
            generation_command=["uv", "pip", "freeze"],
            limitations=limitations,
        ),
    ]
    output_ids = [item["artifact_id"] for item in evidence]
    if junit_path.is_file():
        junit_artifact = _artifact(
            junit_path,
            root,
            artifact_id=JUNIT_ARTIFACT_ID,
            artifact_type="REPORT",
            media_type="application/xml",
            created_at=started_at,
            role="SOFTWARE_TEST_RESULT",
            run_id=SOFTWARE_TEST_RUN_ID,
            sources=sources,
            generation_command=recorded_command,
            limitations=limitations,
        )
        evidence.append(junit_artifact)
        output_ids.append(JUNIT_ARTIFACT_ID)
    run_record_artifact = _artifact(
        run_record_path,
        root,
        artifact_id=SOFTWARE_RUN_RECORD_ARTIFACT_ID,
        artifact_type="MANIFEST",
        media_type="application/json",
        created_at=started_at,
        role="PROVENANCE",
        run_id=SOFTWARE_TEST_RUN_ID,
        sources=[
            IMPORT_PROBE_ARTIFACT_ID,
            CLI_PROBE_ARTIFACT_ID,
            *([JUNIT_ARTIFACT_ID] if junit_path.is_file() else []),
        ],
        external_schema={
            "name": "spmkit-validation.software-test-run",
            "version": "0.1.0",
        },
        generation_command=recorded_command,
        limitations=limitations,
    )
    evidence.append(run_record_artifact)
    output_ids.append(SOFTWARE_RUN_RECORD_ARTIFACT_ID)
    warnings = []
    if junit_summary is not None and junit_summary.skips:
        warnings.append(
            {
                "code": "SOFTWARE_TEST_SKIPS_PRESENT",
                "message": f"selected suite preserved {junit_summary.skips} skips",
                "evidence_id": JUNIT_ARTIFACT_ID,
            }
        )
    run = {
        "run_id": SOFTWARE_TEST_RUN_ID,
        "campaign_id": protocol["campaign"]["campaign_id"],
        "case_ids": [SOFTWARE_CASE_ID],
        "run_type": "SOFTWARE_TEST",
        "started_at": started_at,
        "finished_at": completed_at,
        "command": recorded_command,
        "parameters": {
            "exit_code": pytest_exit,
            "wheel_sha256": wheel_sha256,
            "test_suite_manifest_sha256": manifest_artifact["sha256"],
            "structured_output": "JUnit XML",
            "source_checkout_execution": False,
            "junit": junit_summary.to_dict() if junit_summary is not None else None,
        },
        "seed": None,
        "environment": {
            "environment_id": protocol["campaign"]["system_under_test"]["environment_id"],
            "platform": platform.system().lower(),
            "operating_system": platform.system(),
            "architecture": platform.machine(),
            "python_version": "3.12",
            "snapshot_artifact_id": SOFTWARE_ENVIRONMENT_ARTIFACT_ID,
        },
        "input_artifact_ids": [
            SUITE_MANIFEST_ID,
            SUITE_ARCHIVE_ID,
            PYTEST_ENTRYPOINT_ID,
            WHEEL_POLICY_ID,
            "artifact.execution.sut-wheel",
        ],
        "output_artifact_ids": output_ids,
        "run_manifest_artifact_id": SOFTWARE_RUN_RECORD_ARTIFACT_ID,
        "execution_status": "ERROR" if errors else "COMPLETED",
        "errors": errors,
        "warnings": warnings,
    }
    return SoftwareTestExecutionResult(
        run=run,
        evidence=tuple(sorted(evidence, key=lambda item: item["artifact_id"])),
        junit_summary=junit_summary,
        import_probe=import_probe,
        cli_probe=cli_probe,
        started_at=started_at,
        completed_at=completed_at,
        wheel_sha256=wheel_sha256,
        suite_manifest_sha256=manifest_artifact["sha256"],
    )
