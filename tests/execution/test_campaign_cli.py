from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spmkit_validation.cli import (
    EXIT_PASS,
    EXIT_TAMPERING,
    main,
)
from spmkit_validation.lifecycle import freeze_bundle

from .conftest import FREEZE_TIME, write_fake_spmkit


def _cli_workflow(tmp_path: Path, capsys: Any):
    campaign = tmp_path / "campaign"
    assert (
        main(
            [
                "campaign",
                "prepare-synthetic-roughness",
                "--output-dir",
                str(campaign),
                "--json",
            ]
        )
        == EXIT_PASS
    )
    prepare_payload = json.loads(capsys.readouterr().out)
    assert prepare_payload["status"] == "DRAFT_PREPARED"
    frozen = freeze_bundle(
        campaign / "draft-bundle.json",
        campaign,
        tmp_path / "protocol-snapshot",
        frozen_at=FREEZE_TIME,
    )
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"wheel fixture")
    executable = write_fake_spmkit(tmp_path / "spmkit")
    execution_dir = campaign / "execution"
    assert (
        main(
            [
                "campaign",
                "execute",
                str(frozen.snapshot_path),
                str(frozen.receipt_path),
                "--artifact-root",
                str(campaign),
                "--sut-wheel",
                str(wheel),
                "--output-dir",
                str(execution_dir),
                "--sut-executable",
                str(executable),
                "--json",
            ]
        )
        == EXIT_PASS
    )
    payload = json.loads(capsys.readouterr().out)
    result_dir = execution_dir / "result-snapshot" / payload["result_bundle_sha256"]
    return campaign, frozen, payload, result_dir


def test_cli_prepare_execute_and_verify_json(tmp_path: Path, capsys: Any) -> None:
    campaign, frozen, payload, result_dir = _cli_workflow(tmp_path, capsys)
    assert payload["runs"]["COMPLETED"] == 6
    assert payload["comparisons"] == 18
    code = main(
        [
            "campaign",
            "verify-result",
            str(result_dir / "result-bundle.json"),
            str(result_dir / "execution-receipt.json"),
            "--protocol-bundle",
            str(frozen.snapshot_path),
            "--protocol-receipt",
            str(frozen.receipt_path),
            "--artifact-root",
            str(campaign),
            "--json",
        ]
    )
    assert code == EXIT_PASS
    verification = json.loads(capsys.readouterr().out)
    assert verification["status"] == "RESULT_SNAPSHOT_VALID"


def test_cli_execution_is_blocked_without_valid_freeze(
    tmp_path: Path, capsys: Any
) -> None:
    campaign = tmp_path / "campaign"
    assert main(["campaign", "prepare-synthetic-roughness", "--output-dir", str(campaign)]) == 0
    capsys.readouterr()
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel")
    executable = write_fake_spmkit(tmp_path / "spmkit")
    code = main(
        [
            "campaign",
            "execute",
            str(campaign / "draft-bundle.json"),
            str(tmp_path / "missing-receipt.json"),
            "--artifact-root",
            str(campaign),
            "--sut-wheel",
            str(wheel),
            "--output-dir",
            str(campaign / "execution"),
            "--sut-executable",
            str(executable),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code != EXIT_PASS
    assert "Traceback" not in captured.out + captured.err
    assert json.loads(captured.out)["status"] == "INVALID"


def test_cli_result_tampering_exit_code(tmp_path: Path, capsys: Any) -> None:
    campaign, frozen, _, result_dir = _cli_workflow(tmp_path, capsys)
    result_path = result_dir / "result-bundle.json"
    result_path.write_bytes(result_path.read_bytes() + b"\n")
    code = main(
        [
            "campaign",
            "verify-result",
            str(result_path),
            str(result_dir / "execution-receipt.json"),
            "--protocol-bundle",
            str(frozen.snapshot_path),
            "--protocol-receipt",
            str(frozen.receipt_path),
            "--artifact-root",
            str(campaign),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == EXIT_TAMPERING
    assert json.loads(captured.out)["status"] == "RESULT_NONCANONICAL"
    assert "Traceback" not in captured.out + captured.err
