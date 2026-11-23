"""The ontology-change skill names the guides' sections by heading and relies on lines the commands print.

The skill gives no command of its own: it sends the agent to a section of HANDOUT.md, HOW-TO-UPDATE.md or
kpi-intake/README.md by its heading, and it reads the form check's and the apply's printed lines to know when a step
is done. A renamed heading or a changed line would leave the agent looking for something that is gone. So each name
the skill quotes is listed below with the one guide it belongs to, and must still be a heading (with or without the
handout's section number) or a numbered step of that guide; each printed line must still be in the code that prints
it. A name the skill quotes that is not listed fails too, so a new reference gets its guide named here.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ontology-change" / "SKILL.md"
HANDOUT, GUIDE, INTAKE = "HANDOUT.md", "HOW-TO-UPDATE.md", "kpi-intake/README.md"

# Each double-quoted name in SKILL.md, and the guide it names.
NAMES = {
    "What is inside the release": HANDOUT,
    "The conventions": HANDOUT,
    "Make an everyday change with a form": HANDOUT,
    "3. Make an everyday change with a form": HANDOUT,
    "Add a module": HANDOUT,
    "Let an AI help": HANDOUT,
    "Suggestions for a form": HANDOUT,
    "A draft of new modelling": HANDOUT,
    "After you change the forms' settings": HANDOUT,
    "Upgrade the tools from a newer release": HANDOUT,
    "Check the release and recover": HANDOUT,
    "After every change": HANDOUT,
    "Refresh what people use": HANDOUT,
    "After a change of sections 3 to 5: give people the new forms": HANDOUT,
    "When a run fails": HANDOUT,
    "Replace what a store holds, or reset every store": HANDOUT,
    "See the commit": HANDOUT,
    "Propose a KPI with the forms it waits on": GUIDE,
    "Who does what": INTAKE,
    "How an interview runs": INTAKE,
    "Where an answer routes the request": INTAKE,
}
# Lines the commands print that the skill reads: the phrase as the skill writes it, the text the code prints, and
# the file of that code. The skill's phrase must be in SKILL.md, and the printed text must be in a string the code
# holds (a comment or a docstring does not count).
PRINTED = {
    '"Result: not complete"': ("Result: not complete", "kpi_store/intake/check.py"),
    "starts `Done.`": ("Done. ", "kpi_store/apply.py"),
    "no store needs loading": ("No store needs loading", "kpi_store/apply.py"),
    "a line that says what to run next": ("Run the full check", "kpi_store/apply.py"),
}
# The double-quoted printed line in SKILL.md, which is not a section name.
QUOTED_PRINTED = {"Result: not complete"}


def strings_in(source):
    """Every string the code holds, f-strings' text parts included, but not its docstrings or its comments."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]


def names_in(text):
    names = set()
    for line in text.splitlines():
        heading = re.match(r"#{1,6} +(.+?) *$", line)
        if heading:
            names.add(heading.group(1))
            names.add(re.sub(r"^\d+\. +", "", heading.group(1)))
        step = re.match(r"\d+\. +(.+?)\.? *$", line)
        if step:
            names.add(step.group(1))
    return names


def quoted(text):
    return sorted(set(re.findall(r'"([^"\n]+)"', text)))


def unlisted(skill_text):
    return [name for name in quoted(skill_text) if name not in NAMES and name not in QUOTED_PRINTED]


def missing(names, guides):
    """The names that are no longer in their own guide. names maps a name to a guide; guides maps a guide to text."""
    found = {guide: names_in(text) for guide, text in guides.items()}
    return sorted(name for name, guide in names.items() if name not in found[guide])


def missing_printed(printed, skill_text, sources):
    """The skill phrases that are gone from the skill, and the printed texts that are in no string of their code."""
    gone = [phrase for phrase in printed if phrase.casefold() not in skill_text.casefold()]
    for phrase, (text, path) in printed.items():
        if not any(text in s for s in strings_in(sources[path])):
            gone.append(text)
    return sorted(gone)


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_name_the_skill_quotes_has_its_guide():
    assert unlisted(SKILL.read_text(encoding="utf-8")) == []


def test_every_name_is_in_its_own_guide():
    assert missing(NAMES, {g: read(g) for g in (HANDOUT, GUIDE, INTAKE)}) == []


def test_every_printed_line_is_in_the_skill_and_in_its_code():
    sources = {path: read(path) for _, path in PRINTED.values()}
    assert missing_printed(PRINTED, SKILL.read_text(encoding="utf-8"), sources) == []


def test_the_skill_quotes_names():
    assert len(quoted(SKILL.read_text(encoding="utf-8"))) >= 15


def test_a_new_name_without_a_guide_is_found():
    assert unlisted('Follow "The conventions" and "A section nobody listed".') == ["A section nobody listed"]


def test_a_heading_renamed_in_its_own_guide_is_found_though_another_guide_has_it():
    names = {"Upgrade the tools from a newer release": HANDOUT}
    guides = {HANDOUT: "## 8. Upgrade the tools from the next release\n",
              GUIDE: "## Upgrade the tools from a newer release\n"}
    assert missing(names, guides) == ["Upgrade the tools from a newer release"]


def test_a_numbered_step_and_a_numbered_heading_are_found():
    guides = {HANDOUT: "## 6. Check the release and recover\n\n5. See the commit.\n"}
    assert missing({"Check the release and recover": HANDOUT, "See the commit": HANDOUT}, guides) == []


def test_an_apply_line_that_is_gone_or_only_in_a_comment_is_found():
    printed = {"starts `Done.`": ("Done. ", "apply.py"), "no store needs loading": ("No store needs loading", "apply.py")}
    skill = "Done when it prints a line that starts `Done.`; when it said no store needs loading, the check is enough."
    commented = 'say(f"Done. {key} is now active.")\n# No store needs loading\n'
    assert missing_printed(printed, skill, {"apply.py": commented}) == ["No store needs loading"]
    docstring = 'def f():\n    """No store needs loading"""\n    say(f"Done. {k}")\n'
    assert missing_printed(printed, skill, {"apply.py": docstring}) == ["No store needs loading"]


def test_a_changed_phrase_in_the_skill_is_found():
    printed = {"starts `Done.`": ("Done. ", "apply.py")}
    assert missing_printed(printed, "Done when it prints a line that starts `Finished.`", {"apply.py": 'say("Done. x")'}) \
        == ["starts `Done.`"]


def test_a_next_step_line_that_is_gone_is_found():
    printed = {"a line that says what to run next": ("Run the full check", "apply.py")}
    skill = "Done when each run prints a line that starts `Done.`, and after it a line that says what to run next."
    assert missing_printed(printed, skill, {"apply.py": 'say("Done. x")\nsay("Load the stores")'}) == ["Run the full check"]
