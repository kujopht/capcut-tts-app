"""Lớp quan sát sống V0.5 — bậc thẩm quyền, ngữ nghĩa trạng thái, chỉ-đọc.

LỖI ĐƯỢC GHÌM Ở ĐÂY, nguyên văn tình huống đã gặp:

    Người dùng: "production farmer còn chạy không?"
    Leader    : (Router có 0 việc) -> "không có gì đang chạy"
    Thực tế   : `fanfic-farmer` trên AWS đang chạy, PID 350714, 0 restart.

Cái sai KHÔNG phải là số của Router — Router thật sự có 0 việc. Cái sai là
dùng con số đó để trả lời một câu hỏi về MỘT HỆ THỐNG KHÁC. Nên phần lớn
tệp này kiểm đúng một điều: hai nguồn đó không được trộn, và "không biết"
không được đọc thành "đã dừng".
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.observability import config as cf  # noqa: E402
from scripts.control_center.observability.model import (  # noqa: E402
    AnhChupSong, KhoiQuanSat, QuanSat, TrangThai)
from scripts.control_center.observability.provider import (  # noqa: E402
    KHONG_DUOC_CO, ProviderCoSo)
from scripts.control_center.observability.providers import (  # noqa: E402
    LENH_DOC, ProbeChuaCoDuong, RouterProvider, SshServiceProvider)
from scripts.control_center.observability.service import (  # noqa: E402
    DichVuQuanSat, tom_tat_cho_leader)
from scripts.control_center.observability.tham_quyen import (  # noqa: E402
    Bac, cau_tu_choi_bia, xet_cau_hoi)

GOI = GOC / "scripts" / "control_center" / "observability"


# =============================================== A. BAC THAM QUYEN =========
class TestBacThamQuyen(unittest.TestCase):
    """Câu hỏi về HIỆN TẠI phải đòi bằng chứng SỐNG."""

    HIEN_TAI = (
        "production farmer còn chạy không?",
        "farmer đang chạy không?",
        "farm tới đâu rồi?",
        "worker còn sống không?",
        "service healthy không?",
        "có task nào đang xử lý?",
        "archive xong chưa?",
        "is the farmer running?",
        "kiểm tra giúp tôi farmer",
        "hiện tại thế nào rồi?",
    )
    LICH_SU = (
        "hôm qua farm tới đâu?",
        "tuần trước có lỗi gì không?",
        "đêm qua chạy được bao nhiêu round?",
    )
    KHONG_LIEN_QUAN = (
        "viết cho tôi bài kiểm cho bộ chia đoạn",
        "sửa lỗi encoding trong desktop.py",
        "thêm một dòng vào docs/seed.md",
    )

    def test_cau_hoi_hien_tai_DOI_bang_chung_song(self):
        for c in self.HIEN_TAI:
            with self.subTest(cau=c):
                yc = xet_cau_hoi(c)
                self.assertTrue(yc.can_live, c)
                self.assertEqual(yc.bac_toi_thieu, Bac.LIVE)

    def test_cau_hoi_LICH_SU_khong_bat_buoc_do_lai(self):
        """"hôm qua farm tới đâu" — một phép đo BÂY GIỜ không trả lời được.

        Câu vừa có dấu hiệu hiện tại ("tới đâu") vừa có mốc quá khứ
        ("hôm qua") thì mốc quá khứ thắng.
        """
        for c in self.LICH_SU:
            with self.subTest(cau=c):
                yc = xet_cau_hoi(c)
                self.assertTrue(yc.la_lich_su, c)
                self.assertFalse(yc.can_live, c)

    def test_cau_khong_lien_quan_thi_KHONG_do(self):
        """Đo mọi lượt là thêm vài giây SSH vào cả những tin nhắn chẳng
        cần biết farmer có chạy hay không."""
        for c in self.KHONG_LIEN_QUAN:
            with self.subTest(cau=c):
                self.assertFalse(xet_cau_hoi(c).can_live, c)

    def test_bac_live_cao_hon_ky_uc_va_suy_luan(self):
        self.assertLess(int(Bac.LIVE), int(Bac.KHO))
        self.assertLess(int(Bac.KHO), int(Bac.KY_UC))
        self.assertLess(int(Bac.KY_UC), int(Bac.SUY_LUAN))

    def test_KHONG_ghim_ten_du_an_vao_bo_nhan_dien(self):
        """Lớp này phải dùng được cho mọi dự án.

        Một mẫu chứa "farmer"/"fanfic" sẽ làm Game-X hay Admissions
        Scraper không bao giờ được đo — đúng cái mục 8 cấm.
        """
        src = (GOI / "tham_quyen.py").read_text(encoding="utf-8")
        i = src.index("_MAU_HIEN_TAI")
        j = src.index("_LICH_SU = [")
        mau = src[i:j].lower()
        for ten in ("farmer", "fanfic", "appwrite", "aws", "r2", "drive"):
            with self.subTest(ten=ten):
                self.assertNotIn(ten, mau)


# ============================================ B. NGU NGHIA TRANG THAI ======
class TestNguNghiaTrangThai(unittest.TestCase):
    """Sáu trạng thái, và ba cách "không biết" KHÔNG được thành `DOWN`."""

    def test_chi_DOWN_la_khang_dinh_xau(self):
        self.assertTrue(TrangThai.DOWN.la_khang_dinh_xau)
        for t in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE,
                  TrangThai.STALE, TrangThai.ACTIVE, TrangThai.DEGRADED):
            with self.subTest(t=t):
                self.assertFalse(t.la_khang_dinh_xau)

    def test_UNKNOWN_va_UNAVAILABLE_khong_phai_do_duoc(self):
        for t in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE, TrangThai.STALE):
            self.assertFalse(t.do_duoc, t)
        for t in (TrangThai.ACTIVE, TrangThai.DEGRADED, TrangThai.DOWN):
            self.assertTrue(t.do_duoc, t)

    def test_khong_biet_BAT_BUOC_kem_ly_do(self):
        with self.assertRaises(ValueError):
            QuanSat(khoa="x", trang_thai=TrangThai.UNKNOWN)
        with self.assertRaises(ValueError):
            QuanSat(khoa="x", trang_thai=TrangThai.UNAVAILABLE)

    def test_khong_biet_KHONG_duoc_mang_gia_tri(self):
        """`{"state": "unknown", "count": 0}` là một khẳng định về
        production mà không ai đo — cùng loại lỗi với "Router rảnh nên
        farmer đã dừng"."""
        with self.assertRaises(ValueError):
            QuanSat(khoa="x", trang_thai=TrangThai.UNAVAILABLE,
                    gia_tri=0, ly_do="chưa có probe")

    def test_qua_han_thi_thanh_STALE_chu_khong_giu_gia_tri_cu(self):
        q = QuanSat(khoa="round", trang_thai=TrangThai.ACTIVE, gia_tri=62,
                    nguon="ssh:x", do_luc=time.time() - 500, han_tuoi=120)
        self.assertTrue(q.qua_han)
        self.assertIs(q.hieu_luc(), TrangThai.STALE)
        self.assertIs(q.trang_thai, TrangThai.ACTIVE)   # do goc con nguyen

    def test_khoi_lay_cai_XAU_NHAT_trong_nhung_cai_do_duoc(self):
        k = KhoiQuanSat(khoa="s")
        k.them(QuanSat(khoa="a", trang_thai=TrangThai.ACTIVE, gia_tri=1,
                       nguon="x"))
        k.them(QuanSat(khoa="b", trang_thai=TrangThai.DEGRADED, gia_tri=2,
                       nguon="x"))
        self.assertIs(k.trang_thai, TrangThai.DEGRADED)
        k.them(QuanSat(khoa="c", trang_thai=TrangThai.DOWN, gia_tri=0,
                       nguon="x"))
        self.assertIs(k.trang_thai, TrangThai.DOWN)

    def test_khoi_toan_UNKNOWN_thi_la_UNKNOWN_chu_KHONG_DOWN(self):
        k = KhoiQuanSat(khoa="s")
        k.them(QuanSat(khoa="a", trang_thai=TrangThai.UNKNOWN,
                       nguon="x", ly_do="mạng lỗi"))
        self.assertIs(k.trang_thai, TrangThai.UNKNOWN)
        self.assertIsNot(k.trang_thai, TrangThai.DOWN)


