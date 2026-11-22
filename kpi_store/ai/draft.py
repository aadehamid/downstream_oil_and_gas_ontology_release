"""AI-drafted modelling for a new module of new modelling (KPI-DEC-0002, Q17(a), Q19, Q20 and Q26).

    python -m kpi_store.propose --ai-draft <form.json> [--stores <local settings>] [--ai-answer <file>]
                                [--review-answer <file>]

The form is a new-module form whose N3 is "Something else" (new-modelling), with N13 saying in words what the module
must let people say. A draft is only ever a proposal's content: the AI applies nothing, and the propose and apply
commands check everything again. The order, before anyone signs:

1. The drafter, the provider of [ai] in the local settings, gets the ontology skill and the clear-writing skill as its
   instructions (Q26), and a task: the form's answers, the module's namespace, the classes and properties the release
   holds, the rules a draft must meet (release/drafted_module.py) and the exact JSON of the answer.
2. The command reads the answer strictly, writes nothing yet, and runs the checks of the drafted pattern and gates
   1, 2 and 4 (release/drafted_module.py). If any fails, it says why and keeps nothing.
3. It writes the draft's five files to <form>.draft/ and the record to <form>.draft.json.
4. The reviewer, the provider of [ai_reviewer], of another model family than the drafter (gate 3), gets the ontology
   skill's method and checks as its instructions, and the form's answers, the draft and the gates' results. It
   answers PASS or HOLD, with its findings. A HOLD blocks: the propose command refuses the form.
5. The command adds the review to the record as gate 3, and writes <form>.draft-summary.txt, the plain-words summary
   the signers read before they sign.

The by-hand provider makes no call, for the drafter or the reviewer: the command writes the prompt to a file
(<form>.draft-prompt.txt or <form>.review-prompt.txt) and stops. The person gives it to an assistant, such as Genie
Code, saves its answer to a file, and runs the command again with --ai-answer or --review-answer.

Then the signers read the summary and sign the form: the Data Owner, the Ontology Owner (gate 5) and the Architect.
The plain propose command turns it into a proposal (kpi_store/change/drafted.py, from_signed_form).

The record keeps, for the drafter and the reviewer each, the provider, the assistant, the model's family, the model
and its version, the address called, who approved the provider and when, the date, each skill file with its SHA-256,
the SHA-256 of the prompt and the SHA-256 of the answer (Q20); and the SHA-256 of each file of the draft, which the
signers accept whole by signing. It keeps no prompt text, because the prompt holds the form's answers before signing.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path

from kpi_store.change import ChangeRefused, approval, drafted, new_module

from . import AIRefused, providers, suggest

DRAFT_SKILLS = ("skills/ontology/SKILL.md", "skills/ontology/references/domain-model.md",
                "skills/ontology/references/shacl.md", "skills/clear-writing/SKILL.md")
REVIEW_SKILLS = ("skills/ontology/SKILL.md", "skills/ontology/references/domain-model.md",
                 "skills/ontology/references/shacl.md", "skills/ontology/references/quality.md")
MAX_TOKENS = 16000
DRAFT_PROMPT, REVIEW_PROMPT = ".draft-prompt.txt", ".review-prompt.txt"
DRAFT_ANSWER, REVIEW_ANSWER, SIGNERS_SUMMARY = ".draft-answer.json", ".review-answer.json", ".draft-summary.txt"


def _ready(ai, table):
    """providers.ready, with the messages naming the table they are about."""
    try:
        return providers.ready(ai)
    except AIRefused as err:
        raise AIRefused(str(err).replace("[ai]", f"[{table}]")) from None


def _settings(stores, root, environ):
    from kpi_store import local_settings
    try:
        found = local_settings.load(local_settings.locate(stores, environ), environ=environ, release_root=root)
    except local_settings.LocalSettingsError as err:
        raise AIRefused(f"the local settings that name the AI providers cannot be read: {err}") from None
    return found.ai, found.ai_reviewer


def providers_of(drafter, reviewer):
    """The drafter and the reviewer, each ready, of two model families (gate 3)."""
    drafter, reviewer = _ready(drafter, "ai"), _ready(reviewer, "ai_reviewer")
    for ai, table in ((drafter, "ai"), (reviewer, "ai_reviewer")):
        if not ai.family:
            raise AIRefused(f'[{table}] family must name the model\'s family, such as "claude", "gpt" or "llama": the '
                            "reviewer of a draft must be of another family than the drafter")
    if drafter.family.strip().casefold() == reviewer.family.strip().casefold():
        raise AIRefused(f'[ai] and [ai_reviewer] are both of the family "{drafter.family}". Gate 3 needs a second model '
                        "from another family: name a reviewer of another family in [ai_reviewer]")
    return drafter, reviewer


def _classes_and_properties(release):
    """Lines that name each class and property the release holds, so the drafter reuses them."""
    from rdflib import URIRef
    out = []
    kinds = {new_module.OWL + "Class": "class", new_module.OWL + "ObjectProperty": "object property",
             new_module.OWL + "DatatypeProperty": "datatype property"}
    for kind, name in kinds.items():
        for t in sorted(set(release.union.subjects(URIRef(new_module.RDF + "type"), URIRef(kind))), key=str):
            if not isinstance(t, URIRef) or release.deprecated(t):
                continue
            c = release.curie(t)
            if c:
                d = release.union.value(t, URIRef(new_module.SKOS + "definition"))
                out.append(f"- {c} ({name}), \"{release.label(t)}\"" + (f": {d}" if d else ""))
    return out


def draft_task(spec, intake, release, dm):
    from kpi_store.intake import rules
    ns, offered = dm.namespace(spec), drafted.release_prefixes(release)
    shown = {**dm.STANDARD, spec["prefix"]: ns, "shp": dm.shapes_namespace(spec), "ex": dm.examples_namespace(spec),
             **offered}
    lines = [
        "# The task",
        "",
        "Draft a new module of the KPI Store's ontology from one new-module form. Follow the instructions above: the "
        "ontology skill for the modelling, and the clear-writing skill for every text a person reads.",
        "",
        "The form:",
        f"- The module's name: {spec['title']}",
        f"- What it covers: {spec['description']}",
        f"- The documents that describe it: {spec['citation']}",
        f"- What it must let people say: {''.join(rules.values(intake.answers, drafted.QUESTION)[:1])}",
        "",
        f"The module's namespace is {ns}, with the prefix {spec['prefix']}:. Its shapes are in {dm.shapes_namespace(spec)}, "
        f"with the prefix shp:. Example data uses {dm.examples_namespace(spec)}, with the prefix ex:. These prefixes, "
        "and the standard ones, are declared for you; you may use them without @prefix lines:",
    ]
    lines += [f"- {p}: <{n}>" for p, n in sorted(shown.items())]
    lines += [
        "",
        "The rules the draft must meet. The command checks each one, and refuses the whole draft if one fails:",
        "1. The model adds terms of its own only: every subject of model is a term of the module's namespace. It "
        "changes no term of the release. It reuses the release's classes and properties listed below, by name, "
        "wherever they fit, and names nothing else outside the module except standard RDF, RDFS, OWL, XSD, SKOS, "
        "Dublin Core and SHACL terms.",
        "2. Each term is typed as owl:Class, owl:ObjectProperty, owl:DatatypeProperty or owl:NamedIndividual. Each class "
        "and property has exactly one rdfs:label and exactly one skos:definition, both in English (@en). A definition "
        "says what the thing is, without repeating its name.",
        "3. Each property has exactly one rdfs:domain and exactly one rdfs:range. An object property's range is a "
        "class; a datatype property's range is a datatype, such as xsd:date.",
        "4. Each property has a property shape in shapes with sh:path and sh:minCount or sh:maxCount. Every shape is "
        "in shp:, uses only the core constraints of SHACL, and targets only the module's own classes or terms, with "
        "sh:targetClass, sh:targetNode, sh:targetSubjectsOf or sh:targetObjectsOf. Give each property shape an "
        "sh:message in plain words.",
        "5. The competency questions are SPARQL queries over the model, the passing examples and the release. Each names "
        "a term of the module, uses no SERVICE, FROM or LOAD, and gives its expected answer: true for an ASK query, or "
        "the rows of a SELECT query, each a list of texts in the order of the query's variables. Write an IRI as its "
        "prefixed name or in full, and a literal as its text.",
        "6. The passing examples are Turtle data, with subjects in ex: only, that meet every shape and every rule of "
        "the release. Each failing example changes them (add and remove are Turtle; remove lists triples of the "
        "passing examples, with no blank node) so that they break the node shape it names. Every node shape is "
        "broken by at least one failing example.",
        "7. The model, the passing examples and the release must be consistent: a reasoner checks them.",
        "8. The summary has one entry for each class, property and node shape: what it means in plain words, and an "
        "example, for a reader who has never built an ontology.",
        "",
        "Answer with JSON only, in exactly this form, with no other text:",
        '{"model": "<Turtle>", "shapes": "<Turtle>", '
        '"questions": [{"id": "CQ1", "question": "<the question in words>", "sparql": "<the query>", '
        '"expected": true or [["<value>", ...], ...]}], '
        '"examples": {"pass": "<Turtle>", "fail": [{"id": "F1", "breaks": "<the rule it breaks, in words>", '
        '"shape": "shp:<a node shape>", "add": "<Turtle>", "remove": "<Turtle>"}]}, '
        '"summary": [{"term": "<a prefixed name>", "meaning": "<in plain words>", "example": "<in plain words>"}]}',
        "",
        "The classes and properties the release holds:",
    ]
    lines += _classes_and_properties(release)
    return "\n".join(lines) + "\n"


def review_task(spec, intake, files, results, dm):
    from kpi_store.intake import rules
    lines = [
        "# The task",
        "",
        "Review a draft of a new module of the KPI Store's ontology. Another AI, of another model family, wrote it. "
        "Review it against the ontology skill above: its rules at every step, the Step 3 gate for classes and "
        "properties, the Step 9 gate for shapes, and the quality bar for definitions. Say whether it means what the "
        "form asks for, whether it reuses the release where it should, and whether a reader who has never built an "
        "ontology could rely on its summary.",
        "",
        "The form:",
        f"- The module's name: {spec['title']}",
        f"- What it covers: {spec['description']}",
        f"- The documents that describe it: {spec['citation']}",
        f"- What it must let people say: {''.join(rules.values(intake.answers, drafted.QUESTION)[:1])}",
        "",
        "The checks the command ran, and what each found:",
    ]
    for g in results:
        lines.append(f"- Gate {g['gate']}, {g['name']}: {'passed' if g['passed'] else 'FAILED'}")
        lines += [f"  - {r}" for r in g["results"]]
    lines += ["", "The draft's files:"]
    for name in dm.FILES:
        lines += ["", f"## {name}", "", files[name].rstrip("\n")]
    lines += [
        "",
        "Answer with JSON only, in exactly this form, with no other text:",
        '{"verdict": "PASS" or "HOLD", "findings": [{"gate": "<the rule or gate of the skill>", '
        '"finding": "<what is wrong or worth noting, in one or two plain sentences>"}]}',
        "Give HOLD when the draft breaks a rule of the skill or does not mean what the form asks for, with a finding "
        "for each reason. Give PASS when it does not; a finding may then note something the signers should know.",
    ]
    return "\n".join(lines) + "\n"


def parse_review(text):
    """(verdict, findings) of the reviewer's answer, checked strictly. Refuses the whole answer at the first problem."""
    body = text.strip()
    fenced = suggest.FENCE.fullmatch(body)
    if fenced:
        body = fenced.group(1).strip()
    try:
        data = json.loads(body)
    except ValueError as err:
        raise AIRefused(f"the reviewer's answer is not JSON ({err.msg}, line {err.lineno})") from None
    if not isinstance(data, dict) or set(data) != {"verdict", "findings"} or data["verdict"] not in approval.VERDICTS \
            or not isinstance(data["findings"], list):
        raise AIRefused('the reviewer\'s answer is not of the form {"verdict": "PASS" or "HOLD", "findings": [...]}')
    findings = []
    for n, f in enumerate(data["findings"], 1):
        if not isinstance(f, dict) or set(f) != {"gate", "finding"} or \
                not all(isinstance(f[k], str) and f[k].strip() for k in f):
            raise AIRefused(f"the reviewer's finding {n} does not hold exactly gate and finding, each in words")
        findings.append({"gate": f["gate"].strip(), "finding": f["finding"].strip()})
    if data["verdict"] == "HOLD" and not findings:
        raise AIRefused("the reviewer gives HOLD with no finding, so nobody can tell what to fix")
    return data["verdict"], findings


