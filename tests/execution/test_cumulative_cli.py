from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spmkit_validation.cli import EXIT_PASS, main

from .test_cumulative_population import _populated
from .test_software_verification import _suite_repository


def test_cli_prepares_cumulative_protocol_as_json(tmp_path: Path, capsys: Any) -> None:
    repository, commit = _suite_repository(tmp_path)
    campaign = tmp_path / "campaign"
    code = main(
        [
            "campaign",
            "prepare-cumulative-verification",
            "--output-dir",
            str(campaign),
            "--sut-repository",
            str(repository),
            "--sut-commit",
            commit,
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == EXIT_PASS
    assert payload["status"] == "DRAFT_PREPARED"
    assert payload["case_count"] == 7
    assert payload["scientific_case_count"] == 6
    assert "Traceback" not in captured.out + captured.err


def test_cli_cumulative_execution_is_blocked_without_freeze(
    tmp_path: Path, capsys: Any
) -> None:
    repository, commit = _suite_repository(tmp_path)
    campaign = tmp_path / "campaign"
    assert (
        main(
            [
                "campaign",
                "prepare-cumulative-verification",
                "--output-dir",
                str(campaign),
                "--sut-repository",
                str(repository),
                "--sut-commit",
                commit,
            ]
        )
        == EXIT_PASS
    )
    capsys.readouterr()
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"wheel")
    code = main(
        [
            "campaign",
            "execute-cumulative",
            str(campaign / "draft-bundle.json"),
            str(tmp_path / "missing-receipt.json"),
            "--artifact-root",
            str(campaign),
            "--sut-wheel",
            str(wheel),
            "--output-dir",
            str(campaign / "execution"),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code != EXIT_PASS
    assert json.loads(captured.out)["status"] == "INVALID"
    assert "Traceback" not in captured.out + captured.err
    assert not (campaign / "execution").exists()


def test_cli_cumulative_execute_publishes_machine_result(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    prepared, frozen, cumulative, _ = _populated(tmp_path)
    monkeypatch.setattr(
        "spmkit_validation.cli.execute_cumulative_campaign",
        lambda *args, **kwargs: cumulative,
    )
    wheel = tmp_path / "declared.whl"
    wheel.write_bytes(b"wheel")
    output = prepared.output_dir / "cli-publication"
    code = main(
        [
            "campaign",
            "execute-cumulative",
            str(frozen.snapshot_path),
            str(frozen.receipt_path),
            "--artifact-root",
            str(prepared.output_dir),
            "--sut-wheel",
            str(wheel),
            "--output-dir",
            str(output),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == EXIT_PASS
    assert payload["status"] == "RESULT_PUBLISHED"
    assert payload["software_test"] == {
        "status": "COMPLETED",
        "tests": 5,
        "passed": 5,
        "failures": 0,
        "errors": 0,
        "skips": 0,
    }
    assert payload["scientific_runs"]["COMPLETED"] == 6
    assert payload["comparisons"] == 18
    assert {claim["status"] for claim in payload["claims"]} == {"SUPPORTED"}
    assert "Traceback" not in captured.out + captured.err
