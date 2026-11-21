"""Deterministic, exclusive freeze publication for ValidationBundle v0.1."""

from __future__ import annotations

import copy
import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spmkit_validation.schemas import (
    ValidationBundleError,
    assert_valid_bundle,
    load_validation_bundle,
)

from .artifacts import ArtifactVerificationResult, verify_artifacts
from .canonical import canonical_bundle_bytes
from .issues import LifecycleError, LifecycleIssue, LifecycleIssueCategory, lifecycle_issue
from .receipt import FreezeReceipt, create_freeze_receipt

_UTC_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")


@dataclass(frozen=True, slots=True)
class FreezeResult:
    """Published snapshot paths and their deterministic identity."""

    bundle_sha256: str
    bundle_size_bytes: int
    snapshot_path: Path
    receipt_path: Path
    receipt: FreezeReceipt
    artifact_results: tuple[ArtifactVerificationResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_sha256": self.bundle_sha256,
            "bundle_size_bytes": self.bundle_size_bytes,
            "snapshot_path": str(self.snapshot_path),
            "receipt_path": str(self.receipt_path),
            "artifact_verification_summary": dict(self.receipt.artifact_verification_summary),
        }


def _validation_lifecycle_issues(error: ValidationBundleError) -> tuple[LifecycleIssue, ...]:
    return tuple(
        lifecycle_issue(
            LifecycleIssueCategory.INPUT,
            issue.code,
            issue.path,
            issue.description,
        )
        for issue in error.issues
    )


def _assert_validation_bundle(bundle: Mapping[str, Any]) -> None:
    try:
        assert_valid_bundle(bundle)
    except ValidationBundleError as exc:
        raise LifecycleError(_validation_lifecycle_issues(exc)) from exc


def _freeze_precondition_issues(bundle: Mapping[str, Any]) -> tuple[LifecycleIssue, ...]:
    issues: list[LifecycleIssue] = []
    campaign = bundle.get("campaign", {})
    if not isinstance(campaign, Mapping):
        return ()
    if campaign.get("status") != "DRAFT":
        issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.FREEZE,
                "FREEZE.CAMPAIGN_NOT_DRAFT",
                "/campaign/status",
                "only a DRAFT campaign can be frozen",
            )
        )
    if campaign.get("frozen_at") is not None:
        issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.FREEZE,
                "FREEZE.FROZEN_AT_ALREADY_SET",
                "/campaign/frozen_at",
                "DRAFT campaign must not already declare frozen_at",
            )
        )
    for collection in ("runs", "comparisons"):
        if bundle.get(collection):
            issues.append(
                lifecycle_issue(
                    LifecycleIssueCategory.FREEZE,
                    f"FREEZE.{collection.upper()}_PRESENT",
                    f"/{collection}",
                    f"a protocol snapshot cannot contain {collection}",
                )
            )
    claims = bundle.get("claims", [])
    if isinstance(claims, list):
        for index, claim in enumerate(claims):
            if isinstance(claim, Mapping) and claim.get("status") in {
                "SUPPORTED",
                "SUPERSEDED",
            }:
                issues.append(
                    lifecycle_issue(
                        LifecycleIssueCategory.FREEZE,
                        "FREEZE.EVALUATED_CLAIM_PRESENT",
                        f"/claims/{index}/status",
                        "a protocol snapshot cannot contain an evaluated claim",
                    )
                )
    cases = bundle.get("cases", [])
    if not cases:
        issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.FREEZE,
                "FREEZE.NO_PREDECLARED_CASES",
                "/cases",
                "at least one validation case must be predeclared before freeze",
            )
        )
    elif isinstance(cases, list):
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping) or not case.get("tolerances"):
                issues.append(
                    lifecycle_issue(
                        LifecycleIssueCategory.FREEZE,
                        "FREEZE.NO_PREDECLARED_TOLERANCE",
                        f"/cases/{index}/tolerances",
                        "every case must have an explicit predeclared tolerance",
                    )
                )
    return tuple(issues)


def _validated_frozen_at(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if not isinstance(value, str) or not _UTC_RFC3339.fullmatch(value):
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FREEZE,
                    "FREEZE.INVALID_FROZEN_AT",
                    "/campaign/frozen_at",
                    "frozen_at must be an explicit RFC3339 UTC timestamp",
                )
            ]
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FREEZE,
                    "FREEZE.INVALID_FROZEN_AT",
                    "/campaign/frozen_at",
                    "frozen_at is not a valid calendar timestamp",
                )
            ]
        ) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FREEZE,
                    "FREEZE.INVALID_FROZEN_AT",
                    "/campaign/frozen_at",
                    "frozen_at must use UTC, not a non-zero offset",
                )
            ]
        )
    return value


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _prepare_output_root(output_dir: str | Path) -> Path:
    output_root = Path(output_dir)
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        resolved = output_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.OUTPUT_DIRECTORY_FAILED",
                    "/output_dir",
                    f"output directory could not be prepared: {exc}",
                )
            ]
        ) from exc
    if not resolved.is_dir():
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.OUTPUT_NOT_DIRECTORY",
                    "/output_dir",
                    "output_dir must be a directory",
                )
            ]
        )
    return resolved


