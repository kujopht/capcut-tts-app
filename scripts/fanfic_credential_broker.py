#!/usr/bin/env python3
"""Credential broker — moves secret values between trusted local tooling and
provider APIs WITHOUT the value ever entering an AI model's context.

The problem this solves: setting up production credentials previously required
a human to copy each value out of a browser and paste it somewhere. Every
automated alternative wanted the value to pass through the assistant, which
means through a conversation transcript. This broker breaks that chain: the
value lives in the Windows Credential Manager, and moves from there into a
consumer's stdin inside a single process. Claude can invoke every command
here, and none of them ever emit a secret.

Storage is the OS credential store (Windows Credential Manager, `advapi32`
CredRead/CredWrite via ctypes -- stdlib only, nothing to install). Not a
plaintext file, not an env var in a shell profile, not a repo file.

    # ONE human step per credential. The value is typed/pasted on stdin, so it
    # never appears in argv, in shell history, or on screen.
    python scripts/fanfic_credential_broker.py store --name CLOUDFLARE_API_TOKEN

    # Everything after this point is unattended and safe for Claude to run.
    python scripts/fanfic_credential_broker.py check --name CLOUDFLARE_API_TOKEN
    python scripts/fanfic_credential_broker.py list
    python scripts/fanfic_credential_broker.py push-github --name CLOUDFLARE_API_TOKEN

`push-github` streams the value straight from the credential store into
`gh secret set --body-file -` over a pipe. The value is never rendered, never
written to disk, never placed in argv.

Guarantees, each enforced by construction rather than by convention:
  - never printed to stdout or stderr (the only outputs are names and states)
  - never passed in argv (stdin for input, pipes for handoff)
  - never written to a repository file or any temp file
  - never recorded in telemetry (this module logs nothing but outcomes)
  - never placed in shell history (no shell interpolation of the value)

Exit codes are stable so a caller can branch without parsing text:
  0 success / present
  1 not found
  2 usage or environment error
  3 downstream tool failed (e.g. `gh` rejected the write)
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
# `ctypes.wintypes` raises on non-Windows, which would make this whole module
# unimportable there -- and with it the Render adapter below, whose logic is
# platform-independent and is the part most worth testing in CI (CI runs on
# Linux). The credential-store half stays Windows-only and refuses to run
# elsewhere via `_advapi32()`.
_WINDOWS = sys.platform == "win32"
if _WINDOWS:
    from ctypes import wintypes
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Every credential is namespaced so this never collides with, or reads, an
# unrelated Windows credential belonging to another application.
TARGET_PREFIX = "FanficWorld:"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168

# The canonical set. Keeping it explicit means `list` cannot accidentally
# enumerate unrelated secrets out of the user's credential store.
KNOWN_NAMES = (
    "RENDER_DEPLOY_HOOK_URL",
    # Render's REST API credential. Lets env vars be managed through the
    # supported API instead of typing secrets into a browser form -- the last
    # manual step in the production bootstrap.
    "RENDER_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    # Renamed from FANFIC_ADMIN_CANARY_TOKEN. The rename was free: no secret
    # of either name had been created yet, so there was nothing to migrate and
    # every consumer moved in one commit. The name now says what it is -- a
    # service credential, not a human admin's session.
    "FANFIC_CANARY_SERVICE_TOKEN",
    # Appwrite key for SCHEMA administration (collections/attributes/indexes).
    # Deliberately separate from the runtime `APPWRITE_API_KEY` that Render
    # holds: the backend only needs `documents`, and granting it
    # `collections.write` would hand schema-mutation power to every process
    # carrying the runtime key. Migrations are an operator action, so they
    # carry an operator credential -- and it lives HERE, in the OS credential
    # store, never in `server/.env`, never on Render.
    "APPWRITE_SCHEMA_API_KEY",
    # Beam Cloud API token (beam.cloud dashboard -> settings/api-keys).
    # Mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" (2026-09-01): every
    # `beam` CLI invocation and every `scripts/beam_*.py` HTTP call reads
    # this from the process environment (`beta9`'s own `SDKSettings` does
    # `os.getenv("BEAM_TOKEN")` -- confirmed by reading the installed
    # package source, not assumed) -- storing it here means the operator
    # types it ONCE (this broker's `store` command, stdin only) instead of
    # re-exporting `$env:BEAM_TOKEN` every session. See
    # `scripts/beam_credential.py::resolve_beam_token` for the read side.
    "BEAM_TOKEN",
    # Owner/admin-authenticated bearer token for fas-prod-api's real
    # `/api/novels` and `/api/chapters` write paths. Mission "SHIP A REAL
    # STORY NOW" (2026-09-01): the only credential already in this broker
    # that authenticates against fas-prod-api is FANFIC_CANARY_SERVICE_TOKEN,
    # and it is DELIBERATELY excluded from the general Novel/Chapter write
    # path by server design (`server/main.py::canary_ops_profile`'s own
    # docstring: letting the service token into the general write path would
    # turn a narrow identity into a full user account) -- there is no way to
    # self-mint this from anything else stored locally. Read by
    # `scripts/mission_g_rezero_draft_runner.py` via
    # `os.environ[TOKEN_ENV_VAR]`, so store it and then export it into that
    # process's env before running the runner.
    "FAS_HARVESTER_TOKEN",
)

#: Render env vars this module is permitted to read the VALUE of.
#:
#: An allowlist, not a blocklist, and checked before the request is built.
#: `render_env_names` returns keys only precisely so that a bug here cannot
#: turn the broker into a secret exfiltrator; this function is the one
#: deliberate exception, so it is bounded by name rather than by caller
#: discipline. Every entry is non-secret deployment coordinates that the
#: operator can already read in the Render dashboard. `APPWRITE_API_KEY` is
#: absent ON PURPOSE and must never be added.
RENDER_NON_SECRET_ENV = frozenset({
    "APPWRITE_ENDPOINT",
    "APPWRITE_PROJECT_ID",
    "APPWRITE_DATABASE_ID",
})


class BrokerEnvironmentError(RuntimeError):
    """Credential store or platform problem — maps to the documented exit 2.

    Previously these paths raised SystemExit with a message, which Python turns
    into exit code 1 — the code this tool documents as "not found". A caller
    branching on the exit code would have read an environment failure as a
    missing credential.
    """


if _WINDOWS:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD),
                    ("dwHighDateTime", wintypes.DWORD)]

    class CREDENTIAL_ATTRIBUTE(ctypes.Structure):
        _fields_ = [("Keyword", wintypes.LPWSTR),
                    ("Flags", wintypes.DWORD),
                    ("ValueSize", wintypes.DWORD),
                    ("Value", ctypes.POINTER(ctypes.c_byte))]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD),
                    ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR),
                    ("LastWritten", FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                    ("Persist", wintypes.DWORD),
                    ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTE)),
                    ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]


def _advapi32():
    if sys.platform != "win32":
        raise BrokerEnvironmentError("this broker requires Windows Credential Manager")
    lib = ctypes.WinDLL("advapi32", use_last_error=True)
    lib.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
    lib.CredWriteW.restype = wintypes.BOOL
    lib.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    lib.CredReadW.restype = wintypes.BOOL
    lib.CredFree.argtypes = [ctypes.c_void_p]
    lib.CredFree.restype = None
    return lib


def _target(name: str) -> str:
    return TARGET_PREFIX + name


def store(name: str, secret: str) -> None:
    """Write a value into the OS credential store. Value arrives via stdin."""
    lib = _advapi32()
    blob = secret.encode("utf-16-le")
    buf = ctypes.create_string_buffer(blob, len(blob))
    cred = CREDENTIAL()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = _target(name)
    cred.Comment = "Fanfic World production credential (managed by broker)"
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = "fanfic-broker"
    if not lib.CredWriteW(ctypes.byref(cred), 0):
        raise BrokerEnvironmentError(
            f"CredWrite failed (winerror {ctypes.get_last_error()})")


def fetch(name: str) -> Optional[str]:
    """Read a value back. Callers MUST NOT print the result."""
    lib = _advapi32()
    ptr = ctypes.POINTER(CREDENTIAL)()
    if not lib.CredReadW(_target(name), CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise BrokerEnvironmentError(
            f"CredRead failed (winerror {ctypes.get_last_error()})")
    try:
        cred = ptr.contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        lib.CredFree(ptr)


def push_github(name: str, env: str, repo: Optional[str]) -> int:
    """Stream the stored value into `gh secret set` over a pipe.

    The value goes credential-store -> this process -> gh's stdin. It is never
    rendered, never written to disk, and never placed in argv: `--body-file -`
    is what keeps it off the command line.
    """
    secret = fetch(name)
    if secret is None:
        print(f"{name}: ABSENT from credential store", file=sys.stderr)
        return 1
    # `gh secret set` reads the value from STDIN when --body is omitted. There
    # is NO --body-file flag on this subcommand (verified against the gh
    # manual); an earlier draft used one and would have failed outright.
    # Omitting --body is also what keeps the value off the command line.
    argv = ["gh", "secret", "set", name, "--env", env]
    if repo:
        argv += ["--repo", repo]
    try:
        # Binary mode: text=True would apply newline translation on Windows and
        # could corrupt a value that legitimately contains \r or \n.
        proc = subprocess.run(argv, input=secret.encode("utf-8"),
                              capture_output=True, timeout=120)
    except FileNotFoundError:
        print("gh CLI not found on PATH", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("gh timed out", file=sys.stderr)
        return 3
    if proc.returncode != 0:
        # Deliberately NOT echoing gh's stderr. If gh -- or anything shadowing
        # it on PATH -- ever echoed its stdin, forwarding that output would
        # print the secret. A return code is enough to diagnose.
        print(f"{name}: gh failed with exit code {proc.returncode} "
              f"(output suppressed to avoid echoing the value)", file=sys.stderr)
        return 3
    print(f"{name}: pushed to GitHub environment '{env}' (value not displayed)")
    return 0


# ---------------------------------------------------------------------------
# Render provider adapter.
#
# Uses Render's supported REST API rather than driving the dashboard. Browser
# automation would mean typing a secret into a form -- the exact thing this
# broker exists to avoid -- and it breaks whenever the DOM changes.
#
# Neither credential is ever rendered: RENDER_API_KEY goes into an
# Authorization header, FANFIC_CANARY_SERVICE_TOKEN into a JSON body, both
# built inside this process. Nothing reaches argv, stdout, a temp file or
# telemetry.
# ---------------------------------------------------------------------------
RENDER_API = "https://api.render.com/v1"
RENDER_SERVICE = "fas-prod-api"
CANARY_ENV_KEY = "FAS_CANARY_SERVICE_TOKEN"


class RenderError(RuntimeError):
    """Render API problem. Message is always value-free. Maps to exit 3."""


class RenderNotFound(RenderError):
    """Asked-for thing does not exist. Maps to the documented exit 1, not 3."""


def _render(api_key: str, method: str, path: str, payload=None, timeout: int = 60):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(RENDER_API + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        # The response BODY is deliberately discarded. A 400 from an API can
        # echo back the request it rejected -- which here would be the
        # Authorization header or the {"value": <secret>} body -- and this
        # message is printed to stderr. The status code is enough to act on.
        # Raised by independent security review.
        # Close WITHOUT reading. An unbounded read of a hostile or oversized
        # error body buys nothing here -- the body is discarded either way --
        # and closing alone releases the connection.
        try:
            exc.close()
        except Exception:
            pass
        raise RenderError(f"Render API {method} {path} -> HTTP {exc.code} "
                          f"(response body withheld: it can reflect the request)")
    except Exception as exc:
        raise RenderError(f"Render API {method} {path} failed: {type(exc).__name__}")


def render_identity(api_key: str) -> str:
    """Confirm the key authenticates before it is used for anything else.

    Fail-closed requirement: if identity cannot be established we do not go on
    to mutate configuration on a service we may not have understood.
    """
    _, data = _render(api_key, "GET", "/owners?limit=10")
    if not isinstance(data, list):
        # A malformed 2xx must surface as a downstream failure, not as an
        # AttributeError traceback with the wrong exit code.
        raise RenderError("owner lookup returned an unexpected shape — identity unverified")
    owners = [e.get("owner", {}) for e in data if isinstance(e, dict)]
    # Owner IDs only, never names or emails. If the wrong tenant's key were
    # ever stored, printing their name/email would disclose it before anyone
    # could react -- and the id is enough to tell tenants apart.
    ids = [o.get("id", "?") for o in owners if isinstance(o, dict)]
    if not ids:
        raise RenderError("Render API returned no owner — identity unverified")
    return ", ".join(ids)


def render_resolve_service(api_key: str, name: str = RENDER_SERVICE) -> dict:
    """Resolve a service by EXACT name. More than one match fails closed.

    An ambiguous name is refused rather than guessed: picking the wrong
    service would write a production credential into somebody else's config.
    """
    _, data = _render(api_key, "GET", f"/services?name={urllib.parse.quote(name)}&limit=20")
    if not isinstance(data, list):
        # NOT "not found": a malformed response is a downstream failure, and
        # reporting it as not-found would hide a possible ambiguous match.
        raise RenderError("service lookup returned an unexpected shape")
    services = [e.get("service", {}) for e in data if isinstance(e, dict)]
    # `?name=` is a FILTER on Render's side, not an exact match, so the
    # equality test below is what actually guarantees the right service.
    exact = [s for s in services if isinstance(s, dict) and s.get("name") == name]
    if not exact:
        raise RenderNotFound(f"no Render service named exactly {name!r}")
    if len(exact) > 1:
        ids = ", ".join(s.get("id", "?") for s in exact)
        raise RenderError(f"{len(exact)} services named {name!r} ({ids}) — refusing to guess")
    svc = exact[0]
    if not svc.get("id"):
        # A malformed success response must not surface as a KeyError
        # traceback and exit 1; it is a downstream failure.
        raise RenderError("Render returned a service without an id — cannot proceed safely")
    return svc


def render_env_names(api_key: str, service_id: str) -> list:
    """Every environment variable KEY. Values are never returned or logged.

    Paginated deliberately. A single ``limit=100`` request looks fine until a
    service exceeds one page: the before/after comparison would then be two
    PARTIAL snapshots, and a variable past the ceiling could be dropped
    without ever appearing in either set. That would leave the "nothing else
    was lost" check silently weaker than it reads. Raised by independent
    security review.
    """
    names: list = []
    cursor = None
    complete = False
    for _ in range(50):                       # hard stop; 5000 vars is absurd
        path = f"/services/{service_id}/env-vars?limit=100"
        if cursor:
            path += f"&cursor={urllib.parse.quote(cursor)}"
        _, data = _render(api_key, "GET", path)
        if not isinstance(data, list):
            # Treating a malformed 2xx as "empty and complete" would let the
            # write proceed against an unverifiable pre-write snapshot, which
            # is exactly what the before/after check exists to prevent.
            raise RenderError("env var listing returned an unexpected shape "
                              "— refusing to modify on an unverifiable snapshot")
        page = data
        for entry in page:
            ev = entry.get("envVar", entry) if isinstance(entry, dict) else {}
            key = ev.get("key") if isinstance(ev, dict) else None
            if key:
                names.append(key)
        if len(page) < 100:
            complete = True
            break
        cursor = (page[-1] or {}).get("cursor")
        if not cursor:
            # Full page but no cursor to continue: completeness is
            # unprovable, so refuse rather than compare partial snapshots.
            raise RenderError("env var list looks truncated and offers no cursor "
                              "— refusing to modify on an unverifiable snapshot")
    if not complete:
        # Falling out of the loop would silently return a PARTIAL snapshot and
        # make the later "nothing was lost" comparison meaningless.
        raise RenderError("env var list exceeded the pagination ceiling "
                          "— refusing to modify on an incomplete snapshot")
    # An empty list is a legitimate answer (a service with no env vars yet) and
    # is NOT treated as failure: a genuine read error already raised above.
    return sorted(names)


def render_non_secret_env(api_key: str, service_id: str) -> dict:
    """Read the VALUES of the non-secret deployment coordinates, and only those.

    Refuses to return anything outside `RENDER_NON_SECRET_ENV`. The filter is
    applied to the RESPONSE, so a Render-side rename or an injected extra
    variable cannot widen what comes back -- the allowlist decides, not the
    server.

    Raises `RenderError` on an unreadable listing rather than returning a
    partial map: a caller that silently got three of four coordinates would
    point schema tooling at the wrong project.
    """
    found: dict = {}
    cursor = None
    complete = False
    for _ in range(50):
        path = f"/services/{service_id}/env-vars?limit=100"
        if cursor:
            path += f"&cursor={urllib.parse.quote(cursor)}"
        _, data = _render(api_key, "GET", path)
        if not isinstance(data, list):
            raise RenderError("env var listing returned an unexpected shape")
        for entry in data:
            ev = entry.get("envVar", entry) if isinstance(entry, dict) else {}
            if not isinstance(ev, dict):
                continue
            key = ev.get("key")
            # The allowlist test happens HERE, on the way out. Anything not
            # named in it is dropped before it can reach a caller, a log, or
            # a traceback.
            if key in RENDER_NON_SECRET_ENV:
                found[key] = ev.get("value") or ""
        if len(data) < 100:
            complete = True
            break
        cursor = (data[-1] or {}).get("cursor")
        if not cursor:
            raise RenderError("env var list looks truncated and offers no cursor")
    if not complete:
        raise RenderError("env var list exceeded the pagination ceiling")
    return found


def appwrite_admin_env() -> dict:
    """Everything `scripts.setup_appwrite` needs, assembled in memory.

    Coordinates come from Render (non-secret, already configured); the schema
    key comes from the OS credential store. The returned mapping is meant to
    be pushed straight into `os.environ` of the migration process and NEVER
    printed, written to a file, or passed as an argument.

    Fails closed and names the missing piece, because a half-populated
    environment would make `setup_appwrite` talk to the wrong place or fail
    with an opaque 401.
    """
    render_key = fetch("RENDER_API_KEY")
    if not render_key:
        raise BrokerEnvironmentError(
            "RENDER_API_KEY chưa có trong Windows Credential Manager. "
            "Chạy: fanfic_credential_broker.py store --name RENDER_API_KEY")
    schema_key = fetch("APPWRITE_SCHEMA_API_KEY")
    if not schema_key:
        raise BrokerEnvironmentError(
            "APPWRITE_SCHEMA_API_KEY chưa có trong Windows Credential Manager. "
            "Tạo API key trong Appwrite Console với scopes: databases.read, "
            "collections.read, collections.write, attributes.read, "
            "attributes.write, indexes.read, indexes.write — rồi chạy: "
            "fanfic_credential_broker.py store --name APPWRITE_SCHEMA_API_KEY")

    service = render_resolve_service(render_key)
    coords = render_non_secret_env(render_key, service["id"])
    thieu = sorted(RENDER_NON_SECRET_ENV - set(coords))
    if thieu:
        raise RenderError(
            "Render thiếu toạ độ Appwrite không phải bí mật: " + ", ".join(thieu))

    env = dict(coords)
    env["APPWRITE_SCHEMA_API_KEY"] = schema_key
    return env


def render_upsert_env(api_key: str, service_id: str, key: str, value: str) -> None:
    """Add or update ONE variable, leaving every other one untouched.

    Single-key PUT on purpose. Render also offers a bulk PUT that REPLACES the
    whole set; using it would require sending every other secret back and
    would silently drop anything the read missed. If the single-key endpoint
    is unavailable we fail closed rather than fall back to the bulk form.
    """
    _render(api_key, "PUT", f"/services/{service_id}/env-vars/{urllib.parse.quote(key)}",
            {"value": value})


def render_latest_deploy(api_key: str, service_id: str) -> dict:
    _, data = _render(api_key, "GET", f"/services/{service_id}/deploys?limit=1")
    if not isinstance(data, list) or not data:
        return {}
    first = data[0]
    if not isinstance(first, dict):
        return {}
    deploy = first.get("deploy", {})
    return deploy if isinstance(deploy, dict) else {}


def cmd_render_status(args) -> int:
    api_key = fetch("RENDER_API_KEY")
    if api_key is None:
        print("RENDER_API_KEY: ABSENT from credential store — run `store --name RENDER_API_KEY`",
              file=sys.stderr)
        return 1
    try:
        who = render_identity(api_key)
        svc = render_resolve_service(api_key)
        names = render_env_names(api_key, svc["id"])
        deploy = render_latest_deploy(api_key, svc["id"])
    except RenderNotFound as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 1
    except RenderError as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 3
    print(f"  owner        {who}")
    print(f"  service      {svc.get('name')} ({svc.get('id')})")
    print(f"  env var count {len(names)}")
    print(f"  {CANARY_ENV_KEY}: {'PRESENT' if CANARY_ENV_KEY in names else 'ABSENT'}")
    print(f"  latest deploy status: {deploy.get('status', '?')} commit "
          f"{(deploy.get('commit') or {}).get('id', '?')[:12]}")
    return 0 if CANARY_ENV_KEY in names else 1


def cmd_sync_render_canary(args) -> int:
    """Push the canary service token into Render, without ever showing it."""
    api_key = fetch("RENDER_API_KEY")
    if api_key is None:
        print("RENDER_API_KEY: ABSENT from credential store — bootstrap it first",
              file=sys.stderr)
        return 1
    secret = fetch("FANFIC_CANARY_SERVICE_TOKEN")
    if secret is None:
        print("FANFIC_CANARY_SERVICE_TOKEN: ABSENT from credential store", file=sys.stderr)
        return 1

    try:
        who = render_identity(api_key)
        svc = render_resolve_service(api_key)
        before = render_env_names(api_key, svc["id"])
    except RenderNotFound as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 1
    except RenderError as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 3

    print(f"  owner        {who}")
    print(f"  service      {svc.get('name')} ({svc.get('id')})")
    print(f"  env vars now {len(before)}; {CANARY_ENV_KEY} "
          f"{'PRESENT' if CANARY_ENV_KEY in before else 'ABSENT'}")

    if args.dry_run:
        action = "update" if CANARY_ENV_KEY in before else "add"
        print(f"  DRY RUN — would {action} {CANARY_ENV_KEY} and leave "
              f"{len(before) - (1 if CANARY_ENV_KEY in before else 0)} other vars untouched")
        return 0

    try:
        render_upsert_env(api_key, svc["id"], CANARY_ENV_KEY, secret)
    except RenderError as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 3
    finally:
        # Drops the binding early. NOT a memory wipe: CPython may leave the
        # string in freed-but-not-zeroed heap. Defence in depth, not a
        # guarantee -- stated plainly so nobody reads more into it.
        del secret

    try:
        after = render_env_names(api_key, svc["id"])
    except RenderError as exc:
        print(f"render: wrote but could not verify: {exc}", file=sys.stderr)
        return 3

    # Verify by NAME only, and prove nothing else was lost.
    lost = sorted(set(before) - set(after))
    if lost:
        print(f"  ERROR: {len(lost)} pre-existing var(s) disappeared: {', '.join(lost)}",
              file=sys.stderr)
        return 3
    if CANARY_ENV_KEY not in after:
        print(f"  ERROR: {CANARY_ENV_KEY} still absent after write", file=sys.stderr)
        return 3
    print(f"  {CANARY_ENV_KEY}: PRESENT (value not displayed)")
    print(f"  preserved {len(after) - 1} other env vars; none lost")
    # MEASURED, not assumed (2026-08-30): `fas-prod-api` has autoDeploy=no, and
    # writing an env var through the API does NOT start a deploy. The service
    # sat on f4833d03 while main had moved four PRs ahead. The previous line
    # here claimed the opposite, which is the worst kind of wrong: an operator
    # who believes it polls `render-status`, sees "live", and concludes the new
    # value is in effect when the running process never restarted.
    print("  NOTE: this does NOT redeploy. The new value reaches the running")
    print("  service only after a deploy. Check `autoDeploy` on the service:")
    print("    autoDeploy=no  -> you must trigger a deploy explicitly")
    print("    autoDeploy=yes -> a push to the tracked branch deploys it")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_store = sub.add_parser("store", help="read a value from STDIN into the OS store")
    p_store.add_argument("--name", required=True, choices=KNOWN_NAMES)

    p_check = sub.add_parser("check", help="report presence only, never the value")
    p_check.add_argument("--name", required=True, choices=KNOWN_NAMES)

    sub.add_parser("list", help="list known credential names and presence")

    p_push = sub.add_parser("push-github", help="stream a stored value into gh secret set")
    p_push.add_argument("--name", required=True, choices=KNOWN_NAMES)
    p_push.add_argument("--env", default="production")
    p_push.add_argument("--repo", default=None)

    sub.add_parser("render-status", help="Render service + env var NAMES and deploy state")

    p_sync = sub.add_parser(
        "sync-render-canary",
        help="set FAS_CANARY_SERVICE_TOKEN on fas-prod-api via the Render API")
    p_sync.add_argument("--dry-run", action="store_true",
                        help="report what would change; touch nothing")

    a = ap.parse_args(argv)

    if a.cmd == "store":
        if sys.stdin.isatty():
            # getpass keeps terminal echo OFF, so a pasted value never appears
            # on screen or in a screen-scrape of the terminal.
            import getpass
            secret = getpass.getpass(f"Value for {a.name} (input hidden): ")
        else:
            secret = sys.stdin.read()
        # Strip ONLY the trailing newline a paste or pipe adds. A general
        # .strip() would silently mangle a value with meaningful leading or
        # trailing whitespace.
        secret = secret.rstrip("\r\n")
        if not secret:
            print("refusing to store an empty value", file=sys.stderr)
            return 2
        store(a.name, secret)
        print(f"{a.name}: stored in Windows Credential Manager (value not displayed)")
        return 0

    if a.cmd == "check":
        present = fetch(a.name) is not None
        print(f"{a.name}: {'PRESENT' if present else 'ABSENT'}")
        return 0 if present else 1

    if a.cmd == "list":
        missing = 0
        for name in KNOWN_NAMES:
            present = fetch(name) is not None
            if not present:
                missing += 1
            print(f"  {name:<32} {'PRESENT' if present else 'ABSENT'}")
        return 0 if missing == 0 else 1

    if a.cmd == "push-github":
        return push_github(a.name, a.env, a.repo)

    if a.cmd == "render-status":
        return cmd_render_status(a)

    if a.cmd == "sync-render-canary":
        return cmd_sync_render_canary(a)

    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokerEnvironmentError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
