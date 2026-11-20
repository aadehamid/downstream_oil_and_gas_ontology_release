"""The generated files of the intake pack: the pick lists, the two forms, the two pages and the two examples.

The tests that compare the committed files with the release packages as shipped are listed in
scripts/pinned-tests.txt, because a cut or a new module version makes them stale until the pack is rebuilt.
Every expected value here is written by hand from the catalogue or from the release packages.
"""
import io
import json
import re
import shutil

import jsonschema
import pytest

from kpi_store.intake import answers, build, catalogue, check, page, picklists, rules, workbook
from kpi_store.intake.__main__ import main
from kpi_store.tests import intake_support as made_up
from kpi_store.tests.support import ROOT

PACK = catalogue.PACK
EXAMPLES = ("crack-spreads-pricing", "rm-margin-per-barrel")
KPI = "https://w3id.org/mpc/ontology/modules/kpi/"


@pytest.fixture(scope="module")
def cat():
    return catalogue.load()


@pytest.fixture(scope="module")
def committed():
    return picklists.load(PACK)


# ---- The pick lists ---------------------------------------------------------------------------------------------

def test_every_pick_list_a_question_names_resolves_to_a_list_that_is_not_empty(cat, committed):
    for question in cat.questions:
        if question["type"] in ("choice", "multi_choice"):
            # R9 offers the documents that record the module's tables, and this release has one; a new one needs a
            # specialist, because its evidence tier is in the integration module.
            least = 1 if question["source"] == "table-sources" else 2
            assert len(rules.options(cat, committed["lists"], question)) >= least, question["id"]
    assert set(committed["lists"]) == set(catalogue.ONTOLOGY_LISTS)
    for name, items in committed["lists"].items():
        labels = [item["label"] for item in items]
        assert items and len(set(labels)) == len(labels), name      # a workbook cell finds its item by the label
        assert all(len(label) <= 200 for label in labels), name


def test_the_pick_lists_hold_the_counts_of_this_release(committed):
    # Counted by hand from the newest packages: core 2.4.0, kpi 1.3.0, organization 2.2.0, value-stream 1.2.0,
    # data-product 1.2.0, system 1.5.0 and integration 2.5.0.
    lists = committed["lists"]
    # An entry that settings.toml adds is not the ontology's, so it is not counted here.
    assert {name: sum(1 for item in items if not item.get("added")) for name, items in lists.items()} == {
        "business-areas": 7, "processes": 707, "measures": 41, "roles": 64, "value-stream-steps": 58,
        "measure-relationships": 3, "data-products": 49, "platform-tables": 33, "layers": 4, "data-product-kinds": 2,
        "systems": 49, "sources": 106, "modules": 13, "areas-and-modules": 20, "system-kinds": 3, "system-sources": 25,
        "table-sources": 1}
    by_level = {}
    for process in lists["processes"]:
        by_level[process["level"]] = by_level.get(process["level"], 0) + 1
    assert by_level == {0: 2, 1: 10, 2: 13, 3: 48, 4: 137, 5: 474, 6: 23}      # 71 at levels 1 to 3, 634 at 4 to 6
    assert sum(1 for p in lists["processes"] if p["area"]) == 485
    assert [a["label"] for a in lists["business-areas"] if not a["in_use"]] == ["IT Services"]
    assert sum(1 for r in lists["roles"] if r.get("group") == "Planning persona") == 4
    assert sum(1 for r in lists["roles"] if r["label"].endswith("(deprecated)")) == 3
    assert "Distribution Planner" in [r["label"] for r in lists["roles"]]
    assert "Distribution Planner (planning persona)" in [r["label"] for r in lists["roles"]]
    assert sum(1 for t in lists["platform-tables"] if t["layer"].endswith("/layer/metric-view")) == 3
    assert sorted({s["group"] for s in lists["value-stream-steps"]}) == ["Commercial Hydrocarbon Lifecycle", "Order to Cash"]
    assert [r["label"] for r in lists["measure-relationships"]] == [
        "Benchmarks: The process compares results against the measure as an external reference.",
        "Informs: The process uses the measure as an input.",
        "Measures performance: The process tracks the measure as a result of the business."]
    assert committed["versions"]["kpi"] == "1.3.0" and len(committed["versions"]) == 13
    assert committed["release"] == "KPI Store 1.1"


def test_the_process_list_follows_the_business_area_and_the_chosen_process(cat, committed):
    # Written by hand: 20 of the 71 processes at levels 1 to 3 hold Commercial work, and Refinery Optimization
    # (CM 1.1.4.7) has 8 steps under it.
    lists = committed["lists"]
    commercial = "https://w3id.org/mpc/ontology/modules/core/business-domain/commercial"
    offered = [o for o in rules.options(cat, lists, cat.by_id["1.2"]) if not o["id"].startswith("@")]
    assert len(offered) == 71 and sum(1 for o in offered if commercial in o["areas"]) == 20
    steps = rules.options(cat, lists, cat.by_id["1.3"], {"1.2": "https://w3id.org/mpc/ontology/process/CM-1-1-4-7"})
    assert len(steps) == 9 and "CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price" in [s["label"] for s in steps]
    assert len(rules.options(cat, lists, cat.by_id["1.3"])) == 635      # 634 steps and "The step is missing"


