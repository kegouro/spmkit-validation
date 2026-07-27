from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spmkit_validation.execution import CampaignExecutionError, execute_frozen_campaign

from .conftest import write_fake_spmkit


def _execute(frozen_protocol: Any, tmp_path: Path, *, mode: str = "success"):
    prepared, frozen = frozen_protocol
    executable = write_fake_spmkit(tmp_path / f"fake-spmkit-{mode}", mode=mode)
    wheel = tmp_path / "spmkit-0.1.5.dev0-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel fixture")
    return execute_frozen_campaign(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        output_dir=prepared.output_dir / "execution",
        sut_executable=executable,
        timeout_seconds=0.05 if mode == "timeout" else 5,
    )


def test_black_box_runner_executes_six_cases_from_json(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    result = _execute(frozen_protocol, tmp_path)
    assert len(result.runs) == 6
    assert {run["execution_status"] for run in result.runs} == {"COMPLETED"}
    assert len(result.observations) == 6
    assert all(run["command"][0] == "spmkit" for run in result.runs)
    assert all("--level" in run["command"] for run in result.runs)
    assert all(run["parameters"]["exit_code"] == 0 for run in result.runs)
    assert result.observations["case.synthetic.flat.16x16"] == {
        "Sa": 0.0,
        "Sq": 0.0,
        "Sz": 0.0,
    }


def test_machine_json_not_human_stdout_is_authoritative(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    result = _execute(frozen_protocol, tmp_path)
    assert all(values["Sa"] != 999 for values in result.observations.values())


def test_sut_failure_preserves_six_error_runs(frozen_protocol: Any, tmp_path: Path) -> None:
    result = _execute(frozen_protocol, tmp_path, mode="failure")
    assert len(result.runs) == 6
    assert {run["execution_status"] for run in result.runs} == {"ERROR"}
    assert {run["parameters"]["exit_code"] for run in result.runs} == {9}
    assert result.observations == {}


def test_timeout_preserves_error_without_observation(
    frozen_protocol: Any, tmp_path: Path
) -> None:
    result = _execute(frozen_protocol, tmp_path, mode="timeout")
    assert len(result.runs) == 6
    assert {run["execution_status"] for run in result.runs} == {"ERROR"}
    assert all(run["errors"][0]["code"] == "SUT_TIMEOUT" for run in result.runs)
    assert result.observations == {}


def test_invalid_receipt_blocks_before_any_subprocess(
    frozen_protocol: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared, frozen = frozen_protocol
    frozen.receipt_path.write_bytes(frozen.receipt_path.read_bytes() + b"\n")
    called = False

    def forbidden(*args: Any, **kwargs: Any) -> None:
        nonlocal called
        called = True
        raise AssertionError("subprocess was reached")

    monkeypatch.setattr("spmkit_validation.execution.runner.subprocess.run", forbidden)
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel")
    with pytest.raises(CampaignExecutionError, match="PROTOCOL_NOT_VERIFIED"):
        execute_frozen_campaign(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            output_dir=prepared.output_dir / "execution",
            sut_executable=tmp_path / "unused",
        )
    assert called is False


def test_artifact_mismatch_blocks_before_run(frozen_protocol: Any, tmp_path: Path) -> None:
    prepared, frozen = frozen_protocol
    input_path = next((prepared.output_dir / "inputs").glob("*.npz"))
    input_path.write_bytes(input_path.read_bytes() + b"tampered")
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel")
    with pytest.raises(CampaignExecutionError, match="PROTOCOL_NOT_VERIFIED"):
        execute_frozen_campaign(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            output_dir=prepared.output_dir / "execution",
            sut_executable=tmp_path / "unused",
        )


def test_draft_protocol_cannot_execute(tmp_path: Path) -> None:
    wheel = tmp_path / "sut.whl"
    wheel.write_bytes(b"wheel")
    draft = tmp_path / "draft.json"
    receipt = tmp_path / "receipt.json"
    draft.write_text("{}", encoding="utf-8")
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(CampaignExecutionError, match="PROTOCOL_NOT_VERIFIED"):
        execute_frozen_campaign(
            draft,
            receipt,
            artifact_root=tmp_path,
            sut_wheel=wheel,
            output_dir=tmp_path / "execution",
            sut_executable=tmp_path / "unused",
        )


def test_runmanifest_remains_external(frozen_protocol: Any, tmp_path: Path) -> None:
    result = _execute(frozen_protocol, tmp_path)
    manifests = [item for item in result.evidence if item["artifact_type"] == "MANIFEST"]
    assert len(manifests) == 6
    assert all(
        item["external_schema"]
        == {"name": "spmkit.core.export.RunManifest", "version": "1.0"}
        for item in manifests
    )
