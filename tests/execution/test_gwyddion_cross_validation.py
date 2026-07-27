from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from spmkit_validation.execution import (
    GwyddionCrossValidationExecutionResult,
    compare_gwyddion_cross_repetition,
    execute_frozen_campaign,
    execute_software_test,
    prepare_gwyddion_cross_validation_campaign,
    verify_protocol_continuity,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.execution.gwyddion_population import (
    populate_gwyddion_cross_validation_result_bundle,
)
from spmkit_validation.lifecycle import canonical_bundle_bytes, freeze_bundle
from spmkit_validation.schemas import assert_valid_bundle, validate_semantics

from .conftest import write_fake_spmkit
from .test_software_verification import _fake_environment, _suite_repository


def _external_helper(path: Path) -> Path:
    path.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import os
import sys

if os.environ.get("LC_ALL") != "C" or "DISPLAY" in os.environ:
    raise SystemExit(19)
input_path = sys.argv[-1]
name = input_path.rsplit("/", 1)[-1]
resolution = 16 if "16x16" in name else 32
if ".flat." in name:
    values = {"mean": 0.0, "Sa": 0.0, "Sq": 0.0, "min": 0.0, "max": 0.0, "Sz": 0.0}
elif ".checkerboard." in name:
    values = {"mean": 0.0, "Sa": 1e-9, "Sq": 1e-9, "min": -1e-9, "max": 1e-9, "Sz": 2e-9}
else:
    values = {"mean": 0.0, "Sa": 2e-9, "Sq": 5**0.5*1e-9, "min": -3e-9, "max": 3e-9, "Sz": 6e-9}
document = {
    "schema": "spmkit-gwyddion-reference-output/0.1.0",
    "status": "COMPLETED",
    "producer": "Gwyddion libraries",
    "gwyddion_version": "2.71",
    "helper_version": "0.1.0",
    "input_sha256": hashlib.sha256(open(input_path, "rb").read()).hexdigest(),
    "channel": 0,
    "shape": [resolution, resolution],
    "axis_order": "ROW_Y_COLUMN_X",
    "unit_z": "m",
    "unit_source": "GWYDDION_DATA_FIELD",
    "preprocessing": {"leveling":"NONE","filtering":"NONE","masking":"NONE","roi":"FULL_FIELD"},
    **values,
}
print(json.dumps(document, sort_keys=True, separators=(",", ":")))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_json(path: Path, document: dict[str, object]) -> Path:
    path.write_bytes(canonical_bundle_bytes(document))
    return path


def _cross_populated(tmp_path: Path, monkeypatch):
    repository, commit = _suite_repository(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    helper = _external_helper(records / "gwyddion-helper")
    source = records / "helper.c"
    source.write_bytes(b"/* frozen test helper source; no SPM-Kit code */\n")
    identity = _write_json(
        records / "identity.json",
        {
            "reported_version": "2.71",
            "producer_is_third_party": True,
            "executable": {"sha256": "1" * 64, "size_bytes": 1},
            "libraries": {"gwyddion": "2.71"},
        },
    )
    viability = _write_json(
        records / "viability.json",
        {
            "status": "PASS_INSTALLED_REFERENCE",
            "tolerances_derived_from_probe": False,
        },
    )
    build = _write_json(
        records / "build.json",
        {
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "binary_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        },
    )
    dependency = records / "gwyfile.whl"
    dependency.write_bytes(b"frozen fake gwyfile wheel")
    monkeypatch.setattr(
        "spmkit_validation.execution.gwyddion_protocol.GWYFILE_WHEEL_SHA256",
        hashlib.sha256(dependency.read_bytes()).hexdigest(),
    )
    prepared = prepare_gwyddion_cross_validation_campaign(
        tmp_path / "campaign",
        sut_repository=repository,
        sut_commit=commit,
        gwyddion_identity=identity,
        installed_viability=viability,
        helper_source=source,
        helper_binary=helper,
        helper_build_record=build,
        gwyfile_wheel=dependency,
    )
    frozen = freeze_bundle(
        prepared.bundle_path,
        prepared.output_dir,
        tmp_path / "snapshots",
        frozen_at="2026-07-26T08:02:00Z",
    )
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"synthetic wheel identity")
    environment = _fake_environment(tmp_path, wheel)
    software = execute_software_test(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        installed_environment=environment,
        output_dir=prepared.output_dir / "execution/software-test",
    )
    spmkit = execute_frozen_campaign(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        output_dir=prepared.output_dir / "execution/spmkit",
        sut_executable=write_fake_spmkit(tmp_path / "fake-spmkit"),
    )
    library = tmp_path / "lib"
    modules = tmp_path / "modules"
    library.mkdir()
    modules.mkdir()
    from spmkit_validation.adapters.gwyddion.library_runner import (
        execute_gwyddion_library_reference,
    )

    frozen_bundle = json.loads(frozen.snapshot_path.read_text())
    external = execute_gwyddion_library_reference(
        frozen_bundle,
        artifact_root=prepared.output_dir,
        helper_executable=prepared.helper_binary_path,
        gwyddion_library_dir=library,
        gwyddion_module_dir=modules,
        output_dir=prepared.output_dir / "execution/gwyddion",
    )
    execution = GwyddionCrossValidationExecutionResult(
        software_test=software,
        spmkit=spmkit,
        external_reference=external,
        started_at=software.started_at,
        completed_at=external.completed_at,
        wheel_sha256=spmkit.wheel_sha256,
        wheel_size_bytes=spmkit.wheel_size_bytes,
    )
    truth = json.loads(prepared.ground_truth_path.read_text())
    bundle = populate_gwyddion_cross_validation_result_bundle(
        frozen_bundle, execution, truth
    )
    return prepared, frozen, execution, bundle


def test_cross_population_has_13_runs_54_comparisons_and_level3(
    tmp_path: Path, monkeypatch
) -> None:
    _, _, _, bundle = _cross_populated(tmp_path, monkeypatch)

    assert_valid_bundle(bundle)
    assert len(bundle["runs"]) == 13
    assert len(bundle["comparisons"]) == 54
    cross = [
        item
        for item in bundle["comparisons"]
        if item["comparison_id"].startswith("comparison.cross.gwyddion.")
    ]
    assert len(cross) == 18
    assert {item["outcome"] for item in cross} == {"PASS"}
    claims = {item["claim_id"]: item for item in bundle["claims"]}
    assert claims["claim.software.roughness-wheel"]["status"] == "SUPPORTED"
    for measurand in ("Sa", "Sq", "Sz"):
        assert claims[f"claim.synthetic.{measurand}"]["status"] == "SUPPORTED"
        level3 = claims[f"claim.crossvalidated.gwyddion.{measurand}"]
        assert level3["level"] == "LEVEL 3 — CROSS_VALIDATED"
        assert level3["status"] == "SUPPORTED"


def test_external_fail_is_preserved_and_rejects_only_level3(
    tmp_path: Path, monkeypatch
) -> None:
    prepared, frozen, execution, _ = _cross_populated(tmp_path, monkeypatch)
    observations = copy.deepcopy(execution.external_reference.observations)
    observations["case.synthetic.checkerboard.16x16"]["Sa"] = 5e-9
    failed_external = replace(execution.external_reference, observations=observations)
    failed = replace(execution, external_reference=failed_external)
    protocol = json.loads(frozen.snapshot_path.read_text())
    truth = json.loads(prepared.ground_truth_path.read_text())

    bundle = populate_gwyddion_cross_validation_result_bundle(protocol, failed, truth)
    failed_comparison = next(
        item
        for item in bundle["comparisons"]
        if item["comparison_id"]
        == "comparison.cross.gwyddion.case.synthetic.checkerboard.16x16.Sa"
    )

    assert failed_comparison["outcome"] == "FAIL"
    claims = {item["claim_id"]: item for item in bundle["claims"]}
    assert claims["claim.crossvalidated.gwyddion.Sa"]["status"] == "REJECTED"
    assert claims["claim.synthetic.Sa"]["status"] == "SUPPORTED"


def test_external_error_is_preserved_and_never_supports_level3(
    tmp_path: Path, monkeypatch
) -> None:
    prepared, frozen, execution, _ = _cross_populated(tmp_path, monkeypatch)
    runs = [copy.deepcopy(dict(item)) for item in execution.external_reference.runs]
    runs[0]["execution_status"] = "ERROR"
    runs[0]["errors"] = [{"code": "GWYDDION_ERROR", "message": "preserved failure"}]
    observations = copy.deepcopy(execution.external_reference.observations)
    observations.pop(runs[0]["case_ids"][0])
    failed_external = replace(
        execution.external_reference,
        runs=tuple(runs),
        observations=observations,
    )
    failed = replace(execution, external_reference=failed_external)
    protocol = json.loads(frozen.snapshot_path.read_text())
    truth = json.loads(prepared.ground_truth_path.read_text())

    bundle = populate_gwyddion_cross_validation_result_bundle(protocol, failed, truth)

    assert any(item["outcome"] == "ERROR" for item in bundle["comparisons"])
    assert bundle["campaign"]["status"] == "ABORTED"
    assert all(
        item["status"] == "REJECTED"
        for item in bundle["claims"]
        if item["level"] == "LEVEL 3 — CROSS_VALIDATED"
    )


def test_protocol_continuity_rejects_external_reference_drift(
    tmp_path: Path, monkeypatch
) -> None:
    _, frozen, _, bundle = _cross_populated(tmp_path, monkeypatch)
    protocol = json.loads(frozen.snapshot_path.read_text())
    drifted = copy.deepcopy(bundle)
    reference = next(
        item
        for item in drifted["references"]
        if item["reference_id"] == "reference.external.gwyddion-library.roughness"
    )
    reference["version"] = "2.70"

    try:
        verify_protocol_continuity(protocol, drifted)
    except Exception as exc:
        assert "REFERENCE" in str(exc).upper()
    else:
        raise AssertionError("external reference drift was accepted")


def test_semantics_reject_supported_level3_after_third_party_removed(
    tmp_path: Path, monkeypatch
) -> None:
    _, _, _, bundle = _cross_populated(tmp_path, monkeypatch)
    reference = next(
        item
        for item in bundle["references"]
        if item["reference_id"] == "reference.external.gwyddion-library.roughness"
    )
    reference["producer"]["is_third_party"] = False

    codes = {item.code for item in validate_semantics(bundle)}
    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in codes


def test_cross_repeatability_retains_both_producers_units_hashes_and_exit_codes(
    tmp_path: Path, monkeypatch
) -> None:
    _, _, _, bundle = _cross_populated(tmp_path, monkeypatch)
    repeated = copy.deepcopy(bundle)
    for run in repeated["runs"]:
        run["started_at"] = "2026-07-27T10:00:00Z"
        run["finished_at"] = "2026-07-27T10:00:01Z"

    record = compare_gwyddion_cross_repetition(bundle, repeated)

    assert record["status"] == "PASS"
    assert record["spmkit_values_compared"] == 18
    assert record["gwyddion_values_compared"] == 18
    assert record["units_compared"] == 18
    assert record["input_hashes_compared"] == 6
    assert record["exit_codes_compared"] == 13
    assert record["level_5_claimed"] is False
    repeated["comparisons"][0]["reference"] = 99.0
    assert compare_gwyddion_cross_repetition(bundle, repeated)["status"] == "FAIL"


def _publish(tmp_path: Path, monkeypatch):
    prepared, frozen, execution, bundle = _cross_populated(tmp_path, monkeypatch)
    published = write_execution_receipt(
        bundle,
        frozen_protocol_path=frozen.snapshot_path,
        freeze_receipt_path=frozen.receipt_path,
        artifact_root=prepared.output_dir,
        output_dir=prepared.output_dir / "execution/result-snapshot",
        wheel_sha256=execution.wheel_sha256,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )
    return prepared, frozen, bundle, published


def test_execution_receipt_records_external_identity_and_run_counts(
    tmp_path: Path, monkeypatch
) -> None:
    prepared, frozen, _, published = _publish(tmp_path, monkeypatch)

    external = published.receipt.external_reference
    assert external is not None
    assert external["producer_is_third_party"] is True
    assert external["independence_assessment"] == "INDEPENDENT"
    assert external["gwyddion_version"] == "2.71"
    assert len(external["external_run_ids"]) == 6
    assert external["external_comparison_count"] == 18
    assert len(external["helper_binary_sha256"]) == 64
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.valid


def test_gwyddion_output_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item
        for item in bundle["evidence"]
        if item["artifact_id"].startswith("artifact.gwyddion-output.")
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert verification.status == "ARTIFACT_MISMATCH"


def test_independence_assessment_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item
        for item in bundle["evidence"]
        if item["artifact_id"] == "artifact.reference.independence-assessment"
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert not verification.valid


def test_gwyddion_version_record_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item
        for item in bundle["evidence"]
        if item["artifact_id"] == "artifact.reference.gwyddion-identity"
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert not verification.valid


def test_interchange_input_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item for item in bundle["evidence"] if item["artifact_id"].startswith("artifact.input.")
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert not verification.valid


def test_frozen_tolerance_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item
        for item in bundle["evidence"]
        if item["artifact_id"] == "artifact.protocol.tolerance-budget"
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert not verification.valid


def test_sut_wheel_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, bundle, published = _publish(tmp_path, monkeypatch)
    artifact = next(
        item
        for item in bundle["evidence"]
        if item["artifact_id"] == "artifact.execution.sut-wheel"
    )
    path = prepared.output_dir / artifact["relative_uri"]
    path.write_bytes(path.read_bytes() + b"tamper")

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert verification.status == "ARTIFACT_MISMATCH"


def test_result_receipt_tampering_is_detected(tmp_path: Path, monkeypatch) -> None:
    prepared, frozen, _, published = _publish(tmp_path, monkeypatch)
    published.execution_receipt_path.write_bytes(
        published.execution_receipt_path.read_bytes() + b"tamper"
    )

    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )

    assert verification.status == "EXECUTION_RECEIPT_INVALID"
