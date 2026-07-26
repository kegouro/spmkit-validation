from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.schemas import load_validation_bundle

REPOSITORY_ROOT = Path(__file__).parents[2]


@pytest.fixture
def minimal_bundle() -> dict[str, Any]:
    return load_validation_bundle(REPOSITORY_ROOT / "tests/fixtures/schema/minimal_valid.json")


@pytest.fixture
def complete_bundle() -> dict[str, Any]:
    return load_validation_bundle(
        REPOSITORY_ROOT / "examples/campaigns/synthetic_roughness_v0.1.json"
    )
