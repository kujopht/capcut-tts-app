"""V0.7 — môi giới probe vận hành: CHỈ ĐỌC, có kiểu, không lối thoát shell.

Bộ kiểm này khoá lại đúng những thứ đã làm hỏng việc thật `fanfic.t2efd-1`
(2026-09-11, `tool_permission_denied`): worker phải nhận BẰNG CHỨNG, không
phải nhận quyền chạy lệnh.

Không bài nào trong tệp này chạm mạng: `TruyenGia` thay lớp vận chuyển và
GHI LẠI mọi lệnh, nên một lệnh đột biến lọt qua sẽ bị bài kiểm bắt tận nơi
thay vì bị bắt trên máy production.
"""
from __future__ import annotations

import unittest
from typing import List, Optional, Tuple

from scripts.control_center import probe_van_hanh as PV
from scripts.control_center.observability.model import TrangThai


CAU_HINH = {
    "type": "ssh_service",
    "id": "fanfic_farmer",
    "host": "10.0.0.9",
    "user": "ubuntu",
    "unit": "fanfic-farmer",
    "status_file": "/var/lib/fanfic-farmer/status.json",
    "disk_path": "/",
    "read_paths": ["/var/lib/fanfic-farmer", "/var/log/fanfic-prod-admin.log"],
    "rclone_config": "/var/lib/fanfic-farmer/rclone.conf",
}


class TruyenGia(PV.TruyenSsh):
    """Vận chuyển GIẢ — ghi lại lệnh, không mở kết nối nào."""

    def __init__(self, ra: str = "active", ma: int = 0, loi: str = ""):
        super().__init__(CAU_HINH)
        self.da_chay: List[str] = []
        self._ra, self._ma, self._loi = ra, ma, loi

    def san_sang(self) -> Tuple[bool, str]:
        return True, ""

    def chay(self, lenh: str) -> Tuple[Optional[int], str, str]:
        PV._kiem_chi_doc(lenh)          # luoi thu hai van phai chay
        self.da_chay.append(lenh)
        return self._ma, self._ra, self._loi


def moi_gioi(**kw) -> PV.MoiGioiProbe:
    t = kw.pop("truyen", None) or TruyenGia(**kw)
    return PV.MoiGioiProbe(CAU_HINH, truyen=t)


# ------------------------------------------------------- danh sách cho phép


class TestDanhSachOp(unittest.TestCase):

    def test_chi_co_dung_nhung_op_da_dang_ky(self):
        mg = moi_gioi()
        self.assertEqual(
            set(mg.ops()),
            {"systemd.is_active", "systemd.show", "systemd.journal_tail",
             "filesystem.stat", "filesystem.list_dir", "filesystem.read_text",
             "filesystem.disk_usage", "rclone.listremotes", "rclone.lsjson"})

    def test_KHONG_co_op_chay_lenh_tuy_y(self):
        mg = moi_gioi()
        for ten in ("command", "shell", "bash", "powershell", "exec", "run",
                    "sh", "cmd"):
            self.assertNotIn(ten, mg.ops())
            with self.assertRaises(PV.OpKhongHopLe):
                mg.chay(ten, lenh="ls")

    def test_op_la_bi_TU_CHOI_chu_khong_bi_bo_qua(self):
        mg = moi_gioi()
        with self.assertRaises(PV.OpKhongHopLe):
            mg.chay("systemd.restart", don_vi="fanfic-farmer")
        with self.assertRaises(PV.OpKhongHopLe):
            mg.chay("filesystem.delete", duong="/var/lib/fanfic-farmer")


# --------------------------------------------------------- không có shell --


class TestKhongCoLoiThoatShell(unittest.TestCase):

    def test_tiem_lenh_qua_THAM_SO_bi_chan(self):
        mg = moi_gioi()
        doc = [
            "fanfic-farmer; reboot",
            "fanfic-farmer && reboot",
            "fanfic-farmer | tee /x",
            "fanfic-farmer`id`",
            "$(id)",
            "fanfic-farmer\nreboot",
            "fanfic-farmer > /tmp/x",
        ]
        for xau in doc:
            with self.subTest(xau=xau):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("systemd.is_active", don_vi=xau)
        # Khong mot lenh nao duoc gui di.
        self.assertEqual(mg.truyen.da_chay, [])

    def test_tham_so_duong_dan_khong_nhan_metachar(self):
        mg = moi_gioi()
        for xau in ("/var/lib/fanfic-farmer/*", "/var/lib/fanfic-farmer/$x",
                    "/var/lib/fanfic-farmer/a;b", "/var/lib/fanfic-farmer/'a'"):
            with self.subTest(xau=xau):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("filesystem.stat", duong=xau)


