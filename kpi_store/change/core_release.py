"""A process map request's new processes, steps and business areas, and the core release that adds them (KPI-DEC-0002,
Q10 form 2; KPI-DEC-0004, item 1).

core is the process map. Each core release is built by a builder of its own, build_core_<major>_<minor>.py, from the
released core it starts from and two frozen copies of the map (HOW-TO-UPDATE.md, "Change a process"). This file
makes that release by command: it writes the new nodes into the map and the identity map, freezes the map before and
after, writes the builder from release/build_core_template.py with the template's block of constants filled in,
writes the changelog and runs the builder. What each line says:

    a new process or step   a node of business_architecture/business_process/downstream_process_map.json, under its
                            parent, and a row of ontology/build/output/step2-identity-map.json
                            create node proc:<slug> '<its name>'
                            add definition '<the first sentence of its description>' to proc:<slug>
                            create edge proc:<slug> skos:broader proc:<its parent>
                            create edge proc:<slug> core:businessDomain area:<its business area>
                            facts.csv: proc:<slug>,skos:notation,<its number>
                                       proc:<slug>,core:taxonomyLevel,<its level>
                                       proc:<slug>,skos:scopeNote,<the rest of its description>      when there is a rest
    a new business area     a member of the core:BusinessDomain list, which only core holds
                            create node area:<slug> '<its name>'
                            add definition '<what it covers>' to area:<slug>

A new node's number is its parent's number, a dot, and the first number after the parent's children that no process
of the map or the identity map has; its slug is the number with spaces and dots as hyphens (Step 2), and its level
is one below its parent's. A new node needs a parent the map numbers, a level of 6 or less, one sentence or more of
description, and a business area that core or the same request holds.

check_changes checks the lines against the release. release writes them into a scratch copy and releases core: the
apply command then gives every module that depends on core its patch. compare is the round trip of core.ttl.
"""
import ast
import hashlib
import json
import re
from pathlib import Path

from .. import cut
from . import ChangeRefused, kgcl, process_map

BASE = "https://w3id.org/mpc/ontology/"
# The namespaces of build_core_next.py and build_core_2_2.py; a test checks that they are the builders'.
PREFIXES = {"proc": BASE + "process/", "area": BASE + "modules/core/business-domain/", "core": BASE + "modules/core/",
            "skos": "http://www.w3.org/2004/02/skos/core#"}
RELEASE = cut.ONTOLOGY / "release"
TEMPLATE = RELEASE / "build_core_template.py"
FROZEN = RELEASE / "frozen"
CHANGELOGS = cut.ONTOLOGY / "releases" / "core"
MAP_PATH = "business_architecture/business_process/downstream_process_map.json"   # as the core builders name it
NOTATION, LEVEL, SCOPE = "skos:notation", "core:taxonomyLevel", "skos:scopeNote"
EDGES = ("skos:broader", "core:businessDomain")
ID = re.compile(r"[A-Z]+ \d+(?:\.\d+)*")
MAX_LEVEL = 6
FILL_IN = re.compile(r"# --- FILL IN -+\n.*?\n# -{20,}\n", re.S)
# The source Turtle of each module that reads core; each must still equal a fresh build after the release.
READERS = ((cut.ONTOLOGY / "organization", "build_roles.py"), (cut.ONTOLOGY / "organization", "build_assignments.py"),
           (cut.ONTOLOGY / "kpi", "build_measures.py"), (cut.ONTOLOGY / "data-product", "build_data_products.py"),
           (cut.ONTOLOGY / "data-product", "build_pricing.py"), (cut.ONTOLOGY / "value-stream", "build_value_streams.py"),
           (cut.ONTOLOGY / "system", "build_systems.py"), (cut.ONTOLOGY / "lane", "build_lanes.py"),
           (cut.ONTOLOGY / "market-data", "build_market_data.py"), (cut.ONTOLOGY / "authority", "build_source_tiers.py"),
           (cut.ONTOLOGY / "apqc", "build_apqc_elements.py"), (cut.ONTOLOGY / "population", "build_population.py"),
           (cut.ONTOLOGY / "party", "build_party.py"))


