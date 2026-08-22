"""
Pollinations.ai lam nha cung cap DICH — ban viet lai NATIVE cho main.

BOI CANH: cong viec goc (commit 5137ec0/8672550/2ed65fe, 2026-08-15) nam tren
mot nhanh dung tren `feature/animation-v6`, KHONG merge thang vao main duoc vi
main da tien hoa doc lap `translation_provider_registry.py`. File nay kiem
HANH VI da phuc hoi, tren kien truc main hien tai.

Fixture GIA hoan toan (`httpx.MockTransport`) — khong credential that, khong
goi mang. Cung mau voi `test_translation_provider_registry.py`.

DIEM QUAN TRONG NHAT duoc kiem o day: Pollinations la TRA PHI THEO MAC DINH.
Chi co `POLLINATIONS_API_KEY` KHONG du de no vao registry — phai dat tuong
minh `POLLINATIONS_FREE_TIER=true` hoac rao chan chung
`TRANSLATION_ALLOW_PAID_PROVIDER=true`. Do la rao chan chong "bat ngo bi tinh
phi".
"""

from __future__ import annotations

import unittest

import httpx

from server.translation_model_profiles import POLLINATIONS_MODEL_PROFILES
from server.translation_providers import (
    TranslationContext,
    TranslationProviderError,
)
from server.translation_provider_registry import (
    PollinationsProvider,
    ProviderRateLimited,
    build_provider_registry,
)

_DEEPSEEK = POLLINATIONS_MODEL_PROFILES["deepseek"]


def _client_gia(handler):
    return httpx.Client(base_url="https://vidu.test",
                        transport=httpx.MockTransport(handler))


def _tra_loi_chat(noi_dung: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": noi_dung}}]})


def _ctx() -> TranslationContext:
    return TranslationContext(vai_tro="translator")


class PollinationsProviderTest(unittest.TestCase):

    def test_phan_hoi_binh_thuong(self):
        p = PollinationsProvider(
            api_key="sk_gia", profile=_DEEPSEEK,
            client=_client_gia(lambda r: _tra_loi_chat("Tiêu Viêm")))
        self.assertEqual(p.translate_segment("萧炎", context=_ctx()), "Tiêu Viêm")

    def test_thieu_api_key_bi_tu_choi(self):
        with self.assertRaises(TranslationProviderError):
            PollinationsProvider(api_key="", profile=_DEEPSEEK)

    def test_429_thanh_ProviderRateLimited(self):
        p = PollinationsProvider(
            api_key="sk_gia", profile=_DEEPSEEK,
            client=_client_gia(lambda r: httpx.Response(429, text="rate limited")))
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("你好", context=_ctx())

    def test_base_url_mac_dinh_va_ghi_de(self):
        self.assertEqual(PollinationsProvider.DEFAULT_BASE_URL,
                         "https://gen.pollinations.ai/v1")
        # Ghi de: khong goi mang, chi kiem cau hinh client. `httpx` chuan hoa
        # base_url THEM dau `/` o cuoi — so sanh sau khi bo di.
        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 base_url="https://noi-khac.test/v1")
        self.assertEqual(str(p._client.base_url).rstrip("/"),
                         "https://noi-khac.test/v1")

    def test_khong_gui_tham_so_chua_xac_minh(self):
        """
        Ho so Pollinations co `extra_payload` RONG co y (xem
        `translation_model_profiles`). Kiem THAT than request: khong duoc xuat
        hien `reasoning_effort`/`max_completion_tokens` — do la tham so cua
        Groq/Cerebras, gui cho nha cung cap khac la gui sai.
        """
        da_thay = {}

        def handler(req: httpx.Request) -> httpx.Response:
            import json
            da_thay.update(json.loads(req.content.decode()))
            return _tra_loi_chat("xong")

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 client=_client_gia(handler))
        p.translate_segment("你好", context=_ctx())
        self.assertEqual(da_thay["model"], "deepseek")
        self.assertNotIn("reasoning_effort", da_thay)
        self.assertNotIn("reasoning_format", da_thay)
        self.assertNotIn("max_completion_tokens", da_thay)