def test_the_term_index_leaves_the_measures_out(committed):
    measures = {m["id"] for m in committed["lists"]["measures"]}
    assert committed["terms"] and not [t for t in committed["terms"] if t["id"] in measures]
    assert {t["module"] for t in committed["terms"]} <= set(committed["versions"])


# ---- Freshness (pinned: these compare the committed files with the packages as shipped) ---------------------------

def test_the_committed_pack_equals_a_fresh_build():
    # The pick lists, the HTML form, the Excel form, the two generated pages and both examples in both formats.
    stale = [path.relative_to(ROOT).as_posix() for path in build.stale(ROOT, PACK)]
    assert stale == [], "rebuild with: python -m kpi_store.intake build"


def test_the_build_writes_these_nine_files():
    names = sorted(path.relative_to(PACK).as_posix() for path, _, _ in build.outputs(ROOT, PACK))
    assert names == ["examples/crack-spreads-pricing.json", "examples/crack-spreads-pricing.xlsx",
                     "examples/rm-margin-per-barrel.json", "examples/rm-margin-per-barrel.xlsx", "for-the-architect.md",
                     "kpi-intake-form.html", "kpi-intake-form.xlsx", "pick-lists.json", "what-we-will-ask-you.md"]


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    """A copy of the pack, as built, that a test may change."""
    folder = tmp_path_factory.mktemp("pack") / "kpi-intake"
    shutil.copytree(PACK, folder)
    return folder


def test_a_changed_catalogue_makes_the_forms_stale_and_the_check_writes_nothing(copy, capsys):
    main(["build", "--pack", str(copy)])        # current for this tree's packages, also after a cut
    capsys.readouterr()
    assert main(["build", "--check", "--pack", str(copy)]) == 0
    assert capsys.readouterr().out.endswith("the intake pack is current\n")
    path = copy / "catalogue.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('text = "What do you call this KPI?"', 'text = "What is this KPI called?"'), encoding="utf-8", newline="\n")
    before = {p.name: p.read_bytes() for p in copy.iterdir() if p.is_file()}
    assert main(["build", "--check", "--pack", str(copy)]) == 1
    out = capsys.readouterr().out
    assert "kpi-intake-form.html differs from a fresh build" in out and "kpi-intake-form.xlsx differs from a fresh build" in out
    assert "pick-lists.json differs" not in out             # the question's text is in neither the lists nor the examples
    assert out.endswith("run this command again without --check\n")
    assert before == {p.name: p.read_bytes() for p in copy.iterdir() if p.is_file()}
    assert main(["build", "--pack", str(copy)]) == 0
    assert "What is this KPI called?" in (copy / "kpi-intake-form.html").read_text(encoding="utf-8")
    assert main(["build", "--check", "--pack", str(copy)]) == 0
    path.write_text(text, encoding="utf-8", newline="\n")


def test_a_changed_workbook_cell_or_dropdown_is_not_the_same_content(tmp_path, cat):
    from openpyxl import load_workbook
    lists = made_up.lists()
    path = tmp_path / "form.xlsx"
    workbook.save(workbook.build(cat, lists), path)
    assert workbook.same_content(path, workbook.build(cat, lists))          # two builds differ in bytes, not in content
    wb = load_workbook(path)
    wb["2 What the KPI means"]["B8"].value = "Another question"
    wb.save(path)
    assert not workbook.same_content(path, workbook.build(cat, lists))
    workbook.save(workbook.build(cat, lists), path)
    wb = load_workbook(path)
    wb["1 The business area"].data_validations.dataValidation.pop()
    wb.save(path)
    assert not workbook.same_content(path, workbook.build(cat, lists))
    assert not workbook.same_content(tmp_path / "missing.xlsx", workbook.build(cat, lists))


# ---- The HTML form ----------------------------------------------------------------------------------------------

def test_the_page_is_one_offline_file_with_lf_line_ends():
    raw = (PACK / build.FORM_HTML).read_bytes()
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert text.count("</script>") == 2 and "<script src" not in text and "<link" not in text and "@import" not in text
    assert not re.findall(r"""(?:src|href)=["'](?:https?:)?//""", text)
    assert "url(" not in text                               # no font or image is fetched
    assert "fetch(" not in text and "XMLHttpRequest" not in text
    assert "<pre" not in text                               # the document check would read a <pre> as a command
    data = json.loads(text.split('<script id="intake-data" type="application/json">')[1].split("</script>")[0])
    assert list(data["forms"]) == ["kpi-intake", "domain-activation", "process-map-request", "term-change", "reference-item", "new-module"]
    assert data["release"] == "KPI Store 1.1" and data["catalogue_version"] == "1.2"
    assert len(data["questions"]) == 91 and data["lists"]["processes"]
    assert data["guide"] == "how-to-use-the-form.html" and (PACK / data["guide"]).is_file()     # the guide, beside the form
    # The names of the other modules' terms, and whether each has a definition, with no definition text.
    core = data["term_names"]["core"]
    assert set(core) == {"defined", "undefined"} and all(isinstance(name, str) for names in core.values() for name in names)
    assert "Margin Management" in core["defined"] and "Process Business Renewal Request" in core["undefined"]
    assert [d["label"] for d in made_up.domains_as_shipped(data["settings_lists"]["domains"]) if d["active"]] == [
        "Market Price", "Financial Performance"]


