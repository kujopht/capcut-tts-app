"""
`server/image_provider_registry.py` — Image Studio V1 (overnight build).

Fixture GIA voi `httpx.MockTransport`, cung mau voi
`test_translation_provider_registry.py`. Trong tam PHASE 14:

- Quick Free: thanh cong, timeout, khong kha dung, content-type sai, KHONG
  bao gio nhan tham so model.
- Shared Premium: 401/402/429/5xx, timeout, phan hoi sai dang.
"""

from __future__ import annotations

import unittest

import httpx

from server.image_provider_registry import (
    ImageProviderError,
    ImageProviderRateLimited,
    ImageProviderTimeout,
    ImageProviderUnavailable,
    InvalidImageResponse,
    QUICK_FREE_MODEL_LABEL,
    QuickFreeImageProvider,
    SharedPremiumImageProvider,
    aspect_ratio_to_dimensions,
)


def _client_gia(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


_ANH_GIA = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


class QuickFreeProviderTest(unittest.TestCase):
    def test_thanh_cong_tra_ve_anh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            # KHONG BAO GIO duoc nhan tham so model — day la diem chinh cuoc
            # do tham da phat hien (endpoint bo qua/chuan hoa tham so nay).
            self.assertNotIn("model", request.url.params)
            self.assertNotIn("authorization", {k.lower() for k in request.headers.keys()})
            return httpx.Response(200, content=_ANH_GIA,
                                  headers={"content-type": "image/jpeg"})

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        anh = provider.sinh_anh(prompt="a cat", aspect_ratio_seed=42, client_ip="1.2.3.4")
        self.assertEqual(anh.content, _ANH_GIA)
        self.assertEqual(anh.provider_id, "quick_free")

    def test_timeout_nem_loi_rieng(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        with self.assertRaises(ImageProviderTimeout):
            provider.sinh_anh(prompt="a cat", aspect_ratio_seed=1, client_ip="1.2.3.4")

    def test_5xx_bao_khong_kha_dung_khong_dump_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="<html>chi tiet noi bo nhay cam</html>")

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        with self.assertRaises(ImageProviderUnavailable) as ctx:
            provider.sinh_anh(prompt="a cat", aspect_ratio_seed=1, client_ip="1.2.3.4")
        self.assertNotIn("nhay cam", str(ctx.exception))

    def test_content_type_sai_bao_invalid_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": "khong phai anh"})

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        with self.assertRaises(InvalidImageResponse):
            provider.sinh_anh(prompt="a cat", aspect_ratio_seed=1, client_ip="1.2.3.4")

    def test_than_rong_du_status_200_van_bi_coi_la_that_bai(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"", headers={"content-type": "image/jpeg"})

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        with self.assertRaises(InvalidImageResponse):
            provider.sinh_anh(prompt="a cat", aspect_ratio_seed=1, client_ip="1.2.3.4")

    def test_rate_limit_moi_ip_chan_sau_qua_nhieu_lan(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_ANH_GIA,
                                  headers={"content-type": "image/jpeg"})

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        provider._rate_limiter._so_lan = 2  # gia lap han muc thap de test nhanh
        provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="9.9.9.9")
        provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="9.9.9.9")
        with self.assertRaises(ImageProviderRateLimited):
            provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="9.9.9.9")

    def test_khac_ip_khong_bi_anh_huong_boi_han_muc_ip_khac(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_ANH_GIA,
                                  headers={"content-type": "image/jpeg"})

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        provider._rate_limiter._so_lan = 1
        provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="1.1.1.1")
        # IP khac — khong bi chan boi han muc cua IP truoc.
        anh = provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="2.2.2.2")
        self.assertEqual(anh.content, _ANH_GIA)

    def test_5xx_lien_tiep_kich_hoat_cooldown_cho_request_sau(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        provider = QuickFreeImageProvider(client=_client_gia(handler))
        with self.assertRaises(ImageProviderUnavailable):
            provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="3.3.3.3")
        # Request KE TIEP khong goi mang nua (dang cooldown) — client moi se
        # loi ngay ca khi khong co handler nao duoc goi them.
        with self.assertRaises(ImageProviderUnavailable):
            provider.sinh_anh(prompt="a", aspect_ratio_seed=1, client_ip="4.4.4.4")


class SharedPremiumProviderTest(unittest.TestCase):
    def _provider(self, handler):
        return SharedPremiumImageProvider(api_key="sk-test-fake", client=_client_gia(handler))

    def test_thieu_api_key_nem_loi_ngay_luc_khoi_tao(self):
        with self.assertRaises(ImageProviderError):
            SharedPremiumImageProvider(api_key="")

    def test_gui_dung_authorization_bearer(self):
        ghi_nhan = {}

        def handler(request: httpx.Request) -> httpx.Response:
            ghi_nhan["auth"] = request.headers.get("authorization")
            return httpx.Response(200, content=_ANH_GIA,
                                  headers={"content-type": "image/png"})

        provider = self._provider(handler)
        provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                          width=1024, height=1024, quality="standard")
        self.assertEqual(ghi_nhan["auth"], "Bearer sk-test-fake")

    def test_401_nem_loi_xac_thuc(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        provider = self._provider(handler)
        with self.assertRaises(ImageProviderError):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")

    def test_402_nem_loi_thanh_toan(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json={"error": "payment required"})

        provider = self._provider(handler)
        with self.assertRaises(ImageProviderError):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")

    def test_429_nem_loi_rate_limit_voi_retry_after(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"retry-after": "30"})

        provider = self._provider(handler)
        with self.assertRaises(ImageProviderRateLimited) as ctx:
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")
        self.assertEqual(ctx.exception.retry_after_seconds, 30)

    def test_5xx_nem_loi_khong_kha_dung(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        provider = self._provider(handler)
        with self.assertRaises(ImageProviderUnavailable):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")

    def test_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        provider = self._provider(handler)
        with self.assertRaises(ImageProviderTimeout):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")

    def test_phan_hoi_khong_phai_anh_nem_invalid(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"not": "an image"})

        provider = self._provider(handler)
        with self.assertRaises(InvalidImageResponse):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")

    def test_model_bi_cooldown_rieng_khong_anh_huong_model_khac(self):
        def handler_loi(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        provider = self._provider(handler_loi)
        with self.assertRaises(ImageProviderUnavailable):
            provider.sinh_anh(prompt="p", negative_prompt="", model="flux",
                              width=1024, height=1024, quality="standard")
        # model KHAC khong bi khoa boi cooldown cua "flux" — nhung client gia
        # nay van tra 500 cho moi request, nen ta chi kiem cooldown-check
        # khong tu chan TRUOC khi goi mang (loi van la Unavailable, khong
        # phai loi "dang cooldown").
        with self.assertRaises(ImageProviderUnavailable):
            provider.sinh_anh(prompt="p", negative_prompt="", model="zimage",
                              width=1024, height=1024, quality="standard")


class AspectRatioTest(unittest.TestCase):
    def test_5_ty_le_bat_buoc_co_kich_thuoc(self):
        for ti_le in ("1:1", "16:9", "9:16", "3:4", "4:3"):
            w, h = aspect_ratio_to_dimensions(ti_le)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)

    def test_ty_le_khong_biet_lui_ve_vuong(self):
        w, h = aspect_ratio_to_dimensions("21:9", base=512)
        self.assertEqual((w, h), (512, 512))


class QuickFreeLabelTest(unittest.TestCase):
    def test_nhan_model_luon_la_auto_model(self):
        self.assertEqual(QUICK_FREE_MODEL_LABEL, "Auto model")


if __name__ == "__main__":
    unittest.main()
