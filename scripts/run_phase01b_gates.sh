#!/usr/bin/env bash
set -euo pipefail

PHASE01B_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$PHASE01B_ROOT"

PHASE01B_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spmkit-validation-phase01b-gates.XXXXXX")
cleanup_phase01b_tmp() {
    if [[ -d "$PHASE01B_TMP" ]]; then
        find "$PHASE01B_TMP" -depth -delete
    fi
}
trap cleanup_phase01b_tmp EXIT

export PYTHONDONTWRITEBYTECODE=1
PHASE01B_VENV="$PHASE01B_TMP/test-venv"
uv venv --python 3.12 "$PHASE01B_VENV"
VIRTUAL_ENV="$PHASE01B_VENV" uv sync --active --frozen --all-extras
PHASE01B_PYTHON="$PHASE01B_VENV/bin/python"
PHASE01B_PYTHONPATH="$PHASE01B_ROOT/src"
PHASE01B_PATH="$PHASE01B_VENV/bin:$PATH"

"$PHASE01B_PYTHON" --version
PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" - <<'PY'
import json
from pathlib import Path

roots = (
    Path("schemas/v0.1"),
    Path("tests/fixtures/schema"),
    Path("tests/fixtures/lifecycle"),
    Path("examples/campaigns"),
)
for root in roots:
    for path in sorted(root.rglob("*.json")):
        json.loads(path.read_text(encoding="utf-8"))
PY

PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" -m pytest -q \
    tests/lifecycle/test_canonical.py
PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" -m pytest -q \
    tests/lifecycle/test_artifacts.py tests/lifecycle/test_runmanifest.py
PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" -m pytest -q \
    tests/lifecycle/test_freeze.py tests/lifecycle/test_receipt_verification.py
PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" -m pytest -q \
    tests/lifecycle/test_cli.py tests/lifecycle/test_import_contract.py
PYTHONPATH="$PHASE01B_PYTHONPATH" "$PHASE01B_PYTHON" -m pytest -q tests/
PATH="$PHASE01B_PATH" ruff check .
uv lock --check

uv build --out-dir "$PHASE01B_TMP/dist"
PHASE01B_WHEEL_VENV="$PHASE01B_TMP/wheel-venv"
uv venv --python 3.12 "$PHASE01B_WHEEL_VENV"
set -- "$PHASE01B_TMP"/dist/*.whl
test -f "$1"
uv pip install --python "$PHASE01B_WHEEL_VENV/bin/python" "$1"
PHASE01B_CLI="$PHASE01B_WHEEL_VENV/bin/spmkit-validation"
PHASE01B_FIXTURE="$PHASE01B_ROOT/tests/fixtures/lifecycle/draft-bundle.json"
PHASE01B_ARTIFACTS="$PHASE01B_ROOT/tests/fixtures/lifecycle/artifacts"

"$PHASE01B_CLI" bundle validate "$PHASE01B_FIXTURE" --json
"$PHASE01B_CLI" bundle verify-artifacts "$PHASE01B_FIXTURE" \
    --artifact-root "$PHASE01B_ARTIFACTS" --json
"$PHASE01B_CLI" bundle freeze "$PHASE01B_FIXTURE" \
    --artifact-root "$PHASE01B_ARTIFACTS" \
    --output-dir "$PHASE01B_TMP/snapshot-one" \
    --frozen-at 2026-02-01T00:00:00Z --json
"$PHASE01B_CLI" bundle freeze "$PHASE01B_FIXTURE" \
    --artifact-root "$PHASE01B_ARTIFACTS" \
    --output-dir "$PHASE01B_TMP/snapshot-two" \
    --frozen-at 2026-02-01T00:00:00Z --json

PHASE01B_SNAPSHOT_ONE=$(find "$PHASE01B_TMP/snapshot-one" -mindepth 1 -maxdepth 1 -type d)
PHASE01B_SNAPSHOT_TWO=$(find "$PHASE01B_TMP/snapshot-two" -mindepth 1 -maxdepth 1 -type d)
test -n "$PHASE01B_SNAPSHOT_ONE"
test -n "$PHASE01B_SNAPSHOT_TWO"
cmp "$PHASE01B_SNAPSHOT_ONE/bundle.json" "$PHASE01B_SNAPSHOT_TWO/bundle.json"
PHASE01B_HASH_ONE=$(sha256sum "$PHASE01B_SNAPSHOT_ONE/bundle.json" | awk '{print $1}')
PHASE01B_HASH_TWO=$(sha256sum "$PHASE01B_SNAPSHOT_TWO/bundle.json" | awk '{print $1}')
test "$PHASE01B_HASH_ONE" = "$PHASE01B_HASH_TWO"
test "$(basename "$PHASE01B_SNAPSHOT_ONE")" = "$PHASE01B_HASH_ONE"

"$PHASE01B_CLI" bundle verify-snapshot \
    "$PHASE01B_SNAPSHOT_ONE/bundle.json" \
    "$PHASE01B_SNAPSHOT_ONE/freeze-receipt.json" \
    --artifact-root "$PHASE01B_ARTIFACTS" --json

mkdir "$PHASE01B_TMP/tamper"
cp "$PHASE01B_SNAPSHOT_ONE/bundle.json" "$PHASE01B_TMP/tamper/bundle.json"
cp "$PHASE01B_SNAPSHOT_ONE/freeze-receipt.json" \
    "$PHASE01B_TMP/tamper/freeze-receipt.json"
"$PHASE01B_WHEEL_VENV/bin/python" - "$PHASE01B_TMP/tamper/bundle.json" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.write_bytes(path.read_bytes() + b"\n")
PY
set +e
"$PHASE01B_CLI" bundle verify-snapshot \
    "$PHASE01B_TMP/tamper/bundle.json" \
    "$PHASE01B_TMP/tamper/freeze-receipt.json" --json
PHASE01B_TAMPER_EXIT=$?
set -e
test "$PHASE01B_TAMPER_EXIT" -eq 4

git diff --check
git status --porcelain=v1 > "$PHASE01B_TMP/repository-status"
test ! -s "$PHASE01B_TMP/repository-status"
test "$(git -C ../spmkit-sanitize rev-parse HEAD)" = \
    "11daf8879c9e3e098ce844778592525d4f2bdc53"
git -C ../spmkit-sanitize status --porcelain=v1 > "$PHASE01B_TMP/sut-status"
test ! -s "$PHASE01B_TMP/sut-status"

echo "PHASE_01B gates PASS snapshot_sha256=$PHASE01B_HASH_ONE"
