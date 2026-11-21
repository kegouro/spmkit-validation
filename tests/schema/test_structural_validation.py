from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from spmkit_validation.schemas import (
    IssueCategory,
    ValidationBundleIOError,
    ValidationSchemaError,
    assert_valid_bundle,
    load_validation_bundle,
    validate_schema,
)

SCHEMA_DIRECTORY = Path(__file__).parents[2] / "schemas/v0.1"


def _codes(issues: tuple[Any, ...]) -> set[str]:
    return {issue.code for issue in issues}


def test_minimal_bundle_is_valid(minimal_bundle: dict[str, Any]) -> None:
    assert_valid_bundle(minimal_bundle)


def test_complete_bundle_is_valid(complete_bundle: dict[str, Any]) -> None:
    assert_valid_bundle(complete_bundle)


def test_every_schema_is_valid_json_and_all_refs_resolve(complete_bundle: dict[str, Any]) -> None:
    documents = []
    for schema_path in sorted(SCHEMA_DIRECTORY.glob("*.schema.json")):
        with schema_path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        Draft202012Validator.check_schema(document)
        documents.append(document)

    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents
    )
    root = next(
        document
        for document in documents
        if document["$id"] == "urn:spmkit-validation:schema:v0.1:validation-bundle"
    )
    assert list(Draft202012Validator(root, registry=registry).iter_errors(complete_bundle)) == []


def test_schema_version_incompatible(minimal_bundle: dict[str, Any]) -> None:
    minimal_bundle["schema_version"] = "0.2.0"
    issues = validate_schema(minimal_bundle)
    assert "SCHEMA.VERSION_INCOMPATIBLE" in _codes(issues)
    assert all(issue.category is IssueCategory.SCHEMA for issue in issues)


def test_unix_absolute_artifact_path_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["evidence"][0]["relative_uri"] = "/users/example/private.json"
    issues = validate_schema(complete_bundle)
    assert "SCHEMA.PATTERN" in _codes(issues)
    assert any(issue.path == "/evidence/0/relative_uri" for issue in issues)


def test_windows_absolute_artifact_path_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["evidence"][0]["relative_uri"] = "C:\\Users\\example\\private.json"
    issues = validate_schema(complete_bundle)
    assert "SCHEMA.PATTERN" in _codes(issues)
    assert any(issue.path == "/evidence/0/relative_uri" for issue in issues)


def test_sealed_blind_holdout_with_direct_locator_is_rejected(
    complete_bundle: dict[str, Any],
) -> None:
    dataset = complete_bundle["datasets"][0]
    dataset["role"] = "BLIND_HOLDOUT"
    dataset["sealed_id"] = "sealed.synthetic.opaque"
    dataset["access_policy"] = {"access_level": "SEALED", "access_state": "SEALED"}
    dataset["public_metadata"] = {}
    issues = validate_schema(complete_bundle)
    assert "SCHEMA.FORBIDDEN_PROPERTY" in _codes(issues)


def test_case_without_predeclared_tolerance_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["cases"][0]["tolerances"] = []
    assert "SCHEMA.MIN_ITEMS" in _codes(validate_schema(complete_bundle))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_numbers_are_rejected_on_load(tmp_path: Path, constant: str) -> None:
    path = tmp_path / "invalid-number.json"
    path.write_text('{"value": ' + constant + "}", encoding="utf-8")
    with pytest.raises(ValidationBundleIOError) as caught:
        load_validation_bundle(path)
    assert caught.value.issues[0].code == "IO.INVALID_JSON"


def test_invalid_claim_level_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["claims"][0]["level"] = "FULLY_VALIDATED"
    assert "SCHEMA.ENUM" in _codes(validate_schema(complete_bundle))


def test_malformed_sha256_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["evidence"][0]["sha256"] = "not-a-sha256"
    assert "SCHEMA.PATTERN" in _codes(validate_schema(complete_bundle))


def test_malformed_git_commit_is_rejected(complete_bundle: dict[str, Any]) -> None:
    complete_bundle["campaign"]["system_under_test"]["git_commit"] = "11daf88"
    assert "SCHEMA.PATTERN" in _codes(validate_schema(complete_bundle))


def test_run_manifest_is_a_valid_external_artifact(complete_bundle: dict[str, Any]) -> None:
    run = complete_bundle["runs"][1]
    artifacts = {artifact["artifact_id"]: artifact for artifact in complete_bundle["evidence"]}
    manifest = artifacts[run["run_manifest_artifact_id"]]
    assert manifest["artifact_type"] == "MANIFEST"
    assert manifest["media_type"] == "application/json"
    assert manifest["external_schema"] == {
        "name": "spmkit.core.export.RunManifest",
        "version": "1.0",
    }
    assert_valid_bundle(complete_bundle)


def test_assert_valid_bundle_raises_typed_schema_error(minimal_bundle: dict[str, Any]) -> None:
    del minimal_bundle["campaign"]["objective"]
    with pytest.raises(ValidationSchemaError) as caught:
        assert_valid_bundle(minimal_bundle)
    assert "SCHEMA.REQUIRED" in _codes(caught.value.issues)


def test_validation_does_not_mutate_document(complete_bundle: dict[str, Any]) -> None:
    original = copy.deepcopy(complete_bundle)
    assert_valid_bundle(complete_bundle)
    assert complete_bundle == original
