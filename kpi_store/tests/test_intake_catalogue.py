"""The intake catalogue: it loads, its ids and rules hold together, and a wrong file is refused with the reason."""
import shutil

import pytest

from kpi_store.intake import catalogue, rules
from kpi_store.tests import intake_support as made_up


@pytest.fixture(scope="module")
def cat():
    return made_up.as_shipped(catalogue.load())   # the domain list as shipped, which the tests write by hand


def changed(tmp_path, old, new, file="catalogue.toml", count=1):
    """A copy of the pack's two files with one text replaced."""
    for name in ("catalogue.toml", "settings.toml"):
        shutil.copy(catalogue.PACK / name, tmp_path / name)
    text = (tmp_path / file).read_text(encoding="utf-8")
    assert text.count(old) >= count, old
    (tmp_path / file).write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")
    return tmp_path


def test_the_catalogue_holds_the_approved_questions(cat):
    # Written by hand from the approved list: 34 business questions in six sections, plus the topic question and
    # the two domain questions the owner added; 9 for Digital IT; then the two smaller forms. Catalogue 1.1 added
    # ten questions for the seven field groups: 2.5, 3.8 to 3.13, 6.8, 6.9 and 7.10. KPI Store 1.2 added the term
    # change (KPI-DEC-0002, Q10 form 4): the measure, six changes and the compatibility question of Q5; and the
    # reference item (Q10 form 5): the name, the kind, five questions for a system and two for a table; and P8 of the
    # process map request, the business area of its new processes, which the core release needs.
    per_section = {s["id"]: len(cat.questions_of(section=s["id"])) for s in cat.sections}
    assert per_section == {"1": 6, "2": 5, "3": 13, "4": 9, "5": 4, "6": 9, "7": 10, "D": 10, "P": 8, "T": 8, "R": 9, "N": 13}
    assert cat.version == "1.2"      # 1.1 added the ten questions; 1.2 reworded them
    assert [s["name"] for s in cat.sections][:7] == [
        "The business area", "What the KPI means", "The facts about it", "Where it belongs", "Other names for it",
        "What it connects to", "Where the data lives (IT only)"]
    assert cat.by_id["1.5"]["text"] == "Which domain does this KPI belong to?"
    assert cat.by_id["1.6"]["text"] == "Which other domains' data does it use?"
    assert cat.by_id["2.1"]["text"] == "What do you call this KPI?"


def test_every_question_id_is_unique_and_every_rule_names_a_question(cat):
    ids = [q["id"] for q in cat.questions]
    assert len(ids) == len(set(ids)) == 104
    for q in cat.questions:
        for cond in q.get("ask_when", []):
            assert cond["question"] in cat.by_id, q["id"]
        for key in ("narrow_by", "under", "per"):
            assert q.get(key, q["id"]) in cat.by_id, q["id"]
    assert all(rule["question"] in cat.by_id for rule in cat.kind_rules)


def test_the_role_titles_and_definitions_are_the_approved_ones(cat):
    # Two of the ten, copied by hand from the approved role table, and the Ontology Owner, who signs a major term change.
    assert cat.roles["data-owner"]["definition"] == \
        "Data Owners are accountable for a specific subset of the domains data. Approves definitions, access, and quality targets."
    assert cat.roles["global-process-owner"]["title"] == "Global Process Owner (or a named delegate)"
    assert list(cat.roles) == ["global-process-owner", "domain-owner", "data-owner", "data-product-owner", "data-steward",
                               "digital-it", "enterprise-data-governance", "business-analyst", "program-manager", "architect",
                               "ontology-owner"]


def test_every_required_fact_has_a_question_or_is_derived(cat):
    # The coverage table: a fact the measure shape requires must come from a question or be derived.
    required = [f for f in cat.facts if f["status"] == "required"]
    assert [f["id"] for f in required] == ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10"]
    assert [f["id"] for f in required if not (f["supplied_by"] or f.get("derived"))] == []
    assert len(cat.facts) == 29
    fed = {fact for q in cat.questions for fact in q["fact"]}
    assert {f["id"] for f in cat.facts if f["supplied_by"]} <= fed | {"F3"}   # F3 is derived from 2.1's answer
    # Each question that feeds no fact is a KPI-form question the gaps table names, or belongs to a smaller form.
    gaps = {g["question"] for g in cat.gaps}
    assert [q["id"] for q in cat.questions_of("kpi-intake") if not q["fact"] and q["id"] not in gaps] == []