def tail(text):
    return text.split(":", 1)[1]


def slug_of(number):
    """A process's slug from its number, as Step 2 makes it: CM 1.1.9 gives CM-1-1-9."""
    return number.replace(" ", "-").replace(".", "-")


def split_description(text):
    """The first sentence, and the rest: build_core_2_2.split_description's rule, which the core builders apply. A
    sentence ends at '. ' before a capital, outside brackets."""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "." and depth == 0 and text[i + 1:i + 2] == " " and text[i + 2:i + 3].isupper():
            return text[:i + 1], text[i + 2:].strip()
    return text, ""


def is_core(change):
    return change.subject.split(":", 1)[0] in ("proc", "area")


def node_changes(number, level, name, description, parent, area):
    """The lines and the facts of one new process or step."""
    s = f"proc:{slug_of(number)}"
    definition, scope = split_description(description)
    edge = lambda predicate, target: kgcl.Change("create edge", s, predicate=predicate, target=target)
    lines = [kgcl.Change("create node", s, text=name), kgcl.Change("add definition", s, text=definition),
             edge("skos:broader", f"proc:{parent}"), edge("core:businessDomain", f"area:{area}")]
    facts = [(s, NOTATION, number), (s, LEVEL, str(level))] + ([(s, SCOPE, scope)] if scope else [])
    return lines, facts


def area_changes(slug, name, definition):
    a = f"area:{slug}"
    return [kgcl.Change("create node", a, text=name), kgcl.Change("add definition", a, text=definition)]


def split(changes, facts):
    """A core change as its parts: ({area slug: (name, definition)}, [node]), each node a dict of its slug, number,
    level, name, description, parent and area. Refuses a line or a fact that no part takes."""
    areas, nodes = {}, {}
    for c in changes:
        line = kgcl.write_line(c)
        prefix = c.subject.split(":", 1)[0]
        parts = (areas if prefix == "area" else nodes).setdefault(tail(c.subject), {})
        if c.kind == "create node" and "name" not in parts:
            parts["name"] = c.text
        elif c.kind == "add definition" and "definition" not in parts:
            parts["definition"] = c.text
        elif prefix == "proc" and c.kind == "create edge" and c.predicate in EDGES and c.target.split(":", 1)[0] == (
                "proc" if c.predicate == "skos:broader" else "area") and c.predicate not in parts:
            parts[c.predicate] = tail(c.target)
        else:
            raise ChangeRefused("a new process or step takes create node, add definition, one skos:broader to a process "
                                f"and one core:businessDomain to an area; a new business area takes create node and "
                                f"add definition: {line}")
    for subject, prop, value in facts:
        if not subject.startswith("proc:") or tail(subject) not in nodes or prop not in (NOTATION, LEVEL, SCOPE) \
                or prop in nodes[tail(subject)]:
            raise ChangeRefused(f"a new process's facts are one {NOTATION}, one {LEVEL} and at most one {SCOPE} of a "
                                f"process that a line makes: {subject},{prop},{value}")
        nodes[tail(subject)][prop] = value
    for slug, parts in areas.items():
        if set(parts) != {"name", "definition"}:
            raise ChangeRefused(f"the new business area area:{slug} needs a create node line and an add definition line")
    out = []
    for slug, parts in nodes.items():
        missing = [p for p in ("name", "definition", *EDGES, NOTATION, LEVEL) if p not in parts]
        if missing:
            raise ChangeRefused(f"the new process proc:{slug} has no {', no '.join(missing)}")
        if not ID.fullmatch(parts[NOTATION]) or slug_of(parts[NOTATION]) != slug:
            raise ChangeRefused(f"proc:{slug}: its number {parts[NOTATION]!r} is not one whose slug is {slug}")
        if not parts[LEVEL].isdigit():
            raise ChangeRefused(f"proc:{slug}: its level {parts[LEVEL]!r} is not a number")
        description = parts["definition"] + (f" {parts[SCOPE]}" if SCOPE in parts else "")
        if split_description(description) != (parts["definition"], parts.get(SCOPE, "")):
            raise ChangeRefused(f"proc:{slug}: its definition must be one sentence and its scope note the rest")
        out.append({"slug": slug, "number": parts[NOTATION], "level": int(parts[LEVEL]), "name": parts["name"],
                    "description": description, "parent": parts["skos:broader"], "area": parts["core:businessDomain"]})
    return {s: (p["name"], p["definition"]) for s, p in areas.items()}, sorted(out, key=lambda n: n["slug"])


