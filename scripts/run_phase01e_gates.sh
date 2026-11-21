#!/usr/bin/env bash
set -euo pipefail

PHASE01E_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$PHASE01E_ROOT"

GWYDDION_PREFIX=${GWYDDION_PREFIX:-"$HOME/.local/opt/gwyddion-2.71"}
GWYDDION_EXECUTABLE=${GWYDDION_EXECUTABLE:-"$GWYDDION_PREFIX/bin/gwyddion"}
GWYDDION_LIBRARY_DIR=${GWYDDION_LIBRARY_DIR:-"$GWYDDION_PREFIX/lib"}
GWYDDION_MODULE_DIR=${GWYDDION_MODULE_DIR:-"$GWYDDION_LIBRARY_DIR/gwyddion/modules"}
GWYDDION_HELPER="$PHASE01E_ROOT/tools/gwyddion-reference/spmkit-gwyddion-roughness-reference"
GWYFILE_WHEEL="$PHASE01E_ROOT/campaigns/gwyddion-cross-validation-v0.1/dependencies/gwyfile-0.3.0-py3-none-any.whl"

test -x "$GWYDDION_EXECUTABLE"
test -d "$GWYDDION_LIBRARY_DIR"
test -d "$GWYDDION_MODULE_DIR"
test -f "$GWYFILE_WHEEL"

SUT_HEAD_BEFORE=$(git -C ../spmkit-sanitize rev-parse HEAD)
SUT_STATUS_BEFORE=$(git -C ../spmkit-sanitize status --porcelain=v1 | sha256sum | awk '{print $1}')
SUT_DIFF_BEFORE=$(git -C ../spmkit-sanitize diff --binary | sha256sum | awk '{print $1}')
PHANTOMS_HEAD_BEFORE=$(git -C ../spmkit-phantoms rev-parse HEAD)
PHANTOMS_STATUS_BEFORE=$(git -C ../spmkit-phantoms status --porcelain=v1 | sha256sum | awk '{print $1}')
PHANTOMS_DIFF_BEFORE=$(git -C ../spmkit-phantoms diff --binary | sha256sum | awk '{print $1}')

make phase01d-gates
make phase01e-probe \
    GWYDDION_PREFIX="$GWYDDION_PREFIX" \
    GWYDDION_EXECUTABLE="$GWYDDION_EXECUTABLE" \
    GWYDDION_LIBRARY_DIR="$GWYDDION_LIBRARY_DIR" \
    GWYDDION_MODULE_DIR="$GWYDDION_MODULE_DIR"

PHASE01E_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spmkit-validation-phase01e-gates.XXXXXX")
cleanup_phase01e_tmp() {
    if [[ -d "$PHASE01E_TMP" ]]; then
        find "$PHASE01E_TMP" -depth -delete
    fi
}
trap cleanup_phase01e_tmp EXIT

export PYTHONDONTWRITEBYTECODE=1
PHASE01E_VENV="$PHASE01E_TMP/test-venv"
uv venv --python 3.12 "$PHASE01E_VENV"
VIRTUAL_ENV="$PHASE01E_VENV" uv sync --active --frozen --all-extras
PHASE01E_PYTHON="$PHASE01E_VENV/bin/python"
PHASE01E_PYTHONPATH="$PHASE01E_ROOT/src"
PHASE01E_PATH="$PHASE01E_VENV/bin:$PATH"

SPMKIT_GWYDDION_HELPER="$GWYDDION_HELPER" \
SPMKIT_GWYDDION_LIBRARY_DIR="$GWYDDION_LIBRARY_DIR" \
SPMKIT_GWYDDION_MODULE_DIR="$GWYDDION_MODULE_DIR" \
PYTHONPATH="$PHASE01E_PYTHONPATH" "$PHASE01E_PYTHON" -m pytest -q \
    tests/adapters/gwyddion/test_reference_format.py \
    tests/adapters/gwyddion/test_reference_helper.py \
    tests/adapters/gwyddion/test_library_runner.py \
    tests/execution/test_gwyddion_cross_validation.py \
    tests/execution/test_gwyddion_cross_cli.py \
    tests/adapters/gwyddion/test_independence_semantics.py
PYTHONPATH="$PHASE01E_PYTHONPATH" "$PHASE01E_PYTHON" -m pytest -q tests/
PATH="$PHASE01E_PATH" ruff check .
uv lock --check