def _answer(ai, system, user, answer_file, environ, opener, table, say, what):
    """(text, model version, endpoint, SHA-256 of the answer) from the answer file of a by-hand provider, or from one
    call to the provider."""
    if ai.provider == "by-hand":
        try:
            raw = Path(answer_file).read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise AIRefused(f"the answer file {answer_file} cannot be read ({type(err).__name__})") from None
        say(f"read the {what} of {ai.assistant} from {Path(answer_file).as_posix()}")
        return text, "", "", hashlib.sha256(raw).hexdigest()
    say(f"asked {ai.provider} (model {ai.model}) for the {what}")
    kwargs = {"opener": opener} if opener else {}
    try:
        reply = providers.ask(ai, system, user, environ, max_tokens=MAX_TOKENS, **kwargs)
    except AIRefused as err:
        raise AIRefused(str(err).replace("[ai]", f"[{table}]")) from None
    return reply.text, reply.model_version, reply.endpoint, suggest.sha256(reply.text)


def _step(ai, version, endpoint, skills, prompt, output, today):
    return {"provider": ai.provider, "assistant": ai.assistant, "family": ai.family, "model": ai.model,
            "model_version": version, "endpoint": endpoint, "approved_by": ai.approved_by, "approved_on": ai.approved_on,
            "asked_on": today, "skills": skills, "prompt_sha256": suggest.sha256(prompt), "output_sha256": output}


