from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.lifecycle import LifecycleError, canonical_bundle_bytes, freeze_bundle

from .conftest import FREEZE_TIME


def test_canonical_bytes_are_deterministic() -> None:
    bundle = {"z": [3, 2, 1], "a": {"unicode": "µm"}}
    assert canonical_bundle_bytes(bundle) == canonical_bundle_bytes(bundle)


def test_canonical_keys_are_sorted() -> None:
    assert canonical_bundle_bytes({"z": 1, "a": 2}) == b'{"a":2,"z":1}\n'


def test_canonical_output_has_exactly_one_final_newline() -> None:
    result = canonical_bundle_bytes({"text": "value\n"})
    assert result.endswith(b"\n")
    assert not result.endswith(b"\n\n")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(LifecycleError) as caught:
        canonical_bundle_bytes({"value": value})
    assert caught.value.issues[0].code == "CANONICAL.INVALID_JSON_VALUE"


def test_canonical_input_is_not_mutated(draft_bundle: dict[str, Any]) -> None:
    before = copy.deepcopy(draft_bundle)
    canonical_bundle_bytes(draft_bundle)
    assert draft_bundle == before


def test_same_bundle_and_frozen_at_produce_same_hash(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path
) -> None:
    first = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "first", FREEZE_TIME)
    second = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "second", FREEZE_TIME)
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.snapshot_path.read_bytes() == second.snapshot_path.read_bytes()


def test_changed_value_produces_different_hash(draft_bundle: dict[str, Any]) -> None:
    original = canonical_bundle_bytes(draft_bundle)
    changed = copy.deepcopy(draft_bundle)
    changed["campaign"]["protocol_version"] = "0.1.0-changed"
    modified = canonical_bundle_bytes(changed)
    assert hashlib.sha256(original).digest() != hashlib.sha256(modified).digest()
