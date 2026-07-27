"""Ordered installed-wheel and Gwyddion-library cross-validation execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spmkit_validation.adapters.gwyddion.library_runner import (
    GwyddionLibraryExecutionResult,
    execute_gwyddion_library_reference,
)

from .cumulative_protocol import PYTEST_VERSION, SUITE_MANIFEST_ID
from .gwyddion_protocol import (
    CROSS_CAMPAIGN_ID,
    EXTERNAL_REFERENCE_ID,
    GWYFILE_WHEEL_ARTIFACT_ID,
    GWYFILE_WHEEL_SHA256,
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
class GwyddionCrossValidationExecutionResult:
    """Thirteen ordered runs tied to one SUT wheel and one frozen helper."""

    software_test: SoftwareTestExecutionResult
    spmkit: CampaignExecutionResult
    external_reference: GwyddionLibraryExecutionResult
    started_at: str
    completed_at: str
    wheel_sha256: str
    wheel_size_bytes: int

    @property
    def runs(self) -> tuple[Mapping[str, Any], ...]:
        return (
            self.software_test.run,
            *self.spmkit.runs,
            *self.external_reference.runs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "software_test": self.software_test.to_dict(),
            "spmkit": self.spmkit.to_dict(),
            "external_reference": self.external_reference.to_dict(),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "wheel_sha256": self.wheel_sha256,
            "wheel_size_bytes": self.wheel_size_bytes,
        }


def _artifact_path(
    protocol: Mapping[str, Any], artifact_root: Path, artifact_id: str
) -> Path:
    try:
        artifact = next(
            item for item in protocol["evidence"] if item["artifact_id"] == artifact_id
        )
    except StopIteration as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GWYDDION_CROSS.ARTIFACT_MISSING",
                    "/evidence",
                    f"frozen protocol lacks {artifact_id}",
                )
            ]
        ) from exc
    return artifact_root / artifact["relative_uri"]


def execute_gwyddion_cross_validation_campaign(
    protocol_bundle_path: str | Path,
    freeze_receipt_path: str | Path,
    *,
    artifact_root: str | Path,
    sut_wheel: str | Path,
    gwyddion_command: str | Path,
    gwyddion_library_dir: str | Path,
    gwyddion_module_dir: str | Path,
    output_dir: str | Path,
    software_timeout_seconds: float = 120.0,
    scientific_timeout_seconds: float = 60.0,
    reference_timeout_seconds: float = 60.0,
) -> GwyddionCrossValidationExecutionResult:
    """Verify freeze, install once, then run software, SUT and external reference."""

    root = Path(artifact_root).resolve(strict=True)
    protocol = _validate_protocol_before_subprocess(
        Path(protocol_bundle_path), Path(freeze_receipt_path), root
    )
    if protocol["campaign"]["campaign_id"] != CROSS_CAMPAIGN_ID:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GWYDDION_CROSS.CAMPAIGN_ID_MISMATCH",
                    "/campaign/campaign_id",
                    "cross-validation executor requires its frozen campaign ID",
                )
            ]
        )
    reference = next(
        item for item in protocol["references"] if item["reference_id"] == EXTERNAL_REFERENCE_ID
    )
    if (
        reference["producer"]["is_third_party"] is not True
        or reference["independence_justification"]["independence_assessment"] != "INDEPENDENT"
    ):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GWYDDION_CROSS.INDEPENDENCE_REJECTED",
                    "/references",
                    "frozen external reference is not third-party INDEPENDENT",
                )
            ]
        )
    manifest = _strict_json(_artifact_path(protocol, root, SUITE_MANIFEST_ID))
    test_dependencies = tuple(manifest.get("test_dependencies", []))
    if test_dependencies != (f"pytest=={PYTEST_VERSION}",):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GWYDDION_CROSS.TEST_DEPENDENCY_DRIFT",
                    "/test_dependencies",
                    "frozen test dependencies differ from the supported set",
                )
            ]
        )
    dependency_wheel = _artifact_path(protocol, root, GWYFILE_WHEEL_ARTIFACT_ID)
    frozen_dependency = next(
        item
        for item in protocol["evidence"]
        if item["artifact_id"] == GWYFILE_WHEEL_ARTIFACT_ID
    )
    if frozen_dependency["sha256"] != GWYFILE_WHEEL_SHA256:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.PROTOCOL,
                    "GWYDDION_CROSS.GWYFILE_IDENTITY_DRIFT",
                    "/evidence",
                    "frozen gwyfile wheel differs from the supported exact release",
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
                    "GWYDDION_CROSS.OUTPUT_ESCAPES_ARTIFACT_ROOT",
                    "/output_dir",
                    "cross-validation output must remain below artifact_root",
                )
            ]
        ) from exc
    output.mkdir(exist_ok=False)
    environment = install_sut_wheel_environment(
        Path(sut_wheel),
        output,
        protocol["campaign"]["system_under_test"]["version"],
        test_dependencies=test_dependencies,
        dependency_wheels=(dependency_wheel,),
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
    spmkit = execute_frozen_campaign(
        protocol_bundle_path,
        freeze_receipt_path,
        artifact_root=root,
        sut_wheel=sut_wheel,
        output_dir=output / "spmkit",
        installed_environment=environment,
        timeout_seconds=scientific_timeout_seconds,
    )
    try:
        external = execute_gwyddion_library_reference(
            protocol,
            artifact_root=root,
            helper_executable=gwyddion_command,
            gwyddion_library_dir=gwyddion_library_dir,
            gwyddion_module_dir=gwyddion_module_dir,
            output_dir=output / "gwyddion",
            timeout_seconds=reference_timeout_seconds,
        )
    except (OSError, ValueError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "GWYDDION_CROSS.REFERENCE_EXECUTION_FAILED",
                    "/gwyddion_command",
                    str(exc),
                )
            ]
        ) from exc
    if software.wheel_sha256 != spmkit.wheel_sha256:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.EXECUTION,
                    "GWYDDION_CROSS.WHEEL_IDENTITY_DIVERGED",
                    "/runs",
                    "software and scientific SUT records do not share one wheel hash",
                )
            ]
        )
    return GwyddionCrossValidationExecutionResult(
        software_test=software,
        spmkit=spmkit,
        external_reference=external,
        started_at=software.started_at,
        completed_at=external.completed_at,
        wheel_sha256=spmkit.wheel_sha256,
        wheel_size_bytes=spmkit.wheel_size_bytes,
    )
