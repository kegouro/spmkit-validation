"""Pruebas para los modelos."""

from pathlib import Path

from spmkit_validation.models import RunRecord, Status, ValidationCase


def test_validation_case_creation():
    case = ValidationCase(
        case_id="TEST-01",
        input_path=Path("dummy.nid"),
        command="analyze"
    )
    assert case.case_id == "TEST-01"
    assert case.timeout_seconds == 30.0

def test_run_record_creation():
    record = RunRecord(
        case_id="TEST-01",
        started_at="now",
        finished_at="later",
        return_code=0,
        command=["spmkit", "analyze"],
        stdout_path=Path("out.txt"),
        stderr_path=Path("err.txt"),
        status=Status.PASS
    )
    assert record.status == Status.PASS
