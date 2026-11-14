"""Writes every generated file of the intake pack, or with --check says which of them is stale.

    python -m kpi_store.intake build            write them
    python -m kpi_store.intake build --check    write nothing; exit 1 when a committed file differs from a fresh build

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
GUIDE = page.GUIDE      # written by hand; the build links to it and never writes it


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
    # The page's own last line. The HTML form shows the same explainer and has its own link to the guide.
    lines += [f"[How to use the form]({GUIDE}) shows how the form is filled, saved and checked.", ""]
    return "\n".join(lines)


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def architect_text(cat, lists=None):
    """The Architect's page: the two fixed words, each section's technical name, what each question feeds, the
    facts a new KPI needs with the questions that supply them, the facts that have no place yet and, with the
    built lists, what the organization's settings hide from and add to them."""
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
    if lists is not None:
        out += lists_text(cat, lists)
    return "\n".join(out)


QUESTION_OF_LIST = {"sources": "3.5", "roles": "6.1 and P5", "data-products": "6.6 and D6", "systems": "7.4"}


def lists_text(cat, lists):
    """The Architect's section on the four lists that settings.toml can change: what each offers, hides and adds
    today. It is rebuilt with the pack, so an entry the ontology gains and the settings hide shows here."""
    out = ["## The lists your settings change", "",
           "Four of the forms' lists come from the ontology. `settings.toml` says, under `[pick_list.<name>]`, what your organization hides from each and adds to each. The ontology is not changed. This table is rebuilt with the pack and shows each list as it stands.", "",
           "The Architect, or whoever maintains the form, edits `settings.toml`. The business users never do. Edit it when a role title or a definition changes, when the domain list changes, or when an entry of a list is to be hidden or added. Then run `python -m kpi_store.intake build`.", "",
           "| List | Questions | Offered | Hidden | Added |", "|---|---|---|---|---|"]
    detail = []
    for name, module in catalogue.SETTINGS_LISTS.items():
        items = lists[name]
        change = cat.pick_lists.get(name) or {}
        hidden = [i for i in items if i.get("hidden")]
        added = [i["label"].removesuffix(catalogue.ADDED_MARK) for i in items if i.get("added")]
        out.append(f'| `{name}` | {QUESTION_OF_LIST[name]} | {len(items) - len(hidden)} of {len(items)} | {len(hidden)} | {", ".join(added) or "None"} |')
        if change.get("hide_tiers"):
            counts = {tier: sum(1 for i in hidden if i.get("tier") == tier) for tier in change["hide_tiers"]}
            detail.append(f'- `{name}` hides the sources of these evidence tiers: ' + ", ".join(f"{tier} ({count})" for tier, count in counts.items()) + ".")
        named = [i["label"] for i in hidden if i.get("tier") not in change.get("hide_tiers", [])]
        if change.get("keep_only") and len(named) > 40:      # too many to name: the list of sources
            detail.append(f"- `{name}` offers only the {len(items) - len(hidden)} entries that `keep_only` names, and so hides the other {len(named)}.")
        elif named:
            how = "offers only the entries that `keep_only` names, and so hides" if change.get("keep_only") else "hides"
            detail.append(f'- `{name}` {how}: {"; ".join(_cell(label) for label in named)}.')
        relabelled = [i for i in items if i.get("was") and not i.get("hidden")]
        if relabelled:
            detail.append(f"- `{name}` shows {len(relabelled)} {'entry' if len(relabelled) == 1 else 'entries'} under a label of your settings (`labels`): "
                          + "; ".join(_cell(i["label"]) for i in relabelled) + ". The answers file keeps each entry's id.")
        gained = [i for i in items if i.get("aliases")]
        if gained:
            detail.append(f'- `{name}`: the ontology now holds {", ".join(_cell(i["label"]) for i in gained)}. The entry under `add` is no longer offered a second time. '
                          "An answer saved under it is read as the ontology's entry, and the check says so. "
                          "Remove the entry from `add` once no form in progress uses it.")
        for item in gained:
            if item.get("hidden"):
                how = "`keep_only` does not name it. Add its name to `keep_only` to offer it" if change.get("keep_only") else "its evidence tier is hidden"
                detail.append(f'- `{name}`: {_cell(item["label"])} is in the ontology and is not offered, because {how}.')
        if added:
            detail.append(f'- `{name}` adds: {", ".join(added)}. Each is offered with the mark "{catalogue.ADDED_MARK.strip(" ()")}". '
                          f"When a form names one, the check tells you to add it to the `{module}` module before you apply the KPI.")
    out += [""] + detail + [""]
    out += ["Keep the lists in step with the ontology:", "",
            "- A hidden entry stays known. A form that already holds it still checks, with a note.",
            "- A list with `keep_only` offers nothing new by itself. When a release of `data-product` adds a data product, the rebuild adds its name to the hidden entries above. Add the name to `keep_only` to offer it.",
            "- A list with `hide` offers every new entry of the ontology as soon as the pack is rebuilt.",
            "- A list uses `keep_only`, or `hide` and `hide_tiers`, never both.",
            "- When you have added an entry to the ontology under the same label, rebuild. Leave the entry under `add` for now: the forms offer the ontology's entry only, and an answer that a form in progress saved under the added entry is read as the ontology's. The list above then names the entry. Remove it from `add` once no form in progress uses it. After that, such an answer no longer checks.",
            "- The build stops when `add` names an entry that `hide` names, when an added entry matches more than one entry, or when two added entries share a label.",
            "- One rule reads every saved answer: a saved value names an entry when it is the entry's id, an id your settings once added it under, its label of today or a label it had before, with or without the mark of a hidden or a new entry.",
            "- `KNOWN-OPEN-ITEMS.md` lists the changes to the ontology that these settings stand in for.", ""]
    return out


def outputs(root, pack):
    """Every generated file as (path, kind, content): the text of a text file, or the workbook of an .xlsx."""
    pack = Path(pack)
    # Before anything under examples/ is read: the examples' own settings file is in that folder.
    refuse_links(pack, [pack / name for name in (picklists.FILE, FORM_HTML, FORM_XLSX, EXPLAINER, ARCHITECT)] + [pack / "examples" / examples.FILE])
    cat = catalogue.load(pack)
    release = picklists.Release(root)      # parsed once, for the lists and for the examples
    built = picklists.apply_settings(picklists.build(root, release), cat.pick_lists)
    lists = built["lists"]
    filled = [(spec, examples.build(release, lists, cat, spec)) for spec in examples.specs(pack)]
    column = examples.example_column(cat, lists, [intake for _, intake in filled])
    out = [
        (pack / picklists.FILE, "text", picklists.dumps(built)),
        (pack / FORM_HTML, "text", page.render(cat, built, column)),
        (pack / FORM_XLSX, "workbook", workbook.build(cat, lists, column)),
        (pack / EXPLAINER, "text", explainer_text(cat)),
        (pack / ARCHITECT, "text", architect_text(cat, lists)),
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
