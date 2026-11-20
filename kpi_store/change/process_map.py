"""A process map request's change: new roles, and new RACI entries for processes the map holds (KPI-DEC-0002, Q10
form 2; KPI-DEC-0004, item 1).

The organization module builds its roles and its RACI from three sources (HOW-TO-UPDATE.md, "Change the RACI"): the
`raci` lists of business_architecture/business_process/downstream_process_map.json, organization/role-register.csv,
which maps each name in those lists to a role, and organization/roles.csv, which defines each role. What each line
writes:

    a new role       a row of roles.csv (a position) and a row of role-register.csv (its name, rule exact)
                     create node role:<slug> '<its name>'
                     add definition '<what it does>' to role:<slug>
                     facts.csv: role:<slug>,skos:editorialNote,<the documents the request cites>
    a RACI entry     the role's name in one of the four lists of the process's `raci` object in the map
                     create edge asg:<process>--<level>--<role>--<digest> orgm:forProcess proc:<process>
                     create edge asg:<process>--<level>--<role>--<digest> orgm:assignedRole role:<the live role>
                     create edge asg:<process>--<level>--<role>--<digest> orgm:raciLevel raci:<level>
                     facts.csv: asg:<...>,orgm:sourceRoleText,<the role's name as the map holds it>

The assignment's id is build_assignments.py's: the process, the level, the role the name is registered to, and the
first eight hex digits of the SHA-256 of the name. A RACI entry names one role, of the register or new in the same
request, and a process the map and the identity map hold, or one the same request adds. A new business area, process
or step is core_release.py's, which writes the map and the identity map first.

apply_changes works on a scratch copy of the release. It edits the map as text, then checks the parsed result: the
map must differ from the old one by exactly the entries added. compare is the round trip of roles.ttl and
assignments.ttl.
"""
import hashlib
import json
from pathlib import Path

from .. import cut
from . import ChangeRefused, kgcl

BASE = "https://w3id.org/mpc/ontology/"
# The namespaces of build_roles.py and build_assignments.py; a test checks that they are the builders'.
PREFIXES = {"role": BASE + "modules/organization/role/", "asg": BASE + "modules/organization/assignment/",
            "raci": BASE + "modules/organization/raci-level/", "orgm": BASE + "modules/organization/",
            "proc": BASE + "process/", "skos": "http://www.w3.org/2004/02/skos/core#"}
LEVELS = ("responsible", "accountable", "consulted", "informed")
FOLDER = cut.ONTOLOGY / "organization"
MAP = Path("business_architecture") / "business_process" / "downstream_process_map.json"
IDENTITY = cut.ONTOLOGY / "build" / "output" / "step2-identity-map.json"
BUILT = {"roles": FOLDER / "roles.ttl", "assignments": FOLDER / "assignments.ttl"}
BUILDERS = ((FOLDER, "build_roles.py"), (FOLDER, "build_assignments.py"))
TESTS = (("organization", FOLDER, "test_roles"), ("organization", FOLDER, "test_assignments"))
NOTE, TEXT = "skos:editorialNote", "orgm:sourceRoleText"
EDGES = ("orgm:forProcess", "orgm:assignedRole", "orgm:raciLevel")
_LAYOUT = f"{MAP.as_posix()} is not laid out as the release ships it, so its RACI entries cannot be added; it needs a specialist"


def tail(text):
    return text.split(":", 1)[1]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def assignment(process, level, role, text):
    """The id of an assignment, as build_assignments.py makes it."""
    return f"asg:{process}--{level}--{role}--{digest(text)}"


def entry_changes(process, level, role, live, text):
    """The lines and the fact of one RACI entry."""
    a = assignment(process, level, role, text)
    edge = lambda predicate, target: kgcl.Change("create edge", a, predicate=predicate, target=target)
    return ([edge("orgm:forProcess", f"proc:{process}"), edge("orgm:assignedRole", f"role:{live}"),
             edge("orgm:raciLevel", f"raci:{level}")], (a, TEXT, text))


