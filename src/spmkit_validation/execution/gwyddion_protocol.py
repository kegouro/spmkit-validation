"""Pre-freeze Gwyddion-library cross-validation protocol preparation."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from spmkit_validation.adapters.gwyddion.format import (
    GWYFILE_VERSION,
    deterministic_gwy_bytes,
)
from spmkit_validation.lifecycle import canonical_bundle_bytes
from spmkit_validation.schemas import assert_valid_bundle

from .cumulative_protocol import (
    SOFTWARE_CASE_ID,
    PreparedCumulativeCampaign,
    prepare_cumulative_verification_campaign,
)
from .ground_truth import MEASURANDS, ground_truth_record
from .issues import (
    CampaignExecutionError,
    CampaignExecutionIssueCategory,
    execution_issue,
)
from .synthetic_roughness import (
    CASE_SPECS,
    DEFAULT_CREATED_AT,
    DEFAULT_PREDECLARED_AT,
    DEFAULT_SUT_COMMIT,
    DEFAULT_SUT_VERSION,
    _artifact,
    _write_exclusive,
    surface_array,
)

CROSS_CAMPAIGN_ID = "campaign.gwyddion-cross-validation.synthetic-roughness.v0.1"
EXTERNAL_REFERENCE_ID = "reference.external.gwyddion-library.roughness"
ATTEMPT_ID = "phase01e.install-and-resume.001"
GWYDDION_VERSION = "2.71"
HELPER_VERSION = "0.1.0"
GWYFILE_WHEEL_SHA256 = "6a68c5c748f0390cce1e0d6b8d622fa7f267ef94d47aa5fd7eb95abfeb4256c1"

FORMAT_ARTIFACT_ID = "artifact.protocol.gwy-format-contract"
TOLERANCE_ARTIFACT_ID = "artifact.protocol.tolerance-budget"
INDEPENDENCE_ARTIFACT_ID = "artifact.reference.independence-assessment"
GWYDDION_IDENTITY_ARTIFACT_ID = "artifact.reference.gwyddion-identity"
VIABILITY_ARTIFACT_ID = "artifact.reference.installed-viability"
HELPER_SOURCE_ARTIFACT_ID = "artifact.reference.helper-source"
HELPER_BINARY_ARTIFACT_ID = "artifact.reference.helper-binary"
HELPER_BUILD_ARTIFACT_ID = "artifact.reference.helper-build"
GWYFILE_WHEEL_ARTIFACT_ID = "artifact.reference.gwyfile-wheel"


@dataclass(frozen=True, slots=True)
class PreparedGwyddionCrossValidationCampaign:
    """Validated DRAFT and all local pre-freeze reference artifacts."""

    output_dir: Path
    bundle_path: Path
    ground_truth_path: Path
    tolerance_budget_path: Path
    format_contract_path: Path
    independence_assessment_path: Path
    helper_binary_path: Path
    gwyfile_wheel_path: Path
    bundle: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.bundle["campaign"]["campaign_id"],
            "status": self.bundle["campaign"]["status"],
            "bundle_path": self.bundle_path.name,
            "case_count": len(self.bundle["cases"]),
            "software_case_count": 1,
            "scientific_case_count": 6,
            "external_reference_id": EXTERNAL_REFERENCE_ID,
            "gwyddion_version": GWYDDION_VERSION,
        }


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GWYDDION_PROTOCOL.INVALID_RECORD",
                    f"/{label}",
                    str(exc),
                )
            ]
        ) from exc
    if not isinstance(value, dict):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GWYDDION_PROTOCOL.INVALID_RECORD",
                    f"/{label}",
                    "record must be a JSON object",
                )
            ]
        )
    return value


def _checked_file(path: str | Path, label: str) -> tuple[Path, bytes]:
    try:
        resolved = Path(path).resolve(strict=True)
        mode = resolved.stat().st_mode
        content = resolved.read_bytes()
    except OSError as exc:
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.FILESYSTEM,
                    "GWYDDION_PROTOCOL.FILE_UNAVAILABLE",
                    f"/{label}",
                    str(exc),
                )
            ]
        ) from exc
    if not stat.S_ISREG(mode):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GWYDDION_PROTOCOL.NOT_REGULAR_FILE",
                    f"/{label}",
                    "path must resolve to a regular file",
                )
            ]
        )
    return resolved, content


def _json_file(path: Path, document: Mapping[str, Any]) -> bytes:
    content = canonical_bundle_bytes(document)
    _write_exclusive(path, content)
    return content


def _copy_file(source: Path, destination: Path) -> bytes:
    content = source.read_bytes()
    _write_exclusive(destination, content)
    return content


def _evidence(
    *,
    artifact_id: str,
    artifact_type: str,
    media_type: str,
    relative_uri: str,
    content: bytes,
    created_at: str,
    role: str,
    sources: list[str] | None = None,
    regenerable: bool = True,
    command: list[str] | None = None,
    external_schema: dict[str, str] | None = None,
) -> dict[str, Any]:
    artifact = _artifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        media_type=media_type,
        relative_uri=relative_uri,
        content=content,
        created_at=created_at,
        role=role,
        sources=sources,
    )
    artifact["producer"] = {
        "name": "spmkit-validation",
        "version": importlib.metadata.version("spmkit-validation"),
    }
    artifact["regenerable"] = regenerable
    artifact["generation_command"] = command or []
    if regenerable and not artifact["generation_command"]:
        artifact["generation_command"] = [
            "spmkit-validation",
            "campaign",
            "prepare-gwyddion-cross-validation",
        ]
    if external_schema is not None:
        artifact["external_schema"] = external_schema
    return artifact


def _cross_tolerance_budget(predeclared_at: str) -> dict[str, Any]:
    epsilon = float(np.finfo(np.float64).eps)
    records: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        array = surface_array(spec)
        count = int(array.size)
        scale = max(float(np.max(np.abs(array))), 1e-9)
        absolute = float(128 * count * epsilon * scale + 2 * epsilon * scale)
        relative = float(128 * count * epsilon + 2 * epsilon)
        for measurand in MEASURANDS:
            record: dict[str, Any] = {
                "absolute": absolute,
                "case_id": spec["case_id"],
                "derivation": {
                    "accumulation_safety_factor": 128,
                    "binary64_machine_epsilon": epsilon,
                    "element_count": count,
                    "format_storage": "little-endian IEEE-754 binary64",
                    "gwyddion_json_precision": "17 significant decimal digits",
                    "parser": "strict JSON numeric parser",
                    "scale_bound_m": scale,
                    "unit_conversion": "none",
                },
                "measurand_id": measurand,
                "tolerance_id": f"tolerance.cross.{spec['case_id']}.{measurand}",
                "type": "ABSOLUTE" if spec["family"] == "flat" else "ABSOLUTE_AND_RELATIVE",
                "unit": "m",
            }
            if record["type"] == "ABSOLUTE_AND_RELATIVE":
                record["relative"] = relative
            records.append(record)
    return {
        "budget_version": "0.1.0",
        "campaign_id": CROSS_CAMPAIGN_ID,
        "derived_without_observed_cross_differences": True,
        "forbidden_inputs": [
            "installed viability-probe numerical differences",
            "PHASE_01C observed differences",
            "PHASE_01D observed differences",
            "authoritative SPM-Kit outputs",
            "authoritative Gwyddion outputs",
        ],
        "predeclared_at": predeclared_at,
        "records": records,
        "status": "PREDECLARED",
    }


def _independence_assessment(
    identity: Mapping[str, Any],
    helper_source_sha256: str,
    helper_binary_sha256: str,
) -> dict[str, Any]:
    return {
        "assessment": "INDEPENDENT",
        "attempt_id": ATTEMPT_ID,
        "authors_shared": [],
        "circularity_risks": [
            "The harness authors the execution wrapper and predeclares the shared formulas.",
            (
                "Sa is accumulated by the wrapper over GwyDataField values; mean, Sq, min "
                "and max use public Gwyddion operations."
            ),
            "Both programs necessarily read the same frozen synthetic inputs.",
        ],
        "code_shared_with_harness": False,
        "code_shared_with_spmkit": False,
        "datasets_shared": [spec["dataset_id"] for spec in CASE_SPECS],
        "evidence_ids": [
            GWYDDION_IDENTITY_ARTIFACT_ID,
            VIABILITY_ARTIFACT_ID,
            HELPER_SOURCE_ARTIFACT_ID,
            HELPER_BINARY_ARTIFACT_ID,
            HELPER_BUILD_ARTIFACT_ID,
        ],
        "execution_method": "Separate native headless process using public Gwyddion libraries",
        "execution_wrapper_author": "SPMKit validation harness",
        "formula_definition_shared": True,
        "formulas_shared": [
            "mean=average(z)",
            "Sa=average(abs(z-mean))",
            "Sq=sqrt(average((z-mean)^2))",
            "Sz=max(z)-min(z)",
        ],
        "gwyddion_version": identity["reported_version"],
        "helper_binary_sha256": helper_binary_sha256,
        "helper_source_sha256": helper_source_sha256,
        "libraries_shared": ["system IEEE-754 binary64 arithmetic"],
        "limitations": [
            "Gwyddion-library external reference, not a Gwyddion GUI result.",
            "The harness wrapper implements declared Sa accumulation over Gwyddion-loaded values.",
            "No physical or real-data validation is implied.",
        ],
        "producer_is_third_party": True,
        "producer_name": "Gwyddion project",
        "producer_organization": "Gwyddion upstream project",
        "reference_implementation_shared": False,
        "scientific_code_shared_with_sut": False,
        "standards_shared": ["Sa, Sq and Sz mathematical definitions", "SI metre"],
        "tolerances_derived_from_observed_cross_differences": False,
        "wrapper_code_shared_with_sut": False,
    }


def _external_reference(dataset_ids: list[str]) -> dict[str, Any]:
    return {
        "reference_id": EXTERNAL_REFERENCE_ID,
        "reference_type": "EXTERNAL_SOFTWARE_REFERENCE",
        "name": "Gwyddion-library external roughness reference",
        "version": GWYDDION_VERSION,
        "producer": {
            "name": "Gwyddion project",
            "organization": "Gwyddion upstream project",
            "is_third_party": True,
            "operator_ids": ["party.reference.wrapper-operator"],
        },
        "method": (
            "Separate headless native helper: Gwyddion 2.71 loads the frozen GWY channel; "
            "public GwyDataField operations supply mean, RMS, min and max; the frozen wrapper "
            "accumulates declared Sa; no preprocessing is applied."
        ),
        "independence_justification": {
            "rationale": (
                "Third-party loaders, data structures and statistical operations execute in "
                "a process separate from the SUT; no SUT code or output is read."
            ),
            "shared_algorithms": [],
            "shared_formulas": ["Declared mathematical definitions of Sa, Sq and Sz"],
            "shared_libraries": ["system IEEE-754 binary64 runtime"],
            "shared_datasets": dataset_ids,
            "shared_authors": [],
            "circularity_risks": [
                "Harness-authored wrapper implements Sa accumulation over Gwyddion-loaded data."
            ],
            "independence_assessment": "INDEPENDENT",
        },
        "shared_dependencies": {
            "software": ["system C runtime"],
            "data": dataset_ids,
            "methods": ["Sa, Sq and Sz mathematical definitions"],
            "notes": [
                "No scientific code, imports or observed outputs are shared with SPM-Kit."
            ],
        },
        "known_limitations": [
            "Gwyddion-library external reference rather than a GUI-produced result.",
            "Synthetic binary64 full-field scope only; no physical validation.",
        ],
        "evidence_ids": [
            GWYDDION_IDENTITY_ARTIFACT_ID,
            INDEPENDENCE_ARTIFACT_ID,
            VIABILITY_ARTIFACT_ID,
            HELPER_SOURCE_ARTIFACT_ID,
            HELPER_BINARY_ARTIFACT_ID,
            HELPER_BUILD_ARTIFACT_ID,
        ],
    }


def prepare_gwyddion_cross_validation_campaign(
    output_dir: str | Path,
    *,
    sut_repository: str | Path,
    gwyddion_identity: str | Path,
    installed_viability: str | Path,
    helper_source: str | Path,
    helper_binary: str | Path,
    helper_build_record: str | Path,
    gwyfile_wheel: str | Path,
    created_at: str = DEFAULT_CREATED_AT,
    predeclared_at: str = DEFAULT_PREDECLARED_AT,
    generator_commit: str | None = None,
    sut_commit: str = DEFAULT_SUT_COMMIT,
    sut_version: str = DEFAULT_SUT_VERSION,
) -> PreparedGwyddionCrossValidationCampaign:
    """Create seven DRAFT cases without running either authoritative producer."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=False)
    identity_path, identity_bytes = _checked_file(gwyddion_identity, "gwyddion_identity")
    viability_path, viability_bytes = _checked_file(installed_viability, "installed_viability")
    source_path, source_bytes = _checked_file(helper_source, "helper_source")
    binary_path, binary_bytes = _checked_file(helper_binary, "helper_binary")
    build_path, build_bytes = _checked_file(helper_build_record, "helper_build_record")
    wheel_path, wheel_bytes = _checked_file(gwyfile_wheel, "gwyfile_wheel")
    identity = _load_object(identity_path, "gwyddion_identity")
    viability = _load_object(viability_path, "installed_viability")
    helper_build = _load_object(build_path, "helper_build_record")
    source_sha256 = _hash(source_bytes)
    binary_sha256 = _hash(binary_bytes)
    if (
        identity.get("reported_version") != GWYDDION_VERSION
        or identity.get("producer_is_third_party") is not True
        or viability.get("status") != "PASS_INSTALLED_REFERENCE"
        or viability.get("tolerances_derived_from_probe") is not False
        or helper_build.get("source_sha256") != source_sha256
        or helper_build.get("binary_sha256") != binary_sha256
        or _hash(wheel_bytes) != GWYFILE_WHEEL_SHA256
        or importlib.metadata.version("gwyfile") != GWYFILE_VERSION
    ):
        raise CampaignExecutionError(
            [
                execution_issue(
                    CampaignExecutionIssueCategory.INPUT,
                    "GWYDDION_PROTOCOL.IDENTITY_MISMATCH",
                    "",
                    "installed identity, viability, helper or pinned gwyfile wheel mismatches",
                )
            ]
        )

    with tempfile.TemporaryDirectory(prefix="spmkit-phase01e-protocol-") as temporary:
        base: PreparedCumulativeCampaign = prepare_cumulative_verification_campaign(
            Path(temporary) / "base",
            sut_repository=sut_repository,
            created_at=created_at,
            predeclared_at=predeclared_at,
            generator_commit=generator_commit,
            sut_commit=sut_commit,
            sut_version=sut_version,
        )
        base_bundle = copy.deepcopy(dict(base.bundle))
        retained_ids = {
            "artifact.reference.ground-truth",
            "artifact.software-test.pytest-entrypoint",
            "artifact.software-test.suite-archive",
            "artifact.software-test.suite-manifest",
            "artifact.software-test.wheel-policy",
        }
        retained_evidence: list[dict[str, Any]] = []
        for artifact in base_bundle["evidence"]:
            if artifact["artifact_id"] not in retained_ids:
                continue
            source = base.output_dir / artifact["relative_uri"]
            content = _copy_file(source, root / artifact["relative_uri"])
            copied = copy.deepcopy(artifact)
            copied["sha256"] = _hash(content)
            copied["size_bytes"] = len(content)
            retained_evidence.append(copied)

    ground_truth_path = root / "ground-truth.json"
    ground_truth = _load_object(ground_truth_path, "ground_truth")
    ground_truth["campaign_id"] = CROSS_CAMPAIGN_ID
    ground_truth_bytes = canonical_bundle_bytes(ground_truth)
    ground_truth_path.write_bytes(ground_truth_bytes)
    for artifact in retained_evidence:
        if artifact["artifact_id"] == "artifact.reference.ground-truth":
            artifact["sha256"] = _hash(ground_truth_bytes)
            artifact["size_bytes"] = len(ground_truth_bytes)

    input_evidence: list[dict[str, Any]] = []
    datasets_by_id = {item["dataset_id"]: item for item in base_bundle["datasets"]}
    input_contracts: list[dict[str, Any]] = []
    truth_records: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        array = surface_array(spec)
        truth_records.append(ground_truth_record(spec, array))
        content = deterministic_gwy_bytes(
            array,
            x_size_m=float(spec["x_size_m"]),
            y_size_m=float(spec["y_size_m"]),
        )
        digest = _hash(content)
        input_id = f"artifact.input.{spec['case_id']}"
        manifest_id = f"artifact.generator-manifest.{spec['case_id']}"
        input_uri = f"inputs/{spec['case_id']}.gwy"
        _write_exclusive(root / input_uri, content)
        manifest = {
            "axis_order": "ROW_Y_COLUMN_X",
            "case_id": spec["case_id"],
            "channel": 0,
            "dtype": "IEEE-754 binary64",
            "endianness": "little",
            "family": spec["family"],
            "format": "Gwyddion GWYP native container",
            "manifest_version": "0.1.0",
            "orientation": "row 0 first; column 0 first; no transpose or flip",
            "pixel_dimensions_m": [
                float(spec["y_size_m"]) / int(spec["resolution"]),
                float(spec["x_size_m"]) / int(spec["resolution"]),
            ],
            "scaling": "stored z values are SI metres without multiplier",
            "sha256": digest,
            "shape": spec["shape"],
            "size_bytes": len(content),
            "unit_lateral": "m",
            "unit_vertical": "m",
            "writer": "gwyfile",
            "writer_version": GWYFILE_VERSION,
        }
        manifest_uri = f"generator-manifests/{spec['case_id']}.json"
        manifest_bytes = _json_file(root / manifest_uri, manifest)
        input_evidence.extend(
            [
                _evidence(
                    artifact_id=manifest_id,
                    artifact_type="MANIFEST",
                    media_type="application/json",
                    relative_uri=manifest_uri,
                    content=manifest_bytes,
                    created_at=created_at,
                    role="PROVENANCE",
                    external_schema={
                        "name": "spmkit-validation.gwy-generator-manifest",
                        "version": "0.1.0",
                    },
                ),
                _evidence(
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
        dataset = datasets_by_id[spec["dataset_id"]]
        dataset.update(
            {
                "role": "CROSS_VALIDATION",
                "checksum": digest,
                "locator": input_uri,
                "format": {
                    "media_type": "application/octet-stream",
                    "specification": "Gwyddion GWYP native binary container",
                },
                "provenance": {
                    "producer": "spmkit-validation deterministic GWY generator",
                    "method": "Declared analytical pattern serialized once with gwyfile 0.3.0",
                    "created_at": created_at,
                    "source_artifact_ids": [manifest_id, input_id],
                },
                "public_metadata": {
                    "amplitude": spec["amplitude"],
                    "axis_order": "ROW_Y_COLUMN_X",
                    "channel": 0,
                    "dtype": "float64",
                    "family": spec["family"],
                    "seed": None,
                    "shape": spec["shape"],
                    "unit": "m",
                },
                "limitations": [
                    "Small deterministic synthetic GWY phantom with no instrument effects."
                ],
            }
        )
        input_contracts.append(manifest)

    ground_truth["cases"] = truth_records
    ground_truth_bytes = canonical_bundle_bytes(ground_truth)
    ground_truth_path.write_bytes(ground_truth_bytes)
    for artifact in retained_evidence:
        if artifact["artifact_id"] == "artifact.reference.ground-truth":
            artifact["sha256"] = _hash(ground_truth_bytes)
            artifact["size_bytes"] = len(ground_truth_bytes)
            artifact["source_artifact_ids"] = [
                f"artifact.input.{spec['case_id']}" for spec in CASE_SPECS
            ]

    tolerance = _cross_tolerance_budget(predeclared_at)
    tolerance_path = root / "tolerance-budget.json"
    tolerance_bytes = _json_file(tolerance_path, tolerance)
    format_contract = {
        "contract_version": "0.1.0",
        "authoritative_input_reuse": "BYTE_IDENTICAL_FILE_FOR_BOTH_PRODUCERS",
        "campaign_id": CROSS_CAMPAIGN_ID,
        "dtype": "IEEE-754 binary64",
        "endianness": "little",
        "format": "Gwyddion GWYP native binary container",
        "inputs": input_contracts,
        "orientation": "ROW_Y_COLUMN_X_NO_TRANSPOSE_NO_FLIP",
        "roundtrip_probe": {
            "authoritative_dataset": False,
            "bound_m_predeclared": 1e-22,
            "input_shape": [3, 5],
            "status": viability["status"],
            "tolerance_calibration_use": False,
            "viability_artifact_id": VIABILITY_ARTIFACT_ID,
        },
        "scaling": "SI metres without multiplier",
        "unit_lateral": "m",
        "unit_vertical": "m",
        "writer": "gwyfile",
        "writer_version": GWYFILE_VERSION,
    }
    format_path = root / "format-contract.json"
    format_bytes = _json_file(format_path, format_contract)
    independence = _independence_assessment(identity, source_sha256, binary_sha256)
    independence_path = root / "independence-assessment.json"
    independence_bytes = _json_file(independence_path, independence)

    frozen_files = [
        (
            GWYDDION_IDENTITY_ARTIFACT_ID,
            "REFERENCE_EXPORT",
            "application/json",
            "reference/gwyddion-identity.json",
            identity_bytes,
            "PROVENANCE",
            False,
        ),
        (
            VIABILITY_ARTIFACT_ID,
            "REFERENCE_EXPORT",
            "application/json",
            "reference/viability-probe-installed.json",
            viability_bytes,
            "PROVENANCE",
            False,
        ),
        (
            HELPER_SOURCE_ARTIFACT_ID,
            "INPUT",
            "text/x-c",
            "reference/helper/gwyddion_roughness_reference.c",
            source_bytes,
            "PROVENANCE",
            True,
        ),
        (
            HELPER_BINARY_ARTIFACT_ID,
            "INPUT",
            "application/octet-stream",
            "reference/helper/spmkit-gwyddion-roughness-reference",
            binary_bytes,
            "PROVENANCE",
            True,
        ),
        (
            HELPER_BUILD_ARTIFACT_ID,
            "MANIFEST",
            "application/json",
            "reference/helper/helper-build.json",
            build_bytes,
            "PROVENANCE",
            True,
        ),
        (
            GWYFILE_WHEEL_ARTIFACT_ID,
            "INPUT",
            "application/octet-stream",
            "dependencies/gwyfile-0.3.0-py3-none-any.whl",
            wheel_bytes,
            "PROVENANCE",
            False,
        ),
    ]
    external_evidence: list[dict[str, Any]] = []
    for artifact_id, kind, media, uri, content, role, executable in frozen_files:
        _write_exclusive(root / uri, content)
        if executable:
            os.chmod(root / uri, 0o755 if artifact_id == HELPER_BINARY_ARTIFACT_ID else 0o644)
        external_evidence.append(
            _evidence(
                artifact_id=artifact_id,
                artifact_type=kind,
                media_type=media,
                relative_uri=uri,
                content=content,
                created_at=predeclared_at,
                role=role,
                regenerable=False,
                command=[],
                external_schema=(
                    {
                        "name": "spmkit-validation.gwyddion-helper-build",
                        "version": "0.1.0",
                    }
                    if kind == "MANIFEST"
                    else None
                ),
            )
        )
    protocol_evidence = [
        _evidence(
            artifact_id=TOLERANCE_ARTIFACT_ID,
            artifact_type="TABLE",
            media_type="application/json",
            relative_uri=tolerance_path.name,
            content=tolerance_bytes,
            created_at=predeclared_at,
            role="PROVENANCE",
            sources=[FORMAT_ARTIFACT_ID],
        ),
        _evidence(
            artifact_id=FORMAT_ARTIFACT_ID,
            artifact_type="REPORT",
            media_type="application/json",
            relative_uri=format_path.name,
            content=format_bytes,
            created_at=predeclared_at,
            role="PROVENANCE",
            sources=[VIABILITY_ARTIFACT_ID, GWYFILE_WHEEL_ARTIFACT_ID],
        ),
        _evidence(
            artifact_id=INDEPENDENCE_ARTIFACT_ID,
            artifact_type="REPORT",
            media_type="application/json",
            relative_uri=independence_path.name,
            content=independence_bytes,
            created_at=predeclared_at,
            role="PROVENANCE",
            sources=[
                GWYDDION_IDENTITY_ARTIFACT_ID,
                HELPER_SOURCE_ARTIFACT_ID,
                HELPER_BINARY_ARTIFACT_ID,
                HELPER_BUILD_ARTIFACT_ID,
            ],
        ),
    ]

    bundle = base_bundle
    bundle["campaign"].update(
        {
            "campaign_id": CROSS_CAMPAIGN_ID,
            "title": "Independent Gwyddion-library synthetic roughness cross-validation",
            "objective": (
                "Compare six fresh public SPM-Kit CLI results with six separate Gwyddion 2.71 "
                "library-reference results under one frozen binary64 GWY protocol."
            ),
            "status": "DRAFT",
            "frozen_at": None,
            "intended_validation_level": "LEVEL 3 — CROSS_VALIDATED",
            "determinism_requirement": "NUMERICALLY_REPEATABLE",
            "limitations": [
                "Scope is Sa, Sq and Sz on six small synthetic GWY fields only.",
                "The Gwyddion-library wrapper is harness-authored and explicitly frozen.",
                "No leveling, filtering, masking, physical data, real data or holdouts.",
                "No authenticity, signature, physical validation or LEVEL 5 claim is made.",
            ],
            "responsible_parties": [
                {
                    "party_id": "party.protocol.author",
                    "name": "PHASE_01E protocol author",
                    "role": "protocol author and analytical-control producer",
                },
                {
                    "party_id": "party.reference.wrapper-operator",
                    "name": "PHASE_01E automated reference operator",
                    "role": "operator of frozen third-party-library wrapper",
                },
            ],
        }
    )
    software_dataset_id = next(
        item for item in datasets_by_id if item.startswith("dataset.software")
    )
    bundle["datasets"] = [
        *[datasets_by_id[spec["dataset_id"]] for spec in CASE_SPECS],
        datasets_by_id[software_dataset_id],
    ]
    tolerance_by_id = {item["tolerance_id"]: item for item in tolerance["records"]}
    for case in bundle["cases"]:
        if case["case_id"] == SOFTWARE_CASE_ID:
            case["campaign_id"] = CROSS_CAMPAIGN_ID if "campaign_id" in case else None
            if case.get("campaign_id") is None:
                case.pop("campaign_id", None)
            continue
        case["reference_id"] = EXTERNAL_REFERENCE_ID
        case["purpose"] = "CROSS_VALIDATION"
        case["operation"]["parameters"].update(
            {
                "format": "GWY",
                "external_channel": 0,
                "filtering": "none",
                "masking": "none",
                "roi": "full-field",
            }
        )
        case["tolerances"] = []
        for measurand in MEASURANDS:
            record = tolerance_by_id[f"tolerance.cross.{case['case_id']}.{measurand}"]
            item = {
                "tolerance_id": record["tolerance_id"],
                "measurand_id": measurand,
                "type": record["type"],
                "absolute": record["absolute"],
                "unit": "m",
                "justification": "Frozen binary64 format and accumulation forward-error bound.",
                "source": TOLERANCE_ARTIFACT_ID,
            }
            if record["type"] == "ABSOLUTE_AND_RELATIVE":
                item["relative"] = record["relative"]
            case["tolerances"].append(item)
    dataset_ids = [spec["dataset_id"] for spec in CASE_SPECS]
    bundle["references"] = [*base_bundle["references"], _external_reference(dataset_ids)]
    bundle["evidence"] = sorted(
        [
            *retained_evidence,
            *input_evidence,
            *external_evidence,
            *protocol_evidence,
        ],
        key=lambda item: item["artifact_id"],
    )
    bundle["runs"] = []
    bundle["comparisons"] = []
    bundle["claims"] = []
    assert_valid_bundle(bundle)
    bundle_path = root / "draft-bundle.json"
    _write_exclusive(bundle_path, canonical_bundle_bytes(bundle))
    return PreparedGwyddionCrossValidationCampaign(
        output_dir=root,
        bundle_path=bundle_path,
        ground_truth_path=ground_truth_path,
        tolerance_budget_path=tolerance_path,
        format_contract_path=format_path,
        independence_assessment_path=independence_path,
        helper_binary_path=root / "reference/helper/spmkit-gwyddion-roughness-reference",
        gwyfile_wheel_path=root / "dependencies/gwyfile-0.3.0-py3-none-any.whl",
        bundle=bundle,
    )