def test_the_page_shows_who_answers_why_and_an_example_for_each_question(cat, committed):
    column = _example_column(cat, committed)
    data = page.data(cat, committed, column)
    by_id = {q["id"]: q for q in data["questions"]}
    assert by_id["4.8"]["asked_of_text"] == "Business analyst drafts, Data Owner confirms"
    assert by_id["4.2"]["requirement"] == 'Required if 4.1 is "yes"'
    assert by_id["6.7"]["requirement"] == "Asked only when the kind is market indicator"
    assert by_id["2.1"]["why"] == "One preferred name stops two teams from using two names for one thing."
    # The example comes from the filled examples: the first that answers the question, named.
    assert by_id["2.1"]["example"] == "Crack Spreads Pricing: Crack Spreads Pricing"
    assert by_id["4.7"]["example"] == "R&M Margin per Barrel: Yes"
    assert by_id["1.3"]["example"] == "Crack Spreads Pricing: CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price"
    assert by_id["7.6"]["example"].startswith("Not asked for the filled examples.")
    assert [q["id"] for q in data["questions"] if q["section"] in "1234567" and "example" not in q] == []


def test_the_embedded_data_cannot_close_its_script_element():
    assert page.embed({"text": "</script><b>&"}) == '{"text":"\\u003c/script>\\u003cb>\\u0026"}'


def _example_column(cat, committed):
    from kpi_store.intake import examples
    filled = [answers.read_json(PACK / "examples" / f"{name}.json") for name in EXAMPLES]
    return examples.example_column(cat, committed["lists"], filled)


# ---- The Excel form ---------------------------------------------------------------------------------------------

def test_the_workbook_has_a_sheet_per_section_dropdowns_and_a_hidden_lists_sheet():
    from openpyxl import load_workbook
    wb = load_workbook(PACK / build.FORM_XLSX)
    assert wb.sheetnames == ["Start", "1 The business area", "2 What the KPI means", "3 The facts about it", "4 Where it belongs",
                             "5 Other names for it", "6 What it connects to", "7 Where the data lives", "Sign-off",
                             "Domain activation", "Process map request", "Term change", "Reference item", "Roles", "lists"]
    assert wb["lists"].sheet_state == "hidden" and wb["Start"].sheet_state == "visible"
    ws = wb["1 The business area"]
    header = next(row for row in ws.iter_rows(values_only=True) if row[0] == "No.")
    assert header[:6] == ("No.", "Question", "Asked of", "Answer", "Why we ask", "Example answer")
    assert ws.column_dimensions["G"].hidden
    rows = {row[6]: row for row in ws.iter_rows(values_only=True) if row[6]}
    assert list(rows) == ["1.1", "1.1.detail", "1.2", "1.2.detail", "1.3", "1.3.detail", "1.4", "1.5", "1.5.detail",
                          "1.6#1", "1.6#2", "1.6#3", "1.6#4"]
    assert rows["1.1"][1] == "Which part of the business does this KPI belong to?"
    assert rows["1.1"][2] == "Global Process Owner\nRequired" and rows["1.1"][3] is None
    assert rows["1.1"][5] == "Crack Spreads Pricing: Commercial"
    assert rows["1.5"][1].endswith("Replace it with your organization's domains in settings.toml.")
    # Each choice has a dropdown over its own column of the lists sheet: 1.1 offers the 7 areas and "Not in the list".
    lists = wb["lists"]
    columns = {lists.cell(row=1, column=c).value: c for c in range(1, lists.max_column + 1)}
    areas = [lists.cell(row=r, column=columns["1.1"]).value for r in range(2, 10)]
    assert areas == ["Commercial", "Cross-functional", "Finance", "Finance-enabled Supply & Trading", "IT Services", "Marketing",
                     "Refining", "Not in the list"]
    validations = {str(dv.sqref): dv.formula1 for dv in ws.data_validations.dataValidation}
    row_of = {row[6].value: row[0].row for row in ws.iter_rows() if row[6].value}
    assert validations[f"D{row_of['1.1']}"] == "=lists!$A$2:$A$9"
    assert len(validations) == 5                              # 1.1, 1.2, 1.3, 1.5 and the four rows of 1.6
    signers = [row[0] for row in wb["Sign-off"].iter_rows(values_only=True) if str(row[6] or "").startswith("sign:")]
    assert signers == ["Data Owner", "Domain Owner", "Domain Owner", "Architect"]
    roles = [row[0] for row in wb["Roles"].iter_rows(min_row=2, values_only=True)]
    assert len(roles) == 11 and roles[0] == "Global Process Owner (or a named delegate)" and roles[-1] == "Ontology Owner"


