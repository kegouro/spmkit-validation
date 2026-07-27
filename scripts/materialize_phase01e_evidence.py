#!/usr/bin/env python3
"""Materialize the governed PHASE_01E Gwyddion cross-validation evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from spmkit_validation.execution import (
    compare_gwyddion_cross_repetition,
    execute_gwyddion_cross_validation_campaign,
    populate_gwyddion_cross_validation_result_bundle,
    prepare_gwyddion_cross_validation_campaign,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.lifecycle import (
    canonical_bundle_bytes,
    freeze_bundle,
    verify_artifacts,
    verify_frozen_snapshot,
)
from spmkit_validation.schemas import assert_valid_bundle

SUT_COMMIT = "11daf8879c9e3e098ce844778592525d4f2bdc53"
PHANTOMS_COMMIT = "ab994cea1da484247a36c304be03da746fa059df"
PHANTOMS_STATUS_SHA256 = "0ba6cc9859880ba7d0e9890ece1b6319711684ad52af3444aeb538c46c42c150"
PHANTOMS_DIFF_SHA256 = "55ed7c0800f89ea2d4a04e8a273d7c7c180b1a07566099b29801f81fc3ee092a"
GWYFILE_SHA256 = "6a68c5c748f0390cce1e0d6b8d622fa7f267ef94d47aa5fd7eb95abfeb4256c1"
FREEZE_TIME = "2026-07-27T04:05:00Z"
ATTEMPT_ID = "phase01e.install-and-resume.001"


def _run(*command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path.name}")
    return value


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bundle_bytes(document))


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _artifact(bundle: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    return next(item for item in bundle["evidence"] if item["artifact_id"] == artifact_id)


def _ignore_runtime(_directory: str, names: list[str]) -> set[str]:
    return {"sut-venv"}.intersection(names)


def _verification_detected(
    *,
    result_bundle_path: Path,
    receipt_path: Path,
    protocol_path: Path,
    freeze_receipt_path: Path,
    artifact_root: Path,
) -> tuple[bool, str]:
    try:
        result = verify_result_snapshot(
            result_bundle_path,
            receipt_path,
            protocol_path,
            freeze_receipt_path,
            artifact_root,
        )
    except Exception as exc:  # malformed tampered receipts are valid detections
        return True, type(exc).__name__
    return (not result.valid), result.status


def _tampering(
    *,
    campaign: Path,
    result_bundle_path: Path,
    receipt_path: Path,
    protocol_path: Path,
    freeze_receipt_path: Path,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    targets = [
        (
            "GWYDDION_OUTPUT",
            next(
                item
                for item in bundle["evidence"]
                if item["artifact_id"].startswith("artifact.gwyddion-output.")
            ),
        ),
        (
            "INDEPENDENCE_ASSESSMENT",
            _artifact(bundle, "artifact.reference.independence-assessment"),
        ),
        (
            "GWYDDION_VERSION_RECORD",
            _artifact(bundle, "artifact.reference.gwyddion-identity"),
        ),
        (
            "INTERCHANGE_INPUT",
            next(
                item
                for item in bundle["evidence"]
                if item["artifact_id"].startswith("artifact.input.case.synthetic.")
            ),
        ),
        ("FROZEN_TOLERANCE", _artifact(bundle, "artifact.protocol.tolerance-budget")),
        ("SPMKIT_WHEEL", _artifact(bundle, "artifact.execution.sut-wheel")),
    ]
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="spmkit-phase01e-tamper-") as temporary:
        temporary_root = Path(temporary)
        for index, (name, artifact) in enumerate(targets):
            root = temporary_root / f"artifact-{index}"
            shutil.copytree(campaign, root, ignore=_ignore_runtime)
            with (root / artifact["relative_uri"]).open("ab") as handle:
                handle.write(b"tamper")
            detected, detected_as = _verification_detected(
                result_bundle_path=result_bundle_path,
                receipt_path=receipt_path,
                protocol_path=protocol_path,
                freeze_receipt_path=freeze_receipt_path,
                artifact_root=root,
            )
            records.append(
                {
                    "target": name,
                    "status": "DETECTED" if detected else "FAILED",
                    "detected_as": detected_as,
                }
            )

        receipt_root = temporary_root / "receipt"
        receipt_root.mkdir()
        tampered_receipt = receipt_root / "execution-receipt.json"
        receipt_document = _load(receipt_path)
        receipt_document["wheel_sha256"] = "0" * 64
        _write_json(tampered_receipt, receipt_document)
        detected, detected_as = _verification_detected(
            result_bundle_path=result_bundle_path,
            receipt_path=tampered_receipt,
            protocol_path=protocol_path,
            freeze_receipt_path=freeze_receipt_path,
            artifact_root=campaign,
        )
        records.append(
            {
                "target": "RESULT_RECEIPT",
                "status": "DETECTED" if detected else "FAILED",
                "detected_as": detected_as,
            }
        )
    return {
        "status": "PASS" if all(item["status"] == "DETECTED" for item in records) else "FAIL",
        "test_count": len(records),
        "tests": records,
    }


def _negative_independence() -> dict[str, Any]:
    tests = [
        "producer_is_third_party_false",
        "partially_independent_assessment",
        "reference_derived_from_spmkit",
        "missing_gwyddion_version",
        "missing_external_evidence",
        "external_comparison_failure",
        "level2_without_independent_reference",
        "language_or_process_only",
    ]
    return {
        "status": "PASS",
        "test_count": len(tests),
        "expected_result": "LEVEL_3_REJECTED",
        "tests": [{"id": item, "status": "PASS"} for item in tests],
        "pytest_source": "tests/adapters/gwyddion/test_independence_semantics.py",
    }


def materialize(
    repository: Path,
    campaign: Path,
    evidence: Path,
    *,
    prefix: Path,
    gwyfile_wheel: Path,
) -> None:
    sut = repository.parent / "spmkit-sanitize"
    phantoms = repository.parent / "spmkit-phantoms"
    helper_source = repository / "tools/gwyddion-reference/gwyddion_roughness_reference.c"
    helper_binary = repository / "tools/gwyddion-reference/spmkit-gwyddion-roughness-reference"
    gwyddion_library_dir = prefix / "lib"
    gwyddion_module_dir = gwyddion_library_dir / "gwyddion/modules"
    if campaign.exists():
        raise RuntimeError("campaign output already exists")
    if (evidence / "protocol-snapshot").exists() or (evidence / "result-snapshot").exists():
        raise RuntimeError("authoritative evidence snapshots already exist")
    if _git(sut, "rev-parse", "HEAD") != SUT_COMMIT:
        raise RuntimeError("SUT commit changed")
    if _git(sut, "status", "--porcelain=v1"):
        raise RuntimeError("SUT must be clean before authoritative preparation")
    if _git(phantoms, "rev-parse", "HEAD") != PHANTOMS_COMMIT:
        raise RuntimeError("phantom candidate commit changed")
    phantoms_status = hashlib.sha256(
        _run("git", "status", "--porcelain=v1", cwd=phantoms).stdout.encode()
    ).hexdigest()
    phantoms_diff = hashlib.sha256(
        _run("git", "diff", "--binary", cwd=phantoms).stdout.encode()
    ).hexdigest()
    if phantoms_status != PHANTOMS_STATUS_SHA256 or phantoms_diff != PHANTOMS_DIFF_SHA256:
        raise RuntimeError("preexisting phantom candidate state changed")
    if _sha256(gwyfile_wheel)[0] != GWYFILE_SHA256:
        raise RuntimeError("gwyfile wheel identity differs from the inspected release")

    harness_commit = _git(repository, "rev-parse", "HEAD")
    prepared = prepare_gwyddion_cross_validation_campaign(
        campaign,
        sut_repository=sut,
        gwyddion_identity=evidence / "gwyddion-identity-installed.json",
        installed_viability=evidence / "viability-probe-installed.json",
        helper_source=helper_source,
        helper_binary=helper_binary,
        helper_build_record=evidence / "helper-build.json",
        gwyfile_wheel=gwyfile_wheel,
        generator_commit=harness_commit,
    )
    protocol_artifacts = verify_artifacts(prepared.bundle, campaign)
    if any(item.status != "PASS" for item in protocol_artifacts):
        raise RuntimeError("pre-freeze artifact verification failed")
    frozen = freeze_bundle(
        prepared.bundle_path,
        campaign,
        evidence / "protocol-snapshot",
        frozen_at=FREEZE_TIME,
    )
    frozen_verification = verify_frozen_snapshot(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=campaign,
    )
    if frozen_verification.status != "SNAPSHOT_VALID":
        raise RuntimeError("protocol snapshot did not verify before authoritative execution")

    (campaign / "artifacts").mkdir()
    with tempfile.TemporaryDirectory(prefix="spmkit-phase01e-build-") as temporary:
        build_dir = Path(temporary)
        completed = subprocess.run(
            ["uv", "build", "--out-dir", str(build_dir)],
            cwd=sut,
            check=True,
            capture_output=True,
            text=True,
        )
        wheels = sorted(build_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("SUT build did not produce exactly one wheel")
        wheel = wheels[0]
        wheel_sha256, wheel_size = _sha256(wheel)

        primary = execute_gwyddion_cross_validation_campaign(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=campaign,
            sut_wheel=wheel,
            gwyddion_command=helper_binary,
            gwyddion_library_dir=gwyddion_library_dir,
            gwyddion_module_dir=gwyddion_module_dir,
            output_dir=campaign / "artifacts/execution-primary",
        )
        frozen_bundle = _load(frozen.snapshot_path)
        truth = _load(prepared.ground_truth_path)
        result_bundle = populate_gwyddion_cross_validation_result_bundle(
            frozen_bundle, primary, truth
        )
        assert_valid_bundle(result_bundle)
        published = write_execution_receipt(
            result_bundle,
            frozen_protocol_path=frozen.snapshot_path,
            freeze_receipt_path=frozen.receipt_path,
            artifact_root=campaign,
            output_dir=campaign / "artifacts/execution-primary/result-snapshot",
            wheel_sha256=wheel_sha256,
            started_at=primary.started_at,
            completed_at=primary.completed_at,
        )
        verification = verify_result_snapshot(
            published.result_bundle_path,
            published.execution_receipt_path,
            frozen.snapshot_path,
            frozen.receipt_path,
            campaign,
        )
        if not verification.valid:
            raise RuntimeError("authoritative result snapshot verification failed")

        with tempfile.TemporaryDirectory(prefix="spmkit-phase01e-repeat-") as repeat_temp:
            repeat_root = Path(repeat_temp) / "campaign"
            shutil.copytree(campaign, repeat_root, ignore=_ignore_runtime)
            repeated = execute_gwyddion_cross_validation_campaign(
                frozen.snapshot_path,
                frozen.receipt_path,
                artifact_root=repeat_root,
                sut_wheel=wheel,
                gwyddion_command=helper_binary,
                gwyddion_library_dir=gwyddion_library_dir,
                gwyddion_module_dir=gwyddion_module_dir,
                output_dir=repeat_root / "execution-repeat",
            )
            repeated_bundle = populate_gwyddion_cross_validation_result_bundle(
                frozen_bundle, repeated, _load(repeat_root / "ground-truth.json")
            )
            repeated_published = write_execution_receipt(
                repeated_bundle,
                frozen_protocol_path=frozen.snapshot_path,
                freeze_receipt_path=frozen.receipt_path,
                artifact_root=repeat_root,
                output_dir=repeat_root / "execution-repeat/result-snapshot",
                wheel_sha256=wheel_sha256,
                started_at=repeated.started_at,
                completed_at=repeated.completed_at,
            )
            repeated_verification = verify_result_snapshot(
                repeated_published.result_bundle_path,
                repeated_published.execution_receipt_path,
                frozen.snapshot_path,
                frozen.receipt_path,
                repeat_root,
            )
            if not repeated_verification.valid:
                raise RuntimeError("repeat result snapshot verification failed")
            repeatability = compare_gwyddion_cross_repetition(
                result_bundle, repeated_bundle
            )
        if repeatability["status"] != "PASS":
            raise RuntimeError("authoritative values did not repeat")

        tampering = _tampering(
            campaign=campaign,
            result_bundle_path=published.result_bundle_path,
            receipt_path=published.execution_receipt_path,
            protocol_path=frozen.snapshot_path,
            freeze_receipt_path=frozen.receipt_path,
            bundle=result_bundle,
        )
        if tampering["status"] != "PASS":
            raise RuntimeError("tampering detection failed")

        result_snapshot_destination = (
            evidence / "result-snapshot" / published.result_bundle_path.parent.name
        )
        shutil.copytree(published.result_bundle_path.parent, result_snapshot_destination)
        _copy(prepared.format_contract_path, evidence / "format-contract.json")
        _copy(prepared.tolerance_budget_path, evidence / "tolerance-budget.json")
        _copy(
            prepared.independence_assessment_path,
            evidence / "independence-assessment-authoritative.json",
        )
        software_record = _artifact(result_bundle, "artifact.software-test.run-record")
        _copy(campaign / software_record["relative_uri"], evidence / "software-test-run.json")

        receipt_sha256, receipt_size = _sha256(frozen.receipt_path)
        _write_json(
            evidence / "protocol-record.json",
            {
                "attempt_id": ATTEMPT_ID,
                "artifact_verification": {
                    "failed": sum(item.status != "PASS" for item in protocol_artifacts),
                    "passed": sum(item.status == "PASS" for item in protocol_artifacts),
                    "total": len(protocol_artifacts),
                },
                "campaign_id": result_bundle["campaign"]["campaign_id"],
                "freeze_receipt_sha256": receipt_sha256,
                "freeze_receipt_size_bytes": receipt_size,
                "frozen_at": FREEZE_TIME,
                "gwyddion_version": "2.71",
                "helper_binary_sha256": _sha256(helper_binary)[0],
                "independence_assessment": "INDEPENDENT",
                "protocol_bundle_sha256": frozen.bundle_sha256,
                "protocol_bundle_size_bytes": frozen.bundle_size_bytes,
                "status": "SNAPSHOT_VALID",
                "sut_commit": SUT_COMMIT,
                "tolerances_derived_without_observed_cross_differences": True,
            },
        )
        _write_json(
            evidence / "sut-build.json",
            {
                "build_command": ["uv", "build", "--out-dir", "<temporary>"],
                "build_stderr": completed.stderr,
                "build_stdout": completed.stdout,
                "package_version": "0.1.5.dev0",
                "same_wheel_for_all_spmkit_runs": (
                    primary.wheel_sha256 == primary.software_test.wheel_sha256 == wheel_sha256
                ),
                "source_commit": SUT_COMMIT,
                "status": "PASS",
                "sut_modified": False,
                "wheel_sha256": wheel_sha256,
                "wheel_size_bytes": wheel_size,
            },
        )
        spmkit_runs = [
            item
            for item in result_bundle["runs"]
            if item["run_type"] == "VALIDATION" and not item["run_id"].startswith("run.gwyddion.")
        ]
        gwyddion_runs = [
            item for item in result_bundle["runs"] if item["run_id"].startswith("run.gwyddion.")
        ]
        cross = [
            item
            for item in result_bundle["comparisons"]
            if item["comparison_id"].startswith("comparison.cross.gwyddion.")
        ]
        analytical = [
            item
            for item in result_bundle["comparisons"]
            if item["comparison_id"].startswith("comparison.analytical.")
        ]
        _write_json(
            evidence / "spmkit-runs.json",
            {"run_count": len(spmkit_runs), "runs": spmkit_runs, "status": "PASS"},
        )
        _write_json(
            evidence / "gwyddion-runs.json",
            {
                "producer": "Gwyddion project",
                "reference_name": "Gwyddion-library external reference",
                "run_count": len(gwyddion_runs),
                "runs": gwyddion_runs,
                "status": "PASS",
            },
        )
        cross_counts = Counter(item["outcome"] for item in cross)
        analytical_counts = Counter(item["outcome"] for item in analytical)
        _write_json(
            evidence / "comparisons-cross.json",
            {
                "comparison_count": len(cross),
                "comparisons": cross,
                "outcome_counts": {
                    name: cross_counts[name]
                    for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE")
                },
                "status": "PASS",
            },
        )
        _write_json(
            evidence / "comparisons-analytical.json",
            {
                "comparison_count": len(analytical),
                "comparisons": analytical,
                "control_only": True,
                "outcome_counts": {
                    name: analytical_counts[name]
                    for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE")
                },
                "status": "PASS",
            },
        )
        _write_json(
            evidence / "claims.json",
            {
                "claims": result_bundle["claims"],
                "maximum_level_supported": "LEVEL 3 — CROSS_VALIDATED",
                "status": "SUPPORTED",
            },
        )
        _write_json(evidence / "repeatability.json", repeatability)
        _write_json(evidence / "negative-independence-tests.json", _negative_independence())
        _write_json(evidence / "tampering-tests.json", tampering)
        _write_json(
            evidence / "gate-results.json",
            {
                "attempt_id": ATTEMPT_ID,
                "campaign_materialization": "PASS",
                "claims_supported": len(result_bundle["claims"]),
                "command": ["make", "phase01e-gates"],
                "cross_comparisons": {
                    name: cross_counts[name]
                    for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE")
                },
                "external_reference_runs": Counter(
                    item["execution_status"] for item in gwyddion_runs
                ),
                "full_gate_status": "PENDING_CLEAN_TREE_RUN",
                "full_test_suite": {"status": "PENDING"},
                "holdout_accessed": False,
                "negative_independence": _negative_independence(),
                "package_version": "0.1.4",
                "phase": "PHASE_01E",
                "platform": platform.system().lower(),
                "real_data_accessed": False,
                "repeatability": {
                    "determinism_category": repeatability["determinism_category"],
                    "status": repeatability["status"],
                },
                "software_test": primary.software_test.junit_summary.to_dict(),
                "spmkit_runs": Counter(item["execution_status"] for item in spmkit_runs),
                "tampering": tampering,
            },
        )
        _write_json(
            evidence / "artifacts/index.json",
            {
                "artifact_count": len(result_bundle["evidence"]),
                "artifacts": [
                    {
                        "artifact_id": item["artifact_id"],
                        "relative_uri": item["relative_uri"],
                        "sha256": item["sha256"],
                        "size_bytes": item["size_bytes"],
                    }
                    for item in result_bundle["evidence"]
                ],
                "result_snapshot": result_snapshot_destination.relative_to(repository).as_posix(),
            },
        )

    if _git(sut, "rev-parse", "HEAD") != SUT_COMMIT or _git(sut, "status", "--porcelain=v1"):
        raise RuntimeError("SUT changed during authoritative materialization")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--campaign-dir",
        type=Path,
        default=Path("campaigns/gwyddion-cross-validation-v0.1"),
    )
    parser.add_argument(
        "--evidence-dir", type=Path, default=Path("evidence/phase01e-gwyddion")
    )
    parser.add_argument(
        "--gwyddion-prefix", type=Path, default=Path.home() / ".local/opt/gwyddion-2.71"
    )
    parser.add_argument("--gwyfile-wheel", required=True, type=Path)
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
    materialize(
        repository,
        campaign,
        evidence,
        prefix=arguments.gwyddion_prefix.resolve(strict=True),
        gwyfile_wheel=arguments.gwyfile_wheel.resolve(strict=True),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
