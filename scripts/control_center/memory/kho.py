"""Sổ ký ức của MỘT dự án — SQLite, FTS5, chỉ thêm ở L0.

CÙNG KHUÔN với `control_center/store.py`, vì ba lỗi thật đã dạy khuôn đó:
WAL, một kết nối MỖI LUỒNG, `busy_timeout` 30s, `BEGIN IMMEDIATE` cho phép
đọc-rồi-ghi. Không mở kết nối riêng với pragma khác — Control Center mở
web + Qt + TUI cùng lúc trên cùng gốc, và một người ghi thứ hai với cấu
hình lệch là một `database is locked` lúc 2 giờ sáng.

BA QUYẾT ĐỊNH FTS, mỗi cái có số đo đứng sau (xem báo cáo V0.6):

  1. `tokenize="unicode61 remove_diacritics 2"` — BẮT BUỘC ghi rõ. Mặc
     định (rd=1) gấp `sát→sat` nhưng KHÔNG gấp `tệp`, `cấu`, `dự`: tra
     không dấu đúng một nửa, và test tiếng Anh không bao giờ lộ. Có bài
     kiểm khoá `MATCH 'tep'` → `tệp`.
  2. **External content** (`content='ky_uc'`): nạp nhanh 1.57×, truy vấn
     nhanh ~2×, cùng dung lượng, và giữ được lọc/sắp xếp bằng SQL thường.
  3. **Không vector, không trigram** ở V0.6. Trigram tốn 3.09× văn bản
     gốc; vector cần DLL ngoài. FTS5 thuần là đủ cho một sổ dự án, và
     `tim_kiem` để sẵn chỗ nối cho một provider ngữ nghĩa.

DỰ PHÒNG KHI FTS5 KHÔNG DỰNG ĐƯỢC: cột `chuan` (gấp dấu + `đ→d` + thường)
luôn được duy trì; `LIKE` trên nó vẫn tra không dấu. Chậm hơn, nhưng KHÔNG
BAO GIỜ "không tìm được vì thiếu FTS". Cờ `co_fts` nói thật đang đi đường
nào.

PHIÊN BẢN LƯỢC ĐỒ: `PRAGMA user_version`. `store.py` chưa có — mọi đổi
lược đồ ở đó là thêm bảng `IF NOT EXISTS`. Ở đây phải có từ đầu: một sổ
ký ức sống nhiều năm, và "đổi lược đồ FTS = DROP + rebuild" là chuyện sẽ
xảy ra.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.control_center.memory.bi_mat import loc, loc_dict
from scripts.control_center.memory.model import (BangChung, DiemDung, KyUc,
                                                 LoaiKyUc, QuyetDinh, SuKien,
                                                 TinCay, TrangThaiQuyetDinh,
                                                 VienNang, bam, chuan_hoa,
                                                 gap_dau)

PHIEN_BAN_LUOC_DO = 1

#: Tran INLINE cho `tom_tat` cua su kien: dai hon thi vao blob, so chi giu
#: phan dau. 2000 khop voi `cc_events.detail` cua store.py.
TRAN_TOM_TAT = 2000

LUOC_DO = """
CREATE TABLE IF NOT EXISTS su_kien (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    loai        TEXT NOT NULL,
    nguon       TEXT NOT NULL DEFAULT '',
    task_id     TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL DEFAULT '',
    tham_chieu  TEXT NOT NULL DEFAULT '',
    tom_tat     TEXT NOT NULL DEFAULT '',
    chuan       TEXT NOT NULL DEFAULT '',
    blob_sha    TEXT NOT NULL DEFAULT '',
    meta_json   TEXT NOT NULL DEFAULT '{}',
    dau         TEXT NOT NULL,
    da_loc      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sk_ts   ON su_kien(ts);
CREATE INDEX IF NOT EXISTS ix_sk_loai ON su_kien(loai, id DESC);
CREATE INDEX IF NOT EXISTS ix_sk_task ON su_kien(task_id);
CREATE INDEX IF NOT EXISTS ix_sk_dau  ON su_kien(dau);

CREATE TABLE IF NOT EXISTS ky_uc (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ma          TEXT NOT NULL UNIQUE,
    loai        TEXT NOT NULL,
    tieu_de     TEXT NOT NULL DEFAULT '',
    noi_dung    TEXT NOT NULL,
    chuan       TEXT NOT NULL,
    quan_trong  INTEGER NOT NULL DEFAULT 5,
    tin_cay     TEXT NOT NULL DEFAULT 'ghi_nhan',
    ts          REAL NOT NULL,
    ts_su_kien  REAL NOT NULL,
    ts_cham     REAL NOT NULL,
    han_tuoi    REAL NOT NULL DEFAULT 0,
    the_json    TEXT NOT NULL DEFAULT '[]',
    meta_json   TEXT NOT NULL DEFAULT '{}',
    da_loc      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ku_loai ON ky_uc(loai, ts_su_kien DESC);
CREATE INDEX IF NOT EXISTS ix_ku_ts   ON ky_uc(ts_su_kien DESC);

CREATE TABLE IF NOT EXISTS bang_chung (
    ky_uc_ma    TEXT NOT NULL,
    su_kien_id  INTEGER NOT NULL DEFAULT 0,
    blob_sha    TEXT NOT NULL DEFAULT '',
    ghi_chu     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (ky_uc_ma, su_kien_id, blob_sha)
);

CREATE TABLE IF NOT EXISTS quyet_dinh (
    ma           TEXT PRIMARY KEY,
    so           INTEGER NOT NULL,
    ky_uc_ma     TEXT NOT NULL,
    trang_thai   TEXT NOT NULL DEFAULT 'hieu_luc',
    thay_the_cho TEXT NOT NULL DEFAULT '',
    bi_thay_the  TEXT NOT NULL DEFAULT '',
    ly_do        TEXT NOT NULL DEFAULT '',
    ts           REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS nhat_ky_sua (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    bang      TEXT NOT NULL,
    ma        TEXT NOT NULL,
    hanh_dong TEXT NOT NULL,
    ai        TEXT NOT NULL DEFAULT '',
    ghi_chu   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS vien_nang (
    phien_ban       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL NOT NULL,
    noi_dung_json   TEXT NOT NULL,
    ly_do           TEXT NOT NULL DEFAULT '',
    bang_chung_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS diem_dung (
    ma              TEXT PRIMARY KEY,
    ts              REAL NOT NULL,
    ly_do           TEXT NOT NULL,
    session_id      TEXT NOT NULL DEFAULT '',
    task_id         TEXT NOT NULL DEFAULT '',
    noi_dung_json   TEXT NOT NULL,
    bang_chung_json TEXT NOT NULL DEFAULT '[]',
    tiep_tuc_tu     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_dd_ts ON diem_dung(ts DESC);
"""

#: FTS5 external content. Tokenizer GHI RÕ — xem docstring.
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS ky_uc_fts USING fts5(
    tieu_de, noi_dung, content='ky_uc', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2");
CREATE TRIGGER IF NOT EXISTS ky_uc_ai AFTER INSERT ON ky_uc BEGIN
  INSERT INTO ky_uc_fts(rowid, tieu_de, noi_dung)
  VALUES (new.id, new.tieu_de, new.noi_dung);
END;
CREATE TRIGGER IF NOT EXISTS ky_uc_ad AFTER DELETE ON ky_uc BEGIN
  INSERT INTO ky_uc_fts(ky_uc_fts, rowid, tieu_de, noi_dung)
  VALUES ('delete', old.id, old.tieu_de, old.noi_dung);
END;
CREATE TRIGGER IF NOT EXISTS ky_uc_au AFTER UPDATE ON ky_uc BEGIN
  INSERT INTO ky_uc_fts(ky_uc_fts, rowid, tieu_de, noi_dung)
  VALUES ('delete', old.id, old.tieu_de, old.noi_dung);
  INSERT INTO ky_uc_fts(rowid, tieu_de, noi_dung)
  VALUES (new.id, new.tieu_de, new.noi_dung);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS su_kien_fts USING fts5(
    tom_tat, content='su_kien', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2");
CREATE TRIGGER IF NOT EXISTS su_kien_ai AFTER INSERT ON su_kien BEGIN
  INSERT INTO su_kien_fts(rowid, tom_tat) VALUES (new.id, new.tom_tat);
END;
"""


def _js(x: Any) -> str:
    try:
        return json.dumps(x, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def _un(s: Optional[str], mac_dinh: Any) -> Any:
    if not s:
        return mac_dinh
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return mac_dinh


class KhoLoi(RuntimeError):
    pass


class KhoKyUc:
    """Sổ ký ức của MỘT dự án. An toàn nhiều luồng/tiến trình."""

    def __init__(self, duong: Path):
        self.path = Path(duong)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.co_fts = False
        self.ly_do_khong_fts = ""
        self._mo_luoc_do()

    # -- ket noi ------------------------------------------------------------

    def _c(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=30.0,
                                isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def giao_dich(self):
        c = self._c()
        if c.in_transaction:
            yield c
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")

    def _mo_luoc_do(self) -> None:
        c = self._c()
        c.executescript(LUOC_DO)
        try:
            c.executescript(FTS)
            self.co_fts = True
        except sqlite3.Error as exc:
            # KHONG nem: khong co FTS5 thi con duong `chuan` + LIKE.
            self.co_fts = False
            self.ly_do_khong_fts = f"{type(exc).__name__}: {exc}"[:200]
        pb = int(c.execute("PRAGMA user_version").fetchone()[0] or 0)
        if pb < PHIEN_BAN_LUOC_DO:
            # Cho moi ban di len: them cac buoc `if pb < N:` o day. V0.6 la
            # phien ban dau nen chi dong dau.
            c.execute(f"PRAGMA user_version={PHIEN_BAN_LUOC_DO}")

    @property
    def phien_ban_luoc_do(self) -> int:
        return int(self._c().execute("PRAGMA user_version").fetchone()[0] or 0)

    # -- L0: su kien (CHI THEM) ---------------------------------------------

    def ghi_su_kien(self, sk: SuKien) -> SuKien:
        """Thêm một dòng lịch sử. Không có đường sửa, không có đường xoá."""
        tom, n1 = loc(sk.tom_tat)
        meta, n2 = loc_dict(sk.meta)
        tom = tom[:TRAN_TOM_TAT]
        sk.tom_tat = tom
        sk.meta = meta
        sk.da_loc = int(sk.da_loc) + n1 + n2
        cur = self._c().execute(
            "INSERT INTO su_kien (ts, loai, nguon, task_id, session_id, "
            "tham_chieu, tom_tat, chuan, blob_sha, meta_json, dau, da_loc) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sk.ts, sk.loai, sk.nguon, sk.task_id, sk.session_id,
             sk.tham_chieu, tom, gap_dau(tom), sk.blob_sha, _js(meta),
             sk.dau, sk.da_loc))
        sk.id = int(cur.lastrowid or 0)
        return sk

    def su_kien(self, *, loai: str = "", task_id: str = "",
                tu: float = 0.0, den: float = 0.0, limit: int = 200,
                sau_id: int = 0, truoc_id: int = 0) -> List[SuKien]:
        dk, ts = [], []
        if loai:
            dk.append("loai=?"); ts.append(loai)
        if task_id:
            dk.append("task_id=?"); ts.append(task_id)
        if tu:
            dk.append("ts>=?"); ts.append(tu)
        if den:
            dk.append("ts<=?"); ts.append(den)
        if sau_id:
            dk.append("id>?"); ts.append(sau_id)
        if truoc_id:
            dk.append("id<?"); ts.append(truoc_id)
        sql = "SELECT * FROM su_kien"
        if dk:
            sql += " WHERE " + " AND ".join(dk)
        sql += " ORDER BY id DESC LIMIT ?"
        ts.append(int(limit))
        return [self._sk(h) for h in self._c().execute(sql, ts)]

    def su_kien_theo_id(self, sid: int) -> Optional[SuKien]:
        h = self._c().execute("SELECT * FROM su_kien WHERE id=?",
                              (int(sid),)).fetchone()
        return self._sk(h) if h else None

    @staticmethod
    def _sk(h: sqlite3.Row) -> SuKien:
        return SuKien(loai=h["loai"], ts=h["ts"], tom_tat=h["tom_tat"],
                      nguon=h["nguon"], task_id=h["task_id"],
                      session_id=h["session_id"], tham_chieu=h["tham_chieu"],
                      blob_sha=h["blob_sha"], meta=_un(h["meta_json"], {}),
                      da_loc=int(h["da_loc"] or 0), id=int(h["id"]),
                      dau=h["dau"])

    def tim_su_kien(self, cau: str, *, limit: int = 50) -> List[SuKien]:
        """Tìm trong lịch sử thô. FTS5 nếu có, LIKE trên `chuan` nếu không."""
        q = _cau_fts(cau)
        c = self._c()
        if self.co_fts and q:
            try:
                hs = c.execute(
                    "SELECT s.* FROM su_kien_fts f JOIN su_kien s ON s.id=f.rowid "
                    "WHERE su_kien_fts MATCH ? ORDER BY bm25(su_kien_fts) LIMIT ?",
                    (q, int(limit))).fetchall()
                return [self._sk(h) for h in hs]
            except sqlite3.Error:
                pass
        like = f"%{gap_dau(cau)}%"
        hs = c.execute("SELECT * FROM su_kien WHERE chuan LIKE ? "
                       "ORDER BY id DESC LIMIT ?", (like, int(limit))).fetchall()
        return [self._sk(h) for h in hs]

    # -- L1: ky uc ------------------------------------------------------------

    def luu_ky_uc(self, k: KyUc, *, ai: str = "") -> KyUc:
        """Lưu (idempotent theo `ma`). Ghi nhật ký sửa nếu là cập nhật."""
        nd, n1 = loc(k.noi_dung)
        td, n2 = loc(k.tieu_de)
        meta, n3 = loc_dict(k.meta)
        k.noi_dung, k.tieu_de, k.meta = nd, td, meta
        k.da_loc = int(k.da_loc) + n1 + n2 + n3
        with self.giao_dich() as c:
            cu = c.execute("SELECT id FROM ky_uc WHERE ma=?", (k.ma,)).fetchone()
            if cu:
                c.execute(
                    "UPDATE ky_uc SET quan_trong=?, tin_cay=?, ts_cham=?, "
                    "han_tuoi=?, the_json=?, meta_json=?, da_loc=? WHERE ma=?",
                    (int(k.quan_trong), k.tin_cay.value, time.time(),
                     k.han_tuoi, _js(list(k.the)), _js(meta), k.da_loc, k.ma))
                k.id = int(cu["id"])
                c.execute("INSERT INTO nhat_ky_sua (ts, bang, ma, hanh_dong, ai, "
                          "ghi_chu) VALUES (?,?,?,?,?,?)",
                          (time.time(), "ky_uc", k.ma, "cap_nhat", ai,
                           "ghi lại cùng nội dung"))
            else:
                cur = c.execute(
                    "INSERT INTO ky_uc (ma, loai, tieu_de, noi_dung, chuan, "
                    "quan_trong, tin_cay, ts, ts_su_kien, ts_cham, han_tuoi, "
                    "the_json, meta_json, da_loc) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (k.ma, k.loai.value, td, nd, gap_dau(f"{td} {nd}"),
                     int(k.quan_trong), k.tin_cay.value, k.ts, k.ts_su_kien,
                     k.ts_cham, k.han_tuoi, _js(list(k.the)), _js(meta),
                     k.da_loc))
                k.id = int(cur.lastrowid or 0)
            for b in k.bang_chung:
                c.execute("INSERT OR IGNORE INTO bang_chung (ky_uc_ma, su_kien_id, "
                          "blob_sha, ghi_chu) VALUES (?,?,?,?)",
                          (k.ma, int(b.su_kien_id), b.blob_sha, b.ghi_chu[:300]))
        return k

    def ky_uc(self, ma: str) -> Optional[KyUc]:
        h = self._c().execute("SELECT * FROM ky_uc WHERE ma=?", (ma,)).fetchone()
        return self._ku(h) if h else None

    def cham(self, ma: str) -> None:
        """Đánh dấu vừa được dùng — 'chạm là tươi lại' cho độ mới."""
        self._c().execute("UPDATE ky_uc SET ts_cham=? WHERE ma=?",
                          (time.time(), ma))

    def _ku(self, h: sqlite3.Row, *, kem_bang_chung: bool = True) -> KyUc:
        bc: Tuple[BangChung, ...] = ()
        if kem_bang_chung:
            bc = tuple(BangChung(su_kien_id=int(x["su_kien_id"]),
                                 blob_sha=x["blob_sha"], ghi_chu=x["ghi_chu"])
                       for x in self._c().execute(
                           "SELECT * FROM bang_chung WHERE ky_uc_ma=?",
                           (h["ma"],)))
        return KyUc(loai=LoaiKyUc(h["loai"]), noi_dung=h["noi_dung"],
                    tieu_de=h["tieu_de"], quan_trong=int(h["quan_trong"]),
                    tin_cay=TinCay(h["tin_cay"]), ts=h["ts"],
                    ts_su_kien=h["ts_su_kien"], ts_cham=h["ts_cham"],
                    han_tuoi=h["han_tuoi"], the=tuple(_un(h["the_json"], [])),
                    meta=_un(h["meta_json"], {}), bang_chung=bc,
                    da_loc=int(h["da_loc"] or 0), ma=h["ma"], id=int(h["id"]))

    def liet_ke_ky_uc(self, *, loai: Optional[LoaiKyUc] = None, limit: int = 100,
                      tu: float = 0.0, den: float = 0.0) -> List[KyUc]:
        dk, ts = [], []
        if loai is not None:
            dk.append("loai=?"); ts.append(loai.value)
        if tu:
            dk.append("ts_su_kien>=?"); ts.append(tu)
        if den:
            dk.append("ts_su_kien<=?"); ts.append(den)
        sql = "SELECT * FROM ky_uc"
        if dk:
            sql += " WHERE " + " AND ".join(dk)
        sql += " ORDER BY ts_su_kien DESC LIMIT ?"
        ts.append(int(limit))
        return [self._ku(h) for h in self._c().execute(sql, ts)]

    def tim_ky_uc(self, cau: str, *, loai: Optional[LoaiKyUc] = None,
                  limit: int = 50) -> List[Tuple[KyUc, float]]:
        """Ứng viên `(ký ức, hạng)` — hạng nhỏ hơn = liên quan hơn.

        FTS5: `bm25()` (âm; càng âm càng tốt). LIKE dự phòng: hạng theo vị
        trí xuất hiện (sớm hơn = tốt hơn). Cả hai đều chỉ là ĐIỂM LIÊN
        QUAN thô; `goi_ngu_canh` mới cộng độ mới + độ quan trọng.
        """
        c = self._c()
        q = _cau_fts(cau)
        ra: List[Tuple[KyUc, float]] = []
        if self.co_fts and q:
            try:
                sql = ("SELECT k.*, bm25(ky_uc_fts) AS hang FROM ky_uc_fts f "
                       "JOIN ky_uc k ON k.id=f.rowid WHERE ky_uc_fts MATCH ?")
                ts: List[Any] = [q]
                if loai is not None:
                    sql += " AND k.loai=?"; ts.append(loai.value)
                sql += " ORDER BY hang LIMIT ?"; ts.append(int(limit))
                for h in c.execute(sql, ts):
                    ra.append((self._ku(h), float(h["hang"])))
                return ra
            except sqlite3.Error:
                ra = []
        folded = gap_dau(cau)
        tu_khoa = [t for t in folded.split() if len(t) >= 2][:8]
        if not tu_khoa:
            return []
        dk = " OR ".join("chuan LIKE ?" for _ in tu_khoa)
        ts2: List[Any] = [f"%{t}%" for t in tu_khoa]
        sql = f"SELECT * FROM ky_uc WHERE ({dk})"
        if loai is not None:
            sql += " AND loai=?"; ts2.append(loai.value)
        sql += " ORDER BY ts_su_kien DESC LIMIT ?"; ts2.append(int(limit) * 2)
        for h in c.execute(sql, ts2):
            k = self._ku(h)
            # Nhieu tu khop hon = hang tot hon (am hon).
            so = sum(1 for t in tu_khoa if t in h["chuan"])
            ra.append((k, -float(so)))
        ra.sort(key=lambda x: x[1])
        return ra[:limit]

    # -- quyet dinh -----------------------------------------------------------

    def them_quyet_dinh(self, k: KyUc, *, thay_the_cho: Sequence[str] = (),
                        ly_do: str = "", ai: str = "") -> QuyetDinh:
        """Ghi một quyết định MỚI; nối 'thay thế' HAI CHIỀU trong một giao dịch."""
        k.loai = LoaiKyUc.DECISION
        with self.giao_dich() as c:
            self.luu_ky_uc(k, ai=ai)
            so = int(c.execute("SELECT COALESCE(MAX(so),0)+1 FROM quyet_dinh")
                     .fetchone()[0])
            ma = f"qd_{so:04d}"
            ly, _ = loc(ly_do)
            c.execute("INSERT INTO quyet_dinh (ma, so, ky_uc_ma, trang_thai, "
                      "thay_the_cho, bi_thay_the, ly_do, ts) VALUES "
                      "(?,?,?,?,?,?,?,?)",
                      (ma, so, k.ma, TrangThaiQuyetDinh.HIEU_LUC.value,
                       ",".join(thay_the_cho), "", ly[:1000], time.time()))
            for cu in thay_the_cho:
                c.execute("UPDATE quyet_dinh SET trang_thai=?, bi_thay_the=? "
                          "WHERE ma=? AND bi_thay_the=''",
                          (TrangThaiQuyetDinh.THAY_THE.value, ma, cu))
                c.execute("INSERT INTO nhat_ky_sua (ts, bang, ma, hanh_dong, ai, "
                          "ghi_chu) VALUES (?,?,?,?,?,?)",
                          (time.time(), "quyet_dinh", cu, "thay_the", ai,
                           f"bị {ma} thay thế"))
        return self.quyet_dinh(ma)  # type: ignore[return-value]

    def quyet_dinh(self, ma: str) -> Optional[QuyetDinh]:
        h = self._c().execute("SELECT * FROM quyet_dinh WHERE ma=?",
                              (ma,)).fetchone()
        return self._qd(h) if h else None

    def cac_quyet_dinh(self, *, chi_hieu_luc: bool = False,
                       limit: int = 200) -> List[QuyetDinh]:
        sql = "SELECT * FROM quyet_dinh"
        if chi_hieu_luc:
            sql += " WHERE trang_thai='hieu_luc' AND bi_thay_the=''"
        sql += " ORDER BY so DESC LIMIT ?"
        return [self._qd(h) for h in self._c().execute(sql, (int(limit),))]

    @staticmethod
    def _qd(h: sqlite3.Row) -> QuyetDinh:
        return QuyetDinh(ma=h["ma"], so=int(h["so"]), ky_uc_ma=h["ky_uc_ma"],
                         ts=h["ts"], trang_thai=TrangThaiQuyetDinh(h["trang_thai"]),
                         thay_the_cho=tuple(x for x in (h["thay_the_cho"] or "")
                                            .split(",") if x),
                         bi_thay_the=h["bi_thay_the"], ly_do=h["ly_do"])

    # -- vien nang ------------------------------------------------------------

    def luu_vien_nang(self, vn: VienNang) -> VienNang:
        d, _ = loc_dict(vn.to_dict())
        with self.giao_dich() as c:
            cur = c.execute("INSERT INTO vien_nang (ts, noi_dung_json, ly_do, "
                            "bang_chung_json) VALUES (?,?,?,?)",
                            (time.time(), _js(d), vn.ly_do[:400],
                             _js(list(vn.bang_chung))))
            vn.phien_ban = int(cur.lastrowid or 0)
            vn.ts = time.time()
            c.execute("UPDATE vien_nang SET noi_dung_json=? WHERE phien_ban=?",
                      (_js({**d, "phien_ban": vn.phien_ban, "ts": vn.ts}),
                       vn.phien_ban))
        return vn

    def vien_nang(self, project_id: str = "",
                  phien_ban: int = 0) -> Optional[VienNang]:
        c = self._c()
        if phien_ban:
            h = c.execute("SELECT * FROM vien_nang WHERE phien_ban=?",
                          (int(phien_ban),)).fetchone()
        else:
            h = c.execute("SELECT * FROM vien_nang ORDER BY phien_ban DESC "
                          "LIMIT 1").fetchone()
        if not h:
            return None
        vn = VienNang.tu_dict(_un(h["noi_dung_json"], {}), project_id)
        vn.phien_ban = int(h["phien_ban"]); vn.ts = h["ts"]; vn.ly_do = h["ly_do"]
        return vn

    def cac_phien_ban_vien_nang(self, limit: int = 20) -> List[Dict]:
        return [{"phien_ban": int(h["phien_ban"]), "ts": h["ts"],
                 "ly_do": h["ly_do"]}
                for h in self._c().execute(
                    "SELECT phien_ban, ts, ly_do FROM vien_nang ORDER BY "
                    "phien_ban DESC LIMIT ?", (int(limit),))]

    # -- diem dung ------------------------------------------------------------

    def luu_diem_dung(self, dd: DiemDung) -> DiemDung:
        d, _ = loc_dict(dd.to_dict())
        self._c().execute(
            "INSERT OR REPLACE INTO diem_dung (ma, ts, ly_do, session_id, "
            "task_id, noi_dung_json, bang_chung_json, tiep_tuc_tu) VALUES "
            "(?,?,?,?,?,?,?,?)",
            (dd.ma, dd.ts, dd.ly_do[:200], dd.session_id, dd.task_id, _js(d),
             _js(list(dd.bang_chung)), dd.tiep_tuc_tu))
        return dd

    def diem_dung_moi_nhat(self) -> Optional[DiemDung]:
        h = self._c().execute("SELECT * FROM diem_dung ORDER BY ts DESC LIMIT 1"
                              ).fetchone()
        return DiemDung.tu_dict(_un(h["noi_dung_json"], {})) if h else None

    def diem_dung(self, ma: str) -> Optional[DiemDung]:
        h = self._c().execute("SELECT * FROM diem_dung WHERE ma=?",
                              (ma,)).fetchone()
        return DiemDung.tu_dict(_un(h["noi_dung_json"], {})) if h else None

    def cac_diem_dung(self, limit: int = 50) -> List[DiemDung]:
        return [DiemDung.tu_dict(_un(h["noi_dung_json"], {}))
                for h in self._c().execute(
                    "SELECT * FROM diem_dung ORDER BY ts DESC LIMIT ?",
                    (int(limit),))]

    # -- thong ke / toan ven --------------------------------------------------

    def so_su_kien(self) -> int:
        """Chỉ `count(*)` — cho đường nóng. `dem()` còn có một GROUP BY trên
        toàn bộ vân tay (~200 ms ở 200 k dòng), không thuộc về mỗi lượt chat."""
        return int(self._c().execute("SELECT count(*) FROM su_kien").fetchone()[0])

    def dem(self) -> Dict[str, int]:
        c = self._c()
        ra = {}
        for b in ("su_kien", "ky_uc", "bang_chung", "quyet_dinh",
                  "nhat_ky_sua", "vien_nang", "diem_dung"):
            ra[b] = int(c.execute(f"SELECT count(*) FROM {b}").fetchone()[0])
        for loai in LoaiKyUc:
            ra[f"ky_uc_{loai.value}"] = int(c.execute(
                "SELECT count(*) FROM ky_uc WHERE loai=?",
                (loai.value,)).fetchone()[0])
        ra["su_kien_trung_dau"] = int(c.execute(
            "SELECT COALESCE(SUM(n-1),0) FROM (SELECT count(*) AS n FROM su_kien "
            "GROUP BY dau HAVING n>1)").fetchone()[0])
        return ra

    def byte(self) -> Dict[str, int]:
        """Dung lượng ĐO ĐƯỢC. Không có DBSTAT ở bản SQLite này, nên chỉ
        mục FTS được đo bằng tổng `length(block)` của bảng bóng `_data` —
        một phép đo thật, không phải ước lượng."""
        c = self._c()
        ra: Dict[str, int] = {}
        try:
            ra["tep_db"] = self.path.stat().st_size
            wal = self.path.with_name(self.path.name + "-wal")
            ra["tep_wal"] = wal.stat().st_size if wal.is_file() else 0
        except OSError:
            ra["tep_db"] = 0; ra["tep_wal"] = 0
        ra["tho_su_kien"] = int(c.execute(
            "SELECT COALESCE(SUM(length(tom_tat)+length(meta_json)),0) FROM su_kien"
        ).fetchone()[0])
        ra["co_cau_truc"] = int(c.execute(
            "SELECT COALESCE(SUM(length(noi_dung)+length(tieu_de)+length(meta_json)),0)"
            " FROM ky_uc").fetchone()[0])
        ra["co_cau_truc"] += int(c.execute(
            "SELECT COALESCE(SUM(length(noi_dung_json)),0) FROM vien_nang").fetchone()[0])
        ra["co_cau_truc"] += int(c.execute(
            "SELECT COALESCE(SUM(length(noi_dung_json)),0) FROM diem_dung").fetchone()[0])
        chi_muc = 0
        if self.co_fts:
            for bang in ("ky_uc_fts_data", "su_kien_fts_data"):
                try:
                    chi_muc += int(c.execute(
                        f"SELECT COALESCE(SUM(length(block)),0) FROM {bang}"
                    ).fetchone()[0])
                except sqlite3.Error:
                    pass
        ra["chi_muc_fts"] = chi_muc
        return ra

    def kiem_toan_ven(self) -> Dict[str, Any]:
        c = self._c()
        kq = str(c.execute("PRAGMA quick_check").fetchone()[0])
        fts_ok = True
        if self.co_fts:
            try:
                c.execute("INSERT INTO ky_uc_fts(ky_uc_fts) VALUES('integrity-check')")
            except sqlite3.Error:
                fts_ok = False
        return {"quick_check": kq, "fts": fts_ok, "co_fts": self.co_fts,
                "phien_ban_luoc_do": self.phien_ban_luoc_do}

    def toi_uu(self) -> None:
        """Sau một đợt nạp lớn. Không bắt buộc, không thay đổi dữ liệu."""
        if self.co_fts:
            c = self._c()
            for f in ("ky_uc_fts", "su_kien_fts"):
                try:
                    c.execute(f"INSERT INTO {f}({f}) VALUES('optimize')")
                except sqlite3.Error:
                    pass


# ------------------------------------------------------------- cau FTS ----

import re as _re

_TU = _re.compile(r"\w+", _re.UNICODE)

#: Tu dung tieng Viet + Anh (dang GAP DAU, vi so voi `gap_dau(tu)`). Mot
#: cau hoi "vi sao ta giu kho o che do chi doc" ma khong loc thi "ta",
#: "o", "che", "do" keo ve ca so ky uc — nhieu ung vien, bm25 phai lam viec
#: thay cho mot phep loc re tien.
TU_DUNG = frozenset((
    "co", "la", "cua", "va", "de", "thi", "khong", "mot", "cac", "nhung",
    "duoc", "nay", "do", "cho", "voi", "trong", "ra", "vao", "ta", "toi",
    "anh", "chi", "nhe", "ko", "hay", "hoac", "khi", "neu", "ma", "roi",
    "lai", "da", "dang", "se", "van", "con", "the", "nao", "gi", "sao",
    "vi", "o", "tu", "den", "len", "xuong", "ve", "nhu", "bi", "boi", "cung",
    "rat", "qua", "hon", "nhat", "minh", "ban", "no", "ho", "ay", "kia",
    "and", "the", "or", "of", "to", "in", "is", "it", "we", "you", "a",
    "an", "on", "for", "why", "what", "how", "did", "do", "does", "was",
    "were", "be", "are", "this", "that", "with", "not", "at", "by", "as",
))


def _cau_fts(cau: str) -> str:
    """Câu người dùng -> biểu thức FTS5 AN TOÀN.

    Chỉ giữ từ (`\\w+`, có tiếng Việt), bỏ mọi toán tử/ngoặc/dấu nháy để
    người dùng không thể làm hỏng cú pháp hay chèn `NEAR(` vào truy vấn.
    Bỏ từ dừng. Từ ≥ 3 ký tự thêm `*` (tiền tố). Nối bằng OR: một câu hỏi
    dài vẫn ra ứng viên, còn xếp hạng thì `bm25` + `goi_ngu_canh` lo.
    """
    tat = [t for t in _TU.findall(chuan_hoa(cau).lower()) if len(t) >= 2]
    tu = [t for t in tat if gap_dau(t) not in TU_DUNG]
    if not tu:
        tu = tat                      # cau toan tu dung: giu de con ra gi do
    if not tu:
        return ""
    tu = tu[:12]
    return " OR ".join(f'"{t}"*' if len(t) >= 3 else f'"{t}"' for t in tu)