class TestLuoiThuHaiChiDoc(unittest.TestCase):

    def test_dong_tu_dot_bien_bi_chan(self):
        cam = [
            "systemctl restart fanfic-farmer",
            "systemctl stop fanfic-farmer",
            "systemctl start fanfic-farmer",
            "systemctl enable fanfic-farmer",
            "rm /var/lib/fanfic-farmer/status.json",
            "mv /a /b",
            "chmod 777 /var/lib/fanfic-farmer",
            "chown root /var/lib/fanfic-farmer",
            "sudo cat /var/lib/fanfic-farmer/status.json",
            "apt-get install rclone",
            "pip install x",
            "rclone sync gdrive: /tmp",
            "rclone delete gdrive:x",
            "rclone purge gdrive:x",
            "kill 350714",
            "reboot",
            "git push origin main",
        ]
        for l in cam:
            with self.subTest(lenh=l):
                with self.assertRaises(PV.LenhBiCam):
                    PV._kiem_chi_doc(l)

    def test_noi_lenh_va_chuyen_huong_bi_chan(self):
        for l in ("ls /a; whoami", "ls /a && whoami", "ls /a || whoami",
                  "cat /a > /b", "cat /a >> /b", "echo `id`", "echo $(id)"):
            with self.subTest(lenh=l):
                with self.assertRaises(PV.LenhBiCam):
                    PV._kiem_chi_doc(l)

    def test_lenh_DOC_that_van_qua_duoc(self):
        for l in ("systemctl is-active fanfic-farmer",
                  "systemctl show fanfic-farmer --property=MainPID --no-pager",
                  "stat -c %n:size=%s /var/lib/fanfic-farmer/status.json",
                  "df -Pk / | tail -n 1",
                  "ls -1t /var/lib/fanfic-farmer | head -n 20",
                  "rclone --config /var/lib/fanfic-farmer/rclone.conf listremotes"):
            with self.subTest(lenh=l):
                self.assertEqual(PV._kiem_chi_doc(l), l)

    def test_moi_lenh_THAT_su_gui_di_deu_chi_doc(self):
        mg = moi_gioi()
        mg.chay("systemd.is_active", don_vi="fanfic-farmer")
        mg.chay("systemd.show", don_vi="fanfic-farmer")
        mg.chay("systemd.journal_tail", don_vi="fanfic-farmer", loc="archive")
        mg.chay("filesystem.stat", duong="/var/lib/fanfic-farmer/status.json")
        mg.chay("filesystem.list_dir", duong="/var/lib/fanfic-farmer")
        mg.chay("filesystem.disk_usage", duong="/")
        mg.chay("rclone.listremotes")
        self.assertEqual(len(mg.truyen.da_chay), 7)
        for l in mg.truyen.da_chay:
            PV._kiem_chi_doc(l)                       # khong duoc nem


# --------------------------------------------------- kiểm tham số theo cấu hình