def _write_prompt(path, suffix, prompt, ai, flag, answer_suffix, say):
    written = suggest.beside(path, suffix)
    with written.open("w", encoding="utf-8", newline="\n") as f:
        f.write(prompt)
    say(f"wrote the prompt for the AI: {written.as_posix()}")
    say(f"Give that file to {ai.assistant}. Save its answer, the JSON it writes, in a file such as "
        f"{suggest.beside(path, answer_suffix).as_posix()}. Then run this command again with {flag} <that file>.")


def _say_gates(results, say):
    for g in results:
        say(f"gate {g['gate']}, {g['name']}: {'passed' if g['passed'] else 'FAILED'}")
        if not g["passed"]:
            for line in g["results"]:
                say(f"  {line}")


def signers_summary(spec, files, record, root):
    """The text of <form>.draft-summary.txt: what the signers read before they sign."""
    lines = [f'The AI draft of the new module "{spec["title"]}" ({spec["module"]})', "",
             f"What it covers: {spec['description']}", f"The documents it rests on: {spec['citation']}", ""]
    lines += drafted.summary_lines(spec, files, record, root)
    reviewer = record["reviewer"]
    lines += ["", f"The reviewer's verdict: {reviewer['verdict']}."]
    lines += [f"  - {f['gate']}: {f['finding']}" for f in reviewer["findings"]] or ["  It noted nothing."]
    lines += ["", "When you sign the form, you accept this draft whole. Gate 5: the Ontology Owner signs, and the "
              f"module's first release is {new_module.VERSION}, a major.", ""]
    return "\n".join(lines)


