"""The completeness check: what it says about small filled forms, written by hand, as JSON and as a workbook.

Each case is read once from an answers file and once from a filled workbook. Both must give the same report.
The pick lists are the made-up ones of intake_support; the catalogue is the release's own.
"""
import json
import sys
from pathlib import Path

import pytest

from kpi_store.intake import answers, catalogue, check, workbook
from kpi_store.intake.__main__ import main
from kpi_store.tests import intake_support as made_up


@pytest.fixture(scope="module")
def cat():
    return catalogue.load()


@pytest.fixture(params=["json", "xlsx"])
def report_of(request, tmp_path, cat):
    """Writes an Intake as an answers file or as a filled workbook, reads it back and checks it."""
    def run(intake, terms=(), others=None, form=None):
        data = made_up.data(terms)
        if request.param == "json":
            path = tmp_path / "filled.json"
            path.write_text(answers.dumps(intake), encoding="utf-8", newline="\n")
        else:
            path = tmp_path / "filled.xlsx"
            kpi = intake if intake.form == "kpi-intake" else None
            workbook.save(workbook.build(cat, data["lists"], {}, kpi, others or ({intake.form: intake} if not kpi else None)), path)
        return check.check(cat, data, answers.read(path, cat, data["lists"], form or intake.form))
    return run


def test_a_complete_signed_form_passes(report_of):
    report = report_of(made_up.intake())
    assert report.complete, report.text()
    text = report.text()
    assert text.startswith("KPI intake check: Days of Cover\n")
    assert "2. What the KPI means\n  Answered 3 of the 5 questions that apply.\n  Nothing is missing.\n" in text
    assert "Kind of measure: operational metric (decided by 4.6, test 5)." in text
    assert "  The name is new, and the chosen process agrees with the business area.\n" in text
    assert "Result: the intake is complete and signed.\n" in text
    assert text.endswith("This check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md.\n")


def test_a_missing_required_answer_is_named(report_of):
    report = report_of(made_up.intake(remove=["2.2", "3.5.detail"]))
    assert not report.complete
    text = report.text()
    assert "  Missing:\n    2.2 In one or two sentences, what does it measure?" in text
    assert "    3.5 also needs: The document, its date and the page or section\n" in text
    assert report.blocking == ["2.2 is missing", "3.5 is missing"]
    assert "Result: not complete. 2 things to settle:" in text


