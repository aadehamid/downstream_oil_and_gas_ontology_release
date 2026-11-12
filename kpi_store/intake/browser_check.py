"""Open the HTML intake form in a real browser and prove the sixteen things a person filling it relies on.

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

Every expected value below is written by hand from the catalogue and the release packages. The script exits 1
when a proof fails and names it. scripts/check.sh does not run it, because it needs a browser.
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "kpi-intake" / "kpi-intake-form.html"
EXAMPLE = ROOT / "kpi-intake" / "examples" / "crack-spreads-pricing.json"
COMMERCIAL = "https://w3id.org/mpc/ontology/modules/core/business-domain/commercial"
REFINERY_OPTIMIZATION = "https://w3id.org/mpc/ontology/process/CM-1-1-4-7"
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
    holds(page.locator("#release-line").text_content(), "KPI Store 1.1, catalogue 1.0", "the release line")
    same(page.locator("#tabs [role=tab]").all_inner_texts(),
         ["KPI intake", "Domain activation", "Process map request", "The roles", "What we will ask you"], "the tabs")
    same(page.locator("[data-section]").count(), 7, "sections of the KPI form")
    same(page.locator("[data-question]").count(), 46, "questions of the KPI form")
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
    holds(page.locator('[data-section="2"] .section-progress').inner_text(), "2 required answers left · 2 optional unanswered", "section 2 before")
    card(page, "2.1").locator("input").fill("Tank Turnover")
    card(page, "2.2").locator("textarea").fill("How many times the stored volume is replaced in a month.")
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "Required answers complete · 2 optional unanswered", "section 2 after")
    choose(page, "3.7", "anyone")
    holds(page.locator('[data-nav="3"] .nav-count').inner_text(), "4 required answers left", "the section list")
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
    for hidden in ("4.2", "4.3", "3.1", "3.2", "3.3", "6.7"):
        assert card(page, hidden).is_hidden(), f"{hidden} shows although 4.1 is no"
    holds(page.locator('[data-section="3"] .section-skipped').inner_text(), "3 questions do not apply", "the skipped line of section 3")
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
    same(data["catalogue_version"], "1.0", "catalogue version")
    same(data["kpi_name"], "Tank Turnover", "KPI name")
    same(data["answers"], {"2.1": "Tank Turnover", "4.1": "yes", "4.2": "yes", "5.1": ["turns", "stock turn"]}, "answers")
    same(data["sign_offs"], {"data-owner": {"name": "A name", "date": "2026-11-11"}}, "sign-offs")
    holds(page.locator("#status").inner_text(), "Saved tank-turnover.kpi-intake.json", "the status line")


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
    for tab in ("kpi-intake", "domain-activation", "process-map-request", "roles", "explainer"):
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
        ('{"format":1,"form":"something-else","answers":{}}', 'its "form" names none of the three forms.'),
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
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "Required answers complete · 2 optional unanswered", "section 2 after the refusals")
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
    forms = ("kpi-intake", "domain-activation", "process-map-request")

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
    holds(page.locator('[data-section="2"] .section-progress').inner_text(), "1 required answer left", "section 2 after the refused draft")
    page.reload()
    same(card(page, "2.1").locator("input").input_value(), "Days of Cover", "2.1 from the new draft")
    s.shot(page, "16-bad-draft")


PROOFS = [("1 load", load), ("2 fill", fill), ("3 narrow list", narrow_list), ("4 conditional", conditional),
          ("5 routing", routing), ("6 save", save), ("7 load file", load_file), ("8 draft", draft), ("9 phone", phone),
          ("10 theme", theme), ("11 next step", next_step), ("12 bad file", bad_file), ("13 other form", other_form),
          ("14 detail", detail), ("15 conflict", conflict), ("16 bad draft", bad_draft)]


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
