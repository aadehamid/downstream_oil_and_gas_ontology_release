"""Empties the stores the KPI Store loaded, so that the next run loads them again from nothing.

    python -m kpi_store.runner --reset                        # all four stores
    python -m kpi_store.runner --reset --only fuseki,neo4j    # only these stores
    python -m kpi_store.runner --reset --skip databricks      # all but these stores
    python -m kpi_store.runner --reset --dry-run              # say what would be deleted, and delete nothing
    python -m kpi_store.runner --reset --yes                  # do not ask first; for a script

This module has no command of its own. The runner calls run() here when it is given --reset.

The stores, in the order they are emptied, and what each one loses:
  enterprise  in the one database [neo4j.enterprise] names: every node that carries the KPI Store's marks, with its
              relationships. The marks are the copy's own (kpi_store.copy_enterprise.OWN_RULES), and they include
              the three kinds of marker node. A node without the marks stays. The uniqueness constraint that the
              copy made stays too, because no statement of this code may drop anything on Enterprise.
  neo4j       in the database [neo4j.local] names: the same nodes, and the configuration nodes that the n10s plugin
              wrote for the load. Then the constraints that the load makes, by name (LOAD_CONSTRAINTS). A node that
              the load did not write stays, and so does every other constraint; the plan lists both.
  fuseki      the Fuseki that the load started is stopped, and the folder [fuseki] data_folder names is deleted.
  databricks  the four tables: epm_triples and epm_store_markers in the write schema, tech_graph_triples and
              tech_graph_markers in the technical graph's schema.

What stays, always: the release folder, the run folder with every run's files and reports, the projection's output
folder, and in Databricks the two schemas, the volume with the zip and the reports, and the notebook. The next load
needs them, and the reports are a record.

No store gets a rule of its own here for what may be deleted. Each deletion uses the rule of that store's load:
  enterprise  the copy's marks (copy_enterprise.own_predicate), on the copy's guarded session (open_target). These
              are the marks a replace deletes by. The statement is the reset's own (delete_own), because it runs
              in transactions that also hold the check described below; the copy's remove_own is unchanged.
  neo4j       the same marks with the local load's store name. The load's own wipe is not used: it drops
              every constraint of the database, and the reset drops only the ones the load makes.
  fuseki      load_fuseki.stop, which signals only the process that the load started.
  databricks  DROP TABLE IF EXISTS through load_databricks.Gate, which refuses a write outside the two schemas.

Before it deletes, run() prints for each store what it will delete, with counts where the store can be read, and
asks the person to type the word reset. --yes leaves the question out. --dry-run prints the same and stops there.

A store that cannot be read or emptied is left alone, and the reset goes on with the others. It then ends with
exit code 1, whoever chose the store: every store of the selection must be empty for a 0. To leave a store out on
purpose, name it with --skip. Three cases leave a store alone:
- It cannot be reached, or its settings are missing.
- Databricks, when kpi_store.toml names no SQL warehouse. Databricks is emptied through a warehouse, as the sync
  check reads it. The reset then prints the four statements to run by hand.
- A Neo4j database in which a relationship joins a KPI Store node to a node without the marks. The delete removes
  a node with its relationships, so it would remove that relationship, which another writer made. The reset counts
  such relationships before the question, and again at the start of each transaction that deletes a batch of
  nodes (delete_own). When it finds one it deletes no further node in that database. The copy stops on a node
  without the marks in the same way.

The checks come immediately before the deletes, and that is all they are. Run the reset when nothing else writes
to these stores. Two things are not caught:
- A relationship that another writer commits in the instant between a batch's check and its delete. The two are in
  one transaction, but Neo4j reads committed data and does not hold the check's answer, so the delete takes that
  relationship with its node.
- A part of the Fuseki folder's path that is replaced by a link in the instant between the check of the folder
  and its delete.
Nothing here locks a store against another writer.

The stores are emptied one after another, and a deletion is not undone. When one store fails, or Ctrl+C stops the
reset, it stops there, says which store may be partly emptied, names the stores it did not reach, and leaves the
stores before it empty. Run the same command again: a store that is already empty has nothing to delete.

run() returns 0 when every store of the selection holds nothing of the KPI Store at the end, or when the dry run
found that a reset would empty them all. It returns 1 when a store was left alone, a store failed, Ctrl+C stopped
it, or the word was not typed.
"""
import contextlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import copy_enterprise
from . import load_databricks as ldb
from . import load_fuseki
from . import load_neo4j as local_load
from . import local_settings as ls
from . import settings as settings_module
from . import sync_check
from . import tech_graph

