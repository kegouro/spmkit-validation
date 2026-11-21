from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import verify_artifacts

MANIFEST_ID = "artifact.lifecycle.run-manifest"


def _manifest(bundle: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in bundle["evidence"] if item["artifact_id"] == MANIFEST_ID)


def _manifest_result(bundle: dict[str, Any], root: Path):
    return next(
        result for result in verify_artifacts(bundle, root) if result.artifact_id == MANIFEST_ID
    )


def _replace_manifest(bundle: dict[str, Any], root: Path, content: bytes) -> dict[str, Any]:
    path = root / "synthetic-run-manifest.json"
    path.write_bytes(content)
    artifact = _manifest(bundle)
    artifact["sha256"] = hashlib.sha256(content).hexdigest()
    artifact["size_bytes"] = len(content)
    return artifact


def test_synthetic_runmanifest_is_valid_and_hashed(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    result = _manifest_result(draft_bundle, artifact_root)
    assert result.status == "PASS"
    assert result.calculated_sha256 == _manifest(draft_bundle)["sha256"]
    assert result.calculated_size_bytes == _manifest(draft_bundle)["size_bytes"]


def test_corrupt_runmanifest_json_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    _replace_manifest(draft_bundle, artifact_root, b"{corrupt\n")
    result = _manifest_result(draft_bundle, artifact_root)
    assert result.status == "FAIL"
    assert "RUNMANIFEST_INVALID_JSON" in {issue.code for issue in result.issues}


def test_nonfinite_runmanifest_json_is_rejected(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    _replace_manifest(draft_bundle, artifact_root, b'{"value":1e999}\n')
    result = _manifest_result(draft_bundle, artifact_root)
    assert "RUNMANIFEST_INVALID_JSON" in {issue.code for issue in result.issues}


def test_runmanifest_mime_must_be_json_compatible(
    draft_bundle: dict[str, Any], artifact_root: Path
) -> None:
    _manifest(draft_bundle)["media_type"] = "text/plain"
    result = _manifest_result(draft_bundle, artifact_root)
    assert result.status == "FAIL"
    assert "RUNMANIFEST_MIME_MISMATCH" in {issue.code for issue in result.issues}