# =================================== C. ROUTER vs DICH VU NGOAI ============
class TestRouterKhongPhaiTrangThaiDuAn(unittest.TestCase):
    """Phép kiểm TRUNG TÂM của V0.5."""

    def _anh(self, viec_router: int, tt_ngoai: TrangThai,
             ly_do: str = "") -> AnhChupSong:
        a = AnhChupSong(project_id="p")
        r = KhoiQuanSat(khoa="router", nhan="Router")
        r.them(QuanSat(
            khoa="running_tasks",
            trang_thai=TrangThai.ACTIVE if viec_router else TrangThai.DOWN,
            gia_tri=viec_router, nguon="router:store"))
        a.router["router"] = r
        k = KhoiQuanSat(khoa="svc", nhan="Dịch vụ")
        if tt_ngoai.do_duoc:
            k.them(QuanSat(khoa="service_state", trang_thai=tt_ngoai,
                           gia_tri="active", nguon="ssh:host"))
        else:
            k.them(QuanSat(khoa="service_state", trang_thai=tt_ngoai,
                           nguon="ssh:host", ly_do=ly_do or "không nối được"))
        a.dich_vu["svc"] = k
        return a

    def test_router_0_viec_ma_dich_vu_ACTIVE_thi_tong_the_ACTIVE(self):
        """Đúng tình huống đã gặp: Router rảnh, farmer vẫn chạy."""
        a = self._anh(0, TrangThai.ACTIVE)
        self.assertIs(a.trang_thai_chung, TrangThai.ACTIVE)
        self.assertTrue(a.co_bang_chung_song())

    def test_router_KHONG_tham_gia_trang_thai_chung(self):
        """Router `DOWN` (0 việc) không được kéo dự án xuống `DOWN`."""
        a = self._anh(0, TrangThai.ACTIVE)
        self.assertIs(a.router["router"].trang_thai, TrangThai.DOWN)
        self.assertIs(a.trang_thai_chung, TrangThai.ACTIVE)

    def test_router_0_viec_va_probe_UNKNOWN_thi_KHONG_KET_LUAN_DOWN(self):
        """Chế độ hỏng quan trọng nhất (mục 12.E).

        Router = 0 VÀ probe không đo được thì câu trả lời đúng là "chưa
        biết", không phải "đã dừng".
        """
        a = self._anh(0, TrangThai.UNKNOWN, "SSH quá hạn 12s")
        self.assertIs(a.trang_thai_chung, TrangThai.UNKNOWN)
        self.assertFalse(a.co_bang_chung_song())
        self.assertIsNot(a.trang_thai_chung, TrangThai.DOWN)

    def test_tom_tat_cho_leader_noi_RO_hai_thu_doc_lap(self):
        van = tom_tat_cho_leader(self._anh(0, TrangThai.ACTIVE))
        self.assertIn("ROUTER", van)
        self.assertIn("NGOÀI", van)
        self.assertIn("độc lập", van)
        self.assertIn("ssh:host", van)          # nguon goc

    def test_cau_tu_choi_bia_noi_du_ba_phan(self):
        c = cau_tu_choi_bia(0, ["SSH quá hạn 12s"])
        self.assertIn("0", c)
        self.assertIn("CHƯA xác minh", c)
        self.assertIn("SSH quá hạn 12s", c)
        self.assertIn("KHÔNG có nghĩa", c)