# The order the stores are emptied in. Enterprise comes first: it is the copy furthest from the release files, so a
# reset that stops part-way never leaves a copy standing whose source is already gone.
STORES = ("enterprise", "neo4j", "fuseki", "databricks")
WORD = "reset"   # what the person types to allow the deletion
# What a TDB2 dataset folder holds at its top: the numbered data folders, the lock file and the backups folder.
# The folder is deleted only when it holds nothing else (check_dataset_folder).
TDB2_ENTRY = re.compile(r"^(Data-\d+|tdb\.lock|Backups)$")
# Every constraint a load makes in a Neo4j database, by name. The projection's load script and the copy each make
# this one (build.py and copy_graph.py of the ontology-to-lpg skill); the logical models, the technical graph, the
# release records and the markers make none. The local reset drops these and no other constraint.
LOAD_CONSTRAINTS = ("n10s_unique_uri",)
# The relationships that join a node with the KPI Store's marks to a node without them, counted by the labels of
# the node without. {own} is copy_enterprise.own_predicate, which speaks of the variable n, so the far node is
# renamed first and n is bound again to the near one.
FOREIGN_LINKS = ("MATCH (n) WHERE NOT {own} WITH n AS far MATCH (far)-[r]-(n) WHERE {own} "
                 "RETURN labels(far) AS labels, count(DISTINCT r) AS n")
BATCH = copy_enterprise.BATCH   # nodes per transaction of delete_own, as in the copy's own delete
STOP_WAIT_SECONDS = 30   # how long the reset waits for the stopped Fuseki to end before it gives up
DELETE_TRIES = 10        # Windows frees a stopped program's files a moment after it ends, so the delete is tried again
KEPT = ("kept: the release folder, the run folder with every run's files and reports, and in Databricks the two "
        "schemas, the volume with the zip and the reports, and the notebook")


class ResetFailed(Exception):
    """A store cannot be emptied. The message says why and what was, or was not, deleted."""


@dataclass
class Plan:
    """What the reset will do to one store. status is "delete", "nothing" (the store is already empty) or
    "blocked" (it cannot be read or emptied, so it is left alone; the lines say why). empty() deletes and returns
    the line to print."""
    store: str
    lines: list
    status: str
    empty: object = None


def count_text(counts):
    """The counts as text: "4242 Resource, 12 ModuleRelease"."""
    return copy_enterprise.describe(counts)


# ---- the two Neo4j databases --------------------------------------------------------------------------

def refuse_foreign_links(session, params, rules, where, deleted=0):
    """Raises ResetFailed when a relationship joins a KPI Store node to a node without the marks. The delete removes
    a node with its relationships, and such a relationship is another writer's, so no node, or no further node,
    is deleted. session is a session or a transaction. where names the database in the message, and deleted is the
    number of nodes that earlier batches of the same delete already removed."""
    found = session.run(FOREIGN_LINKS.format(own=copy_enterprise.own_predicate(rules)), **params).data()
    total = sum(row["n"] for row in found)
    if not total:
        return
    far = {}
    for row in found:   # by label of the far node, as holdings counts the nodes without the marks
        for label in row["labels"] or ["(no label)"]:
            far[label] = far.get(label, 0) + row["n"]
    by_count = ", ".join(f"{n} {label}" for label, n in sorted(far.items(), key=lambda item: (-item[1], item[0])))
    raise ResetFailed(f"in {where}, {total} relationship(s) join a KPI Store node to a node without its marks (at the "
                      f"far end: {by_count}). The delete would remove them with the node, and they are another writer's. "
                      + (f"{deleted} node(s) were deleted before this was found, and no more. " if deleted else "Nothing was deleted. ")
                      + "Ask their owner to remove them, then run the reset again")


