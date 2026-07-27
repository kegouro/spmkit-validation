"""Safe, streaming verification of ValidationBundle evidence artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .issues import (
    LifecycleError,
    LifecycleIssue,
    LifecycleIssueCategory,
    lifecycle_issue,
)

_HASH_CHUNK_SIZE = 1024 * 1024
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class ArtifactVerificationResult:
    """Verification result for one declared artifact."""

    artifact_id: str
    status: str
    relative_uri: str | None
    calculated_sha256: str | None
    calculated_size_bytes: int | None
    issues: tuple[LifecycleIssue, ...]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "status": self.status,
            "relative_uri": self.relative_uri,
            "calculated_sha256": self.calculated_sha256,
            "calculated_size_bytes": self.calculated_size_bytes,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def summarize_artifact_results(
    results: Sequence[ArtifactVerificationResult],
) -> dict[str, int]:
    return {
        "total": len(results),
        "passed": sum(result.status == "PASS" for result in results),
        "failed": sum(result.status == "FAIL" for result in results),
        "remote_not_verified": sum(
            result.status == "REMOTE_ARTIFACT_NOT_VERIFIED" for result in results
        ),
    }


def _artifact_issue(code: str, path: str, description: str) -> LifecycleIssue:
    return lifecycle_issue(LifecycleIssueCategory.ARTIFACT, code, path, description)


def _root_issue(code: str, description: str) -> LifecycleIssue:
    return lifecycle_issue(LifecycleIssueCategory.FILESYSTEM, code, "/artifact_root", description)


def _resolve_artifact_root(artifact_root: str | Path) -> Path:
    root = Path(artifact_root)
    try:
        resolved = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LifecycleError(
            [_root_issue("ARTIFACT_ROOT_NOT_FOUND", f"artifact root cannot be resolved: {exc}")]
        ) from exc
    if not resolved.is_dir():
        raise LifecycleError(
            [_root_issue("ARTIFACT_ROOT_NOT_DIRECTORY", "artifact root must be a directory")]
        )
    return resolved


def _classify_locator(value: Any) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value:
        return "unsafe", "ARTIFACT_INVALID_URI"
    if value.startswith("/"):
        return "unsafe", "ARTIFACT_ABSOLUTE_PATH"
    if value.startswith("\\\\") or value.startswith("//"):
        return "unsafe", "ARTIFACT_UNC_PATH"
    if _WINDOWS_DRIVE.match(value):
        return "unsafe", "ARTIFACT_WINDOWS_ABSOLUTE_PATH"

    parsed = urlsplit(value)
    if parsed.scheme.lower() == "file":
        return "unsafe", "ARTIFACT_FILE_URI"
    if parsed.scheme:
        return "remote", None

    normalized = value.replace("\\", "/")
    if any(segment == ".." for segment in normalized.split("/")):
        return "unsafe", "ARTIFACT_PATH_TRAVERSAL"
    return "local", normalized


def _hash_regular_file(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("artifact is not a regular file")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, _HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            raise OSError("artifact changed while it was being verified")
        return digest.hexdigest(), size
    finally:
        os.close(descriptor)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    return parsed


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _validate_run_manifest(
    path: Path, artifact: Mapping[str, Any], index: int
) -> list[LifecycleIssue]:
    external = artifact.get("external_schema")
    if (
        not isinstance(external, Mapping)
        or external.get("name") != ("spmkit.core.export.RunManifest")
        or external.get("version") != "1.0"
    ):
        return []

    issues: list[LifecycleIssue] = []
    media_type = artifact.get("media_type")
    if not isinstance(media_type, str) or not (
        media_type.lower() == "application/json" or media_type.lower().endswith("+json")
    ):
        issues.append(
            _artifact_issue(
                "RUNMANIFEST_MIME_MISMATCH",
                f"/evidence/{index}/media_type",
                "RunManifest 1.0 must declare a JSON-compatible MIME type",
            )
        )
        return issues

    try:
        with path.open("r", encoding="utf-8") as handle:
            json.load(
                handle,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(
            _artifact_issue(
                "RUNMANIFEST_INVALID_JSON",
                f"/evidence/{index}/relative_uri",
                f"RunManifest 1.0 is not strict finite JSON: {exc}",
            )
        )
    return issues


def _artifact_graph_issues(
    artifacts: Sequence[Any],
) -> tuple[dict[int, list[LifecycleIssue]], dict[str, Mapping[str, Any]]]:
    by_index: dict[int, list[LifecycleIssue]] = defaultdict(list)
    by_id: dict[str, Mapping[str, Any]] = {}
    id_indices: dict[str, list[int]] = defaultdict(list)

    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            by_index[index].append(
                _artifact_issue(
                    "ARTIFACT_INVALID_RECORD",
                    f"/evidence/{index}",
                    "artifact record must be an object",
                )
            )
            continue
        artifact_id = artifact.get("artifact_id")
        if not isinstance(artifact_id, str):
            by_index[index].append(
                _artifact_issue(
                    "ARTIFACT_INVALID_ID",
                    f"/evidence/{index}/artifact_id",
                    "artifact_id must be a string",
                )
            )
            continue
        id_indices[artifact_id].append(index)
        by_id.setdefault(artifact_id, artifact)

    for artifact_id, indices in id_indices.items():
        if len(indices) > 1:
            for index in indices:
                by_index[index].append(
                    _artifact_issue(
                        "ARTIFACT_ID_DUPLICATE",
                        f"/evidence/{index}/artifact_id",
                        f"artifact_id {artifact_id!r} is duplicated",
                    )
                )

    graph: dict[str, list[str]] = {artifact_id: [] for artifact_id in by_id}
    for artifact_id, artifact in by_id.items():
        index = id_indices[artifact_id][0]
        sources = artifact.get("source_artifact_ids", [])
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
            continue
        for source_position, source_id in enumerate(sources):
            source_path = f"/evidence/{index}/source_artifact_ids/{source_position}"
            if source_id == artifact_id:
                by_index[index].append(
                    _artifact_issue(
                        "SOURCE_ARTIFACT_SELF_REFERENCE",
                        source_path,
                        "an artifact cannot reference itself as a source",
                    )
                )
            elif source_id not in by_id:
                by_index[index].append(
                    _artifact_issue(
                        "SOURCE_ARTIFACT_NOT_FOUND",
                        source_path,
                        f"source artifact {source_id!r} does not exist",
                    )
                )
            elif isinstance(source_id, str):
                graph[artifact_id].append(source_id)

    color: dict[str, int] = dict.fromkeys(graph, 0)
    stack: list[str] = []
    cycle_nodes: set[str] = set()

    def visit(artifact_id: str) -> None:
        color[artifact_id] = 1
        stack.append(artifact_id)
        for source_id in graph[artifact_id]:
            if color[source_id] == 0:
                visit(source_id)
            elif color[source_id] == 1:
                cycle_nodes.update(stack[stack.index(source_id) :])
        stack.pop()
        color[artifact_id] = 2

    for artifact_id in sorted(graph):
        if color[artifact_id] == 0:
            visit(artifact_id)

    for artifact_id in sorted(cycle_nodes):
        index = id_indices[artifact_id][0]
        by_index[index].append(
            _artifact_issue(
                "SOURCE_ARTIFACT_CYCLE",
                f"/evidence/{index}/source_artifact_ids",
                f"artifact {artifact_id!r} participates in a source cycle",
            )
        )
    return by_index, by_id


def _sealed_artifact_ids(
    bundle: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> set[str]:
    protected: set[str] = set()
    sealed_dataset_ids: set[str] = set()
    datasets = bundle.get("datasets", [])
    if isinstance(datasets, Sequence) and not isinstance(datasets, (str, bytes)):
        for dataset in datasets:
            if not isinstance(dataset, Mapping):
                continue
            access = dataset.get("access_policy", {})
            if dataset.get("role") != "BLIND_HOLDOUT" or not isinstance(access, Mapping):
                continue
            if access.get("access_state") != "SEALED":
                continue
            dataset_id = dataset.get("dataset_id")
            if isinstance(dataset_id, str):
                sealed_dataset_ids.add(dataset_id)
            provenance = dataset.get("provenance", {})
            if isinstance(provenance, Mapping):
                protected.update(
                    source_id
                    for source_id in provenance.get("source_artifact_ids", [])
                    if isinstance(source_id, str)
                )

    cases = bundle.get("cases", [])
    if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes)):
        for case in cases:
            if not isinstance(case, Mapping) or case.get("dataset_id") not in sealed_dataset_ids:
                continue
            selector = case.get("input_selector", {})
            if isinstance(selector, Mapping) and isinstance(
                selector.get("evidence_artifact_id"), str
            ):
                protected.add(selector["evidence_artifact_id"])
            preprocessing = case.get("preprocessing", [])
            if isinstance(preprocessing, Sequence) and not isinstance(preprocessing, (str, bytes)):
                for step in preprocessing:
                    if isinstance(step, Mapping) and isinstance(
                        step.get("evidence_artifact_id"), str
                    ):
                        protected.add(step["evidence_artifact_id"])

    adjacency: dict[str, set[str]] = defaultdict(set)
    for artifact_id, artifact in by_id.items():
        sources = artifact.get("source_artifact_ids", [])
        if isinstance(sources, Sequence) and not isinstance(sources, (str, bytes)):
            for source_id in sources:
                if isinstance(source_id, str) and source_id in by_id:
                    adjacency[artifact_id].add(source_id)
                    adjacency[source_id].add(artifact_id)

    queue = deque(protected)
    while queue:
        artifact_id = queue.popleft()
        for related_id in adjacency.get(artifact_id, set()):
            if related_id not in protected:
                protected.add(related_id)
                queue.append(related_id)
    return protected


def verify_artifacts(
    bundle: Mapping[str, Any], artifact_root: str | Path
) -> tuple[ArtifactVerificationResult, ...]:
    """Verify declared local evidence safely and return artifact-sorted results."""

    root = _resolve_artifact_root(artifact_root)
    evidence = bundle.get("evidence", [])
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.INPUT,
                    "ARTIFACT_EVIDENCE_NOT_ARRAY",
                    "/evidence",
                    "bundle evidence must be an array",
                )
            ]
        )

    graph_issues, by_id = _artifact_graph_issues(evidence)
    sealed_ids = _sealed_artifact_ids(bundle, by_id)
    results: list[ArtifactVerificationResult] = []

    for index, artifact_value in enumerate(evidence):
        artifact = artifact_value if isinstance(artifact_value, Mapping) else {}
        artifact_id_value = artifact.get("artifact_id")
        artifact_id = (
            artifact_id_value if isinstance(artifact_id_value, str) else f"<invalid:{index}>"
        )
        relative_uri_value = artifact.get("relative_uri")
        relative_uri = relative_uri_value if isinstance(relative_uri_value, str) else None
        issues = list(graph_issues.get(index, []))
        calculated_sha256: str | None = None
        calculated_size: int | None = None

        if artifact_id in sealed_ids:
            issues.append(
                _artifact_issue(
                    "SEALED_HOLDOUT_ARTIFACT_BLOCKED",
                    f"/evidence/{index}/relative_uri",
                    "artifact associated with a SEALED blind holdout was not resolved or opened",
                )
            )
            status = "FAIL"
        else:
            locator_kind, locator_detail = _classify_locator(relative_uri_value)
            if locator_kind == "remote":
                issues.append(
                    _artifact_issue(
                        "REMOTE_ARTIFACT_NOT_VERIFIED",
                        f"/evidence/{index}/relative_uri",
                        "remote artifact was not downloaded or verified",
                    )
                )
                status = "REMOTE_ARTIFACT_NOT_VERIFIED"
            elif locator_kind == "unsafe":
                issues.append(
                    _artifact_issue(
                        locator_detail or "ARTIFACT_INVALID_URI",
                        f"/evidence/{index}/relative_uri",
                        "artifact locator is not a safe relative local path",
                    )
                )
                status = "FAIL"
            else:
                candidate = root.joinpath(*(locator_detail or "").split("/"))
                try:
                    resolved = candidate.resolve(strict=True)
                except FileNotFoundError:
                    issues.append(
                        _artifact_issue(
                            "ARTIFACT_NOT_FOUND",
                            f"/evidence/{index}/relative_uri",
                            "declared local artifact does not exist",
                        )
                    )
                except (OSError, RuntimeError) as exc:
                    issues.append(
                        _artifact_issue(
                            "ARTIFACT_RESOLUTION_FAILED",
                            f"/evidence/{index}/relative_uri",
                            f"artifact path could not be resolved safely: {exc}",
                        )
                    )
                else:
                    if not resolved.is_relative_to(root):
                        issues.append(
                            _artifact_issue(
                                "ARTIFACT_ROOT_ESCAPE",
                                f"/evidence/{index}/relative_uri",
                                "resolved artifact path escapes artifact_root",
                            )
                        )
                    else:
                        try:
                            resolved_stat = resolved.stat()
                            if not stat.S_ISREG(resolved_stat.st_mode):
                                issues.append(
                                    _artifact_issue(
                                        "ARTIFACT_NOT_REGULAR_FILE",
                                        f"/evidence/{index}/relative_uri",
                                        "artifact must resolve to a regular file",
                                    )
                                )
                            else:
                                calculated_sha256, calculated_size = _hash_regular_file(resolved)
                                if calculated_sha256 != artifact.get("sha256"):
                                    issues.append(
                                        _artifact_issue(
                                            "ARTIFACT_SHA256_MISMATCH",
                                            f"/evidence/{index}/sha256",
                                            "calculated SHA-256 differs from the declaration",
                                        )
                                    )
                                if calculated_size != artifact.get("size_bytes"):
                                    issues.append(
                                        _artifact_issue(
                                            "ARTIFACT_SIZE_MISMATCH",
                                            f"/evidence/{index}/size_bytes",
                                            "calculated byte size differs from the declaration",
                                        )
                                    )
                                issues.extend(_validate_run_manifest(resolved, artifact, index))
                        except OSError as exc:
                            issues.append(
                                _artifact_issue(
                                    "ARTIFACT_READ_FAILED",
                                    f"/evidence/{index}/relative_uri",
                                    f"artifact could not be verified safely: {exc}",
                                )
                            )
                status = "FAIL" if issues else "PASS"

        if status == "REMOTE_ARTIFACT_NOT_VERIFIED" and any(
            issue.code != "REMOTE_ARTIFACT_NOT_VERIFIED" for issue in issues
        ):
            status = "FAIL"

        results.append(
            ArtifactVerificationResult(
                artifact_id=artifact_id,
                status=status,
                relative_uri=relative_uri,
                calculated_sha256=calculated_sha256,
                calculated_size_bytes=calculated_size,
                issues=tuple(sorted(issues, key=lambda issue: (issue.path, issue.code))),
            )
        )

    return tuple(sorted(results, key=lambda result: result.artifact_id))
