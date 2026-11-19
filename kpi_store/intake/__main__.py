"""The command line of the intake pack: `python -m kpi_store.intake build`, `python -m kpi_store.intake check <file>` and
`python -m kpi_store.intake folders <place>`."""
import argparse
import sys
from pathlib import Path

from kpi_store.intake.catalogue import FORMS, CatalogueError

ROOT = Path(__file__).resolve().parents[2]


def report_path(file, form=None):
    """Where `check --report` writes: beside the file, under its name with .check.txt in place of its ending. For a
    workbook the name also says the form, unless the file's name already ends with it, and then "workbook":
    a workbook holds five forms, and a KPI may have an answers file and a workbook of the same name. So no two
    checks share a report.

        crack-spreads-pricing.kpi-intake.json   crack-spreads-pricing.kpi-intake.check.txt
        crack-spreads-pricing.kpi-intake.xlsx   crack-spreads-pricing.kpi-intake.workbook.check.txt
        the same, --form domain-activation      crack-spreads-pricing.kpi-intake.domain-activation.workbook.check.txt
    """
    file = Path(file)
    stem = file.stem
    if file.suffix.lower() != ".json":
        form = form or "kpi-intake"
        if not stem.endswith("." + form):
            stem += "." + form
        stem += ".workbook"
    return file.with_name(stem + ".check.txt")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m kpi_store.intake", description="The KPI intake pack: build its forms, check a filled form, or set up the shared folder.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="write the forms, the pick lists, the generated pages and the examples")
    build.add_argument("--check", action="store_true", help="write nothing; exit 1 when a committed file differs from a fresh build")
    check = sub.add_parser("check", help="say what a filled form still lacks; exit 0 only when it is complete and signed")
    check.add_argument("file", help="an answers file (.json) or a filled workbook (.xlsx)")
    check.add_argument("--form", choices=list(FORMS), help="the form to read from a workbook (default: kpi-intake)")
    check.add_argument("--report", action="store_true", help="also write the report beside the file, as <file's name>.check.txt; "
                       "for a workbook the form's name comes before .check.txt")
    folders = sub.add_parser("folders", help="make the shared KPI-intake folder in the place you name, with the forms and the guide in it")
    folders.add_argument("place", help="an existing folder, such as your team's shared drive")
    for command in (build, check, folders):
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
    from kpi_store.intake.folders import FoldersError
    errors = (CatalogueError, AnswersError, ReleaseError, FoldersError)
    try:
        if args.command == "build":
            from kpi_store.intake import build as builder
            from kpi_store.intake.examples import ExampleError
            errors += (builder.BuildError, ExampleError)
            try:
                return builder.main(root, pack, args.check)
            except OSError as e:
                if args.check:
                    raise builder.BuildError(f"the pack or the release could not be read: {e}") from None
                raise builder.BuildError(f"the build could not read or write a file: {e}. Files of the pack that it wrote before this one "
                                         "may already be new. Settle the cause, such as a workbook that is open in Excel, and run the "
                                         "build again: it repairs the pack.") from None
        if args.command == "folders":
            from kpi_store.intake import folders as shared
            try:
                top, done = shared.create(args.place, pack)
            except OSError as e:
                raise FoldersError(f"the shared folder could not be made or filled: {e}") from None
            for line in done:
                print(line)
            print(f"{top.name} is ready" if done else f"{top.name} is current; nothing was changed")
            return 0
        from kpi_store.intake import check as checker
        try:
            report = checker.run(args.file, pack, args.form, root)
        except OSError as e:
            raise ReleaseError(f"the check could not read the pack, the file or the release folder {root}: {e}") from None
        saved = None
        if args.report:
            saved = report_path(args.file, args.form)
            if saved.is_symlink():
                raise AnswersError(f"{saved} is a link, so the report was not written there")
            try:
                with saved.open("w", encoding="utf-8", newline="\n") as f:
                    f.write(report.text())
            except OSError as e:
                raise AnswersError(f"the report could not be written to {saved}: {e}") from None
    except errors as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 2
    except OSError as e:      # the last line of defence: a tool error is never exit 1, which means "not complete"
        print(f"stopped: the {args.command} command could not read or write a file: {e}", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(report.text())
        if saved:
            print(f"The report is also in {saved.name}, beside the file.")
        sys.stdout.flush()
    except OSError as e:      # a closed pipe, for one: still a tool error, never "not complete"
        print(f"stopped: the report could not be printed: {e}", file=sys.stderr)
        return 2
    return 0 if report.complete else 1


if __name__ == "__main__":
    sys.exit(main())
