# View the ontology

Open `viewer/index.html` in a browser after unzipping the release. The page contains its ontology data, scripts and fonts. It works offline and needs no installation or server.

The viewer opens on Module overview. The top navigation separates Modules, Value streams and Customer views. Use Module overview to find a module by name or description, read its purpose and see its vocabulary and dependencies. The optional module dependency diagram opens the same overviews. Use Browse all terms to enter that module's complete search and hierarchy. The Order to Cash and Commercial Hydrocarbon Lifecycle buttons open each stream's ordered stages directly; expand a stage's processes or open its details to drill down. Breadcrumbs and return buttons take you back while keeping your searches, filters and expanded sections. This browsing state lasts until you close or reload the page.

Use Search ontology from any view, or press Ctrl+K (Cmd+K on macOS). Find modules by name or description, business views by name, and terms by label, definition or IRI. A prefixed name such as `tg:replaces` also finds its term. Press Enter to open the first result, or choose another result with the Up and Down arrow keys and then press Enter. Use Term type to narrow the terms to classes, properties, concepts or another released type. All ontology also provides these filters and the module hierarchy. Until you select a term, All ontology shows a Choose a term panel that says how to start. Select a term to read its definition, source and relationships. Select a connected term to follow a relationship. Expand All properties and evidence to inspect the recorded predicates and values. Include evidence and constraints to find supporting nodes directly.

Choose the value-stream module to list the value streams. Open a stream to see its stages in sequence, then open a stage to see its processes. Each process links to the core processes it realizes. Use Part of to return to the containing stage or stream.

Use Customer lifecycle in the top navigation to see the business stages. Open Processes and systems under a stage to follow its process links and corresponding system stages. The stages are listed alphabetically; the release does not define a mandatory sequence.

Use Customer conceptual model to see the customer entities together. Select an entity to highlight its connections, read its definition and filter the relationship list. Open an entity or property to inspect its full details; the return button takes you back to the model. Use Zoom in, Zoom out, Fit diagram or Full screen to explore the diagram. Escape exits full screen. The module dependency diagram has the same controls. Each diagram scrolls within its frame on a narrow screen. The conceptual model connections are also listed as text. Arrows show declared domains and ranges, subclass links and disjoint links. They do not imply required fields or cardinalities. Attributes, code lists and system extensions remain in All ontology; the separate customer logical model is in the logical-model module.

The header shows the release name on every view. Release details repeats it and lists the Turtle inputs with their checksums. Counts distinguish ontology terms from evidence, constraints and package metadata. Technical-graph vocabulary is included; runtime records and example datasets are not viewer inputs.

## The reference page

`horoi_viewer/index.html` is a second page over the same release. It reads like a reference: an overview, the process tree, the customer lifecycle, the value streams, the measures, each module with its connections, and a term search. It also works offline. It gives each module the name this viewer gives it. Press `/` to open Find a term with the cursor in its search box. The search lists an exact label match first, then the labels that start with your text, then the other matches. A measure's page shows What points to this term directly under the definition. Its footer links back to this viewer, which it calls the full ontology viewer. `horoi_viewer/build.json` records the release name, the Horoi version, the input files with their checksums and the page's own checksum. `horoi_viewer/NOTICE.txt` gives the credit for the Horoi page styles.

## Rebuild the pages after a change

Each page carries a copy of the ontology data. Editing a package does not refresh that copy, so rebuild both pages after you cut a new module version. Follow `HOW-TO-UPDATE.md` at the release root for the change to the ontology itself.

The two commands need Python 3.11 or later with the `rdflib` package. Run them from the release root. On macOS or Linux, write `python3` in place of `python` when that is your Python's name.

```powershell run=release-copy status-only
python business_architecture/ontology/viewer/build.py --source . --out viewer/index.html
python business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer
```

Each command reads the newest version of every module under `business_architecture/ontology/releases/` and checks each file against its package's manifest. It stops when a file differs from its manifest. Two runs on the same packages write the same bytes.

Add `--check` to compare a page with a fresh build without writing anything. `scripts/check.sh` makes the same comparison, so it fails while a page is older than the packages.

```powershell run=release-copy
python business_architecture/ontology/viewer/build.py --source . --out viewer/index.html --check
python business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer --check
```

```text expect
viewer/index.html is current
horoi_viewer is current
```

## Test the pages in a browser

`scripts/check.sh` proves that each page equals a fresh build. It does not open a browser. After you rebuild the pages, run the browser check from the release root. It needs `uv`, a network connection the first time (`uv` fetches the `playwright` package) and an installed Google Chrome or Microsoft Edge. It downloads no browser and takes about 15 seconds.

```powershell run=slow
uv run --quiet --no-project --with playwright==1.65.0 python business_architecture/ontology/viewer/browser_check.py
```

```text expect
viewer     1 load         pass
viewer     2 release      pass
viewer     3 modules      pass
viewer     4 search       pass
viewer     5 term page    pass
viewer     6 follow       pass
viewer     7 way back     pass
viewer     8 deep link    pass
viewer     9 keys         pass
viewer     10 prefix      pass
viewer     11 shortcut    pass
viewer     12 no term     pass
viewer     13 namespaces  pass
viewer     + narrow       pass
reference  1 load         pass
reference  2 release      pass
reference  3 modules      pass
reference  4 search       pass
reference  5 term page    pass
reference  6 follow       pass
reference  7 way back     pass
reference  8 deep link    pass
reference  9 ranking      pass
reference  10 names       pass
reference  11 measure     pass
reference  12 language    pass
reference  13 slash key   pass
reference  14 wording     pass
reference  + narrow       pass
both pages passed all 29 proofs
```

The check opens each page from its file and stops any request that would leave the machine. For each page it proves that the page loads with no console error and no network request, shows the release name, lists the 13 modules at their versions, finds `tg:replaces` and the crude prices measure by search, shows the measure's label, definition and relationships, follows a relationship to the other term, returns with the Back button and the breadcrumb, opens a term from a direct link, and has no sideways scroll at 390 px. It also proves the keys, the prefixed name, the shortcut, the Choose a term panel and a prefix with several namespaces (`role:carrier`) in this viewer, and the result order, the module names, the measure's page, the hidden language tag, the `/` key and the wording of the reference page. A failed proof prints `FAIL` with the reason, and the command ends with status 1. Add `--shots <folder>` to save a screenshot of each main view, and `--browser msedge` to use Edge.

The block above runs in the document check only when `DOC_SNIPPETS_SLOW` is set, because it needs a browser and a download. Run it before a release is cut.

`business_architecture/ontology/viewer/test_browser.mjs` is a longer test of the full ontology viewer's diagrams, value streams and customer views. Its first lines say what it needs.
