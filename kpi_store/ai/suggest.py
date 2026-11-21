"""AI suggestions for the answers of one form (KPI-DEC-0002, Q16, Q17(b), Q20 and Q26).

    python -m kpi_store.propose --ai <form.json> [--stores <local settings>] [--ai-answer <file>] [--ai-choices <file>]

The order. A signer must see an accepted change before signing it, and a form's sign-off is the names and dates in
the answers file. So the suggestions come before anyone signs:

1. The form is filled, saved as JSON from the HTML form, and not signed. A form that holds a signature is refused.
2. propose --ai sends the provider the form's answers that a person wrote in words (the questions of type text,
   long_text and list) and its choices of a measure or a process, with the names of what the release holds that
   the form may match: its measures and processes, and for some forms its systems, roles or terms. The
   instructions are the release's own skills, read from skills/ at run time: ontology, for what the release holds
   and how a definition is written, then clear-writing, for the words (Q26).
3. The answer must be JSON of one exact form, checked strictly here: for each suggestion the question, the answer
   as the form holds it now, the suggested answer and the reason. An answer that is not that JSON, or that names
   another answer than the form holds, is refused whole, and nothing changes.
4. The person accepts or rejects each suggestion at the terminal, or in a choices file ({"T3": "yes", "T2": "no"}).
   Each accepted suggestion replaces its answer in the form's file. Nothing else in the file changes.
5. The command writes the record of the AI step beside the form, as <form>.ai.json: the provider, the assistant,
   the model and its version, the IT approval, the skill files and their SHA-256, the SHA-256 of the prompt, the
   SHA-256 of the AI's answer, the endpoint it called, and every suggestion with whether the person accepted it (Q20).
   The record keeps no prompt text, since the prompt holds the form's answers before signing: prompt_sha256 is the
   SHA-256 of the system prompt, a blank line and the task, the exact text of the by-hand prompt file.
6. The signers read the form as it now stands and sign it. Then the plain propose command checks the form as it
   checks every form. It finds the record beside the form, and keeps it in the proposal's approval.json and in
   summary.txt, adding to each suggestion whether the signed form still holds it. The apply command keeps the same
   record in the release's approval record.

The by-hand provider makes no call. Step 2 writes the whole prompt, the skills and the task, to <form>.ai-prompt.txt
and stops. The person gives the file to an assistant, such as Genie Code, saves its answer to a file, and runs
the command again with --ai-answer <that file>; steps 3 to 6 are then the same.

Without --ai, and with no record beside the form, the propose command is exactly as it was.
"""
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from kpi_store.change import approval

from . import AIRefused, providers

SKILLS = ("skills/ontology/SKILL.md", "skills/clear-writing/SKILL.md")
TEXT_TYPES, LIST_TYPE, CHOICE_TYPE = ("text", "long_text"), "list", "choice"
CHOICE_LISTS = ("measures", "processes")       # the lists a suggested choice may come from
# The names of what the release holds that each form's answers may match.
RELEVANT = {"kpi-intake": ("measures", "processes"), "term-change": ("measures", "processes"),
            "reference-item": ("systems",), "domain-activation": ("measures", "processes"),
            "process-map-request": ("processes", "roles"), "new-module": ("terms",)}
LIST_TITLES = {"measures": "The measures the release holds (name, short key: definition)",
               "processes": "The processes and steps of the process map", "systems": "The systems the release holds",
               "roles": "The roles the organization module holds", "terms": "The terms the release holds"}
RECORD_SUFFIX, PROMPT_SUFFIX, ANSWER_SUFFIX = ".ai.json", ".ai-prompt.txt", ".ai-answer.json"
FENCE = re.compile(r"```[A-Za-z]*\s*\n(.*)\n```", re.S)
YES, NO = ("yes", "y"), ("no", "n")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def beside(form_path, suffix):
    """A file beside the form, named by the form's name without .json and the suffix."""
    path = Path(form_path)
    return path.with_name(path.stem + suffix)


