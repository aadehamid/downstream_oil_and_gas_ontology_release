"""The AI providers the propose command may ask (KPI-DEC-0002, Q18 and Q22), and the one call each makes.

The local settings file's [ai] table names the provider (kpi_store/local_settings.py). The client's IT approves the
choice once, and the table records who approved it and when (approved_by, approved_on). ready() refuses AI, in a
plain sentence, unless the provider is set, approved and complete.

    databricks   a model served in the client's Databricks workspace, the default choice (Q18): the serving
                 endpoint `model`, at <host>/serving-endpoints/<model>/invocations. The host and the token come
                 from the Databricks configuration profile `profile` (no profile takes anything from [DEFAULT]),
                 or the token from the environment variable `key_env` and the address from `url`.
    anthropic    the Anthropic Messages API, with the API key in the environment variable `key_env`.
    openai       OpenAI chat completions, with the API key in the environment variable `key_env`.
    by-hand      no call. The command writes the prompt to a file. The person gives it to an assistant, such as
                 Genie Code in the Databricks workspace with the release's skills folder registered, saves the
                 answer to a file, and runs the command again with that file (kpi_store/ai/suggest.py).

Each call sends the instructions (the release's skills, Q26) as the system prompt and the task as the one user
message, and takes back one text. The request formats follow each provider's own reference, read on 2026-11-20:

    Databricks   https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/api-reference
                 (last updated 2026-11-15): POST /serving-endpoints/{name}/invocations, a body of `messages` with
                 the roles system and user, and `max_tokens`; the reply's text is choices[0].message.content and
                 its `model` is "the model version used to generate the response". The token is a bearer token.
                 https://docs.databricks.com/aws/en/dev-tools/cli/reference/auth-commands: `databricks auth
                 token` prints {"access_token": ..., "token_type": "Bearer", "expiry": ...} for a profile that
                 signed in with `databricks auth login`.
                 https://docs.databricks.com/aws/en/dev-tools/auth/config-profiles (last updated 2026-09-11): the
                 profiles are in the file .databrickscfg in the home folder, with the fields host and token.
    Anthropic    https://platform.claude.com/docs/en/api/http/messages/create and
                 https://platform.claude.com/docs/en/api/overview: POST https://api.anthropic.com/v1/messages, the
                 headers Authorization: Bearer <key>, anthropic-version: 2026-10-21 and content-type:
                 application/json, a body of `model`, `max_tokens`, the top-level `system` as text blocks, and
                 `messages`; the reply's text is in its `content` blocks of type text, and it names its `model`.
                 https://platform.claude.com/docs/en/api/versioning: 2026-10-21 is the newest API version.
    OpenAI       https://developers.openai.com/api/reference/resources/chat (the chat completions reference):
                 POST https://api.openai.com/v1/chat/completions, the header Authorization: Bearer <key>, a body
                 of `model` and `messages` with the roles system and user; the reply's text is
                 choices[0].message.content, and it names its `model`.

A key or a token is never written to a file, never printed and never put in a message. The standard library makes
every call. Nothing here is specific to suggestions, so the AI-drafted modelling of KPI-DEC-0002, Q17(a), can use
the same call.
"""
import configparser
import datetime as dt
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import AIRefused

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2026-10-21"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_TOKENS = 4096
CALLED = ("databricks", "anthropic", "openai")
ENDPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")   # a serving endpoint's name goes into the URL's path
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DATE = re.compile(r"\d{4}-\d\d-\d\d")
SETTINGS_SECTION = 'HOW-TO-UPDATE.md, "Use AI to suggest answers (optional)"'


@dataclass(frozen=True)
class Reply:
    text: str             # the model's answer, as it gave it
    model_version: str    # the model the reply names, or "" when it names none
    endpoint: str = ""    # the address called: scheme, host, port and path, with no query and no user name


