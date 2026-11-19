"""A new KPI's changes to the modules beside kpi: its value stream steps and the view that gives its values
(KPI-DEC-0004, item 1; KPI-DEC-0002, Q10 form 1). The kpi module's part, with the populations and the sentences for
the scope notes of the measures it is mistaken for, is new_measures.py's.

What each line writes:

    value-stream   a measure link on a step, one for each step that 6.3 names: an entry {measureId, relationship,
                   basis} in the step's "measures" list of business_process/value_stream_*.json, which
                   build_value_streams.py reads
                   create edge vsprocess:<step> vs:measureLink mlink:<step>--<measure>
                   create edge mlink:<step>--<measure> vs:measure measure:<measure>
                   create edge mlink:<step>--<measure> vs:relationship rel:<informs, benchmarks or measures-performance>
                   facts.csv: mlink:<step>--<measure>,dcterms:bibliographicCitation,<what says so (6.5)>
    data-product   the view of 7.1 serves the measure: the serves_measures column of data-product/pricing/tables.csv
                   create edge table:<view> dp:servesMeasure measure:<measure>
                   the assistant of 7.8 answers from that view: the uses column of pricing/agents.csv
                   create edge agent:<assistant> prov:used table:<view>

The step, the view and the assistant are ones the module holds: a new step goes to the process map request, and a
new view or assistant needs a specialist, as the reference-item form says of a table built from other tables.

check_changes and apply_changes take a new KPI's whole change, every module's lines and facts, and hand the kpi
module's part to new_measures.py. apply_changes works on a scratch copy of the release and rebuilds each changed
module in the order its builders read each other: kpi and its populations, data-product, value-stream. compare is the
round trip of one built file.
"""
import json
from pathlib import Path

from .. import cut
from . import ChangeRefused, kgcl, new_measures

BASE = "https://w3id.org/mpc/ontology/"
# The namespaces of build_value_streams.py and build_pricing.py; a test checks that they are the builders'.
PREFIXES = {"vsprocess": BASE + "modules/value-stream/process/", "mlink": BASE + "modules/value-stream/measure-link/",
            "rel": BASE + "modules/value-stream/measure-relationship/", "vs": BASE + "modules/value-stream/",
            "table": BASE + "modules/data-product/table/", "agent": BASE + "modules/data-product/agent/",
            "product": BASE + "modules/data-product/product/", "dp": BASE + "modules/data-product/",
            "prov": "http://www.w3.org/ns/prov#", "dcterms": "http://purl.org/dc/terms/"}
RELATIONSHIPS = ("informs", "benchmarks", "measures-performance")
WHOLE = "product:master-pricing"   # every pricing data product is part of Master Pricing (build_pricing.py)
STREAM_FILES = tuple(Path("business_architecture") / "business_process" / f
                     for f in ("value_stream_commercial_lifecycle.json", "value_stream_order_to_cash.json"))
VS_FOLDER, DP_FOLDER = cut.ONTOLOGY / "value-stream", cut.ONTOLOGY / "data-product"
# The built files a new KPI changes, from the ontology folder, by the module that releases them. population.ttl ships
# in the kpi package.
BUILT = {"kpi": Path("kpi") / "measures.ttl", "population": Path("population") / "population.ttl",
         "data-product": Path("data-product") / "pricing.ttl", "value-stream": Path("value-stream") / "value-streams.ttl"}
MODULE_OF = {"kpi": "kpi", "population": "kpi", "data-product": "data-product", "value-stream": "value-stream"}
TESTS = {"kpi": [(new_measures.FOLDER, "test_measures"), (new_measures.POP_FOLDER, "test_population")],
         "data-product": [(DP_FOLDER, "test_data_products")], "value-stream": [(VS_FOLDER, "test_value_streams")]}
BUILDERS = {"kpi": [(new_measures.FOLDER, "build_measures.py"), (new_measures.POP_FOLDER, "build_population.py")],
            "data-product": [(DP_FOLDER, "build_pricing.py")], "value-stream": [(VS_FOLDER, "build_value_streams.py")]}


def iri(text):
    prefix, name = text.split(":", 1)
    return (PREFIXES.get(prefix) or new_measures.PREFIXES[prefix]) + name


def curie(value):
    """prefix:name for an IRI of PREFIXES or of new_measures.PREFIXES, the longest namespace that fits, else None."""
    every = {**new_measures.PREFIXES, **PREFIXES}
    fits = [(len(ns), p) for p, ns in every.items() if str(value).startswith(ns) and len(str(value)) > len(ns)]
    if not fits:
        return None
    n, prefix = max(fits)
    return f"{prefix}:{str(value)[n:]}"


