"""Open the HTML intake form in a real browser and prove the twenty-two things a person filling it relies on.

    uv run --no-project --with playwright==1.65.0 python kpi_store/intake/browser_check.py

It needs uv, a network connection the first time (uv fetches the playwright package) and an installed Google
Chrome or Microsoft Edge. It downloads no browser. `--shots <folder>` also writes a screenshot of each proof.

Each proof starts from a fresh load of kpi-intake/kpi-intake-form.html, with empty storage:

  1 load         the page opens from file:// with no console error and no network request
  2 fill         a typed answer and a chosen answer change the count of required answers left
  3 narrow list  the process list follows the business area, and the step list follows the process
  4 conditional  a question that the rules skip is hidden, and comes back when the answer changes
  5 routing      an inactive domain and a missing process each show their own notice, and the section says "Routed"
  6 save         "Save answers to file" downloads the answers as a JSON file of the documented shape
  7 load file    "Load answers file" fills the form from the shipped Crack Spreads Pricing example, closes the
                 request details to one line, and counts only the signatures that are needed
  8 draft        an unsaved draft survives a reload, and "Clear this form" asks before it empties the form
  9 phone        at 390 px wide the page has no sideways scroll, a selector changes the view, the Sections
                 button opens the section list, and the page clears the bar of file buttons
 10 theme        the form starts light whatever the system says, and remembers the theme a person chooses
 11 next step    a routing notice names who answers, keeps settings.toml out of sight and opens the right form
 12 bad file     a malformed answers file is refused in words, changes no answer and leaves the form working
 13 other form   a domain activation file loaded from the KPI form opens in its own form and leaves the KPI answers
 14 detail       an optional answer that needs more text counts as a required answer left until the text is there
 15 conflict     a KPI name that another module holds and defines makes the Domain Owner's second signature count,
                 once the KPI has a definition of its own; a name whose term has no definition does not
 16 bad draft    a browser draft with a malformed form, a missing form or a missing field is not restored, in
                 whole, and the form still works
 17 hidden       an entry that settings.toml hides is not offered; a loaded file that holds one shows it, marked,
                 and saves it again
 18 added        an entry that settings.toml adds is offered, marked new; choosing it shows a notice that does not
                 route the request, and the check of the saved file tells the Architect to add it to the ontology
 19 new fields   the status starts at Draft, also after "Clear this form"; the effective date is asked only when a
                 threshold is given; the objective, the grain, the owner and the steward count as required
 20 guide        "How to use this form" links to the guide beside the form, which opens with no network request
 21 alias        an answer saved under an added entry that the ontology has since gained is read as the ontology's
                 entry, from a file and from a draft; the entry is offered once, and the form says what it did
 22 term change  the Term change form asks for the Ontology Owner's signature only when T8 is "no" or "not sure",
                 and saves its file under the measure's name with the measure's id as the answer to T1

Every expected value below is written by hand from the catalogue and the release packages. The script exits 1
when a proof fails and names it. scripts/check.sh does not run it, because it needs a browser.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "kpi-intake" / "kpi-intake-form.html"
GUIDE = "how-to-use-the-form.html"
BLACK_OIL = "https://w3id.org/mpc/ontology/modules/organization/role/black-oil-manager"
NEW_ROLE = "new:value-chain-optimization-director"
EXAMPLE = ROOT / "kpi-intake" / "examples" / "crack-spreads-pricing.json"
COMMERCIAL = "https://w3id.org/mpc/ontology/modules/core/business-domain/commercial"
REFINERY_OPTIMIZATION = "https://w3id.org/mpc/ontology/process/CM-1-1-4-7"
UNIT_UTILIZATION = "https://w3id.org/mpc/ontology/modules/kpi/measure/unit-utilization"
PRICE_STEP = "https://w3id.org/mpc/ontology/process/CM-1-1-4-7-4"


def same(found, expected, what):
    assert found == expected, f"{what}: found {str(found)[:200]!r}, expected {str(expected)[:200]!r}"


def holds(text, part, what):
    assert part in text, f"{what}: {part!r} is not in {text[:300]!r}"


class Session:
    """The form under test: a fresh load for each proof, with every console error and network request counted."""

    def __init__(self, browser, path, shots):
        self.browser, self.url, self.shots = browser, Path(path).resolve().as_uri(), shots
        self.errors, self.requests = [], []

    def open(self, width=1280, height=900, scheme="light"):
        context = self.browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True, color_scheme=scheme)
        # Anything that is not the file itself or data inside it would leave the machine: stop it and count it.
        context.route(lambda url: not url.startswith(("file:", "data:", "blob:", "about:")), self._refuse)
        page = context.new_page()
        page.set_default_timeout(10_000)
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("console", lambda message: message.type == "error" and self.errors.append(message.text))
        page.on("request", lambda request: request.url.startswith("file:") and request.url != self.url and self.requests.append(request.url))
        page.goto(self.url)
        return page

    def _refuse(self, route):
        self.requests.append(route.request.url)
        route.abort()

    def shot(self, page, name):
        if self.shots:
            page.screenshot(path=str(self.shots / f"intake-{name}.png"), full_page=True)


def card(page, question):
    return page.locator(f'[data-question="{question}"]')


def choose(page, question, value):
    """Tick the option of a question that has this id. A long list is searched first, as a person would."""
    box = card(page, question)
    option = box.locator(f'.picker-list input[value="{value}"]')
    if option.count() == 0:
        box.locator(".picker-search").fill(value.rsplit("/", 1)[-1].replace("CM-", "CM ").replace("-", "."))
    option.check()


def load(s):
    page = s.open()
    same(page.locator("h1").inner_text(), "KPI intake form", "the page's heading")
    holds(page.locator("#release-line").text_content(), "KPI Store 1.1, catalogue 1.2", "the release line")
    same(page.locator("#tabs [role=tab]").all_inner_texts(),
         ["KPI intake", "Domain activation", "Process map request", "Term change", "The roles", "What we will ask you"], "the tabs")
    same(page.locator("[data-section]").count(), 7, "sections of the KPI form")
    same(page.locator("[data-question]").count(), 56, "questions of the KPI form")
    holds(page.locator(".brand-line").inner_text(), "Works offline. Sends nothing.", "the line under the name")
    same(page.locator("#save").inner_text(), "Save answers to file", "the save button")
    same(page.locator("#load").inner_text(), "Load answers file", "the load button")
    assert page.locator('[data-part="request-details"]').get_attribute("open") is not None, "the empty request details are closed"
    assert card(page, "1.1").is_visible(), "the first question is not on the page"
    same(card(page, "1.5").locator(".q-asked").inner_text(), "The Domain Owner of the proposed domain.", "who answers 1.5")
    holds(card(page, "1.5").locator(".q-asked-more").inner_text(), "The Program manager proposes", "the coordination line of 1.5")
    s.shot(page, "1-load")


def fill(s):
    page = s.open()
    holds(page.locator('[data-section="2"] .section-progress').inner_text(), "3 required answers left · 2 optional unanswered", "section 2 before")
    card(page, "2.1").locator("input").fill("Tank Turnover")
    card(page, "2.2").locator("textarea").fill("How many times the stored volume is replaced in a month.")
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "1 required answer left · 2 optional unanswered", "section 2 after")
    card(page, "2.5").locator("textarea").fill("Never run a terminal out of product.")
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "Required answers complete · 2 optional unanswered", "section 2 with its objective")
    choose(page, "3.7", "anyone")
    holds(page.locator('[data-nav="3"] .nav-count').inner_text(), "5 required answers left", "the section list")
    card(page, "2.1").locator("input").fill("crack spread")
    holds(card(page, "2.1").locator('[data-notice="same-measure"]').inner_text(), '"Crack Spreads Pricing" has this name', "the notice for a name the ontology holds")
    s.shot(page, "2-fill")


def narrow_list(s):
    page = s.open()
    # 71 processes at levels 1 to 3; the page shows 40 at once and says how many more there are.
    same(card(page, "1.2").locator(".picker-more").inner_text(), "31 more. Type to narrow the list.", "the process list before an area is chosen")
    choose(page, "1.1", COMMERCIAL)
    same(card(page, "1.2").locator('.picker-list input[type=radio]').count(), 21, "processes offered for Commercial (20 and Not in the list)")
    choose(page, "1.2", REFINERY_OPTIMIZATION)
    same(card(page, "1.3").locator('.picker-list input[type=radio]').count(), 9, "steps under Refinery Optimization (8 and The step is missing)")
    choose(page, "1.3", PRICE_STEP)
    holds(card(page, "1.3").locator(".picker-chosen").inner_text(), "CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price", "the chosen step")
    s.shot(page, "3-narrow")


def conditional(s):
    page = s.open()
    assert card(page, "4.2").is_hidden(), "4.2 shows before 4.1 is answered"
    assert card(page, "3.1").is_visible(), "3.1 is hidden before 4.1 is answered"
    choose(page, "4.1", "yes")
    assert card(page, "4.2").is_visible(), "4.2 stays hidden after 4.1 is yes"
    choose(page, "4.2", "no")
    choose(page, "4.3", "yes")
    holds(page.locator('[data-section="4"] [data-part="kind"]').inner_text(), "Kind of measure: market indicator (decided by 4.3)", "the kind")
    assert card(page, "4.4").is_hidden(), "4.4 shows although 4.3 decided the kind"
    assert card(page, "6.7").is_visible(), "6.7 is hidden for a market indicator"
    choose(page, "4.1", "no")
    for hidden in ("4.2", "4.3", "3.1", "3.2", "3.3", "3.8", "6.7"):
        assert card(page, hidden).is_hidden(), f"{hidden} shows although 4.1 is no"
    holds(page.locator('[data-section="3"] .section-skipped').inner_text(), "5 questions do not apply", "the skipped line of section 3")
    s.shot(page, "4-conditional")


def routing(s):
    page = s.open()
    choose(page, "1.5", "customer")
    note = card(page, "1.5").locator('[data-notice="domain-activation"]')
    holds(note.inner_text(), "Domain activation required before this KPI can be added", "the notice for a domain that is not active")
    holds(page.locator('[data-section="1"] .section-progress').inner_text(), "Routed: domain activation", "section 1 with an inactive domain")
    same(page.locator('[data-nav="1"] .nav-count').inner_text(), "Routed: domain activation", "the section list with an inactive domain")
    choose(page, "1.5", "market-price")
    same(card(page, "1.5").locator("[data-notice]").count(), 0, "notices for an active domain")
    choose(page, "1.2", "@not-in-list")
    holds(card(page, "1.2").locator('[data-notice="process-map-request"]').inner_text(), "Process map request required before this KPI can be added", "the notice for a missing process")
    assert card(page, "1.2").locator(".q-detail").is_visible(), "the missing process's name is not asked for"
    choose(page, "3.7", "restricted")
    holds(card(page, "3.7").locator('[data-notice="restricted-review"]').inner_text(), "Privacy, Security, Compliance and Risk", "the notice for a restricted KPI")
    same(card(page, "3.7").locator(".notice-reviewers li").all_inner_texts(), ["Privacy", "Security", "Compliance", "Risk"], "the reviewers of a restricted KPI")
    s.shot(page, "5-routing")


def save(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    choose(page, "4.1", "yes")
    choose(page, "4.2", "yes")
    card(page, "5.1").locator("textarea").fill("turns\nstock turn")
    page.locator('[data-signer="data-owner"] [data-sign="name"]').fill("A name")
    page.locator('[data-signer="data-owner"] [data-sign="date"]').fill("2026-11-11")
    with page.expect_download() as download:
        page.locator("#save").click()
    same(download.value.suggested_filename, "tank-turnover.kpi-intake.json", "the file's name")
    data = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    same(data["format"], 1, "format")
    same(data["form"], "kpi-intake", "form")
    same(data["catalogue_version"], "1.2", "catalogue version")
    same(data["kpi_name"], "Tank Turnover", "KPI name")
    same(data["answers"], {"2.1": "Tank Turnover", "3.9": "draft", "4.1": "yes", "4.2": "yes", "5.1": ["turns", "stock turn"]}, "answers")
    same(data["sign_offs"], {"data-owner": {"name": "A name", "date": "2026-11-11"}}, "sign-offs")
    # The form asked the browser for a download. It cannot know that the file was kept, and does not say so.
    same(page.locator("#status").inner_text(), "Download requested: tank-turnover.kpi-intake.json. Check that the file appears in your chosen folder.", "the status line")


def load_file(s):
    page = s.open()
    page.locator("#load-file").set_input_files(str(EXAMPLE))
    holds(page.locator("#status").inner_text(), "Loaded crack-spreads-pricing.json", "the status line")
    same(card(page, "2.1").locator("input").input_value(), "Crack Spreads Pricing", "2.1")
    assert card(page, "1.1").locator(f'input[value="{COMMERCIAL}"]').is_checked(), "1.1 is not Commercial"
    assert card(page, "1.5").locator('input[value="market-price"]').is_checked(), "1.5 is not Market Price"
    holds(card(page, "1.3").locator(".picker-chosen").inner_text(), "CM 1.1.4.7.4 Capture Product/Crude/Feedstock Price", "1.3")
    same(card(page, "6.4").locator("select").count(), 2, "relationship rows, one for each of the two value stream steps")
    holds(card(page, "6.4").locator(".per-row label").first.inner_text(), "Market Price Calculation & Validation", "the first step's row")
    same(page.locator('[data-signer="architect"] [data-sign="date"]').input_value(), "2026-11-11", "the Architect's date")
    holds(page.locator('[data-part="example-mark"]').inner_text(), "shipped example", "the example mark")
    same(card(page, "2.1").locator("[data-notice]").count(), 0, "notices on the example's own name")
    assert page.locator('[data-part="request-details"]').get_attribute("open") is None, "the filled request details stay open"
    holds(page.locator('[data-part="request-summary"]').inner_text(), "EXAMPLE-1", "the one line of the request details")
    # Four signers, one of them only for a conflict: three are needed and all three have signed.
    same(page.locator('[data-nav="signoff"] .nav-count').inner_text(), "3 of 3 required signed", "the sign-off line")
    same(page.locator('[data-part="signoff-progress"]').inner_text(), "3 of 3 required signatures recorded · conflict review pending check", "the sign-off count")
    same(page.locator('[data-signer="domain-confirmation"] .signer-label').inner_text(), "Domain confirmation", "the first Domain Owner block")
    same(page.locator('[data-signer="domain-owner"] .signer-label').inner_text(), "Conflicting definitions", "the second Domain Owner block")
    same(page.locator('[data-signer="domain-owner"] .signer-status').inner_text(), "Only if the check finds a conflicting definition", "the conflict signature")
    same(page.locator('[data-section="1"] .section-progress').inner_text(), "Required answers complete · 1 optional unanswered", "section 1 of the example")
    with page.expect_download() as download:
        page.locator("#save").click()
    saved = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    same(saved, json.loads(EXAMPLE.read_text(encoding="utf-8")), "the example saved again")
    s.shot(page, "7-load")


def draft(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    choose(page, "1.5", "market-price")
    page.reload()
    same(card(page, "2.1").locator("input").input_value(), "Tank Turnover", "2.1 after a reload")
    assert card(page, "1.5").locator('input[value="market-price"]').is_checked(), "1.5 after a reload"
    holds(page.locator("#status").inner_text(), "draft was restored", "the status line")
    page.locator("#clear").click()
    assert page.locator("#clear-dialog").is_visible(), "Clear this form does not ask first"
    page.locator("#clear-cancel").click()
    same(card(page, "2.1").locator("input").input_value(), "Tank Turnover", "2.1 after Cancel")
    page.locator("#clear").click()
    page.locator("#clear-confirm").click()
    same(card(page, "2.1").locator("input").input_value(), "", "2.1 after Clear")
    assert page.locator("#clear-dialog").is_hidden(), "the question stays after Clear"


def phone(s):
    page = s.open(width=390, height=844)
    page.locator("#load-file").set_input_files(str(EXAMPLE))
    card(page, "7.1").scroll_into_view_if_needed()
    assert page.locator("#tabs").is_hidden(), "the row of tabs shows at 390 px"
    for name in ("view-select", "sections-toggle", "save", "load", "clear"):
        height = page.locator(f"#{name}").bounding_box()["height"]
        assert height >= 44, f"#{name} is {height} px high, under 44"
    # The Sections button names the section in view, and opens the list with the sign-off line at its end.
    page.wait_for_function("document.getElementById('sections-now').textContent.startsWith('7. Where the data lives')")
    assert page.locator("#contents").is_hidden(), "the section list shows before the Sections button is pressed"
    page.locator("#sections-toggle").click()
    assert page.locator("#contents").is_visible(), "the Sections button does not open the section list"
    same(page.locator("#contents-list [data-nav]").count(), 8, "lines of the section list: seven sections and the sign-off")
    page.locator('#contents-list [data-nav="3"]').click()
    assert page.locator("#contents").is_hidden(), "the section list stays open after a choice"
    page.wait_for_function("document.getElementById('sections-now').textContent.startsWith('3. The facts about it')")
    assert page.evaluate("parseFloat(getComputedStyle(document.body).paddingBottom) >= document.getElementById('dock').offsetHeight - 1"), "the page does not clear the bar of file buttons"
    for tab in ("kpi-intake", "domain-activation", "process-map-request", "term-change", "roles", "explainer"):
        page.locator("#view-select").select_option(tab)
        same(page.locator(f'[data-view="{tab}"]').get_attribute("aria-selected"), "true", f"the view after choosing {tab}")
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), f"the {tab} view scrolls sideways at 390 px"
    s.shot(page, "9-phone")


def theme(s):
    page = s.open(scheme="dark")
    same(page.locator("html").get_attribute("data-theme"), "light", "the theme of a fresh visit on a dark system")
    same(page.locator("#theme").input_value(), "light", "the selector of a fresh visit")
    page.locator("#theme").select_option("dark")
    same(page.locator("html").get_attribute("data-theme"), "dark", "the theme after choosing Dark")
    page.reload()
    same(page.locator("#theme").input_value(), "dark", "the selector after a reload")
    same(page.locator("html").get_attribute("data-theme"), "dark", "the theme after a reload")
    page.locator("#theme").select_option("system")
    same(page.locator("html").get_attribute("data-theme"), "dark", "the System theme on a dark system")
    page.emulate_media(color_scheme="light")
    page.wait_for_function("document.documentElement.dataset.theme === 'light'")   # the System theme follows the system
    s.shot(page, "10-theme")


def next_step(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    choose(page, "1.5", "customer")
    note = card(page, "1.5").locator('[data-notice="domain-activation"]')
    holds(note.locator(".notice-who").inner_text(), "The Domain Owner answers and signs.", "who does a domain activation")
    assert "settings.toml" not in note.inner_text(), "the notice shows settings.toml to the business"
    holds(note.locator(".notice-analyst p").text_content(), "settings.toml", "the line for the analyst")
    button = note.locator(".notice-open")
    same(button.inner_text(), "Open the domain activation form", "the button of the notice")
    assert button.bounding_box()["height"] >= 44, "the button of the notice is under 44 px high"
    button.focus()
    page.keyboard.press("Enter")
    same(page.locator('[data-view="domain-activation"]').get_attribute("aria-selected"), "true", "the view after the button")
    assert page.locator('[data-question="D1"]').is_visible(), "the domain activation form is not shown"
    page.locator('[data-view="kpi-intake"]').click()
    same(card(page, "2.1").locator("input").input_value(), "Tank Turnover", "2.1 after coming back")
    choose(page, "1.2", "@not-in-list")
    card(page, "1.2").locator(".notice-open").click()
    same(page.locator('[data-view="process-map-request"]').get_attribute("aria-selected"), "true", "the view after the second button")
    s.shot(page, "11-next-step")


def bad_file(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    refused = "This file is not a KPI intake answers file: "

    def offer(text):
        page.locator("#load-file").set_input_files({"name": "offered.json", "mimeType": "application/json", "buffer": text.encode("utf-8")})

    for text, what in (
        ('{"format":1,"form":"kpi-intake","answers":{"2.1":{"toString":"x"}}}', "the answer to 2.1 is neither a text nor a list of texts."),
        ("not json at all", "it is not JSON."),
        ("[1, 2]", "it is not a JSON object."),
        ('{"format":2,"form":"kpi-intake","answers":{}}', 'its "format" is not 1.'),
        ('{"format":1,"form":"something-else","answers":{}}', 'its "form" names none of the four forms.'),
        ('{"format":1,"form":"kpi-intake","answers":["2.1"]}', 'it has no "answers" object.'),
        ('{"format":1,"form":"kpi-intake","answers":{"5.1":["a",3]}}', "the answer to 5.1 is neither a text nor a list of texts."),
        ('{"format":1,"form":"kpi-intake","answers":{},"comment":{"a":1}}', '"comment" is not a text.'),
        ('{"format":1,"form":"kpi-intake","answers":{},"request":{"number":7}}', '"request" does not hold a text for each field.'),
        ('{"format":1,"form":"kpi-intake","answers":{},"sign_offs":{"data-owner":"A name"}}', '"sign_offs" does not hold texts for each entry.'),
    ):
        offer(text)
        page.wait_for_function("text => document.getElementById('status').textContent === text", arg=refused + what)
        same(card(page, "2.1").locator("input").input_value(), "Tank Turnover", f"2.1 after the refused file ({what})")
    # The form still works after the refusals.
    card(page, "2.2").locator("textarea").fill("How many times the stored volume is replaced in a month.")
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "1 required answer left · 2 optional unanswered", "section 2 after the refusals")
    # A good file may hold markup in an answer. The form shows it as the text it is.
    offer('{"format":1,"form":"kpi-intake","answers":{"2.1":"<img src=x onerror=alert(1)><b>bold</b>","5.1":["<i>x</i>"]},"request":{"number":"<u>7</u>"}}')
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Loaded offered.json')")
    same(card(page, "2.1").locator("input").input_value(), "<img src=x onerror=alert(1)><b>bold</b>", "2.1 from the file with markup")
    same(page.locator("#view img, #view b, #view i, #view u").count(), 0, "elements made from the file's text")
    holds(page.locator('[data-part="request-summary"]').text_content(), "<u>7</u>", "the request line from the file with markup")
    s.shot(page, "12-bad-file")


def other_form(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    page.locator("#load-file").set_input_files({"name": "logistics.domain-activation.json", "mimeType": "application/json",
                                                "buffer": b'{"format":1,"form":"domain-activation","answers":{"D1":"Logistics","2.1":"A stray answer"}}'})
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Loaded')")
    same(page.locator("#status").inner_text(),
         "Loaded logistics.domain-activation.json into the Domain activation form. Left out 1 answer that this form does not ask: 2.1.", "the status line")
    same(page.locator('[data-view="domain-activation"]').get_attribute("aria-selected"), "true", "the view after the load")
    same(card(page, "D1").locator("input").input_value(), "Logistics", "D1")
    page.locator('[data-view="kpi-intake"]').click()
    same(card(page, "2.1").locator("input").input_value(), "Tank Turnover", "2.1 of the KPI form after the load")
    s.shot(page, "13-other-form")


def detail(s):
    page = s.open()
    progress = page.locator('[data-section="1"] .section-progress')
    same(progress.inner_text(), "4 required answers left · 2 optional unanswered", "section 1 before")
    # 1.3 is optional. "The step is missing" makes its extra text required, as the check has it.
    choose(page, "1.3", "@not-in-list")
    same(progress.inner_text(), "Routed: process map request · 5 required answers left · 1 optional unanswered", "section 1 with the step's name missing")
    assert card(page, "1.3").locator(".q-detail-need").is_visible(), "1.3 does not say that its extra text is required"
    choose(page, "1.1", COMMERCIAL)
    choose(page, "1.2", REFINERY_OPTIMIZATION)
    card(page, "1.4").locator("textarea").fill("Planners read the number before they set the refinery plan.")
    choose(page, "1.5", "market-price")
    same(progress.inner_text(), "Routed: process map request · 1 required answer left · 1 optional unanswered", "section 1 with only the step's name missing")
    same(page.locator('[data-nav="1"] progress').get_attribute("value"), "4", "the bar of section 1 with one of five left")
    card(page, "1.3").locator(".q-detail input").fill("Check the posted price")
    same(progress.inner_text(), "Routed: process map request · 1 optional unanswered", "section 1 with the step's name given")
    # 4.6 is required, and "yes" makes its extra text required: the same count covers it.
    for question, answer in (("4.1", "yes"), ("4.2", "no"), ("4.3", "no"), ("4.4", "no"), ("4.5", "no"), ("4.6", "yes")):
        choose(page, question, answer)
    card(page, "4.8").locator("textarea").fill("The business named it as a measure of a stated objective.")
    four = page.locator('[data-section="4"] .section-progress')
    same(four.inner_text(), "1 required answer left · 1 optional unanswered", "section 4 without the document of 4.6")
    card(page, "4.6").locator(".q-detail input").fill("The 2026 objectives paper")
    same(four.inner_text(), "Required answers complete · 1 optional unanswered", "section 4 with the document of 4.6")
    s.shot(page, "14-detail")


def conflict(s):
    page = s.open()
    line = page.locator('[data-nav="signoff"]')
    status = page.locator('[data-signer="domain-owner"] .signer-status')

    def sign(signer):
        page.locator(f'[data-signer="{signer}"] [data-sign="name"]').fill("A name")
        page.locator(f'[data-signer="{signer}"] [data-sign="date"]').fill("2026-11-12")

    card(page, "2.1").locator("input").fill("Tank Turnover")
    for signer in ("data-owner", "domain-confirmation", "architect"):
        sign(signer)
    same(line.locator(".nav-count").inner_text(), "3 of 3 required signed", "the sign-off line for a new name")
    same(status.inner_text(), "Only if the check finds a conflicting definition", "the conflict signature for a new name")
    # "Margin Management" is a process of the core module, so the check will ask Enterprise Data Governance, and
    # the Domain Owner must sign if the two definitions differ.
    card(page, "2.1").locator("input").fill("margin management")
    holds(card(page, "2.1").locator('[data-notice="same-name"]').inner_text(), "Enterprise Data Governance", "the notice before the KPI has a definition")
    # The check finds a conflict only when both definitions are there and differ. Without an answer to 2.2 it cannot.
    same(line.locator(".nav-count").inner_text(), "3 of 3 required signed", "the sign-off line before the KPI has a definition")
    same(status.inner_text(), "Only if the check finds a conflicting definition", "the conflict signature before the KPI has a definition")
    card(page, "2.2").locator("textarea").fill("How many times the stored volume is replaced in a month.")
    same(status.inner_text(), "Needed if the check confirms: the name exists in the core module", "the conflict signature for a name of another module")
    same(line.locator(".nav-count").inner_text(), "3 of 4 required signed", "the sign-off line for a name of another module")
    same(line.get_attribute("data-state"), "open", "the state of the sign-off line")
    holds(page.locator('[data-part="signoff-progress"]').inner_text(), "3 of 4 required signatures recorded", "the sign-off count")
    holds(card(page, "2.1").locator('[data-notice="same-name"]').inner_text(), "Enterprise Data Governance", "the notice for a name of another module")
    sign("domain-owner")
    same(line.locator(".nav-count").inner_text(), "4 of 4 required signed", "the sign-off line with the conflict signature")
    with page.expect_download() as download:
        page.locator("#save").click()
    saved = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    same(saved["sign_offs"]["domain-owner"], {"name": "A name", "date": "2026-11-12"}, "the conflict signature in the saved file")
    # "Process Business Renewal Request" is a term with no definition, so the check can find no conflict with it.
    page.locator('[data-signer="domain-owner"] [data-sign="name"]').fill("")
    card(page, "2.1").locator("input").fill("Process Business Renewal Request")
    holds(card(page, "2.1").locator('[data-notice="same-name"]').inner_text(), "Enterprise Data Governance", "the notice for a term with no definition")
    same(line.locator(".nav-count").inner_text(), "3 of 3 required signed", "the sign-off line for a term with no definition")
    same(status.inner_text(), "Only if the check finds a conflicting definition", "the conflict signature for a term with no definition")
    s.shot(page, "15-conflict")


def bad_draft(s):
    page = s.open()
    good = {"answers": {"2.1": "Tank Turnover"}, "request": {}, "sign_offs": {}, "consulted": {}, "example_of": "", "comment": ""}
    empty = dict(good, answers={})
    forms = ("kpi-intake", "domain-activation", "process-map-request", "term-change")

    def seeded(**changed):
        state = {form: empty for form in forms}
        state["kpi-intake"] = good
        for form, held in changed.items():
            if held is None:
                del state[form.replace("_", "-")]
            else:
                state[form.replace("_", "-")] = held
        return json.dumps({"state": state, "view": "domain-activation"})

    for what, seed in (
        ("a malformed form", seeded(domain_activation=dict(empty, answers={"D1": {"toString": "x"}}))),
        ("a missing form", seeded(process_map_request=None)),
        ("a form with a missing field", seeded(domain_activation={k: v for k, v in empty.items() if k != "comment"})),
        ("a field of the wrong type", seeded(domain_activation=dict(empty, sign_offs=[]))),
    ):
        page.evaluate("text => localStorage.setItem('kpi-intake-draft-1', text)", seed)
        page.reload()
        same(page.locator("#status").inner_text(), "The browser draft could not be read and was not restored.", f"the status line for {what}")
        same(page.locator('[data-view="kpi-intake"]').get_attribute("aria-selected"), "true", f"the view after {what}")
        same(card(page, "2.1").locator("input").input_value(), "", f"2.1 after {what}")
    # A whole draft is restored, with its view.
    page.evaluate("text => localStorage.setItem('kpi-intake-draft-1', text)", seeded())
    page.reload()
    holds(page.locator("#status").inner_text(), "draft was restored", "the status line for a whole draft")
    same(page.locator('[data-view="domain-activation"]').get_attribute("aria-selected"), "true", "the view of a whole draft")
    # After a refused draft the form works, and its own draft is kept.
    page.evaluate("text => localStorage.setItem('kpi-intake-draft-1', text)", seeded(process_map_request=None))
    page.reload()
    card(page, "2.1").locator("input").fill("Days of Cover")
    holds(page.locator('[data-section="2"] .section-progress').inner_text(), "2 required answers left", "section 2 after the refused draft")
    page.reload()
    same(card(page, "2.1").locator("input").input_value(), "Days of Cover", "2.1 from the new draft")
    s.shot(page, "16-bad-draft")


def search(page, question, text):
    box = card(page, question)
    box.locator(".picker-search").fill(text)
    return box


def hidden(s):
    page = s.open()
    # Black Oil Manager is a role of the ontology that settings.toml hides. The list has 64 roles and the new one.
    box = search(page, "6.1", "Black Oil")
    same(box.locator(f'.picker-list input[value="{BLACK_OIL}"]').count(), 0, "the hidden role among the options")
    same(box.locator(".picker-more").inner_text(), "Nothing in the list matches.", "the list searched for the hidden role")
    box = search(page, "6.1", "Asphalt")
    same(box.locator(".picker-list .option-label").first.inner_text(), "Asphalt Manager", "a role the settings leave")
    # The sources: four documents under plain labels, and the document that is not in the list.
    same(card(page, "3.5").locator(".picker-list .option-label").all_inner_texts(), [
        "Marathon Petroleum Corporation, Form 10-K for the fiscal year ended 2025-12-31",
        "MPC Economics, 3-2-1 Crack Spread KPI Definition",
        "MPLX LP, Form 10-K for the fiscal year ended 2025-12-31",
        "Value Chain Optimization Decision Support and Visualization: the planning team's measure list",
        "A document that is not in the list"], "documents offered in 3.5")
    # The data products: 13, then "None yet" and "Not in the list".
    same(card(page, "6.6").locator(".picker-list input").count(), 15, "options of 6.6")
    assert "HR" not in card(page, "6.6").locator(".picker-list .option-label").all_inner_texts(), "a functional area is offered in 6.6"
    # The systems show when the view is new: 44 of the ontology and SharePoint. Databricks and the office tools are hidden.
    choose(page, "7.1", "@not-in-list")
    for office in ("MS Excel", "MS Outlook", "MS PowerPoint", "MS Teams"):
        same(search(page, "7.4", office).locator(".picker-more").inner_text(), "Nothing in the list matches.", f"the list searched for {office}")
    same(search(page, "7.4", "Databricks").locator(".picker-more").inner_text(), "Nothing in the list matches.", "the list searched for Databricks")
    same(search(page, "7.4", "MIPS").locator(".picker-list .option-label").all_inner_texts(), ["MIPS"], "a source system the settings leave")
    # A file saved before the role was hidden still loads. The form shows the role, marked, and saves it again.
    older = {"format": 1, "form": "kpi-intake", "answers": {"2.1": "Tank Turnover", "6.1": [BLACK_OIL]}}
    page.locator("#load-file").set_input_files({"name": "older.kpi-intake.json", "mimeType": "application/json", "buffer": json.dumps(older).encode("utf-8")})
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Loaded older.kpi-intake.json')")
    same(card(page, "6.1").locator(".picker-chosen .chosen-label").all_inner_texts(), ["Black Oil Manager (hidden in this organization's settings)"], "the hidden role a file holds")
    with page.expect_download() as download:
        page.locator("#save").click()
    again = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))["answers"]
    same(again["6.1"], [BLACK_OIL], "the hidden role saved again")
    # The file has no status. The default belongs to a new form and is never put into a loaded one.
    same(card(page, "3.9").locator(".picker-list input:checked").count(), 0, "a status chosen in a loaded file that has none")
    same(again, older["answers"], "the answers of the older file saved again, with no status added")
    card(page, "6.1").locator(".picker-chosen button").click()
    same(search(page, "6.1", "Black Oil").locator(".picker-more").inner_text(), "Nothing in the list matches.", "the hidden role after it was removed")
    s.shot(page, "17-hidden")


def added(s):
    page = s.open()
    card(page, "2.1").locator("input").fill("Tank Turnover")
    box = search(page, "6.1", "Value Chain Optimization D")
    option = box.locator(f'.picker-list input[value="{NEW_ROLE}"]')
    same(box.locator(".picker-list .option-label").all_inner_texts(), ["Value Chain Optimization Director (new, not yet in the ontology)", "A role that is not in the list"], "the added role, and the option that stays")
    option.check()
    note = card(page, "6.1").locator('[data-notice="to-add"]')
    same(note.locator(".notice-title").inner_text(), "You can continue with this entry", "the notice's title")
    same(note.locator(".notice-text").inner_text(), '"Value Chain Optimization Director" is available in this form but is not yet in the ontology. '
         "Continue filling in the KPI. The Architect must add this entry before adding the KPI.", "the notice")
    # The notice fades in. Once it has arrived it is as readable as the form's other text.
    page.wait_for_function("getComputedStyle(document.querySelector('[data-notice=\"to-add\"]')).opacity === '1' && document.querySelector('[data-notice=\"to-add\"]').getAnimations().length === 0")
    assert "HOW-TO-UPDATE.md" not in note.locator(".notice-text").inner_text(), "the notice shows HOW-TO-UPDATE.md to the business"
    holds(note.locator(".notice-analyst p").text_content(), "to the organization module with HOW-TO-UPDATE.md", "the line for the analyst")
    same(card(page, "6.1").locator('[data-notice="process-map-request"]').count(), 0, "a process map request for the added role")
    assert "Routed" not in page.locator('[data-section="6"] .section-progress').inner_text(), "the added role routes the request"
    # SharePoint is the system the settings add.
    choose(page, "7.1", "@not-in-list")
    box = search(page, "7.4", "SharePoint")
    same(box.locator(".picker-list .option-label").all_inner_texts(), ["SharePoint (new, not yet in the ontology)"], "the added system")
    box.locator('.picker-list input[value="new:sharepoint"]').check()
    holds(card(page, "7.4").locator('[data-notice="to-add"] .notice-analyst p').text_content(), "to the system module with HOW-TO-UPDATE.md", "the line for the analyst on 7.4")
    # The check of the saved file tells the Architect, and does not ask for a process map request.
    with page.expect_download() as download:
        page.locator("#save").click()
    saved = Path(download.value.path())
    same(json.loads(saved.read_text(encoding="utf-8"))["answers"]["6.1"], [NEW_ROLE], "the added role in the saved file")
    target = saved.with_name("tank-turnover.kpi-intake.json")
    target.write_bytes(saved.read_bytes())
    done = subprocess.run([sys.executable, "-m", "kpi_store.intake", "check", str(target)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    same(done.returncode, 1, "the exit status of the check of a form that is not complete yet")
    holds(done.stdout, 'To add to the ontology first\n  For the Architect: 6.1 names "Value Chain Optimization Director". The organization\'s settings added it, '
          "and the ontology does not hold it yet. Add it to the organization module with HOW-TO-UPDATE.md before you apply this KPI.", "the check's message for the role")
    holds(done.stdout, '  For the Architect: 7.4 names "SharePoint".', "the check's message for the system")
    assert "6.1 routes the request" not in done.stdout and "Not in the ontology" not in done.stdout, "the check refuses or routes the added entries"
    s.shot(page, "18-added")


def new_fields(s):
    page = s.open()
    three = page.locator('[data-section="3"] .section-progress')
    assert card(page, "3.9").locator('input[value="draft"]').is_checked(), "the status does not start at Draft"
    same(card(page, "3.9").locator(".picker-list .option-label").all_inner_texts(), ["Draft", "Certified", "Retired"], "the statuses")
    # Seven required questions, one of them answered by its default; five optional ones.
    same(three.inner_text(), "6 required answers left · 5 optional unanswered", "section 3 of a new form")
    same(card(page, "3.8").locator(".q-rule").inner_text(), 'Required if 4.1 is not "no"', "the rule of the grain")
    for optional in ("3.10", "3.11", "3.12"):
        same(card(page, optional).locator(".q-rule").inner_text(), "Optional", f"the rule of {optional}")
    # The effective date is asked only when a threshold is given, and is then required.
    assert card(page, "3.13").is_hidden(), "3.13 shows before a threshold is given"
    card(page, "3.12").locator("textarea").fill("Low: under 5 days of cover")
    assert card(page, "3.13").is_visible(), "3.13 stays hidden after a threshold is given"
    same(three.inner_text(), "7 required answers left · 4 optional unanswered", "section 3 with a threshold and no date")
    card(page, "3.13").locator("input").fill("From 2026-01-01")
    card(page, "3.8").locator("input").fill("One value for each day and each terminal.")
    same(three.inner_text(), "5 required answers left · 4 optional unanswered", "section 3 with the grain and the date")
    # The owner and the steward are required; the objective too (proof 2). The API is optional.
    six = page.locator('[data-section="6"] .section-progress')
    same(six.inner_text(), "3 required answers left · 3 optional unanswered", "section 6 of a new form")
    card(page, "6.8").locator("input").fill("Supply Operations Manager")
    card(page, "6.9").locator("input").fill("Inventory Representative")
    same(six.inner_text(), "1 required answer left · 3 optional unanswered", "section 6 with the owner and the steward")
    same(page.locator('[data-section="7"] .section-progress').inner_text(), "1 required answer left · 3 optional unanswered", "section 7 of a new form")
    same(card(page, "7.10").locator(".q-rule").inner_text(), "Optional", "the rule of the API question")
    same(card(page, "7.8").locator(".q-text").inner_text(), "Which AI assistant or report answers from this view?", "question 7.8")
    # What a reader must know is under the answer, in sight, and not under "For the analyst".
    same(card(page, "3.9").locator(".q-help").inner_text(), "The form does not change this status when someone signs.", "the help of 3.9")
    assert card(page, "6.8").locator(".q-help").is_visible() and card(page, "6.8").locator(".q-analyst").is_hidden(), "the note on names is not in sight under 6.8"
    assert card(page, "2.1").locator(".q-help").is_hidden(), "a question with no help shows an empty line"
    same(card(page, "2.5").locator(".q-rule").inner_text(), "Required", "the rule of the objective")
    with page.expect_download() as download:
        page.locator("#save").click()
    same(json.loads(Path(download.value.path()).read_text(encoding="utf-8"))["answers"],
         {"3.8": "One value for each day and each terminal.", "3.9": "draft", "3.12": ["Low: under 5 days of cover"], "3.13": "From 2026-01-01",
          "6.8": "Supply Operations Manager", "6.9": "Inventory Representative"}, "the saved answers")
    # "Clear this form" empties the form and puts the status back at Draft.
    choose(page, "3.9", "certified")
    page.locator("#clear").click()
    page.locator("#clear-confirm").click()
    assert card(page, "3.9").locator('input[value="draft"]').is_checked(), "the status after Clear is not Draft"
    same(card(page, "6.8").locator("input").input_value(), "", "6.8 after Clear")
    s.shot(page, "19-new-fields")


def guide(s):
    page = s.open()
    link = page.locator("#guide-link")
    same(link.inner_text(), "How to use this form", "the link's words")
    same(link.get_attribute("href"), GUIDE, "the link's address, beside the form")
    same(link.get_attribute("target"), "_blank", "the link opens beside the form, so the answers stay")
    target = Path(s.url.removeprefix("file://")).parent / GUIDE if not sys.platform.startswith("win") else None
    guide_url = s.url.rsplit("/", 1)[0] + "/" + GUIDE
    # The guide is its own page: open it apart, count what it asks the network for, and read its heading.
    context = s.browser.new_context(viewport={"width": 1280, "height": 900})
    asked, errors = [], []
    context.route(lambda url: not url.startswith(("file:", "data:", "blob:", "about:")), lambda route: (asked.append(route.request.url), route.abort()))
    other = context.new_page()
    other.on("pageerror", lambda error: errors.append(str(error)))
    other.on("request", lambda request: request.url != guide_url and not request.url.startswith("data:") and asked.append(request.url))
    other.goto(guide_url)
    same(other.locator("h1").inner_text(), "How to use the KPI intake form", "the guide's heading")
    same(other.locator('a[href="kpi-intake-form.html"]').count() > 0, True, "the guide links back to the form")
    same(other.locator(".tasks a").all_inner_texts(), ["Start", "Save", "Continue", "Hand over", "Find a checked KPI"], "the guide's task links")
    for href in other.locator(".tasks a").evaluate_all("links => links.map(a => a.getAttribute('href'))"):
        same(other.locator(href).count(), 1, f"the section {href} of the guide")
    holds(other.locator("#save .ui-status").inner_text(), "Download requested: crack-spreads-pricing.kpi-intake.json. Check that the file appears in your chosen folder.", "the save message the guide shows")
    same(other.locator('#groups a[href="kpi-intake-form.html#q-3.8"]').count(), 1, "the guide's link to question 3.8")
    same(asked, [], "what the guide asked the network or the disk for")
    same(errors, [], "errors on the guide")
    assert target is None or target.is_file(), "the guide is not beside the form"
    context.close()
    # A link of the guide to one question opens the form at that question.
    at = s.open()
    at.goto(s.url + "#q-3.8")
    at.wait_for_function("(() => { const r = document.getElementById('q-3.8').getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; })()")
    # Phone width: the link is a target of 44 px.
    phone_page = s.open(width=390, height=844)
    assert phone_page.locator("#guide-link").bounding_box()["height"] >= 44, "the guide link is under 44 px high at 390 px"
    assert not phone_page.evaluate("document.documentElement.scrollWidth > innerWidth"), "the form scrolls sideways at 390 px with the link"


def alias(s):
    # The shipped settings add no entry that the ontology holds. So this proof opens a copy of the form in which
    # the ontology has gained SharePoint, as the build writes it: the entry carries the added id as an alias.
    text = Path(s.url.removeprefix("file://")).read_text(encoding="utf-8") if not sys.platform.startswith("win") else PAGE.read_text(encoding="utf-8")
    head, rest = text.split('<script id="intake-data" type="application/json">', 1)
    held, tail = rest.split("</script>", 1)
    data = json.loads(held)
    gained = "https://example.org/system/sharepoint"
    data["lists"]["systems"] = [i for i in data["lists"]["systems"] if i["id"] != "new:sharepoint"] + [{"id": gained, "label": "SharePoint", "aliases": ["new:sharepoint"]}]
    # A second entry in another state: the ontology gained it, the settings show it under another label, and
    # keep_only does not name it, so it is hidden. The build writes these marks (picklists.apply_settings).
    renamed = "https://example.org/system/price-desk"
    data["lists"]["systems"].append({"id": renamed, "label": "Price Desk System", "was": ["Price Desk"], "aliases": ["new:price-desk"], "hidden": True})
    folder = Path(tempfile.mkdtemp())
    copy = folder / "kpi-intake-form.html"
    copy.write_text(head + '<script id="intake-data" type="application/json">' + json.dumps(data).replace("<", "\\u003c").replace("&", "\\u0026") + "</script>" + tail, encoding="utf-8")
    context = s.browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(10_000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(copy.as_uri())
    older = {"format": 1, "form": "kpi-intake", "answers": {"2.1": "Tank Turnover", "7.1": "@not-in-list", "7.4": ["new:sharepoint", gained]}}
    page.locator("#load-file").set_input_files({"name": "older.kpi-intake.json", "mimeType": "application/json", "buffer": json.dumps(older).encode("utf-8")})
    page.wait_for_function("document.getElementById('status').textContent.startsWith('Loaded older.kpi-intake.json')")
    same(page.locator("#status").inner_text(), 'Loaded older.kpi-intake.json. "SharePoint" is now in the ontology; the answer was read as that entry.', "the status line")
    same(card(page, "7.4").locator(".picker-chosen .chosen-label").all_inner_texts(), ["SharePoint"], "the answer, read as the ontology's entry, once")
    same(card(page, "7.4").locator('[data-notice="to-add"]').count(), 0, "a notice to add an entry the ontology holds")
    same(search(page, "7.4", "SharePoint").locator(".picker-list .option-label").all_inner_texts(), ["SharePoint"], "SharePoint, offered once and not as new")
    with page.expect_download() as download:
        page.locator("#save").click()
    same(json.loads(Path(download.value.path()).read_text(encoding="utf-8"))["answers"]["7.4"], [gained], "the answer in the file saved again")
    # A draft that holds the added id is read the same way.
    page.evaluate("""() => { const d = JSON.parse(localStorage.getItem('kpi-intake-draft-1')); d.state['kpi-intake'].answers['7.4'] = ['new:sharepoint'];
                     localStorage.setItem('kpi-intake-draft-1', JSON.stringify(d)); }""")
    page.reload()
    same(page.locator("#status").inner_text(), 'Your unsaved draft was restored from this browser. "SharePoint" is now in the ontology; the answer was read as that entry.', "the status line of the draft")
    same(card(page, "7.4").locator(".picker-chosen .chosen-label").all_inner_texts(), ["SharePoint"], "the draft's answer")
    # The one rule (rules.py), value by value: each stored value is read as the entry's id of today.
    for stored, entry in (("new:sharepoint", gained), ("SharePoint (new, not yet in the ontology)", gained), ("SharePoint", gained), (gained, gained),
                          ("new:price-desk", renamed), ("Price Desk (new, not yet in the ontology)", renamed), ("Price Desk", renamed),
                          ("Price Desk System (hidden in this organization's settings)", renamed), ("@not-in-list", "@not-in-list"),
                          ("a system nobody knows", "a system nobody knows")):
        page.evaluate("""stored => { const d = JSON.parse(localStorage.getItem('kpi-intake-draft-1')); d.state['kpi-intake'].answers['7.4'] = [stored];
                         localStorage.setItem('kpi-intake-draft-1', JSON.stringify(d)); }""", stored)
        page.reload()
        with page.expect_download() as download:
            page.locator("#save").click()
        same(json.loads(Path(download.value.path()).read_text(encoding="utf-8"))["answers"]["7.4"], [entry], f"the draft value {stored!r}, saved again")
    # The hidden entry is shown while an answer holds it, and is not offered otherwise.
    page.evaluate("""stored => { const d = JSON.parse(localStorage.getItem('kpi-intake-draft-1')); d.state['kpi-intake'].answers['7.4'] = [stored];
                     localStorage.setItem('kpi-intake-draft-1', JSON.stringify(d)); }""", "new:price-desk")
    page.reload()
    same(card(page, "7.4").locator(".picker-chosen .chosen-label").all_inner_texts(), ["Price Desk System (hidden in this organization's settings)"], "the hidden entry a draft holds")
    same(errors, [], "errors on the page")
    context.close()


def term_change(s):
    page = s.open()
    page.locator('[data-view="term-change"]').click()
    same(page.locator("[data-question]").count(), 8, "questions of the term change")
    measure = card(page, "T1")
    measure.locator(".picker-search").fill("Unit Utilization")
    measure.locator(f'.picker-list input[value="{UNIT_UTILIZATION}"]').check()
    owner, line = page.locator('[data-signer="ontology-owner"]'), page.locator('[data-nav="signoff"] .nav-count')
    same(owner.locator(".signer-status").inner_text(), 'Only when the change is major: the answer to T8 is "no" or "not sure"',
         "the Ontology Owner before T8")
    same(line.inner_text(), "0 of 2 required signed", "the sign-off line before T8")
    for answer, needed in (("no", 3), ("not-sure", 3), ("yes", 2)):
        choose(page, "T8", answer)
        same(line.inner_text(), f"0 of {needed} required signed", f"the sign-off line when T8 is {answer}")
        same(owner.locator(".signer-required").is_visible(), needed == 3, f"the Ontology Owner's requirement when T8 is {answer}")
    card(page, "T4").locator("textarea").fill("unit capacity utilization")
    with page.expect_download() as download:
        page.locator("#save").click()
    same(download.value.suggested_filename, "unit-utilization.term-change.json", "the file's name")
    data = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    same((data["form"], data["kpi_name"]), ("term-change", "Unit Utilization"), "the form and the name")
    same(data["answers"], {"T1": UNIT_UTILIZATION, "T4": ["unit capacity utilization"], "T8": "yes"}, "answers")
    s.shot(page, "22-term-change")


PROOFS = [("1 load", load), ("2 fill", fill), ("3 narrow list", narrow_list), ("4 conditional", conditional),
          ("5 routing", routing), ("6 save", save), ("7 load file", load_file), ("8 draft", draft), ("9 phone", phone),
          ("10 theme", theme), ("11 next step", next_step), ("12 bad file", bad_file), ("13 other form", other_form),
          ("14 detail", detail), ("15 conflict", conflict), ("16 bad draft", bad_draft), ("17 hidden", hidden),
          ("18 added", added), ("19 new fields", new_fields), ("20 guide", guide), ("21 alias", alias),
          ("22 term change", term_change)]


def launch(playwright, channels):
    problems = []
    for channel in channels:
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception as error:  # the browser of this channel is not installed
            problems.append(f"{channel}: {str(error).splitlines()[0]}")
    raise SystemExit("No browser started. Install Google Chrome or Microsoft Edge.\n" + "\n".join(problems))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--page", default=str(PAGE), help="the form's page")
    p.add_argument("--browser", choices=["chrome", "msedge"], help="the installed browser to use (default: Chrome, then Edge)")
    p.add_argument("--shots", help="a folder for a screenshot of each proof")
    args = p.parse_args(argv)
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    failed = []
    with sync_playwright() as playwright:
        browser = launch(playwright, [args.browser] if args.browser else ["chrome", "msedge"])
        try:
            session = Session(browser, args.page, shots)
            for name, run in PROOFS:
                before = len(session.errors), len(session.requests)
                try:
                    run(session)
                    reason = None
                except Exception as error:  # a failed assertion, or a part of the page that never appeared
                    reason = str(error).strip().splitlines()[0]
                if not reason and session.requests[before[1]:]:
                    reason = f"network request: {session.requests[before[1]]}"
                if not reason and session.errors[before[0]:]:
                    reason = f"console error: {session.errors[before[0]]}"
                print(f"intake  {name:13}  {'FAIL  ' + reason if reason else 'pass'}")
                if reason:
                    failed.append(name)
        finally:
            browser.close()
    if failed:
        print(f"{len(failed)} of {len(PROOFS)} proofs failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"the intake form passed all {len(PROOFS)} proofs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
