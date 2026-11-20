"""A domain activation's change: a data domain of kpi-intake/settings.toml made active, or added and made active
(KPI-DEC-0002, Q10 form 3; KPI-DEC-0004, item 1).

The ontology holds no list of data domains: question 1.5 of the KPI form reads the list of settings.toml, and the
catalogue says of D1 "The ontology has no place for a domain yet". So a domain activation changes that list only,
and its proposal holds facts and no KGCL line. Each fact is one field of one entry of the list:

    domain:<id>,active,true              the domain is active
    domain:<id>,description,<text>       D2, when it differs from the description the list holds
    domain:<id>,label,<name>             D1, for a domain the list does not hold yet

A domain the list does not hold yet is added at the end of the list, with the short key of D1 as its id. A domain
that is active already is refused, and so is a name or a description that a line of settings.toml cannot hold.

edit makes the change by a text edit of settings.toml that keeps every comment and every other line, and then
checks the parsed result: the list must differ from the old one by exactly the facts, and the rest of the file not
at all. compare is the round trip: the facts that take one settings.toml to another.
"""
import json
import tomllib
from pathlib import Path

from . import ChangeRefused

SETTINGS = Path("kpi-intake") / "settings.toml"
HEADER = "[[list.domains]]"
FIELDS = ("label", "description", "active")
PREFIX = "domain:"
_LAYOUT = (f"{SETTINGS.as_posix()} is not laid out as the release ships it: each domain must be a {HEADER} block "
           "with one line for each of id, label, description and active. It needs a specialist")


def read(root):
    """The text of settings.toml and its list of domains."""
    path = Path(root) / SETTINGS
    try:
        text = path.read_text(encoding="utf-8")
        data = tomllib.loads(text)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
        raise ChangeRefused(f"{SETTINGS.as_posix()} cannot be read ({type(err).__name__}): it is not a KPI Store "
                            "release") from None
    return text, data.get("list", {}).get("domains", [])


def one_line(text):
    """A form's text as one line, with each run of spaces and line breaks as one space."""
    return " ".join(str(text).split())


def facts_of(name, description, domains, slug):
    """The facts that make the domain named `name` active, with `description` (D2). `slug` gives a new domain's id
    from its name. Refuses a domain that is active already."""
    name, description = one_line(name), one_line(description)
    if not name or not description:
        raise ChangeRefused("a domain activation needs the domain's name (D1) and what data it covers (D2)")
    found = [d for d in domains if str(d.get("label", "")).casefold() == name.casefold()
             or str(d.get("id", "")).casefold() == name.casefold()]
    if found:
        domain = found[0]
        if domain.get("active") is True:
            raise ChangeRefused(f'the domain "{domain["label"]}" is active already. A KPI can be added to it now, and '
                                "it needs no domain activation")
        subject = PREFIX + domain["id"]
        facts = [(subject, "description", description)] if description != domain.get("description") else []
        return facts + [(subject, "active", "true")]
    key = slug(name)
    if not key:
        raise ChangeRefused(f'D1: "{name}" has no letter or digit to make the short key of the domain from')
    if any(d.get("id") == key for d in domains):
        raise ChangeRefused(f'D1: the short key of "{name}" is {key}, and another domain of {SETTINGS.as_posix()} has '
                            "it. Name the domain as the list does, or give it a name of its own")
    subject = PREFIX + key
    return [(subject, "label", name), (subject, "description", description), (subject, "active", "true")]


def _wanted(domains, facts):
    """The list of domains as the facts leave it."""
    out = [dict(d) for d in domains]
    held, seen = {d.get("id") for d in domains}, set()
    for subject, prop, value in facts:
        key = subject[len(PREFIX):]
        if not subject.startswith(PREFIX) or not key or prop not in FIELDS:
            raise ChangeRefused(f"a domain activation's fact is domain:<id>,<{', '.join(FIELDS)}>,<value>: "
                                f"{subject},{prop},{value}")
        if (key, prop) in seen:
            raise ChangeRefused(f"{subject} gets two {prop} facts")
        seen.add((key, prop))
        entry = next((d for d in out if d.get("id") == key), None)
        if entry is None:
            entry = {"id": key}
            out.append(entry)
        if prop == "active":
            if value != "true":
                raise ChangeRefused(f"a domain activation makes a domain active, and {subject} gets active {value}")
            if entry.get("active") is True:
                raise ChangeRefused(f'the domain "{entry.get("label")}" is active already, so {subject} needs no domain '
                                    "activation")
            entry["active"] = True
        else:
            if not value or value != one_line(value):
                raise ChangeRefused(f"the {prop} of {subject} must be one line of text, and is {value!r}")
            if key in held and prop == "label":
                raise ChangeRefused(f"the list holds {subject} already, and a domain activation keeps its name")
            if entry.get(prop) == value:
                raise ChangeRefused(f"{subject} has that {prop} already: {value!r}")
            entry[prop] = value
    for key in sorted({k for k, _ in seen} - {k for k, p in seen if p == "active"}):
        raise ChangeRefused(f"a domain activation makes a domain active, and {PREFIX}{key} gets no active,true fact")
    for entry in out:
        missing = [f for f in ("id", *FIELDS) if f not in entry]
        if missing:
            raise ChangeRefused(f"{PREFIX}{entry['id']} is a new domain, and the facts give it no {', no '.join(missing)}")
    return out


