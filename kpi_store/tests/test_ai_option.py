"""The AI option of the propose command (KPI-DEC-0002, Q16 to Q20, Q22 and Q26).

A stub HTTP server in this file speaks each provider's documented request and reply: Databricks model serving,
the Anthropic Messages API and OpenAI chat completions. The tests check the exact request the command sends, with its
headers and its system prompt, which must equal the release's skill files. No test reaches a real service. The forms
and the proposals are written to temporary folders; the release tree is only read, except by the one apply test,
which runs on a scratch copy.
"""
import datetime as dt
import hashlib
import http.server
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

from kpi_store import apply as apply_cmd, local_settings as ls, propose as propose_cmd
from kpi_store.ai import AIRefused, providers, suggest
from kpi_store.change import approval
from kpi_store.tests import support
from kpi_store.tests.test_propose_apply import git, no_global_git, scratch_release  # noqa: F401 (a fixture)

ROOT = support.ROOT
NOW = dt.datetime(2026, 11, 20, 9, 0, tzinfo=dt.timezone.utc)
MEASURE = "https://w3id.org/mpc/ontology/modules/kpi/measure/unit-utilization"
SIGNED = {"data-owner": {"name": "A Data Owner", "date": "2026-11-20"},
          "architect": {"name": "An Architect", "date": "2026-11-20"}}
SAMPLE = ROOT / "kpi_store" / "ai" / "sample-answer.json"
APPROVED = {"approved_by": "An IT Approver", "approved_on": "2026-11-18"}


def quiet(line):
    pass


def form(folder, answers=None, sign_offs=None, name="unit-utilization"):
    """An unsigned term change of Unit Utilization, with the answers the shipped sample answer is about."""
    answers = answers if answers is not None else {"T2": "process unit utilisation", "T4": ["unit cap util"]}
    data = {"format": 1, "form": "term-change", "catalogue_version": "1.2", "kpi_name": "Unit Utilization",
            "request": {"number": "TC-2026-002", "date": "2026-11-20", "requester_role": "Data Owner", "invited": ""},
            "answers": {"T1": MEASURE, "T8": "yes", **answers}, "sign_offs": sign_offs or {},
            "consulted": {}, "example_of": "", "comment": ""}
    path = Path(folder) / f"{name}.term-change.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def sign(path, sign_offs=SIGNED):
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sign_offs"] = sign_offs
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def skills_text():
    return "\n\n".join((ROOT / name).read_bytes().decode("utf-8") for name in suggest.SKILLS)


def settings(folder, text):
    path = Path(folder) / "kpi-store-local.toml"
    path.write_text(text, encoding="utf-8")
    return path


def by_hand(**more):
    return ls.AI("by-hand", assistant="Genie Code", **{**APPROVED, **more})


# ---------- the stub server ----------

class Stub:
    """A local HTTP server that records each request and answers with the reply set for its path."""

    def __init__(self):
        self.requests, self.replies, self.delay = [], {}, 0
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                stub.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                                      "body": json.loads(body)})
                if stub.delay:
                    time.sleep(stub.delay)
                status, reply = stub.replies.get(self.path, (404, {"error": "no such path"}))
                data = reply.encode() if isinstance(reply, str) else json.dumps(reply).encode()
                short = status == "short"   # a reply that promises more bytes than it sends, then closes
                try:
                    self.send_response(200 if short else status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data) + 100 if short else len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub(monkeypatch):
    no_proxy(monkeypatch)
    s = Stub()
    yield s
    s.close()


