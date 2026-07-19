"""Modelos de datos para el arnés de validación."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ValidationCase:
    case_id: str
    input_path: Path
    command: str
    arguments: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunRecord:
    case_id: str
    started_at: str
    finished_at: str
    return_code: int | None
    command: list[str]
    stdout_path: Path
    stderr_path: Path
    artifacts: list[Path] = field(default_factory=list)
    status: Status = Status.INCONCLUSIVE
    error: str | None = None
