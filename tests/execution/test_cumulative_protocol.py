from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

from spmkit_validation.execution import (
    CUMULATIVE_CAMPAIGN_ID,
    SOFTWARE_CASE_ID,
    export_software_test_suite,
    prepare_cumulative_verification_campaign,
)
from spmkit_validation.execution.cumulative_protocol import SELECTED_SUITE_PATHS
from spmkit_validation.lifecycle import verify_artifacts
from spmkit_validation.schemas import assert_valid_bundle


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _sut_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "sut"
    repository.mkdir()
    _git(repository, "init", "-q")
    for index, relative_path in enumerate(SELECTED_SUITE_PATHS):
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# selected source {index}: {relative_path}\n", encoding="utf-8")
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
        "selected tests",
    )
    return repository, _git(repository, "rev-parse", "HEAD")


def test_exact_suite_export_records_git_and_content_identity(tmp_path: Path) -> None:
    repository, commit = _sut_repository(tmp_path)
    archive, manifest = export_software_test_suite(repository, commit)

    assert manifest["sut_commit"] == commit
    assert [record["path"] for record in manifest["files"]] == list(SELECTED_SUITE_PATHS)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as source:
        members = sorted(member.name for member in source.getmembers() if member.isfile())
        assert members == list(SELECTED_SUITE_PATHS)
        for record in manifest["files"]:
            extracted = source.extractfile(record["path"])
            assert extracted is not None
            content = extracted.read()
            assert hashlib.sha256(content).hexdigest() == record["sha256"]
            assert len(content) == record["size_bytes"]
            assert _git(repository, "rev-parse", f"{commit}:{record['path']}") == record[
                "git_blob"
            ]


def test_cumulative_draft_has_one_software_and_six_scientific_cases(
    tmp_path: Path,
) -> None:
    repository, commit = _sut_repository(tmp_path)
    prepared = prepare_cumulative_verification_campaign(
        tmp_path / "campaign",
        sut_repository=repository,
        sut_commit=commit,
    )

    assert_valid_bundle(prepared.bundle)
    assert prepared.bundle["campaign"]["campaign_id"] == CUMULATIVE_CAMPAIGN_ID
    assert prepared.bundle["campaign"]["status"] == "DRAFT"
    assert prepared.bundle["campaign"]["frozen_at"] is None
    assert len(prepared.bundle["cases"]) == 7
    assert prepared.bundle["cases"][0]["case_id"] == SOFTWARE_CASE_ID
    assert prepared.bundle["runs"] == []
    assert prepared.bundle["comparisons"] == []
    assert prepared.bundle["claims"] == []
    assert {result.status for result in verify_artifacts(prepared.bundle, prepared.output_dir)} == {
        "PASS"
    }


def test_suite_manifest_is_predeclared_and_excludes_source_execution(tmp_path: Path) -> None:
    repository, commit = _sut_repository(tmp_path)
    prepared = prepare_cumulative_verification_campaign(
        tmp_path / "campaign",
        sut_repository=repository,
        sut_commit=commit,
    )
    manifest = json.loads(prepared.suite_manifest_path.read_text(encoding="utf-8"))

    assert manifest["source_checkout_execution"] is False
    assert manifest["real_data_included"] is False
    assert manifest["restricted_data_included"] is False
    assert manifest["expected_structured_output"]["format"] == "JUnit XML"
    assert manifest["logical_command"][0:2] == ["python", "pytest-entrypoint.py"]
    assert all("gui" not in path.lower() for path in SELECTED_SUITE_PATHS)


def test_suite_hash_changes_when_selected_git_object_changes(tmp_path: Path) -> None:
    repository, first_commit = _sut_repository(tmp_path)
    first_archive, _ = export_software_test_suite(repository, first_commit)
    selected = repository / "tests/core/test_roughness.py"
    selected.write_text("# changed selected test\n", encoding="utf-8")
    _git(repository, "add", selected.relative_to(repository).as_posix())
    _git(
        repository,
        "-c",
        "user.name=Phase Test",
        "-c",
        "user.email=phase-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "change selected test",
    )
    second_commit = _git(repository, "rev-parse", "HEAD")
    second_archive, _ = export_software_test_suite(repository, second_commit)

    assert hashlib.sha256(first_archive).digest() != hashlib.sha256(second_archive).digest()
