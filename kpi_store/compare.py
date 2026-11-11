"""Compares the ontology with the workspace and writes the findings as report rows.

A finding blocks the load when an object, a column or a table edge that the ontology names is missing or renamed
in Databricks. Everything else is a row for a person to read and does not block: a column name that differs only
in case, an object the ontology does not have, a measure link proposed from a Genie space, an object with no
lineage, stale data, a migration pair, a question.

All name comparisons ignore case. The ontology's catalog names are translated by the settings' [names] first.
"""
import datetime as dt
import re
from dataclasses import dataclass, field

from . import discovery as disc
from . import metric_view as mv

BLOCKING = ("object-missing", "object-renamed", "column-missing", "column-renamed", "edge-missing")
STALE_AFTER_DAYS = 35
# Words too common in measure names and filter titles to tell one measure from another.
COMMON_WORDS = frozenset("a an and the of for by with no not kpi filter market pricing price additional value default".split())


@dataclass
class Comparison:
    rows: list = field(default_factory=list)      # report rows without their IDs, in report order
    passes: dict = field(default_factory=dict)    # {"object_names", "table_edges", "metric_view_sources"}

    @property
    def blocked(self):
        return any(r["blocks"] for r in self.rows)


def _row(kind, obj, ontology_value="", found_value="", evidence="", fix=None, recommended="", note=""):
    return {"kind": kind, "blocks": kind in BLOCKING, "object": obj, "ontology_value": ontology_value,
            "found_value": found_value, "evidence": evidence, "proposed_fix": fix or {"action": "none"},
            "recommended": recommended, "decision": "", "decided_by": "", "note": note}