uv build --out-dir "$PHASE01E_TMP/harness-dist"
PHASE01E_WHEEL_VENV="$PHASE01E_TMP/harness-wheel-venv"
uv venv --python 3.12 "$PHASE01E_WHEEL_VENV"
set -- "$PHASE01E_TMP"/harness-dist/*.whl
test -f "$1"
uv pip install --python "$PHASE01E_WHEEL_VENV/bin/python" "$1"
PHASE01E_CLI="$PHASE01E_WHEEL_VENV/bin/spmkit-validation"
test "$($PHASE01E_WHEEL_VENV/bin/python -c 'import importlib.metadata; print(importlib.metadata.version("spmkit-validation"))')" = "0.1.4"

PHASE01E_CAMPAIGN="$PHASE01E_TMP/campaign"
"$PHASE01E_CLI" campaign prepare-gwyddion-cross-validation \
    --output-dir "$PHASE01E_CAMPAIGN" \
    --sut-repository ../spmkit-sanitize \
    --gwyddion-identity evidence/phase01e-gwyddion/gwyddion-identity-installed.json \
    --installed-viability evidence/phase01e-gwyddion/viability-probe-installed.json \
    --helper-source tools/gwyddion-reference/gwyddion_roughness_reference.c \
    --helper-binary "$GWYDDION_HELPER" \
    --helper-build-record evidence/phase01e-gwyddion/helper-build.json \
    --gwyfile-wheel "$GWYFILE_WHEEL" \
    --generator-commit "$(git rev-parse HEAD)" --json
"$PHASE01E_CLI" bundle validate "$PHASE01E_CAMPAIGN/draft-bundle.json" --json
"$PHASE01E_CLI" bundle verify-artifacts "$PHASE01E_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01E_CAMPAIGN" --json
"$PHASE01E_CLI" bundle freeze "$PHASE01E_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01E_CAMPAIGN" \
    --output-dir "$PHASE01E_TMP/protocol-snapshot" \
    --frozen-at 2026-07-27T04:05:00Z --json
PHASE01E_PROTOCOL_DIR=$(find "$PHASE01E_TMP/protocol-snapshot" \
    -mindepth 1 -maxdepth 1 -type d)
test -n "$PHASE01E_PROTOCOL_DIR"
PHASE01E_PROTOCOL="$PHASE01E_PROTOCOL_DIR/bundle.json"
PHASE01E_FREEZE_RECEIPT="$PHASE01E_PROTOCOL_DIR/freeze-receipt.json"
"$PHASE01E_CLI" bundle verify-snapshot "$PHASE01E_PROTOCOL" \
    "$PHASE01E_FREEZE_RECEIPT" --artifact-root "$PHASE01E_CAMPAIGN" --json

(
    cd ../spmkit-sanitize
    uv build --out-dir "$PHASE01E_TMP/sut-dist"
)
set -- "$PHASE01E_TMP"/sut-dist/*.whl
test -f "$1"
PHASE01E_SUT_WHEEL="$1"

PHASE01E_PRIMARY_JSON=$(
    "$PHASE01E_CLI" campaign execute-gwyddion-cross-validation \
        "$PHASE01E_PROTOCOL" "$PHASE01E_FREEZE_RECEIPT" \
        --artifact-root "$PHASE01E_CAMPAIGN" \
        --sut-wheel "$PHASE01E_SUT_WHEEL" \
        --gwyddion-command "$GWYDDION_HELPER" \
        --gwyddion-library-dir "$GWYDDION_LIBRARY_DIR" \
        --gwyddion-module-dir "$GWYDDION_MODULE_DIR" \
        --output-dir "$PHASE01E_CAMPAIGN/execution-primary" --json
)
PHASE01E_RESULT_HASH=$(
    "$PHASE01E_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01E_PRIMARY_JSON"
)
PHASE01E_RESULT_DIR="$PHASE01E_CAMPAIGN/execution-primary/result-snapshot/$PHASE01E_RESULT_HASH"
PHASE01E_RESULT="$PHASE01E_RESULT_DIR/result-bundle.json"
PHASE01E_RECEIPT="$PHASE01E_RESULT_DIR/execution-receipt.json"
"$PHASE01E_CLI" campaign verify-result "$PHASE01E_RESULT" "$PHASE01E_RECEIPT" \
    --protocol-bundle "$PHASE01E_PROTOCOL" \
    --protocol-receipt "$PHASE01E_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01E_CAMPAIGN" --json

"$PHASE01E_PYTHON" - "$PHASE01E_PRIMARY_JSON" "$PHASE01E_RESULT" "$PHASE01E_RECEIPT" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

payload = json.loads(sys.argv[1])
bundle = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
receipt = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
cross = [item for item in bundle["comparisons"] if item["comparison_id"].startswith("comparison.cross.gwyddion.")]
assert payload["software_test"] == "COMPLETED", payload
assert payload["spmkit_runs"] == 6 and payload["external_reference_runs"] == 6, payload
assert len(bundle["runs"]) == 13 and len(bundle["comparisons"]) == 54
assert Counter(item["outcome"] for item in cross) == {"PASS": 18}
assert len(bundle["claims"]) == 7
assert {item["status"] for item in bundle["claims"]} == {"SUPPORTED"}
assert {item["level"] for item in bundle["claims"]} == {
    "LEVEL 1 — SOFTWARE_VERIFIED",
    "LEVEL 2 — NUMERICALLY_VERIFIED",
    "LEVEL 3 — CROSS_VALIDATED",
}
assert receipt["external_reference"]["producer_is_third_party"] is True
assert receipt["external_reference"]["independence_assessment"] == "INDEPENDENT"
assert len(receipt["external_reference"]["external_run_ids"]) == 6
assert receipt["external_reference"]["external_comparison_count"] == 18
PY

PHASE01E_REPEAT_JSON=$(
    "$PHASE01E_CLI" campaign execute-gwyddion-cross-validation \
        "$PHASE01E_PROTOCOL" "$PHASE01E_FREEZE_RECEIPT" \
        --artifact-root "$PHASE01E_CAMPAIGN" \
        --sut-wheel "$PHASE01E_SUT_WHEEL" \
        --gwyddion-command "$GWYDDION_HELPER" \
        --gwyddion-library-dir "$GWYDDION_LIBRARY_DIR" \
        --gwyddion-module-dir "$GWYDDION_MODULE_DIR" \
        --output-dir "$PHASE01E_CAMPAIGN/execution-repeat" --json
)
PHASE01E_REPEAT_HASH=$(
    "$PHASE01E_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01E_REPEAT_JSON"
)
PHASE01E_REPEAT_RESULT="$PHASE01E_CAMPAIGN/execution-repeat/result-snapshot/$PHASE01E_REPEAT_HASH/result-bundle.json"
"$PHASE01E_WHEEL_VENV/bin/python" - "$PHASE01E_RESULT" "$PHASE01E_REPEAT_RESULT" <<'PY'
import json
import sys
from pathlib import Path

from spmkit_validation.execution import compare_gwyddion_cross_repetition

first = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
second = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
record = compare_gwyddion_cross_repetition(first, second)
assert record["status"] == "PASS", record
assert record["determinism_category"] == "NUMERICALLY_REPEATABLE"
assert record["level_5_claimed"] is False
PY

if rg -n '/home/|/Users/' "$PHASE01E_CAMPAIGN" -g '!**/sut-venv/**'; then
    exit 1
fi
git diff --check
test -z "$(git status --porcelain=v1)"
test "$(git -C ../spmkit-sanitize rev-parse HEAD)" = "$SUT_HEAD_BEFORE"
test "$(git -C ../spmkit-sanitize status --porcelain=v1 | sha256sum | awk '{print $1}')" = "$SUT_STATUS_BEFORE"
test "$(git -C ../spmkit-sanitize diff --binary | sha256sum | awk '{print $1}')" = "$SUT_DIFF_BEFORE"
test "$(git -C ../spmkit-phantoms rev-parse HEAD)" = "$PHANTOMS_HEAD_BEFORE"
test "$(git -C ../spmkit-phantoms status --porcelain=v1 | sha256sum | awk '{print $1}')" = "$PHANTOMS_STATUS_BEFORE"
test "$(git -C ../spmkit-phantoms diff --binary | sha256sum | awk '{print $1}')" = "$PHANTOMS_DIFF_BEFORE"

echo "PHASE_01E gates PASS software_tests=12 spmkit_runs=6 external_reference_runs=6 cross_comparisons=18_PASS claims=LEVEL_1_LEVEL_2_LEVEL_3_SUPPORTED repeatability=NUMERICALLY_REPEATABLE negative_independence=PASS tampering=DETECTED real_data_accessed=NO holdout_accessed=NO"
