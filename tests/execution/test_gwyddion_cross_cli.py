from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from spmkit_validation.cli import EXIT_PASS, main
from spmkit_validation.execution import (
    execute_gwyddion_cross_validation_campaign,
    populate_gwyddion_cross_validation_result_bundle,
    prepare_gwyddion_cross_validation_campaign,
)

from .test_gwyddion_cross_validation import _cross_populated


def test_public_import_contract_exposes_cross_validation_workflow() -> None:
    assert callable(prepare_gwyddion_cross_validation_campaign)
    assert callable(execute_gwyddion_cross_validation_campaign)
    assert callable(populate_gwyddion_cross_validation_result_bundle)


def test_cli_prepares_cross_protocol_as_json(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    captured_arguments = {}

    def fake_prepare(output_dir, **kwargs):
        captured_arguments.update({"output_dir": output_dir, **kwargs})
        return SimpleNamespace(
            to_dict=lambda: {
                "campaign_id": "campaign.gwyddion-cross-validation.synthetic-roughness.v0.1",
                "status": "DRAFT",
                "bundle_path": "draft-bundle.json",
                "case_count": 7,
                "software_case_count": 1,
                "scientific_case_count": 6,
                "external_reference_id": "reference.external.gwyddion-library.roughness",
                "gwyddion_version": "2.71",
            }
        )

    monkeypatch.setattr(
        "spmkit_validation.cli.prepare_gwyddion_cross_validation_campaign", fake_prepare
    )
    names = ("identity", "viability", "source", "helper", "build", "wheel")
    paths = [tmp_path / name for name in names]
    code = main(
        [
            "campaign",
            "prepare-gwyddion-cross-validation",
            "--output-dir",
            str(tmp_path / "campaign"),
            "--sut-repository",
            str(tmp_path / "sut"),
            "--gwyddion-identity",
            str(paths[0]),
            "--installed-viability",
            str(paths[1]),
            "--helper-source",
            str(paths[2]),
            "--helper-binary",
            str(paths[3]),
            "--helper-build-record",
            str(paths[4]),
            "--gwyfile-wheel",
            str(paths[5]),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == EXIT_PASS
    assert output["status"] == "DRAFT_PREPARED"
    assert output["case_count"] == 7
    assert captured_arguments["gwyddion_identity"] == paths[0]


def test_cli_cross_execution_is_blocked_without_freeze(tmp_path: Path, capsys) -> None:
    draft = tmp_path / "draft.json"
    draft.write_text("{}", encoding="utf-8")
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel")
    helper = tmp_path / "helper"
    helper.write_bytes(b"helper")
    library = tmp_path / "lib"
    modules = tmp_path / "modules"
    library.mkdir()
    modules.mkdir()

    code = main(
        [
            "campaign",
            "execute-gwyddion-cross-validation",
            str(draft),
            str(tmp_path / "missing-receipt.json"),
            "--artifact-root",
            str(tmp_path),
            "--sut-wheel",
            str(wheel),
            "--gwyddion-command",
            str(helper),
            "--gwyddion-library-dir",
            str(library),
            "--gwyddion-module-dir",
            str(modules),
            "--output-dir",
            str(tmp_path / "execution"),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code != EXIT_PASS
    assert output["status"] == "INVALID"
    assert not (tmp_path / "execution").exists()


def test_cli_cross_execution_publishes_machine_result(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    prepared, frozen, execution, _ = _cross_populated(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "spmkit_validation.cli.execute_gwyddion_cross_validation_campaign",
        lambda *args, **kwargs: execution,
    )
    wheel = tmp_path / "declared.whl"
    wheel.write_bytes(b"declared")
    helper = tmp_path / "declared-helper"
    helper.write_bytes(b"helper")
    library = tmp_path / "declared-lib"
    modules = tmp_path / "declared-modules"
    library.mkdir()
    modules.mkdir()

    code = main(
        [
            "campaign",
            "execute-gwyddion-cross-validation",
            str(frozen.snapshot_path),
            str(frozen.receipt_path),
            "--artifact-root",
            str(prepared.output_dir),
            "--sut-wheel",
            str(wheel),
            "--gwyddion-command",
            str(helper),
            "--gwyddion-library-dir",
            str(library),
            "--gwyddion-module-dir",
            str(modules),
            "--output-dir",
            str(prepared.output_dir / "cli-publication"),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == EXIT_PASS
    assert output["status"] == "RESULT_PUBLISHED"
    assert output["spmkit_runs"] == 6
    assert output["external_reference_runs"] == 6
    assert output["cross_comparisons"]["PASS"] == 18
    assert {item["status"] for item in output["claims"]} == {"SUPPORTED"}
