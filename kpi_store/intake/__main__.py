"""The command line of the intake pack: `py -m kpi_store.intake build` and `py -m kpi_store.intake check <file>`."""
import argparse
import sys
from pathlib import Path

from kpi_store.intake.catalogue import FORMS, CatalogueError

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="py -m kpi_store.intake", description="The KPI intake pack: build its forms, or check a filled form.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="write the forms, the pick lists, the generated pages and the examples")
    build.add_argument("--check", action="store_true", help="write nothing; exit 1 when a committed file differs from a fresh build")
    check = sub.add_parser("check", help="say what a filled form still lacks; exit 0 only when it is complete and signed")
    check.add_argument("file", help="an answers file (.json) or a filled workbook (.xlsx)")
    check.add_argument("--form", choices=list(FORMS), help="the form to read from a workbook (default: kpi-intake)")
    for command in (build, check):
        command.add_argument("--root", default=str(ROOT), help="the release folder (default: the one this code is in)")
        command.add_argument("--pack", help="the pack's folder (default: kpi-intake in the release folder)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    pack = Path(args.pack) if args.pack else root / "kpi-intake"
    # Output is UTF-8 on every system. A Windows console would otherwise fail on a character its code page lacks.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    from kpi_store.intake.answers import AnswersError
    from kpi_store.ontology_view import ReleaseError
    try:
        if args.command == "build":
            from kpi_store.intake import build as builder
            return builder.main(root, pack, args.check)
        from kpi_store.intake import check as checker
        report = checker.run(args.file, pack, args.form, root)
    except (CatalogueError, AnswersError, ReleaseError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(report.text())
    return 0 if report.complete else 1


if __name__ == "__main__":
    sys.exit(main())
