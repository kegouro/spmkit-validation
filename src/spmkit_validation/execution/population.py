"""Populate runs, derived comparisons and narrow claims into a result bundle."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping
from typing import Any

from spmkit_validation.schemas import assert_valid_bundle

from .continuity import verify_protocol_continuity
from .ground_truth import MEASURANDS
from .runner import CampaignExecutionResult


def _passes(tolerance: Mapping[str, Any], absolute: float, relative: float | None) -> bool:
    tolerance_type = tolerance["type"]
    if tolerance_type == "ABSOLUTE":
        return absolute <= tolerance["absolute"]
    if tolerance_type == "ABSOLUTE_AND_RELATIVE":
        return (
            absolute <= tolerance["absolute"]
            and relative is not None
            and relative <= tolerance["relative"]
        )
    raise ValueError(f"PHASE_01C protocol uses unsupported tolerance {tolerance_type!r}")


def _claim(
    measurand: str,
    cases: list[Mapping[str, Any]],
    comparisons: list[Mapping[str, Any]],
    evidence_ids: list[str],
) -> dict[str, Any]:
    selected = [item for item in comparisons if item["measurand_id"] == measurand]
    outcomes = Counter(item["outcome"] for item in selected)
    limitations = [
        (
            "Claim remains LEVEL 0 because this six-run campaign contains no completed "
            "SOFTWARE_TEST run or SOFTWARE_TEST_RESULT evidence required by "
            "ValidationBundle v0.1 for LEVEL 1+."
        ),
        (
            "Scope is six synthetic NPZ phantoms, no leveling, 16x16 and 32x32, "
            "SPM-Kit 0.1.5.dev0 at commit "
            "11daf8879c9e3e098ce844778592525d4f2bdc53."
        ),
        "Analytical reference and protocol share authorship and are not third-party independent.",
    ]
    if any(outcome != "PASS" for outcome in outcomes):
        limitations.append(
            "Non-PASS comparisons are preserved: "
            + ", ".join(f"{name}={count}" for name, count in sorted(outcomes.items()))
            + "."
        )
    return {
        "claim_id": f"claim.synthetic.{measurand}",
        "claim_text": (
            f"Proposed scoped claim for {measurand} recovery on the declared synthetic "
            "flat, checkerboard and four-level NPZ phantoms without leveling."
        ),
        "level": "LEVEL 0 — CLAIMED",
        "scope": {
            "description": (
                f"{measurand}; synthetic NPZ; no preprocessing; resolutions 16x16 and "
                "32x32; SPM-Kit commit 11daf8879c9e3e098ce844778592525d4f2bdc53."
            ),
            "measurands": [measurand],
            "dataset_roles": ["VERIFICATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [case["case_id"] for case in cases],
        "supported_comparison_ids": [item["comparison_id"] for item in selected],
        "supported_evidence_ids": evidence_ids,
        "limitations": limitations,
        "status": "PROPOSED",
    }


def populate_result_bundle(
    frozen_protocol_bundle: Mapping[str, Any],
    execution_result: CampaignExecutionResult,
    ground_truth_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a validated result copy; outcomes are calculated, never accepted as input."""

    bundle = copy.deepcopy(dict(frozen_protocol_bundle))
    bundle["campaign"]["status"] = (
        "COMPLETED"
        if all(run["execution_status"] == "COMPLETED" for run in execution_result.runs)
        else "ABORTED"
    )
    if bundle["campaign"]["status"] == "ABORTED":
        bundle["campaign"]["limitations"].append(
            "One or more SUT runs ended in ERROR; all failures and missing observations "
            "are preserved."
        )
    bundle["runs"] = [copy.deepcopy(dict(run)) for run in execution_result.runs]
    bundle["evidence"] = sorted(
        [*bundle["evidence"], *(copy.deepcopy(dict(item)) for item in execution_result.evidence)],
        key=lambda item: item["artifact_id"],
    )
    truth_by_case = {
        record["case_id"]: record["analytical"] for record in ground_truth_document["cases"]
    }
    runs_by_case = {run["case_ids"][0]: run for run in bundle["runs"]}
    comparisons: list[dict[str, Any]] = []
    for case in bundle["cases"]:
        case_id = case["case_id"]
        run = runs_by_case[case_id]
        tolerances = {item["measurand_id"]: item for item in case["tolerances"]}
        for measurand in MEASURANDS:
            reference = float(truth_by_case[case_id][measurand])
            tolerance = tolerances[measurand]
            base: dict[str, Any] = {
                "comparison_id": f"comparison.{case_id}.{measurand}",
                "case_id": case_id,
                "run_id": run["run_id"],
                "measurand_id": measurand,
                "reference": reference,
                "tolerance_used": tolerance["tolerance_id"],
                "evidence_ids": [
                    "artifact.reference.ground-truth",
                    f"artifact.result-json.{case_id}",
                ]
                if run["execution_status"] == "COMPLETED"
                else ["artifact.reference.ground-truth", run["run_manifest_artifact_id"]],
                "notes": [
                    "Outcome and metrics were derived from frozen truth and official SUT JSON."
                ],
            }
            if run["execution_status"] == "COMPLETED" and case_id in execution_result.observations:
                observed = float(execution_result.observations[case_id][measurand])
                difference = observed - reference
                absolute = abs(difference)
                relative = None if reference == 0.0 else absolute / abs(reference)
                outcome = "PASS" if _passes(tolerance, absolute, relative) else "FAIL"
                base.update(
                    {
                        "observed": observed,
                        "difference": difference,
                        "absolute_error": absolute,
                        "relative_error": relative,
                        "normalized_error": None,
                        "evaluation_status": "EVALUATED",
                        "outcome": outcome,
                    }
                )
            else:
                error_text = "; ".join(error["message"] for error in run["errors"])
                base.update(
                    {
                        "observed": None,
                        "difference": None,
                        "absolute_error": None,
                        "relative_error": None,
                        "normalized_error": None,
                        "evaluation_status": "ERROR",
                        "evaluation_error": error_text or "SUT result unavailable",
                        "outcome": "ERROR",
                    }
                )
            comparisons.append(base)
    bundle["comparisons"] = comparisons
    quantitative_evidence = sorted(
        artifact["artifact_id"]
        for artifact in bundle["evidence"]
        if artifact["scientific_role"] in {"QUANTITATIVE_RESULT", "REFERENCE_VALUE"}
    )
    bundle["claims"] = [
        _claim(measurand, bundle["cases"], comparisons, quantitative_evidence)
        for measurand in MEASURANDS
    ]
    verify_protocol_continuity(frozen_protocol_bundle, bundle)
    assert_valid_bundle(bundle)
    return bundle