def tail(text):
    return text.split(":", 1)[1]


def split(changes, facts):
    """A new KPI's change as its parts: (the kpi module's lines and facts, the value-stream links, the data-product
    links). Refuses a line that no part takes."""
    kpi, links, served, used = [], {}, [], []
    for change in changes:
        line = kgcl.write_line(change)
        prefix = change.subject.split(":", 1)[0]
        if prefix == "measure":
            kpi.append(change)
        elif change.kind == "create edge" and prefix == "vsprocess" and change.predicate == "vs:measureLink":
            links.setdefault(change.target, {}).setdefault("step", []).append(tail(change.subject))
        elif change.kind == "create edge" and prefix == "mlink" and change.predicate in ("vs:measure", "vs:relationship"):
            links.setdefault(change.subject, {}).setdefault(change.predicate, []).append(change.target)
        elif change.kind == "create edge" and prefix == "table" and change.predicate == "dp:servesMeasure":
            served.append((tail(change.subject), change.target))
        elif change.kind == "create edge" and prefix == "agent" and change.predicate == "prov:used":
            if not change.target.startswith("table:"):
                raise ChangeRefused(f"prov:used of an assistant points at table:<id>: {line}")
            used.append((tail(change.subject), tail(change.target)))
        else:
            raise ChangeRefused("a new KPI changes another module only by these links: vs:measureLink, vs:measure and "
                                f"vs:relationship of a value stream step, dp:servesMeasure of a view and prov:used of an "
                                f"assistant: {line}")
    kpi_facts, bases = [], {}
    for subject, prop, value in facts:
        if subject.startswith("mlink:") and prop == "dcterms:bibliographicCitation":
            if subject in bases:
                raise ChangeRefused(f"the measure link has this fact already: {subject},{prop},{value}")
            bases[subject] = value
        else:
            kpi_facts.append((subject, prop, value))
    made = {c.subject for c in kpi if c.kind == "create node"}
    steps = []
    for link, parts in links.items():
        for key in ("step", "vs:measure", "vs:relationship"):
            if len(parts.get(key, [])) != 1:
                what = "vs:measureLink to it" if key == "step" else f"{key} link"
                raise ChangeRefused(f"{link} needs exactly one {what}, and has {len(parts.get(key, []))}")
        [step], [measure], [relationship] = parts["step"], parts["vs:measure"], parts["vs:relationship"]
        if tail(link) != f"{step}--{tail(measure)}":
            raise ChangeRefused(f"a measure link's id is <the step>--<the measure>, and {link} is not "
                                f"mlink:{step}--{tail(measure)}")
        if measure not in made:
            raise ChangeRefused(f"{measure} is not a new measure of this change: {link}")
        if not relationship.startswith("rel:") or tail(relationship) not in RELATIONSHIPS:
            raise ChangeRefused(f"{relationship} is not a relationship of a measure link ({', '.join(RELATIONSHIPS)})")
        if link not in bases:
            raise ChangeRefused(f"{link} needs a dcterms:bibliographicCitation fact: the document that says the step "
                                "uses the measure (6.5)")
        problem = new_measures._fact_problem("kpi:basis", bases[link])
        if problem:
            raise ChangeRefused(f"{problem}: {link},dcterms:bibliographicCitation,{bases[link]}")
        steps.append({"link": link, "step": step, "measure": tail(measure), "relationship": tail(relationship),
                      "basis": bases[link]})
    stray = sorted(set(bases) - set(links))
    if stray:
        raise ChangeRefused(f"a fact of facts.csv is about a measure link that no line makes: {stray[0]}")
    for _, measure in served:
        if measure not in made:
            raise ChangeRefused(f"{measure} is not a new measure of this change")
    return kpi, kpi_facts, steps, served, used


def _streams(root):
    out = []
    for path in STREAM_FILES:
        try:
            text = (Path(root) / path).read_text(encoding="utf-8")
            out.append((path, text, json.loads(text)))
        except (OSError, ValueError) as err:
            raise ChangeRefused(f"{path.as_posix()} cannot be read ({type(err).__name__}): it is not a KPI Store release") from None
    return out


def _step(streams, step):
    for path, _, data in streams:
        for stage in data["stages"]:
            for process in stage["processes"]:
                if process["id"] == "p-" + step:
                    return path, process
    return None, None