class TestThamSoTheoCauHinh(unittest.TestCase):

    def test_service_phai_nam_trong_cau_hinh(self):
        mg = moi_gioi()
        mg.chay("systemd.is_active", don_vi="fanfic-farmer")   # OK
        for u in ("sshd", "nginx", "fanfic-worker-prod", "fanfic-farmer2"):
            with self.subTest(unit=u):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("systemd.is_active", don_vi=u)

    def test_duong_dan_phai_nam_duoi_goc_da_khai(self):
        mg = moi_gioi()
        mg.chay("filesystem.stat", duong="/var/lib/fanfic-farmer/work")
        for d in ("/etc/shadow", "/root/.ssh/id_rsa", "/etc/fanfic-audio/farmer.env",
                  "/home/ubuntu"):
            with self.subTest(duong=d):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("filesystem.stat", duong=d)

    def test_TIEN_TO_gan_giong_KHONG_lot(self):
        # So theo DOAN, khong theo tien to: `/var/lib/fanfic-farmer-evil`
        # khong duoc coi la nam trong `/var/lib/fanfic-farmer`.
        mg = moi_gioi()
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("filesystem.stat", duong="/var/lib/fanfic-farmer-evil/x")

    def test_di_len_thu_muc_cha_bi_chan(self):
        mg = moi_gioi()
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("filesystem.stat",
                    duong="/var/lib/fanfic-farmer/../../etc/shadow")

    def test_thuoc_tinh_systemd_theo_bang_va_KHONG_co_Environment(self):
        mg = moi_gioi()
        self.assertNotIn("Environment", PV.THUOC_TINH_CHO_PHEP)
        mg.chay("systemd.show", don_vi="fanfic-farmer", thuoc_tinh=["MainPID"])
        for tt in ("Environment", "EnvironmentFiles", "ExecStart"):
            with self.subTest(tt=tt):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("systemd.show", don_vi="fanfic-farmer",
                            thuoc_tinh=[tt])

    def test_loc_nhat_ky_chi_nhan_TEN_co_san_khong_nhan_regex(self):
        mg = moi_gioi()
        mg.chay("systemd.journal_tail", don_vi="fanfic-farmer", loc="loi")
        for l in (".*", "a|b", "(?i)x", "unknown_filter"):
            with self.subTest(loc=l):
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("systemd.journal_tail", don_vi="fanfic-farmer",
                            loc=l)

    def test_so_luong_bi_chan_khoang(self):
        mg = moi_gioi()
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("systemd.journal_tail", don_vi="fanfic-farmer",
                    so_luong=100000)
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("systemd.journal_tail", don_vi="fanfic-farmer",
                    khoang_so=0)

    def test_mau_lenh_journal_dat_MAU_LOC_trong_nhay_don(self):
        # Neu khong co nhay don, shell hieu `|` thanh ONG DAN va `grep -iE
        # error|fail` se chay `fail` nhu mot lenh rieng.
        mg = moi_gioi()
        mg.chay("systemd.journal_tail", don_vi="fanfic-farmer", loc="loi")
        lenh = mg.truyen.da_chay[-1]
        self.assertIn("grep -iE '", lenh)
        self.assertIn("'", lenh.split("grep -iE ")[1][:2])


class TestRcloneChiDoc(unittest.TestCase):

    def test_chi_co_thao_tac_DOC(self):
        mg = moi_gioi()
        for op in mg.ops():
            if op.startswith("rclone."):
                self.assertIn(op.split(".", 1)[1], ("listremotes", "lsjson"))

    def test_lsjson_dung_config_da_khai_va_khong_lo_noi_dung(self):
        mg = moi_gioi(ra="[]")
        mg.chay("rclone.lsjson", remote="gdrive", duong_remote="FanficWorld/production")
        lenh = mg.truyen.da_chay[-1]
        self.assertIn("--config /var/lib/fanfic-farmer/rclone.conf", lenh)
        self.assertIn("lsjson", lenh)
        for xau in ("copy", "sync", "move", "delete", "purge"):
            self.assertNotIn(f" {xau} ", lenh)

    def test_chua_khai_config_thi_bao_ro_chu_khong_doan(self):
        mg = PV.MoiGioiProbe({k: v for k, v in CAU_HINH.items()
                              if k != "rclone_config"}, truyen=TruyenGia())
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("rclone.listremotes")
        self.assertIn("rclone", mg.kha_dung()["khong_kha_dung"])


# ------------------------------------------------------ provider không có --


class TestKhongKhaDung(unittest.TestCase):

    def test_du_an_khong_khai_probe_thi_UNAVAILABLE_co_ly_do(self):
        mg = PV.MoiGioiProbe(None)
        r = mg.chay("systemd.is_active", don_vi="x") if False else None
        kd = mg.kha_dung()
        self.assertFalse(kd["san_sang"])
        self.assertTrue(kd["ly_do"])

    def test_UNAVAILABLE_khong_bao_gio_mang_gia_tri(self):
        with self.assertRaises(ValueError):
            PV.KetQuaProbe(op="x", dich="y",
                           trang_thai=TrangThai.UNAVAILABLE,
                           gia_tri="123", ly_do="thiếu")

    def test_UNAVAILABLE_phai_co_ly_do(self):
        with self.assertRaises(ValueError):
            PV.KetQuaProbe(op="x", dich="y", trang_thai=TrangThai.UNAVAILABLE)

    def test_may_xa_khong_noi_duoc_thi_UNKNOWN_chu_khong_phai_DOWN(self):
        class TruyenChet(TruyenGia):
            def chay(self, lenh):
                return None, "", "connect timeout"
        mg = moi_gioi(truyen=TruyenChet())
        r = mg.chay("systemd.is_active", don_vi="fanfic-farmer")
        self.assertIs(r.trang_thai, TrangThai.UNKNOWN)
        self.assertIsNone(r.gia_tri)
        self.assertIn("timeout", r.ly_do)


