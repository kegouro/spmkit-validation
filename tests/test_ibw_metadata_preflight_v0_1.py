from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/ibw"
DOCUMENT = ROOT / "docs/validation/IBW_METADATA_PREFLIGHT_v0.1.md"


def test_metadata_preflight_evidence_is_complete_and_sanitized() -> None:
    allowlist = json.loads((EVIDENCE / "ibw_metadata_preflight_v0.1_allowlist.json").read_text())
    inventory = json.loads((EVIDENCE / "ibw_metadata_preflight_v0.1_structural_inventory.json").read_text())
    families = json.loads((EVIDENCE / "ibw_metadata_preflight_v0.1_families.json").read_text())
    candidates = allowlist["candidates"]
    records = inventory["records"]
    assert allowlist["candidate_count"] == len(candidates) == len(records) == 14
    assert len({item["sha256"] for item in candidates}) == 14
    assert all(item["relative_path"].startswith("<external-data>/") for item in candidates)
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in candidates)
    assert inventory["non_allowlist_files_opened"] == 0
    assert inventory["payload_bytes_read"] == 0
    assert inventory["scientific_data_observed"] is False
    assert inventory["max_header_bytes_read"] <= 4096
    assert {record["structural_result"] for record in records} == {"HEADER_VALID"}
    assert families["unique_hashes"] == 14
    assert families["exact_duplicates"] == 0
    assert families["structural_family_count"] == 2

    evidence_paths = [
        EVIDENCE / "ibw_metadata_preflight_v0.1_allowlist.json",
        EVIDENCE / "ibw_metadata_preflight_v0.1_structural_inventory.json",
        EVIDENCE / "ibw_metadata_preflight_v0.1_families.json",
    ]
    curated = "\n".join([DOCUMENT.read_text(), *(path.read_text() for path in evidence_paths)])
    assert "/Users/" not in curated
    assert "file://" not in curated
    assert "@" not in curated
    prohibited = ("min", "max", "mean", "rms", "roughness", "preview", "thumbnail", "Sa", "Sq", "Sz")
    assert not any(re.search(rf"\\b{re.escape(token)}\\b", curated, re.IGNORECASE) for token in prohibited)
