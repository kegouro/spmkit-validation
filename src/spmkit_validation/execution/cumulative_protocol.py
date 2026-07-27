"""Pre-freeze cumulative software and numerical verification protocol."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import canonical_bundle_bytes
from spmkit_validation.schemas import assert_valid_bundle

from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .synthetic_roughness import (
    DEFAULT_CREATED_AT,
    DEFAULT_PREDECLARED_AT,
    DEFAULT_SUT_COMMIT,
    DEFAULT_SUT_VERSION,
    PreparedSyntheticCampaign,
    _artifact,
    _write_exclusive,
    prepare_synthetic_roughness_campaign,
)

CUMULATIVE_CAMPAIGN_ID = "campaign.cumulative-software-numerical.v0.1"
SOFTWARE_CASE_ID = "case.software.roughness-wheel"
SOFTWARE_DATASET_ID = "dataset.software.roughness-wheel-suite"
SOFTWARE_REFERENCE_ID = "reference.software.zero-test-failures"
SOFTWARE_TEST_RUN_ID = "run.software.roughness-wheel"
SUITE_MANIFEST_ID = "artifact.software-test.suite-manifest"
SUITE_ARCHIVE_ID = "artifact.software-test.suite-archive"
PYTEST_ENTRYPOINT_ID = "artifact.software-test.pytest-entrypoint"
WHEEL_POLICY_ID = "artifact.software-test.wheel-policy"
SUITE_MANIFEST_VERSION = "0.1.0"
PYTEST_VERSION = "9.1.1"

_SELECTED_TEST_PATHS = (
    "tests/core/test_export.py",
    "tests/core/test_manifest.py",
    "tests/core/test_npz.py",
    "tests/core/test_roughness.py",
)
_FIXTURE_PATHS = (
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/core/__init__.py",
)
SELECTED_SUITE_PATHS = tuple(sorted((*_SELECTED_TEST_PATHS, *_FIXTURE_PATHS)))
SELECTED_NODE_IDS = (
    "tests/core/test_roughness.py",
    "tests/core/test_export.py",
    "tests/core/test_npz.py",
    "tests/core/test_manifest.py::test_numpy_serialization",
    "tests/core/test_manifest.py::test_invalid_input_error",
)

_PYTEST_ENTRYPOINT = b'''from __future__ import annotations

import platform
import sys

import pytest

platform.node = lambda: "spmkit-validation"  # privacy-only JUnit metadata control
raise SystemExit(pytest.main(sys.argv[1:]))
'''


@dataclass(frozen=True, slots=True)
class PreparedCumulativeCampaign:
    """Validated combined DRAFT and every predeclared local artifact."""

    output_dir: Path
    bundle_path: Path
    ground_truth_path: Path
    tolerance_budget_path: Path
    suite_manifest_path: Path
    suite_archive_path: Path
    pytest_entrypoint_path: Path
    wheel_policy_path: Path
    bundle: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.bundle["campaign"]["campaign_id"],
            "status": self.bundle["campaign"]["status"],
            "bundle_path": self.bundle_path.name,
            "case_count": len(self.bundle["cases"]),
            "software_case_id": SOFTWARE_CASE_ID,
            "scientific_case_count": len(self.bundle["cases"]) - 1,
            "suite_manifest_path": self.suite_manifest_path.name,
        }


def _git(
    repository: Path,
    arguments: Sequence[str],
    *,
    binary: bool = False,
) -> bytes | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=not binary,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "SOFTWARE_SUITE.GIT_FAILED",
                    "/sut_repository",
                    str(exc),
                )
            ]
        ) from exc
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode()
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "SOFTWARE_SUITE.GIT_OBJECT_UNAVAILABLE",
                    "/sut_commit",
                    stderr.strip() or "Git object read failed",
                )
            ]
        )
    return result.stdout


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _suite_manifest(
    repository: Path,
    sut_commit: str,
    archive_bytes: bytes,
    entrypoint_sha256: str,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative_path in SELECTED_SUITE_PATHS:
        content = _git(repository, ["show", f"{sut_commit}:{relative_path}"], binary=True)
        assert isinstance(content, bytes)
        blob = _git(repository, ["rev-parse", f"{sut_commit}:{relative_path}"])
        assert isinstance(blob, str)
        files.append(
            {
                "path": relative_path,
                "kind": "FIXTURE" if relative_path in _FIXTURE_PATHS else "TEST",
                "git_blob": blob.strip(),
                "sha256": _sha256(content),
                "size_bytes": len(content),
            }
        )
    return {
        "manifest_version": SUITE_MANIFEST_VERSION,
        "sut_commit": sut_commit,
        "files": files,
        "selected_node_ids": list(SELECTED_NODE_IDS),
        "fixtures": list(_FIXTURE_PATHS),
        "markers": {
            "included": [],
            "excluded": [
                "GUI tests",
                "tests requiring external or instrument-origin data",
                "manufacturer-format integration tests",
            ],
        },
        "selection_reasons": [
            "roughness statistics on deterministic synthetic arrays",
            "public JSON and CSV exports",
            "public NumPy NPZ loading",
            "RunManifest construction and clean CLI error behavior",
        ],
        "logical_command": [
            "python",
            "pytest-entrypoint.py",
            "-q",
            "-o",
            "addopts=",
            "--junitxml",
            "junit.xml",
            *SELECTED_NODE_IDS,
        ],
        "expected_test_framework": {"name": "pytest", "version": PYTEST_VERSION},
        "test_dependencies": [f"pytest=={PYTEST_VERSION}"],
        "expected_structured_output": {
            "format": "JUnit XML",
            "family": "xunit2",
            "relative_uri": "junit.xml",
        },
        "source_archive": {
            "format": "POSIX tar emitted by git archive",
            "sha256": _sha256(archive_bytes),
            "size_bytes": len(archive_bytes),
        },
        "privacy_control": {
            "pytest_entrypoint_sha256": entrypoint_sha256,
            "junit_hostname": "spmkit-validation",
            "result_fields_modified": False,
        },
        "source_checkout_execution": False,
        "real_data_included": False,
        "restricted_data_included": False,
    }


def export_software_test_suite(
    sut_repository: str | Path,
    sut_commit: str,
) -> tuple[bytes, dict[str, Any]]:
    """Return exact selected Git objects as tar plus a content-identity manifest."""

    repository = Path(sut_repository)
    if not repository.is_dir():
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "SOFTWARE_SUITE.REPOSITORY_INVALID",
                    "/sut_repository",
                    "SUT repository must be an explicit directory",
                )
            ]
        )
    resolved = _git(repository, ["rev-parse", f"{sut_commit}^{{commit}}"])
    assert isinstance(resolved, str)
    if resolved.strip() != sut_commit:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "SOFTWARE_SUITE.COMMIT_MISMATCH",
                    "/sut_commit",
                    "selected suite commit does not resolve to the declared full commit",
                )
            ]
        )
    archive = _git(
        repository,
        ["archive", "--format=tar", sut_commit, *SELECTED_SUITE_PATHS],
        binary=True,
    )
    assert isinstance(archive, bytes)
    return archive, _suite_manifest(repository, sut_commit, archive, _sha256(_PYTEST_ENTRYPOINT))


def _json_file(path: Path, document: Mapping[str, Any]) -> bytes:
    content = canonical_bundle_bytes(document)
    _write_exclusive(path, content)
    return content


def _software_reference() -> dict[str, Any]:
    return {
        "reference_id": SOFTWARE_REFERENCE_ID,
        "reference_type": "ANALYTICAL_REFERENCE",
        "name": "Predeclared zero-failure selected software-suite criterion",
        "version": SUITE_MANIFEST_VERSION,
        "producer": {
            "name": "spmkit-validation cumulative protocol",
            "is_third_party": False,
            "operator_ids": ["party.protocol.author"],
        },
        "method": "A successful selected suite has zero JUnit failures and zero errors.",
        "independence_justification": {
            "rationale": (
                "The suite is authored with the SUT and is software evidence, not an "
                "independent numerical reference."
            ),
            "shared_algorithms": ["SPM-Kit public roughness implementation"],
            "shared_formulas": ["Sa, Sq and Sz definitions exercised by the selected tests"],
            "shared_libraries": ["pytest", "NumPy", "SPM-Kit installed wheel"],
            "shared_datasets": [SOFTWARE_DATASET_ID],
            "shared_authors": ["SPM-Kit contributors"],
            "circularity_risks": ["Selected tests and SUT share repository authorship."],
            "independence_assessment": "NOT_INDEPENDENT",
        },
        "shared_dependencies": {
            "software": ["pytest", "NumPy", "SPM-Kit installed wheel"],
            "data": [SOFTWARE_DATASET_ID],
            "methods": ["Selected SUT tests"],
            "notes": ["This reference supports LEVEL 1 software verification only."],
        },
        "known_limitations": [
            "Narrow non-GUI suite; it is not a complete verification of every SPM-Kit feature."
        ],
        "evidence_ids": [SUITE_MANIFEST_ID],
    }


def _software_case(predeclared_at: str) -> dict[str, Any]:
    return {
        "case_id": SOFTWARE_CASE_ID,
        "dataset_id": SOFTWARE_DATASET_ID,
        "reference_id": SOFTWARE_REFERENCE_ID,
        "purpose": "VERIFICATION",
        "operation": {
            "name": "pytest selected tests against installed SPM-Kit wheel",
            "version": PYTEST_VERSION,
            "parameters": {
                "structured_output": "JUnit XML",
                "source_checkout_execution": False,
                "wheel_identity_policy": "ONE_HASH_FOR_SOFTWARE_AND_NUMERICAL_RUNS",
                "selected_node_ids": list(SELECTED_NODE_IDS),
            },
        },
        "input_selector": {"selector_type": "FULL_DATASET"},
        "preprocessing": [],
        "measurands": [
            {
                "measurand_id": "software_test_failures",
                "canonical_unit": "count",
                "physical_quantity": "failed selected software tests",
                "description": "JUnit failures plus errors in the predeclared selected suite.",
            }
        ],
        "tolerances": [
            {
                "tolerance_id": "tolerance.software.zero-failures",
                "measurand_id": "software_test_failures",
                "type": "ABSOLUTE",
                "absolute": 0,
                "unit": "count",
                "justification": "Software verification requires zero failures and zero errors.",
                "source": SUITE_MANIFEST_ID,
            }
        ],
        "expected_units": {"software_test_failures": "count"},
        "acceptance_policy": {
            "aggregation": "ALL_MEASURANDS_MUST_PASS",
            "on_evaluation_error": "ERROR",
            "on_missing_result": "NOT_EVALUATED",
        },
        "predeclared_at": predeclared_at,
        "case_status": "ACTIVE",
        "determinism_requirement": "CANONICALLY_REPEATABLE",
        "determinism_override_justification": (
            "JUnit status and counts must repeat; durations are operational metadata."
        ),
    }


def prepare_cumulative_verification_campaign(
    output_dir: str | Path,
    *,
    sut_repository: str | Path,
    created_at: str = DEFAULT_CREATED_AT,
    predeclared_at: str = DEFAULT_PREDECLARED_AT,
    generator_commit: str | None = None,
    sut_commit: str = DEFAULT_SUT_COMMIT,
    sut_version: str = DEFAULT_SUT_VERSION,
) -> PreparedCumulativeCampaign:
    """Prepare seven frozen-before-run cases without invoking pytest or SPM-Kit."""

    base: PreparedSyntheticCampaign = prepare_synthetic_roughness_campaign(
        output_dir,
        created_at=created_at,
        predeclared_at=predeclared_at,
        generator_commit=generator_commit,
        sut_commit=sut_commit,
        sut_version=sut_version,
        campaign_id=CUMULATIVE_CAMPAIGN_ID,
        campaign_title="Cumulative installed-wheel software and synthetic roughness verification",
        campaign_objective=(
            "Combine a selected installed-wheel software suite with fresh black-box Sa, Sq "
            "and Sz recovery on six analytical synthetic phantoms."
        ),
        environment_id="environment.phase01d.authoritative",
        responsible_party_name="PHASE_01D protocol author",
        write_bundle=False,
    )
    root = base.output_dir
    archive_bytes, suite_manifest = export_software_test_suite(sut_repository, sut_commit)
    suite_archive_path = root / "software-test-suite.tar"
    _write_exclusive(suite_archive_path, archive_bytes)
    pytest_entrypoint_path = root / "software-test-harness/pytest-entrypoint.py"
    _write_exclusive(pytest_entrypoint_path, _PYTEST_ENTRYPOINT)
    suite_manifest_path = root / "software-test-suite-manifest.json"
    suite_manifest_bytes = _json_file(suite_manifest_path, suite_manifest)
    wheel_policy = {
        "policy_version": "0.1.0",
        "sut_commit": sut_commit,
        "sut_version": sut_version,
        "required_python": "3.12",
        "requirements": [
            "Build one wheel from the declared SUT commit after protocol verification.",
            "Use the identical wheel SHA-256 for SOFTWARE_TEST and all numerical runs.",
            "Resolve the imported spmkit module under the clean environment site-packages.",
            "Run exported tests outside the SUT checkout with PYTHONPATH absent.",
        ],
    }
    wheel_policy_path = root / "wheel-identity-policy.json"
    wheel_policy_bytes = _json_file(wheel_policy_path, wheel_policy)

    bundle = dict(base.bundle)
    bundle["campaign"] = dict(bundle["campaign"])
    bundle["campaign"]["limitations"] = [
        "Software scope is the exact selected non-GUI suite recorded by Git object identity.",
        *bundle["campaign"]["limitations"],
    ]
    archive_artifact = _artifact(
        artifact_id=SUITE_ARCHIVE_ID,
        artifact_type="INPUT",
        media_type="application/x-tar",
        relative_uri=suite_archive_path.name,
        content=archive_bytes,
        created_at=created_at,
        role="INPUT_DATA",
    )
    entrypoint_artifact = _artifact(
        artifact_id=PYTEST_ENTRYPOINT_ID,
        artifact_type="INPUT",
        media_type="text/x-python",
        relative_uri="software-test-harness/pytest-entrypoint.py",
        content=_PYTEST_ENTRYPOINT,
        created_at=created_at,
        role="PROVENANCE",
    )
    manifest_artifact = _artifact(
        artifact_id=SUITE_MANIFEST_ID,
        artifact_type="MANIFEST",
        media_type="application/json",
        relative_uri=suite_manifest_path.name,
        content=suite_manifest_bytes,
        created_at=created_at,
        role="PROVENANCE",
        sources=[SUITE_ARCHIVE_ID, PYTEST_ENTRYPOINT_ID],
    )
    manifest_artifact["external_schema"] = {
        "name": "spmkit-validation.software-test-suite-manifest",
        "version": SUITE_MANIFEST_VERSION,
    }
    policy_artifact = _artifact(
        artifact_id=WHEEL_POLICY_ID,
        artifact_type="REPORT",
        media_type="application/json",
        relative_uri=wheel_policy_path.name,
        content=wheel_policy_bytes,
        created_at=predeclared_at,
        role="PROVENANCE",
        sources=[SUITE_MANIFEST_ID],
    )
    bundle["evidence"] = sorted(
        [
            *bundle["evidence"],
            archive_artifact,
            entrypoint_artifact,
            manifest_artifact,
            policy_artifact,
        ],
        key=lambda item: item["artifact_id"],
    )
    archive_sha256 = _sha256(archive_bytes)
    bundle["datasets"] = [
        *bundle["datasets"],
        {
            "dataset_id": SOFTWARE_DATASET_ID,
            "title": "Exact selected SPM-Kit software test suite",
            "role": "VERIFICATION",
            "source_type": "PUBLIC_DATASET",
            "provenance": {
                "producer": "Git object export from declared SPM-Kit commit",
                "method": "git archive of exact predeclared paths",
                "created_at": created_at,
                "source_artifact_ids": [SUITE_MANIFEST_ID, SUITE_ARCHIVE_ID],
            },
            "license": "MIT",
            "checksum": archive_sha256,
            "format": {
                "media_type": "application/x-tar",
                "specification": "POSIX tar emitted by git archive",
            },
            "access_policy": {"access_level": "PUBLIC", "access_state": "OPENED"},
            "locator": suite_archive_path.name,
            "public_metadata": {
                "sut_commit": sut_commit,
                "selected_test_files": len(_SELECTED_TEST_PATHS),
                "selected_node_ids": len(SELECTED_NODE_IDS),
                "contains_only_source_tests_and_synthetic_fixtures": True,
            },
            "limitations": ["Narrow selected test suite; GUI and external-data tests excluded."],
        },
    ]
    bundle["references"] = [*bundle["references"], _software_reference()]
    bundle["cases"] = [_software_case(predeclared_at), *bundle["cases"]]
    assert_valid_bundle(bundle)
    bundle_path = root / "draft-bundle.json"
    _write_exclusive(bundle_path, canonical_bundle_bytes(bundle))
    return PreparedCumulativeCampaign(
        output_dir=root,
        bundle_path=bundle_path,
        ground_truth_path=base.ground_truth_path,
        tolerance_budget_path=base.tolerance_budget_path,
        suite_manifest_path=suite_manifest_path,
        suite_archive_path=suite_archive_path,
        pytest_entrypoint_path=pytest_entrypoint_path,
        wheel_policy_path=wheel_policy_path,
        bundle=bundle,
    )
