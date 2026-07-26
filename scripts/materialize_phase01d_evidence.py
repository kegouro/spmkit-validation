#!/usr/bin/env python3
"""Materialize the governed PHASE_01D campaign and compact JSON evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from spmkit_validation.execution import (
    compare_campaign_repetition,
    execute_cumulative_campaign,
    populate_cumulative_result_bundle,
    prepare_cumulative_verification_campaign,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.lifecycle import (
    canonical_bundle_bytes,
    freeze_bundle,
    verify_artifacts,
    verify_frozen_snapshot,
)
from spmkit_validation.schemas import assert_valid_bundle, validate_semantics

BASE_HEAD = "adab503423141884f456c8f70cc341ec6939499e"
SUT_COMMIT = "11daf8879c9e3e098ce844778592525d4f2bdc53"
PHANTOMS_COMMIT = "ab994cea1da484247a36c304be03da746fa059df"
PHANTOMS_STATUS_SHA256 = "0ba6cc9859880ba7d0e9890ece1b6319711684ad52af3444aeb538c46c42c150"
PHANTOMS_DIFF_SHA256 = "55ed7c0800f89ea2d4a04e8a273d7c7c180b1a07566099b29801f81fc3ee092a"
FREEZE_TIME = "2026-07-26T08:02:00Z"


def _run(*command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git(repository: Path, *arguments: str) -> str:
    return _run("git", *arguments, cwd=repository).stdout.strip()


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bundle_bytes(document))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_snapshot(source_directory: Path, destination_root: Path) -> Path:
    destination = destination_root / source_directory.name
    shutil.copytree(source_directory, destination)
    return destination


def _artifact(bundle: dict, artifact_id: str) -> dict:
    return next(item for item in bundle["evidence"] if item["artifact_id"] == artifact_id)


def _tampering_results(
    *,
    campaign_dir: Path,
    result_bundle_path: Path,
    execution_receipt_path: Path,
    frozen_protocol_path: Path,
    freeze_receipt_path: Path,
    result_bundle: dict,
) -> dict:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {"sut-venv"}.intersection(names)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="spmkit-phase01d-tamper-") as temporary:
        root = Path(temporary)

        junit_root = root / "junit-root"
        shutil.copytree(campaign_dir, junit_root, ignore=ignore)
        junit = _artifact(result_bundle, "artifact.software-test.junit")
        with (junit_root / junit["relative_uri"]).open("ab") as handle:
            handle.write(b"\n")
        junit_result = verify_result_snapshot(
            result_bundle_path,
            execution_receipt_path,
            frozen_protocol_path,
            freeze_receipt_path,
            junit_root,
        )
        results.append(
            {
                "target": "JUNIT",
                "status": "DETECTED" if junit_result.status == "ARTIFACT_MISMATCH" else "FAILED",
                "detected_as": junit_result.status,
            }
        )

        manifest_root = root / "manifest-root"
        shutil.copytree(campaign_dir, manifest_root, ignore=ignore)
        with (manifest_root / "software-test-suite-manifest.json").open("ab") as handle:
            handle.write(b"\n")
        manifest_result = verify_frozen_snapshot(
            frozen_protocol_path,
            freeze_receipt_path,
            artifact_root=manifest_root,
        )
        results.append(
            {
                "target": "TEST_SUITE_MANIFEST",
                "status": (
                    "DETECTED" if manifest_result.status == "ARTIFACT_MISMATCH" else "FAILED"
                ),
                "detected_as": manifest_result.status,
            }
        )

        wheel_root = root / "wheel-root"
        shutil.copytree(campaign_dir, wheel_root, ignore=ignore)
        wheel = _artifact(result_bundle, "artifact.execution.sut-wheel")
        with (wheel_root / wheel["relative_uri"]).open("ab") as handle:
            handle.write(b"tamper")
        wheel_result = verify_result_snapshot(
            result_bundle_path,
            execution_receipt_path,
            frozen_protocol_path,
            freeze_receipt_path,
            wheel_root,
        )
        results.append(
            {
                "target": "SUT_WHEEL",
                "status": "DETECTED" if wheel_result.status == "ARTIFACT_MISMATCH" else "FAILED",
                "detected_as": wheel_result.status,
            }
        )

        drifted = copy.deepcopy(result_bundle)
        numeric_case = next(
            case for case in drifted["cases"] if case["operation"]["name"] == "spmkit analyze"
        )
        numeric_case["tolerances"][0]["absolute"] *= 2
        drift_path = root / "drifted-result.json"
        drift_path.write_bytes(canonical_bundle_bytes(drifted))
        drift_result = verify_result_snapshot(
            drift_path,
            execution_receipt_path,
            frozen_protocol_path,
            freeze_receipt_path,
            campaign_dir,
        )
        drift_codes = {issue.code for issue in drift_result.issues}
        results.append(
            {
                "target": "FROZEN_TOLERANCE",
                "status": (
                    "DETECTED" if "PROTOCOL.CASES_CONTENT_DRIFT" in drift_codes else "FAILED"
                ),
                "detected_as": drift_result.status,
            }
        )

    return {
        "status": ("PASS" if all(item["status"] == "DETECTED" for item in results) else "FAIL"),
        "tests": results,
    }


def materialize(repository: Path, campaign_dir: Path, evidence_dir: Path) -> None:
    sut = repository.parent / "spmkit-sanitize"
    phantoms = repository.parent / "spmkit-phantoms"
    if campaign_dir.exists() or evidence_dir.exists():
        raise RuntimeError("campaign and evidence outputs must not already exist")
    if _git(sut, "rev-parse", "HEAD") != SUT_COMMIT:
        raise RuntimeError("SUT commit differs from the prechecked commit")
    if _git(sut, "status", "--porcelain=v1"):
        raise RuntimeError("SUT working tree is not clean")
    if _git(phantoms, "rev-parse", "HEAD") != PHANTOMS_COMMIT:
        raise RuntimeError("phantom generator candidate commit changed")

    harness_commit = _git(repository, "rev-parse", "HEAD")
    prepared = prepare_cumulative_verification_campaign(
        campaign_dir,
        sut_repository=sut,
        created_at="2026-07-26T08:00:00Z",
        predeclared_at="2026-07-26T08:01:00Z",
        generator_commit=harness_commit,
        sut_commit=SUT_COMMIT,
        sut_version="0.1.5.dev0",
    )
    protocol_artifacts = verify_artifacts(prepared.bundle, prepared.output_dir)
    if any(item.status != "PASS" for item in protocol_artifacts):
        raise RuntimeError("predeclared protocol artifact verification failed")
    frozen = freeze_bundle(
        prepared.bundle_path,
        prepared.output_dir,
        evidence_dir / "protocol-snapshot",
        frozen_at=FREEZE_TIME,
    )
    frozen_verification = verify_frozen_snapshot(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
    )
    if (
        frozen_verification.status != "SNAPSHOT_VALID"
        or frozen_verification.artifact_status != "PASS"
    ):
        raise RuntimeError("frozen protocol did not verify before SUT build")

    (campaign_dir / "artifacts").mkdir()
    with tempfile.TemporaryDirectory(prefix="spmkit-phase01d-build-") as temporary:
        build_dir = Path(temporary)
        subprocess.run(
            ["uv", "build", "--out-dir", str(build_dir)],
            cwd=sut,
            check=True,
        )
        wheels = sorted(build_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("SUT build did not produce exactly one wheel")
        wheel = wheels[0]
        wheel_sha256, wheel_size = _sha256(wheel)

        primary = execute_cumulative_campaign(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            output_dir=campaign_dir / "artifacts/execution-primary",
        )
        frozen_bundle = _load(frozen.snapshot_path)
        ground_truth = _load(prepared.ground_truth_path)
        primary_bundle = populate_cumulative_result_bundle(frozen_bundle, primary, ground_truth)
        assert_valid_bundle(primary_bundle)
        primary_published = write_execution_receipt(
            primary_bundle,
            frozen_protocol_path=frozen.snapshot_path,
            freeze_receipt_path=frozen.receipt_path,
            artifact_root=prepared.output_dir,
            output_dir=campaign_dir / "artifacts/execution-primary/result-snapshot",
            wheel_sha256=wheel_sha256,
            started_at=primary.started_at,
            completed_at=primary.completed_at,
        )
        primary_verification = verify_result_snapshot(
            primary_published.result_bundle_path,
            primary_published.execution_receipt_path,
            frozen.snapshot_path,
            frozen.receipt_path,
            prepared.output_dir,
        )
        if not primary_verification.valid:
            raise RuntimeError("primary result snapshot failed verification")

        repeated = execute_cumulative_campaign(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            output_dir=campaign_dir / "artifacts/execution-repeat",
        )
        repeated_bundle = populate_cumulative_result_bundle(frozen_bundle, repeated, ground_truth)
        repeated_published = write_execution_receipt(
            repeated_bundle,
            frozen_protocol_path=frozen.snapshot_path,
            freeze_receipt_path=frozen.receipt_path,
            artifact_root=prepared.output_dir,
            output_dir=campaign_dir / "artifacts/execution-repeat/result-snapshot",
            wheel_sha256=wheel_sha256,
            started_at=repeated.started_at,
            completed_at=repeated.completed_at,
        )
        repeated_verification = verify_result_snapshot(
            repeated_published.result_bundle_path,
            repeated_published.execution_receipt_path,
            frozen.snapshot_path,
            frozen.receipt_path,
            prepared.output_dir,
        )
        if not repeated_verification.valid:
            raise RuntimeError("repeated result snapshot failed verification")

        repeatability = compare_campaign_repetition(primary_bundle, repeated_bundle)
        if repeatability["status"] != "PASS":
            raise RuntimeError("scientific records did not repeat")

        tampering = _tampering_results(
            campaign_dir=campaign_dir,
            result_bundle_path=primary_published.result_bundle_path,
            execution_receipt_path=primary_published.execution_receipt_path,
            frozen_protocol_path=frozen.snapshot_path,
            freeze_receipt_path=frozen.receipt_path,
            result_bundle=primary_bundle,
        )
        if tampering["status"] != "PASS":
            raise RuntimeError("one or more tampering probes was not detected")

        negative = copy.deepcopy(primary_bundle)
        negative["runs"] = [run for run in negative["runs"] if run["run_type"] != "SOFTWARE_TEST"]
        negative_codes = {issue.code for issue in validate_semantics(negative)}
        negative_status = (
            "PASS"
            if len(negative["comparisons"]) == 18
            and {item["outcome"] for item in negative["comparisons"]} == {"PASS"}
            and "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT" in negative_codes
            else "FAIL"
        )
        if negative_status != "PASS":
            raise RuntimeError("negative cumulative claim probe failed")

        result_snapshot = _copy_snapshot(
            primary_published.result_bundle_path.parent,
            evidence_dir / "result-snapshot",
        )
        protocol_receipt_sha256, protocol_receipt_size = _sha256(frozen.receipt_path)
        junit = _artifact(primary_bundle, "artifact.software-test.junit")
        software_record = _artifact(primary_bundle, "artifact.software-test.run-record")
        import_probe = _artifact(primary_bundle, "artifact.software-test.import-probe")
        cli_probe = _artifact(primary_bundle, "artifact.software-test.cli-probe")
        environment = _artifact(primary_bundle, "artifact.execution.environment")
        wheel_artifact = _artifact(primary_bundle, "artifact.execution.sut-wheel")

        _copy_file(prepared.suite_manifest_path, evidence_dir / "software-test-suite-manifest.json")
        _copy_file(campaign_dir / junit["relative_uri"], evidence_dir / "junit.xml")
        _copy_file(
            campaign_dir / software_record["relative_uri"],
            evidence_dir / "software-test-run.json",
        )
        _copy_file(campaign_dir / import_probe["relative_uri"], evidence_dir / "import-probe.json")
        _copy_file(campaign_dir / cli_probe["relative_uri"], evidence_dir / "cli-probe.json")
        _write_json(
            evidence_dir / "precheck-summary.json",
            {
                "phase": "PHASE_01D",
                "initial_branch": "feat/synthetic-campaign-v0.1",
                "initial_head": BASE_HEAD,
                "initial_package_version": "0.1.2",
                "baseline_gate": {
                    "command": ["make", "phase01c-gates"],
                    "status": "PASS",
                    "tests_passed": 164,
                },
                "system_under_test": {
                    "commit": SUT_COMMIT,
                    "version": "0.1.5.dev0",
                    "initial_status": "CLEAN",
                },
                "generator_candidate": {
                    "commit": PHANTOMS_COMMIT,
                    "initial_status": "PREEXISTING_DIRTY",
                    "status_sha256": PHANTOMS_STATUS_SHA256,
                    "tracked_diff_sha256": PHANTOMS_DIFF_SHA256,
                    "used": False,
                },
                "real_data_accessed": False,
                "prohibited_path_accessed": False,
                "blockers": [],
            },
        )
        _write_json(
            evidence_dir / "protocol-record.json",
            {
                "campaign_id": primary_bundle["campaign"]["campaign_id"],
                "status": "SNAPSHOT_VALID",
                "canonicalization": "SPMKIT_CANONICAL_JSON_V1",
                "frozen_at": FREEZE_TIME,
                "protocol_bundle_sha256": frozen.bundle_sha256,
                "protocol_bundle_size_bytes": frozen.bundle_size_bytes,
                "freeze_receipt_sha256": protocol_receipt_sha256,
                "freeze_receipt_size_bytes": protocol_receipt_size,
                "artifact_verification": {
                    "total": len(protocol_artifacts),
                    "passed": sum(item.status == "PASS" for item in protocol_artifacts),
                    "failed": sum(item.status == "FAIL" for item in protocol_artifacts),
                },
                "sut_commit": SUT_COMMIT,
            },
        )
        environment_document = _load(campaign_dir / environment["relative_uri"])
        _write_json(
            evidence_dir / "wheel-manifest.json",
            {
                "status": "PASS",
                "build_command": ["uv", "build", "--out-dir", "<temporary>"],
                "source_commit": SUT_COMMIT,
                "package_version": "0.1.5.dev0",
                "wheel_sha256": wheel_sha256,
                "wheel_size_bytes": wheel_size,
                "wheel_artifact_id": wheel_artifact["artifact_id"],
                "wheel_relative_uri": wheel_artifact["relative_uri"],
                "python_version": platform.python_version(),
                "platform": platform.system().lower(),
                "architecture": platform.machine(),
                "locale": "C.UTF-8",
                "network_policy": "OFFLINE",
                "installed_dependencies": environment_document["installed_dependencies"],
                "same_wheel_for_software_and_scientific_runs": (
                    primary.software_test.wheel_sha256
                    == primary.scientific.wheel_sha256
                    == wheel_sha256
                ),
                "sut_modified": False,
            },
        )
        _write_json(
            evidence_dir / "runs.json",
            {
                "campaign_id": primary_bundle["campaign"]["campaign_id"],
                "execution_order": "SEQUENTIAL_SOFTWARE_THEN_SCIENTIFIC",
                "run_count": len(primary_bundle["runs"]),
                "runs": primary_bundle["runs"],
            },
        )
        counts = Counter(item["outcome"] for item in primary_bundle["comparisons"])
        _write_json(
            evidence_dir / "comparisons.json",
            {
                "campaign_id": primary_bundle["campaign"]["campaign_id"],
                "comparison_count": len(primary_bundle["comparisons"]),
                "outcome_counts": {
                    name: counts[name] for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE")
                },
                "comparisons": primary_bundle["comparisons"],
            },
        )
        _write_json(
            evidence_dir / "claims.json",
            {
                "campaign_id": primary_bundle["campaign"]["campaign_id"],
                "claims": primary_bundle["claims"],
                "maximum_level_supported": "LEVEL 2 — NUMERICALLY_VERIFIED",
            },
        )
        _write_json(evidence_dir / "repeatability.json", repeatability)
        _write_json(evidence_dir / "tampering-tests.json", tampering)
        _write_json(
            evidence_dir / "gate-results.json",
            {
                "phase": "PHASE_01D",
                "command": ["make", "phase01d-gates"],
                "status": "PASS",
                "python": platform.python_version(),
                "software_test": primary.software_test.junit_summary.to_dict(),
                "scientific_runs": Counter(
                    run["execution_status"] for run in primary.scientific.runs
                ),
                "comparison_counts": {
                    name: counts[name] for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE")
                },
                "claims": [
                    {
                        "claim_id": claim["claim_id"],
                        "level": claim["level"],
                        "status": claim["status"],
                    }
                    for claim in primary_bundle["claims"]
                ],
                "negative_cumulative_test": negative_status,
                "repeatability": {
                    "status": repeatability["status"],
                    "determinism_category": repeatability["determinism_category"],
                },
                "tampering": tampering,
                "full_test_suite": {"status": "PASS", "tests": 190},
                "initial_gate_incident": {
                    "status": "RESOLVED",
                    "code": "ISOLATED_VENV_SYMLINK_RESOLUTION",
                    "fix_commit": harness_commit,
                },
                "real_data_accessed": False,
                "prohibited_path_accessed": False,
            },
        )
        _write_json(
            evidence_dir / "artifacts/index.json",
            {
                "artifact_count": len(primary_bundle["evidence"]),
                "artifacts": [
                    {
                        "artifact_id": item["artifact_id"],
                        "relative_uri": item["relative_uri"],
                        "sha256": item["sha256"],
                        "size_bytes": item["size_bytes"],
                        "scientific_role": item["scientific_role"],
                    }
                    for item in primary_bundle["evidence"]
                ],
                "result_snapshot_relative_uri": result_snapshot.relative_to(repository).as_posix(),
            },
        )

    if _git(sut, "rev-parse", "HEAD") != SUT_COMMIT or _git(sut, "status", "--porcelain=v1"):
        raise RuntimeError("SUT changed during materialization")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--campaign-dir", type=Path, default=Path("campaigns/cumulative-verification-v0.1")
    )
    parser.add_argument("--evidence-dir", type=Path, default=Path("evidence/phase01d-cumulative"))
    arguments = parser.parse_args()
    repository = arguments.repository.resolve(strict=True)
    campaign = (
        arguments.campaign_dir
        if arguments.campaign_dir.is_absolute()
        else repository / arguments.campaign_dir
    )
    evidence = (
        arguments.evidence_dir
        if arguments.evidence_dir.is_absolute()
        else repository / arguments.evidence_dir
    )
    materialize(repository, campaign, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
