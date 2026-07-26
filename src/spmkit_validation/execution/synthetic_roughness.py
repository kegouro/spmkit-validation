"""Deterministic preparation of the six-case synthetic roughness protocol."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from spmkit_validation.lifecycle import canonical_bundle_bytes
from spmkit_validation.schemas import assert_valid_bundle

from .ground_truth import MEASURANDS, ground_truth_record
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .tolerance import derive_tolerance_budget

CAMPAIGN_ID = "campaign.synthetic-roughness.v0.1"
PROTOCOL_VERSION = "0.1.0"
DEFAULT_CREATED_AT = "2026-07-26T12:00:00Z"
DEFAULT_PREDECLARED_AT = "2026-07-26T12:01:00Z"
DEFAULT_SUT_COMMIT = "11daf8879c9e3e098ce844778592525d4f2bdc53"
DEFAULT_SUT_VERSION = "0.1.5.dev0"
GENERATOR_VERSION = "0.1.0"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _case_specs() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "case_id": f"case.synthetic.{family}.{resolution}x{resolution}",
            "dataset_id": f"dataset.synthetic.{family}.{resolution}x{resolution}",
            "reference_id": f"reference.analytical.{family}",
            "family": family,
            "resolution": resolution,
            "shape": [resolution, resolution],
            "dtype": "float64",
            "unit": "m",
            "amplitude": 0.0 if family == "flat" else 1e-9,
            "seed": None,
            "x_size_m": 1e-6,
            "y_size_m": 1e-6,
        }
        for family in ("flat", "checkerboard", "four-level")
        for resolution in (16, 32)
    )


CASE_SPECS = _case_specs()


@dataclass(frozen=True, slots=True)
class PreparedSyntheticCampaign:
    """Files and validated DRAFT produced before protocol freeze."""

    output_dir: Path
    bundle_path: Path
    ground_truth_path: Path
    tolerance_budget_path: Path
    decision_path: Path
    bundle: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.bundle["campaign"]["campaign_id"],
            "status": self.bundle["campaign"]["status"],
            "bundle_path": self.bundle_path.name,
            "ground_truth_path": self.ground_truth_path.name,
            "tolerance_budget_path": self.tolerance_budget_path.name,
            "case_count": len(self.bundle["cases"]),
        }


def surface_array(spec: Mapping[str, Any]) -> np.ndarray:
    """Generate one exact balanced family in row-major order."""

    resolution = int(spec["resolution"])
    amplitude = float(spec["amplitude"])
    family = spec["family"]
    if family == "flat":
        return np.zeros((resolution, resolution), dtype=np.float64)
    rows, columns = np.indices((resolution, resolution))
    if family == "checkerboard":
        signs = np.where((rows + columns) % 2 == 0, -1.0, 1.0)
        return np.asarray(signs * amplitude, dtype=np.float64)
    if family == "four-level":
        levels = np.array([-3.0, -1.0, 1.0, 3.0], dtype=np.float64) * amplitude
        return np.asarray(levels[(rows * resolution + columns) % 4], dtype=np.float64)
    raise CampaignExecutionError(
        [
            execution_issue(
                CampaignExecutionIssueCategory.INPUT,
                "GENERATOR.UNKNOWN_FAMILY",
                "/family",
                f"unsupported family {family!r}",
            )
        ]
    )


def _npy_bytes(array: np.ndarray) -> bytes:
    target = io.BytesIO()
    np.lib.format.write_array(target, np.asarray(array), allow_pickle=False)
    return target.getvalue()


def deterministic_npz_bytes(spec: Mapping[str, Any], z_data: np.ndarray) -> bytes:
    """Create a NumPy-compatible archive with stable member bytes and metadata."""

    members = {
        "model_name.npy": _npy_bytes(np.array([spec["family"]], dtype="<U32")),
        "x_size_m.npy": _npy_bytes(np.array([spec["x_size_m"]], dtype=np.float64)),
        "y_size_m.npy": _npy_bytes(np.array([spec["y_size_m"]], dtype=np.float64)),
        "z_data.npy": _npy_bytes(np.asarray(z_data, dtype=np.float64)),
        "z_unit.npy": _npy_bytes(np.array([spec["unit"]], dtype="<U8")),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, members[name])
    return output.getvalue()


def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "PREPARE.WRITE_FAILED",
                    "",
                    f"could not create campaign file {path.name!r}: {exc}",
                )
            ]
        ) from exc


def _sha256_size(content: bytes) -> tuple[str, int]:
    return hashlib.sha256(content).hexdigest(), len(content)


def _artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    media_type: str,
    relative_uri: str,
    content: bytes,
    created_at: str,
    role: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    digest, size = _sha256_size(content)
    return {
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "media_type": media_type,
        "relative_uri": relative_uri,
        "sha256": digest,
        "size_bytes": size,
        "created_at": created_at,
        "producer": {"name": "spmkit-validation", "version": GENERATOR_VERSION},
        "regenerable": True,
        "generation_command": [
            "spmkit-validation",
            "campaign",
            "prepare-synthetic-roughness",
        ],
        "source_artifact_ids": sources or [],
        "scientific_role": role,
        "contains_sensitive_data": False,
        "limitations": ["Synthetic PHASE_01C artifact; contains no instrument data."],
    }


def _measurands() -> list[dict[str, str]]:
    descriptions = {
        "Sa": "Arithmetic mean absolute height deviation from the mean plane.",
        "Sq": "Root mean square height deviation from the mean plane.",
        "Sz": "Peak-to-valley height range.",
    }
    quantities = {
        "Sa": "arithmetical mean height deviation",
        "Sq": "root mean square height deviation",
        "Sz": "maximum surface height",
    }
    return [
        {
            "measurand_id": name,
            "canonical_unit": "m",
            "physical_quantity": quantities[name],
            "description": descriptions[name],
        }
        for name in MEASURANDS
    ]


def _reference(family: str, evidence_id: str, datasets: list[str]) -> dict[str, Any]:
    formulas = {
        "flat": "z=0 implies Sa=Sq=Sz=0",
        "checkerboard": "balanced {-A,+A}: Sa=A, Sq=A, Sz=2A",
        "four-level": "balanced {-3A,-A,+A,+3A}: Sa=2A, Sq=sqrt(5)A, Sz=6A",
    }
    return {
        "reference_id": f"reference.analytical.{family}",
        "reference_type": "ANALYTICAL_REFERENCE",
        "name": f"Closed-form {family} roughness reference",
        "version": "0.1.0",
        "producer": {
            "name": "spmkit-validation synthetic protocol",
            "is_third_party": False,
            "operator_ids": ["party.protocol.author"],
        },
        "method": formulas[family],
        "independence_justification": {
            "rationale": (
                "Closed-form values and a local direct discrete self-check are derived "
                "before SUT execution; this is not a third-party reference."
            ),
            "shared_algorithms": ["Definitions of Sa, Sq and Sz"],
            "shared_formulas": [formulas[family]],
            "shared_libraries": [
                "Python math for the analytical reference",
                "NumPy only for synthetic array storage",
            ],
            "shared_datasets": datasets,
            "shared_authors": ["PHASE_01C protocol author"],
            "circularity_risks": [
                "Protocol and analytical reference share authorship; no SUT outputs are inputs."
            ],
            "independence_assessment": "NOT_INDEPENDENT",
        },
        "shared_dependencies": {
            "software": ["IEEE-754 binary64 arithmetic"],
            "data": datasets,
            "methods": ["Definitions of Sa, Sq and Sz"],
            "notes": ["No SPM-Kit code or output calculates reference values."],
        },
        "known_limitations": [
            "Synthetic analytical reference only; no third-party or physical validation."
        ],
        "evidence_ids": [evidence_id],
    }


def _json_artifact(
    root: Path,
    relative_uri: str,
    document: Mapping[str, Any],
    *,
    artifact_id: str,
    artifact_type: str,
    created_at: str,
    role: str,
    sources: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    content = canonical_bundle_bytes(document)
    path = root / relative_uri
    _write_exclusive(path, content)
    return path, _artifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        media_type="application/json",
        relative_uri=relative_uri,
        content=content,
        created_at=created_at,
        role=role,
        sources=sources,
    )


def prepare_synthetic_roughness_campaign(
    output_dir: str | Path,
    *,
    created_at: str = DEFAULT_CREATED_AT,
    predeclared_at: str = DEFAULT_PREDECLARED_AT,
    generator_commit: str | None = None,
    sut_commit: str = DEFAULT_SUT_COMMIT,
    sut_version: str = DEFAULT_SUT_VERSION,
) -> PreparedSyntheticCampaign:
    """Prepare and validate the six-case DRAFT without invoking SPM-Kit."""

    root = Path(output_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "PREPARE.OUTPUT_DIRECTORY_FAILED",
                    "/output_dir",
                    str(exc),
                )
            ]
        ) from exc

    evidence: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    truth_records: list[dict[str, Any]] = []
    input_ids: list[str] = []
    for spec in CASE_SPECS:
        z_data = surface_array(spec)
        truth_records.append(ground_truth_record(spec, z_data))
        content = deterministic_npz_bytes(spec, z_data)
        digest, size = _sha256_size(content)
        input_uri = f"inputs/{spec['case_id']}.npz"
        _write_exclusive(root / input_uri, content)
        input_id = f"artifact.input.{spec['case_id']}"
        manifest_id = f"artifact.generator-manifest.{spec['case_id']}"
        input_ids.append(input_id)
        manifest = {
            "manifest_version": "0.1.0",
            "case_id": spec["case_id"],
            "generator": {
                "name": "spmkit-validation deterministic synthetic roughness generator",
                "version": GENERATOR_VERSION,
                "commit": generator_commit,
            },
            "command": [
                "spmkit-validation",
                "campaign",
                "prepare-synthetic-roughness",
                "--output-dir",
                ".",
            ],
            "family": spec["family"],
            "seed": spec["seed"],
            "shape": spec["shape"],
            "dtype": spec["dtype"],
            "unit": spec["unit"],
            "amplitude": spec["amplitude"],
            "format": "NumPy NPZ with deterministic ZIP metadata",
            "sha256": digest,
            "size_bytes": size,
        }
        manifest_path, manifest_artifact = _json_artifact(
            root,
            f"generator-manifests/{spec['case_id']}.json",
            manifest,
            artifact_id=manifest_id,
            artifact_type="MANIFEST",
            created_at=created_at,
            role="PROVENANCE",
        )
        del manifest_path
        manifest_artifact["external_schema"] = {
            "name": "spmkit-validation.synthetic-generator-manifest",
            "version": "0.1.0",
        }
        evidence.extend(
            [
                manifest_artifact,
                _artifact(
                    artifact_id=input_id,
                    artifact_type="INPUT",
                    media_type="application/octet-stream",
                    relative_uri=input_uri,
                    content=content,
                    created_at=created_at,
                    role="INPUT_DATA",
                    sources=[manifest_id],
                ),
            ]
        )
        datasets.append(
            {
                "dataset_id": spec["dataset_id"],
                "title": f"Synthetic {spec['family']} {spec['resolution']}x{spec['resolution']}",
                "role": "VERIFICATION",
                "source_type": "SYNTHETIC",
                "provenance": {
                    "producer": "spmkit-validation deterministic generator",
                    "method": (
                        "Declarative analytical pattern serialized as deterministic NumPy NPZ"
                    ),
                    "created_at": created_at,
                    "source_artifact_ids": [manifest_id, input_id],
                },
                "license": "CC0-1.0",
                "checksum": digest,
                "format": {
                    "media_type": "application/octet-stream",
                    "specification": "NumPy NPZ accepted by the public SPM-Kit loader",
                },
                "access_policy": {"access_level": "PUBLIC", "access_state": "OPENED"},
                "locator": input_uri,
                "public_metadata": {
                    "synthetic": True,
                    "family": spec["family"],
                    "shape": spec["shape"],
                    "dtype": spec["dtype"],
                    "unit": spec["unit"],
                    "amplitude": spec["amplitude"],
                    "seed": spec["seed"],
                },
                "limitations": [
                    "Small deterministic synthetic phantom with no instrument effects."
                ],
            }
        )

    ground_truth_document = {
        "ground_truth_version": "0.1.0",
        "campaign_id": CAMPAIGN_ID,
        "derived_before_freeze": True,
        "uses_sut_outputs": False,
        "reference_classification": "ANALYTICAL_REFERENCE_NOT_THIRD_PARTY",
        "cases": truth_records,
        "status": "PASS",
    }
    ground_truth_id = "artifact.reference.ground-truth"
    ground_truth_path, ground_truth_artifact = _json_artifact(
        root,
        "ground-truth.json",
        ground_truth_document,
        artifact_id=ground_truth_id,
        artifact_type="REFERENCE_EXPORT",
        created_at=predeclared_at,
        role="REFERENCE_VALUE",
        sources=input_ids,
    )
    evidence.append(ground_truth_artifact)

    tolerance_document = derive_tolerance_budget(
        CASE_SPECS, tuple(truth_records), predeclared_at
    )
    tolerance_path, tolerance_artifact = _json_artifact(
        root,
        "tolerance-budget.json",
        tolerance_document,
        artifact_id="artifact.protocol.tolerance-budget",
        artifact_type="TABLE",
        created_at=predeclared_at,
        role="PROVENANCE",
        sources=[ground_truth_id],
    )
    evidence.append(tolerance_artifact)

    decisions = {
        "decision_version": "0.1.0",
        "campaign_id": CAMPAIGN_ID,
        "generator_candidate": {
            "name": "spmkit-phantoms",
            "commit": "ab994cea1da484247a36c304be03da746fa059df",
            "used": False,
            "reason": (
                "Public API lacks checkerboard and balanced four-level families; "
                "candidate working tree was already dirty."
            ),
        },
        "selected_format": "NumPy NPZ supported by the public SPM-Kit loader",
        "leveling": "none",
        "network": "disabled by protocol",
        "real_data": False,
    }
    decision_path, decision_artifact = _json_artifact(
        root,
        "design-decisions.json",
        decisions,
        artifact_id="artifact.protocol.design-decisions",
        artifact_type="REPORT",
        created_at=predeclared_at,
        role="PROVENANCE",
    )
    evidence.append(decision_artifact)

    tolerance_by_id = {
        record["tolerance_id"]: record for record in tolerance_document["records"]
    }
    cases: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        tolerances: list[dict[str, Any]] = []
        for measurand in MEASURANDS:
            budget = tolerance_by_id[f"tolerance.{spec['case_id']}.{measurand}"]
            tolerance = {
                "tolerance_id": budget["tolerance_id"],
                "measurand_id": measurand,
                "type": budget["type"],
                "absolute": budget["absolute"],
                "unit": "m",
                "justification": "Predeclared forward float64 error budget with safety factor.",
                "source": "artifact.protocol.tolerance-budget",
            }
            if budget["type"] == "ABSOLUTE_AND_RELATIVE":
                tolerance["relative"] = budget["relative"]
            tolerances.append(tolerance)
        cases.append(
            {
                "case_id": spec["case_id"],
                "dataset_id": spec["dataset_id"],
                "reference_id": spec["reference_id"],
                "purpose": "VERIFICATION",
                "operation": {
                    "name": "spmkit analyze",
                    "version": "public-cli-v0.1.5.dev0",
                    "parameters": {
                        "channel": "Z-Axis",
                        "leveling": "none",
                        "preprocessing": "none",
                    },
                },
                "input_selector": {"selector_type": "FULL_DATASET"},
                "preprocessing": [],
                "measurands": _measurands(),
                "tolerances": tolerances,
                "expected_units": dict.fromkeys(MEASURANDS, "m"),
                "acceptance_policy": {
                    "aggregation": "ALL_MEASURANDS_MUST_PASS",
                    "on_evaluation_error": "ERROR",
                    "on_missing_result": "NOT_EVALUATED",
                },
                "predeclared_at": predeclared_at,
                "case_status": "ACTIVE",
            }
        )

    references = [
        _reference(
            family,
            ground_truth_id,
            [spec["dataset_id"] for spec in CASE_SPECS if spec["family"] == family],
        )
        for family in ("flat", "checkerboard", "four-level")
    ]
    bundle: dict[str, Any] = {
        "schema_version": "0.1.0",
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "title": "Deterministic synthetic Sa/Sq/Sz recovery",
            "objective": (
                "Evaluate public black-box recovery of Sa, Sq and Sz on six small "
                "analytical phantoms."
            ),
            "protocol_version": PROTOCOL_VERSION,
            "status": "DRAFT",
            "created_at": created_at,
            "frozen_at": None,
            "system_under_test": {
                "package_name": "spmkit",
                "version": sut_version,
                "git_commit": sut_commit,
                "repository": "https://github.com/kegouro/spmkit.git",
                "ref": "chore/workspace-sanitize",
                "platform": "black-box-python-3.12",
                "environment_id": "environment.phase01c.authoritative",
            },
            "intended_validation_level": "LEVEL 2 — NUMERICALLY_VERIFIED",
            "determinism_requirement": "NUMERICALLY_REPEATABLE",
            "limitations": [
                "Scope is limited to Sa, Sq and Sz on six small synthetic NumPy phantoms.",
                "Analytical references are not third-party independent.",
                "No real, physical, cross-validation or blind data are included.",
            ],
            "responsible_parties": [
                {
                    "party_id": "party.protocol.author",
                    "name": "PHASE_01C protocol author",
                    "role": "protocol author and synthetic reference producer",
                }
            ],
        },
        "datasets": datasets,
        "references": references,
        "cases": cases,
        "runs": [],
        "comparisons": [],
        "evidence": sorted(evidence, key=lambda item: item["artifact_id"]),
        "claims": [],
    }
    assert_valid_bundle(bundle)
    bundle_path = root / "draft-bundle.json"
    _write_exclusive(bundle_path, canonical_bundle_bytes(bundle))
    return PreparedSyntheticCampaign(
        output_dir=root,
        bundle_path=bundle_path,
        ground_truth_path=ground_truth_path,
        tolerance_budget_path=tolerance_path,
        decision_path=decision_path,
        bundle=bundle,
    )
