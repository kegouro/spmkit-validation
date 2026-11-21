from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from spmkit_validation.adapters.gwyddion.viability import (
    BLOCKED_STATUS,
    run_viability_probe,
)


def _machine_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_gwyddion(directory: Path) -> Path:
    executable = directory / "gwyddion"
    executable.write_text(
        """#!/usr/bin/env python3
import sys

if sys.argv[1:] == [\"--version\"]:
    print(\"Gwyddion fake-version\")
    print(\"version diagnostic\", file=sys.stderr)
    raise SystemExit(0)
if sys.argv[1:] == [\"--help\"]:
    print(\"identity-only fake help\")
    print(\"help diagnostic\", file=sys.stderr)
    raise SystemExit(0)
raise SystemExit(64)
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def test_missing_gwyddion_produces_machine_readable_blocker(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()

    probe = run_viability_probe(output, search_path=str(empty_path))

    assert probe["status"] == BLOCKED_STATUS
    assert probe["authoritative_campaign_started"] is False
    assert probe["authoritative_gwyddion_runs"] == 0
    assert probe["reference_values_observed"] is False
    assert probe["tolerances_derived"] is False
    assert probe["spmkit_sut_imported"] is False
    assert probe["real_data_accessed"] is False
    assert probe["holdout_accessed"] is False
    assert probe["blocking_question_ids"] == [
        "Q1_OPEN_INPUT_NONINTERACTIVE",
        "Q2_COMPUTE_SA_SQ_SZ",
        "Q3_STRUCTURED_DETERMINISTIC_OUTPUT",
        "Q4_EXPLICIT_PREPROCESSING",
        "Q5_EXACT_VERSION",
    ]
    assert _machine_json(output / "viability-probe.json") == probe
    blocker = _machine_json(output / "blocker.json")
    assert blocker["status"] == BLOCKED_STATUS
    assert blocker["level_3_claimed"] is False
    assert blocker["claims_promoted"] == []
    identity = _machine_json(output / "gwyddion-identity.json")
    assert identity["identity_status"] == "NOT_FOUND"
    assert identity["executable_sha256"] is None


def test_identity_probe_uses_tokenized_process_and_preserves_streams(tmp_path: Path) -> None:
    executable = _fake_gwyddion(tmp_path)
    output = tmp_path / "evidence"

    probe = run_viability_probe(
        output,
        candidate_names=("gwyddion",),
        search_path=str(tmp_path),
    )

    assert probe["status"] == BLOCKED_STATUS
    assert probe["blocking_question_ids"] == [
        "Q1_OPEN_INPUT_NONINTERACTIVE",
        "Q2_COMPUTE_SA_SQ_SZ",
        "Q3_STRUCTURED_DETERMINISTIC_OUTPUT",
        "Q4_EXPLICIT_PREPROCESSING",
    ]
    candidate = probe["candidate_inventory"][0]
    assert candidate["executable_sha256"]
    assert candidate["executable_size_bytes"] == executable.stat().st_size
    assert candidate["version_probe"]["argv"] == ["gwyddion", "--version"]
    assert candidate["version_probe"]["exit_code"] == 0
    assert candidate["version_probe"]["display_environment_present"] is False
    assert (output / candidate["version_probe"]["stdout_artifact"]).read_text() == (
        "Gwyddion fake-version\n"
    )
    assert (output / candidate["version_probe"]["stderr_artifact"]).read_text() == (
        "version diagnostic\n"
    )
    assert (output / candidate["help_probe"]["stdout_artifact"]).read_text() == (
        "identity-only fake help\n"
    )
    assert (output / candidate["help_probe"]["stderr_artifact"]).read_text() == (
        "help diagnostic\n"
    )


def test_versioned_probe_omits_absolute_paths(tmp_path: Path) -> None:
    _fake_gwyddion(tmp_path)
    output = tmp_path / "evidence"

    run_viability_probe(
        output,
        candidate_names=("gwyddion",),
        search_path=str(tmp_path),
    )

    for path in output.rglob("*.json"):
        content = path.read_text(encoding="utf-8")
        assert str(tmp_path) not in content
        assert '"path_disclosure":"OMITTED_FROM_VERSIONED_EVIDENCE"' in content or (
            path.name != "viability-probe.json"
        )


def test_probe_does_not_import_spmkit_sut(tmp_path: Path) -> None:
    before = set(sys.modules)

    run_viability_probe(tmp_path / "evidence", search_path=str(tmp_path))

    newly_imported = set(sys.modules) - before
    assert "spmkit" not in newly_imported
