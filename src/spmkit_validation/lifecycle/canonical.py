"""Deterministic JSON serialization used by the PHASE_01B lifecycle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .issues import LifecycleError, LifecycleIssueCategory, lifecycle_issue

CANONICALIZATION_NAME = "SPMKIT_CANONICAL_JSON_V1"


def canonical_bundle_bytes(bundle: Mapping[str, Any]) -> bytes:
    """Return deterministic UTF-8 JSON without mutating *bundle*.

    This is the deliberately scoped SPMKIT_CANONICAL_JSON_V1 representation,
    not an implementation of RFC 8785/JCS.
    """

    try:
        text = json.dumps(
            bundle,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LifecycleError(
            [
                lifecycle_issue(
                    LifecycleIssueCategory.INPUT,
                    "CANONICAL.INVALID_JSON_VALUE",
                    "",
                    f"document cannot be represented as finite canonical JSON: {exc}",
                )
            ]
        ) from exc
    return (text + "\n").encode("utf-8")
