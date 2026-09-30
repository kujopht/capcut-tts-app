"""
Secret references for AI provider slots.

A slot stores only a NAME (`secret_ref`, e.g. "GEMINI_PROJECT_01"). The value
lives in the server environment as `FAS_AI_SECRET_GEMINI_PROJECT_01` (set on
the host, never in Appwrite, never in the client bundle, never in logs, never
in an admin API response).

What leaves this module:
  * `resolve()` -> the raw value, ONLY to the provider client that sends it
    upstream (called at request time, never cached in a config object);
  * `status()` -> presence + a masked fingerprint ("sha256:1a2b3c4d") so an
    admin can tell two keys apart or notice a rotation without seeing them.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from server.ai_assistant.control.model import SECRET_REF_RE

SECRET_ENV_PREFIX = "FAS_AI_SECRET_"


def env_name(secret_ref: str) -> str:
    if not SECRET_REF_RE.match(secret_ref or ""):
        raise ValueError("invalid secret_ref")
    return SECRET_ENV_PREFIX + secret_ref


@dataclass(frozen=True)
class SecretStatus:
    secret_ref: str
    env_name: str
    present: bool
    fingerprint: Optional[str]


class SecretResolver:
    """Reads `FAS_AI_SECRET_*` from an environment mapping (os.environ by
    default; tests inject a dict). Never logs, never raises with a value."""

    def __init__(self, environ: Optional[Mapping[str, str]] = None,
                 *, getenv: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._env = environ
        self._getenv = getenv

    def _read(self, name: str) -> Optional[str]:
        if self._getenv is not None:
            v = self._getenv(name)
        else:
            v = (self._env if self._env is not None else os.environ).get(name)
        v = (v or "").strip()
        return v or None

    def resolve(self, secret_ref: str) -> Optional[str]:
        try:
            return self._read(env_name(secret_ref))
        except ValueError:
            return None

    def status(self, secret_ref: str) -> SecretStatus:
        try:
            name = env_name(secret_ref)
        except ValueError:
            return SecretStatus(secret_ref, "", False, None)
        v = self._read(name)
        fp = ("sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()[:8]) if v else None
        return SecretStatus(secret_ref, name, bool(v), fp)
