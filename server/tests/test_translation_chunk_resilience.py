"""
Kha nang chiu loi o cap DOAN (feature/pollinations-translation) —
`TranslationService._dich_mot_chuong`: thu lai MOT DOAN rieng le, giu dung
THU TU cac doan sau khi ghep, khong lap doan khi thu lai, va bo nho dem doan
dich (cache) tranh goi LLM lai cho dau vao giong het.

Chay tren `MockTranslationProvider`-nhu (khong goi mang that), cung ha tang
`Nen`/`cho_job_xong` voi `test_translation_service.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.translation_providers import MockTranslationProvider, TranslationProviderError
from server.translation_service import TranslationService
from server.translation_store import MockTranslationStore
from server.tests.test_translation_service import cho_job_xong


class _ThatBaiTheoVanBan(MockTranslationProvider):
    """That bai DUNG so lan cau hinh cho MOI van ban cu the (khoa la chinh
    van ban doan), sau do thanh cong — mo phong 'mot doan rieng le that bai
    thoang qua rồi on dinh lai', khong lien quan gi den cac doan KHAC."""

    def __init__(self, so_lan_that_bai_cho: dict):
        self._con_lai = dict(so_lan_that_bai_cho)
        self.lich_su_goi: list = []

    def translate_segment(self, text, *, context):
        if context.vai_tro != "translator":
            return text
        self.lich_su_goi.append(text)
        con = self._con_lai.get(text, 0)
        if con > 0:
            self._con_lai[text] = con - 1
            raise TranslationProviderError("Lỗi thoáng qua giả lập để kiểm thử.")
        return f"[DỊCH] {text}"


class _DemLuotGoi(MockTranslationProvider):
    def __init__(self):
        self.so_lan_goi = 0
        self.lich_su_goi: list = []

    def translate_segment(self, text, *, context):
        if context.vai_tro != "translator":
            return text
        self.so_lan_goi += 1
        self.lich_su_goi.append(text)
        return f"[DỊCH] {text}"


#: Ba doan RIENG BIET, moi doan ~180 ky tu (< 200 nhung 2 doan cong lai >
#: 200) — voi `DOAN_KY_TU_MOI_LAN_GOI` bi vá xuong 200 trong cac test duoi
#: day, moi doan chac chan thanh MOT chunk RIENG (khong bi gop chung).
_DOAN_1 = "甲" * 90 + "。" + "一" * 90 + "。"
_DOAN_2 = "乙" * 90 + "。" + "二" * 90 + "。"
_DOAN_3 = "丙" * 90 + "。" + "三" * 90 + "。"
assert 150 < len(_DOAN_1) < 200
# KHONG co dong tieu de chuong ("第1章 ...") o day CO CHU DICH: mot dong
# tieu de NGAN se bi `_pack` (desktop_app.text_chunker) GOP CHUNG voi doan
# dau tien vao CUNG mot chunk (con du cho trong gioi han), pha vo gia dinh
# "moi _DOAN la MOT chunk rieng" ma cac test duoi day dua vao.
# `tach_chuong` khong tim thay tieu de nao thi tra ve CA VAN BAN nhu MOT
# chuong duy nhat — dung y dinh cua cac test nay.
_VAN_BAN_BA_DOAN = f"{_DOAN_1}\n\n{_DOAN_2}\n\n{_DOAN_3}"


class Nen(unittest.TestCase):
    def _svc(self, provider):
        identity = MockIdentityAdapter()
        novels = MockMetadataStore()
        store = MockTranslationStore()
        svc = TranslationService(store, novels, provider=provider)
        an = identity.register("an@vidu.vn", "MatKhau123", "An")
        return svc, an


