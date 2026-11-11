"""Open both ontology pages in a real browser and prove the eight things a reader relies on.

    uv run --no-project --with playwright==1.65.0 python business_architecture/ontology/viewer/browser_check.py

It needs uv, a network connection the first time (uv fetches the playwright package) and an installed Google
Chrome or Microsoft Edge. It downloads no browser. `--shots <folder>` also writes a screenshot of each main view.

For viewer/index.html and for horoi_viewer/index.html it proves, each from a fresh load of the file:

  1 load          the page opens from file:// with no console error and no network request
  2 release       the release name shown is KPI Store 1.1
  3 modules       the module list holds the 13 modules at their versions
  4 search        search finds tg:replaces and the crude prices measure, and opens each term's page
  5 term page     the term's page shows its label, its definition and its relationships
  6 follow        a relationship link opens the other term
  7 way back      the browser's Back button and the breadcrumb return to where the reader was
  8 deep link     a link to a term opens that term directly
  + narrow        at 390 px the page has no sideways scroll

Every expected value below is written by hand from the release packages. The script exits 1 when a proof fails
and names it.
"""

import argparse
from pathlib import Path
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]
RELEASE = "KPI Store 1.1"
# The newest version of each module under business_architecture/ontology/releases/.
MODULES = {
    "core": "2.4.0",
    "data-product": "1.2.0",
    "integration": "2.5.0",
    "kpi": "1.3.0",
    "lane": "1.1.0",
    "logical-model": "1.0.0",
    "market-data": "1.1.0",
    "organization": "2.2.0",
    "party": "2.1.0",
    "ref-mpc": "1.3.0",
    "system": "1.5.0",
    "technical-graph": "1.1.0",
    "value-stream": "1.2.0",
}
# tg:replaces, which technical-graph 1.1.0 added.
REPLACES = "https://w3id.org/mpc/ontology/modules/technical-graph/replaces"
# The crude prices measure of the kpi module, its definition, and the process its kpi:informsProcess names.
MEASURE = "https://w3id.org/mpc/ontology/modules/kpi/measure/crude-prices"
MEASURE_LABEL = "Crude Market Pricing"
MEASURE_DEFINITION = "Crude oil benchmark prices and differentials, with related futures (natural gas, heating oil, RBOB)."
PROCESS = "https://w3id.org/mpc/ontology/process/CM-1-1-4-7-4"
PROCESS_LABEL = "Capture Product/Crude/Feedstock Price"
# One of the two views whose dp:servesMeasure names the measure: the measure's source on the data platform.
SOURCE_VIEW = "idp_sbx.semantic_sem_commercial.mips_mpr_executive_summary_fact_vw"


def same(found, expected, what):
    assert found == expected, f"{what}: found {found!r}, expected {expected!r}"


def holds(text, part, what):
    assert part in text, f"{what}: {part!r} is not in {text[:300]!r}"


class Session:
    """One page under test: a fresh load for each proof, with every console error and network request counted."""

    def __init__(self, browser, path, shots, name):
        self.browser, self.url, self.shots, self.name = browser, Path(path).resolve().as_uri(), shots, name
        self.errors, self.requests = [], []

    def open(self, fragment="", width=1440, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height})
        # Anything that is not the file itself or data inside it would leave the machine: stop it and count it.
        context.route(lambda url: not url.startswith(("file:", "data:", "blob:", "about:")), self._refuse)
        page = context.new_page()
        page.set_default_timeout(10_000)  # a part that never appears fails its proof after ten seconds
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("console", lambda message: message.type == "error" and self.errors.append(message.text))
        page.on("request", lambda request: request.url.startswith("file:") and request.url.split("#")[0] != self.url and self.requests.append(request.url))
        page.goto(self.url + fragment)
        return page

    def _refuse(self, route):
        self.requests.append(route.request.url)
        route.abort()

    def shot(self, target, view, **options):
        """Save a screenshot of a page, or of one part of it."""
        if self.shots:
            target.screenshot(path=str(self.shots / f"{self.name}-{view}.png"), **options)


