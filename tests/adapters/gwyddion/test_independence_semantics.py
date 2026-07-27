from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.schemas import (
    assert_valid_bundle,
    load_validation_bundle,
    validate_schema,
    validate_semantics,
)

REPOSITORY_ROOT = Path(__file__).parents[3]


@pytest.fixture
def complete_bundle() -> dict[str, Any]:
    return load_validation_bundle(
        REPOSITORY_ROOT / "examples/campaigns/synthetic_roughness_v0.1.json"
    )


def _codes(issues: tuple[Any, ...]) -> set[str]:
    return {issue.code for issue in issues}


def _level3_bundle(complete_bundle: dict[str, Any]) -> dict[str, Any]:
    reference = complete_bundle["references"][0]
    reference.update(
        {
            "reference_type": "EXTERNAL_SOFTWARE_REFERENCE",
            "name": "Fake Gwyddion semantic fixture",
            "version": "test-only",
            "producer": {
                "name": "Fake third-party producer",
                "organization": "Independent test fixture",
                "is_third_party": True,
                "operator_ids": [],
            },
            "method": "Test-only external process with structured output.",
            "independence_justification": {
                "rationale": "Test-only independent producer and scientific code path.",
                "shared_algorithms": [],
                "shared_formulas": ["Sa, Sq and Sz definitions"],
                "shared_libraries": [],
                "shared_datasets": ["dataset.synthetic.flat-plane"],
                "shared_authors": [],
                "circularity_risks": [],
                "independence_assessment": "INDEPENDENT",
            },
            "shared_dependencies": {
                "software": [],
                "data": ["dataset.synthetic.flat-plane"],
                "methods": ["Sa, Sq and Sz definitions"],
                "notes": ["Semantic fixture only; not campaign evidence."],
            },
            "known_limitations": ["Fake reference used only to test semantic rules."],
            "evidence_ids": ["artifact.reference.values"],
        }
    )
    artifact = next(
        item
        for item in complete_bundle["evidence"]
        if item["artifact_id"] == "artifact.reference.values"
    )
    artifact["producer"] = {
        "name": "Fake third-party producer",
        "version": "test-only",
    }
    claim = complete_bundle["claims"][0]
    claim["level"] = "LEVEL 3 — CROSS_VALIDATED"
    claim["claim_id"] = "claim.crossvalidated.fake-gwyddion"
    complete_bundle["campaign"]["intended_validation_level"] = (
        "LEVEL 3 — CROSS_VALIDATED"
    )
    return complete_bundle


def test_level3_accepts_complete_third_party_independent_fixture(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)

    assert_valid_bundle(bundle)


def test_level3_rejects_non_third_party_producer(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    bundle["references"][0]["producer"]["is_third_party"] = False

    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(validate_semantics(bundle))


def test_level3_rejects_partially_independent_assessment(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    bundle["references"][0]["independence_justification"][
        "independence_assessment"
    ] = "PARTIALLY_INDEPENDENT"

    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(validate_semantics(bundle))


def test_level3_rejects_reference_honestly_classified_as_derived_from_spmkit(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    justification = bundle["references"][0]["independence_justification"]
    justification["shared_algorithms"] = ["SPM-Kit scientific output reused as reference"]
    justification["circularity_risks"] = ["Reference values derive from SPM-Kit output"]
    justification["independence_assessment"] = "NOT_INDEPENDENT"

    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(validate_semantics(bundle))


def test_level3_rejects_missing_gwyddion_version(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    del bundle["references"][0]["version"]

    assert "SCHEMA.REQUIRED" in _codes(validate_schema(bundle))


def test_level3_rejects_missing_external_evidence_contract(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    del bundle["references"][0]["evidence_ids"]

    assert "SCHEMA.REQUIRED" in _codes(validate_schema(bundle))


def test_level3_rejects_external_comparison_failure(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    for comparison in bundle["comparisons"]:
        comparison.update(
            {
                "absolute_error": 1.0,
                "difference": 1.0,
                "observed": 1.0,
                "outcome": "FAIL",
                "relative_error": None,
            }
        )

    codes = _codes(validate_semantics(bundle))
    assert "CLAIM.LEVEL_2_EVIDENCE_INSUFFICIENT" in codes
    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in codes


def test_level3_rejects_level2_only_without_independent_reference(
    complete_bundle: dict[str, Any],
) -> None:
    complete_bundle["claims"][0]["level"] = "LEVEL 3 — CROSS_VALIDATED"

    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(
        validate_semantics(complete_bundle)
    )


def test_new_language_or_process_does_not_create_independence(
    complete_bundle: dict[str, Any],
) -> None:
    bundle = _level3_bundle(complete_bundle)
    reference = bundle["references"][0]
    reference["method"] = "Same producer and scientific code wrapped by another process."
    reference["producer"]["is_third_party"] = False
    justification = reference["independence_justification"]
    justification["shared_algorithms"] = ["Same scientific implementation in another language"]
    justification["shared_authors"] = ["SPM-Kit contributors"]
    justification["independence_assessment"] = "NOT_INDEPENDENT"

    assert "CLAIM.LEVEL_3_EVIDENCE_INSUFFICIENT" in _codes(validate_semantics(bundle))
