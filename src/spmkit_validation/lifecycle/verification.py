"""Post-freeze verification of snapshot, receipt, and optional artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spmkit_validation.schemas import ValidationBundleError, load_validation_bundle

from .artifacts import verify_artifacts
from .canonical import CANONICALIZATION_NAME, canonical_bundle_bytes
from .freeze import _assert_validation_bundle
from .issues import LifecycleError, LifecycleIssue, LifecycleIssueCategory, lifecycle_issue
from .receipt import (
    SNAPSHOT_TYPE,
    FreezeReceipt,
    load_receipt_document,
    validate_freeze_receipt,
)


@dataclass(frozen=True, slots=True)
class SnapshotVerificationResult:
    """Structured outcome for later snapshot verification."""

    status: str
    artifact_status: str
    bundle_sha256: str | None
    issues: tuple[LifecycleIssue, ...]

    @property
    def passed(self) -> bool:
        return self.status == "SNAPSHOT_VALID"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifact_status": self.artifact_status,
            "bundle_sha256": self.bundle_sha256,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _snapshot_issue(code: str, path: str, description: str) -> LifecycleIssue:
    return lifecycle_issue(LifecycleIssueCategory.SNAPSHOT, code, path, description)


def _invalid_result(
    status: str,
    issues: list[LifecycleIssue] | tuple[LifecycleIssue, ...],
    bundle_sha256: str | None = None,
) -> SnapshotVerificationResult:
    return SnapshotVerificationResult(
        status=status,
        artifact_status="ARTIFACT_NOT_VERIFIED",
        bundle_sha256=bundle_sha256,
        issues=tuple(issues),
    )


def _load_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        before = path.read_bytes()
    except OSError as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "SNAPSHOT_READ_FAILED",
                    "",
                    f"snapshot could not be read: {exc}",
                )
            ]
        ) from exc
    try:
        bundle = load_validation_bundle(path)
    except ValidationBundleError as exc:
        raise LifecycleError(
            [
                _snapshot_issue(
                    "BUNDLE_INVALID",
                    issue.path,
                    issue.description,
                )
                for issue in exc.issues
            ]
        ) from exc
    try:
        after = path.read_bytes()
    except OSError as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "SNAPSHOT_READ_FAILED",
                    "",
                    f"snapshot could not be re-read safely: {exc}",
                )
            ]
        ) from exc
    if before != after:
        raise LifecycleError(
            [
                _snapshot_issue(
                    "BUNDLE_INVALID",
                    "",
                    "snapshot changed while it was being read",
                )
            ]
        )
    return bundle, after


def _receipt_metadata_issues(
    receipt: FreezeReceipt, bundle: dict[str, Any], snapshot_path: Path
) -> list[LifecycleIssue]:
    issues: list[LifecycleIssue] = []
    campaign = bundle.get("campaign", {})
    comparisons = (
        ("bundle_schema_version", bundle.get("schema_version"), "/bundle_schema_version"),
        ("campaign_id", campaign.get("campaign_id"), "/campaign_id"),
        ("frozen_at", campaign.get("frozen_at"), "/frozen_at"),
        ("snapshot_type", SNAPSHOT_TYPE, "/snapshot_type"),
        ("canonicalization", CANONICALIZATION_NAME, "/canonicalization"),
        ("snapshot_relative_uri", snapshot_path.name, "/snapshot_relative_uri"),
    )
    receipt_values = receipt.to_dict()
    for field, expected, path in comparisons:
        if receipt_values[field] != expected:
            issues.append(
                lifecycle_issue(
                    LifecycleIssueCategory.RECEIPT,
                    "RECEIPT_BUNDLE_CONTRADICTION",
                    path,
                    f"receipt {field} contradicts the snapshot",
                )
            )
    if receipt.created_at != receipt.frozen_at:
        issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.RECEIPT,
                "RECEIPT_TIMESTAMP_CONTRADICTION",
                "/created_at",
                "deterministic v0.1 receipt created_at must equal frozen_at",
            )
        )
    return issues


def _artifact_record(result: Any) -> dict[str, Any]:
    return {
        "artifact_id": result.artifact_id,
        "status": result.status,
        "calculated_sha256": result.calculated_sha256,
        "calculated_size_bytes": result.calculated_size_bytes,
    }


def verify_frozen_snapshot(
    snapshot_path: str | Path,
    receipt_path: str | Path,
    artifact_root: str | Path | None = None,
) -> SnapshotVerificationResult:
    """Verify exact snapshot bytes, receipt, and optionally current artifacts."""

    try:
        receipt_document, receipt_raw = load_receipt_document(receipt_path)
    except LifecycleError as exc:
        if any(issue.category is LifecycleIssueCategory.FILESYSTEM for issue in exc.issues):
            raise
        return _invalid_result("RECEIPT_INVALID", list(exc.issues))

    receipt_issues = list(validate_freeze_receipt(receipt_document))
    try:
        canonical_receipt = canonical_bundle_bytes(receipt_document)
    except LifecycleError as exc:
        receipt_issues.extend(exc.issues)
        canonical_receipt = b""
    if receipt_raw != canonical_receipt:
        receipt_issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.RECEIPT,
                "RECEIPT_NONCANONICAL",
                "",
                "receipt bytes are not SPMKIT_CANONICAL_JSON_V1",
            )
        )
    if receipt_issues:
        return _invalid_result("RECEIPT_INVALID", receipt_issues)
    receipt = FreezeReceipt.from_dict(receipt_document)

    try:
        bundle, snapshot_raw = _load_snapshot(Path(snapshot_path))
    except LifecycleError as exc:
        if all(issue.category is LifecycleIssueCategory.SNAPSHOT for issue in exc.issues):
            return _invalid_result("BUNDLE_INVALID", list(exc.issues))
        raise

    actual_hash = hashlib.sha256(snapshot_raw).hexdigest()
    issues: list[LifecycleIssue] = []
    try:
        canonical_snapshot = canonical_bundle_bytes(bundle)
    except LifecycleError as exc:
        return _invalid_result("BUNDLE_INVALID", list(exc.issues), actual_hash)
    if snapshot_raw != canonical_snapshot:
        issues.append(
            _snapshot_issue(
                "SNAPSHOT_NONCANONICAL",
                "",
                "snapshot bytes are not SPMKIT_CANONICAL_JSON_V1",
            )
        )
    if len(snapshot_raw) != receipt.bundle_size_bytes:
        issues.append(
            _snapshot_issue(
                "SNAPSHOT_SIZE_MISMATCH",
                "",
                "snapshot byte size differs from the receipt",
            )
        )
    if actual_hash != receipt.bundle_sha256:
        issues.append(
            _snapshot_issue(
                "SNAPSHOT_HASH_MISMATCH",
                "",
                "snapshot SHA-256 differs from the receipt",
            )
        )

    try:
        _assert_validation_bundle(bundle)
    except LifecycleError as exc:
        issues.extend(
            _snapshot_issue("BUNDLE_INVALID", issue.path, issue.description) for issue in exc.issues
        )
    campaign = bundle.get("campaign", {})
    if not isinstance(campaign, dict) or campaign.get("status") != "FROZEN":
        issues.append(
            _snapshot_issue(
                "BUNDLE_INVALID",
                "/campaign/status",
                "snapshot campaign must be FROZEN",
            )
        )
    metadata_issues = _receipt_metadata_issues(receipt, bundle, Path(snapshot_path))
    issues.extend(metadata_issues)

    codes = {issue.code for issue in issues}
    if "BUNDLE_INVALID" in codes:
        return _invalid_result("BUNDLE_INVALID", issues, actual_hash)
    if metadata_issues:
        return _invalid_result("RECEIPT_INVALID", issues, actual_hash)
    if "SNAPSHOT_NONCANONICAL" in codes:
        return _invalid_result("SNAPSHOT_NONCANONICAL", issues, actual_hash)
    if "SNAPSHOT_SIZE_MISMATCH" in codes:
        return _invalid_result("SNAPSHOT_SIZE_MISMATCH", issues, actual_hash)
    if "SNAPSHOT_HASH_MISMATCH" in codes:
        return _invalid_result("SNAPSHOT_HASH_MISMATCH", issues, actual_hash)

    artifact_status = "ARTIFACT_NOT_VERIFIED"
    if artifact_root is not None:
        artifact_results = verify_artifacts(bundle, artifact_root)
        failures = [result for result in artifact_results if result.status == "FAIL"]
        remote = [
            result for result in artifact_results if result.status == "REMOTE_ARTIFACT_NOT_VERIFIED"
        ]
        actual_records = [_artifact_record(result) for result in artifact_results]
        expected_records = [dict(record) for record in receipt.artifact_verification_records]
        if failures or actual_records != expected_records:
            artifact_issues = [issue for result in failures for issue in result.issues]
            if actual_records != expected_records:
                artifact_issues.append(
                    _snapshot_issue(
                        "ARTIFACT_RECEIPT_MISMATCH",
                        "/artifact_verification_records",
                        "current artifact verification differs from the freeze receipt",
                    )
                )
            return SnapshotVerificationResult(
                status="ARTIFACT_MISMATCH",
                artifact_status="ARTIFACT_MISMATCH",
                bundle_sha256=actual_hash,
                issues=tuple(artifact_issues),
            )
        artifact_status = "ARTIFACT_NOT_VERIFIED" if remote else "PASS"

    return SnapshotVerificationResult(
        status="SNAPSHOT_VALID",
        artifact_status=artifact_status,
        bundle_sha256=actual_hash,
        issues=(),
    )
