"""Sổ đăng ký adapter — Story Harvester V4, Phase A.

Điều đáng kiểm không phải "tra cứu có chạy không", mà là các cách hỏng **im
lặng**: hai adapter cùng nhận một host (ai thắng phụ thuộc thứ tự import), một
bản khai năng lực mâu thuẫn (bộ lập lịch tin nó rồi xếp sai worker), hoặc một
host viết hơi khác (`WWW.`, cổng, dấu chấm cuối) rơi nhầm vào "không hỗ trợ".
"""
from __future__ import annotations

import unittest

from server.scraper.adapters import (
    AdapterCapabilities,
    AdapterRegistration,
    AdapterRegistry,
    DuplicateHostError,
    InvalidRegistrationError,
    UnsupportedUrlError,
    default_registry,
    normalize_host,
)


def _cap(hosts=("vd.test",), **kw):
    return AdapterCapabilities(supported_hosts=tuple(hosts), **kw)


def _reg(name="a", hosts=("vd.test",), **kw):
    return AdapterRegistration(name=name, capabilities=_cap(hosts, **kw),
                               build=lambda url, fetcher: object())


class ChuanHoaHostTest(unittest.TestCase):
    """Cùng một host viết nhiều kiểu phải về cùng một khoá."""

    def test_cac_bien_the_deu_ve_mot_host(self):
        for u in ("https://vd.test/a", "https://WWW.VD.TEST/a",
                  "https://vd.test:443/a", "https://vd.test./a",
                  "http://user:pw@www.vd.test:8080/a"):
            self.assertEqual(normalize_host(u), "vd.test", u)

    def test_chuoi_host_tran_cung_dung(self):
        self.assertEqual(normalize_host("WWW.Vd.Test."), "vd.test")

    def test_ipv6_khong_bi_cat_nham(self):
        """`split(':')` ngây thơ sẽ cắt nát một host IPv6."""
        self.assertEqual(normalize_host("http://[::1]:8080/a"), "[::1]")

    def test_chuoi_rong(self):
        self.assertEqual(normalize_host(""), "")


class DangKyHopLeTest(unittest.TestCase):
    def test_host_rong_bi_tu_choi(self):
        """Adapter không nhận host nào thì không bao giờ được chọn — im lặng
        bỏ qua nó trông y hệt 'URL không được hỗ trợ'."""
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(_reg(hosts=()))

    def test_host_chua_chuan_hoa_bi_tu_choi(self):
        for xau in ("WWW.vd.test", "vd.test:443", "vd.test.", "VD.TEST"):
            with self.assertRaises(InvalidRegistrationError, msg=xau):
                AdapterRegistry().register(_reg(hosts=(xau,)))

    def test_chien_luoc_chuan_hoa_la_bi_tu_choi(self):
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(_reg(canonicalization="bia_dat"))

    def test_khong_tai_tinh_va_khong_can_trinh_duyet_la_mau_thuan(self):
        """Không có đường nào lấy được nội dung."""
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(
                _reg(supports_static_fetch=False, requires_browser=False))

    def test_gia_tang_ma_khong_co_danh_tinh_on_dinh_la_mau_thuan(self):
        """Cập nhật gia tăng so theo danh tính chương. Không ổn định thì mọi
        lượt quét đều đọc thành 'chương mới' — đúng thứ nó sinh ra để tránh."""
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(
                _reg(supports_incremental_updates=True,
                     stable_chapter_identity=False))

    def test_ten_rong_bi_tu_choi(self):
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(
                AdapterRegistration(name="  ", capabilities=_cap(),
                                    build=lambda u, f: object()))

    def test_build_khong_goi_duoc_bi_tu_choi(self):
        with self.assertRaises(InvalidRegistrationError):
            AdapterRegistry().register(
                AdapterRegistration(name="a", capabilities=_cap(), build="khong phai ham"))

    def test_khai_bao_hop_le_thi_qua(self):
        r = AdapterRegistry()
        r.register(_reg())
        self.assertEqual(r.names(), ["a"])


