"""Stable lifecycle issues and fail-loudly exceptions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class LifecycleIssueCategory(str, Enum):
    """High-level classification for lifecycle failures."""

    INPUT = "INPUT"
    ARTIFACT = "ARTIFACT"
    FILESYSTEM = "FILESYSTEM"
    FREEZE = "FREEZE"
    RECEIPT = "RECEIPT"
    SNAPSHOT = "SNAPSHOT"


@dataclass(frozen=True, slots=True)
class LifecycleIssue:
    """One stable, machine-readable lifecycle issue."""

    category: LifecycleIssueCategory
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


class LifecycleError(Exception):
    """An operation could not complete without weakening lifecycle guarantees."""

    def __init__(self, issues: Iterable[LifecycleIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{issue.code} at {issue.path}: {issue.description}" for issue in self.issues
        )
        super().__init__(summary or "validation bundle lifecycle operation failed")


def lifecycle_issue(
    category: LifecycleIssueCategory,
    code: str,
    path: str,
    description: str,
) -> LifecycleIssue:
    return LifecycleIssue(
        category=category,
        code=code,
        path=path,
        description=description,
    )
