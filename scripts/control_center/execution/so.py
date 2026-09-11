"""SỔ BỀN của vòng kín thực thi — V0.9, §2 và §11.

CÙNG TỆP `control.db`, CÙNG KẾT NỐI. Không mở sổ thứ năm: `execution*` là
bảng THÊM VÀO, và chúng đi qua `So.ket_noi()` + `So.giao_dich_ghi()` để dùng
chung WAL và phép tuần tự hoá người ghi. Một tệp SQLite riêng sẽ làm hai thứ
cần nguyên tử CÙNG NHAU (đổi trạng thái thực thi + đổi trạng thái việc) nằm
ở hai giao dịch không liên quan.

BA TÍNH CHẤT ĐƯỢC KHOÁ BẰNG BÀI KIỂM:

1. **Chuyển trạng thái được KIỂM trong giao dịch.** `doi_trang_thai` đọc
   trạng thái cũ và ghi trạng thái mới trong CÙNG một `BEGIN IMMEDIATE`. Đọc
   rồi ghi ngoài giao dịch là cách hai luồng cùng thấy `RUNNING` rồi cùng
   viết `DONE`.
2. **Bản kế hoạch cũ KHÔNG bị xoá** (§10). `luu_ke_hoach` chỉ hạ
   `dang_hieu_luc` của các bản trước; bản v1 ở lại vĩnh viễn.
3. **Không bí mật, không dòng suy nghĩ.** Mọi văn bản đi qua
   `y_dinh.khong_suy_nghi` (đã gồm `redact`) trước khi chạm đĩa.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.ke_hoach import KeHoachThucThi
from scripts.control_center.execution.ket_qua import (HopDongKetQua,
                                                      TrangThaiXacMinh)
from scripts.control_center.execution.tiep_noi import DeXuat
from scripts.control_center.execution.trang_thai import (TrangThaiThucThi,
                                                         kiem_chuyen)
from scripts.control_center.execution.y_dinh import (LopThamQuyen, MucRuiRo,
                                                     TrangThaiDuyet,
                                                     YDinhThucThi,
                                                     khong_suy_nghi)

#: Giữ bao nhiêu sự kiện thực thi. Cùng lý do `store.MAX_EVENTS`.
MAX_SU_KIEN = 20000


def _js(x: Any) -> str:
    try:
        return json.dumps(x, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(x), ensure_ascii=False)


def _un(s: Optional[str], mac_dinh: Any) -> Any:
    if not s:
        return mac_dinh
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return mac_dinh


class SoThucThi:
    """CRUD của vòng kín. Bọc `ControlStore`, không thay thế nó."""

    def __init__(self, store) -> None:
        self.store = store

    # ------------------------------------------------------------- su kien --

    def ghi_su_kien(self, execution_id: str, kind: str, *, project_id: str = "",
                    buoc_id: str = "", level: str = "INFO", detail: str = "",
                    meta: Optional[Dict] = None) -> int:
        """Vết kiểm toán của một lần thực thi. §13 đòi huỷ phải TRUY ĐƯỢC."""
        d = khong_suy_nghi(detail, toi_da=2000)
        m = json.loads(khong_suy_nghi(_js(meta or {}), toi_da=8000) or "{}") \
            if meta else {}
        with self.store.giao_dich_ghi() as c:
            cur = c.execute(
                "INSERT INTO execution_events(execution_id, project_id, kind, "
                "level, buoc_id, detail, meta_json, ts) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (execution_id, project_id, kind, level, buoc_id, d,
                 _js(m), time.time()))
            rid = int(cur.lastrowid or 0)
            c.execute(
                "DELETE FROM execution_events WHERE id <= "
                "(SELECT MAX(id) - ? FROM execution_events)", (MAX_SU_KIEN,))
        return rid

    def su_kien(self, execution_id: str = "", *, limit: int = 200) -> List[Dict]:
        q = "SELECT * FROM execution_events"
        a: List[Any] = []
        if execution_id:
            q += " WHERE execution_id = ?"
            a.append(execution_id)
        q += " ORDER BY id DESC LIMIT ?"
        a.append(int(limit))
        return [{"id": h["id"], "execution_id": h["execution_id"],
                 "project_id": h["project_id"], "kind": h["kind"],
                 "level": h["level"], "buoc_id": h["buoc_id"],
                 "detail": h["detail"], "meta": _un(h["meta_json"], {}),
                 "ts": h["ts"]}
                for h in self.store.ket_noi().execute(q, a).fetchall()]

    # -------------------------------------------------------------- y dinh --

    def luu(self, y: YDinhThucThi) -> YDinhThucThi:
        y.updated_at = time.time()
        with self.store.giao_dich_ghi() as c:
            c.execute(
                "INSERT INTO executions(execution_id, project_id, goal, state, "
                " pha, tham_quyen, duyet, duyet_boi, duyet_luc, rui_ro, "
                " tac_dong_prod, cong_gated_json, nguon_message, "
                " nguon_de_xuat, nguon_cau, pham_vi_json, rang_buoc_json, "
                " tieu_chi_json, ban_ke_hoach, so_lan_thu_lai, so_lan_lap_lai,"
                " ket_luan, ly_do_dung, created_at, updated_at, ended_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(execution_id) DO UPDATE SET "
                " goal=excluded.goal, state=excluded.state, pha=excluded.pha, "
                " tham_quyen=excluded.tham_quyen, duyet=excluded.duyet, "
                " duyet_boi=excluded.duyet_boi, duyet_luc=excluded.duyet_luc, "
                " rui_ro=excluded.rui_ro, "
                " tac_dong_prod=excluded.tac_dong_prod, "
                " cong_gated_json=excluded.cong_gated_json, "
                " pham_vi_json=excluded.pham_vi_json, "
                " rang_buoc_json=excluded.rang_buoc_json, "
                " tieu_chi_json=excluded.tieu_chi_json, "
                " ban_ke_hoach=excluded.ban_ke_hoach, "
                " so_lan_thu_lai=excluded.so_lan_thu_lai, "
                " so_lan_lap_lai=excluded.so_lan_lap_lai, "
                " ket_luan=excluded.ket_luan, ly_do_dung=excluded.ly_do_dung, "
                " updated_at=excluded.updated_at, ended_at=excluded.ended_at",
                (y.execution_id, y.project_id, y.goal, y.trang_thai.value,
                 y.pha, y.tham_quyen.value, y.duyet.value, y.duyet_boi,
                 y.duyet_luc, y.rui_ro.value, int(bool(y.tac_dong_production)),
                 _js([dict(x) for x in y.cong_gated]), int(y.nguon_message_id),
                 y.nguon_de_xuat, y.nguon_cau_nguoi_dung, _js(list(y.pham_vi)),
                 _js(list(y.rang_buoc)), _js(list(y.tieu_chi_dat)),
                 int(y.ban_ke_hoach), int(y.so_lan_thu_lai),
                 int(y.so_lan_lap_lai), y.ket_luan, y.ly_do_dung,
                 y.created_at, y.updated_at, y.ended_at))
        return y

    @staticmethod
    def _tu_hang(h) -> YDinhThucThi:
        return YDinhThucThi(
            execution_id=h["execution_id"], project_id=h["project_id"],
            goal=h["goal"] or "?",
            nguon_message_id=int(h["nguon_message"] or 0),
            nguon_de_xuat=h["nguon_de_xuat"] or "",
            nguon_cau_nguoi_dung=h["nguon_cau"] or "",
            pham_vi=tuple(_un(h["pham_vi_json"], [])),
            rang_buoc=tuple(_un(h["rang_buoc_json"], [])),
            tieu_chi_dat=tuple(_un(h["tieu_chi_json"], [])),
            tham_quyen=LopThamQuyen(h["tham_quyen"]),
            duyet=TrangThaiDuyet(h["duyet"]),
            duyet_boi=h["duyet_boi"] or "", duyet_luc=float(h["duyet_luc"] or 0),
            rui_ro=MucRuiRo(h["rui_ro"]),
            tac_dong_production=bool(h["tac_dong_prod"]),
            cong_gated=tuple(_un(h["cong_gated_json"], [])),
            trang_thai=TrangThaiThucThi(h["state"]), pha=h["pha"] or "",
            ban_ke_hoach=int(h["ban_ke_hoach"] or 0),
            so_lan_thu_lai=int(h["so_lan_thu_lai"] or 0),
            so_lan_lap_lai=int(h["so_lan_lap_lai"] or 0),
            ket_luan=h["ket_luan"] or "", ly_do_dung=h["ly_do_dung"] or "",
            created_at=float(h["created_at"] or 0),
            updated_at=float(h["updated_at"] or 0),
            ended_at=float(h["ended_at"] or 0))

    def y_dinh(self, execution_id: str) -> Optional[YDinhThucThi]:
        h = self.store.ket_noi().execute(
            "SELECT * FROM executions WHERE execution_id = ?",
            (execution_id,)).fetchone()
        return self._tu_hang(h) if h else None

    def danh_sach(self, project_id: str = "", *,
                  states: Sequence[TrangThaiThucThi] = (),
                  dang_song: Optional[bool] = None,
                  limit: int = 200) -> List[YDinhThucThi]:
        q = "SELECT * FROM executions WHERE 1=1"
        a: List[Any] = []
        if project_id:
            q += " AND project_id = ?"
            a.append(project_id)
        if states:
            q += " AND state IN (%s)" % ",".join("?" * len(states))
            a += [s.value for s in states]
        if dang_song is not None:
            kt = sorted(x.value for x in TrangThaiThucThi if x.ket_thuc)
            q += (" AND state NOT IN (%s)" if dang_song
                  else " AND state IN (%s)") % ",".join("?" * len(kt))
            a += kt
        q += " ORDER BY created_at DESC LIMIT ?"
        a.append(int(limit))
        return [self._tu_hang(h)
                for h in self.store.ket_noi().execute(q, a).fetchall()]

    def dang_chay(self, project_id: str = "") -> List[YDinhThucThi]:
        """Lần thực thi CÒN SỐNG. Đây là thứ §12 trả lời "xong chưa bro?"."""
        return self.danh_sach(project_id, dang_song=True)

    def doi_trang_thai(self, execution_id: str, moi: TrangThaiThucThi, *,
                       ly_do: str = "", pha: str = "",
                       force: bool = False) -> YDinhThucThi:
        """Đổi trạng thái CÓ KIỂM, trong MỘT giao dịch.

        `force` cố ý KHÔNG bỏ qua bảng chuyển — nó chỉ bỏ qua yêu cầu "phải
        có lý do". `RUNNING -> DONE` vẫn ném kể cả với `force=True`; đó là
        điểm chính của §5 và một cờ không được phép mở nó.
        """
        with self.store.giao_dich_ghi() as c:
            h = c.execute("SELECT * FROM executions WHERE execution_id = ?",
                          (execution_id,)).fetchone()
            if h is None:
                raise KeyError(f"không có lần thực thi {execution_id!r}")
            cu = TrangThaiThucThi(h["state"])
            kiem_chuyen(execution_id, cu, moi)
            if cu is not moi and not force and moi.can_nguoi and not ly_do:
                raise ValueError(
                    f"{execution_id}: vào {moi.value} phải nói VÌ SAO — "
                    f"người dùng đọc dòng đó để biết cần làm gì")
            now = time.time()
            ket = now if moi.ket_thuc else 0.0
            c.execute(
                "UPDATE executions SET state = ?, pha = ?, ly_do_dung = ?, "
                " updated_at = ?, ended_at = ? WHERE execution_id = ?",
                (moi.value, pha or (h["pha"] or ""),
                 khong_suy_nghi(ly_do or (h["ly_do_dung"] or ""), toi_da=600),
                 now, ket or float(h["ended_at"] or 0), execution_id))
            h2 = c.execute("SELECT * FROM executions WHERE execution_id = ?",
                           (execution_id,)).fetchone()
        self.ghi_su_kien(
            execution_id, "EXEC_STATE", project_id=h["project_id"],
            level=("WARNING" if moi.can_nguoi or moi is TrangThaiThucThi.FAILED
                   else "INFO"),
            detail=f"{cu.value} -> {moi.value}" + (f": {ly_do}" if ly_do else ""),
            meta={"cu": cu.value, "moi": moi.value, "pha": pha})
        return self._tu_hang(h2)

    def dat_duyet(self, execution_id: str, duyet: TrangThaiDuyet, *,
                  boi: str = "user") -> YDinhThucThi:
        """Đổi trạng thái CỔNG. Tách khỏi `doi_trang_thai` có chủ đích.

        Duyệt một cổng và đổi trạng thái máy là hai sự kiện khác nhau, và
        gộp chúng sẽ làm bản kiểm toán không phân biệt được "người đã duyệt"
        với "máy tự đi tiếp".
        """
        with self.store.giao_dich_ghi() as c:
            c.execute("UPDATE executions SET duyet = ?, duyet_boi = ?, "
                      " duyet_luc = ?, updated_at = ? WHERE execution_id = ?",
                      (duyet.value, str(boi or "")[:80], time.time(),
                       time.time(), execution_id))
        y = self.y_dinh(execution_id)
        if y is None:
            raise KeyError(f"không có lần thực thi {execution_id!r}")
        self.ghi_su_kien(execution_id, "EXEC_AUTHORITY",
                         project_id=y.project_id, level="WARNING",
                         detail=f"cổng thẩm quyền -> {duyet.value} (bởi {boi})")
        return y

    # ------------------------------------------------------------ ke hoach --

    def luu_ke_hoach(self, kh: KeHoachThucThi) -> KeHoachThucThi:
        """Lưu một BẢN. Bản cũ chỉ mất `dang_hieu_luc`, KHÔNG bị xoá — §10."""
        with self.store.giao_dich_ghi() as c:
            if kh.dang_hieu_luc:
                c.execute("UPDATE execution_plans SET dang_hieu_luc = 0 "
                          "WHERE execution_id = ?", (kh.execution_id,))
            c.execute(
                "INSERT INTO execution_plans(execution_id, phien_ban, "
                " buoc_json, ly_do_sua, thay_doi_json, bang_chung_json, "
                " dang_hieu_luc, created_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(execution_id, phien_ban) DO UPDATE SET "
                " buoc_json=excluded.buoc_json, "
                " ly_do_sua=excluded.ly_do_sua, "
                " thay_doi_json=excluded.thay_doi_json, "
                " bang_chung_json=excluded.bang_chung_json, "
                " dang_hieu_luc=excluded.dang_hieu_luc",
                (kh.execution_id, kh.phien_ban,
                 _js([b.to_dict() for b in kh.buoc]), kh.ly_do_sua,
                 _js(list(kh.thay_doi)), _js(list(kh.bang_chung_gay_ra)),
                 int(bool(kh.dang_hieu_luc)), kh.created_at))
            c.execute("UPDATE executions SET ban_ke_hoach = ?, updated_at = ? "
                      "WHERE execution_id = ? AND ? >= ban_ke_hoach",
                      (kh.phien_ban, time.time(), kh.execution_id,
                       kh.phien_ban))
        return kh

    @staticmethod
    def _kh_tu_hang(h) -> KeHoachThucThi:
        return KeHoachThucThi.tu_dict({
            "execution_id": h["execution_id"], "phien_ban": h["phien_ban"],
            "buoc": _un(h["buoc_json"], []), "ly_do_sua": h["ly_do_sua"],
            "thay_doi": _un(h["thay_doi_json"], []),
            "bang_chung_gay_ra": _un(h["bang_chung_json"], []),
            "dang_hieu_luc": bool(h["dang_hieu_luc"]),
            "created_at": h["created_at"]})

    def ke_hoach(self, execution_id: str,
                 phien_ban: int = 0) -> Optional[KeHoachThucThi]:
        """Bản `phien_ban`, hoặc bản ĐANG HIỆU LỰC khi `phien_ban == 0`."""
        c = self.store.ket_noi()
        if phien_ban:
            h = c.execute("SELECT * FROM execution_plans WHERE execution_id = ? "
                          "AND phien_ban = ?",
                          (execution_id, int(phien_ban))).fetchone()
        else:
            h = c.execute("SELECT * FROM execution_plans WHERE execution_id = ? "
                          "AND dang_hieu_luc = 1 ORDER BY phien_ban DESC "
                          "LIMIT 1", (execution_id,)).fetchone()
        return self._kh_tu_hang(h) if h else None

    def cac_ban_ke_hoach(self, execution_id: str) -> List[KeHoachThucThi]:
        """MỌI bản, cũ nhất trước. Lịch sử §10 đọc từ đây."""
        return [self._kh_tu_hang(h) for h in self.store.ket_noi().execute(
            "SELECT * FROM execution_plans WHERE execution_id = ? "
            "ORDER BY phien_ban ASC", (execution_id,)).fetchall()]

    # ---------------------------------------------------------------- buoc --

    def luu_buoc(self, execution_id: str, phien_ban: int, buoc_id: str, *,
                 task_id: Optional[str] = None, state: Optional[str] = None,
                 xac_minh: Optional[TrangThaiXacMinh] = None,
                 ket_qua: Optional[HopDongKetQua] = None,
                 kiem: Optional[Sequence[Dict]] = None,
                 tang_lan_thu: bool = False) -> Dict:
        """Cập nhật MỘT bước. Chỉ trường được truyền mới bị ghi đè.

        `tang_lan_thu` là một phép cộng NGUYÊN TỬ trong giao dịch, không phải
        `doc -> +1 -> ghi` ở tầng trên: trần thử lại của §9 dựa vào con số
        này, và một lần đếm hụt sẽ biến trần 2 thành trần vô hạn.
        """
        with self.store.giao_dich_ghi() as c:
            c.execute(
                "INSERT INTO execution_steps(execution_id, phien_ban, buoc_id,"
                " task_id, state, xac_minh, ket_qua_json, kiem_json, "
                " so_lan_thu, updated_at) VALUES(?,?,?,'','CHUA_CHAY',"
                " 'CHUA_KIEM','','[]',0,?) "
                "ON CONFLICT(execution_id, phien_ban, buoc_id) DO NOTHING",
                (execution_id, int(phien_ban), buoc_id, time.time()))
            dat, a = ["updated_at = ?"], [time.time()]
            if task_id is not None:
                dat.append("task_id = ?")
                a.append(task_id)
            if state is not None:
                dat.append("state = ?")
                a.append(state)
            if xac_minh is not None:
                dat.append("xac_minh = ?")
                a.append(xac_minh.value)
            if ket_qua is not None:
                dat.append("ket_qua_json = ?")
                a.append(_js(ket_qua.to_dict()))
            if kiem is not None:
                dat.append("kiem_json = ?")
                a.append(_js(list(kiem)))
            if tang_lan_thu:
                dat.append("so_lan_thu = so_lan_thu + 1")
            a += [execution_id, int(phien_ban), buoc_id]
            c.execute("UPDATE execution_steps SET " + ", ".join(dat)
                      + " WHERE execution_id = ? AND phien_ban = ? "
                        "AND buoc_id = ?", a)
            h = c.execute("SELECT * FROM execution_steps WHERE execution_id = ? "
                          "AND phien_ban = ? AND buoc_id = ?",
                          (execution_id, int(phien_ban), buoc_id)).fetchone()
        return self._buoc_tu_hang(h)

    @staticmethod
    def _buoc_tu_hang(h) -> Dict:
        return {"execution_id": h["execution_id"], "phien_ban": h["phien_ban"],
                "buoc_id": h["buoc_id"], "task_id": h["task_id"],
                "state": h["state"], "xac_minh": h["xac_minh"],
                "ket_qua": _un(h["ket_qua_json"], None),
                "kiem": _un(h["kiem_json"], []),
                "so_lan_thu": int(h["so_lan_thu"] or 0),
                "updated_at": h["updated_at"]}

    def buoc(self, execution_id: str, phien_ban: int = 0) -> List[Dict]:
        c = self.store.ket_noi()
        if not phien_ban:
            kh = self.ke_hoach(execution_id)
            phien_ban = kh.phien_ban if kh else 1
        return [self._buoc_tu_hang(h) for h in c.execute(
            "SELECT * FROM execution_steps WHERE execution_id = ? AND "
            "phien_ban = ? ORDER BY buoc_id", (execution_id, int(phien_ban))
        ).fetchall()]

    def buoc_theo_task(self, task_id: str) -> Optional[Dict]:
        """Việc Router V4 nào thuộc bước nào. Bộ điều phối gọi lúc việc xong."""
        h = self.store.ket_noi().execute(
            "SELECT * FROM execution_steps WHERE task_id = ? "
            "ORDER BY updated_at DESC LIMIT 1", (task_id,)).fetchone()
        return self._buoc_tu_hang(h) if h else None

    def dem_thu_lai(self, execution_id: str, *, tang: int = 0) -> int:
        with self.store.giao_dich_ghi() as c:
            if tang:
                c.execute("UPDATE executions SET so_lan_thu_lai = "
                          "so_lan_thu_lai + ?, updated_at = ? "
                          "WHERE execution_id = ?",
                          (int(tang), time.time(), execution_id))
            h = c.execute("SELECT so_lan_thu_lai FROM executions "
                          "WHERE execution_id = ?", (execution_id,)).fetchone()
        return int((h["so_lan_thu_lai"] if h else 0) or 0)

    def dem_lap_lai(self, execution_id: str, *, tang: int = 0) -> int:
        with self.store.giao_dich_ghi() as c:
            if tang:
                c.execute("UPDATE executions SET so_lan_lap_lai = "
                          "so_lan_lap_lai + ?, updated_at = ? "
                          "WHERE execution_id = ?",
                          (int(tang), time.time(), execution_id))
            h = c.execute("SELECT so_lan_lap_lai FROM executions "
                          "WHERE execution_id = ?", (execution_id,)).fetchone()
        return int((h["so_lan_lap_lai"] if h else 0) or 0)

    def dat_ket_luan(self, execution_id: str, ket_luan: str) -> None:
        with self.store.giao_dich_ghi() as c:
            c.execute("UPDATE executions SET ket_luan = ?, updated_at = ? "
                      "WHERE execution_id = ?",
                      (khong_suy_nghi(ket_luan, toi_da=4000), time.time(),
                       execution_id))

    # ------------------------------------------------------------- de xuat --

    def luu_de_xuat(self, d: DeXuat) -> DeXuat:
        with self.store.giao_dich_ghi() as c:
            c.execute(
                "INSERT INTO de_xuat(ma, project_id, message_id, tom_tat, "
                " cac_buoc_json, rui_ro, tac_dong_prod, tu_vai, execution_id, "
                " ts) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(ma) DO UPDATE SET tom_tat=excluded.tom_tat, "
                " cac_buoc_json=excluded.cac_buoc_json, "
                " rui_ro=excluded.rui_ro, "
                " tac_dong_prod=excluded.tac_dong_prod, "
                " execution_id=excluded.execution_id",
                (d.ma, d.project_id, int(d.message_id),
                 khong_suy_nghi(d.tom_tat, toi_da=2000),
                 _js([khong_suy_nghi(x, toi_da=300) for x in d.cac_buoc]),
                 d.rui_ro, int(bool(d.tac_dong_production)), d.tu_vai,
                 d.execution_id, d.ts))
        return d

    @staticmethod
    def _dx_tu_hang(h) -> DeXuat:
        return DeXuat(ma=h["ma"], project_id=h["project_id"],
                      message_id=int(h["message_id"] or 0),
                      tom_tat=h["tom_tat"] or "",
                      cac_buoc=tuple(_un(h["cac_buoc_json"], [])),
                      rui_ro=h["rui_ro"] or "LOW",
                      tac_dong_production=bool(h["tac_dong_prod"]),
                      tu_vai=h["tu_vai"] or "strategist",
                      execution_id=h["execution_id"] or "",
                      ts=float(h["ts"] or 0))

    def de_xuat(self, project_id: str, *, limit: int = 20,
                chua_dung: bool = False) -> List[DeXuat]:
        q = "SELECT * FROM de_xuat WHERE project_id = ?"
        a: List[Any] = [project_id]
        if chua_dung:
            q += " AND execution_id = ''"
        q += " ORDER BY ts DESC LIMIT ?"
        a.append(int(limit))
        return [self._dx_tu_hang(h)
                for h in self.store.ket_noi().execute(q, a).fetchall()]

    def danh_dau_de_xuat(self, ma: str, execution_id: str) -> None:
        with self.store.giao_dich_ghi() as c:
            c.execute("UPDATE de_xuat SET execution_id = ? WHERE ma = ?",
                      (execution_id, ma))

    # ------------------------------------------------------------ anh chup --

    def anh_chup(self, execution_id: str) -> Dict:
        """Ảnh chụp ĐẦY ĐỦ một lần thực thi — thứ API và Leader cùng đọc."""
        y = self.y_dinh(execution_id)
        if y is None:
            return {}
        kh = self.ke_hoach(execution_id)
        bs = self.buoc(execution_id, kh.phien_ban if kh else 1)
        theo_ma = {b["buoc_id"]: b for b in bs}
        return {"y_dinh": y.to_dict(),
                "ke_hoach": (kh.to_dict() if kh else None),
                "buoc": [{**(kh.buoc_theo_ma(b["buoc_id"]).to_dict()
                             if kh and kh.buoc_theo_ma(b["buoc_id"]) else {}),
                          **b}
                         for b in bs],
                "ban_ke_hoach": [{"phien_ban": p.phien_ban,
                                  "ly_do_sua": p.ly_do_sua,
                                  "thay_doi": list(p.thay_doi),
                                  "bang_chung": list(p.bang_chung_gay_ra),
                                  "dang_hieu_luc": p.dang_hieu_luc,
                                  "so_buoc": len(p.buoc),
                                  "created_at": p.created_at}
                                 for p in self.cac_ban_ke_hoach(execution_id)],
                "su_kien": self.su_kien(execution_id, limit=60),
                "tien_do": tien_do(kh, theo_ma)}


def tien_do(kh: Optional[KeHoachThucThi], theo_ma: Dict[str, Dict]) -> Dict:
    """`{xong, tong, dang_chay, hong, chua_kiem}` — §12 trả lời từ đây.

    Hàm THUẦN, tách khỏi sổ có chủ đích: Leader, API và bài kiểm đều gọi nó,
    và không cái nào trong ba cái đó nên phải mở SQLite để biết "3/5 bước".
    """
    if kh is None:
        return {"xong": 0, "tong": 0, "dang_chay": 0, "hong": 0,
                "chua_kiem": 0, "phan_tram": 0}
    tong = len(kh.buoc)
    xong = hong = chay = chua = 0
    for b in kh.buoc:
        st = (theo_ma.get(b.buoc_id) or {})
        xm = str(st.get("xac_minh") or "CHUA_KIEM")
        s = str(st.get("state") or "CHUA_CHAY")
        if xm in ("DAT", "SUY_GIAM"):
            xong += 1
        elif xm in ("KHONG_DAT", "THIEU_BANG_CHUNG"):
            hong += 1
        elif s == "RUNNING":
            chay += 1
        elif s == "DONE":
            chua += 1                       # da chay, CHUA kiem — khong tinh xong
    return {"xong": xong, "tong": tong, "dang_chay": chay, "hong": hong,
            "chua_kiem": chua,
            "phan_tram": int(round(100.0 * xong / tong)) if tong else 0}