def core_graph(root):
    """The newest released core graph of a release."""
    from rdflib import Graph
    from kpi_store import ontology_view as ov
    version = ov.newest_versions(Path(root) / ov.RELEASES)["core"]
    return version, Graph().parse(str(Path(root) / ov.RELEASES / "core" / version / "core.ttl"), format="turtle")


def area_members(g):
    from rdflib import URIRef
    from rdflib.namespace import SKOS
    return {str(s)[len(PREFIXES["area"]):] for s in g.subjects(SKOS.inScheme, URIRef(PREFIXES["core"] + "BusinessDomain"))}


def read_identity(root):
    path = Path(root) / process_map.IDENTITY
    try:
        text = path.read_text(encoding="utf-8")
        rows = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ChangeRefused(f"{process_map.IDENTITY.as_posix()} cannot be read ({type(err).__name__}): it is not a KPI "
                            "Store release") from None
    if json.dumps(rows, indent=1, ensure_ascii=False) + "\n" != text:
        raise ChangeRefused(f"{process_map.IDENTITY.as_posix()} is not laid out as the release ships it; it needs a specialist")
    return rows


def numbers(data, rows):
    """Every process number the map or the identity map holds."""
    return set(process_map.processes(data)) | {r["skos_notation"] for r in rows if r.get("skos_notation")}


def next_number(parent, data, rows, taken=()):
    """The number of a new child of `parent` (a map node): its number, a dot, and the first number after its
    children's count that no process has."""
    used = numbers(data, rows) | set(taken)
    n = len(parent.get("children", [])) + 1
    while f"{parent['id']}.{n}" in used:
        n += 1
    return f"{parent['id']}.{n}"


def _edit(changes, facts, root):
    """The parts checked against the release, and the map's and the identity map's new texts in memory: (areas,
    nodes, map text, identity rows). Raises ChangeRefused when a part does not fit."""
    areas, nodes = split(changes, facts)
    version, g = core_graph(root)
    held = area_members(g)
    for slug in areas:
        if slug in held:
            raise ChangeRefused(f"area:{slug} is a business area of core {version} already")
    text, data = process_map.read_map(root)
    rows = read_identity(root)
    by_slug = {r["slug"]: r for r in rows}
    tree = process_map.processes(data)
    used = numbers(data, rows)
    for n in nodes:
        parent_row = by_slug.get(n["parent"])
        parent = tree.get(parent_row["skos_notation"]) if parent_row and parent_row.get("skos_notation") else None
        if parent is None:
            raise ChangeRefused(f"proc:{n['parent']} is not a process of the process map with a number, so proc:{n['slug']} "
                                "cannot go under it")
        if n["number"] in used or n["slug"] in by_slug:
            raise ChangeRefused(f"the number {n['number']} is a process of the process map already")
        if not n["number"].startswith(parent["id"] + ".") or "." in n["number"][len(parent["id"]) + 1:]:
            raise ChangeRefused(f"the number {n['number']} is not one of a child of {parent['id']}")
        if n["level"] != parent["level"] + 1 or n["level"] > MAX_LEVEL:
            raise ChangeRefused(f"{n['number']} is at level {n['level']}, and a child of {parent['id']} is at level "
                                f"{parent['level'] + 1}; the map has {MAX_LEVEL} levels")
        if n["area"] not in held | set(areas):
            raise ChangeRefused(f"area:{n['area']} is neither a business area of core {version} nor a new one of this "
                                "request")
        if any(c.get("name") == n["name"] for c in parent.get("children", [])):
            raise ChangeRefused(f'{parent["id"]} has a process named "{n["name"]}" already')
        used.add(n["number"])
        parent.setdefault("children", []).append({"id": n["number"], "level": n["level"], "name": n["name"],
                                                  "description": n["description"]})
        at = max((i for i, r in enumerate(rows) if r["slug"] == n["parent"] or r.get("parent_slug") == n["parent"]))
        rows.insert(at + 1, {"uri": PREFIXES["proc"] + n["slug"], "slug": n["slug"], "level": n["level"],
                             "name": n["name"], "skos_notation": n["number"], "parent_slug": n["parent"],
                             "minted": False, "proposed_repo_id": n["number"], "deprecated": False})
        by_slug[n["slug"]] = rows[at + 1]
    if not nodes and not areas:
        raise ChangeRefused("the change adds no process, step or business area")
    return areas, nodes, process_map._dump(text, data), rows


