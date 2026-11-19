"""Applies KGCL changes to the kpi module's source tables, rebuilds the module, and turns the difference between two
built kpi graphs back into KGCL lines (KPI-DEC-0002, Q7 items 3 and 5).

apply_changes works on the release folder it is given, which must be a scratch copy: the later apply command
copies the release first, as kpi_store/cut.py does, and writes the real sources only after every check has passed.
It reads and writes the tables with cut.Tables and runs the builder with cut._run.

What each change writes, in the kpi tables (business_architecture/ontology/kpi):

    rename <measure> from '<old>' to '<new>'             measure-classification.csv, the name column
    change definition of <measure> to '<text>'           measure-details.csv, the definition column
    create exact synonym '<text>' for <measure>          measure-details.csv, the aliases column (; between)
    remove synonym '<text>' for <measure>                the same column
    create edge <measure> kpi:informsProcess proc:<p>    measure-details.csv, the informs_process column, as the
    delete edge <measure> kpi:informsProcess proc:<p>    process's notation (CM 1.1.4.4), as the table writes it

A <measure> is measure:<measure_id>. No table is written when any change is refused.
"""
import importlib.util
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SKOS

from .. import cut
from . import ChangeRefused
from .kgcl import Change, write_line

KPI_FOLDER = Path("business_architecture") / "ontology" / "kpi"
BUILDER = "build_measures.py"
MEASURES = KPI_FOLDER / "measures.ttl"
CLASSIFICATION, DETAILS = "measure-classification", "measure-details"
# The namespaces of build_measures.py; a test checks that they are the builder's. measure: comes before kpi:,
# because every measure IRI also starts with the kpi namespace.
PREFIXES = {"measure": "https://w3id.org/mpc/ontology/modules/kpi/measure/",
            "kpi": "https://w3id.org/mpc/ontology/modules/kpi/",
            "proc": "https://w3id.org/mpc/ontology/process/"}
INFORMS = "kpi:informsProcess"
PREDICATES = {SKOS.prefLabel: "name", SKOS.definition: "definition", SKOS.altLabel: "synonym",
              URIRef(PREFIXES["kpi"] + "informsProcess"): "edge"}


LANGUAGE = "en"
ORDER = {"remove synonym": 0, "rename": 1, "create synonym": 2}


def _split(text):
    """A list cell's values, as build_measures.split reads them."""
    return [t.strip() for t in text.split(";") if t.strip()]


def _curie(iri):
    """prefix:name for an IRI of one of PREFIXES' namespaces with a name after it, else None."""
    if not isinstance(iri, URIRef):
        return None
    for prefix, ns in PREFIXES.items():
        if str(iri).startswith(ns) and len(str(iri)) > len(ns):
            return f"{prefix}:{str(iri)[len(ns):]}"
    return None


def _process_index(root):
    """{notation or slug: process IRI} from the newest core package of the release, as build_measures.py reads it."""
    try:
        spec = importlib.util.spec_from_file_location("kpi_change_newest", root / "business_architecture" /
                                                      "ontology" / "release" / "newest.py")
        newest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(newest)
        g = Graph().parse(newest.core_file(ontology=str(root / "business_architecture" / "ontology")))
    except (OSError, ValueError) as err:
        raise ChangeRefused(f"{root} has no readable newest core package, which an edge needs to find its process "
                            f"({type(err).__name__}: {err})") from None
    proc = PREFIXES["proc"]
    index = {str(n): str(s) for s, n in g.subject_objects(SKOS.notation) if str(s).startswith(proc)}
    index.update({str(s)[len(proc):]: str(s) for s in g.subjects(RDF.type, SKOS.Concept) if str(s).startswith(proc)})
    notation = {iri: n for n, iri in index.items() if not iri.endswith("/" + n)}
    return index, notation


def check_changes(changes, release_root):
    """Raises ChangeRefused when any change does not fit the kpi tables of the release, read in order as
    apply_changes reads them. Writes nothing and runs no builder: the propose command calls it on the real release."""
    _edit(changes, Path(release_root).resolve())


def apply_changes(changes, release_root):
    """Writes the changes into the kpi tables of a scratch copy of the release, in order, and rebuilds measures.ttl
    with the module's builder. Returns the path of the rebuilt measures.ttl. Raises ChangeRefused, and writes
    nothing, when any change does not fit the tables. When the builder refuses the changed tables, they stay
    written in the scratch copy, and ChangeRefused carries the builder's message."""
    root = Path(release_root).resolve()
    tables = _edit(changes, root)
    tables.write(root)
    try:
        cut._run("rebuild the kpi module", [BUILDER, "--write"], root / KPI_FOLDER)
    except cut.CutFailed as err:
        raise ChangeRefused(f"the kpi builder refused the changed tables: {err}") from None
    return root / MEASURES


