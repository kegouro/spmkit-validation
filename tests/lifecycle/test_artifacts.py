from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

import spmkit_validation.lifecycle.artifacts as artifact_module
from spmkit_validation.lifecycle import LifecycleError, verify_artifacts


def _result(bundle: dict[str, Any], root: Path, artifact_id: str):
    return next(
        result for result in verify_artifacts(bundle, root) if result.artifact_id == artifact_id
    )


def _codes(result: Any) -> set[str]:
    return {issue.code for issue in result.issues}


def test_valid_local_artifacts_pass(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    results = verify_artifacts(draft_bundle, artifact_root)
    assert [result.artifact_id for result in results] == sorted(
        result.artifact_id for result in results
    )
    assert all(result.status == "PASS" for result in results)


def test_incorrect_hash_fails(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    draft_bundle["evidence"][0]["sha256"] = "0" * 64
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert result.status == "FAIL"
    assert "ARTIFACT_SHA256_MISMATCH" in _codes(result)


def test_incorrect_size_fails(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    draft_bundle["evidence"][0]["size_bytes"] += 1
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "ARTIFACT_SIZE_MISMATCH" in _codes(result)


def test_missing_file_fails(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    draft_bundle["evidence"][0]["relative_uri"] = "missing.txt"
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "ARTIFACT_NOT_FOUND" in _codes(result)


def test_directory_is_rejected_when_artifact_must_be_a_file(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    (artifact_root / "directory").mkdir()
    draft_bundle["evidence"][0]["relative_uri"] = "directory"
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "ARTIFACT_NOT_REGULAR_FILE" in _codes(result)


def test_artifact_root_must_be_an_explicit_directory(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    root_file = artifact_root / "not-a-directory"
    root_file.write_text("synthetic root file\n", encoding="utf-8")
    with pytest.raises(LifecycleError) as caught:
        verify_artifacts(draft_bundle, root_file)
    assert caught.value.issues[0].code == "ARTIFACT_ROOT_NOT_DIRECTORY"


@pytest.mark.parametrize(
    ("locator", "expected_code"),
    [
        ("/tmp/synthetic.txt", "ARTIFACT_ABSOLUTE_PATH"),
        (r"C:\synthetic\protocol.txt", "ARTIFACT_WINDOWS_ABSOLUTE_PATH"),
        (r"\\server\share\protocol.txt", "ARTIFACT_UNC_PATH"),
        ("nested/../protocol.txt", "ARTIFACT_PATH_TRAVERSAL"),
        ("file:protocol.txt", "ARTIFACT_FILE_URI"),
    ],
)
def test_unsafe_locator_is_rejected(
    draft_bundle: dict[str, Any],
    artifact_root: Path,
    locator: str,
    expected_code: str,
) -> None:
    draft_bundle["evidence"][0]["relative_uri"] = locator
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert result.status == "FAIL"
    assert expected_code in _codes(result)


def test_internal_symlink_is_allowed(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    (artifact_root / "protocol-link.txt").symlink_to("protocol.txt")
    draft_bundle["evidence"][0]["relative_uri"] = "protocol-link.txt"
    assert _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol").status == "PASS"


def test_symlink_escaping_root_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic outside file\n", encoding="utf-8")
    (artifact_root / "escape.txt").symlink_to(outside)
    draft_bundle["evidence"][0]["relative_uri"] = "escape.txt"
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "ARTIFACT_ROOT_ESCAPE" in _codes(result)


def test_fifo_is_rejected_without_opening(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    fifo = artifact_root / "synthetic.fifo"
    os.mkfifo(fifo)
    draft_bundle["evidence"][0]["relative_uri"] = fifo.name
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "ARTIFACT_NOT_REGULAR_FILE" in _codes(result)


def test_evidence_cycle_is_rejected(draft_bundle: dict[str, Any], artifact_root: Path) -> None:
    draft_bundle["evidence"][0]["source_artifact_ids"] = ["artifact.lifecycle.analytical-reference"]
    results = verify_artifacts(draft_bundle, artifact_root)
    cycle_results = [result for result in results if "SOURCE_ARTIFACT_CYCLE" in _codes(result)]
    assert {result.artifact_id for result in cycle_results} == {
        "artifact.lifecycle.protocol",
        "artifact.lifecycle.analytical-reference",
    }
    assert all(result.status == "FAIL" for result in cycle_results)


def test_evidence_self_reference_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    draft_bundle["evidence"][0]["source_artifact_ids"] = ["artifact.lifecycle.protocol"]
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "SOURCE_ARTIFACT_SELF_REFERENCE" in _codes(result)


def test_unknown_source_artifact_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    draft_bundle["evidence"][0]["source_artifact_ids"] = ["artifact.synthetic.missing"]
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert "SOURCE_ARTIFACT_NOT_FOUND" in _codes(result)


def test_duplicate_artifact_id_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    draft_bundle["evidence"].append(copy.deepcopy(draft_bundle["evidence"][0]))
    duplicates = [
        result
        for result in verify_artifacts(draft_bundle, artifact_root)
        if result.artifact_id == "artifact.lifecycle.protocol"
    ]
    assert len(duplicates) == 2
    assert all("ARTIFACT_ID_DUPLICATE" in _codes(result) for result in duplicates)


def test_remote_uri_is_explicitly_not_verified(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    draft_bundle["evidence"][0]["relative_uri"] = "urn:synthetic:artifact:remote"
    result = _result(draft_bundle, artifact_root, "artifact.lifecycle.protocol")
    assert result.status == "REMOTE_ARTIFACT_NOT_VERIFIED"
    assert "REMOTE_ARTIFACT_NOT_VERIFIED" in _codes(result)


def test_large_artifact_is_streamed_without_path_read_bytes(
    draft_bundle: dict[str, Any], artifact_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"synthetic-stream-block\n" * 180_000
    large = artifact_root / "large.bin"
    large.write_bytes(content)
    artifact = draft_bundle["evidence"][0]
    artifact["relative_uri"] = large.name
    artifact["sha256"] = hashlib.sha256(content).hexdigest()
    artifact["size_bytes"] = len(content)

    def forbidden_read_bytes(self: Path) -> bytes:
        raise AssertionError(f"read_bytes forbidden for streaming test: {self.name}")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    assert _result(draft_bundle, artifact_root, artifact["artifact_id"]).status == "PASS"


def test_sealed_holdout_artifact_is_never_opened(
    draft_bundle: dict[str, Any],
    artifact_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = draft_bundle["datasets"][0]
    dataset["role"] = "BLIND_HOLDOUT"
    dataset["sealed_id"] = "sealed.synthetic.opaque"
    dataset["access_policy"] = {"access_level": "SEALED", "access_state": "SEALED"}
    dataset["public_metadata"] = {}
    dataset.pop("locator")

    def forbidden_hash(path: Path) -> tuple[str, int]:
        raise AssertionError(f"sealed artifact was opened: {path.name}")

    monkeypatch.setattr(artifact_module, "_hash_regular_file", forbidden_hash)
    results = verify_artifacts(draft_bundle, artifact_root)
    assert results
    assert all("SEALED_HOLDOUT_ARTIFACT_BLOCKED" in _codes(result) for result in results)