def test_a_fact_with_no_question_fails_the_coverage_rule(tmp_path):
    # The coverage test above must be able to fail: take the question away from a required fact.
    folder = changed(tmp_path, 'status = "required"\nsupplied_by = ["2.2"]', 'status = "required"\nsupplied_by = []')
    broken = catalogue.load(folder)
    assert [f["id"] for f in broken.facts if f["status"] == "required" and not (f["supplied_by"] or f.get("derived"))] == ["F2"]


@pytest.mark.parametrize("old, new, message", [
    ('id = "2.2"\nsection = "2"', 'id = "2.1"\nsection = "2"', "question '2.1': the id is used twice"),
    ('ask_when = [{ question = "4.1", is = "yes" }]', 'ask_when = [{ question = "4.0", is = "yes" }]', "depends on the question '4.0', which does not exist"),
    ('type = "multi_choice"\nsource = "measures"', 'type = "multi_choice"\nsource = "measurements"', "names the list 'measurements'"),
    ('source = "settings:visibility"', 'source = "settings:audience"', "names the list 'settings:audience', which does not exist"),
    ('when = "restricted"\n  outcome = "restricted-review"', 'when = "secret"\n  outcome = "restricted-review"', "routes on 'secret', which is none of its options"),
    ('outcome = "restricted-review"\n  notice', 'outcome = "legal-review"\n  notice', "routes to 'legal-review', which is no outcome"),
    ('asked_of = ["data-steward"]\ntype = "long_text"\nrequired = "required"', 'asked_of = ["auditor"]\ntype = "long_text"\nrequired = "required"', "is asked of 'auditor', which is no role"),
    ('ask_when = [{ question = "4.1", is = "yes" }]', 'ask_when = [{ question = "4.3", is = "yes" }]', "question '4.2' depends on itself through"),
    ('per = "6.3"\nrequired = "required"\nask_when = [{ question = "6.3", answered = true }]\nwhy = "A step', 'per = "6.99"\nrequired = "required"\nask_when = [{ question = "6.3", answered = true }]\nwhy = "A step', "`per` names the question '6.99'"),
    ('default = "draft"', 'default = "approved"', "question '3.9': its default 'approved' is none of its options"),
])
def test_a_wrong_catalogue_is_refused_with_the_reason(tmp_path, old, new, message):
    with pytest.raises(catalogue.CatalogueError) as error:
        catalogue.load(changed(tmp_path, old, new))
    assert message in str(error.value)


def test_a_settings_file_without_a_role_the_catalogue_names_is_refused(tmp_path):
    folder = changed(tmp_path, 'id = "data-steward"', 'id = "steward"', file="settings.toml")
    with pytest.raises(catalogue.CatalogueError, match="is asked of 'data-steward', which is no role"):
        catalogue.load(folder)


def test_a_list_can_come_from_the_ontology_the_catalogue_or_the_settings_file(cat):
    lists = made_up.lists()
    assert [o["id"] for o in rules.options(cat, lists, cat.by_id["1.1"])] == [made_up.AREA_SUPPLY, made_up.AREA_SALES, "@not-in-list"]
    assert [o["label"] for o in rules.options(cat, lists, cat.by_id["4.1"])] == ["Yes", "No"]
    assert [o["label"] for o in rules.options(cat, lists, cat.by_id["3.7"])] == ["Anyone in the company", "Restricted"]
    # The example domain list of settings.toml, written here by hand: two active, six not.
    assert [o["label"] for o in rules.options(cat, lists, cat.by_id["1.5"])] == [
        "Customer (not active)", "Product (not active)", "Market Price", "Supply and Demand Plan (not active)",
        "Refinery Production (not active)", "Logistics (not active)", "Asset and Turnaround (not active)",
        "Financial Performance", "Not in the list"]


