"""A new module of new modelling, drafted by an AI under the five gates of KPI-DEC-0002, Q19 (Q17(a) and Q20).

The new-module form's N3 answer "new-modelling" asks for a module that the two patterns of new_module.py cannot
make: new classes, new properties or rules of its own. Nobody writes it by hand. Before anyone signs the form, the
Architect asks the AI to draft it (python -m kpi_store.propose --ai-draft <form>, kpi_store/ai/draft.py). The draft
and the record of the AI steps stay beside the form until the form is signed:

    <form>.draft/         the five files of the draft (release/drafted_module.py says what each holds)
    <form>.draft.json     the record: the module's settings, the drafter and the reviewer (each model and its
                          version, who approved it, the skill files, the SHA-256 of the prompt and of the answer),
                          the reviewer's verdict and findings, the SHA-256 of each file of the draft, the SHA-256 of
                          the form's answers it was drafted from, and the result of each gate

What the propose command calls: from_signed_form, which refuses the form unless its draft passed gates 1 to 4, the
reviewer passed it, the form's answers are those it was drafted from, and the Ontology Owner signed (gate 5). It
runs gates 1, 2 and 4 again against the release as it is now. The proposal then holds the draft's files under
draft/, KGCL lines that name each new class and property with its definition, the module's facts (its pattern,
title, description and documents), and the record in approval.json under "draft".

What the apply command calls: check_proposal (the same checks, on the proposal's own files, before anything is
written), write (the module's folder, written from the drafted pattern and registered in every place by
release/register_module.py), and compare (the round trip: the built module holds exactly the proposal's draft).
"""
import hashlib
import json
from pathlib import Path

from . import ChangeRefused, kgcl, new_module
from .kgcl import Change

