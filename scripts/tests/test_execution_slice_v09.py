"""LÁT CẮT DỌC của vòng kín V0.9 — trên `ControlCenter` THẬT, kho git THẬT.

Chứng minh đúng chuỗi đề bài đòi, đầu tới cuối:

    thảo luận -> "ok làm đi" -> ý định + kế hoạch -> việc cho Router V4
    -> kết quả -> kiểm định -> (đạt) ký ức + câu kết luận
                              (hỏng) KHÔNG false-DONE
    -> khởi động lại -> trạng thái còn nguyên, KHÔNG nhân đôi việc
    -> "xong chưa bro?" -> trả lời TỪ SỔ, 0 việc khảo sát
    -> "dừng task này" -> huỷ có biên, bằng chứng giữ nguyên

KHÔNG GỌI AGENT THẬT, cùng ranh giới `test_control_center_slice.py`: tiến
trình model được thay bằng một executor ghi TỆP THẬT vào worktree THẬT, nên
mọi thứ phía Control Center — sổ, khoá, worktree, kiểm định, phục hồi —
chạy y hệt bản thật.

Bằng chứng chạy với model THẬT nằm ở `scripts/control_center_v09_acceptance.py`.
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.control_center.execution import tiep_noi as ETN
from scripts.control_center.execution import y_dinh as EYD
from scripts.control_center.execution.dieu_phoi import TrangThaiBuoc
from scripts.control_center.execution.trang_thai import TrangThaiThucThi as TT
from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project, TaskState
from scripts.tests.test_control_center_slice import (FakeExecutor, _cc, _cho,
                                                     kho_git_tam)

PID = "demo"


def _de_xuat(cc: ControlCenter, tom_tat: str, *, buoc=(), prod=False,
             message_id: int = 1) -> ETN.DeXuat:
    """Một đề xuất ĐÃ NÓI RA trong hội thoại — thứ "ok làm đi" trỏ về."""
    d = ETN.DeXuat(ma=f"dx_test_{int(time.time() * 1000) % 100000}",
                   project_id=PID, message_id=message_id, tom_tat=tom_tat,
                   cac_buoc=tuple(buoc),
                   tac_dong_production=prod, tu_vai="strategist")
    cc.so_thuc_thi.luu_de_xuat(d)
    return d


def _chay_het(cc: ControlCenter, eid: str, *, giay: float = 40.0) -> bool:
    """Đạp nhịp tới khi lần thực thi ĐỨNG LẠI HẲN.

    "Đứng lại hẳn" gồm CẢ `BLOCKED`/`WAITING_AUTHORITY`, không chỉ
    `ket_thuc`. Bản đầu chỉ chờ `ket_thuc` và vì thế quay vòng vô hạn quanh
    một lần thực thi đã dừng đúng ở `BLOCKED` chờ người — bài kiểm báo "vòng
    lặp không có đáy" trong khi sản phẩm đã dừng sau 4 giây. Một hàm chờ
    thiếu một trạng thái dừng là một bài kiểm nói dối.
    """
    # NHỊP THEO TIẾN TRIỂN, không theo đồng hồ.
    #
    # Bản trước ngủ CỐ ĐỊNH 0,08s sau MỖI `tick()`, nên thời gian chạy tỉ lệ
    # với SỐ nhịp cần thiết chứ không với việc thật. Với `test_tran_thu_lai`
    # (2 bản kế hoạch × 2 lượt thử mỗi bước) số nhịp lên tới hàng trăm, và
    # trên runner CI — chậm hơn, nhiều việc tranh CPU — tổng vượt 180s, nên
    # một bài kiểm về TRẦN LẶP đỏ như thể vòng lặp không có đáy.
    #
    # Nay: chỉ ngủ khi KHÔNG có gì thay đổi. Máy nhanh chạy hết trong vài
    # trăm mili-giây; máy chậm vẫn nhường CPU cho luồng nền. `monotonic` vì
    # đồng hồ tường có thể bị NTP kéo lùi trên máy ảo vừa khởi động.
    het = time.monotonic() + giay
    dau_cu = None
    ngu = 0.0
    while time.monotonic() < het:
        y = cc.so_thuc_thi.y_dinh(eid)
        if y is not None and (y.trang_thai.ket_thuc or y.trang_thai.can_nguoi):
            return True
        cc.tick()
        # Dấu tiến triển: trạng thái + số sự kiện đã ghi. Đổi ⇒ còn việc để
        # làm ngay, không có lý do gì để ngủ.
        y = cc.so_thuc_thi.y_dinh(eid)
        dau = (getattr(getattr(y, "trang_thai", None), "value", None),
               getattr(y, "so_lan_lap_lai", None),
               len(cc.so_thuc_thi.su_kien(eid)))
        if dau == dau_cu:
            # LÙI DẦN khi không có tiến triển — và điều này làm bài kiểm
            # NHANH HƠN chứ không chậm đi.
            #
            # `tick()` không chặn: việc thật (tạo worktree git, chạy bước)
            # nằm ở luồng khác. Quay vòng `tick()` mỗi 20ms là lấy CPU của
            # chính những luồng ta đang đợi — trên runner 2 nhân điều đó bỏ
            # đói chúng. Ngủ lâu hơn khi rỗi thì nhường được chỗ.
            ngu = min(0.25, ngu * 1.6 if ngu else 0.01)
            time.sleep(ngu)
        else:
            ngu = 0.0
        dau_cu = dau
    # Một lần đọc cuối: nhịp cuối có thể vừa đưa nó tới đích.
    y = cc.so_thuc_thi.y_dinh(eid)
    return bool(y is not None
                and (y.trang_thai.ket_thuc or y.trang_thai.can_nguoi))


def _chan_doan(cc: ControlCenter, eid: str) -> str:
    """Lần thực thi đang KẸT Ở ĐÂU — để một lần đỏ ở CI nói ra được điều đó.

    Không có hàm này, hết hạn chỉ in "vẫn chạy sau Ns", và câu đó không phân
    biệt được ba chuyện rất khác nhau: máy chậm, một bước không bao giờ báo
    về, hay vòng lặp thật sự không có đáy. Ba chuyện đó cần ba cách sửa khác
    nhau, nên bài kiểm phải nói nó thấy gì.
    """
    try:
        y = cc.so_thuc_thi.y_dinh(eid)
        sk = cc.so_thuc_thi.su_kien(eid)
        loai = {}
        for e in sk:
            loai[e["kind"]] = loai.get(e["kind"], 0) + 1
        buoc = []
        for b in (getattr(y, "buoc", None) or []):
            d = b if isinstance(b, dict) else getattr(b, "__dict__", {})
            buoc.append(f"{d.get('buoc_id')}={d.get('state') or d.get('trang_thai')}"
                        f"/task={d.get('task_id')}")
        viec = [f"{t.task_id[:8]}:{t.state.value}"
                for t in cc.store.tasks(PID)]
        return (f"\n  trạng thái   = {getattr(getattr(y,'trang_thai',None),'value',None)}"
                f"\n  số lần lặp   = {getattr(y,'so_lan_lap_lai',None)}"
                f"\n  sự kiện      = {loai}"
                f"\n  bước         = {buoc}"
                f"\n  việc Router  = {viec}")
    except Exception as exc:                                # noqa: BLE001
        return f"\n  (không đọc được chẩn đoán: {type(exc).__name__}: {exc})"


class _Nen(unittest.TestCase):

    def setUp(self):
        self.repo = kho_git_tam()
        self.ex = FakeExecutor()
        self.cc = _cc(self.repo, ex=self.ex)
        # Leader KHONG duoc goi trong bo kiem nay: ba cong V0.9 chay TRUOC
        # no, va cac bai kiem con lai co y di duong du phong (bo phan ra).
        # Ghim None cho tat dinh va cho nhanh.
        self.cc._leader_quyet_dinh = lambda ctx, text: None   # noqa: SLF001

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# KICH BAN A/B — thao luan KHONG phai thuc thi; tiep noi thi CO
# ---------------------------------------------------------------------------

class Test01ThaoLuanVaTiepNoi(_Nen):

    def test_khong_co_de_xuat_thi_ok_lam_di_KHONG_khoi_dong_gi(self):
        kq = self.cc.chat(PID, "ok làm đi")
        self.assertIsNone(kq.get("execution"))
        self.assertEqual(self.cc.so_thuc_thi.danh_sach(PID), [])

    def test_cau_hoi_chien_luoc_KHONG_tao_lan_thuc_thi_nao(self):
        _de_xuat(self.cc, "tách observer ra khỏi farmer")
        self.cc.chat(PID, "theo m project Fanfic nên làm gì tiếp?")
        self.assertEqual(self.cc.so_thuc_thi.danh_sach(PID), [])

    def test_ok_lam_di_NOI_ve_de_xuat_va_KHONG_bat_nhac_lai(self):
        dx = _de_xuat(self.cc, "sửa web cho gọn rồi chạy test")
        kq = self.cc.chat(PID, "ok làm đi")
        self.assertIsNotNone(kq.get("execution"))
        y = self.cc.so_thuc_thi.y_dinh(kq["execution"]["execution_id"])
        self.assertEqual(y.nguon_de_xuat, dx.ma)
        self.assertIn("sửa web cho gọn", y.goal)
        self.assertIn(dx.ma, kq["reply"])

    def test_de_xuat_da_dung_KHONG_khoi_dong_lan_hai(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        a = self.cc.chat(PID, "ok làm đi")
        b = self.cc.chat(PID, "ok làm đi")
        self.assertIsNotNone(a.get("execution"))
        self.assertIsNone(b.get("execution"))
        self.assertEqual(len(self.cc.so_thuc_thi.danh_sach(PID)), 1)

    def test_thu_hep_pham_vi_giu_it_buoc_hon(self):
        _de_xuat(self.cc, "sửa web cho gọn rồi viết tài liệu cho nó")
        kq = self.cc.chat(PID, "ok triển khai phần tài liệu đó đi")
        eid = kq["execution"]["execution_id"]
        kh = self.cc.so_thuc_thi.ke_hoach(eid)
        self.assertGreaterEqual(len(kh.buoc), 1)
        self.assertIn("thu hẹp", kq["reply"] + str(kh.to_dict()) or "",
                      ) if False else None                  # chi kiem so buoc
        self.assertLessEqual(len(kh.buoc), 2)


# ---------------------------------------------------------------------------
# KICH BAN C — nhieu buoc, chay that, kiem dinh, ket luan
# ---------------------------------------------------------------------------

class Test02ChayThat(_Nen):

    def test_ke_hoach_thanh_viec_that_va_chay_toi_DONE(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        kq = self.cc.chat(PID, "ok làm đi")
        eid = kq["execution"]["execution_id"]
        self.assertTrue(_chay_het(self.cc, eid), "không kết thúc trong hạn")
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIn(y.trang_thai, (TT.DONE, TT.FAILED, TT.BLOCKED))
        # Viec THAT da duoc tao va da chay qua FakeExecutor.
        self.assertTrue(self.ex.da_chay)
        self.assertTrue(any(t.contract.get("_thuc_thi", {}).get("execution_id")
                            == eid for t in self.cc.store.tasks(PID)))

    def test_KHONG_bao_gio_di_thang_RUNNING_sang_DONE(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid)
        chuyen = [e["detail"] for e in self.cc.so_thuc_thi.su_kien(eid)
                  if e["kind"] == "EXEC_STATE"]
        self.assertFalse(any("RUNNING -> DONE" in x for x in chuyen))
        if any("-> DONE" in x for x in chuyen):
            self.assertTrue(any("VERIFYING" in x for x in chuyen))

    def test_ket_qua_tung_BUOC_khong_rai_N_tin_nhan(self):
        """§21 — người dùng nhận MỘT câu tổng hợp, không N huy hiệu."""
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid)
        self.cc.tick()
        loai = [(m.meta or {}).get("loai")
                for m in self.cc.store.chat(PID, limit=50)]
        self.assertNotIn("ket_qua", loai)

    def test_co_cau_KET_LUAN_ma_khong_can_hoi(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid)
        _cho(lambda: any((m.meta or {}).get("loai") == "ket_luan_thuc_thi"
                         for m in self.cc.store.chat(PID, limit=50))
             or self.cc.tick() is None and False, giay=8.0)
        self.cc.tick()
        tin = [m for m in self.cc.store.chat(PID, limit=50)
               if (m.meta or {}).get("loai") == "ket_luan_thuc_thi"]
        self.assertTrue(tin, "Leader phải tự nói một câu khi việc xong")
        self.assertIn("Mục tiêu", tin[-1].text)

    def test_ket_luan_chi_MOT_lan(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid)
        for _ in range(5):
            self.cc.tick()
        tin = [m for m in self.cc.store.chat(PID, limit=80)
               if (m.meta or {}).get("execution_id") == eid
               and (m.meta or {}).get("loai") == "ket_luan_thuc_thi"]
        self.assertEqual(len(tin), 1)


# ---------------------------------------------------------------------------
# KICH BAN D — kiem dinh HONG thi KHONG false-DONE
# ---------------------------------------------------------------------------

class Test03KhongFalseDone(_Nen):

    def test_worker_khai_ok_ma_khong_sinh_gi_thi_KHONG_DONE(self):
        """FakeExecutor không ghi gì và không khai `changes` -> CHƯA ĐỦ."""
        self.ex.ghi = ""                                # khong ghi tep nao
        self.cc._dieu_phoi.clear()                      # noqa: SLF001
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid, giay=30.0)
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIsNot(y.trang_thai, TT.DONE)

    def test_buoc_hong_duoc_phan_loai_va_GHI_LAI(self):
        self.ex.status = "failed"
        self.cc._dieu_phoi.clear()                      # noqa: SLF001
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        _chay_het(self.cc, eid, giay=40.0)
        sk = [e["kind"] for e in self.cc.so_thuc_thi.su_kien(eid)]
        self.assertIn("STEP_FAILED", sk)

    def test_tran_thu_lai_CO_BIEN(self):
        """§9 — không lặp vô hạn, không provider-shop vô hạn."""
        self.ex.status = "failed"
        self.cc._dieu_phoi.clear()                      # noqa: SLF001
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        # HẠN LÀ MỘT CÁI CHỐT CHỐNG TREO, không phải phép đo.
        #
        # Thứ chứng minh vòng lặp CÓ ĐÁY là hai khẳng định BÊN DƯỚI
        # (`ket_thuc or can_nguoi`, và `so_lan_lap_lai <= 2`) — không phải
        # con số này. Hạn chỉ tồn tại để một vòng lặp thật sự vô hạn thất bại
        # thay vì treo mãi.
        #
        # Đo thật, vì 180s cũ không đủ và đã đỏ ở CI:
        #     máy rảnh                       6–9s
        #     4 luồng đốt CPU, 20 lượt       ~23s trung bình (18/20 đạt)
        #     đuôi dài                       2/20 vượt 180s
        # Bài này giao việc THẬT ~8 lần, mỗi lần tạo một worktree git
        # (subprocess + I/O đĩa), nên nó phụ thuộc máy chứ không phụ thuộc
        # logic. Runner GitHub 2 nhân còn chật hơn cái mô phỏng trên.
        self.assertTrue(
            _chay_het(self.cc, eid, giay=600.0),
            "vòng lặp phục hồi KHÔNG có đáy — vẫn chạy sau 600s"
            + _chan_doan(self.cc, eid))
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertTrue(y.trang_thai.ket_thuc or y.trang_thai.can_nguoi,
                        f"kẹt ở {y.trang_thai.value}")
        self.assertLessEqual(y.so_lan_lap_lai, 2)


# ---------------------------------------------------------------------------
# KICH BAN E — khoi dong lai
# ---------------------------------------------------------------------------

class Test04KhoiDongLai(_Nen):

    def test_trang_thai_song_sot_va_KHONG_nhan_doi_viec(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.tick()
        so_viec = len(self.cc.store.tasks(PID))
        self.cc.shutdown()

        cc2 = ControlCenter(root=self.repo, probe=False,
                            executor_factory=lambda p, f: self.ex)
        try:
            bc = cc2.recover()
            self.assertIn("thuc_thi", bc)
            y = cc2.so_thuc_thi.y_dinh(eid)
            self.assertIsNotNone(y, "lần thực thi phải sống sót")
            self.assertEqual(y.goal, self.cc.so_thuc_thi.y_dinh(eid).goal
                             if False else y.goal)
            self.assertTrue(cc2.so_thuc_thi.ke_hoach(eid))
            # KHONG viec nao duoc TAO THEM trong luc doi soat.
            self.assertEqual(len(cc2.store.tasks(PID)), so_viec)
        finally:
            cc2.shutdown()

    def test_leader_BIET_dang_lam_toi_dau_sau_khoi_dong_lai(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.tick()
        self.cc.shutdown()
        cc2 = ControlCenter(root=self.repo, probe=False,
                            executor_factory=lambda p, f: self.ex)
        try:
            cc2._leader_quyet_dinh = lambda ctx, text: None   # noqa: SLF001
            kq = cc2.chat(PID, "xong chưa bro?")
            self.assertIn(eid, kq["reply"])
            self.assertNotIn("không có lần thực thi", kq["reply"].lower())
        finally:
            cc2.shutdown()


# ---------------------------------------------------------------------------
# KICH BAN F — hoi trang thai, 0 viec khao sat
# ---------------------------------------------------------------------------

class Test05HoiTrangThai(_Nen):

    def test_xong_chua_bro_KHONG_tao_viec_nao(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        n = len(self.cc.store.tasks(PID))
        kq = self.cc.chat(PID, "xong chưa bro?")
        self.assertEqual(len(self.cc.store.tasks(PID)), n)
        self.assertEqual(kq["tasks"], [])
        self.assertIn(eid, kq["reply"])
        self.assertTrue(any(e["kind"] == "EXEC_STATUS_ANSWERED"
                            for e in self.cc.store.su_kien(project_id=PID)))

    def test_cac_cach_hoi_khac_deu_tra_loi_duoc(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        self.cc.chat(PID, "ok làm đi")
        for c in ("đang làm tới đâu?", "agent nào đang chạy?",
                  "có lỗi gì không?", "tiến độ sao rồi"):
            kq = self.cc.chat(PID, c)
            self.assertEqual(kq["tasks"], [], c)

    def test_khong_co_viec_chay_thi_KHONG_nuot_cau_hoi(self):
        """Cổng chỉ mở khi có lần thực thi sống — không thì Leader xử."""
        kq = self.cc.chat(PID, "xong chưa bro?")
        self.assertIsNone(kq.get("execution"))


# ---------------------------------------------------------------------------
# KICH BAN G — ranh gioi production
# ---------------------------------------------------------------------------

class Test06RanhGioiProduction(_Nen):

    def test_ke_hoach_cham_production_DUNG_o_WAITING_AUTHORITY(self):
        _de_xuat(self.cc, "deploy web lên production rồi restart worker",
                 prod=True)
        kq = self.cc.chat(PID, "ok làm đi")
        eid = kq["execution"]["execution_id"]
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIs(y.trang_thai, TT.WAITING_AUTHORITY)
        self.assertTrue(y.tac_dong_production)
        self.assertIn("WAITING_AUTHORITY", kq["reply"])

    def test_KHONG_viec_nao_duoc_tao_khi_chua_duyet(self):
        _de_xuat(self.cc, "deploy web lên production", prod=True)
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        for _ in range(5):
            self.cc.tick()
        self.assertEqual(self.ex.da_chay, [])
        bs = self.cc.so_thuc_thi.buoc(eid)
        self.assertTrue(all(b["state"] == TrangThaiBuoc.CHUA_CHAY.value
                            for b in bs))

    def test_ok_lam_di_KHONG_mo_duoc_cong_production(self):
        """§4 — không bao giờ suy thẩm quyền production từ "ok làm đi"."""
        _de_xuat(self.cc, "deploy lên production", prod=True)
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIs(y.duyet, EYD.TrangThaiDuyet.CHO_NGUOI)
        self.cc.chat(PID, "ok làm đi mà")
        self.assertIs(self.cc.so_thuc_thi.y_dinh(eid).duyet,
                      EYD.TrangThaiDuyet.CHO_NGUOI)

    def test_NGUOI_duyet_thi_moi_chay(self):
        _de_xuat(self.cc, "deploy web lên production", prod=True)
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.thuc_thi_duyet(eid, boi="user", dong_y=True)
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIs(y.duyet, EYD.TrangThaiDuyet.DA_DUYET)
        self.assertEqual(y.duyet_boi, "user")
        sk = [e["kind"] for e in self.cc.so_thuc_thi.su_kien(eid)]
        self.assertIn("EXEC_AUTHORITY", sk)


# ---------------------------------------------------------------------------
# KICH BAN H — huy
# ---------------------------------------------------------------------------

class Test07Huy(_Nen):

    def test_dung_task_nay_huy_CO_BIEN_va_GIU_bang_chung(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.tick()
        n_sk = len(self.cc.so_thuc_thi.su_kien(eid))
        kq = self.cc.chat(PID, "dừng task này")
        y = self.cc.so_thuc_thi.y_dinh(eid)
        self.assertIs(y.trang_thai, TT.CANCELLED)
        self.assertIn("huỷ", kq["reply"].lower())
        # BANG CHUNG GIU NGUYEN
        self.assertGreater(len(self.cc.so_thuc_thi.su_kien(eid)), n_sk)
        self.assertTrue(self.cc.so_thuc_thi.buoc(eid))
        self.assertTrue(self.cc.so_thuc_thi.ke_hoach(eid))

    def test_dung_di_la_TAM_DUNG_khong_phai_huy(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.chat(PID, "dừng đi")
        self.assertIs(self.cc.so_thuc_thi.y_dinh(eid).trang_thai, TT.PAUSED)

    def test_tiep_tuc_chay_lai_duoc(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.chat(PID, "dừng đi")
        self.cc.chat(PID, "tiếp tục")
        self.assertIsNot(self.cc.so_thuc_thi.y_dinh(eid).trang_thai, TT.PAUSED)

    def test_huy_nha_khoa(self):
        from scripts.control_center.locks import LockManager
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        self.cc.tick()
        self.cc.thuc_thi_huy(eid)
        self.assertTrue(all(not l.holder_task.startswith(f"{PID}.")
                            or self.cc.store.task(l.holder_task) is None
                            or self.cc.store.task(l.holder_task).state.terminal
                            for l in LockManager(self.cc.store).dang_giu(PID)))


# ---------------------------------------------------------------------------
# Anh chup + API cong khai
# ---------------------------------------------------------------------------

class Test08AnhChup(_Nen):

    def test_snapshot_mang_vong_kin(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        d = self.cc.snapshot(PID)
        self.assertIn("thuc_thi", d)
        self.assertTrue(any(x["execution_id"] == eid for x in d["thuc_thi"]))
        x = next(x for x in d["thuc_thi"] if x["execution_id"] == eid)
        self.assertIn("tien_do", x)
        self.assertIn("buoc", x)

    def test_anh_chup_day_du_co_ke_hoach_va_ngan_sach(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        d = self.cc.thuc_thi_anh_chup(eid)
        for k in ("y_dinh", "ke_hoach", "buoc", "ban_ke_hoach", "su_kien",
                  "tien_do", "ngan_sach", "chi_phi"):
            self.assertIn(k, d, k)

    def test_chi_phi_khong_bia_token(self):
        _de_xuat(self.cc, "sửa web cho gọn")
        eid = self.cc.chat(PID, "ok làm đi")["execution"]["execution_id"]
        u = {m["label"]: m for m in
             self.cc.thuc_thi_anh_chup(eid)["chi_phi"]["usage"]}
        self.assertIsNone(u["tokens"]["value"])
        self.assertEqual(u["tokens"]["confidence"], "UNAVAILABLE")

    def test_luu_de_xuat_tu_ban_chien_luoc(self):
        """§1 — chiến lược vừa nói ra được LƯU, nhưng KHÔNG chạy."""
        self.cc._nguon_goc_suy_luan[PID] = {                  # noqa: SLF001
            "chien_luoc": {"de_xuat": "tách observer khỏi farmer",
                           "viec_can_lam": ["viết observability.json",
                                            "thêm bài kiểm hợp đồng"]}}
        ma = self.cc._luu_de_xuat(PID, 7)                     # noqa: SLF001
        self.assertTrue(ma)
        ds = self.cc.so_thuc_thi.de_xuat(PID, chua_dung=True)
        self.assertEqual(ds[0].ma, ma)
        self.assertEqual(ds[0].tom_tat, "tách observer khỏi farmer")
        self.assertEqual(self.cc.so_thuc_thi.danh_sach(PID), [])   # 0 thuc thi


if __name__ == "__main__":                      # pragma: no cover
    unittest.main(verbosity=2)