class ThuLaiMotDoanRiengLeTest(Nen):
    """'support retry of individual failed chunks rather than restarting
    the whole chapter' — CHI khi `TRANSLATION_CHUNK_RETRY_COUNT` > 0 (mac
    dinh TAT, xem ghi chu tai `translation_service.py`)."""

    def test_mot_doan_giua_that_bai_thoang_qua_duoc_thu_lai_khong_gian_doan_chuong(self):
        provider = _ThatBaiTheoVanBan({_DOAN_2: 1})  # doan 2 that bai DUNG 1 lan
        svc, an = self._svc(provider)
        with patch("server.translation_service.DOAN_KY_TU_MOI_LAN_GOI", 200), \
             patch("server.translation_service.TRANSLATION_CHUNK_RETRY_COUNT", 1), \
             patch("server.translation_service._CHUNK_RETRY_DELAY_SECONDS", 0.0):
            p = svc.create_project(an.user_id, title="x",
                                   source_text=_VAN_BAN_BA_DOAN, quality_mode="nhanh")
            job = svc.create_job(p.project_id, an.user_id)
            job = cho_job_xong(svc, job.job_id, an.user_id)

        self.assertEqual(job.status.value, "completed", job.error)
        p_sau = svc.get_project(p.project_id, an.user_id)
        ban_dich = p_sau.translated_chapters[0]

        # DUNG THU TU: doan 1 -> doan 2 -> doan 3, khong bi dao hay mat.
        vi_tri_1 = ban_dich.index(f"[DỊCH] {_DOAN_1}")
        vi_tri_2 = ban_dich.index(f"[DỊCH] {_DOAN_2}")
        vi_tri_3 = ban_dich.index(f"[DỊCH] {_DOAN_3}")
        self.assertLess(vi_tri_1, vi_tri_2)
        self.assertLess(vi_tri_2, vi_tri_3)

        # KHONG LAP: ban dich cua doan 2 chi xuat hien DUNG MOT LAN, du no
        # da that bai lan dau va duoc thu lai (khong phai bi noi them ban
        # thu-lai VAO SAU ban that-bai).
        self.assertEqual(ban_dich.count(f"[DỊCH] {_DOAN_2}"), 1)
        # Provider THUC SU duoc goi 2 lan cho doan 2 (that bai + thu lai
        # thanh cong), 1 lan cho moi doan con lai — 4 lan goi tong cong.
        self.assertEqual(provider.lich_su_goi.count(_DOAN_2), 2)
        self.assertEqual(provider.lich_su_goi.count(_DOAN_1), 1)
        self.assertEqual(provider.lich_su_goi.count(_DOAN_3), 1)

    def test_thu_lai_tat_thi_giu_hanh_vi_cu_khong_gian_doan_bi_loi_ngay(self):
        """`TRANSLATION_CHUNK_RETRY_COUNT=0` (mac dinh) — mot doan that bai
        lam CA CHUONG that bai ngay, khong tu thu lai (an toan mac dinh,
        khong doi hanh vi retry-cap-job da co san — xem `RetryJobTest`)."""
        provider = _ThatBaiTheoVanBan({_DOAN_2: 1})
        svc, an = self._svc(provider)
        with patch("server.translation_service.DOAN_KY_TU_MOI_LAN_GOI", 200), \
             patch("server.translation_service.TRANSLATION_CHUNK_RETRY_COUNT", 0):
            p = svc.create_project(an.user_id, title="x",
                                   source_text=_VAN_BAN_BA_DOAN, quality_mode="nhanh")
            job = svc.create_job(p.project_id, an.user_id)
            job = cho_job_xong(svc, job.job_id, an.user_id)
        self.assertEqual(job.status.value, "failed")


