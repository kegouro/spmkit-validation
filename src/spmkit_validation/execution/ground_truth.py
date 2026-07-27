"""Analytical and discrete references for the synthetic roughness protocol."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)

MEASURANDS = ("Sa", "Sq", "Sz")


def analytical_roughness(family: str, amplitude: float) -> dict[str, float]:
    """Return closed-form Sa, Sq and Sz without consulting any SUT output."""

    if family == "flat":
        return {"Sa": 0.0, "Sq": 0.0, "Sz": 0.0}
    if family == "checkerboard":
        return {"Sa": amplitude, "Sq": amplitude, "Sz": 2.0 * amplitude}
    if family == "four-level":
        return {
            "Sa": 2.0 * amplitude,
            "Sq": math.sqrt(5.0) * amplitude,
            "Sz": 6.0 * amplitude,
        }
    raise CampaignExecutionError(
        [
            execution_issue(
                CampaignExecutionIssueCategory.INPUT,
                "GROUND_TRUTH.UNKNOWN_FAMILY",
                "/family",
                f"unsupported synthetic family {family!r}",
            )
        ]
    )


def discrete_roughness(z_data: np.ndarray) -> dict[str, float]:
    """Compute the three definitions directly, independently of SPM-Kit."""

    array = np.asarray(z_data)
    if array.ndim != 2 or not np.issubdtype(array.dtype, np.floating):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GROUND_TRUTH.INVALID_ARRAY",
                    "/z_data",
                    "ground-truth input must be a two-dimensional floating array",
                )
            ]
        )
    values = [float(value) for value in array.ravel(order="C")]
    if not values or not all(math.isfinite(value) for value in values):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GROUND_TRUTH.NONFINITE_ARRAY",
                    "/z_data",
                    "ground-truth input must contain finite values",
                )
            ]
        )
    count = len(values)
    mean = math.fsum(values) / count
    deviations = [value - mean for value in values]
    return {
        "Sa": math.fsum(abs(value) for value in deviations) / count,
        "Sq": math.sqrt(math.fsum(value * value for value in deviations) / count),
        "Sz": max(values) - min(values),
    }


def ground_truth_record(
    case_spec: Mapping[str, Any], z_data: np.ndarray
) -> dict[str, Any]:
    """Cross-check analytical and discrete values against a prior numeric bound."""

    analytical = analytical_roughness(case_spec["family"], float(case_spec["amplitude"]))
    discrete = discrete_roughness(z_data)
    count = int(z_data.size)
    scale = max(abs(float(case_spec["amplitude"])), 1e-30)
    bound = max(1e-30, 64.0 * count * float(np.finfo(np.float64).eps) * scale)
    differences = {
        measurand: discrete[measurand] - analytical[measurand]
        for measurand in MEASURANDS
    }
    status = (
        "PASS"
        if all(abs(differences[measurand]) <= bound for measurand in MEASURANDS)
        else "FAIL"
    )
    record = {
        "case_id": case_spec["case_id"],
        "family": case_spec["family"],
        "shape": list(z_data.shape),
        "unit": case_spec["unit"],
        "amplitude": float(case_spec["amplitude"]),
        "analytical": analytical,
        "discrete": discrete,
        "differences": differences,
        "predeclared_self_check_bound": bound,
        "status": status,
    }
    if status != "PASS":
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GROUND_TRUTH.SELF_CHECK_FAILED",
                    f"/cases/{case_spec['case_id']}",
                    "analytical and discrete references disagree before freeze",
                )
            ]
        )
    return record
