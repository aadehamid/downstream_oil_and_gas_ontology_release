"""The Fuseki load: Java and the jar, starting the server, and the load with its hash check, against a store in memory."""
import hashlib
import json
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from kpi_store import load_databricks as ldb
from kpi_store import load_fuseki as lf
from kpi_store.tests import stores_support, support

RDFSTORE = ldb.import_rdfstore(support.ROOT)
DP = "https://w3id.org/mpc/ontology/modules/data-product/"
KPI = "https://w3id.org/mpc/ontology/modules/kpi/"
# The small release's graphs, written by hand: three per package, and the data-product package's own graph.
GRAPHS = sorted([DP + "1.0.0", DP + "1.0.0/shapes", DP + "1.0.0/catalog", DP + "1.0.0/sample-model",
                 KPI + "1.0.0", KPI + "1.0.0/shapes", KPI + "1.0.0/catalog"])
BASES = [DP, KPI]


def release(tmp_path):
    root = support.small_release(tmp_path / "release")
    ss = ldb.import_sync_stores(root)
    return root, ss, lf.pack(RDFSTORE, lf.store_graphs(root, ss))


# ---- Java and the jar ------------------------------------------------------------------------------

def test_java_is_found_in_the_settings_then_java_home_then_the_path(tmp_path):
    exe = "java.exe" if lf.os.name == "nt" else "java"
    (tmp_path / "home" / "bin").mkdir(parents=True)
    for path in (tmp_path / "own-java", tmp_path / "home" / "bin" / exe, tmp_path / "path-java"):
        path.write_text("", encoding="utf-8", newline="\n")
    which = lambda name: str(tmp_path / "path-java")   # noqa: E731
    environ = {"JAVA_HOME": str(tmp_path / "home")}
    assert lf.find_java(tmp_path / "own-java", environ, which) == tmp_path / "own-java"
    assert lf.find_java(None, environ, which) == tmp_path / "home" / "bin" / exe
    assert lf.find_java(None, {}, which) == tmp_path / "path-java"
    assert lf.find_java(None, {"JAVA_HOME": str(tmp_path / "gone")}, lambda name: None) is None
    assert lf.find_java(tmp_path / "gone", environ, which) is None   # a setting that names no file is not replaced silently


@pytest.mark.parametrize("text, major", [
    ('openjdk version "21.0.2" 2024-01-16 LTS', 21), ('java version "1.8.0_292"', 8), ('openjdk version "17" 2021-09-14', 17),
    ('openjdk version "24.0.2" 2025-07-15', 24), ("no version here", None)])
def test_the_java_version_is_read_from_its_own_words(text, major):
    assert lf.java_major("java", lambda cmd, **k: SimpleNamespace(stderr=text, stdout="")) == major


def test_a_java_that_cannot_start_has_no_version():
    def run(cmd, **k):
        raise OSError("no such file")
    assert lf.java_major("java", run) is None


def test_java_older_than_21_is_refused(tmp_path):
    local = stores_support.local_settings(tmp_path)
    which = lambda name: "/sample/java"   # noqa: E731
    old = lambda cmd, **k: SimpleNamespace(stderr='openjdk version "17.0.5"', stdout="")   # noqa: E731
    with pytest.raises(lf.FusekiError, match="is version 17; Fuseki 6.2.0 needs 21 or later"):
        lf.check_java(local.fuseki, {}, which, old)
    with pytest.raises(lf.FusekiError, match="Java was not found"):
        lf.check_java(local.fuseki, {}, lambda name: None, old)
    new = lambda cmd, **k: SimpleNamespace(stderr='openjdk version "21.0.2"', stdout="")   # noqa: E731
    assert lf.check_java(local.fuseki, {}, which, new) == Path("/sample/java")


def test_the_jar_is_checked_by_its_checksum(tmp_path):
    assert lf.FUSEKI_SHA256 == "2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee"
    with pytest.raises(lf.FusekiError, match="is missing"):
        lf.check_jar(tmp_path / "jena-fuseki-server-6.2.0.jar")
    jar = tmp_path / "jena-fuseki-server-6.2.0.jar"
    jar.write_bytes(b"another jar")
    with pytest.raises(lf.FusekiError, match="SHA-256 is " + hashlib.sha256(b"another jar").hexdigest()):
        lf.check_jar(jar)


