from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

from spmkit_validation.execution import (
    CampaignExecutionError,
    CumulativeExecutionResult,
    compare_campaign_repetition,
    execute_frozen_campaign,
    execute_software_test,
    populate_cumulative_result_bundle,
    verify_protocol_continuity,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.schemas import assert_valid_bundle, validate_semantics

from .conftest import write_fake_spmkit
from .test_software_verification import _frozen


def _codes(bundle: dict) -> set[str]:
    return {issue.code for issue in validate_semantics(bundle)}


def _populated(tmp_path: Path, *, software_failure: bool = False):
    prepared, frozen, wheel, environment = _frozen(tmp_path, failure=software_failure)
    software = execute_software_test(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        installed_environment=environment,
        output_dir=prepared.output_dir / "execution/software-test",
    )
    scientific = execute_frozen_campaign(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        output_dir=prepared.output_dir / "execution/scientific",
        sut_executable=write_fake_spmkit(tmp_path / "fake-spmkit"),
    )
    cumulative = CumulativeExecutionResult(
        software_test=software,
        scientific=scientific,
        started_at=software.started_at,
        completed_at=scientific.completed_at,
        wheel_sha256=scientific.wheel_sha256,
        wheel_size_bytes=scientific.wheel_size_bytes,
    )
    truth = json.loads(prepared.ground_truth_path.read_text(encoding="utf-8"))
    frozen_bundle = json.loads(frozen.snapshot_path.read_text(encoding="utf-8"))
    populated = populate_cumulative_result_bundle(frozen_bundle, cumulative, truth)
    return prepared, frozen, cumulative, populated


def test_cumulative_population_supports_level_1_and_level_2(tmp_path: Path) -> None:
    _, _, cumulative, bundle = _populated(tmp_path)

    assert_valid_bundle(bundle)
    assert len(bundle["runs"]) == 7
    assert bundle["runs"][0]["run_type"] == "SOFTWARE_TEST"
    assert len(bundle["comparisons"]) == 18
    assert {item["outcome"] for item in bundle["comparisons"]} == {"PASS"}
    claims = {claim["claim_id"]: claim for claim in bundle["claims"]}
    assert claims["claim.software.roughness-wheel"]["level"] == "LEVEL 1 — SOFTWARE_VERIFIED"
    assert claims["claim.software.roughness-wheel"]["status"] == "SUPPORTED"
    assert {claims[f"claim.synthetic.{name}"]["level"] for name in ("Sa", "Sq", "Sz")} == {
        "LEVEL 2 — NUMERICALLY_VERIFIED"
    }
    assert {claims[f"claim.synthetic.{name}"]["status"] for name in ("Sa", "Sq", "Sz")} == {
        "SUPPORTED"
    }
    assert cumulative.software_test.wheel_sha256 == cumulative.scientific.wheel_sha256


def test_eighteen_pass_without_software_test_cannot_support_level_2(tmp_path: Path) -> None:
    _, _, _, bundle = _populated(tmp_path)
    unsupported = copy.deepcopy(bundle)
    unsupported["runs"] = [run for run in unsupported["runs"] if run["run_type"] != "SOFTWARE_TEST"]

    assert len(unsupported["comparisons"]) == 18
    assert {item["outcome"] for item in unsupported["comparisons"]} == {"PASS"}
    assert "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT" in _codes(unsupported)


def test_failed_junit_blocks_level_1_and_level_2(tmp_path: Path) -> None:
    _, _, _, bundle = _populated(tmp_path, software_failure=True)
    assert bundle["runs"][0]["execution_status"] == "ERROR"
    assert {claim["status"] for claim in bundle["claims"]} == {"REJECTED"}

    contradicted = copy.deepcopy(bundle)
    for claim in contradicted["claims"]:
        claim["status"] = "SUPPORTED"
    assert "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT" in _codes(contradicted)


def test_missing_junit_is_preserved_as_valid_rejected_result(tmp_path: Path) -> None:
    prepared, frozen, cumulative, _ = _populated(tmp_path)
    software_run = copy.deepcopy(dict(cumulative.software_test.run))
    software_run["output_artifact_ids"].remove("artifact.software-test.junit")
    software_run["execution_status"] = "ERROR"
    software_run["errors"] = [
        {"code": "JUNIT_MISSING", "message": "pytest did not produce JUnit XML"}
    ]
    evidence = [
        copy.deepcopy(dict(item))
        for item in cumulative.software_test.evidence
        if item["artifact_id"] != "artifact.software-test.junit"
    ]
    run_record = next(
        item
        for item in evidence
        if item["artifact_id"] == "artifact.software-test.run-record"
    )
    run_record["source_artifact_ids"].remove("artifact.software-test.junit")
    software = replace(
        cumulative.software_test,
        run=software_run,
        evidence=tuple(evidence),
        junit_summary=None,
    )
    failed = replace(cumulative, software_test=software)
    frozen_bundle = json.loads(frozen.snapshot_path.read_text(encoding="utf-8"))
    truth = json.loads(prepared.ground_truth_path.read_text(encoding="utf-8"))

    bundle = populate_cumulative_result_bundle(frozen_bundle, failed, truth)

    assert_valid_bundle(bundle)
    assert {claim["status"] for claim in bundle["claims"]} == {"REJECTED"}
    assert all(
        "artifact.software-test.junit" not in claim["supported_evidence_ids"]
        for claim in bundle["claims"]
    )


def test_level_1_without_linked_junit_evidence_is_rejected(tmp_path: Path) -> None:
    _, _, _, bundle = _populated(tmp_path)
    unsupported = copy.deepcopy(bundle)
    software_run = unsupported["runs"][0]
    software_run["output_artifact_ids"].remove("artifact.software-test.junit")

    assert "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT" in _codes(unsupported)


def test_cumulative_protocol_continuity_rejects_deleted_software_case(tmp_path: Path) -> None:
    _, frozen, _, bundle = _populated(tmp_path)
    drifted = copy.deepcopy(bundle)
    drifted["cases"] = [
        case for case in drifted["cases"] if case["case_id"] != "case.software.roughness-wheel"
    ]
    frozen_bundle = json.loads(frozen.snapshot_path.read_text(encoding="utf-8"))

    try:
        verify_protocol_continuity(frozen_bundle, drifted)
    except CampaignExecutionError as exc:
        assert "PROTOCOL.CASES_SET_DRIFT" in {issue.code for issue in exc.issues}
    else:
        raise AssertionError("deleted frozen software case was accepted")


def test_cumulative_scientific_repeatability_ignores_authorized_timing(tmp_path: Path) -> None:
    _, _, _, bundle = _populated(tmp_path)
    repeated = copy.deepcopy(bundle)
    for run in repeated["runs"]:
        run["started_at"] = "2026-07-26T10:00:00Z"
        run["finished_at"] = "2026-07-26T10:00:01Z"
    record = compare_campaign_repetition(bundle, repeated)
    assert record["status"] == "PASS"
    assert record["determinism_category"] == "NUMERICALLY_REPEATABLE"

    repeated["comparisons"][0]["observed"] = 1.0
    assert compare_campaign_repetition(bundle, repeated)["status"] == "FAIL"


def test_cumulative_receipt_records_software_hashes_and_detects_junit_tampering(
    tmp_path: Path,
) -> None:
    prepared, frozen, cumulative, bundle = _populated(tmp_path)
    published = write_execution_receipt(
        bundle,
        frozen_protocol_path=frozen.snapshot_path,
        freeze_receipt_path=frozen.receipt_path,
        artifact_root=prepared.output_dir,
        output_dir=prepared.output_dir / "execution/result-snapshot",
        wheel_sha256=cumulative.wheel_sha256,
        started_at=cumulative.started_at,
        completed_at=cumulative.completed_at,
    )
    software = published.receipt.software_verification
    assert software is not None
    assert software["software_test_run_id"] == "run.software.roughness-wheel"
    assert len(software["scientific_run_ids"]) == 6
    verified = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verified.valid

    junit_artifact = next(
        item for item in bundle["evidence"] if item["artifact_id"] == "artifact.software-test.junit"
    )
    junit_path = prepared.output_dir / junit_artifact["relative_uri"]
    junit_path.write_bytes(junit_path.read_bytes() + b"\n")
    tampered = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert tampered.status == "ARTIFACT_MISMATCH"


def test_cumulative_result_detects_wheel_artifact_tampering(tmp_path: Path) -> None:
    prepared, frozen, cumulative, bundle = _populated(tmp_path)
    published = write_execution_receipt(
        bundle,
        frozen_protocol_path=frozen.snapshot_path,
        freeze_receipt_path=frozen.receipt_path,
        artifact_root=prepared.output_dir,
        output_dir=prepared.output_dir / "execution/result-snapshot",
        wheel_sha256=cumulative.wheel_sha256,
        started_at=cumulative.started_at,
        completed_at=cumulative.completed_at,
    )
    wheel_artifact = next(
        item for item in bundle["evidence"] if item["artifact_id"] == "artifact.execution.sut-wheel"
    )
    wheel_path = prepared.output_dir / wheel_artifact["relative_uri"]
    wheel_path.write_bytes(wheel_path.read_bytes() + b"tamper")

    verified = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verified.status == "ARTIFACT_MISMATCH"