# ============================================== D. PROVIDER / PARSE ========
class _SshGia(SshServiceProvider):
    """`SshServiceProvider` với `_ssh` thay bằng đầu ra ĐÃ GHI SẴN.

    Cho phép kiểm phép phân tích trên những hình dạng thật của
    `systemctl`/`df` mà không cần mạng — và quan trọng hơn, kiểm cả các
    hình dạng HỎNG mà một máy thật ít khi cho đúng lúc ta cần.
    """

    def __init__(self, cfg, dap):
        super().__init__(cfg)
        self._dap = dap

    def _duong_khoa(self):
        return Path(__file__)               # ton tai la du

    def _ssh(self, lenh):
        for mau, kq in self._dap.items():
            if mau in lenh:
                return kq
        return 1, "", "không có đáp án giả cho lệnh này"


_CFG = {"id": "svc", "label": "SVC", "host": "h", "user": "u",
        "unit": "fanfic-farmer",
        "status_file": "/var/lib/fanfic-farmer/status.json",
        "key_path": __file__, "timeout": 3, "max_age": 120}


class TestPhanTichSsh(unittest.TestCase):
    def test_active_pid_restarts_status_json(self):
        p = _SshGia(_CFG, {
            "is-active": (0, "active", ""),
            "systemctl show": (0, "MainPID=350714\nNRestarts=0\n"
                                  "ActiveState=active\nSubState=running\n"
                                  "ExecMainStartTimestamp=Tue 2026-09-08 "
                                  "15:55:31 UTC", ""),
            "cat /var/lib": (0, json.dumps(
                {"healthy": True, "round": 62,
                 "updated_at": 1788967800,
                 "archive_status": "ARCHIVE_DONE"}), ""),
            "df -Pk": (0, "/dev/root 100 21 79 21% /", ""),
        })
        k = p.thu({})
        self.assertIs(k.trang_thai, TrangThai.ACTIVE)
        self.assertEqual(k.lay("main_pid").gia_tri, 350714)
        self.assertEqual(k.lay("restarts").gia_tri, 0)
        self.assertIs(k.lay("healthy").trang_thai, TrangThai.ACTIVE)
        self.assertEqual(k.lay("round").gia_tri, 62)
        self.assertEqual(k.lay("archive_status").gia_tri, "ARCHIVE_DONE")
        self.assertEqual(k.lay("disk").gia_tri, 21)

    def test_inactive_thi_DOWN(self):
        p = _SshGia(_CFG, {"is-active": (3, "inactive", ""),
                           "systemctl show": (0, "MainPID=0\nNRestarts=2", ""),
                           "cat /var/lib": (1, "", "No such file"),
                           "stat -c": (1, "", "No such file"),
                           "df -Pk": (0, "/dev/root 100 1 99 1% /", "")})
        k = p.thu({})
        self.assertIs(k.lay("service_state").trang_thai, TrangThai.DOWN)
        self.assertIs(k.trang_thai, TrangThai.DOWN)
        self.assertEqual(k.lay("main_pid").gia_tri, 0)

    def test_ssh_hong_thi_UNKNOWN_va_DUNG_o_do(self):
        """Không nối được máy thì KHÔNG biết dịch vụ thế nào."""
        p = _SshGia(_CFG, {})       # moi lenh tra loi
        p._ssh = lambda lenh: (None, "", "Connection timed out")
        k = p.thu({})
        self.assertIs(k.trang_thai, TrangThai.UNKNOWN)
        self.assertIn("timed out", k.lay("ssh").ly_do)
        # va KHONG di doc tiep — mot khoi UNKNOWN, khong bia phan con lai
        self.assertIsNone(k.lay("service_state"))

    def test_restart_nhieu_lan_la_DEGRADED_chu_khong_DOWN(self):
        p = _SshGia(_CFG, {
            "is-active": (0, "active", ""),
            "systemctl show": (0, "MainPID=42\nNRestarts=7", ""),
            "cat /var/lib": (0, json.dumps({"healthy": True}), ""),
            "df -Pk": (0, "/dev/root 100 1 99 1% /", "")})
        k = p.thu({})
        self.assertIs(k.lay("restarts").trang_thai, TrangThai.DEGRADED)
        self.assertIs(k.trang_thai, TrangThai.DEGRADED)

    def test_status_json_khong_doc_duoc_thi_van_lay_duoc_MOC_SUA(self):
        """Đo được thật trên production: `status.json` thuộc root nên
        `cat` trả "Permission denied", nhưng `stat` vẫn chạy — và mốc sửa
        là thứ trả lời "số này còn mới không"."""
        p = _SshGia(_CFG, {
            "is-active": (0, "active", ""),
            "systemctl show": (0, "MainPID=42\nNRestarts=0", ""),
            "cat /var/lib": (1, "", "cat: ...: Permission denied"),
            "stat -c": (0, str(int(time.time()) - 30), ""),
            "df -Pk": (0, "/dev/root 100 1 99 1% /", "")})
        k = p.thu({})
        self.assertIs(k.lay("healthy").trang_thai, TrangThai.UNKNOWN)
        self.assertIn("Permission denied", k.lay("healthy").ly_do)
        self.assertIs(k.lay("last_update").trang_thai, TrangThai.ACTIVE)
        # dich vu VAN la ACTIVE: khong doc duoc tep khong lam no dung
        self.assertIs(k.lay("service_state").trang_thai, TrangThai.ACTIVE)

    def test_thieu_cau_hinh_thi_UNAVAILABLE_kem_ly_do(self):
        k = SshServiceProvider({"id": "x"}).thu({})
        self.assertIs(k.trang_thai, TrangThai.UNAVAILABLE)
        self.assertIn("host", k.lay("ssh").ly_do)

    def test_khong_co_tep_khoa_thi_UNAVAILABLE_chu_khong_DOWN(self):
        cfg = dict(_CFG, key_path="C:/khong/ton/tai/x.pem")
        k = SshServiceProvider(cfg).thu({})
        self.assertIn(k.trang_thai, (TrangThai.UNKNOWN,
                                     TrangThai.UNAVAILABLE))
        self.assertIsNot(k.trang_thai, TrangThai.DOWN)

    def test_provider_KHONG_BAO_GIO_nem(self):
        class No(ProviderCoSo):
            ma, nhan, nhom = "no", "Nổ", "dich_vu"

            def _do(self, ctx):
                raise RuntimeError("vỡ")

        k = No().thu({})
        self.assertIs(k.trang_thai, TrangThai.UNKNOWN)
        self.assertIn("vỡ", k.lay("probe").ly_do)