def test_the_settings_file_can_replace_a_list(tmp_path):
    folder = changed(tmp_path, 'id = "restricted"\nlabel = "Restricted"', 'id = "restricted"\nlabel = "Named people only"', file="settings.toml")
    cat = catalogue.load(folder)
    assert [o["label"] for o in rules.options(cat, made_up.lists(), cat.by_id["3.7"])] == ["Anyone in the company", "Named people only"]


def test_the_levels_and_the_chosen_process_narrow_the_process_list(cat):
    lists = made_up.lists()
    assert [o["id"] for o in rules.options(cat, lists, cat.by_id["1.2"])] == [made_up.P_PLAN, made_up.P_SELL, made_up.P_BARE, "@not-in-list"]
    steps = rules.options(cat, lists, cat.by_id["1.3"], {"1.2": made_up.P_SELL})
    assert [o["id"] for o in steps] == [made_up.P_SELL_STEP, "@not-in-list"]


def test_the_five_tests_stop_at_the_first_that_decides(cat):
    def asked(answers):
        return [q["id"] for q in cat.questions_of(section="4") if rules.is_asked(cat, answers, q)]

    assert asked({}) == ["4.1", "4.8", "4.9"]
    assert asked({"4.1": "yes", "4.2": "no", "4.3": "yes"}) == ["4.1", "4.2", "4.3", "4.8", "4.9"]
    assert asked({"4.1": "yes", "4.2": "no", "4.3": "no", "4.4": "no", "4.5": "no", "4.6": "no"}) == \
        ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9"]
    # A later answer left behind by an earlier change does not count: 4.1 "no" ends the chain.
    assert asked({"4.1": "no", "4.2": "no", "4.3": "yes"}) == ["4.1", "4.8", "4.9"]
    kinds = {
        ("4.1", "no"): ("tracker or report", 1), ("4.2", "yes"): ("alert", 2), ("4.3", "yes"): ("market indicator", 3),
        ("4.4", "yes"): ("decision-support indicator", 3), ("4.5", "yes"): ("plan-variance diagnostic", 4),
        ("4.6", "yes"): ("KPI", 5), ("4.6", "no"): ("operational metric", 5)}
    chain = ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6"]
    for (question, answer), (kind, test) in kinds.items():
        answers = {q: ("yes" if q == "4.1" else "no") for q in chain[:chain.index(question)]}
        answers[question] = answer
        rule = rules.kind(cat, answers)
        assert (rule["kind"], rule["test"]) == (kind, test), question
    assert rules.kind(cat, {"4.1": "yes"}) is None
    assert not rules.is_asked(cat, {"4.1": "no"}, cat.by_id["3.1"]) and rules.is_asked(cat, {}, cat.by_id["3.1"])
    assert rules.is_asked(cat, {"4.1": "yes", "4.2": "no", "4.3": "yes"}, cat.by_id["6.7"])
    assert not rules.is_asked(cat, {"4.1": "no", "4.3": "yes"}, cat.by_id["6.7"])


