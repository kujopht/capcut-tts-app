"""Kiem thu lop ghi kho san xuat chinh tac.

Trong tam la cac BAT BIEN ma dot ra soat du dieu kien da phat hien la chua
duoc cuong che o dau ca:

    - duong dan TAT DINH, va khong den tu model
    - cay legacy KHONG BAO GIO bi cham toi
    - Drive hong KHONG lam hong duong phuc vu
    - thieu tranh => KHONG READY (chu khong phai "READY nhung xau")
"""
from __future__ import annotations

import json
import shutil
import unittest
from dataclasses import dataclass
from pathlib import Path

from server.farmer import canonical, drive_archive
from server.farmer.artwork import ArtworkError, colours_for, generate
from server.farmer.canonical import (
    ARTIFACT_BACKGROUND, ARTIFACT_COVER, ARTIFACT_MANIFEST, ARTIFACT_TEXT,
    BUCKET_FANFIC_TTS, PRODUCTION_ROOT, WorkManifest,
)
from server.farmer.production_writer import (
    ProductionWriteError, ProductionWriter, normalize_text,
)

URL = "https://archiveofourown.org/works/123456"


@dataclass
class _Verdict:
    approved: bool = True
    decision: str = "approve"
    score: int = 88
    reasons: tuple = ("mach lac", "du dai")
    language: str = "vi"
    model: str = "antigravity/gemini"
    canonical_title: str = "Mot Tac Pham"
    display_title: str = "Mot Tác Phẩm"
    fandom: str = "Nguyen tac X"
    category: str = "fanfic"
    author: str = "ai do"
    content_type: str = "prose"
    completeness: str = "complete"
    tags: tuple = ("the-loai-a",)


class _R2:
    """R2 gia — mot dict. Ghi lai ca content-type de kiem."""

    def __init__(self, hong_voi: str = ""):
        self.objects, self.types = {}, {}
        self._hong_voi = hong_voi

    def put(self, key, data, content_type="application/octet-stream"):
        if self._hong_voi and self._hong_voi in key:
            raise RuntimeError("R2 tu choi")
        self.objects[key] = data
        self.types[key] = content_type

    def get(self, key):
        return self.objects[key]


def _tranh(wid):
    return (b"COVER:" + wid.encode(), b"BG:" + wid.encode())


def _luu_ok(ghi_lai):
    def luu(path, *, work_key, timeout=300):
        ghi_lai.append((work_key, Path(path).name))
        return drive_archive.ArchiveOutcome(
            drive_archive.ARCHIVE_DONE,
            remote_path=f"fanfic-gdrive:{PRODUCTION_ROOT}/{work_key}")
    return luu


def _luu_hong(path, *, work_key, timeout=300):
    return drive_archive.ArchiveOutcome(
        drive_archive.ARCHIVE_PENDING, detail="rclone chua cai")


class NormalizeTest(unittest.TestCase):
    def test_deterministic_and_lossless_enough(self):
        raw = "  Dong mot   \r\n\r\n\r\n\r\n   Dong hai\t\n"
        # Khoang trang DAU TAI LIEU bi bo (mot tep mo dau bang dong trong la
        # rac cua trinh trich xuat), nhung thut dau DONG ben trong thi giu —
        # do co the la dinh dang co y cua tac gia.
        self.assertEqual(normalize_text(raw), "Dong mot\n\n   Dong hai\n")
        self.assertEqual(normalize_text(raw), normalize_text(raw))

    def test_empty_stays_empty(self):
        """Chuoi rong KHONG duoc thanh mot ky tu xuong dong — mot tep 1 byte
        trong nhu mot tep hop le va se qua mat moi phep kiem 'co ton tai'."""
        self.assertEqual(normalize_text("   \n\n  "), "")


class PathsAreDeterministicTest(unittest.TestCase):
    def test_same_source_twice_gives_the_same_directory(self):
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        mot = w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T1",
                               body="noi dung", verdict=_Verdict())
        # Lan hai voi mot TIEU DE KHAC han — duong dan phai KHONG doi.
        hai = w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL,
                               title="Mot tieu de hoan toan khac",
                               body="noi dung", verdict=_Verdict())
        self.assertEqual(mot.canonical_dir, hai.canonical_dir)
        self.assertEqual(mot.work_id, hai.work_id)

    def test_never_writes_into_the_legacy_tree(self):
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                         body="x", verdict=_Verdict())
        for k in a.objects:
            self.assertTrue(k.startswith(PRODUCTION_ROOT + "/"), k)
            self.assertNotIn("FanficWorld/archive", k)