def check_changes(changes, facts, root):
    """Raises ChangeRefused when the core part of a process map request does not fit the release. Writes nothing."""
    _edit(changes, facts, Path(root).resolve())


def newest_builder(root):
    """The newest core builder's module name and the map label it was built from (its SOURCE_COMMIT)."""
    release = Path(root) / RELEASE
    found = [(int(m.group(1)), int(m.group(2)), f.name) for f in release.iterdir()
             for m in [re.fullmatch(r"build_core_(\d+)_(\d+)\.py", f.name)] if m]
    if not found:
        raise ChangeRefused(f"{RELEASE.as_posix()} holds no core builder: it is not a KPI Store release")
    name = max(found)[2]
    tree = ast.parse((release / name).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SOURCE_COMMIT" for t in node.targets):
            return name[:-3], ast.literal_eval(node.value)
    raise ChangeRefused(f"{name} names no SOURCE_COMMIT; it needs a specialist")


def next_minor(version):
    from kpi_store import ontology_view as ov
    key = ov.version_key(version)
    return f"{key[0]}.{key[1] + 1}.0"


def builder_name(version):
    major, minor, _ = version.split(".")
    return f"build_core_{major}_{minor}.py"


def builder_text(template, constants, docstring):
    """The core builder: the template with its docstring and its block of constants replaced. Refuses a template
    whose block is not where the release ships it, and checks that the result compiles and holds the constants."""
    if not FILL_IN.search(template) or not template.startswith('"""'):
        raise ChangeRefused(f"{TEMPLATE.as_posix()} is not laid out as the release ships it; it needs a specialist")
    block = "# --- FILL IN " + "-" * 105 + "\n" + "".join(f"{k} = {v!r}\n" for k, v in constants.items()) + "# " + "-" * 117 + "\n"
    body = template[template.index('"""', 3) + 3:]
    text = f'"""{docstring}"""' + FILL_IN.sub(lambda _: block, body, count=1)
    try:
        tree = ast.parse(text)
        compile(tree, builder_name(constants["VERSION"]), "exec")
    except SyntaxError as err:
        raise ChangeRefused(f"the core builder does not compile ({err}); it needs a specialist") from None
    held = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name) and t.id in constants}
    if held != constants:
        raise ChangeRefused("the core builder does not hold the constants it was written with; it needs a specialist")
    return text


