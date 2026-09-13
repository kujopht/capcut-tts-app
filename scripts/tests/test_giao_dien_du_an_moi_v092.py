# -*- coding: utf-8 -*-
"""GIAO DIỆN «+ Dự án mới» + cài đặt thư mục gốc — V0.9.2.

Backend đã có và đã được kiểm ở `test_tao_du_an_v092.py`. Tệp này canh phần
CÒN LẠI: đường đi từ nút bấm tới API, và cái ô cài đặt quyết định Router tạo
thư mục ở đâu.

BA HỎNG THẬT mà tệp này được viết ra để bắt lại, vì cả ba đều IM LẶNG cho
tới lúc người dùng bấm nút:

1. **Tham chiếu ra ngoài phạm vi.** Bản đầu của tôi gọi `json({ten})` làm
   thân request — nhưng `json` là một `const` khai báo BÊN TRONG một hàm
   khác, nên ở đây nó là `ReferenceError`, và chỉ lộ ra lúc bấm «Tạo dự án».
   `node --check` KHÔNG bắt được: sai phạm vi không phải sai cú pháp.
2. **Sai `id`.** Bản đầu focus `#o-chat`; ô soạn thật tên `#o-soan`. Không
   lỗi, không cảnh báo — chỉ là con trỏ không nhảy vào ô.
3. **Bản sao thứ hai của logic đặt tên.** Bản cũ tự suy `project_id` bằng JS
   (`ten.toLowerCase().replace(...)`) rồi `POST /api/project`. Backend có
   `slug()` riêng, đã kiểm; hai bản sẽ trôi khỏi nhau.
"""

from __future__ import annotations

import json as _json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.tao_du_an import (GOC_MAC_DINH_WIN,  # noqa: E402
                                              KHOA_THU_MUC_GOC, TaoDuAnLoi,
                                              kiem_thu_muc_goc)

try:
    from fastapi.testclient import TestClient
    CO_FASTAPI = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_FASTAPI = False

WEB = GOC / "scripts" / "control_center" / "web"
APP_JS = WEB / "app.js"
INDEX = WEB / "index.html"
STYLE = WEB / "style.css"


# ==========================================================================
# 1. Ô CÀI ĐẶT — kiểm giá trị
# ==========================================================================

class TestKiemThuMucGoc(unittest.TestCase):
    """Cài đặt DUY NHẤT quyết định Router tạo thư mục ở đâu."""

    def test_01_rong_la_hop_le_nghia_la_bo_thiet_lap(self):
        for x in ("", "   ", None):
            with self.subTest(x=x):
                self.assertEqual(kiem_thu_muc_goc(x), "")

    #: Một đường TUYỆT ĐỐI của HỆ ĐANG CHẠY.
    #:
    #: `GOC_MAC_DINH_WIN` (`C:\RouterProjects`) chỉ tuyệt đối trên Windows;
    #: trên Linux `Path("C:\\RouterProjects").is_absolute()` là `False`, nên
    #: `kiem_thu_muc_goc` từ chối nó — ĐÚNG như nó phải làm — và hai bài dưới
    #: đỏ ở runner CI dù không có gì hỏng. Hợp đồng cần kiểm là "đường tuyệt
    #: đối thì nhận", và hợp đồng đó đúng ở mọi nền; chỉ cái LITERAL là riêng
    #: của Windows.
    GOC_TUYET_DOI = (GOC_MAC_DINH_WIN if os.name == "nt"
                     else "/srv/RouterProjects")

    def test_02_nhan_duong_dan_tuyet_doi(self):
        self.assertEqual(kiem_thu_muc_goc(self.GOC_TUYET_DOI),
                         self.GOC_TUYET_DOI)

    def test_03_bo_dau_nhay_nguoi_dung_dan_tu_explorer(self):
        self.assertEqual(kiem_thu_muc_goc(f'"{self.GOC_TUYET_DOI}"'),
                         self.GOC_TUYET_DOI)

    def test_04_TU_CHOI_duong_tuong_doi(self):
        for x in ("RouterProjects", r"..\kho", "./x"):
            with self.subTest(x=x):
                with self.assertRaises(TaoDuAnLoi):
                    kiem_thu_muc_goc(x)

    def test_05_TU_CHOI_doan_hai_cham(self):
        with self.assertRaises(TaoDuAnLoi):
            kiem_thu_muc_goc(r"C:\Kho\..\Windows")

    def test_06_TU_CHOI_goc_o_dia(self):
        """`C:\\` biến phép kiểm containment thành phép luôn đúng."""
        with self.assertRaises(TaoDuAnLoi):
            kiem_thu_muc_goc("C:\\")

    def test_07_TU_CHOI_khi_tro_vao_mot_TEP(self):
        tmp = Path(tempfile.mkdtemp(prefix="goc-tep-"))
        try:
            t = tmp / "khong-phai-thu-muc.txt"
            t.write_text("x", encoding="utf-8")
            with self.assertRaises(TaoDuAnLoi):
                kiem_thu_muc_goc(str(t))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_08_thu_muc_CHUA_ton_tai_van_duoc_nhan(self):
        """Bắt người dùng đi mkdir trước là đúng cái phiền V0.9.2 xoá đi."""
        tmp = Path(tempfile.mkdtemp(prefix="goc-chua-"))
        try:
            d = tmp / "chua-co" / "o-day"
            self.assertEqual(kiem_thu_muc_goc(str(d)), str(d))
            self.assertFalse(d.exists(), "phép KIỂM không được chạm đĩa")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_09_TU_CHOI_duong_qua_dai(self):
        with self.assertRaises(TaoDuAnLoi):
            kiem_thu_muc_goc("C:\\" + "x" * 300)