class TestLocBiMat(unittest.TestCase):

    def test_bang_chung_va_ly_do_deu_di_qua_redact(self):
        bi_mat = "AKIAIOSFODNN7EXAMPLE"
        mg = moi_gioi(ra=f"token={bi_mat} ok")
        r = mg.chay("systemd.is_active", don_vi="fanfic-farmer")
        self.assertNotIn(bi_mat, str(r.gia_tri))
        self.assertNotIn(bi_mat, r.bang_chung)

        class TruyenLoi(TruyenGia):
            def chay(self, lenh):
                return 1, "", f"failed with key {bi_mat}"
        mg2 = moi_gioi(truyen=TruyenLoi())
        r2 = mg2.chay("systemd.is_active", don_vi="fanfic-farmer")
        self.assertNotIn(bi_mat, r2.ly_do)


class TestNguonGoc(unittest.TestCase):

    def test_moi_ket_qua_mang_du_NGUON_GOC(self):
        mg = moi_gioi()
        r = mg.chay("systemd.is_active", don_vi="fanfic-farmer")
        d = r.to_dict()
        for k in ("op", "dich", "trang_thai", "nguon", "do_luc", "tuoi_giay",
                  "ly_do", "bang_chung", "ma_thoat"):
            self.assertIn(k, d)
        self.assertEqual(d["op"], "systemd.is_active")
        self.assertEqual(d["dich"], "fanfic-farmer")
        self.assertTrue(d["nguon"].startswith("ssh:"))

    def test_qua_han_thanh_STALE_chu_khong_phai_so_hien_tai(self):
        r = PV.KetQuaProbe(op="systemd.is_active", dich="u",
                           trang_thai=TrangThai.ACTIVE, gia_tri="active",
                           do_luc=0.0, han_tuoi=60.0)
        self.assertIs(r.hieu_luc(), TrangThai.STALE)

    def test_doi_duoc_sang_QuanSat_cua_V05(self):
        mg = moi_gioi()
        q = mg.chay("systemd.is_active", don_vi="fanfic-farmer").to_quan_sat()
        self.assertTrue(q.nguon.startswith("ssh:"))
        self.assertEqual(q.nhan, "systemd.is_active")


# ---------------------------------------------------------- phân loại A–F --


class TestPhanLoai(unittest.TestCase):

    def test_du_SAU_phan_loai(self):
        self.assertEqual(set(PV.PHAN_LOAI), set("ABCDEF"))

    def test_khong_co_probe_thi_F_chu_khong_doan(self):
        bc = PV.kiem_duong_ong(PV.MoiGioiProbe(None))
        self.assertEqual(bc.phan_loai, "F")
        self.assertTrue(bc.thieu)

    def test_thieu_bang_chung_archive_thi_F_va_NOI_RO_thieu_gi(self):
        mg = moi_gioi(ra="active")
        bc = PV.kiem_duong_ong(mg)
        self.assertEqual(bc.phan_loai, "F")
        self.assertTrue(any("status.json" in x for x in bc.thieu))
        self.assertTrue(any("Appwrite" in x for x in bc.thieu))

    def test_service_khong_active_thi_D_co_can_cu(self):
        mg = moi_gioi(ra="failed")
        bc = PV.kiem_duong_ong(mg)
        self.assertEqual(bc.phan_loai, "D")
        self.assertIn("failed", bc.ly_do)

    def test_bao_cao_render_khong_lo_bi_mat_va_co_nguon(self):
        mg = moi_gioi(ra="active")
        van = PV.kiem_duong_ong(mg).render()
        self.assertIn("KIỂM TOÁN ĐƯỜNG ỐNG", van)
        self.assertIn("ssh:", van)


