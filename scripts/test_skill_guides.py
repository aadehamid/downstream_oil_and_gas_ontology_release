"""The ontology-change skill names the guides' sections by heading and quotes a line the form check prints.

The skill gives no command of its own: it sends the agent to a section of HANDOUT.md, HOW-TO-UPDATE.md or
kpi-intake/README.md by its heading. A renamed heading would leave the agent looking for a section that is gone,
so every name the skill quotes must still be a heading (with or without the handout's section number), or a
numbered step, in one of those three files; a printed line it quotes must still be in the code that prints it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ontology-change" / "SKILL.md"
GUIDES = ("HANDOUT.md", "HOW-TO-UPDATE.md", "kpi-intake/README.md")
# A quoted line that a command prints, not a heading: the file of the code that prints it.
PRINTED = {"Result: not complete": "kpi_store/intake/check.py"}


def names_in_guides(texts):
    names = set()
    for text in texts:
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


def missing(skill_text, guide_texts, printed_texts):
    names = names_in_guides(guide_texts)
    gone = []
    for name in quoted(skill_text):
        if name in PRINTED:
            if name not in printed_texts[name]:
                gone.append(name)
        elif name not in names:
            gone.append(name)
    return gone


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_name_the_skill_quotes_is_in_the_guides():
    printed = {name: read(path) for name, path in PRINTED.items()}
    assert missing(SKILL.read_text(encoding="utf-8"), [read(g) for g in GUIDES], printed) == []


def test_the_skill_quotes_names():
    assert len(quoted(SKILL.read_text(encoding="utf-8"))) >= 15


def test_a_renamed_heading_is_found():
    guide = "## 6. Check the release and recover\n\n### After every change\n\n5. See the commit.\n"
    skill = 'Follow "Check the release and recover", "After every change", "See the commit" and "When a run fails".'
    assert missing(skill, [guide], {}) == ["When a run fails"]


def test_a_printed_line_that_is_gone_is_found():
    skill = 'Its check prints "Result: not complete".'
    assert missing(skill, [""], {"Result: not complete": "Result: the intake is complete."}) == ["Result: not complete"]
