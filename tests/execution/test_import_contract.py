from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_execution_import_has_no_sut_or_gui_dependencies() -> None:
    forbidden = (
        "PyQt6",
        "pyqtgraph",
        "spmkit",
        "scipy",
        "spmkit_validation.adapters",
        "spmkit_validation.runner",
    )
    code = f"""
import json
import sys
import spmkit_validation.execution
forbidden = {forbidden!r}
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
print(json.dumps(loaded))
"""
    environment = os.environ.copy()
    source_root = os.path.abspath("src")
    environment["PYTHONPATH"] = source_root
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert json.loads(completed.stdout) == []


def test_execution_import_declares_numpy_directly() -> None:
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"numpy>=1.24,<3"' in project
