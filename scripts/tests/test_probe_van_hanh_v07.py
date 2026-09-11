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
    "telemetry_file": "/var/lib/fanfic-farmer/observability.json",
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
             "filesystem.disk_usage", "rclone.listremotes", "rclone.lsjson",
             "telemetry.snapshot"})

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


class TestDanhSachCamTepBiMat(unittest.TestCase):
    """Danh sách CẤM thắng danh sách cho phép.

    `read_paths` khai theo THƯ MỤC, nên một tệp bí mật nằm trong đó vẫn lọt
    nếu chỉ dựa vào allowlist. Hôm nay hệ điều hành chặn (`rclone.conf` là
    `600`), nhưng để quyền của máy chủ làm rào DUY NHẤT là sai.
    """

    def test_rclone_conf_KHONG_doc_duoc_du_nam_trong_goc_da_khai(self):
        mg = moi_gioi()
        # Khang dinh tien de: no THAT SU nam duoi mot goc da khai.
        self.assertTrue(
            PV._duoi_goc("/var/lib/fanfic-farmer/rclone.conf",
                         "/var/lib/fanfic-farmer"))
        with self.assertRaises(PV.ThamSoKhongHopLe):
            mg.chay("filesystem.read_text",
                    duong="/var/lib/fanfic-farmer/rclone.conf")
        self.assertEqual(mg.truyen.da_chay, [])

    def test_cac_dang_tep_bi_mat_khac_cung_bi_chan(self):
        mg = moi_gioi()
        for ten in ("rclone.conf", "worker-prod.env", ".env", "farmer.pem",
                    "id_rsa", "credentials.json", "token_cache.json",
                    "service_account.json", ".netrc"):
            with self.subTest(ten=ten):
                self.assertTrue(PV.la_tep_bi_mat(ten))
                with self.assertRaises(PV.ThamSoKhongHopLe):
                    mg.chay("filesystem.read_text",
                            duong=f"/var/lib/fanfic-farmer/{ten}")

    def test_tep_thuong_van_doc_duoc(self):
        mg = moi_gioi()
        for ten in ("status.json", "farmer.log", "observability.json",
                    "notes.txt"):
            with self.subTest(ten=ten):
                self.assertFalse(PV.la_tep_bi_mat(ten))
        mg.chay("filesystem.read_text",
                duong="/var/log/fanfic-prod-admin.log")
        self.assertEqual(len(mg.truyen.da_chay), 1)

    def test_SIEU_DU_LIEU_van_lay_duoc_cho_tep_bi_mat(self):
        # `stat` chi doc sieu du lieu, khong doc noi dung — va no la thu tra
        # loi "tep con duoc ghi khong". Khong duoc chan nham.
        mg = moi_gioi()
        mg.chay("filesystem.stat", duong="/var/lib/fanfic-farmer/rclone.conf")
        self.assertIn("stat -c", mg.truyen.da_chay[-1])


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


