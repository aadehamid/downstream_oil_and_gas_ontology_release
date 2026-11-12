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
            assert len(rules.options(cat, committed["lists"], question)) >= 2, question["id"]
    assert set(committed["lists"]) == set(catalogue.ONTOLOGY_LISTS)
    for name, items in committed["lists"].items():
        labels = [item["label"] for item in items]
        assert items and len(set(labels)) == len(labels), name      # a workbook cell finds its item by the label
        assert all(len(label) <= 200 for label in labels), name


def test_the_pick_lists_hold_the_counts_of_this_release(committed):
    # Counted by hand from the newest packages: core 2.4.0, kpi 1.3.0, organization 2.2.0, value-stream 1.2.0,
    # data-product 1.2.0, system 1.5.0 and integration 2.5.0.
    lists = committed["lists"]
    assert {name: len(items) for name, items in lists.items()} == {
        "business-areas": 7, "processes": 707, "measures": 41, "roles": 64, "value-stream-steps": 58,
        "measure-relationships": 3, "data-products": 49, "platform-tables": 33, "layers": 4, "data-product-kinds": 2,
        "systems": 49, "sources": 106, "modules": 13, "areas-and-modules": 20}
    by_level = {}
    for process in lists["processes"]:
        by_level[process["level"]] = by_level.get(process["level"], 0) + 1
    assert by_level == {0: 2, 1: 10, 2: 13, 3: 48, 4: 137, 5: 474, 6: 23}      # 71 at levels 1 to 3, 634 at 4 to 6
    assert sum(1 for p in lists["processes"] if p["area"]) == 485
    assert [a["label"] for a in lists["business-areas"] if not a["in_use"]] == ["IT Services"]
    assert sum(1 for r in lists["roles"] if r["group"] == "Planning persona") == 4
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
    assert stale == [], "rebuild with: py -m kpi_store.intake build"


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
    assert list(data["forms"]) == ["kpi-intake", "domain-activation", "process-map-request"]
    assert data["release"] == "KPI Store 1.1" and data["catalogue_version"] == "1.0"
    assert len(data["questions"]) == 63 and data["lists"]["processes"]
    assert [d["label"] for d in data["settings_lists"]["domains"] if d["active"]] == ["Market Price", "Financial Performance"]


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
                             "Domain activation", "Process map request", "Roles", "lists"]
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
    assert len(roles) == 10 and roles[0] == "Global Process Owner (or a named delegate)"


def test_a_filled_workbook_reads_back_as_the_same_answers(cat, committed):
    from openpyxl import load_workbook
    for name in EXAMPLES:
        from_json = answers.read_json(PACK / "examples" / f"{name}.json")
        from_workbook = answers.read(PACK / "examples" / f"{name}.xlsx", cat, committed["lists"])
        assert from_workbook.as_dict() == from_json.as_dict(), name
    # The blank form reads as a form with no answer, not as an error.
    blank = answers.read(PACK / build.FORM_XLSX, cat, committed["lists"])
    assert blank.answers == {} and blank.sign_offs == {}
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
    # The answers the ontology does not hold say so.
    assert all(a[q].startswith("Illustration: ") for q in ("1.4", "3.2", "4.9"))


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
    assert 250 <= len(text.split()) <= 350      # one page


def test_the_architects_page_maps_every_question_and_lists_the_facts_with_no_place(cat):
    text = build.architect_text(cat)
    for question in cat.questions:
        assert f"\n| {question['id']} | " in text, question["id"]
    assert "| 1 | The business area | domain identification |" in text
    assert "| 2.1 | What do you call this KPI? | Required | `skos:prefLabel`. The Architect derives `skos:notation` from it. |" in text
    assert "| F1 Name | `skos:prefLabel`, exactly one, English | kpi | required | 2.1 |  |" in text
    assert "The ontology's property is named `core:businessDomain`" in text
    for fact in ("The domain of a KPI", "The business area of a measure", "The decision the KPI supports", "The unit, as a value of its own",
                 "Who may see the KPI", "The topic, or family, of the KPI", "The accountable owner of a KPI", "The target of a KPI",
                 "The direction of a good value"):
        assert f"\n| {fact} | " in text, fact
