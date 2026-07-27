#!/usr/bin/env bash
set -euo pipefail

PHASE01E_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$PHASE01E_ROOT"

UV=${UV:-uv}
GWYDDION_PREFIX=${GWYDDION_PREFIX:-"$HOME/.local/opt/gwyddion-2.71"}
GWYDDION_EXECUTABLE=${GWYDDION_EXECUTABLE:-"$GWYDDION_PREFIX/bin/gwyddion"}
GWYDDION_LIBRARY_DIR=${GWYDDION_LIBRARY_DIR:-"$GWYDDION_PREFIX/lib"}
GWYDDION_MODULE_DIR=${GWYDDION_MODULE_DIR:-"$GWYDDION_LIBRARY_DIR/gwyddion/modules"}
GWYDDION_HELPER=${GWYDDION_HELPER:-"$PHASE01E_ROOT/tools/gwyddion-reference/spmkit-gwyddion-roughness-reference"}

export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=src "$UV" run --frozen --python 3.12 python -m pytest -q \
    tests/adapters/gwyddion/test_viability.py \
    tests/adapters/gwyddion/test_independence_semantics.py
PYTHONPATH=src "$UV" run --frozen --python 3.12 python -m \
    spmkit_validation.adapters.gwyddion.viability \
    --output-dir evidence/phase01e-gwyddion \
    --observed-at 2026-07-26T12:00:00Z --json

make -C tools/gwyddion-reference GWYDDION_PREFIX="$GWYDDION_PREFIX"
SPMKIT_GWYDDION_HELPER="$GWYDDION_HELPER" \
SPMKIT_GWYDDION_LIBRARY_DIR="$GWYDDION_LIBRARY_DIR" \
SPMKIT_GWYDDION_MODULE_DIR="$GWYDDION_MODULE_DIR" \
PYTHONPATH=src "$UV" run --frozen --python 3.12 python -m pytest -q \
    tests/adapters/gwyddion/test_reference_format.py \
    tests/adapters/gwyddion/test_reference_helper.py \
    tests/adapters/gwyddion/test_library_runner.py

PHASE01E_PROBE_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spmkit-phase01e-probe.XXXXXX")
cleanup_phase01e_probe() {
    if [[ -d "$PHASE01E_PROBE_TMP" ]]; then
        find "$PHASE01E_PROBE_TMP" -depth -delete
    fi
}
trap cleanup_phase01e_probe EXIT
PYTHONPATH=src "$UV" run --frozen --python 3.12 python -m \
    spmkit_validation.adapters.gwyddion.installed_viability \
    --output-dir "$PHASE01E_PROBE_TMP" \
    --gwyddion-executable "$GWYDDION_EXECUTABLE" \
    --helper-executable "$GWYDDION_HELPER" \
    --gwyddion-library-dir "$GWYDDION_LIBRARY_DIR" \
    --gwyddion-module-dir "$GWYDDION_MODULE_DIR" \
    --observed-at 2026-07-27T04:00:00Z --json
PYTHONPATH=src "$UV" run --frozen --python 3.12 python - \
    "$PHASE01E_PROBE_TMP/viability-probe-installed.json" \
    evidence/phase01e-gwyddion/viability-probe-installed.json <<'PY'
import json
import sys
from pathlib import Path


def normalized(path):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    roundtrip = document["roundtrip"]
    roundtrip.pop("converted_sha256", None)
    roundtrip.pop("converted_size_bytes", None)
    return document


assert normalized(sys.argv[1]) == normalized(sys.argv[2])
PY
echo "PASS_INSTALLED_REFERENCE attempt_id=phase01e.install-and-resume.001"