def delete_own(session, params, rules, where):
    """Deletes the KPI Store's nodes, by the copy's marks, in batches of BATCH nodes. Returns the number deleted.

    Each batch is one explicit transaction that first runs the check for another writer's relationship and then
    deletes. So the time between a check and its delete is one transaction, and never the wait at the question
    or the length of an earlier batch. This does not make the two atomic. Neo4j's transactions read committed
    data: a relationship that another writer commits after the check has read and before the delete reaches its
    node is deleted with the node. The check also covers the whole database in every batch, not only that batch's
    nodes, so a relationship found after the first batch stops the delete with the earlier batches gone.

    The copy's own remove_own is not used and not changed: it is one statement that commits its batches itself
    (CALL ... IN TRANSACTIONS), and such a statement cannot run inside an explicit transaction."""
    statement = f"MATCH (n) WHERE {copy_enterprise.own_predicate(rules)} WITH n LIMIT {int(BATCH)} DETACH DELETE n RETURN count(*) AS c"
    deleted = 0
    while True:
        tx = session.begin_transaction()
        try:
            refuse_foreign_links(tx, params, rules, where, deleted)
            n = tx.run(statement, **params).single()["c"]
            tx.commit()
        except BaseException:   # Ctrl+C too: the batch that was open is not left half-done
            with contextlib.suppress(Exception):
                tx.rollback()
            raise
        deleted += n
        if n < BATCH:   # a batch that is not full was the last one
            return deleted


def marks(ctx, code, store):
    """The parameters that the copy's rules read (copy_enterprise.release_marks), for this release folder and for
    the markers of one database."""
    want = ldb.expected(ctx.release_root, code.ss)
    return copy_enterprise.release_marks(ctx.release_root, local_load.run_config(ctx.release_root, ctx.local, ""),
                                         want["newest"], code, store=store)


def plan_enterprise(ctx, code, connect):
    """The Enterprise database: the delete of the copy's replace, and nothing else. A node without the KPI Store's
    marks does not stop the reset, as it stops the copy: the reset deletes by the marks and leaves that node."""
    cfg = ctx.local.need("neo4j_enterprise")
    database = copy_enterprise.checked_name(cfg.database)
    rules = ctx.hooks["own_rules"] or copy_enterprise.OWN_RULES
    params = marks(ctx, code(), copy_enterprise.STORE)

    @contextlib.contextmanager
    def session():
        # The copy's own way in: the one database by name, confirmed by the server, and the guard on every statement.
        with connect(cfg) as driver, copy_enterprise.open_target(driver, database) as target:
            yield target

    def empty():
        with session() as target:
            before = copy_enterprise.holdings(target, params, rules)
            # The check for another writer's relationship runs again inside each batch's transaction.
            delete_own(target, params, rules, f"the database {database}")
            after = copy_enterprise.holdings(target, params, rules)   # read back: the delete must have left none
        if after["own"]:
            raise ResetFailed(f"the database {database} still holds {sum(after['own'].values())} node(s) with the KPI "
                              "Store's marks after the delete; run the reset again")
        return (f"emptied. {sum(before['own'].values())} node(s) deleted from the database {database}"
                + (f"; {after['foreign_nodes']} node(s) without the KPI Store's marks left as they were" if after["foreign_nodes"] else ""))

    with session() as target:
        held = copy_enterprise.holdings(target, params, rules)
        refuse_foreign_links(target, params, rules, f"the database {database}")   # the plan then reads "cannot be emptied"
    own = sum(held["own"].values())
    stay = ([f"{held['foreign_nodes']} node(s) without those marks stay ({count_text(held['foreign'])}). The next copy "
             "stops while the database holds them"] if held["foreign_nodes"] else [])
    if not own:
        return Plan("enterprise", [f"the database {database} holds no node with the KPI Store's marks; nothing to delete"] + stay, "nothing")
    return Plan("enterprise", [f"in the database {database}, delete {own} node(s) that carry the KPI Store's marks, with "
                               f"their relationships ({count_text(held['own'])})"] + stay
                + ["the uniqueness constraint that the copy made stays; the next copy uses it"], "delete", empty)