def test_a_filled_workbook_reads_back_as_the_same_answers(cat, committed):
    from openpyxl import load_workbook
    for name in EXAMPLES:
        from_json = answers.read_json(PACK / "examples" / f"{name}.json")
        from_workbook = answers.read(PACK / "examples" / f"{name}.xlsx", cat, committed["lists"])
        assert from_workbook.as_dict() == from_json.as_dict(), name
    # The blank form reads as a form with no answer, not as an error.
    blank = answers.read(PACK / build.FORM_XLSX, cat, committed["lists"])
    assert blank.answers == {"3.9": "draft"} and blank.sign_offs == {}      # the status starts at Draft
    buffer = io.BytesIO()
    load_workbook(PACK / build.FORM_XLSX).save(buffer)        # a workbook saved again by a person still reads
    assert answers.read(PACK / build.FORM_XLSX, cat, committed["lists"], "domain-activation").answers == {}


# ---- The examples -----------------------------------------------------------------------------------------------

def test_both_examples_pass_the_check_in_both_formats(cat, committed):
    for name in EXAMPLES:
        for suffix in (".json", ".xlsx"):
            intake = answers.read(PACK / "examples" / (name + suffix), cat, committed["lists"])
            report = check.check(cat, committed, intake)
            assert report.complete, name + suffix + "\n" + report.text()
            assert "This file is a shipped example of that measure, filled in as if it were new, so the match is expected." in report.text()


