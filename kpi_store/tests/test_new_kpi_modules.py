"""The new-KPI path beyond the kpi module: what the KPI intake form says about the population (2.3, 2.4), the value
stream steps (6.3 to 6.5), the view and its assistant (6.6, 7.1, 7.8) and the measures it is mistaken for (5.2), as
KGCL lines and facts of the same proposal, applied in one run that releases each changed module.

The form is the shipped example Crack Spreads Pricing with a name, a definition and an other name of its own, as in
test_new_kpi.py. The lines, the facts and the rows they expect are written by hand. The apply tests run on a
temporary copy of the release; the tree itself is never written.
"""
import csv
import json
import shutil
from pathlib import Path

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from kpi_store import apply as apply_cmd, cut, propose as propose_cmd
from kpi_store.change import ChangeRefused, kgcl, kpi_tables, new_measures as nm, other_modules as om, proposal
from kpi_store.tests import support
from kpi_store.tests.test_new_kpi import FACTS as KPI_FACTS, LINES as KPI_LINES, M, SIGNED, kpi_form
from kpi_store.tests.test_propose_apply import NOW, _versions, digest, git, no_global_git, quiet, scratch_release  # noqa: F401

ROOT = support.ROOT
NAME = "Test Spread Margin"
VIEW = "view-mpr-mips-crack-spread-price-fact-metrics-vw"
STEPS = ("market-price-calculation-validation", "performance-tracking-analysis")
BASES = ("MPC's market benchmarks are the Gulf Coast, Mid-Continent and West Coast 3-2-1 crack spreads; MPC FY2025 10-K, "
         "Item 7 (reference/mpc/mpc-fy2025-10k-fact-sheet.md, section 8)",
         "MPC states that the sweet and sour crude differentials explain why realized margin differs from the blended "
         "crack; MPC FY2025 10-K, Item 7 (reference/mpc/mpc-fy2025-10k-fact-sheet.md, section 8)")
LINKS = [f"mlink:{s}--test-spread-margin" for s in STEPS]
OTHER_LINES = [line for step, link in zip(STEPS, LINKS) for line in (
    f"create edge vsprocess:{step} vs:measureLink {link}",
    f"create edge {link} vs:measure {M}",
    f"create edge {link} vs:relationship rel:benchmarks")] + [f"create edge table:{VIEW} dp:servesMeasure {M}"]
INCLUDES = "The crude and product benchmarks of each series' recipe (the market-data module's series)."
EXCLUDES = "The market cost of RINs, in MPC's 10-K regional and blended crack spreads."
RETURN = f"Not {NAME}: the scope note of {NAME} says how the two differ."
OTHER_FACTS = [(M, "pop:includes", INCLUDES), (M, "pop:excludes", EXCLUDES),
               (M, "pop:populationEvidence", "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"),
               (LINKS[0], "dcterms:bibliographicCitation", BASES[0]), (LINKS[1], "dcterms:bibliographicCitation", BASES[1]),
               ("measure:margin-capture", "skos:scopeNote", RETURN),
               ("measure:rm-margin-indicator", "skos:scopeNote", RETURN),
               ("measure:rm-margin-per-barrel", "skos:scopeNote", RETURN)]
LINES, FACTS = KPI_LINES + OTHER_LINES, KPI_FACTS + OTHER_FACTS
WHOLE = dict(drop=("3.6",))   # the example's answers of 2.3 to 7.8 stay in


# The pack builds the example's answers from the ontology, and a cut or another form can change them (a correction
# makes another view serve Crack Spreads Pricing): the answers these tests read are set here.
PINNED = {"2.3": INCLUDES, "2.4": EXCLUDES, "6.3": [om.PREFIXES["vsprocess"] + s for s in STEPS],
          "6.4": [om.PREFIXES["rel"] + "benchmarks"] * 2, "6.5": list(BASES), "6.6": om.PREFIXES["product"] + "master-pricing",
          "7.1": om.PREFIXES["table"] + VIEW, "7.8": "Crack Spread Price Analytics"}


def whole_form(folder, changes=None, number="", sign_offs=SIGNED):
    return kpi_form(folder, {**PINNED, **(changes or {})}, sign_offs, number, **WHOLE)


