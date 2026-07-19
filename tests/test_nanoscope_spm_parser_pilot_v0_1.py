import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_design_is_six_unique_cases_with_declared_unblinding() -> None:
    lock = json.loads((ROOT / "locks/nanoscope_spm_parser_pilot_v0.1.json").read_text())
    rows = [json.loads(line) for line in (ROOT / "campaigns/design/nanoscope_spm_parser_pilot_v0.1.jsonl").read_text().splitlines()]
    assert lock["state"] == "READY_FOR_IMPLEMENTATION"
    assert lock["incident"]["classification"] == "ACCIDENTAL_PRE_FREEZE_UNBLINDING"
    assert [row["role"] for row in rows].count("DEVELOPMENT") == 4
    assert [row["role"] for row in rows].count("EXTERNAL_CONFIRMATION") == 2
    assert len({row["sha256"] for row in rows}) == 6
    assert all("/Users/" not in json.dumps(value) for value in (lock, rows))
    assert len(lock["unblinded_reserve_sha256"]) == 12
    assert all(len(value) == 64 for value in lock["unblinded_reserve_sha256"])
