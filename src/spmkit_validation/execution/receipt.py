"""Operational receipt for tamper-evident populated result snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import (
    CANONICALIZATION_NAME,
    canonical_bundle_bytes,
    verify_artifacts,
)
from spmkit_validation.schemas import assert_valid_bundle, load_validation_bundle

from .continuity import verify_protocol_continuity
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssue,
    CampaignExecutionIssueCategory,
    execution_issue,
)

EXECUTION_RECEIPT_VERSION = "0.1.0"
RESULT_SNAPSHOT_TYPE = "TAMPER_EVIDENT_RESULT_SNAPSHOT"


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """Typed operational identity of one populated result snapshot."""

    receipt_version: str
    snapshot_type: str
    canonicalization: str
    bundle_schema_version: str
    protocol_bundle_sha256: str
    protocol_receipt_sha256: str
    result_bundle_sha256: str
    result_bundle_size_bytes: int
    result_relative_uri: str
    campaign_id: str
    sut_commit: str
    wheel_sha256: str
    started_at: str
    completed_at: str
    run_ids: tuple[str, ...]
    case_count: int
    comparison_counts: Mapping[str, int]
    claims: tuple[Mapping[str, str], ...]
    artifact_verification_summary: Mapping[str, int]
    tool: Mapping[str, Any]
    limitations: tuple[str, ...]
    receipt_sha256: str
    software_verification: Mapping[str, Any] | None = None
    external_reference: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        document = {
            "receipt_version": self.receipt_version,
            "snapshot_type": self.snapshot_type,
            "canonicalization": self.canonicalization,
            "bundle_schema_version": self.bundle_schema_version,
            "protocol_bundle_sha256": self.protocol_bundle_sha256,
            "protocol_receipt_sha256": self.protocol_receipt_sha256,
            "result_bundle_sha256": self.result_bundle_sha256,
            "result_bundle_size_bytes": self.result_bundle_size_bytes,
            "result_relative_uri": self.result_relative_uri,
            "campaign_id": self.campaign_id,
            "sut_commit": self.sut_commit,
            "wheel_sha256": self.wheel_sha256,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "run_ids": list(self.run_ids),
            "case_count": self.case_count,
            "comparison_counts": dict(self.comparison_counts),
            "claims": [dict(claim) for claim in self.claims],
            "artifact_verification_summary": dict(self.artifact_verification_summary),
            "tool": dict(self.tool),
            "limitations": list(self.limitations),
            "receipt_sha256": self.receipt_sha256,
        }
        if self.software_verification is not None:
            document["software_verification"] = dict(self.software_verification)
        if self.external_reference is not None:
            document["external_reference"] = dict(self.external_reference)
        return document

    def canonical_bytes(self) -> bytes:
        return canonical_bundle_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> ExecutionReceipt:
        issues = validate_execution_receipt(document)
        if issues:
            raise CampaignExecutionError(issues)
        return cls(
            receipt_version=document["receipt_version"],
            snapshot_type=document["snapshot_type"],
            canonicalization=document["canonicalization"],
            bundle_schema_version=document["bundle_schema_version"],
            protocol_bundle_sha256=document["protocol_bundle_sha256"],
            protocol_receipt_sha256=document["protocol_receipt_sha256"],
            result_bundle_sha256=document["result_bundle_sha256"],
            result_bundle_size_bytes=document["result_bundle_size_bytes"],
            result_relative_uri=document["result_relative_uri"],
            campaign_id=document["campaign_id"],
            sut_commit=document["sut_commit"],
            wheel_sha256=document["wheel_sha256"],
            started_at=document["started_at"],
            completed_at=document["completed_at"],
            run_ids=tuple(document["run_ids"]),
            case_count=document["case_count"],
            comparison_counts=dict(document["comparison_counts"]),
            claims=tuple(dict(claim) for claim in document["claims"]),
            artifact_verification_summary=dict(document["artifact_verification_summary"]),
            tool=dict(document["tool"]),
            limitations=tuple(document["limitations"]),
            receipt_sha256=document["receipt_sha256"],
            software_verification=(
                dict(document["software_verification"])
                if "software_verification" in document
                else None
            ),
            external_reference=(
                dict(document["external_reference"])
                if "external_reference" in document
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ResultSnapshotWriteResult:
    """Paths and hashes published by write_execution_receipt."""

    result_bundle_path: Path
    execution_receipt_path: Path
    result_bundle_sha256: str
    result_bundle_size_bytes: int
    execution_receipt_sha256: str
    receipt: ExecutionReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_bundle_path": str(self.result_bundle_path),
            "execution_receipt_path": str(self.execution_receipt_path),
            "result_bundle_sha256": self.result_bundle_sha256,
            "result_bundle_size_bytes": self.result_bundle_size_bytes,
            "execution_receipt_sha256": self.execution_receipt_sha256,
        }


def _receipt_schema() -> dict[str, Any]:
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:spmkit-validation:receipt:v0.1:execution",
        "type": "object",
        "required": [
            "receipt_version",
            "snapshot_type",
            "canonicalization",
            "bundle_schema_version",
            "protocol_bundle_sha256",
            "protocol_receipt_sha256",
            "result_bundle_sha256",
            "result_bundle_size_bytes",
            "result_relative_uri",
            "campaign_id",
            "sut_commit",
            "wheel_sha256",
            "started_at",
            "completed_at",
            "run_ids",
            "case_count",
            "comparison_counts",
            "claims",
            "artifact_verification_summary",
            "tool",
            "limitations",
            "receipt_sha256",
        ],
        "properties": {
            "receipt_version": {"const": EXECUTION_RECEIPT_VERSION},
            "snapshot_type": {"const": RESULT_SNAPSHOT_TYPE},
            "canonicalization": {"const": CANONICALIZATION_NAME},
            "bundle_schema_version": {"const": "0.1.0"},
            "protocol_bundle_sha256": sha,
            "protocol_receipt_sha256": sha,
            "result_bundle_sha256": sha,
            "result_bundle_size_bytes": {"type": "integer", "minimum": 1},
            "result_relative_uri": {"const": "result-bundle.json"},
            "campaign_id": {"type": "string", "minLength": 1},
            "sut_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
            "wheel_sha256": sha,
            "started_at": {"type": "string", "format": "date-time"},
            "completed_at": {"type": "string", "format": "date-time"},
            "run_ids": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "case_count": {"type": "integer", "minimum": 1},
            "comparison_counts": {
                "type": "object",
                "required": ["PASS", "FAIL", "ERROR", "INCONCLUSIVE", "NOT_EVALUATED"],
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["claim_id", "level", "status"],
                    "additionalProperties": {"type": "string"},
                },
            },
            "artifact_verification_summary": {
                "type": "object",
                "required": ["total", "passed", "failed", "remote_not_verified"],
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "tool": {
                "type": "object",
                "required": ["name", "version", "git_commit"],
                "properties": {
                    "name": {"const": "spmkit-validation"},
                    "version": {"type": "string", "minLength": 1},
                    "git_commit": {
                        "oneOf": [
                            {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                            {"type": "null"},
                        ]
                    },
                },
                "additionalProperties": False,
            },
            "limitations": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "receipt_sha256": sha,
            "software_verification": {
                "type": "object",
                "required": [
                    "software_test_run_id",
                    "junit_sha256",
                    "test_suite_manifest_sha256",
                    "scientific_run_ids",
                ],
                "properties": {
                    "software_test_run_id": {"type": "string", "minLength": 1},
                    "junit_sha256": sha,
                    "test_suite_manifest_sha256": sha,
                    "scientific_run_ids": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": False,
            },
            "external_reference": {
                "type": "object",
                "required": [
                    "reference_id",
                    "producer_name",
                    "producer_is_third_party",
                    "independence_assessment",
                    "gwyddion_version",
                    "gwyddion_executable_sha256",
                    "gwyddion_identity_record_sha256",
                    "gwyddion_library_versions",
                    "helper_source_sha256",
                    "helper_binary_sha256",
                    "independence_assessment_sha256",
                    "external_run_ids",
                    "external_comparison_count",
                ],
                "properties": {
                    "reference_id": {"type": "string", "minLength": 1},
                    "producer_name": {"type": "string", "minLength": 1},
                    "producer_is_third_party": {"const": True},
                    "independence_assessment": {"const": "INDEPENDENT"},
                    "gwyddion_version": {"type": "string", "minLength": 1},
                    "gwyddion_executable_sha256": sha,
                    "gwyddion_identity_record_sha256": sha,
                    "gwyddion_library_versions": {
                        "type": "object",
                        "additionalProperties": {"type": "string", "minLength": 1},
                    },
                    "helper_source_sha256": sha,
                    "helper_binary_sha256": sha,
                    "independence_assessment_sha256": sha,
                    "external_run_ids": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "external_comparison_count": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _payload_sha256(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("receipt_sha256", None)
    return hashlib.sha256(canonical_bundle_bytes(payload)).hexdigest()


def validate_execution_receipt(
    document: Mapping[str, Any],
) -> tuple[CampaignExecutionIssue, ...]:
    """Validate receipt structure and its internal payload checksum."""

    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(_receipt_schema(), format_checker=FormatChecker())
    issues = [
        execution_issue(
            CampaignExecutionIssueCategory.RECEIPT,
            "EXECUTION_RECEIPT.INVALID",
            "/" + "/".join(str(part) for part in error.absolute_path),
            error.message,
        )
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]
    if not issues and document["receipt_sha256"] != _payload_sha256(document):
        issues.append(
            execution_issue(
                CampaignExecutionIssueCategory.RECEIPT,
                "EXECUTION_RECEIPT.HASH_MISMATCH",
                "/receipt_sha256",
                "receipt payload checksum does not match",
            )
        )
    return tuple(issues)


def _tool_version() -> str:
    try:
        return metadata.version("spmkit-validation")
    except metadata.PackageNotFoundError:
        from spmkit_validation import __version__

        return __version__


def _tool_commit() -> str | None:
    root = Path(__file__).resolve().parents[3]
    if not (root / ".git").exists() or not (root / "pyproject.toml").is_file():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    candidate = result.stdout.strip().lower()
    valid = len(candidate) == 40 and all(c in "0123456789abcdef" for c in candidate)
    return candidate if valid else None


def _hash_bytes(path: Path) -> tuple[str, int, bytes]:
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest(), len(raw), raw


def _summary(results: Sequence[Any]) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(result.status == "PASS" for result in results),
        "failed": sum(result.status == "FAIL" for result in results),
        "remote_not_verified": sum(
            result.status == "REMOTE_ARTIFACT_NOT_VERIFIED" for result in results
        ),
    }


def _external_reference_summary(
    bundle: Mapping[str, Any], artifact_root: str | Path
) -> dict[str, Any] | None:
    references = [
        item
        for item in bundle.get("references", [])
        if item.get("reference_type") == "EXTERNAL_SOFTWARE_REFERENCE"
        and item.get("producer", {}).get("is_third_party") is True
    ]
    external_runs = [
        item["run_id"]
        for item in bundle.get("runs", [])
        if item.get("run_id", "").startswith("run.gwyddion.")
    ]
    if not references or not external_runs:
        return None
    reference = references[0]
    artifacts = {item["artifact_id"]: item for item in bundle.get("evidence", [])}
    required = {
        "identity": "artifact.reference.gwyddion-identity",
        "source": "artifact.reference.helper-source",
        "binary": "artifact.reference.helper-binary",
        "independence": "artifact.reference.independence-assessment",
    }
    if any(artifact_id not in artifacts for artifact_id in required.values()):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.RECEIPT,
                    "EXECUTION_RECEIPT.EXTERNAL_EVIDENCE_MISSING",
                    "/evidence",
                    "external receipt requires identity, helper and independence artifacts",
                )
            ]
        )
    identity_artifact = artifacts[required["identity"]]
    identity_path = Path(artifact_root) / identity_artifact["relative_uri"]
    try:
        identity = json.loads(identity_path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.RECEIPT,
                    "EXECUTION_RECEIPT.EXTERNAL_IDENTITY_INVALID",
                    "/evidence",
                    str(exc),
                )
            ]
        ) from exc
    return {
        "reference_id": reference["reference_id"],
        "producer_name": reference["producer"]["name"],
        "producer_is_third_party": reference["producer"]["is_third_party"],
        "independence_assessment": reference["independence_justification"][
            "independence_assessment"
        ],
        "gwyddion_version": reference["version"],
        "gwyddion_executable_sha256": identity["executable"]["sha256"],
        "gwyddion_identity_record_sha256": identity_artifact["sha256"],
        "gwyddion_library_versions": dict(identity["libraries"]),
        "helper_source_sha256": artifacts[required["source"]]["sha256"],
        "helper_binary_sha256": artifacts[required["binary"]]["sha256"],
        "independence_assessment_sha256": artifacts[required["independence"]]["sha256"],
        "external_run_ids": external_runs,
        "external_comparison_count": sum(
            item.get("comparison_id", "").startswith("comparison.cross.gwyddion.")
            for item in bundle.get("comparisons", [])
        ),
    }


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def write_execution_receipt(
    result_bundle: Mapping[str, Any],
    *,
    frozen_protocol_path: str | Path,
    freeze_receipt_path: str | Path,
    artifact_root: str | Path,
    output_dir: str | Path,
    wheel_sha256: str,
    started_at: str,
    completed_at: str,
) -> ResultSnapshotWriteResult:
    """Validate and exclusively publish a content-addressed result and receipt."""

    assert_valid_bundle(result_bundle)
    frozen = load_validation_bundle(frozen_protocol_path)
    verify_protocol_continuity(frozen, result_bundle)
    artifact_results = verify_artifacts(result_bundle, artifact_root)
    if any(result.status != "PASS" for result in artifact_results):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.ARTIFACT,
                    "RESULT.ARTIFACT_VERIFICATION_FAILED",
                    "/evidence",
                    "all result artifacts must verify locally before publication",
                )
            ]
        )
    protocol_sha, _, _ = _hash_bytes(Path(frozen_protocol_path))
    protocol_receipt_sha, _, _ = _hash_bytes(Path(freeze_receipt_path))
    result_bytes = canonical_bundle_bytes(result_bundle)
    result_sha = hashlib.sha256(result_bytes).hexdigest()
    outcomes = Counter(item["outcome"] for item in result_bundle["comparisons"])
    comparison_counts = {
        name: outcomes.get(name, 0)
        for name in ("PASS", "FAIL", "ERROR", "INCONCLUSIVE", "NOT_EVALUATED")
    }
    receipt_document: dict[str, Any] = {
        "receipt_version": EXECUTION_RECEIPT_VERSION,
        "snapshot_type": RESULT_SNAPSHOT_TYPE,
        "canonicalization": CANONICALIZATION_NAME,
        "bundle_schema_version": result_bundle["schema_version"],
        "protocol_bundle_sha256": protocol_sha,
        "protocol_receipt_sha256": protocol_receipt_sha,
        "result_bundle_sha256": result_sha,
        "result_bundle_size_bytes": len(result_bytes),
        "result_relative_uri": "result-bundle.json",
        "campaign_id": result_bundle["campaign"]["campaign_id"],
        "sut_commit": result_bundle["campaign"]["system_under_test"]["git_commit"],
        "wheel_sha256": wheel_sha256,
        "started_at": started_at,
        "completed_at": completed_at,
        "run_ids": [run["run_id"] for run in result_bundle["runs"]],
        "case_count": len(result_bundle["cases"]),
        "comparison_counts": comparison_counts,
        "claims": [
            {"claim_id": claim["claim_id"], "level": claim["level"], "status": claim["status"]}
            for claim in result_bundle["claims"]
        ],
        "artifact_verification_summary": _summary(artifact_results),
        "tool": {
            "name": "spmkit-validation",
            "version": _tool_version(),
            "git_commit": _tool_commit(),
        },
        "limitations": [
            "Tamper evidence detects byte changes but does not authenticate a producer.",
            "Synthetic analytical evidence does not establish physical or cross-validation claims.",
            "Local repetition in one environment is not LEVEL 5 evidence.",
        ],
    }
    software_runs = [
        run for run in result_bundle["runs"] if run.get("run_type") == "SOFTWARE_TEST"
    ]
    if software_runs:
        if len(software_runs) != 1:
            raise CampaignExecutionError(
                [
                    execution_issue(
                        CampaignExecutionIssueCategory.RECEIPT,
                        "EXECUTION_RECEIPT.SOFTWARE_RUN_COUNT",
                        "/runs",
                        "cumulative receipt requires exactly one SOFTWARE_TEST run",
                    )
                ]
            )
        artifacts = {item["artifact_id"]: item for item in result_bundle["evidence"]}
        junit = artifacts.get("artifact.software-test.junit")
        manifest = artifacts.get("artifact.software-test.suite-manifest")
        if junit is None or manifest is None:
            raise CampaignExecutionError(
                [
                    execution_issue(
                        CampaignExecutionIssueCategory.RECEIPT,
                        "EXECUTION_RECEIPT.SOFTWARE_EVIDENCE_MISSING",
                        "/evidence",
                        "cumulative receipt requires JUnit and suite-manifest evidence",
                    )
                ]
            )
        receipt_document["software_verification"] = {
            "software_test_run_id": software_runs[0]["run_id"],
            "junit_sha256": junit["sha256"],
            "test_suite_manifest_sha256": manifest["sha256"],
            "scientific_run_ids": [
                run["run_id"]
                for run in result_bundle["runs"]
                if run.get("run_type") == "VALIDATION"
            ],
        }
    external_reference = _external_reference_summary(result_bundle, artifact_root)
    if external_reference is not None:
        receipt_document["external_reference"] = external_reference
    receipt_document["receipt_sha256"] = _payload_sha256(receipt_document)
    receipt = ExecutionReceipt.from_dict(receipt_document)
    receipt_bytes = receipt.canonical_bytes()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_root / result_sha
    try:
        snapshot_dir.mkdir(exist_ok=False)
        result_path = snapshot_dir / "result-bundle.json"
        receipt_path = snapshot_dir / "execution-receipt.json"
        _write_exclusive(result_path, result_bytes)
        _write_exclusive(receipt_path, receipt_bytes)
    except OSError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "RESULT.PUBLICATION_FAILED",
                    "/output_dir",
                    str(exc),
                )
            ]
        ) from exc
    return ResultSnapshotWriteResult(
        result_bundle_path=result_path,
        execution_receipt_path=receipt_path,
        result_bundle_sha256=result_sha,
        result_bundle_size_bytes=len(result_bytes),
        execution_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        receipt=receipt,
    )
