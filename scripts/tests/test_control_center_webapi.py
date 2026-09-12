"""Ranh giới an toàn của API cục bộ — CI cưỡng chế.

Một localhost server KHÔNG phải là riêng tư, và đó là điều tệp này tồn tại
để canh. Ba lớp, mỗi lớp một nhóm bài kiểm:

    token       mọi trang web bạn đang mở đều GỬI được request tới
                127.0.0.1; không có token thì một quảng cáo ở tab khác
                `POST /api/chat` được và điều khiển Router của bạn
    Host        DNS rebinding: một tên miền của kẻ tấn công trỏ về
                127.0.0.1 sẽ đi vòng qua phép kiểm origin
    bind        `127.0.0.1` chứ không `0.0.0.0` — một ký tự khác biệt giữa
                "công cụ cá nhân" và "mở cổng ra mạng LAN"

Dùng `TestClient` của Starlette: nó gọi ASGI app trực tiếp, nên không mở
cổng thật và không phụ thuộc mạng — chạy được trên CI Linux.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

try:
    from fastapi.testclient import TestClient
    CO_FASTAPI = True
except ModuleNotFoundError:                                 # pragma: no cover
    CO_FASTAPI = False

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
PDF = b"%PDF-1.7\n" + b"x" * 96


def _kho_git(goc: Path) -> None:
    (goc / "docs").mkdir(parents=True, exist_ok=True)
    (goc / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    for c in (["git", "init", "-q"],
              ["git", "config", "user.email", "t@local"],
              ["git", "config", "user.name", "t"],
              ["git", "add", "-A"], ["git", "commit", "-q", "-m", "seed"]):
        subprocess.run(c, cwd=goc, check=True, capture_output=True)


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class _Nen(unittest.TestCase):
    def setUp(self):
        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project
        from scripts.control_center.webapi import PhienWeb, dung_app
        self.goc = Path(tempfile.mkdtemp(prefix="cc-web-"))
        _kho_git(self.goc)
        self.cc = ControlCenter(root=self.goc, probe=False)
        self.cc.them_project(Project(project_id="p", name="P",
                                     repo_path=str(self.goc)))
        self.phien = PhienWeb(self.cc, token="TOKEN-THU-NGHIEM", cong=8765)
        self.app = dung_app(self.phien)
        self.cl = TestClient(self.app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        shutil.rmtree(self.goc, ignore_errors=True)

    @property
    def h(self):
        return {"X-CC-Token": self.phien.token}


class TestSuyLuanV08(_Nen):
    """§12 — định tuyến giải thích được, và §4 — chế độ chất lượng BỀN."""

    def test_doc_dinh_tuyen_khong_do_han_muc(self):
        r = self.cl.get("/api/reasoning?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["che_do"], "AUTO")
        self.assertEqual(d["che_do_hop_le"], ["ECO", "AUTO", "STRONG", "MAX"])
        self.assertFalse(d["da_do_han_muc"],
                         "không được gọi CLI nhà cung cấp khi chưa ai bấm")
        self.assertEqual(d["han_muc_do_duoc"], {})
        self.assertEqual(len(d["vai"]), 3)

    def test_thieu_project_thi_400(self):
        self.assertEqual(
            self.cl.get("/api/reasoning", headers=self.h).status_code, 400)

    def test_chinh_sach_cao_cap_FAIL_CLOSED_khi_khong_co_ky_uc(self):
        d = self.cl.get("/api/reasoning?project=p", headers=self.h).json()
        cs = d["chinh_sach_cao_cap"]
        self.assertTrue(cs["han_che"])
        self.assertNotEqual(cs["nguon"], "ky_uc")

    def test_han_muc_khong_doc_duoc_thi_None_khong_phai_0(self):
        d = self.cl.get("/api/reasoning?project=p", headers=self.h).json()
        for n in d["nang_luc"]:
            with self.subTest(p=n["placement"]):
                self.assertTrue(n["quota_con_lai"] is None
                                or isinstance(n["quota_con_lai"], (int, float)))

    def test_doi_che_do_BEN(self):
        r = self.cl.post("/api/reasoning/mode",
                         json={"project": "p", "che_do": "MAX"}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["che_do"], "MAX")
        # BEN: doc lai tu so, khong tu bo nho cua mot lan goi.
        self.assertEqual(
            self.cl.get("/api/reasoning?project=p", headers=self.h).json()["che_do"],
            "MAX")
        self.assertEqual(self.cc.leader_ban_ghi("p").che_do, "MAX")

    def test_che_do_LA_thi_400_khong_am_tham_ve_AUTO(self):
        """Một chế độ gõ sai không được lặng lẽ thành AUTO — người dùng sẽ
        tưởng họ đang ở MAX."""
        r = self.cl.post("/api/reasoning/mode",
                         json={"project": "p", "che_do": "TURBO"},
                         headers=self.h)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.cc.leader_ban_ghi("p").che_do, "AUTO")

    def test_snapshot_mang_ban_GON_cua_dinh_tuyen(self):
        d = self.cl.get("/api/state?project=p", headers=self.h).json()
        self.assertIn("suy_luan", d)

    def test_che_do_di_theo_NHIP_NHANH_cua_state(self):
        """Đo bằng Chrome thật: thanh trên chỉ đồng bộ ở đường ảnh chụp `git`
        (bộ đệm 30s), nên đổi chế độ ở một tab không hiện ra ở tab kia."""
        self.assertEqual(
            self.cl.get("/api/state?project=p", headers=self.h).json()["che_do"],
            "AUTO")
        self.cl.post("/api/reasoning/mode",
                     json={"project": "p", "che_do": "MAX"}, headers=self.h)
        self.assertEqual(
            self.cl.get("/api/state?project=p", headers=self.h).json()["che_do"],
            "MAX")

    def test_dinh_tuyen_di_qua_bo_loc_bi_mat(self):
        r = self.cl.get("/api/reasoning?project=p", headers=self.h)
        self.assertNotIn(self.phien.token, r.text)


class TestTokenBatBuoc(_Nen):
    """Không token thì 401 — kể cả `GET`."""

    DUONG_GET = ("/api/state", "/api/usage", "/api/task/p.t1/log",
                 # V0.8 — dinh tuyen suy luan. `/api/reasoning` doc ra ca ten
                 # model, chinh sach du an va han muc do duoc; mot trang web
                 # bat ky KHONG duoc doc no.
                 "/api/reasoning",
                 # V0.9 — vong kin. `/api/execution` doc ra muc tieu, ke
                 # hoach, bang chung va lich su ban ke hoach cua mot du an
                 # that; `/api/executions` liet ke moi muc tieu dang chay.
                 "/api/executions", "/api/execution?id=ex_1")
    DUONG_POST = ("/api/chat", "/api/task/p.t1/pause",
                  "/api/task/p.t1/resume", "/api/task/p.t1/stop",
                  "/api/task/p.t1/approve", "/api/project",
                  # V0.8 — doi che do chat luong la mot thao tac GHI: no doi
                  # model nao chay cho moi luot sau do.
                  "/api/reasoning/mode",
                  # V0.9 — `approve` la duong DUY NHAT mo mot cong tham
                  # quyen NGOAI KHO. Neu no khong doi token thi mot trang web
                  # bat ky dang mo co the duyet mot lan deploy production.
                  # Day la tuyen nhay cam nhat ma v0.9 them vao.
                  "/api/execution/ex_1/approve",
                  "/api/execution/ex_1/pause",
                  "/api/execution/ex_1/resume",
                  "/api/execution/ex_1/cancel")

    def test_GET_khong_token_thi_401(self):
        for d in self.DUONG_GET:
            with self.subTest(duong=d):
                self.assertEqual(self.cl.get(d).status_code, 401)

    def test_POST_khong_token_thi_401(self):
        """Đây là bài quan trọng nhất của tệp.

        Trình duyệt cho phép gửi request cross-origin (nó chỉ ngăn *đọc*
        phản hồi). Nên nếu `POST /api/chat` không đòi token, một trang web
        bất kỳ bạn đang mở có thể tạo việc trong Router của bạn — và bạn
        sẽ không thấy request đó ở đâu cả.
        """
        for d in self.DUONG_POST:
            with self.subTest(duong=d):
                r = self.cl.post(d, json={"project_id": "p", "text": "x"})
                self.assertEqual(r.status_code, 401, f"{d} không đòi token")

    def test_tai_len_khong_token_thi_401(self):
        r = self.cl.post("/api/attachments",
                         data={"project_id": "p"},
                         files={"file": ("a.png", PNG, "image/png")})
        self.assertEqual(r.status_code, 401)

    def test_xoa_dinh_kem_khong_token_thi_401(self):
        self.assertEqual(
            self.cl.delete("/api/attachments/att_x").status_code, 401)

    def test_blob_khong_token_thi_401(self):
        """Đọc byte tệp phải đòi token — nếu không, một trang khác có thể
        rút ảnh chụp màn hình bạn vừa dán."""
        self.assertEqual(
            self.cl.get("/api/attachments/att_x/blob").status_code, 401)

    def test_token_SAI_thi_401(self):
        r = self.cl.get("/api/state", headers={"X-CC-Token": "sai-be-bet"})
        self.assertEqual(r.status_code, 401)

    def test_token_DUNG_thi_200(self):
        self.assertEqual(self.cl.get("/api/state", headers=self.h)
                         .status_code, 200)

    def test_token_qua_query_cung_duoc(self):
        """WebSocket không đặt được header, nên query cũng phải chấp nhận."""
        r = self.cl.get(f"/api/state?t={self.phien.token}")
        self.assertEqual(r.status_code, 200)

    def test_so_sanh_token_theo_THOI_GIAN_HANG(self):
        """Dùng `hmac.compare_digest`, không dùng `==`.

        Với một bí mật cục bộ thì rủi ro timing là thấp, nhưng đây là chỗ
        không có lý do gì để làm sai: `compare_digest` không đắt hơn.
        """
        import ast
        ma = (GOC / "scripts" / "control_center" / "webapi.py").read_text(
            encoding="utf-8")
        cay = ast.parse(ma)
        goi = [n for n in ast.walk(cay)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "compare_digest"]
        self.assertTrue(goi, "không dùng hmac.compare_digest")

    def test_trang_goc_va_tep_tinh_KHONG_doi_token(self):
        """Trình duyệt phải tải được HTML/JS TRƯỚC khi nó biết token.

        Chúng không chứa dữ liệu nào, nên miễn token là đúng — nhưng phải
        là *chỉ* chúng.
        """
        self.assertEqual(self.cl.get("/").status_code, 200)


class TestVongKinV09(_Nen):
    """§20 + §23 — bề mặt thực thi qua HTTP, và cổng thẩm quyền của nó."""

    def _mot_lan(self, goal: str = "sửa docs cho gọn"):
        from scripts.control_center.execution import ke_hoach as KH
        from scripts.control_center.execution import y_dinh as YD
        y = YD.tao_y_dinh(project_id="p", goal=goal, cau_nguoi_dung=goal)
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(KH.BuocKeHoach(buoc_id="b1", tieu_de="b1",
                                 muc_tieu="khảo sát docs"),))
        return self.cc.dieu_phoi("p").bat_dau(y, kh)

    def test_liet_ke_va_anh_chup(self):
        y = self._mot_lan()
        r = self.cl.get("/api/executions?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(x["execution_id"] == y.execution_id
                            for x in r.json()["ket_qua"]))
        d = self.cl.get(f"/api/execution?id={y.execution_id}",
                        headers=self.h).json()
        for k in ("y_dinh", "ke_hoach", "buoc", "ban_ke_hoach", "su_kien",
                  "tien_do", "ngan_sach", "chi_phi"):
            self.assertIn(k, d, k)

    def test_id_khong_co_thi_404(self):
        self.assertEqual(
            self.cl.get("/api/execution?id=ex_khong_ton_tai",
                        headers=self.h).status_code, 404)

    def test_snapshot_mang_phan_gon(self):
        y = self._mot_lan()
        d = self.cl.get("/api/state?project=p", headers=self.h).json()
        self.assertTrue(any(x["execution_id"] == y.execution_id
                            for x in d.get("thuc_thi") or []))

    def test_tam_dung_va_tiep_tuc(self):
        y = self._mot_lan()
        eid = y.execution_id
        self.assertEqual(
            self.cl.post(f"/api/execution/{eid}/pause", headers=self.h)
            .json()["y_dinh"]["trang_thai"], "PAUSED")
        self.cl.post(f"/api/execution/{eid}/resume", headers=self.h)
        self.assertNotEqual(
            self.cc.so_thuc_thi.y_dinh(eid).trang_thai.value, "PAUSED")

    def test_huy_giu_bang_chung(self):
        y = self._mot_lan()
        eid = y.execution_id
        r = self.cl.post(f"/api/execution/{eid}/cancel", headers=self.h,
                         json={"ly_do": "đổi hướng"})
        self.assertEqual(r.json()["y_dinh"]["trang_thai"], "CANCELLED")
        self.assertTrue(self.cc.so_thuc_thi.buoc(eid))
        self.assertTrue(self.cc.so_thuc_thi.su_kien(eid))

    def test_cong_tham_quyen_KHONG_tu_mo(self):
        """Đường DUY NHẤT mở cổng NGOÀI KHO — và nó phải cần một POST rõ ràng."""
        y = self._mot_lan("deploy lên production")
        eid = y.execution_id
        self.assertEqual(y.trang_thai.value, "WAITING_AUTHORITY")
        self.assertEqual(y.duyet.value, "CHO_NGUOI")
        # Doc trang thai, goi tick, xem anh chup — KHONG cai nao mo duoc cong.
        self.cl.get("/api/executions?project=p", headers=self.h)
        self.cl.get(f"/api/execution?id={eid}", headers=self.h)
        self.cc.tick()
        self.assertEqual(
            self.cc.so_thuc_thi.y_dinh(eid).duyet.value, "CHO_NGUOI")
        r = self.cl.post(f"/api/execution/{eid}/approve", headers=self.h,
                         json={"dong_y": True, "boi": "user"})
        self.assertEqual(r.json()["y_dinh"]["duyet"], "DA_DUYET")

    def test_tu_choi_cong_thi_CANCELLED(self):
        y = self._mot_lan("deploy lên production")
        r = self.cl.post(f"/api/execution/{y.execution_id}/approve",
                         headers=self.h, json={"dong_y": False})
        self.assertEqual(r.json()["y_dinh"]["trang_thai"], "CANCELLED")

    def test_loi_tra_ve_400_chu_khong_no(self):
        r = self.cl.post("/api/execution/ex_khong_co/pause", headers=self.h)
        self.assertEqual(r.status_code, 400)


class TestChanDNSRebinding(_Nen):
    """`Host` lạ thì từ chối, dù token có đúng."""

    def test_Host_la_thi_400_du_token_DUNG(self):
        for host in ("evil.example.com", "attacker.test",
                     "cc.local.attacker.com"):
            with self.subTest(host=host):
                r = self.cl.get("/api/state",
                                headers={**self.h, "Host": host})
                self.assertEqual(r.status_code, 400,
                                 f"Host {host!r} phải bị từ chối")

    def test_kiem_Host_TRUOC_khi_kiem_token(self):
        """Host lạ + token SAI vẫn phải là 400 (Host), không phải 401.

        Thứ tự này quan trọng: chính việc token *có thể* đúng là điều đang
        được phòng, nên đừng để phép kiểm token quyết định trước.
        """
        r = self.cl.get("/api/state",
                        headers={"X-CC-Token": "sai", "Host": "evil.test"})
        self.assertEqual(r.status_code, 400)

    def test_127_va_localhost_deu_duoc(self):
        for host in ("127.0.0.1:8765", "localhost:8765", "127.0.0.1"):
            with self.subTest(host=host):
                r = self.cl.get("/api/state",
                                headers={**self.h, "Host": host})
                self.assertEqual(r.status_code, 200)


class TestKhongCORS(_Nen):
    """Cố ý KHÔNG có CORS. Frontend là same-origin nên nó không cần."""

    def test_khong_co_header_Access_Control_Allow_Origin(self):
        r = self.cl.get("/api/state", headers={**self.h,
                                               "Origin": "https://evil.test"})
        self.assertNotIn("access-control-allow-origin",
                         {k.lower() for k in r.headers})

    def test_middleware_CORS_KHONG_duoc_gan(self):
        import ast
        ma = (GOC / "scripts" / "control_center" / "webapi.py").read_text(
            encoding="utf-8")
        self.assertNotIn("CORSMiddleware", ma)
        cay = ast.parse(ma)
        ten = []
        for n in ast.walk(cay):
            if isinstance(n, ast.ImportFrom) and n.module:
                ten += [a.name for a in n.names]
        self.assertNotIn("CORSMiddleware", ten)


class TestChiBindLocalhost(unittest.TestCase):
    """`127.0.0.1`, không bao giờ `0.0.0.0`."""

    @staticmethod
    def _ma_chay_duoc(p: Path) -> str:
        """Mã nguồn ĐÃ BỎ chú thích và docstring.

        Grep thô sẽ báo động vì chính docstring GIẢI THÍCH luật ("không bao
        giờ `0.0.0.0`") — cùng cái bẫy đã gặp ở `cc_agent_tool`, nơi một
        phép grep báo động vì đúng câu nói mã đó an toàn.
        """
        import ast
        cay = ast.parse(p.read_text(encoding="utf-8"))
        # Bo docstring cua module/lop/ham.
        for n in ast.walk(cay):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)):
                if (n.body and isinstance(n.body[0], ast.Expr)
                        and isinstance(n.body[0].value, ast.Constant)
                        and isinstance(n.body[0].value.value, str)):
                    n.body = n.body[1:] or [ast.Pass()]
        return ast.unparse(ast.fix_missing_locations(cay))

    def test_ma_CHAY_DUOC_KHONG_chua_0_0_0_0(self):
        for ten in ("webapi.py", "webmain.py"):
            p = GOC / "scripts" / "control_center" / ten
            if not p.is_file():
                continue
            with self.subTest(tep=ten):
                self.assertNotIn("0.0.0.0", self._ma_chay_duoc(p),
                                 f"{ten} bind ra ngoài localhost")

    def test_webmain_bind_dung_127(self):
        p = GOC / "scripts" / "control_center" / "webmain.py"
        if not p.is_file():
            self.skipTest("chưa có webmain.py")
        self.assertIn('"127.0.0.1"', p.read_text(encoding="utf-8"))


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestKhongRoBiMat(_Nen):
    """Payload đi ra không được mang thứ giống credential."""

    def test_state_di_qua_bo_loc_bi_mat(self):
        self.cc.store.them_chat(
            "p", "user",
            "token cua toi la ghp_AbCdEfGhIjKlMnOpQrStUvWxYz012345 nhe")
        r = self.cl.get("/api/state?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("ghp_AbCdEfGhIjKlMnOpQrStUvWxYz012345", r.text)

    def test_token_phien_KHONG_nam_trong_payload_state(self):
        r = self.cl.get("/api/state?project=p", headers=self.h)
        self.assertNotIn(self.phien.token, r.text)

    def test_khong_co_trang_docs_liet_ke_API(self):
        for d in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(duong=d):
                self.assertIn(self.cl.get(d).status_code, (401, 404))


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestDinhKemQuaHTTP(_Nen):
    """Tái dùng toàn bộ tầng đính kèm — API chỉ là một cửa vào nữa."""

    def _tai_len(self, ten: str, noi: bytes):
        return self.cl.post("/api/attachments", headers=self.h,
                            data={"project_id": "p"},
                            files={"file": (ten, noi,
                                            "application/octet-stream")})

    def test_tai_len_anh_roi_lay_lai_dung_BYTE(self):
        r = self._tai_len("anh.png", PNG)
        self.assertEqual(r.status_code, 200, r.text)
        dk = r.json()
        self.assertEqual(dk["media_type"], "image")
        b = self.cl.get(f"/api/attachments/{dk['attachment_id']}/blob",
                        headers=self.h)
        self.assertEqual(b.status_code, 200)
        self.assertEqual(b.content, PNG, "byte lấy về không khớp byte gửi lên")

    def test_bam_va_kich_co_KHOP(self):
        import hashlib
        dk = self._tai_len("a.pdf", PDF).json()
        self.assertEqual(dk["sha256"], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(dk["size_bytes"], len(PDF))

    def test_loai_NGOAI_allowlist_bi_tu_choi_400(self):
        r = self._tai_len("evil.exe", b"MZ\x90\x00" + b"\x00" * 64)
        self.assertEqual(r.status_code, 400)
        self.assertIn("không nằm trong danh sách", r.json()["error"])

    def test_duoi_tep_KHONG_khop_noi_dung_bi_tu_choi(self):
        r = self._tai_len("anh.png", b"MZ\x90\x00" + b"\x00" * 64)
        self.assertEqual(r.status_code, 400)
        self.assertIn("không khớp", r.json()["error"])

    def test_ten_tep_co_DUONG_DAN_khong_thoat_ra_duoc(self):
        r = self._tai_len(r"..\..\..\Windows\System32\evil.png", PNG)
        self.assertEqual(r.status_code, 200, r.text)
        dk = r.json()
        self.assertNotIn("..", dk["filename"])
        self.assertNotIn("System32", dk["rel_path"])
        self.assertTrue(dk["rel_path"].startswith("objects/"))

    def test_blob_cua_ma_KHONG_TON_TAI_thi_404(self):
        r = self.cl.get("/api/attachments/att_khong_co/blob", headers=self.h)
        self.assertEqual(r.status_code, 404)

    def test_KHONG_co_tham_so_duong_dan_nao_o_endpoint_blob(self):
        """Đọc byte chỉ đi qua `attachment_id`.

        Không có tham số path nào để chen `../` vào — phép kiểm nằm ở
        `KhoDinhKem.duong_dan()`, một chỗ duy nhất, và có bài kiểm riêng
        ở `test_control_center_attachments.py`.
        """
        import ast
        ma = (GOC / "scripts" / "control_center" / "webapi.py").read_text(
            encoding="utf-8")
        self.assertIn('"/api/attachments/{attachment_id}/blob"', ma)
        cay = ast.parse(ma)
        for n in ast.walk(cay):
            # `async def` la `AsyncFunctionDef`, KHONG phai `FunctionDef` —
            # ban dau chi tim `FunctionDef` nen bai kiem "khong tim thay
            # endpoint" va bao hong ma khong noi gi ve an toan.
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "blob"):
                ten = [a.arg for a in n.args.args]
                self.assertEqual(ten, ["attachment_id"],
                                 f"endpoint blob nhận thêm tham số: {ten}")
                break
        else:
            self.fail("không tìm thấy endpoint blob")

    def test_blob_co_nosniff(self):
        """Không để trình duyệt tự đoán một `.txt` thành HTML rồi chạy nó."""
        dk = self._tai_len("a.txt", b"xin chao").json()
        r = self.cl.get(f"/api/attachments/{dk['attachment_id']}/blob",
                        headers=self.h)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")

    def test_xoa_dinh_kem_thi_blob_mat_theo(self):
        dk = self._tai_len("a.png", PNG).json()
        aid = dk["attachment_id"]
        self.assertEqual(
            self.cl.delete(f"/api/attachments/{aid}",
                           headers=self.h).status_code, 200)
        self.assertEqual(
            self.cl.get(f"/api/attachments/{aid}/blob",
                        headers=self.h).status_code, 404)


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestChatVaQuyenAgent(_Nen):
    """Đính kèm gửi qua web phải tới đúng việc, y như đường Qt."""

    def test_gui_chat_kem_dinh_kem_thi_agent_duoc_cap(self):
        dk = self.cl.post("/api/attachments", headers=self.h,
                          data={"project_id": "p"},
                          files={"file": ("a.png", PNG, "image/png")}).json()
        r = self.cl.post("/api/chat", headers=self.h, json={
            "project_id": "p",
            "text": "update docs/seed.md with one line",
            "attachment_ids": [dk["attachment_id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        viec = self.cc.store.tasks("p")
        self.assertTrue(viec)
        for t in viec:
            with self.subTest(task=t.task_id):
                ds = self.cc.dinh_kem.cho_agent(t.task_id)
                self.assertEqual([x.attachment_id for x in ds],
                                 [dk["attachment_id"]])
        self.assertEqual(self.cc.dinh_kem.cho_agent("p.khong_lien_quan"), [])

    def test_ma_dinh_kem_cua_DU_AN_KHAC_bi_bo_qua(self):
        """FAIL CLOSED: frontend chỉ gửi mã, và mã lạ không được cấp."""
        from scripts.control_center.model import Project
        self.cc.them_project(Project(project_id="q", name="Q",
                                     repo_path=str(self.goc)))
        dk = self.cl.post("/api/attachments", headers=self.h,
                          data={"project_id": "q"},
                          files={"file": ("a.png", PNG, "image/png")}).json()
        self.cl.post("/api/chat", headers=self.h, json={
            "project_id": "p", "text": "update docs/seed.md with one line",
            "attachment_ids": [dk["attachment_id"]]})
        for t in self.cc.store.tasks("p"):
            with self.subTest(task=t.task_id):
                self.assertEqual(self.cc.dinh_kem.cho_agent(t.task_id), [])
        kinds = [e["kind"] for e in self.cc.store.su_kien(limit=50)]
        self.assertIn("ATTACHMENT_REJECTED", kinds)

    def test_chat_rong_va_khong_dinh_kem_thi_400(self):
        r = self.cl.post("/api/chat", headers=self.h,
                         json={"project_id": "p", "text": "   "})
        self.assertEqual(r.status_code, 400)

    def test_state_mang_theo_dinh_kem_theo_tin_nhan(self):
        dk = self.cl.post("/api/attachments", headers=self.h,
                          data={"project_id": "p"},
                          files={"file": ("a.png", PNG, "image/png")}).json()
        self.cl.post("/api/chat", headers=self.h, json={
            "project_id": "p", "text": "xem anh nay",
            "attachment_ids": [dk["attachment_id"]]})
        d = self.cl.get("/api/state?project=p", headers=self.h).json()
        gom = d.get("attachments_by_message") or {}
        self.assertTrue(gom, "state không mang đính kèm nào")
        moi = [x for ds in gom.values() for x in ds]
        self.assertIn(dk["attachment_id"],
                      [x["attachment_id"] for x in moi])


@unittest.skipUnless(CO_FASTAPI, "chưa cài fastapi")
class TestWebSocket(_Nen):
    #: `TestClient` gui `Host: testserver` cho WebSocket BAT KE `base_url`
    #: — da do. Nen phai dat Host tuong minh; KHONG noi long phep kiem Host
    #: cua san pham cho tien bo kiem.
    HDR = {"host": "127.0.0.1:8765"}

    def test_khong_token_thi_bi_dong(self):
        with self.assertRaises(Exception):
            with self.cl.websocket_connect("/ws", headers=self.HDR) as s:
                s.receive_text()

    def test_Host_LA_thi_bi_dong_du_token_DUNG(self):
        """Phát hiện được nhờ chính bộ kiểm: `TestClient` gửi
        `Host: testserver`, và server đã từ chối — đúng như phải vậy.

        Nếu WebSocket không kiểm Host thì nó thành lỗ để đi vòng qua toàn
        bộ lớp phòng DNS rebinding của phía HTTP.
        """
        with self.assertRaises(Exception):
            with self.cl.websocket_connect(
                    f"/ws?t={self.phien.token}",
                    headers={"host": "evil.example.com"}) as s:
                s.receive_text()

    def test_token_dung_thi_nhan_duoc_trang_thai(self):
        with self.cl.websocket_connect(
                f"/ws?t={self.phien.token}&project=p",
                headers=self.HDR) as s:
            goi = json.loads(s.receive_text())
        self.assertEqual(goi["kind"], "state")
        self.assertIn("tasks", goi["data"])

    def test_trang_thai_qua_ws_cung_di_qua_bo_loc_bi_mat(self):
        self.cc.store.them_chat(
            "p", "user", "key ghp_ZzYyXxWwVvUuTtSsRrQqPpOoNn123456 day")
        with self.cl.websocket_connect(
                f"/ws?t={self.phien.token}&project=p",
                headers=self.HDR) as s:
            tho = s.receive_text()
        self.assertNotIn("ghp_ZzYyXxWwVvUuTtSsRrQqPpOoNn123456", tho)


if __name__ == "__main__":
    unittest.main()
