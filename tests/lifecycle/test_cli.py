from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spmkit_validation.cli import (
    EXIT_ARTIFACT,
    EXIT_FILESYSTEM,
    EXIT_INCOMPLETE,
    EXIT_INVALID,
    EXIT_PASS,
    EXIT_TAMPERING,
    main,
)
from spmkit_validation.lifecycle import freeze_bundle

from .conftest import FREEZE_TIME, write_bundle


def test_cli_validate_passes(draft_bundle_path: Path, capsys: Any) -> None:
    assert main(["bundle", "validate", str(draft_bundle_path)]) == EXIT_PASS
    captured = capsys.readouterr()
    assert captured.out.startswith("VALID ")
    assert captured.err == ""


def test_cli_validate_fails_without_traceback(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    capsys: Any,
) -> None:
    draft_bundle["schema_version"] = "9.9.9"
    write_bundle(draft_bundle_path, draft_bundle)
    assert main(["bundle", "validate", str(draft_bundle_path)]) == EXIT_INVALID
    captured = capsys.readouterr()
    assert "INVALID" in captured.out
    assert "SCHEMA.VERSION_INCOMPATIBLE" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_cli_verify_artifacts_passes(
    draft_bundle_path: Path, artifact_root: Path, capsys: Any
) -> None:
    code = main(
        [
            "bundle",
            "verify-artifacts",
            str(draft_bundle_path),
            "--artifact-root",
            str(artifact_root),
        ]
    )
    assert code == EXIT_PASS
    assert capsys.readouterr().out.startswith("PASS ")


def test_cli_verify_artifacts_mismatch_exit_code(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    capsys: Any,
) -> None:
    draft_bundle["evidence"][0]["sha256"] = "0" * 64
    write_bundle(draft_bundle_path, draft_bundle)
    code = main(
        [
            "bundle",
            "verify-artifacts",
            str(draft_bundle_path),
            "--artifact-root",
            str(artifact_root),
        ]
    )
    assert code == EXIT_ARTIFACT
    assert capsys.readouterr().out.startswith("FAIL ")


def test_cli_remote_artifact_is_incomplete_exit_code(
    draft_bundle: dict[str, Any],
    draft_bundle_path: Path,
    artifact_root: Path,
    capsys: Any,
) -> None:
    draft_bundle["evidence"][0]["relative_uri"] = "urn:synthetic:artifact:remote"
    write_bundle(draft_bundle_path, draft_bundle)
    code = main(
        [
            "bundle",
            "verify-artifacts",
            str(draft_bundle_path),
            "--artifact-root",
            str(artifact_root),
        ]
    )
    assert code == EXIT_INCOMPLETE
    assert capsys.readouterr().out.startswith("INCOMPLETE ")


def test_cli_freeze_passes(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path, capsys: Any
) -> None:
    code = main(
        [
            "bundle",
            "freeze",
            str(draft_bundle_path),
            "--artifact-root",
            str(artifact_root),
            "--output-dir",
            str(tmp_path / "snapshots"),
            "--frozen-at",
            FREEZE_TIME,
        ]
    )
    assert code == EXIT_PASS
    assert capsys.readouterr().out.startswith("FROZEN sha256=")


def test_cli_freeze_never_overwrites(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path, capsys: Any
) -> None:
    command = [
        "bundle",
        "freeze",
        str(draft_bundle_path),
        "--artifact-root",
        str(artifact_root),
        "--output-dir",
        str(tmp_path / "snapshots"),
        "--frozen-at",
        FREEZE_TIME,
    ]
    assert main(command) == EXIT_PASS
    capsys.readouterr()
    assert main(command) == EXIT_FILESYSTEM
    captured = capsys.readouterr()
    assert "FREEZE.OUTPUT_EXISTS" in captured.err
    assert "Traceback" not in captured.err


def test_cli_verify_snapshot_passes(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path, capsys: Any
) -> None:
    result = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    code = main(
        [
            "bundle",
            "verify-snapshot",
            str(result.snapshot_path),
            str(result.receipt_path),
            "--artifact-root",
            str(artifact_root),
        ]
    )
    assert code == EXIT_PASS
    assert capsys.readouterr().out.startswith("SNAPSHOT_VALID ")


def test_cli_verify_snapshot_tampering_exit_code(
    draft_bundle_path: Path, artifact_root: Path, tmp_path: Path, capsys: Any
) -> None:
    result = freeze_bundle(draft_bundle_path, artifact_root, tmp_path / "snapshots", FREEZE_TIME)
    result.snapshot_path.write_bytes(result.snapshot_path.read_bytes() + b"\n")
    code = main(
        [
            "bundle",
            "verify-snapshot",
            str(result.snapshot_path),
            str(result.receipt_path),
        ]
    )
    assert code == EXIT_TAMPERING
    captured = capsys.readouterr()
    assert "SNAPSHOT_NONCANONICAL" in captured.out
    assert "Traceback" not in captured.out + captured.err


def test_cli_json_output_is_parseable(draft_bundle_path: Path, capsys: Any) -> None:
    assert main(["bundle", "validate", str(draft_bundle_path), "--json"]) == EXIT_PASS
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "bundle.validate"
    assert payload["status"] == "VALID"


def test_cli_invalid_json_exit_code(draft_bundle_path: Path, capsys: Any) -> None:
    draft_bundle_path.write_text("{invalid\n", encoding="utf-8")
    assert main(["bundle", "validate", str(draft_bundle_path), "--json"]) == EXIT_INVALID
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "INVALID"
    assert payload["issues"][0]["category"] == "IO"


def test_legacy_run_placeholder_remains_available(capsys: Any) -> None:
    assert main(["--run"]) == EXIT_PASS
    assert "would run here" in capsys.readouterr().out