# ==========================================================================
# 2. API — cài đặt đi qua ĐÚNG một cửa, và BỀN
# ==========================================================================

def _kho_git(goc: Path) -> None:
    (goc / "docs").mkdir(parents=True, exist_ok=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "t@local"],
              ["git", "config", "user.name", "t"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestApiCaiDatGoc(unittest.TestCase):

    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        from scripts.control_center.webapi import PhienWeb, dung_app
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-goc-"))
        self.kho = self.tmp / "kho"
        self.kho.mkdir()
        _kho_git(self.kho)
        self.cc = ControlCenter(root=self.tmp / "data", probe=False)
        self.cc.them_project(Project(project_id="p", name="P",
                                     repo_path=str(self.kho)))
        self.phien = PhienWeb(self.cc, token="kiem-thu", cong=8765)
        self.cl = TestClient(dung_app(self.phien),
                             base_url="http://127.0.0.1:8765")

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    @property
    def h(self):
        return {"X-CC-Token": self.phien.token}

    def _ghi(self, v):
        return self.cl.post("/api/ui", headers=self.h,
                            json={KHOA_THU_MUC_GOC: v})

    def test_10_ghi_va_doc_lai_duoc(self):
        d = str(self.tmp / "KhoDuAn")
        r = self._ghi(d)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()[KHOA_THU_MUC_GOC], d)
        self.assertEqual(
            self.cl.get("/api/ui", headers=self.h).json()[KHOA_THU_MUC_GOC], d)

    def test_11_gia_tri_HONG_bi_tu_choi_400_kem_cau_doc_duoc(self):
        r = self._ghi("kho-tuong-doi")
        self.assertEqual(r.status_code, 400)
        loi = r.json()["error"]
        self.assertIn("tương đối", loi)
        self.assertNotIn("Traceback", loi)
        self.assertIsNone(
            self.cl.get("/api/ui", headers=self.h).json().get(KHOA_THU_MUC_GOC),
            "giá trị hỏng KHÔNG được ghi vào sổ")

    def test_12_ben_qua_KHOI_DONG_LAI(self):
        """Cài đặt nằm ở sổ, không ở bộ nhớ tiến trình."""
        from scripts.control_center.engine import ControlCenter
        d = str(self.tmp / "SongSotKhoiDong")
        self.assertEqual(self._ghi(d).status_code, 200)
        self.cc.shutdown()
        cc2 = ControlCenter(root=self.tmp / "data", probe=False)
        try:
            self.assertEqual(cc2.store.cai_dat_ui().get(KHOA_THU_MUC_GOC), d)
        finally:
            cc2.shutdown()
            self.cc = cc2       # tearDown se shutdown lai, vo hai

    def test_13_XEM_TRUOC_theo_dung_cai_dat_vua_ghi(self):
        d = self.tmp / "GocMoi"
        self.assertEqual(self._ghi(str(d)).status_code, 200)
        r = self.cl.get("/api/project/create/preview?ten=Todo%20Dogfood",
                        headers=self.h).json()
        self.assertEqual(r["goc"], str(d))
        self.assertEqual(r["duong"], str(d / "Todo-Dogfood"))

    def test_14_doi_cai_dat_KHONG_doi_cho_du_an_da_nhan(self):
        """Bất biến chính: ô này chỉ là MẶC ĐỊNH cho dự án TẠO MỚI."""
        truoc = self.cc.store.project("p").repo_path
        self.assertEqual(self._ghi(str(self.tmp / "ChoKhac")).status_code, 200)
        self.assertEqual(self.cc.store.project("p").repo_path, truoc)
        self.assertTrue((self.kho / "docs" / "seed.md").is_file())

    def test_15_ghi_RONG_thi_quay_ve_mac_dinh(self):
        self.assertEqual(self._ghi(str(self.tmp / "Tam")).status_code, 200)
        self.assertEqual(self._ghi("").status_code, 200)
        r = self.cl.get("/api/project/create/preview?ten=X",
                        headers=self.h).json()
        self.assertEqual(r["goc"], GOC_MAC_DINH_WIN)

    def test_16_khoa_khac_van_di_qua_nhu_cu(self):
        """Thêm khoá mới không được làm hỏng danh sách CHO PHÉP cũ."""
        r = self.cl.post("/api/ui", headers=self.h, json={"fit": "contain"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["fit"], "contain")
        self.assertEqual(
            self.cl.post("/api/ui", headers=self.h,
                         json={"khong-biet": 1}).status_code, 400)


# ==========================================================================
# 3. GIAO DIỆN — những hỏng chỉ lộ ra lúc bấm
# ==========================================================================

class TestClickPath(unittest.TestCase):
    """Đọc `app.js`/`index.html` như một bài kiểm cấu trúc.

    Không có trình duyệt ở CI, nên ba hỏng ở đầu tệp này phải bắt được bằng
    phép đọc tĩnh — nếu không thì chỗ duy nhất bắt được chúng là ngón tay
    người dùng.
    """

    @classmethod
    def setUpClass(cls):
        cls.js = APP_JS.read_text(encoding="utf-8")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.css = STYLE.read_text(encoding="utf-8")

    # -- cu phap ----------------------------------------------------------
    def test_17_app_js_dung_cu_phap(self):
        r = subprocess.run(["node", "--check", str(APP_JS)],
                           capture_output=True, text=True)
        if r.returncode == 127 or "not found" in (r.stderr or "").lower():
            self.skipTest("không có node trên máy này")
        self.assertEqual(r.returncode, 0,
                         (r.stdout or "") + (r.stderr or ""))

    # -- id co that -------------------------------------------------------
    def _id_co_that(self):
        co = set(re.findall(r'id="([A-Za-z0-9_-]+)"', self.html))
        co |= set(re.findall(r'id="([A-Za-z0-9_-]+)"', self.js))
        co |= set(re.findall(r"id='([A-Za-z0-9_-]+)'", self.js))
        # id sinh dong: `id="viec-${x}"` -> chi lay tien to, bo qua
        co |= set(re.findall(r'id="([A-Za-z0-9_-]+)-\$\{', self.js))
        return co

    def test_18_moi_selector_id_deu_tro_toi_mot_id_CO_THAT(self):
        """`$('#o-chat')` thay vì `$('#o-soan')` không báo lỗi — nó chỉ im."""
        co = self._id_co_that()
        dong = {}
        for i, d in enumerate(self.js.splitlines(), 1):
            for m in re.finditer(r"""\$\(['"]#([A-Za-z0-9_-]+)['"]\)""", d):
                dong.setdefault(m.group(1), i)
        thieu = {k: v for k, v in dong.items() if k not in co}
        self.assertEqual(thieu, {},
                         f"selector trỏ tới id không tồn tại: {thieu}")

    def test_19_o_soan_la_id_dung_cua_o_chat(self):
        self.assertIn('id="o-soan"', self.html)
        self.assertNotIn("#o-chat", self.js)

    # -- pham vi ----------------------------------------------------------
    def _khoi_du_an_moi(self):
        i = self.js.index("du an moi ----")
        j = self.js.index("noi va lam moi --", i)
        return self.js[i:j]

    def _khoi_ma(self):
        """Khối trên, BỎ chú thích và nội dung template literal.

        Cần thiết vì cả hai chỗ đó đầy văn xuôi: chính chú thích của khối này
        nhắc tên `json()` và `toLowerCase()` (để giải thích hai lỗi cũ), và
        khối HTML chứa `thiểu (`, `<code>` — phép quét mã đọc phải chúng thì
        bài kiểm chỉ đo được văn xuôi của chính nó.
        """
        m = re.sub(r"`[^`]*`", "``", self._khoi_du_an_moi(), flags=re.S)
        return "\n".join(d for d in m.splitlines()
                         if not d.lstrip().startswith("//"))

    def test_20_moi_ham_khoi_du_an_moi_goi_deu_o_PHAM_VI_MODULE(self):
        """Hỏng #1: `json({ten})` — `json` là `const` trong một hàm KHÁC.

        Sai phạm vi không phải sai cú pháp, nên `node --check` xanh và lỗi
        chỉ nổ lúc bấm nút. Phép kiểm: mọi hàm khối này GỌI phải có khai báo
        ở cột 0 (phạm vi module) hoặc là hàm dựng sẵn của trình duyệt.
        """
        khoi = self._khoi_ma()
        dung_san = {
            "if", "for", "while", "switch", "catch", "return", "typeof",
            "async", "function", "setTimeout", "clearTimeout", "String", "Number",
            "Boolean", "Array", "Object", "JSON", "Error", "Date", "Math",
            "encodeURIComponent", "parseInt", "parseFloat", "console",
            "fetch", "await", "toggle", "close", "focus", "trim", "stringify",
        }
        mo_dun = set(re.findall(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
                                self.js, re.M))
        mo_dun |= set(re.findall(r"^(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
                                 self.js, re.M))
        cuc_bo = set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)",
                                khoi))
        la = set()
        for m in re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", khoi):
            t = m.group(1)
            if t in dung_san or t in mo_dun or t in cuc_bo:
                continue
            la.add(t)
        self.assertEqual(la, set(),
                         f"gọi hàm KHÔNG có ở phạm vi module: {sorted(la)}")

    # -- khong co ban sao thu hai cua logic dat ten ------------------------
    def test_21_JS_KHONG_tu_suy_project_id(self):
        """Hỏng #3: `slug()` sống ở backend, đã kiểm — JS không được chép."""
        khoi = self._khoi_ma()
        self.assertNotIn("toLowerCase()", khoi)
        self.assertNotIn("/api/project'", khoi,
                         "tab «Nhập repo» phải đi qua /api/project/adopt")
        for d in ("/api/project/create", "/api/project/adopt"):
            self.assertIn(d, khoi, f"thiếu lời gọi {d}")
        # Xem trước nằm trong một template literal (`?ten=${...}`) nên phải
        # tìm ở bản THÔ — `_khoi_ma()` đã bỏ ruột template đi.
        self.assertIn("/api/project/create/preview", self._khoi_du_an_moi())

    # -- hai tab, mac dinh la TAO MOI -------------------------------------
    def test_22_hai_tab_va_mac_dinh_la_tao_moi(self):
        khoi = self._khoi_du_an_moi()
        self.assertIn('id="np-tab-moi" class="np-tab-nut chon"', khoi,
                      "tab «Tạo mới» phải được chọn sẵn")
        self.assertIn('id="np-tab-nhap" class="np-tab-nut"', khoi)
        self.assertIn('id="np-pane-nhap" hidden', khoi,
                      "khung «Nhập repo» phải ẩn lúc mở")
        self.assertNotIn('id="np-pane-moi" hidden', khoi)

    def test_23_co_CSS_cho_tab_va_o_bao_loi(self):
        """Không có CSS thì hai tab trông y hệt nhau — nhầm tab là nhầm HÀNH VI."""
        for lop in (".np-tab", ".np-tab-nut", ".np-tab-nut.chon", ".np-loi"):
            self.assertIn(lop, self.css, f"thiếu kiểu cho {lop}")

    # -- thong bao loi -----------------------------------------------------
    def test_24_loi_hien_TRONG_hop_thoai_khong_phai_stack_trace(self):
        khoi = self._khoi_ma()
        self.assertIn("npLoi('#np-loi'", khoi)
        self.assertIn("npLoi('#np-loi2'", khoi)
        self.assertNotIn(".stack", khoi)
        self.assertNotIn("alert(", khoi, "dialog chặn cả phiên trình duyệt")

    def test_25_o_cai_dat_goc_co_mat_va_goi_dung_khoa(self):
        self.assertIn('id="cd-goc"', self.js)
        self.assertIn('id="cd-goc-luu"', self.js)
        self.assertIn(f"luuCaiDatUI({{ {KHOA_THU_MUC_GOC}:", self.js)

    def test_26_luuCaiDatUI_TRA_VE_ket_qua_chu_khong_nem_loi(self):
        """Hỏng #4: báo «đã lưu» cho một giá trị backend vừa TỪ CHỐI.

        `luuCaiDatUI` NUỐT lỗi (cố ý — một lần lưu hỏng không được làm gãy
        tay kéo thanh trượt). Nên `try { await luuCaiDatUI(...) } catch` là
        một phép kiểm KHÔNG BAO GIỜ chạy, và nhánh «thành công» chạy cho cả
        lần thất bại. Chỉ lộ ra trong trình duyệt — không một phép kiểm
        Python nào chạm tới nó.
        """
        i = self.js.index("async function luuCaiDatUI")
        than = self.js[i:self.js.index("\n}", i)]
        self.assertIn("return true", than)
        self.assertIn("return false", than)
        # Người gọi phải ĐỌC giá trị trả về, không được đoán bằng `catch`.
        j = self.js.index("#cd-goc-luu")
        goi = self.js[j:j + 700]
        self.assertIn(f"if (await luuCaiDatUI({{ {KHOA_THU_MUC_GOC}:", goi)


if __name__ == "__main__":
    unittest.main()
