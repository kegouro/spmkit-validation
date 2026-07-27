from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from gwyfile import load

from spmkit_validation.adapters.gwyddion.format import (
    PREPROCESSING_CONTRACT,
    GwyddionReferenceOutputError,
    deterministic_gwy_bytes,
    strict_json_object,
    validate_reference_output,
)


def _valid_output(content: bytes) -> dict[str, object]:
    return {
        "schema": "spmkit-gwyddion-reference-output/0.1.0",
        "status": "COMPLETED",
        "producer": "Gwyddion libraries",
        "gwyddion_version": "2.71",
        "helper_version": "0.1.0",
        "input_sha256": hashlib.sha256(content).hexdigest(),
        "channel": 0,
        "shape": [2, 2],
        "axis_order": "ROW_Y_COLUMN_X",
        "unit_z": "m",
        "unit_source": "GWYDDION_DATA_FIELD",
        "preprocessing": PREPROCESSING_CONTRACT,
        "mean": 0.0,
        "Sa": 1.0,
        "Sq": 1.0,
        "min": -1.0,
        "max": 1.0,
        "Sz": 2.0,
    }


def test_gwy_writer_is_deterministic_and_preserves_orientation_and_units() -> None:
    array = np.arange(15, dtype=np.float64).reshape(3, 5) * 1e-9
    first = deterministic_gwy_bytes(array, x_size_m=5e-6, y_size_m=3e-6)
    second = deterministic_gwy_bytes(array, x_size_m=5e-6, y_size_m=3e-6)

    assert first == second
    container = load(__import__("io").BytesIO(first))
    field = container["/0/data"]
    assert np.array_equal(field.data, array)
    assert field.data.shape == (3, 5)
    assert field.si_unit_xy.unitstr == "m"
    assert field.si_unit_z.unitstr == "m"
    assert field.xreal == 5e-6
    assert field.yreal == 3e-6


@pytest.mark.parametrize(
    "array",
    [np.array([1.0]), np.array([[np.nan]]), np.array([[np.inf]])],
)
def test_gwy_writer_rejects_invalid_arrays(array: np.ndarray) -> None:
    with pytest.raises(ValueError):
        deterministic_gwy_bytes(array, x_size_m=1.0, y_size_m=1.0)


def test_strict_json_rejects_duplicate_and_nonfinite_values() -> None:
    with pytest.raises(GwyddionReferenceOutputError, match="duplicate"):
        strict_json_object(b'{"Sa":1,"Sa":2}\n')
    with pytest.raises(GwyddionReferenceOutputError, match="non-finite"):
        strict_json_object(b'{"Sa":NaN}\n')


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unit_z", "nm"),
        ("input_sha256", "0" * 64),
        ("shape", [5, 3]),
        ("axis_order", "COLUMN_X_ROW_Y"),
        ("preprocessing", {**PREPROCESSING_CONTRACT, "leveling": "PLANE"}),
        ("gwyddion_version", "2.70"),
    ],
)
def test_reference_contract_rejects_identity_and_scientific_mismatch(
    field: str, value: object
) -> None:
    content = b"input"
    document = _valid_output(content)
    document[field] = value

    with pytest.raises(GwyddionReferenceOutputError):
        validate_reference_output(
            document,
            input_sha256=hashlib.sha256(content).hexdigest(),
            shape=(2, 2),
            unit_z="m",
            expected_gwyddion_version="2.71",
        )


def test_reference_contract_accepts_strict_machine_output() -> None:
    content = b"input"
    raw = json.dumps(_valid_output(content), allow_nan=False).encode()
    parsed = strict_json_object(raw)

    validated = validate_reference_output(
        parsed,
        input_sha256=hashlib.sha256(content).hexdigest(),
        shape=(2, 2),
        unit_z="m",
        expected_gwyddion_version="2.71",
    )

    assert validated["status"] == "COMPLETED"
