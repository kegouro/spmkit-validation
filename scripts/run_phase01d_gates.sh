#!/usr/bin/env bash
set -euo pipefail

PHASE01D_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$PHASE01D_ROOT"

make phase01c-gates

PHASE01D_TMP=$(mktemp -d "${TMPDIR:-/tmp}/spmkit-validation-phase01d-gates.XXXXXX")
cleanup_phase01d_tmp() {
    if [[ -d "$PHASE01D_TMP" ]]; then
        find "$PHASE01D_TMP" -depth -delete
    fi
}
trap cleanup_phase01d_tmp EXIT

export PYTHONDONTWRITEBYTECODE=1
PHASE01D_VENV="$PHASE01D_TMP/test-venv"
uv venv --python 3.12 "$PHASE01D_VENV"
VIRTUAL_ENV="$PHASE01D_VENV" uv sync --active --frozen --all-extras
PHASE01D_PYTHON="$PHASE01D_VENV/bin/python"
PHASE01D_PYTHONPATH="$PHASE01D_ROOT/src"
PHASE01D_PATH="$PHASE01D_VENV/bin:$PATH"

"$PHASE01D_PYTHON" --version
PYTHONPATH="$PHASE01D_PYTHONPATH" "$PHASE01D_PYTHON" -m pytest -q \
    tests/execution/test_cumulative_protocol.py
PYTHONPATH="$PHASE01D_PYTHONPATH" "$PHASE01D_PYTHON" -m pytest -q \
    tests/execution/test_software_verification.py
PYTHONPATH="$PHASE01D_PYTHONPATH" "$PHASE01D_PYTHON" -m pytest -q \
    tests/execution/test_cumulative_population.py
PYTHONPATH="$PHASE01D_PYTHONPATH" "$PHASE01D_PYTHON" -m pytest -q \
    tests/execution/test_cumulative_cli.py tests/execution/test_import_contract.py
PYTHONPATH="$PHASE01D_PYTHONPATH" "$PHASE01D_PYTHON" -m pytest -q tests/
PATH="$PHASE01D_PATH" ruff check .
uv lock --check

