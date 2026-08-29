"""Lối vào schema Appwrite — các thuộc tính an toàn, không phải đường hạnh phúc.

Lối này cầm một credential quản schema trên sản xuất, nên điều đáng kiểm là
những gì nó TỪ CHỐI làm: trả về giá trị của một biến bí mật, chạy khi chỉ có
một nửa toạ độ, coi "thuộc tính có mặt" là "thuộc tính dùng được", hay lặng lẽ
lui về khoá runtime chỉ có quyền documents.

Mọi bài đều chặn lớp HTTP. Không bài nào chạm tới mạng, Appwrite, Render, hay
Windows Credential Manager.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, *rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _broker():
    return _load("_broker_qa2", ("scripts", "fanfic_credential_broker.py"))


def _schema_tool():
    return _load("_schema_qa", ("scripts", "fanfic_appwrite_schema.py"))


def _ev(key, value):
    return {"envVar": {"key": key, "value": value}, "cursor": "c-" + key}


COORDS = [
    _ev("APPWRITE_ENDPOINT", "https://appwrite.example/v1"),
    _ev("APPWRITE_PROJECT_ID", "proj-1"),
    _ev("APPWRITE_DATABASE_ID", "db-1"),
]


class NonSecretAllowlistTest(unittest.TestCase):
    """Đây là hàm DUY NHẤT trong broker trả về giá trị biến môi trường của
    Render. Nếu danh sách cho phép hỏng, broker thành công cụ rút bí mật."""

    def test_returns_only_allowlisted_names(self):
        b = _broker()
        tra_ve = COORDS + [_ev("APPWRITE_API_KEY", "BI-MAT-KHONG-DUOC-LO"),
                           _ev("FAS_CANARY_SERVICE_TOKEN", "CUNG-BI-MAT")]
        with patch.object(b, "_render", return_value=(200, tra_ve)):
            ra = b.render_non_secret_env("k", "srv-1")
        self.assertEqual(set(ra), b.RENDER_NON_SECRET_ENV)
        # Khẳng định trên GIÁ TRỊ, không chỉ trên khoá: một lỗi gộp dict có thể
        # giữ đúng tập khoá mà vẫn kéo theo giá trị bí mật.
        self.assertNotIn("BI-MAT-KHONG-DUOC-LO", repr(ra))
        self.assertNotIn("CUNG-BI-MAT", repr(ra))

    def test_runtime_api_key_is_not_in_the_allowlist(self):
        """Khoá runtime nằm ngoài danh sách CÓ CHỦ Ý. Bài này tồn tại để một
        bản sửa sau không thêm nó vào cho tiện."""
        b = _broker()
        self.assertNotIn("APPWRITE_API_KEY", b.RENDER_NON_SECRET_ENV)
        self.assertEqual(len(b.RENDER_NON_SECRET_ENV), 3)

    def test_paginates_and_sends_the_cursor(self):
        b = _broker()
        trang1 = [_ev(f"K{i:03d}", "x") for i in range(100)]
        paths = []

        def fake(api_key, method, path, payload=None, timeout=60):
            paths.append(path)
            return (200, trang1) if len(paths) == 1 else (200, COORDS)

        with patch.object(b, "_render", side_effect=fake):
            ra = b.render_non_secret_env("k", "srv-1")
        self.assertEqual(set(ra), b.RENDER_NON_SECRET_ENV,
                         "toạ độ ở trang 2 không được vô hình")
        self.assertIn(f"cursor={trang1[-1]['cursor']}", paths[1])

    def test_truncated_listing_refuses_instead_of_returning_partial(self):
        b = _broker()
        trang = [{"envVar": {"key": f"K{i}", "value": "x"}} for i in range(100)]
        with patch.object(b, "_render", return_value=(200, trang)):
            with self.assertRaises(b.RenderError):
                b.render_non_secret_env("k", "srv-1")


class AdminEnvTest(unittest.TestCase):
    """Một môi trường nửa vời sẽ trỏ công cụ schema vào sai nơi, hoặc hỏng với
    một lỗi 401 mờ mịt. Phải dừng sớm và gọi tên thứ đang thiếu."""

    def _patch(self, b, creds, coords=COORDS):
        return (patch.object(b, "fetch", side_effect=lambda n: creds.get(n)),
                patch.object(b, "render_resolve_service",
                             return_value={"id": "srv-1", "name": "fas-prod-api"}),
                patch.object(b, "_render", return_value=(200, coords)))

    def test_assembles_all_four_values(self):
        b = _broker()
        creds = {"RENDER_API_KEY": "rk", "APPWRITE_SCHEMA_API_KEY": "sk"}
        for p in self._patch(b, creds):
            p.start()
        try:
            env = b.appwrite_admin_env()
        finally:
            patch.stopall()
        self.assertEqual(set(env), b.RENDER_NON_SECRET_ENV | {"APPWRITE_SCHEMA_API_KEY"})
        self.assertEqual(env["APPWRITE_SCHEMA_API_KEY"], "sk")

    def test_missing_schema_key_names_the_scopes_to_create(self):
        b = _broker()
        creds = {"RENDER_API_KEY": "rk"}
        for p in self._patch(b, creds):
            p.start()
        try:
            with self.assertRaises(b.BrokerEnvironmentError) as ctx:
                b.appwrite_admin_env()
        finally:
            patch.stopall()
        loi = str(ctx.exception)
        # Thông báo phải chỉ ra VIỆC CẦN LÀM. Người vận hành đứng ở Console
        # Appwrite cần biết chính xác các scope, không phải "thiếu credential".
        for scope in ("collections.write", "attributes.write", "indexes.write"):
            self.assertIn(scope, loi)

    def test_missing_render_key_fails_before_touching_render(self):
        b = _broker()
        with patch.object(b, "fetch", return_value=None), \
             patch.object(b, "_render") as goi:
            with self.assertRaises(b.BrokerEnvironmentError):
                b.appwrite_admin_env()
        goi.assert_not_called()

    def test_partial_coordinates_refuse_rather_than_return_three_of_four(self):
        b = _broker()
        creds = {"RENDER_API_KEY": "rk", "APPWRITE_SCHEMA_API_KEY": "sk"}
        thieu = [_ev("APPWRITE_ENDPOINT", "https://x/v1")]     # thiếu 2 toạ độ
        for p in self._patch(b, creds, coords=thieu):
            p.start()
        try:
            with self.assertRaises(b.RenderError) as ctx:
                b.appwrite_admin_env()
        finally:
            patch.stopall()
        self.assertIn("APPWRITE_DATABASE_ID", str(ctx.exception))


class DiffTest(unittest.TestCase):
    """Phép đối chiếu là thứ quyết định "có được phép ghi không". Một khác biệt
    bị bỏ sót đọc thành "sản xuất đã khớp"."""

    def setUp(self):
        self.t = _schema_tool()
        self.spec = {
            "name": "T",
            "attributes": [("a", "string", True, 64),
                           ("e", "enum", True, ["x", "y"]),
                           ("m", "email", False, None)],
            "indexes": [("idx", "key", ["a"])],
        }
        self.khoe = {
            "attributes": [
                {"key": "a", "type": "string", "required": True, "status": "available"},
                {"key": "e", "type": "string", "format": "enum", "required": True,
                 "elements": ["x", "y"], "status": "available"},
                {"key": "m", "type": "string", "format": "email", "required": False,
                 "status": "available"},
            ],
            "indexes": [{"key": "idx", "attributes": ["a"], "status": "available"}],
        }

    def test_healthy_collection_reports_no_difference(self):
        """enum và email đều là `string` kèm `format` trong Appwrite. So thẳng
        tên kiểu sẽ báo sai lệch trên một schema hoàn toàn đúng."""
        self.assertEqual(self.t._khac_biet_collection("T", self.spec, self.khoe), [])

    def test_missing_collection_is_reported_as_the_whole_collection(self):
        ra = self.t._khac_biet_collection("T", self.spec, None)
        self.assertEqual(len(ra), 1)
        self.assertIn("THIẾU CẢ COLLECTION", ra[0])

    def test_present_but_unusable_attribute_is_a_difference(self):
        """Sự cố thật 2026-08-21: cột kẹt ở "processing" mãi mãi. "Có mặt"
        không phải "dùng được" — đúng cái bẫy đã làm hỏng một lần chạy trước."""
        hong = {**self.khoe, "attributes": [
            {**self.khoe["attributes"][0], "status": "processing"},
            *self.khoe["attributes"][1:]]}
        ra = self.t._khac_biet_collection("T", self.spec, hong)
        self.assertTrue(any("processing" in d for d in ra), ra)

    def test_enum_missing_a_value_is_detected(self):
        hep = {**self.khoe, "attributes": [
            self.khoe["attributes"][0],
            {**self.khoe["attributes"][1], "elements": ["x"]},
            self.khoe["attributes"][2]]}
        ra = self.t._khac_biet_collection("T", self.spec, hep)
        self.assertTrue(any("enum thiếu giá trị" in d for d in ra), ra)

    def test_required_mismatch_is_detected(self):
        loi = {**self.khoe, "attributes": [
            {**self.khoe["attributes"][0], "required": False},
            *self.khoe["attributes"][1:]]}
        ra = self.t._khac_biet_collection("T", self.spec, loi)
        self.assertTrue(any("required" in d for d in ra), ra)

    def test_missing_and_miswired_index_are_both_detected(self):
        ra = self.t._khac_biet_collection(
            "T", self.spec, {**self.khoe, "indexes": []})
        self.assertTrue(any("thiếu index" in d for d in ra), ra)
        sai = {**self.khoe,
               "indexes": [{"key": "idx", "attributes": ["b"], "status": "available"}]}
        ra2 = self.t._khac_biet_collection("T", self.spec, sai)
        self.assertTrue(any("cột" in d for d in ra2), ra2)

    def test_extra_production_attributes_are_not_reported(self):
        """Đối chiếu là MỘT CHIỀU có chủ ý: SCHEMA cần gì mà sản xuất chưa có.
        Một cột thừa trên sản xuất không phải thứ migration này sửa, và báo nó
        lên sẽ khiến cổng "không còn thay đổi" không bao giờ xanh."""
        thua = {**self.khoe,
                "attributes": self.khoe["attributes"] + [
                    {"key": "cu_ky", "type": "string", "required": False,
                     "status": "available"}]}
        self.assertEqual(self.t._khac_biet_collection("T", self.spec, thua), [])


class ReaderIsReadOnlyTest(unittest.TestCase):
    def test_reader_exposes_no_write_method(self):
        t = _schema_tool()
        cong_khai = [n for n in dir(t.Reader) if not n.startswith("_")]
        for xau in ("post", "put", "patch", "delete", "write", "create"):
            self.assertFalse(any(xau in n.lower() for n in cong_khai),
                             f"Reader lộ ra một phương thức ghi: {cong_khai}")

    def test_key_travels_in_the_header_never_in_the_url(self):
        t = _schema_tool()
        reader = t.Reader({"APPWRITE_ENDPOINT": "https://a.test/v1",
                           "APPWRITE_PROJECT_ID": "p",
                           "APPWRITE_DATABASE_ID": "d",
                           "APPWRITE_SCHEMA_API_KEY": "KHOA-BI-MAT"})
        ghi = {}

        class FakeClient:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def get(self_inner, url, headers=None):
                ghi["url"] = url
                ghi["headers"] = headers

                class R:
                    status_code = 200
                    content = b"{}"

                    def json(self_r):
                        return {}
                return R()

        with patch.object(t.httpx, "Client", lambda **kw: FakeClient()):
            reader.get("/v1/databases/d")
        self.assertNotIn("KHOA-BI-MAT", ghi["url"])
        self.assertEqual(ghi["headers"]["X-Appwrite-Key"], "KHOA-BI-MAT")

    def test_plain_http_endpoint_is_refused(self):
        """Khoá schema đi trong header của chính request đó; `http://` sẽ gửi
        nó đi dưới dạng rõ. Nêu ra qua review bảo mật độc lập."""
        t = _schema_tool()
        for xau in ("http://a.test/v1", "ftp://a.test", "a.test/v1"):
            with self.assertRaises(t.AuditError, msg=f"chấp nhận {xau!r}"):
                t.Reader({"APPWRITE_ENDPOINT": xau, "APPWRITE_PROJECT_ID": "p",
                          "APPWRITE_DATABASE_ID": "d",
                          "APPWRITE_SCHEMA_API_KEY": "k"})

    def test_trailing_v1_in_endpoint_is_not_doubled(self):
        """Render lưu endpoint CÓ `/v1`, còn mọi path trong mã đã tự mang `/v1`.
        Ghép thẳng sẽ ra `/v1/v1/...` và mọi phép đọc trả 404 — đọc y hệt
        "sản xuất trống trơn", tức là hỏng theo hướng nguy hiểm nhất."""
        t = _schema_tool()
        for dat, mong in (("https://a.test/v1", "https://a.test"),
                          ("https://a.test/v1/", "https://a.test"),
                          ("https://a.test", "https://a.test")):
            reader = t.Reader({"APPWRITE_ENDPOINT": dat, "APPWRITE_PROJECT_ID": "p",
                               "APPWRITE_DATABASE_ID": "d",
                               "APPWRITE_SCHEMA_API_KEY": "k"})
            self.assertEqual(reader._endpoint, mong, f"từ {dat!r}")


class ApplyScopeTest(unittest.TestCase):
    def test_apply_refuses_a_collection_outside_schema(self):
        t = _schema_tool()
        args = type("A", (), {"only": "khong_he_ton_tai"})()
        with patch.object(t, "_broker") as b:
            self.assertEqual(t.cmd_apply(args), 2)
        b.return_value.appwrite_admin_env.assert_not_called()

    def test_environment_is_restored_so_the_key_does_not_outlive_the_run(self):
        """`os.environ.update()` trần không bao giờ được dọn: khoá nằm lại tới
        lúc tiến trình thoát và mọi tiến trình con sinh ra sau đó thừa hưởng
        nó. Nêu ra qua review bảo mật độc lập (Antigravity Claude Opus)."""
        t = _schema_tool()
        os.environ.pop("APPWRITE_SCHEMA_API_KEY", None)
        os.environ["APPWRITE_PROJECT_ID"] = "gia-tri-cu"
        trong_luc_chay = {}

        with t._moi_truong_tam({"APPWRITE_SCHEMA_API_KEY": "KHOA-BI-MAT",
                                "APPWRITE_PROJECT_ID": "gia-tri-moi"}):
            trong_luc_chay = dict(os.environ)

        # Trong lúc chạy thì phải CÓ, nếu không phép tiêm vô nghĩa.
        self.assertEqual(trong_luc_chay["APPWRITE_SCHEMA_API_KEY"], "KHOA-BI-MAT")
        # Khoá trước đó KHÔNG tồn tại phải bị xoá hẳn, không phải đặt lại "".
        # Một biến rỗng chưa từng có vẫn là một thay đổi để lại.
        self.assertNotIn("APPWRITE_SCHEMA_API_KEY", os.environ)
        self.assertEqual(os.environ["APPWRITE_PROJECT_ID"], "gia-tri-cu")

    def test_environment_is_restored_even_when_the_migration_raises(self):
        """Một migration hỏng giữa chừng là đúng lúc KHÔNG được để khoá nằm lại."""
        t = _schema_tool()
        os.environ.pop("APPWRITE_SCHEMA_API_KEY", None)
        with self.assertRaises(RuntimeError):
            with t._moi_truong_tam({"APPWRITE_SCHEMA_API_KEY": "KHOA-BI-MAT"}):
                raise RuntimeError("migration hỏng")
        self.assertNotIn("APPWRITE_SCHEMA_API_KEY", os.environ)

    def test_apply_blanks_the_runtime_key_so_there_is_no_silent_fallback(self):
        """`setup_appwrite` lui về `APPWRITE_API_KEY` khi không có khoá schema.
        Khoá runtime chỉ có quyền documents, nên lối lui đó tạo ra một lần
        chạy hỏng giữa chừng thay vì một lần từ chối sạch sẽ."""
        t = _schema_tool()
        args = type("A", (), {"only": "scrape_run_items"})()
        gia_env = {"APPWRITE_ENDPOINT": "https://a/v1", "APPWRITE_PROJECT_ID": "p",
                   "APPWRITE_DATABASE_ID": "d", "APPWRITE_SCHEMA_API_KEY": "sk"}
        cu = dict(os.environ)
        os.environ["APPWRITE_API_KEY"] = "khoa-runtime-chi-co-documents"
        thay_gi = {}

        def ghi_lai(argv):
            # Chụp môi trường ĐÚNG LÚC `setup_appwrite` đọc nó. Kiểm tra sau
            # khi `cmd_apply` trả về sẽ luôn sai, vì môi trường đã được khôi
            # phục — và đó chính là hành vi mong muốn.
            thay_gi.update(os.environ)
            thay_gi["_argv"] = argv
            return 0

        try:
            with patch.object(t, "_broker") as b, \
                 patch("scripts.setup_appwrite.main", side_effect=ghi_lai):
                b.return_value.appwrite_admin_env.return_value = gia_env
                self.assertEqual(t.cmd_apply(args), 0)
            # Điều cần bảo đảm là KHÔNG có khoá chỉ-có-quyền-documents nào
            # để lui về — chứ không phải khoá runtime bị bỏ trống. Bỏ trống
            # làm `configured` thành False và `setup_appwrite` thoát ngay
            # (đã vấp thật ở lần chạy sản xuất đầu tiên).
            self.assertEqual(thay_gi["APPWRITE_API_KEY"], "sk",
                             "cả hai tên phải trỏ vào khoá schema")
            self.assertEqual(thay_gi["APPWRITE_SCHEMA_API_KEY"], "sk")
            self.assertEqual(thay_gi["FAS_ENV_FILE"], "")
            self.assertEqual(thay_gi["_argv"], ["--only", "scrape_run_items"])
            # ...và sau đó khoá runtime thật phải trở lại nguyên vẹn.
            self.assertEqual(os.environ["APPWRITE_API_KEY"],
                             "khoa-runtime-chi-co-documents")
            self.assertNotIn("APPWRITE_SCHEMA_API_KEY", os.environ)
        finally:
            os.environ.clear()
            os.environ.update(cu)


if __name__ == "__main__":
    unittest.main()