def chat_reply(text, model="the-served-model-2026-11-01"):
    """A chat completion, in the form Databricks model serving and OpenAI both document."""
    return {"id": "chatcmpl-1", "object": "chat.completion", "created": 1795000000, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def messages_reply(text, model="claude-sample-2026-10-01"):
    """A message, in the form the Anthropic Messages API documents."""
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


SAMPLE_TEXT = SAMPLE.read_text(encoding="utf-8")
YES_NO = {"T2": "yes", "T4": "no"}


def choices(folder, given=YES_NO):
    path = Path(folder) / "choices.json"
    path.write_text(json.dumps(given), encoding="utf-8")
    return path


# ---------- the settings ----------

def test_ai_is_off_unless_the_settings_name_an_approved_provider(tmp_path):
    example = ls.parse((ROOT / "kpi_store" / "stores.example.toml").read_bytes(), tmp_path / "local.toml",
                       environ={"SAMPLE_PW": "x"}, release_root=ROOT)
    assert example.ai.provider == "off"
    bare = ls.parse(b'[tools]\nbash = ""\n', tmp_path / "local.toml", release_root=ROOT)
    assert bare.ai == ls.AI_OFF
    with pytest.raises(AIRefused, match=r'^AI is off: the local settings file names no AI provider \(\[ai\] provider is "off"'):
        providers.ready(bare.ai)
    for missing in ({"approved_by": ""}, {"approved_on": ""}, {"approved_on": "2026-13-40"}):
        with pytest.raises(AIRefused, match='the AI provider "by-hand" has no recorded approval'):
            providers.ready(by_hand(**missing))
    assert providers.ready(by_hand()).assistant == "Genie Code"
    with pytest.raises(AIRefused, match="assistant must name the assistant"):
        providers.ready(ls.AI("by-hand", **APPROVED))
    with pytest.raises(AIRefused, match="key_env must name the environment variable"):
        providers.ready(ls.AI("anthropic", model="m", **APPROVED))
    with pytest.raises(AIRefused, match="exactly one of profile"):
        providers.ready(ls.AI("databricks", model="kpi-chat", **APPROVED))
    with pytest.raises(AIRefused, match="never the key itself"):
        providers.ready(ls.AI("openai", model="m", key_env="sk-live-123", **APPROVED))


def test_the_settings_file_holds_no_key(tmp_path):
    for key in ("api_key", "token", "secret"):
        with pytest.raises(ls.LocalSettingsError, match=f"^\\[ai\\] {key} is not a setting: the file holds no key or token"):
            ls.parse(f'[ai]\nprovider = "anthropic"\n{key} = "sk-123"\n'.encode(), tmp_path / "l.toml", release_root=ROOT)
    with pytest.raises(ls.LocalSettingsError, match=r'\[ai\] provider must be "off", "databricks"'):
        ls.parse(b'[ai]\nprovider = "genie"\n', tmp_path / "l.toml", release_root=ROOT)
    with pytest.raises(ls.LocalSettingsError, match=r"\[ai\] lacks 'provider'"):
        ls.parse(b'[ai]\nmodel = "m"\n', tmp_path / "l.toml", release_root=ROOT)


# ---------- the request each provider gets ----------

def test_databricks_serving_gets_the_skill_as_system_prompt_and_a_bearer_token_from_the_profile(tmp_path, stub):
    cfg = tmp_path / "databrickscfg"
    cfg.write_text(f"[kpi]\nhost = {stub.url}/\ntoken = dapi-sample-token\n", encoding="utf-8")
    stub.replies["/serving-endpoints/kpi-chat/invocations"] = (200, chat_reply('{"suggestions": []}'))
    ai = ls.AI("databricks", model="kpi-chat", profile="kpi", **APPROVED)
    reply = providers.ask(ai, "THE SKILL", "THE TASK", environ={"DATABRICKS_CONFIG_FILE": str(cfg)})
    assert reply == providers.Reply('{"suggestions": []}', "the-served-model-2026-11-01",
                                    f"{stub.url}/serving-endpoints/kpi-chat/invocations")
    [sent] = stub.requests
    assert sent["path"] == "/serving-endpoints/kpi-chat/invocations"
    assert sent["headers"]["authorization"] == "Bearer dapi-sample-token"
    assert sent["headers"]["content-type"] == "application/json"
    assert sent["body"] == {"messages": [{"role": "system", "content": "THE SKILL"}, {"role": "user", "content": "THE TASK"}],
                            "max_tokens": providers.MAX_TOKENS}


def test_databricks_takes_a_signed_in_profile_s_token_from_the_cli(tmp_path, stub, monkeypatch):
    cfg = tmp_path / "databrickscfg"
    cfg.write_text(f"[DEFAULT]\nhost = {stub.url}\nauth_type = databricks-cli\n", encoding="utf-8")
    stub.replies["/serving-endpoints/kpi-chat/invocations"] = (200, chat_reply("text"))
    monkeypatch.setattr(providers.shutil, "which", lambda name, path=None: "/opt/databricks")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps({"access_token": "oauth-token", "token_type": "Bearer"}), "")
    ai = ls.AI("databricks", model="kpi-chat", profile="DEFAULT", **APPROVED)
    providers.ask(ai, "S", "U", environ={"DATABRICKS_CONFIG_FILE": str(cfg)}, run=run)
    assert calls == [["/opt/databricks", "auth", "token", "--profile", "DEFAULT"]]
    assert stub.requests[0]["headers"]["authorization"] == "Bearer oauth-token"
    with pytest.raises(AIRefused, match="databricks auth token gave no token for the profile DEFAULT"):
        providers.ask(ai, "S", "U", environ={"DATABRICKS_CONFIG_FILE": str(cfg)},
                      run=lambda args, **k: subprocess.CompletedProcess(args, 1, "", "not signed in"))
    with pytest.raises(AIRefused, match="has no profile other with a host"):
        providers.ask(ls.AI("databricks", model="kpi-chat", profile="other", **APPROVED), "S", "U",
                      environ={"DATABRICKS_CONFIG_FILE": str(cfg)})


def test_the_anthropic_messages_api_gets_its_documented_headers_and_the_skill_as_system(stub):
    stub.replies["/v1/messages"] = (200, messages_reply("the answer"))
    ai = ls.AI("anthropic", model="claude-sample", key_env="SAMPLE_ANTHROPIC_KEY", url=stub.url + "/v1/messages", **APPROVED)
    reply = providers.ask(ai, "THE SKILL", "THE TASK", environ={"SAMPLE_ANTHROPIC_KEY": "sk-ant-sample"})
    assert reply == providers.Reply("the answer", "claude-sample-2026-10-01", f"{stub.url}/v1/messages")
    [sent] = stub.requests
    assert sent["path"] == "/v1/messages"
    assert sent["headers"]["authorization"] == "Bearer sk-ant-sample"
    assert sent["headers"]["anthropic-version"] == "2026-10-21"
    assert sent["headers"]["content-type"] == "application/json"
    assert sent["body"] == {"model": "claude-sample", "max_tokens": providers.MAX_TOKENS,
                            "system": [{"type": "text", "text": "THE SKILL"}],
                            "messages": [{"role": "user", "content": "THE TASK"}]}
    assert providers.request(ls.AI("anthropic", model="m", key_env="K", **APPROVED), "S", "U", {"K": "k"})[0] == \
        "https://api.anthropic.com/v1/messages"