def plan_neo4j(ctx, code, connect):
    """The local database. The nodes the load wrote are the copy's rules plus the n10s plugin's own configuration
    nodes, which have no Resource label and are never copied (copy_graph.CONFIG_LABELS). Of the constraints, only
    the ones the load makes are dropped, by name."""
    cfg = ctx.local.need("neo4j_local")
    release_code = code()
    rules = dict(ctx.hooks["own_rules"] or copy_enterprise.OWN_RULES) | {label: "true" for label in release_code.cg.CONFIG_LABELS}
    params = marks(ctx, release_code, local_load.STORE)
    where = f"the local database {cfg.database}"

    def read(session):
        """(holdings, the load's constraints that exist, every other constraint), after the check for a
        relationship of another writer."""
        held = copy_enterprise.holdings(session, params, rules)
        refuse_foreign_links(session, params, rules, where)
        names = sorted(session.run("SHOW CONSTRAINTS YIELD name RETURN name").value())
        return held, [n for n in names if n in LOAD_CONSTRAINTS], [n for n in names if n not in LOAD_CONSTRAINTS]

    def named(constraints):
        return f"constraint{'' if len(constraints) == 1 else 's'}"

    def empty():
        with connect(cfg) as driver, driver.session(database=cfg.database) as session:
            before, mine, others = read(session)   # read again: the question may have waited a long time
            delete_own(session, params, rules, where)   # checks once more inside each batch's transaction
            # The load's own wipe would drop every constraint here. Only the load's constraints go, each by its
            # name; LOAD_CONSTRAINTS holds fixed names, so no name from the database reaches the statement.
            for name in mine:
                session.run(f"DROP CONSTRAINT `{name}` IF EXISTS").consume()
            after = copy_enterprise.holdings(session, params, rules)   # read back: the delete must have left none
        if after["own"]:
            raise ResetFailed(f"{where} still holds nodes that the load wrote after the delete; run the reset again")
        left = [f"{after['foreign_nodes']} node(s) that the load did not write"] if after["foreign_nodes"] else []
        left += [f"{len(others)} constraint(s) that it did not make"] if others else []
        return (f"emptied. {sum(before['own'].values())} node(s) deleted from {where}"
                + (f", and the {named(mine)} {', '.join(mine)} dropped" if mine else "")
                + (f"; {' and '.join(left)} left as they were" if left else ""))

    with connect(cfg) as driver, driver.session(database=cfg.database) as session:
        held, mine, others = read(session)
    own, foreign = sum(held["own"].values()), held["foreign_nodes"]
    stay = ([f"{foreign} node(s) that the load did not write stay ({count_text(held['foreign'])})"] if foreign else []) \
        + ([f"{len(others)} constraint(s) that the load did not make stay ({', '.join(others)})"] if others else [])
    if not own and not mine:
        return Plan("neo4j", [f"{where} holds no node that the load wrote and no constraint that it made; nothing to delete"] + stay, "nothing")
    steps = ([f"delete {own} node(s) that the load wrote, with their relationships ({count_text(held['own'])})"] if own else []) \
        + ([f"drop the {named(mine)} that the load made ({', '.join(mine)})"] if mine else [])
    return Plan("neo4j", [f"in {where}, " + ", then ".join(steps)] + stay, "delete", empty)


# ---- Fuseki -------------------------------------------------------------------------------------------

def same_path(one, two):
    """True when two paths name the same place. Case is ignored, as Windows ignores it (local_settings.is_inside)."""
    return ls.is_inside(one, two) and ls.is_inside(two, one)


def check_dataset_folder(folder, local, release_root):
    """Raises ResetFailed unless this folder may be deleted as the Fuseki dataset. It must be the folder that
    [fuseki] data_folder names, a real folder reached through no link, with nothing in it but a TDB2 dataset, and
    nothing the KPI Store needs may lie in it. The last two checks are for a data_folder line that names a wrong
    folder, such as the whole local folder: the settings would then allow a delete that takes the settings file
    with it. Returns the folder's resolved path: the path that was checked, and the one to delete."""
    folder = Path(folder)
    configured = local.fuseki.data_folder if local.fuseki else None
    if configured is None or not same_path(folder, configured):
        raise ResetFailed(f"{folder} is not the folder that [fuseki] data_folder names; nothing was deleted")
    # No part of the configured path may be a link, the last part or any folder above it. Through a link the
    # settings would name one place and the delete would reach another, which the person never saw named.
    written = Path(os.path.abspath(configured.expanduser()))   # absolute, with .. removed, and no link followed
    for part in (*reversed(written.parents), written):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():   # is_junction: Windows, Python 3.12
            raise ResetFailed(f"{part} is a link, so [fuseki] data_folder does not say which folder would be deleted; "
                              "nothing was deleted. Name the real folder in [fuseki] data_folder")
    # Resolved once. Every check below is of this path, and it is the path the caller deletes.
    folder = written.resolve()
    if not folder.is_dir():
        raise ResetFailed(f"{folder} is a file, not a folder; nothing was deleted")
    needed = (("the release folder", release_root), ("the local settings file", local.path),
              ("the settings file of [release] settings", local.settings), ("the run folder", local.run_folder),
              ("the folder of [projection] out", local.projection_out), ("the Fuseki jar", local.fuseki.jar),
              ("the ROBOT jar", local.robot_jar))
    for name, path in needed:
        if path is not None and ls.is_inside(path, folder):
            raise ResetFailed(f"{folder} holds {name}, so it is not only a Fuseki dataset folder; nothing was deleted. "
                              "Correct [fuseki] data_folder")
    strange = sorted(p.name for p in folder.iterdir() if not TDB2_ENTRY.match(p.name))
    if strange:
        raise ResetFailed(f"{folder} holds {strange[0]}, which is no part of a Fuseki dataset; nothing was deleted. "
                          "Correct [fuseki] data_folder, or move that file away")
    return folder


