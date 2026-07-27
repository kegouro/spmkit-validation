from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spmkit_validation.execution import (
    CampaignExecutionError,
    InstalledSUTEnvironment,
    execute_software_test,
    install_sut_wheel_environment,
    parse_junit_xml,
    prepare_cumulative_verification_campaign,
    validate_import_probe,
)
from spmkit_validation.execution import runner as runner_module
from spmkit_validation.execution.cumulative_protocol import SELECTED_SUITE_PATHS
from spmkit_validation.lifecycle import freeze_bundle

FREEZE_TIME = "2026-07-26T08:02:00Z"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _suite_repository(tmp_path: Path, *, failure: bool = False) -> tuple[Path, str]:
    repository = tmp_path / "sut"
    repository.mkdir()
    _git(repository, "init", "-q")
    sources = {
        "tests/__init__.py": "",
        "tests/conftest.py": "",
        "tests/core/__init__.py": "",
        "tests/core/test_roughness.py": "def test_roughness():\n    assert 1 + 1 == 2\n",
        "tests/core/test_export.py": "def test_export():\n    assert {'Sa': 1}['Sa'] == 1\n",
        "tests/core/test_npz.py": "def test_npz():\n    assert bytes([1, 2]) == b'\\x01\\x02'\n",
        "tests/core/test_manifest.py": (
            "def test_numpy_serialization():\n    assert True\n\n"
            "def test_invalid_input_error():\n"
            f"    assert {not failure!r}\n"
        ),
    }
    assert set(sources) == set(SELECTED_SUITE_PATHS)
    for relative_path, source in sources.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    _git(repository, "add", "tests")
    _git(
        repository,
        "-c",
        "user.name=Phase Test",
        "-c",
        "user.email=phase-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "selected suite",
    )
    return repository, _git(repository, "rev-parse", "HEAD")


def _fake_environment(tmp_path: Path, wheel: Path) -> InstalledSUTEnvironment:
    executable = tmp_path / "spmkit"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import sys\n"
        "if '--help' in sys.argv:\n"
        "    print('Usage: spmkit COMMAND\\n  analyze')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | 0o100)
    python = tmp_path / "python-wrapper"
    probe = {
        "probe_version": "0.1.0",
        "status": "PASS",
        "distribution_version": "0.1.5.dev0",
        "module_origin": "site-packages/spmkit/__init__.py",
        "resolved_inside_site_packages": True,
        "resolved_inside_source_checkout": False,
        "isolated_mode": True,
        "python_version": "3.12.0",
    }
    python.write_text(
        "#!/usr/bin/python3\n"
        "import json, os, sys\n"
        f"target = {sys.executable!r}\n"
        f"probe = {probe!r}\n"
        "if sys.argv[1:3] == ['-I', '-c']:\n"
        "    print(json.dumps(probe))\n"
        "    raise SystemExit(0)\n"
        "os.execv(target, [target, *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    python.chmod(python.stat().st_mode | 0o100)
    content = wheel.read_bytes()
    return InstalledSUTEnvironment(
        executable=executable,
        python_executable=python,
        wheel_sha256=hashlib.sha256(content).hexdigest(),
        wheel_size_bytes=len(content),
        installation="synthetic-test-environment",
        installed_dependencies=("pytest==9.1.1", "spmkit==0.1.5.dev0"),
    )


def _frozen(tmp_path: Path, *, failure: bool = False):
    repository, commit = _suite_repository(tmp_path, failure=failure)
    prepared = prepare_cumulative_verification_campaign(
        tmp_path / "campaign",
        sut_repository=repository,
        sut_commit=commit,
    )
    frozen = freeze_bundle(
        prepared.bundle_path,
        prepared.output_dir,
        tmp_path / "snapshots",
        frozen_at=FREEZE_TIME,
    )
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"synthetic wheel identity")
    environment = _fake_environment(tmp_path, wheel)
    return prepared, frozen, wheel, environment


