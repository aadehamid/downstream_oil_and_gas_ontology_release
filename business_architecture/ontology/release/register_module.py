"""Registers a new module in every place the release lists its modules, one function per place.

Two callers use it. release/onboard_example.py registers the made-up module `sample-area` that HOW-TO-UPDATE.md,
"Onboard another module", walks through by hand. The apply command registers a module that the new-module form asks
for (kpi_store/change/new_module.py). Each caller describes its module in a Module, and register() does the rest:

    places = register(Module(...), root, date, write=True)

Every change is worked out in memory before the first file is written, so a place that has moved stops the run
with nothing changed (Refused). After the edits, check_places() reads each edited file back as the release reads
it, the Python tables by their syntax tree and the JSON as JSON, and refuses an edit that does not hold the module
as meant.
"""
import ast
import csv
import io
import json
import os
import re
from dataclasses import dataclass, field

ONT = "business_architecture/ontology"
NAMESPACES = "https://w3id.org/mpc/ontology/modules/"
ROMAN = (("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100), ("XC", 90), ("L", 50), ("XL", 40),
         ("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1))


class Refused(Exception):
    """The release holds the module already, or a place is not where this code expects it. Nothing changed."""


@dataclass
class Module:
    """What the places need to know of one new module. Paths in `parts` and `shapes` are under the ontology folder;
    `files` are the module folder's own files, by name."""
    name: str
    version: str
    prefix: str
    title: str
    description: str
    approver: str
    approval: tuple             # (where the approval is recorded, the approval words)
    parts: list
    shapes: list
    depends_on: list
    decisions: list
    files: dict                 # {file name: text} of the module's folder
    builder: str                # the builder's file name, in the module's folder
    test: str                   # the test file's name, in the module's folder
    changelog: str              # the text of releases/<module>/CHANGELOG.md
    question: str               # the competency question, numbered after the last
    question_heading: str       # the heading of the question's section in competency-questions.md
    question_intro: str         # one sentence under that heading
    query_name: str             # the query's file name after q<number>-, such as "sample-area-processes"
    query: str                  # the query's text after its first comment line
    regression_files: list      # the module's files, by name in its folder, that the regression loads
    purpose: str                # the module's row in MODULES.md
    modules_section: str        # the module's section of MODULES.md, from its heading to its last line
    approval_text: str = ""     # the text of a Markdown approval file at approval[0], or "" when it is written elsewhere
    entry_comment: list = field(default_factory=list)   # comment lines above the module's entry in build_module.py

    @property
    def namespace(self):
        return f"{NAMESPACES}{self.name}/"

    def entry(self, date):
        """The module's entry in build_module.py's MODULES table, as the table holds it."""
        return {"title": self.title, "description": self.description, "version": self.version, "stage": None,
                "approver": self.approver, "issued": date, "approval": tuple(self.approval), "parts": list(self.parts),
                "shapes": list(self.shapes), "depends_on": list(self.depends_on), "decisions": list(self.decisions)}


def py(text):
    """A string as a Python literal in double quotes, as the release's tables write them."""
    return json.dumps(text, ensure_ascii=False)


def roman(n):
    out = ""
    for letters, value in ROMAN:
        while n >= value:
            out, n = out + letters, n - value
    return out


def from_roman(text):
    values = dict(ROMAN)
    total, i = 0, 0
    while i < len(text):
        if text[i:i + 2] in values:
            total, i = total + values[text[i:i + 2]], i + 2
        else:
            total, i = total + values[text[i]], i + 1
    return total


class Tree:
    """The release's files as this run reads and changes them. Nothing is written until save().

    Every path is checked before it is read and again before it is written (inside): a file that is a link, or
    that lies under a folder that is a link, could send a write to a place outside the copy, so the run refuses
    it. The copy's own top folder may be reached through a link: that is the reader's choice. The checks read the
    disk as it is at that moment. They do not lock the copy: do not let another program change it during a run."""

    def __init__(self, root):
        self.root, self.texts, self.places = root, {}, []

    def inside(self, path):
        """The full path of a file of the copy. Raises Refused when the path, or a folder between the top folder
        and it, is a link, or when the path does not resolve to a place inside the top folder."""
        at = self.root
        for part in path.replace("\\", "/").split("/"):
            at = os.path.join(at, part)
            if os.path.islink(at) or getattr(os.path, "isjunction", lambda p: False)(at):   # isjunction: Windows, Python 3.12
                raise Refused(f"{os.path.relpath(at, self.root).replace(os.sep, '/')} is a link. This command changes only "
                              "files inside the copy, so it does not follow a link. Remove the link and run the command again")
        top, full = os.path.realpath(self.root), os.path.realpath(os.path.join(self.root, path))
        if os.path.commonpath([top, full]) != top:
            raise Refused(f"{path} is not inside the copy")
        # A hard link is a second name of one file: a write through the name in the copy would change the other too.
        if os.path.isfile(full) and os.stat(full).st_nlink > 1:
            raise Refused(f"{path} has a second name on this disk (a hard link). This command changes only files inside "
                          "the copy. Replace it with a copy of its own and run the command again")
        return os.path.join(self.root, path)

    def read(self, path):
        if path not in self.texts:
            full = self.inside(path)
            if not os.path.isfile(full):
                raise Refused(f"{path} is missing")
            with open(full, encoding="utf-8", newline="") as f:
                self.texts[path] = f.read()
        return self.texts[path]

    def new(self, path, text):
        if os.path.lexists(self.inside(path)):
            raise Refused(f"{path} exists already")
        self.texts[path] = text

    def after(self, path, pattern, added):
        """Adds text right after the one place the pattern matches. A pattern that matches no place, or two,
        stops the run: the file is not as this code expects it."""
        text = self.read(path)
        found = list(re.finditer(pattern, text, re.M))
        if len(found) != 1:
            raise Refused(f"{path}: expected one place that matches {pattern!r}, found {len(found)}")
        self.texts[path] = text[:found[0].end()] + added + text[found[0].end():]

    def save(self):
        for path in self.texts:   # every path is checked before the first write
            self.inside(path)
        for path, text in self.texts.items():
            os.makedirs(os.path.dirname(os.path.join(self.root, path)), exist_ok=True)
            full = self.inside(path)   # and again right before its own write, after its folders exist
            with open(full, "w", encoding="utf-8", newline="") as f:
                f.write(text)


# ---- one function per place -------------------------------------------------------------------------

def module_folder(tree, m, date):
    """The module's own folder: its README, sources, builder and test."""
    for name, text in m.files.items():
        tree.new(f"{ONT}/{m.name}/{name}", text)
    return f"{ONT}/{m.name}/"


def approval_file(tree, m, date):
    """The sentence that approved the first release, when it is a file of its own. The module's entry names it."""
    if not m.approval_text:
        return None
    tree.new(f"{ONT}/{m.approval[0]}", m.approval_text)
    return f"{ONT}/{m.approval[0]}"


def release_builder(tree, m, date):
    """An entry in MODULES: what the package is built from, its version, who approved it and what it requires."""
    e = m.entry(date)
    lists = lambda values: "[" + ", ".join(py(v) for v in values) + "]"
    comment = "".join(f"        # {line}\n" for line in m.entry_comment)
    entry = (f"\n    {py(m.name)}: {{\n"
             f"        \"title\": {py(e['title'])},\n"
             f"        \"description\": {py(e['description'])},\n" + comment +
             f"        \"version\": {py(e['version'])}, \"stage\": None, \"approver\": {py(e['approver'])}, \"issued\": {py(date)},\n"
             f"        \"approval\": ({py(e['approval'][0])}, {py(e['approval'][1])}),\n"
             f"        \"parts\": {lists(e['parts'])},\n"
             f"        \"shapes\": {lists(e['shapes'])},\n"
             f"        \"depends_on\": {lists(e['depends_on'])},\n"
             f"        \"decisions\": {lists(e['decisions'])},\n"
             f"    }},")
    tree.after(f"{ONT}/release/build_module.py", r'^    "lane": \{\n(?:.*\n)*?    \},', entry)
    return f"{ONT}/release/build_module.py"


def changelog(tree, m, date):
    """The module's changelog: a title line, then the section of the first release."""
    tree.new(f"{ONT}/releases/{m.name}/CHANGELOG.md", m.changelog)
    return f"{ONT}/releases/{m.name}/CHANGELOG.md"


def check_script(tree, m, date):
    """Three lines: the package's --verify, the builder's --verify, and the test file in the test list."""
    path = "scripts/check.sh"
    tree.after(path, r"^\(cd \$ONT/release && run with_deps python build_module\.py lane --verify\)\n",
               f"(cd $ONT/release && run with_deps python build_module.py {m.name} --verify)\n")
    tree.after(path, r"^\(cd \$ONT/lane && run with_deps python build_lanes\.py --verify\)\n",
               f"(cd $ONT/{m.name} && run with_deps python {m.builder} --verify)\n")
    tree.after(path, r"^  business_architecture/ontology/lane/test_lanes\.py \\\n",
               f"  business_architecture/ontology/{m.name}/{m.test} \\\n")
    return path


def projection_lists(tree, m, date):
    """The projection's package list, its list of own namespaces and its fixed prefixes."""
    path = f"{ONT}/projection/pipeline.py"
    tree.after(path, r'\("lane", "[^"]+"\),', f' ({py(m.name)}, {py(m.version)}),')
    tree.after(path, r'"system", "lane",', f' {py(m.name)},')
    tree.after(path, r'^    "lane": "https://w3id\.org/mpc/ontology/modules/lane/",\n', f'    {py(m.prefix)}: {py(m.namespace)},\n')
    return path


def projection_config(tree, m, date):
    """The same three facts in the skill's projection configuration."""
    path = f"{ONT}/projection/skill-run/epm-config.json"
    tree.after(path, r'^    "https://w3id\.org/mpc/ontology/modules/lane/",\n', f'    {py(m.namespace)},\n')
    tree.after(path, r'^    "lane": "https://w3id\.org/mpc/ontology/modules/lane/",\n', f'    {py(m.prefix)}: {py(m.namespace)},\n')
    tree.after(path, r'^    "lane": "\d[^"]*",\n', f'    {py(m.name)}: {py(m.version)},\n')
    return path


def question_number(tree):
    """The number the new competency question takes: one after the highest in expected.csv."""
    rows = list(csv.DictReader(io.StringIO(tree.read(f"{ONT}/regression/expected.csv"))))
    return max(int(r["question"]) for r in rows) + 1


def regression(tree, m, date):
    """The module's competency question: its row in expected.csv, its query, and the module's files in run.py."""
    n = tree.question
    name = f"q{n}-{m.query_name}.rq"
    tree.new(f"{ONT}/regression/queries/{name}", f"# Q{n} {m.question}\n{m.query}")
    expected = tree.read(f"{ONT}/regression/expected.csv")
    end = "\r\n" if expected.endswith("\r\n") else "\n"
    tree.texts[f"{ONT}/regression/expected.csv"] = expected + f"{n},answerable,{name},{end}"
    files = ", ".join(py(f) for f in m.regression_files) + ("," if len(m.regression_files) == 1 else "")
    tree.after(f"{ONT}/regression/run.py", r'^    \+ \[os\.path\.join\(HERE, "\.\.", "lane", n\) for n in \("vocabulary\.ttl", "lanes\.ttl"\)\] \\\n',
               f'    + [os.path.join(HERE, "..", {py(m.name)}, n) for n in ({files})] \\\n')
    return f"{ONT}/regression/"


def shape_list(tree, m, date):
    """The module's shapes in the test that runs every module's shapes over the whole graph."""
    tree.after(f"{ONT}/validation/test_all_module_shapes.py", r'"lane/shapes\.ttl",', f' {py(m.name + "/shapes.ttl")},')
    return f"{ONT}/validation/test_all_module_shapes.py"


def questions(tree, m, date):
    """The new question, numbered after the last, in a section of its own, numbered after the last section."""
    path = f"{ONT}/competency-questions.md"
    text = tree.read(path)
    sections = [from_roman(s) for s in re.findall(r"^## ([IVXLCDM]+)\. ", text, re.M)]
    if not sections:
        raise Refused(f"{path} holds no numbered section")
    tree.texts[path] = text.rstrip("\n") + (f"\n\n## {roman(max(sections) + 1)}. {m.question_heading} (added {date})\n"
                                             f"{m.question_intro}\n{tree.question}. {m.question}\n")
    return path


def modules_guide(tree, m, date):
    """A row in the table of what each package is built from, and a section with an example from the release."""
    path = f"{ONT}/MODULES.md"
    parts = ", ".join(f"`{p}`" for p in m.parts)
    tree.after(path, r"^\| `lane` \|.*\n", f"| `{m.name}` | {m.purpose} | {parts} | `{m.name}/shapes.ttl` |\n")
    tree.after(path, r"^### lane: .*\n(?:.*\n)*?(?=^### )", m.modules_section)
    return path


def pages(tree, m, date):
    """The module's folder in the list of READMEs that get an HTML page."""
    tree.after("scripts/build_docs_html.py", r'^MODULE_READMES = \["kpi", "lane",', f' {py(m.name)},')
    return "scripts/build_docs_html.py"


PLACES = (module_folder, approval_file, release_builder, changelog, check_script, projection_lists, projection_config,
          regression, shape_list, questions, modules_guide, pages)


# ---- the edits, read back ---------------------------------------------------------------------------

def _assigned(text, name, path):
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return node.value
    raise Refused(f"{path} holds no {name} after the edit")


def check_places(tree, m, date):
    """Reads each edited file back and refuses an edit that does not hold the module as meant."""
    def wrong(path, what):
        raise Refused(f"{path} does not hold the module {m.name} as meant after the edit: {what}. Nothing was changed")
    path = f"{ONT}/release/build_module.py"
    try:
        modules = ast.literal_eval(_assigned(tree.read(path), "MODULES", path))
    except (SyntaxError, ValueError) as err:
        wrong(path, f"the MODULES table cannot be read ({err})")
    if modules.get(m.name) != m.entry(date):
        wrong(path, "its entry in MODULES differs")
    path = f"{ONT}/projection/pipeline.py"
    text = tree.read(path)
    try:
        packages = ast.literal_eval(_assigned(text, "PACKAGES", path))
        prefixes = _assigned(text, "PREFIXES", path)
        own = _assigned(text, "OWN", path)
    except (SyntaxError, ValueError) as err:
        wrong(path, f"it cannot be read ({err})")
    held = {k.value: v for k, v in zip(prefixes.keys, prefixes.values) if isinstance(k, ast.Constant)}
    keys = [k.value for k in prefixes.keys if isinstance(k, ast.Constant)]
    twice = sorted({k for k in keys if keys.count(k) > 1})
    if twice:
        wrong(path, f"PREFIXES binds {', '.join(twice)} twice")
    names = [c.value for c in ast.walk(own) if isinstance(c, ast.Constant)]
    if (m.name, m.version) not in packages or m.name not in names or \
            not isinstance(held.get(m.prefix), ast.Constant) or held[m.prefix].value != m.namespace:
        wrong(path, "PACKAGES, OWN or PREFIXES lacks it")
    path = f"{ONT}/projection/skill-run/epm-config.json"
    def once(pairs):
        keys = [k for k, _ in pairs]
        twice = sorted({k for k in keys if keys.count(k) > 1})
        if twice:
            raise ValueError(f"{', '.join(twice)} twice")
        return dict(pairs)
    try:
        config = json.loads(tree.read(path), object_pairs_hook=once)
    except ValueError as err:
        wrong(path, f"it is not JSON with each key once ({err})")
    if m.namespace not in config["own_namespaces"] or config["prefixes"].get(m.prefix) != m.namespace or \
            config["packages"].get(m.name) != m.version:
        wrong(path, "own_namespaces, prefixes or packages lacks it")
    path = f"{ONT}/validation/test_all_module_shapes.py"
    listed = [c.value for c in _assigned(tree.read(path), "SHAPE_FILES", path).elts if isinstance(c, ast.Constant)]
    if f"{m.name}/shapes.ttl" not in listed:
        wrong(path, "SHAPE_FILES lacks its shapes")
    path = "scripts/build_docs_html.py"
    if m.name not in ast.literal_eval(_assigned(tree.read(path), "MODULE_READMES", path)):
        wrong(path, "MODULE_READMES lacks it")
    path = f"{ONT}/regression/run.py"
    try:
        ast.parse(tree.read(path))
    except SyntaxError as err:
        wrong(path, f"it no longer parses ({err})")
    lines = tree.read("scripts/check.sh").splitlines()
    for line in (f"(cd $ONT/release && run with_deps python build_module.py {m.name} --verify)",
                 f"(cd $ONT/{m.name} && run with_deps python {m.builder} --verify)",
                 f"  business_architecture/ontology/{m.name}/{m.test} \\"):
        if lines.count(line) != 1:
            wrong("scripts/check.sh", f"the line {line!r} is not there once")


def register(m, root, date, write=False):
    """Registers the module in every place, or only works it out (write=False). Returns the places, in order.
    Raises Refused with nothing changed."""
    if os.path.exists(os.path.join(root, ONT, m.name)) or os.path.exists(os.path.join(root, ONT, "releases", m.name)):
        raise Refused(f"this release holds the module {m.name} already; nothing was changed")
    tree = Tree(root)
    tree.question = question_number(tree)   # worked out once: the regression's place adds a row to expected.csv
    done = [place(tree, m, date) for place in PLACES]
    check_places(tree, m, date)
    if write:
        tree.save()
    return [p for p in done if p]
