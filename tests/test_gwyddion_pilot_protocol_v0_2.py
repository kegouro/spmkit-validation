from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest
import yaml

from spmkit_validation.gwyddion_gsf import read_gsf, write_gsf


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "protocols" / "gwyddion_pilot_v0.2.yaml"
LOCK = ROOT / "locks" / "gwyddion_pilot_v0.2.json"
DOCUMENT = ROOT / "docs" / "pilots" / "gwyddion_pilot_v0.2.md"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def canonical_nm(values_m: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(values_m * 1.0e9, dtype="<f4")


def test_v0_2_contract_lock_and_sanitization() -> None:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert protocol["protocol_id"] == "gwyddion-pilot-v0.2"
    assert protocol["mode"] == "PILOT"
    assert protocol["evidence_target"] == "LEVEL 2 NUMERICALLY_VERIFIED"
    assert protocol["pass_fail_thresholds"] is None
    assert {key: protocol[key] for key in (
        "canonical_z_numeric_unit", "canonical_dtype", "canonical_byte_order",
        "canonical_memory_order", "gsf_z_unit", "gsf_payload_scaling",
        "spmkit_input_numeric_unit", "spmkit_output_unit", "gwyddion_output_normalized_unit",
    )} == {
        "canonical_z_numeric_unit": "nm", "canonical_dtype": "float32",
        "canonical_byte_order": "little", "canonical_memory_order": "C",
        "gsf_z_unit": "nm", "gsf_payload_scaling": "none",
        "spmkit_input_numeric_unit": "nm", "spmkit_output_unit": "nm",
        "gwyddion_output_normalized_unit": "nm",
    }
    assert [case["case_id"] for case in protocol["cases"]] == [
        "P01_PLANE_RAW", "P02_SINE_RAW", "P03_STEP_GAUSSIAN", "P04_SINE_LINE_OFFSETS",
    ]
    assert lock["state"] == "READY_TO_EXECUTE"
    semantics = lock["gwyddion"]["output_semantics"]
    assert semantics["classification"] == "GWY_NATIVE_NM"
    assert semantics["normalization_to_nm"] == "identity"
    assert semantics["observed_sz"] == 100.0
    text = PROTOCOL.read_text() + LOCK.read_text() + DOCUMENT.read_text()
    assert not PRIVATE.search(text)
    assert "LEVEL 3" not in text


def test_v0_2_nm_matrices_and_gsf_payload(tmp_path: Path) -> None:
    phantoms = pytest.importorskip("spmkit_phantoms")
    shape = (256, 256)
    x_size_m = y_size_m = 10e-6
    p02_source = phantoms.sinusoidal_surface(shape, x_size_m, y_size_m, 50e-9, 2.5e-6, 10e-6, axis="x").z_data
    p02 = canonical_nm(p02_source)
    assert p02.dtype == np.dtype("<f4") and p02.flags.c_contiguous
    assert np.all(p02 == p02[0])
    assert np.isclose(np.max(p02), 50.0, rtol=1e-6)
    assert np.isclose(np.ptp(p02), 100.0, rtol=1e-6)
    assert np.allclose(p02[0], np.roll(p02[0], 64), rtol=0.0, atol=1e-5)

    clean_step = phantoms.step_surface(shape, x_size_m, y_size_m, 100e-9, 0.5).z_data
    observed_step = phantoms.AdditiveGaussianNoise(5e-9).apply(
        phantoms.step_surface(shape, x_size_m, y_size_m, 100e-9, 0.5), np.random.default_rng(42)
    ).observed_z
    assert np.isclose(np.mean(canonical_nm(clean_step)[:, 128:]) - np.mean(canonical_nm(clean_step)[:, :128]), 100.0)
    assert np.array_equal(canonical_nm(observed_step), canonical_nm(phantoms.AdditiveGaussianNoise(5e-9).apply(
        phantoms.step_surface(shape, x_size_m, y_size_m, 100e-9, 0.5), np.random.default_rng(42)
    ).observed_z))

    observed_p04 = phantoms.LineOffsets(5e-9).apply(
        phantoms.sinusoidal_surface(shape, x_size_m, y_size_m, 50e-9, 2.5e-6, 10e-6, axis="x"), np.random.default_rng(42)
    ).observed_z
    offsets = observed_p04 - p02_source
    assert np.allclose(offsets, offsets[:, :1])
    assert np.std(offsets[:, 0]) > 0.0

    output = tmp_path / "pilot-v0-2.gsf"
    write_gsf(output, p02, x_size_m, y_size_m, "nm", "P02_SINE_RAW")
    recovered, metadata = read_gsf(output)
    assert np.array_equal(recovered, p02)
    assert hashlib.sha256(recovered.tobytes(order="C")).hexdigest() == hashlib.sha256(p02.tobytes(order="C")).hexdigest()
    assert metadata["ZUnits"] == "nm"