class TestAnhChupDaLoc(unittest.TestCase):
    """Ảnh chụp quan sát: danh sách CHO PHÉP, không phải danh sách cấm."""

    DAY_DU = {
        "schema_version": 1, "generated_at": "2026-09-11T10:00:00Z",
        "farmer": {"started_at": "x", "updated_at": "y", "healthy": True,
                   "unhealthy_reason": ""},
        "round": {"number": 42, "started_at": "z", "seconds": 12.5},
        "lanes": {"A": {"discovered": 3, "produced": 1, "archived": 1,
                        "archive_pending": 0, "error_count": 0,
                        "last_error_class": ""}},
        "totals": {"produced": 100},
        "quotas": {"daily": 50},
        "archive": {"remote_alias": "gdrive",
                    "root": "gdrive:FanficWorld/production",
                    "enabled": True, "rclone_installed": True,
                    "reachable": True, "status": "ARCHIVE_DONE",
                    "last_error_class": "", "last_attempt_at": "t",
                    "last_success_at": "t", "done": 10, "pending": 0,
                    "failed": 0},
        "integrity": {"ok": True},
    }

    def test_khoa_LA_bi_bo_chu_khong_di_tiep(self):
        d = dict(self.DAY_DU)
        d["rclone_conf"] = "[gdrive]\ntoken = {\"access_token\":\"ya29.secret\"}"
        d["archive"] = dict(d["archive"], authorization="Bearer abc123")
        sach, bo = PV.loc_telemetry(d)
        self.assertNotIn("rclone_conf", sach)
        self.assertNotIn("authorization", sach["archive"])
        self.assertIn("rclone_conf", bo)
        import json as _j
        tho = _j.dumps(sach, ensure_ascii=False)
        self.assertNotIn("ya29.secret", tho)
        self.assertNotIn("Bearer abc123", tho)

    def test_lop_loi_LA_thanh_unknown_chu_khong_truyen_nguyen_van(self):
        d = dict(self.DAY_DU)
        d["archive"] = dict(d["archive"],
                            last_error_class="token=ya29.abcdefghijklmnop")
        sach, _ = PV.loc_telemetry(d)
        self.assertEqual(sach["archive"]["last_error_class"], "unknown")

    def test_truong_van_ban_tu_do_bi_LOC_va_CAT(self):
        d = dict(self.DAY_DU)
        d["farmer"] = dict(d["farmer"],
                           unhealthy_reason="key AKIAIOSFODNN7EXAMPLE " + "x" * 500)
        sach, _ = PV.loc_telemetry(d)
        vi = sach["farmer"]["unhealthy_reason"]
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", vi)
        self.assertLessEqual(len(vi), 200)

    def test_lane_chi_giu_SO_NGUYEN(self):
        d = dict(self.DAY_DU)
        d["lanes"] = {"A": {"discovered": 3, "errors": ["traceback: token=x"]}}
        sach, bo = PV.loc_telemetry(d)
        self.assertEqual(sach["lanes"]["A"], {"discovered": 3})
        self.assertIn("lanes.A.errors", bo)

    def test_anh_chup_MOI_HON_ma_thi_KHONG_doan_nghia(self):
        mg = moi_gioi(ra='{"schema_version": 99}')
        tm, r = PV.doc_telemetry(mg)
        self.assertEqual(tm, {})
        self.assertIs(r.trang_thai, TrangThai.UNKNOWN)
        self.assertIn("mới hơn", r.ly_do)

    def test_khong_phai_JSON_thi_UNKNOWN_co_ly_do(self):
        mg = moi_gioi(ra="khong phai json")
        tm, r = PV.doc_telemetry(mg)
        self.assertEqual(tm, {})
        self.assertIs(r.trang_thai, TrangThai.UNKNOWN)

    def test_chua_khai_telemetry_thi_UNAVAILABLE_noi_ro(self):
        mg = PV.MoiGioiProbe({k: v for k, v in CAU_HINH.items()
                              if k != "telemetry_file"}, truyen=TruyenGia())
        tm, r = PV.doc_telemetry(mg)
        self.assertEqual(tm, {})
        self.assertIs(r.trang_thai, TrangThai.UNAVAILABLE)
        self.assertIn("telemetry_file", r.ly_do)

    def test_doc_anh_chup_KHONG_cham_rclone_conf(self):
        mg = moi_gioi(ra="{}")
        PV.doc_telemetry(mg)
        for lenh in mg.truyen.da_chay:
            self.assertNotIn("rclone.conf", lenh)