# ------------------------------------- worker headless nhận BẰNG CHỨNG -----


class TestGoiBangChungChoWorker(unittest.TestCase):

    def test_goi_bang_chung_CAM_worker_chay_lenh(self):
        mg = moi_gioi(ra="active")
        van = PV.goi_bang_chung(PV.kiem_duong_ong(mg))
        self.assertIn(PV.DAU_PROBE, van)
        self.assertIn("KHÔNG chạy lệnh", van)
        self.assertIn("`command`", van)

    def test_goi_bang_chung_co_JSON_nguon_goc_va_bi_chan_do_dai(self):
        import json
        mg = moi_gioi(ra="active")
        van = PV.goi_bang_chung(PV.kiem_duong_ong(mg), tran_ky_tu=800)
        self.assertIn("JSON", van)
        self.assertLess(len(van), 12000)
        # Phan JSON phai la JSON that o dau chuoi.
        tho = van.split("JSON (nguồn gốc đầy đủ):\n", 1)[1]
        self.assertTrue(tho.lstrip().startswith("{"))
        json.JSONDecoder().raw_decode(tho.lstrip())


class TestPhatHienCauHoiVanHanh(unittest.TestCase):

    def test_cau_hoi_CHAN_DOAN_production_duoc_nhan(self):
        from scripts.control_center import leader as LD
        that = [
            "Kiểm tra READ-ONLY vì sao từ hôm qua tới giờ tôi không thấy "
            "production artifact mới được mirror lên Google Drive.",
            "tại sao Drive 24h chưa có file mới?",
            "điều tra vì sao farmer không tạo artifact nào",
        ]
        for c in that:
            with self.subTest(cau=c):
                vh, chan, dau = LD.la_cau_hoi_van_hanh(c)
                self.assertTrue(vh, dau)
                self.assertTrue(chan, dau)

    def test_cau_hoi_TRANG_THAI_DON_khong_bi_coi_la_chan_doan(self):
        from scripts.control_center import leader as LD
        vh, chan, _ = LD.la_cau_hoi_van_hanh("production farmer đang chạy không?")
        self.assertTrue(vh)
        self.assertFalse(chan, "câu trạng thái đơn không nên gom 11 probe")

    def test_cau_khong_lien_quan_thi_KHONG_bat(self):
        from scripts.control_center import leader as LD
        for c in ("sửa docs", "ê bro", "viết test cho text_chunker"):
            with self.subTest(cau=c):
                vh, chan, _ = LD.la_cau_hoi_van_hanh(c)
                self.assertFalse(vh)
                self.assertFalse(chan)


class TestWorkerNhanBangChung(unittest.TestCase):
    """§9 — worker headless nhận BẰNG CHỨNG, không nhận quyền `command`."""

    def test_kem_probe_vao_hop_dong_va_CAM_chay_lenh(self):
        from scripts.control_center.engine import ControlCenter
        mg = moi_gioi(ra="active")
        khoi = PV.goi_bang_chung(PV.kiem_duong_ong(mg))
        hd = {"objective": "Điều tra vì sao Drive chưa có artifact mới."}
        ok = ControlCenter._kem_probe_vao_hd(None, khoi, hd)
        self.assertTrue(ok)
        self.assertIn(PV.DAU_PROBE, hd["objective"])
        self.assertIn("KHÔNG chạy lệnh", hd["objective"])
        # Muc tieu goc phai con nguyen.
        self.assertIn("Điều tra vì sao Drive", hd["objective"])

    def test_khong_co_bang_chung_thi_khong_sua_hop_dong(self):
        from scripts.control_center.engine import ControlCenter
        hd = {"objective": "x"}
        self.assertFalse(ControlCenter._kem_probe_vao_hd(None, "", hd))
        self.assertEqual(hd["objective"], "x")

    def test_hop_dong_KHONG_xin_quyen_command(self):
        mg = moi_gioi(ra="active")
        khoi = PV.goi_bang_chung(PV.kiem_duong_ong(mg))
        for xau in ("permissions.allow", "dangerously-skip-permissions",
                    "command(", "allow-rule"):
            self.assertNotIn(xau, khoi)


