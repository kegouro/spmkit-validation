from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_schema_import_has_no_gui_scientific_or_instrument_reader_side_effects() -> None:
    repository_root = Path(__file__).parents[2]
    source_root = repository_root / "src"
    check = """
import sys
import spmkit_validation.schemas

forbidden_exact = {"PyQt6", "pyqtgraph", "matplotlib", "scipy"}
forbidden_prefixes = (
    "PyQt6.",
    "pyqtgraph.",
    "matplotlib.",
    "scipy.",
    "spmkit.readers.",
    "spmkit.core.readers.",
    "spmkit_validation.adapters.",
)
loaded = sorted(
    name
    for name in sys.modules
    if name in forbidden_exact or name.startswith(forbidden_prefixes)
)
if loaded:
    raise SystemExit("forbidden imports: " + ", ".join(loaded))
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(source_root)
    result = subprocess.run(
        [sys.executable, "-c", check],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
