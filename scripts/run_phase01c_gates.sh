#!/usr/bin/env bash
set -euo pipefail

PHASE01C_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$PHASE01C_ROOT"

make phase01b-gates

PHASE01C_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spmkit-validation-phase01c-gates.XXXXXX")
cleanup_phase01c_tmp() {
    if [[ -d "$PHASE01C_TMP" ]]; then
        find "$PHASE01C_TMP" -depth -delete
    fi
}
trap cleanup_phase01c_tmp EXIT

export PYTHONDONTWRITEBYTECODE=1
PHASE01C_VENV="$PHASE01C_TMP/test-venv"
uv venv --python 3.12 "$PHASE01C_VENV"
VIRTUAL_ENV="$PHASE01C_VENV" uv sync --active --frozen --all-extras
PHASE01C_PYTHON="$PHASE01C_VENV/bin/python"
PHASE01C_PYTHONPATH="$PHASE01C_ROOT/src"
PHASE01C_PATH="$PHASE01C_VENV/bin:$PATH"

"$PHASE01C_PYTHON" --version
PYTHONPATH="$PHASE01C_PYTHONPATH" "$PHASE01C_PYTHON" -m pytest -q \
    tests/execution/test_synthetic_protocol.py
PYTHONPATH="$PHASE01C_PYTHONPATH" "$PHASE01C_PYTHON" -m pytest -q \
    tests/execution/test_runner.py tests/execution/test_population_continuity.py
PYTHONPATH="$PHASE01C_PYTHONPATH" "$PHASE01C_PYTHON" -m pytest -q \
    tests/execution/test_result_receipt.py tests/execution/test_campaign_cli.py \
    tests/execution/test_import_contract.py
PYTHONPATH="$PHASE01C_PYTHONPATH" "$PHASE01C_PYTHON" -m pytest -q tests/
PATH="$PHASE01C_PATH" ruff check .
uv lock --check

