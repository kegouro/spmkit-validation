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
PROTOCOL = ROOT / "protocols" / "gwyddion_pilot_v0.1.yaml"
LOCK = ROOT / "locks" / "gwyddion_pilot_v0.1.json"
DOCUMENT = ROOT / "docs" / "pilots" / "gwyddion_pilot_v0.1.md"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def test_protocol_and_lock_are_frozen_and_sanitized() -> None:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in protocol["cases"]}

    assert protocol["protocol_id"] == "gwyddion-pilot-v0.1"
    assert protocol["matrix_shape"] == [256, 256]
    assert protocol["z_unit"] == "nm"
    assert protocol["metrics_primary"] == ["Sa", "Sq", "Sz"]
    assert protocol["pass_fail_thresholds"] is None
    assert set(cases) == {"P01_PLANE_RAW", "P02_SINE_RAW", "P03_STEP_GAUSSIAN", "P04_SINE_LINE_OFFSETS"}
    assert cases["P02_SINE_RAW"]["parameters"]["axis"] == "x"
    assert cases["P02_SINE_RAW"]["parameters"]["period_x_m"] == 2.5e-6
    assert cases["P03_STEP_GAUSSIAN"]["corruptions"][0]["seed"] == 42
    assert cases["P04_SINE_LINE_OFFSETS"]["corruptions"][0]["type"] == "LineOffsets"
    assert lock["state"] == "READY_TO_EXECUTE"
    assert lock["gwyddion"]["batch_capability"] == "BATCH_CONFIRMED"
    assert lock["repositories"]["spmkit"]["commit"] == "5a704d61145cc502a8e5bc855bf300836fc3832e"
    assert lock["repositories"]["spmkit_phantoms"]["commit"] == "16fffcebc931765fdd193cf531b07db576689523"
    assert set(item["path"] for item in lock["repositories"].values()) == {"<spmkit>", "<validation>", "<phantoms>"}
    text = PROTOCOL.read_text() + LOCK.read_text() + DOCUMENT.read_text()
    assert not PRIVATE.search(text)
    assert "LEVEL 3" not in text


def test_axis_aligned_phantom_and_gsf_round_trip(tmp_path: Path) -> None:
    phantoms = pytest.importorskip("spmkit_phantoms")
    matrix = phantoms.sinusoidal_surface(
        (256, 256), 10e-6, 10e-6, 50e-9, 2.5e-6, 10e-6, axis="x"
    ).z_data.astype("<f4")
    duplicate = phantoms.sinusoidal_surface(
        (256, 256), 10e-6, 10e-6, 50e-9, 2.5e-6, 10e-6, axis="x"
    ).z_data.astype("<f4")
    output = tmp_path / "pilot.gsf"

    write_gsf(output, matrix, 10e-6, 10e-6, "nm", "P02_SINE_RAW")
    recovered, metadata = read_gsf(output)

    assert matrix.shape == (256, 256)
    assert np.array_equal(matrix, duplicate)
    assert np.array_equal(matrix, recovered)
    assert np.all(matrix == matrix[0])
    assert np.isclose(np.max(matrix), 50e-9)
    assert np.isclose(np.min(matrix), -50e-9)
    assert float(metadata["XReal"]) == 10e-6
    assert float(metadata["YReal"]) == 10e-6
    assert metadata["ZUnits"] == "nm"
    assert hashlib.sha256(matrix.tobytes()).hexdigest()