# =============================================== E. CHI DOC ================
class TestChiDoc(unittest.TestCase):
    """Mục 10: không đường tác động nào được lọt vào lớp quan sát."""

    def test_khong_tep_nao_trong_goi_mang_dong_tu_doi_trang_thai(self):
        loi = []
        for f in sorted(GOI.glob("*.py")):
            src = f.read_text(encoding="utf-8")
            # Bo dong chu thich va chinh danh sach CAM: tep
            # `provider.py` PHAI nhac ten cac dong tu do de cam chung.
            ma = "\n".join(
                d for d in src.splitlines()
                if not d.lstrip().startswith("#")
                and not d.lstrip().startswith('"'))
            if f.name == "provider.py":
                i = ma.find("KHONG_DUOC_CO")
                j = ma.find(")", ma.find("iam ", i))
                if i >= 0 and j > i:
                    ma = ma[:i] + ma[j:]
            for x in KHONG_DUOC_CO:
                if x in ma:
                    loi.append(f"{f.name}: {x!r}")
        self.assertEqual(loi, [], "lớp QUAN SÁT mang động từ TÁC ĐỘNG: "
                                 + "; ".join(loi))

    def test_lenh_ssh_la_ALLOWLIST_va_toan_bo_chi_doc(self):
        for ten, mau in LENH_DOC.items():
            with self.subTest(lenh=ten):
                for x in ("restart", "stop", "start ", "enable", "disable",
                          "rm ", "kill", ">"):
                    self.assertNotIn(x, mau, f"{ten}: {mau}")
        # Chi bon dong tu doc.
        for mau in LENH_DOC.values():
            self.assertTrue(
                mau.startswith(("systemctl is-active", "systemctl show",
                                "cat ", "stat ", "df ")), mau)

    def test_khong_dung_sudo(self):
        """`sudo` nâng quyền trên một máy production — một lớp quan
        sát không được làm việc đó.

        Xét MÃ, không xét chú thích: `providers.py` GIẢI THÍCH vì sao
        không dùng nó, và một phép kiểm bắt cả chú thích sẽ buộc người
        sau xoá lời giải thích để làm bài kiểm xanh.
        """
        for mau in LENH_DOC.values():
            self.assertNotIn("sudo", mau)
        for f in GOI.glob("*.py"):
            ma = chr(10).join(
                d for d in f.read_text(encoding="utf-8").splitlines()
                if not d.lstrip().startswith("#"))
            with self.subTest(tep=f.name):
                self.assertNotIn("sudo", ma)

    def test_api_live_khong_nhan_tham_so_hanh_dong(self):
        src = (GOC / "scripts" / "control_center"
               / "webapi.py").read_text(encoding="utf-8")
        i = src.index('@app.get("/api/live")')
        j = src.index('@app.get("/api/live/capabilities")')
        than = src[i:j]
        # Chi `GET`, va chi hai tham so doc.
        self.assertNotIn("@app.post", than)
        for x in ("restart", "stop", "delete", "deploy", "write"):
            self.assertNotIn(x, than.lower())

    def test_cau_hinh_TU_CHOI_noi_dung_bi_mat(self):
        with self.assertRaises(cf.CauHinhLoi):
            cf.kiem_cau_hinh({"projects": {"p": {"providers": [
                {"type": "ssh_service", "id": "s", "host": "h", "unit": "u",
                 "key_path": "-----BEGIN RSA PRIVATE KEY-----\nabc"}]}}})
        with self.assertRaises(cf.CauHinhLoi):
            cf.kiem_cau_hinh({"projects": {"p": {"providers": [
                {"type": "ssh_service", "id": "s", "host": "h", "unit": "u",
                 "password": "hunter2"}]}}})

    def test_cau_hinh_TU_CHOI_loai_provider_la(self):
        with self.assertRaises(cf.CauHinhLoi):
            cf.kiem_cau_hinh({"projects": {"p": {"providers": [
                {"type": "shell", "id": "x"}]}}})

    def test_cau_hinh_THAT_cua_kho_nay_hop_le(self):
        d = cf.nap()
        self.assertIn("fanfic", d["projects"])
        prov = d["projects"]["fanfic"]["providers"]
        ssh = [p for p in prov if p["type"] == "ssh_service"]
        self.assertEqual(len(ssh), 1)
        self.assertEqual(ssh[0]["unit"], "fanfic-farmer")
        # Chi duong dan, khong noi dung.
        self.assertIn("key_path", ssh[0])
        self.assertNotIn("PRIVATE KEY", json.dumps(d))