def sideways_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth > innerWidth")


# ---- viewer/index.html --------------------------------------------------------------------------------------


def viewer_search(page, text, result):
    """Search from the header, check the result is listed, and open it."""
    page.locator("#global-search-open").click()
    page.locator("#global-query").fill(text)
    hit = page.locator(f'#global-results button[data-result="{result}"]')
    same(hit.count(), 1, f"search results for {text!r} that are {result}")
    return hit


def viewer_load(s):
    page = s.open()
    same(page.locator("#overview").get_attribute("data-view"), "modules", "the first view")
    same(page.locator("#overview > h2").inner_text(), "Module overview", "the first heading")
    s.shot(page, "1-first-screen")


def viewer_release(s):
    page = s.open()
    holds(page.locator("header").inner_text(), f"{RELEASE} · Definitions and relationships", "the header")
    page.locator("#about").click()
    same(page.locator("#release-pin").inner_text(), RELEASE, "the release name in Release details")
    page.locator("#release-info details").last.locator("summary").click()
    holds(page.locator("#sources").inner_text(), "releases/technical-graph/1.1.0/technical-graph.ttl", "the Turtle inputs")
    s.shot(page, "5-release-details")


def viewer_modules(s):
    page = s.open()
    rows = page.locator("#module-catalogue article")
    same(rows.count(), 13, "modules listed")
    found = {}
    for i in range(rows.count()):
        name = rows.nth(i).get_attribute("data-module")
        holds(rows.nth(i).inner_text(), f"{name} · {MODULES.get(name)}", f"the row of {name}")
        found[name] = MODULES.get(name)
    same(found, MODULES, "the modules and their versions")
    page.locator('#module-catalogue button[data-module="technical-graph"]').click()
    same(page.locator("#overview").get_attribute("data-view"), "module:technical-graph", "the view after choosing a module")
    holds(page.locator("#overview").inner_text(), "1.1.0", "the technical-graph overview")
    s.shot(page, "2-module-overview")


def viewer_search_proof(s):
    page = s.open()
    viewer_search(page, "replaces", REPLACES).click()
    same(page.locator("#iri").text_content(), REPLACES, "the term opened from the search for replaces")
    same(page.locator("#title").inner_text(), "replaces", "its title")
    holds(page.locator("#modules").inner_text(), "technical-graph 1.1.0", "its module")
    hit = viewer_search(page, MEASURE_LABEL, MEASURE)
    same(page.locator("#global-results button").first.get_attribute("data-result"), MEASURE, "the first result")
    s.shot(page, "4-search-results")
    hit.click()
    same(page.locator("#iri").text_content(), MEASURE, "the term opened from the search for the measure")


def viewer_term(s):
    page = s.open()
    viewer_search(page, MEASURE_LABEL, MEASURE).click()
    same(page.locator("#title").inner_text(), MEASURE_LABEL, "the label")
    same(page.locator("#kind").inner_text(), "Concept", "the kind")
    same(page.locator("#modules").inner_text(), "kpi 1.3.0", "the module")
    same(page.locator("#definition").inner_text().strip(), MEASURE_DEFINITION, "the definition")
    relations = page.locator("#relations").inner_text()
    holds(relations, "Outgoing: informs process\n" + PROCESS_LABEL, "the relationships")
    holds(relations, "Incoming: serves measure\n" + SOURCE_VIEW, "the relationships")
    same(page.locator("#graph g.selected").get_attribute("aria-label"), MEASURE_LABEL, "the centre of the diagram")
    s.shot(page, "3-term-page")


def viewer_follow(s):
    page = s.open()
    viewer_search(page, MEASURE_LABEL, MEASURE).click()
    page.locator("#relations button", has_text=PROCESS_LABEL).click()
    same(page.locator("#iri").text_content(), PROCESS, "the term the relationship link opened")
    same(page.locator("#title").inner_text(), PROCESS_LABEL, "its label")
    holds(page.url, quote(PROCESS, safe=""), "the address")


