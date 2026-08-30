import unittest

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import AcquisitionStatus, SourceClass
from server.scraper.universal.adapter import SourceCapabilities, StoryProviderAdapter

_BASE = "https://vd-universal.example"


def _make_pages(n: int) -> dict:
    links = "".join(f'<li><a href="/truyen/x/chuong-{i}">C{i}</a></li>' for i in range(1, n + 1))
    pages = {f"{_BASE}/truyen/x": f"<html><body><ul>{links}</ul></body></html>"}
    for i in range(1, n + 1):
        pages[f"{_BASE}/truyen/x/chuong-{i}"] = (
            f"<html><body><article><h1>Chuong {i}</h1><p>"
            + ("Noi dung day du cua chuong. " * 15)
            + "</p></article></body></html>")
    return pages


def _make_bridge(n=3):
    pages = _make_pages(n)
    provider = GenericIndexAdapter(FixtureFetcher(pages), chapter_href_pattern=r"/chuong-\d+")
    return StoryProviderAdapter(provider), pages


class SourceCapabilitiesTest(unittest.TestCase):
    def test_rong_source_classes_nem_loi(self):
        with self.assertRaises(ValueError):
            SourceCapabilities(source_classes=frozenset()).validate()

    def test_hop_le_khong_nem_loi(self):
        SourceCapabilities(source_classes=frozenset({SourceClass.WEB_FICTION})).validate()


class StoryProviderAdapterTest(unittest.TestCase):
    def test_probe_true_cho_url_ho_tro(self):
        bridge, _ = _make_bridge()
        self.assertTrue(bridge.probe(f"{_BASE}/truyen/x"))

    def test_probe_false_cho_url_khong_ho_tro(self):
        bridge, _ = _make_bridge()
        self.assertFalse(bridge.probe("https://khac-han.example/x"))

    def test_capabilities_khai_bao_web_fiction(self):
        bridge, _ = _make_bridge()
        caps = bridge.capabilities()
        self.assertIn(SourceClass.WEB_FICTION, caps.source_classes)
        caps.validate()

    def test_canonicalize_tra_ve_url_that(self):
        bridge, _ = _make_bridge()
        self.assertEqual(bridge.canonicalize(f"{_BASE}/truyen/x"), f"{_BASE}/truyen/x")

    def test_extract_metadata_co_title(self):
        bridge, _ = _make_bridge()
        meta = bridge.extract_metadata(f"{_BASE}/truyen/x")
        self.assertIn("title", meta)
        self.assertIn("canonical_url", meta)

    def test_list_units_tra_dung_so_chuong(self):
        bridge, _ = _make_bridge(3)
        units = bridge.list_units(f"{_BASE}/truyen/x")
        self.assertEqual(len(units), 3)

    def test_fetch_unit_ok_that(self):
        bridge, pages = _make_bridge(1)
        bridge.list_units(f"{_BASE}/truyen/x")
        unit_ref = f"{_BASE}/truyen/x/chuong-1"
        acq = bridge.fetch_unit(unit_ref)
        self.assertEqual(acq.status, AcquisitionStatus.OK)
        self.assertTrue(acq.ok)
        self.assertIn("Chuong 1", acq.html)

    def test_fetch_unit_that_bai_tra_status_failed_khong_nem_loi(self):
        bridge, _ = _make_bridge(1)
        bridge.list_units(f"{_BASE}/truyen/x")
        acq = bridge.fetch_unit(f"{_BASE}/truyen/x/chuong-khong-ton-tai")
        self.assertEqual(acq.status, AcquisitionStatus.FAILED)
        self.assertFalse(acq.ok)
        self.assertTrue(acq.errors)

    def test_normalize_truoc_list_units_nem_loi_ro_rang(self):
        bridge, _ = _make_bridge(1)
        acq = bridge.fetch_unit(f"{_BASE}/truyen/x/chuong-1")
        with self.assertRaises(RuntimeError):
            bridge.normalize(f"{_BASE}/truyen/x/chuong-1", acq)

    def test_normalize_va_stable_identity_full_round_trip(self):
        bridge, _ = _make_bridge(1)
        unit_ref = f"{_BASE}/truyen/x/chuong-1"
        bridge.list_units(f"{_BASE}/truyen/x")
        acq = bridge.fetch_unit(unit_ref)
        chapter = bridge.normalize(unit_ref, acq)
        identity = bridge.stable_identity(chapter)
        self.assertTrue(identity)
        self.assertEqual(identity, chapter.source_fingerprint)


if __name__ == "__main__":
    unittest.main()