# ======================================= F. GENERIC + DICH VU ==============
class TestDuAnChung(unittest.TestCase):
    """Mục 8: dự án không có adapter riêng vẫn được quan sát."""

    def setUp(self):
        from scripts.control_center.model import Project
        from scripts.control_center.store import ControlStore
        self.goc = Path(tempfile.mkdtemp(prefix="cc-obs-"))
        self.st = ControlStore(root=self.goc)
        self.addCleanup(self.st.close)
        self.st.luu_project(Project(project_id="khac", name="Dự án khác",
                                    repo_path=str(self.goc)))
        self.dv = DichVuQuanSat(self.st, cau_hinh={"projects": {}})

    def test_du_an_KHONG_khai_gi_van_co_router_va_git(self):
        kn = self.dv.kha_nang("khac")
        self.assertIn("router", kn)
        self.assertIn("git", kn)
        a = self.dv.anh_chup("khac", buoc_moi=True)
        self.assertIn("router", a.router)
        self.assertIn("git", a.kho)

    def test_khong_co_probe_DICH_VU_thi_UNAVAILABLE_chu_khong_DOWN(self):
        """Dự án chỉ có Router + git thì KHÔNG có bằng chứng dịch vụ.

        `git` nằm ở nhóm `kho` và CỐ Ý không tính là dịch vụ sống: một
        lần `git status` thành công không cho ai quyền nói gì về việc
        một service trên máy khác còn chạy hay không.
        """
        a = self.dv.anh_chup("khac", buoc_moi=True)
        self.assertIs(a.trang_thai_chung, TrangThai.UNAVAILABLE)
        self.assertFalse(a.co_bang_chung_song())
        # nhung kho git VAN duoc quan sat va bao rieng
        self.assertIn("git", a.kho)

    def test_fanfic_chi_la_CHUNG_cong_them(self):
        """Adapter Fanfic không được THAY THẾ phần chung."""
        dv = DichVuQuanSat(self.st)         # nap cau hinh that
        kn = dv.kha_nang("fanfic")
        self.assertIn("router", kn)
        self.assertIn("git", kn)
        self.assertIn("fanfic_farmer", kn)
        for x in ("appwrite", "r2", "drive"):
            self.assertIn(x, kn)

    def test_probe_chua_co_duong_la_UNAVAILABLE_kem_ly_do_chinh_xac(self):
        k = ProbeChuaCoDuong("appwrite", "Appwrite", "ung_dung",
                             "chưa có đường đọc an toàn").thu({})
        self.assertIs(k.trang_thai, TrangThai.UNAVAILABLE)
        self.assertIn("chưa có", k.lay("state").ly_do)
        self.assertIsNone(k.lay("state").gia_tri)

    def test_cau_hinh_HONG_khong_lam_mat_ca_tinh_nang(self):
        dv = DichVuQuanSat(self.st, duong_cau_hinh=self.goc / "khong-co.json")
        a = dv.anh_chup("khac", buoc_moi=True)
        self.assertIn("router", a.router)

    def test_bo_dem_khong_do_lai_ngay(self):
        a1 = self.dv.anh_chup("khac", buoc_moi=True)
        a2 = self.dv.anh_chup("khac")
        self.assertIs(a1, a2, "lượt thứ hai phải lấy từ bộ đệm")

    def test_buoc_moi_thi_do_lai_that(self):
        a1 = self.dv.anh_chup("khac", buoc_moi=True)
        a2 = self.dv.anh_chup("khac", buoc_moi=True)
        self.assertIsNot(a1, a2)

    def test_router_provider_dem_dung(self):
        from scripts.control_center.model import Task, TaskState
        self.st.luu_task(Task(task_id="khac.t1", project_id="khac",
                              title="t", objective="o",
                              state=TaskState.RUNNING))
        k = RouterProvider().thu({"store": self.st, "project_id": "khac"})
        self.assertEqual(k.lay("running_tasks").gia_tri, 1)
        self.assertIs(k.lay("running_tasks").trang_thai, TrangThai.ACTIVE)