def instructions(root, names=SKILLS):
    """The system prompt, the release's skill files one after the other, and [{path, sha256}] of each file."""
    texts, hashes = [], []
    for name in names:
        try:   # bytes, so that the fingerprint is the file's own whatever its line ends
            raw = (Path(root) / name).read_bytes()
            texts.append(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError):
            raise AIRefused(f"the release has no readable {name}, the skill the AI follows") from None
        hashes.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest()})
    return "\n\n".join(texts), hashes


def _choices(lists, source):
    """{folded name: (name, id)} of the entries of one pick list that the form offers."""
    return {i["label"].casefold(): (i["label"], i["id"]) for i in lists.get(source, []) if not i.get("hidden")}


def questions(cat, lists, intake):
    """The questions the AI may suggest a new answer for: {id: (type, the question, its list, the answer now as the
    prompt gives it)}. A choice's answer is the name of the chosen entry."""
    out = {}
    for q in cat.questions_of(intake.form):
        kind, source = q["type"], q.get("source", "")
        value = intake.answers.get(q["id"])
        if kind in TEXT_TYPES:
            now = value if isinstance(value, str) else "\n".join(value or [])
        elif kind == LIST_TYPE:
            now = [value] if isinstance(value, str) and value else list(value or [])
        elif kind == CHOICE_TYPE and source in CHOICE_LISTS and source in RELEVANT.get(intake.form, ()):
            names = {i: n for n, i in _choices(lists, source).values()}
            now = names.get(value, value) if isinstance(value, str) else ""
        else:
            continue
        out[q["id"]] = (kind, q["text"], source if kind == CHOICE_TYPE else "", now)
    return out


def _names(form, lists, terms):
    lines = []
    for name in RELEVANT.get(form, ()):
        if name == "terms":
            entries = sorted({t["names"][0] for t in terms if t.get("names")})
        elif name == "measures":
            entries = [f'{m["label"]} ({m["notation"]}): {m.get("definition", "")}' for m in lists.get("measures", [])
                       if not m.get("hidden")]
        else:
            entries = [i["label"] for i in lists.get(name, []) if not i.get("hidden")]
        lines += ["", f"{LIST_TITLES[name]}:"] + [f"- {e}" for e in entries]
    return lines


def task(cat, data, intake, asked):
    """The user message: what to do, the answer's form, the form's answers and the names the release holds."""
    from kpi_store.intake.catalogue import FORMS
    shown = [{"question": q, "type": kind, "asks": text, **({"list": source} if source else {}), "answer": now}
             for q, (kind, text, source, now) in asked.items()]
    lines = [
        "# The task",
        "",
        f"Suggest changes to the answers of one filled form of the KPI Store's intake pack: a {FORMS[intake.form]} "
        "form. Follow the instructions above: the ontology skill for what the release holds and how a definition is "
        "written, and the clear-writing skill for the words of each answer.",
        "",
        "1. Read each answer below.",
        "2. Suggest a change only when an answer is unclear, does not answer its question, or matches something the "
        "release holds already: one of the names listed below. Leave a good answer as it is.",
        "3. Write each suggestion as the whole new answer. Add no fact that the form does not give.",
        "4. Give the reason in one or two plain sentences. When the suggestion rests on something the release "
        "holds, name it.",
        "",
        "Answer with JSON only, in exactly this form, with no other text:",
        '{"suggestions": [{"question": "<the question\'s id>", "current": <the answer exactly as given below>, '
        '"suggested": <the new answer>, "reason": "<why, in one or two sentences>"}]}',
        "For a question of type text or long_text, an answer is a text. For type list, it is a list of texts. For "
        "type choice, it is the name of one entry of the list the question names, exactly as listed below. Give at "
        'most one suggestion for each question. When no answer needs a change, answer {"suggestions": []}.',
        "",
        "The questions and their answers, as JSON:",
        json.dumps(shown, ensure_ascii=False, indent=1),
    ]
    lines += _names(intake.form, data["lists"], data.get("terms", []))
    return "\n".join(lines) + "\n"


