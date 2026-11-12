"""Open the HTML intake form in a real browser and prove the nine things a person filling it relies on.

    uv run --no-project --with playwright==1.65.0 python kpi_store/intake/browser_check.py

It needs uv, a network connection the first time (uv fetches the playwright package) and an installed Google
Chrome or Microsoft Edge. It downloads no browser. `--shots <folder>` also writes a screenshot of each proof.

Each proof starts from a fresh load of kpi-intake/kpi-intake-form.html, with empty storage:

  1 load         the page opens from file:// with no console error and no network request
  2 fill         a typed answer and a chosen answer are counted in the section's progress
  3 narrow list  the process list follows the business area, and the step list follows the process
  4 conditional  a question that the rules skip is hidden, and comes back when the answer changes
  5 routing      an inactive domain and a missing process each show their own notice
  6 save         "Save answers" downloads the answers as a JSON file of the documented shape
  7 load file    "Load answers" fills the form from the shipped Crack Spreads Pricing example
  8 draft        an unsaved draft survives a reload
  9 phone        at 390 px wide the page has no sideways scroll

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

    def open(self, width=1280, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height}, accept_downloads=True)
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
    holds(page.locator("#release-line").inner_text(), "KPI Store 1.1, catalogue 1.0", "the release line")
    same(page.locator("#tabs [role=tab]").all_inner_texts(),
         ["KPI intake", "Domain activation", "Process map request", "The roles", "What we will ask you"], "the tabs")
    same(page.locator("[data-section]").count(), 7, "sections of the KPI form")
    same(page.locator("[data-question]").count(), 46, "questions of the KPI form")
    s.shot(page, "1-load")


def fill(s):
    page = s.open()
    holds(page.locator('[data-section="2"] .section-progress').inner_text(), "0 of 4 answered, 2 required still missing", "section 2 before")
    card(page, "2.1").locator("input").fill("Tank Turnover")
    card(page, "2.2").locator("textarea").fill("How many times the stored volume is replaced in a month.")
    same(page.locator('[data-section="2"] .section-progress').inner_text(), "2 of 4 answered", "section 2 after")
    choose(page, "3.7", "anyone")
    holds(page.locator('[data-nav="3"] .nav-count').inner_text(), "1 of 7 answered", "the section list")
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
    holds(note.inner_text(), "Domain activation needed", "the notice for a domain that is not active")
    choose(page, "1.5", "market-price")
    same(card(page, "1.5").locator("[data-notice]").count(), 0, "notices for an active domain")
    choose(page, "1.2", "@not-in-list")
    holds(card(page, "1.2").locator('[data-notice="process-map-request"]').inner_text(), "Process map request needed", "the notice for a missing process")
    assert card(page, "1.2").locator(".q-detail").is_visible(), "the missing process's name is not asked for"
    choose(page, "3.7", "restricted")
    holds(card(page, "3.7").locator('[data-notice="restricted-review"]').inner_text(), "Privacy, Security, Compliance and Risk", "the notice for a restricted KPI")
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
    page.locator("#clear").click()
    same(card(page, "2.1").locator("input").input_value(), "", "2.1 after Start again")


def phone(s):
    page = s.open(width=390, height=844)
    page.locator("#load-file").set_input_files(str(EXAMPLE))
    card(page, "7.1").scroll_into_view_if_needed()
    for tab in ("kpi-intake", "domain-activation", "process-map-request", "roles", "explainer"):
        page.locator(f'[data-view="{tab}"]').click()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), f"the {tab} view scrolls sideways at 390 px"
    s.shot(page, "9-phone")


PROOFS = [("1 load", load), ("2 fill", fill), ("3 narrow list", narrow_list), ("4 conditional", conditional),
          ("5 routing", routing), ("6 save", save), ("7 load file", load_file), ("8 draft", draft), ("9 phone", phone)]


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
