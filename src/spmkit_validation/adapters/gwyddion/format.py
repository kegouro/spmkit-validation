"""Deterministic GWY interchange and strict external-reference output parsing."""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from gwyfile.objects import GwyContainer, GwyDataField

REFERENCE_OUTPUT_SCHEMA = "spmkit-gwyddion-reference-output/0.1.0"
GWYFILE_VERSION = "0.3.0"
PREPROCESSING_CONTRACT = {
    "leveling": "NONE",
    "filtering": "NONE",
    "masking": "NONE",
    "roi": "FULL_FIELD",
}


class GwyddionReferenceOutputError(ValueError):
    """Raised when helper stdout is not the frozen structured contract."""


def deterministic_gwy_bytes(
    z_data: np.ndarray,
    *,
    x_size_m: float,
    y_size_m: float,
    title: str = "Z-Axis",
) -> bytes:
    """Serialize one binary64 channel with explicit metre units and stable ordering."""

    array = np.asarray(z_data, dtype="<f8", order="C")
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError("GWY input must be a finite two-dimensional binary64 array")
    if not x_size_m > 0.0 or not y_size_m > 0.0:
        raise ValueError("GWY lateral dimensions must be positive")
    container = GwyContainer()
    container["/0/data"] = GwyDataField(
        array,
        xreal=float(x_size_m),
        yreal=float(y_size_m),
        si_unit_xy="m",
        si_unit_z="m",
    )
    container["/0/data/title"] = title
    output = io.BytesIO()
    container.tofile(output)
    return output.getvalue()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def strict_json_object(content: bytes) -> dict[str, Any]:
    """Decode one strict JSON object, rejecting duplicate keys and non-finite values."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            content,
            parse_constant=reject_constant,
            object_pairs_hook=unique_pairs,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise GwyddionReferenceOutputError(str(exc)) from exc
    if not isinstance(value, dict):
        raise GwyddionReferenceOutputError("reference output must be a JSON object")
    return value


def validate_reference_output(
    document: Mapping[str, Any],
    *,
    input_sha256: str,
    shape: tuple[int, int],
    unit_z: str,
    channel: int = 0,
    expected_gwyddion_version: str | None = None,
    expected_helper_version: str = "0.1.0",
) -> dict[str, Any]:
    """Validate identity, preprocessing, orientation, units and finite statistics."""

    exact = {
        "schema": REFERENCE_OUTPUT_SCHEMA,
        "status": "COMPLETED",
        "producer": "Gwyddion libraries",
        "helper_version": expected_helper_version,
        "input_sha256": input_sha256,
        "channel": channel,
        "shape": list(shape),
        "axis_order": "ROW_Y_COLUMN_X",
        "unit_z": unit_z,
        "unit_source": "GWYDDION_DATA_FIELD",
        "preprocessing": PREPROCESSING_CONTRACT,
    }
    for key, expected in exact.items():
        if document.get(key) != expected:
            raise GwyddionReferenceOutputError(
                f"{key} mismatch: expected {expected!r}, got {document.get(key)!r}"
            )
    version = document.get("gwyddion_version")
    if not isinstance(version, str) or not version:
        raise GwyddionReferenceOutputError("gwyddion_version must be non-empty")
    if expected_gwyddion_version is not None and version != expected_gwyddion_version:
        raise GwyddionReferenceOutputError(
            "gwyddion_version differs from the frozen reference identity"
        )
    for name in ("mean", "Sa", "Sq", "min", "max", "Sz"):
        value = document.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise GwyddionReferenceOutputError(f"{name} must be numeric")
        if not math.isfinite(float(value)):
            raise GwyddionReferenceOutputError(f"{name} must be finite")
    if float(document["Sa"]) < 0.0 or float(document["Sq"]) < 0.0:
        raise GwyddionReferenceOutputError("Sa and Sq cannot be negative")
    if float(document["Sz"]) != float(document["max"]) - float(document["min"]):
        raise GwyddionReferenceOutputError("Sz must equal max minus min")
    return dict(document)