def check_url(url, what="[ai] url"):
    """The parts of an address the command may call: http or https, a host, a port that is a number, and no user
    name or password, which messages and records would show. Refuses any other address."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:   # an unmatched bracket, or a character no host name may hold
        raise AIRefused(f"{what} is not an http or https address with a host") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AIRefused(f"{what} is not an http or https address with a host")
    if parts.username is not None or parts.password is not None:
        raise AIRefused(f"{what} must not hold a user name or a password")
    try:
        port = parts.port
    except ValueError:
        port = 0
    if port == 0:
        raise AIRefused(f"{what} has a port that is not a number from 1 to 65535")
    return parts


def where(parts):
    """The host and port that messages name."""
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname   # an IPv6 address keeps its brackets
    return host + (f":{parts.port}" if parts.port is not None else "")


def endpoint_of(parts):
    return f"{parts.scheme}://{where(parts)}{parts.path}"


def ready(ai):
    """Refuses AI unless the [ai] table names a provider, records its approval and gives what the provider needs.
    Returns the settings when they are complete."""
    if ai.provider == "off":
        raise AIRefused("AI is off: the local settings file names no AI provider ([ai] provider is \"off\", or the "
                        f"file has no [ai] table). {SETTINGS_SECTION} says how the client's IT switches it on")
    if not ai.approved_by or not DATE.fullmatch(ai.approved_on) or not _is_date(ai.approved_on):
        raise AIRefused(f'the AI provider "{ai.provider}" has no recorded approval. The client\'s IT approves it once, '
                        "and the local settings file records it: [ai] approved_by names who approved it, and "
                        "approved_on gives the date as YYYY-MM-DD")
    if ai.key_env and not VARIABLE.fullmatch(ai.key_env):
        raise AIRefused("[ai] key_env must be the name of an environment variable, such as ANTHROPIC_API_KEY, and "
                        "never the key itself")
    if ai.provider == "by-hand":
        if not ai.assistant:
            raise AIRefused('[ai] assistant must name the assistant you give the prompt to, such as "Genie Code"')
        return ai
    if not ai.model:
        what = "the serving endpoint's name" if ai.provider == "databricks" else "the model's name"
        raise AIRefused(f"[ai] model must give {what}")
    if ai.provider == "databricks":
        if not ENDPOINT.fullmatch(ai.model):
            raise AIRefused("[ai] model must be the serving endpoint's name: letters, digits, dots, hyphens and "
                            "underscores")
        if bool(ai.profile) == bool(ai.key_env):
            raise AIRefused("[ai] needs exactly one of profile, the Databricks configuration profile, and key_env, the "
                            "environment variable that holds a Databricks token")
        if ai.profile and ai.url:
            raise AIRefused("[ai] url goes with key_env, not with profile: with a profile, the address comes from the "
                            "profile's host, so that its token goes only there")
        if ai.key_env and not ai.url:
            raise AIRefused("[ai] url must give the endpoint's address when the token comes from key_env, such as "
                            "https://<your workspace>/serving-endpoints/<the endpoint>/invocations")
    elif not ai.key_env:
        raise AIRefused("[ai] key_env must name the environment variable that holds the API key")
    if ai.url:
        check_url(ai.url)
    return ai


def _is_date(text):
    try:
        dt.date.fromisoformat(text)
        return True
    except ValueError:
        return False


def _clean(value, what):
    """A key or a token as it goes into a header. One with a line break or a NUL is refused, and never shown."""
    value = value.strip()
    if any(c in value for c in "\r\n\x00"):
        raise AIRefused(f"{what} holds a line break or a NUL, so it cannot be sent. Set it again with the key alone")
    return value


def _secret(ai, environ):
    value = environ.get(ai.key_env, "")
    if not value.strip():
        raise AIRefused(f"[ai] key_env names {ai.key_env}, which is not set. Set it in this terminal, then run the "
                        "command again")
    return _clean(value, f"the environment variable {ai.key_env}")


def _databricks_target(ai, environ, run):
    """(the URL, the token) of a Databricks serving endpoint."""
    if ai.key_env:
        return ai.url, _secret(ai, environ)
    path = Path(environ.get("DATABRICKS_CONFIG_FILE") or Path.home() / ".databrickscfg")
    # In .databrickscfg, [DEFAULT] is a profile like any other, so no profile takes a host or a token from it.
    parser = configparser.ConfigParser(interpolation=None, default_section="")
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, configparser.Error) as err:
        raise AIRefused(f"the Databricks configuration file {path} cannot be read ({type(err).__name__}). Sign in "
                        f"with: databricks auth login --profile {ai.profile}") from None
    section = parser[ai.profile] if parser.has_section(ai.profile) else None
    host = (section or {}).get("host", "").strip().rstrip("/")
    if not host:
        raise AIRefused(f"the Databricks configuration file {path} has no profile {ai.profile} with a host. Sign in "
                        f"with: databricks auth login --profile {ai.profile}")
    url = f"{host}/serving-endpoints/{ai.model}/invocations"
    check_url(url, f"the host of the profile {ai.profile} in {path.name}")
    token = (section or {}).get("token", "").strip()
    if token:
        return url, _clean(token, f"the token of the profile {ai.profile}")
    cli = shutil.which("databricks", path=environ.get("PATH"))
    if not cli:
        raise AIRefused(f"the profile {ai.profile} holds no token, and the databricks command is not on PATH to get "
                        "one. Install the Databricks CLI, or give the profile a token")
    try:
        done = run([cli, "auth", "token", "--profile", ai.profile], capture_output=True, text=True, timeout=120,
                   env=dict(environ))
        token = json.loads(done.stdout).get("access_token", "") if done.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        token = ""
    token = token.strip() if isinstance(token, str) else ""
    if not token:
        raise AIRefused(f"databricks auth token gave no token for the profile {ai.profile}. Sign in again with: "
                        f"databricks auth login --profile {ai.profile}")
    return url, _clean(token, f"the token databricks auth token gave for the profile {ai.profile}")


def request(ai, system, user, environ=None, run=subprocess.run):
    """The call the provider gets: (URL, headers, body). The body's system prompt is `system` exactly, and its one
    user message is `user`."""
    environ = os.environ if environ is None else environ
    ready(ai)
    json_type = {"Content-Type": "application/json"}
    if ai.provider == "databricks":
        url, token = _databricks_target(ai, environ, run)
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": MAX_TOKENS}
        return url, {**json_type, "Authorization": f"Bearer {token}"}, body
    if ai.provider == "anthropic":
        body = {"model": ai.model, "max_tokens": MAX_TOKENS, "system": [{"type": "text", "text": system}],
                "messages": [{"role": "user", "content": user}]}
        return (ai.url or ANTHROPIC_URL, {**json_type, "Authorization": f"Bearer {_secret(ai, environ)}",
                                          "anthropic-version": ANTHROPIC_VERSION}, body)
    if ai.provider == "openai":
        body = {"model": ai.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        return ai.url or OPENAI_URL, {**json_type, "Authorization": f"Bearer {_secret(ai, environ)}"}, body
    raise AIRefused(f'the provider "{ai.provider}" makes no call: the command writes the prompt to a file instead')


def _text_of(provider, reply):
    """The reply's text and the model it names, or AIRefused when the reply holds no whole answer."""
    if not isinstance(reply, dict):
        raise AIRefused("the AI provider's reply is not a JSON object")
    model = reply.get("model") if isinstance(reply.get("model"), str) else ""
    if provider == "anthropic":
        if reply.get("stop_reason") == "max_tokens":
            raise AIRefused(f"the AI's answer was cut off at {MAX_TOKENS} tokens, so it cannot be used")
        blocks = reply.get("content")
        texts = [b.get("text") for b in blocks if isinstance(b, dict) and b.get("type") == "text"] if isinstance(blocks, list) else []
    else:
        choices = reply.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        if first.get("finish_reason") == "length":
            raise AIRefused("the AI's answer was cut off at its length limit, so it cannot be used")
        content = first["message"].get("content") if isinstance(first.get("message"), dict) else None
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):   # a Databricks reasoning model gives parts; those of type text are the answer
            texts = [p.get("text") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        else:
            texts = []
    texts = [t for t in texts if isinstance(t, str)]
    if not "".join(texts).strip():
        raise AIRefused("the AI provider's reply holds no text")
    return Reply("".join(texts), model)


def ask(ai, system, user, environ=None, opener=urllib.request.urlopen, run=subprocess.run):
    """Asks the provider once and returns its Reply. Refuses, in a plain sentence, when the call fails, times out or
    gives no answer."""
    url, headers, body = request(ai, system, user, environ, run)
    parts = check_url(url)
    host = where(parts)
    call = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers,
                                  method="POST")
    try:
        with opener(call, timeout=ai.timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as err:
        raise AIRefused(f"the AI provider at {host} refused the request with HTTP {err.code} ({err.reason})") from None
    except (TimeoutError, socket.timeout):
        raise AIRefused(f"the AI provider at {host} gave no answer within {ai.timeout_seconds} seconds") from None
    except urllib.error.URLError as err:
        if isinstance(err.reason, (TimeoutError, socket.timeout)):
            raise AIRefused(f"the AI provider at {host} gave no answer within {ai.timeout_seconds} seconds") from None
        raise AIRefused(f"the AI provider at {host} cannot be reached ({err.reason})") from None
    except http.client.HTTPException as err:
        raise AIRefused(f"the AI provider at {host} sent a reply that broke off ({type(err).__name__})") from None
    except OSError as err:
        raise AIRefused(f"the AI provider at {host} cannot be reached ({type(err).__name__})") from None
    try:
        reply = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AIRefused(f"the AI provider at {host} sent a reply that is not JSON") from None
    found = _text_of(ai.provider, reply)
    return Reply(found.text, found.model_version, endpoint_of(parts))