def test_openai_chat_completions_gets_a_bearer_key_and_a_system_message(stub):
    stub.replies["/v1/chat/completions"] = (200, chat_reply("the answer", model="gpt-sample-2026"))
    ai = ls.AI("openai", model="gpt-sample", key_env="SAMPLE_OPENAI_KEY", url=stub.url + "/v1/chat/completions", **APPROVED)
    assert providers.ask(ai, "THE SKILL", "THE TASK", environ={"SAMPLE_OPENAI_KEY": "sk-sample"}) == \
        providers.Reply("the answer", "gpt-sample-2026", f"{stub.url}/v1/chat/completions")
    [sent] = stub.requests
    assert sent["headers"]["authorization"] == "Bearer sk-sample"
    assert sent["body"] == {"model": "gpt-sample", "messages": [{"role": "system", "content": "THE SKILL"},
                                                               {"role": "user", "content": "THE TASK"}]}
    assert providers.request(ls.AI("openai", model="m", key_env="K", **APPROVED), "S", "U", {"K": "k"})[0] == \
        "https://api.openai.com/v1/chat/completions"


def test_a_failed_call_is_refused_in_a_plain_sentence_that_names_no_key(stub):
    ai = ls.AI("openai", model="m", key_env="K", url=stub.url + "/v1/chat/completions", timeout_seconds=1, **APPROVED)
    environ = {"K": "sk-very-secret"}
    with pytest.raises(AIRefused, match="key_env names K, which is not set") as err:
        providers.ask(ai, "S", "U", environ={})
    stub.replies["/v1/chat/completions"] = (401, {"error": {"message": "bad key sk-very-secret"}})
    with pytest.raises(AIRefused) as err:
        providers.ask(ai, "S", "U", environ=environ)
    assert str(err.value).startswith("the AI provider at 127.0.0.1:") and "HTTP 401" in str(err.value)
    assert "sk-very-secret" not in str(err.value)
    stub.replies["/v1/chat/completions"] = (200, "this is not JSON")
    with pytest.raises(AIRefused, match="sent a reply that is not JSON"):
        providers.ask(ai, "S", "U", environ=environ)
    for broken in ({"choices": []}, {"choices": [{"message": {"content": ""}}]},
                   {"choices": [{"message": {"content": "x"}, "finish_reason": "length"}]}):
        stub.replies["/v1/chat/completions"] = (200, broken)
        with pytest.raises(AIRefused, match="holds no text|cut off"):
            providers.ask(ai, "S", "U", environ=environ)
    stub.replies["/v1/chat/completions"] = (200, chat_reply("late"))
    stub.delay = 2
    with pytest.raises(AIRefused, match=r"gave no answer within 1 seconds$"):
        providers.ask(ai, "S", "U", environ=environ)
    stub.delay = 0
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(AIRefused, match="cannot be reached"):
        providers.ask(ls.AI("openai", model="m", key_env="K", url=f"http://127.0.0.1:{port}/x", **APPROVED), "S", "U",
                      environ=environ)


# ---------- the suggestions ----------

def test_the_system_prompt_is_the_release_s_skills_read_at_run_time(tmp_path, stub):
    path = form(tmp_path)
    stub.replies["/v1/messages"] = (200, messages_reply(SAMPLE_TEXT))
    ai = ls.AI("anthropic", model="claude-sample", key_env="K", url=stub.url + "/v1/messages", **APPROVED)
    record = suggest.run(path, ROOT, ai=ai, choices_file=choices(tmp_path), today="2026-11-20",
                         environ={"K": "k"}, say=quiet)
    [sent] = stub.requests
    assert sent["body"]["system"] == [{"type": "text", "text": skills_text()}]
    user = sent["body"]["messages"][0]["content"]
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert "prompt" not in saved
    assert saved["skills"] == [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
                               for name in suggest.SKILLS]
    assert saved["prompt_sha256"] == hashlib.sha256((skills_text() + "\n\n" + user).encode()).hexdigest()
    assert saved["output_sha256"] == hashlib.sha256(SAMPLE_TEXT.encode()).hexdigest()
    assert {k: saved[k] for k in ("format", "form", "provider", "assistant", "model", "model_version", "approved_by",
                                  "approved_on", "asked_on")} == \
        {"format": 1, "form": "term-change", "provider": "anthropic", "assistant": "", "model": "claude-sample",
         "model_version": "claude-sample-2026-10-01", "approved_by": "An IT Approver", "approved_on": "2026-11-18",
         "asked_on": "2026-11-20"}
    # The task gives the form's free-text answers, its choice of a measure by name, and the measures and processes.
    assert '"question": "T2"' in user and '"answer": "process unit utilisation"' in user
    assert '"answer": "Unit Utilization"' in user and "- Unit Utilization (unit-utilization): " in user
    assert "The processes and steps of the process map:" in user and '"question": "T8"' not in user


