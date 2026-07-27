"""Verification of populated result snapshot, receipt and protocol continuity."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import (
    canonical_bundle_bytes,
    verify_artifacts,
    verify_frozen_snapshot,
)
from spmkit_validation.schemas import (
    ValidationBundleError,
    assert_valid_bundle,
    load_validation_bundle,
)

from .continuity import protocol_continuity_issues
from .issues import (
    CampaignExecutionIssue,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .receipt import (
    ExecutionReceipt,
    _external_reference_summary,
    validate_execution_receipt,
)


@dataclass(frozen=True, slots=True)
class ResultSnapshotVerificationResult:
    """Machine-readable result snapshot verification outcome."""

    status: str
    artifact_status: str
    result_bundle_sha256: str | None
    issues: tuple[CampaignExecutionIssue, ...]

    @property
    def valid(self) -> bool:
        return self.status == "RESULT_SNAPSHOT_VALID" and self.artifact_status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifact_status": self.artifact_status,
            "result_bundle_sha256": self.result_bundle_sha256,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(code: str, path: str, description: str) -> CampaignExecutionIssue:
    return execution_issue(CampaignExecutionIssueCategory.RECEIPT, code, path, description)


def _strict_document(path: Path) -> tuple[dict[str, Any], bytes]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite constant {value!r}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("document root is not an object")
    return value, raw


def _invalid(
    status: str,
    issues: list[CampaignExecutionIssue],
    digest: str | None = None,
    artifact_status: str = "ARTIFACT_NOT_VERIFIED",
) -> ResultSnapshotVerificationResult:
    return ResultSnapshotVerificationResult(status, artifact_status, digest, tuple(issues))


def _metadata_issues(
    receipt: ExecutionReceipt,
    bundle: Mapping[str, Any],
    frozen_raw: bytes,
    freeze_receipt_raw: bytes,
    artifact_root: str | Path,
) -> list[CampaignExecutionIssue]:
    issues: list[CampaignExecutionIssue] = []
    expected = {
        "bundle_schema_version": bundle.get("schema_version"),
        "campaign_id": bundle.get("campaign", {}).get("campaign_id"),
        "sut_commit": bundle.get("campaign", {}).get("system_under_test", {}).get("git_commit"),
        "protocol_bundle_sha256": hashlib.sha256(frozen_raw).hexdigest(),
        "protocol_receipt_sha256": hashlib.sha256(freeze_receipt_raw).hexdigest(),
        "case_count": len(bundle.get("cases", [])),
        "run_ids": tuple(run["run_id"] for run in bundle.get("runs", [])),
    }
    receipt_values = receipt.to_dict()
    for field, value in expected.items():
        current = receipt.run_ids if field == "run_ids" else receipt_values[field]
        if current != value:
            issues.append(
                _issue(
                    f"RESULT_RECEIPT.{field.upper()}_MISMATCH",
                    f"/{field}",
                    f"receipt {field} contradicts result or protocol",
                )
            )
    outcomes = Counter(item["outcome"] for item in bundle.get("comparisons", []))
    expected_counts = {
        name: outcomes.get(name, 0)
        for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE", "NOT_EVALUATED")
    }
    if dict(receipt.comparison_counts) != expected_counts:
        issues.append(
            _issue(
                "RESULT_RECEIPT.COMPARISON_COUNTS_MISMATCH",
                "/comparison_counts",
                "receipt outcome counts contradict result comparisons",
            )
        )
    expected_claims = [
        {"claim_id": item["claim_id"], "level": item["level"], "status": item["status"]}
        for item in bundle.get("claims", [])
    ]
    if [dict(item) for item in receipt.claims] != expected_claims:
        issues.append(
            _issue(
                "RESULT_RECEIPT.CLAIMS_MISMATCH",
                "/claims",
                "receipt claim states contradict the result bundle",
            )
        )
    wheel = next(
        (
            item
            for item in bundle.get("evidence", [])
            if item.get("artifact_id") == "artifact.execution.sut-wheel"
        ),
        None,
    )
    if not wheel or wheel.get("sha256") != receipt.wheel_sha256:
        issues.append(
            _issue(
                "RESULT_RECEIPT.WHEEL_HASH_MISMATCH",
                "/wheel_sha256",
                "receipt wheel hash contradicts the registered wheel artifact",
            )
        )
    software_runs = [
        run for run in bundle.get("runs", []) if run.get("run_type") == "SOFTWARE_TEST"
    ]
    if software_runs:
        artifacts = {item["artifact_id"]: item for item in bundle.get("evidence", [])}
        junit = artifacts.get("artifact.software-test.junit")
        manifest = artifacts.get("artifact.software-test.suite-manifest")
        expected_software = {
            "software_test_run_id": software_runs[0]["run_id"] if len(software_runs) == 1 else None,
            "junit_sha256": junit.get("sha256") if junit else None,
            "test_suite_manifest_sha256": manifest.get("sha256") if manifest else None,
            "scientific_run_ids": [
                run["run_id"]
                for run in bundle.get("runs", [])
                if run.get("run_type") == "VALIDATION"
            ],
        }
        if dict(receipt.software_verification or {}) != expected_software:
            issues.append(
                _issue(
                    "RESULT_RECEIPT.SOFTWARE_VERIFICATION_MISMATCH",
                    "/software_verification",
                    "receipt software verification hashes or run IDs contradict the result bundle",
                )
            )
    try:
        expected_external = _external_reference_summary(bundle, artifact_root)
    except Exception as exc:
        issues.append(
            _issue(
                "RESULT_RECEIPT.EXTERNAL_REFERENCE_INVALID",
                "/external_reference",
                str(exc),
            )
        )
    else:
        if dict(receipt.external_reference or {}) != dict(expected_external or {}):
            issues.append(
                _issue(
                    "RESULT_RECEIPT.EXTERNAL_REFERENCE_MISMATCH",
                    "/external_reference",
                    "receipt external-reference identity contradicts result artifacts",
                )
            )
    return issues


def verify_result_snapshot(
    result_bundle_path: str | Path,
    execution_receipt_path: str | Path,
    frozen_protocol_path: str | Path,
    freeze_receipt_path: str | Path,
    artifact_root: str | Path,
) -> ResultSnapshotVerificationResult:
    """Verify exact bytes, semantics, continuity, counts and every local artifact."""

    try:
        receipt_document, receipt_raw = _strict_document(Path(execution_receipt_path))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return _invalid(
            "EXECUTION_RECEIPT_INVALID",
            [_issue("EXECUTION_RECEIPT.INVALID", "", str(exc))],
        )
    receipt_issues = list(validate_execution_receipt(receipt_document))
    try:
        receipt_canonical = canonical_bundle_bytes(receipt_document)
    except Exception as exc:  # already converted to a typed status below
        receipt_issues.append(_issue("EXECUTION_RECEIPT.INVALID", "", str(exc)))
        receipt_canonical = b""
    if receipt_raw != receipt_canonical:
        receipt_issues.append(
            _issue(
                "EXECUTION_RECEIPT.NONCANONICAL",
                "",
                "execution receipt bytes are not SPMKIT_CANONICAL_JSON_V1",
            )
        )
    if receipt_issues:
        return _invalid("EXECUTION_RECEIPT_INVALID", receipt_issues)
    receipt = ExecutionReceipt.from_dict(receipt_document)

    try:
        result_raw = Path(result_bundle_path).read_bytes()
        bundle = load_validation_bundle(result_bundle_path)
    except (OSError, ValidationBundleError) as exc:
        descriptions = (
            [issue.description for issue in exc.issues]
            if isinstance(exc, ValidationBundleError)
            else [str(exc)]
        )
        return _invalid(
            "RESULT_BUNDLE_INVALID",
            [_issue("RESULT.BUNDLE_INVALID", "", description) for description in descriptions],
        )
    digest = hashlib.sha256(result_raw).hexdigest()
    issues: list[CampaignExecutionIssue] = []
    try:
        canonical = canonical_bundle_bytes(bundle)
    except Exception as exc:
        return _invalid("RESULT_BUNDLE_INVALID", [_issue("RESULT.BUNDLE_INVALID", "", str(exc))])
    if result_raw != canonical:
        issues.append(
            _issue(
                "RESULT.NONCANONICAL",
                "",
                "result bundle bytes are not SPMKIT_CANONICAL_JSON_V1",
            )
        )
    if len(result_raw) != receipt.result_bundle_size_bytes:
        issues.append(
            _issue("RESULT.SIZE_MISMATCH", "", "result byte size differs from the receipt")
        )
    if digest != receipt.result_bundle_sha256:
        issues.append(
            _issue("RESULT.HASH_MISMATCH", "", "result SHA-256 differs from the receipt")
        )
    try:
        assert_valid_bundle(bundle)
    except ValidationBundleError as exc:
        issues.extend(
            _issue("RESULT.BUNDLE_INVALID", issue.path, issue.description) for issue in exc.issues
        )
    try:
        frozen_raw = Path(frozen_protocol_path).read_bytes()
        freeze_receipt_raw = Path(freeze_receipt_path).read_bytes()
        frozen = load_validation_bundle(frozen_protocol_path)
    except (OSError, ValidationBundleError) as exc:
        return _invalid(
            "PROTOCOL_INVALID",
            [_issue("RESULT.PROTOCOL_INVALID", "", str(exc))],
            digest,
        )
    freeze_verification = verify_frozen_snapshot(
        frozen_protocol_path, freeze_receipt_path, artifact_root=artifact_root
    )
    if freeze_verification.status != "SNAPSHOT_VALID":
        issues.append(
            _issue(
                "RESULT.PROTOCOL_INVALID",
                "",
                f"frozen protocol verification is {freeze_verification.status}",
            )
        )
    issues.extend(protocol_continuity_issues(frozen, bundle))
    issues.extend(
        _metadata_issues(receipt, bundle, frozen_raw, freeze_receipt_raw, artifact_root)
    )
    if issues:
        codes = {issue.code for issue in issues}
        if "RESULT.NONCANONICAL" in codes:
            status = "RESULT_NONCANONICAL"
        elif "RESULT.SIZE_MISMATCH" in codes:
            status = "RESULT_SIZE_MISMATCH"
        elif "RESULT.HASH_MISMATCH" in codes:
            status = "RESULT_HASH_MISMATCH"
        elif any(
            code.startswith("PROTOCOL.") or code == "RESULT.PROTOCOL_INVALID"
            for code in codes
        ):
            status = "PROTOCOL_DRIFT"
        else:
            status = "RESULT_BUNDLE_INVALID"
        return _invalid(status, issues, digest)

    artifact_results = verify_artifacts(bundle, artifact_root)
    failures = [result for result in artifact_results if result.status != "PASS"]
    expected_summary = {
        "total": len(artifact_results),
        "passed": sum(result.status == "PASS" for result in artifact_results),
        "failed": sum(result.status == "FAIL" for result in artifact_results),
        "remote_not_verified": sum(
            result.status == "REMOTE_ARTIFACT_NOT_VERIFIED" for result in artifact_results
        ),
    }
    if failures or expected_summary != dict(receipt.artifact_verification_summary):
        artifact_issues = [
            execution_issue(
                CampaignExecutionIssueCategory.ARTIFACT,
                issue.code,
                issue.path,
                issue.description,
            )
            for result in failures
            for issue in result.issues
        ]
        if expected_summary != dict(receipt.artifact_verification_summary):
            artifact_issues.append(
                execution_issue(
                    CampaignExecutionIssueCategory.ARTIFACT,
                    "RESULT_RECEIPT.ARTIFACT_SUMMARY_MISMATCH",
                    "/artifact_verification_summary",
                    "receipt artifact summary differs from current verification",
                )
            )
        return _invalid("ARTIFACT_MISMATCH", artifact_issues, digest, "ARTIFACT_MISMATCH")
    return ResultSnapshotVerificationResult("RESULT_SNAPSHOT_VALID", "PASS", digest, ())