def delete_folder(folder, sleep):
    """Deletes the folder and everything in it. A failed delete is tried again for a few seconds (DELETE_TRIES)."""
    for attempt in range(DELETE_TRIES):
        try:
            shutil.rmtree(folder)
            return
        except OSError as err:
            if attempt == DELETE_TRIES - 1:
                raise ResetFailed(f"{folder} could not be deleted ({type(err).__name__}); a program may hold one of its "
                                  "files open. Part of the folder may be gone. Close that program and run the reset again") from None
            sleep(1)


def plan_fuseki(ctx):
    """The local Fuseki: stop the server that the load started, then delete its dataset folder. A Fuseki that
    someone else started is never stopped, and the folder is never deleted under a server that still runs."""
    fuseki = ctx.local.need("fuseki")
    state = ctx.local.need("run_folder") / "fuseki"
    folder = fuseki.data_folder
    not_ours = (f"a Fuseki answers at {fuseki.url}, and the load did not start it, so this command does not stop it. "
                "Stop it in its own window, then run the reset again. Nothing of the dataset was deleted")
    if not fuseki.is_local:
        return Plan("fuseki", [f"cannot be emptied: {fuseki.url} is not on this machine, and this command stops and "
                               "empties only a Fuseki that the load started here"], "blocked")
    up, started = load_fuseki.answers(fuseki), (state / load_fuseki.PID_FILE).is_file()
    if up and not started:
        return Plan("fuseki", ["cannot be emptied: " + not_ours], "blocked")
    on_disk = folder is not None and folder.exists()
    if on_disk:
        folder = check_dataset_folder(folder, ctx.local, ctx.release_root)   # a wrong folder is refused before the question

    def empty():
        outcome, pid = load_fuseki.stop(state)
        waited = 0
        # The folder is deleted only after the server has ended: its process is gone and nothing answers.
        while load_fuseki.answers(fuseki) or (outcome == "stopped" and load_fuseki.command_line(pid) is not None):
            if outcome != "stopped":
                raise ResetFailed(not_ours)
            if waited >= STOP_WAIT_SECONDS:
                raise ResetFailed(f"the Fuseki process {pid} did not end within {STOP_WAIT_SECONDS} seconds; nothing of "
                                  "the dataset was deleted. Run the reset again")
            ctx.sleep(1)
            waited += 1
        said = [f"process {pid} stopped"] if outcome == "stopped" else []
        if folder is not None and folder.exists():
            # Checked again here, immediately before the delete: the question may have waited a long time for its
            # answer. What is deleted is the resolved path that this check returns, not the text of the settings.
            # A part of the path that is swapped for a link between this check and the delete is not caught.
            checked = check_dataset_folder(folder, ctx.local, ctx.release_root)
            delete_folder(checked, ctx.sleep)
            said.append(f"{checked} deleted")
        return "emptied. " + "; ".join(said)

    if not up and not started and not on_disk:
        return Plan("fuseki", ["no Fuseki runs that the load started, and there is no dataset folder; nothing to delete"], "nothing")
    held = ""
    if up:
        try:   # the dataset's own answer: its graphs and each graph's triples
            graphs = ldb.import_sync_stores(ctx.release_root).read_jena(fuseki.query_url)
            held = f" ({len(graphs)} graph(s), {sum(graphs.values())} triples)"
        except Exception:
            held = " (its content could not be counted)"
    steps = (["stop the Fuseki that the load started"] if started else []) \
        + ([f"delete the dataset folder {folder}"] if on_disk else [])
    lines = [", then ".join(steps) + held]
    if folder is None:
        lines.append("the dataset is in memory, so it is gone when the server stops")
    return Plan("fuseki", lines, "delete", empty)