class ThuTuVaKhongLapDoanTest(Nen):
    """'preserve paragraph boundaries' + 'avoid duplicated paragraphs during
    retry/reassembly' — truong hop KHONG co loi nao (duong hanh phuc), chi
    kiem tra ghep dung thu tu/khong trung lap voi nhieu doan."""

    def test_nhieu_doan_ghep_lai_dung_thu_tu_khong_trung_lap(self):
        provider = _DemLuotGoi()
        svc, an = self._svc(provider)
        with patch("server.translation_service.DOAN_KY_TU_MOI_LAN_GOI", 200):
            p = svc.create_project(an.user_id, title="x",
                                   source_text=_VAN_BAN_BA_DOAN, quality_mode="nhanh")
            job = svc.create_job(p.project_id, an.user_id)
            job = cho_job_xong(svc, job.job_id, an.user_id)

        self.assertEqual(job.status.value, "completed", job.error)
        p_sau = svc.get_project(p.project_id, an.user_id)
        ban_dich = p_sau.translated_chapters[0]
        thu_tu_mong_doi = "\n\n".join(
            f"[DỊCH] {d}" for d in (_DOAN_1, _DOAN_2, _DOAN_3))
        self.assertEqual(ban_dich, thu_tu_mong_doi)
        # Moi doan CHI duoc goi dung MOT LAN (3 doan, 3 lan goi — khong hon).
        self.assertEqual(provider.so_lan_goi, 3)


class CacheKhongGoiLaiLLMTest(Nen):
    """Audit caching (yeu cau Pollinations): 'should not invoke the LLM
    again when an identical source text + target language + prompt/model
    version is already cached'."""

    def test_van_ban_giong_het_o_du_an_khac_khong_goi_lai_provider(self):
        provider = _DemLuotGoi()
        svc, an = self._svc(provider)

        van_ban = "甲。"  # khong co dong tieu de — xem ghi chu tai _VAN_BAN_BA_DOAN
        p1 = svc.create_project(an.user_id, title="x1", source_text=van_ban,
                                quality_mode="nhanh")
        job1 = svc.create_job(p1.project_id, an.user_id)
        cho_job_xong(svc, job1.job_id, an.user_id)
        self.assertEqual(provider.so_lan_goi, 1)

        # Du an THU HAI, CUNG van ban chuong, CUNG ngu canh mac dinh (khong
        # glossary, khong tom tat, cung genre/naming_mode/quality_mode) —
        # phai lay tu cache, KHONG goi provider them lan nao.
        p2 = svc.create_project(an.user_id, title="x2", source_text=van_ban,
                                quality_mode="nhanh")
        job2 = svc.create_job(p2.project_id, an.user_id)
        cho_job_xong(svc, job2.job_id, an.user_id)
        self.assertEqual(provider.so_lan_goi, 1,
                         "cache phải tránh gọi LLM lại cho đầu vào giống hệt")

        p2_sau = svc.get_project(p2.project_id, an.user_id)
        self.assertEqual(p2_sau.translated_chapters[0], "[DỊCH] 甲。")

    def test_glossary_khac_nhau_khong_dung_cache_sai(self):
        """An toan cache: NGU CANH khac (glossary khac) khong duoc phep lay
        nham ket qua cache cua ngu canh khac — moi lan phai goi provider
        that khi glossary thuc su khac."""
        provider = _DemLuotGoi()
        svc, an = self._svc(provider)
        van_ban = "甲。"  # khong co dong tieu de — xem ghi chu tai _VAN_BAN_BA_DOAN

        p1 = svc.create_project(an.user_id, title="x1", source_text=van_ban,
                                quality_mode="nhanh")
        job1 = svc.create_job(p1.project_id, an.user_id)
        cho_job_xong(svc, job1.job_id, an.user_id)
        self.assertEqual(provider.so_lan_goi, 1)

        p2 = svc.create_project(an.user_id, title="x2", source_text=van_ban,
                                quality_mode="nhanh")
        svc.add_glossary_entry(p2.project_id, an.user_id, category="character",
                               original="甲", translated="Giáp")
        job2 = svc.create_job(p2.project_id, an.user_id)
        cho_job_xong(svc, job2.job_id, an.user_id)
        self.assertEqual(provider.so_lan_goi, 2,
                         "glossary khác nhau phải là một khoá cache khác")


if __name__ == "__main__":
    unittest.main()
