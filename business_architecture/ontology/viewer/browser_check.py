"""Open both ontology pages in a real browser and prove the things a reader relies on.

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

For viewer/index.html it also proves:

  9 keys          in search, Enter opens the first result, and the arrow keys choose another result for Enter
  10 prefix       search finds a term by its prefixed name, tg:replaces
  11 shortcut     the search box names its shortcut, and Ctrl+K and Cmd+K open the search
  12 no term      All ontology shows a "Choose a term" panel until the reader selects a term

For horoi_viewer/index.html it also proves:

  9 ranking       search lists an exact label match first, then the labels that start with the search text
  10 names        each module has the name the full ontology viewer gives it
  11 measure      a measure's page shows "What points to this term" directly under its definition
  12 language     a definition shows no "en" language tag
  13 slash key    the "/" key opens Find a term with the cursor in its search box, except while the reader types
  14 wording      the page calls the other page the full ontology viewer

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
# The kpi measure whose definition names Crude Market Pricing. Of the 15 other terms that hold that text, its label
# comes first in alphabetical order.
SECOND_RESULT = "https://w3id.org/mpc/ontology/modules/kpi/measure/additional-market-prices"
SECOND_RESULT_LABEL = "Additional Market Prices (Renewables, NGLs)"
# The first term in the list of All ontology.
ABBREVIATION = "https://w3id.org/mpc/ontology/modules/party/attribute/rightangle/create/abbreviation"
# The party module's site type whose label is "Terminal", and its class whose label is "customer account".
TERMINAL = "https://w3id.org/mpc/ontology/modules/party/site-type/terminal"
CUSTOMER_ACCOUNT = "https://w3id.org/mpc/ontology/modules/party/CustomerAccount"
# The labels of 32 terms start with "terminal" in either case: 4 in data-product, 13 in party, 1 in system,
# 2 in value-stream, 3 in core and 9 in logical-model. One of the 32 is "Terminal" itself.
TERMINAL_LABELS = 32
# Each module's dcterms:title, the name the full ontology viewer shows on Module overview.
MODULE_NAMES = {
    "core": "MPC Core Process Ontology",
    "data-product": "MPC Data Product Module",
    "integration": "MPC Integration Vocabularies",
    "kpi": "MPC KPI Module",
    "lane": "MPC Lane Module",
    "logical-model": "MPC Logical Model Module",
    "market-data": "MPC Market Data Module",
    "organization": "MPC Organization Module",
    "party": "MPC Party Module",
    "ref-mpc": "MPC Reference Instances: Marathon Petroleum Corporation",
    "system": "MPC System Module",
    "technical-graph": "MPC Technical Graph Module",
    "value-stream": "MPC Value Stream Module",
}


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


def viewer_keys(s):
    page = s.open()
    viewer_search(page, MEASURE_LABEL, MEASURE)
    same(page.locator("#global-results button.active").get_attribute("data-result"), MEASURE, "the result Enter opens")
    page.locator("#global-query").press("Enter")
    same(page.locator("#global-search").evaluate("dialog => dialog.open"), False, "the search is open after Enter")
    same(page.locator("#iri").text_content(), MEASURE, "the term Enter opened")
    # The second result is the next label in alphabetical order that holds the search text.
    viewer_search(page, MEASURE_LABEL, MEASURE)
    page.locator("#global-query").press("ArrowDown")
    same(page.locator("#global-results button.active").count(), 1, "highlighted results")
    same(page.locator("#global-results button.active").get_attribute("data-result"), SECOND_RESULT, "the result after Down")
    page.locator("#global-query").press("ArrowDown")
    page.locator("#global-query").press("ArrowUp")
    same(page.locator("#global-results button.active").get_attribute("data-result"), SECOND_RESULT, "the result after Down, Down, Up")
    page.locator("#global-query").press("Enter")
    same(page.locator("#iri").text_content(), SECOND_RESULT, "the term Enter opened after the arrow keys")
    same(page.locator("#title").inner_text(), SECOND_RESULT_LABEL, "its label")


def viewer_prefix(s):
    page = s.open()
    hit = viewer_search(page, "tg:replaces", REPLACES)
    same(page.locator("#global-results button").first.get_attribute("data-result"), REPLACES, "the first result")
    hit.click()
    same(page.locator("#iri").text_content(), REPLACES, "the term opened from the search for tg:replaces")
    # The filter beside the term list reads a prefixed name the same way.
    page.locator("#breadcrumbs button", has_text="Search results").click()
    page.locator("#global-search-close").click()
    page.locator("#query").fill("tg:replaces")
    same(page.locator("#results button[data-term]").first.get_attribute("data-term"), REPLACES, "the first term of the filtered list")


def viewer_shortcut(s):
    page = s.open()
    same(page.locator("#global-query").get_attribute("placeholder"), "Search ontology (Ctrl+K)", "the search box's placeholder")
    for keys in ("Control+k", "Meta+k"):
        same(page.locator("#global-search").evaluate("dialog => dialog.open"), False, f"the search is open before {keys}")
        page.keyboard.press(keys)
        same(page.locator("#global-search").evaluate("dialog => dialog.open"), True, f"the search is open after {keys}")
        same(page.evaluate("document.activeElement.id"), "global-query", f"the part that has the cursor after {keys}")
        page.locator("#global-search-close").click()


def viewer_no_term(s):
    page = s.open()
    page.locator("#view-browse").click()
    same(page.locator("#choose-term").is_visible(), True, "the panel is shown")
    same(page.locator("#choose-term h2").inner_text(), "Choose a term", "the panel's heading")
    same(
        page.locator("#choose-term p").inner_text(),
        "Search in Find a term, or open Module overview in the navigation and pick a module. "
        "Then select a term in the list to read its definition and relationships.",
        "the panel's text",
    )
    for part in ("#title", "#copy", "#definition", "#graph"):
        same(page.locator(part).is_visible(), False, f"{part} is shown before a term is chosen")
    s.shot(page, "7-no-term")
    page.locator(f'#results button[data-term="{ABBREVIATION}"]').click()
    same(page.locator("#title").inner_text(), "Abbreviation", "the term chosen from the list")
    same(page.locator("#choose-term").is_visible(), False, "the panel is shown after a term is chosen")
    same(page.locator("#definition").is_visible(), True, "the definition is shown")


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
    reference_heading(page, "MPC Technical Graph Module", "the module page")
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
    same(page.locator(".crumb").inner_text(), "Overview / MPC KPI Module / Business concepts", "the breadcrumb")
    page.go_back()
    same(page.locator("#search").input_value(), MEASURE_LABEL, "the search text after a second Back")
    page.go_forward()
    reference_heading(page, MEASURE_LABEL, "the term after Forward")
    page.locator(".crumb a", has_text="MPC KPI Module").click()
    reference_heading(page, "MPC KPI Module", "the module page its breadcrumb opens")
    same(page.locator("#content .eyebrow").first.text_content(), "kpi · 1.3.0", "its version line")
    page.locator(".crumb a", has_text="Overview").click()
    page.locator(".module-directory").wait_for()
    same(page.locator(".module-directory a.tile").count(), 13, "the modules on the overview its breadcrumb opens")


def reference_deep_link(s):
    page = s.open(term_link(MEASURE))
    reference_heading(page, MEASURE_LABEL, "the term a direct link opens")
    same(page.locator("#term-iri").inner_text(), MEASURE, "its identifier")
    page = s.open("#module=technical-graph")
    reference_heading(page, "MPC Technical Graph Module", "the module a direct link opens")


def reference_narrow(s):
    page = s.open(width=390, height=844)
    same(page.locator("#release-scope").inner_text(), f"{RELEASE} · All ontology modules", "the release bar")
    same(sideways_scroll(page), False, "sideways scroll on the first screen")
    s.shot(page, "6-first-screen-390")
    page = s.open(term_link(MEASURE), width=390, height=844)
    reference_heading(page, MEASURE_LABEL, "the label")
    same(sideways_scroll(page), False, "sideways scroll on the term page")
    s.shot(page, "6-term-page-390")


def reference_ranking(s):
    page = s.open("#browse")
    reference_search(page, "terminal", TERMINAL)
    holds(page.locator("#result-count").inner_text(), "176 results.", "the result count")
    same(page.locator("#results li > a").first.get_attribute("href"), term_link(TERMINAL), "the first result for terminal")
    labels = page.locator("#results li > a").all_inner_texts()
    starts = [label.lower().startswith("terminal") for label in labels]
    same(starts[:TERMINAL_LABELS], [True] * TERMINAL_LABELS, "the labels that start with the search text come next")
    same(starts[TERMINAL_LABELS], False, "the next label starts with the search text")
    reference_search(page, "customer account", CUSTOMER_ACCOUNT)
    same(page.locator("#results li > a").first.get_attribute("href"), term_link(CUSTOMER_ACCOUNT), "the first result for customer account")


def reference_names(s):
    page = s.open()
    tiles = page.locator(".module-directory a.tile")
    found = {}
    for i in range(tiles.count()):
        found[tiles.nth(i).locator(".eyebrow").text_content().split(" · ")[0]] = tiles.nth(i).locator("h2").inner_text()
    same(found, MODULE_NAMES, "the module names on the overview")
    page = s.open("#browse")
    options = page.locator("#module-filter option").all_inner_texts()
    same(options, ["All modules", *MODULE_NAMES.values()], "the module names in the search filter")


def section_headings(page):
    return page.locator("#content > section.section > h2").all_inner_texts()


def reference_measure(s):
    page = s.open(term_link(MEASURE))
    reference_heading(page, MEASURE_LABEL, "the measure's page")
    same(page.locator(".term-definition + *").evaluate("part => part.querySelector('h2')?.innerText"), "What points to this term", "the part directly under the definition")
    same(section_headings(page), ["What points to this term", "Where this term fits", "Follow its connections"], "the sections of a measure's page")
    # A term that is not a measure keeps the order it had.
    page = s.open(term_link(PROCESS))
    reference_heading(page, PROCESS_LABEL, "the process's page")
    same(section_headings(page), ["Where this term fits", "Follow its connections", "What points to this term"], "the sections of a process's page")


def reference_language(s):
    page = s.open(term_link(MEASURE))
    reference_heading(page, MEASURE_LABEL, "the measure's page")
    same(page.locator(".term-definition").inner_text().strip(), MEASURE_DEFINITION, "the definition block")
    same(page.locator(".term-definition .lang").count(), 0, "language tags in the definition block")
    same(page.evaluate("[...document.querySelectorAll('#content .lang')].filter(tag => !tag.closest('#facts')).length"), 0, "language tags outside the recorded facts")
    # The table of recorded facts still states each literal's language.
    page.locator("#facts > summary").click()
    holds(page.locator("#facts").inner_text(), "Language: en", "the recorded facts")


def reference_slash(s):
    page = s.open()
    page.locator(".module-directory").wait_for()
    page.keyboard.press("/")
    page.locator("#search").wait_for()
    same(page.evaluate("document.activeElement.id"), "search", "the part that has the cursor after /")
    holds(page.url, "#browse", "the address after /")
    same(page.locator("#search").input_value(), "", "the search text after /")
    # In the search box the key types a slash.
    page.keyboard.type("a/b")
    same(page.locator("#search").input_value(), "a/b", "the search text after typing a/b")
    # On Find a term the key puts the cursor back in the search box.
    page.locator("#module-filter").select_option("kpi")
    page.locator("#result-count").click()
    page.keyboard.press("/")
    same(page.evaluate("document.activeElement.id"), "search", "the part that has the cursor after / on Find a term")
    same(page.locator("#search").input_value(), "a/b", "the search text after / on Find a term")


def reference_wording(s):
    page = s.open("#modules")
    reference_heading(page, "Modules and connections", "the modules page")
    holds(page.locator("#content").inner_text(), "The full ontology viewer remains available from the footer.", "the modules page")
    same(page.locator("footer a").first.inner_text(), "Open the full ontology viewer", "the footer link")
    page = s.open(term_link(MEASURE))
    reference_heading(page, MEASURE_LABEL, "the measure's page")
    same(page.locator("#content .actions a").last.inner_text(), "Open this term in the full ontology viewer", "the link to the other page")
    # Every other name for that page is gone from the page's own text. The ontology data is not searched.
    own_text = page.evaluate("[...document.querySelectorAll('script:not([id]), body > :not(script)')].map(part => part.textContent).join(' ')")
    for name in ("original ontology viewer", "original viewer", "full viewer", "Full viewer"):
        assert name not in own_text, f"the page still says {name!r}"


PAGES = {
    "viewer": [
        ("1 load", viewer_load),
        ("2 release", viewer_release),
        ("3 modules", viewer_modules),
        ("4 search", viewer_search_proof),
        ("5 term page", viewer_term),
        ("6 follow", viewer_follow),
        ("7 way back", viewer_back),
        ("8 deep link", viewer_deep_link),
        ("9 keys", viewer_keys),
        ("10 prefix", viewer_prefix),
        ("11 shortcut", viewer_shortcut),
        ("12 no term", viewer_no_term),
        ("+ narrow", viewer_narrow),
    ],
    "reference": [
        ("1 load", reference_load),
        ("2 release", reference_release),
        ("3 modules", reference_modules),
        ("4 search", reference_search_proof),
        ("5 term page", reference_term),
        ("6 follow", reference_follow),
        ("7 way back", reference_back),
        ("8 deep link", reference_deep_link),
        ("9 ranking", reference_ranking),
        ("10 names", reference_names),
        ("11 measure", reference_measure),
        ("12 language", reference_language),
        ("13 slash key", reference_slash),
        ("14 wording", reference_wording),
        ("+ narrow", reference_narrow),
    ],
}
TOTAL = sum(len(proofs) for proofs in PAGES.values())


def launch(playwright, channels):
    problems = []
    for channel in channels:
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception as error:  # the browser of this channel is not installed
            problems.append(f"{channel}: {str(error).splitlines()[0]}")
    raise SystemExit("No browser started. Install Google Chrome or Microsoft Edge.\n" + "\n".join(problems))


def check_page(browser, name, path, shots):
    """Run one page's proofs. Returns the proofs that failed, each with its reason."""
    session, failed = Session(browser, path, shots, name), []
    for proof, run in PAGES[name]:
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
        print(f"{name:9}  {proof:12}  {'FAIL  ' + reason if reason else 'pass'}")
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
        print(f"{len(failed)} of {TOTAL} proofs failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"both pages passed all {TOTAL} proofs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