class PollinationsRetryScopeTest(unittest.TestCase):
    """
    Thu lai CUC BO co gioi han, CHI cho 429. Het luot thi loi LAN LEN de
    `ProviderRegistry` doi sang nha cung cap DOC LAP khac.
    """

    def test_mac_dinh_khong_thu_lai(self):
        dem = {"n": 0}

        def handler(req):
            dem["n"] += 1
            return httpx.Response(429, text="rate limited")

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 client=_client_gia(handler))
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("x", context=_ctx())
        self.assertEqual(dem["n"], 1, "mac dinh retry_count=0 -> goi DUNG mot lan")

    def test_retry_count_gioi_han_dung_so_lan(self):
        dem = {"n": 0}

        def handler(req):
            dem["n"] += 1
            return httpx.Response(429, text="rate limited")

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 retry_count=2, client=_client_gia(handler))
        p.RETRY_DELAY_SECONDS = 0  # khong lam cham bo test
        with self.assertRaises(ProviderRateLimited):
            p.translate_segment("x", context=_ctx())
        self.assertEqual(dem["n"], 3, "retry_count=2 -> 1 lan dau + 2 lan thu lai")

    def test_thu_lai_thanh_cong_thi_tra_ket_qua(self):
        dem = {"n": 0}

        def handler(req):
            dem["n"] += 1
            if dem["n"] == 1:
                return httpx.Response(429, text="rate limited")
            return _tra_loi_chat("Dược Lão")

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 retry_count=1, client=_client_gia(handler))
        p.RETRY_DELAY_SECONDS = 0
        self.assertEqual(p.translate_segment("药老", context=_ctx()), "Dược Lão")
        self.assertEqual(dem["n"], 2)

    def test_KHONG_thu_lai_loi_credential(self):
        """401 la loi khong the doi ket qua — thu lai chi lam cham fallback."""
        dem = {"n": 0}

        def handler(req):
            dem["n"] += 1
            return httpx.Response(401, text="unauthorized")

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 retry_count=3, client=_client_gia(handler))
        p.RETRY_DELAY_SECONDS = 0
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("x", context=_ctx())
        self.assertEqual(dem["n"], 1, "401 -> KHONG thu lai")

    def test_KHONG_thu_lai_phan_hoi_sai_hinh_dang(self):
        dem = {"n": 0}

        def handler(req):
            dem["n"] += 1
            return httpx.Response(200, json={"khong": "dung hinh dang"})

        p = PollinationsProvider(api_key="sk_gia", profile=_DEEPSEEK,
                                 retry_count=3, client=_client_gia(handler))
        p.RETRY_DELAY_SECONDS = 0
        with self.assertRaises(TranslationProviderError):
            p.translate_segment("x", context=_ctx())
        self.assertEqual(dem["n"], 1)


