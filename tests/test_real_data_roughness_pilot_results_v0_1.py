from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
RESULTS = ROOT / "evidence/campaigns/real_data_roughness_pilot_v0.1_results.jsonl"
SUMMARY = ROOT / "evidence/campaigns/real_data_roughness_pilot_v0.1_summary.json"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.I)


def test_curated_real_data_results_contract() -> None:
    rows = [json.loads(line) for line in RESULTS.read_text().splitlines()]
    summary = json.loads(SUMMARY.read_text())
    comparisons = [value for row in rows for value in row["shared_matrix"]["comparisons"].values()]
    assert len(rows) == 12
    assert len({row["case_id"] for row in rows}) == 12
    assert {row["source_id"] for row in rows} == {"ce-6ntsk", "16287446", "17970187"}
    assert len(comparisons) == 36
    assert all(value["status"] == "WITHIN_THRESHOLD" for value in comparisons)
    assert summary["shared_matrix_within_threshold"] == 36
    assert summary["shared_matrix_outside_threshold"] == 0
    assert summary["evidence_level"] == "LEVEL 3 CROSS_VALIDATED"
    assert summary["parser_fidelity"]["PARSER_EQUIVALENCE_OBSERVED"] == 10
    assert summary["parser_fidelity"]["PARSER_DIFFERENCE_OBSERVED"] == 2
    text = RESULTS.read_text() + SUMMARY.read_text()
    assert not PRIVATE.search(text)
