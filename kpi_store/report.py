"""The discovery report: its format, and how to write, read and validate it.

One JSON file, discovery-report.json, holds the run and its rows. discovery-report.csv holds the same rows for a
person to read and to clear. A person clears a row by writing a decision; the report is cleared when every row
that blocks has one.

Where it sits: the report is the one file that passes between the three parts of the loop. The notebook writes it
to the volume (kpi_store.load_databricks.run). The runner fetches it, and a person clears it. The cut tool reads
the cleared report and turns the accepted rows into a correction version. This module holds the format for all
three, so they share one definition of it. It has no command.

A row's decision is one of DECISIONS. "accept" applies the row's proposed fix. "reject" changes nothing and
becomes a standing decision, so the next comparison leaves the row out. "environment setting" means the
difference belongs to this environment and goes into kpi_store.toml, not into the ontology.
"""
import csv
import hashlib
import io
import json
import secrets
from pathlib import Path

FORMAT = 1   # the format's number; read refuses a report with another
JSON_NAME = "discovery-report.json"
CSV_NAME = "discovery-report.csv"
# Every kind a row may have. A row blocks exactly when its kind is one of BLOCKING_KINDS. validate refuses a
# report in which a row's blocks does not follow from its kind, so a hand edit of blocks alone is caught. It does
# not catch a hand edit of the kind itself: a blocking kind rewritten as another kind passes.
BLOCKING_KINDS = ("object-missing", "object-renamed", "column-missing", "column-renamed", "edge-missing")
OTHER_KINDS = ("column-case", "object-extra", "measure-link", "second-source", "no-lineage", "stale-data",
               "migration-pair", "question")
KINDS = BLOCKING_KINDS + OTHER_KINDS
DECISIONS = ("accept", "reject", "environment setting")
PASSES = ("object_names", "table_edges", "metric_view_sources")   # the three counts of what agreed
ROW_FIELDS = ("id", "kind", "blocks", "object", "ontology_value", "found_value", "evidence", "proposed_fix",
              "recommended", "decision", "decided_by", "note")
RUN_FIELDS = ("id", "at", "settings_sha256", "zip_sha256")
# The rows a person rejected in a cleared report. The cut tool writes the file and the comparison reads it.
STANDING_DECISIONS = Path("business_architecture") / "ontology" / "discovery-runs" / "standing-decisions.json"


class ReportError(Exception):
    """The report does not have the format this module writes."""