class TestPhanLoaiTuAnhChup(unittest.TestCase):
    """A–E chỉ được khẳng định khi có BỘ ĐẾM chống lưng."""

    def _tm(self, **ar):
        goc = {"archive": {"enabled": True, "reachable": True,
                           "done": 0, "pending": 0, "failed": 0,
                           "last_error_class": "", "remote_alias": "gdrive"},
               "lanes": {"A": {"discovered": 0, "produced": 0,
                               "audio_attached": 0}}}
        goc["archive"].update(ar.pop("archive", {}))
        goc["lanes"]["A"].update(ar.pop("lanes", {}))
        return goc

    def test_C_khi_archive_hong_co_lop_loi(self):
        pl, vi = PV._phan_loai_tu_telemetry(
            self._tm(archive={"failed": 3, "last_error_class": "network"}))
        self.assertEqual(pl, "C")
        self.assertIn("network", vi)

    def test_C_khi_token_Drive_het_han(self):
        pl, vi = PV._phan_loai_tu_telemetry(
            self._tm(archive={"last_error_class": "auth_invalid_grant"}))
        self.assertEqual(pl, "C")
        self.assertIn("reconnect", vi)

    def test_B_khi_co_tac_pham_nhung_archive_dang_cho(self):
        pl, _ = PV._phan_loai_tu_telemetry(
            self._tm(archive={"pending": 4}, lanes={"produced": 2}))
        self.assertEqual(pl, "B")

    def test_A_khi_khong_co_ung_vien_nao(self):
        pl, _ = PV._phan_loai_tu_telemetry(self._tm())
        self.assertEqual(pl, "A")

    def test_D_khi_co_ung_vien_nhung_khong_ra_tac_pham(self):
        pl, _ = PV._phan_loai_tu_telemetry(self._tm(lanes={"discovered": 9}))
        self.assertEqual(pl, "D")

    def test_A_khi_MOI_ung_vien_deu_TRUNG_khong_phai_D(self):
        # Do that o vong dau sau khi trien khai observer: discovered=2,
        # deduped=2 — tim thay 2 thu nhung ca hai DA XONG TU TRUOC. Do la
        # "khong co viec moi" (A), KHONG phai "duong ong tac" (D).
        pl, vi = PV._phan_loai_tu_telemetry(
            self._tm(lanes={"discovered": 2, "deduped": 2}))
        self.assertEqual(pl, "A")
        self.assertIn("trùng", vi)

    def test_D_khi_dang_CHO_DANH_GIA(self):
        pl, vi = PV._phan_loai_tu_telemetry(
            self._tm(lanes={"discovered": 5, "deduped": 5,
                            "review_pending": 3}))
        self.assertEqual(pl, "D")
        self.assertIn("ĐÁNH GIÁ", vi)

    def test_ket_luan_LUON_mang_CUA_SO_bo_dem(self):
        # Bo dem cong don tu luc tien trinh khoi dong, khong phai 24h. Tra
        # loi "tu hom qua toi gio" bang mot cua so hai phut la noi doi.
        tm = self._tm(lanes={"discovered": 2, "deduped": 2})
        tm["farmer"] = {"started_at": "2026-09-11T03:43:18+00:00"}
        tm["round"] = {"number": 1}
        _pl, vi = PV._phan_loai_tu_telemetry(tm)
        self.assertIn("bộ đếm tính từ khi tiến trình khởi động", vi)
        self.assertIn("vòng 1", vi)

    def test_E_khi_khong_voi_toi_remote(self):
        pl, vi = PV._phan_loai_tu_telemetry(
            self._tm(archive={"reachable": False,
                              "last_error_class": "not_found"}))
        self.assertEqual(pl, "E")
        self.assertIn("gdrive", vi)

    def test_KHONG_co_anh_chup_thi_van_la_F(self):
        mg = moi_gioi(ra="active")
        bao = PV.kiem_duong_ong(mg)
        self.assertEqual(bao.phan_loai, "F")
        self.assertTrue(any("ảnh chụp" in x for x in bao.thieu))


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
            "telemetry.snapshot": {},
        }
        self.assertEqual(set(goi), set(mg.ops()), "có op mới chưa được kiểm")
        for op, kw in goi.items():
            with self.subTest(op=op):
                lenh, _dich = mg._bang()[op].dung(mg, dict(kw))
                PV._kiem_chi_doc(lenh)


if __name__ == "__main__":
    unittest.main()