class QuyenSoHuuHostTest(unittest.TestCase):
    def test_hai_adapter_cung_nhan_mot_host_bi_tu_choi(self):
        """Không ghi đè: ai thắng sẽ phụ thuộc thứ tự import — một cách hỏng
        không tái hiện được."""
        r = AdapterRegistry()
        r.register(_reg(name="a", hosts=("vd.test",)))
        with self.assertRaises(DuplicateHostError) as ctx:
            r.register(_reg(name="b", hosts=("vd.test",)))
        self.assertIn("vd.test", str(ctx.exception))
        self.assertIn("a", str(ctx.exception))

    def test_dang_ky_lai_CHINH_no_thi_khong_sao(self):
        """Nạp lại cùng một adapter là vô hại; chỉ tranh chấp mới là lỗi."""
        r = AdapterRegistry()
        r.register(_reg(name="a"))
        r.register(_reg(name="a"))
        self.assertEqual(r.hosts(), ["vd.test"])

    def test_host_khac_nhau_thi_cung_ton_tai_duoc(self):
        r = AdapterRegistry()
        r.register(_reg(name="a", hosts=("vd.test",)))
        r.register(_reg(name="b", hosts=("khac.test",)))
        self.assertEqual(r.hosts(), ["khac.test", "vd.test"])


class KhongNhapNhangTest(unittest.TestCase):
    """Nhập nhằng bị chặn ở ĐĂNG KÝ, nên lúc chạy không phải phân xử."""

    def test_subdomain_KHONG_khop_gan_dung(self):
        """`sub.vd.test` khi chỉ có `vd.test` phải là "không hỗ trợ".
        Khớp gần đúng ở đây sẽ quét nhầm sang một site khác."""
        r = AdapterRegistry()
        r.register(_reg(name="a", hosts=("vd.test",)))
        with self.assertRaises(UnsupportedUrlError):
            r.resolve("https://sub.vd.test/x")

    def test_mot_url_chi_khop_dung_mot_adapter(self):
        r = AdapterRegistry()
        r.register(_reg(name="a", hosts=("vd.test",)))
        r.register(_reg(name="b", hosts=("khac.test",)))
        self.assertEqual(r.resolve("https://vd.test/x").name, "a")
        self.assertEqual(r.resolve("https://khac.test/x").name, "b")


class TraCuuTest(unittest.TestCase):
    def setUp(self):
        self.r = AdapterRegistry()
        self.r.register(_reg(name="a", hosts=("vd.test",)))

    def test_tra_cuu_dung_adapter(self):
        self.assertEqual(self.r.resolve("https://vd.test/truyen/1").name, "a")

    def test_bien_the_host_van_tra_cuu_duoc(self):
        for u in ("https://WWW.vd.test/x", "https://vd.test:443/x",
                  "https://vd.test./x"):
            self.assertEqual(self.r.resolve(u).name, "a", u)

    def test_host_khong_ho_tro_nem_loi_RIENG(self):
        """`UnsupportedUrlError` khác hẳn 'có adapter nhưng hỏng' — nơi gọi
        cần phân biệt để báo đúng cho người vận hành."""
        with self.assertRaises(UnsupportedUrlError) as ctx:
            self.r.resolve("https://khong-biet.test/x")
        self.assertIn("khong-biet.test", str(ctx.exception))

    def test_url_khong_co_host_nem_loi(self):
        with self.assertRaises(UnsupportedUrlError):
            self.r.resolve("khong-phai-url")

    def test_find_tra_None_thay_vi_nem(self):
        self.assertIsNone(self.r.find("https://khong-biet.test/x"))
        self.assertIsNotNone(self.r.find("https://vd.test/x"))

    def test_thong_bao_loi_liet_ke_host_dang_ho_tro(self):
        with self.assertRaises(UnsupportedUrlError) as ctx:
            self.r.resolve("https://khac.test/x")
        self.assertIn("vd.test", str(ctx.exception))


