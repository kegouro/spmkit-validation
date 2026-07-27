"""Ordered execution of one software run and six scientific runs from one wheel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cumulative_protocol import (
    CUMULATIVE_CAMPAIGN_ID,
    PYTEST_VERSION,
    SUITE_MANIFEST_ID,
)
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .runner import (
    CampaignExecutionResult,
    _strict_json,
    _validate_protocol_before_subprocess,
    execute_frozen_campaign,
    install_sut_wheel_environment,
)
from .software_verification import SoftwareTestExecutionResult, execute_software_test


@dataclass(frozen=True, slots=True)
class CumulativeExecutionResult:
    """Ordered software and scientific records sharing one wheel identity."""

    software_test: SoftwareTestExecutionResult
    scientific: CampaignExecutionResult
    started_at: str
    completed_at: str
    wheel_sha256: str
    wheel_size_bytes: int

    @property
    def runs(self) -> tuple[Mapping[str, Any], ...]:
        return (self.software_test.run, *self.scientific.runs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "software_test": self.software_test.to_dict(),
            "scientific": self.scientific.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "wheel_sha256": self.wheel_sha256,
            "wheel_size_bytes": self.wheel_size_bytes,
        }


def _manifest_path(protocol: Mapping[str, Any], artifact_root: Path) -> Path:
    try:
        artifact = next(
            item for item in protocol["evidence"] if item["artifact_id"] == SUITE_MANIFEST_ID
        )
    except StopIteration as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "CUMULATIVE.SUITE_MANIFEST_MISSING",
                    "/evidence",
                    "frozen cumulative protocol lacks its selected-suite manifest",
                )
            ]
        ) from exc
    return artifact_root / artifact["relative_uri"]


def execute_cumulative_campaign(
    protocol_bundle_path: str | Path,
    freeze_receipt_path: str | Path,
    *,
    artifact_root: str | Path,
    sut_wheel: str | Path,
    output_dir: str | Path,
    software_timeout_seconds: float = 120.0,
    scientific_timeout_seconds: float = 60.0,
) -> CumulativeExecutionResult:
    """Verify first, install once, then execute software followed by science."""

    root = Path(artifact_root).resolve(strict=True)
    protocol = _validate_protocol_before_subprocess(
        Path(protocol_bundle_path), Path(freeze_receipt_path), root
    )
    if protocol["campaign"]["campaign_id"] != CUMULATIVE_CAMPAIGN_ID:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "CUMULATIVE.CAMPAIGN_ID_MISMATCH",
                    "/campaign/campaign_id",
                    "execute_cumulative_campaign requires the cumulative protocol",
                )
            ]
        )
    manifest = _strict_json(_manifest_path(protocol, root))
    test_dependencies = tuple(manifest.get("test_dependencies", []))
    expected_dependencies = (f"pytest=={PYTEST_VERSION}",)
    if test_dependencies != expected_dependencies:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "CUMULATIVE.TEST_DEPENDENCY_DRIFT",
                    "/test_dependencies",
                    "test dependencies differ from the supported frozen dependency set",
                )
            ]
        )
    output = Path(output_dir)
    parent = output.parent.resolve(strict=True)
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "CUMULATIVE.OUTPUT_ESCAPES_ARTIFACT_ROOT",
                    "/output_dir",
                    "cumulative output must be created below artifact_root",
                )
            ]
        ) from exc
    output.mkdir(exist_ok=False)
    environment = install_sut_wheel_environment(
        Path(sut_wheel),
        output,
        protocol["campaign"]["system_under_test"]["version"],
        test_dependencies=test_dependencies,
    )
    software = execute_software_test(
        protocol_bundle_path,
        freeze_receipt_path,
        artifact_root=root,
        sut_wheel=sut_wheel,
        installed_environment=environment,
        output_dir=output / "software-test",
        timeout_seconds=software_timeout_seconds,
    )
    scientific = execute_frozen_campaign(
        protocol_bundle_path,
        freeze_receipt_path,
        artifact_root=root,
        sut_wheel=sut_wheel,
        output_dir=output / "scientific",
        installed_environment=environment,
        timeout_seconds=scientific_timeout_seconds,
    )
    if software.wheel_sha256 != scientific.wheel_sha256:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "CUMULATIVE.WHEEL_IDENTITY_DIVERGED",
                    "/runs",
                    "software and scientific execution did not use one wheel hash",
                )
            ]
        )
    return CumulativeExecutionResult(
        software_test=software,
        scientific=scientific,
        started_at=software.started_at,
        completed_at=scientific.completed_at,
        wheel_sha256=scientific.wheel_sha256,
        wheel_size_bytes=scientific.wheel_size_bytes,
    )
