import json
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_results_match_frozen_design_and_thresholds():
    design = {json.loads(line)["case_id"]: json.loads(line) for line in (ROOT / "campaigns/design/gwyddion_roughness_48_v0.1.jsonl").read_text().splitlines()}
    records = [json.loads(line) for line in (ROOT / "evidence/campaigns/gwyddion_roughness_48_v0.1_results.jsonl").read_text().splitlines()]
    summary = json.loads((ROOT / "evidence/campaigns/gwyddion_roughness_48_v0.1_summary.json").read_text())
    assert len(records) == len(design) == 48
    assert summary["counts"] == {"cases": 48, "comparisons": 144, "within_threshold": 144, "outside_threshold": 0, "execution_errors": 0}
    assert summary["global_status"] == "CAMPAIGN_PASS"
    assert summary["evidence_level"] == "LEVEL 3 CROSS_VALIDATED"
    for record in records:
        frozen = design[record["case_id"]]
        assert record["canonical_matrix_sha256"] == frozen["canonical_matrix_sha256"]
        assert record["gsf_sha256"] == frozen["gsf_sha256"]
        assert set(record["metrics"]) == {"Sa", "Sq", "Sz"}
        for metric in record["metrics"].values():
            allowed = 1e-6 + 1e-6 * max(abs(metric["spmkit_nm"]), abs(metric["gwyddion_nm"]))
            assert metric["allowed_delta_nm"] == allowed
            assert metric["abs_delta_nm"] <= allowed
            assert metric["status"] == "WITHIN_THRESHOLD"
        assert record["case_status"] == "CASE_PASS"
