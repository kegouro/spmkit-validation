from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from spmkit_validation import dataset_classifier


EXPECTED_OUTPUTS = {
    "CLASSIFICATION_REPORT.md",
    "DUPLICATES.md",
    "HUMAN_REVIEW_QUEUE.md",
    "VALIDATION_MATRIX.csv",
    "VALIDATION_MATRIX.jsonl",
    "duplicate_datasets.csv",
    "duplicate_files.csv",
    "file_inventory.csv",
    "file_inventory.jsonl",
    "spmkit_probe_results.csv",
    "spmkit_probe_results.jsonl",
}
PROBE_FIELDS = {
    "dataset_id",
    "relative_path",
    "command",
    "exit_code",
    "timed_out",
    "runtime_seconds",
    "success",
    "stdout",
    "stderr",
}


def make_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "datasets"
    dataset = root / "sample"
    dataset.mkdir(parents=True)
    (dataset / "height.csv").write_text("0,1\n2,3\n4,5\n6,7\n8,9\n", encoding="utf-8")
    (dataset / "notes.md").write_text("AFM height units: nm\n", encoding="utf-8")
    (dataset / "sample.nid").write_bytes(b"not a real instrument file")
    return root, dataset


def run_classifier(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    output: Path | None = None,
    *extra: str,
) -> int:
    argv = ["spmkit-validation-classify", str(root)]
    if output is not None:
        argv.extend(("--output", str(output)))
    argv.extend(extra)
    monkeypatch.setattr(sys, "argv", argv)
    return dataset_classifier.main()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def assert_valid_inventory(output: Path, dataset: Path) -> None:
    inventory_csv = read_csv(output / "file_inventory.csv")
    inventory_jsonl = read_jsonl(output / "file_inventory.jsonl")
    matrix_csv = read_csv(output / "VALIDATION_MATRIX.csv")
    matrix_jsonl = read_jsonl(output / "VALIDATION_MATRIX.jsonl")

    assert {row["name"] for row in inventory_csv} == {"height.csv", "notes.md", "sample.nid"}
    assert len(inventory_jsonl) == len(inventory_csv) == 3
    assert all(Path(row["absolute_path"]).is_absolute() for row in inventory_csv)
    assert {row["dataset_path"] for row in inventory_csv} == {str(dataset.resolve())}

    assert len(matrix_csv) == len(matrix_jsonl) == 1
    assert matrix_csv[0]["dataset_id"] == matrix_jsonl[0]["dataset_id"] == "sample"
    assert matrix_csv[0]["local_path"] == matrix_jsonl[0]["local_path"] == str(dataset.resolve())
    assert matrix_csv[0]["file_count"] == str(len(inventory_csv))


def test_inventory_defaults_and_output_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, dataset = make_fixture(tmp_path)
    output = root.parent / "validation" / "triage"

    assert run_classifier(monkeypatch, root) == 0
    assert {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()} == EXPECTED_OUTPUTS
    assert_valid_inventory(output, dataset)
    assert read_csv(output / "duplicate_files.csv") == []
    assert read_csv(output / "duplicate_datasets.csv") == []
    assert read_jsonl(output / "spmkit_probe_results.jsonl") == []
    assert read_csv(output / "spmkit_probe_results.csv") == []
    for name in ("CLASSIFICATION_REPORT.md", "DUPLICATES.md", "HUMAN_REVIEW_QUEUE.md"):
        assert (output / name).read_text(encoding="utf-8").strip()


def test_output_guards_reject_root_and_nested_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _dataset = make_fixture(tmp_path)

    assert run_classifier(monkeypatch, root, root) == 2
    assert "output must be outside the immutable dataset root" in capsys.readouterr().err

    nested = root / "nested-output"
    assert run_classifier(monkeypatch, root, nested) == 2
    assert "output must be outside the immutable dataset root" in capsys.readouterr().err


def test_probe_absent_and_failed_preserve_structured_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, dataset = make_fixture(tmp_path)

    absent_output = tmp_path / "absent-probe"
    assert run_classifier(
        monkeypatch, root, absent_output, "--probe-spmkit", "--spmkit-command", "missing-spmkit"
    ) == 0
    assert_valid_inventory(absent_output, dataset)
    assert read_csv(absent_output / "spmkit_probe_results.csv") == []
    assert read_jsonl(absent_output / "spmkit_probe_results.jsonl") == []

    failing_probe = tmp_path / "failing-spmkit"
    failing_probe.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    failing_probe.chmod(0o755)
    failed_output = tmp_path / "failed-probe"
    assert run_classifier(
        monkeypatch, root, failed_output, "--probe-spmkit", "--spmkit-command", str(failing_probe)
    ) == 0
    assert_valid_inventory(failed_output, dataset)

    csv_rows = read_csv(failed_output / "spmkit_probe_results.csv")
    json_rows = read_jsonl(failed_output / "spmkit_probe_results.jsonl")
    assert set(csv_rows[0]) == PROBE_FIELDS
    assert set(json_rows[0]) == PROBE_FIELDS
    assert len(csv_rows) == len(json_rows) == 1
    assert csv_rows[0]["dataset_id"] == json_rows[0]["dataset_id"] == "sample"
    assert csv_rows[0]["relative_path"] == json_rows[0]["relative_path"] == "sample.nid"
    assert csv_rows[0]["exit_code"] == "7"
    assert json_rows[0]["exit_code"] == 7
    assert csv_rows[0]["timed_out"] == "False"
    assert json_rows[0]["timed_out"] is False
    assert csv_rows[0]["success"] == "False"
    assert json_rows[0]["success"] is False
    assert csv_rows[0]["stdout"] == json_rows[0]["stdout"] == ""
    assert csv_rows[0]["stderr"] == json_rows[0]["stderr"] == ""
    assert float(csv_rows[0]["runtime_seconds"]) >= 0
    assert isinstance(json_rows[0]["runtime_seconds"], float)