def changelog(version, base, change, areas, nodes, area_names, date):
    """The core release's changelog, in the form of CHANGELOG-2.4.0.md."""
    what = " and ".join(w for w in (f"{len(nodes)} process{'es' if len(nodes) != 1 else ''}" if nodes else "",
                                    f"{len(areas)} business area{'s' if len(areas) != 1 else ''}" if areas else "") if w)
    lines = ["# core changelog", "", f"## {version} ({date})", "",
             f"A minor release: it adds {what}, and changes or removes nothing. Built from the released {base} graph; "
             f"{base} is unchanged. It carries the process map request {change}, which the Global Process Owner and the "
             f"Architect signed (approvals/{change}.json). The apply command wrote this release and its builder, "
             f"{builder_name(version)}, from the request.", ""]
    for slug, (name, definition) in sorted(areas.items()):
        lines.append(f"- [minor] **New business area {name}** (`area:{slug}`): {definition}")
    for n in nodes:
        lines.append(f"- [minor] **New process {n['number']} {n['name']}**, under `proc:{n['parent']}`, in the business "
                     f"area {area_names.get(n['area'], n['area'])}: {split_description(n['description'])[0]}")
    lines += [f"- The shapes and the canonical-fact mapping are {base}'s, unchanged.", ""]
    return "\n".join(lines)


def release(changes, facts, root, change, words, date):
    """Writes the new nodes and areas into a scratch copy of the release and releases core at the next minor: the
    map, the identity map, the frozen maps, the builder, the changelog and the package. Returns (old version, new
    version). Raises ChangeRefused, and writes nothing, when a part does not fit."""
    root = Path(root).resolve()
    areas, nodes, text, rows = _edit(changes, facts, root)
    base, g = core_graph(root)
    from rdflib import URIRef
    from rdflib.namespace import SKOS
    area_names = {s: str(g.value(URIRef(PREFIXES["area"] + s), SKOS.prefLabel)) for s in area_members(g)}
    area_names.update({s: name for s, (name, _) in areas.items()})
    version = next_minor(base)
    _, earlier = newest_builder(root)
    if not (root / FROZEN / f"{earlier[:12]}-downstream_process_map.json").is_file():
        raise ChangeRefused(f"the frozen map {earlier[:12]} that core {base} was built from is missing; it needs a specialist")
    source = hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]
    if (root / RELEASE / builder_name(version)).exists():
        raise ChangeRefused(f"{builder_name(version)} exists already; core {version} needs a specialist")
    constants = {"VERSION": version, "ISSUED": date, "BASE_VERSION": base, "EARLIER_COMMIT": earlier,
                 "SOURCE_COMMIT": source, "APPROVAL": (f"approvals/{change}.json", words),
                 "DECISIONS": [f"approvals/{change}.json"],
                 "APPROVED_NODE": {n["number"]: ({"id": n["number"], "level": n["level"], "name": n["name"]}, n["parent"],
                                                 n["area"]) for n in nodes},
                 "APPROVED_AREAS": dict(areas)}
    docstring = (f"Build core {version} from the released core {base}: the process map request {change}.\n\n"
                 f"    python3 {builder_name(version)} --write    # write releases/core/{version}/\n"
                 f"    python3 {builder_name(version)} --verify   # fail unless the written package equals a fresh build\n\n"
                 "The apply command wrote this file from build_core_template.py, with the block marked FILL IN filled\n"
                 f"from the request's signed change file, approvals/{change}.kgcl. core {base} stays as it was released.\n")
    builder = builder_text((root / TEMPLATE).read_text(encoding="utf-8"), constants, docstring)
    writes = {process_map.MAP: text, process_map.IDENTITY: json.dumps(rows, indent=1, ensure_ascii=False) + "\n",
              FROZEN / f"{source[:12]}-downstream_process_map.json": text, RELEASE / builder_name(version): builder,
              CHANGELOGS / f"CHANGELOG-{version}.md": changelog(version, base, change, areas, nodes, area_names, date)}
    for path, content in writes.items():
        with (root / path).open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    try:
        cut._run("write the core package", [builder_name(version), "--write"], root / RELEASE)
    except cut.CutFailed as err:
        raise ChangeRefused(f"the core builder refused the new nodes: {err}") from None
    return base, version