# ---- Databricks ---------------------------------------------------------------------------------------

def databricks_tables(settings):
    """The four tables the KPI Store loads, by their full names, from the two modules that write them. The reset
    names no other table."""
    return (settings.triples_table, settings.markers_table, *tech_graph.delta_tables(settings))


def drop_statements(settings):
    """One DROP TABLE IF EXISTS per table of databricks_tables: what the reset sends, and what it prints for a
    person to run by hand."""
    return [f"DROP TABLE IF EXISTS {table}" for table in databricks_tables(settings)]


def plan_databricks(ctx, client_for):
    """The four tables, dropped through the Gate on a SQL warehouse. The runner's own Databricks steps use the
    command line, which runs no SQL, and the notebook's Spark session exists only inside the notebook. So outside
    the notebook the one way to run a statement is the warehouse that the sync check reads through."""
    settings = ctx.settings
    tables = databricks_tables(settings)
    if not settings.warehouse_id:
        return Plan("databricks", ["cannot be emptied from this machine: kpi_store.toml names no SQL warehouse, and outside "
                                   "the notebook this code runs SQL only through one. Set [databricks] warehouse_id and run "
                                   "the reset again. Or run these four statements in a Databricks SQL editor, and leave "
                                   "Databricks out of the reset with --skip databricks:"]
                    + [f"{statement};" for statement in drop_statements(settings)], "blocked")
    gate = ldb.Gate(settings, sync_check.statement_runner(client_for(ctx.local.need("databricks").profile), settings.warehouse_id))

    def there():
        """The tables of the four that exist now, in the order of databricks_tables."""
        found = {f"{settings.store_schema}.{name}".lower() for name in ldb._own_tables(gate, settings)} \
            | {f"{settings.write_catalog}.{settings.tech_graph_schema}.{name}".lower() for name in tech_graph._own_tables(gate, settings)}
        return [table for table in tables if table.lower() in found]

    def empty():
        dropped = there()
        for statement in drop_statements(settings):
            gate.run(statement)
        left = there()   # read back: a drop that Databricks did not carry out must not read as done
        if left:
            raise ResetFailed(f"{', '.join(left)} still exist(s) after the drop; run the reset again")
        return f"emptied. {len(dropped)} table(s) dropped: {', '.join(dropped)}"

    found = there()
    if not found:
        return Plan("databricks", [f"none of the four tables exists ({', '.join(tables)}); nothing to delete"], "nothing")
    rows = {table: int(gate.run(f"SELECT count(*) AS n FROM {table}")[0]["n"]) for table in found}
    return Plan("databricks", [f"drop {len(found)} table(s): " + ", ".join(f"{t} ({n} row(s))" for t, n in rows.items())]
                + ([f"not there, so not dropped: {', '.join(t for t in tables if t not in found)}"] if len(found) < len(tables) else []),
                "delete", empty)


# ---- the whole reset ----------------------------------------------------------------------------------

def plan(store, ctx, code, connect, client_for):
    """One store's plan. A store that cannot be read is not guessed at: its plan is "blocked", with the reason,
    and the reset leaves it alone."""
    try:
        if store == "enterprise":
            return plan_enterprise(ctx, code, connect)
        if store == "neo4j":
            return plan_neo4j(ctx, code, connect)
        if store == "fuseki":
            return plan_fuseki(ctx)
        return plan_databricks(ctx, client_for)
    except (ls.LocalSettingsError, settings_module.SettingsError, copy_enterprise.Refused, local_load.LoadError,
            ldb.ov.ReleaseError, ldb.GateRefusal, ResetFailed) as err:
        return Plan(store, [f"cannot be emptied: {err}"], "blocked")   # this code's own words
    except Exception as err:   # a driver's or a client's own text can carry an address, so only the error's kind is shown
        return Plan(store, [f"cannot be read ({type(err).__name__}), so it will not be changed"], "blocked")