def test_the_questions_of_the_seven_field_groups_keep_their_numbers_and_rules(cat):
    # Written by hand from the owner's decision: what each new question asks, of whom, and whether it is required.
    expected = {
        "2.5": ("data-owner", "Required"), "3.8": ("data-steward", 'Required if 4.1 is not "no"'),
        "3.9": ("data-steward", "Required"), "3.10": ("data-steward", "Optional"), "3.11": ("data-steward", "Optional"),
        "3.12": ("data-steward", "Optional"), "3.13": ("data-steward", "Required if 3.12 has an answer"),
        "6.8": ("data-owner", "Required"), "6.9": ("data-owner", "Required"), "7.10": ("digital-it", "Optional")}
    for qid, (role, rule) in expected.items():
        question = cat.by_id[qid]
        assert (question["asked_of"], cat.requirement(question)) == ([role], rule), qid
        assert question["feeds"].startswith("Recorded on the form; the ontology has no place for it yet (see KNOWN-OPEN-ITEMS.md)."), qid
    assert cat.by_id["2.5"]["text"].startswith("Which business objective does this KPI help you track?")
    assert cat.by_id["7.8"]["text"] == "Which AI assistant or report answers from this view?"
    # The status is a choice of the settings file and starts at Draft. No older question changed its number.
    assert cat.by_id["3.9"]["default"] == "draft"
    assert [(i["id"], i["label"]) for i in cat.settings_lists["status"]] == [("draft", "Draft"), ("certified", "Certified"), ("retired", "Retired")]
    assert cat.by_id["3.3"]["text"] == "How often do people receive this KPI, and which breakdowns do they need in the report?"
    assert cat.by_id["4.6"]["text"] == "Has the business formally chosen this measure to track that objective, with a target and an accountable owner?"
    # What a reader must see is under the answer, not under "For the analyst".
    assert cat.by_id["3.9"]["help"] == "The form does not change this status when someone signs."
    assert cat.by_id["4.6"]["help"].startswith("Record the objective in 2.5 and the owner in 6.8.")
    assert "note" not in cat.by_id["6.8"] and "never goes into the ontology" in cat.by_id["6.8"]["help"]
    assert "Illustration, not a real limit" in cat.by_id["3.12"]["help"] and "YYYY-MM-DD" in cat.by_id["3.13"]["text"]


def test_the_settings_hide_and_add_entries_of_the_ontologys_lists(cat):
    # Copied by hand from the owner's decisions on questions 3.5, 6.1, 6.6 and 7.4.
    assert cat.pick_lists["sources"]["keep_only"] == ["mpc-economics-crack-spread-kpi-definition", "mpc-s01", "mplx-s01", "planner-measure-list-2026-10-18"]
    assert cat.pick_lists["sources"]["labels"]["mpc-s01"] == "Marathon Petroleum Corporation, Form 10-K for the fiscal year ended 2025-12-31"
    assert set(cat.pick_lists["sources"]) == {"keep_only", "labels"}
    assert cat.pick_lists["roles"] == {"hide": ["Black Oil Manager"],
                                       "add": [{"id": "value-chain-optimization-director", "label": "Value Chain Optimization Director"}]}
    assert len(cat.pick_lists["data-products"]["keep_only"]) == 13
    assert cat.pick_lists["systems"] == {"hide": ["Databricks", "MS Excel", "MS Outlook", "MS PowerPoint", "MS Teams"],
                                         "add": [{"id": "sharepoint", "label": "SharePoint"}]}


@pytest.mark.parametrize("old, new, message", [
    ("[pick_list.systems]", "[pick_list.measures]", "the lists that settings.toml can change are sources, roles, data-products, systems"),
    ('[pick_list.roles]\nhide = ["Black Oil Manager"]', '[pick_list.roles]\nhide_tiers = ["industry"]', "`hide_tiers` is for the list of sources only"),
    ('[pick_list.roles]\nhide = ["Black Oil Manager"]', '[pick_list.roles]\nhidden = ["Black Oil Manager"]', "it takes only hide, hide_tiers, keep_only, add"),
    ('[pick_list.roles]\nhide = ["Black Oil Manager"]', '[pick_list.roles]\nhide = "Black Oil Manager"', "`hide` is a list of texts"),
    ('[pick_list.data-products]\nkeep_only = [', '[pick_list.data-products]\nhide = ["HR"]\nkeep_only = [', "use `keep_only`, or `hide` and `hide_tiers`, not both"),
    ('id = "sharepoint"\nlabel = "SharePoint"', 'id = "sharepoint"', "each added entry needs an id and a label"),
    ('id = "sharepoint"', 'id = "new:sharepoint"', "the id of an added entry is a short name of its own"),
    ('"mpc-s01" = "Marathon', '"mpc-s01" = 7\n"x" = "Marathon', "`labels` gives an entry the label the forms show"),
    ('id = "sharepoint"\nlabel = "SharePoint"', 'id = "sharepoint"\nlabel = "SharePoint"\n\n[[pick_list.systems.add]]\nid = "sharepoint-online"\nlabel = " sharepoint "',
     "two added entries have the same label"),
])
def test_a_wrong_pick_list_setting_is_refused_with_the_reason(tmp_path, old, new, message):
    with pytest.raises(catalogue.CatalogueError) as error:
        catalogue.load(changed(tmp_path, old, new, file="settings.toml"))
    assert message in str(error.value)