class ArtifactSetTest(unittest.TestCase):
    def test_the_full_canonical_set_is_written(self):
        a, ghi = _R2(), []
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_ok(ghi))
        ket_qua = w.write_approved(
            bucket=BUCKET_FANFIC_TTS, url=URL, title="T", body="noi dung",
            verdict=_Verdict(), novel_id="nov_1", tts_job_id="job_1")

        d = ket_qua.canonical_dir
        for ten in (ARTIFACT_TEXT, ARTIFACT_COVER, ARTIFACT_BACKGROUND,
                    ARTIFACT_MANIFEST):
            self.assertIn(f"{d}/{ten}", a.objects, ten)
        # Chi muc phang de liet ke duoc ma khong quet ca cay.
        self.assertIn(f"{PRODUCTION_ROOT}/{canonical.MANIFESTS}/"
                      f"{ket_qua.work_id}.json", a.objects)
        self.assertTrue(ket_qua.ready)
        self.assertEqual(ket_qua.blocked_reason, "")
        self.assertEqual(a.types[f"{d}/{ARTIFACT_COVER}"], "image/webp")
        # Bon tep di len Drive, moi tep vao dung thu muc con cua no.
        self.assertEqual(len(ghi), 3)                   # text + 2 tranh
        self.assertTrue(any(k.endswith("/artwork") for k, _ in ghi), ghi)

    def test_manifest_keeps_the_originals_and_the_normalized_side_by_side(self):
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        r = w.write_approved(
            bucket=BUCKET_FANFIC_TTS, url=URL, title="Tieu de GOC",
            body="than bai", verdict=_Verdict(), novel_id="nov_9",
            tts_job_id="job_9", source_meta={"provider_id": "ao3:123456",
                                             "_disabled": False})
        man = json.loads(a.objects[f"{r.canonical_dir}/{ARTIFACT_MANIFEST}"])

        # Ban GOC con nguyen — chuan hoa khong duoc lam mat no.
        self.assertEqual(man["source"]["title"], "Tieu de GOC")
        self.assertEqual(man["source"]["url"], URL)
        self.assertEqual(man["source"]["provider_id"], "ao3:123456")
        self.assertIn("body_sha256", man["source"]["hashes"])
        # Ban da chuan hoa nam RIENG.
        self.assertEqual(man["normalized"]["canonical_title"], "Mot Tac Pham")
        self.assertEqual(man["normalized"]["quality_score"], 88)
        # Dinh danh ben duong phuc vu truy nguoc duoc.
        self.assertEqual(man["serving"]["novel_id"], "nov_9")
        self.assertEqual(man["serving"]["tts_job_id"], "job_9")
        # Co dieu khien cua tep nguon KHONG phai su that ve tac pham.
        self.assertNotIn("_disabled", man["source"]["metadata_raw"])
        # Doc lai duoc.
        self.assertEqual(WorkManifest.from_dict(man).work_id, r.work_id)


class FailureModesTest(unittest.TestCase):
    def test_drive_failure_never_breaks_the_serving_path(self):
        """Yeu cau nen tang: mot su co Drive KHONG BAO GIO duoc lam hong mot
        object R2 hop le, va khong duoc nem."""
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        r = w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                             body="x", verdict=_Verdict())
        self.assertEqual(r.archive_status, drive_archive.ARCHIVE_PENDING)
        self.assertTrue(r.ready, "Drive hong khong duoc chan READY")
        self.assertIn(f"{r.canonical_dir}/{ARTIFACT_TEXT}", a.objects)
        man = json.loads(a.objects[f"{r.canonical_dir}/{ARTIFACT_MANIFEST}"])
        self.assertEqual(man["archive"]["state"], drive_archive.ARCHIVE_PENDING)

    def test_missing_artwork_blocks_ready_but_keeps_the_work(self):
        def tranh_hong(wid):
            raise ArtworkError("khong tim thay ffmpeg")

        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=tranh_hong,
                             archive_file=_luu_hong)
        r = w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                             body="x", verdict=_Verdict())
        self.assertFalse(r.ready)
        self.assertIn("ffmpeg", r.blocked_reason)
        # Van ban VAN duoc ghi — tac pham khong bi vut di, no chi chua READY.
        self.assertIn(f"{r.canonical_dir}/{ARTIFACT_TEXT}", a.objects)
        man = json.loads(a.objects[f"{r.canonical_dir}/{ARTIFACT_MANIFEST}"])
        self.assertFalse(man["ready"])

    def test_a_broken_serving_write_is_a_real_error(self):
        """Khac han Drive: khong ghi duoc van ban thi KHONG co tac pham."""
        a = _R2(hong_voi="normalized.txt")
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        with self.assertRaises(ProductionWriteError):
            w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                             body="x", verdict=_Verdict())