def viewer_back(s):
    page = s.open()
    viewer_search(page, MEASURE_LABEL, MEASURE).click()
    page.locator("#relations button", has_text=PROCESS_LABEL).click()
    same(page.locator("#breadcrumbs li").all_inner_texts()[-2:], [MEASURE_LABEL, PROCESS_LABEL], "the end of the breadcrumb")
    page.go_back()
    page.wait_for_function("id => document.getElementById('iri').textContent === id", arg=MEASURE)
    same(page.locator("#title").inner_text(), MEASURE_LABEL, "the term after Back")
    page.go_forward()
    page.wait_for_function("id => document.getElementById('iri').textContent === id", arg=PROCESS)
    page.locator("#breadcrumbs button", has_text=MEASURE_LABEL).click()
    same(page.locator("#iri").text_content(), MEASURE, "the term after its breadcrumb")
    page.locator("#breadcrumbs button", has_text="Search results").click()
    same(page.locator("#global-search").evaluate("dialog => dialog.open"), True, "the search is open again")
    same(page.locator("#global-query").input_value(), MEASURE_LABEL, "the search text it kept")


def viewer_deep_link(s):
    page = s.open("#" + quote(MEASURE, safe=""))
    same(page.locator("#iri").text_content(), MEASURE, "the term a direct link opens")
    same(page.locator("#title").inner_text(), MEASURE_LABEL, "its label")
    same(page.locator("#layout").is_visible(), True, "the term page is shown")
    same(page.locator("#overview").is_visible(), False, "the module overview is hidden")


def viewer_narrow(s):
    page = s.open(width=390, height=844)
    same(sideways_scroll(page), False, "sideways scroll on the first screen")
    s.shot(page, "6-first-screen-390")
    viewer_search(page, MEASURE_LABEL, MEASURE).click()
    same(page.locator("#title").inner_text(), MEASURE_LABEL, "the label")
    same(page.locator("main").is_visible(), True, "the term page is shown")
    same(sideways_scroll(page), False, "sideways scroll on the term page")
    s.shot(page, "6-term-page-390")


# ---- horoi_viewer/index.html --------------------------------------------------------------------------------


def term_link(iri):
    return "#term=" + quote(iri, safe="")


def reference_search(page, text, result):
    page.locator("#search").fill(text)
    hit = page.locator(f'#results a[href="{term_link(result)}"]')
    same(hit.count(), 1, f"search results for {text!r} that are {result}")
    return hit


def reference_heading(page, expected, what):
    page.wait_for_function("text => document.querySelector('#content h1')?.innerText === text", arg=expected)
    same(page.locator("#content h1").inner_text(), expected, what)


def reference_load(s):
    page = s.open()
    holds(page.locator("#content h1").inner_text(), "Understand the concepts.", "the first heading")
    same(page.locator(".masthead nav a[aria-current]").inner_text(), "Overview", "the marked navigation entry")
    s.shot(page, "1-first-screen")
    # The measures view loads too, and a group of one measure says "1 entry".
    page = s.open("#measures")
    groups = page.locator("#content details > summary").all_inner_texts()
    assert "Decision-support indicator · 1 entry" in groups and "KPI · 2 entries" in groups, f"the measure groups: {groups}"


def reference_release(s):
    page = s.open()
    same(page.locator("#release-scope").inner_text(), f"{RELEASE} · All ontology modules", "the release bar")
    same(page.locator("#credits").inner_text(), "Adapted from Horoi 0.2.0 · Credits", "the credit in the footer")
    page = s.open("#about")
    about = page.locator("#content").inner_text()
    holds(about, f"every current ontology module of {RELEASE}.", "Release and coverage")
    holds(about, f"release packages of {RELEASE}.", "Release and coverage")
    for word in ("commit", "undefined", "EPM"):
        assert word not in about, f"Release and coverage holds the word {word!r}"
    same(page.locator("#release-scope").inner_text(), f"{RELEASE} · All ontology modules", "the release bar on a second view")
    s.shot(page, "5-release-details")