def test_a_hidden_entry_is_not_offered_and_an_added_entry_is_offered_marked_new(cat):
    from kpi_store.intake import picklists
    built = picklists.apply_settings(made_up.data(), {
        "roles": {"hide": ["Billing Clerk"], "add": [{"id": "night-planner", "label": "Night Planner"}]},
        "sources": {"hide_tiers": ["industry"]}, "systems": {"keep_only": [made_up.SYSTEM]}})
    lists = built["lists"]
    question = cat.by_id["6.1"]
    assert [o["label"] for o in rules.options(cat, lists, question)] == [
        "Night Planner (new, not yet in the ontology)", "Stock Planner", "A role that is not in the list"]
    assert [o["id"] for o in rules.options(cat, lists, question)][0] == "new:night-planner"
    # A reader that must know an older answer still finds the hidden entry, with the mark in its label.
    assert "Billing Clerk (hidden in this organization's settings)" in [o["label"] for o in rules.options(cat, lists, question, hidden=True)]
    assert [s["id"] for s in lists["sources"] if s.get("hidden")] == [made_up.SOURCE]
    assert not any(s.get("hidden") for s in lists["systems"])
    # A name that matches no entry stops the build, and so does an added label the list already holds.
    for change, message in (
        ({"roles": {"hide": ["Billing Clark"]}}, "`hide` names 'Billing Clark', which is no entry of the list"),
        ({"systems": {"keep_only": ["Ledger"]}}, "`keep_only` names 'Ledger'"),
        ({"sources": {"hide_tiers": ["folklore"]}}, "`hide_tiers` names 'folklore', which is no tier"),
        ({"roles": {"hide": ["Stock Planner"], "add": [{"id": "stock", "label": "stock planner"}]}}, "`hide` hides 'Stock Planner' and `add` adds it"),
        ({"roles": {"add": [{"id": "clerk", "label": "Stock Planner"}]}}, "the added entry 'Stock Planner' matches 2 entries of the list"),
        ({"roles": {"add": [{"id": "a", "label": "Night Planner"}, {"id": "b", "label": "night planner "}]}}, "two added entries have the label"),
    ):
        with pytest.raises(catalogue.CatalogueError) as error:
            picklists.apply_settings(made_up.data(), change)
        assert message in str(error.value)


def test_an_added_entry_the_ontology_has_gained_becomes_an_alias_and_is_not_offered_twice(cat):
    from kpi_store.intake import picklists
    # "Billing Clerk" is in the list. The settings still add it, as they did before the ontology held it.
    built = picklists.apply_settings(made_up.data(), {"roles": {"add": [{"id": "billing-clerk", "label": "Billing Clerk"}]}})
    question = cat.by_id["6.1"]
    assert [o["label"] for o in rules.options(cat, built["lists"], question)] == ["Billing Clerk", "Stock Planner", "A role that is not in the list"]
    assert rules.resolver(cat, built["lists"], question)["new:billing-clerk"] == (made_up.ROLE_CLERK, True)
    assert not any(r.get("added") for r in built["lists"]["roles"])


