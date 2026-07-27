from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from spmkit_validation.execution import (
    compare_campaign_repetition,
    execute_frozen_campaign,
    populate_result_bundle,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.lifecycle import canonical_bundle_bytes

from .conftest import write_fake_spmkit


def _snapshot(frozen_protocol: Any, tmp_path: Path, name: str = "first"):
    prepared, frozen = frozen_protocol
    wheel = tmp_path / "sut.whl"
    if not wheel.exists():
        wheel.write_bytes(b"wheel fixture")
    executable = write_fake_spmkit(tmp_path / f"spmkit-{name}")
    execution = execute_frozen_campaign(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        output_dir=prepared.output_dir / name,
        sut_executable=executable,
    )
    frozen_bundle = json.loads(frozen.snapshot_path.read_text(encoding="utf-8"))
    truth = json.loads(prepared.ground_truth_path.read_text(encoding="utf-8"))
    result = populate_result_bundle(frozen_bundle, execution, truth)
    published = write_execution_receipt(
        result,
        frozen_protocol_path=frozen.snapshot_path,
        freeze_receipt_path=frozen.receipt_path,
        artifact_root=prepared.output_dir,
        output_dir=tmp_path / f"snapshots-{name}",
        wheel_sha256=execution.wheel_sha256,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )
    return prepared, frozen, result, execution, published


def test_valid_result_receipt_and_snapshot(frozen_protocol: Any, tmp_path: Path) -> None:
    prepared, frozen, _, _, published = _snapshot(frozen_protocol, tmp_path)
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.valid


def test_result_hash_mismatch_and_tolerance_tampering_detected(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    prepared, frozen, result, _, published = _snapshot(frozen_protocol, tmp_path)
    result["cases"][0]["tolerances"][0]["absolute"] = 9.0
    published.result_bundle_path.write_bytes(canonical_bundle_bytes(result))
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.status in {
        "RESULT_HASH_MISMATCH",
        "RESULT_SIZE_MISMATCH",
        "PROTOCOL_DRIFT",
    }


def test_result_whitespace_and_truncation_detected(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    prepared, frozen, _, _, published = _snapshot(frozen_protocol, tmp_path)
    published.result_bundle_path.write_bytes(published.result_bundle_path.read_bytes() + b"\n")
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.status == "RESULT_NONCANONICAL"
    published.result_bundle_path.write_bytes(b'{"schema_version":')
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.status == "RESULT_BUNDLE_INVALID"


def test_receipt_modification_detected(frozen_protocol: Any, tmp_path: Path) -> None:
    prepared, frozen, _, _, published = _snapshot(frozen_protocol, tmp_path)
    receipt = json.loads(published.execution_receipt_path.read_text(encoding="utf-8"))
    receipt["case_count"] = 99
    published.execution_receipt_path.write_bytes(canonical_bundle_bytes(receipt))
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert verification.status == "EXECUTION_RECEIPT_INVALID"


def test_protocol_hash_mismatch_detected(frozen_protocol: Any, tmp_path: Path) -> None:
    prepared, frozen, _, _, published = _snapshot(frozen_protocol, tmp_path)
    frozen.snapshot_path.write_bytes(frozen.snapshot_path.read_bytes() + b"\n")
    verification = verify_result_snapshot(
        published.result_bundle_path,
        published.execution_receipt_path,
        frozen.snapshot_path,
        frozen.receipt_path,
        prepared.output_dir,
    )
    assert not verification.valid


def test_artifact_tampering_detected(frozen_protocol: Any, tmp_path: Path) -> None:
    prepared, frozen, result, _, published = _snapshot(frozen_protocol, tmp_path)
    artifact = next(
        item
        for item in result["evidence"]
        if item["artifact_id"].startswith("artifact.result-json")
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


def test_repetition_ignores_timestamps_but_detects_scientific_divergence(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    _, _, first, _, _ = _snapshot(frozen_protocol, tmp_path, "first")
    _, _, second, _, _ = _snapshot(frozen_protocol, tmp_path, "second")
    record = compare_campaign_repetition(first, second)
    assert record["status"] == "PASS"
    assert record["determinism_category"] == "NUMERICALLY_REPEATABLE"
    changed = copy.deepcopy(second)
    changed["comparisons"][0]["observed"] = 1.0
    assert compare_campaign_repetition(first, changed)["status"] == "FAIL"
