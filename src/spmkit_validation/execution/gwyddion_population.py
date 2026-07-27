"""Derived external comparisons and cumulative LEVEL 1/2/3 claims."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping
from typing import Any

from spmkit_validation.schemas import assert_valid_bundle

from .continuity import verify_protocol_continuity
from .cumulative_protocol import SOFTWARE_CASE_ID
from .ground_truth import MEASURANDS
from .gwyddion_cross_validation import GwyddionCrossValidationExecutionResult
from .gwyddion_protocol import (
    EXTERNAL_REFERENCE_ID,
    FORMAT_ARTIFACT_ID,
    GWYDDION_IDENTITY_ARTIFACT_ID,
    HELPER_BINARY_ARTIFACT_ID,
    HELPER_BUILD_ARTIFACT_ID,
    HELPER_SOURCE_ARTIFACT_ID,
    INDEPENDENCE_ARTIFACT_ID,
    TOLERANCE_ARTIFACT_ID,
)
from .software_verification import (
    CLI_PROBE_ARTIFACT_ID,
    IMPORT_PROBE_ARTIFACT_ID,
    JUNIT_ARTIFACT_ID,
    SOFTWARE_RUN_RECORD_ARTIFACT_ID,
)


def _passes(tolerance: Mapping[str, Any], absolute: float, relative: float | None) -> bool:
    if tolerance["type"] == "ABSOLUTE":
        return absolute <= tolerance["absolute"]
    if tolerance["type"] == "ABSOLUTE_AND_RELATIVE":
        return (
            absolute <= tolerance["absolute"]
            and relative is not None
            and relative <= tolerance["relative"]
        )
    raise ValueError(f"unsupported cross-validation tolerance {tolerance['type']!r}")


def _comparison(
    *,
    comparison_id: str,
    case: Mapping[str, Any],
    run: Mapping[str, Any],
    measurand: str,
    observed: float | None,
    reference: float | None,
    evidence_ids: list[str],
    error: str | None,
    note: str,
) -> dict[str, Any]:
    tolerance = next(
        item for item in case["tolerances"] if item["measurand_id"] == measurand
    )
    base: dict[str, Any] = {
        "comparison_id": comparison_id,
        "case_id": case["case_id"],
        "run_id": run["run_id"],
        "measurand_id": measurand,
        "reference": reference,
        "tolerance_used": tolerance["tolerance_id"],
        "evidence_ids": evidence_ids,
        "notes": [note],
    }
    if error is not None or observed is None or reference is None:
        base.update(
            {
                "observed": observed,
                "difference": None,
                "absolute_error": None,
                "relative_error": None,
                "normalized_error": None,
                "evaluation_status": "ERROR",
                "evaluation_error": error or "required result unavailable",
                "outcome": "ERROR",
            }
        )
        return base
    difference = observed - reference
    absolute = abs(difference)
    relative = None if reference == 0.0 else absolute / abs(reference)
    base.update(
        {
            "observed": observed,
            "difference": difference,
            "absolute_error": absolute,
            "relative_error": relative,
            "normalized_error": None,
            "evaluation_status": "EVALUATED",
            "outcome": "PASS" if _passes(tolerance, absolute, relative) else "FAIL",
        }
    )
    return base


def _run_error(run: Mapping[str, Any]) -> str | None:
    if run["execution_status"] == "COMPLETED":
        return None
    return "; ".join(item["message"] for item in run["errors"]) or "run unavailable"


def _software_supported(execution: GwyddionCrossValidationExecutionResult) -> bool:
    software = execution.software_test
    return (
        software.run["execution_status"] == "COMPLETED"
        and not software.run["errors"]
        and software.junit_summary is not None
        and software.junit_summary.successful
        and software.import_probe.get("status") == "PASS"
        and software.import_probe.get("resolved_inside_site_packages") is True
        and software.cli_probe.get("status") == "PASS"
        and any(item["artifact_id"] == JUNIT_ARTIFACT_ID for item in software.evidence)
    )


def _common_software_evidence(
    execution: GwyddionCrossValidationExecutionResult,
) -> set[str]:
    available = {item["artifact_id"] for item in execution.software_test.evidence}
    return {
        "artifact.software-test.suite-manifest",
        "artifact.execution.sut-wheel",
        IMPORT_PROBE_ARTIFACT_ID,
        CLI_PROBE_ARTIFACT_ID,
        SOFTWARE_RUN_RECORD_ARTIFACT_ID,
        *([JUNIT_ARTIFACT_ID] if JUNIT_ARTIFACT_ID in available else []),
    }


def _software_claim(
    execution: GwyddionCrossValidationExecutionResult,
) -> dict[str, Any]:
    supported = _software_supported(execution)
    return {
        "claim_id": "claim.software.roughness-wheel",
        "claim_text": (
            "The declared SPM-Kit wheel passes the exact frozen selected non-GUI "
            "roughness, export, NPZ and RunManifest software suite."
        ),
        "level": "LEVEL 1 — SOFTWARE_VERIFIED",
        "scope": {
            "description": "Installed-wheel selected software suite at the declared SUT commit.",
            "measurands": ["software_test_failures"],
            "dataset_roles": ["VERIFICATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [SOFTWARE_CASE_ID],
        "supported_comparison_ids": [],
        "supported_evidence_ids": sorted(_common_software_evidence(execution)),
        "limitations": [
            "Selected non-GUI suite only; unselected SPM-Kit features are outside scope.",
            "Software tests and SUT implementation share repository authorship.",
        ],
        "status": "SUPPORTED" if supported else "REJECTED",
    }


def _level2_claim(
    measurand: str,
    cases: list[Mapping[str, Any]],
    comparisons: list[Mapping[str, Any]],
    execution: GwyddionCrossValidationExecutionResult,
) -> dict[str, Any]:
    selected = [
        item
        for item in comparisons
        if item["measurand_id"] == measurand
        and item["comparison_id"].startswith("comparison.analytical.spmkit.")
    ]
    supported = (
        _software_supported(execution)
        and len(selected) == 6
        and all(item["outcome"] == "PASS" for item in selected)
    )
    evidence = {
        *_common_software_evidence(execution),
        "artifact.reference.ground-truth",
        TOLERANCE_ARTIFACT_ID,
        FORMAT_ARTIFACT_ID,
        *(evidence_id for item in selected for evidence_id in item["evidence_ids"]),
    }
    return {
        "claim_id": f"claim.synthetic.{measurand}",
        "claim_text": (
            f"SPM-Kit recovers {measurand} within frozen analytical-control bounds on "
            "the six declared synthetic GWY fields."
        ),
        "level": "LEVEL 2 — NUMERICALLY_VERIFIED",
        "scope": {
            "description": (
                f"{measurand}; synthetic GWY; full field; no preprocessing; flat, "
                "checkerboard and four-level at 16x16 and 32x32."
            ),
            "measurands": [measurand],
            "dataset_roles": ["CROSS_VALIDATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [SOFTWARE_CASE_ID, *[item["case_id"] for item in cases]],
        "supported_comparison_ids": [item["comparison_id"] for item in selected],
        "supported_evidence_ids": sorted(evidence),
        "limitations": [
            "Analytical control and protocol share authorship.",
            "Synthetic binary64 full-field scope only; no physical validation.",
        ],
        "status": "SUPPORTED" if supported else "REJECTED",
    }


def _level3_claim(
    measurand: str,
    cases: list[Mapping[str, Any]],
    comparisons: list[Mapping[str, Any]],
    execution: GwyddionCrossValidationExecutionResult,
) -> dict[str, Any]:
    selected = [
        item
        for item in comparisons
        if item["measurand_id"] == measurand
        and item["comparison_id"].startswith("comparison.cross.gwyddion.")
    ]
    supported = (
        _software_supported(execution)
        and len(selected) == 6
        and all(item["outcome"] == "PASS" for item in selected)
    )
    evidence = {
        *_common_software_evidence(execution),
        GWYDDION_IDENTITY_ARTIFACT_ID,
        INDEPENDENCE_ARTIFACT_ID,
        HELPER_SOURCE_ARTIFACT_ID,
        HELPER_BINARY_ARTIFACT_ID,
        HELPER_BUILD_ARTIFACT_ID,
        FORMAT_ARTIFACT_ID,
        TOLERANCE_ARTIFACT_ID,
        *(evidence_id for item in selected for evidence_id in item["evidence_ids"]),
    }
    limitations = [
        "Gwyddion-library reference with a frozen harness-authored execution wrapper.",
        "Sa wrapper accumulation is declared; Gwyddion supplies loading, units and data field.",
        "Synthetic binary64 full-field scope only; no physical or real-data validation.",
    ]
    if not supported:
        outcomes = Counter(item["outcome"] for item in selected)
        limitations.append(
            "External comparison outcomes: "
            + ", ".join(f"{name}={count}" for name, count in sorted(outcomes.items()))
        )
    return {
        "claim_id": f"claim.crossvalidated.gwyddion.{measurand}",
        "claim_text": (
            f"SPM-Kit {measurand} agrees within frozen bounds with the independent "
            "Gwyddion 2.71 library reference on all six declared synthetic GWY fields."
        ),
        "level": "LEVEL 3 — CROSS_VALIDATED",
        "scope": {
            "description": (
                f"{measurand}; SPM-Kit public CLI versus separate Gwyddion-library process; "
                "six synthetic GWY fields; no preprocessing."
            ),
            "measurands": [measurand],
            "dataset_roles": ["CROSS_VALIDATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [SOFTWARE_CASE_ID, *[item["case_id"] for item in cases]],
        "supported_comparison_ids": [item["comparison_id"] for item in selected],
        "supported_evidence_ids": sorted(evidence),
        "limitations": limitations,
        "status": "SUPPORTED" if supported else "REJECTED",
    }


def populate_gwyddion_cross_validation_result_bundle(
    frozen_protocol_bundle: Mapping[str, Any],
    execution: GwyddionCrossValidationExecutionResult,
    ground_truth_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive 18 cross and 36 analytical-control comparisons without manual outcomes."""

    bundle = copy.deepcopy(dict(frozen_protocol_bundle))
    bundle["runs"] = [copy.deepcopy(dict(item)) for item in execution.runs]
    bundle["evidence"] = sorted(
        [
            *bundle["evidence"],
            *(copy.deepcopy(dict(item)) for item in execution.software_test.evidence),
            *(copy.deepcopy(dict(item)) for item in execution.spmkit.evidence),
            *(copy.deepcopy(dict(item)) for item in execution.external_reference.evidence),
        ],
        key=lambda item: item["artifact_id"],
    )
    bundle["campaign"]["status"] = (
        "COMPLETED"
        if all(item["execution_status"] == "COMPLETED" for item in bundle["runs"])
        else "ABORTED"
    )
    if bundle["campaign"]["status"] == "ABORTED":
        bundle["campaign"]["limitations"].append(
            "One or more software, SPM-Kit or external-reference runs ended in ERROR."
        )
    truth = {
        item["case_id"]: item["analytical"] for item in ground_truth_document["cases"]
    }
    spmkit_runs = {item["case_ids"][0]: item for item in execution.spmkit.runs}
    external_runs = {
        item["case_ids"][0]: item for item in execution.external_reference.runs
    }
    cases = [item for item in bundle["cases"] if item["reference_id"] == EXTERNAL_REFERENCE_ID]
    comparisons: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["case_id"]
        spmkit_run = spmkit_runs[case_id]
        external_run = external_runs[case_id]
        spmkit_error = _run_error(spmkit_run)
        external_error = _run_error(external_run)
        for measurand in MEASURANDS:
            spmkit_value = execution.spmkit.observations.get(case_id, {}).get(measurand)
            external_value = execution.external_reference.observations.get(case_id, {}).get(
                measurand
            )
            analytical_value = float(truth[case_id][measurand])
            comparisons.extend(
                [
                    _comparison(
                        comparison_id=f"comparison.cross.gwyddion.{case_id}.{measurand}",
                        case=case,
                        run=spmkit_run,
                        measurand=measurand,
                        observed=spmkit_value,
                        reference=external_value,
                        evidence_ids=(
                            [
                                f"artifact.result-json.{case_id}",
                                f"artifact.gwyddion-output.{case_id}",
                                INDEPENDENCE_ARTIFACT_ID,
                            ]
                            if spmkit_error is None and external_error is None
                            else [
                                spmkit_run["run_manifest_artifact_id"],
                                external_run["run_manifest_artifact_id"],
                                INDEPENDENCE_ARTIFACT_ID,
                            ]
                        ),
                        error=spmkit_error or external_error,
                        note=(
                            "Observed is public SPM-Kit JSON; reference is strict structured "
                            "Gwyddion-library helper output from the identical frozen input."
                        ),
                    ),
                    _comparison(
                        comparison_id=(
                            f"comparison.analytical.spmkit.{case_id}.{measurand}"
                        ),
                        case=case,
                        run=spmkit_run,
                        measurand=measurand,
                        observed=spmkit_value,
                        reference=analytical_value,
                        evidence_ids=(
                            ["artifact.reference.ground-truth", f"artifact.result-json.{case_id}"]
                            if spmkit_error is None
                            else [
                                "artifact.reference.ground-truth",
                                spmkit_run["run_manifest_artifact_id"],
                            ]
                        ),
                        error=spmkit_error,
                        note=(
                            "Analytical control only; it does not replace external "
                            "cross-validation."
                        ),
                    ),
                    _comparison(
                        comparison_id=(
                            f"comparison.analytical.gwyddion.{case_id}.{measurand}"
                        ),
                        case=case,
                        run=external_run,
                        measurand=measurand,
                        observed=external_value,
                        reference=analytical_value,
                        evidence_ids=(
                            [
                                "artifact.reference.ground-truth",
                                f"artifact.gwyddion-output.{case_id}",
                            ]
                            if external_error is None
                            else [
                                "artifact.reference.ground-truth",
                                external_run["run_manifest_artifact_id"],
                            ]
                        ),
                        error=external_error,
                        note="Analytical control of the external reference; not the LEVEL 3 basis.",
                    ),
                ]
            )
    bundle["comparisons"] = comparisons
    bundle["claims"] = [
        _software_claim(execution),
        *[
            _level2_claim(measurand, cases, comparisons, execution)
            for measurand in MEASURANDS
        ],
        *[
            _level3_claim(measurand, cases, comparisons, execution)
            for measurand in MEASURANDS
        ],
    ]
    verify_protocol_continuity(frozen_protocol_bundle, bundle)
    assert_valid_bundle(bundle)
    return bundle


