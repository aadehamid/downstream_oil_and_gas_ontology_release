# consumer: rules for those who read the graph

How a catalog row binds a Named KPI (competency question 35), and what a graph or meaning agent may answer from the graph and must refuse (questions 41 and 42). the decision of 2026-10-19 records the rules.

| File | What |
|---|---|
| `vocabulary.ttl` | `con:publishesMeasure`, the catalog binding from a defined data product to a defined measure; the `con:Rule` class and its kinds; eight may-answer rules (the seventh, what a measure counts, from the decision of 2026-10-19; the eighth, a value quoted through the bound metric view, from the decision of 2026-10-25, item 6) and five must-refuse rules, each naming the graph terms it relies on |
| `shapes.ttl` | A binding needs both ends defined; each rule has a name, a definition, a kind, the terms it relies on and its citation |
| `test_consumer_rules.py` | Tests: the rule counts, each rule's relied-on terms pinned by hand from the decision of 2026-10-19, every term a rule relies on exists in the graph, the rules conform, and the binding accepts defined ends and rejects undefined ones |

No catalog row binds a measure yet: no source says which data product publishes which measure. The binding is the pattern a catalog uses when it does.

Released in `integration` 1.0.0 on 2026-10-22, with `placement` and `authority`, the shapes included (the decision of 2026-10-22): the package in `../releases/integration/1.0.0/`. *2026-10-23:* `integration` 2.0.0 (`../releases/integration/2.0.0/`): `con:reliesOn` takes `rdfs:range rdf:Property`, and one rule's process concept moves to `rdfs:seeAlso` (the decision of 2026-10-23). *2026-10-25:* `integration` 2.1.0, states the code list's top concepts both ways (the decision of 2026-10-25). *2026-10-25:* `integration` 2.2.0 (`../releases/integration/2.2.0/`): `rule:value-through-bound-view` lets an agent quote a value through the metric view bound to the measure (the decision of 2026-10-25, item 6; the decision of 2026-10-25). *2026-10-26:* `integration` 2.3.0 tiers the two sources of the drafted descriptions (the decision of 2026-10-26).
