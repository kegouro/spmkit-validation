from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import (
    FreezeReceipt,
    canonical_bundle_bytes,
    freeze_bundle,
    verify_frozen_snapshot,
)
from spmkit_validation.lifecycle.receipt import validate_freeze_receipt

from .conftest import FREEZE_TIME


def _freeze(draft_bundle_path: Path, artifact_root: Path, output: Path):
    return freeze_bundle(draft_bundle_path, artifact_root, output, FREEZE_TIME)


def _rewrite_snapshot(path: Path, mutate: Any) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_bytes(canonical_bundle_bytes(document))


def test_valid_receipt_passes_operational_schema(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    document = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert validate_freeze_receipt(document) == ()
    receipt = FreezeReceipt.from_dict(document)
    assert receipt.snapshot_type == "TAMPER_EVIDENT_SNAPSHOT"
    assert receipt.receipt_version == "0.1.0"


def test_receipt_is_canonical_and_newline_terminated(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    raw = result.receipt_path.read_bytes()
    assert raw == result.receipt.canonical_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")


def test_tolerance_modification_is_detected(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    _rewrite_snapshot(
        result.snapshot_path,
        lambda bundle: bundle["cases"][0]["tolerances"][0].update({"absolute": 1.0}),
    )
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path)
    assert verified.status == "SNAPSHOT_HASH_MISMATCH"


def test_sut_commit_modification_is_detected(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    _rewrite_snapshot(
        result.snapshot_path,
        lambda bundle: bundle["campaign"]["system_under_test"].update({"git_commit": "f" * 40}),
    )
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path)
    assert verified.status == "SNAPSHOT_HASH_MISMATCH"


def test_whitespace_modification_is_detected_as_noncanonical(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    result.snapshot_path.write_bytes(result.snapshot_path.read_bytes() + b"\n")
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path)
    assert verified.status == "SNAPSHOT_NONCANONICAL"
    assert "SNAPSHOT_NONCANONICAL" in {issue.code for issue in verified.issues}


def test_modified_receipt_is_detected(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    receipt["limitations"].append("Synthetic receipt mutation.")
    result.receipt_path.write_bytes(canonical_bundle_bytes(receipt))
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path)
    assert verified.status == "RECEIPT_INVALID"
    assert "RECEIPT_HASH_MISMATCH" in {issue.code for issue in verified.issues}


def test_truncated_bundle_is_detected(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    raw = result.snapshot_path.read_bytes()
    result.snapshot_path.write_bytes(raw[: len(raw) // 2])
    assert (
        verify_frozen_snapshot(result.snapshot_path, result.receipt_path).status == "BUNDLE_INVALID"
    )


def test_valid_snapshot_without_artifact_root(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path)
    assert verified.status == "SNAPSHOT_VALID"
    assert verified.artifact_status == "ARTIFACT_NOT_VERIFIED"


def test_valid_snapshot_with_artifact_reverification(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path, artifact_root)
    assert verified.status == "SNAPSHOT_VALID"
    assert verified.artifact_status == "PASS"


def test_artifact_changed_after_freeze_is_detected(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = _freeze(draft_bundle_path, artifact_root, tmp_path / "snapshots")
    protocol = artifact_root / "protocol.txt"
    protocol.write_bytes(protocol.read_bytes() + b"tampered\n")
    verified = verify_frozen_snapshot(result.snapshot_path, result.receipt_path, artifact_root)
    assert verified.status == "ARTIFACT_MISMATCH"
    assert verified.artifact_status == "ARTIFACT_MISMATCH"