def _pricing(root, names):
    try:
        return cut.Tables(root, cut.PRICING, names)
    except cut.CutRefused:
        raise ChangeRefused(f"{root} holds no data-product tables: it is not a KPI Store release") from None


def _edit(changes, facts, root):
    """Every part checked against the release, and each module's tables with the new rows in memory: (the kpi
    tables, {stream file: new text}, the pricing tables). Raises ChangeRefused when any part does not fit."""
    kpi, kpi_facts, steps, served, used = split(changes, facts)
    found, kpi_tables = new_measures._edit(kpi, kpi_facts, root)
    streams = _streams(root)
    texts = {path: text for path, text, _ in streams}
    for s in steps:
        path, process = _step(streams, s["step"])
        if process is None:
            raise ChangeRefused(f"vsprocess:{s['step']} is not a step of a value stream. A new step goes to the "
                                "process map request")
        if any(m["measureId"] == s["measure"] for m in process.get("measures", [])):
            raise ChangeRefused(f"the step vsprocess:{s['step']} is linked to measure:{s['measure']} already")
        entry = {"measureId": s["measure"], "relationship": s["relationship"], "basis": s["basis"]}
        try:
            texts[path] = _add_entry(texts[path], process, entry)
        except ValueError:
            raise ChangeRefused(_LAYOUT.format(path.as_posix())) from None
        process.setdefault("measures", []).append(entry)
    for path, _, data in streams:
        try:   # the text edit must give exactly the entries added, and no key twice
            same = json.loads(texts[path], object_pairs_hook=_once) == data
        except ValueError:
            same = False
        if not same:
            raise ChangeRefused(_LAYOUT.format(path.as_posix()))
    pricing = _pricing(root, ("tables", "agents"))
    tables = {t["slug"]: t for t in pricing.rows["tables"]}
    agents = {a["slug"]: a for a in pricing.rows["agents"]}
    for view, measure in served:
        t = tables.get(view)
        if t is None or t["layer"] != "metric-view":
            raise ChangeRefused(f"table:{view} is not a metric view of the data-product module. Only a metric view "
                                "serves a measure")
        held = [m for m in t["serves_measures"].split(";") if m]
        if tail(measure) in held:
            raise ChangeRefused(f"table:{view} serves {measure} already in this change")
        t["serves_measures"] = ";".join([*held, tail(measure)])
    for agent, view in used:
        a = agents.get(agent)
        if a is None:
            raise ChangeRefused(f"agent:{agent} is not an assistant of the data-product module. A new assistant "
                                "needs a specialist")
        if tables.get(view, {}).get("layer") != "metric-view" or view not in {v for v, _ in served}:
            raise ChangeRefused(f"agent:{agent} may use table:{view} only when the new measure's view is that metric view")
        uses = [v for v in a["uses"].split(";") if v]
        if view in uses:
            raise ChangeRefused(f"agent:{agent} uses table:{view} already")
        a["uses"] = ";".join([*uses, view])
    changed = {"kpi"} | ({"value-stream"} if steps else set()) | ({"data-product"} if served or used else set())
    originals = {path: text for path, text, _ in streams}
    return kpi_tables, {p: t for p, t in texts.items() if t != originals[p]}, pricing, changed


_LAYOUT = "{} is not laid out as the release ships it, so its entries cannot be added; it needs a specialist"


def _once(pairs):
    """A JSON object's pairs as a dict, refusing a key that is given twice (json.loads would keep the last)."""
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError(f"a key is given twice: {sorted(k for k in set(keys) if keys.count(k) > 1)}")
    return dict(pairs)


def _add_entry(text, process, entry):
    """The stream file's text with one entry added to the step's "measures" list, as the file lays one out: one line
    for each entry, at the list's indent plus two. A list empty on one line opens up; a step without the list gains
    it after its last field. Raises ValueError for a layout it does not know."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip() == f'"id": "{process["id"]}",'), None)
    if start is None:
        raise ValueError("the step's id is not on a line of its own")
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(" " * (indent - 2) + "}")), None)
    if end is None or indent < 2:
        raise ValueError("the step's object does not close at its indent")
    item = "{ " + ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in entry.items()) + " }"
    pad = " " * indent
    for i in range(start, end):
        if lines[i] in (f'{pad}"measures": []', f'{pad}"measures": [],'):
            lines[i:i + 1] = [f'{pad}"measures": [', f"{pad}  {item}", f"{pad}]" + ("," if lines[i].endswith(",") else "")]
            return "\n".join(lines)
        if lines[i] == f'{pad}"measures": [':
            closing = next((j for j in range(i + 1, end) if lines[j] in (f"{pad}]", f"{pad}],")), None)
            if closing is None:
                raise ValueError("the step's list of measures does not close at its indent")
            if closing > i + 1:
                lines[closing - 1] += ","
            lines.insert(closing, f"{pad}  {item}")
            return "\n".join(lines)
    lines[end - 1] += ","
    lines[end:end] = [f'{pad}"measures": [', f"{pad}  {item}", f"{pad}]"]
    return "\n".join(lines)


def check_changes(changes, facts, release_root):
    """Raises ChangeRefused when any part of a new KPI's change does not fit the release. Writes nothing."""
    _edit(changes, facts, Path(release_root).resolve())


