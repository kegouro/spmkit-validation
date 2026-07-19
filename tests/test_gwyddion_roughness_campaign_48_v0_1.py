from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
PROTOCOL = ROOT / "protocols" / "gwyddion_roughness_campaign_48_v0.1.yaml"
LOCK = ROOT / "locks" / "gwyddion_roughness_campaign_48_v0.1.json"
DESIGN = ROOT / "campaigns" / "design" / "gwyddion_roughness_48_v0.1.jsonl"
DOCUMENT = ROOT / "docs" / "campaigns" / "gwyddion_roughness_48_v0.1.md"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)
RECORD_KEYS = (
    "schema_version", "campaign_id", "case_index", "case_id", "surface_id",
    "surface_parameters", "corruption_id", "corruption_parameters", "seed",
    "rng_engine", "rng_semantics", "sampling_convention", "array_axis_0",
    "array_axis_1", "shape", "x_real_um", "y_real_um", "z_numeric_unit",
    "dtype", "byte_order", "memory_order", "canonical_matrix_sha256",
    "gsf_sha256", "expected_execution_status",
)


def test_frozen_design_contract_and_privacy() -> None:
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in DESIGN.read_text(encoding="utf-8").splitlines()]

    assert protocol["protocol_id"] == "gwyddion-roughness-campaign-48-v0.1"
    assert protocol["execution_state"] == "READY_TO_EXECUTE"
    assert protocol["metrics_future"] == ["Sa", "Sq", "Sz"]
    assert protocol["thresholds"]["absolute_tolerance_nm"] == 1e-6
    assert protocol["thresholds"]["relative_tolerance"] == 1e-6
    assert lock["state"] == "READY_TO_EXECUTE"
    assert lock["design"]["records"] == 48
    assert lock["design"]["future_comparisons"] == 144
    assert lock["design"]["jsonl_sha256"] == hashlib.sha256(DESIGN.read_bytes()).hexdigest()
    assert len(records) == 48
    assert [record["case_index"] for record in records] == list(range(1, 49))
    assert all(tuple(record) == RECORD_KEYS for record in records)
    assert {record["case_id"] for record in records}.__len__() == 48
    assert {record["canonical_matrix_sha256"] for record in records}.__len__() == 48
    assert {record["gsf_sha256"] for record in records}.__len__() == 48
    assert all(record["expected_execution_status"] == "READY_TO_EXECUTE" for record in records)
    assert all(record["shape"] == [256, 256] for record in records)
    assert all(record["dtype"] == "float32" for record in records)
    assert all(record["byte_order"] == "little" for record in records)
    assert all(record["memory_order"] == "C" for record in records)
    step = next(record for record in records if record["surface_id"] == "S03")
    assert step["surface_parameters"] == {
        "requested_position_um": 3.7,
        "low_height_nm": 0.0,
        "high_height_nm": 83.0,
        "sampling_rule": "low_if_x_lt_requested_high_if_x_gte_requested",
        "first_high_column_index": 95,
        "first_high_sample_x_um": 3.7109375,
    }
    text = "".join(path.read_text(encoding="utf-8") for path in (PROTOCOL, LOCK, DESIGN, DOCUMENT))
    assert not PRIVATE.search(text)
    assert "LEVEL 3" not in text