def normalized_gwyddion_cross_record(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize path/time variability while retaining both producers and input identity."""

    artifacts = {item["artifact_id"]: item for item in bundle["evidence"]}
    datasets = {item["dataset_id"]: item for item in bundle["datasets"]}
    cases = {
        item["case_id"]: item
        for item in bundle["cases"]
        if item["reference_id"] == EXTERNAL_REFERENCE_ID
    }
    cross = [
        item
        for item in bundle["comparisons"]
        if item["comparison_id"].startswith("comparison.cross.gwyddion.")
    ]
    output_ids = sorted(
        artifact_id
        for artifact_id in artifacts
        if artifact_id.startswith(("artifact.result-json.", "artifact.gwyddion-output."))
    )
    return {
        "campaign_id": bundle["campaign"]["campaign_id"],
        "determinism_category": "NUMERICALLY_REPEATABLE",
        "inputs": {
            case_id: {
                "sha256": datasets[case["dataset_id"]]["checksum"],
                "shape": datasets[case["dataset_id"]]["public_metadata"]["shape"],
                "unit": case["expected_units"],
            }
            for case_id, case in sorted(cases.items())
        },
        "runs": [
            {
                "run_id": item["run_id"],
                "exit_code": item["parameters"].get("exit_code"),
                "execution_status": item["execution_status"],
            }
            for item in bundle["runs"]
        ],
        "cross_comparisons": [
            {
                key: item[key]
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
            for item in cross
        ],
        "deterministic_output_hashes": {
            artifact_id: artifacts[artifact_id]["sha256"] for artifact_id in output_ids
        },
    }


def compare_gwyddion_cross_repetition(
    first_bundle: Mapping[str, Any], second_bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two complete local executions without elevating them to LEVEL 5."""

    first = normalized_gwyddion_cross_record(first_bundle)
    second = normalized_gwyddion_cross_record(second_bundle)
    equal = first == second
    return {
        "repeatability_version": "0.1.0",
        "status": "PASS" if equal else "FAIL",
        "determinism_category": "NUMERICALLY_REPEATABLE",
        "records_equal": equal,
        "spmkit_values_compared": 18,
        "gwyddion_values_compared": 18,
        "outcomes_compared": 18,
        "units_compared": 18,
        "input_hashes_compared": 6,
        "exit_codes_compared": 13,
        "level_5_claimed": False,
        "first": first,
        "second": second,
    }
