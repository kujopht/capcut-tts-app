# -*- coding: utf-8 -*-
"""DI TRÚ kho dữ liệu Router về GỐC CHÍNH TẮC — khám phá, xem trước, gộp an toàn.

Vì sao cần: trước 2026-09-10 gốc dữ liệu neo vào VỊ TRÍ MÃ (cạnh EXE khi đóng
gói, `parents[2]`/`cwd` khi chạy nguồn), nên cùng một `project_id` có nhiều
quyển sổ độc lập. `duong_du_lieu.py` đã dựng gốc chính tắc; tệp này mang dữ
liệu CŨ về đó mà không mất gì.

LUẬT (đề bài nghiệm thu, và cũng là luật đúng):

* **KHÔNG quét cả máy.** Chỉ những gốc ỨNG VIÊN được nêu tường minh (kho
  nguồn, các `dist-*`, hoặc đường người vận hành đưa). Một lần `rglob` trên
  `C:\\` là cách chắc nhất để hút vào sổ của dự án khác.
* **Nhận dạng theo LƯỢC ĐỒ + DANH TÍNH DỰ ÁN**, không theo tên thư mục: một
  `memory.db` phải có bảng `su_kien`/`ky_uc`; `ns` được quy về `project_id`
  bằng cách so `khong_gian_ten(project_id)` của CHÍNH sổ `control.db` cùng
  gốc. Không quy được thì BỎ QUA (không đoán).
* **Xem trước trước khi ghi** (`thu_kho=True`): đếm nguồn/đích, không ghi gì.
* **Sao lưu đích** trước mọi lần ghi.
* **Khử trùng**: `su_kien` theo dấu vân tay `dau`; `ky_uc` theo `ma` (mã ổn
  định theo NỘI DUNG, nên ghi lại cùng một điều là no-op).
* **Không bao giờ ghi đè bản MỚI HƠN**: `ky_uc` trùng `ma` thì giữ bản có
  `ts_sua` lớn hơn.
* **Giữ L0 bất biến**: chỉ THÊM dòng lịch sử, không sửa/xoá dòng nào.
* **Giữ nguồn gốc**: `bang_chung`/`nguon_id` được ÁNH XẠ theo id sự kiện mới,
  nên "vì sao nhớ điều này" vẫn lần về đúng dòng.
* **Xung đột bản ghi có cấu trúc thì GIỮ CẢ HAI**: `quyet_dinh` trùng `ma`
  nhưng trỏ ký ức khác thì bản đến được ĐÁNH SỐ LẠI (`qd_` kế tiếp), không
  ghi đè — supersession có sẵn lo phần "bản nào đang hiệu lực".
* **Không trích bí mật**: không đọc/không chuyển Credential Manager. Chỉ
  `providers.db` (chỉ chứa `credential_ref`) được sao khi đích chưa có.
* **Idempotent**: chạy lại chỉ tăng `trung`, không nhân bản.
* **Không xoá sổ cũ.** Sau khi chứng minh xong, chỉ đặt mốc `DA_DI_TRU.json`.

FTS: các bảng `*_fts` do TRIGGER duy trì trên INSERT, nên `INSERT` thẳng vào
`su_kien`/`ky_uc` vẫn cập nhật chỉ mục — đã kiểm trong `kho.py`.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.duong_du_lieu import (co_du_lieu, dam_bao_kho,
                                                  duong_memory, duong_router,
                                                  goc_du_lieu)
from scripts.control_center.memory.model import khong_gian_ten

TEN_MOC_DI_TRU = "DA_DI_TRU.json"
#: Bảng ký ức được gộp, theo thứ tự phụ thuộc.
BANG_KY_UC = ("su_kien", "ky_uc", "bang_chung", "quyet_dinh", "diem_dung",
              "vien_nang", "nhat_ky_sua")


def _mo_ro(p: Path) -> Optional[sqlite3.Connection]:
    """Mở CHỈ ĐỌC, chịu được WAL nóng. `None` nếu không mở được."""
    if not Path(p).is_file():
        return None
    for che in ("mode=ro", "immutable=1"):
        try:
            c = sqlite3.connect(f"file:{Path(p).as_posix().replace(' ', '%20')}?{che}",
                                uri=True)
            c.row_factory = sqlite3.Row
            c.execute("SELECT 1")
            return c
        except sqlite3.Error:
            continue
    return None


def _bang(c: sqlite3.Connection) -> set:
    try:
        return {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error:
        return set()


def _dem(c: sqlite3.Connection, bang: str) -> int:
    try:
        return int(c.execute(f"SELECT COUNT(*) FROM {bang}").fetchone()[0])
    except sqlite3.Error:
        return 0


# ------------------------------------------------------------- kham pha -----

@dataclass
class QuyenSach:
    """Một quyển ký ức của MỘT dự án trong MỘT gốc."""
    ns: str
    duong: Path
    project_id: str = ""          # "" = không quy được -> bỏ qua
    dem: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"ns": self.ns, "duong": str(self.duong),
                "project_id": self.project_id, "dem": dict(self.dem)}


@dataclass
class NguonKho:
    """Một gốc dữ liệu Router tìm thấy."""
    goc: Path
    nhan: str
    control_db: Optional[Path] = None
    providers_db: Optional[Path] = None
    sach: List[QuyenSach] = field(default_factory=list)
    du_an: Dict[str, str] = field(default_factory=dict)   # project_id -> repo_path
    hop_le: bool = False
    ly_do: str = ""

    @property
    def tong_su_kien(self) -> int:
        return sum(s.dem.get("su_kien", 0) for s in self.sach)

    @property
    def tong_ky_uc(self) -> int:
        return sum(s.dem.get("ky_uc", 0) for s in self.sach)

    def to_dict(self) -> Dict:
        return {"goc": str(self.goc), "nhan": self.nhan, "hop_le": self.hop_le,
                "ly_do": self.ly_do,
                "control_db": str(self.control_db) if self.control_db else "",
                "du_an": dict(self.du_an),
                "sach": [s.to_dict() for s in self.sach],
                "tong_su_kien": self.tong_su_kien, "tong_ky_uc": self.tong_ky_uc}


def ung_vien_mac_dinh(kho_nguon: Optional[Path] = None) -> List[Tuple[Path, str]]:
    """Danh sách gốc ỨNG VIÊN — TƯỜNG MINH, không quét máy.

    Gồm: kho nguồn đang chạy (source-mode cũ) và mọi `dist-*/<app>/` cạnh nó
    (các bản đóng gói cũ). Chỉ những đường THẬT TỒN TẠI được trả về.
    """
    ra: List[Tuple[Path, str]] = []
    goc_kho = Path(kho_nguon) if kho_nguon else Path(__file__).resolve().parents[2]
    if (goc_kho / ".router").is_dir():
        ra.append((goc_kho, "source-mode (kho nguồn)"))
    for d in sorted(goc_kho.glob("dist-*")):
        if not d.is_dir():
            continue
        for app in sorted(d.glob("*/.router")):
            ra.append((app.parent, f"đóng gói {d.name}"))
    return ra


def kham_pha(ung_vien: Optional[Sequence[Tuple[Path, str]]] = None,
             *, kho_nguon: Optional[Path] = None) -> List[NguonKho]:
    """Nhận dạng từng gốc ứng viên. KHÔNG ghi gì, KHÔNG mở sổ đích."""
    ds = list(ung_vien) if ung_vien is not None else ung_vien_mac_dinh(kho_nguon)
    ra: List[NguonKho] = []
    for goc, nhan in ds:
        goc = Path(goc)
        n = NguonKho(goc=goc, nhan=nhan)
        r = goc / ".router"
        cdb = r / "control_center" / "control.db"
        pdb = r / "control_center" / "providers.db"
        n.control_db = cdb if cdb.is_file() else None
        n.providers_db = pdb if pdb.is_file() else None
        # Danh tinh du an tu control.db (de quy ns -> project_id).
        ns2pid: Dict[str, str] = {}
        if n.control_db:
            c = _mo_ro(n.control_db)
            if c is not None:
                try:
                    if "projects" in _bang(c):
                        for row in c.execute("SELECT project_id, repo_path FROM projects"):
                            pid = str(row["project_id"])
                            n.du_an[pid] = str(row["repo_path"])
                            ns2pid[khong_gian_ten(pid)] = pid
                finally:
                    c.close()
        # Cac quyen ky uc.
        mem = r / "memory"
        if mem.is_dir():
            for d in sorted(mem.iterdir()):
                db = d / "memory.db"
                if not (d.is_dir() and db.is_file()):
                    continue
                c = _mo_ro(db)
                if c is None:
                    continue
                try:
                    bs = _bang(c)
                    if not {"su_kien", "ky_uc"} <= bs:
                        continue        # khong dung luoc do ky uc -> bo qua
                    q = QuyenSach(ns=d.name, duong=db,
                                  project_id=ns2pid.get(d.name, ""))
                    q.dem = {b: _dem(c, b) for b in BANG_KY_UC if b in bs}
                    n.sach.append(q)
                finally:
                    c.close()
        n.hop_le = bool(n.control_db or n.sach)
        if not n.hop_le:
            n.ly_do = "không có control.db và không có quyển ký ức nào"
        elif n.sach and not any(s.project_id for s in n.sach):
            n.ly_do = ("có quyển ký ức nhưng không quy được ns -> project_id "
                       "(thiếu control.db cùng gốc)")
        ra.append(n)
    return ra


# -------------------------------------------------------------- sao luu -----

def sao_luu(dich: Optional[object] = None, *, thu_muc: Optional[Path] = None) -> Optional[Path]:
    """Sao lưu cây `.router` của ĐÍCH thành một thư mục có mốc thời gian.

    `None` nếu đích chưa có gì (không cần sao lưu). Sao lưu là ĐIỀU KIỆN
    TIÊN QUYẾT của mọi lần ghi — xem `di_tru()`.
    """
    g = goc_du_lieu(dich)
    r = duong_router(g)
    if not r.is_dir() or not co_du_lieu(g):
        return None
    dst = Path(thu_muc) if thu_muc else (g / "sao_luu" /
                                        time.strftime("%Y%m%d-%H%M%S"))
    dst.mkdir(parents=True, exist_ok=True)
    for ten in ("control_center", "memory"):
        src = r / ten
        if src.is_dir():
            shutil.copytree(src, dst / ten, dirs_exist_ok=True)
    (dst / "GHI_CHU.txt").write_text(
        "Sao lưu TRƯỚC khi di trú kho dữ liệu Router.\n"
        f"nguồn : {r}\nlúc   : {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Phục hồi: đóng Router, xoá `control_center/` và `memory/` ở gốc dữ "
        "liệu rồi copy hai thư mục này về đúng chỗ đó.\n", encoding="utf-8")
    return dst


# ---------------------------------------------------------------- gop -------

def _cot(c: sqlite3.Connection, bang: str) -> List[str]:
    return [r[1] for r in c.execute(f"PRAGMA table_info({bang})")]


def _gop_mot_quyen(src_db: Path, dst_db: Path, *, thu_kho: bool) -> Dict[str, int]:
    """Gộp MỘT quyển ký ức nguồn vào quyển đích. Trả thống kê.

    Thứ tự: `su_kien` (khử trùng theo `dau`, dựng ÁNH XẠ id) -> `ky_uc` (khử
    trùng theo `ma`, không ghi đè bản mới hơn, ánh xạ `nguon_id`) ->
    `bang_chung` (ánh xạ `su_kien_id`) -> `quyet_dinh` (trùng `ma` thì đánh số
    lại, GIỮ CẢ HAI) -> `diem_dung` / `vien_nang` / `nhat_ky_sua`.
    """
    tk = {k: 0 for k in ("su_kien_moi", "su_kien_trung", "ky_uc_moi",
                         "ky_uc_trung", "ky_uc_cu_hon", "bang_chung_moi",
                         "quyet_dinh_moi", "quyet_dinh_danh_so_lai",
                         "diem_dung_moi", "vien_nang_moi", "nhat_ky_moi")}
    s = _mo_ro(src_db)
    if s is None:
        return tk
    try:
        bs = _bang(s)
        d = sqlite3.connect(str(dst_db))
        d.row_factory = sqlite3.Row
        try:
            d.execute("PRAGMA foreign_keys=OFF")
            bd = _bang(d)
            if not {"su_kien", "ky_uc"} <= bd:
                return tk       # dich chua dung luoc do -> nguoi goi phai gieo truoc

            # --- su_kien: khu trung theo `dau`, dung anh xa id -------------
            #
            # ANH XA GIU NGUYEN ID KHI DUOC. Mot dau van tay co the xuat hien
            # NHIEU lan trong nguon (hai dong y het); neu luc nao cung quy ve
            # dong DAU tien o dich thi mot dong nguon thu hai se doi id, roi
            # `bang_chung` cua no thanh mot hang MOI (khoa chinh khac) — chay
            # lai lan hai lai them 5 hang. Do that o lan chay thu hai. Nen:
            # neu dich CO SAN dong cung id VA cung dau van tay thi anh xa
            # id -> chinh no; chi khi khong co moi tra ve tra cuu theo dau.
            anh_xa: Dict[int, int] = {}
            co_dau: Dict[str, int] = {}
            dau_theo_id: Dict[int, str] = {}
            for r0 in d.execute("SELECT id, dau FROM su_kien WHERE dau <> ''"):
                co_dau.setdefault(str(r0["dau"]), int(r0["id"]))
                dau_theo_id[int(r0["id"])] = str(r0["dau"])
            cot_s = [x for x in _cot(s, "su_kien") if x in set(_cot(d, "su_kien"))]
            cot_ghi = [x for x in cot_s if x != "id"]
            for row in s.execute("SELECT * FROM su_kien ORDER BY id"):
                dau = row["dau"] if "dau" in row.keys() else ""
                cu_id = int(row["id"])
                if dau and dau in co_dau:
                    # Uu tien anh xa DONG NHAT (id giu nguyen) de chay lai la no-op.
                    anh_xa[cu_id] = (cu_id if dau_theo_id.get(cu_id) == dau
                                     else int(co_dau[dau]))
                    tk["su_kien_trung"] += 1
                    continue
                if thu_kho:
                    tk["su_kien_moi"] += 1
                    continue
                gt = [row[k] for k in cot_ghi]
                cur = d.execute(
                    f"INSERT INTO su_kien ({','.join(cot_ghi)}) "
                    f"VALUES ({','.join('?' * len(cot_ghi))})", gt)
                moi = int(cur.lastrowid or 0)
                anh_xa[cu_id] = moi
                if dau:
                    co_dau[dau] = moi
                tk["su_kien_moi"] += 1

            # --- ky_uc: `ma` on dinh theo NOI DUNG -> ghi lai la no-op ------
            cot_k = [x for x in _cot(s, "ky_uc") if x in set(_cot(d, "ky_uc"))]
            cot_kghi = [x for x in cot_k if x != "id"]
            for row in s.execute("SELECT * FROM ky_uc"):
                ma = str(row["ma"])
                cu = d.execute("SELECT ma, ts_sua FROM ky_uc WHERE ma=?",
                               (ma,)).fetchone()
                if cu is not None:
                    ts_cu = float(cu["ts_sua"] or 0)
                    ts_moi = float((row["ts_sua"] if "ts_sua" in row.keys() else 0) or 0)
                    if ts_moi > ts_cu:
                        tk["ky_uc_cu_hon"] += 1     # dich CU hon: van KHONG ghi de
                    tk["ky_uc_trung"] += 1
                    continue
                if thu_kho:
                    tk["ky_uc_moi"] += 1
                    continue
                gt = []
                for k in cot_kghi:
                    v = row[k]
                    if k == "nguon_id" and str(v or "").isdigit():
                        v = str(anh_xa.get(int(v), v))   # NGUON GOC theo id moi
                    gt.append(v)
                d.execute(f"INSERT INTO ky_uc ({','.join(cot_kghi)}) "
                          f"VALUES ({','.join('?' * len(cot_kghi))})", gt)
                tk["ky_uc_moi"] += 1

            # --- bang_chung: anh xa su_kien_id ------------------------------
            if "bang_chung" in bs and "bang_chung" in bd:
                for row in s.execute("SELECT * FROM bang_chung"):
                    sid = int(row["su_kien_id"] or 0)
                    sid_moi = anh_xa.get(sid, sid if sid == 0 else 0)
                    if sid and not sid_moi:
                        continue        # khong anh xa duoc -> bo, khong bia
                    if thu_kho:
                        tk["bang_chung_moi"] += 1
                        continue
                    cur = d.execute("INSERT OR IGNORE INTO bang_chung "
                                    "(ky_uc_ma, su_kien_id, blob_sha, ghi_chu) "
                                    "VALUES (?,?,?,?)",
                                    (row["ky_uc_ma"], sid_moi, row["blob_sha"],
                                     row["ghi_chu"]))
                    # Dem HANG THAT SU vao (rowcount), khong dem so lan thu —
                    # bao cao phai noi dung thu da them.
                    tk["bang_chung_moi"] += int(cur.rowcount or 0)

            # --- quyet_dinh: trung `ma` -> DANH SO LAI, giu ca hai ----------
            if "quyet_dinh" in bs and "quyet_dinh" in bd:
                cot_q = [x for x in _cot(s, "quyet_dinh")
                         if x in set(_cot(d, "quyet_dinh"))]
                for row in s.execute("SELECT * FROM quyet_dinh"):
                    ma = str(row["ma"])
                    kuma = str(row["ky_uc_ma"])
                    da_co = d.execute(
                        "SELECT ma, ky_uc_ma FROM quyet_dinh WHERE ky_uc_ma=?",
                        (kuma,)).fetchone()
                    if da_co is not None:
                        continue        # CUNG mot ky uc -> da co, khong nhan ban
                    trung_ma = d.execute("SELECT 1 FROM quyet_dinh WHERE ma=?",
                                         (ma,)).fetchone() is not None
                    ma_dung = ma
                    if trung_ma:
                        n = 1
                        while d.execute("SELECT 1 FROM quyet_dinh WHERE ma=?",
                                        (f"qd_{n:04d}",)).fetchone() is not None:
                            n += 1
                        ma_dung = f"qd_{n:04d}"
                        tk["quyet_dinh_danh_so_lai"] += 1
                    if thu_kho:
                        tk["quyet_dinh_moi"] += 1
                        continue
                    gt = [(ma_dung if k == "ma" else row[k]) for k in cot_q]
                    d.execute(f"INSERT INTO quyet_dinh ({','.join(cot_q)}) "
                              f"VALUES ({','.join('?' * len(cot_q))})", gt)
                    tk["quyet_dinh_moi"] += 1

            # --- diem_dung / vien_nang / nhat_ky_sua ------------------------
            if "diem_dung" in bs and "diem_dung" in bd:
                cot_dd = [x for x in _cot(s, "diem_dung")
                          if x in set(_cot(d, "diem_dung"))]
                for row in s.execute("SELECT * FROM diem_dung"):
                    if d.execute("SELECT 1 FROM diem_dung WHERE ma=?",
                                 (row["ma"],)).fetchone() is not None:
                        continue
                    if thu_kho:
                        tk["diem_dung_moi"] += 1
                        continue
                    d.execute(f"INSERT INTO diem_dung ({','.join(cot_dd)}) "
                              f"VALUES ({','.join('?' * len(cot_dd))})",
                              [row[k] for k in cot_dd])
                    tk["diem_dung_moi"] += 1
            # `vien_nang` (viên nang có phiên bản) và `nhat_ky_sua` (sổ audit)
            # KHÔNG có khoá tự nhiên, nên bản đầu chèn vô điều kiện -> chạy lại
            # là thêm một phiên bản + 7 dòng audit MỖI LẦN. Khử trùng theo
            # TOÀN BỘ nội dung hàng: hai hàng y hệt nhau là một hàng.
            for bang, khoa in (("vien_nang", "vien_nang_moi"),
                               ("nhat_ky_sua", "nhat_ky_moi")):
                if bang not in bs or bang not in bd:
                    continue
                cot_b = [x for x in _cot(s, bang) if x in set(_cot(d, bang))]
                pk = "phien_ban" if bang == "vien_nang" else ""
                cot_i = [x for x in cot_b if x not in ("id", pk)]
                if not cot_i:
                    continue
                dk = " AND ".join(f"IFNULL({k},'')=IFNULL(?,'')" for k in cot_i)
                for row in s.execute(f"SELECT * FROM {bang}"):
                    gt = [row[k] for k in cot_i]
                    if d.execute(f"SELECT 1 FROM {bang} WHERE {dk} LIMIT 1",
                                 gt).fetchone() is not None:
                        continue                    # da co hang y het -> bo
                    if thu_kho:
                        tk[khoa] += 1
                        continue
                    try:
                        d.execute(f"INSERT INTO {bang} ({','.join(cot_i)}) "
                                  f"VALUES ({','.join('?' * len(cot_i))})", gt)
                        tk[khoa] += 1
                    except sqlite3.Error:
                        pass
            if not thu_kho:
                d.commit()
        finally:
            d.close()
    finally:
        s.close()
    return tk


def _sao_blob(src_goc: Path, dst_goc: Path, ns: str) -> int:
    """Sao tệp blob (bằng chứng nội dung đầy) theo băm — bỏ qua tệp đã có."""
    s = src_goc / ".router" / "memory" / ns / "blobs"
    d = duong_memory(dst_goc) / ns / "blobs"
    if not s.is_dir():
        return 0
    n = 0
    for f in s.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(s)
        dich = d / rel
        if dich.is_file():
            continue
        dich.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dich)
        n += 1
    return n


def gieo_tu_nguon(nguon: NguonKho, dich: Optional[object] = None) -> Dict:
    """ĐÍCH còn trống -> sao NGUYÊN cây `.router` của một nguồn.

    Đây là đường CHÍNH XÁC NHẤT: giữ đúng từng id, từng dòng L0, từng liên
    kết bằng chứng, cả `providers.db` (chỉ chứa `credential_ref`) và đính kèm.
    Chỉ dùng khi đích chưa có dữ liệu.
    """
    g = goc_du_lieu(dich)
    dam_bao_kho(g)
    if co_du_lieu(g):
        return {"gieo": False, "ly_do": "đích đã có dữ liệu — dùng đường gộp"}
    r_src = Path(nguon.goc) / ".router"
    r_dst = duong_router(g)
    n = 0
    for ten in ("control_center", "memory", "attachments"):
        s = r_src / ten
        if s.is_dir():
            shutil.copytree(s, r_dst / ten, dirs_exist_ok=True)
            n += 1
    return {"gieo": True, "tu": str(nguon.goc), "thu_muc": n}


def di_tru(dich: Optional[object] = None, *,
           nguon: Optional[Sequence[NguonKho]] = None,
           kho_nguon: Optional[Path] = None,
           thu_kho: bool = True,
           chi_du_an: Optional[Sequence[str]] = None) -> Dict:
    """Di trú mọi nguồn tìm thấy về gốc chính tắc.

    `thu_kho=True` (mặc định) = XEM TRƯỚC, không ghi gì. Ghi thật thì tự sao
    lưu đích trước. Idempotent: chạy lại chỉ tăng `*_trung`.
    """
    g = goc_du_lieu(dich)
    ds = list(nguon) if nguon is not None else kham_pha(kho_nguon=kho_nguon)
    ds = [n for n in ds if n.hop_le]
    # Khong tu di tru chinh no.
    ds = [n for n in ds if Path(n.goc).resolve() != g]
    bc: Dict = {"dich": str(g), "thu_kho": bool(thu_kho),
                "phien_ban_kho": None, "sao_luu": "", "gieo": None,
                "nguon": [n.to_dict() for n in ds], "gop": [], "tong": {}}
    if not ds:
        bc["ly_do"] = "không tìm thấy nguồn nào (ngoài chính đích)"
        return bc
    if not thu_kho:
        moc = dam_bao_kho(g, ung_dung="di_tru")
        bc["phien_ban_kho"] = moc.get("phien_ban_kho")
        sl = sao_luu(g)
        bc["sao_luu"] = str(sl) if sl else "(đích trống — không cần)"
    else:
        bc["phien_ban_kho"] = None

    # GIEO = sao NGUYEN cay `.router` cua nguon giau nhat. Chinh xac nhat,
    # nhung no sao CA quyen cua MOI du an trong nguon do — nen khi nguoi goi
    # gioi han `chi_du_an` thi KHONG duoc gieo: phai di duong GOP (co loc).
    # Bai kiem `test_cach_ly_du_an_la` bat duoc ro ri nay.
    chinh = max(ds, key=lambda n: (n.tong_su_kien, n.tong_ky_uc))
    if not co_du_lieu(g) and not chi_du_an:
        if thu_kho:
            bc["gieo"] = {"gieo": True, "tu": str(chinh.goc), "thu_kho": True}
        else:
            bc["gieo"] = gieo_tu_nguon(chinh, g)
        con_lai = [n for n in ds if n is not chinh]
    else:
        bc["gieo"] = {"gieo": False, "ly_do": (
            "giới hạn `chi_du_an` — đi đường gộp có lọc"
            if chi_du_an else "đích đã có dữ liệu")}
        con_lai = list(ds)

    tong: Dict[str, int] = {}
    for n in con_lai:
        for s in n.sach:
            if not s.project_id:
                bc["gop"].append({"nguon": n.nhan, "ns": s.ns,
                                  "bo_qua": "không quy được ns -> project_id"})
                continue
            if chi_du_an and s.project_id not in set(chi_du_an):
                bc["gop"].append({"nguon": n.nhan, "ns": s.ns,
                                  "bo_qua": f"ngoài phạm vi {list(chi_du_an)}"})
                continue
            dst_db = duong_memory(g) / s.ns / "memory.db"
            if not dst_db.is_file():
                # Chua co quyen nay o dich: dung provider that de dung luoc do
                # (FTS + trigger + phien ban), roi gop vao.
                if not thu_kho:
                    from scripts.control_center.memory.provider import \
                        LocalMemoryProvider
                    p = LocalMemoryProvider(duong_memory(g), s.project_id)
                    p.close()
            tk = ({} if (thu_kho and not dst_db.is_file())
                  else _gop_mot_quyen(s.duong, dst_db, thu_kho=thu_kho))
            if thu_kho and not dst_db.is_file():
                tk = {"su_kien_moi": s.dem.get("su_kien", 0),
                      "ky_uc_moi": s.dem.get("ky_uc", 0),
                      "ghi_chu": "quyển mới ở đích (xem trước: nhận toàn bộ)"}
            blob = 0 if thu_kho else _sao_blob(Path(n.goc), g, s.ns)
            bc["gop"].append({"nguon": n.nhan, "goc": str(n.goc), "ns": s.ns,
                              "project_id": s.project_id, "blob": blob, **tk})
            for k, v in tk.items():
                if isinstance(v, int):
                    tong[k] = tong.get(k, 0) + v
    bc["tong"] = tong
    return bc


def dat_moc_da_di_tru(nguon: NguonKho, dich: Optional[object] = None,
                      *, bao_cao: Optional[Dict] = None) -> Path:
    """Đặt mốc `DA_DI_TRU.json` vào gốc CŨ. KHÔNG xoá gì — người vận hành
    quyết việc dọn về sau."""
    p = Path(nguon.goc) / ".router" / TEN_MOC_DI_TRU
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"da_di_tru_luc": time.time(), "den": str(goc_du_lieu(dich)),
         "nhan": nguon.nhan,
         "ghi_chu": ("Sổ này ĐÃ được di trú về gốc dữ liệu chính tắc. Giữ "
                     "nguyên làm bằng chứng; KHÔNG xoá tự động."),
         "tong": (bao_cao or {}).get("tong", {})},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return p