NEW_MODELLING = "new-modelling"
DRAFTED = "drafted"
DRAFT_FOLDER = "draft"              # the draft's files in a proposal folder
RECORD_SUFFIX, FOLDER_SUFFIX = ".draft.json", ".draft"
QUESTION = "N13"                    # what the module must let people say, in words


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def answers_sha256(answers):
    """The fingerprint of a form's answers: what the draft was made from, so a later edit to them is seen."""
    return sha256_bytes(json.dumps(answers, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def pattern(root):
    return new_module._load(root, "drafted_module")


def is_drafted(facts):
    return any(s.startswith(new_module.SUBJECT) and p == "pattern" and v == DRAFTED for s, p, v in facts)


def spec_of_form(answers, root, release=None):
    """The drafted module's settings from a new-module form whose N3 is new-modelling: its key, prefix, title,
    description and documents, checked against the release as new_module.split checks a pattern's. Raises
    ChangeRefused."""
    straight = lambda text: text.replace(kgcl.TYPOGRAPHIC, "'").strip()
    from kpi_store.intake import rules
    if new_module._one(answers, "N3") != NEW_MODELLING:
        raise ChangeRefused("N3: an AI draft is for a module of new modelling, the answer \"Something else\"")
    title = straight(new_module._one(answers, "N1"))
    key = new_module.module_key(title)
    if not key:
        raise ChangeRefused(f'N1: "{title}" has no letter or digit to make the module\'s short key from')
    release = release or new_module.Release(root)
    spec = new_module.module_settings(key, DRAFTED, title, straight(new_module._one(answers, "N2")),
                                      "; ".join(straight(s) for s in rules.values(answers, "N12")), root, release)
    brief = straight(new_module._one(answers, QUESTION))
    if not brief:
        raise ChangeRefused(f"{QUESTION}: say in words what the module must let people say, so the AI can draft it")
    return {"module": spec["module"], "pattern": DRAFTED, "prefix": spec["prefix"], "title": spec["title"],
            "description": spec["description"], "citation": spec["citation"], "depends_on": [], "prefixes": {}}


def release_prefixes(release):
    """The release's own prefixes, each bound to one namespace by its packages."""
    return {p: ns for p, ns in release.prefixes.items() if p not in new_module.STANDARD_PREFIXES}


def from_answer(text, spec, root, release=None):
    """The draft of an AI's answer: (the module's settings, completed, and {file name: text} of the five files in
    their canonical form). The answer is JSON of one exact form: model, shapes, questions, examples and summary.
    Each class and property gets the form's documents as its citation when the AI gave it none. Raises ChangeRefused
    for an answer of another form; the gates come after (gates)."""
    from rdflib import Literal, URIRef
    dm = pattern(root)
    release = release or new_module.Release(root)
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        body = body.rsplit("```", 1)[0]
    try:
        data = json.loads(body)
    except ValueError as err:
        raise ChangeRefused(f"the AI's draft is not JSON ({err})") from None
    wanted = {"model", "shapes", "questions", "examples", "summary"}
    if not isinstance(data, dict) or set(data) != wanted or not isinstance(data["model"], str) or \
            not isinstance(data["shapes"], str):
        raise ChangeRefused("the AI's draft must be one JSON object with exactly model, shapes, questions, examples and "
                            "summary, where model and shapes are Turtle texts")
    offered = release_prefixes(release)
    spec = dict(spec, prefixes=offered)
    texts = {dm.MODEL: data["model"], dm.SHAPES: data["shapes"],
             dm.QUESTIONS: json.dumps(data["questions"], ensure_ascii=False),
             dm.EXAMPLES: json.dumps(data["examples"], ensure_ascii=False),
             dm.SUMMARY: json.dumps(data["summary"], ensure_ascii=False)}
    try:
        draft = dm.Draft(spec, texts)
    except dm.DraftError as err:
        raise ChangeRefused(f"the AI's draft cannot be read: {err}") from None
    cite = URIRef(dm.DCTERMS + "bibliographicCitation")
    for t in draft.of_kind("class") + draft.of_kind("property"):
        if not list(draft.model.objects(t, cite)):
            draft.model.add((t, cite, Literal(spec["citation"], lang="en")))
    # The modules the module requires: those whose newest package gives a type to a name the draft uses.
    used = {str(x) for g in [draft.model, draft.shapes, draft.passing] + [a for _, a, _ in draft.failing]
            for triple in g for x in triple if isinstance(x, URIRef)}
    depends = sorted({m for iri in used if iri.startswith(new_module.BASE) and not iri.startswith(dm.namespace(spec))
                      for m in release.defined_in(iri)})
    every = "\n".join(texts.values())
    kept = {p: ns for p, ns in offered.items() if f"{p}:" in every or ns in every}
    spec = dict(spec, depends_on=depends, prefixes=kept)
    draft = dm.Draft(spec, dict(texts, **{dm.MODEL: dm.model_text(spec, draft.model)}))
    return spec, dm.canonical(draft)


def gates(spec, files, root):
    """[{gate, name, passed, results}] of gates 1, 2 and 4 over the draft's files, against the release's newest
    packages. Raises ChangeRefused when the draft does not have the form the pattern needs."""
    dm = pattern(root)
    try:
        return dm.gates(dm.Draft(spec, files), str(Path(root) / "business_architecture" / "ontology"))
    except dm.DraftError as err:
        raise ChangeRefused(str(err)) from None


def parts(files):
    """[{path, sha256}] of the draft's files, in name order."""
    return [{"path": name, "sha256": sha256_bytes(files[name].encode("utf-8"))} for name in sorted(files)]


def read_files(folder, root):
    """{file name: text} of a draft folder's five files."""
    dm = pattern(root)
    out = {}
    for name in dm.FILES:
        try:
            out[name] = (Path(folder) / name).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise ChangeRefused(f"the draft's file {name} cannot be read ({type(err).__name__})") from None
    return out


def changes_of(spec, files, root):
    """The KGCL lines that name the draft's new classes, properties and named individuals: each one's name and
    definition, and its class, domain and range where the release's prefixes write them. They are what the change
    file and the release notes list; the module itself is the draft's files."""
    from rdflib import URIRef
    dm = pattern(root)
    draft = dm.Draft(spec, files)
    out = []
    known = dm.prefixes(spec)

    def short(iri):
        c = dm.curie(spec, iri)
        return c if c != str(iri) and kgcl.ID.fullmatch(c) and c.split(":", 1)[0] in known else None
    for kind in ("class", "property", "individual"):
        for t in draft.of_kind(kind):
            s = short(t)
            if not s:
                raise ChangeRefused(f"{t} has no short name that a KGCL line can write")
            out.append(Change("create node", s, text=draft.label(t)))
            for d in draft.model.objects(t, URIRef(dm.SKOS + "definition")):
                out.append(Change("add definition", s, text=str(d)))
            for p, name in ((dm.RDFS + "subClassOf", "rdfs:subClassOf"), (dm.RDFS + "domain", "rdfs:domain"),
                            (dm.RDFS + "range", "rdfs:range")):
                for o in sorted(draft.model.objects(t, URIRef(p)), key=str):
                    if isinstance(o, URIRef) and short(o):
                        out.append(Change("create edge", s, predicate=name, target=short(o)))
    for c in out:
        kgcl.write_line(c)   # refuses a text that a KGCL line cannot carry
    return out


def facts_of(spec):
    m = new_module.SUBJECT + spec["module"]
    return [(m, "pattern", DRAFTED), (m, "title", spec["title"]), (m, "description", spec["description"]),
            (m, "source", spec["citation"])]


def _failed(results):
    return [f"gate {g['gate']} ({g['name']}): " + "; ".join(g["results"]) for g in results if not g["passed"]]


def check_record(record, files, answers=None):
    """Refuses a record beside a form, or in a proposal, unless gates 1 to 4 passed, the reviewer gave PASS, the
    files are those it fingerprints, and (with `answers`) the form's answers are those the draft was made from."""
    from kpi_store.change import approval
    approval.check_draft(record, signed=False)
    if record["reviewer"] is None:
        raise ChangeRefused("the AI draft has not been reviewed yet (gate 3). Run python -m kpi_store.propose "
                            "--ai-draft <the form> again, with --review-answer when the reviewer works by hand")
    failed = _failed(record["gates"])
    if failed:
        raise ChangeRefused("the AI draft did not pass every gate: " + " | ".join(failed))
    if parts(files) != record["parts"]:
        raise ChangeRefused("the draft's files are not those the AI drafted and the reviewer read: a file changed after "
                            "the AI step. Delete the draft and its record, and ask again")
    if answers is not None and answers_sha256(answers) != record["form_sha256"]:
        raise ChangeRefused("the form's answers changed after the AI drafted the module, so the draft may not be "
                            "what the form now asks for. Delete the draft and its record, and ask again")


def from_signed_form(path, intake, root, signatures):
    """(key, changes, facts, files, record) of a signed new-modelling form: the record beside it, checked, with gates
    1, 2 and 4 run again against the release as it is now, and gate 5 added from the Ontology Owner's signature.
    Raises ChangeRefused."""
    path = Path(path)
    record_path, folder = path.with_name(path.stem + RECORD_SUFFIX), path.with_name(path.stem + FOLDER_SUFFIX)
    if not record_path.is_file():
        raise ChangeRefused(f"{path.name} asks for new modelling (N3), and has no AI draft beside it. A specialist "
                            "designs it, or the AI drafts it before anyone signs: python -m kpi_store.propose "
                            f"--ai-draft {path.as_posix()} (HOW-TO-UPDATE.md, \"Draft new modelling with AI (optional)\")")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ChangeRefused(f"the record of the AI draft {record_path.name} cannot be read ({type(err).__name__})") from None
    files = read_files(folder, root)
    check_record(record, files, intake.answers)
    spec = record["module"]
    fresh = spec_of_form(intake.answers, root)
    for k in ("module", "prefix", "title", "description", "citation"):
        if fresh[k] != spec[k]:
            raise ChangeRefused(f"the record of the AI draft gives the module's {k} as {spec[k]!r}, and the form now gives "
                                f"{fresh[k]!r}. Delete the draft and its record, and ask again")
    now = gates(spec, files, root)
    failed = _failed(now)
    if failed:
        raise ChangeRefused("the AI draft no longer passes against the release as it is now: " + " | ".join(failed))
    owner = next((s for s in signatures if s["role"] == "Ontology Owner"), None)
    if not owner:
        raise ChangeRefused("gate 5: the Ontology Owner has not signed the form")
    gate5 = {"gate": 5, "name": pattern(root).GATE_NAMES[5], "passed": True,
             "results": [f"the Ontology Owner signed on {owner['date']}", "the route is major, and the module's first "
                         f"release is {new_module.VERSION}"]}
    record = dict(record, gates=[g for g in record["gates"] if g["gate"] != 5] + [gate5])
    return spec["module"], changes_of(spec, files, root), facts_of(spec), files, record


def check_proposal(p, root):
    """The checks of the apply command on a drafted module's proposal, before it writes anything: the record holds
    every gate passed and the Ontology Owner's signature (gate 5); the draft's files are those it fingerprints; gates
    1, 2 and 4 pass again against this release; and the KGCL lines are those of the draft. Returns the files."""
    from kpi_store.change import approval
    record = p.record.get("draft")
    if record is None:
        raise ChangeRefused(f"the proposal {p.change} is a drafted module, and its approval record holds no record of "
                            "the AI draft")
    approval.check_draft(record, signed=True)
    files = read_files(p.folder / DRAFT_FOLDER, root)
    check_record(record, files)
    if not any(s["role"] == "Ontology Owner" for s in p.record["signatures"]) or p.record["route"] != "major":
        raise ChangeRefused(f"the proposal {p.change}: gate 5 needs the Ontology Owner's signature and the route major")
    spec = record["module"]
    if facts_of(spec) != [tuple(f) for f in p.facts]:
        raise ChangeRefused(f"the proposal {p.change}: its facts are not those of the drafted module {spec['module']}")
    failed = _failed(gates(spec, files, root))
    if failed:
        raise ChangeRefused(f"the proposal {p.change} no longer passes against this release: " + " | ".join(failed))
    if [kgcl.write_line(c) for c in changes_of(spec, files, root)] != p.lines:
        raise ChangeRefused(f"the proposal {p.change}: its KGCL lines are not those of its draft")
    return files


def summary_lines(spec, files, record, root):
    """The drafted module in plain words, for summary.txt: what each new thing means, the gates and the reviewer."""
    dm = pattern(root)
    draft = dm.Draft(spec, files)
    out = ["What the new things mean, as the AI wrote it for the signers:"] + dm.summary_lines(draft)
    out += ["", "The competency questions it answers:"]
    out += [f"  - {q['id']}: {q['question']}" for q in draft.questions]
    out += ["", "The gates (KPI-DEC-0002, Q19):"]
    for g in sorted(record["gates"], key=lambda g: g["gate"]):
        out.append(f"  - Gate {g['gate']}, {g['name']}: {'passed' if g['passed'] else 'FAILED'}.")
        out += [f"      {line}" for line in g["results"]]
    for role in ("drafter", "reviewer"):
        step = record[role]
        who = step["assistant"] if step["provider"] == "by-hand" else f"{step['provider']}, model {step['model']}"
        out.append(f"  The {role}: {who} ({step['family']}), asked on {step['asked_on']}, approved by "
                   f"{step['approved_by']} on {step['approved_on']}.")
    out.append('  The whole record, with its fingerprints, is in approval.json under "draft".')
    return out


def module_of(spec, files, change, words, date, root):
    """The release/register_module.py Module of a drafted module."""
    dm, rm = pattern(root), new_module.places(root)
    draft = dm.Draft(spec, files)
    key = spec["module"]
    folder_files = dict(files)
    folder_files.update({"README.md": dm.readme_text(spec, draft, change), dm.builder_name(key): dm.builder_text(spec, change),
                         dm.test_name(key): dm.test_text(spec)})
    section = (f"### {key}: {spec['title']}\n\n{spec['description']} An AI drafted the module's classes, properties and "
               f"shapes, under the five gates of KPI-DEC-0002, Q19 (proposal {change}).\n\n<!-- module: {key} -->\n"
               f"```turtle parse\n{dm.example(spec, draft)}```\n\n")
    requires = (f" It requires the newest {', '.join(spec['depends_on'])}." if spec["depends_on"] else
                " It requires no other module.")
    changelog = (f"# {key} changelog\n\n## {new_module.VERSION} ({date})\n\nThe module's first release, a major. It "
                 f"carries the new-module form's proposal {change}, which the Data Owner, the Ontology Owner and the "
                 f"Architect signed (approvals/{change}.json). An AI drafted its {dm.figures(draft)}, and the draft "
                 "passed the five gates of KPI-DEC-0002, Q19: its competency questions and examples, the reasoner, a "
                 "review by a second model of another family, a plain-words summary, and the Ontology Owner's "
                 f"signature.{requires} The Ontology Owner owns the module until they name a module owner.\n\n"
                 "### Known gaps\n\nNone.\n")
    return rm.Module(
        name=key, version=new_module.VERSION, prefix=spec["prefix"], title=spec["title"], description=spec["description"],
        approver=new_module.OWNER_WORDS, approval=(f"approvals/{change}.json", words), parts=[f"{key}/{dm.MODEL}"],
        shapes=[f"{key}/{dm.SHAPES}"], depends_on=list(spec["depends_on"]), decisions=[f"approvals/{change}.json"],
        files=folder_files, builder=dm.builder_name(key), test=dm.test_name(key), changelog=changelog,
        question=dm.question(spec), question_heading=spec["title"],
        question_intro=f"The question of the `{key}` module, which an AI drafted (proposal {change}).",
        query_name=f"{key}-content", query=dm.query(spec), regression_files=[dm.MODEL],
        purpose="A module of new modelling, drafted by an AI under five gates", modules_section=section,
        entry_comment=[f"1.0.0 is the module's first release, which the AI-drafted proposal {change} made."])


def write(p, files, root, words, date):
    """Writes the drafted module's folder into a scratch copy of the release and registers it in every place.
    Returns the module's key."""
    spec = p.record["draft"]["module"]
    module = module_of(spec, files, p.change, words, date, root)
    try:
        new_module.places(root).register(module, str(root), date, write=True)
    except Exception as err:   # register_module.Refused: a place is not where the code expects it
        raise ChangeRefused(f"the module cannot be registered: {err}") from None
    return spec["module"]


def compare(root, key, files):
    """Raises ChangeRefused unless the module's folder holds exactly the draft's files: the same graphs in model.ttl
    and shapes.ttl, and the same questions, examples and summary."""
    from rdflib.compare import isomorphic
    dm = pattern(root)
    folder = Path(root) / "business_architecture" / "ontology" / key
    spec = _spec(folder / dm.builder_name(key))
    built, proposed = dm.Draft(spec, read_files(folder, root)), dm.Draft(spec, files)
    for name, a, b in ((dm.MODEL, built.model, proposed.model), (dm.SHAPES, built.shapes, proposed.shapes)):
        if not isomorphic(a, b):
            raise ChangeRefused(f"the {key} module's {name} does not hold exactly the proposal's draft")
    for name in (dm.QUESTIONS, dm.EXAMPLES, dm.SUMMARY):
        if json.loads(built.texts[name]) != json.loads(files[name]):
            raise ChangeRefused(f"the {key} module's {name} is not the proposal's")


def _spec(builder):
    import ast
    for node in ast.parse(Path(builder).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "SPEC":
            return ast.literal_eval(node.value)
    raise ChangeRefused(f"{builder} holds no SPEC")
