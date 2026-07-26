from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from spmkit_validation.execution import (
    CASE_SPECS,
    CampaignExecutionError,
    analytical_roughness,
    deterministic_npz_bytes,
    discrete_roughness,
    prepare_synthetic_roughness_campaign,
    surface_array,
)
from spmkit_validation.lifecycle import verify_artifacts
from spmkit_validation.schemas import assert_valid_bundle


@pytest.mark.parametrize("resolution", [16, 32])
@pytest.mark.parametrize(
    ("family", "expected"),
    [
        ("flat", {"Sa": 0.0, "Sq": 0.0, "Sz": 0.0}),
        ("checkerboard", {"Sa": 1e-9, "Sq": 1e-9, "Sz": 2e-9}),
        (
            "four-level",
            {"Sa": 2e-9, "Sq": math.sqrt(5.0) * 1e-9, "Sz": 6e-9},
        ),
    ],
)
def test_analytical_and_discrete_ground_truth(
    family: str, resolution: int, expected: dict[str, float]
) -> None:
    spec = next(
        item
        for item in CASE_SPECS
        if item["family"] == family and item["resolution"] == resolution
    )
    analytical = analytical_roughness(family, float(spec["amplitude"]))
    discrete = discrete_roughness(surface_array(spec))
    assert analytical == pytest.approx(expected, rel=1e-15, abs=1e-30)
    assert discrete == pytest.approx(expected, rel=1e-15, abs=1e-30)


def test_generator_is_byte_deterministic_and_parameter_sensitive() -> None:
    spec = copy.deepcopy(CASE_SPECS[2])
    array = surface_array(spec)
    first = deterministic_npz_bytes(spec, array)
    second = deterministic_npz_bytes(spec, surface_array(spec))
    assert first == second
    changed = copy.deepcopy(spec)
    changed["amplitude"] = 2e-9
    changed_bytes = deterministic_npz_bytes(changed, surface_array(changed))
    assert hashlib.sha256(first).digest() != hashlib.sha256(changed_bytes).digest()


def test_prepare_produces_valid_six_case_draft(tmp_path: Path) -> None:
    prepared = prepare_synthetic_roughness_campaign(tmp_path / "campaign")
    assert_valid_bundle(prepared.bundle)
    assert prepared.bundle["campaign"]["status"] == "DRAFT"
    assert len(prepared.bundle["cases"]) == 6
    assert prepared.bundle["runs"] == []
    assert prepared.bundle["comparisons"] == []
    assert prepared.bundle["claims"] == []
    assert {result.status for result in verify_artifacts(prepared.bundle, prepared.output_dir)} == {
        "PASS"
    }


def test_ground_truth_self_check_precedes_serialization(tmp_path: Path) -> None:
    prepared = prepare_synthetic_roughness_campaign(tmp_path / "campaign")
    document = json.loads(prepared.ground_truth_path.read_text(encoding="utf-8"))
    assert document["uses_sut_outputs"] is False
    assert document["derived_before_freeze"] is True
    assert document["status"] == "PASS"
    assert len(document["cases"]) == 6
    assert all(record["status"] == "PASS" for record in document["cases"])


def test_tolerances_are_predeclared_and_do_not_accept_observed(tmp_path: Path) -> None:
    prepared = prepare_synthetic_roughness_campaign(tmp_path / "campaign")
    document = json.loads(prepared.tolerance_budget_path.read_text(encoding="utf-8"))
    assert document["derived_without_sut_outputs"] is True
    assert len(document["records"]) == 18
    assert all("observed" not in record for record in document["records"])
    zero = [
        record
        for record in document["records"]
        if record["variables"]["reference_magnitude"] == 0
    ]
    nonzero = [record for record in document["records"] if record not in zero]
    assert zero and all(record["type"] == "ABSOLUTE" for record in zero)
    assert nonzero and all(record["type"] == "ABSOLUTE_AND_RELATIVE" for record in nonzero)
    assert all(record["predeclared_at"].endswith("Z") for record in document["records"])


def test_tolerance_artifact_is_hashed_from_real_bytes(tmp_path: Path) -> None:
    prepared = prepare_synthetic_roughness_campaign(tmp_path / "campaign")
    artifact = next(
        item
        for item in prepared.bundle["evidence"]
        if item["artifact_id"] == "artifact.protocol.tolerance-budget"
    )
    content = prepared.tolerance_budget_path.read_bytes()
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    assert artifact["size_bytes"] == len(content)


def test_preparation_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "campaign"
    prepare_synthetic_roughness_campaign(output)
    with pytest.raises(CampaignExecutionError):
        prepare_synthetic_roughness_campaign(output)


def test_discrete_reference_rejects_nonfinite_values() -> None:
    with pytest.raises(CampaignExecutionError):
        discrete_roughness(np.array([[math.nan]], dtype=np.float64))