def test_the_by_hand_round_trip_writes_the_prompt_reads_the_answer_and_keeps_only_accepted_suggestions(tmp_path):
    path = form(tmp_path)
    said = []
    assert suggest.run(path, ROOT, ai=by_hand(), today="2026-11-20", say=said.append) is None
    prompt = tmp_path / "unit-utilization.term-change.ai-prompt.txt"
    assert said[0] == f"wrote the prompt for the AI: {prompt.as_posix()}"
    assert said[1].startswith("Give that file to Genie Code. Save its answer")
    assert prompt.read_bytes().decode("utf-8").startswith(skills_text() + "\n\n# The task\n")
    assert not (tmp_path / "unit-utilization.term-change.ai.json").exists()
    answer = tmp_path / "answer.json"
    answer.write_text("```json\n" + SAMPLE_TEXT + "```\n", encoding="utf-8")   # as a chat often wraps it
    typed = iter(["maybe", "yes", "n"])
    said = []
    record = suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, today="2026-11-20", ask=lambda q: next(typed),
                         say=said.append)
    assert "the AI suggested 2 changes" in said and "accepted 1 of 2 suggestions; wrote it into unit-utilization.term-change.json" in said
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert (saved["provider"], saved["assistant"], saved["model_version"]) == ("by-hand", "Genie Code", "")
    assert saved["prompt_sha256"] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert [(s["question"], s["accepted"]) for s in saved["suggestions"]] == [("T2", True), ("T4", False)]
    answers = json.loads(path.read_text(encoding="utf-8"))["answers"]
    assert answers["T2"] == "Process Unit Utilization" and answers["T4"] == ["unit cap util"]

    # Signed, the form becomes a proposal that holds the accepted change and not the rejected one.
    sign(path)
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    lines = (folder / "change.kgcl").read_text(encoding="utf-8").splitlines()
    assert lines == ["rename measure:unit-utilization from 'Unit Utilization' to 'Process Unit Utilization'",
                     "create exact synonym 'unit cap util' for measure:unit-utilization"]
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["ai"] == dict(saved, suggestions=[dict(saved["suggestions"][0], kept=True),
                                                    dict(saved["suggestions"][1], kept=False)])
    text = (folder / "summary.txt").read_text(encoding="utf-8")
    assert "AI suggestions: Genie Code was asked on 2026-11-20, with the provider approved by An IT Approver on 2026-11-18." in text
    assert '  - T2, accepted (the signed form holds it): "Process Unit Utilization".' in text
    assert '  - T4, rejected: ["unit capacity utilization"].' in text
    assert text.index("AI suggestions:") < text.index("Nothing in the ontology has changed yet.")


def test_a_signer_s_later_change_to_an_accepted_answer_shows_in_the_record(tmp_path):
    path = form(tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path), say=quiet)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["answers"]["T2"] = "Process Unit Utilization (Refinery)"
    data["sign_offs"] = SIGNED
    path.write_text(json.dumps(data), encoding="utf-8")
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert record["ai"]["suggestions"][0]["kept"] is False
    assert "T2, accepted (a person changed it again before signing)" in (folder / "summary.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("answer, reason", [
    ("Here are my suggestions.", r"^the AI's answer is not JSON \(Expecting value, line 1\)$"),
    ('{"changes": []}', r'^the AI\'s answer is not of the form \{"suggestions": \[...\]\}$'),
    ('{"suggestions": [{"question": "T2", "current": "process unit utilisation", "suggested": "X"}]}',
     "suggestion 1 does not hold exactly question, current, suggested and reason"),
    ('{"suggestions": [{"question": "T9", "current": "", "suggested": "X", "reason": "r"}]}',
     "names the question 'T9', which is not one the AI was asked about"),
    ('{"suggestions": [{"question": "T8", "current": "yes", "suggested": "no", "reason": "r"}]}',
     "names the question 'T8', which is not one the AI was asked about"),
    ('{"suggestions": [{"question": "T2", "current": "another name", "suggested": "X", "reason": "r"}]}',
     "for T2, gives another answer than the form holds as the answer now"),
    ('{"suggestions": [{"question": "T4", "current": ["unit cap util"], "suggested": "one", "reason": "r"}]}',
     "for T4, must suggest a list of texts"),
    ('{"suggestions": [{"question": "T2", "current": "process unit utilisation", "suggested": "X", "reason": " "}]}',
     "for T2, gives no reason"),
    ('{"suggestions": [{"question": "T2", "current": "process unit utilisation", "suggested": "process unit utilisation", "reason": "r"}]}',
     "suggests the answer the form holds already"),
    ('{"suggestions": [{"question": "T1", "current": "Unit Utilization", "suggested": "A Made-up Measure", "reason": "r"}]}',
     'for T1, names "A Made-up Measure", which is not an entry of the list measures'),
    ('{"suggestions": [{"question": "T2", "current": "process unit utilisation", "suggested": "X", "reason": "r"},'
     ' {"question": "T2", "current": "process unit utilisation", "suggested": "Y", "reason": "r"}]}',
     "suggestion 2 is a second suggestion for T2"),
])
def test_an_answer_that_is_not_the_asked_json_is_refused_whole_and_changes_nothing(tmp_path, answer, reason):
    path = form(tmp_path)
    before = path.read_bytes()
    given = tmp_path / "answer.json"
    given.write_text(answer, encoding="utf-8")
    with pytest.raises(AIRefused, match=reason):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=given, choices_file=choices(tmp_path), say=quiet)
    assert path.read_bytes() == before and not (tmp_path / "unit-utilization.term-change.ai.json").exists()


def test_a_choice_suggestion_names_an_entry_and_the_form_takes_its_id(tmp_path):
    path = form(tmp_path)
    given = tmp_path / "answer.json"
    given.write_text(json.dumps({"suggestions": [{"question": "T1", "current": "Unit Utilization",
                                                  "suggested": "unit rates", "reason": "r"}]}), encoding="utf-8")
    with pytest.raises(AIRefused, match='names "unit rates", which is not an entry'):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=given, say=quiet)
    from kpi_store.intake import picklists
    other = next(m for m in picklists.load(ROOT / "kpi-intake")["lists"]["measures"] if m["id"] != MEASURE)
    given.write_text(json.dumps({"suggestions": [{"question": "T1", "current": "Unit Utilization",
                                                  "suggested": other["label"].upper(), "reason": "r"}]}), encoding="utf-8")
    suggest.run(path, ROOT, ai=by_hand(), answer_file=given, choices_file=choices(tmp_path, {"T1": "yes"}), say=quiet)
    assert json.loads(path.read_text(encoding="utf-8"))["answers"]["T1"] == other["id"]