def run(form_path, release_root=".", stores=None, answer_file=None, review_file=None, drafter=None, reviewer=None,
        today=None, environ=None, say=print, opener=None):
    """The AI draft for one form, steps 1 to 5 of the module's docstring. Returns the record's path when the draft has
    been reviewed, or None when it wrote a by-hand prompt and stops there. `drafter` and `reviewer` replace the
    settings that `stores` names."""
    from kpi_store.intake import answers
    root = Path(release_root).resolve()
    path = Path(form_path)
    if drafter is None or reviewer is None:
        found = _settings(stores, root, environ)
        drafter, reviewer = drafter or found[0], reviewer or found[1]
    drafter, reviewer = providers_of(drafter, reviewer)
    if path.suffix.lower() != ".json":
        raise AIRefused(f"{path.name} is not a form saved as JSON. --ai-draft takes the answers file the HTML form saves")
    try:
        intake = answers.read_json(path)
    except answers.AnswersError as err:
        raise AIRefused(f"{path.name} cannot be read: {err}") from None
    if intake.form != "new-module":
        raise AIRefused(f"{path.name} is a {intake.form} form. --ai-draft takes a new-module form whose N3 is "
                        "\"Something else\"")
    signed = sorted(k for k, v in intake.sign_offs.items() if v.get("name", "").strip() or v.get("date", "").strip())
    if signed:
        raise AIRefused(f"{path.name} is signed already ({', '.join(signed)}). The AI drafts before anyone signs, so "
                        "that each signer reads the draft. Clear the sign-off first")
    today = today or dt.date.today().isoformat()
    record_path, folder = suggest.beside(path, drafted.RECORD_SUFFIX), suggest.beside(path, drafted.FOLDER_SUFFIX)
    dm = drafted.pattern(root)
    try:
        release = new_module.Release(root)
        spec = drafted.spec_of_form(intake.answers, root, release)
    except ChangeRefused as err:
        raise AIRefused(str(err)) from None
    if record_path.exists():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            approval.check_draft(record, signed=False)
        except (OSError, UnicodeDecodeError, ValueError, ChangeRefused) as err:
            raise AIRefused(f"the record of the AI draft {record_path.name} cannot be used ({err})") from None
        if record["reviewer"] is not None:
            raise AIRefused(f"{record_path.name} exists: this form has its reviewed AI draft. To ask again, delete it and "
                            f"the folder {folder.name} first")
        if answer_file:
            raise AIRefused(f"the draft exists already ({folder.name}). Give the reviewer's answer with --review-answer")
        if record["form_sha256"] != drafted.answers_sha256(intake.answers):
            raise AIRefused("the form's answers changed after the AI drafted the module. Delete "
                            f"{record_path.name} and the folder {folder.name}, and ask again")
        try:
            files = drafted.read_files(folder, root)
        except ChangeRefused as err:
            raise AIRefused(str(err)) from None
        if drafted.parts(files) != record["parts"]:
            raise AIRefused(f"a file of {folder.name} changed after the AI drafted it. Delete {record_path.name} and the "
                            "folder, and ask again")
        spec = record["module"]
        if record["drafter"]["family"].strip().casefold() == reviewer.family.strip().casefold():
            raise AIRefused(f'the draft was made by a model of the family "{record["drafter"]["family"]}", and '
                            "[ai_reviewer] names the same family. Gate 3 needs a reviewer of another family")
        if not all(g["passed"] for g in record["gates"]) or sorted(g["gate"] for g in record["gates"]) != [1, 2, 4]:
            raise AIRefused(f"{record_path.name} does not show gates 1, 2 and 4 passed, so the draft goes to no reviewer. "
                            f"Delete it and the folder {folder.name}, and ask again")
    else:
        if review_file:
            raise AIRefused("--review-answer comes after the draft: run the command first without it")
        if answer_file and drafter.provider != "by-hand":
            raise AIRefused(f'--ai-answer is for a by-hand drafter, and [ai] names "{drafter.provider}"')
        if folder.exists():
            raise AIRefused(f"the folder {folder.name} is in the way, with no record beside it. Move it, then run the "
                            "command again")
        system, skills = suggest.instructions(root, DRAFT_SKILLS)
        user = draft_task(spec, intake, release, dm)
        prompt = system + "\n\n" + user
        if drafter.provider == "by-hand" and not answer_file:
            _write_prompt(path, DRAFT_PROMPT, prompt, drafter, "--ai-answer", DRAFT_ANSWER, say)
            return None
        text, version, endpoint, output = _answer(drafter, system, user, answer_file, environ, opener, "ai", say, "draft")
        try:
            spec, files = drafted.from_answer(text, spec, root, release)
            results = drafted.gates(spec, files, root)
        except ChangeRefused as err:
            raise AIRefused(f"the draft cannot be used: {err}. Nothing was kept") from None
        _say_gates(results, say)
        failed = [g["gate"] for g in results if not g["passed"]]
        if failed:
            raise AIRefused(f"the draft did not pass gate {', '.join(map(str, failed))}, as the lines above say. Nothing "
                            "was kept. Ask again, and give the AI those lines")
        record = {"format": 1, "form": intake.form, "module": spec, "form_sha256": drafted.answers_sha256(intake.answers),
                  "drafter": _step(drafter, version, endpoint, skills, prompt, output, today), "reviewer": None,
                  "parts": drafted.parts(files), "gates": results}
        approval.check_draft(record, signed=False)
        folder.mkdir()
        for name, content in files.items():
            with (folder / name).open("w", encoding="utf-8", newline="\n") as f:
                f.write(content)
        suggest._write_whole(record_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        say(f"wrote the draft: {folder.as_posix()}, and its record: {record_path.as_posix()}")
    # The review (gate 3).
    if review_file and reviewer.provider != "by-hand":
        raise AIRefused(f'--review-answer is for a by-hand reviewer, and [ai_reviewer] names "{reviewer.provider}"')
    system, skills = suggest.instructions(root, REVIEW_SKILLS)
    user = review_task(spec, intake, files, record["gates"], dm)
    prompt = system + "\n\n" + user
    if reviewer.provider == "by-hand" and not review_file:
        _write_prompt(path, REVIEW_PROMPT, prompt, reviewer, "--review-answer", REVIEW_ANSWER, say)
        return None
    text, version, endpoint, output = _answer(reviewer, system, user, review_file, environ, opener, "ai_reviewer", say,
                                              "review")
    verdict, findings = parse_review(text)
    review = dict(_step(reviewer, version, endpoint, skills, prompt, output, today), verdict=verdict, findings=findings)
    gate3 = {"gate": 3, "name": dm.GATE_NAMES[3], "passed": verdict == "PASS",
             "results": [f"{reviewer.assistant if reviewer.provider == 'by-hand' else reviewer.model} "
                         f"({reviewer.family}) gives {verdict}"] + [f"{f['gate']}: {f['finding']}" for f in findings]}
    record = dict(record, reviewer=review, gates=sorted(record["gates"] + [gate3], key=lambda g: g["gate"]))
    try:
        approval.check_draft(record, signed=False)
    except ChangeRefused as err:
        raise AIRefused(str(err)) from None
    suggest._write_whole(record_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    summary = suggest.beside(path, SIGNERS_SUMMARY)
    suggest._write_whole(summary, signers_summary(spec, files, record, root))
    say(f"gate 3, {dm.GATE_NAMES[3]}: {'passed' if verdict == 'PASS' else 'FAILED'} ({verdict})")
    for f in findings:
        say(f"  {f['gate']}: {f['finding']}")
    say(f"wrote the record of the review: {record_path.as_posix()}")
    say(f"wrote the summary for the signers: {summary.as_posix()}")
    if verdict == "HOLD":
        say("The reviewer holds the draft, so the propose command will refuse this form. Fix what the findings say in "
            f"the form, delete {record_path.name} and the folder {folder.name}, and ask again.")
    else:
        say("Next: the signers read the summary and sign the form: the Data Owner, the Ontology Owner and the Architect. "
            f"Then turn it into a proposal with: python -m kpi_store.propose {path.as_posix()}")
    return record_path
