"""Pruebas para el runner de subprocess."""

import sys
from pathlib import Path

from spmkit_validation.models import Status, ValidationCase
from spmkit_validation.runner import run_case


def test_runner_success(tmp_path: Path):
    case = ValidationCase(
        case_id="SUCCESS-01",
        input_path=Path("dummy.nid"),
        command="-c",
        arguments=["print('hello world')"]
    )
    
    # Run with current Python executable as dummy target
    record = run_case(case, sys.executable, tmp_path)
    
    assert record.return_code == 0
    assert record.status == Status.PASS
    assert "hello world" in record.stdout_path.read_text()

def test_runner_error(tmp_path: Path):
    case = ValidationCase(
        case_id="ERR-01",
        input_path=Path("dummy.nid"),
        command="-c",
        arguments=["import sys; sys.exit(1)"]
    )
    
    record = run_case(case, sys.executable, tmp_path)
    
    assert record.return_code == 1
    assert record.status == Status.FAIL

def test_runner_timeout(tmp_path: Path):
    case = ValidationCase(
        case_id="TIME-01",
        input_path=Path("dummy.nid"),
        command="-c",
        arguments=["import time; time.sleep(2)"],
        timeout_seconds=0.1
    )
    
    record = run_case(case, sys.executable, tmp_path)
    
    assert record.status == Status.TIMEOUT
