"""The command line for the cross-graph questions.

    python -m kpi_store.questions.run discover --settings S --mapping M
    python -m kpi_store.questions.run confirm  --settings S --mapping M
    python -m kpi_store.questions.run check    --settings S --mapping M
    python -m kpi_store.questions.run ask q6   --settings S --mapping M --param kpi=crude-prices --out FOLDER

`discover` reads both graphs' schemas and writes a proposed mapping. A person reads the file, corrects it where
discovery guessed wrong, and runs `confirm`. `check` compares the confirmed mapping with the live schemas.
`ask` runs that check first, then one question, and writes the rows as JSON and CSV.

Every query is sent in a read transaction (READ_ACCESS, execute_read). The server is relied on to refuse a write
in such a transaction, should one get past the renderer's write guard.

Run it after the stores are loaded and the KPI Store graph is copied to Neo4j Enterprise (the runner's
`enterprise` step). The runner does not call it. Do `discover` and `confirm` once per environment, and again
when `check` says the governance graph's schema changed.

It reads the connection settings, the mapping file and both graphs. It writes the mapping file (`discover`,
`confirm`) and, for `ask`, <question>.json and <question>.csv in the --out folder. All of these must be outside
the release folder, and the command stops when one is inside. It sends no write to either graph: the schema
queries are fixed read queries, and a question passes the renderer's write guard and runs in a read transaction.

Exit 0 when the command did its work, 1 when it stopped. The last line it prints says why.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import connection as C
from . import discover as D
from . import mapping as M
from . import render as T
from . import roles as R

# A language tag at the end of a text, such as @en or @en-GB. The KPI Store graph keeps the tag of a label in
# the text itself, and an answer shows the label without it.
LANGUAGE_TAG = re.compile(r"@[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$")


class Reader:
    """Runs read queries on the composite database. The driver is imported here so the rest needs no driver."""

    def __init__(self, connection: C.Connection):
        from neo4j import GraphDatabase
        self.connection = connection
        self.driver = GraphDatabase.driver(connection.uri, auth=(connection.user, connection.password),
                                           notifications_min_severity="OFF")
        self.last_columns: list[str] = []

    def read(self, query: str, params: dict | None = None) -> list[dict]:
        """Runs one query in a read transaction on the composite database and returns its rows as dicts."""
        from neo4j import READ_ACCESS
        with self.driver.session(database=self.connection.composite, default_access_mode=READ_ACCESS) as session:
            def work(tx):
                result = tx.run(query, params or {})
                return list(result.keys()), [record.data() for record in result]
            # The columns are kept apart from the rows, so an answer with no rows still names its columns.
            self.last_columns, rows = session.execute_read(work)
            return rows

    def close(self) -> None:
        self.driver.close()


def read_schemas(reader, graphs: dict[str, str]) -> dict[str, D.Schema]:
    """Both graphs' schemas, each read through the composite database. The graph's name travels as a parameter,
    in front of each of discover.py's schema queries."""
    return {graph: D.read_schema(lambda query, name=name: reader.read("USE graph.byName($graph) " + query,
                                                                       {"graph": name}))
            for graph, name in graphs.items()}