def new_run(now, settings_sha256, zip_sha256):
    """The report's run record. The ID is the UTC time and eight random hexadecimal digits, which keep two runs
    in the same second apart unless the digits repeat. The two checksums say which settings and which zip the
    run read."""
    return {"id": f"{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}", "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "settings_sha256": settings_sha256, "zip_sha256": zip_sha256}


def build(release, ontology, run, rows, passes):
    """A report from the comparison's rows, which get their IDs here: R001, R002, in the order given."""
    numbered = [{"id": f"R{n:03d}", **{k: row[k] for k in ROW_FIELDS if k != "id"}} for n, row in enumerate(rows, 1)]
    report = {"format": FORMAT, "release": release, "ontology": dict(sorted(ontology.items())), "run": dict(run),
              "blocked": any(r["blocks"] for r in numbered), "passes": {k: passes[k] for k in PASSES}, "rows": numbered}
    validate(report)
    return report


def problems(report):
    """Every way the report departs from the format, in words. An empty list means it is valid."""
    found = []
    if not isinstance(report, dict):
        return ["the report is not a JSON object"]
    if report.get("format") != FORMAT:
        found.append(f"format is {report.get('format')!r}, not {FORMAT}")
    if not isinstance(report.get("release"), str) or not report.get("release"):
        found.append("release is missing")
    ontology = report.get("ontology")
    if not isinstance(ontology, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in ontology.items()):
        found.append("ontology must map each module to its version")
    run = report.get("run")
    if not isinstance(run, dict) or any(not isinstance(run.get(k), str) or not run.get(k) for k in RUN_FIELDS):
        found.append(f"run must hold {', '.join(RUN_FIELDS)}")
    passes = report.get("passes")
    if not isinstance(passes, dict) or any(type(passes.get(k)) is not int for k in PASSES):
        found.append(f"passes must hold a whole number for each of {', '.join(PASSES)}")
    rows = report.get("rows")
    if not isinstance(rows, list):
        return found + ["rows is not a list"]
    seen = set()
    for n, row in enumerate(rows, 1):
        where = f"row {n}"
        if not isinstance(row, dict) or set(row) != set(ROW_FIELDS):
            found.append(f"{where} must hold exactly {', '.join(ROW_FIELDS)}")
            continue
        where = f"row {row['id']}"
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in seen:
            found.append(f"{where}: the ID is empty or used twice")
        seen.add(row["id"])
        if row["kind"] not in KINDS:
            found.append(f"{where}: unknown kind {row['kind']!r}")
        elif row["blocks"] is not (row["kind"] in BLOCKING_KINDS):
            found.append(f"{where}: blocks must be {row['kind'] in BLOCKING_KINDS} for kind {row['kind']}")
        if not isinstance(row["proposed_fix"], dict) or not isinstance(row["proposed_fix"].get("action"), str):
            found.append(f"{where}: proposed_fix must be an object with an action")
        for key in ("object", "ontology_value", "found_value", "evidence", "decided_by", "note"):
            if not isinstance(row[key], str):
                found.append(f"{where}: {key} must be text")
        for key in ("recommended", "decision"):
            if row[key] not in ("",) + DECISIONS:
                found.append(f"{where}: {key} must be empty or one of {', '.join(DECISIONS)}")
        if row.get("decision") and not row.get("decided_by"):
            found.append(f"{where}: a decision needs decided_by")
    if isinstance(report.get("blocked"), bool) and report["blocked"] != any(isinstance(r, dict) and r.get("blocks") for r in rows):
        found.append("blocked must be true exactly when a row blocks")
    elif not isinstance(report.get("blocked"), bool):
        found.append("blocked must be true or false")
    return found


def validate(report):
    """Raises ReportError naming every problem; returns the report when it has none."""
    found = problems(report)
    if found:
        raise ReportError("; ".join(found))
    return report


def is_cleared(report):
    """True when every row that blocks has a decision."""
    return all(row["decision"] for row in report["rows"] if row["blocks"])


def to_json(report):
    """The report as JSON text. Letters outside ASCII stay as they are, so a person can read the file."""
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def to_csv(report):
    """The rows as CSV text. proposed_fix is one JSON cell. The line ending is LF on every platform."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(ROW_FIELDS)
    for row in report["rows"]:
        writer.writerow([json.dumps(row[k], sort_keys=True) if k == "proposed_fix" else
                         ("true" if row[k] else "false") if k == "blocks" else row[k] for k in ROW_FIELDS])
    return out.getvalue()


def write(report, folder):
    """Writes both files into the folder, after validating. Returns (JSON path, CSV path)."""
    validate(report)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = folder / JSON_NAME, folder / CSV_NAME
    for path, text in zip(paths, (to_json(report), to_csv(report))):
        with path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return paths


def read(path):
    """The validated report from a JSON file."""
    try:
        with Path(path).open(encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, ValueError) as err:
        raise ReportError(f"cannot read the report {path}: {type(err).__name__}") from None
    return validate(report)


def standing_key(row):
    """What makes two findings the same one: the kind, the object, the ontology's value and the found value, case
    ignored. It is a SHA-256, so the standing decisions never hold a found value as text."""
    # The parts are joined with the unit separator (\x1f), a character names do not use, so the parts of one row
    # do not run together into the text of another.
    parts = (row["kind"], row["object"].lower(), row["ontology_value"].lower(), row["found_value"].lower())
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def read_standing(release_root):
    """The keys (standing_key) of the rows that a cleared report rejected, from the release's standing decisions.
    An empty set when the release has none."""
    path = Path(release_root) / STANDING_DECISIONS
    if not path.is_file():
        return frozenset()
    try:
        with path.open(encoding="utf-8") as f:
            return frozenset(d["key"] for d in json.load(f)["decisions"])
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise ReportError(f"cannot read the standing decisions {path}: {type(err).__name__}") from None


def apply_csv_decisions(report, csv_path):
    """The report with the decision, decided_by and note of each row taken from a cleared CSV, matched by ID. The
    CSV may be the one a person edited in a spreadsheet. A row ID the report does not have raises ReportError."""
    # utf-8-sig: a spreadsheet may save the file with a byte-order mark in front of the first column's name.
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as f:
        cleared = {r["id"]: r for r in csv.DictReader(f)}
    unknown = sorted(set(cleared) - {r["id"] for r in report["rows"]})
    if unknown:
        raise ReportError(f"the CSV holds row IDs the report does not have: {', '.join(unknown)}")
    rows = [{**row, **{k: (cleared[row["id"]].get(k) or "").strip() for k in ("decision", "decided_by", "note")}}
            if row["id"] in cleared else row for row in report["rows"]]
    return validate({**report, "rows": rows})
