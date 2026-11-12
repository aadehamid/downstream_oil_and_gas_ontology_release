"""Writes every generated file of the intake pack, or with --check says which of them is stale.

    py -m kpi_store.intake build            write them
    py -m kpi_store.intake build --check    write nothing; exit 1 when a committed file differs from a fresh build

Run it from the release's top folder, after you change kpi-intake/catalogue.toml, kpi-intake/settings.toml or
kpi-intake/examples/examples.toml, and after every release of a module, because the pick lists come from the
newest packages. Needs rdflib and openpyxl.

What it writes, all under kpi-intake/:

    pick-lists.json              the pick lists and the term index, from the release packages
    kpi-intake-form.html         the HTML form
    kpi-intake-form.xlsx         the Excel form
    what-we-will-ask-you.md      the one-page explainer
    for-the-architect.md         what each question feeds, and the facts with no place in the ontology
    examples/<name>.json, .xlsx  each filled example

The text files are the same bytes on every system: UTF-8, LF line ends, sorted keys. A workbook is not, because
its file format stores the time of writing. So a workbook is compared by content (workbook.same_content), and
the build leaves a workbook alone when its content is already current.

The build writes only inside the pack folder it is given. A generated file, or a folder on the way to it, that
is a link could send a write somewhere else, so the build refuses it (refuse_links) and --check does the same,
without reading through the link. The pack folder itself may be reached by a link: that is the operator's choice.
"""
import sys
from pathlib import Path

from kpi_store.intake import answers, catalogue, examples, page, picklists, workbook

FORM_HTML, FORM_XLSX = "kpi-intake-form.html", "kpi-intake-form.xlsx"
EXPLAINER, ARCHITECT = "what-we-will-ask-you.md", "for-the-architect.md"


class BuildError(Exception):
    """The build will not write here. The message says why."""


def refuse_links(pack, paths):
    """Raises BuildError when one of the paths, or a folder between the pack folder and it, is a link, or when a
    path does not resolve to a place inside the pack folder. `pack` may itself be reached by a link."""
    real = Path(pack).resolve()
    for path in paths:
        relative = Path(path).relative_to(pack)
        at = Path(pack)
        for part in relative.parts:
            at = at / part
            if at.is_symlink():
                raise BuildError(f"{at.relative_to(pack).as_posix()} in the pack folder is a link. The build writes only inside "
                                 "the pack folder, so it does not follow a link. Remove the link and run the command again.")
        if not Path(path).resolve().is_relative_to(real):
            raise BuildError(f"{relative.as_posix()} is not inside the pack folder {real}. The build writes only inside the pack folder.")


def explainer_text(cat):
    lines = [f'# {cat.explainer["title"]}', ""]
    for block in cat.explainer["block"]:
        if "p" in block:
            lines += [block["p"], ""]
        if "ol" in block:
            lines += [f"{n}. {item}" for n, item in enumerate(block["ol"], 1)] + [""]
    return "\n".join(lines)


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def architect_text(cat):
    """The Architect's page: the two fixed words, each section's technical name, what each question feeds, the
    facts a new KPI needs with the questions that supply them, and the facts that have no place yet."""
    out = ["# For the Architect: what each question feeds", "",
           "This page maps the KPI intake form to the ontology. The business never sees it. It is built from `catalogue.toml`, so change the text there and run the build command of [the guide](README.md).", "",
           "The check of a filled form changes nothing in the ontology. In this release you apply a complete intake by hand, with the release steps of [`HOW-TO-UPDATE.md`](../HOW-TO-UPDATE.md).", "",
           "## Business area and domain", ""]
    for note in cat.architect_notes:
        out += [note, ""]
    out += ["## The sections and their technical names", "", "| Section | Plain name | Technical name |", "|---|---|---|"]
    for s in cat.sections:
        out.append(f'| {s["id"]} | {_cell(s["name"])} | {_cell(s["technical_name"])} |')
    out += ["", "## What each question feeds", ""]
    for form, title in catalogue.FORMS.items():
        out += [f"### {title}", "", "| No. | Question | Rule | Feeds |", "|---|---|---|---|"]
        for q in cat.questions_of(form):
            out.append(f'| {q["id"]} | {_cell(q["text"])} | {_cell(cat.requirement(q))} | {_cell(q["feeds"])} |')
        out.append("")
    out += ["## The facts one new KPI needs, and the questions that supply them", "",
            "| Fact | Property or pattern | Module | Status | Supplied by | Note |", "|---|---|---|---|---|---|"]
    for f in cat.facts:
        supplied = ", ".join(f["supplied_by"]) or "Not asked"
        if f.get("derived"):
            supplied = "Derived" + (f' from {", ".join(f["supplied_by"])}' if f["supplied_by"] else "")
        out.append(f'| {f["id"]} {_cell(f["name"])} | {_cell(f["property"])} | {_cell(f["module"])} | {_cell(f["status"])} | {supplied} | {_cell(f.get("note", ""))} |')
    out += ["", "## The kind of measure", "", "Section 4 asks its tests in order. The first answer in this table that matches decides the kind.", "",
            "| Question | Answer | Kind | Test |", "|---|---|---|---|"]
    for rule in cat.kind_rules:
        out.append(f'| {rule["question"]} | {rule["answer"]} | {rule["kind"]} | {rule["test"]} |')
    out += ["", "## Facts with no place in the ontology yet", "",
            "The form asks for some of these and keeps the answers in its own file. `KNOWN-OPEN-ITEMS.md` at the top of the release lists them too.", "",
            "| Fact | Question | Note |", "|---|---|---|"]
    for gap in cat.gaps:
        out.append(f'| {_cell(gap["fact"])} | {gap["question"] or "Not asked"} | {_cell(gap["note"])} |')
    out.append("")
    return "\n".join(out)