# ============================================ G. TICH HOP LEADER ===========
class TestLeaderDoiBangChungSong(unittest.TestCase):
    """Mục 12.D: "farmer đang chạy không?" phải kéo trạng thái SỐNG vào."""

    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        self.goc = Path(tempfile.mkdtemp(prefix="cc-obs-ld-"))
        self.cc = ControlCenter(root=self.goc, probe=False)
        self.addCleanup(self.cc.store.close)
        self.cc.store.luu_project(Project(project_id="p", name="P",
                                          repo_path=str(self.goc)))

    def test_cau_hoi_hien_tai_SINH_khoi_song(self):
        van = self.cc._khoi_song("p", "farmer đang chạy không?")
        self.assertTrue(van, "câu hỏi hiện tại phải sinh khối SỐNG")
        self.assertIn("TRẠNG THÁI SỐNG", van)
        self.assertIn("ROUTER", van)

    def test_cau_khong_lien_quan_thi_KHONG_do(self):
        self.assertEqual(
            self.cc._khoi_song("p", "viết bài kiểm cho bộ chia đoạn"), "")

    def test_khong_co_bang_chung_song_thi_KEM_CAU_TU_CHOI_BIA(self):
        """Dự án không khai probe ngoài + Router rảnh -> khối phải nói rõ
        là chưa xác minh được, không được để model tự điền."""
        van = self.cc._khoi_song("p", "service healthy không?")
        self.assertIn("CHƯA xác minh", van)
        self.assertIn("KHÔNG có nghĩa", van)

    def test_nhac_nho_dat_LUAT_THAM_QUYEN_truoc_anh_chup_tinh(self):
        from scripts.control_center import leader
        anh = self.cc.anh_chup_du_an("p")
        nn = leader.dung_nhac_nho(anh, [], "farmer chạy không?",
                                  khoi_song="TRẠNG THÁI SỐNG: ...")
        self.assertIn("LUẬT THẨM QUYỀN", nn)
        # So VI TRI HAI MOC DU LIEU, khong so hai cum tu: ban huong
        # dan chung o dau nhac nho cung nhac ten hai khoi do, nen
        # `index()` tren cum tu se dung vao van xuoi.
        i_song = nn.index("--- BẮT ĐẦU DỮ LIỆU: TRẠNG THÁI SỐNG")
        i_tinh = nn.index("--- BẮT ĐẦU DỮ LIỆU: TRẠNG THÁI DỰ ÁN")
        self.assertLess(i_song, i_tinh,
                        "bằng chứng vừa đo phải đứng trước bằng chứng cũ")

    def test_luat_tham_quyen_CAM_dung_so_router_cho_dich_vu_ngoai(self):
        from scripts.control_center import leader
        for x in ("KHÔNG suy trạng thái một dịch vụ BÊN NGOÀI từ số việc",
                  "KHÔNG đọc UNKNOWN/UNAVAILABLE/STALE thành DOWN",
                  "KHÔNG bịa số"):
            self.assertIn(x, leader.LUAT_SONG)

    def test_khong_co_khoi_song_thi_nhac_nho_KHONG_co_luat(self):
        from scripts.control_center import leader
        anh = self.cc.anh_chup_du_an("p")
        nn = leader.dung_nhac_nho(anh, [], "sửa docs")
        self.assertNotIn("LUẬT THẨM QUYỀN", nn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