def _squash(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def words(text):
    """The telling words of a title, in lower case and singular: "Crack spreads KPI filter" gives crack, spread."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        w = w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
        if w not in COMMON_WORDS and not w.isdigit():
            out.add(w)
    return out


def _renamed_object(name, ontology, found, settings, taken):
    """The one object in the same schema that the missing object most likely became, with the evidence, or None.
    Two tests, in order: table lineage gives it every source the ontology's edges name; a name that differs only in punctuation."""
    schema = name.lower().rsplit(".", 1)[0]
    candidates = [k for k in found.tables if k.rsplit(".", 1)[0] == schema and k not in taken]
    want = {settings.environment_name(up).lower() for up in ontology.upstream(_ontology_name(name, ontology, settings))}
    same_lineage = [k for k in candidates if want and want <= found.upstream(k)]
    if len(same_lineage) == 1:
        return same_lineage[0], "table lineage gives it every source the ontology's edges name"
    same_name = [k for k in candidates if _squash(k.rsplit(".", 1)[1]) == _squash(name.rsplit(".", 1)[1])]
    if len(same_name) == 1:
        return same_name[0], "the names differ only in punctuation"
    return None


def _ontology_name(environment_name, ontology, settings):
    for key, obj in ontology.objects.items():
        if settings.environment_name(obj.full_name).lower() == environment_name.lower():
            return key
    return environment_name.lower()


def _renamed_column(table, column, free, ontology_sources, found):
    """The one current column that the missing column most likely became, with the evidence, or None. Two tests, in
    order: column lineage gives both names the same sources; the names differ only in punctuation or by a suffix."""
    sources = found.column_sources(table, column.name) or ontology_sources
    same_sources = [c for c in free if sources and found.column_sources(table, c) == sources]
    if len(same_sources) == 1:
        how = "column lineage holds both names with the same sources" if found.column_sources(table, column.name) \
            else "column lineage gives it the sources the ontology names"
        return same_sources[0], how
    old = _squash(column.name)
    alike = [c for c in free if _squash(c) == old or _squash(c).startswith(old) or old.startswith(_squash(c))]
    if len(alike) == 1:
        return alike[0], "the names differ only in punctuation or by a suffix"
    return None


def _readers(table, column, found):
    """The metric views that read the table and name the column."""
    return sorted(v.name for v in found.metric_views.values() if table.lower() in v.tables and v.reads_column(column))


def compare(ontology, found, settings, now=None, stale_after_days=STALE_AFTER_DAYS):
    """A Comparison of an OntologyView with a Discovery. stale_after_days None leaves freshness out."""
    out = Comparison()
    settings.one_name_each(obj.full_name for obj in ontology.objects.values())
    here = {key: settings.environment_name(obj.full_name) for key, obj in ontology.objects.items()}
    names_here = {name.lower(): key for key, name in here.items()}

    # 1. Objects.
    present, taken = {}, set(n for n in names_here if found.exists(n))
    catalogs_found = {t.catalog.lower() for t in found.tables.values()}
    for key, obj in sorted(ontology.objects.items()):
        name = here[key]
        if found.exists(name):
            present[key] = name.lower()
            continue
        catalog = name.split(".")[0]
        if catalog.lower() not in catalogs_found:
            out.rows.append(_row("object-missing", name, obj.full_name, "", f"no object of catalog {catalog} was found",
                                 {"action": "set-catalog-name", "setting": "names", "ontology_catalog": obj.full_name.split(".")[0]},
                                 "environment setting"))
            continue
        guess = _renamed_object(name, ontology, found, settings, taken)
        if guess:
            taken.add(guess[0])
            new = found.spelled(guess[0])
            out.rows.append(_row("object-renamed", name, obj.full_name, new, guess[1],
                                 {"action": "rename-object", "module": "data-product", "from": obj.full_name,
                                  "to": _to_ontology_catalog(new, obj.full_name)}, "accept"))
        else:
            out.rows.append(_row("object-missing", name, obj.full_name, "", "information_schema.tables does not list it",
                                 {"action": "remove-object", "module": "data-product", "object": obj.full_name}))
    out.passes["object_names"] = len(present)

    # 2. Columns.
    by_table = {}
    for column in ontology.columns:
        by_table.setdefault(column.table.lower(), []).append(column)
    for key, columns in sorted(by_table.items()):
        if key not in present:
            continue   # the object's own row covers its columns
        table, current = present[key], found.columns.get(present[key], [])
        lower = {c.lower(): c for c in current}
        named = {c.name.lower() for c in columns}
        used = set()
        for column in sorted(columns, key=lambda c: c.name.lower()):
            spelled = lower.get(column.name.lower())
            name = found.spelled(table)
            if spelled == column.name:
                continue
            if spelled:
                out.rows.append(_row("column-case", name, column.name, spelled, "the two names differ only in case",
                                     {"action": "rename-column", "module": "data-product", "from": column.name, "to": spelled}, "accept"))
                continue
            free = [c for c in current if c.lower() not in named and c not in used]
            sources = {(settings.environment_name(t).lower(), c.lower()) for t, c in column.derived_from}
            guess = _renamed_column(table, column, free, sources, found)
            if guess:
                used.add(guess[0])
                readers = _readers(table, guess[0], found)
                evidence = guess[1] + (f"; the metric view {readers[0]} reads {guess[0]}" if readers else "")
                out.rows.append(_row("column-renamed", name, column.name, guess[0], evidence,
                                     {"action": "rename-column", "module": "data-product", "from": column.name, "to": guess[0]}, "accept"))
            else:
                out.rows.append(_row("column-missing", name, column.name, "", "information_schema.columns does not list it",
                                     {"action": "remove-column", "module": "data-product", "column": column.name}))

    # 3. Table edges and metric view sources.
    edges_found, unchecked = 0, {}
    for down, up in sorted(ontology.edges):
        if down not in present or up not in present:
            continue   # the missing object's own row covers its edges
        target, source = present[down], present[up]
        view = found.metric_views.get(target)
        if (source, target) in found.table_edges or (view and source in view.tables):
            edges_found += 1
        elif not found.upstream(target) and not view:
            unchecked.setdefault(target, []).append(source)
        else:
            out.rows.append(_row("edge-missing", found.spelled(target), found.spelled(source), "",
                                 "neither table lineage nor a metric view definition holds this edge",
                                 {"action": "remove-edge", "module": "data-product", "from": ontology.objects[down].full_name,
                                  "to": ontology.objects[up].full_name}))
    out.passes["table_edges"] = edges_found
    for target, sources in sorted(unchecked.items()):
        out.rows.append(_row("no-lineage", found.spelled(target), f"{len(sources)} source(s)", "",
                             "table lineage holds no edge into this object, so its edges could not be checked"))
    views_ok = 0
    for key, obj in sorted(ontology.objects.items()):
        if obj.layer != "metric-view" or key not in present:
            continue
        view = found.metric_views.get(present[key])
        if not view:
            out.rows.append(_row("question", found.spelled(present[key]), "metric view", found.tables[present[key]].table_type,
                                 "its definition could not be read as a metric view, so its sources were not checked"))
            continue
        want = {present[up] for up in ontology.upstream(key) if up in present}
        extra = sorted(set(view.tables) - want)
        if want <= set(view.tables) and not extra and len(want) == len(ontology.upstream(key)):
            views_ok += 1
        for table in extra:
            out.rows.append(_row("question", view.name, "", found.spelled(table) if found.exists(table) else table,
                                 "the metric view's definition reads this table, and the ontology does not name it as a source",
                                 {"action": "add-edge", "module": "data-product", "from": obj.full_name, "to": table}))
    out.passes["metric_view_sources"] = views_ok

    # 4. Objects the ontology does not have, in the schemas of its silver, gold and metric view objects. The replica
    # schemas are left out: a source system holds many tables that no data product reads.
    schemas = {present[k].rsplit(".", 1)[0] for k, o in ontology.objects.items() if k in present and o.layer != "replica"}
    renamed_to = {r["found_value"].lower() for r in out.rows if r["kind"] == "object-renamed"}
    for key, info in sorted(found.tables.items()):
        if key.rsplit(".", 1)[0] in schemas and key not in names_here and key not in renamed_to:
            out.rows.append(_row("object-extra", info.full_name, "", info.table_type, "the ontology does not name this object",
                                 {"action": "add-object", "module": "data-product", "object": info.full_name}, "reject"))

    # 5. Lineage into the ontology's objects that the ontology does not hold.
    for (source, target), _ in sorted(found.table_edges.items()):
        if target not in names_here or (names_here[target], names_here.get(source)) in ontology.edges:
            continue
        if (source, target) in found.migration_pairs:
            out.rows.append(_row("migration-pair", found.spelled(target), "", found.spelled(source),
                                 "table lineage feeds the object from a table of the same name, and the schema names follow the layer rule",
                                 {"action": "record-replaces", "module": "technical-graph", "table": found.spelled(target),
                                  "replaces": found.spelled(source)}, "accept"))
        else:
            out.rows.append(_row("question", found.spelled(target), "", found.spelled(source),
                                 "table lineage feeds the object from this table, and the ontology holds no such edge"))

    # 6. Measure links proposed from the Genie spaces.
    out.rows += _genie_rows(ontology, found, names_here)

    # 7. Freshness.
    if stale_after_days is not None:
        now = now or dt.datetime.now(dt.timezone.utc)
        limit = disc.instant(now) - dt.timedelta(days=stale_after_days)
        for key in sorted(present):
            if not ontology.upstream(key):
                continue   # a source table is written outside Databricks, so lineage says nothing about it
            last = found.last_written(present[key])
            if last and disc.instant(last) < limit:
                out.rows.append(_row("stale-data", found.spelled(present[key]), "", last,
                                     f"table lineage shows no write in the last {stale_after_days} days"))
    return out


def _to_ontology_catalog(found_name, ontology_name):
    """A found object's name with the ontology's catalog name, so a fix never writes an environment's name."""
    return ontology_name.split(".")[0] + "." + found_name.split(".", 1)[1]


def _filter_view(snippet, space, found):
    """The one table of the space that a filter applies to, in lower case, or None when that is not clear."""
    tables = [t.lower() for t in space.tables]
    columns = mv.columns_in_sql(snippet["sql"])
    qualifiers = {q for q, _ in columns if q}
    named = [t for t in tables if t.rsplit(".", 1)[1] in qualifiers]
    if len(named) == 1:
        return named[0]
    if len(tables) == 1:
        return tables[0]
    wanted = {c for _, c in columns}
    holding = [t for t in tables if wanted and wanted <= {c.lower() for c in found.columns.get(t, [])}]
    return holding[0] if len(holding) == 1 else None


def _genie_rows(ontology, found, names_here):
    rows = []
    measure_words = {m.notation: words(" ".join((m.label, m.notation.replace("-", " "), *m.alt_labels)))
                     for m in ontology.measures.values()}
    for space in found.genie_spaces:
        linked = set()
        for snippet in space.filters:
            title = words(snippet["title"])
            scores = {n: len(title & w) for n, w in measure_words.items() if title & w}
            best = [n for n, s in scores.items() if s == max(scores.values())] if scores else []
            if len(best) != 1:
                continue   # a filter that names no measure, or more than one, is not a measure link
            measure = ontology.measures[best[0]]
            view = _filter_view(snippet, space, found)
            if view is None or view not in found.tables:
                rows.append(_row("question", f"Genie space {space.title}", measure.notation, snippet["title"],
                                 "the filter names this measure, and the table it applies to is not clear"))
                continue
            linked.add(view)
            name = found.spelled(view)
            obj = ontology.objects.get(names_here.get(view, ""))
            serves = bool(obj and measure.notation in obj.measures)
            rows.append(_row("measure-link", name, measure.notation if serves else "", snippet["title"],
                             f"Genie space {space.title!r} holds the filter {snippet['title']!r} for {measure.label}",
                             {"action": "add-measure-link", "module": "data-product", "view": obj.full_name if obj else name,
                              "measure": measure.notation,
                              "filter_name": snippet["title"], "filter": snippet["sql"], "space": space.space_id},
                             "accept", "The Genie space's creator confirms the filter before it goes into the ontology."))
            others = sorted(o.full_name for o in ontology.objects.values() if measure.notation in o.measures)
            if not serves and others:
                rows.append(_row("second-source", name, f"{measure.notation} is served by {', '.join(others)}", snippet["title"],
                                 f"Genie space {space.title!r} also reads {measure.label} from this view",
                                 {"action": "add-serves-measure", "module": "data-product", "view": obj.full_name if obj else name,
                                  "measure": measure.notation},
                                 "accept", f"Question: does {measure.label} also come from this view?"))
        if not linked:
            continue   # a space with no measure filter says nothing about its other tables
        for table in sorted(t.lower() for t in space.tables):
            if table in linked or table not in found.metric_views:
                continue
            obj = ontology.objects.get(names_here.get(table, ""))
            serves = ", ".join(obj.measures) if obj and obj.measures else "no measure"
            rows.append(_row("question", found.spelled(table), serves, "",
                             f"Genie space {space.title!r} reads this view, and none of its filters links the view to a measure",
                             note="Question: does this view have a measure of its own?"))
    return rows
