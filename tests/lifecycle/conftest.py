from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.schemas import load_validation_bundle

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "lifecycle"
FREEZE_TIME = "2026-02-01T00:00:00Z"


@pytest.fixture
def lifecycle_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "lifecycle"
    shutil.copytree(FIXTURE_ROOT, workspace)
    return workspace


@pytest.fixture
def draft_bundle_path(lifecycle_workspace: Path) -> Path:
    return lifecycle_workspace / "draft-bundle.json"


@pytest.fixture
def artifact_root(lifecycle_workspace: Path) -> Path:
    return lifecycle_workspace / "artifacts"


@pytest.fixture
def draft_bundle(draft_bundle_path: Path) -> dict[str, Any]:
    return load_validation_bundle(draft_bundle_path)


def write_bundle(path: Path, bundle: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