def plain(value):
    """A value as JSON can hold it: dates and times as ISO text."""
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def ask(reader, question: str, mapping: dict, graphs: dict[str, str], params: dict | None = None,
        now: dt.datetime | None = None) -> dict:
    """One question's answer. Stops before the question's query when the mapping is unconfirmed or has drifted.
    The schema queries of the drift check have run by then."""
    M.require_confirmed(mapping)
    # The schemas are read again for every question, not kept from an earlier run: the governance graph belongs
    # to its owner and can change between two questions.
    schemas = read_schemas(reader, graphs)
    problems = M.drift(mapping, schemas)
    if problems:
        raise M.MappingError("the graphs changed since the mapping was confirmed:\n  " + "\n  ".join(problems))
    rendered = T.render(question, mapping, schemas, params, graphs)
    rows = [plain(row) for row in reader.read(rendered.query, rendered.params)]
    for row in rows:
        for column in rendered.language_tagged:
            if isinstance(row.get(column), str):
                row[column] = LANGUAGE_TAG.sub("", row[column])
    # The answer file names the question's own parameters. The two graph names belong to the environment.
    shown = {name: value for name, value in rendered.params.items() if name not in T.GRAPH_PARAMS.values()}
    now = now or dt.datetime.now(dt.timezone.utc)
    return {"question": question, "title": rendered.title, "params": shown,
            "asked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "columns": list(getattr(reader, "last_columns", None) or (rows[0] if rows else [])), "rows": rows}


def write_answer(answer: dict, folder: Path) -> tuple[Path, Path]:
    """Writes one answer as <question>.json (everything) and <question>.csv (the rows, for a spreadsheet), both
    with LF line ends, and returns the two paths. A second answer to the same question replaces the first."""
    folder.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = folder / f"{answer['question']}.json", folder / f"{answer['question']}.csv"
    with json_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(answer, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(answer["columns"])
        for row in answer["rows"]:
            # A list or a map goes into one cell as JSON, so the CSV keeps one row per answer row.
            writer.writerow(["" if row[c] is None else row[c] if isinstance(row[c], (str, int, float))
                             and not isinstance(row[c], bool) else json.dumps(row[c], ensure_ascii=False)
                             for c in answer["columns"]])
    return json_path, csv_path


def parse_params(pairs) -> dict:
    """The --param name=value pairs as a dict. A value that reads as JSON is taken as JSON, so a number stays a
    number and a list a list."""
    params = {}
    for pair in pairs or []:
        name, sep, text = pair.partition("=")
        if not sep or not name:
            raise T.RenderError(f"--param takes name=value, not {pair}")
        try:
            params[name] = json.loads(text)      # 5, true or ["a", "b"]
        except json.JSONDecodeError:
            params[name] = text                  # anything else is the text itself
    return params


def show(mapping: dict, out) -> None:
    """Prints the mapping one role per line, for the person who corrects and confirms it. A required role with
    no value is marked, because confirm will refuse the mapping until it has one."""
    for name, entry in mapping["roles"].items():
        value = entry["value"]
        if isinstance(value, dict):
            value = " | ".join(value["types"]) + f" (up to {value['max_hops']} steps)"
        note = "" if value is not None else ("  REQUIRED, NOT FOUND" if entry["required"] else "  (optional, absent)")
        others = f"  other choices: {json.dumps(entry['alternatives'])}" if entry.get("alternatives") else ""
        print(f"{entry['graph']:<10} {name:<32} {value if value is not None else '-'}"
              f"  confidence {entry.get('confidence', 0):.1f}{note}{others}", file=out)


def main(argv=None, out=sys.stdout, reader_factory=Reader, confirm_input=input) -> int:
    """The command line. The tests replace `out`, the reader and the typed answer."""
    parser = argparse.ArgumentParser(prog="python -m kpi_store.questions.run",
                                     description="KPI Store cross-graph questions.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("discover", "Read both graphs' schemas and write a proposed role mapping."),
                       ("confirm", "Mark the role mapping as confirmed, after checking it against the graphs."),
                       ("check", "Compare the confirmed mapping with the live schemas."),
                       ("ask", "Check the mapping, run one question and write its rows.")):
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument("--settings", type=Path, help="the connection settings file (TOML), outside the release")
        command.add_argument("--mapping", type=Path, required=True, help="the role mapping file, outside the release")
        if name == "discover":
            command.add_argument("--replace", action="store_true", help="replace a mapping that is already confirmed")
        if name == "confirm":
            command.add_argument("--yes", action="store_true", help="confirm without the typed question")
        if name == "ask":
            command.add_argument("question", choices=T.QUESTIONS)
            command.add_argument("--param", action="append", metavar="NAME=VALUE", help="a question parameter")
            command.add_argument("--out", type=Path, default=Path("."), help="the folder for the JSON and CSV files")
    args = parser.parse_args(argv)
    reader = None
    try:
        # The paths are checked before the settings are read and before any connection is opened, so a path
        # inside the release folder stops the command before it reads a file or a graph and before it writes.
        mapping_path = C.outside_release(args.mapping, "the mapping file")
        if args.command == "ask":
            args.out = C.outside_release(args.out, "the folder for the answers (--out)")
        connection = C.read(args.settings)
        reader = reader_factory(connection)
        if args.command == "discover":
            # A confirmed mapping holds a person's corrections, and a new proposal would overwrite them. A mapping
            # that was corrected and not yet confirmed has no such guard: the proposal is written over it.
            if mapping_path.exists() and M.is_confirmed(M.load(mapping_path)) and not args.replace:
                raise M.MappingError(f"{mapping_path} is confirmed: pass --replace to write a new proposal over it")
            proposal = D.propose(read_schemas(reader, connection.graphs))
            M.save(mapping_path, proposal)
            show(proposal, out)
            print(f"wrote {mapping_path}. Read it, correct any value, then run confirm.", file=out)
        elif args.command == "confirm":
            mapping = M.load(mapping_path)
            confirmed = M.confirm(mapping, read_schemas(reader, connection.graphs))
            show(confirmed, out)
            # The file is saved only after the typed yes, or at once with --yes. Any other answer leaves the file
            # on disk as it was.
            if not args.yes and confirm_input("Type yes to confirm this mapping: ").strip().lower() != "yes":
                print("not confirmed", file=out)
                return 1
            M.save(mapping_path, confirmed)
            print(f"confirmed {mapping_path}", file=out)
        elif args.command == "check":
            mapping = M.load(mapping_path)
            M.require_confirmed(mapping)
            problems = M.drift(mapping, read_schemas(reader, connection.graphs))
            if problems:
                raise M.MappingError("the graphs changed since the mapping was confirmed:\n  " + "\n  ".join(problems))
            print(f"the mapping still fits both graphs ({len(R.ROLES)} roles checked)", file=out)
        else:
            answer = ask(reader, args.question, M.load(mapping_path), connection.graphs, parse_params(args.param))
            json_path, csv_path = write_answer(answer, args.out)
            print(f"{args.question}: {len(answer['rows'])} rows; wrote {json_path} and {csv_path}", file=out)
        return 0
    except (C.SettingsError, M.MappingError, T.RenderError) as error:
        print(f"STOPPED: {error}", file=out)
        return 1
    except Exception as error:
        # A driver error (no server, wrong login) is an answer for the person, not a traceback.
        if not type(error).__module__.startswith("neo4j"):
            raise
        print(f"STOPPED: {type(error).__name__}: {error}", file=out)
        return 1
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    sys.exit(main())
