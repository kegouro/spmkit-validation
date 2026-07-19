from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
DESIGN = ROOT / "campaigns/design/real_data_roughness_pilot_v0.1.jsonl"
LOCK = ROOT / "locks/real_data_roughness_pilot_v0.1.json"
PROTOCOL = ROOT / "protocols/real_data_roughness_pilot_v0.1.yaml"
COVERAGE = ROOT / "docs/validation/SPMKIT_VALIDATION_COVERAGE_v0.1.md"
KEYS = ("schema_version", "campaign_id", "case_index", "case_id", "source_id", "source_title", "source_doi", "source_url", "license", "attribution", "file_sha256", "file_format", "file_size_bytes", "channel_name", "channel_index", "data_status", "selection_class", "spmkit_parser", "gwyddion_importer", "declared_xy_unit", "declared_z_unit", "expected_shape", "parser_thresholds", "metric_threshold_policy", "expected_execution_status", "limitations")
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def test_frozen_real_data_pilot_contract() -> None:
    records = [json.loads(line) for line in DESIGN.read_text().splitlines()]
    lock = json.loads(LOCK.read_text())
    protocol = yaml.safe_load(PROTOCOL.read_text())
    assert len(records) == 12
    assert all(tuple(record) == KEYS for record in records)
    assert [record["case_index"] for record in records] == list(range(1, 13))
    assert Counter(record["source_id"] for record in records) == {"ce-6ntsk": 4, "16287446": 4, "17970187": 4}
    assert len({record["file_sha256"] for record in records}) == 12
    assert all(record["file_format"] == "GWY" for record in records)
    assert all(record["selection_class"] == "ELIGIBLE_NATIVE_DUAL_PARSE" for record in records)
    assert all(record["parser_thresholds"] is None for record in records)
    assert all(record["metric_threshold_policy"] == {"atol_nm": 1e-6, "rtol": 1e-6} for record in records)
    assert all(record["expected_execution_status"] == "PENDING" for record in records)
    assert all(re.fullmatch(r"[0-9a-f]{64}", record["file_sha256"]) for record in records)
    assert lock["state"] == "READY_TO_EXECUTE"
    assert lock["design"]["jsonl_sha256"] == hashlib.sha256(DESIGN.read_bytes()).hexdigest()
    assert lock["algorithm_threshold"] == {"atol_nm": 1e-6, "rtol": 1e-6, "future_comparisons": 36}
    assert lock["parser_thresholds"] is None
    assert set(lock["gwyddion_helpers"]) == {"stats", "extract"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", helper["binary_sha256"]) for helper in lock["gwyddion_helpers"].values())
    assert protocol["tracks"]["parser_fidelity"]["thresholds"] is None
    assert "NOT_ASSESSED" in COVERAGE.read_text()
    text = "".join(path.read_text() for path in (DESIGN, LOCK, PROTOCOL, COVERAGE))
    assert not PRIVATE.search(text)
