from pathlib import Path

from spmkit_validation.cli import build_parser


def test_campaign_command_parses_paths() -> None:
    args = build_parser().parse_args(
        ["campaign", "campaigns/smoke_v0.1.yaml", "results/smoke", "--spmkit", "/bin/spmkit"]
    )
    assert args.command == "campaign"
    assert args.campaign == Path("campaigns/smoke_v0.1.yaml")
    assert args.out_dir == Path("results/smoke")
    assert args.spmkit == Path("/bin/spmkit")


def test_report_command_parses_paths() -> None:
    args = build_parser().parse_args(["report", "cases.csv", "report-dir"])
    assert args.command == "report"
    assert args.cases_csv == Path("cases.csv")
    assert args.out_dir == Path("report-dir")
