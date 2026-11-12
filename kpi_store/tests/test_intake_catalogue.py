"""The intake catalogue: it loads, its ids and rules hold together, and a wrong file is refused with the reason."""
import shutil

import pytest

from kpi_store.intake import catalogue, rules
from kpi_store.tests import intake_support as made_up


@pytest.fixture(scope="module")
def cat():
    return catalogue.load()


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
    # ten questions for the seven field groups: 2.5, 3.8 to 3.13, 6.8, 6.9 and 7.10.
    per_section = {s["id"]: len(cat.questions_of(section=s["id"])) for s in cat.sections}
    assert per_section == {"1": 6, "2": 5, "3": 13, "4": 9, "5": 4, "6": 9, "7": 10, "D": 10, "P": 7}
    assert cat.version == "1.1"
    assert [s["name"] for s in cat.sections][:7] == [
        "The business area", "What the KPI means", "The facts about it", "Where it belongs", "Other names for it",
        "What it connects to", "Where the data lives (IT only)"]
    assert cat.by_id["1.5"]["text"] == "Which domain does this KPI belong to?"
    assert cat.by_id["1.6"]["text"] == "Which other domains' data does it use?"
    assert cat.by_id["2.1"]["text"] == "What do you call this KPI?"


def test_every_question_id_is_unique_and_every_rule_names_a_question(cat):
    ids = [q["id"] for q in cat.questions]
    assert len(ids) == len(set(ids)) == 73
    for q in cat.questions:
        for cond in q.get("ask_when", []):
            assert cond["question"] in cat.by_id, q["id"]
        for key in ("narrow_by", "under", "per"):
            assert q.get(key, q["id"]) in cat.by_id, q["id"]
    assert all(rule["question"] in cat.by_id for rule in cat.kind_rules)


def test_the_role_titles_and_definitions_are_the_approved_ones(cat):
    # Two of the ten, copied by hand from the approved role table.
    assert cat.roles["data-owner"]["definition"] == \
        "Data Owners are accountable for a specific subset of the domains data. Approves definitions, access, and quality targets."
    assert cat.roles["global-process-owner"]["title"] == "Global Process Owner (or a named delegate)"
    assert list(cat.roles) == ["global-process-owner", "domain-owner", "data-owner", "data-product-owner", "data-steward",
                               "digital-it", "enterprise-data-governance", "business-analyst", "program-manager", "architect"]


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
    assert cat.by_id["2.5"]["text"].startswith("Which strategic objective does this KPI serve?")
    assert cat.by_id["7.8"]["text"] == "Which AI assistant or report answers from this view?"
    # The status is a choice of the settings file and starts at Draft. No older question changed its number.
    assert cat.by_id["3.9"]["default"] == "draft"
    assert [(i["id"], i["label"]) for i in cat.settings_lists["status"]] == [("draft", "Draft"), ("certified", "Certified"), ("retired", "Retired")]
    assert cat.by_id["3.3"]["text"] == "How often is it stated, and broken down by what?"
    assert cat.by_id["4.6"]["text"].startswith("Has the business named it as one of the few measures of a stated objective")


def test_the_settings_hide_and_add_entries_of_the_ontologys_lists(cat):
    # Copied by hand from the owner's decisions on questions 3.5, 6.1, 6.6 and 7.4.
    assert cat.pick_lists["sources"] == {"hide_tiers": ["industry", "framework", "peers"]}
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
        ({"roles": {"add": [{"id": "planner", "label": "stock planner"}]}}, "the list already holds 'stock planner'"),
    ):
        with pytest.raises(catalogue.CatalogueError) as error:
            picklists.apply_settings(made_up.data(), change)
        assert message in str(error.value)
