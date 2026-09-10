"""V0.5 — endpoint `/api/live` và ô "TRẠNG THÁI SỐNG" ở giao diện.

Hai điều bị khoá lại ở đây, và cả hai đều là chỗ dễ tuột:

1. **Endpoint là CHỈ ĐỌC và nằm sau cùng bộ rào của V0.2** — token mọi
   request kể cả `GET`, kiểm `Host` trước kiểm token, không CORS. Một
   endpoint mới rất dễ được thêm mà quên phần đó.
2. **Giao diện KHÔNG được vẽ Router thành trạng thái dự án.** Ô SỐNG và
   ô Router phải đọc ra là hai thứ khác nhau, và một trường
   `UNKNOWN`/`UNAVAILABLE` KHÔNG được hiện ra một con số.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

APP_JS = GOC / "scripts" / "control_center" / "web" / "app.js"
INDEX = GOC / "scripts" / "control_center" / "web" / "index.html"
WEBAPI = GOC / "scripts" / "control_center" / "webapi.py"


def _ma_js(van: str) -> str:
    """Bỏ chú thích `//` trước khi phân tích — cùng lý do như bộ kiểm
    V0.4: tệp này GIẢI THÍCH lỗi cũ bằng cách nhắc lại đoạn mã sai."""
    return "\n".join(d for d in van.splitlines()
                     if not d.lstrip().startswith("//"))


class TestEndpointChiDoc(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        from scripts.control_center.webapi import PhienWeb, dung_app
        self.goc = Path(tempfile.mkdtemp(prefix="cc-live-api-"))
        self.cc = ControlCenter(root=self.goc, probe=False)
        self.addCleanup(self.cc.store.close)
        self.cc.store.luu_project(Project(project_id="p", name="P",
                                          repo_path=str(self.goc)))
        self.phien = PhienWeb(self.cc, token="TOK-LIVE", cong=45999)
        self.c = TestClient(dung_app(self.phien))
        self.h = {"X-CC-Token": "TOK-LIVE", "Host": "127.0.0.1:45999"}

    def test_doi_token_ke_ca_GET(self):
        """Trình duyệt cho gửi request cross-origin; không có token thì
        một trang web bất kỳ đang mở đọc được trạng thái production."""
        r = self.c.get("/api/live?project=p",
                       headers={"Host": "127.0.0.1:45999"})
        self.assertEqual(r.status_code, 401)

    def test_kiem_Host_TRUOC_kiem_token(self):
        r = self.c.get("/api/live?project=p",
                       headers={"X-CC-Token": "TOK-LIVE",
                                "Host": "ke-tan-cong.example.com"})
        self.assertIn(r.status_code, (400, 403))

    def test_tra_ve_anh_chup_co_ROUTER_TACH_RIENG(self):
        r = self.c.get("/api/live?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for k in ("project_id", "thu_luc", "tuoi", "trang_thai_chung",
                  "co_bang_chung_song", "router", "dich_vu", "luu_tru",
                  "ung_dung", "kho"):
            self.assertIn(k, d, k)
        # ROUTER la mot nhom RIENG, khong tron vao `dich_vu`.
        self.assertIn("router", d["router"])
        self.assertNotIn("router", d["dich_vu"])

    def test_thieu_project_thi_400(self):
        self.assertEqual(
            self.c.get("/api/live", headers=self.h).status_code, 400)

    def test_KHONG_co_phuong_thuc_ghi_tren_duong_live(self):
        for pt in ("post", "put", "delete", "patch"):
            with self.subTest(pt=pt):
                r = getattr(self.c, pt)("/api/live?project=p", headers=self.h)
                self.assertIn(r.status_code, (404, 405))

    def test_capabilities_liet_ke_provider(self):
        r = self.c.get("/api/live/capabilities?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("router", d)
        self.assertIn("git", d)

    def test_khong_lo_duong_dan_khoa_ra_payload(self):
        """Đường dẫn khoá không phải bí mật, nhưng cũng không có lý do gì
        để nó đi ra API — và `.pem` trong payload là thứ đầu tiên một
        người soi log sẽ hỏi."""
        r = self.c.get("/api/live?project=p", headers=self.h)
        tho = json.dumps(r.json())
        for x in ("PRIVATE KEY", "fanficappwrite", ".pem"):
            self.assertNotIn(x, tho, x)

    def test_endpoint_khong_nam_trong_api_state(self):
        """`/api/state` bị WebSocket gọi mỗi nhịp. Nhét probe SSH vào đó
        là biến một ô quan sát thành một trận spam SSH vào production."""
        src = WEBAPI.read_text(encoding="utf-8")
        i = src.index('@app.get("/api/state")')
        j = src.index('@app.get("/api/usage")')
        self.assertNotIn("quan_sat", src[i:j])


class TestOSongTrenGiaoDien(unittest.TestCase):
    def setUp(self):
        self.js = _ma_js(APP_JS.read_text(encoding="utf-8"))
        self.html = INDEX.read_text(encoding="utf-8")

    def test_co_o_SONG_rieng_va_nhan_ROUTER_rieng(self):
        self.assertIn('id="the-song"', self.html)
        self.assertIn('id="insp-song"', self.html)
        # O Router phai duoc dan nhan ROUTER, de khong ai doc no thanh
        # trang thai cua he thong ngoai.
        i = self.html.index('id="insp-dangchay"')
        self.assertIn("ROUTER", self.html[max(0, i - 300):i])

    def test_co_nut_lam_moi_tay_va_chi_bao_do_tuoi(self):
        self.assertIn('id="nut-song-lai"', self.html)
        self.assertIn('id="song-tuoi"', self.html)
        self.assertIn("nut-song-lai').onclick", self.js)

    def test_KHONG_ve_gia_tri_cho_o_khong_do_duoc(self):
        """`UNKNOWN`/`UNAVAILABLE` phải hiện ra CHỮ trạng thái, không
        phải một con số — một `0` ở đó là khẳng định về production."""
        i = self.js.index("function veSongTuCache(")
        than = self.js[i:i + 2600]
        self.assertIn("doDuoc", than)
        self.assertIn("'ACTIVE', 'DEGRADED', 'DOWN'", than)

    def test_lam_moi_o_luong_NEN_khong_chan_giao_dien(self):
        """`veSong` là `async` và đi qua `api()` — không có lời gọi đồng
        bộ nào chặn vòng vẽ."""
        self.assertIn("async function veSong(", self.js)
        i = self.js.index("async function veSong(")
        than = self.js[i:i + 900]
        self.assertIn("await api(", than)

    def test_nhip_lam_moi_CHAM_va_co_dieu_kien(self):
        """Mỗi lần là một phiên SSH thật ra máy production."""
        self.assertIn("veSong(); }, 90000)", self.js.replace("\n", " ")
                      .replace("  ", " ") or self.js)

    def test_doi_du_an_thi_BO_cache_song(self):
        i = self.js.index("if (t.dataset.pid)")
        than = self.js[i:i + 420]
        self.assertIn("songCache = null", than)
        self.assertIn("veSong()", than)

    def test_loi_probe_KHONG_lam_vo_o(self):
        i = self.js.index("async function veSong(")
        than = self.js[i:i + 1200]
        self.assertIn("catch", than)
        self.assertIn("không đo được", than)

    def test_veHet_ve_lai_tu_CACHE_khong_goi_mang(self):
        """Vòng vẽ chạy mỗi nhịp WebSocket. Nếu nó gọi `/api/live` thì
        mỗi giây một phiên SSH."""
        i = self.js.index("function veHet(")
        than = self.js[i:i + 900]
        self.assertIn("veSongTuCache()", than)
        self.assertNotIn("veSong()", than)


if __name__ == "__main__":
    unittest.main(verbosity=2)