def normalized_scientific_record(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Remove authorized timing/path variability for an independent repetition."""

    artifacts = {
        item["artifact_id"]: item
        for item in bundle["evidence"]
        if item["artifact_id"].startswith(
            ("artifact.result-json.", "artifact.result-csv.")
        )
    }
    return {
        "campaign_id": bundle["campaign"]["campaign_id"],
        "determinism_requirement": bundle["campaign"]["determinism_requirement"],
        "runs": [
            {
                "run_id": run["run_id"],
                "exit_code": run["parameters"].get("exit_code"),
                "execution_status": run["execution_status"],
            }
            for run in bundle["runs"]
        ],
        "comparisons": [
            {
                key: comparison[key]
                for key in (
                    "comparison_id",
                    "observed",
                    "reference",
                    "difference",
                    "absolute_error",
                    "relative_error",
                    "outcome",
                )
            }
            for comparison in bundle["comparisons"]
        ],
        "deterministic_output_hashes": {
            artifact_id: artifact["sha256"] for artifact_id, artifact in sorted(artifacts.items())
        },
    }


def compare_campaign_repetition(
    first_bundle: Mapping[str, Any], second_bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare normalized scientific records without implying LEVEL 5."""

    first = normalized_scientific_record(first_bundle)
    second = normalized_scientific_record(second_bundle)
    return {
        "repeatability_version": "0.1.0",
        "status": "PASS" if first == second else "FAIL",
        "determinism_category": "NUMERICALLY_REPEATABLE",
        "records_equal": first == second,
        "level_5_claimed": False,
        "first": first,
        "second": second,
    }
