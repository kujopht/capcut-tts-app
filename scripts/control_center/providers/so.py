"""SỔ PROVIDER — SQLite `providers.db`: provider / tài khoản / model.

Sổ này giữ `credential_ref`, alias, base_url, trạng thái thử kết nối, số
hỏng liên tiếp, cooldown — và KHÔNG BAO GIỜ giữ giá trị credential. Rào
nằm ở tầng ghi: mọi chuỗi đi vào sổ đi qua `_khong_bi_mat()`; một chuỗi
giống khoá API (`sk-…`, `AKID…`, `Bearer …`, `KEY=…`) làm `luu_*` NÉM
`LoiBiMatLotVao` thay vì ghi. Bài kiểm đọc THẲNG bytes của tệp `.db` để
khẳng định khoá giả không có mặt.

Tách khỏi `control.db`: sổ Control Center đã có lược đồ V0.2..V0.6 của nó;
provider là một miền khác với vòng đời khác (người vận hành thêm/xoá), và
một tệp riêng làm việc sao lưu/xoá sạch rõ ràng hơn.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.memory.bi_mat import loc as _loc_bi_mat

PHIEN_BAN_LUOC_DO = 1

LUOC_DO = """
CREATE TABLE IF NOT EXISTS providers (
    provider_id TEXT PRIMARY KEY,
    ten         TEXT NOT NULL DEFAULT '',
    preset      TEXT NOT NULL,
    base_url    TEXT NOT NULL DEFAULT '',
    bat         INTEGER NOT NULL DEFAULT 1,
    ts          REAL NOT NULL,
    meta        TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS tai_khoan (
    account_id      TEXT PRIMARY KEY,
    provider_id     TEXT NOT NULL,
    alias           TEXT NOT NULL,
    credential_ref  TEXT NOT NULL,
    bat             INTEGER NOT NULL DEFAULT 1,
    cho_phep_auto   INTEGER NOT NULL DEFAULT 0,
    ts              REAL NOT NULL,
    trang_thai      TEXT NOT NULL DEFAULT 'chua_thu',
    lan_thu_ts      REAL NOT NULL DEFAULT 0,
    lan_thu_ok      INTEGER,
    lan_thu_chi_tiet TEXT NOT NULL DEFAULT '',
    hong_lien_tiep  INTEGER NOT NULL DEFAULT 0,
    cooldown_den    REAL NOT NULL DEFAULT 0,
    dang_dung       INTEGER NOT NULL DEFAULT 0,
    meta            TEXT NOT NULL DEFAULT '{}',
    UNIQUE (provider_id, alias)
);
CREATE TABLE IF NOT EXISTS models (
    provider_id TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    ten         TEXT NOT NULL DEFAULT '',
    nang_luc    TEXT NOT NULL DEFAULT '[]',
    bac         INTEGER NOT NULL DEFAULT 1,
    bat         INTEGER NOT NULL DEFAULT 1,
    nguon       TEXT NOT NULL DEFAULT 'preset',
    meta        TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (provider_id, model_id)
);
"""

_MA_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_MA_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$")
#: Hinh dang khoa API pho bien — bo sung cho bo loc chung (bo loc chung giu
#: TEN khoa va thay GIA TRI; o day ta chi can biet CO hay KHONG).
_HINH_KHOA = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}"           # OpenAI / DashScope / nhieu OpenAI-compat
    r"|\bAKID[A-Za-z0-9]{13,}"            # Tencent Cloud SecretId
    r"|\bAKIA[0-9A-Z]{16}"                # AWS
    r"|\bAIza[0-9A-Za-z_-]{30,}"          # Google
    r"|(?i:\bbearer\s+[A-Za-z0-9._~+/-]{20,})"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}")    # JWT


class LoiSoProvider(ValueError):
    pass


class LoiBiMatLotVao(LoiSoProvider):
    """Một chuỗi giống credential đang bị ghi vào sổ. TỪ CHỐI."""


def _khong_bi_mat(*van: Any, o_dau: str = "") -> None:
    for v in van:
        if v is None:
            continue
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        if _HINH_KHOA.search(s) or _loc_bi_mat(s)[1] > 0:
            raise LoiBiMatLotVao(
                f"từ chối ghi {o_dau or 'trường'} vào sổ provider: chuỗi giống "
                f"credential. Sổ chỉ giữ credential_ref; giá trị đi vào KhoBiMat.")


def _js(x: Any) -> str:
    try:
        return json.dumps(x, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _un(s: Optional[str], mac_dinh: Any) -> Any:
    if not s:
        return mac_dinh
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return mac_dinh


@dataclass
class Provider:
    provider_id: str
    preset: str
    ten: str = ""
    base_url: str = ""
    bat: bool = True
    ts: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"provider_id": self.provider_id, "preset": self.preset, "ten": self.ten,
                "base_url": self.base_url, "bat": self.bat, "ts": self.ts,
                "meta": dict(self.meta)}


@dataclass
class TaiKhoan:
    account_id: str
    provider_id: str
    alias: str
    credential_ref: str
    bat: bool = True
    cho_phep_auto: bool = False
    ts: float = 0.0
    trang_thai: str = "chua_thu"       # chua_thu | ok | hong | cooldown
    lan_thu_ts: float = 0.0
    lan_thu_ok: Optional[bool] = None
    lan_thu_chi_tiet: str = ""
    hong_lien_tiep: int = 0
    cooldown_den: float = 0.0
    dang_dung: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def dang_cooldown(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) < self.cooldown_den

    def to_dict(self) -> Dict:
        return {"account_id": self.account_id, "provider_id": self.provider_id,
                "alias": self.alias, "credential_ref": self.credential_ref,
                "bat": self.bat, "cho_phep_auto": self.cho_phep_auto, "ts": self.ts,
                "trang_thai": self.trang_thai, "lan_thu_ts": self.lan_thu_ts,
                "lan_thu_ok": self.lan_thu_ok, "lan_thu_chi_tiet": self.lan_thu_chi_tiet,
                "hong_lien_tiep": self.hong_lien_tiep,
                "cooldown_den": self.cooldown_den or None,
                "dang_dung": self.dang_dung, "meta": dict(self.meta)}


@dataclass
class ModelNgoai:
    provider_id: str
    model_id: str
    ten: str = ""
    nang_luc: Tuple[str, ...] = ()
    bac: int = 1
    bat: bool = True
    nguon: str = "preset"              # preset (khai bao) | probed (do that qua /models)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"provider_id": self.provider_id, "model_id": self.model_id, "ten": self.ten,
                "nang_luc": list(self.nang_luc), "bac": self.bac, "bat": self.bat,
                "nguon": self.nguon, "meta": dict(self.meta)}


def duong_so(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "control_center" / "providers.db"


class SoProvider:
    """Sổ bền. An toàn nhiều luồng (một khoá, một kết nối WAL)."""

    def __init__(self, path: Optional[Path] = None, *, root: Optional[Path] = None):
        self.path = Path(path) if path else duong_so(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._khoa = threading.RLock()
        self._c = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self._c.row_factory = sqlite3.Row
        with self._khoa:
            self._c.execute("PRAGMA journal_mode=WAL")
            self._c.executescript(LUOC_DO)
            self._c.execute(f"PRAGMA user_version={PHIEN_BAN_LUOC_DO}")
            self._c.commit()

    def close(self) -> None:
        with self._khoa:
            try:
                self._c.close()
            except sqlite3.Error:
                pass

    # -- provider -----------------------------------------------------------

    def luu_provider(self, p: Provider) -> Provider:
        if not _MA_PROVIDER.match(p.provider_id or ""):
            raise LoiSoProvider("provider_id: chữ thường/số/_/-, 2..32 ký tự, bắt đầu bằng chữ")
        _khong_bi_mat(p.ten, p.base_url, p.meta, o_dau="provider")
        p.ts = p.ts or time.time()
        with self._khoa:
            self._c.execute(
                "INSERT INTO providers (provider_id, ten, preset, base_url, bat, ts, meta) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider_id) DO UPDATE SET "
                "ten=excluded.ten, preset=excluded.preset, base_url=excluded.base_url, "
                "bat=excluded.bat, meta=excluded.meta",
                (p.provider_id, p.ten, p.preset, p.base_url, int(p.bat), p.ts, _js(p.meta)))
            self._c.commit()
        return p

    def provider(self, provider_id: str) -> Optional[Provider]:
        with self._khoa:
            r = self._c.execute("SELECT * FROM providers WHERE provider_id=?",
                                (provider_id,)).fetchone()
        return self._p(r) if r else None

    def providers(self) -> List[Provider]:
        with self._khoa:
            rs = self._c.execute("SELECT * FROM providers ORDER BY ts, provider_id").fetchall()
        return [self._p(r) for r in rs]

    def xoa_provider(self, provider_id: str) -> List[str]:
        """Xoá provider + model + tài khoản của nó. Trả các `credential_ref` để
        bên gọi xoá khỏi KhoBiMat (sổ không giữ giá trị nên không tự xoá được)."""
        with self._khoa:
            refs = [r["credential_ref"] for r in self._c.execute(
                "SELECT credential_ref FROM tai_khoan WHERE provider_id=?", (provider_id,))]
            self._c.execute("DELETE FROM tai_khoan WHERE provider_id=?", (provider_id,))
            self._c.execute("DELETE FROM models WHERE provider_id=?", (provider_id,))
            self._c.execute("DELETE FROM providers WHERE provider_id=?", (provider_id,))
            self._c.commit()
        return refs

    @staticmethod
    def _p(r) -> Provider:
        return Provider(provider_id=r["provider_id"], preset=r["preset"], ten=r["ten"],
                        base_url=r["base_url"], bat=bool(r["bat"]), ts=float(r["ts"]),
                        meta=_un(r["meta"], {}))

    # -- tai khoan -------------------------------------------------------------

    def luu_tai_khoan(self, t: TaiKhoan) -> TaiKhoan:
        if not _MA_ALIAS.match(t.alias or ""):
            raise LoiSoProvider("alias: chữ/số/khoảng trắng/._-, 1..40 ký tự")
        _khong_bi_mat(t.alias, t.credential_ref, t.lan_thu_chi_tiet, t.meta, o_dau="tài khoản")
        t.ts = t.ts or time.time()
        with self._khoa:
            self._c.execute(
                "INSERT INTO tai_khoan (account_id, provider_id, alias, credential_ref, bat, "
                "cho_phep_auto, ts, trang_thai, lan_thu_ts, lan_thu_ok, lan_thu_chi_tiet, "
                "hong_lien_tiep, cooldown_den, dang_dung, meta) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
                "alias=excluded.alias, bat=excluded.bat, cho_phep_auto=excluded.cho_phep_auto, "
                "trang_thai=excluded.trang_thai, lan_thu_ts=excluded.lan_thu_ts, "
                "lan_thu_ok=excluded.lan_thu_ok, lan_thu_chi_tiet=excluded.lan_thu_chi_tiet, "
                "hong_lien_tiep=excluded.hong_lien_tiep, cooldown_den=excluded.cooldown_den, "
                "dang_dung=excluded.dang_dung, meta=excluded.meta",
                (t.account_id, t.provider_id, t.alias, t.credential_ref, int(t.bat),
                 int(t.cho_phep_auto), t.ts, t.trang_thai, t.lan_thu_ts,
                 None if t.lan_thu_ok is None else int(t.lan_thu_ok), t.lan_thu_chi_tiet,
                 t.hong_lien_tiep, t.cooldown_den, t.dang_dung, _js(t.meta)))
            self._c.commit()
        return t

    def cap_nhat_tai_khoan(self, account_id: str, **truong) -> Optional[TaiKhoan]:
        t = self.tai_khoan(account_id)
        if t is None:
            return None
        for k, v in truong.items():
            if not hasattr(t, k):
                raise LoiSoProvider(f"trường không có: {k}")
            setattr(t, k, v)
        return self.luu_tai_khoan(t)

    def tai_khoan(self, account_id: str) -> Optional[TaiKhoan]:
        with self._khoa:
            r = self._c.execute("SELECT * FROM tai_khoan WHERE account_id=?",
                                (account_id,)).fetchone()
        return self._t(r) if r else None

    def tai_khoan_cua(self, provider_id: str) -> List[TaiKhoan]:
        with self._khoa:
            rs = self._c.execute("SELECT * FROM tai_khoan WHERE provider_id=? "
                                 "ORDER BY ts, alias", (provider_id,)).fetchall()
        return [self._t(r) for r in rs]

    def tai_khoan_tat_ca(self) -> List[TaiKhoan]:
        with self._khoa:
            rs = self._c.execute("SELECT * FROM tai_khoan ORDER BY provider_id, ts, alias"
                                 ).fetchall()
        return [self._t(r) for r in rs]

    def xoa_tai_khoan(self, account_id: str) -> Optional[str]:
        t = self.tai_khoan(account_id)
        if t is None:
            return None
        with self._khoa:
            self._c.execute("DELETE FROM tai_khoan WHERE account_id=?", (account_id,))
            self._c.commit()
        return t.credential_ref

    @staticmethod
    def _t(r) -> TaiKhoan:
        ok = r["lan_thu_ok"]
        return TaiKhoan(account_id=r["account_id"], provider_id=r["provider_id"],
                        alias=r["alias"], credential_ref=r["credential_ref"],
                        bat=bool(r["bat"]), cho_phep_auto=bool(r["cho_phep_auto"]),
                        ts=float(r["ts"]), trang_thai=r["trang_thai"],
                        lan_thu_ts=float(r["lan_thu_ts"]),
                        lan_thu_ok=None if ok is None else bool(ok),
                        lan_thu_chi_tiet=r["lan_thu_chi_tiet"],
                        hong_lien_tiep=int(r["hong_lien_tiep"]),
                        cooldown_den=float(r["cooldown_den"]), dang_dung=int(r["dang_dung"]),
                        meta=_un(r["meta"], {}))

    # -- model -----------------------------------------------------------------

    def luu_model(self, m: ModelNgoai) -> ModelNgoai:
        if not m.model_id or len(m.model_id) > 120:
            raise LoiSoProvider("model_id rỗng hoặc quá dài")
        _khong_bi_mat(m.model_id, m.ten, m.meta, o_dau="model")
        with self._khoa:
            self._c.execute(
                "INSERT INTO models (provider_id, model_id, ten, nang_luc, bac, bat, nguon, meta) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(provider_id, model_id) DO UPDATE SET "
                "ten=excluded.ten, nang_luc=excluded.nang_luc, bac=excluded.bac, "
                "bat=excluded.bat, nguon=excluded.nguon, meta=excluded.meta",
                (m.provider_id, m.model_id, m.ten, _js(list(m.nang_luc)), m.bac, int(m.bat),
                 m.nguon, _js(m.meta)))
            self._c.commit()
        return m

    def models_cua(self, provider_id: str, *, chi_bat: bool = False) -> List[ModelNgoai]:
        with self._khoa:
            rs = self._c.execute("SELECT * FROM models WHERE provider_id=? ORDER BY model_id",
                                 (provider_id,)).fetchall()
        ra = [ModelNgoai(provider_id=r["provider_id"], model_id=r["model_id"], ten=r["ten"],
                         nang_luc=tuple(_un(r["nang_luc"], [])), bac=int(r["bac"]),
                         bat=bool(r["bat"]), nguon=r["nguon"], meta=_un(r["meta"], {}))
              for r in rs]
        return [m for m in ra if m.bat] if chi_bat else ra

    def xoa_models(self, provider_id: str, *, nguon: Optional[str] = None) -> int:
        with self._khoa:
            if nguon:
                cur = self._c.execute("DELETE FROM models WHERE provider_id=? AND nguon=?",
                                      (provider_id, nguon))
            else:
                cur = self._c.execute("DELETE FROM models WHERE provider_id=?", (provider_id,))
            self._c.commit()
        return cur.rowcount

    # -- kiem toan -------------------------------------------------------------

    def moi_chuoi(self) -> List[str]:
        """Mọi chuỗi trong sổ — cho bài kiểm 'khoá giả không có mặt'."""
        ra: List[str] = []
        with self._khoa:
            for bang in ("providers", "tai_khoan", "models"):
                for r in self._c.execute(f"SELECT * FROM {bang}"):
                    ra.extend(str(v) for v in tuple(r) if isinstance(v, str))
        return ra
