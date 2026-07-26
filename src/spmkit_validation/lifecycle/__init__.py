"""Public black-box lifecycle API for ValidationBundle v0.1."""

from .artifacts import ArtifactVerificationResult, verify_artifacts
from .canonical import CANONICALIZATION_NAME, canonical_bundle_bytes
from .freeze import FreezeResult, freeze_bundle
from .issues import LifecycleError, LifecycleIssue
from .receipt import FreezeReceipt
from .verification import SnapshotVerificationResult, verify_frozen_snapshot

__all__ = [
    "CANONICALIZATION_NAME",
    "ArtifactVerificationResult",
    "FreezeReceipt",
    "FreezeResult",
    "LifecycleError",
    "LifecycleIssue",
    "SnapshotVerificationResult",
    "canonical_bundle_bytes",
    "freeze_bundle",
    "verify_artifacts",
    "verify_frozen_snapshot",
]