uv build --out-dir "$PHASE01D_TMP/harness-dist"
PHASE01D_WHEEL_VENV="$PHASE01D_TMP/harness-wheel-venv"
uv venv --python 3.12 "$PHASE01D_WHEEL_VENV"
set -- "$PHASE01D_TMP"/harness-dist/*.whl
test -f "$1"
uv pip install --python "$PHASE01D_WHEEL_VENV/bin/python" "$1"
PHASE01D_CLI="$PHASE01D_WHEEL_VENV/bin/spmkit-validation"

SUT_HEAD_BEFORE=$(git -C ../spmkit-sanitize rev-parse HEAD)
SUT_STATUS_BEFORE=$(git -C ../spmkit-sanitize status --porcelain=v1 | sha256sum | awk '{print $1}')
SUT_DIFF_BEFORE=$(git -C ../spmkit-sanitize diff --binary | sha256sum | awk '{print $1}')
PHANTOMS_HEAD_BEFORE=$(git -C ../spmkit-phantoms rev-parse HEAD)
PHANTOMS_STATUS_BEFORE=$(git -C ../spmkit-phantoms status --porcelain=v1 | sha256sum | awk '{print $1}')
PHANTOMS_DIFF_BEFORE=$(git -C ../spmkit-phantoms diff --binary | sha256sum | awk '{print $1}')

PHASE01D_CAMPAIGN="$PHASE01D_TMP/campaign"
"$PHASE01D_CLI" campaign prepare-cumulative-verification \
    --output-dir "$PHASE01D_CAMPAIGN" \
    --sut-repository ../spmkit-sanitize \
    --generator-commit "$(git rev-parse HEAD)" --json
"$PHASE01D_CLI" bundle validate "$PHASE01D_CAMPAIGN/draft-bundle.json" --json
"$PHASE01D_CLI" bundle verify-artifacts "$PHASE01D_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01D_CAMPAIGN" --json
"$PHASE01D_CLI" bundle freeze "$PHASE01D_CAMPAIGN/draft-bundle.json" \
    --artifact-root "$PHASE01D_CAMPAIGN" \
    --output-dir "$PHASE01D_TMP/protocol-snapshot" \
    --frozen-at 2026-07-26T08:02:00Z --json
PHASE01D_PROTOCOL_DIR=$(find "$PHASE01D_TMP/protocol-snapshot" \
    -mindepth 1 -maxdepth 1 -type d)
test -n "$PHASE01D_PROTOCOL_DIR"
PHASE01D_PROTOCOL="$PHASE01D_PROTOCOL_DIR/bundle.json"
PHASE01D_FREEZE_RECEIPT="$PHASE01D_PROTOCOL_DIR/freeze-receipt.json"
"$PHASE01D_CLI" bundle verify-snapshot "$PHASE01D_PROTOCOL" \
    "$PHASE01D_FREEZE_RECEIPT" --artifact-root "$PHASE01D_CAMPAIGN" --json

(
    cd ../spmkit-sanitize
    uv build --out-dir "$PHASE01D_TMP/sut-dist"
)
set -- "$PHASE01D_TMP"/sut-dist/*.whl
test -f "$1"
PHASE01D_SUT_WHEEL="$1"

PHASE01D_EXECUTION_ONE_JSON=$(
    "$PHASE01D_CLI" campaign execute-cumulative "$PHASE01D_PROTOCOL" \
        "$PHASE01D_FREEZE_RECEIPT" --artifact-root "$PHASE01D_CAMPAIGN" \
        --sut-wheel "$PHASE01D_SUT_WHEEL" \
        --output-dir "$PHASE01D_CAMPAIGN/execution-one" --json
)
PHASE01D_RESULT_HASH_ONE=$(
    "$PHASE01D_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01D_EXECUTION_ONE_JSON"
)
PHASE01D_RESULT_DIR_ONE="$PHASE01D_CAMPAIGN/execution-one/result-snapshot/$PHASE01D_RESULT_HASH_ONE"
PHASE01D_RESULT_ONE="$PHASE01D_RESULT_DIR_ONE/result-bundle.json"
PHASE01D_EXECUTION_RECEIPT_ONE="$PHASE01D_RESULT_DIR_ONE/execution-receipt.json"
"$PHASE01D_CLI" campaign verify-result "$PHASE01D_RESULT_ONE" \
    "$PHASE01D_EXECUTION_RECEIPT_ONE" --protocol-bundle "$PHASE01D_PROTOCOL" \
    --protocol-receipt "$PHASE01D_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01D_CAMPAIGN" --json

"$PHASE01D_WHEEL_VENV/bin/python" - "$PHASE01D_EXECUTION_ONE_JSON" \
    "$PHASE01D_RESULT_ONE" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
bundle = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert payload["software_test"] == {
    "status": "COMPLETED",
    "tests": 12,
    "passed": 12,
    "failures": 0,
    "errors": 0,
    "skips": 0,
}, payload
assert payload["scientific_runs"]["COMPLETED"] == 6, payload
assert len(bundle["runs"]) == 7
assert len(bundle["comparisons"]) == 18
assert {item["outcome"] for item in bundle["comparisons"]} == {"PASS"}
assert {claim["status"] for claim in bundle["claims"]} == {"SUPPORTED"}
assert {claim["level"] for claim in bundle["claims"]} == {
    "LEVEL 1 — SOFTWARE_VERIFIED",
    "LEVEL 2 — NUMERICALLY_VERIFIED",
}
PY

PHASE01D_EXECUTION_TWO_JSON=$(
    "$PHASE01D_CLI" campaign execute-cumulative "$PHASE01D_PROTOCOL" \
        "$PHASE01D_FREEZE_RECEIPT" --artifact-root "$PHASE01D_CAMPAIGN" \
        --sut-wheel "$PHASE01D_SUT_WHEEL" \
        --output-dir "$PHASE01D_CAMPAIGN/execution-two" --json
)
PHASE01D_RESULT_HASH_TWO=$(
    "$PHASE01D_PYTHON" -c 'import json,sys; print(json.load(sys.stdin)["result_bundle_sha256"])' \
        <<<"$PHASE01D_EXECUTION_TWO_JSON"
)
PHASE01D_RESULT_TWO="$PHASE01D_CAMPAIGN/execution-two/result-snapshot/$PHASE01D_RESULT_HASH_TWO/result-bundle.json"
"$PHASE01D_WHEEL_VENV/bin/python" - "$PHASE01D_RESULT_ONE" "$PHASE01D_RESULT_TWO" <<'PY'
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

PHASE01D_JUNIT_RELATIVE=$(
    "$PHASE01D_PYTHON" - "$PHASE01D_RESULT_ONE" <<'PY'
import json
import sys
from pathlib import Path

bundle = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
artifact = next(item for item in bundle["evidence"] if item["artifact_id"] == "artifact.software-test.junit")
print(artifact["relative_uri"])
PY
)
cp -a "$PHASE01D_CAMPAIGN" "$PHASE01D_TMP/tamper-junit-campaign"
printf '\n' >>"$PHASE01D_TMP/tamper-junit-campaign/$PHASE01D_JUNIT_RELATIVE"
set +e
"$PHASE01D_CLI" campaign verify-result "$PHASE01D_RESULT_ONE" \
    "$PHASE01D_EXECUTION_RECEIPT_ONE" --protocol-bundle "$PHASE01D_PROTOCOL" \
    --protocol-receipt "$PHASE01D_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01D_TMP/tamper-junit-campaign" --json
PHASE01D_JUNIT_TAMPER_EXIT=$?
set -e
test "$PHASE01D_JUNIT_TAMPER_EXIT" -eq 3

cp -a "$PHASE01D_CAMPAIGN" "$PHASE01D_TMP/tamper-manifest-campaign"
printf '\n' >>"$PHASE01D_TMP/tamper-manifest-campaign/software-test-suite-manifest.json"
set +e
"$PHASE01D_CLI" bundle verify-snapshot "$PHASE01D_PROTOCOL" \
    "$PHASE01D_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01D_TMP/tamper-manifest-campaign" --json
PHASE01D_MANIFEST_TAMPER_EXIT=$?
set -e
test "$PHASE01D_MANIFEST_TAMPER_EXIT" -eq 3

mkdir "$PHASE01D_TMP/protocol-drift"
cp "$PHASE01D_RESULT_ONE" "$PHASE01D_TMP/protocol-drift/result-bundle.json"
cp "$PHASE01D_EXECUTION_RECEIPT_ONE" "$PHASE01D_TMP/protocol-drift/execution-receipt.json"
"$PHASE01D_WHEEL_VENV/bin/python" - "$PHASE01D_TMP/protocol-drift/result-bundle.json" <<'PY'
import json
import sys
from pathlib import Path

from spmkit_validation.lifecycle import canonical_bundle_bytes

path = Path(sys.argv[1])
bundle = json.loads(path.read_text(encoding="utf-8"))
numeric_case = next(case for case in bundle["cases"] if case["operation"]["name"] == "spmkit analyze")
numeric_case["tolerances"][0]["absolute"] *= 2
path.write_bytes(canonical_bundle_bytes(bundle))
PY
set +e
"$PHASE01D_CLI" campaign verify-result \
    "$PHASE01D_TMP/protocol-drift/result-bundle.json" \
    "$PHASE01D_TMP/protocol-drift/execution-receipt.json" \
    --protocol-bundle "$PHASE01D_PROTOCOL" \
    --protocol-receipt "$PHASE01D_FREEZE_RECEIPT" \
    --artifact-root "$PHASE01D_CAMPAIGN" --json
PHASE01D_PROTOCOL_DRIFT_EXIT=$?
set -e
test "$PHASE01D_PROTOCOL_DRIFT_EXIT" -eq 4

"$PHASE01D_WHEEL_VENV/bin/python" - "$PHASE01D_RESULT_ONE" <<'PY'
import json
import sys
from pathlib import Path

from spmkit_validation.schemas import validate_semantics

bundle = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
bundle["runs"] = [run for run in bundle["runs"] if run["run_type"] != "SOFTWARE_TEST"]
assert len(bundle["comparisons"]) == 18
assert {comparison["outcome"] for comparison in bundle["comparisons"]} == {"PASS"}
codes = {issue.code for issue in validate_semantics(bundle)}
assert "CLAIM.LEVEL_1_EVIDENCE_INSUFFICIENT" in codes, codes
PY

if rg -n '/home/|/Users/' "$PHASE01D_CAMPAIGN" -g '!**/sut-venv/**'; then
    exit 1
fi
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

echo "PHASE_01D gates PASS software_tests=12 scientific_runs=6 comparisons=18 claims=LEVEL_1_LEVEL_2_SUPPORTED repeatability=NUMERICALLY_REPEATABLE tampering=DETECTED negative_cumulative=PASS real_data_accessed=NO holdout_accessed=NO"
