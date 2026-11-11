"""An `expect` block against the output of the block before it."""
from __future__ import annotations

import re

from .registry import PLACEHOLDER


def normalise(text: str) -> list:
    """The lines of an output or of an `expect` block, as they are compared: line ends as LF, colour codes and
    spaces at a line's end removed, blank lines at the start and the end dropped."""
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def has_fixed_text(expected: str) -> bool:
    """True when at least one line holds text of its own. An empty block, a lone `...` or lines made only of
    placeholders would match any output, so they check nothing."""
    return any(line.strip() != "..." and PLACEHOLDER.sub("", line).strip() for line in normalise(expected))


def _line_pattern(expected: str):
    parts, at = [], 0
    for m in PLACEHOLDER.finditer(expected):
        parts.append(re.escape(expected[at:m.start()]))
        parts.append(".+?")
        at = m.end()
    parts.append(re.escape(expected[at:]))
    return re.compile("".join(parts))


def output_matches(expected: str, actual: str) -> bool:
    """True when the output is what the `expect` block shows. A placeholder such as <run id> stands for any text
    on its line; a line that is only `...` stands for any number of lines, also none. A block with no text of
    its own matches nothing."""
    if not has_fixed_text(expected):
        return False
    want, got = normalise(expected), normalise(actual)
    patterns = [None if line.strip() == "..." else _line_pattern(line) for line in want]
    # reach[j] is true when the expected lines read so far can end exactly at output line j.
    reach = [True] + [False] * len(got)
    for pattern in patterns:
        if pattern is None:
            first = next((j for j, ok in enumerate(reach) if ok), None)
            reach = [first is not None and j >= first for j in range(len(got) + 1)]
        else:
            reach = [False] + [reach[j] and bool(pattern.fullmatch(got[j])) for j in range(len(got))]
    return reach[len(got)]