def test_the_ai_step_comes_before_signing_and_happens_once(tmp_path):
    signed = form(tmp_path, sign_offs={"data-owner": {"name": "A Data Owner", "date": ""}}, name="signed")
    with pytest.raises(AIRefused, match=r"^signed.term-change.json is signed already \(data-owner\). AI suggestions come "
                                        "before anyone signs, so that each signer reads the answers the AI changed"):
        suggest.run(signed, ROOT, ai=by_hand(), say=quiet)
    path = form(tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text('{"suggestions": []}', encoding="utf-8")
    said = []
    suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, say=said.append)
    assert "the AI suggested 0 changes" in said and "accepted 0 of 0 suggestions; the form is as it was" in said
    with pytest.raises(AIRefused, match="unit-utilization.term-change.ai.json exists: this form has had its AI step"):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, say=quiet)
    workbook = tmp_path / "form.xlsx"
    workbook.write_bytes(b"")
    with pytest.raises(AIRefused, match="form.xlsx is not a form saved as JSON"):
        suggest.run(workbook, ROOT, ai=by_hand(), say=quiet)
    with pytest.raises(AIRefused, match='--ai-answer is for the by-hand provider, and the local settings name "openai"'):
        suggest.run(form(tmp_path, name="other"), ROOT, answer_file=answer, say=quiet,
                    ai=ls.AI("openai", model="m", key_env="K", **APPROVED))


def test_choices_from_a_file_must_answer_each_suggestion(tmp_path):
    path = form(tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    for given in ({"T2": "yes"}, {"T2": "yes", "T4": "perhaps"}, ["yes", "no"]):
        with pytest.raises(AIRefused, match="must give yes or no for exactly the questions T2, T4"):
            suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path, given), say=quiet)

    def closed(question):
        raise EOFError
    with pytest.raises(AIRefused, match="no choice was typed for a suggestion"):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, ask=closed, say=quiet)
    assert not (tmp_path / "unit-utilization.term-change.ai.json").exists()


def test_a_broken_or_mismatched_record_beside_a_form_stops_the_proposal(tmp_path):
    path = form(tmp_path, sign_offs=SIGNED)
    record = tmp_path / "unit-utilization.term-change.ai.json"
    record.write_text("{", encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="the record of the AI step unit-utilization.term-change.ai.json "
                                                         "cannot be read"):
        propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    record.write_text('{"format": 1}', encoding="utf-8")
    with pytest.raises(propose_cmd.ProposeRefused, match="is not complete: the record of the AI step must hold exactly"):
        propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    assert not (tmp_path / "proposals").exists()


def test_a_form_with_no_ai_step_gives_the_proposal_it_gave_before(tmp_path):
    path = form(tmp_path, sign_offs=SIGNED)
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    record = json.loads((folder / "approval.json").read_text(encoding="utf-8"))
    assert list(record) == list(approval.FIELDS)
    assert (folder / "approval.json").read_text(encoding="utf-8") == json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    assert "AI" not in (folder / "summary.txt").read_text(encoding="utf-8")
    assert sorted(p.name for p in folder.iterdir()) == ["approval.json", "change.kgcl", "summary.txt"]


# ---------- the command line ----------

