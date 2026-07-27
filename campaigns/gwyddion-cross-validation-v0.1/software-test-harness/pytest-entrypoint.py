from __future__ import annotations

import platform
import sys

import pytest

platform.node = lambda: "spmkit-validation"  # privacy-only JUnit metadata control
raise SystemExit(pytest.main(sys.argv[1:]))
