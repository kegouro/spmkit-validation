"""Population and validator-governed claims for cumulative verification."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from spmkit_validation.schemas import assert_valid_bundle

from .cumulative import CumulativeExecutionResult
from .cumulative_protocol import SOFTWARE_CASE_ID
from .ground_truth import MEASURANDS
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .population import populate_result_bundle
from .software_verification import (
    CLI_PROBE_ARTIFACT_ID,
    IMPORT_PROBE_ARTIFACT_ID,
    JUNIT_ARTIFACT_ID,
    SOFTWARE_RUN_RECORD_ARTIFACT_ID,
)


def _software_supported(execution: CumulativeExecutionResult) -> bool:
    software = execution.software_test
    return (
        software.run["run_type"] == "SOFTWARE_TEST"
        and software.run["execution_status"] == "COMPLETED"
        and not software.run["errors"]
        and software.junit_summary is not None
        and software.junit_summary.successful
        and software.import_probe.get("status") == "PASS"
        and software.import_probe.get("resolved_inside_site_packages") is True
        and software.cli_probe.get("status") == "PASS"
        and any(
            artifact["artifact_id"] == JUNIT_ARTIFACT_ID
            and artifact["scientific_role"] == "SOFTWARE_TEST_RESULT"
            and artifact["artifact_id"] in software.run["output_artifact_ids"]
            for artifact in software.evidence
        )
    )


def _software_evidence_ids(execution: CumulativeExecutionResult) -> set[str]:
    return {item["artifact_id"] for item in execution.software_test.evidence}


def _software_claim(
    software_supported: bool,
    available_evidence_ids: set[str],
) -> dict[str, Any]:
    return {
        "claim_id": "claim.software.roughness-wheel",
        "claim_text": (
            "The declared SPM-Kit wheel passes the exact selected non-GUI roughness, "
            "export, NPZ, RunManifest and clean-error software suite."
        ),
        "level": "LEVEL 1 — SOFTWARE_VERIFIED",
        "scope": {
            "description": (
                "Installed wheel import, public CLI availability, synthetic roughness unit "
                "tests, JSON/CSV export, NPZ loading, RunManifest construction and invalid "
                "input handling at the declared SUT commit."
            ),
            "measurands": ["software_test_failures"],
            "dataset_roles": ["VERIFICATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [SOFTWARE_CASE_ID],
        "supported_comparison_ids": [],
        "supported_evidence_ids": sorted(
            {
                "artifact.software-test.suite-manifest",
                "artifact.execution.sut-wheel",
                IMPORT_PROBE_ARTIFACT_ID,
                CLI_PROBE_ARTIFACT_ID,
                SOFTWARE_RUN_RECORD_ARTIFACT_ID,
                *(
                    [JUNIT_ARTIFACT_ID]
                    if JUNIT_ARTIFACT_ID in available_evidence_ids
                    else []
                ),
            }
        ),
        "limitations": [
            "Selected non-GUI suite only; no claim is made for unselected SPM-Kit features.",
            "Software tests and implementation share repository authorship.",
        ],
        "status": "SUPPORTED" if software_supported else "REJECTED",
    }


def _numeric_claim(
    measurand: str,
    numeric_cases: list[Mapping[str, Any]],
    comparisons: list[Mapping[str, Any]],
    software_supported: bool,
    available_evidence_ids: set[str],
) -> dict[str, Any]:
    selected = [item for item in comparisons if item["measurand_id"] == measurand]
    comparisons_pass = bool(selected) and all(item["outcome"] == "PASS" for item in selected)
    supported = software_supported and comparisons_pass
    limitations = [
        (
            "Scope is six synthetic NPZ phantoms, no leveling or preprocessing, "
            "resolutions 16x16 and 32x32."
        ),
        "Analytical reference and protocol share authorship; no third-party independence.",
        "No physical, manufacturer, cross-validation or real-data evidence is included.",
    ]
    if not software_supported:
        limitations.append("Cumulative LEVEL 1 software evidence did not pass.")
    if not comparisons_pass:
        outcomes = sorted({item["outcome"] for item in selected})
        limitations.append("Applicable numerical outcomes: " + ", ".join(outcomes) + ".")
    result_evidence = sorted(
        {
            evidence_id
            for comparison in selected
            for evidence_id in comparison["evidence_ids"]
        }
    )
    return {
        "claim_id": f"claim.synthetic.{measurand}",
        "claim_text": (
            f"SPM-Kit recovers {measurand} within the frozen analytical tolerances on "
            "the declared six synthetic phantoms after cumulative software verification."
        ),
        "level": "LEVEL 2 — NUMERICALLY_VERIFIED",
        "scope": {
            "description": (
                f"{measurand}; synthetic NPZ; no preprocessing; flat, checkerboard and "
                "four-level families at 16x16 and 32x32; declared SUT wheel."
            ),
            "measurands": [measurand],
            "dataset_roles": ["VERIFICATION"],
            "reproducibility_dimensions": [],
        },
        "supported_case_ids": [SOFTWARE_CASE_ID, *[case["case_id"] for case in numeric_cases]],
        "supported_comparison_ids": [item["comparison_id"] for item in selected],
        "supported_evidence_ids": sorted(
            {
                "artifact.software-test.suite-manifest",
                "artifact.execution.sut-wheel",
                "artifact.reference.ground-truth",
                "artifact.protocol.tolerance-budget",
                IMPORT_PROBE_ARTIFACT_ID,
                CLI_PROBE_ARTIFACT_ID,
                SOFTWARE_RUN_RECORD_ARTIFACT_ID,
                *(
                    [JUNIT_ARTIFACT_ID]
                    if JUNIT_ARTIFACT_ID in available_evidence_ids
                    else []
                ),
                *result_evidence,
            }
        ),
        "limitations": limitations,
        "status": "SUPPORTED" if supported else "REJECTED",
    }


def populate_cumulative_result_bundle(
    frozen_protocol_bundle: Mapping[str, Any],
    execution_result: CumulativeExecutionResult,
    ground_truth_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Populate seven runs and derive claims; the existing validator is authoritative."""

    if execution_result.software_test.wheel_sha256 != execution_result.scientific.wheel_sha256:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "CUMULATIVE.WHEEL_IDENTITY_DIVERGED",
                    "/runs",
                    "software and scientific records do not share one wheel hash",
                )
            ]
        )

    scientific = populate_result_bundle(
        frozen_protocol_bundle,
        execution_result.scientific,
        ground_truth_document,
    )
    bundle = copy.deepcopy(scientific)
    bundle["runs"] = [
        copy.deepcopy(dict(execution_result.software_test.run)),
        *(copy.deepcopy(dict(run)) for run in execution_result.scientific.runs),
    ]
    bundle["evidence"] = sorted(
        [
            *scientific["evidence"],
            *(
                copy.deepcopy(dict(artifact))
                for artifact in execution_result.software_test.evidence
            ),
        ],
        key=lambda item: item["artifact_id"],
    )
    all_completed = all(run["execution_status"] == "COMPLETED" for run in bundle["runs"])
    bundle["campaign"]["status"] = "COMPLETED" if all_completed else "ABORTED"
    if not all_completed:
        bundle["campaign"]["limitations"].append(
            "One or more cumulative software or numerical runs ended in ERROR."
        )
    numeric_case_ids = {record["case_id"] for record in ground_truth_document["cases"]}
    numeric_cases = [
        case for case in bundle["cases"] if case["case_id"] in numeric_case_ids
    ]
    software_supported = _software_supported(execution_result)
    available_evidence_ids = _software_evidence_ids(execution_result)
    bundle["claims"] = [
        _software_claim(software_supported, available_evidence_ids),
        *[
            _numeric_claim(
                measurand,
                numeric_cases,
                bundle["comparisons"],
                software_supported,
                available_evidence_ids,
            )
            for measurand in MEASURANDS
        ],
    ]
    assert_valid_bundle(bundle)
    return bundle