def test_the_command_line_refuses_ai_in_a_plain_sentence(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ls.ENV_VAR, raising=False)
    path = form(tmp_path)
    off = settings(tmp_path, '[ai]\nprovider = "off"\n')
    assert propose_cmd.main(["--ai", str(path), "--stores", str(off), "--release", str(ROOT)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("No AI suggestions: AI is off: the local settings file names no AI provider") and "Traceback" not in err
    unapproved = settings(tmp_path, '[ai]\nprovider = "by-hand"\nassistant = "Genie Code"\n')
    assert propose_cmd.main(["--ai", str(path), "--stores", str(unapproved), "--release", str(ROOT)]) == 1
    assert 'the AI provider "by-hand" has no recorded approval' in capsys.readouterr().err
    assert propose_cmd.main(["--ai", str(path), "--release", str(ROOT)]) == 1
    assert "name the local settings file with --stores <file>, or set KPI_STORE_LOCAL" in capsys.readouterr().err
    assert propose_cmd.main(["--ai", str(path), str(path), "--stores", str(off)]) == 1
    assert "--ai takes one form" in capsys.readouterr().err
    assert propose_cmd.main([str(path), "--ai-answer", "x.json"]) == 1
    assert "--stores, --ai-answer and --ai-choices go with --ai" in capsys.readouterr().err


def test_the_command_line_runs_the_ai_step_against_a_provider(tmp_path, stub, capsys, monkeypatch):
    path = form(tmp_path)
    stub.replies["/serving-endpoints/kpi-chat/invocations"] = (200, chat_reply(SAMPLE_TEXT))
    monkeypatch.setenv("SAMPLE_SERVING_KEY", "dapi-sample")
    local = settings(tmp_path, '[ai]\nprovider = "databricks"\nmodel = "kpi-chat"\nkey_env = "SAMPLE_SERVING_KEY"\n'
                               f'url = "{stub.url}/serving-endpoints/kpi-chat/invocations"\n'
                               'approved_by = "An IT Approver"\napproved_on = "2026-11-18"\n')
    assert propose_cmd.main(["--ai", str(path), "--stores", str(local), "--release", str(ROOT),
                             "--ai-choices", str(choices(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"asked databricks (model kpi-chat) for suggestions on {path.name}\nthe AI suggested 2 changes\n")
    assert "  Your choice, from choices.json: yes" in out and "dapi-sample" not in out
    assert stub.requests[0]["headers"]["authorization"] == "Bearer dapi-sample"
    saved = json.loads((tmp_path / "unit-utilization.term-change.ai.json").read_text(encoding="utf-8"))
    assert (saved["provider"], saved["model"], saved["model_version"]) == ("databricks", "kpi-chat", "the-served-model-2026-11-01")


# ---------- apply keeps the record ----------

@pytest.mark.skipif(shutil.which("git") is None, reason="Git is not installed")
def test_apply_keeps_the_ai_record_in_the_release_s_approval_record(tmp_path, no_global_git):
    root = scratch_release(tmp_path, git_copy=True)
    path = form(tmp_path)
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path), say=quiet)
    sign(path)
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", root, now=NOW, say=quiet)
    apply_cmd.apply([folder], root, say=quiet, now=NOW)
    kept = approval.read_record(approval.record_path(root, folder.name))
    assert kept["ai"] == json.loads((folder / "approval.json").read_text(encoding="utf-8"))["ai"]
    assert git(root, "status", "--porcelain") == ""


# ---------- the first review's findings ----------

def _record(tmp_path, name="unit-utilization"):
    """A form and the complete record of its by-hand AI step, both written to tmp_path."""
    path = form(tmp_path, name=name)
    answer = tmp_path / f"{name}.answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    record = suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path), say=quiet)
    return path, record


def test_the_record_keeps_the_prompt_s_fingerprint_and_not_its_text(tmp_path):
    path = form(tmp_path)
    suggest.run(path, ROOT, ai=by_hand(), say=quiet)
    prompt = suggest.beside(path, suggest.PROMPT_SUFFIX).read_bytes()
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    record = suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path), say=quiet)
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert "prompt" not in saved and "prompt" not in approval.AI_FIELDS
    system, _ = suggest.instructions(ROOT)
    assert prompt.decode("utf-8").startswith(system + "\n\n# The task\n")
    assert saved["prompt_sha256"] == hashlib.sha256(prompt).hexdigest()
    sign(path)
    [folder] = propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)
    assert "prompt" not in json.loads((folder / "approval.json").read_text(encoding="utf-8"))["ai"]
    assert "the prompt and" not in (folder / "summary.txt").read_text(encoding="utf-8")


def test_a_named_databricks_profile_inherits_nothing_from_default(tmp_path, stub, monkeypatch):
    cfg = tmp_path / "databrickscfg"
    cfg.write_text(f"[DEFAULT]\nhost = {stub.url}\ntoken = dapi-dev-token\n\n[prod]\nhost = {stub.url}\n"
                   "auth_type = databricks-cli\n\n[nohost]\nauth_type = databricks-cli\n", encoding="utf-8")
    stub.replies["/serving-endpoints/kpi-chat/invocations"] = (200, chat_reply("text"))
    monkeypatch.setattr(providers.shutil, "which", lambda name, path=None: "/opt/databricks")
    run = lambda args, **k: subprocess.CompletedProcess(args, 0, json.dumps({"access_token": "prod-oauth"}), "")
    environ = {"DATABRICKS_CONFIG_FILE": str(cfg)}
    providers.ask(ls.AI("databricks", model="kpi-chat", profile="prod", **APPROVED), "S", "U", environ=environ, run=run)
    assert stub.requests[-1]["headers"]["authorization"] == "Bearer prod-oauth"
    with pytest.raises(AIRefused, match="has no profile nohost with a host"):
        providers.ask(ls.AI("databricks", model="kpi-chat", profile="nohost", **APPROVED), "S", "U", environ=environ, run=run)
    providers.ask(ls.AI("databricks", model="kpi-chat", profile="DEFAULT", **APPROVED), "S", "U", environ=environ, run=run)
    assert stub.requests[-1]["headers"]["authorization"] == "Bearer dapi-dev-token"


def test_a_broken_reply_or_a_secret_with_a_line_break_is_refused_without_a_traceback(stub):
    stub.replies["/v1/chat/completions"] = ("short", chat_reply("text"))
    ai = ls.AI("openai", model="m", key_env="K", url=stub.url + "/v1/chat/completions", **APPROVED)
    with pytest.raises(AIRefused, match="sent a reply that broke off"):
        providers.ask(ai, "S", "U", environ={"K": "k"})
    for value in ("sk-live-secret\nextra", "sk-live-secret\rextra", "sk-live\x00secret"):
        with pytest.raises(AIRefused) as err:
            providers.ask(ai, "S", "U", environ={"K": value})
        assert "K holds a line break or a NUL" in str(err.value) and "secret" not in str(err.value)


