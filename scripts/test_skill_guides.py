"""The ontology-change skill names the guides' sections by heading and relies on lines the commands print.

The skill gives no command of its own: it sends the agent to a section of HANDOUT.md, HOW-TO-UPDATE.md or
kpi-intake/README.md by its heading, and it reads the form check's and the apply's printed lines to know when a step
is done. A renamed heading or a changed line would leave the agent looking for something that is gone. So each name
the skill quotes is listed below with the one guide it belongs to, and must still be a heading (with or without the
handout's section number) or a numbered step of that guide; each printed line must still be in the code that prints
it. A name the skill quotes that is not listed fails too, so a new reference gets its guide named here.
"""
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
# Lines the commands print that the skill reads, and the file of the code that prints each.
PRINTED = {
    "Result: not complete": "kpi_store/intake/check.py",
    "Done. ": "kpi_store/apply.py",
    "No store needs loading": "kpi_store/apply.py",
    "Run the full check before you load": "kpi_store/apply.py",
}
# The double-quoted printed line in SKILL.md; the others it names with backticks or in a sentence.
QUOTED_PRINTED = {"Result: not complete"}


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


def missing_printed(printed, sources):
    return sorted(line for line, path in printed.items() if line not in sources[path])


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_name_the_skill_quotes_has_its_guide():
    assert unlisted(SKILL.read_text(encoding="utf-8")) == []


def test_every_name_is_in_its_own_guide():
    assert missing(NAMES, {g: read(g) for g in (HANDOUT, GUIDE, INTAKE)}) == []


def test_every_printed_line_is_in_its_code():
    assert missing_printed(PRINTED, {p: read(p) for p in set(PRINTED.values())}) == []


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


def test_an_apply_line_that_is_gone_is_found():
    printed = {"Done. ": "apply.py", "No store needs loading": "apply.py", "Result: not complete": "check.py"}
    sources = {"apply.py": 'say(f"Done. {key} is now active.")', "check.py": "Result: not complete"}
    assert missing_printed(printed, sources) == ["No store needs loading"]
