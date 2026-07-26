"""Operational freeze receipt v0.1.0."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from .artifacts import ArtifactVerificationResult, summarize_artifact_results
from .canonical import CANONICALIZATION_NAME, canonical_bundle_bytes
from .issues import LifecycleError, LifecycleIssue, LifecycleIssueCategory, lifecycle_issue

RECEIPT_VERSION = "0.1.0"
SNAPSHOT_TYPE = "TAMPER_EVIDENT_SNAPSHOT"

_RECEIPT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:spmkit-validation:receipt:v0.1:freeze",
    "type": "object",
    "required": [
        "receipt_version",
        "snapshot_type",
        "canonicalization",
        "bundle_schema_version",
        "bundle_sha256",
        "bundle_size_bytes",
        "snapshot_relative_uri",
        "source_bundle_sha256",
        "created_at",
        "frozen_at",
        "campaign_id",
        "artifact_verification_summary",
        "artifact_verification_records",
        "tool",
        "limitations",
        "receipt_sha256",
    ],
    "properties": {
        "receipt_version": {"const": RECEIPT_VERSION},
        "snapshot_type": {"const": SNAPSHOT_TYPE},
        "canonicalization": {"const": CANONICALIZATION_NAME},
        "bundle_schema_version": {"const": "0.1.0"},
        "bundle_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "bundle_size_bytes": {"type": "integer", "minimum": 1},
        "snapshot_relative_uri": {"const": "bundle.json"},
        "source_bundle_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "created_at": {"type": "string", "format": "date-time"},
        "frozen_at": {"type": "string", "format": "date-time"},
        "campaign_id": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9._:-]{0,127}$"},
        "artifact_verification_summary": {
            "type": "object",
            "required": ["total", "passed", "failed", "remote_not_verified"],
            "properties": {
                "total": {"type": "integer", "minimum": 0},
                "passed": {"type": "integer", "minimum": 0},
                "failed": {"type": "integer", "minimum": 0},
                "remote_not_verified": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "artifact_verification_records": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "artifact_id",
                    "status",
                    "calculated_sha256",
                    "calculated_size_bytes",
                ],
                "properties": {
                    "artifact_id": {"type": "string"},
                    "status": {"enum": ["PASS", "REMOTE_ARTIFACT_NOT_VERIFIED"]},
                    "calculated_sha256": {
                        "oneOf": [
                            {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                            {"type": "null"},
                        ]
                    },
                    "calculated_size_bytes": {
                        "oneOf": [
                            {"type": "integer", "minimum": 0},
                            {"type": "null"},
                        ]
                    },
                },
                "additionalProperties": False,
            },
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
            "uniqueItems": True,
        },
        "receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class FreezeReceipt:
    """Typed operational view of a validated freeze receipt."""

    receipt_version: str
    snapshot_type: str
    canonicalization: str
    bundle_schema_version: str
    bundle_sha256: str
    bundle_size_bytes: int
    snapshot_relative_uri: str
    source_bundle_sha256: str
    created_at: str
    frozen_at: str
    campaign_id: str
    artifact_verification_summary: Mapping[str, int]
    artifact_verification_records: tuple[Mapping[str, Any], ...]
    tool: Mapping[str, Any]
    limitations: tuple[str, ...]
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_version": self.receipt_version,
            "snapshot_type": self.snapshot_type,
            "canonicalization": self.canonicalization,
            "bundle_schema_version": self.bundle_schema_version,
            "bundle_sha256": self.bundle_sha256,
            "bundle_size_bytes": self.bundle_size_bytes,
            "snapshot_relative_uri": self.snapshot_relative_uri,
            "source_bundle_sha256": self.source_bundle_sha256,
            "created_at": self.created_at,
            "frozen_at": self.frozen_at,
            "campaign_id": self.campaign_id,
            "artifact_verification_summary": dict(self.artifact_verification_summary),
            "artifact_verification_records": [
                dict(record) for record in self.artifact_verification_records
            ],
            "tool": dict(self.tool),
            "limitations": list(self.limitations),
            "receipt_sha256": self.receipt_sha256,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bundle_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> FreezeReceipt:
        issues = validate_freeze_receipt(document)
        if issues:
            raise LifecycleError(issues)
        return cls(
            receipt_version=document["receipt_version"],
            snapshot_type=document["snapshot_type"],
            canonicalization=document["canonicalization"],
            bundle_schema_version=document["bundle_schema_version"],
            bundle_sha256=document["bundle_sha256"],
            bundle_size_bytes=document["bundle_size_bytes"],
            snapshot_relative_uri=document["snapshot_relative_uri"],
            source_bundle_sha256=document["source_bundle_sha256"],
            created_at=document["created_at"],
            frozen_at=document["frozen_at"],
            campaign_id=document["campaign_id"],
            artifact_verification_summary=dict(document["artifact_verification_summary"]),
            artifact_verification_records=tuple(
                dict(record) for record in document["artifact_verification_records"]
            ),
            tool=dict(document["tool"]),
            limitations=tuple(document["limitations"]),
            receipt_sha256=document["receipt_sha256"],
        )


def _json_pointer(parts: Sequence[Any]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else ""


def _receipt_payload_sha256(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("receipt_sha256", None)
    return hashlib.sha256(canonical_bundle_bytes(payload)).hexdigest()


def validate_freeze_receipt(document: Mapping[str, Any]) -> tuple[LifecycleIssue, ...]:
    """Validate the operational receipt schema and internal checksum."""

    from jsonschema import Draft202012Validator, FormatChecker

    validator = Draft202012Validator(_RECEIPT_SCHEMA, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    issues = [
        lifecycle_issue(
            LifecycleIssueCategory.RECEIPT,
            "RECEIPT_INVALID",
            _json_pointer(list(error.absolute_path)),
            error.message,
        )
        for error in errors
    ]
    if not errors:
        records = document["artifact_verification_records"]
        artifact_ids = [record["artifact_id"] for record in records]
        summary = document["artifact_verification_summary"]
        expected_summary = {
            "total": len(records),
            "passed": sum(record["status"] == "PASS" for record in records),
            "failed": 0,
            "remote_not_verified": sum(
                record["status"] == "REMOTE_ARTIFACT_NOT_VERIFIED" for record in records
            ),
        }
        if artifact_ids != sorted(artifact_ids) or len(artifact_ids) != len(set(artifact_ids)):
            issues.append(
                lifecycle_issue(
                    LifecycleIssueCategory.RECEIPT,
                    "RECEIPT_ARTIFACT_RECORD_ORDER",
                    "/artifact_verification_records",
                    "artifact records must contain unique IDs sorted by artifact_id",
                )
            )
        if summary != expected_summary:
            issues.append(
                lifecycle_issue(
                    LifecycleIssueCategory.RECEIPT,
                    "RECEIPT_ARTIFACT_SUMMARY_MISMATCH",
                    "/artifact_verification_summary",
                    "artifact summary does not match its records",
                )
            )
        for index, record in enumerate(records):
            values_present = (
                record["calculated_sha256"] is not None
                and record["calculated_size_bytes"] is not None
            )
            if (record["status"] == "PASS") != values_present:
                issues.append(
                    lifecycle_issue(
                        LifecycleIssueCategory.RECEIPT,
                        "RECEIPT_ARTIFACT_RECORD_CONTRADICTION",
                        f"/artifact_verification_records/{index}",
                        "PASS requires calculated hash and size; unverified remote "
                        "records forbid them",
                    )
                )
    if not issues and document.get("receipt_sha256") != _receipt_payload_sha256(document):
        issues.append(
            lifecycle_issue(
                LifecycleIssueCategory.RECEIPT,
                "RECEIPT_HASH_MISMATCH",
                "/receipt_sha256",
                "receipt checksum does not match its canonical payload",
            )
        )
    return tuple(issues)


def _tool_version() -> str:
    try:
        return metadata.version("spmkit-validation")
    except metadata.PackageNotFoundError:
        from spmkit_validation import __version__

        return __version__


def _tool_git_commit() -> str | None:
    repository_root = Path(__file__).resolve().parents[3]
    if (
        not (repository_root / ".git").exists()
        or not (repository_root / "pyproject.toml").is_file()
    ):
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    candidate = result.stdout.strip().lower()
    if (
        result.returncode == 0
        and len(candidate) == 40
        and all(character in "0123456789abcdef" for character in candidate)
    ):
        return candidate
    return None


def create_freeze_receipt(
    *,
    bundle_schema_version: str,
    bundle_sha256: str,
    bundle_size_bytes: int,
    source_bundle_sha256: str,
    frozen_at: str,
    campaign_id: str,
    artifact_results: Sequence[ArtifactVerificationResult],
) -> FreezeReceipt:
    """Create a deterministic receipt for already verified snapshot bytes."""

    records = tuple(
        {
            "artifact_id": result.artifact_id,
            "status": result.status,
            "calculated_sha256": result.calculated_sha256,
            "calculated_size_bytes": result.calculated_size_bytes,
        }
        for result in artifact_results
    )
    document: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "snapshot_type": SNAPSHOT_TYPE,
        "canonicalization": CANONICALIZATION_NAME,
        "bundle_schema_version": bundle_schema_version,
        "bundle_sha256": bundle_sha256,
        "bundle_size_bytes": bundle_size_bytes,
        "snapshot_relative_uri": "bundle.json",
        "source_bundle_sha256": source_bundle_sha256,
        "created_at": frozen_at,
        "frozen_at": frozen_at,
        "campaign_id": campaign_id,
        "artifact_verification_summary": summarize_artifact_results(artifact_results),
        "artifact_verification_records": list(records),
        "tool": {
            "name": "spmkit-validation",
            "version": _tool_version(),
            "git_commit": _tool_git_commit(),
        },
        "limitations": [
            "The receipt detects later byte changes but does not authenticate its producer.",
            "Freeze records validation and local artifact integrity, not scientific truth.",
            "Remote artifacts are not downloaded or verified by PHASE_01B.",
        ],
    }
    document["receipt_sha256"] = _receipt_payload_sha256(document)
    return FreezeReceipt.from_dict(document)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    return parsed


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_receipt_document(path: str | Path) -> tuple[dict[str, Any], bytes]:
    """Load a receipt as strict JSON and preserve its exact bytes."""

    receipt_path = Path(path)
    try:
        raw = receipt_path.read_bytes()
        document = json.loads(
            raw,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            object_pairs_hook=_unique_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.RECEIPT,
                    "RECEIPT_INVALID",
                    "",
                    f"receipt is not strict finite JSON: {exc}",
                )
            ]
        ) from exc
    if not isinstance(document, dict):
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.RECEIPT,
                    "RECEIPT_INVALID",
                    "",
                    "receipt root must be an object",
                )
            ]
        )
    return document, raw
