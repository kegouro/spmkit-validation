"""Stable command-line interface for ValidationBundle operations."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from spmkit_validation.lifecycle import (
    LifecycleError,
    freeze_bundle,
    verify_artifacts,
    verify_frozen_snapshot,
)
from spmkit_validation.schemas import (
    ValidationBundleError,
    assert_valid_bundle,
    load_validation_bundle,
)

EXIT_PASS = 0
EXIT_INVALID = 2
EXIT_ARTIFACT = 3
EXIT_TAMPERING = 4
EXIT_FILESYSTEM = 5
EXIT_INCOMPLETE = 6


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SPM-Kit Validation Harness")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Preserved legacy placeholder; does not execute a campaign",
    )
    commands = parser.add_subparsers(dest="command")
    bundle = commands.add_parser("bundle", help="ValidationBundle v0.1 lifecycle")
    operations = bundle.add_subparsers(dest="bundle_command")

    validate = operations.add_parser("validate", help="validate schema and semantics")
    validate.add_argument("bundle_path", metavar="BUNDLE.json", type=Path)
    validate.add_argument("--json", action="store_true", dest="json_output")

    verify = operations.add_parser(
        "verify-artifacts", help="verify declared artifacts under an explicit root"
    )
    verify.add_argument("bundle_path", metavar="BUNDLE.json", type=Path)
    verify.add_argument("--artifact-root", required=True, type=Path)
    verify.add_argument("--json", action="store_true", dest="json_output")

    freeze = operations.add_parser("freeze", help="publish a tamper-evident protocol snapshot")
    freeze.add_argument("bundle_path", metavar="BUNDLE.json", type=Path)
    freeze.add_argument("--artifact-root", required=True, type=Path)
    freeze.add_argument("--output-dir", required=True, type=Path)
    freeze.add_argument("--frozen-at")
    freeze.add_argument("--json", action="store_true", dest="json_output")

    snapshot = operations.add_parser(
        "verify-snapshot", help="verify snapshot and receipt, with optional artifacts"
    )
    snapshot.add_argument("snapshot_path", metavar="SNAPSHOT.json", type=Path)
    snapshot.add_argument("receipt_path", metavar="RECEIPT.json", type=Path)
    snapshot.add_argument("--artifact-root", type=Path)
    snapshot.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _issues_payload(error: ValidationBundleError | LifecycleError) -> list[dict[str, str]]:
    return [
        {
            "category": issue.category.value,
            "code": issue.code,
            "path": issue.path,
            "description": issue.description,
        }
        for issue in error.issues
    ]


def _emit(payload: dict[str, Any], *, json_output: bool, human: str) -> None:
    if json_output:
        print(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    else:
        print(human)


def _emit_expected_error(
    operation: str,
    error: ValidationBundleError | LifecycleError,
    *,
    json_output: bool,
) -> None:
    issues = _issues_payload(error)
    _emit(
        {"operation": operation, "status": "INVALID", "issues": issues},
        json_output=json_output,
        human=f"INVALID ({len(issues)} issue{'s' if len(issues) != 1 else ''})",
    )
    if not json_output:
        for issue in issues:
            print(
                f"{issue['code']} {issue['path']}: {issue['description']}",
                file=sys.stderr,
            )


def _lifecycle_error_exit(error: LifecycleError) -> int:
    if any(issue.category.value == "FILESYSTEM" for issue in error.issues):
        return EXIT_FILESYSTEM
    if any(
        issue.code in {"REMOTE_ARTIFACT_NOT_VERIFIED", "FREEZE.REMOTE_ARTIFACT_NOT_VERIFIED"}
        for issue in error.issues
    ):
        return EXIT_INCOMPLETE
    if any(
        issue.category.value == "ARTIFACT" and not issue.code.startswith("FREEZE.")
        for issue in error.issues
    ):
        return EXIT_ARTIFACT
    return EXIT_INVALID


def _load_and_assert(path: Path) -> dict[str, Any]:
    bundle = load_validation_bundle(path)
    assert_valid_bundle(bundle)
    return bundle


def _command_validate(args: argparse.Namespace) -> int:
    try:
        bundle = _load_and_assert(args.bundle_path)
    except ValidationBundleError as exc:
        _emit_expected_error("bundle.validate", exc, json_output=args.json_output)
        return EXIT_INVALID
    _emit(
        {
            "operation": "bundle.validate",
            "status": "VALID",
            "schema_version": bundle["schema_version"],
            "issues": [],
        },
        json_output=args.json_output,
        human=f"VALID schema_version={bundle['schema_version']}",
    )
    return EXIT_PASS


def _command_verify_artifacts(args: argparse.Namespace) -> int:
    try:
        bundle = _load_and_assert(args.bundle_path)
        results = verify_artifacts(bundle, args.artifact_root)
    except ValidationBundleError as exc:
        _emit_expected_error("bundle.verify-artifacts", exc, json_output=args.json_output)
        return EXIT_INVALID
    except LifecycleError as exc:
        _emit_expected_error("bundle.verify-artifacts", exc, json_output=args.json_output)
        return _lifecycle_error_exit(exc)

    failed = sum(result.status == "FAIL" for result in results)
    remote = sum(result.status == "REMOTE_ARTIFACT_NOT_VERIFIED" for result in results)
    status = "PASS" if not failed and not remote else "INCOMPLETE" if not failed else "FAIL"
    payload = {
        "operation": "bundle.verify-artifacts",
        "status": status,
        "summary": {
            "total": len(results),
            "passed": sum(result.status == "PASS" for result in results),
            "failed": failed,
            "remote_not_verified": remote,
        },
        "results": [result.to_dict() for result in results],
    }
    _emit(
        payload,
        json_output=args.json_output,
        human=(
            f"{status} artifacts={len(results)} passed={payload['summary']['passed']} "
            f"failed={failed} remote_not_verified={remote}"
        ),
    )
    if failed:
        return EXIT_ARTIFACT
    if remote:
        return EXIT_INCOMPLETE
    return EXIT_PASS


def _command_freeze(args: argparse.Namespace) -> int:
    try:
        result = freeze_bundle(
            args.bundle_path,
            args.artifact_root,
            args.output_dir,
            frozen_at=args.frozen_at,
        )
    except LifecycleError as exc:
        _emit_expected_error("bundle.freeze", exc, json_output=args.json_output)
        return _lifecycle_error_exit(exc)
    payload = {"operation": "bundle.freeze", "status": "FROZEN", **result.to_dict()}
    _emit(
        payload,
        json_output=args.json_output,
        human=f"FROZEN sha256={result.bundle_sha256}",
    )
    return EXIT_PASS


def _command_verify_snapshot(args: argparse.Namespace) -> int:
    try:
        result = verify_frozen_snapshot(
            args.snapshot_path,
            args.receipt_path,
            artifact_root=args.artifact_root,
        )
    except LifecycleError as exc:
        _emit_expected_error("bundle.verify-snapshot", exc, json_output=args.json_output)
        return _lifecycle_error_exit(exc)
    payload = {"operation": "bundle.verify-snapshot", **result.to_dict()}
    _emit(
        payload,
        json_output=args.json_output,
        human=f"{result.status} artifacts={result.artifact_status}",
    )
    if result.status == "ARTIFACT_MISMATCH":
        return EXIT_ARTIFACT
    if result.status != "SNAPSHOT_VALID":
        return EXIT_TAMPERING
    if args.artifact_root is not None and result.artifact_status == "ARTIFACT_NOT_VERIFIED":
        return EXIT_INCOMPLETE
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.run and args.command is None:
        print("Validation suite would run here.")
        return EXIT_PASS
    if args.command is None:
        parser.print_help()
        return EXIT_PASS
    if args.command != "bundle" or args.bundle_command is None:
        parser.print_help()
        return EXIT_INVALID
    handlers = {
        "validate": _command_validate,
        "verify-artifacts": _command_verify_artifacts,
        "freeze": _command_freeze,
        "verify-snapshot": _command_verify_snapshot,
    }
    return handlers[args.bundle_command](args)


if __name__ == "__main__":
    raise SystemExit(main())