# ---- the server ------------------------------------------------------------------------------------

def test_the_start_command_keeps_the_dataset_on_disk_when_a_folder_is_named(tmp_path):
    fuseki = stores_support.local_settings(tmp_path).fuseki
    assert lf.start_command("java", fuseki) == [
        "java", "-jar", str(tmp_path / "jena-fuseki-server-6.2.0.jar"), "--tdb2", "--loc", str(tmp_path / "fuseki-db"),
        "--update", "--localhost", "--port", "3030", "/ds"]
    memory = stores_support.local_settings(tmp_path, data_folder='data_folder = ""', url='url = "http://localhost:17999/kpi"').fuseki
    assert lf.start_command("java", memory) == [
        "java", "-jar", str(tmp_path / "jena-fuseki-server-6.2.0.jar"), "--mem", "--update", "--localhost", "--port", "17999", "/kpi"]
    assert lf.start_command("java", memory, "ab12")[:3] == ["java", "-Dkpi_store.fuseki=ab12", "-jar"]


class Process:
    def __init__(self, pid=4242, exits=None):
        self.pid, self.returncode, self._exits = pid, None, exits

    def poll(self):
        self.returncode = self._exits
        return self._exits


def test_start_waits_until_the_dataset_answers_and_writes_the_process_id(tmp_path):
    fuseki = stores_support.local_settings(tmp_path).fuseki
    started, polls = [], iter([False, False, True])
    def popen(cmd, **options):
        started.append((cmd, options))
        return Process()
    pid = lf.start("java", fuseki, tmp_path / "state", popen=popen, answers=lambda f: next(polls), sleep=lambda s: None, token="ab12")
    assert pid == 4242 and json.loads((tmp_path / "state" / "fuseki.pid").read_text(encoding="utf-8")) == {"pid": 4242, "token": "ab12"}
    cmd, options = started[0]
    assert cmd == lf.start_command("java", fuseki, "ab12") and options["stdin"] == lf.subprocess.DEVNULL
    lf.start("java", fuseki, tmp_path / "other", popen=popen, answers=lambda f: True)
    token = json.loads((tmp_path / "other" / "fuseki.pid").read_text(encoding="utf-8"))["token"]
    assert len(token) == 32 and token != "ab12" and f"-Dkpi_store.fuseki={token}" in started[1][0]   # a new token per start
    assert options.get("start_new_session") is True or "creationflags" in options
    assert (tmp_path / "fuseki-db").is_dir() and (tmp_path / "state" / "fuseki.log").is_file()


def test_start_fails_when_the_server_stops_or_never_answers(tmp_path):
    fuseki = stores_support.local_settings(tmp_path).fuseki
    never = dict(answers=lambda f: False, sleep=lambda s: None)
    with pytest.raises(lf.FusekiError, match=r"stopped as it started \(exit 1\)"):
        lf.start("java", fuseki, tmp_path / "state", popen=lambda cmd, **o: Process(exits=1), **never)
    with pytest.raises(lf.FusekiError, match="did not answer within 3 seconds"):
        lf.start("java", fuseki, tmp_path / "state", popen=lambda cmd, **o: Process(), wait_seconds=3, **never)


def test_a_fuseki_on_another_machine_is_never_started(tmp_path):
    remote = stores_support.local_settings(tmp_path, url='url = "http://fuseki.example.org:3030/ds"').fuseki
    def popen(cmd, **options):
        raise AssertionError("nothing may be started")
    with pytest.raises(lf.FusekiError, match="not on this machine"):
        lf.start("java", remote, tmp_path / "state", popen=popen)


OURS = "/sample/java -Dkpi_store.fuseki=ab12 -jar jena-fuseki-server-6.2.0.jar --tdb2 --loc db --update --localhost --port 3030 /ds"


def saved(tmp_path, text='{"pid": 4242, "token": "ab12"}'):
    (tmp_path / "fuseki.pid").write_text(text + "\n", encoding="utf-8", newline="\n")


def test_stop_ends_the_process_start_wrote_and_only_once(tmp_path):
    saved(tmp_path)
    killed = []
    kill = lambda pid, sig: killed.append((pid, sig))   # noqa: E731
    assert lf.stop(tmp_path, kill=kill, command_line=lambda pid: OURS if pid == 4242 else None) == ("stopped", 4242)
    assert killed == [(4242, signal.SIGTERM)] and not (tmp_path / "fuseki.pid").exists()
    assert lf.stop(tmp_path, kill=kill, command_line=lambda pid: OURS) == ("none", None) and len(killed) == 1


