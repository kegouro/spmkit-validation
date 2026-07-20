from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/incidents/ibw_preflight_scope_incident_v0.1.md"
MANIFEST = ROOT / "evidence/incidents/ibw_preflight_scope_incident_v0.1.json"


def test_ibw_incident_record_preserves_scope_without_scientific_values() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["incident"] == "ACCIDENTAL_OUT_OF_SCOPE_NUMERIC_EMISSION"
    assert manifest["decision"] == "IBW_PANEL_BLINDNESS_PRESERVED"
    assert manifest["candidate_observations"] == {
        "files_opened": 0,
        "content_read": False,
        "scientific_values_emitted": False,
        "selection_made": False,
    }
    candidates = manifest["candidates"]
    assert len(candidates) == 14
    assert {item["relative_path"] for item in candidates}
    assert all(item["incident_classification"] == "NOT_TOUCHED" for item in candidates)
    assert all(item["relative_path"].startswith("<external-data>/") for item in candidates)
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in candidates)

    curated_text = DOCUMENT.read_text(encoding="utf-8") + MANIFEST.read_text(encoding="utf-8")
    assert "/Users/" not in curated_text
    assert "file://" not in curated_text
    assert "@" not in curated_text
    prohibited = ("matrix", "pixel", "roughness", "preview", "profile", '"Sa"', '"Sq"', '"Sz"')
    assert not any(token in curated_text for token in prohibited)
