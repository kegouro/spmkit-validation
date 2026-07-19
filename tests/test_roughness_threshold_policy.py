from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "protocols" / "roughness_threshold_calibration_v0.1.yaml"
LOCK = ROOT / "locks" / "roughness_threshold_calibration_v0.1.json"
DOCUMENT = ROOT / "docs" / "validation" / "roughness_threshold_policy_v0.1.md"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def test_candidate_policy_is_frozen_and_independent() -> None:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    policy = protocol["candidate_policy"]
    cases = protocol["corpus"]["cases"]
    assert protocol["state"] == "CANDIDATE_FROZEN"
    assert protocol["evidence_target"] == "LEVEL 2 NUMERICALLY_VERIFIED"
    assert policy["absolute_tolerance_nm"] == 1.0e-6
    assert policy["relative_tolerance"] == 1.0e-6
    assert policy["criterion"] == "abs(a-b) <= absolute_tolerance_nm + relative_tolerance * max(abs(a), abs(b))"
    assert policy["metrics"] == ["Sa", "Sq", "Sz"]
    assert protocol["matrix_contract"] == {
        "shape": [256, 256],
        "numeric_unit": "nm",
        "dtype": "float32",
        "byte_order": "little",
        "memory_order": "C",
        "gsf_z_unit": "nm",
        "gsf_payload_scaling": "none",
        "shared_matrix_bytes": "required",
    }
    assert len(cases) == 20
    assert len({case["case_id"] for case in cases}) == 20
    assert protocol["corpus"]["independent_of_pilot_p01_p04"] is True
    assert protocol["corpus"]["excluded_from_future_48_exact_cases"] is True
    assert lock["candidate_policy"]["state"] == "CANDIDATE_FROZEN"
    assert lock["gwyddion"]["normalization_to_nm"] == "identity"
    text = PROTOCOL.read_text() + LOCK.read_text() + DOCUMENT.read_text()
    assert not PRIVATE.search(text)
    assert "LEVEL 3" not in text
