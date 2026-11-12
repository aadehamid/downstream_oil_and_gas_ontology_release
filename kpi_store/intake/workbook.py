"""The Excel form: write it from the catalogue, read a filled one back, and compare two workbooks by content.

The workbook has a Start sheet, one sheet per section of the KPI form, a Sign-off sheet, one sheet for each of the
two smaller forms (Domain activation and Process map request), a Roles sheet and a hidden lists sheet that the
dropdowns read. On a section sheet the columns are: number, question, asked of,
answer (the cell to fill), why we ask, example. Column G is hidden and holds each row's key, for example "6.1#2"
for the second answer to 6.1 or "3.5.detail" for the extra text of 3.5. The reader finds an answer by its key, so
a person may sort or widen the sheet without breaking it, and must not delete column G.

A choice cell holds the label a person sees. The reader turns it back into the item's id. A label it does not
know stays as typed, and the check then reports it. A dropdown does not offer an entry that the organization's
settings hide. A cell that already holds one keeps it, with the mark in its label, and the reader still knows it.
The blank form starts a question that has a default with that answer.

Two builds of the same content are not the same bytes, because the file format stores the time of writing. So
same_content() compares what matters: the sheet names and their visibility, every cell's value, the dropdowns and
the hidden columns. Needs openpyxl.
"""
import datetime
import io
import re
from pathlib import Path

from kpi_store.intake import rules
from kpi_store.intake.answers import AnswersError, Intake
from kpi_store.intake.catalogue import ADDED_MARK, CHOICE_TYPES, DEFAULT_ROWS, FORMS, HIDDEN_MARK, MANY_TYPES

START, SIGN_OFF, ROLES, LISTS = "Start", "Sign-off", "Roles", "lists"
OTHER_FORMS = [f for f in FORMS if f != "kpi-intake"]    # each has one sheet, named as FORMS names it
HEADERS = ("No.", "Question", "Asked of", "Answer", "Why we ask", "Example answer")
ANSWER_COLUMN, SECOND_COLUMN, KEY_COLUMN = 4, 5, 7     # D holds the answer, E a second value, G the row's key
WIDTHS = {"A": 11, "B": 52, "C": 22, "D": 48, "E": 40, "F": 48}
FIXED_DATE = datetime.datetime(2026, 11, 11)           # the file's own "created" date, so it does not change per build


def sheet_title(section):
    """A section's sheet name: its number and name, without the characters a sheet name may not hold."""
    name = re.sub(r"\s*\(.*?\)", "", section["name"])
    return re.sub(r"[\[\]:*?/\\]", "", f'{section["id"]} {name}')[:31]


def _rows_of(cat, question):
    """The answer rows of a question: (key, number shown, text shown)."""
    rows = []
    if question["type"] in MANY_TYPES:
        count = question.get("rows") or cat.by_id.get(question.get("per"), {}).get("rows") or DEFAULT_ROWS
        for n in range(1, count + 1):
            text = question["text"] if n == 1 else f'Another answer to {question["id"]}'
            if "per" in question:
                text = question["text"] if n == 1 else f'{question["id"]} for answer {n} of {question["per"]}'
            rows.append((f'{question["id"]}#{n}', f'{question["id"]} ({n})', text))
    else:
        rows.append((question["id"], question["id"], question["text"]))
    if question.get("detail"):
        rows.append((question["id"] + ".detail", f'{question["id"]} (more)', question["detail"]["label"]))
    return rows


