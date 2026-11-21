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


def test_legacy_campaign_dispatch(monkeypatch, tmp_path) -> None:
    from spmkit_validation import campaign, cli

    calls = []
    monkeypatch.setattr(campaign, "run_campaign", lambda *a, **k: calls.append((a, k)))
    assert cli.main(["campaign", "input.yaml", str(tmp_path), "--target", "spmkit"]) == 0
    assert calls[0][0][:2] == (Path("input.yaml"), tmp_path)
    assert calls[0][1] == {"target": "spmkit"}


def test_legacy_report_dispatch(monkeypatch, tmp_path) -> None:
    from spmkit_validation import cli, report

    calls = []
    monkeypatch.setattr(report, "write_report", lambda *a: calls.append(a))
    assert cli.main(["report", "cases.csv", str(tmp_path)]) == 0
    assert calls == [(Path("cases.csv"), tmp_path)]
