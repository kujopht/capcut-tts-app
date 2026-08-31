"""server/import_pipeline/pipeline.py — AuthorizedImportService end-to-end
(kho Mock, khong mang, khong Appwrite)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.adapters import MockImportRecordStore, MockMetadataStore
from server.domain import Chapter, PublicationMode, RightsBasis
from server.fandom_registry import FandomRegistry
from server.import_pipeline.formats import UnsupportedImportFormatError
from server.import_pipeline.pipeline import (
    AuthorizedImportService, NoContentExtractedError,
)
from server.scraper.raw_archive import SensitiveContentDetected


def _tao_tao_chuong_gia(store):
    """Mo phong dung chu ky/hanh vi cot loi cua
    `main.py::_tao_chuong_cho_truyen` — tao qua `store.create_chapter_once`,
    KHONG lam thong bao/XP (khong can cho test nay)."""
    def _tao_chuong(*, novel, owner_id, title, content, order_index,
                    bao_nguoi_theo_doi=True):
        chuong = Chapter(novel_id=novel.novel_id, owner_id=owner_id,
                         title=title.strip(), content=content, order_index=order_index)
        return store.create_chapter_once(chuong)
    return _tao_chuong


class AuthorizedImportServiceTestBase(unittest.TestCase):
    def setUp(self):
        self.store = MockMetadataStore()
        self.import_records = MockImportRecordStore()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = AuthorizedImportService(
            self.store, self.import_records, tao_chuong=_tao_tao_chuong_gia(self.store),
            fandom_registry=FandomRegistry(), spool_root=Path(self._tmp.name))


class ImportTxtTest(AuthorizedImportServiceTestBase):
    def test_nhap_txt_that_tao_novel_chapter_that_o_draft(self):
        raw = "Chương 1\nNội dung chương một.\nChương 2\nNội dung chương hai."
        ket_qua = self.svc.import_authorized_work(
            data=raw.encode("utf-8"), filename="truyen.txt", declared_format="txt",
            owner_id="u1", title="Truyện thử nghiệm",
            rights_basis=RightsBasis.AUTHOR, fandom_names=["Naruto"])

        self.assertEqual(len(ket_qua.chapters), 2)
        self.assertEqual(ket_qua.novel.state.value, "draft")
        self.assertEqual(len(ket_qua.novel.fandom_ids), 1)
        self.assertEqual(ket_qua.fandom_match_summary["unmatched"], [])
        self.assertEqual(ket_qua.import_record.rights_basis, RightsBasis.AUTHOR)
        self.assertEqual(ket_qua.import_record.novel_id, ket_qua.novel.novel_id)
        self.assertTrue(ket_qua.raw_archive_local_dir.exists())

    def test_fandom_chua_biet_khong_lam_hong_nhap_van_ghi_unmatched(self):
        raw = "Chương 1\nNội dung."
        ket_qua = self.svc.import_authorized_work(
            data=raw.encode("utf-8"), filename="t.txt", declared_format="txt",
            owner_id="u1", title="T", rights_basis=RightsBasis.AUTHOR,
            fandom_names=["Mot Fandom La"])
        self.assertEqual(ket_qua.novel.fandom_ids, [])
        self.assertEqual(ket_qua.fandom_match_summary["unmatched"], ["Mot Fandom La"])

    def test_khong_co_noi_dung_nem_loi_ro_rang(self):
        with self.assertRaises(NoContentExtractedError):
            self.svc.import_authorized_work(
                data=b"", filename="rong.txt", declared_format="txt",
                owner_id="u1", title="T", rights_basis=RightsBasis.AUTHOR)

    def test_du_lieu_nhay_cam_bi_chan(self):
        raw = "Chương 1\nliên hệ tôi qua contact@example.com nhé."
        with self.assertRaises(SensitiveContentDetected):
            self.svc.import_authorized_work(
                data=raw.encode("utf-8"), filename="t.txt", declared_format="txt",
                owner_id="u1", title="T", rights_basis=RightsBasis.AUTHOR)

    def test_dinh_dang_khong_ho_tro_nem_loi_ro_rang(self):
        with self.assertRaises(UnsupportedImportFormatError):
            self.svc.import_authorized_work(
                data=b"data", filename="t.pdf", declared_format="pdf",
                owner_id="u1", title="T", rights_basis=RightsBasis.AUTHOR)

    def test_metadata_only_publication_mode_duoc_giu(self):
        raw = "Chương 1\nNội dung."
        ket_qua = self.svc.import_authorized_work(
            data=raw.encode("utf-8"), filename="t.txt", declared_format="txt",
            owner_id="u1", title="T", rights_basis=RightsBasis.PERMISSION_GRANTED,
            publication_mode=PublicationMode.METADATA_ONLY)
        self.assertEqual(ket_qua.novel.publication_mode, PublicationMode.METADATA_ONLY)
        self.assertEqual(ket_qua.import_record.rights_basis, RightsBasis.PERMISSION_GRANTED)


class ImportZipTest(AuthorizedImportServiceTestBase):
    def test_nhap_zip_gop_nhieu_tep_theo_thu_tu_ten(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("01-mot.txt", "Chương 1\nNội dung một.")
            zf.writestr("02-hai.txt", "Chương 2\nNội dung hai.")
        ket_qua = self.svc.import_authorized_work(
            data=buf.getvalue(), filename="truyen.zip", declared_format="zip",
            owner_id="u1", title="T", rights_basis=RightsBasis.AUTHOR)
        self.assertEqual(len(ket_qua.chapters), 2)


if __name__ == "__main__":
    unittest.main()