def build(cat, lists, examples=None, intake=None, others=None):
    """The workbook. With an Intake, its answers fill the KPI form's cells; `others` fills the smaller forms'
    sheets: {form: Intake}. `examples` gives the example column: {question id: text}."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    examples = examples or {}
    wb = Workbook()
    wb.properties.creator = "KPI Store"
    wb.properties.created = wb.properties.modified = FIXED_DATE
    bold, wrap = Font(bold=True), Alignment(wrap_text=True, vertical="top")
    fill = PatternFill("solid", fgColor="FFF8DC")       # marks the cells a person fills
    head_fill = PatternFill("solid", fgColor="E8EEF4")

    def setup(ws):
        for letter, width in WIDTHS.items():
            ws.column_dimensions[letter].width = width
        ws.column_dimensions[get_column_letter(KEY_COLUMN)].hidden = True

    def put(ws, row, column, value, style=None, answer=False):
        cell = ws.cell(row=row, column=column, value=value if value != "" else None)
        cell.alignment = wrap
        if style:
            cell.font = style
        if answer:
            cell.fill = fill
        return cell

    def header(ws, row, titles):
        for column, title in enumerate(titles, 1):
            if title:
                put(ws, row, column, title, bold).fill = head_fill

    # The lists sheet: one column for each choice question, holding the labels its dropdown offers.
    lists_ws = wb.active
    lists_ws.title = LISTS
    ranges = {}
    choice_questions = [q for q in cat.questions if q["type"] in CHOICE_TYPES]
    for column, question in enumerate(choice_questions, 1):
        labels = [o["label"] for o in rules.options(cat, lists, question)]
        lists_ws.cell(row=1, column=column, value=question["id"])
        for row, label in enumerate(labels, 2):
            lists_ws.cell(row=row, column=column, value=label)
        letter = get_column_letter(column)
        ranges[question["id"]] = f"={LISTS}!${letter}$2:${letter}${len(labels) + 1}"

    def label_of(question, value):
        offered = {o["id"]: o["label"] for o in rules.options(cat, lists, question, hidden=True)}
        return offered.get(value) or rules.aliases(lists, question).get(value, {}).get("label", value)

    def section_rows(ws, row, section, held):
        """The rows of one section, from `row` on. Returns the next free row."""
        put(ws, row, 1, f'{section["id"]}. {section["name"]}' if section["form"] == "kpi-intake" else section["name"], Font(bold=True, size=14))
        for label, key in (("What this section is for", "about"), ("Who takes part", "who"), ("Done when", "done_when"), ("Warning for IT", "warning")):
            if section.get(key):
                row += 1
                put(ws, row, 1, label, bold)
                put(ws, row, 2, section[key])
                ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
                ws.row_dimensions[row].height = 15 * max(1, len(section[key]) // 150 + 1)
        row += 2
        header(ws, row, HEADERS)
        validations = {}
        for question in cat.questions_of(section=section["id"]):
            answer = rules.positions(held, question["id"])
            for n, (key, number, text) in enumerate(_rows_of(cat, question)):
                row += 1
                first = n == 0
                put(ws, row, 1, number)
                put(ws, row, 2, text + ("\n" + question["note"] if first and question.get("note") else ""))
                put(ws, row, 3, cat.asked_of(question) + "\n" + cat.requirement(question) if first else "")
                put(ws, row, 5, question["why"] if first else "")
                put(ws, row, 6, examples.get(question["id"], "") if first else "")
                put(ws, row, KEY_COLUMN, key)
                if key.endswith(".detail"):
                    value = "".join(rules.values(held, key)[:1])
                else:
                    value = answer[n] if n < len(answer) else ""
                    if not value and blank and question.get("default"):
                        value = question["default"]
                    if question["type"] in CHOICE_TYPES:
                        value = label_of(question, value) if value else ""
                        validations.setdefault(question["id"], []).append(f"D{row}")
                put(ws, row, ANSWER_COLUMN, value, answer=True)
        for question_id, cells in validations.items():
            dv = DataValidation(type="list", formula1=ranges[question_id], allow_blank=True)
            dv.error, dv.errorTitle = "Choose an answer from the list.", "Not in the list"
            dv.sqref = " ".join(cells)
            ws.add_data_validation(dv)
        return row + 1

    def sign_rows(ws, row, form, held):
        header(ws, row, ("Signs", "What the signature means", "Required", "Name", "Date"))
        for signer in cat.signers(form):
            row += 1
            given = (held.sign_offs if held else {}).get(signer["id"], {})
            put(ws, row, 1, cat.roles[signer["role"]]["short"])
            meaning = signer.get("activation_meaning") if form == "domain-activation" and signer.get("activation_meaning") else signer["meaning"]
            put(ws, row, 2, f'"{meaning}"')
            put(ws, row, 3, signer["required"])
            put(ws, row, ANSWER_COLUMN, given.get("name", ""), answer=True)
            put(ws, row, SECOND_COLUMN, given.get("date", ""), answer=True)
            put(ws, row, KEY_COLUMN, "sign:" + signer["id"])
        return row + 1

    # Start
    ws = wb.create_sheet(START)
    setup(ws)
    put(ws, 1, 1, "KPI intake form", Font(bold=True, size=16))
    notes = [
        f'{cat.release}, catalogue {cat.version}. One workbook is for one KPI.',
        "Fill in the yellow cells. Sections 1 to 6 are for the business. Section 7 is for Digital IT, after the business has signed.",
        "Where a cell has a dropdown, choose from it. If the right answer is not in the list, choose \"Not in the list\".",
        "A question with several answers has several rows. Use one row for each answer and leave the others empty.",
        "Leave a question empty when its rule in the \"Asked of\" column says it does not apply.",
        "Check the filled workbook with: py -m kpi_store.intake check <this file>",
    ]
    for row, note in enumerate(notes, 2):
        put(ws, row, 1, note)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    row = len(notes) + 3
    header(ws, row, ("The request", "", "", "Answer"))
    request = intake.request if intake else {}
    for item in cat.request_fields:
        row += 1
        put(ws, row, 1, item["label"])
        put(ws, row, ANSWER_COLUMN, request.get(item["id"], ""), answer=True)
        put(ws, row, KEY_COLUMN, "req:" + item["id"])
    row += 1
    put(ws, row, 1, "Comment")
    put(ws, row, ANSWER_COLUMN, intake.comment if intake else "", answer=True)
    put(ws, row, KEY_COLUMN, "comment")
    row += 1
    put(ws, row, 1, "Example of")
    put(ws, row, 2, "Leave this empty. Only the shipped examples fill it.")
    put(ws, row, ANSWER_COLUMN, intake.example_of if intake else "")
    put(ws, row, KEY_COLUMN, "example_of")

    held = intake.answers if intake else {}
    blank = intake is None      # only the blank form starts with the default answers
    for section in cat.sections:
        if section["form"] != "kpi-intake":
            continue
        ws = wb.create_sheet(sheet_title(section))
        setup(ws)
        section_rows(ws, 1, section, held)

    ws = wb.create_sheet(SIGN_OFF)
    setup(ws)
    put(ws, 1, 1, "Sign-off", Font(bold=True, size=14))
    put(ws, 2, 1, cat.sign_off["intro"])
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=6)
    ws.row_dimensions[2].height = 45
    row = sign_rows(ws, 4, "kpi-intake", intake)
    row += 1
    put(ws, row, 1, "Two groups are consulted and do not sign. Record the date and the outcome of each.")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    row += 1
    header(ws, row, ("Consulted", "When", "", "Date", "Outcome"))
    for item in cat.sign_off["consulted"]:
        row += 1
        given = (intake.consulted if intake else {}).get(item["id"], {})
        put(ws, row, 1, item["who"])
        put(ws, row, 2, item["when_text"])
        put(ws, row, ANSWER_COLUMN, given.get("date", ""), answer=True)
        put(ws, row, SECOND_COLUMN, given.get("outcome", ""), answer=True)
        put(ws, row, KEY_COLUMN, "consult:" + item["id"])

    for form in OTHER_FORMS:
        filled = (others or {}).get(form)
        ws = wb.create_sheet(FORMS[form])
        setup(ws)
        row = 1
        for section in cat.sections:
            if section["form"] == form:
                row = section_rows(ws, row, section, filled.answers if filled else {}) + 1
        sign_rows(ws, row, form, filled)

    ws = wb.create_sheet(ROLES)
    setup(ws)
    header(ws, 1, ("Role", "Definition", "", "In the intake"))
    for row, role in enumerate(cat.roles.values(), 2):
        put(ws, row, 1, role["title"])
        put(ws, row, 2, role["definition"])
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        put(ws, row, 4, role["in_intake"])
        ws.row_dimensions[row].height = 15 * max(1, len(role["definition"]) // 70 + 1)

    # The lists sheet was made first so the dropdowns could name it. It goes last and is hidden.
    wb.move_sheet(LISTS, offset=len(wb.sheetnames) - 1)
    lists_ws.sheet_state = "hidden"
    wb.active = wb.sheetnames.index(START)
    return wb


def save(wb, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def snapshot(wb):
    """What two workbooks must agree on to be the same form."""
    out = []
    for ws in wb.worksheets:
        cells = {cell.coordinate: cell.value for row in ws.iter_rows() for cell in row if cell.value is not None}
        validations = sorted((str(dv.sqref), dv.type, dv.formula1) for dv in ws.data_validations.dataValidation)
        hidden = sorted(letter for letter, dim in ws.column_dimensions.items() if dim.hidden)
        out.append((ws.title, ws.sheet_state, cells, validations, hidden))
    return out


def _reloaded(wb):
    """The workbook as a reader gets it from a file."""
    from openpyxl import load_workbook
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return load_workbook(buffer)


def same_content(path, wb):
    """True when the workbook file at `path` holds the same content as `wb`."""
    from openpyxl import load_workbook
    path = Path(path)
    if not path.is_file():
        return False
    try:
        on_disk = load_workbook(path)
    except Exception:       # a damaged file is simply not the same
        return False
    return snapshot(on_disk) == snapshot(_reloaded(wb))


def label_ids(cat, lists, question):
    """{label: id} for every label a cell of this question may hold. A workbook filled before the settings changed
    holds the label of that time, so an entry is known by its label with and without its mark: the plain label of
    an entry that is hidden now, and the "new" label of an entry the ontology has since gained."""
    ids = {}
    offered = rules.options(cat, lists, question, hidden=True)
    for option in offered:
        ids[option["label"]] = option["id"]
    for option in offered:
        for mark in (HIDDEN_MARK, ADDED_MARK):
            if option["label"].endswith(mark):
                ids.setdefault(option["label"].removesuffix(mark), option["id"])
    for alias, item in rules.aliases(lists, question).items():
        ids.setdefault(item["label"] + ADDED_MARK, alias)
    return ids


def _text(value):
    """A cell's value as the text a person typed. A date cell gives its ISO date."""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat() if value.time() == datetime.time() else value.isoformat(sep=" ")
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read(path, cat, lists, form="kpi-intake"):
    """An Intake from a filled workbook: the KPI form, or the sheet of one of the smaller forms."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(Path(path), data_only=True)
    except Exception as e:
        raise AnswersError(f"{path} cannot be read as a workbook: {e}") from None
    if form == "kpi-intake":
        wanted = [START, SIGN_OFF] + [sheet_title(s) for s in cat.sections if s["form"] == form]
    else:
        wanted = [START, FORMS[form]]
    missing = [name for name in wanted if name not in wb.sheetnames]
    if missing:
        raise AnswersError(f"{path} is not a KPI intake workbook: it has no sheet named {', '.join(missing)}")
    intake = Intake(form=form, catalogue_version=cat.version)
    collected = {}
    for name in wanted:
        ws = wb[name]
        for row in ws.iter_rows(min_col=1, max_col=KEY_COLUMN):
            key = _text(row[KEY_COLUMN - 1].value)
            if not key:
                continue
            first, second = _text(row[ANSWER_COLUMN - 1].value), _text(row[SECOND_COLUMN - 1].value)
            if key.startswith("req:"):
                intake.request[key[4:]] = first
            elif key == "comment":
                intake.comment = first
            elif key == "example_of":
                intake.example_of = first
            elif key.startswith("sign:"):
                if first or second:
                    intake.sign_offs[key[5:]] = {"name": first, "date": second}
            elif key.startswith("consult:"):
                if first or second:
                    intake.consulted[key[8:]] = {"date": first, "outcome": second}
            else:
                base, _, index = key.partition("#")
                collected.setdefault(base, []).append((int(index) if index.isdigit() else 0, first))
    if not collected and form == "kpi-intake":
        raise AnswersError(f"{path} holds no answer rows: column G, which names each row, is missing or empty")
    for base, found in collected.items():
        question = cat.by_id.get(base.removesuffix(".detail"))
        texts = [text for _, text in sorted(found)]
        while texts and not texts[-1]:
            texts.pop()
        if question is None or cat.form_of(question) != form:
            if texts:
                intake.unknown_keys.append(base)
            continue
        if not texts:
            continue
        if base.endswith(".detail"):
            intake.answers[base] = texts[0]
            continue
        if question["type"] in CHOICE_TYPES:
            ids = label_ids(cat, lists, question)
            texts = [ids.get(text, text) for text in texts]
        intake.answers[base] = rules.as_answer(question, texts)
    intake.kpi_name = "".join(rules.values(intake.answers, "2.1")[:1])
    if form != "kpi-intake":      # the Start sheet's comment and example mark belong to the KPI form
        intake.comment = intake.example_of = ""
    return intake