def modules_of(changes):
    """The modules a new KPI's change releases, with the route each one's lines suggest: kpi always, value-stream
    and data-product when it links to them. Every such line adds content, so each is a minor."""
    prefixes = {c.subject.split(":", 1)[0] for c in changes}
    out = {"kpi": "minor"}
    if prefixes & {"table", "agent"}:
        out["data-product"] = "minor"
    if prefixes & {"vsprocess", "mlink"}:
        out["value-stream"] = "minor"
    return out


def apply_changes(changes, facts, release_root):
    """Writes every part into a scratch copy of the release and rebuilds each changed module, in the order its
    builders read each other. Raises ChangeRefused, and writes nothing, when any part does not fit."""
    root = Path(release_root).resolve()
    (tables, population), texts, pricing, changed = _edit(changes, facts, root)
    tables.write(root)
    population.write(root)
    pricing.write(root)
    for path, text in texts.items():
        with (root / path).open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    for module in ("kpi", "data-product", "value-stream"):
        if module not in changed:
            continue
        for folder, builder in BUILDERS[module]:
            try:
                cut._run(f"rebuild the {module} module", [builder, "--write"], root / folder)
            except cut.CutFailed as err:
                raise ChangeRefused(f"the {module} builder refused the changed tables: {err}") from None
    return root / new_measures.kpi_tables.MEASURES


def compare(name, before, after):
    """The KGCL lines and facts that take one built file of BUILT, `before`, to `after` (files or Graphs). Raises
    ChangeRefused for a difference that no line and no fact of a new KPI states."""
    if name == "kpi":
        return new_measures.compare(before, after)
    if name == "population":
        return new_measures.compare_population(before, after)
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import RDF, XSD
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    removed, added = set(before) - set(after), set(after) - set(before)
    unsupported = [f"- {s} {p} {o}" for s, p, o in removed]
    lines, rows, typed = [], [], set()
    edges = {"value-stream": {"vs:measureLink": ("vsprocess", "mlink"), "vs:measure": ("mlink", "measure"),
                              "vs:relationship": ("mlink", "rel")},
             "data-product": {"dp:servesMeasure": ("table", "measure"), "prov:used": ("agent", "table")}}[name]
    held = set(before.subjects())
    for s, p, o in added:
        subject, predicate, target = curie(s), curie(p), curie(o) if isinstance(o, URIRef) else None
        if name == "value-stream" and p == RDF.type and o == URIRef(PREFIXES["vs"] + "MeasureLink") \
                and (subject or "").startswith("mlink:") and s not in held:
            typed.add(s)
        elif predicate in edges and target and (subject or ":").split(":", 1)[0] == edges[predicate][0] \
                and target.split(":", 1)[0] == edges[predicate][1]:
            lines.append(kgcl.write_line(kgcl.Change("create edge", subject, predicate=predicate, target=target)))
        elif name == "value-stream" and predicate == "dcterms:bibliographicCitation" and (subject or "").startswith("mlink:") \
                and isinstance(o, Literal) and o.datatype == XSD.string and s not in held:
            rows.append((subject, predicate, str(o)))
        else:
            unsupported.append(f"+ {s} {p} {o!r}")
    if name == "value-stream":
        made = {URIRef(iri(line.split()[-1])) for line in lines if " vs:measureLink " in line}
        unsupported += [f"{s} lacks its type vs:MeasureLink" for s in sorted(made - typed)]
        unsupported += [f"{s} is a vs:MeasureLink that no step links to" for s in sorted(typed - made)]
    if unsupported:
        raise ChangeRefused(f"the graphs differ in {len(unsupported)} ways that no line and no fact of a new KPI states: "
                            + "; ".join(sorted(unsupported)[:10]))
    return sorted(lines), sorted(rows)