def freeze_bundle(
    bundle_path: str | Path,
    artifact_root: str | Path,
    output_dir: str | Path,
    frozen_at: str | None = None,
) -> FreezeResult:
    """Validate and publish a deterministic content-addressed protocol snapshot."""

    source_path = Path(bundle_path)
    try:
        source_before = source_path.read_bytes()
    except OSError as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.SOURCE_READ_FAILED",
                    "",
                    f"source bundle could not be read: {exc}",
                )
            ]
        ) from exc
    try:
        bundle = load_validation_bundle(source_path)
    except ValidationBundleError as exc:
        raise LifecycleError(_validation_lifecycle_issues(exc)) from exc
    try:
        source_after = source_path.read_bytes()
    except OSError as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.SOURCE_READ_FAILED",
                    "",
                    f"source bundle could not be re-read safely: {exc}",
                )
            ]
        ) from exc
    if source_before != source_after:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FREEZE,
                    "FREEZE.SOURCE_CHANGED_DURING_READ",
                    "",
                    "source bundle changed while freeze was reading it",
                )
            ]
        )

    _assert_validation_bundle(bundle)
    precondition_issues = _freeze_precondition_issues(bundle)
    if precondition_issues:
        raise LifecycleError(precondition_issues)
    freeze_time = _validated_frozen_at(frozen_at)

    artifact_results = verify_artifacts(bundle, artifact_root)
    failed = [result for result in artifact_results if result.status == "FAIL"]
    remote = [
        result for result in artifact_results if result.status == "REMOTE_ARTIFACT_NOT_VERIFIED"
    ]
    if failed:
        issues = [issue for result in failed for issue in result.issues]
        raise LifecycleError(issues)
    if remote:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.ARTIFACT,
                    "FREEZE.REMOTE_ARTIFACT_NOT_VERIFIED",
                    "/evidence",
                    "freeze requires complete verification of every declared artifact",
                )
            ]
        )

    frozen_bundle = copy.deepcopy(bundle)
    frozen_bundle["campaign"]["status"] = "FROZEN"
    frozen_bundle["campaign"]["frozen_at"] = freeze_time
    _assert_validation_bundle(frozen_bundle)

    snapshot_bytes = canonical_bundle_bytes(frozen_bundle)
    bundle_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    source_sha256 = hashlib.sha256(source_after).hexdigest()
    receipt = create_freeze_receipt(
        bundle_schema_version=frozen_bundle["schema_version"],
        bundle_sha256=bundle_sha256,
        bundle_size_bytes=len(snapshot_bytes),
        source_bundle_sha256=source_sha256,
        frozen_at=freeze_time,
        campaign_id=frozen_bundle["campaign"]["campaign_id"],
        artifact_results=artifact_results,
    )
    receipt_bytes = receipt.canonical_bytes()

    output_root = _prepare_output_root(output_dir)
    final_directory = output_root / bundle_sha256
    if final_directory.exists():
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.OUTPUT_EXISTS",
                    "/output_dir",
                    "content-addressed snapshot already exists; no files were replaced",
                )
            ]
        )

    temporary_directory = Path(tempfile.mkdtemp(prefix=".spmkit-freeze-", dir=output_root))
    published = False
    try:
        _write_exclusive(temporary_directory / "bundle.json", snapshot_bytes)
        _write_exclusive(temporary_directory / "freeze-receipt.json", receipt_bytes)
        if final_directory.exists():
            raise FileExistsError("content-addressed snapshot appeared during freeze")
        temporary_directory.rename(final_directory)
        published = True
    except (OSError, RuntimeError) as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.FILESYSTEM,
                    "FREEZE.PUBLICATION_FAILED",
                    "/output_dir",
                    f"snapshot publication failed without replacing prior output: {exc}",
                )
            ]
        ) from exc
    finally:
        if not published and temporary_directory.exists():
            shutil.rmtree(temporary_directory)

    return FreezeResult(
        bundle_sha256=bundle_sha256,
        bundle_size_bytes=len(snapshot_bytes),
        snapshot_path=final_directory / "bundle.json",
        receipt_path=final_directory / "freeze-receipt.json",
        receipt=receipt,
        artifact_results=artifact_results,
    )
