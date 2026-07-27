from __future__ import annotations

import copy
import math
from typing import Any

import pytest

from spmkit_validation.schemas import (
    IssueCategory,
    ValidationSemanticError,
    assert_valid_bundle,
    validate_semantics,
)


def _codes(issues: tuple[Any, ...]) -> set[str]:
    return {issue.code for issue in issues}


def test_duplicate_id_is_rejected(complete_bundle: dict[str, Any]) -> None:
    duplicate = copy.deepcopy(complete_bundle["evidence"][0])
    complete_bundle["evidence"].append(duplicate)
    assert "SEMANTIC.DUPLICATE_ID" in _codes(validate_semantics(complete_bundle))


def test_missing_cross_reference_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["cases"][0]["dataset_id"] = "dataset.does-not-exist"
    issues = validate_semantics(complete_bundle)
    assert "REFERENCE.UNKNOWN_DATASET" in _codes(issues)
    assert any(issue.category is IssueCategory.REFERENCE for issue in issues)


def test_declared_pass_when_calculated_fail_is_rejected(complete_bundle: dict[str, Any]) -> None:
    comparison = complete_bundle["comparisons"][0]
    comparison.update(
        {
            "observed": 1.0,
            "reference": 0.0,
            "difference": 1.0,
            "absolute_error": 1.0,
            "relative_error": None,
            "normalized_error": None,
            "outcome": "PASS",
        }
    )
    issues = validate_semantics(complete_bundle)
    assert "OUTCOME.DECLARED_MISMATCH" in _codes(issues)
    contradiction = next(issue for issue in issues if issue.code == "OUTCOME.DECLARED_MISMATCH")
    assert contradiction.category is IssueCategory.OUTCOME_CONTRADICTION
    assert "derived 'FAIL'" in contradiction.description


def test_declared_fail_when_calculated_pass_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["comparisons"][0]["outcome"] = "FAIL"
    issues = validate_semantics(complete_bundle)
    assert "OUTCOME.DECLARED_MISMATCH" in _codes(issues)
    assert any("derived 'PASS'" in issue.description for issue in issues)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_python_number_is_rejected(
    complete_bundle: dict[str, Any], value: float
) -> None:
    complete_bundle["comparisons"][0]["observed"] = value
    assert "SEMANTIC.NON_FINITE_NUMBER" in _codes(validate_semantics(complete_bundle))


def test_level_3_without_independent_reference_is_rejected(
    complete_bundle: dict[str, Any],
) -> None:
    complete_bundle["claims"][0]["level"] = "LEVEL 3 — CROSS_VALIDATED"
    issues = validate_semantics(complete_bundle)
    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(issues)


def test_level_4_without_calibration_and_uncertainty_is_rejected(
    complete_bundle: dict[str, Any],
) -> None:
    complete_bundle["claims"][0]["level"] = "LEVEL 4 — PHYSICALLY_VALIDATED"
    issues = validate_semantics(complete_bundle)
    assert "CLAIM.LEVEL_4_EVIDENCE_INSUFFICIENT" in _codes(issues)


def test_claim_with_unknown_evidence_id_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["claims"][0]["supported_evidence_ids"].append("artifact.missing")
    issues = validate_semantics(complete_bundle)
    assert "REFERENCE.UNKNOWN_ARTIFACT" in _codes(issues)


def test_tolerance_declared_after_freeze_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["cases"][0]["predeclared_at"] = "2026-01-02T00:00:01Z"
    assert "TOLERANCE.NOT_PREDECLARED" in _codes(validate_semantics(complete_bundle))


def test_holdout_cannot_be_used_for_development(complete_bundle: dict[str, Any]) -> None:
    dataset = complete_bundle["datasets"][0]
    dataset["role"] = "BLIND_HOLDOUT"
    dataset["sealed_id"] = "sealed.synthetic.opaque"
    dataset["access_policy"] = {"access_level": "SEALED", "access_state": "AUTHORIZED"}
    dataset["public_metadata"] = {}
    dataset.pop("locator")
    complete_bundle["cases"][0]["purpose"] = "DEVELOPMENT"
    complete_bundle["cases"][0]["input_selector"] = {
        "selector_type": "OPAQUE_SELECTION",
        "opaque_selector_id": "selector.opaque.01",
    }
    assert "HOLDOUT.INVALID_CASE_PURPOSE" in _codes(validate_semantics(complete_bundle))


def test_error_state_is_preserved_and_never_becomes_pass(complete_bundle: dict[str, Any]) -> None:
    comparison = complete_bundle["comparisons"][0]
    comparison["evaluation_status"] = "ERROR"
    comparison["evaluation_error"] = "Synthetic evaluation exception"
    comparison["outcome"] = "ERROR"
    issues = validate_semantics(complete_bundle)
    assert "OUTCOME.DECLARED_MISMATCH" not in _codes(issues)


def test_metric_mismatch_is_rejected_even_when_outcome_matches(
    complete_bundle: dict[str, Any],
) -> None:
    complete_bundle["comparisons"][0]["difference"] = 123.0
    assert "SEMANTIC.METRIC_MISMATCH" in _codes(validate_semantics(complete_bundle))


def test_assert_valid_bundle_raises_typed_semantic_error(
    complete_bundle: dict[str, Any],
) -> None:
    complete_bundle["comparisons"][0]["outcome"] = "FAIL"
    with pytest.raises(ValidationSemanticError) as caught:
        assert_valid_bundle(complete_bundle)
    assert "OUTCOME.DECLARED_MISMATCH" in _codes(caught.value.issues)