@pytest.mark.parametrize("now_running", [
    "/usr/bin/some-editor notes.txt",                                                      # the number went to another program
    "/sample/java -Dkpi_store.fuseki=ffff -jar jena-fuseki-server-6.2.0.jar --mem /ds",   # another start of Fuseki
    "/sample/java -jar jena-fuseki-server-6.2.0.jar --mem --update --port 3030 /ds",      # a Fuseki someone else started
    None,                                                                                  # no such process, or it cannot be read
])
def test_a_saved_process_id_that_now_belongs_to_another_process_is_never_signalled(tmp_path, now_running):
    saved(tmp_path)
    def kill(pid, sig):
        raise AssertionError("another process was signalled")
    assert lf.stop(tmp_path, kill=kill, command_line=lambda pid: now_running) == ("stale", 4242)
    assert not (tmp_path / "fuseki.pid").exists()


@pytest.mark.parametrize("text", ["4242", '{"pid": 4242}', '{"pid": 4242, "token": ""}', "not json"])
def test_a_saved_file_without_a_token_proves_nothing_and_stops_nothing(tmp_path, text):
    saved(tmp_path, text)
    def kill(pid, sig):
        raise AssertionError("a process was signalled on its number alone")
    outcome, _ = lf.stop(tmp_path, kill=kill, command_line=lambda pid: OURS.replace("ab12", ""))
    assert outcome == "stale" and not (tmp_path / "fuseki.pid").exists()


def test_the_command_line_is_read_with_no_shell_on_either_system():
    calls = []
    def run(cmd, **options):
        calls.append((cmd, options))
        return SimpleNamespace(returncode=0, stdout=OURS + "\n")
    assert lf.command_line(4242, run, windows=False) == OURS and lf.command_line(4242, run, windows=True) == OURS
    assert calls[0][0] == ["ps", "-p", "4242", "-o", "command="]
    assert calls[1][0] == ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                           "(Get-CimInstance Win32_Process -Filter 'ProcessId=4242').CommandLine"]
    assert all("shell" not in options for _, options in calls)
    assert lf.command_line(4242, lambda cmd, **o: SimpleNamespace(returncode=1, stdout=""), windows=False) is None
    def missing(cmd, **options):
        raise OSError("no ps")
    assert lf.command_line(4242, missing, windows=False) is None


def test_a_fuseki_that_answers_is_reused_without_java(tmp_path, monkeypatch):
    fuseki = stores_support.local_settings(tmp_path).fuseki
    monkeypatch.setattr(lf, "answers", lambda f: True)
    monkeypatch.setattr(lf, "check_java", lambda *a, **k: pytest.fail("Java is not needed"))
    assert lf.ensure_running(fuseki, tmp_path / "state") == ("reused", None)


def test_answers_is_false_when_nothing_listens(tmp_path):
    fuseki = stores_support.local_settings(tmp_path).fuseki
    def refuse(request, timeout):
        raise OSError("connection refused")
    assert lf.answers(fuseki, refuse) is False
    seen = []
    class Ok:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *exc): return None
    assert lf.answers(fuseki, lambda request, timeout: seen.append(request.full_url) or Ok()) is True
    assert seen == ["http://127.0.0.1:3030/ds/query?query=ASK+%7B%7D"]


# ---- the dataset -----------------------------------------------------------------------------------

def test_the_dataset_holds_every_graph_of_the_release(tmp_path):
    root, ss, dataset = release(tmp_path)
    assert RDFSTORE.named_graphs(dataset) == GRAPHS and len(dataset) == 32
    assert lf.module_bases(ss) == BASES


