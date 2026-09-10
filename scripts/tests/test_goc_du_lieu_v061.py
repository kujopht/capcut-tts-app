# -*- coding: utf-8 -*-
"""V0.6.1 — GỐC DỮ LIỆU CHÍNH TẮC + DI TRÚ (khuyết tật liên tục 2026-09-10).

Khuyết tật: danh tính dự án ổn định (`project_id="fanfic"` -> `fanfic-dcf29d1141`)
nhưng CHỖ LƯU thì neo vào VỊ TRÍ MÃ (cạnh EXE / `parents[2]` / `cwd`), nên cùng
một dự án có nhiều quyển sổ độc lập — đúng lý do tuyên bố "GPT-6 Astra…" gõ ở
bản `dist-v06` không hiện ra ở bản source-mode.

Bộ kiểm này khoá: gốc KHÔNG đổi theo cwd / vị trí EXE / worktree / thư mục
phiên bản; danh tính dự án ổn định; di trú idempotent + khử trùng + sao lưu +
không ghi đè bản mới hơn + cách ly dự án lạ; phiên bản KHO tách khỏi phiên bản
ứng dụng; một-người-ghi; bí mật KHÔNG vào sổ thường.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import di_tru as DT                        # noqa: E402
from scripts.control_center import duong_du_lieu as DD                 # noqa: E402
from scripts.control_center.memory.model import (BangChung, KyUc,      # noqa: E402
                                                 LoaiKyUc, SuKien, TinCay,
                                                 khong_gian_ten)
from scripts.control_center.memory.provider import LocalMemoryProvider  # noqa: E402
from scripts.control_center.model import Project                       # noqa: E402
from scripts.control_center.store import ControlStore                  # noqa: E402


class _Tam(unittest.TestCase):
    def setUp(self):
        self.tam = Path(tempfile.mkdtemp(prefix="cc-goc-"))
        self._env_cu = os.environ.get(DD.BIEN_GOC)
        self._cwd_cu = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd_cu)
        if self._env_cu is None:
            os.environ.pop(DD.BIEN_GOC, None)
        else:
            os.environ[DD.BIEN_GOC] = self._env_cu
        shutil.rmtree(self.tam, ignore_errors=True)


# ================================================== goc bat bien ==========

class TestGocBatBien(_Tam):
    """Gốc dữ liệu KHÔNG suy từ vị trí mã/cwd/exe."""

    def test_chinh_tac_theo_localappdata(self):
        os.environ.pop(DD.BIEN_GOC, None)
        la = os.environ.get("LOCALAPPDATA")
        if not la:
            self.skipTest("không có LOCALAPPDATA")
        self.assertEqual(DD.goc_chinh_tac(), (Path(la) / DD.TEN_UNG_DUNG).resolve())
        self.assertEqual(DD.goc_du_lieu(), DD.goc_chinh_tac())

    def test_cwd_khong_anh_huong(self):
        os.environ.pop(DD.BIEN_GOC, None)
        a = DD.goc_du_lieu()
        os.chdir(self.tam)                     # doi cwd
        b = DD.goc_du_lieu()
        sub = self.tam / "sau" / "sau_nua"
        sub.mkdir(parents=True)
        os.chdir(sub)
        c = DD.goc_du_lieu()
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_vi_tri_exe_va_frozen_khong_anh_huong(self):
        """Bản ĐÓNG GÓI và bản NGUỒN ra CÙNG một gốc."""
        from scripts.control_center.desktop import _goc_mac_dinh
        os.environ.pop(DD.BIEN_GOC, None)
        nguon = _goc_mac_dinh()
        exe_cu = sys.executable
        try:
            sys.frozen = True                                  # type: ignore[attr-defined]
            sys.executable = str(self.tam / "dist-v99" / "App" / "App.exe")
            dong_goi = _goc_mac_dinh()
        finally:
            if hasattr(sys, "frozen"):
                del sys.frozen                                 # type: ignore[attr-defined]
            sys.executable = exe_cu
        self.assertEqual(nguon, dong_goi,
                         "bản đóng gói phải ra CÙNG gốc với bản nguồn")
        self.assertEqual(nguon, DD.goc_chinh_tac())
        self.assertNotIn("dist-v99", str(dong_goi))

    def test_thu_muc_phien_ban_va_worktree_khong_anh_huong(self):
        os.environ.pop(DD.BIEN_GOC, None)
        goc = DD.goc_du_lieu()
        for gia in ("dist-v06/Router Control Center", "dist-v0612/App",
                    "worktrees/wt-a", "C:/Router-1.2.3"):
            with self.subTest(gia=gia):
                # Du "chay tu" bat ky dau, ham KHONG doc vi tri do.
                self.assertEqual(DD.goc_du_lieu(), goc)

    def test_ghi_de_tuong_minh_va_bien_moi_truong(self):
        self.assertEqual(DD.goc_du_lieu(self.tam), self.tam.resolve())
        os.environ[DD.BIEN_GOC] = str(self.tam / "env")
        self.assertEqual(DD.goc_du_lieu(), (self.tam / "env").resolve())
        # Tham so TUONG MINH thang bien moi truong.
        self.assertEqual(DD.goc_du_lieu(self.tam / "ep"), (self.tam / "ep").resolve())

    def test_moi_duong_con_deu_treo_tu_goc(self):
        g = self.tam
        self.assertEqual(DD.duong_router(g), g / ".router")
        self.assertEqual(DD.duong_control_db(g),
                         g / ".router" / "control_center" / "control.db")
        self.assertEqual(DD.duong_memory(g), g / ".router" / "memory")


# ================================================ danh tinh du an =========

class TestDanhTinhDuAn(unittest.TestCase):

    def test_namespace_chi_theo_project_id(self):
        self.assertEqual(khong_gian_ten("fanfic"), "fanfic-dcf29d1141")
        # Khong phu thuoc cwd/exe/duong dan.
        cwd = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            self.assertEqual(khong_gian_ten("fanfic"), "fanfic-dcf29d1141")
        finally:
            os.chdir(cwd)
        self.assertNotEqual(khong_gian_ten("fanfic"), khong_gian_ten("router"))


# ============================================== phien ban kho =============

class TestPhienBanKho(_Tam):

    def test_dat_va_doc_phien_ban(self):
        self.assertEqual(DD.phien_ban_kho(self.tam), 0)      # chua co moc
        moc = DD.dam_bao_kho(self.tam, ung_dung="test")
        self.assertEqual(moc["phien_ban_kho"], DD.PHIEN_BAN_KHO)
        self.assertEqual(DD.phien_ban_kho(self.tam), DD.PHIEN_BAN_KHO)
        for ten in ("control_center", "memory", "attachments"):
            self.assertTrue((DD.duong_router(self.tam) / ten).is_dir())

    def test_mo_lai_khong_tao_so_moi(self):
        DD.dam_bao_kho(self.tam)
        moc1 = DD.doc_moc(self.tam)
        time.sleep(0.01)
        DD.dam_bao_kho(self.tam, ung_dung="V9")
        moc2 = DD.doc_moc(self.tam)
        self.assertEqual(moc1["tao_luc"], moc2["tao_luc"],
                         "mở lại KHÔNG được tạo kho mới")
        self.assertEqual(moc2["ung_dung"], "V9")

    def test_so_moi_hon_ma_thi_DUNG(self):
        DD.dam_bao_kho(self.tam)
        m = DD.doc_moc(self.tam)
        m["phien_ban_kho"] = DD.PHIEN_BAN_KHO + 5
        DD._ghi_moc(self.tam, m)
        with self.assertRaises(DD.KhoLoi) as cm:
            DD.dam_bao_kho(self.tam)
        self.assertIn("phiên bản", str(cm.exception))

    def test_nang_tu_phien_ban_cu(self):
        DD.dam_bao_kho(self.tam)
        m = DD.doc_moc(self.tam)
        m["phien_ban_kho"] = 0            # gia lap so RAT cu (khong co moc)
        DD._ghi_moc(self.tam, m)
        moc = DD.dam_bao_kho(self.tam)
        self.assertEqual(moc["phien_ban_kho"], DD.PHIEN_BAN_KHO)


# ============================================ mot nguoi ghi ===============

class TestMotNguoiGhi(_Tam):

    def test_nguoi_ghi_thu_hai_bi_chan_va_co_cau_noi_ro(self):
        DD.dam_bao_kho(self.tam)
        a = DD.KhoaKho(self.tam)
        self.assertTrue(a.thu_giu())
        b = DD.KhoaKho(self.tam)
        self.assertFalse(b.thu_giu(), "người ghi thứ hai PHẢI bị chặn")
        cau = b.cau_bao_dang_dung()
        self.assertIn("đang được dùng", cau)
        self.assertIn(str(self.tam), cau)
        a.nha()
        self.assertTrue(b.thu_giu(), "nhả rồi thì bản sau giành được")
        b.nha()

    def test_goc_khac_thi_khong_tranh_nhau(self):
        g2 = self.tam / "khac"
        DD.dam_bao_kho(self.tam)
        DD.dam_bao_kho(g2)
        a, b = DD.KhoaKho(self.tam), DD.KhoaKho(g2)
        try:
            self.assertTrue(a.thu_giu())
            self.assertTrue(b.thu_giu())
        finally:
            a.nha(); b.nha()

    def test_context_manager(self):
        DD.dam_bao_kho(self.tam)
        with DD.KhoaKho(self.tam) as k:
            self.assertTrue(k.giu)
            self.assertFalse(DD.KhoaKho(self.tam).thu_giu())
        self.assertTrue(DD.KhoaKho(self.tam).thu_giu())


# =================================================== di tru ===============

def _dung_kho(goc: Path, pid: str, *, so_su_kien: int = 3,
              them_ky_uc: bool = True, noi_dung: str = "",
              nhan: str = "") -> None:
    """Dựng một gốc dữ liệu có control.db + một quyển ký ức thật.

    `nhan` phân biệt NỘI DUNG giữa các nguồn. Không có nó thì hai nguồn sinh
    dòng y hệt nhau và phép khử trùng (đúng đắn) gộp chúng lại — bản đầu của
    bài kiểm này tưởng đó là lỗi di trú.
    """
    DD.dam_bao_kho(goc)
    st = ControlStore(root=goc)
    st.luu_project(Project(project_id=pid, name=pid, repo_path=str(goc)))
    st.close()
    dau_nhan = nhan or goc.name
    p = LocalMemoryProvider(DD.duong_memory(goc), pid)
    ids = []
    for i in range(so_su_kien):
        sk = p.ghi_su_kien(SuKien(loai="test", ts=time.time() - i,
                                  tom_tat=f"{pid}/{dau_nhan} dòng {i}",
                                  nguon="test"),
                           noi_dung_day=f"{pid}/{dau_nhan} nội dung {i}")
        ids.append(sk.id)
    if them_ky_uc:
        p.luu_ky_uc(KyUc(loai=LoaiKyUc.FACT, quan_trong=6, tin_cay=TinCay.GHI_NHAN,
                         tieu_de=f"{pid} sự thật",
                         noi_dung=noi_dung or f"{pid} nội dung ký ức ổn định",
                         bang_chung=(BangChung(su_kien_id=ids[0]),)))
    p.close()


class TestDiTru(_Tam):

    def setUp(self):
        super().setUp()
        self.a = self.tam / "nguon_a"
        self.b = self.tam / "nguon_b"
        self.dich = self.tam / "dich"
        _dung_kho(self.a, "fanfic", so_su_kien=4)
        _dung_kho(self.b, "fanfic", so_su_kien=2, noi_dung="điều khác ở nguồn B")

    def _ung(self):
        return [(self.a, "nguồn A"), (self.b, "nguồn B")]

    def _dem(self, bang: str, pid: str = "fanfic") -> int:
        db = DD.duong_memory(self.dich) / khong_gian_ten(pid) / "memory.db"
        if not db.is_file():
            return 0
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            return int(c.execute(f"SELECT COUNT(*) FROM {bang}").fetchone()[0])
        finally:
            c.close()

    def test_kham_pha_nhan_dang_theo_luoc_do_va_du_an(self):
        ds = DT.kham_pha(self._ung())
        self.assertEqual(len(ds), 2)
        for n in ds:
            self.assertTrue(n.hop_le)
            self.assertEqual([s.project_id for s in n.sach], ["fanfic"])
            self.assertEqual(n.sach[0].ns, khong_gian_ten("fanfic"))

    def test_khong_nhan_thu_muc_khong_phai_kho(self):
        rac = self.tam / "rac"
        (rac / ".router" / "memory" / "gia").mkdir(parents=True)
        (rac / ".router" / "memory" / "gia" / "memory.db").write_bytes(b"khong phai sqlite")
        ds = DT.kham_pha([(rac, "rác")])
        self.assertEqual(ds[0].sach, [], "memory.db sai lược đồ phải bị bỏ qua")

    def test_xem_truoc_khong_ghi_gi(self):
        bc = DT.di_tru(self.dich, nguon=DT.kham_pha(self._ung()), thu_kho=True)
        self.assertTrue(bc["thu_kho"])
        self.assertFalse(DD.co_du_lieu(self.dich), "xem trước KHÔNG được ghi")

    def test_di_tru_roi_idempotent(self):
        ung = DT.kham_pha(self._ung())
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)
        sk1, ku1, bc1 = self._dem("su_kien"), self._dem("ky_uc"), self._dem("bang_chung")
        self.assertGreaterEqual(sk1, 6)      # 4 + 2 (noi dung khac nhau)
        self.assertGreaterEqual(ku1, 2)
        # Chay lai: KHONG duoc tang gi.
        bc = DT.di_tru(self.dich, nguon=DT.kham_pha(self._ung()), thu_kho=False)
        self.assertEqual((self._dem("su_kien"), self._dem("ky_uc"),
                          self._dem("bang_chung")), (sk1, ku1, bc1),
                         "di trú lần hai phải là no-op")
        self.assertEqual(bc["tong"].get("su_kien_moi", 0), 0)

    def test_khu_trung_su_kien_giong_nhau(self):
        # Hai nguon co dong Y HET nhau (cung `nhan`) -> chi MOT hang o dich.
        c = self.tam / "nguon_c"
        _dung_kho(c, "fanfic", so_su_kien=4, nhan="nguon_a")   # y het A
        ung = DT.kham_pha([(self.a, "A"), (c, "C")])
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)
        db = DD.duong_memory(self.dich) / khong_gian_ten("fanfic") / "memory.db"
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            trung = con.execute(
                "SELECT dau, COUNT(*) k FROM su_kien WHERE dau<>'' "
                "GROUP BY dau HAVING k > 1").fetchall()
        finally:
            con.close()
        self.assertEqual(trung, [], "không được có hai hàng cùng dấu vân tay")

    def test_sao_luu_truoc_khi_ghi(self):
        ung = DT.kham_pha(self._ung())
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)       # lan 1: dich trong
        bc = DT.di_tru(self.dich, nguon=ung, thu_kho=False)  # lan 2: co sao luu
        self.assertTrue(bc["sao_luu"])
        self.assertTrue(Path(bc["sao_luu"]).is_dir())
        self.assertTrue((Path(bc["sao_luu"]) / "memory").is_dir())
        self.assertTrue((Path(bc["sao_luu"]) / "GHI_CHU.txt").is_file())

    def test_khong_ghi_de_ban_moi_hon(self):
        ung = DT.kham_pha(self._ung())
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)
        db = DD.duong_memory(self.dich) / khong_gian_ten("fanfic") / "memory.db"
        d = sqlite3.connect(str(db))
        ma, = d.execute("SELECT ma FROM ky_uc LIMIT 1").fetchone()
        d.execute("UPDATE ky_uc SET noi_dung=?, ts_sua=? WHERE ma=?",
                  ("BẢN MỚI HƠN Ở ĐÍCH", time.time() + 999, ma))
        d.commit(); d.close()
        DT.di_tru(self.dich, nguon=DT.kham_pha(self._ung()), thu_kho=False)
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            nd, = c.execute("SELECT noi_dung FROM ky_uc WHERE ma=?", (ma,)).fetchone()
        finally:
            c.close()
        self.assertEqual(nd, "BẢN MỚI HƠN Ở ĐÍCH", "KHÔNG được ghi đè bản mới hơn")

    def test_cach_ly_du_an_la(self):
        la = self.tam / "du_an_la"
        _dung_kho(la, "du-an-khac", so_su_kien=5)
        ung = DT.kham_pha([(self.a, "A"), (la, "LẠ")])
        DT.di_tru(self.dich, nguon=ung, thu_kho=False, chi_du_an=["fanfic"])
        self.assertEqual(self._dem("su_kien", "du-an-khac"), 0,
                         "dự án ngoài phạm vi KHÔNG được vào đích")
        self.assertGreater(self._dem("su_kien", "fanfic"), 0)

    def test_khong_tu_di_tru_chinh_no(self):
        bc = DT.di_tru(self.a, nguon=DT.kham_pha([(self.a, "A")]), thu_kho=True)
        self.assertIn("không tìm thấy nguồn", bc.get("ly_do", ""))

    def test_dat_moc_khong_xoa_gi(self):
        ung = DT.kham_pha(self._ung())
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)
        p = DT.dat_moc_da_di_tru(ung[0], self.dich)
        self.assertTrue(p.is_file())
        self.assertTrue((self.a / ".router" / "memory").is_dir(),
                        "sổ cũ PHẢI còn nguyên")
        import json
        self.assertIn("KHÔNG xoá tự động", json.loads(p.read_text(encoding="utf-8"))["ghi_chu"])

    def test_giu_nguon_goc_bang_chung_sau_gop(self):
        """Mắt xích bằng chứng phải trỏ về ĐÚNG dòng L0 sau khi ánh xạ id."""
        ung = DT.kham_pha([(self.b, "B")])
        DT.di_tru(self.dich, nguon=ung, thu_kho=False)
        db = DD.duong_memory(self.dich) / khong_gian_ten("fanfic") / "memory.db"
        c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        try:
            r = c.execute("SELECT ky_uc_ma, su_kien_id FROM bang_chung "
                          "WHERE su_kien_id > 0 LIMIT 1").fetchone()
            self.assertIsNotNone(r, "phải còn mắt xích bằng chứng")
            sk = c.execute("SELECT id, tom_tat FROM su_kien WHERE id=?",
                           (r["su_kien_id"],)).fetchone()
            self.assertIsNotNone(sk, "bằng chứng phải trỏ tới một dòng L0 THẬT")
            self.assertIn("fanfic", sk["tom_tat"])
        finally:
            c.close()


# ============================================ bi mat ngoai so =============

class TestBiMatNgoaiSo(_Tam):

    def test_di_tru_khong_cham_kho_bi_mat(self):
        nguon = Path(DT.__file__).read_text(encoding="utf-8")
        for xau in ("kho_bi_mat", "CredRead", "CredWrite", "keyring"):
            self.assertNotIn(xau, nguon,
                             f"di trú KHÔNG được chạm kho bí mật ({xau})")

    def test_goc_du_lieu_khong_giu_bi_mat(self):
        nguon = Path(DD.__file__).read_text(encoding="utf-8")
        for xau in ("CredRead", "CredWrite", "password", "secret="):
            self.assertNotIn(xau, nguon)


if __name__ == "__main__":
    unittest.main()
