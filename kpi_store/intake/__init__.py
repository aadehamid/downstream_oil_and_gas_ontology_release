"""The KPI intake pack: the forms a business analyst fills in to ask for a new KPI, and the check of a filled form.

    py -m kpi_store.intake build            write the forms, the pick lists, the two generated pages and the examples
    py -m kpi_store.intake build --check    write nothing; exit 1 when a committed file differs from a fresh build
    py -m kpi_store.intake check <file>     say what a filled form (answers JSON or workbook) still lacks

The questions live in kpi-intake/catalogue.toml and the organization's own lists in kpi-intake/settings.toml.
Everything else in kpi-intake/ except README.md, the JSON Schema and examples/examples.toml is built from those two
files and the release packages.

Where each part is:

    catalogue.py   reads and validates the two TOML files
    picklists.py   reads the pick lists from the release packages (needs rdflib)
    rules.py       which questions are asked, the kind of measure, the routing outcomes
    answers.py     the answers file: read it from JSON or from a filled workbook
    check.py       the completeness check
    workbook.py    the Excel form (needs openpyxl)
    page.py        the HTML form, from form.html
    examples.py    the filled examples, from the ontology
    build.py       the one command that writes or compares all of them

The check changes nothing in the ontology. The Architect applies a complete intake by hand, with HOW-TO-UPDATE.md.
"""