class HoldingTest(unittest.TestCase):
    def test_a_quarantined_work_gets_a_verdict_but_no_production_artifacts(self):
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        r = w.write_holding(
            bucket=BUCKET_FANFIC_TTS, url=URL, title="T", body="x",
            verdict=_Verdict(approved=False, decision="quarantine", score=40))
        self.assertFalse(r.ready)
        self.assertIn(f"/{canonical.QUARANTINE}/", r.canonical_dir)
        # Ban an tim lai duoc...
        self.assertIn(f"{r.canonical_dir}/{ARTIFACT_MANIFEST}", a.objects)
        # ...nhung khong ton dung luong san xuat nao.
        self.assertNotIn(f"{r.canonical_dir}/{ARTIFACT_TEXT}", a.objects)
        self.assertNotIn(f"{r.canonical_dir}/{ARTIFACT_COVER}", a.objects)

    def test_rejected_and_quarantined_go_to_different_places(self):
        a = _R2()
        w = ProductionWriter(put_object=a.put, generate_artwork=_tranh,
                             archive_file=_luu_hong)
        q = w.write_holding(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                            body="x", verdict=_Verdict(decision="quarantine"))
        j = w.write_holding(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                            body="x", verdict=_Verdict(decision="reject"))
        self.assertNotEqual(q.canonical_dir, j.canonical_dir)


class AttachAudioTest(unittest.TestCase):
    def test_audio_is_added_without_losing_the_earlier_manifest(self):
        """TTS chay bat dong bo, nen manifest phai BO SUNG duoc — ghi de bang
        mot ban moi se lam mat ban an va sieu du lieu goc."""
        a = _R2()
        w = ProductionWriter(put_object=a.put, get_object=a.get,
                             generate_artwork=_tranh, archive_file=_luu_hong)
        r = w.write_approved(bucket=BUCKET_FANFIC_TTS, url=URL, title="T",
                             body="x", verdict=_Verdict(), novel_id="nov_1")
        w.attach_audio(bucket=BUCKET_FANFIC_TTS, url=URL,
                       object_key="audio/nov_1/ch1.mp3")
        man = json.loads(a.objects[f"{r.canonical_dir}/{ARTIFACT_MANIFEST}"])
        self.assertEqual(man["artifacts"][canonical.ARTIFACT_AUDIO_VI],
                         "audio/nov_1/ch1.mp3")
        # Nhung thu cu VAN con.
        self.assertEqual(man["serving"]["novel_id"], "nov_1")
        self.assertEqual(man["normalized"]["quality_score"], 88)
        self.assertIn(canonical.ARTIFACT_COVER, man["artifacts"])


class ArtworkTest(unittest.TestCase):
    def test_colours_are_deterministic(self):
        self.assertEqual(colours_for("w_abc"), colours_for("w_abc"))

    @unittest.skipUnless(shutil.which("ffmpeg"), "khong co ffmpeg tren may nay")
    def test_ffmpeg_really_produces_two_distinct_webp_images(self):
        bia, nen = generate("w_kiemthu")
        # `RIFF....WEBP` — chu ky that cua tep WebP, khong chi "khac rong".
        for du_lieu in (bia, nen):
            self.assertEqual(du_lieu[:4], b"RIFF")
            self.assertEqual(du_lieu[8:12], b"WEBP")
        self.assertNotEqual(bia, nen)


if __name__ == "__main__":
    unittest.main()

