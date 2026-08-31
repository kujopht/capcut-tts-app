"""
Self-hosted OpenAI-compatible translation endpoint (Tencent Hy-MT2 family via
vLLM/TGI) chuân bị — khép 3 khoảng trống thực:

  1. `detect_source_language` — heuristics ngôn ngữ nguồn (không thêm pip dep).
  2. `source_text_hash`/`translated_content_hash` + `source_text_hash` bỏ qua
     chương không đổi (`create_project_or_reuse` idempotent).
  3. Đường custom provider (TRANSLATION_BASE_URL/API_KEY/MODEL) — chứng minh
     `build_provider_registry`/`DocuTranslateProvider` gọi và đọc được bản dịch
     từ một phản hồi OpenAI chat-completions dạng Hy-MT2 (fixture, không mạng).

Dùng `httpx.MockTransport` — cùng mẫu với `test_translation_provider_registry.py`
và `test_translation_cerebras_groq.py` (không cần mạng thật).
"""

from __future__ import annotations

import unittest

import httpx

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation import TranslationJobStatus
from server.translation_domain import (
    TranslationProject,
    TranslationVersion,
    _hash_text,
    detect_source_language,
)
from server.translation_provider_registry import build_provider_registry
from server.translation_providers import TranslationContext
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore


def _tra_loi_chat_hy_mt2(noi_dung: str, *, status_code: int = 200,
                         model: str = "hy-mt2-7b") -> httpx.Response:
    """Phản hồi OpenAI chat-completions CHUẨN mà vLLM/TGI phục vụ Hy-MT2 sẽ
    trả về (dạng HTTP body thật của một self-hosted endpoint)."""
    return httpx.Response(
        status_code,
        json={
            "id": "chatcmpl-hymt2-test",
            "object": "chat.completion",
            "created": 1770000000,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": noi_dung},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45,
                      "total_tokens": 165},
        })


class DetectSourceLanguageTest(unittest.TestCase):
    def test_tieng_trung(self):
        self.assertEqual(detect_source_language("萧炎看向药老，他继续前进。"),
                         "zh")

    def test_tieng_nhat_co_kana(self):
        self.assertEqual(
            detect_source_language("私は日本語を話します。これはテストです。"),
            "ja")

    def test_tieng_han_hangul(self):
        self.assertEqual(
            detect_source_language("안녕하세요. 이것은 한국어 테스트 문장입니다."),
            "ko")

    def test_tieng_viet_co_dau(self):
        self.assertEqual(
            detect_source_language(
                "Xin chào. Đây là một bài kiểm tra tiếng Việt có dấu."),
            "vi")

    def test_tieng_anh(self):
        self.assertEqual(
            detect_source_language(
                "This is a simple English story about a young man."),
            "en")

    def test_ngan_khong_du_tin_hieu(self):
        self.assertEqual(detect_source_language("好的"), "unknown")
        self.assertEqual(detect_source_language(""), "unknown")
        self.assertEqual(detect_source_language("12345 67890"), "unknown")


class CreateProjectDetectNguonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_tu_dong_phat_hien_nguon_tieng_viet(self):
        p = self.svc.create_project(
            self.an.user_id,
            title="Truyện",
            source_text="Xin chào. Đây là một câu chuyện tiếng Việt có dấu.",
        )
        self.assertEqual(p.source_language, "vi")

    def test_ghi_de_nguon_thu_cong_duoc_giu(self):
        p = self.svc.create_project(
            self.an.user_id,
            title="Truyện",
            source_text="Xin chào. Đây là một câu chuyện tiếng Việt có dấu.",
            source_language="zh",
        )
        self.assertEqual(p.source_language, "zh")

    def test_source_text_hash_duoc_tao_va_deterministic(self):
        p1 = self.svc.create_project(
            self.an.user_id, title="Truyện",
            source_text="萧炎看向药老。")
        p2 = self.svc.create_project(
            self.an.user_id, title="Truyện Khác",
            source_text="萧炎看向药老。")
        self.assertTrue(p1.source_text_hash)
        self.assertEqual(p1.source_text_hash, p2.source_text_hash)
        self.assertEqual(p1.source_text_hash, _hash_text("萧炎看向药老。"))


class CreateProjectOrReuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def _tao_va_hoan_tat(self, title, source_text):
        """Tao du an, chay job den COMPLETED that (mock provider) roi tra ve."""
        p = self.svc.create_project(self.an.user_id, title=title,
                                    source_text=source_text)
        job = self.svc.create_job(p.project_id, self.an.user_id)
        # Chay toi cung (inline worker) roi cho xong
        import time
        from server.translation import TERMINAL_STATUSES
        han = time.time() + 5
        while time.time() < han:
            job = self.svc.get_job(job.job_id, self.an.user_id)
            if job.status in TERMINAL_STATUSES:
                break
            time.sleep(0.005)
        return p

    def test_reuse_cung_title_va_source_hash(self):
        p1 = self._tao_va_hoan_tat("Đấu Phá", VB_MOT_CHUONG)
        # Goi lai cung owner + cung title + cung noidung cho du job da xong
        p2 = self.svc.create_project_or_reuse(
            self.an.user_id, title="Đấu Phá", source_text=VB_MOT_CHUONG)
        self.assertEqual(p1.project_id, p2.project_id)
        so_du_an = len(self.store.list_projects(self.an.user_id))
        self.assertEqual(so_du_an, 1)

    def test_noi_dung_khac_thi_tao_moi_khong_reuse(self):
        p1 = self._tao_va_hoan_tat("Đấu Phá", VB_MOT_CHUONG)
        p2 = self.svc.create_project_or_reuse(
            self.an.user_id, title="Đấu Phá",
            source_text=VB_MOT_CHUONG + "\nThêm một câu khác hoàn toàn.")
        self.assertNotEqual(p1.project_id, p2.project_id)
        self.assertEqual(len(self.store.list_projects(self.an.user_id)), 2)

    def test_job_chua_hoan_thanh_khong_reuse(self):
        """Neu job gio het dong cua du an cu, khong duoc dung lai du an do."""
        p1 = self.svc.create_project(self.an.user_id, title="Đấu Phá",
                                     source_text=VB_MOT_CHUONG)
        # Tao job nhung KHONG cho no hoan thanh -> khong co su that reuse.
        self.svc.create_job(p1.project_id, self.an.user_id)
        p2 = self.svc.create_project_or_reuse(
            self.an.user_id, title="Đấu Phá", source_text=VB_MOT_CHUONG)
        self.assertNotEqual(p1.project_id, p2.project_id)


class TranslatedContentHashTest(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.novels = MockMetadataStore()
        self.store = MockTranslationStore()
        self.svc = TranslationService(self.store, self.novels)
        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")

    def test_ghi_version_tu_dong_co_translated_content_hash(self):
        p = self.svc.create_project(self.an.user_id, title="Truyện",
                                    source_text=VB_MOT_CHUONG)
        job = self.svc.create_job(p.project_id, self.an.user_id)
        from server.translation import TERMINAL_STATUSES
        import time
        han = time.time() + 5
        while time.time() < han:
            job = self.svc.get_job(job.job_id, self.an.user_id)
            if job.status in TERMINAL_STATUSES:
                break
            time.sleep(0.005)
        versions = self.store.list_versions(p.project_id)
        self.assertTrue(versions, "phai co it nhat mot ban ghi lich su")
        v = versions[0]
        self.assertTrue(v.translated_content_hash)
        self.assertEqual(v.translated_content_hash, _hash_text(v.new_text))


class CustomProviderHyMT2Test(unittest.TestCase):
    def test_build_provider_registry_va_doc_ban_dich_tu_hy_mt2(self):
        """Tao registry voi bien custom, goi that qua MockTransport nhu mot
        endpoint Hy-MT2 that, va kiem thuat toan doc ket qua dich."""
        config = {
            "TRANSLATION_BASE_URL": "https://hymt2.selfhost.test/v1",
            "TRANSLATION_API_KEY": "sk-local-hymt2",
            "TRANSLATION_MODEL": "hy-mt2-7b",
            "TRANSLATION_CUSTOM_PROVIDER_FREE": "true",
        }
        reg = build_provider_registry(env=config)
        self.assertTrue(bool(reg))
        custom = reg.get("custom")
        self.assertIsNotNone(custom)
        self.assertEqual(custom.model_id, "hy-mt2-7b")
        self.assertTrue(custom.free_tier)

        # Ghi de client cua provider bang MockTransport the hien mot endpoint
        # Hy-MT2 that tra ve ban dich tieng Viet.
        ya_gui: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json
            nonlocal ya_gui
            ya_gui = _json.loads(request.content)
            return _tra_loi_chat_hy_mt2("Tiêu Viêm nhìn về phía Dược Lão.")

        custom.provider._client = httpx.Client(
            base_url="https://hymt2.selfhost.test/v1",
            transport=httpx.MockTransport(handler))

        ra = custom.translate_segment(
            "萧炎看向药老。",
            context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")
        # Xac nhan no gui dung than request OpenAI chat-completions voi model
        self.assertEqual(ya_gui["model"], "hy-mt2-7b")
        self.assertEqual(ya_gui["messages"][1]["role"], "user")

    def test_custom_provider_mac_dinh_khong_duoc_coi_la_mien_phi(self):
        """Khong dat TRANSLATION_CUSTOM_PROVIDER_FREE cung khong bat
        TRANSLATION_ALLOW_PAID_PROVIDER -> custom im lang khong ton tai."""
        reg = build_provider_registry(env={
            "TRANSLATION_BASE_URL": "https://hymt2.selfhost.test/v1",
            "TRANSLATION_API_KEY": "sk-local-hymt2",
            "TRANSLATION_MODEL": "hy-mt2-7b",
        })
        self.assertFalse(bool(reg))


VB_MOT_CHUONG = "第1章 Khởi đầu\n萧炎看向药老。他继续前进。\n"


if __name__ == "__main__":
    unittest.main()
