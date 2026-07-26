"""Stable issues for synthetic campaign preparation and execution."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class CampaignExecutionIssueCategory(str, Enum):
    """High-level machine-readable campaign failure categories."""

    INPUT = "INPUT"
    PROTOCOL = "PROTOCOL"
    EXECUTION = "EXECUTION"
    OUTPUT = "OUTPUT"
    CONTINUITY = "CONTINUITY"
    RECEIPT = "RECEIPT"
    ARTIFACT = "ARTIFACT"
    FILESYSTEM = "FILESYSTEM"


@dataclass(frozen=True, slots=True)
class CampaignExecutionIssue:
    """One fail-loudly campaign issue with a stable code and JSON path."""

    category: CampaignExecutionIssueCategory
    code: str
    path: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category.value,
            "code": self.code,
            "path": self.path,
            "description": self.description,
        }


class CampaignExecutionError(Exception):
    """Operation failure carrying all structured campaign issues."""

    def __init__(self, issues: Iterable[CampaignExecutionIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{issue.code} at {issue.path}: {issue.description}" for issue in self.issues
        )
        super().__init__(summary or "synthetic campaign operation failed")


def execution_issue(
    category: CampaignExecutionIssueCategory,
    code: str,
    path: str,
    description: str,
) -> CampaignExecutionIssue:
    return CampaignExecutionIssue(category, code, path, description)
