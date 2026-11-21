"""Pre-observation tolerance budget for deterministic float64 phantoms."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from .ground_truth import MEASURANDS


def derive_tolerance_budget(
    case_specs: tuple[Mapping[str, Any], ...],
    truth_records: tuple[Mapping[str, Any], ...],
    predeclared_at: str,
) -> dict[str, Any]:
    """Derive conservative numeric bounds without accepting observed values."""

    truth_by_case = {record["case_id"]: record for record in truth_records}
    epsilon = float(np.finfo(np.float64).eps)
    safety_factor = 16.0
    records: list[dict[str, Any]] = []
    for spec in case_specs:
        count = int(spec["resolution"]) ** 2
        truth = truth_by_case[spec["case_id"]]["analytical"]
        amplitude = abs(float(spec["amplitude"]))
        for measurand in MEASURANDS:
            reference = abs(float(truth[measurand]))
            scale = max(amplitude, reference, 1e-30)
            components = {
                "input_float64_rounding": epsilon * scale,
                "mean_and_centering": count * epsilon * scale,
                "absolute_or_squared_accumulation": 2.0 * count * epsilon * scale,
                "sqrt_rounding": epsilon * scale if measurand == "Sq" else 0.0,
                "unit_conversion": 0.0,
                "json_serialization_roundtrip": epsilon * scale,
                "json_parsing": epsilon * scale,
            }
            calculated_bound = sum(components.values())
            final_absolute = max(1e-21, safety_factor * calculated_bound)
            tolerance_type = "ABSOLUTE" if reference == 0.0 else "ABSOLUTE_AND_RELATIVE"
            final_relative = final_absolute / reference if reference else None
            records.append(
                {
                    "tolerance_id": f"tolerance.{spec['case_id']}.{measurand}",
                    "case_id": spec["case_id"],
                    "measurand_id": measurand,
                    "type": tolerance_type,
                    "unit": spec["unit"],
                    "formula": "max(1e-21, safety_factor * sum(component_bounds))",
                    "variables": {
                        "dtype": "float64",
                        "machine_epsilon": epsilon,
                        "amplitude": amplitude,
                        "pixel_count": count,
                        "reference_magnitude": reference,
                        "output_precision": "IEEE-754 repr round-trip JSON",
                        "unit_conversion_factor": 1.0,
                    },
                    "component_bounds": components,
                    "calculated_bound": calculated_bound,
                    "safety_factor": safety_factor,
                    "absolute": final_absolute,
                    "relative": final_relative,
                    "source": "Forward float64 error budget derived before SUT execution",
                    "predeclared_at": predeclared_at,
                    "derived_without_sut_outputs": True,
                }
            )
    return {
        "budget_version": "0.1.0",
        "predeclared_at": predeclared_at,
        "derived_without_sut_outputs": True,
        "records": records,
    }