def test_parse_valid_junit_from_testcases(tmp_path: Path) -> None:
    path = tmp_path / "junit.xml"
    path.write_text(
        '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="1">'
        '<testcase name="pass"/><testcase name="fail"><failure/></testcase>'
        '<testcase name="skip"><skipped/></testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    summary = parse_junit_xml(path)
    assert summary.to_dict() == {
        "tests": 3,
        "passed": 1,
        "failures": 1,
        "errors": 0,
        "skips": 1,
    }


def test_corrupt_or_contradictory_junit_is_rejected(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.xml"
    corrupt.write_text("<testsuite", encoding="utf-8")
    with pytest.raises(CampaignExecutionError):
        parse_junit_xml(corrupt)
    mismatch = tmp_path / "mismatch.xml"
    mismatch.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0">'
        '<testcase name="only"/></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(CampaignExecutionError):
        parse_junit_xml(mismatch)


def test_import_probe_requires_isolated_site_packages() -> None:
    valid = {
        "status": "PASS",
        "module_origin": "site-packages/spmkit/__init__.py",
        "resolved_inside_site_packages": True,
        "resolved_inside_source_checkout": False,
        "isolated_mode": True,
    }
    validate_import_probe(valid)
    checkout = dict(valid, module_origin="src/spmkit/__init__.py")
    checkout["resolved_inside_site_packages"] = False
    checkout["resolved_inside_source_checkout"] = True
    with pytest.raises(CampaignExecutionError):
        validate_import_probe(checkout)


def test_installed_environment_keeps_venv_python_entry_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"wheel")
    base_python = tmp_path / "base-python"
    base_python.write_bytes(b"python")

    def fake_run(command, **_kwargs):
        if command[1] == "venv":
            venv = Path(command[-1])
            (venv / "bin").mkdir(parents=True)
            (venv / "bin/python").symlink_to(base_python)
            executable = venv / "bin/spmkit"
            executable.write_bytes(b"#!/bin/sh\n")
            executable.chmod(0o755)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1:3] == ["pip", "install"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "-c":
            return subprocess.CompletedProcess(command, 0, "spmkit==0.1.5.dev0\n", "")
        raise AssertionError(command)

    monkeypatch.setattr(runner_module.shutil, "which", lambda _name: "/usr/bin/uv")
    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    environment = install_sut_wheel_environment(
        wheel, tmp_path / "execution", "0.1.5.dev0"
    )

    assert environment.python_executable == (
        tmp_path / "execution/sut-venv/bin/python"
    ).absolute()
    assert environment.python_executable != environment.python_executable.resolve()


def test_valid_software_test_runs_only_after_verified_freeze(tmp_path: Path) -> None:
    prepared, frozen, wheel, environment = _frozen(tmp_path)
    result = execute_software_test(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        installed_environment=environment,
        output_dir=prepared.output_dir / "execution/software-test",
    )

    assert result.run["run_type"] == "SOFTWARE_TEST"
    assert result.run["execution_status"] == "COMPLETED"
    assert result.run["errors"] == []
    assert result.junit_summary is not None
    assert result.junit_summary.tests == 5
    assert result.junit_summary.failures == 0
    assert result.import_probe["resolved_inside_site_packages"] is True
    assert result.cli_probe["status"] == "PASS"
    assert any(
        artifact["scientific_role"] == "SOFTWARE_TEST_RESULT"
        for artifact in result.evidence
    )


def test_junit_failure_preserves_error_software_run(tmp_path: Path) -> None:
    prepared, frozen, wheel, environment = _frozen(tmp_path, failure=True)
    result = execute_software_test(
        frozen.snapshot_path,
        frozen.receipt_path,
        artifact_root=prepared.output_dir,
        sut_wheel=wheel,
        installed_environment=environment,
        output_dir=prepared.output_dir / "execution/software-test",
    )

    assert result.run["execution_status"] == "ERROR"
    assert result.junit_summary is not None
    assert result.junit_summary.failures == 1
    assert any(error["code"] == "SOFTWARE_TEST_JUNIT_FAILURE" for error in result.run["errors"])


def test_draft_protocol_blocks_before_any_software_subprocess(tmp_path: Path) -> None:
    repository, commit = _suite_repository(tmp_path)
    prepared = prepare_cumulative_verification_campaign(
        tmp_path / "campaign", sut_repository=repository, sut_commit=commit
    )
    wheel = tmp_path / "spmkit.whl"
    wheel.write_bytes(b"wheel")
    environment = _fake_environment(tmp_path, wheel)
    before = os.stat(environment.executable).st_atime_ns
    with pytest.raises(CampaignExecutionError):
        execute_software_test(
            prepared.bundle_path,
            tmp_path / "missing-receipt.json",
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            installed_environment=environment,
            output_dir=prepared.output_dir / "execution/software-test",
        )
    assert not (prepared.output_dir / "execution").exists()
    assert os.stat(environment.executable).st_atime_ns == before


def test_installed_environment_wheel_mismatch_blocks(tmp_path: Path) -> None:
    prepared, frozen, wheel, environment = _frozen(tmp_path)
    mismatched = InstalledSUTEnvironment(
        executable=environment.executable,
        python_executable=environment.python_executable,
        wheel_sha256="0" * 64,
        wheel_size_bytes=environment.wheel_size_bytes,
        installation=environment.installation,
        installed_dependencies=environment.installed_dependencies,
    )
    with pytest.raises(CampaignExecutionError) as caught:
        execute_software_test(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            installed_environment=mismatched,
            output_dir=prepared.output_dir / "execution/software-test",
        )
    assert {issue.code for issue in caught.value.issues} == {
        "SOFTWARE_TEST.WHEEL_IDENTITY_MISMATCH"
    }


def test_tampered_frozen_suite_manifest_blocks_before_pytest(tmp_path: Path) -> None:
    prepared, frozen, wheel, environment = _frozen(tmp_path)
    prepared.suite_manifest_path.write_bytes(prepared.suite_manifest_path.read_bytes() + b"\n")
    with pytest.raises(CampaignExecutionError, match="PROTOCOL_NOT_VERIFIED"):
        execute_software_test(
            frozen.snapshot_path,
            frozen.receipt_path,
            artifact_root=prepared.output_dir,
            sut_wheel=wheel,
            installed_environment=environment,
            output_dir=prepared.output_dir / "execution/software-test",
        )
    assert not (prepared.output_dir / "execution").exists()


def test_fake_probe_payload_is_json_machine_readable(tmp_path: Path) -> None:
    wheel = tmp_path / "wheel.whl"
    wheel.write_bytes(b"wheel")
    environment = _fake_environment(tmp_path, wheel)
    completed = subprocess.run(
        [str(environment.python_executable), "-I", "-c", "ignored"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["status"] == "PASS"
    assert Path(sys.executable).is_file()