def test_an_entry_can_be_shown_under_a_label_of_the_settings_and_is_still_found_by_its_older_label(cat, tmp_path):
    from kpi_store.intake import answers, check, picklists, workbook
    # The workbook is filled before the settings rename the role, so its cell holds "Stock Planner".
    before = made_up.data()
    path = tmp_path / "filled.xlsx"
    workbook.save(workbook.build(cat, before["lists"], {}, made_up.intake()), path)
    after = picklists.apply_settings(made_up.data(), {"roles": {"labels": {"planner": "Planner of stock"}, "hide": ["Billing Clerk"]},
                                                       "sources": {"keep_only": ["manual"], "labels": {made_up.SOURCE: "The stock manual"}}})
    question = cat.by_id["6.1"]
    assert [o["label"] for o in rules.options(cat, after["lists"], question)] == ["Planner of stock", "A role that is not in the list"]
    ids = workbook.label_ids(cat, after["lists"], question)
    assert ids["Stock Planner"] == ids["Planner of stock"] == made_up.ROLE_PLANNER      # the old label, the new label, one entry
    assert ids["Billing Clerk"] == ids["Billing Clerk (hidden in this organization's settings)"] == made_up.ROLE_CLERK
    intake = answers.read(path, cat, after["lists"])
    assert intake.answers["6.1"] == [made_up.ROLE_PLANNER] and intake.answers["3.5"] == [made_up.SOURCE]
    report = check.check(cat, after, intake)
    assert report.complete, report.text()
    # A workbook built after the change shows the new label, and reads back as the same id.
    workbook.save(workbook.build(cat, after["lists"], {}, made_up.intake()), path)
    from openpyxl import load_workbook
    cells = [c.value for row in load_workbook(path)["6 What it connects to"].iter_rows() for c in row]
    assert "Planner of stock" in cells
    assert answers.read(path, cat, after["lists"]).answers["6.1"] == [made_up.ROLE_PLANNER]
    # An added entry that the ontology gained under a label the settings then changed is still read as that entry.
    gained = made_up.data()
    gained["lists"]["roles"].append({"id": made_up.X + "role/night", "label": "Night Planner", "group": "Role register"})
    both = picklists.apply_settings(gained, {"roles": {"add": [{"id": "night", "label": "Night Shift Planner"}], "labels": {"Night Planner": "Night Shift Planner"}}})
    assert rules.resolver(cat, both["lists"], question)["new:night"] == (made_up.X + "role/night", True)
    assert workbook.label_ids(cat, both["lists"], question)["Night Shift Planner (new, not yet in the ontology)"] == "new:night"
    # A label that two entries would share, and a name that matches no entry, stop the build.
    for change, message in (({"roles": {"labels": {"planner": "Billing Clerk"}}}, "`labels` gives two entries the label"),
                            ({"roles": {"labels": {"ghost": "A ghost"}}}, "`labels` names 'ghost', which is no entry of the list")):
        with pytest.raises(catalogue.CatalogueError) as error:
            picklists.apply_settings(made_up.data(), change)
        assert message in str(error.value)


NIGHT = made_up.X + "role/night"


def _state(name):
    """The made-up lists in one state of one role, "Night Planner", and the id every stored value must be read as."""
    from kpi_store.intake import picklists
    add = [{"id": "night", "label": "Night Planner"}]
    data = made_up.data()
    in_ontology = {"id": NIGHT, "label": "Night Planner", "group": "Role register"}
    if name == "added":                      # the settings add it; the ontology does not hold it
        return picklists.apply_settings(data, {"roles": {"add": add}})["lists"], "new:night"
    data["lists"]["roles"].append(in_ontology)
    settings = {
        "kept": {},
        "hidden": {"roles": {"hide": ["Night Planner"]}},
        "relabelled": {"roles": {"labels": {"night": "Planner of the night shift"}}},
        "gained": {"roles": {"add": add}},
        "gained and relabelled": {"roles": {"add": add, "labels": {"night": "Planner of the night shift"}}},
        "gained and not kept": {"roles": {"add": add, "keep_only": ["Stock Planner"]}},
        "gained, relabelled and not kept": {"roles": {"add": add, "keep_only": ["planner"], "labels": {NIGHT: "Planner of the night shift"}}},
    }[name]
    return picklists.apply_settings(data, settings)["lists"], NIGHT


STORED = {       # state: the values an answers file, a draft or a workbook cell may hold for the entry
    "added": ["new:night", "Night Planner (new, not yet in the ontology)", "Night Planner"],
    "kept": [NIGHT, "Night Planner"],
    "hidden": [NIGHT, "Night Planner", "Night Planner (hidden in this organization's settings)"],
    "relabelled": [NIGHT, "Night Planner", "Planner of the night shift"],
    "gained": [NIGHT, "new:night", "Night Planner", "Night Planner (new, not yet in the ontology)"],
    "gained and relabelled": [NIGHT, "new:night", "Night Planner", "Night Planner (new, not yet in the ontology)", "Planner of the night shift",
                              "Planner of the night shift (new, not yet in the ontology)"],
    "gained and not kept": [NIGHT, "new:night", "Night Planner", "Night Planner (new, not yet in the ontology)",
                            "Night Planner (hidden in this organization's settings)"],
    "gained, relabelled and not kept": [NIGHT, "new:night", "Night Planner (new, not yet in the ontology)",
                                        "Planner of the night shift (hidden in this organization's settings)"],
}


