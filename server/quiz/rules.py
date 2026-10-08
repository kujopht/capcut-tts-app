"""
Luat Tactical Summon solo (mode v1 / scoring v1) — CHI chay o server.

  * boolean  : 1 lan tra loi.
  * single   : min(2, so_lua_chon - 1) lan; tra loi sai o lan 1 thi lua chon do
               bi loai (`eliminated_option_ids`) cho lan 2.
  * multiple : 2 lan, cham DUNG-TRON-TAP (exact set), khong loai lua chon.
  * 1 diem cho moi cau tra loi dung (lan nao cung vay), 0 diem neu sai/het
    gio, KHONG thuong toc do.
"""

from __future__ import annotations

from typing import Iterable

GRACE_MS = 1_500
"""Do tre mang cho phep sau `time_limit_ms` truoc khi server coi la tre."""

CORRECT_POINTS = 1


def attempt_limit(kind: str, option_count: int) -> int:
    if kind == "boolean":
        if option_count != 2:
            raise ValueError("boolean requires exactly 2 options")
        return 1
    if not 2 <= option_count <= 8:
        raise ValueError("option count out of range")
    if kind == "single":
        return min(2, option_count - 1)
    if kind == "multiple":
        return 2
    raise ValueError(f"unknown kind {kind!r}")


def is_correct(selected: Iterable[str], correct: Iterable[str]) -> bool:
    return set(selected) == set(correct)


def selection_shape_ok(kind: str, selected_count: int) -> bool:
    """single/boolean chon dung 1; multiple chon >= 1."""
    return selected_count == 1 if kind in ("single", "boolean") else selected_count >= 1


def hit_cue(attempt: int) -> str:
    return "hit-first" if attempt == 1 else "hit-second"
