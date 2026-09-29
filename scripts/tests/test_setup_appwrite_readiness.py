"""
`scripts/setup_appwrite.py` — cho SAN SANG that su cua thuoc tinh/index,
khong chi "da ton tai".

Su co that (2026-08-21, self-host PROD): job nen tao `profiles.user_id` bi
Appwrite danh dau "failed" trong hang doi (Utopia queue), khong co co che tu
dong thu lai. Thuoc tinh ket vinh vien o "processing". Ham cu
(`_doi_thuoc_tinh_san_sang`) chi cho khi CO thuoc tinh MOI trong lan chay
hien tai, va im lang bo qua sau khi het luot thu — nen lan chay lai nao cung
thay thuoc tinh "da co" va khong bao gio phat hien no khong dung duoc, cho
toi khi `_ensure_index` that bai voi loi 400 mo ho "not yet available".

Cac test o day dung mock truc tiep `Setup._call` (khong goi mang that) de
tai hien tung tinh huong trang thai ma khong can Appwrite that.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import httpx

os.environ.setdefault("FAS_ENV_FILE", "")

from scripts.setup_appwrite import Setup  # noqa: E402


def _tao_setup() -> Setup:
    # dry_run=True chi de qua duoc __init__ (khong doi hoi credential that) —
    # cac ham duoc test o day khong tu kiem tra `self.dry_run`.
    return Setup(dry_run=True)


# Vong cho doc TUNG muc (`GET .../attributes/{key}`, `GET .../indexes/{key}`),
# khong doc tai lieu collection — xem `Setup._doc_muc_that`. Mock tra dung
# hinh dang mot muc don.
def _thuoc_tinh(key: str, status: str, error: str = "") -> dict:
    return {"key": key, "status": status, "error": error}


def _index(key: str, status: str, error: str = "") -> dict:
    return {"key": key, "status": status, "error": error}


def _theo_duong_dan(bang: dict):
    """side_effect cho `_call`: tra ket qua theo DUONG DAN duoc hoi (muc cuoi)."""
    def _call_gia(method, path, *a, **kw):
        return bang[path]
    return _call_gia


class ChoThuocTinhSanSangTest(unittest.TestCase):
    def test_1_available_ngay_lap_tuc(self):
        """Kich ban 1: da 'available' tu lan kiem tra dau — khong lap lai."""
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "available")) as m:
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertEqual(m.call_count, 1)

    def test_2_processing_roi_available(self):
        """Kich ban 2: 'processing' vai lan roi chuyen 'available'."""
        s = _tao_setup()
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "available"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")

    def test_3_processing_roi_failed_nem_loi_ro_rang(self):
        """Kich ban 3: chuyen 'failed' — phai nem loi NGAY, khong cho tiep,
        va thong diep phai chua nguyen van loi Appwrite tra ve."""
        s = _tao_setup()
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "failed", error="Mongo write conflict"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertIn("failed", str(ctx.exception))
        self.assertIn("Mongo write conflict", str(ctx.exception))

    def test_4_stuck_nem_loi_ro_rang(self):
        """Kich ban 4: trang thai 'stuck' cung phai nem loi ngay lap tuc,
        khong tiep tuc cho vo ich."""
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "stuck")):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertIn("stuck", str(ctx.exception))

    def test_5_het_thoi_gian_cho_nem_loi_ro_rang(self):
        """Kich ban 5: mai 'processing', khong bao gio 'available'/'failed' —
        phai nem loi RO RANG sau `timeout_giay`, khong treo vo han va khong
        im lang bo qua (khac ham cu)."""
        s = _tao_setup()
        # timeout_giay rat nho de test chay nhanh — dung time.monotonic that
        # (khong mock) vi ham dung no de tinh han chot.
        with patch.object(s, "_call", return_value=_thuoc_tinh("user_id", "processing")), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id", timeout_giay=0.01)
        self.assertIn("processing", str(ctx.exception))

    def test_thuoc_tinh_bien_mat_nem_loi(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value={}):
            with self.assertRaises(SystemExit):
                s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")


class ChoIndexSanSangTest(unittest.TestCase):
    def test_available_ngay(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_index("email_unique", "available")):
            s._cho_index_san_sang("/v1/.../profiles", "email_unique")

    def test_failed_nem_loi(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value=_index("email_unique", "failed", "duplicate key")):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_index_san_sang("/v1/.../profiles", "email_unique")
        self.assertIn("duplicate key", str(ctx.exception))


class IndexChoTatCaThuocTinhTest(unittest.TestCase):
    """Kich ban 6: tao index phai kiem TRUOC rang moi thuoc tinh no tham
    chieu deu 'available' — bao loi RO RANG liet ke dung thuoc tinh nao chua
    san sang, thay vi de Appwrite tra 400 mo ho."""

    def test_index_tu_choi_khi_mot_thuoc_tinh_chua_available(self):
        s = _tao_setup()
        bang = {
            "/v1/.../t/attributes/a": _thuoc_tinh("a", "available"),
            "/v1/.../t/attributes/b": _thuoc_tinh("b", "processing"),
        }
        with patch.object(s, "_call", side_effect=_theo_duong_dan(bang)):
            with self.assertRaises(SystemExit) as ctx:
                s._kiem_thuoc_tinh_san_sang_cho_index(
                    "/v1/.../t", "t_idx", ["a", "b"])
        thong_diep = str(ctx.exception)
        self.assertIn("t_idx", thong_diep)
        self.assertIn("['b']", thong_diep)
        self.assertNotIn("'a'", thong_diep)

    def test_index_khong_bao_loi_khi_tat_ca_da_available(self):
        s = _tao_setup()
        bang = {
            "/v1/.../t/attributes/a": _thuoc_tinh("a", "available"),
            "/v1/.../t/attributes/b": _thuoc_tinh("b", "available"),
        }
        with patch.object(s, "_call", side_effect=_theo_duong_dan(bang)):
            s._kiem_thuoc_tinh_san_sang_cho_index("/v1/.../t", "t_idx", ["a", "b"])


class CacheCollectionCuKhongChanVongChoTest(unittest.TestCase):
    """Do that 2026-09-26 tren Appwrite 1.9.6 + MongoDB THU: tai lieu collection
    trong cache Redis (TTL -1) giu `rights_mode` = 'processing' mai mai, trong
    khi chinh thuoc tinh da 'available'. Ba lan chay lai deu het 120s o cung mot
    cho. Vong cho KHONG duoc doc tai lieu collection nua."""

    BASE = "/v1/databases/db/collections/novels"
    COLLECTION_CU = {
        "attributes": [{"key": "rights_mode", "status": "processing"}],
        "indexes": [{"key": "state_idx", "status": "processing"}],
    }

    def _bang(self):
        return {
            self.BASE: self.COLLECTION_CU,
            f"{self.BASE}/attributes/rights_mode": _thuoc_tinh("rights_mode", "available"),
            f"{self.BASE}/attributes/state": _thuoc_tinh("state", "available"),
            f"{self.BASE}/indexes/state_idx": _index("state_idx", "available"),
        }

    def test_thuoc_tinh_doc_tung_muc_khong_doc_collection(self):
        s = _tao_setup()
        with patch.object(s, "_call", side_effect=_theo_duong_dan(self._bang())) as m, \
             patch("time.sleep", return_value=None):
            s._cho_thuoc_tinh_san_sang(self.BASE, "rights_mode", timeout_giay=0.01)
        self.assertEqual([c.args[1] for c in m.call_args_list],
                         [f"{self.BASE}/attributes/rights_mode"])

    def test_index_doc_tung_muc_khong_doc_collection(self):
        s = _tao_setup()
        with patch.object(s, "_call", side_effect=_theo_duong_dan(self._bang())) as m, \
             patch("time.sleep", return_value=None):
            s._cho_index_san_sang(self.BASE, "state_idx", timeout_giay=0.01)
        self.assertNotIn(self.BASE, [c.args[1] for c in m.call_args_list])

    def test_kiem_truoc_index_doc_tung_thuoc_tinh(self):
        s = _tao_setup()
        with patch.object(s, "_call", side_effect=_theo_duong_dan(self._bang())) as m:
            s._kiem_thuoc_tinh_san_sang_cho_index(self.BASE, "x_idx", ["rights_mode", "state"])
        self.assertNotIn(self.BASE, [c.args[1] for c in m.call_args_list])


class IndexCacheCollectionCuTest(unittest.TestCase):
    """Do that 2026-09-29 (may kiem 1.9.6, `user_follows.created_at`): doc tung muc 'available' nhung POST index
    400 "not yet available" vi tai lieu collection trong cache van 'processing'; chay lai cung chet dung cho do.
    PUT collection KHONG DOI GI lam moi cache (do that) -> thu lai thanh cong."""

    BASE = "/v1/databases/db/collections/user_follows"
    HIEN = {"name": "User follows", "$permissions": [], "documentSecurity": True, "enabled": True,
            "attributes": [{"key": "created_at", "status": "processing"}]}
    LOI = SystemExit("Appwrite lỗi 400: The requested attribute 'created_at' is not yet available. Please try again later.")

    def _gia(self, trang_thai="available", lan_hong=1):
        goi = []

        def _call(method, path, payload=None, **kw):
            goi.append((method, path, payload))
            if method == "POST" and path.endswith("/indexes"):
                if sum(1 for g in goi if g[0] == "POST") <= lan_hong:
                    raise self.LOI
                return {}
            if method == "GET" and path == self.BASE:
                return dict(self.HIEN)
            if method == "GET" and "/attributes/" in path:
                return _thuoc_tinh(path.rsplit("/", 1)[-1], trang_thai)
            if method == "PUT":
                return {}
            raise AssertionError((method, path))
        return goi, _call

    def _setup(self):
        s = _tao_setup()
        s.dry_run = False
        return s

    def test_lam_moi_cache_bang_put_khong_doi_gi_roi_thu_lai(self):
        s = self._setup()
        goi, f = self._gia()
        with patch.object(s, "_call", side_effect=f):
            s._ensure_index(self.BASE, "follower_created_idx", "key", ["follower_id", "created_at"])
        put = [g for g in goi if g[0] == "PUT"]
        self.assertEqual(len(put), 1)
        # Gui TUONG MINH ca bon truong, dung gia tri dang co — documentSecurity KHONG bao gio de mac dinh false.
        self.assertEqual(put[0][2], {"name": "User follows", "permissions": [], "documentSecurity": True, "enabled": True})
        self.assertEqual(sum(1 for g in goi if g[0] == "POST"), 2)

    def test_thuoc_tinh_that_su_chua_san_sang_thi_khong_cham_collection(self):
        s = self._setup()
        goi, f = self._gia(trang_thai="processing")
        with patch.object(s, "_call", side_effect=f), self.assertRaises(SystemExit):
            s._ensure_index(self.BASE, "follower_created_idx", "key", ["follower_id", "created_at"])
        self.assertFalse([g for g in goi if g[0] == "PUT"], "lỗi thật: không được PUT collection")

    def test_loi_400_khac_nem_nguyen_van(self):
        s = self._setup()

        def _call(method, path, payload=None, **kw):
            raise SystemExit("Appwrite lỗi 400: Invalid index type")
        with patch.object(s, "_call", side_effect=_call), self.assertRaises(SystemExit) as ctx:
            s._ensure_index(self.BASE, "x_idx", "key", ["a"])
        self.assertIn("Invalid index type", str(ctx.exception))

    def test_co_tran_so_lan_lam_moi(self):
        s = self._setup()
        goi, f = self._gia(lan_hong=99)
        with patch.object(s, "_call", side_effect=f), self.assertRaises(SystemExit):
            s._ensure_index(self.BASE, "x_idx", "key", ["created_at"])
        self.assertEqual(sum(1 for g in goi if g[0] == "PUT"), Setup.LAM_MOI_CACHE_TOI_DA)

    def test_sai_kieu_documentSecurity_thi_khong_put(self):
        for sai in ({"documentSecurity": 0}, {"documentSecurity": "true"}, {"enabled": None}, {"$permissions": "x"}):
            s = self._setup()
            goi, f = self._gia()
            self.HIEN = {**IndexCacheCollectionCuTest.HIEN, **sai}
            with patch.object(s, "_call", side_effect=f), self.assertRaises(SystemExit):
                s._ensure_index(self.BASE, "x_idx", "key", ["created_at"])
            self.assertFalse([g for g in goi if g[0] == "PUT"], f"sai kiểu {sai}: không được PUT")

    def test_thieu_truong_trong_ban_doc_thi_khong_put(self):
        s = self._setup()
        goi, f = self._gia()
        self.HIEN = {"name": "User follows", "enabled": True}  # thieu documentSecurity / $permissions
        with patch.object(s, "_call", side_effect=f), self.assertRaises(SystemExit) as ctx:
            s._ensure_index(self.BASE, "x_idx", "key", ["created_at"])
        self.assertIn("làm mới cache an toàn", str(ctx.exception))
        self.assertFalse([g for g in goi if g[0] == "PUT"])


class IdempotentSauThatBaiMotPhanTest(unittest.TestCase):
    """Kich ban 7: chay lai sau khi mot thuoc tinh da bi xoa+tao lai (mo
    phong sua loi thu cong sau su co that) — thuoc tinh 'da co' van phai
    duoc cho san sang, khong duoc coi 'da co' la xong ngay."""

    def test_da_co_van_duoc_kiem_lai_san_sang(self):
        s = _tao_setup()
        # Mo phong: thuoc tinh da ton tai (tu lan chay truoc) nhung van
        # 'processing' (chua kip san sang khi script chay lai ngay sau).
        ket_qua = [
            _thuoc_tinh("user_id", "processing"),
            _thuoc_tinh("user_id", "available"),
        ]
        with patch.object(s, "_call", side_effect=ket_qua), \
             patch("time.sleep", return_value=None):
            # Goi thang ham cho, dung nhu duong _ensure_collection se di qua
            # cho truong hop "key in da_co" (bo qua _ensure_attribute nhung
            # VAN goi _cho_thuoc_tinh_san_sang).
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")


class LoiMangThoangQuaTest(unittest.TestCase):
    """Su co that thu hai cung ngay (2026-08-21): tren cung self-host PROD,
    mot lan GET rieng bi `httpx.ReadTimeout` (loi mang that, khong phai
    status Appwrite) khien toan bo script sap ngang giua vong cho, ngay sau
    khi da qua duoc su co dau tien. `_goi_doc_thoi_thu_lai` phai coi day la
    MOT LAN THU THAT BAI binh thuong, khong phai ly do dung khac
    ('thuoc tinh bien mat')."""

    def test_read_timeout_duoc_thu_lai_roi_thanh_cong(self):
        s = _tao_setup()
        ket_qua = [
            httpx.ReadTimeout("The read operation timed out"),
            _thuoc_tinh("user_id", "available"),
        ]

        def _call_gia(*a, **kw):
            gia_tri = ket_qua.pop(0)
            if isinstance(gia_tri, Exception):
                raise gia_tri
            return gia_tri

        with patch.object(s, "_call", side_effect=_call_gia), \
             patch("time.sleep", return_value=None):
            s._cho_thuoc_tinh_san_sang("/v1/.../profiles", "user_id")
        self.assertEqual(ket_qua, [])

    def test_read_timeout_lap_lai_het_thoi_gian_nem_loi_ro_rang(self):
        s = _tao_setup()
        with patch.object(s, "_call",
                          side_effect=httpx.ReadTimeout("timed out")), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                s._cho_thuoc_tinh_san_sang(
                    "/v1/.../profiles", "user_id", timeout_giay=0.01)
        self.assertIn("mạng", str(ctx.exception))


class PlanChiDocTest(unittest.TestCase):
    """`--plan`: CHI DOC — rao cung chan moi phuong thuc khac GET; phat hien tai nguyen da co; bao muc khac thiet ke."""

    def _setup(self):
        s = _tao_setup()
        s.dry_run, s.plan_only = False, True
        return s

    def test_rao_cung_chan_ghi_truoc_khi_gui(self):
        s = self._setup()
        with patch("httpx.Client", side_effect=AssertionError("không được mở kết nối")):
            for m in ("POST", "PUT", "PATCH", "DELETE"):
                with self.assertRaises(SystemExit) as ctx:
                    s._call(m, "/v1/databases/db/collections", {"collectionId": "x"})
                self.assertIn("CHỈ ĐỌC", str(ctx.exception))

    def test_phat_hien_da_co_va_se_tao_va_lech(self):
        from scripts.setup_appwrite import SCHEMA

        s = self._setup()
        dac_ta = SCHEMA["chat_fanouts"]
        cot_dung = [{"key": k, "type": "string" if kind == "string" else kind, "size": extra, "required": req,
                     "status": "available"} for k, kind, req, extra in dac_ta["attributes"]]
        cot_dung[0]["size"] = 999  # lech co y

        def doc(path):
            if path.endswith("/collections/chat_messages"):
                return 404, {"message": "Collection not found"}
            if path.endswith("/collections/chat_fanouts"):
                return 200, {"$permissions": [], "documentSecurity": True}
            if path.endswith("/collections/chat_fanouts/attributes"):
                return 200, {"attributes": cot_dung + [{"key": "cu_thua", "type": "string"}]}
            if path.endswith("/collections/chat_fanouts/indexes"):
                return 200, {"indexes": []}
            return 200, {}
        with patch.object(s, "_doc", side_effect=doc):
            tong = s.plan(["chat_messages", "chat_fanouts"])
        self.assertEqual(tong["tao_bang"], 1)
        self.assertEqual(tong["da_co_bang"], 1)
        self.assertEqual(tong["tao_cot"], len(SCHEMA["chat_messages"]["attributes"]))
        self.assertEqual(tong["tao_index"], len(SCHEMA["chat_messages"]["indexes"]))
        self.assertEqual(tong["khac"], 1, "size lệch phải được báo")

    def test_khoa_khong_du_quyen_bao_ro(self):
        s = self._setup()
        with patch.object(s, "_doc", return_value=(401, {})), self.assertRaises(SystemExit) as ctx:
            s.plan(["chat_messages"])
        self.assertIn("collections.read", str(ctx.exception))


class NovelsKhongCanFulltextTest(unittest.TestCase):
    """2026-08-26: PR #56 them title_fulltext_idx + description_fulltext_idx
    vao `novels` dua tren gia dinh sai la `contains()` can chi muc fulltext.
    Kiem tra truc tiep tren Appwrite self-host 1.9.6 (khong phai Cloud) —
    dung mot collection dung mot lan roi tu xoa trong chinh
    fanfic-world-prod/fanfic_world_prod — chung minh nguoc lai:
    q_or(contains(title,...), contains(description,...)) tra dung ket qua
    voi KHONG chi muc fulltext nao ca. Appwrite cung chi cho MOT chi muc
    fulltext moi collection nen phien ban hai chi muc chua bao gio triem
    khai duoc nhu code. Test nay khoa lai viec da go ca hai, tranh vo tinh
    them lai khi chua co bang chung song moi."""

    def test_novels_khong_con_chi_muc_fulltext(self):
        from scripts.setup_appwrite import SCHEMA

        indexes = SCHEMA["novels"]["indexes"]
        kinds = [kind for (_key, kind, _attrs) in indexes]
        self.assertNotIn("fulltext", kinds)

    def test_novels_van_giu_cac_chi_muc_key_khac(self):
        from scripts.setup_appwrite import SCHEMA

        keys = {key for (key, _kind, _attrs) in SCHEMA["novels"]["indexes"]}
        self.assertEqual(
            keys,
            {"owner_idx", "state_idx", "state_created_idx", "novel_id_idx"},
        )


class Muc404LaChuaHienTest(unittest.TestCase):
    """Review doc lap 2026-09-28: ngay sau POST, `GET .../attributes/<key>` co the 404 mot luc. Voi phep DOC
    trang thai tung muc, 404 = "chua hien" (cho tiep toi han) — KHONG phai "xong", khong thoat ngay. Moi 404
    khac (vd `GET` collection, hay phep GHI) van la loi nhu cu."""

    class _TraLoi:
        def __init__(self, status):
            self.status_code, self.content = status, b"{}"

        def json(self):
            return {"message": "not found", "type": "attribute_not_found"}

    class _Client:
        def __init__(self, status):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return Muc404LaChuaHienTest._TraLoi(self.status)

    def _setup_that(self):
        s = _tao_setup()
        s.dry_run = False  # _call that, nhung httpx gia — khong goi mang
        return s

    def test_404_tung_muc_la_chua_hien(self):
        s = self._setup_that()
        with patch("httpx.Client", lambda **k: self._Client(404)):
            self.assertEqual(s._call("GET", "/v1/db/c/attributes/user_id", doc_thoi=True),
                             {"key": "user_id", "status": "chưa hiện (404)"})
            self.assertEqual(s._call("GET", "/v1/db/c/indexes/user_idx", doc_thoi=True)["status"], "chưa hiện (404)")
            for method, path, doc in (("GET", "/v1/db/c", True), ("POST", "/v1/db/c/attributes/string", False),
                                      ("GET", "/v1/db/c/attributes/user_id", False)):
                with self.assertRaises(SystemExit, msg=(method, path, doc)):
                    s._call(method, path, doc_thoi=doc)

    def test_vong_cho_404_mai_thi_het_han_bao_ro(self):
        s = _tao_setup()
        with patch.object(s, "_call", return_value={"key": "a", "status": "chưa hiện (404)"}), \
                patch("time.sleep", return_value=None), self.assertRaises(SystemExit) as ctx:
            s._cho_thuoc_tinh_san_sang("/v1/db/t", "a", timeout_giay=0.01)
        self.assertIn("404", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