def test_an_extra_graph_joins_the_dataset_and_may_not_take_a_release_graphs_name(tmp_path):
    root, ss, _ = release(tmp_path)
    (tmp_path / "tech").mkdir()
    (tmp_path / "tech" / "objects.ttl").write_text("<urn:sample:table> a <urn:sample:Table> .\n", encoding="utf-8", newline="\n")
    (tmp_path / "tech" / "graphs.json").write_text(json.dumps({"urn:sample:tech-graph": "objects.ttl"}), encoding="utf-8", newline="\n")
    extra = lf.read_extra_graphs(tmp_path / "tech" / "graphs.json")
    assert extra == {"urn:sample:tech-graph": tmp_path / "tech" / "objects.ttl"}
    dataset = lf.pack(RDFSTORE, lf.store_graphs(root, ss, extra))
    assert RDFSTORE.named_graphs(dataset) == sorted(GRAPHS + ["urn:sample:tech-graph"]) and len(dataset) == 33
    with pytest.raises(lf.FusekiError, match="has the name of a release graph"):
        lf.store_graphs(root, ss, {DP + "1.0.0/shapes": tmp_path / "tech" / "objects.ttl"})


@pytest.mark.parametrize("text, message", [
    ('{"urn:sample:g": "gone.ttl"}', "which is missing"), ('["urn:sample:g"]', "must map each graph IRI to a file"),
    ('{"no-colon": "objects.ttl"}', "must map each graph IRI to a file"), ("{", "cannot read the extra graphs file")])
def test_a_wrong_extra_graphs_file_is_refused(tmp_path, text, message):
    (tmp_path / "graphs.json").write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(lf.FusekiError, match=message):
        lf.read_extra_graphs(tmp_path / "graphs.json")


# ---- the load --------------------------------------------------------------------------------------

def test_the_first_load_writes_and_the_second_changes_nothing(tmp_path):
    _, _, dataset = release(tmp_path)
    store = stores_support.FakeFuseki(RDFSTORE)
    first = lf.load(store, dataset, RDFSTORE, BASES)
    assert (first["status"], first["graphs"], first["triples"], first["dropped"]) == ("loaded", 7, 32, [])
    assert first["store_hash"] == first["dataset_hash"] and store.writes == ["publish"]
    assert store.graphs() == GRAPHS
    second = lf.load(store, dataset, RDFSTORE, BASES)
    assert second["status"] == "current" and store.writes == ["publish"]


def test_an_earlier_version_of_a_module_is_dropped(tmp_path):
    _, _, dataset = release(tmp_path)
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(DP + "0.9.0", 3)
    store.add(DP + "0.9.0/shapes")
    result = lf.load(store, dataset, RDFSTORE, BASES)
    assert result["status"] == "loaded" and result["dropped"] == [DP + "0.9.0", DP + "0.9.0/shapes"]
    assert store.writes == [f"DROP SILENT GRAPH <{DP}0.9.0>", f"DROP SILENT GRAPH <{DP}0.9.0/shapes>", "publish"]
    assert store.graphs() == GRAPHS


@pytest.mark.parametrize("graph, named", [("urn:other:work", "urn:other:work"), (None, "the default graph")])
def test_a_graph_that_is_not_the_kpi_stores_stops_the_load_before_any_write(tmp_path, graph, named):
    _, _, dataset = release(tmp_path)
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(graph, 2)
    with pytest.raises(lf.FusekiError, match=f"1 graph\\(s\\) that are not the KPI Store's, e.g. \\['\\(?{named}"):
        lf.load(store, dataset, RDFSTORE, BASES)
    assert store.writes == [] and len(store.dataset) == 2
    result = lf.load(store, dataset, RDFSTORE, BASES, drop_unknown=True)
    assert result["status"] == "loaded" and store.graphs() == GRAPHS and len(store.dataset) == 32


def test_the_technical_graphs_graphs_are_left_alone_and_out_of_the_hash(tmp_path):
    _, _, dataset = release(tmp_path)
    apart = ["urn:kpi-store:tech:idp_sbx+synapse_dev:graph"]
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(apart[0], 5)
    first = lf.load(store, dataset, RDFSTORE, BASES, apart=apart)
    assert first["status"] == "loaded" and first["store_hash"] == first["dataset_hash"] and first["dropped"] == []
    assert store.graphs() == sorted(GRAPHS + apart) and len(store.dataset) == 37   # its five triples are still there
    assert lf.load(store, dataset, RDFSTORE, BASES, apart=apart)["status"] == "current" and store.writes == ["publish"]
    assert len(lf.held_dataset(store, RDFSTORE, apart)) == 32 and len(lf.held_dataset(store, RDFSTORE)) == 37


