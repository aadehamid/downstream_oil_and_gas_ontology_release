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
    # the two domain questions the owner added; 9 for Digital IT; then the two smaller forms.
    per_section = {s["id"]: len(cat.questions_of(section=s["id"])) for s in cat.sections}
    assert per_section == {"1": 6, "2": 4, "3": 7, "4": 9, "5": 4, "6": 7, "7": 9, "D": 10, "P": 7}
    assert [s["name"] for s in cat.sections][:7] == [
        "The business area", "What the KPI means", "The facts about it", "Where it belongs", "Other names for it",
        "What it connects to", "Where the data lives (IT only)"]
    assert cat.by_id["1.5"]["text"] == "Which domain does this KPI belong to?"
    assert cat.by_id["1.6"]["text"] == "Which other domains' data does it use?"
    assert cat.by_id["2.1"]["text"] == "What do you call this KPI?"


def test_every_question_id_is_unique_and_every_rule_names_a_question(cat):
    ids = [q["id"] for q in cat.questions]
    assert len(ids) == len(set(ids)) == 63
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
    ('per = "6.3"\nrequired = "required"\nask_when = [{ question = "6.3", answered = true }]\nwhy = "A step', 'per = "6.9"\nrequired = "required"\nask_when = [{ question = "6.3", answered = true }]\nwhy = "A step', "`per` names the question '6.9'"),
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