def _blocks(lines):
    """(first, end) of each domain block: its header line, and the line after its last field."""
    out = []
    for i, line in enumerate(lines):
        if line.strip() == HEADER:
            end = i + 1
            while end < len(lines) and lines[end].strip() and not lines[end].lstrip().startswith(("[", "#")):
                end += 1
            out.append((i, end))
    return out


def _value(value):
    return "true" if value is True else json.dumps(value, ensure_ascii=False)


def edit(text, facts):
    """settings.toml's text with the facts made, and its list of domains after them. Raises ChangeRefused when a
    fact does not fit, or when the file is not laid out as the release ships it."""
    data = tomllib.loads(text)
    domains = data.get("list", {}).get("domains", [])
    wanted = _wanted(domains, facts)
    lines = text.split("\n")
    blocks = _blocks(lines)
    if len(blocks) != len(domains) or not blocks:
        raise ChangeRefused(_LAYOUT)
    for (first, end), domain in zip(blocks, domains):
        entry = next(w for w in wanted if w["id"] == domain["id"])
        for prop in FIELDS:
            if entry[prop] == domain.get(prop):
                continue
            at = [i for i in range(first + 1, end) if lines[i].split("=", 1)[0].strip() == prop]
            if len(at) != 1:
                raise ChangeRefused(_LAYOUT)
            lines[at[0]] = f"{prop} = {_value(entry[prop])}"
    added = [w for w in wanted if w["id"] not in {d["id"] for d in domains}]
    last = blocks[-1][1]
    for entry in reversed(added):
        lines[last:last] = ["", HEADER] + [f"{f} = {_value(entry[f])}" for f in ("id", *FIELDS)]
    new = "\n".join(lines)
    try:   # the parsed result: exactly the list the facts give, and the rest of the file as it was
        parsed = tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        raise ChangeRefused(_LAYOUT) from None
    rest, old_rest = dict(parsed), dict(data)
    got = rest.pop("list", {}).copy()
    kept = old_rest.pop("list", {}).copy()
    if got.pop("domains", None) != wanted or got != {k: v for k, v in kept.items() if k != "domains"} or rest != old_rest:
        raise ChangeRefused(_LAYOUT)
    return new, wanted


def check_changes(facts, root):
    """Raises ChangeRefused when the facts do not fit the release's settings.toml. Writes nothing."""
    edit(read(root)[0], facts)


def apply_changes(facts, root):
    """Writes the facts into settings.toml of `root`, which must be a scratch copy of the release."""
    new, _ = edit(read(root)[0], facts)
    with (Path(root) / SETTINGS).open("w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    return Path(root) / SETTINGS


def compare(before, after):
    """The facts that take the list of domains of settings.toml at `before` (a release folder) to the one at `after`.
    Refuses a removed domain, a domain made inactive, a changed id, a domain that is not one id, label, description
    and active, and any change outside the list of domains."""
    (old_text, old), (new_text, new) = read(before), read(after)
    rest = lambda text: {**tomllib.loads(text), "list": {k: v for k, v in tomllib.loads(text).get("list", {}).items()
                                                         if k != "domains"}}
    if rest(old_text) != rest(new_text):
        raise ChangeRefused(f"{SETTINGS.as_posix()} changed outside its list of domains")
    for d in new:
        if set(d) != {"id", *FIELDS} or not all(isinstance(d[f], str) and d[f] for f in ("id", "label", "description")) \
                or not isinstance(d["active"], bool):
            raise ChangeRefused(f"a domain of {SETTINGS.as_posix()} is not one id, label, description and active: {d}")
    ids = [d["id"] for d in new]
    if len(ids) != len(set(ids)):
        raise ChangeRefused(f"a domain is in {SETTINGS.as_posix()} twice: {sorted({i for i in ids if ids.count(i) > 1})}")
    held = {d.get("id"): d for d in old}
    if not set(held) <= set(ids):
        raise ChangeRefused(f"a domain left {SETTINGS.as_posix()}: {sorted(set(held) - set(ids))}")
    rows = []
    for d in new:
        was = held.get(d["id"], {})
        for prop in FIELDS:
            if d[prop] == was.get(prop):
                continue
            if prop == "active" and d[prop] is not True:
                raise ChangeRefused(f"the domain {d['id']} is no longer active")
            rows.append((PREFIX + d["id"], prop, "true" if d[prop] is True else d[prop]))
    return sorted(rows)