class SoDangKyMacDinhTest(unittest.TestCase):
    """Sổ mặc định phải khớp `site_registry` — không chép tay."""

    def test_moi_domain_cua_site_registry_deu_co_adapter(self):
        from server.scraper import site_registry

        r = default_registry()
        for d in site_registry.supported_domains():
            self.assertIsNotNone(r.find(f"https://{d}/x"),
                                 f"{d} có trong site_registry nhưng không có adapter")

    def test_khong_them_host_nao_ngoai_site_registry(self):
        """Sổ đăng ký nhận một host mà `site_registry` không cấu hình sẽ làm
        `build` nổ lúc chạy — bắt ở đây rẻ hơn nhiều."""
        from server.scraper import site_registry

        hop_le = {normalize_host(d) for d in site_registry.supported_domains()}
        self.assertEqual(set(default_registry().hosts()), hop_le)

    def test_nang_luc_cua_generic_index_hop_le(self):
        cap = default_registry().capabilities_of("generic_index")
        self.assertTrue(cap.supports_chapter_index)
        self.assertTrue(cap.supports_incremental_updates)
        self.assertFalse(cap.requires_browser)
        cap.validate("generic_index")          # khong duoc nem

    def test_dung_duoc_adapter_that_tu_url_that(self):
        from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
        from server.scraper.http_fetcher import FixtureFetcher

        r = default_registry()
        provider = r.build_for(
            "https://vi.wikisource.org/wiki/L%E1%BB%81u_ch%C3%B5ng",
            FixtureFetcher({}))
        self.assertIsInstance(provider, GenericIndexAdapter)

    def test_url_dung_host_nhung_SAI_HINH_DANG_khong_bi_nuot(self):
        """`royalroad.com` cần ID truyện ngay trong đường dẫn. Một URL đúng
        host nhưng thiếu ID là lỗi THẬT của người dùng, và `site_registry`
        ném `ScopeExtractionError` để nói rõ điều đó.

        Sổ đăng ký phải ĐỂ NGUYÊN lỗi ấy. Bắt rồi lùi về một pattern rỗng sẽ
        quét nhầm sang truyện khác xuất hiện trên cùng trang — đúng cái bẫy
        mà `scope_id_pattern` sinh ra để chặn."""
        from server.scraper.http_fetcher import FixtureFetcher
        from server.scraper.site_registry import ScopeExtractionError

        with self.assertRaises(ScopeExtractionError):
            default_registry().build_for("https://royalroad.com/",
                                         FixtureFetcher({}))

    def test_nang_luc_cua_ten_khong_co_thi_nem(self):
        with self.assertRaises(UnsupportedUrlError):
            default_registry().capabilities_of("khong_ton_tai")


class HopDongTuongLaiTest(unittest.TestCase):
    """Hợp đồng V4 phải chứa được nguồn kiểu khác mà KHÔNG phải sửa gì."""

    def test_nguon_can_trinh_duyet_khai_bao_duoc(self):
        r = AdapterRegistry()
        r.register(_reg(name="browser", hosts=("js.test",),
                        requires_browser=True, supports_static_fetch=False))
        self.assertTrue(r.capabilities_of("browser").requires_browser)

    def test_nguon_khong_co_trang_muc_luc_khai_bao_duoc(self):
        r = AdapterRegistry()
        r.register(_reg(name="khong_muc_luc", hosts=("x.test",),
                        supports_chapter_index=False))
        self.assertFalse(r.capabilities_of("khong_muc_luc").supports_chapter_index)

    def test_nguon_co_ID_rieng_khai_bao_duoc(self):
        r = AdapterRegistry()
        r.register(_reg(name="co_id", hosts=("y.test",),
                        canonicalization="source_id"))
        self.assertEqual(r.capabilities_of("co_id").canonicalization, "source_id")


if __name__ == "__main__":
    unittest.main()
