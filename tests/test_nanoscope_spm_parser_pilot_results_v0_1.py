from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evidence/campaigns/nanoscope_spm_parser_pilot_v0.1_results.jsonl"
SUMMARY = ROOT / "evidence/campaigns/nanoscope_spm_parser_pilot_v0.1_summary.json"
LOCK = ROOT / "locks/nanoscope_spm_parser_pilot_v0.1.json"
PRIVATE = re.compile(r"/" + "Users/|file" + r"://|[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}", re.I)


def test_nanoscope_pilot_results_contract() -> None:
    rows = [json.loads(line) for line in RESULTS.read_text().splitlines()]
    summary = json.loads(SUMMARY.read_text())
    lock = json.loads(LOCK.read_text())
    comparisons = [value for row in rows for value in row["end_to_end"]["comparisons"].values()]
    assert len(rows) == 6
    assert len({row["case_id"] for row in rows}) == 6
    assert [row["role"] for row in rows].count("DEVELOPMENT") == 4
    assert [row["role"] for row in rows].count("EXTERNAL_CONFIRMATION") == 2
    assert [row["file_sha256"] for row in rows] == [case["sha256"] for case in lock["cases"]]
    assert all(row["parser_fidelity"]["status"] == "PARSER_EQUIVALENCE_OBSERVED" for row in rows)
    assert len(comparisons) == 18
    assert all(value["status"] == "WITHIN_THRESHOLD" for value in comparisons)
    assert summary["incident"] == "ACCIDENTAL_PRE_FREEZE_UNBLINDING"
    assert summary["evidence_level"] == "LEVEL 2 NUMERICALLY_VERIFIED"
    assert summary["roughness_within_threshold"] == 18
    assert summary["roughness_outside_threshold"] == 0
    assert not PRIVATE.search(RESULTS.read_text() + SUMMARY.read_text())
