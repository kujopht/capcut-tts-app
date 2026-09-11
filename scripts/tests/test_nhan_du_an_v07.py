# -*- coding: utf-8 -*-
"""V0.7 Phase 1 — NHẬN DỰ ÁN HIỆN CÓ + VIÊN NANG + KIỂM LIÊN TỤC.

Bộ kiểm này khoá đúng những điều dễ hỏng nhất của lớp "hiểu dự án":

* nhận một kho THẬT mà KHÔNG sửa một byte nào của nó (đo bằng băm trước/sau);
* nhận LẠI là idempotent, và KHÔNG BAO GIỜ sinh `du-an-2`;
* danh tính bền: đổi nhánh/HEAD vẫn là cùng dự án, cùng quyển ký ức;
* viên nang có NGUỒN GỐC cho từng mục, và `UNKNOWN` khi thiếu bằng chứng —
  không bịa;
* phiên bản chỉ tăng khi có mục ĐỔI THẬT; lịch sử không bị ghi đè;
* quyết định bị THAY THẾ không còn nằm trong viên nang;
* mục CŨ được ĐÁNH DẤU chứ không im lặng;
* Leader hydrate CÓ TRẦN (bản gọn nhỏ hơn hẳn bản đầy);
* điểm liên tục KHÔNG bao giờ hoàn hảo giả;
* hai dự án không rò nhau.

Dùng kho git TẠM + gốc dữ liệu TẠM. Không chạm kho/production thật.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import kiem_lien_tuc as KL                 # noqa: E402
from scripts.control_center import nhan_du_an as ND                    # noqa: E402
from scripts.control_center import vien_nang_du_an as VN               # noqa: E402
from scripts.control_center.duong_du_lieu import dam_bao_kho           # noqa: E402
from scripts.control_center.engine import ControlCenter                # noqa: E402
from scripts.control_center.memory.model import khong_gian_ten         # noqa: E402


def _git(goc: Path, *a: str) -> None:
    p = subprocess.run(["git", "-C", str(goc), *a], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"git {a[0]} hỏng: {p.stderr[:300]}")


def kho_gia(goc: Path, *, ten: str = "Dự Án Thử",
            co_tai_lieu: bool = True) -> Path:
    """Một kho git THẬT hình dạng giống dự án thật (có CLAUDE.md + docs)."""
    goc.mkdir(parents=True, exist_ok=True)
    _git(goc, "init", "-q", "-b", "main")
    _git(goc, "config", "user.email", "t@example.invalid")
    _git(goc, "config", "user.name", "t")
    _git(goc, "config", "commit.gpgsign", "false")
    (goc / "CLAUDE.md").write_text(
        f"# {ten}\n\nKho này làm MỘT việc: thử nghiệm lớp nhận dự án của Router.\n",
        encoding="utf-8")
    (goc / "README.md").write_text("# readme\n\nmô tả ngắn\n", encoding="utf-8")
    if co_tai_lieu:
        d = goc / "docs"
        d.mkdir(exist_ok=True)
        (d / "ARCHITECTURE.md").write_text("# Kiến trúc\n\nba lớp\n", encoding="utf-8")
        (d / "PRODUCTION_CUTOVER.md").write_text("# Production\n\nmột host\n",
                                                 encoding="utf-8")
        (d / "HANDOFF.md").write_text("# Handoff\n\nbước tiếp theo: X\n",
                                      encoding="utf-8")
        (d / "STORAGE.md").write_text("# Lưu trữ\n\nbucket + đĩa\n", encoding="utf-8")
        (d / "GCE-WORKER-CAPACITY.md").write_text("# Giới hạn\n\ntrần 100k\n",
                                                  encoding="utf-8")
        (goc / "src").mkdir(exist_ok=True)
        (goc / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(goc, "add", "-A")
    _git(goc, "commit", "-q", "-m", "khởi tạo dự án thử")
    return goc


def anh_chup_kho(goc: Path) -> dict:
    """Băm MỌI tệp theo dõi được + trạng thái git — để chứng minh không sửa."""
    ra = {}
    for f in sorted(goc.rglob("*")):
        if not f.is_file() or ".git" in f.parts:
            continue
        try:
            ra[str(f.relative_to(goc))] = hashlib.sha256(f.read_bytes()).hexdigest()
        except OSError:
            pass
    p = subprocess.run(["git", "-C", str(goc), "status", "--porcelain"],
                       capture_output=True, text=True)
    ra["__git_status__"] = p.stdout
    p2 = subprocess.run(["git", "-C", str(goc), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    ra["__head__"] = p2.stdout.strip()
    return ra


class _Nen(unittest.TestCase):
    def setUp(self):
        self.tam = Path(tempfile.mkdtemp(prefix="cc-v07-"))
        self.kho = kho_gia(self.tam / "du-an-thu")
        self.goc = self.tam / "kho_du_lieu"
        dam_bao_kho(self.goc)
        self.cc = ControlCenter(root=self.goc, probe=False, leader_bat=False)

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.tam, ignore_errors=True)


# =============================================== NHAN DU AN (Phan A/B) =====

class TestNhanDuAn(_Nen):

    def test_nhan_kho_that_va_do_duoc_nhan_dang(self):
        kq = ND.nhan_du_an(self.cc, self.kho, ten="Dự Án Thử")
        self.assertTrue(kq.ok, kq.ly_do)
        self.assertTrue(kq.moi)
        self.assertFalse(kq.lien_ket_lai)
        self.assertTrue(kq.kho.la_git)
        self.assertEqual(kq.kho.nhanh, "main")
        self.assertEqual(kq.kho.so_commit, 1)
        self.assertTrue(kq.kho.head)
        # Du an THAT SU vao so.
        pj = self.cc.store.project(kq.project_id)
        self.assertIsNotNone(pj)
        self.assertTrue(Path(pj.repo_path).samefile(self.kho))

    def test_NHAN_KHONG_SUA_MOT_BYTE_NAO_CUA_KHO(self):
        truoc = anh_chup_kho(self.kho)
        ND.nhan_du_an(self.cc, self.kho)
        VN.dung_va_luu(self.cc, ND._suy_project_id(str(self.kho)))
        KL.kiem(self.cc, ND._suy_project_id(str(self.kho)))
        sau = anh_chup_kho(self.kho)
        self.assertEqual(truoc, sau, "nhận/dựng nang/kiểm KHÔNG được sửa kho đích")
        self.assertFalse((self.kho / ".router").exists(),
                         "KHÔNG được tạo .router trong kho đích")

    def test_nhan_lai_la_IDEMPOTENT_va_khong_tao_ban_thu_hai(self):
        a = ND.nhan_du_an(self.cc, self.kho)
        n1 = len(self.cc.store.projects())
        b = ND.nhan_du_an(self.cc, self.kho)
        c = ND.nhan_du_an(self.cc, str(self.kho) + os.sep)   # dấu / ở cuối
        self.assertEqual({a.project_id, b.project_id, c.project_id},
                         {a.project_id}, "phải LIÊN KẾT LẠI cùng một dự án")
        self.assertTrue(b.lien_ket_lai and c.lien_ket_lai)
        self.assertFalse(b.moi or c.moi)
        self.assertEqual(len(self.cc.store.projects()), n1,
                         "không được sinh dự án thứ hai")

    def test_nhan_tu_THU_MUC_CON_van_ra_dung_du_an(self):
        a = ND.nhan_du_an(self.cc, self.kho)
        b = ND.nhan_du_an(self.cc, self.kho / "src")
        self.assertEqual(b.project_id, a.project_id)
        self.assertTrue(b.lien_ket_lai)

    def test_danh_tinh_KHONG_doi_theo_nhanh(self):
        a = ND.nhan_du_an(self.cc, self.kho)
        ns1 = khong_gian_ten(a.project_id)
        _git(self.kho, "checkout", "-q", "-b", "nhanh-khac")
        (self.kho / "moi.txt").write_text("x\n", encoding="utf-8")
        _git(self.kho, "add", "-A")
        _git(self.kho, "commit", "-q", "-m", "trên nhánh khác")
        b = ND.nhan_du_an(self.cc, self.kho)
        self.assertEqual(b.project_id, a.project_id, "đổi nhánh KHÔNG đổi dự án")
        self.assertEqual(khong_gian_ten(b.project_id), ns1,
                         "namespace ký ức phải giữ nguyên")
        self.assertEqual(b.kho.nhanh, "nhanh-khac")

    def test_project_id_da_dung_cho_kho_khac_thi_TU_CHOI(self):
        a = ND.nhan_du_an(self.cc, self.kho)
        kho2 = kho_gia(self.tam / "kho-khac")
        kq = ND.nhan_du_an(self.cc, kho2, project_id=a.project_id)
        self.assertFalse(kq.ok)
        self.assertIn("đã dùng cho kho khác", kq.ly_do)

    def test_thu_muc_khong_phai_git_van_nhan_duoc_va_noi_ro(self):
        d = self.tam / "khong-git"
        d.mkdir()
        (d / "README.md").write_text("# x\n\nmô tả\n", encoding="utf-8")
        kq = ND.nhan_du_an(self.cc, d)
        self.assertTrue(kq.ok)
        self.assertFalse(kq.kho.la_git)
        self.assertTrue(any("không phải kho git" in g for g in kq.ghi_chu))

    def test_duong_khong_ton_tai_thi_bao_ro(self):
        kq = ND.nhan_du_an(self.cc, self.tam / "khong-co-that")
        self.assertFalse(kq.ok)
        self.assertIn("không có thư mục", kq.ly_do)

    def test_url_remote_bi_LOC_credential(self):
        self.assertEqual(ND.loc_url("https://u:tok@github.com/a/b.git"),
                         "https://github.com/a/b.git")
        self.assertNotIn("tok", ND.loc_url("https://u:tok@h/x"))


# ============================================ VIEN NANG (Phan C/D/E/J) =====

class TestVienNang(_Nen):

    def setUp(self):
        super().setUp()
        self.pid = ND.nhan_du_an(self.cc, self.kho, ten="Dự Án Thử").project_id

    def test_dung_nang_co_muc_va_NGUON_GOC(self):
        kq = VN.dung_va_luu(self.cc, self.pid)
        self.assertTrue(kq["luu"])
        self.assertGreaterEqual(kq["phien_ban"], 1)
        muc = kq["muc"]
        self.assertEqual(set(muc), set(VN.KHOA_MUC))
        # Danh tinh + muc tieu + tai lieu phai CO va co bang chung.
        for k in ("danh_tinh", "muc_tieu", "kien_truc"):
            with self.subTest(k=k):
                self.assertEqual(muc[k]["trang_thai"], VN.CO, muc[k])
                self.assertTrue(muc[k]["nguon"])
                self.assertTrue(muc[k]["bang_chung"], "mục CÓ phải có bằng chứng")

    def test_muc_tieu_lay_tu_CLAUDE_md_co_duong_dan_lam_bang_chung(self):
        muc = VN.dung_muc(self.cc, self.pid)
        m = muc["muc_tieu"]
        self.assertEqual(m["trang_thai"], VN.CO)
        self.assertIn("doc:CLAUDE.md", m["bang_chung"])
        self.assertIn("Dự Án Thử", str(m["gia_tri"]))

    def test_thieu_bang_chung_thi_UNKNOWN_chu_khong_bia(self):
        # Kho khong tai lieu -> cac muc dua tai lieu phai UNKNOWN.
        kho2 = kho_gia(self.tam / "tron", co_tai_lieu=False)
        (kho2 / "CLAUDE.md").unlink()
        (kho2 / "README.md").unlink()
        _git(kho2, "add", "-A")
        _git(kho2, "commit", "-q", "-m", "bỏ tài liệu")
        pid2 = ND.nhan_du_an(self.cc, kho2).project_id
        muc = VN.dung_muc(self.cc, pid2)
        for k in ("muc_tieu", "kien_truc", "topo_production", "roadmap"):
            with self.subTest(k=k):
                self.assertEqual(muc[k]["trang_thai"], VN.KHONG_RO,
                                 f"{k} phải UNKNOWN khi không có bằng chứng")
                self.assertEqual(muc[k]["gia_tri"], "")
                self.assertTrue(muc[k]["ghi_chu"], "UNKNOWN phải nói VÌ SAO")

    def test_phien_ban_chi_tang_khi_CO_MUC_DOI(self):
        a = VN.dung_va_luu(self.cc, self.pid)
        b = VN.dung_va_luu(self.cc, self.pid)
        self.assertTrue(a["luu"])
        self.assertFalse(b["luu"], "không đổi gì thì KHÔNG sinh phiên bản")
        self.assertEqual(b["phien_ban"], a["phien_ban"])
        # Co quyet dinh moi -> DOI -> phien ban tang, ban cu con nguyen.
        self.cc.store.them_chat(self.pid, role="user",
                                text="hãy ghi nhớ đây là một quyết định của "
                                     "project: chỉ deploy vào thứ Ba.")
        time.sleep(0.15)
        c = VN.dung_va_luu(self.cc, self.pid)
        self.assertTrue(c["luu"])
        self.assertGreater(c["phien_ban"], a["phien_ban"])
        self.assertIn("quyet_dinh", c["doi"])
        p = self.cc.ky_uc.provider(self.pid)
        self.assertGreaterEqual(len(p.cac_phien_ban_vien_nang(10)), 2,
                                "lịch sử phiên bản KHÔNG được ghi đè")

    def test_quyet_dinh_hieu_luc_vao_nang_va_ban_THAY_THE_thi_khong(self):
        self.cc.store.them_chat(self.pid, role="user",
                                text="hãy ghi nhớ đây là một quyết định của "
                                     "project: dùng model A cho mọi task.")
        time.sleep(0.15)
        muc = VN.dung_muc(self.cc, self.pid)
        self.assertIn("model A", str(muc["quyet_dinh"]["gia_tri"]))
        # Thay the tuong minh -> ban cu ra khoi nang, ban moi vao.
        self.cc.store.them_chat(self.pid, role="user",
                                text="hãy ghi nhớ đây là một quyết định của "
                                     "project, thay thế quyết định trước: dùng "
                                     "model B cho mọi task.")
        time.sleep(0.2)
        muc2 = VN.dung_muc(self.cc, self.pid)
        van = str(muc2["quyet_dinh"]["gia_tri"])
        self.assertIn("model B", van)
        self.assertNotIn("model A", van, "quyết định ĐÃ THAY THẾ không được ở lại")

    def test_su_co_lich_su_vao_nang(self):
        p = self.cc.ky_uc.provider(self.pid)
        from scripts.control_center.memory.model import KyUc, LoaiKyUc, TinCay
        p.luu_ky_uc(KyUc(loai=LoaiKyUc.INCIDENT, quan_trong=7,
                         tin_cay=TinCay.DO_DUOC, tieu_de="khoá SSH sai tên tệp",
                         noi_dung="tham chiếu sai tên khoá nên SSH gãy"))
        muc = VN.dung_muc(self.cc, self.pid)
        self.assertEqual(muc["su_co"]["trang_thai"], VN.CO)
        self.assertIn("SSH", str(muc["su_co"]["gia_tri"]))

    def test_danh_dau_muc_CU_khi_HEAD_doi(self):
        VN.dung_va_luu(self.cc, self.pid)
        muc, pb = VN.nap(self.cc, self.pid)
        self.assertNotIn(VN.CU, [muc[k]["trang_thai"] for k in VN.KHOA_MUC])
        (self.kho / "them.txt").write_text("y\n", encoding="utf-8")
        _git(self.kho, "add", "-A")
        _git(self.kho, "commit", "-q", "-m", "đổi HEAD")
        muc2, _ = VN.nap(self.cc, self.pid)
        self.assertEqual(muc2["danh_tinh"]["trang_thai"], VN.CU,
                         "HEAD đổi -> mục danh tính phải bị ĐÁNH DẤU CŨ")
        self.assertIn("CŨ", muc2["danh_tinh"]["ghi_chu"])

    def test_nap_BOUNDED_nho_hon_ban_day(self):
        VN.dung_va_luu(self.cc, self.pid)
        muc, _ = VN.nap(self.cc, self.pid)
        day = VN.uoc_token(muc)
        gon = VN._ut_gon(muc)
        self.assertGreater(day, 0)
        self.assertLessEqual(gon, 1000, "bản gọn phải có TRẦN")
        self.assertLess(gon, day + 1)
        self.assertIn("Danh tính", VN.render_gon(muc))

    def test_thu_tu_nap_DAY_MUC_LIEN_QUAN_len_theo_cau_hoi(self):
        # Do duoc o nghiem thu v0.7: bang uu tien CO DINH cat mat dung muc
        # dang bi hoi, va Leader lap cho trong bang cach BIA ("5 account"
        # trong khi so ghi 8). Nen: duoi bang xep theo do lien quan.
        # Muc khop manh nhat chen len ngay SAU danh tinh: khi ngan sach chat
        # thi no van song, vi no chinh la thu "can o luot nay".
        t = VN.thu_tu_nap("hiện Router có bao nhiêu Antigravity account?")
        self.assertEqual(t[1], "tai_nguyen_agent")
        t2 = VN.thu_tu_nap("R2 và Google Drive giữ vai trò lưu trữ gì?")
        self.assertEqual(t2[1], "luu_tru")
        # Chi chen MOT muc: ca dau bang van con nguyen trong 7 vi tri dau.
        for q in ("", "account nào?", "lưu trữ ở đâu?"):
            dau7 = set(VN.thu_tu_nap(q)[:VN._DAU_LUON + 1])
            self.assertTrue(set(VN.UU_TIEN_NAP[:VN._DAU_LUON]) <= dau7,
                            f"dau bang phai con nguyen: q={q!r}")
        # Moi lan goi phai tra du 19 muc, khong trung, khong mat.
        for q in ("", "lưu trữ", "account", "zzzz"):
            tt = VN.thu_tu_nap(q)
            self.assertEqual(sorted(tt), sorted(VN.UU_TIEN_NAP))
        # Khong co tu khoa nao khop -> giu nguyen thu tu mac dinh.
        self.assertEqual(VN.thu_tu_nap("zzzz qqqq"), list(VN.UU_TIEN_NAP))

    def test_thu_tu_nap_KHOP_KHONG_PHU_THUOC_DAU(self):
        a = VN.thu_tu_nap("bao nhieu tai khoan antigravity")
        b = VN.thu_tu_nap("bao nhiêu tài khoản Antigravity")
        self.assertEqual(a[1], "tai_nguyen_agent")
        self.assertEqual(a, b)

    def test_dong_CAT_phai_NEU_TEN_muc_chua_nap(self):
        # Dong cat chi DEM thi Leader khong phan biet duoc "khong co bang
        # chung" voi "co ma chua nap" -> no BIA. Neu TEN thi khong.
        muc = {k: {"gia_tri": [f"{k} " + "x" * 90] * 4, "trang_thai": VN.CO,
                   "nguon": "kho", "bang_chung": [], "ghi_chu": "", "ts": 0.0}
               for k in VN.KHOA_MUC}
        g = VN.render_gon(muc)
        chan = [l for l in g.splitlines() if l.startswith("(viên nang")]
        self.assertEqual(len(chan), 1, "phai co dung mot dong cat")
        self.assertIn("CHƯA NẠP", chan[0])
        self.assertTrue(any(VN.NHAN_MUC[k] in chan[0] for k in VN.KHOA_MUC),
                        "dong cat phai NEU TEN muc, khong chi dem")

    def test_dong_CAT_khong_duoc_hy_sinh_muc_LIEN_QUAN_NHAT(self):
        # Bug do duoc: ban tru-sau day dung muc lien quan nhat ra de lay cho
        # cho dong cat, roi ten no roi vao phan "+N muc" -> Leader khong thay
        # ca noi dung lan ten. Thu duoc phep hy sinh la TEN, khong la MUC.
        muc = {k: {"gia_tri": [f"{k} " + "y" * 90] * 4, "trang_thai": VN.CO,
                   "nguon": "kho", "bang_chung": [], "ghi_chu": "", "ts": 0.0}
               for k in VN.KHOA_MUC}
        q = "R2 và Google Drive giữ vai trò lưu trữ gì?"
        g = VN.render_gon(muc, cau_hoi=q)
        dau_muc = [l.split(":")[0] for l in g.splitlines()
                   if l and not l.startswith((" ", "(viên nang"))]
        self.assertIn(VN.NHAN_MUC["luu_tru"], dau_muc,
                      "muc lien quan nhat phai duoc NAP, khong bi doi cho")

    def test_render_gon_GIU_TRAN_ke_ca_khi_co_dong_cat(self):
        from scripts.control_center.memory.model import uoc_token as ut
        muc = {k: {"gia_tri": [f"{k} " + "z" * 120] * 5, "trang_thai": VN.CO,
                   "nguon": "kho", "bang_chung": [], "ghi_chu": "", "ts": 0.0}
               for k in VN.KHOA_MUC}
        for q in ("", "lưu trữ R2 drive", "bao nhiêu account antigravity"):
            for tran in (300, 600, 900):
                g = VN.render_gon(muc, cau_hoi=q, tran_token=tran)
                self.assertLessEqual(ut(g), tran,
                                     f"tran phai THAT: q={q!r} tran={tran}")

    def test_LUAT_NANG_cam_doan_khi_muc_bi_CAT_hoac_MONG(self):
        # Hai lo hong do duoc tren app that, moi cai mot luat. Xoa luat nao
        # thi Leader lai lap cho trong bang cach bia, nen khoa ca hai lai.
        from scripts.control_center import leader
        lu = leader.LUAT_NANG
        self.assertIn("CHƯA NẠP", lu, "phai noi ve muc bi CAT")
        self.assertIn("MỎNG", lu, "phai noi ve muc CO MAT nhung MONG")
        for ma in ("qd_", "ku_", "doc:"):
            self.assertIn(ma, lu, f"phai doi MA bang chung ({ma})")
        # Luat phai duoc GAN vao nhac nho khi co khoi vien nang.
        class _Anh:
            def tom_tat(self):
                return "(trạng thái rỗng)"
        nn = leader.dung_nhac_nho(_Anh(), [], "kho luu tru ra sao?",
                                  khoi_nang="Danh tính: x")
        self.assertIn(lu[:30], nn)
        # Khong co khoi nang thi KHONG gan luat (khong noi ve thu khong co).
        self.assertNotIn(lu[:30], leader.dung_nhac_nho(_Anh(), [], "sửa docs"))

    def test_render_hien_UNKNOWN_de_Leader_biet_ma_hoi(self):
        kho2 = kho_gia(self.tam / "tron2", co_tai_lieu=False)
        pid2 = ND.nhan_du_an(self.cc, kho2).project_id
        muc = VN.dung_muc(self.cc, pid2)
        self.assertIn("UNKNOWN", VN.render(muc))

    def test_bi_mat_KHONG_vao_nang(self):
        p = self.cc.ky_uc.provider(self.pid)
        from scripts.control_center.memory.model import KyUc, LoaiKyUc, TinCay
        p.luu_ky_uc(KyUc(loai=LoaiKyUc.INCIDENT, quan_trong=7,
                         tin_cay=TinCay.DO_DUOC, tieu_de="rò khoá",
                         noi_dung="token AKIA1234567890ABCDEF đã bị thu hồi"))
        VN.dung_va_luu(self.cc, self.pid)
        muc, _ = VN.nap(self.cc, self.pid)
        import json
        self.assertNotIn("AKIA1234567890ABCDEF", json.dumps(muc, ensure_ascii=False))


# ================================================ KIEM LIEN TUC (Phan F) ===

class TestKiemLienTuc(_Nen):

    def test_kho_tron_thi_KHONG_san_sang_va_noi_ro_thieu_gi(self):
        kho2 = kho_gia(self.tam / "tron3", co_tai_lieu=False)
        (kho2 / "CLAUDE.md").unlink()
        (kho2 / "README.md").unlink()
        _git(kho2, "add", "-A")
        _git(kho2, "commit", "-q", "-m", "trống")
        pid = ND.nhan_du_an(self.cc, kho2).project_id
        VN.dung_va_luu(self.cc, pid)
        kq = KL.kiem(self.cc, pid)
        self.assertIn(kq["san_sang"], ("NO", "PARTIAL"))
        self.assertNotEqual(kq["san_sang"], "YES",
                            "kho trống KHÔNG được báo sẵn sàng")
        self.assertLess(kq["phu_bang_chung"], 1.0, "không được phủ 100% giả")
        self.assertTrue(kq["vi_sao"])
        # Moi hang phai co ket qua hop le va ly do.
        for h in kq["hang"]:
            self.assertIn(h["ket_qua"], (KL.PASS, KL.PARTIAL, KL.FAIL))
            self.assertTrue(h["ly_do"], f"{h['khoa']} thiếu lý do")

    def test_du_an_co_tai_lieu_diem_cao_hon_kho_tron(self):
        pid = ND.nhan_du_an(self.cc, self.kho).project_id
        VN.dung_va_luu(self.cc, pid)
        a = KL.kiem(self.cc, pid)
        kho2 = kho_gia(self.tam / "tron4", co_tai_lieu=False)
        pid2 = ND.nhan_du_an(self.cc, kho2).project_id
        VN.dung_va_luu(self.cc, pid2)
        b = KL.kiem(self.cc, pid2)
        self.assertGreater(a["phu_bang_chung"], b["phu_bang_chung"])
        self.assertIn("CONTINUITY AUDIT", KL.bang_chu(a))

    def test_bang_chu_khong_bao_gio_in_100_phan_tram_gia(self):
        pid = ND.nhan_du_an(self.cc, self.kho).project_id
        VN.dung_va_luu(self.cc, pid)
        kq = KL.kiem(self.cc, pid)
        self.assertLessEqual(kq["phu_bang_chung_phan_tram"], 100)
        co = sum(1 for k in VN.KHOA_MUC
                 if (VN.nap(self.cc, pid)[0].get(k) or {}).get("trang_thai") == VN.CO)
        self.assertEqual(kq["so_muc_co"] >= co, True)


# ================================================== CACH LY / KHO CHINH ====

class TestCachLyVaKho(_Nen):

    def test_hai_du_an_khong_ro_nhau(self):
        p1 = ND.nhan_du_an(self.cc, self.kho, ten="A").project_id
        kho2 = kho_gia(self.tam / "kho-b", ten="Dự Án B")
        p2 = ND.nhan_du_an(self.cc, kho2, ten="B").project_id
        self.assertNotEqual(p1, p2)
        self.cc.store.them_chat(p1, role="user",
                                text="hãy ghi nhớ đây là một quyết định của "
                                     "project: bí mật của A.")
        time.sleep(0.15)
        VN.dung_va_luu(self.cc, p1)
        VN.dung_va_luu(self.cc, p2)
        m1, _ = VN.nap(self.cc, p1)
        m2, _ = VN.nap(self.cc, p2)
        # `de_bat` chuẩn hoá nội dung (hoa chữ đầu), nên so KHÔNG phân biệt hoa.
        self.assertIn("bí mật của a", str(m1["quyet_dinh"]["gia_tri"]).lower())
        self.assertNotIn("bí mật của a", str(m2).lower())
        self.assertIn("Dự Án B", str(m2["muc_tieu"]["gia_tri"]))

    def test_nang_o_dung_quyen_so_cua_GOC_CHINH_TAC(self):
        pid = ND.nhan_du_an(self.cc, self.kho).project_id
        VN.dung_va_luu(self.cc, pid)
        db = (self.goc / ".router" / "memory" / khong_gian_ten(pid) / "memory.db")
        self.assertTrue(db.is_file(), "viên nang phải nằm trong sổ của gốc đã cho")
        import sqlite3
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            n = c.execute("SELECT COUNT(*) FROM vien_nang").fetchone()[0]
        finally:
            c.close()
        self.assertGreaterEqual(n, 1)

    def test_nang_SONG_QUA_khoi_dong_lai(self):
        pid = ND.nhan_du_an(self.cc, self.kho).project_id
        a = VN.dung_va_luu(self.cc, pid)
        self.cc.shutdown()
        # Mo mot ControlCenter MOI tren cung goc — nang phai con.
        cc2 = ControlCenter(root=self.goc, probe=False, leader_bat=False)
        try:
            muc, pb = VN.nap(cc2, pid)
            self.assertEqual(pb, a["phien_ban"])
            self.assertEqual(muc["danh_tinh"]["trang_thai"], VN.CO)
            self.assertTrue(cc2._khoi_vien_nang(pid),
                            "Leader phải hydrate được sau khởi động lại")
        finally:
            cc2.shutdown()
        self.cc = ControlCenter(root=self.goc, probe=False, leader_bat=False)


if __name__ == "__main__":
    unittest.main()