def test_a_conditional_question_is_rightly_skipped(report_of):
    # 4.3 "yes" decides the kind, so 4.4 to 4.7 are not asked, and 6.7 is.
    form = made_up.intake(change={"4.3": "yes", "6.7": "no"}, remove=["4.4", "4.5", "4.6", "4.7"])
    report = report_of(form)
    assert report.complete, report.text()
    text = report.text()
    assert '  Rightly skipped: 4.4 (Required if 4.3 is "no"); 4.5 (Required if 4.4 is "no"); 4.6 (Required if 4.5 is "no"); 4.7 (Required if 4.6 is "no")\n' in text
    assert "Kind of measure: market indicator (decided by 4.3, test 3)." in text
    # 4.1 "no" makes it a tracker or report: 3.1 to 3.3 and the other tests are skipped, and need no answer.
    report = report_of(made_up.intake(change={"4.1": "no"}, remove=["3.1", "3.2", "3.3", "3.8", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"]))
    assert report.complete, report.text()
    assert ('  Rightly skipped: 3.1 (Required if 4.1 is not "no"); 3.2 (Required if 4.1 is not "no"); 3.3 (Required if 4.1 is not "no"); '
            '3.8 (Required if 4.1 is not "no"); 3.13 (Required if 3.12 has an answer)\n') in report.text()
    assert "Kind of measure: tracker or report (decided by 4.1, test 1)." in report.text()


def test_an_answer_to_a_question_the_rules_skip_is_an_error(report_of):
    report = report_of(made_up.intake(change={"4.3": "yes", "6.7": "no"}))   # 4.4 to 4.7 keep their answers
    assert not report.complete
    assert "4.4 has an answer, but its rule says it is not asked" in report.text()


def test_a_domain_that_is_not_active_routes_to_domain_activation(report_of):
    report = report_of(made_up.intake(change={"1.5": "customer"}))
    assert not report.complete
    assert ('  Domain activation needed: 1.5 is "Customer (not active)". This domain is not active yet. '
            "The KPI cannot be added until the domain is activated.\n") in report.text()
    assert report.blocking == ["1.5 routes the request: domain activation needed"]
    # "Not in the list" routes the same way, and asks for the missing domain's name.
    report = report_of(made_up.intake(change={"1.5": "@not-in-list", "1.5.detail": "Trading Risk"}))
    assert report.blocking == ["1.5 routes the request: domain activation needed"]
    report = report_of(made_up.intake(change={"1.5": "@not-in-list"}))
    assert report.blocking == ["1.5 is missing", "1.5 routes the request: domain activation needed"]


def test_a_domain_that_the_settings_file_does_not_hold_is_an_error(report_of):
    report = report_of(made_up.intake(change={"1.5": "Trading Risk"}))
    assert not report.complete
    assert '  Not in the ontology: 1.5: "Trading Risk" is not in the list of domains.\n' in report.text()


def test_a_missing_process_or_role_routes_to_a_process_map_request_not_to_domain_activation(report_of):
    report = report_of(made_up.intake(change={"1.2": "@not-in-list", "1.2.detail": "Blend Stock"}, remove=["1.3"]))
    text = report.text()
    assert '  Process map request needed: 1.2 is "Not in the list". The ontology does not hold this process.' in text
    assert "Domain activation needed" not in text
    assert report.blocking == ["1.2 routes the request: process map request needed"]
    report = report_of(made_up.intake(change={"6.1": [made_up.ROLE_PLANNER, "@not-in-list"], "6.1.detail": "Tank Farm Lead"}))
    assert report.blocking == ["6.1 routes the request: process map request needed"]


def test_a_restricted_kpi_brings_in_the_four_reviews(report_of):
    report = report_of(made_up.intake(change={"3.7": "restricted"}))
    text = report.text()
    assert '  Restricted: bring in Privacy, Security, Compliance and Risk: 3.7 is "Restricted".' in text
    assert "  Privacy, Security, Compliance and Risk: to consult. Record the date and the outcome.\n" in text
    assert report.blocking == ["Privacy, Security, Compliance and Risk must be consulted, and the form records no date and outcome"]
    done = made_up.intake(change={"3.7": "restricted"}, consulted={"privacy-security-compliance-risk": {"date": "2026-11-12", "outcome": "No objection."}})
    report = report_of(done)
    assert report.complete, report.text()
    assert "  Privacy, Security, Compliance and Risk: consulted on 2026-11-12. Outcome: No objection.\n" in report.text()


def test_a_name_the_ontology_already_holds_as_a_measure_stops_the_form(report_of):
    for name in ("Tank Turns", "tank turns", "Stock Turn"):       # the label, another case, and an other name
        report = report_of(made_up.intake(change={"2.1": name}))
        assert report.blocking == ['the measure "Tank Turns" already has this name'], name
        assert "Stop the form. The request becomes a change to that measure." in report.text()
    close = report_of(made_up.intake(change={"2.1": "Tank Turn"}))
    assert close.complete
    assert '  Close match: the measure "Tank Turns" has a name close to "Tank Turn".' in close.text()


TURNS_DEFINITION = "How often the stored volume is replaced in a month."     # the made-up measure's own definition


def test_a_shipped_example_left_as_it_is_matches_its_measure_on_purpose(report_of):
    example = report_of(made_up.intake(change={"2.1": "Tank Turns", "2.2": TURNS_DEFINITION}, example_of="tank-turns"))
    assert example.complete, example.text()
    assert ('  Same measure: the ontology already holds "Tank Turns". This file is a shipped example of that measure, '
            "filled in as if it were new, so the match is expected.\n") in example.text()
    assert "Example changed" not in example.text()
    # Case and punctuation do not count as a change, as everywhere in the check.
    example = report_of(made_up.intake(change={"2.1": "tank turns", "2.2": TURNS_DEFINITION.upper()}, example_of="tank-turns"))
    assert example.complete, example.text()


CHANGED = ('  Example changed: this file started from the shipped example of "Tank Turns", and its name (2.1) or its '
           "definition (2.2) has changed since. It is checked as a new request, like any other form.\n")


def test_an_example_renamed_with_its_definition_kept_is_the_same_measure(report_of):
    report = report_of(made_up.intake(change={"2.1": "Tank Throughput Ratio", "2.2": TURNS_DEFINITION}, example_of="tank-turns"))
    assert report.blocking == ['the measure "Tank Turns" already has this definition']
    text = report.text()
    assert CHANGED in text
    assert ('  Same measure: the measure "Tank Turns" already has this definition. '
            "Stop the form. The request becomes a change to that measure.\n") in text
    assert "so the match is expected" not in text


def test_an_example_with_its_name_kept_and_a_new_definition_is_the_same_measure(report_of):
    report = report_of(made_up.intake(change={"2.1": "Tank Turns", "2.2": "The number of tanks emptied in a week."}, example_of="tank-turns"))
    assert report.blocking == ['the measure "Tank Turns" already has this name']
    assert CHANGED in report.text()
    assert "so the match is expected" not in report.text()


def test_a_measure_typed_into_example_of_does_not_waive_the_match(report_of):
    # A new request whose author typed a measure's notation into "Example of", and copied that measure's definition.
    report = report_of(made_up.intake(change={"2.2": TURNS_DEFINITION}, example_of="tank-turns"))
    assert report.blocking == ['the measure "Tank Turns" already has this definition']
    assert CHANGED in report.text()
    assert "so the match is expected" not in report.text()
    # A notation that names no measure waives nothing either.
    report = report_of(made_up.intake(change={"2.1": "Tank Turns", "2.2": TURNS_DEFINITION}, example_of="no-such-measure"))
    assert report.blocking == ['the measure "Tank Turns" already has this name']
    assert '"Example of" holds "no-such-measure", which is not a measure in the ontology' in report.text()
    assert CHANGED not in report.text()


def test_the_same_name_in_another_module_asks_for_enterprise_data_governance(report_of):
    term = {"id": made_up.X + "party/days-of-cover", "module": "party", "names": ["Days of cover"], "definition": ""}
    report = report_of(made_up.intake(), terms=[term])
    text = report.text()
    assert '  Same name in another module: the party module holds a term named "Days of Cover"' in text
    assert report.blocking == ["Enterprise Data Governance must be consulted, and the form records no date and outcome"]
    consulted = {"enterprise-data-governance": {"date": "2026-11-12", "outcome": "Keep both; they differ."}}
    assert report_of(made_up.intake(consulted=consulted), terms=[term]).complete
    # A different definition under the same name also needs the Domain Owner's decision.
    term = dict(term, definition="The days until a contract ends.")
    report = report_of(made_up.intake(consulted=consulted), terms=[term])
    assert "The Domain Owner decides between the two and signs." in report.text()
    assert report.blocking == ['the Domain Owner has not signed: "I have decided between the two definitions, and this one stands."']
    signed = dict(made_up.SIGNED, **{"domain-owner": {"name": "A fourth signer", "date": "2026-11-12"}})
    assert report_of(made_up.intake(consulted=consulted, sign_offs=signed), terms=[term]).complete


def test_a_process_of_another_business_area_returns_the_form(report_of):
    report = report_of(made_up.intake(change={"1.1": made_up.AREA_SALES}))
    assert report.blocking == ['the process "S 1.1 Count Tanks" belongs to Supply, and the answer to 1.1 is Sales']
    assert "Return the form to the Business analyst." in report.text()


def test_a_value_the_ontology_does_not_hold_is_named(report_of):
    report = report_of(made_up.intake(change={"6.1": [made_up.X + "role/ghost"], "5.2": ["Shrinkage"]}, remove=["1.3"]))
    assert report.blocking == [
        "5.3 is missing", '5.2: "Shrinkage" is not in the list of measures.',
        '6.1: "https://example.org/role/ghost" is not in the list of roles.']
    # A step that is not under the chosen process, and a deprecated term.
    report = report_of(made_up.intake(change={"1.3": made_up.P_SELL_STEP}))
    assert '1.3: "M 1.1 Quote Price" is not under the process chosen in 1.2.' in report.blocking
    report = report_of(made_up.intake(change={"1.2": made_up.P_BARE}, remove=["1.3"]))
    assert report.blocking == ['1.2: "X 1 Unowned Work (deprecated)" is deprecated in the ontology. Choose the term that replaced it.']


def test_an_unsigned_form_is_not_complete(report_of):
    report = report_of(made_up.intake(sign_offs={}))
    assert report.blocking == [
        'the Data Owner has not signed: "The KPI\'s definition in this form is right: its name, its meaning, what it counts and what it leaves out."',
        'the Domain Owner has not signed: "This KPI belongs to my domain."',
        'the Architect has not signed: "The form is complete, and I approve the change to the ontology."']
    # A name without a date is no signature.
    half = dict(made_up.SIGNED, architect={"name": "A third signer", "date": ""})
    assert len(report_of(made_up.intake(sign_offs=half)).blocking) == 1


def test_the_domain_owners_confirmation_is_needed_on_every_kpi(report_of):
    without = {k: v for k, v in made_up.SIGNED.items() if k != "domain-confirmation"}
    report = report_of(made_up.intake(sign_offs=without))
    assert report.blocking == ['the Domain Owner has not signed: "This KPI belongs to my domain."']
    assert '  Domain Owner ("I have decided between the two definitions, and this one stands."): not needed.' in report.text()


def test_a_step_of_a_value_stream_needs_its_relationship_and_its_document(report_of):
    report = report_of(made_up.intake(change={"6.3": [made_up.STEP_SHIP, made_up.STEP_BILL], "6.4": [made_up.REL_INFORMS],
                                              "6.5": ["The stock manual, chapter 4.", "The stock manual, chapter 5."]}))
    assert report.blocking == ["6.4 is missing"]
    assert "    6.4 needs one answer for each answer to 6.3" in report.text()
    full = made_up.intake(change={"6.3": [made_up.STEP_SHIP], "6.4": [made_up.REL_INFORMS], "6.5": ["The stock manual, chapter 4."]})
    assert report_of(full).complete


def test_the_two_smaller_forms_have_their_own_questions_and_signers(report_of):
    activation = answers.Intake(form="domain-activation", answers={
        "D1": "Customer", "D2": "Accounts and contracts. Prices belong to Market Price.", "D3": "Head of Sales Operations",
        "D4": ["Accounts: the account lead"], "D5": ["The sales data steward"], "D7": [made_up.AREA_SALES],
        "D9": ["Contract Renewal Rate"], "D10": "The data governance charter of 2026-10-01."})
    report = report_of(activation)
    assert report.text().startswith("Domain activation check: Customer\n")
    assert report.blocking == ['the Domain Owner has not signed: "The domain is described rightly in this form, and I am its owner."',
                               'the Architect has not signed: "The form is complete, and I approve the change to the ontology."']
    activation.sign_offs = {"domain-owner": {"name": "A signer", "date": "2026-11-12"}, "architect": {"name": "A second signer", "date": "2026-11-12"}}
    assert report_of(activation).complete
    request = answers.Intake(form="process-map-request", answers={"P1": ["The step Blend Stock"]},
                             sign_offs={"global-process-owner": {"name": "A signer", "date": "2026-11-12"}, "architect": {"name": "A second signer", "date": "2026-11-12"}})
    report = report_of(request)
    assert report.blocking == ["P7 is missing"]
    request.answers["P7"] = ["The blending manual, 2026."]
    assert report_of(request).complete


def test_pick_lists_older_than_the_packages_stop_the_check(cat):
    report = check.check(cat, made_up.data(), made_up.intake(), stale={"kpi": ("1.0.0", "1.1.0")})
    assert report.blocking == ["the pick lists are older than the release packages"]
    assert "kpi (1.0.0 then, 1.1.0 now). Rebuild them first: python -m kpi_store.intake build" in report.text()


def test_a_workbook_cell_holds_the_label_and_a_label_it_does_not_know_stays_as_typed(tmp_path, cat):
    from openpyxl import load_workbook
    data = made_up.data()
    path = tmp_path / "filled.xlsx"
    workbook.save(workbook.build(cat, data["lists"], {}, made_up.intake()), path)
    wb = load_workbook(path)
    ws = wb["1 The business area"]
    rows = {row[6].value: row for row in ws.iter_rows() if row[6].value}
    assert rows["1.1"][3].value == "Supply" and rows["1.5"][3].value == "Market Price"
    rows["1.1"][3].value = "Shipping"                      # typed by hand, not in the list
    ws = wb["6 What it connects to"]
    rows = {row[6].value: row for row in ws.iter_rows() if row[6].value}
    assert rows["6.1#1"][3].value == "Stock Planner" and rows["6.1#2"][3].value is None
    rows["6.1#3"][3].value = "Billing Clerk"               # a gap between two answers is fine
    wb.save(path)
    read = answers.read(path, cat, data["lists"])
    assert read.answers["1.1"] == "Shipping"
    assert read.answers["6.1"] == [made_up.ROLE_PLANNER, "", made_up.ROLE_CLERK]
    report = check.check(cat, data, read)
    assert '1.1: "Shipping" is not in the list of business areas.' in report.blocking
    assert "  Roles: 1 of the chosen roles are in the role register." in report.text()


def test_a_date_typed_into_a_workbook_is_read_as_a_date(tmp_path, cat):
    import datetime
    from openpyxl import load_workbook
    data = made_up.data()
    path = tmp_path / "filled.xlsx"
    workbook.save(workbook.build(cat, data["lists"], {}, made_up.intake()), path)
    wb = load_workbook(path)
    rows = {row[6].value: row for row in wb["Sign-off"].iter_rows() if row[6].value}
    rows["sign:architect"][4].value = datetime.datetime(2026, 11, 13)
    wb.save(path)
    assert answers.read(path, cat, data["lists"]).sign_offs["architect"] == {"name": "A third signer", "date": "2026-11-13"}


def test_a_file_that_is_no_answers_file_is_refused(tmp_path, cat):
    lists = made_up.lists()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(answers.AnswersError, match="is not JSON"):
        answers.read(bad, cat, lists)
    bad.write_text(json.dumps({"format": 2, "form": "kpi-intake", "answers": {"2.1": 7}}), encoding="utf-8")
    with pytest.raises(answers.AnswersError) as error:
        answers.read(bad, cat, lists)
    assert "`format` must be 1" in str(error.value) and "the answer to 2.1 must be a text or a list of texts" in str(error.value)
    with pytest.raises(answers.AnswersError, match="neither a .json answers file nor a .xlsx workbook"):
        answers.read(tmp_path / "filled.csv", cat, lists)
    from openpyxl import Workbook
    other = tmp_path / "other.xlsx"
    Workbook().save(other)
    with pytest.raises(answers.AnswersError, match="is not a KPI intake workbook"):
        answers.read(other, cat, lists)


def test_the_command_exits_0_only_for_a_complete_form(tmp_path, capsys, monkeypatch):
    # The command reads the release's own pack. The shipped example is complete; the same file unsigned is not.
    # After a cut the committed lists are older than the packages, which another test covers, so that is set aside.
    monkeypatch.setattr("kpi_store.intake.picklists.stale_modules", lambda data, root: {})
    example = catalogue.PACK / "examples" / "crack-spreads-pricing.json"
    assert main(["check", str(example)]) == 0
    assert "Result: the intake is complete and signed." in capsys.readouterr().out
    data = json.loads(example.read_text(encoding="utf-8"))
    data["sign_offs"] = {}
    unsigned = tmp_path / "unsigned.json"
    unsigned.write_text(json.dumps(data), encoding="utf-8")
    assert main(["check", str(unsigned)]) == 1
    assert "Result: not complete. 3 things to settle:" in capsys.readouterr().out
    assert main(["check", str(tmp_path / "missing.json")]) == 2
    assert "stopped: " in capsys.readouterr().err


def test_the_questions_of_the_field_groups_are_required_or_optional_as_decided(report_of):
    # The objective, the grain, the status, the owner and the steward are required. The rest are optional.
    report = report_of(made_up.intake(remove=["2.5", "3.8", "3.9", "6.8", "6.9"]))
    assert report.blocking == ["2.5 is missing", "3.8 is missing", "3.9 is missing", "6.8 is missing", "6.9 is missing"]
    assert "    6.8 Who is accountable for this KPI's meaning and the action taken on" in report.text()
    # A threshold needs the date it applies from. The quality rule, the review and the API are optional.
    report = report_of(made_up.intake(change={"3.12": ["Low: under 5 days"]}))
    assert report.blocking == ["3.13 is missing"]
    full = {"3.10": "Counted tanks only.", "3.11": "Reviewed each year.", "3.12": ["Low: under 5 days"], "3.13": "From 2026-01-01.",
            "7.10": "The stock API."}
    report = report_of(made_up.intake(change=full))
    assert report.complete, report.text()
    assert "3. The facts about it\n  Answered 11 of the 13 questions that apply.\n  Nothing is missing.\n" in report.text()
    # A status that the settings file does not hold is named.
    report = report_of(made_up.intake(change={"3.9": "approved"}))
    assert report.blocking == ['3.9: "approved" is not in the list of status.']


def _with_settings(cat, tmp_path, kind, intake, pick_lists):
    """The report on a form, read from JSON or a workbook, against the made-up lists marked with these settings."""
    from kpi_store.intake import picklists
    data = picklists.apply_settings(made_up.data(), pick_lists)
    path = tmp_path / f"filled.{kind}"
    if kind == "json":
        path.write_text(answers.dumps(intake), encoding="utf-8", newline="\n")
    else:
        workbook.save(workbook.build(cat, data["lists"], {}, intake), path)
    return check.check(cat, data, answers.read(path, cat, data["lists"]))


@pytest.mark.parametrize("kind", ["json", "xlsx"])
def test_an_answer_the_settings_now_hide_still_checks_with_a_note(cat, tmp_path, kind):
    hide = {"roles": {"hide": ["Stock Planner"]}}
    report = _with_settings(cat, tmp_path, kind, made_up.intake(), hide)
    assert report.complete, report.text()
    assert ('  Note: 6.1: "Stock Planner" is hidden in this organization\'s settings. The forms no longer offer it. '
            "The answer was given before, and it stands.\n") in report.text()
    assert "Not in the ontology" not in report.text()


@pytest.mark.parametrize("kind", ["json", "xlsx"])
def test_an_answer_the_settings_added_tells_the_architect_to_add_it_first(cat, tmp_path, kind):
    add = {"roles": {"add": [{"id": "night-planner", "label": "Night Planner"}]}}
    report = _with_settings(cat, tmp_path, kind, made_up.intake(change={"6.1": [made_up.ROLE_PLANNER, "new:night-planner"]}), add)
    assert report.complete, report.text()        # it does not stop the intake, and it is no process map request
    assert ('To add to the ontology first\n  For the Architect: 6.1 names "Night Planner". The organization\'s settings added it, and the '
            "ontology does not hold it yet. Add it to the organization module with HOW-TO-UPDATE.md before you apply this KPI.\n") in report.text()
    assert "Process map request" not in report.text()
    # The free-text option still works, and still routes to the process map request.
    report = _with_settings(cat, tmp_path, kind, made_up.intake(change={"6.1": ["@not-in-list"], "6.1.detail": "Night Planner"}), add)
    assert report.blocking == ["6.1 routes the request: process map request needed"]
    # Without the setting, the same id is an unknown value.
    report = _with_settings(cat, tmp_path, kind, made_up.intake(change={"6.1": ["new:night-planner"]}), {})
    assert report.blocking == ['6.1: "new:night-planner" is not in the list of roles.']


def test_the_report_option_writes_the_report_beside_the_file(tmp_path, capsys, monkeypatch):
    import shutil
    monkeypatch.setattr("kpi_store.intake.picklists.stale_modules", lambda data, root: {})
    filled = tmp_path / "crack-spreads-pricing.kpi-intake.json"
    shutil.copy(catalogue.PACK / "examples" / "crack-spreads-pricing.json", filled)
    assert main(["check", str(filled), "--report"]) == 0
    out = capsys.readouterr().out
    saved = tmp_path / "crack-spreads-pricing.kpi-intake.check.txt"
    assert out.endswith("The report is also in crack-spreads-pricing.kpi-intake.check.txt, beside the file.\n")
    assert saved.read_text(encoding="utf-8") + out.splitlines()[-1] + "\n" == out
    assert "Result: the intake is complete and signed." in saved.read_text(encoding="utf-8")


@pytest.mark.parametrize("change", [{"roles": {"hide": ["Stock Planner"]}}, {"roles": {"keep_only": ["Billing Clerk"]}}])
def test_a_workbook_filled_before_an_entry_was_hidden_still_checks(cat, tmp_path, change):
    from kpi_store.intake import picklists
    before = made_up.data()
    path = tmp_path / "filled.xlsx"
    workbook.save(workbook.build(cat, before["lists"], {}, made_up.intake()), path)       # its cell holds "Stock Planner"
    after = picklists.apply_settings(made_up.data(), change)
    intake = answers.read(path, cat, after["lists"])
    assert intake.answers["6.1"] == [made_up.ROLE_PLANNER]
    report = check.check(cat, after, intake)
    assert report.complete, report.text()
    assert '  Note: 6.1: "Stock Planner" is hidden in this organization\'s settings.' in report.text()


@pytest.mark.parametrize("kind", ["json", "xlsx"])
def test_an_answer_saved_under_an_added_entry_is_read_as_the_entry_the_ontology_gained(cat, tmp_path, kind):
    from kpi_store.intake import picklists
    add = {"roles": {"add": [{"id": "night-planner", "label": "Night Planner"}]}}
    before = picklists.apply_settings(made_up.data(), add)
    filled = made_up.intake(change={"6.1": [made_up.ROLE_PLANNER, "new:night-planner"]})
    path = tmp_path / f"filled.{kind}"
    if kind == "json":
        path.write_text(answers.dumps(filled), encoding="utf-8", newline="\n")
    else:
        workbook.save(workbook.build(cat, before["lists"], {}, filled), path)     # its cell holds the "new" label
    # The ontology gains the role. The settings still name it under `add`.
    gained = made_up.data()
    night = made_up.X + "role/night-planner"
    gained["lists"]["roles"].append({"id": night, "label": "Night Planner", "group": "Role register"})
    import copy
    after = picklists.apply_settings(copy.deepcopy(gained), add)
    report = check.check(cat, after, answers.read(path, cat, after["lists"]))
    assert report.complete, report.text()
    assert 'Note: 6.1: "Night Planner" is now in the ontology; the answer was read as that entry.\n' in report.text()
    assert "To add to the ontology first" not in report.text() and "Not in the ontology" not in report.text()
    assert "Roles: 1 of the chosen roles are in the role register." in report.text()        # read as the register's role
    # An answer that holds both the old id and the new one is one answer.
    both = check._resolve(cat, after["lists"], made_up.intake(change={"6.1": [night, "new:night-planner"]}))[0]
    assert both.answers["6.1"] == [night]
    # Once the entry is removed from `add`, the old answer is unknown again, as the Architect's page says.
    report = check.check(cat, gained, made_up.intake(change={"6.1": ["new:night-planner"]}))
    assert report.blocking == ['6.1: "new:night-planner" is not in the list of roles.']


def test_a_form_loaded_without_a_status_is_not_given_the_default(cat, tmp_path):
    # The default belongs to a new form. A filled workbook that lacks 3.9 reads back without it, and the check says so.
    data = made_up.data()
    path = tmp_path / "filled.xlsx"
    workbook.save(workbook.build(cat, data["lists"], {}, made_up.intake(remove=["3.9"])), path)
    intake = answers.read(path, cat, data["lists"])
    assert "3.9" not in intake.answers
    assert check.check(cat, data, intake).blocking == ["3.9 is missing"]


def test_the_reports_of_two_forms_of_one_workbook_do_not_share_a_file(tmp_path, capsys, monkeypatch):
    import shutil
    from kpi_store.intake.__main__ import report_path
    monkeypatch.setattr("kpi_store.intake.picklists.stale_modules", lambda data, root: {})
    book = tmp_path / "crack-spreads-pricing.kpi-intake.xlsx"
    shutil.copy(catalogue.PACK / "examples" / "crack-spreads-pricing.xlsx", book)
    assert main(["check", str(book), "--report"]) == 0
    assert main(["check", str(book), "--form", "domain-activation", "--report"]) == 1
    out = capsys.readouterr().out
    first, second = tmp_path / "crack-spreads-pricing.kpi-intake.workbook.check.txt", tmp_path / "crack-spreads-pricing.kpi-intake.domain-activation.workbook.check.txt"
    assert first.read_text(encoding="utf-8").startswith("KPI intake check: Crack Spreads Pricing\n")
    assert second.read_text(encoding="utf-8").startswith("Domain activation check: ")
    assert "The report is also in crack-spreads-pricing.kpi-intake.domain-activation.workbook.check.txt, beside the file.\n" in out
    # An answers file of the same KPI, beside the workbook, has a report of its own.
    paired = tmp_path / "crack-spreads-pricing.kpi-intake.json"
    shutil.copy(catalogue.PACK / "examples" / "crack-spreads-pricing.json", paired)
    assert main(["check", str(paired), "--report"]) == 0
    assert report_path(paired) != report_path(book) and report_path(paired).is_file() and first.is_file()
    assert len(list(tmp_path.glob("*.check.txt"))) == 3
    # The rule: a JSON file holds one form and keeps its name; a workbook's report names the form.
    assert report_path("x.kpi-intake.json").name == "x.kpi-intake.check.txt"
    assert report_path("x.domain-activation.json", "domain-activation").name == "x.domain-activation.check.txt"
    assert report_path("margin.xlsx").name == "margin.kpi-intake.workbook.check.txt"
    assert report_path("margin.xlsx", "process-map-request").name == "margin.process-map-request.workbook.check.txt"


def test_a_report_that_cannot_be_written_says_so(tmp_path, capsys, monkeypatch):
    import shutil
    monkeypatch.setattr("kpi_store.intake.picklists.stale_modules", lambda data, root: {})
    filled = tmp_path / "crack-spreads-pricing.kpi-intake.json"
    shutil.copy(catalogue.PACK / "examples" / "crack-spreads-pricing.json", filled)
    (tmp_path / "crack-spreads-pricing.kpi-intake.check.txt").mkdir()        # a folder where the report would go
    assert main(["check", str(filled), "--report"]) == 2
    assert "stopped: the report could not be written to " in capsys.readouterr().err


def test_a_release_folder_without_its_packages_is_a_tool_error_in_words(tmp_path, capsys):
    # Exit 1 means "the form is not complete". A release that cannot be read is exit 2, with no traceback.
    example = catalogue.PACK / "examples" / "crack-spreads-pricing.json"
    assert main(["check", str(example), "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("stopped: ") and "Traceback" not in err and len(err.strip().splitlines()) == 1


def test_a_report_that_cannot_be_printed_is_a_tool_error(monkeypatch, capsys):
    # A closed pipe must not look like "the form is not complete" (exit 1) or end in a traceback.
    class Closed:
        def write(self, text):
            raise BrokenPipeError(32, "Broken pipe")

        def flush(self):
            pass

    example = catalogue.PACK / "examples" / "crack-spreads-pricing.json"
    monkeypatch.setattr(sys, "stdout", Closed())
    assert main(["check", str(example)]) == 2
    monkeypatch.undo()
    err = capsys.readouterr().err
    assert err.startswith("stopped: the report could not be printed") and "Traceback" not in err


def test_the_form_takes_a_mark_off_the_end_of_a_label_only():
    # rules.resolver removes a mark only at the end of a label. The form's script must do the same: String.replace
    # would remove the first place the mark's words appear, and a label may hold those words inside it.
    script = (Path(check.__file__).parent / "form.html").read_text(encoding="utf-8")
    assert "function withoutMark(label, mark)" in script and "label.endsWith(mark)" in script
    assert ".replace(DATA.added_mark" not in script and ".replace(DATA.hidden_mark" not in script