def store_list(names):
    """Store names as text: "enterprise, neo4j and fuseki"."""
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def run(ctx, stores=STORES, yes=False, dry_run=False, ask=input, connect=local_load.connect,
        client_for=sync_check.workspace_client, code=None):
    """The whole reset of the stores of the selection. Prints the plan, asks for the word unless yes, deletes store
    by store, and returns the exit code: 0 only when no store of the selection was left alone. ask, connect,
    client_for and code are replaced by the tests."""
    loaded = {}

    def release_code():
        # Imported once, and only when a Neo4j store is named: the import needs the release's skill scripts.
        if "code" not in loaded:
            loaded["code"] = code or local_load.release_code(ctx.release_root)
        return loaded["code"]

    plans = [plan(store, ctx, release_code, connect, client_for) for store in STORES if store in stores]
    ctx.out(f"reset{' (dry run)' if dry_run else ''}: what {'would' if dry_run else 'will'} be deleted in "
            f"{store_list(p.store for p in plans)}. Nothing is deleted yet")
    for item in plans:
        for i, text in enumerate(item.lines):
            ctx.out(f"{item.store}: {text}" if i == 0 else f"  {text}")
    ctx.out(KEPT)
    # A store that is left alone fails the reset, whether the person named it or the default chose it: an exit 0
    # must mean that every store of the selection is empty. --skip is how a store is left out on purpose.
    left_alone = [p.store for p in plans if p.status == "blocked"]
    skip_hint = f"leave a store out on purpose with --skip {','.join(left_alone)}"
    to_do = [p for p in plans if p.status == "delete"]
    if dry_run:
        ctx.out("dry run: nothing was deleted" + (f". The reset would leave {store_list(left_alone)} alone and end with "
                                                  f"exit code 1; {skip_hint}" if left_alone else ""))
        return 1 if left_alone else 0
    if to_do and not yes:
        try:
            typed = ask(f"Type {WORD} to delete this, or press Enter to stop: ")
        except (EOFError, KeyboardInterrupt):   # no keyboard, as under a scheduler, or Ctrl+C: nobody typed the word
            typed = ""
        if typed.strip() != WORD:
            ctx.out(f"reset: STOPPED. The word {WORD} was not typed; nothing was deleted")
            return 1
    for position, item in enumerate(to_do):
        try:
            said = item.empty()
        except KeyboardInterrupt:
            # Ctrl+C is answered here and not passed on as a traceback: the person must learn which store the
            # stop caught half-way and which stores were never touched. The runner has no exit code of its own
            # for an interrupt, so this is its code for a failure.
            said = "STOPPED by Ctrl+C while it was being emptied. It may be partly emptied"
        except (ResetFailed, copy_enterprise.Refused, ldb.GateRefusal, ls.LocalSettingsError) as err:
            said = f"FAILED. {err}"
        except Exception as err:   # only the error's kind: its text can carry an address
            said = (f"FAILED. The store did not answer, or a statement failed ({type(err).__name__}). It may be part "
                    "emptied; run the reset again")
        ctx.out(f"{item.store}: {said}")
        if said.startswith(("FAILED", "STOPPED")):
            later = [p.store for p in to_do[position + 1:]]
            ctx.out("reset: STOPPED at " + item.store + (f". Not reached, so not changed: {store_list(later)}" if later else "")
                    + ". Run the same command again")
            return 1
    empty = [p.store for p in plans if p.status != "blocked"]
    # "Nothing of the KPI Store", not "empty": a node that the KPI Store did not write may still be there.
    holds = f"{store_list(empty)} {'holds' if len(empty) == 1 else 'hold'} nothing of the KPI Store" if empty else ""
    if left_alone:
        ctx.out("reset: NOT DONE. " + ("" if empty else "Nothing was deleted. ")
                + f"Not emptied: {store_list(left_alone)}; {'its line above says' if len(left_alone) == 1 else 'their lines above say'} why. " + (f"{holds}. " if empty else "")
                + f"Run the same command again, or {skip_hint}")
        return 1
    ctx.out(f"reset done: {holds}. To load again, run: python -m kpi_store.runner")
    return 0