def no_proxy(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


def test_the_address_is_checked_and_messages_show_no_user_name_or_password(tmp_path, monkeypatch):
    no_proxy(monkeypatch)
    cfg = tmp_path / "databrickscfg"
    cfg.write_text("[kpi]\nhost = adb-123.azuredatabricks.net\ntoken = dapi-x\n", encoding="utf-8")
    with pytest.raises(AIRefused, match="is not an http or https address"):
        providers.ask(ls.AI("databricks", model="kpi-chat", profile="kpi", **APPROVED), "S", "U",
                      environ={"DATABRICKS_CONFIG_FILE": str(cfg)})
    cfg.write_text("[kpi]\nhost = file:///etc\ntoken = dapi-x\n", encoding="utf-8")
    with pytest.raises(AIRefused, match="is not an http or https address"):
        providers.ask(ls.AI("databricks", model="kpi-chat", profile="kpi", **APPROVED), "S", "U",
                      environ={"DATABRICKS_CONFIG_FILE": str(cfg)})
    for url in ("https://user:secret@127.0.0.1:1/v1", "http://127.0.0.1:badport/v1", "https:///v1"):
        with pytest.raises(AIRefused) as err:
            providers.ready(ls.AI("openai", model="m", key_env="K", url=url, **APPROVED))
        assert "secret" not in str(err.value) and "[ai] url" in str(err.value)
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(AIRefused, match=f"^the AI provider at 127.0.0.1:{port} cannot be reached"):
        providers.ask(ls.AI("openai", model="m", key_env="K", url=f"http://127.0.0.1:{port}/x?q=1", **APPROVED), "S", "U",
                      environ={"K": "k"})


def test_the_record_names_the_endpoint_called_and_a_profile_takes_no_url(tmp_path, stub):
    path = form(tmp_path)
    stub.replies["/v1/messages?x=1"] = (200, messages_reply(SAMPLE_TEXT))
    ai = ls.AI("anthropic", model="claude-sample", key_env="K", url=stub.url + "/v1/messages?x=1", **APPROVED)
    record = suggest.run(path, ROOT, ai=ai, choices_file=choices(tmp_path), environ={"K": "k"}, say=quiet)
    assert json.loads(record.read_text(encoding="utf-8"))["endpoint"] == stub.url + "/v1/messages"
    other = tmp_path / "other"
    other.mkdir()
    _, by_hand_record = _record(other)
    assert json.loads(by_hand_record.read_text(encoding="utf-8"))["endpoint"] == ""
    with pytest.raises(AIRefused, match="url goes with key_env, not with profile"):
        providers.ready(ls.AI("databricks", model="kpi-chat", profile="DEFAULT", url="https://other.example.com/x", **APPROVED))


def test_the_settings_file_is_refused_inside_the_release_named_and_read_from_the_given_environment(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    inside = settings(release, '[ai]\nprovider = "by-hand"\nassistant = "Genie Code"\napproved_by = "A"\napproved_on = "2026-11-18"\n')
    with pytest.raises(AIRefused, match="inside the release folder"):
        suggest.run(form(tmp_path), release, stores=str(inside), say=quiet)
    outside = settings(tmp_path, '[ai]\nprovider = "off"\n')
    with pytest.raises(AIRefused, match="AI is off"):
        suggest.run(form(tmp_path, name="other"), ROOT, environ={ls.ENV_VAR: str(outside)}, say=quiet)


@pytest.mark.parametrize("change", [
    {"format": True}, {"provider": "off"}, {"provider": ""}, {"approved_by": ""}, {"approved_on": "not-a-date"},
    {"asked_on": ""}, {"form": ""}, {"assistant": ""}, {"skills": [{"path": "", "sha256": "0" * 64}]},
])
def test_an_incomplete_ai_record_is_refused(tmp_path, change):
    _, record = _record(tmp_path)
    saved = json.loads(record.read_text(encoding="utf-8"))
    with pytest.raises(approval.ChangeRefused):
        approval.check_ai(dict(saved, **change), step=True)


@pytest.mark.parametrize("change", [{"question": ["T2"]}, {"question": ""}, {"reason": 3}, {"current": {"a": 1}},
                                    {"suggested": [1]}, {"answer": None}])
def test_a_suggestion_of_the_wrong_shape_stops_the_proposal_in_a_plain_sentence(tmp_path, change):
    path, record = _record(tmp_path)
    saved = json.loads(record.read_text(encoding="utf-8"))
    saved["suggestions"][0].update(change)
    record.write_text(json.dumps(saved), encoding="utf-8")
    sign(path)
    with pytest.raises(propose_cmd.ProposeRefused, match="is not complete"):
        propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)


@pytest.mark.skipif(os.name == "nt", reason="a folder's write permission works another way on Windows")
def test_a_record_that_cannot_be_written_leaves_the_form_as_it_was(tmp_path):
    folder = tmp_path / "locked"
    folder.mkdir()
    path = form(folder)
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    given = choices(tmp_path)
    before = path.read_bytes()
    folder.chmod(0o555)
    try:
        with pytest.raises(OSError):
            suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=given, say=quiet)
        assert path.read_bytes() == before
    finally:
        folder.chmod(0o755)


def test_a_choice_that_differs_only_in_case_is_no_change(tmp_path):
    path = form(tmp_path)
    given = tmp_path / "answer.json"
    given.write_text(json.dumps({"suggestions": [{"question": "T1", "current": "Unit Utilization",
                                                  "suggested": "unit utilization", "reason": "r"}]}), encoding="utf-8")
    with pytest.raises(AIRefused, match="suggests the answer the form holds already"):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=given, say=quiet)


def test_a_hidden_measure_is_not_offered_in_the_prompt():
    lists = {"measures": [{"label": "Shown Measure", "notation": "shown", "definition": "d", "id": "x:1"},
                          {"label": "Hidden Measure", "notation": "hidden", "definition": "d", "id": "x:2", "hidden": True}],
             "processes": []}
    text = "\n".join(suggest._names("term-change", lists, []))
    assert "Shown Measure" in text and "Hidden Measure" not in text