class PollinationsRaoChanTinhPhiTest(unittest.TestCase):
    """
    RAO CHAN quan trong nhat: khong bao gio tu dua Pollinations vao duong thu
    tu dong chi vi co API key.
    """

    def _ids(self, env):
        return [e.provider_id for e in build_provider_registry(env=env).catalog()]

    def test_khong_co_key_thi_khong_co_provider(self):
        self.assertEqual(self._ids({}), [])

    def test_CHI_co_key_thi_VAN_khong_vao_registry(self):
        ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia"})
        self.assertEqual(
            ids, [],
            "tra phi theo mac dinh: chi co key KHONG du de tu dong dung")

    def test_free_tier_tuong_minh_thi_vao_registry(self):
        ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia",
                         "POLLINATIONS_FREE_TIER": "true"})
        self.assertEqual(
            ids,
            [f"pollinations_{k}" for k in POLLINATIONS_MODEL_PROFILES],
            "moi model curated thanh MOT muc rieng, dung thu tu ho so")

    def test_rao_chan_chung_MOT_MINH_van_KHONG_du(self):
        """
        Phat hien khi viet test nay (khong phai gia dinh ban dau):
        `TRANSLATION_ALLOW_PAID_PROVIDER=true` MOT MINH van KHONG du.

        Ly do: `build_provider_registry` chi bo qua buoc loc CUOI
        (`if not cho_phep_tra_phi`), nhung `ProviderRegistry.__init__` con loc
        `[p for p in providers if p.free_tier]` VO DIEU KIEN — dung nhu
        docstring cua no ("an toan kep"). Nen provider co `free_tier=False`
        KHONG BAO GIO vao duoc registry dung chung, du rao chan chung da mo.

        Provider "custom" san co cung co dung tinh chat nay. Ket luan: duong
        DUY NHAT de dung Pollinations la dat `POLLINATIONS_FREE_TIER=true`
        (tuyen bo RO rang rang tai khoan nay o hang mien phi). Day la hanh vi
        AN TOAN HON, nen kiem lai o day de khong ai "sua" no thanh long hon.
        """
        ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia",
                         "TRANSLATION_ALLOW_PAID_PROVIDER": "true"})
        self.assertEqual(ids, [])

    def test_free_tier_va_rao_chan_chung_cung_bat(self):
        ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia",
                         "POLLINATIONS_FREE_TIER": "true",
                         "TRANSLATION_ALLOW_PAID_PROVIDER": "true"})
        self.assertEqual(len(ids), len(POLLINATIONS_MODEL_PROFILES))

    def test_free_tier_sai_chinh_ta_KHONG_mo_rao(self):
        for gia_tri in ("True ", "yes", "1", "on", ""):
            with self.subTest(gia_tri=gia_tri):
                ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia",
                                 "POLLINATIONS_FREE_TIER": gia_tri})
                if gia_tri.strip().lower() == "true":
                    self.assertTrue(ids)
                else:
                    self.assertEqual(ids, [], "chi dung 'true' moi mo rao")

    def test_catalog_KHONG_lo_api_key(self):
        reg = build_provider_registry(env={
            "POLLINATIONS_API_KEY": "sk_bi_mat_khong_duoc_lo",
            "POLLINATIONS_FREE_TIER": "true"})
        van_ban = repr([e.to_dict() for e in reg.catalog()])
        self.assertNotIn("sk_bi_mat_khong_duoc_lo", van_ban)

    def test_retry_count_sai_dinh_dang_khong_lam_sap_registry(self):
        ids = self._ids({"POLLINATIONS_API_KEY": "sk_gia",
                         "POLLINATIONS_FREE_TIER": "true",
                         "POLLINATIONS_RETRY_COUNT": "khong-phai-so"})
        self.assertEqual(len(ids), len(POLLINATIONS_MODEL_PROFILES))


class PollinationsKhongHoiQuyTest(unittest.TestCase):
    """Them Pollinations KHONG duoc lam doi hanh vi provider dang co."""

    def test_thu_tu_provider_cu_giu_nguyen(self):
        env_cu = {"CEREBRAS_API_KEY": "c", "GROQ_API_KEY": "g"}
        truoc = [e.provider_id for e in build_provider_registry(env=env_cu).catalog()]
        env_moi = dict(env_cu, POLLINATIONS_API_KEY="sk_gia",
                       POLLINATIONS_FREE_TIER="true")
        sau = [e.provider_id for e in build_provider_registry(env=env_moi).catalog()]
        self.assertEqual(
            sau[:len(truoc)], truoc,
            "provider cu phai giu DUNG thu tu cu; Pollinations noi vao CUOI")
        self.assertTrue(all(i.startswith("pollinations_") for i in sau[len(truoc):]))

    def test_khong_bat_Pollinations_thi_registry_giong_het_truoc(self):
        env_cu = {"CEREBRAS_API_KEY": "c", "GROQ_API_KEY": "g"}
        truoc = [e.provider_id for e in build_provider_registry(env=env_cu).catalog()]
        sau = [e.provider_id for e in build_provider_registry(
            env=dict(env_cu, POLLINATIONS_API_KEY="sk_gia")).catalog()]
        self.assertEqual(truoc, sau)

    def test_model_command_a_plus_KHONG_nam_trong_ho_so(self):
        """
        Benchmark THAT (2026-08-15) ghi nhan `command-a-plus` dung pinyin thay
        vi phien am Han Viet ("Xiao Yan" thay vi "Tieu Viem") va dich sai ten
        rieng. Da loai CO Y — test nay giu quyet dinh do khoi bi lang le dao
        nguoc.
        """
        for k, p in POLLINATIONS_MODEL_PROFILES.items():
            self.assertNotIn("command", p.model_id.lower())
            self.assertNotIn("command", k.lower())


if __name__ == "__main__":
    unittest.main()