def curie(value):
    fits = [(len(ns), p) for p, ns in PREFIXES.items() if str(value).startswith(ns) and len(str(value)) > len(ns)]
    if not fits:
        return None
    n, prefix = max(fits)
    return f"{prefix}:{str(value)[n:]}"


def compare(before, after):
    """The KGCL lines and facts that take core.ttl `before` to `after` (files or Graphs), leaving out the ontology's
    own header. Raises ChangeRefused for a difference that no line and no fact of a process map request states."""
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import DCTERMS, RDF, SKOS, XSD
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    header = URIRef(PREFIXES["core"][:-1])
    removed = {t for t in set(before) - set(after) if t[0] != header}
    added = {t for t in set(after) - set(before) if t[0] != header}
    unsupported = [f"- {s} {p} {o}" for s, p, o in removed]
    held = set(before.subjects())
    areas = URIRef(PREFIXES["core"] + "BusinessDomain")
    scheme = URIRef(PREFIXES["core"][:-1])
    lines, rows, made = [], [], {}
    for s, p, o in added:
        subject = curie(s) or ""
        kind = subject.split(":", 1)[0] if s not in held and subject.split(":", 1)[0] in ("proc", "area") else ""
        if s == areas and p == SKOS.hasTopConcept and (curie(o) or "").startswith("area:") and o not in held:
            made.setdefault(o, set()).add("top")
        elif kind and (p, o) in ((RDF.type, SKOS.Concept), (SKOS.inScheme, scheme if kind == "proc" else areas)) \
                or kind == "area" and (p, o) == (SKOS.topConceptOf, areas) \
                or kind and p == DCTERMS.provenance and isinstance(o, Literal) and o.language == "en" \
                and str(p) not in made.get(s, ()):
            made.setdefault(s, set()).add(str(p) + (str(o) if p != DCTERMS.provenance else ""))
        elif kind and p in (SKOS.prefLabel, SKOS.definition) and isinstance(o, Literal) and o.language == "en" \
                and str(p) not in made.get(s, ()):
            made.setdefault(s, set()).add(str(p))
            lines.append(kgcl.write_line(kgcl.Change("create node" if p == SKOS.prefLabel else "add definition", subject,
                                                     text=str(o))))
        elif kind == "proc" and curie(p) in EDGES and isinstance(o, URIRef) and curie(o):
            lines.append(kgcl.write_line(kgcl.Change("create edge", subject, predicate=curie(p), target=curie(o))))
        elif kind == "proc" and p == SKOS.notation and isinstance(o, Literal) and o.datatype is None and not o.language:
            rows.append((subject, NOTATION, str(o)))
        elif kind == "proc" and p == URIRef(PREFIXES["core"] + "taxonomyLevel") and isinstance(o, Literal) \
                and o.datatype == XSD.integer:
            rows.append((subject, LEVEL, str(o)))
        elif kind == "proc" and p == SKOS.scopeNote and isinstance(o, Literal) and o.language == "en":
            rows.append((subject, SCOPE, str(o)))
        else:
            unsupported.append(f"+ {s} {p} {o!r}")
    for s in {s for s, _, _ in added if s not in held and s != areas} | set(made):
        kind = (curie(s) or ":").split(":", 1)[0]
        need = {str(RDF.type) + str(SKOS.Concept), str(SKOS.inScheme) + str(scheme if kind == "proc" else areas),
                str(DCTERMS.provenance), str(SKOS.prefLabel), str(SKOS.definition)} \
            | ({str(SKOS.topConceptOf) + str(areas)} if kind == "area" else set())
        got = made.get(s, set())
        if kind == "area" and "top" not in got:
            unsupported.append(f"{s} is not a top concept of core:BusinessDomain")
        if not need <= got:
            unsupported.append(f"{s} lacks its type, its scheme, its name, its definition or its provenance")
    if unsupported:
        raise ChangeRefused(f"core differs in {len(unsupported)} ways that no line and no fact of a process map request "
                            "states: " + "; ".join(sorted(unsupported)[:10]))
    return sorted(lines), sorted(rows)