def reference_modules(s):
    page = s.open()
    tiles = page.locator(".module-directory a.tile")
    same(tiles.count(), 13, "modules listed")
    found = {}
    for i in range(tiles.count()):
        name, version = tiles.nth(i).locator(".eyebrow").text_content().split(" · ")
        found[name] = version
    same(found, MODULES, "the modules and their versions")
    s.shot(page.locator(".module-directory"), "2-module-list")
    page.locator(".module-directory a.tile.technical-graph").click()
    reference_heading(page, "Technical graph", "the module page")
    same(page.locator("#content .eyebrow").first.text_content(), "technical-graph · 1.1.0", "its version line")
    page.wait_for_function("scrollY < 5")  # the page scrolls back to its top smoothly; wait for that to end
    s.shot(page, "2-module-overview")


def reference_search_proof(s):
    page = s.open("#browse")
    reference_search(page, "replaces", REPLACES).click()
    reference_heading(page, "replaces", "the term opened from the search for replaces")
    same(page.locator("#term-iri").inner_text(), REPLACES, "its identifier")
    page = s.open("#browse")
    hit = reference_search(page, MEASURE_LABEL, MEASURE)
    holds(page.locator("#result-count").inner_text(), "15 results.", "the result count")
    s.shot(page, "4-search-results")
    hit.click()
    reference_heading(page, MEASURE_LABEL, "the term opened from the search for the measure")
    same(page.locator("#term-iri").inner_text(), MEASURE, "its identifier")


def reference_term(s):
    page = s.open("#browse")
    reference_search(page, MEASURE_LABEL, MEASURE).click()
    reference_heading(page, MEASURE_LABEL, "the label")
    same(page.locator(".term-head .badge").inner_text(), "Concept", "the kind")
    holds(page.locator(".term-definition").inner_text(), MEASURE_DEFINITION, "the definition")
    content = page.locator("#content").inner_text()
    for heading in ("Where this term fits", "Follow its connections", "What points to this term"):
        holds(content, heading, "the term page")
    outgoing = page.locator("#content tr", has=page.locator(f'a[href="{term_link(PROCESS)}"]'))
    holds(outgoing.first.inner_text(), "informs process", "the row of the outgoing relationship")
    incoming = page.locator("#content tr", has_text=SOURCE_VIEW)
    holds(incoming.first.inner_text(), "serves measure", "the row of the incoming relationship")
    s.shot(page, "3-term-page", full_page=True)


def reference_follow(s):
    page = s.open("#browse")
    reference_search(page, MEASURE_LABEL, MEASURE).click()
    reference_heading(page, MEASURE_LABEL, "the label")
    page.locator(f'#content table a[href="{term_link(PROCESS)}"]', has_text=PROCESS_LABEL).first.click()
    reference_heading(page, PROCESS_LABEL, "the term the relationship link opened")
    same(page.locator("#term-iri").inner_text(), PROCESS, "its identifier")
    holds(page.url, term_link(PROCESS), "the address")


def reference_back(s):
    page = s.open("#browse")
    reference_search(page, MEASURE_LABEL, MEASURE).click()
    reference_heading(page, MEASURE_LABEL, "the label")
    page.locator(f'#content table a[href="{term_link(PROCESS)}"]', has_text=PROCESS_LABEL).first.click()
    reference_heading(page, PROCESS_LABEL, "the term the relationship link opened")
    page.go_back()
    reference_heading(page, MEASURE_LABEL, "the term after Back")
    same(page.locator(".crumb").inner_text(), "Overview / Measures and KPIs / Business concepts", "the breadcrumb")
    page.go_back()
    same(page.locator("#search").input_value(), MEASURE_LABEL, "the search text after a second Back")
    page.go_forward()
    reference_heading(page, MEASURE_LABEL, "the term after Forward")
    page.locator(".crumb a", has_text="Measures and KPIs").click()
    reference_heading(page, "Measures and KPIs", "the module page its breadcrumb opens")
    same(page.locator("#content .eyebrow").first.text_content(), "kpi · 1.3.0", "its version line")
    page.locator(".crumb a", has_text="Overview").click()
    page.locator(".module-directory").wait_for()
    same(page.locator(".module-directory a.tile").count(), 13, "the modules on the overview its breadcrumb opens")