def test_the_examples_match_the_answers_file_schema():
    schema = json.loads((PACK / "answers.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    for name in EXAMPLES:
        data = json.loads((PACK / "examples" / f"{name}.json").read_text(encoding="utf-8"))
        jsonschema.validate(data, schema)
        assert answers.structure_problems(data) == []
    # The schema and the code refuse the same wrong files.
    good = made_up.intake().as_dict()
    for change in ({"format": 2}, {"form": "survey"}, {"answers": {"2.1": 7}}, {"answers": ["2.1"]}, {"sign_offs": {"architect": {"signed": "yes"}}},
                   {"consulted": {"x": "yes"}}, {"extra": 1}, {"request": {"number": 7}}):
        bad = dict(good, **change)
        assert answers.structure_problems(bad), change
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)
    jsonschema.validate(good, schema)


def test_the_crack_spreads_example_quotes_the_ontology_word_for_word():
    # Each value is copied by hand from the kpi 1.3.0, value-stream 1.2.0 and data-product 1.2.0 packages.
    data = json.loads((PACK / "examples" / "crack-spreads-pricing.json").read_text(encoding="utf-8"))
    a = data["answers"]
    assert data["example_of"] == "crack-spreads" and data["kpi_name"] == a["2.1"] == "Crack Spreads Pricing"
    assert a["1.1"] == "https://w3id.org/mpc/ontology/modules/core/business-domain/commercial"
    assert (a["1.2"], a["1.3"]) == ("https://w3id.org/mpc/ontology/process/CM-1-1-4-7", "https://w3id.org/mpc/ontology/process/CM-1-1-4-7-4")
    assert a["1.5"] == "market-price"
    assert a["2.2"] == "Benchmark crack spreads: the market value of products made from a set ratio of crude, less the crude's price."
    assert a["2.4"] == "The market cost of RINs, in MPC's 10-K regional and blended crack spreads."
    assert a["3.1"] == "products price - crude price, for a stated crude:product ratio (for example 3-2-1)"
    assert a["3.3"] == "daily, by market hub" and a["3.4"] == "30-day trend; 5-year history"
    assert a["3.5.detail"] == "MPC-S01 Item 7 pp. 46, 51; KI-27; KI-28"
    assert (a["4.1"], a["4.2"], a["4.3"]) == ("yes", "no", "yes") and not {"4.4", "4.5", "4.6", "4.7"} & set(a)
    assert a["5.1"] == ["3-2-1 crack", "crack spread", "the crack"]
    assert a["5.2"] == [KPI + "measure/margin-capture", KPI + "measure/rm-margin-indicator", KPI + "measure/rm-margin-per-barrel"]
    assert a["5.3"].startswith("Not realized refinery margin, not margin capture, and not MPC's R&M Margin Indicator.")
    assert a["5.4"] == "MPC 10 (Gulf Coast, Mid-Continent, West Coast and blended 3-2-1 cracks)"
    assert a["6.1"] == [KPI + "persona/distribution-planner", KPI + "persona/prompt-planner", KPI + "persona/short-term-planner"]
    assert [s.rsplit("/", 1)[-1] for s in a["6.3"]] == ["market-price-calculation-validation", "performance-tracking-analysis"]
    assert [r.rsplit("/", 1)[-1] for r in a["6.4"]] == ["benchmarks", "benchmarks"]
    assert a["6.5"][0].startswith("MPC's market benchmarks are the Gulf Coast, Mid-Continent and West Coast 3-2-1 crack spreads; MPC FY2025 10-K, Item 7")
    assert a["6.6"].endswith("/product/master-pricing") and a["6.7"] == "yes"
    assert a["7.1"].endswith("/table/view-mpr-mips-crack-spread-price-fact-metrics-vw") and a["7.8"] == "Crack Spread Price Analytics"
    # The answers the ontology does not hold say so. The grain, the quality rule and the status follow the reference.
    assert all(a[q].startswith("Illustration: ") for q in ("1.4", "2.5", "3.2", "3.8", "3.10", "3.11", "4.9", "6.8", "6.9"))
    assert a["3.8"] == "Illustration: One value for each day and each Price Master record. It rolls up by price group, price sheet and price batch."
    assert a["3.10"].startswith("Illustration: Active records only. Soft-deleted rows are excluded.") and a["3.9"] == "draft"
    assert "3.12" not in a and "3.13" not in a and "7.10" not in a
    # settings.toml hides the measure's other source, so the example names only the planning team's measure list.
    assert a["3.5"] == ["https://w3id.org/mpc/ontology/source/planner-measure-list-2026-10-18"]


def test_the_margin_example_walks_all_five_tests():
    # Copied by hand from the kpi 1.3.0 package: an operational metric, decided by test 5, and a KPI candidate.
    data = json.loads((PACK / "examples" / "rm-margin-per-barrel.json").read_text(encoding="utf-8"))
    a = data["answers"]
    assert data["example_of"] == "rm-margin-per-barrel" and a["2.1"] == "R&M Margin per Barrel"
    assert [a[q] for q in ("4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7")] == ["yes", "no", "no", "no", "no", "no", "yes"]
    assert a["2.2"] == ("MPC's Refining & Marketing margin (sales revenue less the cost of refinery inputs and purchased products) "
                        "per barrel of net refinery throughput.")
    assert a["1.1"].endswith("/business-domain/marketing") and a["1.5"] == "financial-performance"
    assert (a["1.2"], a["1.3"]) == ("https://w3id.org/mpc/ontology/process/CM-1-3-5", "https://w3id.org/mpc/ontology/process/CM-1-3-5-1-4")
    assert a["6.2"] == ["https://w3id.org/mpc/ontology/process/CM-1-1-5"]
    assert [r.rsplit("/", 1)[-1] for r in a["6.4"]] == ["informs", "measures-performance"]
    assert a["5.4"] == "MPC 7" and a["6.6"] == "@none-yet" and a["7.1"] == "@no-data-yet"
    assert "6.7" not in a and "3.6" not in a
    assert a["3.12"][0].startswith("Illustration: Realized margin per barrel below the month's forecast")
    assert a["3.13"] == "Illustration: Starts 2026-01-01. No end date." and a["6.8"] == "Illustration: Value Chain Optimization Director, Commercial"
    # settings.toml hides both sources the package gives this measure. The example names the MPC Form 10-K instead,
    # and that is true to the package: the measure's citation there, quoted in 3.5's detail, cites MPC-S01, the 10-K.
    assert a["3.5"] == ["https://w3id.org/mpc/ontology/source/mpc-s01"] and a["3.5.detail"] == "MPC-S01 p. 51; MPC-S17; KI-01"
    package = (ROOT / "business_architecture/ontology/releases/kpi/1.3.0/kpi.ttl").read_text(encoding="utf-8")
    block = package.split("\nmeasure:rm-margin-per-barrel a ", 1)[1].split(" .\n", 1)[0]
    assert 'dcterms:bibliographicCitation "MPC-S01 p. 51; MPC-S17; KI-01"' in block
    assert "src:mpc-s01" not in block      # the package itself does not name the 10-K as this measure's source; the comment says so
    assert "MPC-S01 p. 51" in data["comment"]


def test_an_example_of_a_measure_the_ontology_lacks_is_refused(cat, committed):
    from kpi_store.intake import examples
    release = picklists.Release(ROOT)
    with pytest.raises(examples.ExampleError, match="holds no measure 'tank-turns'"):
        examples.build(release, committed["lists"], cat, {"measure": "tank-turns", "file": "x"})


# ---- The generated pages ----------------------------------------------------------------------------------------

def test_the_explainer_is_one_short_page(cat):
    text = build.explainer_text(cat)
    assert text.startswith("# What we will ask you and why\n\nYou have been asked to an interview about a KPI.")
    assert "1. Which part of the business the KPI belongs to, which process it is about, and which data domain it belongs to.\n" in text
    assert text.endswith("[How to use the form](how-to-use-the-form.html) shows how the form is filled, saved and checked.\n")
    assert 250 <= len(text.split()) <= 400      # one page


def test_the_architects_page_maps_every_question_and_lists_the_facts_with_no_place(cat):
    text = build.architect_text(cat)
    for question in cat.questions:
        assert f"\n| {question['id']} | " in text, question["id"]
    assert "| 1 | The business area | domain identification |" in text
    assert "| 2.1 | What do you call this KPI? | Required | `skos:prefLabel`. The Architect derives `skos:notation` from it. |" in text
    assert "| F1 Name | `skos:prefLabel`, exactly one, English | kpi | required | 2.1 |  |" in text
    assert "The ontology's property is named `core:businessDomain`" in text
    for fact in ("The domain of a KPI", "The business area of a measure", "The decision the KPI supports", "The unit, as a value of its own",
                 "Who may see the KPI", "The topic, or family, of the KPI", "The named owner of a KPI", "The thresholds of a KPI",
                 "The direction of a good value", "The strategic objective a measure serves", "The grain, as a value of its own"):
        assert f"\n| {fact} | " in text, fact
    assert "## The lists your settings change" not in text      # that section needs the built lists


def test_the_architects_page_says_what_the_settings_hide_and_add(cat, committed):
    # Counted by hand from the owner's decisions and the packages: 4 of 106 sources are offered,
    # one of 64 roles is hidden and one added, 13 of 49 catalog entries are data products, 5 of 49 systems are hidden
    # and one added.
    text = build.architect_text(cat, committed["lists"])
    for row in ("| `sources` | 3.5 | 4 of 106 | 102 | None |", "| `roles` | 6.1 and P5 | 64 of 65 | 1 | Value Chain Optimization Director |",
                "| `data-products` | 6.6 and D6 | 13 of 49 | 36 | None |", "| `systems` | 7.4 | 45 of 50 | 5 | SharePoint |"):
        assert row in text, row
    assert "- `sources` offers only the 4 entries that `keep_only` names, and so hides the other 102." in text
    assert "- `sources` shows 2 entries under a label of your settings (`labels`): MPC Economics, 3-2-1 Crack Spread KPI Definition; " in text
    assert "- `roles` hides: Black Oil Manager." in text
    assert "- `systems` hides: Databricks; MS Excel; MS Outlook; MS PowerPoint; MS Teams." in text
    assert "`data-products` offers only the entries that `keep_only` names, and so hides: BP&A; Brand Data & Integration;" in text


def test_the_forms_offer_what_the_settings_leave_and_add(cat, committed):
    lists = committed["lists"]
    offered = {q: [o["label"] for o in rules.options(cat, lists, cat.by_id[q])] for q in ("3.5", "6.1", "6.6", "7.4")}
    assert offered["3.5"] == [
        "Marathon Petroleum Corporation, Form 10-K for the fiscal year ended 2025-12-31",
        "MPC Economics, 3-2-1 Crack Spread KPI Definition",
        "MPLX LP, Form 10-K for the fiscal year ended 2025-12-31",
        "Value Chain Optimization Decision Support and Visualization: the planning team's measure list",
        "A document that is not in the list"]
    assert sorted(s["id"].rsplit("/", 1)[-1] for s in lists["sources"] if not s.get("hidden")) == [
        "mpc-economics-crack-spread-kpi-definition", "mpc-s01", "mplx-s01", "planner-measure-list-2026-10-18"]
    assert "Black Oil Manager" not in offered["6.1"] and "Value Chain Optimization Director (new, not yet in the ontology)" in offered["6.1"]
    assert not any(label.startswith("Value Chain Optimization (") for label in offered["6.1"])
    assert offered["6.6"] == [
        "Backcasting & Refining Continuous Improvement", "Commercial Risk", "Customer Master", "External Market Data",
        "Local Production Planning & Crude Scheduling", "Logistic Execution", "Master Pricing", "Operational Margin", "Physical Trading",
        "Product Availability & Allocations", "Rack Pricing", "Regional Production & Distribution Planning",
        "Revenue Accounting & Scheduling", "None yet", "Not in the list"]
    assert not {"Databricks", "MS Excel", "MS Outlook", "MS PowerPoint", "MS Teams"} & set(offered["7.4"])
    assert "SharePoint (new, not yet in the ontology)" in offered["7.4"] and "MIPS" in offered["7.4"] and len(offered["7.4"]) == 45
    # Every view the ontology holds under a data product is under one the form still offers, so 6.6 can name it.
    kept = {p["id"] for p in lists["data-products"] if not p.get("hidden")}
    assert {t["product"] for t in lists["platform-tables"] if t["product"]} <= kept
    # The workbook's dropdowns offer the same, and the page holds the marks.
    from openpyxl import load_workbook
    sheet = load_workbook(PACK / build.FORM_XLSX)["lists"]
    column = next(c for c in sheet.iter_cols() if c[0].value == "7.4")
    assert [cell.value for cell in column[1:] if cell.value] == offered["7.4"]
    data = page.data(cat, committed, {})
    assert data["added_modules"] == {"sources": "integration", "roles": "organization", "data-products": "data-product", "systems": "system"}
    assert sum(1 for s in data["lists"]["systems"] if s.get("hidden")) == 5


def test_the_folders_command_makes_the_shared_folder_and_keeps_what_is_in_it(tmp_path, capsys):
    from kpi_store.intake import folders
    assert main(["folders", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    top = tmp_path / "KPI-intake"
    assert sorted(p.name for p in top.iterdir()) == ["1-in-progress", "2-ready-for-check", "3-checked", "READ-ME.txt", "the-form"]
    assert sorted(p.name for p in (top / "the-form").iterdir()) == ["how-to-use-the-form.html", "kpi-intake-form.html", "kpi-intake-form.xlsx"]
    assert (top / "the-form" / "kpi-intake-form.html").read_bytes() == (PACK / "kpi-intake-form.html").read_bytes()
    assert "made KPI-intake/1-in-progress\n" in out and out.endswith("KPI-intake is ready\n")
    assert "2-ready-for-check\n  Answers files the Business analyst has finished." in (top / "READ-ME.txt").read_text(encoding="utf-8")
    # A second run changes nothing. A file a person keeps there is left alone, and an older form is replaced.
    kept = top / "1-in-progress" / "crack-spreads-pricing.kpi-intake.json"
    kept.write_text("{}", encoding="utf-8")
    assert main(["folders", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "KPI-intake is current; nothing was changed\n"
    (top / "the-form" / "kpi-intake-form.html").write_text("an older form", encoding="utf-8")
    assert main(["folders", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "replaced KPI-intake/the-form/kpi-intake-form.html\nKPI-intake is ready\n"
    assert kept.read_text(encoding="utf-8") == "{}"
    # A place that is no folder is refused in words.
    assert main(["folders", str(tmp_path / "nowhere")]) == 2
    assert "is not a folder" in capsys.readouterr().err
    assert [name for name, _ in folders.FOLDERS] == ["the-form", "1-in-progress", "2-ready-for-check", "3-checked"]


@pytest.mark.parametrize("linked", ["KPI-intake", "KPI-intake/the-form", "KPI-intake/3-checked", "KPI-intake/READ-ME.txt",
                                    "KPI-intake/the-form/kpi-intake-form.html"])
def test_the_folders_command_refuses_a_link_and_changes_nothing(tmp_path, capsys, linked):
    place, outside = tmp_path / "shared", tmp_path / "outside"
    place.mkdir()
    outside.mkdir()
    is_file = linked.endswith((".txt", ".html"))
    target = outside / ("kept.txt" if is_file else "folder")
    if is_file:
        target.write_text("kept as it was", encoding="utf-8")
    else:
        target.mkdir()
    link = place / linked
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=not is_file)
    except OSError:
        pytest.skip("this system does not let the test make a link")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert main(["folders", str(place)]) == 2
    err = capsys.readouterr().err
    assert "is a link." in err and "Nothing was changed." in err and "report" not in err
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == before      # nothing was made, inside or outside
    if is_file:
        assert target.read_text(encoding="utf-8") == "kept as it was"
    # The place itself may be reached by a link: that is the operator's choice.
    way = tmp_path / "way-in"
    link.unlink()
    way.symlink_to(place, target_is_directory=True)
    assert main(["folders", str(way)]) == 0
    assert (place / "KPI-intake" / "the-form" / "kpi-intake-form.html").is_file()


def test_a_build_that_cannot_write_a_file_says_so_and_how_to_repair_the_pack(copy, capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")
    main(["build", "--pack", str(copy)])
    capsys.readouterr()
    path = copy / "catalogue.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('text = "What do you call this KPI?"', 'text = "What is the KPI called?"'), encoding="utf-8", newline="\n")
    monkeypatch.setattr(workbook, "save", refuse)         # as when the workbook is open in Excel
    try:
        assert main(["build", "--pack", str(copy)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("stopped: the build could not read or write a file: ") and "Traceback" not in err
        assert "may already be new" in err and "run the build again: it repairs the pack" in err
    finally:
        monkeypatch.undo()
        path.write_text(text, encoding="utf-8", newline="\n")
        assert main(["build", "--pack", str(copy)]) == 0          # running it again repairs the pack
        assert main(["build", "--check", "--pack", str(copy)]) == 0
        capsys.readouterr()


def test_a_failure_to_make_the_folders_is_not_called_a_report_failure(tmp_path, capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr("shutil.copyfile", refuse)
    assert main(["folders", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("stopped: the shared folder could not be made or filled: ") and "report" not in err


def test_the_architects_page_names_an_added_entry_the_ontology_has_gained(cat):
    import copy as copies
    from kpi_store.intake import catalogue as c
    data = made_up.data()
    data["lists"]["systems"].append({"id": made_up.X + "sys/sharepoint", "label": "SharePoint"})
    settings = copies.copy(cat)
    settings.pick_lists = {"systems": {"add": [{"id": "sharepoint", "label": "SharePoint"}]}}
    built = picklists.apply_settings(data, settings.pick_lists)
    text = "\n".join(build.lists_text(settings, built["lists"]))
    # Not named by keep_only: the page says the entry is in the ontology, why it is not offered, and how to offer it.
    kept = copies.copy(cat)
    kept.pick_lists = {"systems": {"add": [{"id": "sharepoint", "label": "SharePoint"}], "keep_only": ["Stock Ledger"]}}
    data2 = made_up.data()
    data2["lists"]["systems"].append({"id": made_up.X + "sys/sharepoint", "label": "SharePoint"})
    text2 = "\n".join(build.lists_text(kept, picklists.apply_settings(data2, kept.pick_lists)["lists"]))
    assert "- `systems`: SharePoint is in the ontology and is not offered, because `keep_only` does not name it. Add its name to `keep_only` to offer it." in text2
    assert "- `systems`: the ontology now holds SharePoint." in text2
    assert ("- `systems`: the ontology now holds SharePoint. The entry under `add` is no longer offered a second time. An answer saved under it "
            "is read as the ontology's entry, and the check says so. Remove the entry from `add` once no form in progress uses it.") in text
    assert "| `systems` | 7.4 | 2 of 2 | 0 | None |" in text and c.ADDED_MARK not in text.split("Keep the lists")[0].split("|---|")[1]


def test_the_settings_still_hide_a_role_by_its_plain_label_after_it_is_deprecated():
    # The ontology's label of the role is "Stock Clerk". The build shows a deprecated term with a mark, and a `hide`
    # that was written before the deprecation names the label without it.
    def lists(*roles):
        data = made_up.data()
        data["lists"]["roles"] = [{"id": made_up.X + "role/" + tail, "label": label} for tail, label in roles]
        return data

    def hidden(data):
        built = picklists.apply_settings(data, {"roles": {"hide": ["Stock Clerk"]}})
        return {r["label"]: r.get("hidden", False) for r in built["lists"]["roles"]}

    marked = lists(("stock-clerk", "Stock Clerk" + picklists.DEPRECATED_MARK), ("yard-planner", "Yard Planner"))
    assert hidden(marked) == {"Stock Clerk (deprecated)": True, "Yard Planner": False}
    # A live entry of that exact label is the one meant, and the deprecated one beside it is left alone.
    both = lists(("stock-clerk-old", "Stock Clerk" + picklists.DEPRECATED_MARK), ("stock-clerk", "Stock Clerk"))
    assert hidden(both) == {"Stock Clerk (deprecated)": False, "Stock Clerk": True}
    # A name that no entry has, with or without the mark, still stops the build.
    with pytest.raises(catalogue.CatalogueError, match="names 'Stock Clerk'"):
        hidden(lists(("stock-clark", "Stock Clark" + picklists.DEPRECATED_MARK)))


# ---- The build writes only inside the pack folder -----------------------------------------------------------------

def _linked(tmp_path, name, directory=False):
    """A fresh copy of the pack in which one generated path is a link to a place outside it. Returns the pack and
    the outside target. Skips where the system does not let a test make a link, as Windows may."""
    pack = tmp_path / "kpi-intake"
    shutil.copytree(PACK, pack)
    outside = tmp_path / "outside" / name
    outside.parent.mkdir()
    inside = pack / name
    if directory:
        shutil.copytree(inside, outside)
        shutil.rmtree(inside)
    else:
        outside.write_text("not the pack's file\n", encoding="utf-8", newline="\n")
        inside.unlink()
    try:
        inside.symlink_to(outside, target_is_directory=directory)
    except OSError:
        pytest.skip("this system does not let the test make a link")
    return pack, outside


@pytest.mark.parametrize("check", [False, True])
def test_a_generated_file_that_is_a_link_is_refused_and_its_target_is_unchanged(tmp_path, capsys, check):
    pack, outside = _linked(tmp_path, "pick-lists.json")
    assert main(["build", "--pack", str(pack)] + (["--check"] if check else [])) == 2
    captured = capsys.readouterr()
    assert captured.err == ("stopped: pick-lists.json in the pack folder is a link. The build writes only inside the pack folder, "
                            "so it does not follow a link. Remove the link and run the command again.\n")
    assert captured.out == ""                               # nothing was written or compared before the refusal
    assert outside.read_text(encoding="utf-8") == "not the pack's file\n"
    assert (pack / "pick-lists.json").is_symlink()


@pytest.mark.parametrize("check", [False, True])
def test_a_linked_examples_folder_is_refused(tmp_path, capsys, check):
    pack, outside = _linked(tmp_path, "examples", directory=True)
    before = {p.name: p.read_bytes() for p in outside.iterdir()}
    # Make the examples stale, so a build that followed the link would write through it.
    (outside / "crack-spreads-pricing.json").write_text("{}\n", encoding="utf-8", newline="\n")
    before["crack-spreads-pricing.json"] = b"{}\n"
    assert main(["build", "--pack", str(pack)] + (["--check"] if check else [])) == 2
    assert capsys.readouterr().err.startswith("stopped: examples in the pack folder is a link.")
    assert before == {p.name: p.read_bytes() for p in outside.iterdir()}


def test_a_build_in_a_copied_pack_still_works_also_when_the_pack_folder_itself_is_reached_by_a_link(tmp_path, capsys):
    pack = tmp_path / "real" / "kpi-intake"
    shutil.copytree(PACK, pack)
    (pack / "what-we-will-ask-you.md").unlink()
    assert main(["build", "--pack", str(pack)]) == 0
    assert (pack / "what-we-will-ask-you.md").read_bytes() == build.explainer_text(catalogue.load(pack)).encode("utf-8")
    assert main(["build", "--check", "--pack", str(pack)]) == 0
    capsys.readouterr()
    # An operator may keep the pack behind a link of their own. The link to the pack folder is theirs to choose;
    # only a link below it is refused.
    link = tmp_path / "my-pack"
    try:
        link.symlink_to(pack, target_is_directory=True)
    except OSError:
        pytest.skip("this system does not let the test make a link")
    assert main(["build", "--check", "--pack", str(link)]) == 0
    assert capsys.readouterr().out.endswith("the intake pack is current\n")


def test_an_example_named_to_land_outside_the_pack_is_refused(tmp_path, capsys):
    pack = tmp_path / "kpi-intake"
    shutil.copytree(PACK, pack)
    spec = pack / "examples" / "examples.toml"
    text = spec.read_text(encoding="utf-8")
    assert text.count('file = "rm-margin-per-barrel"') == 1
    spec.write_text(text.replace('file = "rm-margin-per-barrel"', 'file = "../../escaped"'), encoding="utf-8", newline="\n")
    assert main(["build", "--pack", str(pack)]) == 2
    assert "is not inside the pack folder" in capsys.readouterr().err
    assert not (tmp_path / "escaped.json").exists() and not (tmp_path / "escaped.xlsx").exists()
