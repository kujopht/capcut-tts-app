"""`server/translation_providers.py` — provider gia (mock) va lua chon provider."""

from __future__ import annotations

import json
import unittest

import httpx

from server.translation_providers import (
    DocuTranslateProvider,
    MockTranslationProvider,
    PermanentProviderError,
    TransientProviderError,
    TranslationContext,
    TranslationProviderError,
    build_provider,
)


def _client_gia(handler):
    """`httpx.Client` dung `MockTransport` — KHONG BAO GIO goi mang that.
    `handler(request) -> httpx.Response`. Can `base_url` de duong dan tuong
    doi nhu `/chat/completions` giai quyet duoc, giong client that trong
    `DocuTranslateProvider.__init__`."""
    return httpx.Client(base_url="https://vidu.test",
                        transport=httpx.MockTransport(handler))


def _tra_loi_chat(noi_dung: str, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"choices": [{"message": {"content": noi_dung}}]},
    )


class MockProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.p = MockTranslationProvider()

    def test_vi_du_dung_tu_yeu_cau_goc(self):
        ra = self.p.translate_segment(
            "萧炎看向药老。", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")

    def test_doan_rong_nem_loi_khong_tra_thanh_cong_gia(self):
        with self.assertRaises(TranslationProviderError):
            self.p.translate_segment(
                "   ", context=TranslationContext(vai_tro="translator"))

    def test_vai_tro_editor_tra_nguyen_van(self):
        """Mock KHONG gia vo bien tap duoc — tra dung nguyen dau vao."""
        vao = "Một câu tiếng Việt đã dịch."
        ra = self.p.translate_segment(
            vao, context=TranslationContext(vai_tro="editor"))
        self.assertEqual(ra, vao)

    def test_vai_tro_qa_tra_nguyen_van(self):
        vao = "Một câu tiếng Việt đã dịch."
        ra = self.p.translate_segment(
            vao, context=TranslationContext(vai_tro="qa"))
        self.assertEqual(ra, vao)

    def test_ap_dung_glossary_khi_khong_co_trong_tu_dien_cung(self):
        ra = self.p.translate_segment(
            "夜妖精 xuất hiện.",
            context=TranslationContext(
                vai_tro="translator", glossary={"夜妖精": "Dạ Yêu Tinh"}))
        self.assertIn("Dạ Yêu Tinh", ra)
        self.assertTrue(ra.startswith("[MOCK-VI]"))

    def test_tat_dinh_cung_dau_vao_ra_cung_ket_qua(self):
        vb = "một đoạn bất kỳ không nằm trong từ điển cứng"
        ctx = TranslationContext(vai_tro="translator")
        self.assertEqual(self.p.translate_segment(vb, context=ctx),
                         self.p.translate_segment(vb, context=ctx))

    def test_khong_goi_mang(self):
        """Mock la mot lop hoc — kiem bang code, khong the kiem 'khong co
        request mang' truc tiep, nen kiem GIAN TIEP: chay duoc khi khong co
        mang (offline) van phai OK — test nay tu no da chung minh dieu do vi
        moi bai trong file deu chay trong CI khong co mang ra ngoai."""
        self.assertEqual(MockTranslationProvider.name, "mock")


class DocuTranslateProviderTest(unittest.TestCase):
    def test_thieu_cau_hinh_nem_loi_ro_rang(self):
        with self.assertRaises(TranslationProviderError):
            DocuTranslateProvider(base_url="", api_key="", model="")

    def test_goi_that_tra_ve_dung_noi_dung(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/chat/completions")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "m")
            return _tra_loi_chat("Tiêu Viêm nhìn về phía Dược Lão.")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        ra = p.translate_segment("萧炎看向药老。",
                                 context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")

    def test_client_that_mang_dung_header_xac_thuc(self):
        """Khong tiem `client` — kiem duong dung PHAI thuc su dung
        `Authorization: Bearer <key>`. Tao `httpx.Client` khong cham mang
        (chi goi mang khi thuc su gui request), nen an toan chay trong test."""
        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="bi-mat",
                                  model="m")
        self.assertEqual(p._client.headers["authorization"], "Bearer bi-mat")

    def test_prompt_he_thong_doi_theo_vai_tro(self):
        """Ba vai tro phai tao ra ba he-thong-prompt KHAC NHAU — day la ly do
        goc chi mot phuong thuc van du cho ca ba pass (xem docstring dau
        file)."""
        thay = {}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            thay["he_thong"] = body["messages"][0]["content"]
            return _tra_loi_chat("kết quả")

        for vai_tro in ("translator", "editor", "qa"):
            p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                      model="m", client=_client_gia(handler))
            p.translate_segment("x", context=TranslationContext(vai_tro=vai_tro))
            thay[vai_tro] = thay.pop("he_thong")

        self.assertNotEqual(thay["translator"], thay["editor"])
        self.assertNotEqual(thay["editor"], thay["qa"])
        self.assertNotEqual(thay["translator"], thay["qa"])

    def test_glossary_va_tom_tat_di_vao_prompt_nguoi_dung(self):
        thay = {}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            thay["nguoi_dung"] = body["messages"][1]["content"]
            return _tra_loi_chat("kết quả")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        p.translate_segment(
            "夜妖精 xuất hiện.",
            context=TranslationContext(
                vai_tro="translator",
                tom_tat_truoc="Chương trước: nhân vật chính rời làng.",
                glossary={"夜妖精": "Dạ Yêu Tinh"},
                custom_instruction="Giữ giọng văn trang trọng."))
        self.assertIn("Dạ Yêu Tinh", thay["nguoi_dung"])
        self.assertIn("nhân vật chính rời làng", thay["nguoi_dung"])
        self.assertIn("trang trọng", thay["nguoi_dung"])

    def test_xung_ho_can_ngu_canh_nam_trong_prompt_he_thong(self):
        """Khong dung tu dien tinh anh xa mot-mot — LLM phai tu thay danh
        sach nay va TU quyet dinh theo ngu canh (xem yeu cau goc muc 9)."""
        thay = {}

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            thay["he_thong"] = body["messages"][0]["content"]
            return _tra_loi_chat("kết quả")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        p.translate_segment("你好", context=TranslationContext(vai_tro="translator"))
        self.assertIn("你", thay["he_thong"])
        self.assertIn("师兄", thay["he_thong"])
        self.assertIn("NGỮ CẢNH", thay["he_thong"])

    def test_loi_http_thanh_TranslationProviderError(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("x", context=TranslationContext(vai_tro="translator"))

    def test_phan_hoi_sai_dang_thanh_TranslationProviderError(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"khong_dung_dang": True})

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("x", context=TranslationContext(vai_tro="translator"))

    def test_noi_dung_rong_thanh_TranslationProviderError(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _tra_loi_chat("   ")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("x", context=TranslationContext(vai_tro="translator"))

    def test_doan_vao_rong_khong_goi_mang(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("khong duoc goi mang voi doan vao rong")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("   ", context=TranslationContext(vai_tro="translator"))

    def test_last_usage_none_truoc_lan_goi_dau(self):
        """Mission 'Hy-MT2 1.8B translation production readiness' - real gap
        fix: truoc day lop nay khong doc `usage` tu phan hoi (khac
        `_OpenAICompatFreeProvider`), du mot endpoint self-hosted (vLLM)
        van tra truong nay dung chuan OpenAI-compat."""
        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m")
        self.assertIsNone(p.last_usage)

    def test_last_usage_doc_duoc_tu_phan_hoi_co_usage(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "kết quả"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 17},
            })

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        p.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(p.last_usage, {"input_tokens": 42, "output_tokens": 17})

    def test_last_usage_none_khi_phan_hoi_khong_kem_usage(self):
        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(
                                      lambda r: _tra_loi_chat("kết quả")))
        p.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertIsNone(p.last_usage)

    def test_extra_payload_mac_dinh_rong_khong_doi_hanh_vi(self):
        """Mac dinh (khong truyen extra_payload) -> than request Y HET
        truoc mission nay: chi model/messages/temperature=0.3."""
        thay = {}

        def handler(request: httpx.Request) -> httpx.Response:
            thay["body"] = json.loads(request.content)
            return _tra_loi_chat("kết quả")

        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m", client=_client_gia(handler))
        p.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(thay["body"]["temperature"], 0.3)
        self.assertNotIn("top_p", thay["body"])
        self.assertNotIn("max_tokens", thay["body"])

    def test_extra_payload_ghi_de_duoc_gui_trong_than_request(self):
        """Khi caller truyen extra_payload (vd khuyen nghi model-card cua
        Hy-MT2), cac tham so do PHAI xuat hien trong than request that,
        va co the ghi de ca `temperature` mac dinh."""
        thay = {}

        def handler(request: httpx.Request) -> httpx.Response:
            thay["body"] = json.loads(request.content)
            return _tra_loi_chat("kết quả")

        p = DocuTranslateProvider(
            base_url="https://vidu.test", api_key="k", model="m",
            client=_client_gia(handler),
            extra_payload={"temperature": 0.7, "top_p": 0.6, "top_k": 20,
                          "repetition_penalty": 1.05, "max_tokens": 4096})
        p.translate_segment("x", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(thay["body"]["temperature"], 0.7)
        self.assertEqual(thay["body"]["top_p"], 0.6)
        self.assertEqual(thay["body"]["top_k"], 20)
        self.assertEqual(thay["body"]["repetition_penalty"], 1.05)
        self.assertEqual(thay["body"]["max_tokens"], 4096)


class ChonProviderTest(unittest.TestCase):
    def test_khong_co_settings_ra_mock(self):
        self.assertIsInstance(build_provider(None), MockTranslationProvider)

    def test_settings_thieu_key_van_ra_mock_khong_nem(self):
        class GiaSettings:
            translation_base_url = ""
            translation_api_key = ""
            translation_model = ""

        self.assertIsInstance(build_provider(GiaSettings()),
                              MockTranslationProvider)

    def test_du_ca_ba_moi_ra_docutranslate(self):
        class GiaSettings:
            translation_base_url = "https://vidu.test"
            translation_api_key = "k"
            translation_model = "m"

        self.assertIsInstance(build_provider(GiaSettings()),
                              DocuTranslateProvider)

    def test_settings_THAT_tu_config_py_co_ba_truong_nay(self):
        """
        Rao chan hoi quy CU THE: `server/main.py` tung goi
        `TranslationService(translation_store, store)` KHONG truyen
        `provider`, nen `build_provider` chi bao gio nhan `None` — mot API
        key that dien vao `.env` van im lang khong co tac dung gi. Nguyen
        nhan sau: `Settings` (dataclass that o `server/config.py`) khong he
        khai bao ba thuoc tinh nay, nen `getattr(settings, ..., "")` luon ra
        chuoi rong du `load_settings()` co doc duoc bien moi truong hay
        khong. Bai nay dung `Settings` THAT (khong phai lop gia tu ke o
        tren) de dam bao ba truong ton tai va `build_provider` doc dung.
        """
        from server.config import Settings

        rong = Settings()
        self.assertEqual(rong.translation_base_url, "")
        self.assertIsInstance(build_provider(rong), MockTranslationProvider)

        day_du = Settings(translation_base_url="https://vidu.test",
                          translation_api_key="k", translation_model="m")
        self.assertIsInstance(build_provider(day_du), DocuTranslateProvider)


class DocuTranslateProviderErrorClassificationTest(unittest.TestCase):
    """Mission 'REMOVE THE HUMAN FROM BEAM OPERATIONS' muc E — moi loai loi
    that PHAI anh xa dung nhom TAM THOI/VINH VIEN, khong con roi tat ca vao
    mot `TranslationProviderError` chung chung nhu truoc (nguyen nhan goc
    cua vong lap `waiting_for_provider` vo han that da quan sat duoc)."""

    def _p(self, handler):
        return DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                     model="m", client=_client_gia(handler))

    def test_timeout_la_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        with self.assertRaises(TransientProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_connect_error_la_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with self.assertRaises(TransientProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_502_503_504_la_transient(self):
        for status in (502, 503, 504):
            with self.subTest(status=status):
                def handler(request: httpx.Request, status=status) -> httpx.Response:
                    return httpx.Response(status, text="bad gateway")

                with self.assertRaises(TransientProviderError):
                    self._p(handler).translate_segment(
                        "x", context=TranslationContext(vai_tro="translator"))

    def test_429_la_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="too many requests")

        with self.assertRaises(TransientProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_noi_dung_rong_la_transient(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return _tra_loi_chat("   ")

        with self.assertRaises(TransientProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_401_403_la_permanent(self):
        for status in (401, 403):
            with self.subTest(status=status):
                def handler(request: httpx.Request, status=status) -> httpx.Response:
                    return httpx.Response(status, text="unauthorized")

                with self.assertRaises(PermanentProviderError):
                    self._p(handler).translate_segment(
                        "x", context=TranslationContext(vai_tro="translator"))

    def test_404_la_permanent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        with self.assertRaises(PermanentProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_dinh_dang_sai_la_permanent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"khong_dung_dang": True})

        with self.assertRaises(PermanentProviderError):
            self._p(handler).translate_segment(
                "x", context=TranslationContext(vai_tro="translator"))

    def test_thieu_cau_hinh_la_permanent(self):
        with self.assertRaises(PermanentProviderError):
            DocuTranslateProvider(base_url="", api_key="", model="")


if __name__ == "__main__":
    unittest.main(verbosity=2)
