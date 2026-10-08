"""
Entitlement quiz (D4) — server quyet dinh, client chi nhan allowance de hien thi.

  * Free (mac dinh cho MOI user da dang nhap): 5 quiz da publish, theme Neon Tactics.
  * Pro: CHI qua grant tong hop cuc bo (`GrantRecord`) gan voi user_id da resolve —
    50 quiz da publish, them Arcane Academy. Grant co created/expires/revoked +
    actor + ly do (audit). KHONG co route HTTP cap/thu hoi grant, KHONG anh xa
    vai tro (creator/admin/tier host) sang Pro, KHONG gan thanh toan.

Cap grant cho QA cuc bo:

    python -m server.quiz.entitlements grant --var-dir <dir> --user <id> \
        --actor <ten> --reason "<ly do>" [--expires 2026-12-31T00:00:00Z]
    python -m server.quiz.entitlements revoke --var-dir <dir> --user <id> \
        --grant <grant_id> --actor <ten> --reason "<ly do>"
"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple

from server.quiz.contracts import EntitlementSummary
from server.quiz.store import GrantRecord, QuizStore, StoreNotFound


@dataclass(frozen=True)
class Allowance:
    plan: str
    published_limit: int
    themes: Tuple[str, ...]


FREE = Allowance("free", 5, ("neon-tactics",))
PRO = Allowance("pro", 50, ("neon-tactics", "arcane-academy"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp must carry a UTC offset")
    return dt


def _active(grant: GrantRecord, now: datetime) -> bool:
    if grant.revoked_at is not None:
        return False
    if parse_iso(grant.created_at) > now:
        return False
    return grant.expires_at is None or parse_iso(grant.expires_at) > now


class EntitlementPolicy:
    def __init__(self, store: QuizStore, clock: Callable[[], datetime]):
        self._store = store
        self._clock = clock

    def resolve(self, user_id: str) -> Tuple[Allowance, Optional[str]]:
        now = self._clock()
        active = [g for g in self._store.list_grants(user_id) if g.plan == "pro" and _active(g, now)]
        if not active:
            return FREE, None
        if any(g.expires_at is None for g in active):
            return PRO, None
        return PRO, max(g.expires_at for g in active)

    def summary(self, user_id: str) -> EntitlementSummary:
        allowance, expires = self.resolve(user_id)
        return EntitlementSummary(
            plan=allowance.plan, published_limit=allowance.published_limit,
            published_used=self._store.count_published(user_id),
            themes=list(allowance.themes), pro_expires_at=expires)


def grant_pro(store: QuizStore, *, user_id: str, actor: str, reason: str,
              now: datetime, expires_at: Optional[datetime] = None,
              grant_id: Optional[str] = None) -> GrantRecord:
    if expires_at is not None and expires_at <= now:
        raise ValueError("expires_at must be after the grant time")
    return store.put_grant(GrantRecord(
        grant_id=grant_id or str(uuid.uuid4()), user_id=user_id, plan="pro",
        created_at=iso(now), created_by=actor, reason=reason,
        expires_at=iso(expires_at) if expires_at else None))


def revoke_grant(store: QuizStore, *, user_id: str, grant_id: str, actor: str,
                 reason: str, now: datetime) -> GrantRecord:
    grant = next((g for g in store.list_grants(user_id) if g.grant_id == grant_id), None)
    if grant is None:
        raise StoreNotFound(grant_id)
    if grant.revoked_at is not None:
        return grant
    return store.put_grant(grant.model_copy(update={
        "revoked_at": iso(now), "revoked_by": actor, "revoke_reason": reason}))


def _main(argv: Optional[list] = None) -> int:
    from server.quiz.local_store import LocalQuizStore

    ap = argparse.ArgumentParser(prog="python -m server.quiz.entitlements")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant")
    r = sub.add_parser("revoke")
    ls = sub.add_parser("list")
    for p in (g, r, ls):
        p.add_argument("--var-dir", required=True, type=Path)
        p.add_argument("--user", required=True)
    for p in (g, r):
        p.add_argument("--actor", required=True)
        p.add_argument("--reason", required=True)
    g.add_argument("--expires")
    r.add_argument("--grant", required=True)
    args = ap.parse_args(argv)

    store = LocalQuizStore.under_var_dir(args.var_dir)
    now = datetime.now(timezone.utc)
    if args.cmd == "grant":
        rec = grant_pro(store, user_id=args.user, actor=args.actor, reason=args.reason, now=now,
                        expires_at=parse_iso(args.expires) if args.expires else None)
    elif args.cmd == "revoke":
        rec = revoke_grant(store, user_id=args.user, grant_id=args.grant, actor=args.actor,
                           reason=args.reason, now=now)
    else:
        for rec in store.list_grants(args.user):
            print(rec.model_dump_json())
        return 0
    print(rec.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
