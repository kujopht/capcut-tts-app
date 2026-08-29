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
import subprocess
import sys
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
    "CLOUDFLARE_API_TOKEN",
    # Renamed from FANFIC_ADMIN_CANARY_TOKEN. The rename was free: no secret
    # of either name had been created yet, so there was nothing to migrate and
    # every consumer moved in one commit. The name now says what it is -- a
    # service credential, not a human admin's session.
    "FANFIC_CANARY_SERVICE_TOKEN",
)


class BrokerEnvironmentError(RuntimeError):
    """Credential store or platform problem — maps to the documented exit 2.

    Previously these paths raised SystemExit with a message, which Python turns
    into exit code 1 — the code this tool documents as "not found". A caller
    branching on the exit code would have read an environment failure as a
    missing credential.
    """


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

    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokerEnvironmentError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