def test_a_load_run_alone_leaves_the_technical_graph_a_runner_load_left(tmp_path):
    """The command run alone gets no technical-graph file, so nothing names the graph apart. It knows the graph by
    its name's form and leaves it, with --drop-unknown too."""
    _, _, dataset = release(tmp_path)
    tech = "urn:kpi-store:tech:idp_sbx+synapse_dev:graph"
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(tech, 5)
    first = lf.load(store, dataset, RDFSTORE, BASES)
    assert first["status"] == "loaded" and first["store_hash"] == first["dataset_hash"] and first["dropped"] == []
    assert store.graphs() == sorted(GRAPHS + [tech]) and len(store.dataset) == 37
    assert lf.load(store, dataset, RDFSTORE, BASES)["status"] == "current" and store.writes == ["publish"]
    assert lf.load(store, dataset, RDFSTORE, BASES, drop_unknown=True)["status"] == "current" and len(store.dataset) == 37


@pytest.mark.parametrize("graph", ["urn:kpi-store:tech:idp_sbx:other", "urn:kpi-store:tech:graph",
                                   "urn:other:tech:idp_sbx:graph", "urn:kpi-store:tech:idp_sbx:graph/more"])
def test_a_name_that_only_looks_like_the_technical_graphs_still_stops_the_load(tmp_path, graph):
    _, _, dataset = release(tmp_path)
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(graph, 2)
    with pytest.raises(lf.FusekiError, match="1 graph\\(s\\) that are not the KPI Store's"):
        lf.load(store, dataset, RDFSTORE, BASES)
    assert store.writes == []


def test_a_dataset_the_store_cannot_hold_is_refused_before_an_earlier_version_is_dropped(tmp_path):
    _, _, dataset = release(tmp_path)
    ox = RDFSTORE.ox
    shared = ox.BlankNode("shared")
    for graph in (DP + "1.0.0", KPI + "1.0.0"):   # one blank node in two graphs
        dataset.add(ox.Quad(shared, ox.NamedNode("urn:sample:p"), ox.Literal("made up"), ox.NamedNode(graph)))
    store = stores_support.FakeFuseki(RDFSTORE)
    store.add(DP + "0.9.0", 3)
    with pytest.raises(lf.FusekiError, match="a blank node occurs in more than one graph"):
        lf.load(store, dataset, RDFSTORE, BASES)
    assert store.writes == [] and store.graphs() == [DP + "0.9.0"] and len(store.dataset) == 3


def test_a_store_that_alters_a_triple_reads_as_a_mismatch(tmp_path):
    _, _, dataset = release(tmp_path)
    result = lf.load(stores_support.FakeFuseki(RDFSTORE, alter=True), dataset, RDFSTORE, BASES)
    assert result["status"] == "mismatch" and result["store_hash"] != result["dataset_hash"]
    assert "mismatch" in lf.line({**result, "persistent": True, "server": "reused"})


def test_a_store_that_lost_a_graph_is_loaded_again(tmp_path):
    _, _, dataset = release(tmp_path)
    store = stores_support.FakeFuseki(RDFSTORE)
    lf.load(store, dataset, RDFSTORE, BASES)
    store._drop(store.ox.NamedNode(KPI + "1.0.0/shapes"))
    assert len(store.graphs()) == 6
    assert lf.load(store, dataset, RDFSTORE, BASES)["status"] == "loaded" and store.graphs() == GRAPHS


def test_the_line_says_whether_a_restart_keeps_the_dataset():
    result = {"status": "loaded", "graphs": 7, "triples": 32, "dataset_hash": "ab12", "store_hash": "ab12", "server": "started"}
    assert lf.line({**result, "persistent": True}) == ("fuseki: loaded, 7 graphs, 32 triples, RDFC-1.0 hash ab12 equal in "
                                                      "the store and the release files (started server, kept on disk)")
    assert "in memory: a restart empties it" in lf.line({**result, "persistent": False})
    tech = {"status": "loaded", "graphs": {"urn:kpi-store:tech:sample:graph": 269}}
    assert lf.line({**result, "persistent": True, "tech_graph": tech}).endswith("kept on disk); technical graph loaded, 269 triples")


def test_the_command_refuses_bad_settings_before_anything_else(tmp_path, capsys):
    assert lf.main(["--stores", str(tmp_path / "missing.toml")]) == 2
    assert "cannot read the local settings file" in capsys.readouterr().err