def tables(root):
    try:
        return cut.Tables(root, FOLDER, ("roles", "role-register"))
    except cut.CutRefused:
        raise ChangeRefused(f"{root} holds no organization tables: it is not a KPI Store release") from None


def read_map(root):
    """The map's text and its parsed content. Refuses a map whose text is not what json.dumps writes, since only that
    layout can be written back unchanged."""
    path = Path(root) / MAP
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ChangeRefused(f"{MAP.as_posix()} cannot be read ({type(err).__name__}): it is not a KPI Store release") from None
    if _dump(text, data) != text:
        raise ChangeRefused(_LAYOUT)
    return text, data


def _dump(text, data):
    """The map's text as the release lays it out: the blank lines it starts with, then json.dumps with an indent of
    two, then a line end."""
    lead = text[:len(text) - len(text.lstrip("\n"))]
    return lead + json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def processes(data):
    """Each node of the map that has an id, by its id."""
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("id"):
                out.setdefault(node["id"], node)
            for child in node.get("children", []):
                walk(child)
    for root in data:
        walk(root)
    return out


def slugs(root):
    """Each process's slug (the end of its IRI) by its id in the map, from the identity map."""
    try:
        rows = json.loads((Path(root) / IDENTITY).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ChangeRefused(f"{IDENTITY.as_posix()} cannot be read ({type(err).__name__}): it is not a KPI Store release") from None
    return {r["skos_notation"]: r["uri"].rsplit("/", 1)[1] for r in rows if r.get("skos_notation")}


def split(changes, facts):
    """A process map request's change as its parts: ({slug: (label, definition, note)}, [(process slug, level,
    registered role, live role, text, id)]). Refuses a line or a fact that no part takes."""
    roles, edges, notes, texts = {}, {}, {}, {}
    for c in changes:
        line = kgcl.write_line(c)
        prefix = c.subject.split(":", 1)[0]
        part = {"create node": "label", "add definition": "definition"}.get(c.kind) if prefix == "role" else None
        if part:
            if part in roles.setdefault(tail(c.subject), {}):
                raise ChangeRefused(f"{c.subject} has two {c.kind} lines")
            roles[tail(c.subject)][part] = c.text
        elif prefix == "asg" and c.kind == "create edge" and c.predicate in EDGES:
            edges.setdefault(c.subject, {}).setdefault(c.predicate, []).append(c.target)
        else:
            raise ChangeRefused("a process map request adds roles (create node and add definition of role:<slug>) and "
                                f"RACI entries (orgm:forProcess, orgm:assignedRole and orgm:raciLevel of asg:<id>): {line}")
    for subject, prop, value in facts:
        if subject.startswith("role:") and prop == NOTE:
            if tail(subject) in notes:
                raise ChangeRefused(f"{subject} has two {NOTE} facts")
            notes[tail(subject)] = value
        elif subject.startswith("asg:") and prop == TEXT and subject not in texts:
            texts[subject] = value
        else:
            raise ChangeRefused(f"a process map request's fact is role:<slug>,{NOTE},<text> or asg:<id>,{TEXT},<text>: "
                                f"{subject},{prop},{value}")
    new = {}
    for slug, parts in roles.items():
        if set(parts) != {"label", "definition"} or slug not in notes:
            raise ChangeRefused(f"the new role role:{slug} needs a create node line, an add definition line and a "
                                f"{NOTE} fact")
        new[slug] = (parts["label"], parts["definition"], notes.pop(slug))
    if notes:
        raise ChangeRefused(f"a fact is about a role that no line makes: role:{sorted(notes)[0]}")
    entries = []
    for a, parts in edges.items():
        for p in EDGES:
            if len(parts.get(p, [])) != 1:
                raise ChangeRefused(f"{a} needs exactly one {p} line, and has {len(parts.get(p, []))}")
        [process], [live], [level] = (parts[p] for p in EDGES)
        if not (process.startswith("proc:") and live.startswith("role:") and level.startswith("raci:")) \
                or tail(level) not in LEVELS:
            raise ChangeRefused(f"{a} links a process (proc:), a role (role:) and a level (raci:{', raci:'.join(LEVELS)})")
        if a not in texts:
            raise ChangeRefused(f"{a} needs a {TEXT} fact: the role's name as the map holds it")
        text = texts.pop(a)
        prefix = f"asg:{tail(process)}--{tail(level)}--"
        registered = a[len(prefix):].rsplit("--", 1)[0] if a.startswith(prefix) else ""
        if a != assignment(tail(process), tail(level), registered, text):
            raise ChangeRefused(f"an assignment's id is <the process>--<the level>--<the role>--<the first 8 hex digits "
                                f"of the SHA-256 of the name>, and {a} is not one for {process}, {level} and {text!r}")
        entries.append((tail(process), tail(level), registered, tail(live), text, a))
    if texts:
        raise ChangeRefused(f"a fact is about an assignment that no line makes: {sorted(texts)[0]}")
    return new, entries


def _edit(changes, facts, root, after_core=None):
    """Every part checked against the release, and the new tables and map text in memory: (the tables, the map's new
    text). `after_core` is (the map's text, the identity map's rows) as a core part of the same request leaves them
    (core_release.py), so a RACI entry may name a process the request adds. Raises ChangeRefused when any part does
    not fit."""
    new, entries = split(changes, facts)
    t = tables(root)
    roles = {r["slug"]: r for r in t.rows["roles"]}
    register = {r["source_text"]: r for r in t.rows["role-register"]}
    labels = {s.casefold() for r in t.rows["roles"] for s in (r["label"], r["preferred_label"]) if s}
    for slug, (label, definition, note) in new.items():
        if slug in roles:
            raise ChangeRefused(f"role:{slug} is a role of the organization module already")
        if label.casefold() in labels or label in register:
            raise ChangeRefused(f'"{label}" is the name of a role of the organization module already')
        if not kgcl.ID.fullmatch(f"role:{slug}"):
            raise ChangeRefused(f"role:{slug} is not a role's id")
        t.rows["roles"].append({**{f: "" for f in t.fields["roles"]}, "slug": slug, "label": label, "kind": "position",
                                "definition": definition, "note": note})
        t.rows["role-register"].append({**{f: "" for f in t.fields["role-register"]}, "source_text": label,
                                        "roles": slug, "rule": "exact"})
        roles[slug] = t.rows["roles"][-1]
        register[label] = t.rows["role-register"][-1]
    if after_core:
        text, data = after_core[0], json.loads(after_core[0])
        slug_of = {r["skos_notation"]: r["uri"].rsplit("/", 1)[1] for r in after_core[1] if r.get("skos_notation")}
    else:
        text, data = read_map(root)
        slug_of = slugs(root)
    nodes = processes(data)
    by_slug = {s: n for n, s in slug_of.items()}
    named, touched = set(), {}
    for process, level, registered, live, name, a in entries:
        node = nodes.get(by_slug.get(process, ""))
        if node is None:
            raise ChangeRefused(f"proc:{process} is not a process of the process map, nor a new process of the same "
                                "request")
        row = register.get(name)
        if row is None or row["roles"].split(";") != [registered]:
            raise ChangeRefused(f'the name "{name}" is not registered to the one role role:{registered}')
        successor = roles[registered]["replaced_by"] or registered
        if live != successor:
            raise ChangeRefused(f"{a} names role:{live}, and the name {name!r} gives its assignments to role:{successor}")
        raci = node.get("raci", {})
        if name in raci.get(level, []):
            raise ChangeRefused(f'the process {node["id"]} has "{name}" as {level} already')
        if "raci" not in node:
            keys = list(node)
            at = keys.index("description") + 1 if "description" in keys else keys.index("name") + 1
            items = list(node.items())
            node.clear()
            node.update(items[:at] + [("raci", {lv: [] for lv in LEVELS})] + items[at:])
            raci = node["raci"]
        raci.setdefault(level, []).append(name)
        named.add(registered)
        touched[node["id"]] = raci
    # A process with RACI entries has an accountable role (the competency question q04b of regression/).
    lacking = sorted(pid for pid, raci in touched.items() if not raci.get("accountable"))
    if lacking:
        raise ChangeRefused(f"the process {lacking[0]} would have RACI entries and no accountable role. Add a line to P6 "
                            "that names who is accountable for it")
    unnamed = sorted(set(new) - named)
    if unnamed:
        raise ChangeRefused(f"the new role role:{unnamed[0]} is in no RACI entry. The organization module holds a role "
                            "only when a process names it: give it a line in P6")
    return t, _dump(text, data)


def check_changes(changes, facts, root, after_core=None):
    """Raises ChangeRefused when any part of a process map request does not fit the release. Writes nothing."""
    _edit(changes, facts, Path(root).resolve(), after_core)


def apply_changes(changes, facts, root):
    """Writes the new rows and the map into a scratch copy of the release and rebuilds the roles, then the
    assignments. Raises ChangeRefused, and writes nothing, when any part does not fit."""
    root = Path(root).resolve()
    t, text = _edit(changes, facts, root)
    t.write(root)
    with (root / MAP).open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    for folder, builder in BUILDERS:
        try:
            cut._run("rebuild the organization module", [builder, "--write"], root / folder)
        except cut.CutFailed as err:
            raise ChangeRefused(f"the organization builder refused the changed tables: {err}") from None
    return root / BUILT["assignments"]


def curie(value):
    fits = [(len(ns), p) for p, ns in PREFIXES.items() if str(value).startswith(ns) and len(str(value)) > len(ns)]
    if not fits:
        return None
    n, prefix = max(fits)
    return f"{prefix}:{str(value)[n:]}"


def compare(name, before, after):
    """The KGCL lines and facts that take roles.ttl or assignments.ttl, `before`, to `after` (files or Graphs).
    Raises ChangeRefused for a difference that no line and no fact of a process map request states."""
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS, XSD
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    removed, added = set(before) - set(after), set(after) - set(before)
    unsupported = [f"- {s} {p} {o}" for s, p, o in removed]
    held = set(before.subjects())
    source = URIRef(BASE + "source/downstream-process-map")
    kind = {"roles": ("role", URIRef("http://www.w3.org/ns/org#Role")),
            "assignments": ("asg", URIRef(PREFIXES["orgm"] + "ResponsibilityAssignment"))}[name]
    lines, rows, made, stated = [], [], set(), set()
    for s, p, o in added:
        subject = curie(s) or ""
        new = s not in held and subject.startswith(kind[0] + ":")
        if new and ((p, o) == (RDF.type, kind[1]) or (p, o) == (DCTERMS.source, source)):
            made.add(s)
            continue
        if name == "roles" and new and p == SKOS.prefLabel and isinstance(o, Literal) and o.language == "en":
            lines.append(kgcl.write_line(kgcl.Change("create node", subject, text=str(o))))
        elif name == "roles" and new and p == SKOS.definition and isinstance(o, Literal) and o.language == "en":
            lines.append(kgcl.write_line(kgcl.Change("add definition", subject, text=str(o))))
        elif name == "roles" and new and p == SKOS.editorialNote and isinstance(o, Literal) and o.language == "en":
            rows.append((subject, NOTE, str(o)))
        elif name == "assignments" and new and curie(p) in EDGES and isinstance(o, URIRef) and curie(o):
            lines.append(kgcl.write_line(kgcl.Change("create edge", subject, predicate=curie(p), target=curie(o))))
        elif name == "assignments" and new and curie(p) == TEXT and isinstance(o, Literal) and o.datatype == XSD.string:
            rows.append((subject, TEXT, str(o)))
        else:
            unsupported.append(f"+ {s} {p} {o!r}")
            continue
        stated.add(s)
    for s in made - stated:
        unsupported.append(f"{s} is new, and no line and no fact states it")
    for s in {s for s, _, _ in added if s not in held}:
        if (s, RDF.type, kind[1]) not in after or (s, DCTERMS.source, source) not in after:
            unsupported.append(f"{s} lacks its type or its source, the process map")
    if unsupported:
        raise ChangeRefused(f"the graphs differ in {len(unsupported)} ways that no line and no fact of a process map "
                            "request states: " + "; ".join(sorted(unsupported)[:10]))
    return sorted(lines), sorted(rows)