def test_the_fingerprints_are_of_the_files_bytes(tmp_path):
    root = tmp_path / "release"
    for name in suggest.SKILLS:
        (root / name).parent.mkdir(parents=True)
        (root / name).write_bytes(b"---\r\nname: x\r\n---\r\nA rule.\r\n")
    system, hashes = suggest.instructions(root)
    assert [h["sha256"] for h in hashes] == [hashlib.sha256((root / n).read_bytes()).hexdigest() for n in suggest.SKILLS]
    assert "\r\n" in system
    shutil.copytree(ROOT / "kpi-intake", root / "kpi-intake")
    path = form(tmp_path)
    suggest.run(path, root, ai=by_hand(), say=quiet)
    prompt = suggest.beside(path, suggest.PROMPT_SUFFIX).read_bytes()
    assert prompt.startswith(system.encode("utf-8") + b"\n\n# The task\n") and b"\r\n" in prompt
    answer = tmp_path / "answer.json"
    answer.write_bytes(SAMPLE_TEXT.replace("\n", "\r\n").encode())
    record = suggest.run(path, root, ai=by_hand(), answer_file=answer, choices_file=choices(tmp_path), say=quiet)
    saved = json.loads(record.read_text(encoding="utf-8"))
    assert saved["output_sha256"] == hashlib.sha256(answer.read_bytes()).hexdigest()
    assert saved["prompt_sha256"] == hashlib.sha256(prompt).hexdigest()


def test_a_record_for_another_kind_of_form_stops_the_proposal(tmp_path):
    path, record = _record(tmp_path)
    saved = json.loads(record.read_text(encoding="utf-8"))
    record.write_text(json.dumps(dict(saved, form="kpi-intake")), encoding="utf-8")
    sign(path)
    with pytest.raises(propose_cmd.ProposeRefused, match="is for a kpi-intake form, and unit-utilization.term-change.json "
                                                         "is a term-change form"):
        propose_cmd.propose([path], tmp_path / "proposals", ROOT, now=NOW, say=quiet)


# ---------- the second review's findings ----------

def test_an_ipv6_host_keeps_its_brackets_and_port_0_is_refused():
    parts = providers.check_url("http://[::1]:8080/v1/chat/completions")
    assert providers.where(parts) == "[::1]:8080"
    assert providers.endpoint_of(parts) == "http://[::1]:8080/v1/chat/completions"
    with pytest.raises(AIRefused, match="has a port that is not a number from 1 to 65535"):
        providers.check_url("http://127.0.0.1:0/v1")


def test_an_address_that_cannot_be_read_is_refused_in_a_plain_sentence():
    for url in ("https://[your-workspace/serving-endpoints/kpi-chat/invocations", "http://[::1/x"):
        with pytest.raises(AIRefused, match="is not an http or https address with a host"):
            providers.ready(ls.AI("openai", model="m", key_env="K", url=url, **APPROVED))


def _failing(monkeypatch, step, which):
    """Makes one step of writing one file fail: `step` is "write" or "replace", and `which` is "record" or "form"."""
    ending = suggest.RECORD_SUFFIX if which == "record" else ".term-change.json"
    hit = lambda p: Path(p).name.removesuffix(".tmp").endswith(ending)
    if step == "write":
        real = Path.write_text

        def write_text(self, *args, **kwargs):
            if self.name.endswith(".tmp") and hit(self):
                self.open("w").close()   # the disk took the file's name, then filled up
                raise OSError(28, "No space left on device")
            return real(self, *args, **kwargs)
        monkeypatch.setattr(Path, "write_text", write_text)
    else:
        real = os.replace

        def replace(src, dst):
            if hit(dst):
                raise PermissionError("the file is open in another program")
            return real(src, dst)
        monkeypatch.setattr(suggest.os, "replace", replace)


@pytest.mark.parametrize("step, which", [("replace", "record"), ("replace", "form"), ("write", "record"),
                                         ("write", "form"), ("directory", "form")])
def test_a_failed_write_leaves_the_form_as_it_was_and_no_record(tmp_path, monkeypatch, step, which):
    folder = tmp_path / "forms"
    folder.mkdir()
    path = form(folder)
    answer = tmp_path / "answer.json"
    answer.write_text(SAMPLE_TEXT, encoding="utf-8")
    given = choices(tmp_path)
    before = path.read_bytes()
    kept = []
    if step == "directory":   # a folder in the way of the form's .tmp file, which the command must leave alone
        (folder / (path.name + ".tmp")).mkdir()
        kept = [path.name + ".tmp"]
    else:
        _failing(monkeypatch, step, which)
    with pytest.raises(OSError):
        suggest.run(path, ROOT, ai=by_hand(), answer_file=answer, choices_file=given, say=quiet)
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert sorted(p.name for p in folder.iterdir()) == sorted([path.name] + kept)


def test_a_cli_token_that_is_not_text_or_is_blank_is_no_token(tmp_path, stub, monkeypatch):
    cfg = tmp_path / "databrickscfg"
    cfg.write_text(f"[prod]\nhost = {stub.url}\nauth_type = databricks-cli\n", encoding="utf-8")
    monkeypatch.setattr(providers.shutil, "which", lambda name, path=None: "/opt/databricks")
    ai = ls.AI("databricks", model="kpi-chat", profile="prod", **APPROVED)
    for token in (123, "   ", None, ["t"]):
        run = lambda args, token=token, **k: subprocess.CompletedProcess(args, 0, json.dumps({"access_token": token}), "")
        with pytest.raises(AIRefused, match="databricks auth token gave no token for the profile prod"):
            providers.ask(ai, "S", "U", environ={"DATABRICKS_CONFIG_FILE": str(cfg)}, run=run)
    assert stub.requests == []
