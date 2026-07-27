from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.execution import (
    CampaignExecutionError,
    execute_frozen_campaign,
    populate_result_bundle,
    verify_protocol_continuity,
)
from spmkit_validation.schemas import ValidationBundleError, assert_valid_bundle

from .conftest import write_fake_spmkit


def _execution(frozen_protocol: Any, tmp_path: Path, mode: str = "success"):
    prepared, frozen = frozen_protocol
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel fixture")
    executable = write_fake_spmkit(tmp_path / f"spmkit-{mode}", mode=mode)
    execution = execute_frozen_campaign(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        output_dir=prepared.output_dir / "execution",
        sut_executable=executable,
        timeout_seconds=5,
    )
    frozen_bundle = json.loads(frozen.snapshot_path.read_text(encoding="utf-8"))
    truth = json.loads(prepared.ground_truth_path.read_text(encoding="utf-8"))
    return prepared, frozen, frozen_bundle, truth, execution


def test_population_has_six_runs_and_eighteen_derived_passes(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    assert_valid_bundle(result)
    assert result["campaign"]["status"] == "COMPLETED"
    assert len(result["runs"]) == 6
    assert len(result["comparisons"]) == 18
    assert {item["outcome"] for item in result["comparisons"]} == {"PASS"}
    assert {claim["level"] for claim in result["claims"]} == {"LEVEL 0 — CLAIMED"}
    assert {claim["status"] for claim in result["claims"]} == {"PROPOSED"}


def test_observed_values_come_from_machine_json(frozen_protocol: Any, tmp_path: Path) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    for comparison in result["comparisons"]:
        assert comparison["observed"] == execution.observations[comparison["case_id"]][
            comparison["measurand_id"]
        ]


def test_declared_outcome_contradiction_remains_invalid(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    result["comparisons"][0]["outcome"] = "FAIL"
    with pytest.raises(ValidationBundleError, match="OUTCOME.DECLARED_MISMATCH"):
        assert_valid_bundle(result)


def test_fail_is_preserved_and_claim_not_elevated(frozen_protocol: Any, tmp_path: Path) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    observations = {case_id: dict(values) for case_id, values in execution.observations.items()}
    observations["case.synthetic.checkerboard.16x16"]["Sa"] = 2.0
    changed = replace(execution, observations=observations)
    result = populate_result_bundle(frozen, changed, truth)
    assert any(item["outcome"] == "FAIL" for item in result["comparisons"])
    assert all(claim["status"] != "SUPPORTED" for claim in result["claims"])
    assert_valid_bundle(result)


def test_error_is_preserved_as_eighteen_error_comparisons(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path, mode="failure")
    result = populate_result_bundle(frozen, execution, truth)
    assert result["campaign"]["status"] == "ABORTED"
    assert len(result["comparisons"]) == 18
    assert {item["outcome"] for item in result["comparisons"]} == {"ERROR"}
    assert all(claim["status"] != "SUPPORTED" for claim in result["claims"])
    assert_valid_bundle(result)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda bundle: bundle["cases"][0]["tolerances"][0].update(absolute=9.0),
            "CASES_CONTENT_DRIFT",
        ),
        (
            lambda bundle: bundle["references"][0].update(version="changed"),
            "REFERENCES_CONTENT_DRIFT",
        ),
        (lambda bundle: bundle["datasets"][0].update(checksum="0" * 64), "DATASETS_CONTENT_DRIFT"),
        (lambda bundle: bundle["cases"][0].update(case_status="RETIRED"), "CASES_CONTENT_DRIFT"),
        (
            lambda bundle: bundle["campaign"]["system_under_test"].update(
                git_commit="0" * 40
            ),
            "SYSTEM_UNDER_TEST_DRIFT",
        ),
        (
            lambda bundle: bundle["datasets"][0].update(locator="inputs/substitute.npz"),
            "DATASETS_CONTENT_DRIFT",
        ),
        (lambda bundle: bundle["cases"].pop(), "CASES_SET_DRIFT"),
    ],
)
def test_protocol_drift_is_rejected(
    frozen_protocol: Any,
    tmp_path: Path,
    mutation: Any,
    code: str,
) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    mutation(result)
    with pytest.raises(CampaignExecutionError, match=code):
        verify_protocol_continuity(frozen, result)


def test_population_additions_and_status_transition_are_allowed(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    verify_protocol_continuity(frozen, result)
    assert result["runs"] and result["comparisons"]
    assert result["campaign"]["frozen_at"] == frozen["campaign"]["frozen_at"]


def test_frozen_artifact_deletion_is_rejected(frozen_protocol: Any, tmp_path: Path) -> None:
    _, _, frozen, truth, execution = _execution(frozen_protocol, tmp_path)
    result = populate_result_bundle(frozen, execution, truth)
    frozen_id = frozen["evidence"][0]["artifact_id"]
    result["evidence"] = [
        item for item in result["evidence"] if item["artifact_id"] != frozen_id
    ]
    with pytest.raises(CampaignExecutionError, match="ARTIFACT_REMOVED"):
        verify_protocol_continuity(frozen, result)