def reference_deep_link(s):
    page = s.open(term_link(MEASURE))
    reference_heading(page, MEASURE_LABEL, "the term a direct link opens")
    same(page.locator("#term-iri").inner_text(), MEASURE, "its identifier")
    page = s.open("#module=technical-graph")
    reference_heading(page, "Technical graph", "the module a direct link opens")


def reference_narrow(s):
    page = s.open(width=390, height=844)
    same(page.locator("#release-scope").inner_text(), f"{RELEASE} · All ontology modules", "the release bar")
    same(sideways_scroll(page), False, "sideways scroll on the first screen")
    s.shot(page, "6-first-screen-390")
    page = s.open(term_link(MEASURE), width=390, height=844)
    reference_heading(page, MEASURE_LABEL, "the label")
    same(sideways_scroll(page), False, "sideways scroll on the term page")
    s.shot(page, "6-term-page-390")


PROOFS = ["1 load", "2 release", "3 modules", "4 search", "5 term page", "6 follow", "7 way back", "8 deep link", "+ narrow"]
PAGES = {
    "viewer": [viewer_load, viewer_release, viewer_modules, viewer_search_proof, viewer_term, viewer_follow, viewer_back, viewer_deep_link, viewer_narrow],
    "reference": [reference_load, reference_release, reference_modules, reference_search_proof, reference_term, reference_follow, reference_back, reference_deep_link, reference_narrow],
}


def launch(playwright, channels):
    problems = []
    for channel in channels:
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception as error:  # the browser of this channel is not installed
            problems.append(f"{channel}: {str(error).splitlines()[0]}")
    raise SystemExit("No browser started. Install Google Chrome or Microsoft Edge.\n" + "\n".join(problems))


def check_page(browser, name, path, shots):
    """Run the nine proofs on one page. Returns the proofs that failed, each with its reason."""
    session, failed = Session(browser, path, shots, name), []
    for proof, run in zip(PROOFS, PAGES[name]):
        before = len(session.errors), len(session.requests)
        try:
            run(session)
            reason = None
        except Exception as error:  # a failed assertion, or a part of the page that never appeared
            reason = str(error).strip().splitlines()[0]
        # The first proof owns the load: an error or a request during any later proof also fails that proof.
        if not reason and session.requests[before[1]:]:
            reason = f"network request: {session.requests[before[1]]}"
        if not reason and session.errors[before[0]:]:
            reason = f"console error: {session.errors[before[0]]}"
        print(f"{name:9}  {proof:11}  {'FAIL  ' + reason if reason else 'pass'}")
        if reason:
            failed.append(f"{name} {proof}")
    return failed


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--viewer", default=str(ROOT / "viewer/index.html"), help="the full viewer's page")
    p.add_argument("--reference", default=str(ROOT / "horoi_viewer/index.html"), help="the reference page")
    p.add_argument("--browser", choices=["chrome", "msedge"], help="the installed browser to use (default: Chrome, then Edge)")
    p.add_argument("--shots", help="a folder for a screenshot of each main view")
    args = p.parse_args(argv)
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = launch(playwright, [args.browser] if args.browser else ["chrome", "msedge"])
        try:
            failed = check_page(browser, "viewer", args.viewer, shots) + check_page(browser, "reference", args.reference, shots)
        finally:
            browser.close()
    if failed:
        print(f"{len(failed)} of 18 proofs failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("both pages passed all 18 proofs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
