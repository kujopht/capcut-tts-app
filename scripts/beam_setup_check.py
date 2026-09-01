#!/usr/bin/env python3
"""Read-only Beam Cloud setup check — run BEFORE any deploy/benchmark.

Resolves BEAM_TOKEN via `beam_credential.resolve_beam_token()` (never
printed/logged — see that module's docstring for the env-var-first,
Windows-Credential-Manager-fallback resolution order). Confirms: beam CLI
installed, auth resolves, and reports what `beam machine list` shows for
this account (real GPU availability, not guessed). Deploys nothing, spends
nothing.

    .venv\\Scripts\\python.exe scripts\\beam_setup_check.py

Mission "REMOVE THE HUMAN FROM BEAM OPERATIONS" (2026-09-01) findings baked
in here (see docs/reports/beam-unattended-operator-2026-09-01.md for full
citations):
  - `beam-client` is a REAL, clean native Windows pip install (confirmed —
    `pip install --dry-run beam-client` resolved with zero conflicts against
    this repo's existing venv). The previous "install inside WSL Ubuntu"
    guidance was an untested assumption, not a real requirement — no WSL2,
    no container, no Cloud Shell needed.
  - A bare `beam` CLI call on a fresh machine (empty `~/.beam/config.ini`)
    crashes with `UnicodeEncodeError` trying to print an emoji banner under
    Windows' default cp1252 console code page — reproduced directly, not
    assumed. Setting `CI=1` in the subprocess environment skips that
    interactive first-auth path entirely (the ONLY use of `os.getenv("CI")`
    in the installed beta9 0.1.265 source — grepped, not guessed), so every
    `beam` subprocess call in this repo's tooling sets it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from beam_credential import TOKEN_ENV_VAR, resolve_beam_token  # noqa: E402


def beam_subprocess_env(token: str) -> dict:
    """Env for a `beam` subprocess call: the real process env plus `CI=1`
    (skip the interactive/crashing first-auth banner) and the resolved
    token. Never mutates this process's own `os.environ` — a fresh dict
    only, passed via `subprocess.run(..., env=...)`."""
    import os
    env = dict(os.environ)
    env["CI"] = "1"
    env[TOKEN_ENV_VAR] = token
    return env


def _beam_executable():
    """Resolve `beam` - `beam-client` installs `beam.exe` into
    `.venv\\Scripts\\` alongside `python.exe`, but that directory is NOT
    automatically on PATH for a subprocess just because this interpreter's
    full path was used to launch this script (confirmed by reproducing:
    `shutil.which("beam")` returned None despite the file existing right
    next to `sys.executable`)."""
    found = shutil.which("beam")
    if found:
        return found
    candidate = Path(sys.executable).parent / (
        "beam.exe" if os.name == "nt" else "beam")
    return str(candidate) if candidate.is_file() else None


def main() -> int:
    beam_bin = _beam_executable()
    print(f"beam CLI on PATH: {'yes at ' + beam_bin if beam_bin else 'NO'}")
    if not beam_bin:
        print("\nBLOCKED: install the Beam CLI first (real, tested command):")
        print("  .venv\\Scripts\\python.exe -m pip install beam-client==0.2.207")
        print("(native Windows install, confirmed clean — no WSL2/container "
              "needed. Pin this version; see beam_operator.py's own version "
              "check for why pinning matters.)")
        return 2

    token = resolve_beam_token()
    print(f"{TOKEN_ENV_VAR} resolved: {'yes (value withheld)' if token else 'ABSENT'}")
    if not token:
        print(f"\nBLOCKED: {TOKEN_ENV_VAR} not found in this process's "
              "environment or the Windows Credential Manager broker.")
        print("ONE-TIME setup (value typed on stdin — never seen by Claude, "
              "never in argv/shell history):")
        print("  python scripts/fanfic_credential_broker.py store --name BEAM_TOKEN")
        print("Or, for this shell session only:")
        print(f'  $env:{TOKEN_ENV_VAR} = "<your token>"')
        return 2

    # `beam machine list` is a real, read-only account inspection call - does
    # not deploy or reserve anything. Token passed via subprocess env only;
    # never placed in argv/logged here.
    try:
        result = subprocess.run(
            [beam_bin, "machine", "list"], capture_output=True, text=True,
            timeout=60, env=beam_subprocess_env(token))
    except FileNotFoundError:
        print("\nBLOCKED: 'beam' binary not runnable despite being on PATH.")
        return 2
    print("\n=== beam machine list ===")
    print(result.stdout or "(empty)")
    if result.returncode != 0:
        print("stderr:", result.stderr[:1000], file=sys.stderr)
        print(f"\nbeam CLI exited {result.returncode} - check auth "
              f"(token may be invalid/expired).")
        return 1

    print("\nSetup looks real and usable. Next: deploy the two apps in "
          "beam_apps/ via the benchmark scripts, or use scripts/beam_operator.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
