"""Strict structural and semantic validation for ValidationBundle v0.1."""

from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA_VERSION = "0.1.0"
ROOT_SCHEMA_ID = "urn:spmkit-validation:schema:v0.1:validation-bundle"
SCHEMA_FILENAMES = (
    "common.schema.json",
    "dataset.schema.json",
    "reference.schema.json",
    "case.schema.json",
    "run.schema.json",
    "comparison.schema.json",
    "evidence.schema.json",
    "claim.schema.json",
    "validation-bundle.schema.json",
)


class IssueCategory(str, Enum):
    """Stable high-level classification for validation failures."""

    IO = "IO"
    SCHEMA = "SCHEMA"
    SEMANTIC = "SEMANTIC"
    REFERENCE = "REFERENCE"
    OUTCOME_CONTRADICTION = "OUTCOME_CONTRADICTION"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One immutable validation issue."""

    category: IssueCategory
    code: str
    path: str
    description: str


class ValidationBundleError(Exception):
    """Base exception carrying one or more structured issues."""

    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{issue.code} at {issue.path}: {issue.description}" for issue in self.issues
        )
        super().__init__(summary or "ValidationBundle validation failed")


class ValidationBundleIOError(ValidationBundleError):
    """The JSON document could not be read strictly."""


class ValidationSchemaError(ValidationBundleError):
    """The document does not conform to the normative JSON Schema."""


class ValidationSemanticError(ValidationBundleError):
    """The document violates cross-entity or quantitative invariants."""


class _DuplicateJSONKey(ValueError):
    pass


def _json_pointer(parts: Iterable[object]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else ""


def _issue(
    category: IssueCategory, code: str, path: str, description: str
) -> ValidationIssue:
    return ValidationIssue(category=category, code=code, path=path, description=description)


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant {value!r}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_validation_bundle(path: str | Path) -> dict[str, Any]:
    """Load canonical JSON without accepting duplicate keys, NaN, or Infinity."""

    bundle_path = Path(path)
    try:
        with bundle_path.open(encoding="utf-8") as handle:
            document = json.load(
                handle,
                parse_constant=_reject_nonstandard_constant,
                object_pairs_hook=_reject_duplicate_keys,
            )
    except OSError as exc:
        raise ValidationBundleIOError(
            [_issue(IssueCategory.IO, "IO.READ_FAILED", "", str(exc))]
        ) from exc
    except _DuplicateJSONKey as exc:
        raise ValidationBundleIOError(
            [_issue(IssueCategory.IO, "IO.DUPLICATE_JSON_KEY", "", str(exc))]
        ) from exc
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationBundleIOError(
            [_issue(IssueCategory.IO, "IO.INVALID_JSON", "", str(exc))]
        ) from exc
    if not isinstance(document, dict):
        raise ValidationBundleIOError(
            [
                _issue(
                    IssueCategory.IO,
                    "IO.ROOT_NOT_OBJECT",
                    "",
                    "the ValidationBundle JSON root must be an object",
                )
            ]
        )
    return document


def _source_schema_directory() -> Path | None:
    candidate = Path(__file__).resolve().parents[3] / "schemas" / "v0.1"
    return candidate if candidate.is_dir() else None


def _read_schema_documents() -> tuple[dict[str, Any], ...]:
    source_directory = _source_schema_directory()
    documents: list[dict[str, Any]] = []
    if source_directory is not None:
        for filename in SCHEMA_FILENAMES:
            documents.append(json.loads((source_directory / filename).read_text(encoding="utf-8")))
        return tuple(documents)

    package_root = resources.files("spmkit_validation").joinpath("_schema_resources/v0.1")
    for filename in SCHEMA_FILENAMES:
        documents.append(json.loads(package_root.joinpath(filename).read_text(encoding="utf-8")))
    return tuple(documents)


def _build_validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    documents = _read_schema_documents()
    for document in documents:
        Draft202012Validator.check_schema(document)
    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents
    )
    root = next(document for document in documents if document["$id"] == ROOT_SCHEMA_ID)
    return Draft202012Validator(root, registry=registry, format_checker=FormatChecker())


_SCHEMA_CODE_BY_VALIDATOR = {
    "additionalProperties": "SCHEMA.ADDITIONAL_PROPERTY",
    "const": "SCHEMA.CONST",
    "enum": "SCHEMA.ENUM",
    "format": "SCHEMA.FORMAT",
    "maxItems": "SCHEMA.MAX_ITEMS",
    "minItems": "SCHEMA.MIN_ITEMS",
    "not": "SCHEMA.FORBIDDEN_PROPERTY",
    "oneOf": "SCHEMA.ONE_OF",
    "pattern": "SCHEMA.PATTERN",
    "required": "SCHEMA.REQUIRED",
    "type": "SCHEMA.TYPE",
    "uniqueItems": "SCHEMA.UNIQUE_ITEMS",
}


def validate_schema(bundle: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
    """Return every structural issue without changing *bundle*."""

    if not isinstance(bundle, Mapping):
        return (
            _issue(
                IssueCategory.SCHEMA,
                "SCHEMA.ROOT_TYPE",
                "",
                "the ValidationBundle root must be an object",
            ),
        )
    try:
        errors = sorted(_build_validator().iter_errors(bundle), key=lambda error: list(error.path))
    except Exception as exc:  # registry/schema failures must be visible, never bypassed
        return (
            _issue(
                IssueCategory.SCHEMA,
                "SCHEMA.REFERENCE_RESOLUTION",
                "",
                f"schema registry could not validate the bundle: {exc}",
            ),
        )

    issues: list[ValidationIssue] = []
    for error in errors:
        path = _json_pointer(error.absolute_path)
        if path == "/schema_version" and error.validator == "const":
            code = "SCHEMA.VERSION_INCOMPATIBLE"
        else:
            code = _SCHEMA_CODE_BY_VALIDATOR.get(error.validator, "SCHEMA.VIOLATION")
        issues.append(_issue(IssueCategory.SCHEMA, code, path, error.message))
    return tuple(issues)


def _entity_index(items: Any, id_field: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return {}
    return {
        item[id_field]: item
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get(id_field), str)
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _walk_values(
    value: Any, path: tuple[object, ...] = ()
) -> Iterable[tuple[Any, tuple[object, ...]]]:
    yield value, path
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_values(child, (*path, key))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            yield from _walk_values(child, (*path, index))


_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


def _unsafe_locator(value: str) -> bool:
    if value.startswith("/") or _WINDOWS_ABSOLUTE.match(value):
        return True
    parsed = urlsplit(value)
    if parsed.scheme.lower() == "file":
        return True
    if parsed.scheme:
        return False
    normalized = value.replace("\\", "/")
    return any(part == ".." for part in normalized.split("/"))


def _command_contains_absolute_path(token: str) -> bool:
    candidates = (token, token.split("=", 1)[1] if "=" in token else "")
    return any(candidate and _unsafe_locator(candidate) for candidate in candidates)


def _check_bulk_container(
    value: Any, path: tuple[object, ...], issues: list[ValidationIssue]
) -> None:
    for child, child_path in _walk_values(value, path):
        if isinstance(child, Mapping) and len(child) > 64:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "SEMANTIC.EMBEDDED_BULK_DATA",
                    _json_pointer(child_path),
                    "large maps must be stored as checksummed evidence artifacts",
                )
            )
        elif (
            isinstance(child, Sequence)
            and not isinstance(child, (str, bytes))
            and len(child) > 64
        ):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "SEMANTIC.EMBEDDED_BULK_DATA",
                    _json_pointer(child_path),
                    "large arrays must be stored as checksummed evidence artifacts",
                )
            )


def _add_missing_reference(
    issues: list[ValidationIssue], path: str, kind: str, identifier: Any
) -> None:
    issues.append(
        _issue(
            IssueCategory.REFERENCE,
            f"REFERENCE.UNKNOWN_{kind.upper()}",
            path,
            f"referenced {kind} ID {identifier!r} does not exist",
        )
    )


def _metric_matches(declared: Any, calculated: float | None) -> bool:
    if calculated is None:
        return declared is None
    return isinstance(declared, (int, float)) and not isinstance(declared, bool) and math.isclose(
        float(declared), calculated, rel_tol=1e-12, abs_tol=1e-15
    )


def _ordered_float_bits(value: float) -> int:
    bits = struct.unpack(">q", struct.pack(">d", value))[0]
    return 0x8000000000000000 - bits if bits < 0 else bits + 0x8000000000000000


def _ulp_distance(left: float, right: float) -> int:
    return abs(_ordered_float_bits(left) - _ordered_float_bits(right))


def _calculate_metrics(comparison: Mapping[str, Any]) -> dict[str, float | None]:
    observed = float(comparison["observed"])
    reference = float(comparison["reference"])
    difference = observed - reference
    absolute_error = abs(difference)
    relative_error = None if reference == 0.0 else absolute_error / abs(reference)
    observed_uncertainty = comparison.get("observed_uncertainty")
    reference_uncertainty = comparison.get("reference_uncertainty")
    normalized_error = None
    if isinstance(observed_uncertainty, (int, float)) and isinstance(
        reference_uncertainty, (int, float)
    ):
        combined = math.hypot(float(observed_uncertainty), float(reference_uncertainty))
        if combined > 0.0:
            normalized_error = absolute_error / combined
    return {
        "difference": difference,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "normalized_error": normalized_error,
    }


def _tolerance_passes(
    tolerance: Mapping[str, Any], comparison: Mapping[str, Any], metrics: Mapping[str, Any]
) -> bool | None:
    tolerance_type = tolerance.get("type")
    if tolerance_type == "ABSOLUTE":
        return metrics["absolute_error"] <= tolerance["absolute"]
    if tolerance_type == "RELATIVE":
        return (
            metrics["relative_error"] is not None
            and metrics["relative_error"] <= tolerance["relative"]
        )
    if tolerance_type == "ABSOLUTE_AND_RELATIVE":
        return (
            metrics["absolute_error"] <= tolerance["absolute"]
            and metrics["relative_error"] is not None
            and metrics["relative_error"] <= tolerance["relative"]
        )
    if tolerance_type == "INTERVAL":
        return tolerance["lower"] <= comparison["observed"] <= tolerance["upper"]
    if tolerance_type == "ULP":
        distance = _ulp_distance(
            float(comparison["observed"]), float(comparison["reference"])
        )
        return distance <= tolerance["max_ulp"]
    if tolerance_type == "UNCERTAINTY_NORMALIZED":
        return (
            metrics["normalized_error"] is not None
            and metrics["normalized_error"] <= tolerance["max_normalized_error"]
        )
    return None


def _validate_claim_support(
    claim: Mapping[str, Any],
    claim_index: int,
    datasets: Mapping[str, Mapping[str, Any]],
    references: Mapping[str, Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    runs: Mapping[str, Mapping[str, Any]],
    comparisons: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
    issues: list[ValidationIssue],
) -> None:
    base_path = f"/claims/{claim_index}"
    level = claim.get("level")
    status = claim.get("status")
    if status == "PROPOSED":
        if level != "LEVEL 0 — CLAIMED":
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.PROPOSED_ABOVE_LEVEL_0",
                    f"{base_path}/level",
                    "a proposed claim has no supported level above LEVEL 0",
                )
            )
        return
    if status == "REJECTED":
        return
    if status not in {"SUPPORTED", "SUPERSEDED"}:
        return
    if level == "LEVEL 0 — CLAIMED":
        issues.append(
            _issue(
                IssueCategory.SEMANTIC,
                "CLAIM.LEVEL_0_NOT_SUPPORTED",
                f"{base_path}/level",
                "LEVEL 0 is claimed, not an evidence-supported validation level",
            )
        )
        return

    supported_case_ids = set(claim.get("supported_case_ids", []))
    supported_comparison_ids = set(claim.get("supported_comparison_ids", []))
    supported_evidence_ids = set(claim.get("supported_evidence_ids", []))
    supported_runs = [
        run
        for run in runs.values()
        if supported_case_ids.intersection(run.get("case_ids", []))
    ]
    supported_comparisons = [
        comparisons[comparison_id]
        for comparison_id in supported_comparison_ids
        if comparison_id in comparisons
    ]
    supported_artifacts = [
        evidence[artifact_id]
        for artifact_id in supported_evidence_ids
        if artifact_id in evidence
    ]

    successful_test_runs = [
        run
        for run in supported_runs
        if run.get("run_type") == "SOFTWARE_TEST"
        and run.get("execution_status") == "COMPLETED"
        and not run.get("errors")
    ]
    software_test_artifacts = [
        artifact
        for artifact in supported_artifacts
        if artifact.get("scientific_role") == "SOFTWARE_TEST_RESULT"
        and any(
            artifact.get("artifact_id") in run.get("output_artifact_ids", [])
            for run in successful_test_runs
        )
    ]
    if not successful_test_runs or not software_test_artifacts:
        issues.append(
            _issue(
                IssueCategory.SEMANTIC,
                "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT",
                f"{base_path}/level",
                "LEVEL 1+ requires a completed SOFTWARE_TEST run and linked "
                "successful test evidence",
            )
        )

    numeric_levels = {
        "LEVEL 2 — NUMERICALLY_VERIFIED",
        "LEVEL 3 — CROSS_VALIDATED",
        "LEVEL 4 — PHYSICALLY_VALIDATED",
        "LEVEL 5 — REPRODUCIBILITY_VALIDATED",
    }
    if level in numeric_levels:
        numeric_qualifiers = []
        for comparison in supported_comparisons:
            case = cases.get(comparison.get("case_id"))
            if not case:
                continue
            dataset = datasets.get(case.get("dataset_id"), {})
            reference = references.get(case.get("reference_id"), {})
            if reference.get("reference_type") == "ANALYTICAL_REFERENCE" or dataset.get(
                "source_type"
            ) == "SYNTHETIC":
                numeric_qualifiers.append(comparison)
        if not supported_comparisons or any(
            comparison.get("outcome") != "PASS" for comparison in supported_comparisons
        ) or not numeric_qualifiers:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.LEVEL_2_EVIDENCE_INSUFFICIENT",
                    f"{base_path}/level",
                    "LEVEL 2+ requires PASS comparisons against an analytical "
                    "reference or synthetic phantom",
                )
            )

    cross_levels = {
        "LEVEL 3 — CROSS_VALIDATED",
        "LEVEL 4 — PHYSICALLY_VALIDATED",
        "LEVEL 5 — REPRODUCIBILITY_VALIDATED",
    }
    if level in cross_levels:
        independent_comparisons = []
        for comparison in supported_comparisons:
            case = cases.get(comparison.get("case_id"))
            reference = references.get(case.get("reference_id"), {}) if case else {}
            assessment = reference.get("independence_justification", {}).get(
                "independence_assessment"
            )
            if (
                comparison.get("outcome") == "PASS"
                and reference.get("reference_type")
                in {
                    "INDEPENDENT_IMPLEMENTATION",
                    "EXTERNAL_SOFTWARE_REFERENCE",
                    "INDEPENDENT_LAB_REPRODUCTION",
                }
                and reference.get("producer", {}).get("is_third_party") is True
                and assessment == "INDEPENDENT"
            ):
                independent_comparisons.append(comparison)
        if not independent_comparisons:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT",
                    f"{base_path}/level",
                    "LEVEL 3+ requires a PASS comparison against a third-party "
                    "reference classified INDEPENDENT",
                )
            )

    physical_levels = {
        "LEVEL 4 — PHYSICALLY_VALIDATED",
        "LEVEL 5 — REPRODUCIBILITY_VALIDATED",
    }
    if level in physical_levels:
        physical_comparisons = []
        for comparison in supported_comparisons:
            case = cases.get(comparison.get("case_id"))
            dataset = datasets.get(case.get("dataset_id"), {}) if case else {}
            reference = references.get(case.get("reference_id"), {}) if case else {}
            tolerance = next(
                (
                    candidate
                    for candidate in case.get("tolerances", [])
                    if candidate.get("tolerance_id") == comparison.get("tolerance_used")
                ),
                {},
            ) if case else {}
            if (
                comparison.get("outcome") == "PASS"
                and dataset.get("role") == "PHYSICAL_REFERENCE"
                and reference.get("reference_type") == "PHYSICAL_REFERENCE_ARTIFACT"
                and tolerance.get("type") == "UNCERTAINTY_NORMALIZED"
                and comparison.get("observed_uncertainty") is not None
                and comparison.get("reference_uncertainty") is not None
            ):
                physical_comparisons.append(comparison)
        roles = {artifact.get("scientific_role") for artifact in supported_artifacts}
        calibration_certificates = [
            artifact
            for artifact in supported_artifacts
            if artifact.get("artifact_type") == "PHYSICAL_CALIBRATION_CERTIFICATE"
            and artifact.get("scientific_role") == "CALIBRATION"
        ]
        if (
            not physical_comparisons
            or not calibration_certificates
            or "UNCERTAINTY" not in roles
        ):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.LEVEL_4_EVIDENCE_INSUFFICIENT",
                    f"{base_path}/level",
                    "LEVEL 4+ requires physical-reference PASS comparisons, "
                    "calibration, and uncertainty evidence",
                )
            )

    if level == "LEVEL 5 — REPRODUCIBILITY_VALIDATED":
        dimensions = claim.get("scope", {}).get("reproducibility_dimensions", [])
        fields = {
            "ENVIRONMENT": "environment_id",
            "PLATFORM": "platform",
            "OPERATOR": "operator_id",
            "INSTRUMENT": "instrument_id",
            "LABORATORY": "laboratory_id",
        }
        completed_runs = [
            run for run in supported_runs if run.get("execution_status") == "COMPLETED"
        ]
        insufficient = not dimensions or any(
            len(
                {
                    run.get("environment", {}).get(fields[dimension])
                    for run in completed_runs
                    if run.get("environment", {}).get(fields[dimension]) is not None
                }
            )
            < 2
            for dimension in dimensions
        )
        if insufficient or not supported_comparisons or any(
            comparison.get("outcome") != "PASS" for comparison in supported_comparisons
        ):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.LEVEL_5_EVIDENCE_INSUFFICIENT",
                    f"{base_path}/level",
                    "LEVEL 5 requires PASS comparisons and at least two values "
                    "for every declared reproducibility dimension",
                )
            )


def validate_semantics(bundle: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
    """Return cross-entity and quantitative issues without mutating *bundle*."""

    required = {
        "campaign",
        "datasets",
        "references",
        "cases",
        "runs",
        "comparisons",
        "evidence",
        "claims",
    }
    if not isinstance(bundle, Mapping) or not required.issubset(bundle):
        return (
            _issue(
                IssueCategory.SEMANTIC,
                "SEMANTIC.SCHEMA_PREREQUISITE",
                "",
                "semantic validation requires a structurally complete bundle",
            ),
        )

    issues: list[ValidationIssue] = []
    campaign = bundle.get("campaign", {})
    datasets = _entity_index(bundle.get("datasets"), "dataset_id")
    references = _entity_index(bundle.get("references"), "reference_id")
    cases = _entity_index(bundle.get("cases"), "case_id")
    runs = _entity_index(bundle.get("runs"), "run_id")
    comparisons = _entity_index(bundle.get("comparisons"), "comparison_id")
    evidence = _entity_index(bundle.get("evidence"), "artifact_id")

    for value, value_path in _walk_values(bundle):
        if isinstance(value, float) and not math.isfinite(value):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "SEMANTIC.NON_FINITE_NUMBER",
                    _json_pointer(value_path),
                    "NaN and Infinity are not valid scientific values",
                )
            )

    collections = (
        ("campaign", [campaign], "campaign_id"),
        ("datasets", bundle.get("datasets", []), "dataset_id"),
        ("references", bundle.get("references", []), "reference_id"),
        ("cases", bundle.get("cases", []), "case_id"),
        ("runs", bundle.get("runs", []), "run_id"),
        ("comparisons", bundle.get("comparisons", []), "comparison_id"),
        ("evidence", bundle.get("evidence", []), "artifact_id"),
        ("claims", bundle.get("claims", []), "claim_id"),
    )
    seen: dict[str, str] = {}
    for collection_name, items, id_field in collections:
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, Mapping) or not isinstance(item.get(id_field), str):
                continue
            identifier = item[id_field]
            path = f"/{collection_name}/{index}/{id_field}"
            if identifier in seen:
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "SEMANTIC.DUPLICATE_ID",
                        path,
                        f"ID {identifier!r} duplicates {seen[identifier]}",
                    )
                )
            else:
                seen[identifier] = path

    tolerance_ids: dict[str, str] = {}
    frozen_at = (
        _parse_timestamp(campaign.get("frozen_at")) if isinstance(campaign, Mapping) else None
    )
    created_at = (
        _parse_timestamp(campaign.get("created_at")) if isinstance(campaign, Mapping) else None
    )
    if created_at and frozen_at and frozen_at < created_at:
        issues.append(
            _issue(
                IssueCategory.SEMANTIC,
                "CAMPAIGN.FROZEN_BEFORE_CREATED",
                "/campaign/frozen_at",
                "frozen_at cannot precede created_at",
            )
        )
    if campaign.get("status") == "DRAFT" and (
        bundle.get("runs")
        or bundle.get("comparisons")
        or any(
            claim.get("status") == "SUPPORTED"
            for claim in bundle.get("claims", [])
            if isinstance(claim, Mapping)
        )
    ):
        issues.append(
            _issue(
                IssueCategory.SEMANTIC,
                "CAMPAIGN.DRAFT_NOT_EVALUABLE",
                "/campaign/status",
                "a DRAFT campaign cannot contain runs, comparisons, or supported claims",
            )
        )

    lockfile_id = campaign.get("system_under_test", {}).get("lockfile_artifact_id")
    if lockfile_id is not None and lockfile_id not in evidence:
        _add_missing_reference(
            issues,
            "/campaign/system_under_test/lockfile_artifact_id",
            "artifact",
            lockfile_id,
        )

    for dataset_index, dataset in enumerate(bundle.get("datasets", [])):
        if not isinstance(dataset, Mapping):
            continue
        for artifact_index, artifact_id in enumerate(
            dataset.get("provenance", {}).get("source_artifact_ids", [])
        ):
            if artifact_id not in evidence:
                _add_missing_reference(
                    issues,
                    f"/datasets/{dataset_index}/provenance/source_artifact_ids/{artifact_index}",
                    "artifact",
                    artifact_id,
                )
        locator = dataset.get("locator")
        if isinstance(locator, str) and _unsafe_locator(locator):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "PATH.ABSOLUTE_OR_UNSAFE",
                    f"/datasets/{dataset_index}/locator",
                    "dataset locators must be relative or use a permitted non-file URI",
                )
            )

    for reference_index, reference in enumerate(bundle.get("references", [])):
        if not isinstance(reference, Mapping):
            continue
        for evidence_index, artifact_id in enumerate(reference.get("evidence_ids", [])):
            if artifact_id not in evidence:
                _add_missing_reference(
                    issues,
                    f"/references/{reference_index}/evidence_ids/{evidence_index}",
                    "artifact",
                    artifact_id,
                )
        for dataset_index, dataset_id in enumerate(
            reference.get("independence_justification", {}).get("shared_datasets", [])
        ):
            if dataset_id not in datasets:
                _add_missing_reference(
                    issues,
                    f"/references/{reference_index}/independence_justification/shared_datasets/{dataset_index}",
                    "dataset",
                    dataset_id,
                )

    for case_index, case in enumerate(bundle.get("cases", [])):
        if not isinstance(case, Mapping):
            continue
        dataset_id = case.get("dataset_id")
        reference_id = case.get("reference_id")
        dataset = datasets.get(dataset_id)
        if dataset is None:
            _add_missing_reference(issues, f"/cases/{case_index}/dataset_id", "dataset", dataset_id)
        if reference_id not in references:
            _add_missing_reference(
                issues, f"/cases/{case_index}/reference_id", "reference", reference_id
            )
        predeclared_at = _parse_timestamp(case.get("predeclared_at"))
        if frozen_at and predeclared_at and predeclared_at > frozen_at:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "TOLERANCE.NOT_PREDECLARED",
                    f"/cases/{case_index}/predeclared_at",
                    "case and tolerances must be declared no later than campaign.frozen_at",
                )
            )
        measurands = {
            item.get("measurand_id"): item
            for item in case.get("measurands", [])
            if isinstance(item, Mapping) and isinstance(item.get("measurand_id"), str)
        }
        expected_units = case.get("expected_units", {})
        if isinstance(expected_units, Mapping) and set(expected_units) != set(measurands):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CASE.EXPECTED_UNITS_MISMATCH",
                    f"/cases/{case_index}/expected_units",
                    "expected_units keys must exactly match the declared measurand IDs",
                )
            )
        for measurand_id, measurand in measurands.items():
            if expected_units.get(measurand_id) != measurand.get("canonical_unit"):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "CASE.UNIT_MISMATCH",
                        f"/cases/{case_index}/expected_units/{measurand_id}",
                        "expected unit must equal the measurand canonical unit",
                    )
                )
        tolerances_by_measurand: dict[str, int] = {}
        for tolerance_index, tolerance in enumerate(case.get("tolerances", [])):
            if not isinstance(tolerance, Mapping):
                continue
            tolerance_id = tolerance.get("tolerance_id")
            tolerance_path = f"/cases/{case_index}/tolerances/{tolerance_index}"
            if isinstance(tolerance_id, str):
                if tolerance_id in tolerance_ids:
                    issues.append(
                        _issue(
                            IssueCategory.SEMANTIC,
                            "SEMANTIC.DUPLICATE_ID",
                            f"{tolerance_path}/tolerance_id",
                            f"tolerance ID {tolerance_id!r} duplicates "
                            f"{tolerance_ids[tolerance_id]}",
                        )
                    )
                tolerance_ids[tolerance_id] = f"{tolerance_path}/tolerance_id"
            measurand_id = tolerance.get("measurand_id")
            tolerances_by_measurand[measurand_id] = tolerances_by_measurand.get(measurand_id, 0) + 1
            if measurand_id not in measurands:
                _add_missing_reference(
                    issues, f"{tolerance_path}/measurand_id", "measurand", measurand_id
                )
            elif tolerance.get("type") in {"ABSOLUTE", "ABSOLUTE_AND_RELATIVE", "INTERVAL"}:
                if tolerance.get("unit") != measurands[measurand_id].get("canonical_unit"):
                    issues.append(
                        _issue(
                            IssueCategory.SEMANTIC,
                            "TOLERANCE.UNIT_MISMATCH",
                            f"{tolerance_path}/unit",
                            "dimensional tolerance unit must match the measurand canonical unit",
                        )
                    )
            elif tolerance.get("unit") != "1":
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "TOLERANCE.UNIT_MISMATCH",
                        f"{tolerance_path}/unit",
                        "relative, ULP, and normalized tolerances must use dimensionless unit '1'",
                    )
                )
            if (
                tolerance.get("type") == "INTERVAL"
                and isinstance(tolerance.get("lower"), (int, float))
                and isinstance(tolerance.get("upper"), (int, float))
                and tolerance["lower"] > tolerance["upper"]
            ):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "TOLERANCE.INVALID_INTERVAL",
                        tolerance_path,
                        "interval lower bound must not exceed upper bound",
                    )
                )
        for measurand_id in measurands:
            if tolerances_by_measurand.get(measurand_id) != 1:
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "TOLERANCE.MISSING_OR_AMBIGUOUS",
                        f"/cases/{case_index}/tolerances",
                        f"measurand {measurand_id!r} must have exactly one predeclared tolerance",
                    )
                )
        if dataset and dataset.get("role") == "BLIND_HOLDOUT":
            if case.get("purpose") != "BLIND_EVALUATION":
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "HOLDOUT.INVALID_CASE_PURPOSE",
                        f"/cases/{case_index}/purpose",
                        "a blind holdout may only be used for BLIND_EVALUATION",
                    )
                )
            if case.get("input_selector", {}).get("selector_type") != "OPAQUE_SELECTION":
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "HOLDOUT.REVEALING_SELECTOR",
                        f"/cases/{case_index}/input_selector",
                        "a blind holdout requires an opaque selector",
                    )
                )
        _check_bulk_container(
            case.get("operation", {}).get("parameters", {}),
            ("cases", case_index, "operation", "parameters"),
            issues,
        )
        for preprocessing_index, preprocessing in enumerate(case.get("preprocessing", [])):
            if not isinstance(preprocessing, Mapping):
                continue
            artifact_id = preprocessing.get("evidence_artifact_id")
            if artifact_id is not None and artifact_id not in evidence:
                _add_missing_reference(
                    issues,
                    f"/cases/{case_index}/preprocessing/{preprocessing_index}/evidence_artifact_id",
                    "artifact",
                    artifact_id,
                )
            _check_bulk_container(
                preprocessing.get("parameters", {}),
                ("cases", case_index, "preprocessing", preprocessing_index, "parameters"),
                issues,
            )
        selector_artifact = case.get("input_selector", {}).get("evidence_artifact_id")
        if selector_artifact is not None and selector_artifact not in evidence:
            _add_missing_reference(
                issues,
                f"/cases/{case_index}/input_selector/evidence_artifact_id",
                "artifact",
                selector_artifact,
            )

    for run_index, run in enumerate(bundle.get("runs", [])):
        if not isinstance(run, Mapping):
            continue
        if run.get("campaign_id") != campaign.get("campaign_id"):
            _add_missing_reference(
                issues, f"/runs/{run_index}/campaign_id", "campaign", run.get("campaign_id")
            )
        run_case_ids = run.get("case_ids", [])
        for case_id_index, case_id in enumerate(run_case_ids):
            if case_id not in cases:
                _add_missing_reference(
                    issues,
                    f"/runs/{run_index}/case_ids/{case_id_index}",
                    "case",
                    case_id,
                )
            else:
                dataset = datasets.get(cases[case_id].get("dataset_id"), {})
                if (
                    dataset.get("role") == "BLIND_HOLDOUT"
                    and dataset.get("access_policy", {}).get("access_state") == "SEALED"
                ):
                    issues.append(
                        _issue(
                            IssueCategory.SEMANTIC,
                            "HOLDOUT.SEALED_DATA_EXECUTION",
                            f"/runs/{run_index}/case_ids/{case_id_index}",
                            "a sealed holdout cannot be executed",
                        )
                    )
        artifact_fields = ("input_artifact_ids", "output_artifact_ids")
        for field in artifact_fields:
            for artifact_index, artifact_id in enumerate(run.get(field, [])):
                if artifact_id not in evidence:
                    _add_missing_reference(
                        issues,
                        f"/runs/{run_index}/{field}/{artifact_index}",
                        "artifact",
                        artifact_id,
                    )
        manifest_id = run.get("run_manifest_artifact_id")
        manifest = evidence.get(manifest_id)
        if manifest is None:
            _add_missing_reference(
                issues,
                f"/runs/{run_index}/run_manifest_artifact_id",
                "artifact",
                manifest_id,
            )
        elif manifest.get("artifact_type") != "MANIFEST" or manifest.get(
            "media_type"
        ) != "application/json":
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "RUN.INVALID_MANIFEST_ARTIFACT",
                    f"/runs/{run_index}/run_manifest_artifact_id",
                    "run manifest must reference a MANIFEST artifact with "
                    "application/json MIME type",
                )
            )
        snapshot_id = run.get("environment", {}).get("snapshot_artifact_id")
        if snapshot_id is not None and snapshot_id not in evidence:
            _add_missing_reference(
                issues,
                f"/runs/{run_index}/environment/snapshot_artifact_id",
                "artifact",
                snapshot_id,
            )
        for field in ("errors", "warnings"):
            for message_index, message in enumerate(run.get(field, [])):
                artifact_id = message.get("evidence_id") if isinstance(message, Mapping) else None
                if artifact_id is not None and artifact_id not in evidence:
                    _add_missing_reference(
                        issues,
                        f"/runs/{run_index}/{field}/{message_index}/evidence_id",
                        "artifact",
                        artifact_id,
                    )
        started_at = _parse_timestamp(run.get("started_at"))
        finished_at = _parse_timestamp(run.get("finished_at"))
        if frozen_at and started_at and started_at < frozen_at:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "RUN.STARTED_BEFORE_FREEZE",
                    f"/runs/{run_index}/started_at",
                    "a run cannot start before the campaign is frozen",
                )
            )
        if started_at and finished_at and finished_at < started_at:
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "RUN.FINISHED_BEFORE_STARTED",
                    f"/runs/{run_index}/finished_at",
                    "finished_at cannot precede started_at",
                )
            )
        for command_index, token in enumerate(run.get("command", [])):
            if isinstance(token, str) and _command_contains_absolute_path(token):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "PATH.ABSOLUTE_OR_UNSAFE",
                        f"/runs/{run_index}/command/{command_index}",
                        "commands stored in bundles must not contain absolute user paths",
                    )
                )
        _check_bulk_container(
            run.get("parameters", {}), ("runs", run_index, "parameters"), issues
        )

    for artifact_index, artifact in enumerate(bundle.get("evidence", [])):
        if not isinstance(artifact, Mapping):
            continue
        uri = artifact.get("relative_uri")
        if isinstance(uri, str) and _unsafe_locator(uri):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "PATH.ABSOLUTE_OR_UNSAFE",
                    f"/evidence/{artifact_index}/relative_uri",
                    "artifact URI must be relative or use a permitted non-file URI",
                )
            )
        for source_index, source_id in enumerate(artifact.get("source_artifact_ids", [])):
            if source_id not in evidence:
                _add_missing_reference(
                    issues,
                    f"/evidence/{artifact_index}/source_artifact_ids/{source_index}",
                    "artifact",
                    source_id,
                )
            elif source_id == artifact.get("artifact_id"):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "EVIDENCE.SELF_REFERENCE",
                        f"/evidence/{artifact_index}/source_artifact_ids/{source_index}",
                        "an artifact cannot list itself as a source",
                    )
                )
        producer_run_id = artifact.get("producer", {}).get("run_id")
        if producer_run_id is not None and producer_run_id not in runs:
            _add_missing_reference(
                issues,
                f"/evidence/{artifact_index}/producer/run_id",
                "run",
                producer_run_id,
            )
        for command_index, token in enumerate(artifact.get("generation_command", [])):
            if isinstance(token, str) and _command_contains_absolute_path(token):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "PATH.ABSOLUTE_OR_UNSAFE",
                        f"/evidence/{artifact_index}/generation_command/{command_index}",
                        "generation commands must not contain absolute user paths",
                    )
                )

    for comparison_index, comparison in enumerate(bundle.get("comparisons", [])):
        if not isinstance(comparison, Mapping):
            continue
        case_id = comparison.get("case_id")
        run_id = comparison.get("run_id")
        case = cases.get(case_id)
        run = runs.get(run_id)
        if case is None:
            _add_missing_reference(
                issues, f"/comparisons/{comparison_index}/case_id", "case", case_id
            )
        if run is None:
            _add_missing_reference(
                issues, f"/comparisons/{comparison_index}/run_id", "run", run_id
            )
        elif case_id not in run.get("case_ids", []):
            issues.append(
                _issue(
                    IssueCategory.REFERENCE,
                    "REFERENCE.RUN_DOES_NOT_COVER_CASE",
                    f"/comparisons/{comparison_index}/run_id",
                    "the referenced run does not include the comparison case",
                )
            )
        for evidence_index, artifact_id in enumerate(comparison.get("evidence_ids", [])):
            if artifact_id not in evidence:
                _add_missing_reference(
                    issues,
                    f"/comparisons/{comparison_index}/evidence_ids/{evidence_index}",
                    "artifact",
                    artifact_id,
                )
        tolerance = None
        if case:
            measurand_ids = {
                measurand.get("measurand_id")
                for measurand in case.get("measurands", [])
                if isinstance(measurand, Mapping)
            }
            if comparison.get("measurand_id") not in measurand_ids:
                _add_missing_reference(
                    issues,
                    f"/comparisons/{comparison_index}/measurand_id",
                    "measurand",
                    comparison.get("measurand_id"),
                )
            tolerance = next(
                (
                    candidate
                    for candidate in case.get("tolerances", [])
                    if isinstance(candidate, Mapping)
                    and candidate.get("tolerance_id") == comparison.get("tolerance_used")
                    and candidate.get("measurand_id") == comparison.get("measurand_id")
                ),
                None,
            )
            if tolerance is None:
                _add_missing_reference(
                    issues,
                    f"/comparisons/{comparison_index}/tolerance_used",
                    "tolerance",
                    comparison.get("tolerance_used"),
                )
            dataset = datasets.get(case.get("dataset_id"), {})
            if (
                dataset.get("role") == "BLIND_HOLDOUT"
                and dataset.get("access_policy", {}).get("access_state") == "SEALED"
            ):
                issues.append(
                    _issue(
                        IssueCategory.SEMANTIC,
                        "HOLDOUT.SEALED_RESULT",
                        f"/comparisons/{comparison_index}",
                        "a sealed holdout cannot contain observed results",
                    )
                )

        evaluation_status = comparison.get("evaluation_status")
        run_status = run.get("execution_status") if run else None
        if run_status in {"ERROR", "ABORTED"}:
            derived_outcome = "ERROR"
        elif run_status in {"NOT_RUN", "RUNNING"}:
            derived_outcome = "NOT_EVALUATED"
        elif evaluation_status == "ERROR":
            derived_outcome = "ERROR"
        elif evaluation_status == "INCONCLUSIVE":
            derived_outcome = "INCONCLUSIVE"
        elif evaluation_status == "NOT_EVALUATED":
            derived_outcome = "NOT_EVALUATED"
        elif evaluation_status == "EVALUATED" and run_status == "COMPLETED" and tolerance:
            try:
                metrics = _calculate_metrics(comparison)
            except (KeyError, TypeError, ValueError, OverflowError):
                derived_outcome = "ERROR"
            else:
                for metric_name, calculated in metrics.items():
                    if not _metric_matches(comparison.get(metric_name), calculated):
                        issues.append(
                            _issue(
                                IssueCategory.SEMANTIC,
                                "SEMANTIC.METRIC_MISMATCH",
                                f"/comparisons/{comparison_index}/{metric_name}",
                                f"declared metric does not equal recalculated value {calculated!r}",
                            )
                        )
                if tolerance.get("type") == "UNCERTAINTY_NORMALIZED" and metrics[
                    "normalized_error"
                ] is None:
                    issues.append(
                        _issue(
                            IssueCategory.SEMANTIC,
                            "COMPARISON.UNCERTAINTY_REQUIRED",
                            f"/comparisons/{comparison_index}",
                            "uncertainty-normalized comparison requires positive "
                            "observed and reference uncertainties",
                        )
                    )
                passes = _tolerance_passes(tolerance, comparison, metrics)
                if passes is True:
                    derived_outcome = "PASS"
                elif passes is False:
                    derived_outcome = "FAIL"
                else:
                    derived_outcome = "ERROR"
        else:
            derived_outcome = "NOT_EVALUATED"
        if comparison.get("outcome") != derived_outcome:
            issues.append(
                _issue(
                    IssueCategory.OUTCOME_CONTRADICTION,
                    "OUTCOME.DECLARED_MISMATCH",
                    f"/comparisons/{comparison_index}/outcome",
                    f"declared {comparison.get('outcome')!r}, derived {derived_outcome!r}",
                )
            )

    bad_comparisons = {
        comparison.get("comparison_id"): comparison
        for comparison in bundle.get("comparisons", [])
        if isinstance(comparison, Mapping)
        and comparison.get("outcome") in {"FAIL", "ERROR", "INCONCLUSIVE"}
    }
    if bad_comparisons and not campaign.get("limitations"):
        issues.append(
            _issue(
                IssueCategory.SEMANTIC,
                "CAMPAIGN.ADVERSE_RESULTS_UNDISCLOSED",
                "/campaign/limitations",
                "campaign limitations must disclose FAIL, ERROR, and INCONCLUSIVE results",
            )
        )

    for claim_index, claim in enumerate(bundle.get("claims", [])):
        if not isinstance(claim, Mapping):
            continue
        claim_refs = (
            ("supported_case_ids", cases, "case"),
            ("supported_comparison_ids", comparisons, "comparison"),
            ("supported_evidence_ids", evidence, "artifact"),
        )
        for field, index, kind in claim_refs:
            for id_index, identifier in enumerate(claim.get(field, [])):
                if identifier not in index:
                    _add_missing_reference(
                        issues, f"/claims/{claim_index}/{field}/{id_index}", kind, identifier
                    )
        supported_cases = set(claim.get("supported_case_ids", []))
        for comparison_id in claim.get("supported_comparison_ids", []):
            comparison = comparisons.get(comparison_id)
            if comparison and comparison.get("case_id") not in supported_cases:
                issues.append(
                    _issue(
                        IssueCategory.REFERENCE,
                        "REFERENCE.CLAIM_COMPARISON_OUTSIDE_CASE_SCOPE",
                        f"/claims/{claim_index}/supported_comparison_ids",
                        "every supported comparison must belong to a supported case",
                    )
                )
        affected_bad = set(claim.get("supported_comparison_ids", [])).intersection(bad_comparisons)
        if affected_bad and not claim.get("limitations"):
            issues.append(
                _issue(
                    IssueCategory.SEMANTIC,
                    "CLAIM.ADVERSE_RESULTS_UNDISCLOSED",
                    f"/claims/{claim_index}/limitations",
                    "claim limitations must disclose supported FAIL, ERROR, or "
                    "INCONCLUSIVE comparisons",
                )
            )
        _validate_claim_support(
            claim,
            claim_index,
            datasets,
            references,
            cases,
            runs,
            comparisons,
            evidence,
            issues,
        )

    return tuple(issues)


def assert_valid_bundle(bundle: Mapping[str, Any]) -> None:
    """Raise a typed exception unless both validation layers pass."""

    schema_issues = validate_schema(bundle)
    if schema_issues:
        raise ValidationSchemaError(schema_issues)
    semantic_issues = validate_semantics(bundle)
    if semantic_issues:
        raise ValidationSemanticError(semantic_issues)
