"""Protocol continuity between a frozen snapshot and a populated result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssue,
    CampaignExecutionIssueCategory,
    execution_issue,
)

_CAMPAIGN_FROZEN_FIELDS = (
    "campaign_id",
    "title",
    "objective",
    "protocol_version",
    "created_at",
    "frozen_at",
    "system_under_test",
    "intended_validation_level",
    "determinism_requirement",
    "responsible_parties",
)


def _continuity_issue(code: str, path: str, description: str) -> CampaignExecutionIssue:
    return execution_issue(CampaignExecutionIssueCategory.CONTINUITY, code, path, description)


def _index_by_id(
    values: Any, id_field: str
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return {}
    return {
        value[id_field]: value
        for value in values
        if isinstance(value, Mapping) and isinstance(value.get(id_field), str)
    }


def protocol_continuity_issues(
    frozen_protocol_bundle: Mapping[str, Any],
    populated_result_bundle: Mapping[str, Any],
) -> tuple[CampaignExecutionIssue, ...]:
    """Return every detectable frozen-field drift without changing either input."""

    issues: list[CampaignExecutionIssue] = []
    if frozen_protocol_bundle.get("schema_version") != populated_result_bundle.get(
        "schema_version"
    ):
        issues.append(
            _continuity_issue(
                "PROTOCOL.SCHEMA_VERSION_DRIFT",
                "/schema_version",
                "result schema version differs from the frozen protocol",
            )
        )
    frozen_campaign = frozen_protocol_bundle.get("campaign", {})
    result_campaign = populated_result_bundle.get("campaign", {})
    if isinstance(frozen_campaign, Mapping) and isinstance(result_campaign, Mapping):
        for field in _CAMPAIGN_FROZEN_FIELDS:
            if frozen_campaign.get(field) != result_campaign.get(field):
                issues.append(
                    _continuity_issue(
                        f"PROTOCOL.CAMPAIGN_{field.upper()}_DRIFT",
                        f"/campaign/{field}",
                        f"frozen campaign field {field!r} changed",
                    )
                )
        frozen_limitations = frozen_campaign.get("limitations", [])
        result_limitations = result_campaign.get("limitations", [])
        if not isinstance(result_limitations, Sequence) or any(
            limitation not in result_limitations for limitation in frozen_limitations
        ):
            issues.append(
                _continuity_issue(
                    "PROTOCOL.LIMITATION_REMOVED",
                    "/campaign/limitations",
                    "result bundle must preserve every frozen limitation",
                )
            )
        if result_campaign.get("status") not in {"RUNNING", "COMPLETED", "ABORTED"}:
            issues.append(
                _continuity_issue(
                    "PROTOCOL.INVALID_STATUS_TRANSITION",
                    "/campaign/status",
                    "FROZEN may transition only to RUNNING, COMPLETED or ABORTED",
                )
            )

    for collection, id_field in (
        ("datasets", "dataset_id"),
        ("references", "reference_id"),
        ("cases", "case_id"),
    ):
        frozen = _index_by_id(frozen_protocol_bundle.get(collection), id_field)
        result = _index_by_id(populated_result_bundle.get(collection), id_field)
        if set(frozen) != set(result):
            issues.append(
                _continuity_issue(
                    f"PROTOCOL.{collection.upper()}_SET_DRIFT",
                    f"/{collection}",
                    f"frozen {collection} must not be added, removed or substituted",
                )
            )
        for identifier in sorted(set(frozen).intersection(result)):
            if frozen[identifier] != result[identifier]:
                issues.append(
                    _continuity_issue(
                        f"PROTOCOL.{collection.upper()}_CONTENT_DRIFT",
                        f"/{collection}/{identifier}",
                        f"frozen {collection[:-1]} {identifier!r} changed",
                    )
                )

    frozen_evidence = _index_by_id(frozen_protocol_bundle.get("evidence"), "artifact_id")
    result_evidence = _index_by_id(populated_result_bundle.get("evidence"), "artifact_id")
    for artifact_id, artifact in frozen_evidence.items():
        if artifact_id not in result_evidence:
            issues.append(
                _continuity_issue(
                    "PROTOCOL.ARTIFACT_REMOVED",
                    "/evidence",
                    f"frozen artifact {artifact_id!r} was removed",
                )
            )
        elif artifact != result_evidence[artifact_id]:
            issues.append(
                _continuity_issue(
                    "PROTOCOL.ARTIFACT_DRIFT",
                    f"/evidence/{artifact_id}",
                    f"frozen artifact {artifact_id!r} changed",
                )
            )
    return tuple(issues)


def verify_protocol_continuity(
    frozen_protocol_bundle: Mapping[str, Any],
    populated_result_bundle: Mapping[str, Any],
) -> None:
    """Raise a typed error when any frozen protocol field drifts."""

    issues = protocol_continuity_issues(frozen_protocol_bundle, populated_result_bundle)
    if issues:
        raise CampaignExecutionError(issues)
