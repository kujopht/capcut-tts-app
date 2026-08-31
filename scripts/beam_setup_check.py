#!/usr/bin/env python3
"""Read-only Beam Cloud setup check — run BEFORE any deploy/benchmark.

Reads BEAM_TOKEN from this process's own environment (never printed/
logged). Confirms: beam CLI installed, auth resolves, and reports what
`beam machine list` shows for this account (real GPU availability, not
guessed). Deploys nothing, spends nothing.

    .venv\\Scripts\\python.exe scripts\\beam_setup_check.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

TOKEN_ENV_VAR = "BEAM_TOKEN"


def main() -> int:
    beam_bin = shutil.which("beam")
    print(f"beam CLI on PATH: {'yes at ' + beam_bin if beam_bin else 'NO'}")
    if not beam_bin:
        print("\nBLOCKED: install the Beam CLI first (real, documented command):")
        print("  uv tool install beam-client")
        print("(Windows: install inside WSL Ubuntu 22.04 per docs.beam.cloud)")
        return 2

    token = os.environ.get(TOKEN_ENV_VAR)
    print(f"{TOKEN_ENV_VAR} in process env: {'present' if token else 'ABSENT'}")
    if not token:
        print(f"\nBLOCKED: {TOKEN_ENV_VAR} is not set in this process's environment.")
        print("Get one from the Beam dashboard (beam.cloud) after creating an "
              "account, then either:")
        print(f'  $env:{TOKEN_ENV_VAR} = "<your token>"   # this shell session only')
        print("  beam config create                      # persists to "
              "~/.beam/config.ini instead, if you prefer that over an env var")
        return 2

    # `beam machine list` is a real, read-only account inspection call - does
    # not deploy or reserve anything. Token is inherited via os.environ by the
    # subprocess automatically; never placed in argv/logged here.
    try:
        result = subprocess.run(
            ["beam", "machine", "list"], capture_output=True, text=True,
            timeout=60)
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
          "beam_apps/ via the benchmark scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