def parse(text, asked, lists):
    """The suggestions of the AI's answer, checked strictly: [{question, current, suggested, reason, answer}], where
    answer is the value the form takes when the suggestion is accepted. Refuses the whole answer at the first
    problem."""
    body = text.strip()
    fenced = FENCE.fullmatch(body)
    if fenced:
        body = fenced.group(1).strip()
    try:
        data = json.loads(body)
    except ValueError as err:
        raise AIRefused(f"the AI's answer is not JSON ({err.msg}, line {err.lineno})") from None
    if not isinstance(data, dict) or set(data) != {"suggestions"} or not isinstance(data["suggestions"], list):
        raise AIRefused('the AI\'s answer is not of the form {"suggestions": [...]}')
    out, seen = [], set()
    for n, item in enumerate(data["suggestions"], 1):
        where = f"the AI's suggestion {n}"
        if not isinstance(item, dict) or set(item) != {"question", "current", "suggested", "reason"}:
            raise AIRefused(f"{where} does not hold exactly question, current, suggested and reason")
        q = item["question"]
        if not isinstance(q, str) or q not in asked:
            raise AIRefused(f"{where} names the question {q!r}, which is not one the AI was asked about")
        if q in seen:
            raise AIRefused(f"{where} is a second suggestion for {q}")
        seen.add(q)
        kind, _, source, now = asked[q]
        if item["current"] != now:
            raise AIRefused(f"{where}, for {q}, gives another answer than the form holds as the answer now")
        new = item["suggested"]
        if kind in TEXT_TYPES or kind == CHOICE_TYPE:
            ok = isinstance(new, str) and new.strip() != ""
        else:
            ok = isinstance(new, list) and all(isinstance(v, str) and v.strip() for v in new)
        if not ok:
            what = "a list of texts" if kind == LIST_TYPE else "a text that is not empty"
            raise AIRefused(f"{where}, for {q}, must suggest {what}")
        answer = new
        if kind == CHOICE_TYPE:   # the entry's own name, so that a change of case alone is no change
            found = _choices(lists, source).get(new.casefold())
            if not found:
                raise AIRefused(f"{where}, for {q}, names \"{new}\", which is not an entry of the list {source}")
            new, answer = found
        if new == now:
            raise AIRefused(f"{where}, for {q}, suggests the answer the form holds already")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise AIRefused(f"{where}, for {q}, gives no reason")
        out.append({"question": q, "current": now, "suggested": new, "reason": item["reason"].strip(), "answer": answer})
    return out


def _shown(value):
    return json.dumps(value, ensure_ascii=False)


