"""Builds the filled examples from the ontology.

An example is a measure the ontology already holds, filled in as if it were new. Each answer that the ontology
holds is read from the newest packages, word for word. kpi-intake/examples/examples.toml names the measures and
gives the few answers the ontology does not hold, which that file marks as illustrations.

The build command writes each example as an answers file and as a filled workbook, and its --check fails when a
committed example differs from a fresh build. So an example cannot drift from the ontology unnoticed.
"""
import tomllib
from pathlib import Path

from kpi_store.intake import picklists as pl
from kpi_store.intake.answers import Intake

FILE = "examples.toml"
MKT = pl.BASE + "modules/market-data/"
POP = pl.BASE + "modules/population/"
PROV_USED = "http://www.w3.org/ns/prov#used"


class ExampleError(Exception):
    """examples.toml names something the ontology does not hold."""


def specs(folder):
    """The examples that examples.toml in the pack's examples folder names."""
    path = Path(folder) / "examples" / FILE
    with path.open("rb") as f:
        return tomllib.load(f).get("example", [])


def _kind_answers(release, measure):
    """The yes and no answers of section 4 that lead to the measure's kind, from its kind and its test."""
    kind = release.text("kpi", measure, pl.KPI + "measureKind").rsplit("/", 1)[-1]
    candidate = release.text("kpi", measure, pl.KPI + "kpiCandidate") == "true"
    chains = {
        "tracker-or-report": {"4.1": "no"},
        "not-a-measure": {"4.1": "no"},
        "alert": {"4.1": "yes", "4.2": "yes"},
        "market-indicator": {"4.1": "yes", "4.2": "no", "4.3": "yes"},
        "decision-support-indicator": {"4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "yes"},
        "plan-variance-diagnostic": {"4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "no", "4.5": "yes"},
        "kpi": {"4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "no", "4.5": "no", "4.6": "yes"},
        "operational-metric": {"4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "no", "4.5": "no", "4.6": "no",
                               "4.7": "yes" if candidate else "no"},
    }
    if kind not in chains:
        raise ExampleError(f"{measure} has the kind {kind!r}, which the examples do not know")
    return chains[kind]


def build(release, lists, cat, spec):
    """The Intake of one example. `release` is a picklists.Release."""
    from rdflib import URIRef
    measure = pl.KPI + "measure/" + spec["measure"]
    kpi = release.graph("kpi")
    if (URIRef(measure), URIRef(pl.RDF_TYPE), URIRef(pl.KPI + "MeasureDefinition")) not in kpi:
        raise ExampleError(f"the kpi module holds no measure {spec['measure']!r}")

    def text(predicate):
        return release.text("kpi", measure, predicate)

    answers = {}
    processes = {p["id"]: p for p in lists["processes"]}
    informed = sorted(release.texts("kpi", measure, pl.KPI + "informsProcess"), key=lambda p: (-processes[p]["level"], p))
    if informed:
        # The deepest process is where people use the number. Its level 1 to 3 ancestor answers 1.2.
        main = processes[informed[0]]
        top = main
        while top["level"] > 3:
            top = processes[top["parent"]]
        areas = [main["area"]] if main["area"] else main["areas"]
        if areas:
            answers["1.1"] = areas[0]
        answers["1.2"] = top["id"]
        if main is not top:
            answers["1.3"] = main["id"]
        if informed[1:]:
            answers["6.2"] = informed[1:]
    answers["2.1"] = text(pl.SKOS + "prefLabel")
    answers["2.2"] = text(pl.SKOS + "definition")
    answers["2.3"] = text(POP + "includes")
    answers["2.4"] = text(POP + "excludes")
    answers["3.1"] = text(pl.KPI + "basis")
    answers["3.3"] = text(pl.KPI + "grain")
    answers["3.4"] = text(pl.KPI + "comparedAgainst")
    listed = {s["id"] for s in lists["sources"]}
    answers["3.5"] = [s for s in release.texts("kpi", measure, pl.DCTERMS + "source") if s in listed]
    answers["3.5.detail"] = text(pl.DCTERMS + "bibliographicCitation")
    answers["3.6"] = text(pl.SKOS + "note")
    answers.update(_kind_answers(release, measure))
    answers["4.8"] = text(pl.KPI + "classificationReason")
    answers["5.1"] = release.texts("kpi", measure, pl.SKOS + "altLabel")
    answers["5.2"] = release.texts("kpi", measure, pl.KPI + "notToBeConfusedWith")
    answers["5.3"] = text(pl.SKOS + "scopeNote")
    answers["5.4"] = text(pl.KPI + "publicCounterpart")
    answers["6.1"] = release.texts("kpi", measure, pl.KPI + "usedBy")
    vs = release.graph("value-stream")
    links = sorted(str(s) for s in vs.subjects(URIRef(pl.VS + "measure"), URIRef(measure)))
    steps = []
    for link in links:
        step = "".join(str(s) for s in vs.subjects(URIRef(pl.VS + "measureLink"), URIRef(link)))
        steps.append((step, release.text("value-stream", link, pl.VS + "relationship"),
                      release.text("value-stream", link, pl.DCTERMS + "bibliographicCitation")))
    if steps:
        answers["6.3"] = [s[0] for s in steps]
        answers["6.4"] = [s[1] for s in steps]
        answers["6.5"] = [s[2] for s in steps]
    tables = release.subjects("data-product", pl.DP + "servesMeasure", measure)
    products = {p["id"] for p in lists["data-products"]}
    if tables:
        table = tables[0]
        product = release.text("data-product", table, pl.DCTERMS + "isPartOf")
        answers["6.6"] = product if product in products else "@none-yet"
        answers["7.1"] = table
        agents = release.subjects("data-product", PROV_USED, table)
        if agents:
            answers["7.8"] = release.text("data-product", agents[0], pl.RDFS_LABEL)
    else:
        answers["6.6"] = "@none-yet"
        answers["7.1"] = "@no-data-yet"
    if answers.get("4.3") == "yes":
        series = list(release.graph("market-data").subjects(URIRef(MKT + "seriesOf"), URIRef(measure)))
        answers["6.7"] = "yes" if len(series) > 1 else "no"
    for key, value in spec.get("illustration", {}).items():
        if key.removesuffix(".detail") not in cat.by_id:
            raise ExampleError(f"examples.toml gives an answer to {key}, which is no question")
        answers[key] = value
    answers = {k: v for k, v in answers.items() if v not in ("", [])}
    return Intake(form="kpi-intake", catalogue_version=cat.version, kpi_name=answers.get("2.1", ""),
                  request=dict(spec.get("request", {})), answers=answers,
                  sign_offs={k: dict(v) for k, v in spec.get("sign_offs", {}).items()},
                  consulted={k: dict(v) for k, v in spec.get("consulted", {}).items()},
                  example_of=spec["measure"], comment=spec.get("comment", ""))


def answer_text(cat, lists, intake, question):
    """One example answer as the forms show it: labels in place of ids, one line per answer."""
    from kpi_store.intake import rules
    held = rules.positions(intake.answers, question["id"])
    if not any(held):
        return ""
    labels = {o["id"]: o["label"] for o in rules.options(cat, lists, question)}
    lines = [labels.get(v, v) for v in held if v]
    detail = "".join(rules.values(intake.answers, question["id"] + ".detail")[:1])
    if detail:
        lines.append(detail)
    return "\n".join(lines)


def example_column(cat, lists, intakes):
    """The example answer of each question: the first example that answers it, named, else the catalogue's own
    example text."""
    out = {}
    for question in cat.questions:
        for intake in intakes:
            text = answer_text(cat, lists, intake, question)
            if text:
                out[question["id"]] = f"{intake.kpi_name}: {text}" if "\n" not in text else f"{intake.kpi_name}:\n{text}"
                break
        else:
            if question.get("example"):
                out[question["id"]] = question["example"]
    return out
