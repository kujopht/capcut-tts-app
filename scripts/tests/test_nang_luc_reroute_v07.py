"""V0.7 — năng lực runtime + định tuyến lại khi chỗ chạy TỪ CHỐI.

Khuyết tật gốc (`fanfic.t78ce-1`): adapter Codex quét một danh sách TỪ ĐƠN
trên cả gói việc đã render, và trong danh sách có chữ **"quyền"** — thứ nằm
sẵn trong lời nhắc công cụ TIÊU CHUẨN của mọi việc. Nên mọi việc xếp vào
Codex đều bị từ chối, rồi chết ở `BLOCKED` vì lý do đó nằm trong
`KHONG_THU_LAI`.

Bộ kiểm này khoá lại cả ba tầng: phân loại (cụm từ, chỉ phần người viết),
xếp chỗ (rào CỨNG theo năng lực khai báo), và định tuyến lại (có trần, có
nguồn gốc, nhả tài nguyên).
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.control_center import nang_luc as NL
from scripts.control_center.duong_du_lieu import dam_bao_kho
from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Task, TaskState
from scripts.router_v3 import policy as POL

#: Lời nhắc công cụ TIÊU CHUẨN — nguyên văn phần sinh ra dương tính giả.
PREAMBLE = (
    "\n\nLoại việc: analysis.\n\n"
    "CÔNG CỤ: môi trường này chỉ cho chạy ĐÚNG những lệnh dưới đây, từng ký "
    "tự. Mọi lệnh khác bị từ chối LẶNG LẼ và cả lượt của bạn mất trắng — "
    "quyền được khớp theo chuỗi chính xác, không có tiền tố, không có ký tự "
    "đại diện.\n"
    "\nPERMISSION_ENVELOPE (phong bì quyền của việc này):\n"
    "  ĐƯỢC TỰ LÀM, không phải hỏi:\n    - repo_read\n"
    "  TUYỆT ĐỐI KHÔNG tự làm:\n    - secret_rotation\n    - secret_disclosure\n"
)


def hd(title: str, objective: str, **kw) -> dict:
    d = {"title": title, "objective": objective + PREAMBLE}
    d.update(kw)
    return d


# ------------------------------------------------- 1. dương tính giả -------


class TestKhongConDuongTinhGia(unittest.TestCase):
    """§C.1 — việc thường có chữ "quyền" KHÔNG được thành việc bảo mật."""

    VIEC_THUONG = [
        ("Sửa nút Lưu", "Đổi màu nút Lưu cho khớp chủ đề tối."),
        ("Viết test", "Viết test cho text_chunker."),
        ("Điều tra Drive", "Điều tra vì sao Drive chưa có artifact mới."),
        ("Dọn nợ kỹ thuật", "Bỏ hàm trùng trong output_manager."),
        ("Cập nhật tài liệu", "Cập nhật HANDOFF cho mốc mới."),
        ("Sửa lỗi phân trang", "Trang 2 của danh sách truyện bị trống."),
    ]

    def test_chu_quyen_trong_loi_nhac_KHONG_lam_viec_thanh_bao_mat(self):
        for ten, mt in self.VIEC_THUONG:
            with self.subTest(viec=ten):
                self.assertIn("quyền", hd(ten, mt)["objective"],
                              "lời nhắc phải thật sự chứa chữ 'quyền'")
                self.assertEqual(NL.nang_luc_viec(hd(ten, mt)), frozenset())

    def test_viec_bao_mat_THAT_van_duoc_nhan_ra(self):
        that = [
            ("Rà soát bảo mật", "Rà soát bảo mật cho luồng đăng nhập."),
            ("Security review", "Security review of the upload endpoint."),
            ("Xoay khoá", "Luân chuyển khoá API của Appwrite."),
            ("Lỗ hổng", "Kiểm tra lỗ hổng XSS ở trang truyện."),
            ("Phân quyền", "Thiết kế lại phân quyền cho admin."),
            ("Credential", "Move the api_key out of the client bundle."),
        ]
        for ten, mt in that:
            with self.subTest(viec=ten):
                self.assertEqual(NL.nang_luc_viec(hd(ten, mt)),
                                 frozenset({NL.SECURITY_REVIEW}))

    def test_phan_loai_chi_doc_PHAN_NGUOI_VIET(self):
        # Cum tu bao mat nam trong phan BOILERPLATE thi khong tinh: no do
        # Router gan, khong phai nguoi viet.
        d = {"title": "Sửa nút",
             "objective": "Đổi màu nút Lưu." + PREAMBLE +
                          "\n\nBẰNG CHỨNG VẬN HÀNH DO ROUTER ĐO\n"
                          "rà soát bảo mật credential api_key"}
        self.assertEqual(NL.nang_luc_viec(d), frozenset())

    def test_khai_bao_tuong_minh_THANG_moi_phep_doan(self):
        d = hd("Sửa nút", "Đổi màu nút Lưu.")
        d["required_capabilities"] = ["security_review"]
        self.assertEqual(NL.nang_luc_viec(d),
                         frozenset({NL.SECURITY_REVIEW}))

    def test_MOT_nguon_tu_vung_duy_nhat(self):
        # Hai danh sach song song la cach dung de chung lech nhau tro lai.
        self.assertTrue(POL.la_hinh_dang_bao_mat("rà soát bảo mật"))
        self.assertFalse(POL.la_hinh_dang_bao_mat(
            "quyền được khớp theo chuỗi chính xác"))

    def test_tu_don_chung_chung_KHONG_con_la_dau_hieu(self):
        for xau in ("quyền", "auth", "token", "permission", "secret",
                    "xác thực"):
            with self.subTest(tu=xau):
                self.assertFalse(POL.la_hinh_dang_bao_mat(
                    f"Sửa chỗ {xau} bị lệch một dòng."))


# ----------------------------------------- 2. runtime không tương thích ----


class _R:
    def __init__(self, rid, prov):
        self.runtime_id, self.provider = rid, prov


class _Fab:
    def __init__(self):
        self.runtimes = {"AG01": _R("AG01", "antigravity"),
                         "AG02": _R("AG02", "antigravity"),
                         "CODEX01": _R("CODEX01", "codex"),
                         "OPENCODE01": _R("OPENCODE01", "opencode")}


CFG = {"security": {"security_refusal_family": "codex"},
       "runtimes": [{"runtime_id": "OPENCODE01", "refuses": []}]}


class TestLoaiTruRuntime(unittest.TestCase):
    """§C.2 — chỗ chạy đã khai TỪ CHỐI thì không được nhận việc."""

    def test_runtime_khai_tu_choi_bi_loai(self):
        cam = NL.runtime_khong_tuong_thich(_Fab(), {NL.SECURITY_REVIEW}, CFG)
        self.assertEqual(cam, ("CODEX01",))

    def test_viec_thuong_KHONG_loai_tru_ai(self):
        self.assertEqual(NL.runtime_khong_tuong_thich(_Fab(), set(), CFG), ())

    def test_khai_bao_lay_tu_fabric_KHONG_hardcode(self):
        # Doi ho tu choi -> ket qua doi theo. Neu ai do hardcode "codex"
        # trong ma, bai nay do duoc.
        cfg2 = {"security": {"security_refusal_family": "opencode"}}
        self.assertEqual(
            NL.runtime_khong_tuong_thich(_Fab(), {NL.SECURITY_REVIEW}, cfg2),
            ("OPENCODE01",))

    def test_khai_rieng_tung_runtime_cong_them(self):
        cfg3 = {"security": {"security_refusal_family": "codex"},
                "runtimes": [{"runtime_id": "AG02",
                              "refuses": ["security_review"]}]}
        self.assertEqual(
            NL.runtime_khong_tuong_thich(_Fab(), {NL.SECURITY_REVIEW}, cfg3),
            ("AG02", "CODEX01"))

    def test_nang_luc_LA_trong_khai_bao_bi_bo_qua(self):
        cfg4 = {"runtimes": [{"runtime_id": "AG01", "refuses": ["bay_len_troi"]}]}
        self.assertEqual(
            NL.runtime_khong_tuong_thich(_Fab(), {"bay_len_troi"}, cfg4), ())


# --------------------------------------------------- 3-6. định tuyến lại ---


class _Nen(unittest.TestCase):
    def setUp(self):
        self.tam = Path(tempfile.mkdtemp(prefix="cc-reroute-"))
        self.goc = self.tam / "kho"
        dam_bao_kho(self.goc)
        self.cc = ControlCenter(root=self.goc, probe=False, leader_bat=False)
        self.cc.store.luu_project_row(
            project_id="p1", name="P1", repo_path=str(self.tam)) \
            if hasattr(self.cc.store, "luu_project_row") else None

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.tam, ignore_errors=True)

    def _viec(self, **kw) -> Task:
        t = Task(task_id="p1.t1", project_id="p1", title="Rà soát bảo mật",
                 objective="Rà soát bảo mật luồng đăng nhập." + PREAMBLE,
                 state=TaskState.RUNNING, **kw)
        self.cc.store.luu_task(t)
        return t


class _CtxGia:
    class _S:
        def __init__(self):
            self.da_dung = []

        def dung(self, sid, state=None, reason=""):
            self.da_dung.append((sid, reason))

    def __init__(self):
        self.sessions = self._S()


class TestDinhTuyenLai(_Nen):

    def test_dinh_tuyen_lai_THANH_CONG_va_giu_nguon_goc(self):
        """§C.3 — từ chối vì chính sách thì xếp lại chỗ khác."""
        t = self._viec(owner_session="s-1")
        ctx = _CtxGia()
        ok = self.cc._dinh_tuyen_lai(ctx, t, "codex_security_shaped_refusal",
                                     "CODEX01")
        self.assertTrue(ok)
        ls = t.contract["_dinh_tuyen_lai"]
        self.assertEqual(len(ls), 1)
        self.assertEqual(ls[0]["tu_runtime"], "CODEX01")
        self.assertEqual(ls[0]["ly_do"], "codex_security_shaped_refusal")
        self.assertEqual(ls[0]["lan"], 1)
        self.assertEqual(t.contract["_cam_runtime"], ["CODEX01"])

    def test_nha_PHIEN_va_ve_hang_doi(self):
        """§C.6 — tài nguyên/phiên phải được nhả khi định tuyến lại."""
        t = self._viec(owner_session="s-1")
        ctx = _CtxGia()
        self.cc._dinh_tuyen_lai(ctx, t, "codex_security_shaped_refusal",
                                "CODEX01")
        self.assertEqual(len(ctx.sessions.da_dung), 1)
        self.assertEqual(ctx.sessions.da_dung[0][0], "s-1")
        self.assertEqual(t.owner_session, "")
        lai = self.cc.store.task("p1.t1")
        self.assertIs(lai.state, TaskState.QUEUED)

    def test_KHONG_dinh_tuyen_lai_vo_han(self):
        """§C.4 — có trần, và trần được tôn trọng."""
        t = self._viec(owner_session="s-1")
        ctx = _CtxGia()
        for i in range(self.cc.MAX_DINH_TUYEN_LAI):
            self.assertTrue(
                self.cc._dinh_tuyen_lai(ctx, t,
                                        "codex_security_shaped_refusal",
                                        f"R{i}"),
                f"lần {i + 1} phải được phép")
        self.assertFalse(
            self.cc._dinh_tuyen_lai(ctx, t, "codex_security_shaped_refusal",
                                    "R9"),
            "vượt trần thì phải DỪNG")
        self.assertEqual(len(t.contract["_dinh_tuyen_lai"]),
                         self.cc.MAX_DINH_TUYEN_LAI)

    def test_cho_da_tu_choi_thi_bi_CAM_o_luot_sau(self):
        t = self._viec(owner_session="s-1")
        self.cc._dinh_tuyen_lai(_CtxGia(), t,
                                "codex_security_shaped_refusal", "CODEX01")
        self.assertEqual(self.cc._cam_runtime_da_tu_choi(t.contract),
                         ("CODEX01",))

    def test_HONG_THAT_khong_bi_dinh_tuyen_lai(self):
        """§C.5 — lỗi thật của việc/ứng dụng KHÔNG phải chuyện đổi chỗ."""
        for ly_do in ("tool_permission_denied", "security_gate",
                      "requires_decision", "project_repo_invalid",
                      "test_failed", "executor_error"):
            with self.subTest(ly_do=ly_do):
                self.assertNotIn(ly_do, self.cc.LY_DO_DINH_TUYEN_LAI)

    def test_chi_ly_do_CHINH_SACH_moi_duoc_dinh_tuyen_lai(self):
        self.assertEqual(self.cc.LY_DO_DINH_TUYEN_LAI,
                         frozenset({"codex_security_shaped_refusal"}))


# --------------------------------------------------- 7-9. an toàn ----------


class TestAnToan(unittest.TestCase):

    def test_telemetry_KHONG_chua_bi_mat(self):
        """§C.7 — đầu ra quan sát không mang bí mật."""
        from scripts.control_center import probe_van_hanh as PV
        d = {"schema_version": 1,
             "archive": {"remote_alias": "gdrive",
                         "last_error_class": "ya29.token_that",
                         "oauth_token": "ya29.secret"},
             "lanes": {"A": {"produced": 1,
                             "errors": ["AKIAIOSFODNN7EXAMPLE"]}}}
        sach, bo = PV.loc_telemetry(d)
        import json
        tho = json.dumps(sach, ensure_ascii=False)
        self.assertNotIn("ya29.secret", tho)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", tho)
        self.assertEqual(sach["archive"]["last_error_class"], "unknown")

    def test_rclone_conf_VAN_rieng_tu_trong_cau_hinh(self):
        """§C.8 — không có gì trong cấu hình đòi nới quyền rclone.conf."""
        import json
        from pathlib import Path as _P
        cfg = json.loads(_P("scripts/control_center/config/observability.json")
                         .read_text(encoding="utf-8"))
        fan = cfg["projects"]["fanfic"]["providers"]
        ssh = [p for p in fan if p.get("type") == "ssh_service"][0]
        # rclone.conf duoc KHAI de Router BIET no o dau, nhung no khong nam
        # trong `read_paths` — tuc la khong op nao doc noi dung no.
        self.assertNotIn("/var/lib/fanfic-farmer/rclone.conf",
                         ssh.get("read_paths") or [])
        self.assertEqual(ssh.get("rclone_config"),
                         "/var/lib/fanfic-farmer/rclone.conf")

    def test_probe_KHONG_co_thao_tac_doc_noi_dung_rclone_conf(self):
        from scripts.control_center import probe_van_hanh as PV
        mg = PV.tu_du_an("fanfic")
        # `filesystem.read_text` chi nhan duong duoi `read_paths`, va
        # rclone.conf khong nam trong do.
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("filesystem.read_text",
                    duong="/var/lib/fanfic-farmer/rclone.conf")


if __name__ == "__main__":
    unittest.main()