def _edit(changes, root):
    """The kpi tables of the release with the changes made in memory, in order. Raises ChangeRefused when any
    change does not fit them."""
    changes = list(changes)
    if not changes:
        raise ChangeRefused("there are no changes to apply")
    try:
        tables = cut.Tables(root, KPI_FOLDER, (CLASSIFICATION, DETAILS))
    except cut.CutRefused:
        raise ChangeRefused(f"{root} holds no kpi tables: it is not a KPI Store release") from None
    names = {r["measure_id"]: r for r in tables.rows[CLASSIFICATION]}
    details = {r["measure_id"]: r for r in tables.rows[DETAILS]}
    processes = None
    for change in changes:
        line = write_line(change)   # also refuses a change that has no KGCL form
        if not change.subject.startswith("measure:"):
            raise ChangeRefused(f"this release changes only measures (measure:<id>): {line}")
        m = change.subject[len("measure:"):]
        if m not in names or m not in details:
            raise ChangeRefused(f"{change.subject} is not a measure of the kpi module: {line}")
        row, detail = names[m], details[m]
        if change.kind == "rename":
            if change.old != row["name"]:
                raise ChangeRefused(f"the measure's name is {row['name']!r}, not {change.old!r}: {line}")
            if change.text == row["name"]:
                raise ChangeRefused(f"the new name is the current name: {line}")
            if change.text in _split(detail["aliases"]):
                raise ChangeRefused(f"the new name is one of the measure's synonyms; remove the synonym first: {line}")
            row["name"] = change.text
        elif change.kind == "change definition":
            if change.text == detail["definition"]:
                raise ChangeRefused(f"the new definition is the current definition: {line}")
            detail["definition"] = change.text
        elif change.kind in ("create synonym", "remove synonym"):
            aliases = _split(detail["aliases"])
            if change.kind == "create synonym":
                if ";" in change.text:
                    raise ChangeRefused(f"a synonym may not hold a semicolon, which separates them in the table: {line}")
                if change.text in aliases:
                    raise ChangeRefused(f"the measure has this synonym already: {line}")
                if change.text == row["name"]:
                    raise ChangeRefused(f"a synonym may not repeat the measure's name: {line}")
                aliases.append(change.text)
            else:
                if change.text not in aliases:
                    raise ChangeRefused(f"the measure has no such synonym: {line}")
                aliases.remove(change.text)
            detail["aliases"] = ";".join(aliases)
        else:   # create edge, delete edge
            if change.predicate != INFORMS:
                raise ChangeRefused(f"the only edge this release applies is {INFORMS}: {line}")
            if not change.target.startswith("proc:"):
                raise ChangeRefused(f"{INFORMS} points at a process (proc:<id>): {line}")
            if processes is None:
                processes = _process_index(root)
            index, notation = processes
            iri = PREFIXES["proc"] + change.target[len("proc:"):]
            if iri not in index.values():
                raise ChangeRefused(f"{change.target} is not a process of the newest core: {line}")
            current = _split(detail["informs_process"])
            linked = [p for p in current if index.get(p) == iri]
            if change.kind == "create edge":
                if linked:
                    raise ChangeRefused(f"the measure informs this process already: {line}")
                current.append(notation.get(iri, change.target[len("proc:"):]))
            else:
                if not linked:
                    raise ChangeRefused(f"the measure does not inform this process: {line}")
                current = [p for p in current if p not in linked]
            detail["informs_process"] = ";".join(current)
    return tables


def compare(before, after):
    """The KGCL lines that take the built kpi graph `before` to `after` (files or rdflib Graphs), in an order
    apply_changes can replay: removed synonyms, renames, new synonyms, then the rest, each by its text. Raises
    ChangeRefused when the graphs differ in a way no supported line states, naming those differences."""
    before, after = (g if isinstance(g, Graph) else Graph().parse(str(g), format="turtle") for g in (before, after))
    removed, added = set(before) - set(after), set(after) - set(before)
    changes, unsupported, pairs = [], [], {}
    for sign, triples in (("-", removed), ("+", added)):
        for s, p, o in triples:
            subject, kind = _curie(s), PREDICATES.get(p)
            if kind is None or subject is None or not subject.startswith("measure:"):
                unsupported.append(f"{sign} {s} {p} {o}")
            elif kind == "edge":
                target = _curie(o)
                if target is None or not target.startswith("proc:"):
                    unsupported.append(f"{sign} {s} {p} {o}")
                else:
                    changes.append(Change("create edge" if sign == "+" else "delete edge", subject,
                                          predicate=INFORMS, target=target))
            elif not isinstance(o, Literal) or o.language != LANGUAGE or o.datatype is not None:
                unsupported.append(f"{sign} {s} {p} {o!r}")   # the builder writes every name and text @en
            elif kind == "synonym":
                changes.append(Change("create synonym" if sign == "+" else "remove synonym", subject, text=str(o)))
            else:
                pairs.setdefault((subject, kind), {"-": [], "+": []})[sign].append(str(o))
    for (subject, kind), values in pairs.items():
        if len(values["-"]) != 1 or len(values["+"]) != 1:
            unsupported.append(f"{subject}: its {kind} was added or removed, not changed ({values})")
        elif kind == "name":
            changes.append(Change("rename", subject, old=values["-"][0], text=values["+"][0]))
        else:
            changes.append(Change("change definition", subject, text=values["+"][0]))
    if unsupported:
        shown = sorted(unsupported)[:10]
        raise ChangeRefused(f"the graphs differ in {len(unsupported)} ways that no supported KGCL line states: "
                            + "; ".join(shown))
    # In an order apply_changes can replay: a synonym goes before a rename that takes it as the name, and a rename
    # before a synonym that keeps the old name.
    return [line for _, line in sorted((ORDER.get(c.kind, len(ORDER)), write_line(c)) for c in changes)]
