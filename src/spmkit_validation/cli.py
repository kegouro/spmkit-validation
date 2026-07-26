"""Stable command-line interface for ValidationBundle operations."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from spmkit_validation.execution import (
    CampaignExecutionError,
    execute_frozen_campaign,
    populate_result_bundle,
    prepare_synthetic_roughness_campaign,
    verify_result_snapshot,
    write_execution_receipt,
)
from spmkit_validation.execution.issues import (
    CampaignExecutionIssueCategory,
    execution_issue,
)
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
EXIT_EXECUTION = 7


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

    campaign = commands.add_parser("campaign", help="synthetic campaign execution")
    campaign_operations = campaign.add_subparsers(dest="campaign_command")

    prepare = campaign_operations.add_parser(
        "prepare-synthetic-roughness",
        help="prepare six deterministic Sa/Sq/Sz cases without running the SUT",
    )
    prepare.add_argument("--output-dir", required=True, type=Path)
    prepare.add_argument("--created-at", default="2026-07-26T08:00:00Z")
    prepare.add_argument("--predeclared-at", default="2026-07-26T08:01:00Z")
    prepare.add_argument("--generator-commit")
    prepare.add_argument("--json", action="store_true", dest="json_output")

    execute = campaign_operations.add_parser(
        "execute", help="run a verified frozen protocol against a SUT wheel"
    )
    execute.add_argument("protocol_bundle", metavar="PROTOCOL_BUNDLE.json", type=Path)
    execute.add_argument("freeze_receipt", metavar="FREEZE_RECEIPT.json", type=Path)
    execute.add_argument("--artifact-root", required=True, type=Path)
    execute.add_argument("--sut-wheel", required=True, type=Path)
    execute.add_argument("--output-dir", required=True, type=Path)
    execute.add_argument("--sut-executable", type=Path, help=argparse.SUPPRESS)
    execute.add_argument("--timeout-seconds", type=float, default=60.0)
    execute.add_argument("--json", action="store_true", dest="json_output")

    result = campaign_operations.add_parser(
        "verify-result", help="verify result receipt, protocol continuity and artifacts"
    )
    result.add_argument("result_bundle", metavar="RESULT_BUNDLE.json", type=Path)
    result.add_argument("execution_receipt", metavar="EXECUTION_RECEIPT.json", type=Path)
    result.add_argument("--protocol-bundle", required=True, type=Path)
    result.add_argument("--protocol-receipt", required=True, type=Path)
    result.add_argument("--artifact-root", required=True, type=Path)
    result.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _issues_payload(
    error: ValidationBundleError | LifecycleError | CampaignExecutionError,
) -> list[dict[str, str]]:
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
    error: ValidationBundleError | LifecycleError | CampaignExecutionError,
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


def _campaign_error_exit(error: CampaignExecutionError) -> int:
    categories = {issue.category.value for issue in error.issues}
    if "FILESYSTEM" in categories:
        return EXIT_FILESYSTEM
    if "ARTIFACT" in categories:
        return EXIT_ARTIFACT
    if "EXECUTION" in categories or "OUTPUT" in categories:
        return EXIT_EXECUTION
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


def _command_prepare_campaign(args: argparse.Namespace) -> int:
    try:
        prepared = prepare_synthetic_roughness_campaign(
            args.output_dir,
            created_at=args.created_at,
            predeclared_at=args.predeclared_at,
            generator_commit=args.generator_commit,
        )
    except (CampaignExecutionError, ValidationBundleError) as exc:
        _emit_expected_error(
            "campaign.prepare-synthetic-roughness", exc, json_output=args.json_output
        )
        if isinstance(exc, CampaignExecutionError):
            return _campaign_error_exit(exc)
        return EXIT_INVALID
    payload = {
        "operation": "campaign.prepare-synthetic-roughness",
        **prepared.to_dict(),
        "status": "DRAFT_PREPARED",
    }
    _emit(
        payload,
        json_output=args.json_output,
        human=f"DRAFT_PREPARED campaign_id={payload['campaign_id']} cases=6",
    )
    return EXIT_PASS


def _ground_truth_document(protocol: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    artifact = next(
        item
        for item in protocol["evidence"]
        if item["artifact_id"] == "artifact.reference.ground-truth"
    )
    path = artifact_root / artifact["relative_uri"]
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ground truth artifact root must be an object")
    return value


def _command_execute_campaign(args: argparse.Namespace) -> int:
    try:
        execution = execute_frozen_campaign(
            args.protocol_bundle,
            args.freeze_receipt,
            artifact_root=args.artifact_root,
            sut_wheel=args.sut_wheel,
            output_dir=args.output_dir,
            sut_executable=args.sut_executable,
            timeout_seconds=args.timeout_seconds,
        )
        protocol = load_validation_bundle(args.protocol_bundle)
        truth = _ground_truth_document(protocol, args.artifact_root)
        result_bundle = populate_result_bundle(protocol, execution, truth)
        published = write_execution_receipt(
            result_bundle,
            frozen_protocol_path=args.protocol_bundle,
            freeze_receipt_path=args.freeze_receipt,
            artifact_root=args.artifact_root,
            output_dir=args.output_dir / "result-snapshot",
            wheel_sha256=execution.wheel_sha256,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
        )
    except (
        CampaignExecutionError,
        LifecycleError,
        ValidationBundleError,
        ValueError,
        OSError,
    ) as exc:
        if not isinstance(
            exc, (CampaignExecutionError, LifecycleError, ValidationBundleError)
        ):
            error = CampaignExecutionError(
                [
                    execution_issue(
                        CampaignExecutionIssueCategory.INPUT,
                        "EXECUTION.INPUT_FAILED",
                        "",
                        str(exc),
                    )
                ]
            )
        else:
            error = exc
        _emit_expected_error("campaign.execute", error, json_output=args.json_output)
        if isinstance(error, CampaignExecutionError):
            return _campaign_error_exit(error)
        if isinstance(error, LifecycleError):
            return _lifecycle_error_exit(error)
        return EXIT_INVALID
    statuses = {
        status: sum(run["execution_status"] == status for run in execution.runs)
        for status in ("COMPLETED", "ERROR", "ABORTED")
    }
    payload = {
        "operation": "campaign.execute",
        "status": "RESULT_PUBLISHED",
        "campaign_id": execution.campaign_id,
        "wheel_sha256": execution.wheel_sha256,
        "result_bundle_sha256": published.result_bundle_sha256,
        "execution_receipt_sha256": published.execution_receipt_sha256,
        "runs": statuses,
        "comparisons": len(result_bundle["comparisons"]),
    }
    _emit(
        payload,
        json_output=args.json_output,
        human=(
            f"RESULT_PUBLISHED sha256={published.result_bundle_sha256} "
            f"runs={len(execution.runs)} comparisons={len(result_bundle['comparisons'])}"
        ),
    )
    return EXIT_EXECUTION if statuses["ERROR"] or statuses["ABORTED"] else EXIT_PASS


def _command_verify_result(args: argparse.Namespace) -> int:
    result = verify_result_snapshot(
        args.result_bundle,
        args.execution_receipt,
        args.protocol_bundle,
        args.protocol_receipt,
        args.artifact_root,
    )
    payload = {"operation": "campaign.verify-result", **result.to_dict()}
    _emit(
        payload,
        json_output=args.json_output,
        human=f"{result.status} artifacts={result.artifact_status}",
    )
    if result.valid:
        return EXIT_PASS
    if result.status == "ARTIFACT_MISMATCH":
        return EXIT_ARTIFACT
    return EXIT_TAMPERING


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.run and args.command is None:
        print("Validation suite would run here.")
        return EXIT_PASS
    if args.command is None:
        parser.print_help()
        return EXIT_PASS
    if args.command == "bundle" and args.bundle_command is not None:
        handlers = {
            "validate": _command_validate,
            "verify-artifacts": _command_verify_artifacts,
            "freeze": _command_freeze,
            "verify-snapshot": _command_verify_snapshot,
        }
        return handlers[args.bundle_command](args)
    if args.command == "campaign" and args.campaign_command is not None:
        campaign_handlers = {
            "prepare-synthetic-roughness": _command_prepare_campaign,
            "execute": _command_execute_campaign,
            "verify-result": _command_verify_result,
        }
        return campaign_handlers[args.campaign_command](args)
    parser.print_help()
    return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