def outputs(root, pack):
    """Every generated file as (path, kind, content): the text of a text file, or the workbook of an .xlsx."""
    pack = Path(pack)
    # Before anything under examples/ is read: the examples' own settings file is in that folder.
    refuse_links(pack, [pack / name for name in (picklists.FILE, FORM_HTML, FORM_XLSX, EXPLAINER, ARCHITECT)] + [pack / "examples" / examples.FILE])
    cat = catalogue.load(pack)
    release = picklists.Release(root)      # parsed once, for the lists and for the examples
    built = picklists.build(root, release)
    lists = built["lists"]
    filled = [(spec, examples.build(release, lists, cat, spec)) for spec in examples.specs(pack)]
    column = examples.example_column(cat, lists, [intake for _, intake in filled])
    out = [
        (pack / picklists.FILE, "text", picklists.dumps(built)),
        (pack / FORM_HTML, "text", page.render(cat, built, column)),
        (pack / FORM_XLSX, "workbook", workbook.build(cat, lists, column)),
        (pack / EXPLAINER, "text", explainer_text(cat)),
        (pack / ARCHITECT, "text", architect_text(cat)),
    ]
    for spec, intake in filled:
        out.append((pack / "examples" / f'{spec["file"]}.json', "text", answers.dumps(intake)))
        out.append((pack / "examples" / f'{spec["file"]}.xlsx', "workbook", workbook.build(cat, lists, column, intake)))
    refuse_links(pack, [path for path, _, _ in out])       # an example's name comes from a file a person edits
    return out


def is_current(path, kind, content):
    path = Path(path)
    if kind == "workbook":
        return workbook.same_content(path, content)
    return path.is_file() and path.read_bytes() == content.encode("utf-8")


def stale(root, pack):
    """The generated files that differ from a fresh build, as paths."""
    return [path for path, kind, content in outputs(root, pack) if not is_current(path, kind, content)]


def write(root, pack):
    """Writes each file that is not current. Returns the paths written."""
    written = []
    for path, kind, content in outputs(root, pack):
        if is_current(path, kind, content):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == "workbook":
            workbook.save(content, path)
        else:
            with path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        written.append(path)
    return written


def main(root, pack, check=False, out=None):
    root, pack, out = Path(root), Path(pack), out or sys.stdout

    def name(path):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    if check:
        old = stale(root, pack)
        for path in old:
            print(f"{name(path)} differs from a fresh build", file=out)
        if old:
            print("run this command again without --check", file=out)
            return 1
        print("the intake pack is current", file=out)
        return 0
    written = write(root, pack)
    for path in written:
        print(f"wrote {name(path)}", file=out)
    if not written:
        print("the intake pack is current; nothing was written", file=out)
    return 0
