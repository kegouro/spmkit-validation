from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_lifecycle_import_has_no_heavy_gui_reader_adapter_or_spmkit_imports() -> None:
    repository_root = Path(__file__).parents[2]
    source_root = repository_root / "src"
    check = """
import sys
import spmkit_validation.lifecycle

forbidden_exact = {
    "PyQt6",
    "pyqtgraph",
    "matplotlib",
    "scipy",
    "numpy",
    "spmkit",
}
forbidden_prefixes = (
    "PyQt6.",
    "pyqtgraph.",
    "matplotlib.",
    "scipy.",
    "numpy.",
    "spmkit.",
    "spmkit_validation.readers.",
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
