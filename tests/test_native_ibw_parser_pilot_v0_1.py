from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "campaigns/design/native_ibw_parser_pilot_v0.1.jsonl"
LOCK = ROOT / "locks/native_ibw_parser_pilot_v0.1.json"
ALLOWLIST = ROOT / "evidence/ibw/ibw_metadata_preflight_v0.1_allowlist.json"
INVENTORY = ROOT / "evidence/ibw/ibw_metadata_preflight_v0.1_structural_inventory.json"


def test_revised_metadata_only_selection_is_complete_and_disjoint() -> None:
    lock = json.loads(LOCK.read_text())
    allowlist = json.loads(ALLOWLIST.read_text())
    inventory = json.loads(INVENTORY.read_text())
    rows = [json.loads(line) for line in DESIGN.read_text().splitlines()]
    assert all("role" not in candidate for candidate in allowlist["candidates"])
    assert all("role" not in record for record in inventory["records"])
    by_hash = {row["sha256"]: row for row in inventory["records"]}
    groups: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for candidate in allowlist["candidates"]:
        groups[tuple(by_hash[candidate["sha256"]]["shape"])].append(candidate["sha256"])
    for hashes in groups.values():
        hashes.sort()

    expected = {}
    for shape, hashes in groups.items():
        development_count = 1 if shape == (1024, 1024, 3) else 3
        expected.update({value: "DEVELOPMENT" for value in hashes[:development_count]})
        expected[hashes[development_count]] = "BLIND_HOLDOUT"
        expected.update({value: "BLIND_RESERVE" for value in hashes[development_count + 1 :]})

    actual = {row["sha256"]: row["role"] for row in rows}
    assert expected == actual
    assert len(actual) == 14 == len(set(actual))
    assert list(actual.values()).count("DEVELOPMENT") == 4
    assert list(actual.values()).count("BLIND_HOLDOUT") == 2
    assert list(actual.values()).count("BLIND_RESERVE") == 8
    assert {tuple(row["declared_shape"]) for row in rows if row["role"] == "DEVELOPMENT"} == set(groups)
    assert {tuple(row["declared_shape"]) for row in rows if row["role"] == "BLIND_HOLDOUT"} == set(groups)
    assert all(tuple(row["declared_shape"]) == (256, 256, 4) for row in rows if row["role"] == "BLIND_RESERVE")
    assert lock["metadata_evidence"]["payload_bytes_read"] == 0
    assert lock["metadata_evidence"]["scientific_data_observed"] is False
    serialized = "\n".join([LOCK.read_text(), DESIGN.read_text()])
    assert "/Users/" not in serialized
    assert "file://" not in serialized
    assert "@" not in serialized