def test_the_new_prefixes_are_the_builders_namespaces():
    import importlib.util

    def builder(path):
        spec = importlib.util.spec_from_file_location(path.stem + "_for_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    ontology = ROOT / cut.ONTOLOGY
    bv = builder(ontology / "value-stream" / "build_value_streams.py")
    bp = builder(ontology / "data-product" / "build_pricing.py")
    bpop = builder(ontology / "population" / "build_population.py")
    assert (om.PREFIXES["vsprocess"], om.PREFIXES["mlink"], om.PREFIXES["rel"], om.PREFIXES["vs"]) == (
        str(bv.VSPROCESS), str(bv.MLINK), str(bv.REL), str(bv.VS))
    assert (om.PREFIXES["table"], om.PREFIXES["agent"], om.PREFIXES["dp"], om.PREFIXES["prov"]) == (
        str(bp.TABLE), str(bp.AGENT), str(bp.DP), str(bp.PROV))
    assert nm.PREFIXES["pop"] == str(bpop.POP)
    assert om.RELATIONSHIPS == bv.RELATIONSHIPS


def test_every_new_line_reads_and_writes_as_the_official_grammar_does():
    from kgcl_schema.grammar.parser import parse_statement
    from kgcl_schema.grammar.render_operations import render
    for line in OTHER_LINES + [f"create edge agent:crack-spread-price-analytics prov:used table:{VIEW}"]:
        assert kgcl.write_line(kgcl.read_line(line)) == line
        assert render(parse_statement(line)) == line


# ---------- propose ----------

def test_propose_carries_the_population_the_value_stream_the_view_and_the_return_notes(tmp_path):
    said = []
    [folder] = propose_cmd.propose([whole_form(tmp_path, number="NK-MOD-1")], tmp_path / "out", ROOT, now=NOW, say=said.append)
    read = proposal.read(folder)
    assert (read.lines, read.facts, read.route) == (LINES, FACTS, "minor")
    assert said[0] == f"wrote the proposal {folder.as_posix()}: 19 changes and 17 facts, route minor"
    summary = (folder / "summary.txt").read_text(encoding="utf-8")
    assert "Not in this proposal" not in summary
    for line in (f'  - What it counts: "{INCLUDES}"', f'  - What it leaves out: "{EXCLUDES}"',
                 "  - A value stream step that uses it: Market Price Calculation & Validation, as a benchmark.",
                 f'  - What says the step Market Price Calculation & Validation uses it: "{BASES[0]}"',
                 "  - The view that gives its values: idp_sbx.semantic_sem_commercial.mpr_mips_crack_spread_price_fact_metrics_vw.",
                 f'  - A sentence for the scope note of Margin Capture: "{RETURN}"',
                 "The changes reach these modules: kpi (minor), data-product (minor), value-stream (minor).",
                 "For the Architect: 6.7 is yes. The market-data module needs the KPI's named series, which this form "
                 "does not collect. Model them in market-data, as the check's routing says."):
        assert line in summary.splitlines(), line


def test_an_assistant_that_does_not_use_the_view_yet_gains_it(tmp_path):
    other = "view-mips-mpr-benchmark-prices-fact-vw"
    changes = {"7.1": om.PREFIXES["table"] + other}
    [folder] = propose_cmd.propose([whole_form(tmp_path, changes)], tmp_path / "out", ROOT, now=NOW, say=quiet)
    lines = proposal.read(folder).lines
    assert lines[-2:] == [f"create edge table:{other} dp:servesMeasure {M}",
                          f"create edge agent:crack-spread-price-analytics prov:used table:{other}"]


@pytest.mark.parametrize("changes,message", [
    ({"2.3": ""}, "2.4 says what the KPI leaves out, and 2.3 does not say what it counts"),
    ({"7.8": "A Made-Up Assistant"}, '7.8 names "A Made-Up Assistant", which is not an assistant of the data-product module'),
    ({"7.1": om.PREFIXES["table"] + "replica-mips-priceassessment"},
     "7.1 names table:replica-mips-priceassessment, which is not a metric view. Only a metric view serves a measure"),
    ({"6.6": om.PREFIXES["product"] + "rack-pricing"},
     "6.6 names product:rack-pricing, and the view of 7.1 is part of product:master-pricing"),
    ({"6.3": [om.PREFIXES["vsprocess"] + STEPS[0]] * 2, "6.4": [om.PREFIXES["rel"] + "benchmarks"] * 2, "6.5": list(BASES)},
     "6.3 names the step vsprocess:market-price-calculation-validation twice"),
])
def test_propose_refuses_what_the_other_modules_cannot_take(tmp_path, changes, message):
    with pytest.raises((propose_cmd.ProposeRefused, ChangeRefused), match=message):
        propose_cmd.propose([whole_form(tmp_path, changes)], tmp_path / "out", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "out").exists()


def test_a_new_view_needs_a_specialist():
    # The form asks 7.2 to 7.9 of a view that is not in the list; the check makes them complete first, and propose then
    # refuses the view, as the reference-item form refuses a table built from other tables.
    from kpi_store.intake import catalogue, picklists
    from kpi_store.intake.answers import Intake
    cat, lists = catalogue.load(ROOT / "kpi-intake"), picklists.load(ROOT / "kpi-intake")["lists"]
    data = json.loads((ROOT / "kpi-intake" / "examples" / "crack-spreads-pricing.json").read_text(encoding="utf-8"))
    answers = dict(data["answers"], **{"2.1": NAME, "7.1": "@not-in-list"})
    with pytest.raises(propose_cmd.ProposeRefused, match="7.1 names a view that the ontology does not hold. A new view is a "
                                                         "data product, and needs a specialist"):
        propose_cmd.kpi_changes(cat, Intake(answers=answers), lists, ROOT)


@pytest.mark.parametrize("lines,facts,message", [
    ([f"create edge vsprocess:{STEPS[0]} vs:measureLink mlink:{STEPS[1]}--test-spread-margin",
      f"create edge mlink:{STEPS[1]}--test-spread-margin vs:measure {M}",
      f"create edge mlink:{STEPS[1]}--test-spread-margin vs:relationship rel:benchmarks"],
     [(f"mlink:{STEPS[1]}--test-spread-margin", "dcterms:bibliographicCitation", "x")],
     "a measure link's id is <the step>--<the measure>"),
    (OTHER_LINES[:2], [OTHER_FACTS[3]], "needs exactly one vs:relationship link"),
    (OTHER_LINES[:3], [], "needs a dcterms:bibliographicCitation fact"),
    ([line.replace(STEPS[0], "a-made-up-step") for line in OTHER_LINES[:3]],
     [(LINKS[0].replace(STEPS[0], "a-made-up-step"), "dcterms:bibliographicCitation", "x")],
     "vsprocess:a-made-up-step is not a step of a value stream"),
    ([f"create edge table:{VIEW} dp:servesMeasure measure:a-made-up-measure"], [], "measure:a-made-up-measure is not a new measure of this change"),
    ([f"create edge agent:a-made-up-agent prov:used table:{VIEW}"], [], "agent:a-made-up-agent is not an assistant of the data-product module"),
    (["create edge table:x dp:layer layer:gold"], [], "a new KPI changes another module only by these links"),
])
def test_the_lines_and_facts_of_the_other_modules_are_refused_unless_they_fit(lines, facts, message):
    with pytest.raises(ChangeRefused, match=message):
        om.check_changes(kgcl.read_lines("\n".join(KPI_LINES + lines)), KPI_FACTS + facts, ROOT)


# ---------- apply ----------

def _rows(root, folder, name):
    return list(csv.DictReader((root / folder / f"{name}.csv").open(encoding="utf-8")))


@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_one_apply_releases_every_changed_module_and_commits_once(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    ontology = root / cut.ONTOLOGY
    built = {name: ontology / path for name, path in om.BUILT.items()}
    kept = {name: Graph().parse(path) for name, path in built.items()}
    note = {r["measure_id"]: r["not_note"] for r in _rows(root, kpi_tables.KPI_FOLDER, "measure-details")}
    held = _versions(root)
    order = cut._run("list", ["dependents.py", "kpi"], ontology / "release").split()
    [folder] = propose_cmd.propose([whole_form(tmp_path, number="NK-M1")], tmp_path / "proposals", root, now=NOW, say=quiet)
    said = []
    files = apply_cmd.apply([folder], root, say=said.append, now=NOW)
    now = _versions(root)
    from kpi_store import ontology_view as ov
    minor = lambda v: f"{ov.version_key(v)[0]}.{ov.version_key(v)[1] + 1}.0"
    patch = lambda v: f"{ov.version_key(v)[0]}.{ov.version_key(v)[1]}.{ov.version_key(v)[2] + 1}"   # after a correction too
    for module in order:
        assert now[module] == (minor if module in ("kpi", "data-product", "value-stream") else patch)(held[module]), module
    for module in order:   # each changelog names its own route: the changed modules a minor, the others a patch
        changelog = (ontology / "releases" / module / "CHANGELOG.md").read_text(encoding="utf-8")
        kind = "minor" if module in ("kpi", "data-product", "value-stream") else "patch"
        assert f"## {now[module]} (2026-11-19)\n\nA {kind} release." in changelog, module
    assert git(root, "status", "--porcelain") == ""
    assert git(root, "rev-list", "--count", "HEAD").strip() == "2"
    assert git(root, "log", "-1", "--format=%s").strip() == (
        f"Apply the new KPI NK-M1: kpi {now['kpi']}, data-product {now['data-product']}, value-stream {now['value-stream']}")
    assert set(git(root, "show", "--name-only", "--no-renames", "--format=", "HEAD").split()) == set(files)
    assert said[-2] == (f"Done. kpi is now {now['kpi']}, data-product {now['data-product']} and value-stream "
                        f"{now['value-stream']} (minor), and {len(order) - 3} modules that depend on them took a new patch. "
                        f"The apply changed {len(files)} files, and Git committed them.")
    # The rows and the entries the form added, written by hand.
    assert _rows(root, cut.ONTOLOGY / "population", "population")[-1] == {
        "measure_id": "test-spread-margin", "includes": INCLUDES, "excludes": EXCLUDES,
        "evidence": "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"}
    tables = {r["slug"]: r for r in _rows(root, cut.PRICING, "tables")}
    assert tables[VIEW]["serves_measures"].split(";")[-1] == "test-spread-margin"
    stream = json.loads((root / om.STREAM_FILES[0]).read_text(encoding="utf-8"))
    step = next(p for s in stream["stages"] for p in s["processes"] if p["id"] == "p-" + STEPS[0])
    assert step["measures"][-1] == {"measureId": "test-spread-margin", "relationship": "benchmarks", "basis": BASES[0]}
    details = {r["measure_id"]: r["not_note"] for r in _rows(root, kpi_tables.KPI_FOLDER, "measure-details")}
    for other in ("margin-capture", "rm-margin-indicator", "rm-margin-per-barrel"):
        assert details[other] == (f"{note[other]} {RETURN}" if note[other] else RETURN), other
    # The value stream's file changes by the added entries only.
    diff = git(root, "show", "--format=", "--unified=0", "HEAD", "--", om.STREAM_FILES[0].as_posix())
    removed = [x[1:] for x in diff.splitlines() if x.startswith("-") and not x.startswith("---")]
    added = [x[1:] for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++")]
    assert removed and all(line + "," in added for line in removed), diff   # a line that only gained a comma
    # The round trip of every built file, and no signer's name in any graph file.
    back = [om.compare(name, kept[name], built[name]) for name in built]
    assert sorted(line for lines, _ in back for line in lines) == sorted(LINES)
    assert sorted(fact for _, facts in back for fact in facts) == sorted(FACTS)
    for path in ontology.rglob("*"):
        if path.suffix in (".ttl", ".jsonld", ".nt", ".trig"):
            text = path.read_text(encoding="utf-8")
            assert not any(s["name"] in text for s in SIGNED.values()), path


def test_the_round_trip_of_each_module_refuses_what_neither_file_states(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    ontology = root / cut.ONTOLOGY
    before = {name: Graph().parse(ontology / path) for name, path in om.BUILT.items()}
    om.apply_changes(kgcl.read_lines("\n".join(LINES)), FACTS, root)
    after = {name: Graph().parse(ontology / path) for name, path in om.BUILT.items()}
    link = URIRef(om.iri(LINKS[0]))
    view = URIRef(om.iri(f"table:{VIEW}"))
    measure = URIRef(nm.iri(M))
    pop, vs, dp = nm.PREFIXES["pop"], om.PREFIXES["vs"], om.PREFIXES["dp"]
    cases = (
        ("population", lambda g: g.add((measure, URIRef(pop + "includes"), Literal("x", datatype=XSD.string)))),
        ("population", lambda g: g.remove((URIRef(nm.iri("measure:crack-spreads")), URIRef(pop + "excludes"), None))),
        ("value-stream", lambda g: g.add((link, URIRef(nm.PREFIXES["skos"] + "prefLabel"), Literal("x", lang="en")))),
        ("value-stream", lambda g: g.remove((link, None, URIRef(vs + "MeasureLink")))),
        ("data-product", lambda g: g.add((view, URIRef(dp + "servesMeasure"), Literal(nm.iri("measure:unit-utilization"))))),
        ("kpi", lambda g: g.set((URIRef(nm.iri("measure:margin-capture")), URIRef(nm.PREFIXES["skos"] + "scopeNote"),
                                 Literal("Another note.", lang="en")))))
    for name, change in cases:
        changed = Graph() + after[name]
        change(changed)
        with pytest.raises(ChangeRefused, match="the graphs differ"):
            om.compare(name, before[name], changed)
    back = [om.compare(name, before[name], after[name]) for name in om.BUILT]
    assert sorted(f for _, facts in back for f in facts) == sorted(FACTS)


def test_a_failing_step_rolls_every_module_back(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    [folder] = propose_cmd.propose([whole_form(tmp_path)], tmp_path / "proposals", root, now=NOW, say=quiet)
    before = digest(root)

    def fail(name):
        if name == "run the value-stream module's tests":
            raise RuntimeError("made-up failure")
    with pytest.raises(cut.CutFailed, match="the step 'run the value-stream module's tests' failed"):
        apply_cmd.apply([folder], root, say=quiet, now=NOW, before_step=fail)
    assert digest(root) == before


# ---------- round 1 of the review ----------

def _stream_with(root, text_of):
    """Rewrites the scratch release's first value stream file with text_of(its text)."""
    path = root / om.STREAM_FILES[0]
    path.write_text(text_of(path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")


def test_a_step_whose_list_is_empty_on_one_line_or_on_two_takes_its_entry_once(tmp_path):
    step = "p-supply-procurement-strategy"   # a step of the first file with no measure link
    line = f'          "id": "{step}",'
    for n, empty in enumerate(('"measures": [],', '"measures": [\n          ],')):
        root = scratch_release(tmp_path / str(n), git_copy=False)
        _stream_with(root, lambda t: t.replace(line, f"{line}\n          {empty}", 1))
        lines = [f"create edge vsprocess:{step[2:]} vs:measureLink mlink:{step[2:]}--test-spread-margin",
                 f"create edge mlink:{step[2:]}--test-spread-margin vs:measure {M}",
                 f"create edge mlink:{step[2:]}--test-spread-margin vs:relationship rel:informs"]
        facts = [(f"mlink:{step[2:]}--test-spread-margin", "dcterms:bibliographicCitation", "A made-up basis.")]
        _, texts, _, _ = om._edit(kgcl.read_lines("\n".join(KPI_LINES + lines)), KPI_FACTS + facts, root)
        text = texts[om.STREAM_FILES[0]]
        assert text.count('"measures"') == (root / om.STREAM_FILES[0]).read_text(encoding="utf-8").count('"measures"'), empty
        process = next(p for s in json.loads(text)["stages"] for p in s["processes"] if p["id"] == step)
        assert process["measures"] == [{"measureId": "test-spread-margin", "relationship": "informs", "basis": "A made-up basis."}]


def test_a_value_stream_file_laid_out_otherwise_is_refused_in_plain_words(tmp_path):
    root = scratch_release(tmp_path, git_copy=False)
    _stream_with(root, lambda t: t.replace(f'"id": "p-{STEPS[0]}",', f'"id":"p-{STEPS[0]}",', 1))
    with pytest.raises(ChangeRefused, match="is not laid out as the release ships it, so its entries cannot be added"):
        om.check_changes(kgcl.read_lines("\n".join(LINES)), FACTS, root)


@pytest.mark.parametrize("changes,message", [
    ({"6.3": [om.PREFIXES["vsprocess"] + STEPS[0], "@not-in-list"], "6.4": [om.PREFIXES["rel"] + "benchmarks"] * 2,
      "6.5": list(BASES)}, "6.3 names a step that the ontology does not hold. A new value stream step goes to the process "
                           "map request"),
    ({"6.6": "@not-in-list", "6.6.detail": "A made-up data product"},
     "6.6 names a data product that the ontology does not hold, and the view of 7.1 is part of product:master-pricing"),
])
def test_propose_refuses_a_step_or_a_data_product_that_is_not_in_the_list(tmp_path, changes, message):
    from kpi_store.intake import catalogue, picklists
    from kpi_store.intake.answers import Intake
    cat, lists = catalogue.load(ROOT / "kpi-intake"), picklists.load(ROOT / "kpi-intake")["lists"]
    data = json.loads((ROOT / "kpi-intake" / "examples" / "crack-spreads-pricing.json").read_text(encoding="utf-8"))
    answers = dict(data["answers"], **{"2.1": NAME, **changes})
    with pytest.raises(propose_cmd.ProposeRefused, match=message):
        propose_cmd.kpi_changes(cat, Intake(answers=answers), lists, ROOT)


@pytest.mark.parametrize("lines,message", [
    ([f"create edge table:{VIEW} dp:servesMeasure {M}", f"create edge agent:crack-spread-price-analytics prov:used product:{VIEW}"],
     "prov:used of an assistant points at table:<id>"),
    ([f"create edge table:{VIEW} dp:servesMeasure {M}"] * 2, f"table:{VIEW} serves {M} already in this change"),
])
def test_the_data_product_links_are_refused_unless_they_fit(lines, message):
    with pytest.raises(ChangeRefused, match=message):
        om.check_changes(kgcl.read_lines("\n".join(KPI_LINES + lines)), KPI_FACTS, ROOT)


def test_a_token_with_no_prefix_is_refused_before_it_is_split():
    # Round 1, finding 6: kgcl.write_line refuses an id with no colon before split reads its parts.
    change = kgcl.Change("create edge", "agent:crack-spread-price-analytics", predicate="prov:used", target=VIEW)
    with pytest.raises(ChangeRefused, match="is not an id of the form prefix:name"):
        om.split([change], [])


def _proposal(folder, lines, facts, route="minor", owner=False):
    folder.mkdir(parents=True)
    (folder / "change.kgcl").write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    (folder / "facts.csv").write_text(proposal.facts_text(facts), encoding="utf-8")
    signatures = [{"role": "Data Owner", "name": "A Data Owner", "date": "2026-11-19", "words": "Right."},
                  {"role": "Architect", "name": "An Architect", "date": "2026-11-19", "words": "Approved."}]
    if owner:
        signatures.append({"role": "Ontology Owner", "name": "An Ontology Owner", "date": "2026-11-19", "words": "Major."})
    (folder / "approval.json").write_text(json.dumps({"change": folder.name, "route": route, "new_module": False,
                                                      "signatures": signatures}), encoding="utf-8")
    return folder


def test_a_major_new_kpi_releases_each_changed_module_as_a_major(tmp_path):
    read = proposal.read(_proposal(tmp_path / "NK-MAJOR", LINES, FACTS, route="major", owner=True))
    target = apply_cmd.target_of([read])
    assert target.changed == {"kpi": "major", "data-product": "major", "value-stream": "major"}


def test_two_new_kpis_that_share_a_returned_note_or_an_assistant_are_applied_one_at_a_time(tmp_path):
    other = [line.replace("test-spread-margin", "test-spread-margin-two").replace("Test Spread Margin", "Test Spread Margin Two")
             for line in LINES]
    other_facts = [tuple(x.replace("test-spread-margin", "test-spread-margin-two") for x in f) for f in FACTS]
    one, two = _proposal(tmp_path / "one", LINES, FACTS), _proposal(tmp_path / "two", other, other_facts)
    with pytest.raises(ChangeRefused, match="the proposals one and two both add a sentence to the scope note of "
                                            "measure:margin-capture. Apply them one at a time"):
        apply_cmd.plan([one, two], ROOT)
    used = f"create edge agent:executive-summary-kpis-analytics prov:used table:{VIEW}"
    three = _proposal(tmp_path / "three", LINES + [used], FACTS[:-3])
    four = _proposal(tmp_path / "four", other + [used], other_facts[:-3])
    with pytest.raises(ChangeRefused, match=f"the proposals three and four both add the line {used}. Apply one, then make a "
                                            "new form for the other from the changed ontology"):
        apply_cmd.plan([three, four], ROOT)
    # Two new KPIs on the same step and the same view, each with its own lines, go in one run.
    five, six = _proposal(tmp_path / "five", LINES, FACTS[:-3]), _proposal(tmp_path / "six", other, other_facts[:-3])
    assert apply_cmd.plan([five, six], ROOT)[1].changed == {"kpi": "minor", "data-product": "minor", "value-stream": "minor"}


def test_two_renames_of_one_table_conflict_and_two_identical_links_conflict_as_lines():
    # Round 2 of the review: only a link (create edge) about a step, a view or an assistant is keyed by its whole line.
    rename = lambda name: proposal.Proposal(None, name, [kgcl.read_line(
        f"rename table:{VIEW} from 'Old Name' to '{name}'")], [], {})
    assert proposal.conflicts([rename("Name A"), rename("Name B")]) == [
        f"the proposals Name A and Name B both change the name of table:{VIEW}"]
    link = lambda name: proposal.Proposal(None, name, [kgcl.read_line(f"create edge table:{VIEW} dp:servesMeasure {M}")], [], {})
    assert proposal.conflicts([link("one"), link("two")]) == [
        f"the proposals one and two both add the line create edge table:{VIEW} dp:servesMeasure {M}"]