class TestTranhCodexKhiHinhDangBaoMat(unittest.TestCase):
    """Việc mang hình dạng bảo mật KHÔNG được xếp vào Codex.

    Đo được ở nghiệm thu probe: `fanfic.t78ce-1` bị Codex từ chối
    (`codex_security_shaped_refusal`) rồi CHẾT ở `BLOCKED`, vì lý do đó nằm
    trong `KHONG_THU_LAI`. Nặng hơn: lời nhắc công cụ tiêu chuẩn của MỌI
    việc đều chứa chữ "quyền", nên gần như mọi việc xếp vào Codex đều chết.
    """

    class _Fab:
        class _R:
            def __init__(self, rid, prov):
                self.runtime_id, self.provider = rid, prov

        def __init__(self):
            self.runtimes = {
                "AG01": self._R("AG01", "antigravity"),
                "CODEX01": self._R("CODEX01", "codex"),
                "OPENCODE01": self._R("OPENCODE01", "opencode"),
            }

    class _Ctx:
        def __init__(self, fab):
            class _S:
                pass
            self.sessions = _S()
            self.sessions.fabric = fab

    def _goi(self, hd):
        from scripts.control_center.engine import ControlCenter
        return ControlCenter._runtime_codex_neu_hinh_dang_bao_mat(
            None, self._Ctx(self._Fab()), hd)

    def test_loi_nhac_cong_cu_TIEU_CHUAN_da_mang_hinh_dang_bao_mat(self):
        from scripts.router_v3.pool.adapters import _HINH_DANG_BAO_MAT
        mau = "quyền được khớp theo chuỗi chính xác"
        self.assertTrue([k for k in _HINH_DANG_BAO_MAT if k in mau])

    def test_hop_dong_bao_mat_thi_TRANH_codex(self):
        self.assertEqual(self._goi({"objective": "kiểm tra quyền của worker"}),
                         ("CODEX01",))
        self.assertEqual(self._goi({"objective": "rclone permission denied"}),
                         ("CODEX01",))

    def test_hop_dong_thuong_thi_KHONG_tranh_gi(self):
        self.assertEqual(self._goi({"objective": "đổi màu nút Lưu"}), ())

    def test_hong_o_dau_cung_KHONG_lam_vo_luot(self):
        from scripts.control_center.engine import ControlCenter
        self.assertEqual(
            ControlCenter._runtime_codex_neu_hinh_dang_bao_mat(
                None, object(), {"objective": "quyền"}), ())


class TestKhongDotBienProduction(unittest.TestCase):
    """§9/§12 — số lần đột biến production phải bằng 0, chứng minh bằng lệnh."""

    def test_kiem_toan_duong_ong_chi_gui_lenh_DOC(self):
        mg = moi_gioi(ra="active")
        PV.kiem_duong_ong(mg)
        self.assertTrue(mg.truyen.da_chay)
        for lenh in mg.truyen.da_chay:
            with self.subTest(lenh=lenh):
                PV._kiem_chi_doc(lenh)                # khong duoc nem
                self.assertFalse(lenh.strip().startswith("sudo "))

    def test_KHONG_bao_gio_dung_sudo(self):
        mg = moi_gioi(ra="active")
        PV.kiem_duong_ong(mg)
        for lenh in mg.truyen.da_chay:
            self.assertNotIn("sudo", lenh)

    def test_moi_op_trong_bang_deu_sinh_lenh_chi_doc(self):
        mg = moi_gioi(ra="active")
        goi = {
            "systemd.is_active": {"don_vi": "fanfic-farmer"},
            "systemd.show": {"don_vi": "fanfic-farmer"},
            "systemd.journal_tail": {"don_vi": "fanfic-farmer"},
            "filesystem.stat": {"duong": "/var/lib/fanfic-farmer"},
            "filesystem.list_dir": {"duong": "/var/lib/fanfic-farmer"},
            "filesystem.read_text": {"duong": "/var/log/fanfic-prod-admin.log"},
            "filesystem.disk_usage": {"duong": "/"},
            "rclone.listremotes": {},
            "rclone.lsjson": {"remote": "gdrive"},
        }
        self.assertEqual(set(goi), set(mg.ops()), "có op mới chưa được kiểm")
        for op, kw in goi.items():
            with self.subTest(op=op):
                lenh, _dich = mg._bang()[op].dung(mg, dict(kw))
                PV._kiem_chi_doc(lenh)


if __name__ == "__main__":
    unittest.main()