def choose(found, asked, choices_file=None, ask=input, say=print):
    """yes or no for each suggestion: from the choices file, else typed at the terminal. A list of booleans."""
    given = None
    if choices_file:
        try:
            given = json.loads(Path(choices_file).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as err:
            raise AIRefused(f"the choices file {choices_file} cannot be read as JSON ({type(err).__name__})") from None
        wanted = {s["question"] for s in found}
        if not isinstance(given, dict) or set(given) != wanted or \
                not all(isinstance(v, str) and v.strip().lower() in YES + NO for v in given.values()):
            raise AIRefused(f"the choices file {choices_file} must give yes or no for exactly the questions "
                            f"{', '.join(sorted(wanted)) or '(none)'}, as {{\"<question>\": \"yes\"}}")
    out = []
    for n, s in enumerate(found, 1):
        say(f"Suggestion {n} of {len(found)}, for {s['question']}: {asked[s['question']][1]}")
        say(f"  The answer now: {_shown(s['current'])}")
        say(f"  The suggestion: {_shown(s['suggested'])}")
        say(f"  Why: {s['reason']}")
        if given is not None:
            word = given[s["question"]].strip().lower()
            say(f"  Your choice, from {Path(choices_file).name}: {word}")
        else:
            word = ""
            while word not in YES + NO:
                try:
                    word = ask("Accept this suggestion? Type yes or no: ").strip().lower()
                except EOFError:
                    raise AIRefused("no choice was typed for a suggestion. Run the command in a "
                                    "terminal, or give the choices with --ai-choices <file>") from None
        out.append(word in YES)
    return out


def _write_whole(path, text):
    """Writes the text to <name>.tmp, then puts that file in the place of <name>, so that no part of a file ever has
    the real name. Refuses when <name>.tmp exists already, and removes only the .tmp file it wrote."""
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise FileExistsError(f"{tmp.name} is in the way: move it, then run the command again")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _settings(stores, root, environ):
    """[ai] of the local settings file, refused when the file is inside the release folder the command was given."""
    from kpi_store import local_settings
    try:
        return local_settings.load(local_settings.locate(stores, environ), environ=environ, release_root=root).ai
    except local_settings.LocalSettingsError as err:
        raise AIRefused(f"the local settings that name the AI provider cannot be read: {err}") from None


def run(form_path, release_root=".", stores=None, answer_file=None, choices_file=None, ai=None, today=None,
        environ=None, ask=input, say=print, opener=None):
    """The AI step for one form, steps 1 to 5 of the module's docstring. Returns the record's path, or None when it
    wrote the by-hand prompt and stops there. `ai` replaces the settings that `stores` names."""
    from kpi_store.intake import answers, catalogue, picklists
    root = Path(release_root).resolve()
    path = Path(form_path)
    ai = providers.ready(ai if ai is not None else _settings(stores, root, environ))
    if path.suffix.lower() != ".json":
        raise AIRefused(f"{path.name} is not a form saved as JSON. --ai takes the answers file the HTML form saves, "
                        "so that the accepted suggestions can go back into it")
    try:
        intake = answers.read_json(path)
    except answers.AnswersError as err:
        raise AIRefused(f"{path.name} cannot be read: {err}") from None
    signed = sorted(k for k, v in intake.sign_offs.items() if v.get("name", "").strip() or v.get("date", "").strip())
    if signed:
        raise AIRefused(f"{path.name} is signed already ({', '.join(signed)}). AI suggestions come before anyone "
                        "signs, so that each signer reads the answers the AI changed. Clear the sign-off, or "
                        "propose the form without --ai")
    record_path = beside(path, RECORD_SUFFIX)
    if record_path.exists():
        raise AIRefused(f"{record_path.name} exists: this form has had its AI step. One form takes one AI step. To "
                        "ask again, delete that record first")
    if answer_file and ai.provider != "by-hand":
        raise AIRefused(f'--ai-answer is for the by-hand provider, and the local settings name "{ai.provider}"')
    try:
        cat, data = catalogue.load(root / "kpi-intake"), picklists.load(root / "kpi-intake")
    except Exception as err:   # the catalogue's and the pick lists' own errors say what is wrong
        raise AIRefused(f"the KPI intake pack cannot be read: {err}") from None
    asked = questions(cat, data["lists"], intake)
    system, skills = instructions(root)
    user = task(cat, data, intake, asked)
    prompt = system + "\n\n" + user
    if ai.provider == "by-hand" and not answer_file:
        written = beside(path, PROMPT_SUFFIX)
        with written.open("w", encoding="utf-8", newline="\n") as f:
            f.write(prompt)
        say(f"wrote the prompt for the AI: {written.as_posix()}")
        say(f"Give that file to {ai.assistant}. Save its answer, the JSON it writes, in a file such as "
            f"{beside(path, ANSWER_SUFFIX).as_posix()}. Then run this command again with --ai-answer <that file>.")
        return None
    if ai.provider == "by-hand":
        try:
            raw = Path(answer_file).read_bytes()
            text, version, endpoint, output = raw.decode("utf-8"), "", "", hashlib.sha256(raw).hexdigest()
        except (OSError, UnicodeDecodeError) as err:
            raise AIRefused(f"the answer file {answer_file} cannot be read ({type(err).__name__})") from None
        say(f"read the answer of {ai.assistant} from {Path(answer_file).as_posix()}")
    else:
        say(f"asked {ai.provider} (model {ai.model}) for suggestions on {path.name}")
        kwargs = {"opener": opener} if opener else {}
        reply = providers.ask(ai, system, user, environ, **kwargs)
        text, version, endpoint, output = reply.text, reply.model_version, reply.endpoint, sha256(reply.text)
    found = parse(text, asked, data["lists"])
    say(f"the AI suggested {len(found)} change{'s' if len(found) != 1 else ''}")
    accepted = choose(found, asked, choices_file, ask, say) if found else []
    record = {"format": 1, "form": intake.form, "provider": ai.provider, "assistant": ai.assistant,
              "model": ai.model, "model_version": version, "endpoint": endpoint, "approved_by": ai.approved_by,
              "approved_on": ai.approved_on, "asked_on": today or dt.date.today().isoformat(), "skills": skills,
              "prompt_sha256": sha256(prompt), "output_sha256": output,
              "suggestions": [dict(s, accepted=a) for s, a in zip(found, accepted)]}
    approval.check_ai(record, step=True)
    # The record first, then the form, each written whole (_write_whole). If the form cannot be written, the record
    # goes too, so a record is beside a form only when the form holds what the record says.
    _write_whole(record_path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    if any(accepted):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for s, a in zip(found, accepted):
                if a:
                    data["answers"][s["question"]] = s["answer"]
            _write_whole(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            with contextlib.suppress(OSError):
                record_path.unlink()
            raise
    took = sum(accepted)
    say(f"accepted {took} of {len(found)} suggestion{'s' if len(found) != 1 else ''}" +
        (f"; wrote {'it' if took == 1 else 'them'} into {path.name}" if took else "; the form is as it was"))
    say(f"wrote the record of the AI step: {record_path.as_posix()}")
    say("Next: the signers read the form as it now stands and sign it. Then turn it into a proposal with: "
        f"python -m kpi_store.propose {path.as_posix()}")
    return record_path


def audit(form_path, intake):
    """The record of the AI step of one signed form, for its approval record, or None when the form had none. Each
    suggestion gains `kept`: whether the signed form holds its answer."""
    path = beside(form_path, RECORD_SUFFIX)
    if Path(form_path).suffix.lower() != ".json" or not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise AIRefused(f"the record of the AI step {path.name} cannot be read ({type(err).__name__})") from None
    try:
        approval.check_ai(record, step=True)
    except Exception as err:
        raise AIRefused(f"the record of the AI step {path.name} is not complete: {err}") from None
    if record["form"] != intake.form:
        raise AIRefused(f"the record of the AI step {path.name} is for a {record['form']} form, and "
                        f"{Path(form_path).name} is a {intake.form} form")

    def held(s):
        value = intake.answers.get(s["question"], "" if isinstance(s["answer"], str) else [])
        return value == s["answer"]
    record["suggestions"] = [dict(s, kept=held(s)) for s in record["suggestions"]]
    return record


def summary_lines(record):
    """The lines summary.txt gives the AI step, in plain words."""
    who = record["assistant"] if record["provider"] == "by-hand" else f"{record['provider']}, model {record['model']}"
    out = [f"AI suggestions: {who} was asked on {record['asked_on']}, with the provider approved by "
           f"{record['approved_by']} on {record['approved_on']}."]
    if not record["suggestions"]:
        out.append("  - It suggested no change.")
    for s in record["suggestions"]:
        if s["accepted"]:
            kept = "the signed form holds it" if s["kept"] else "a person changed it again before signing"
            out.append(f"  - {s['question']}, accepted ({kept}): {_shown(s['suggested'])}. Why: {s['reason']}")
        else:
            out.append(f"  - {s['question']}, rejected: {_shown(s['suggested'])}. Why: {s['reason']}")
    out.append('  The whole record, with its fingerprints, is in approval.json under "ai".')
    return out