@pytest.mark.parametrize("state, stored", [(state, value) for state, values in STORED.items() for value in values])
@pytest.mark.parametrize("kind", ["json", "xlsx"])
def test_a_stored_value_finds_its_entry_by_one_rule(cat, tmp_path, state, stored, kind):
    """The table of rules.py's one rule: each state of an entry, each value that may have been stored for it, read
    from an answers file and from a workbook cell. Every one is read as the entry's id of today, and the check
    passes. The same table is proved in the browser for a loaded file and a draft (browser_check.py, proof 21)."""
    from openpyxl import load_workbook
    from kpi_store.intake import answers, check, workbook
    lists, expected = _state(state)
    data = dict(made_up.data(), lists=lists)
    question = cat.by_id["6.1"]
    assert rules.resolver(cat, lists, question)[stored][0] == expected
    if kind == "json":
        if not stored.startswith(("new:", made_up.X)):
            pytest.skip("an answers file stores an id; a label is what a workbook stores")
        path = tmp_path / "filled.json"
        path.write_text(answers.dumps(made_up.intake(change={"6.1": [stored]})), encoding="utf-8", newline="\n")
    else:
        path = tmp_path / "filled.xlsx"
        workbook.save(workbook.build(cat, lists, {}, made_up.intake()), path)
        book = load_workbook(path)
        sheet = book[workbook.sheet_title(cat.section("6"))]
        cell = next(row[workbook.ANSWER_COLUMN - 1] for row in sheet.iter_rows() if row[workbook.KEY_COLUMN - 1].value == "6.1#1")
        cell.value = stored          # what a workbook filled under earlier settings holds
        book.save(path)
    report = check.check(cat, data, answers.read(path, cat, lists))
    assert report.complete, report.text()
    said = "is now in the ontology; the answer was read as that entry." in report.text()
    assert said == (state.startswith("gained") and ("new" in stored.split(made_up.X)[0])), report.text()
    assert ("To add to the ontology first" in report.text()) == (state == "added")
    assert ("is hidden in this organization's settings" in report.text()) == (state in ("hidden", "gained and not kept", "gained, relabelled and not kept"))


def test_an_added_entry_is_matched_to_a_gained_entry_that_the_settings_relabelled_or_do_not_keep(cat):
    question = cat.by_id["6.1"]
    # Relabelled: the add entry still has the ontology's label. It becomes an alias; no second "new" entry appears.
    lists, _ = _state("gained and relabelled")
    assert [r["id"] for r in lists["roles"] if r.get("added")] == []
    assert next(r for r in lists["roles"] if r["id"] == NIGHT)["aliases"] == ["new:night"]
    assert [o["label"] for o in rules.options(cat, lists, question)] == ["Billing Clerk", "Planner of the night shift", "Stock Planner", "A role that is not in the list"]
    # Not kept: the build goes on, the entry is an alias and stays hidden.
    lists, _ = _state("gained and not kept")
    night = next(r for r in lists["roles"] if r["id"] == NIGHT)
    assert night["hidden"] is True and night["aliases"] == ["new:night"]
    assert "Night Planner" not in [o["label"] for o in rules.options(cat, lists, question)]
    # An entry the ontology gained under another label is matched by the last part of its id.
    from kpi_store.intake import picklists
    data = made_up.data()
    data["lists"]["roles"].append({"id": NIGHT, "label": "Night Shift Planner", "group": "Role register"})
    lists = picklists.apply_settings(data, {"roles": {"add": [{"id": "night", "label": "Night Planner"}]}})["lists"]
    assert rules.resolver(cat, lists, question)["Night Planner (new, not yet in the ontology)"] == (NIGHT, True)
