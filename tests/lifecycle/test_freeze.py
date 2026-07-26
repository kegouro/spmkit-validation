from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import spmkit_validation.lifecycle.freeze as freeze_module
from spmkit_validation.lifecycle import LifecycleError, freeze_bundle
from spmkit_validation.schemas import assert_valid_bundle, load_validation_bundle

from .conftest import FREEZE_TIME, write_bundle


def _codes(error: LifecycleError) -> set[str]:
    return {issue.code for issue in error.issues}


def test_valid_draft_freezes_to_content_addressed_layout(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    assert result.snapshot_path.name == "bundle.json"
    assert result.receipt_path.name == "freeze-receipt.json"
    assert result.snapshot_path.parent.name == result.bundle_sha256
    assert result.snapshot_path.is_file()
    assert result.receipt_path.is_file()


def test_source_bundle_remains_byte_for_byte_unchanged(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    before = draft_bundle_path.read_bytes()
    freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    assert draft_bundle_path.read_bytes() == before


def test_output_publication_uses_exclusive_files(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "snapshots"
    result = freeze_bundle(draft_bundle_path, artifact_root, output, FREEZE_TIME)
    assert sorted(path.name for path in result.snapshot_path.parent.iterdir()) == [
        "bundle.json",
        "freeze-receipt.json",
    ]
    assert not list(output.glob(".spmkit-freeze-*"))


def test_existing_snapshot_is_never_overwritten(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "snapshots"
    first = freeze_bundle(draft_bundle_path, artifact_root, output, FREEZE_TIME)
    snapshot_before = first.snapshot_path.read_bytes()
    receipt_before = first.receipt_path.read_bytes()
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(draft_bundle_path, artifact_root, output, FREEZE_TIME)
    assert "FREEZE.OUTPUT_EXISTS" in _codes(caught.value)
    assert first.snapshot_path.read_bytes() == snapshot_before
    assert first.receipt_path.read_bytes() == receipt_before


def test_frozen_bundle_cannot_be_frozen_again(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    first = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "first", FREEZE_TIME)
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(first.snapshot_path, artifact_root, tmp_path / "second", FREEZE_TIME)
    assert "FREEZE.CAMPAIGN_NOT_DRAFT" in _codes(caught.value)


@pytest.mark.parametrize(
    ("collection", "record"),
    [
        ("runs", {"run_id": "run.synthetic.forbidden"}),
        ("comparisons", {"comparison_id": "comparison.synthetic.forbidden"}),
        (
            "claims",
            {
                "claim_id": "claim.synthetic.forbidden",
                "status": "SUPPORTED",
            },
        ),
    ],
)
def test_evaluated_content_cannot_be_frozen(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
    collection: str,
    record: dict[str, str],
) -> None:
    draft_bundle[collection].append(record)
    write_bundle(draft_bundle_path, draft_bundle)
    with pytest.raises(LifecycleError):
        freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)


def test_tolerance_declared_after_freeze_is_rejected(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
) -> None:
    draft_bundle["cases"][0]["predeclared_at"] = "2026-02-02T00:00:00Z"
    write_bundle(draft_bundle_path, draft_bundle)
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    assert "TOLERANCE.NOT_PREDECLARED" in _codes(caught.value)


def test_artifact_mismatch_prevents_freeze(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
) -> None:
    draft_bundle["evidence"][0]["sha256"] = "0" * 64
    write_bundle(draft_bundle_path, draft_bundle)
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    assert "ARTIFACT_SHA256_MISMATCH" in _codes(caught.value)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-02-01T00:00:00",
        "2026-02-01T01:00:00+01:00",
        "2026-02-30T00:00:00Z",
        "not-a-timestamp",
    ],
)
def test_non_utc_or_invalid_timestamp_is_rejected(
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
    timestamp: str,
) -> None:
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", timestamp)
    assert "FREEZE.INVALID_FROZEN_AT" in _codes(caught.value)


def test_intermediate_failure_publishes_no_partial_snapshot(
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "snapshots"
    original_write = freeze_module._write_exclusive
    calls = 0

    def fail_second_write(path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic publication failure")
        original_write(path, content)

    monkeypatch.setattr(freeze_module, "_write_exclusive", fail_second_write)
    with pytest.raises(LifecycleError) as caught:
        freeze_bundle(draft_bundle_path, artifact_root, output, FREEZE_TIME)
    assert "FREEZE.PUBLICATION_FAILED" in _codes(caught.value)
    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_frozen_bundle_still_passes_schema_and_semantics(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    result = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    frozen = load_validation_bundle(result.snapshot_path)
    assert frozen["campaign"]["status"] == "FROZEN"
    assert frozen["campaign"]["frozen_at"] == FREEZE_TIME
    assert_valid_bundle(frozen)


def test_freeze_does_not_mutate_supplied_document_fixture(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    tmp_path: Path,
) -> None:
    before = copy.deepcopy(draft_bundle)
    freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    assert draft_bundle == before
