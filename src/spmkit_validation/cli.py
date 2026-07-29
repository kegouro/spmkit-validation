import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External validation harness for SPM-Kit")
    commands = parser.add_subparsers(dest="command", required=True)

    campaign = commands.add_parser("campaign", help="run a YAML campaign through a public CLI")
    campaign.add_argument("campaign", type=Path)
    campaign.add_argument("out_dir", type=Path)
    campaign.add_argument("--spmkit", type=Path)
    campaign.add_argument("--target", choices=["spmkit", "gwyddion"], default="spmkit")

    report = commands.add_parser("report", help="generate a report from campaign cases.csv")
    report.add_argument("cases_csv", type=Path)
    report.add_argument("out_dir", type=Path)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "campaign":
        from spmkit_validation.campaign import run_campaign

        run_campaign(args.campaign, args.out_dir, args.spmkit, target=args.target)
        return

    from spmkit_validation.report import write_report

    write_report(args.cases_csv, args.out_dir)


if __name__ == "__main__":
    main()
