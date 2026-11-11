# View the ontology

Open `viewer/index.html` in a browser after unzipping the release. The page contains its ontology data, scripts and fonts. It works offline and needs no installation or server.

The viewer opens on Module overview. The top navigation separates Modules, Value streams and Customer views. Use Module overview to find a module by name or description, read its purpose and see its vocabulary and dependencies. The optional module dependency diagram opens the same overviews. Use Browse all terms to enter that module's complete search and hierarchy. The Order to Cash and Commercial Hydrocarbon Lifecycle buttons open each stream's ordered stages directly; expand a stage's processes or open its details to drill down. Breadcrumbs and return buttons take you back while keeping your searches, filters and expanded sections. This browsing state lasts until you close or reload the page.

Use Search ontology from any view. Find modules by name or description, business views by name, and terms by label, definition or IRI. Use Term type to narrow the terms to classes, properties, concepts or another released type. All ontology also provides these filters and the module hierarchy. Select a term to read its definition, source and relationships. Select a connected term to follow a relationship. Expand All properties and evidence to inspect the recorded predicates and values. Include evidence and constraints to find supporting nodes directly.

Choose the value-stream module to list the value streams. Open a stream to see its stages in sequence, then open a stage to see its processes. Each process links to the core processes it realizes. Use Part of to return to the containing stage or stream.

Use Customer lifecycle in the top navigation to see the business stages. Open Processes and systems under a stage to follow its process links and corresponding system stages. The stages are listed alphabetically; the release does not define a mandatory sequence.

Use Customer conceptual model to see the customer entities together. Select an entity to highlight its connections, read its definition and filter the relationship list. Open an entity or property to inspect its full details; the return button takes you back to the model. Use Zoom in, Zoom out, Fit diagram or Full screen to explore the diagram. Escape exits full screen. The module dependency diagram has the same controls. Each diagram scrolls within its frame on a narrow screen. The conceptual model connections are also listed as text. Arrows show declared domains and ranges, subclass links and disjoint links. They do not imply required fields or cardinalities. Attributes, code lists and system extensions remain in All ontology; the separate customer logical model is in the logical-model module.

Release details names the release and lists the Turtle inputs with their checksums. Counts distinguish ontology terms from evidence, constraints and package metadata. Technical-graph vocabulary is included; runtime records and example datasets are not viewer inputs.

## The reference page

`horoi_viewer/index.html` is a second page over the same release. It reads like a reference: an overview, the process tree, the customer lifecycle, the value streams, the measures, each module with its connections, and a term search. It also works offline. Its footer links back to this viewer. `horoi_viewer/build.json` records the release name, the input files with their checksums and the page's own checksum. `horoi_viewer/NOTICE.txt` gives the credit for the Horoi page styles.

## Rebuild the pages after a change

Each page carries a copy of the ontology data. Editing a package does not refresh that copy, so rebuild both pages after you cut a new module version. Follow `HOW-TO-UPDATE.md` at the release root for the change to the ontology itself.

The two commands need Python 3.11 or later with the `rdflib` package. Run them from the release root. On macOS or Linux, write `python3` in place of `py`.

```powershell run=release-copy status-only
py business_architecture/ontology/viewer/build.py --source . --out viewer/index.html
py business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer
```

Each command reads the newest version of every module under `business_architecture/ontology/releases/` and checks each file against its package's manifest. It stops when a file differs from its manifest. Two runs on the same packages write the same bytes.

Add `--check` to compare a page with a fresh build without writing anything. `scripts/check.sh` makes the same comparison, so it fails while a page is older than the packages.

```powershell run=release-copy
py business_architecture/ontology/viewer/build.py --source . --out viewer/index.html --check
py business_architecture/ontology/viewer/build_horoi.py --source . --out horoi_viewer --check
```

```text expect
viewer/index.html is current
horoi_viewer is current
```