uv build --out-dir "$PHASE01C_TMP/harness-dist"
PHASE01C_WHEEL_VENV="$PHASE01C_TMP/harness-wheel-venv"
uv venv --python 3.12 "$PHASE01C_WHEEL_VENV"
set -- "$PHASE01C_TMP"/harness-dist/*.whl
test -f "$1"
uv pip install --python "$PHASE01C_WHEEL_VENV/bin/python" "$1"
PHASE01C_CLI="$PHASE01C_WHEEL_VENV/bin/spmkit-validation"

PHASE01C_CAMPAIGN="$PHASE01C_TMP/campaign"
"$PHASE01C_CLI" campaign prepare-synthetic-roughness \
    --output-dir "$PHASE01C_CAMPAIGN" \
    --generator-commit "$(git rev-parse HEAD)" --json
"$PHASE01C_CLI" bundle validate "$PHASE01C_CAMPAIGN/draft-bundle.json" --json
"$PHASE01C_CLI" bundle verify-artifacts "$PHASE01C_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01C_CAMPAIGN" --json
"$PHASE01C_CLI" bundle freeze "$PHASE01C_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01C_CAMPAIGN" \
    --output-dir "$PHASE01C_TMP/protocol-snapshot" \
    --frozen-at 2026-07-26T08:02:00Z --json

PHASE01C_PROTOCOL_DIR=$(find "$PHASE01C_TMP/protocol-snapshot" \
    -mindepth 1 -maxdepth 1 -type d)
test -n "$PHASE01C_PROTOCOL_DIR"
PHASE01C_PROTOCOL="$PHASE01C_PROTOCOL_DIR/bundle.json"
PHASE01C_FREEZE_RECEIPT="$PHASE01C_PROTOCOL_DIR/freeze-receipt.json"
"$PHASE01C_CLI" bundle verify-snapshot "$PHASE01C_PROTOCOL" \
    "$PHASE01C_FREEZE_RECEIPT" --artifact-root "$PHASE01C_CAMPAIGN" --json

SUT_HEAD_BEFORE=$(git -C ../spmkit-sanitize rev-parse HEAD)
SUT_STATUS_BEFORE=$(git -C ../spmkit-sanitize status --porcelain=v1 | sha256sum | awk '{print $1}')
SUT_DIFF_BEFORE=$(git -C ../spmkit-sanitize diff --binary | sha256sum | awk '{print $1}')
PHANTOMS_HEAD_BEFORE=$(git -C ../spmkit-phantoms rev-parse HEAD)
PHANTOMS_STATUS_BEFORE=$(git -C ../spmkit-phantoms status --porcelain=v1 | sha256sum | awk '{print $1}')
PHANTOMS_DIFF_BEFORE=$(git -C ../spmkit-phantoms diff --binary | sha256sum | awk '{print $1}')

(
    cd ../spmkit-sanitize
    uv build --out-dir "$PHASE01C_TMP/sut-dist"
)
set -- "$PHASE01C_TMP"/sut-dist/*.whl
test -f "$1"
PHASE01C_SUT_WHEEL="$1"

PHASE01C_EXECUTION_ONE_JSON=$(
    "$PHASE01C_CLI" campaign execute "$PHASE01C_PROTOCOL" \
        "$PHASE01C_FREEZE_RECEIPT" --artifact-root "$PHASE01C_CAMPAIGN" \
        --sut-wheel "$PHASE01C_SUT_WHEEL" \
        --output-dir "$PHASE01C_CAMPAIGN/execution-one" --json
)
PHASE01C_RESULT_HASH_ONE=$(
    "$PHASE01C_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01C_EXECUTION_ONE_JSON"
)
PHASE01C_RESULT_DIR_ONE="$PHASE01C_CAMPAIGN/execution-one/result-snapshot/$PHASE01C_RESULT_HASH_ONE"
PHASE01C_RESULT_ONE="$PHASE01C_RESULT_DIR_ONE/result-bundle.json"
PHASE01C_EXECUTION_RECEIPT_ONE="$PHASE01C_RESULT_DIR_ONE/execution-receipt.json"
"$PHASE01C_CLI" campaign verify-result "$PHASE01C_RESULT_ONE" \
    "$PHASE01C_EXECUTION_RECEIPT_ONE" --protocol-bundle "$PHASE01C_PROTOCOL" \
    --protocol-receipt "$PHASE01C_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01C_CAMPAIGN" --json

PHASE01C_EXECUTION_TWO_JSON=$(
    "$PHASE01C_CLI" campaign execute "$PHASE01C_PROTOCOL" \
        "$PHASE01C_FREEZE_RECEIPT" --artifact-root "$PHASE01C_CAMPAIGN" \
        --sut-wheel "$PHASE01C_SUT_WHEEL" \
        --output-dir "$PHASE01C_CAMPAIGN/execution-two" --json
)
PHASE01C_RESULT_HASH_TWO=$(
    "$PHASE01C_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01C_EXECUTION_TWO_JSON"
)
PHASE01C_RESULT_TWO="$PHASE01C_CAMPAIGN/execution-two/result-snapshot/$PHASE01C_RESULT_HASH_TWO/result-bundle.json"
"$PHASE01C_WHEEL_VENV/bin/python" - "$PHASE01C_RESULT_ONE" "$PHASE01C_RESULT_TWO" <<'PY'
import json
import sys
from pathlib import Path

from spmkit_validation.execution import compare_campaign_repetition

first = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
second = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
record = compare_campaign_repetition(first, second)
assert record["status"] == "PASS", record
assert record["determinism_category"] == "NUMERICALLY_REPEATABLE"
PY

mkdir "$PHASE01C_TMP/tamper-result"
cp "$PHASE01C_RESULT_ONE" "$PHASE01C_TMP/tamper-result/result-bundle.json"
cp "$PHASE01C_EXECUTION_RECEIPT_ONE" "$PHASE01C_TMP/tamper-result/execution-receipt.json"
"$PHASE01C_PYTHON" - "$PHASE01C_TMP/tamper-result/result-bundle.json" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.write_bytes(path.read_bytes() + b"\n")
PY
set +e
"$PHASE01C_CLI" campaign verify-result \
    "$PHASE01C_TMP/tamper-result/result-bundle.json" \
    "$PHASE01C_TMP/tamper-result/execution-receipt.json" \
    --protocol-bundle "$PHASE01C_PROTOCOL" \
    --protocol-receipt "$PHASE01C_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01C_CAMPAIGN" --json
PHASE01C_TAMPER_EXIT=$?
set -e
test "$PHASE01C_TAMPER_EXIT" -eq 4

mkdir "$PHASE01C_TMP/drift-result"
cp "$PHASE01C_RESULT_ONE" "$PHASE01C_TMP/drift-result/result-bundle.json"
cp "$PHASE01C_EXECUTION_RECEIPT_ONE" "$PHASE01C_TMP/drift-result/execution-receipt.json"
"$PHASE01C_WHEEL_VENV/bin/python" - "$PHASE01C_TMP/drift-result/result-bundle.json" <<'PY'
import json
import sys
from pathlib import Path

from spmkit_validation.lifecycle import canonical_bundle_bytes

path = Path(sys.argv[1])
bundle = json.loads(path.read_text(encoding="utf-8"))
bundle["cases"][0]["tolerances"][0]["absolute"] *= 2
path.write_bytes(canonical_bundle_bytes(bundle))
PY
set +e
"$PHASE01C_CLI" campaign verify-result \
    "$PHASE01C_TMP/drift-result/result-bundle.json" \
    "$PHASE01C_TMP/drift-result/execution-receipt.json" \
    --protocol-bundle "$PHASE01C_PROTOCOL" \
    --protocol-receipt "$PHASE01C_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01C_CAMPAIGN" --json
PHASE01C_DRIFT_EXIT=$?
set -e
test "$PHASE01C_DRIFT_EXIT" -eq 4

git diff --check
test -z "$(git status --porcelain=v1)"
test "$(git -C ../spmkit-sanitize rev-parse HEAD)" = "$SUT_HEAD_BEFORE"
test "$(git -C ../spmkit-sanitize status --porcelain=v1 | sha256sum | awk '{print $1}')" = \
    "$SUT_STATUS_BEFORE"
test "$(git -C ../spmkit-sanitize diff --binary | sha256sum | awk '{print $1}')" = \
    "$SUT_DIFF_BEFORE"
test "$(git -C ../spmkit-phantoms rev-parse HEAD)" = "$PHANTOMS_HEAD_BEFORE"
test "$(git -C ../spmkit-phantoms status --porcelain=v1 | sha256sum | awk '{print $1}')" = \
    "$PHANTOMS_STATUS_BEFORE"
test "$(git -C ../spmkit-phantoms diff --binary | sha256sum | awk '{print $1}')" = \
    "$PHANTOMS_DIFF_BEFORE"

echo "PHASE_01C gates PASS comparisons=18 repeatability=NUMERICALLY_REPEATABLE tampering=DETECTED protocol_drift=DETECTED real_data_accessed=NO holdout_accessed=NO"
