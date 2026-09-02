"""archive_final_render() — HOT (R2) + COLD (Google Drive) archival of one
already-finished rendered video, plus checksum/size persisted onto the
Novel via the existing narrow media-processing PATCH path.

Mission "Persist the one real QA_PASS rendered video that was produced
locally but never persisted anywhere durable" (2026-09-02, backfill target
novel_id=nov_41c9c967f40845a0). These tests mock `upload_to_r2`, `goi`, and
`rclone_copy`/`rclone_verify` — same `mock.patch.object(cmp, ...)`
convention as `test_chinese_media_pipeline_ship_draft.py` in this same
neighborhood. No real network/rclone/R2 call happens in these tests.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chinese_media_pipeline as cmp  # noqa: E402


def _fake_rclone_copy_ok(calls):
    def fake(local_dir, remote_path, **kwargs):
        calls.append(("copy", local_dir, remote_path))
        return {"exit_code": 0, "stdout": "", "stderr_tail": ""}
    return fake


def _fake_rclone_verify_ok(calls, *, file_name, drive_id):
    def fake(local_dir, remote_path, **kwargs):
        calls.append(("verify", local_dir, remote_path))
        lsjson = json.dumps([
            {"Name": file_name, "IsDir": False, "ID": drive_id, "Size": 12},
        ])
        return {
            "check_exit_code": 0, "check_stdout": "", "check_stderr_tail": "",
            "lsjson_exit_code": 0, "lsjson": lsjson,
            "size_exit_code": 0, "size": "",
        }
    return fake


def _fake_goi_patch_ok(calls):
    def fake(api, method, path, payload=None, token=None, timeout=60):
        calls.append((method, path, payload))
        assert method == "PATCH", f"khong bao gio goi {method}, chi PATCH"
        assert path.endswith("/media-processing")
        novel_id = path.split("/")[-2]
        return 200, {"novel": {"novel_id": novel_id, **(payload or {})}}
    return fake


class ArchiveFinalRenderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.render_path = Path(self._tmp.name) / "wikitongues_henan_final.mkv"
        self.render_bytes = b"fake mkv bytes for testing" * 100
        self.render_path.write_bytes(self.render_bytes)
        self.expected_sha256 = hashlib.sha256(self.render_bytes).hexdigest()

    def _run(self, *, novel_id="nov_41c9c967f40845a0",
             slug="wikitongues-henan-chinese", drive_id="1DriveFileIdExample"):
        upload_calls = []
        rclone_calls = []
        goi_calls = []

        def fake_upload(key, data, content_type):
            upload_calls.append((key, data, content_type))

        with mock.patch.object(cmp, "upload_to_r2", side_effect=fake_upload), \
             mock.patch.object(cmp, "rclone_copy",
                               side_effect=_fake_rclone_copy_ok(rclone_calls)), \
             mock.patch.object(cmp, "rclone_verify",
                               side_effect=_fake_rclone_verify_ok(
                                   rclone_calls, file_name=self.render_path.name,
                                   drive_id=drive_id)), \
             mock.patch.object(cmp, "goi", side_effect=_fake_goi_patch_ok(goi_calls)):
            result = cmp.archive_final_render(
                local_render_path=self.render_path, novel_id=novel_id,
                slug=slug, token="fake-token",
            )
        return result, upload_calls, rclone_calls, goi_calls

    # -- happy path -----------------------------------------------------

    def test_sha256_va_size_tinh_dung(self):
        result, *_ = self._run()
        self.assertEqual(result["sha256"], self.expected_sha256)
        self.assertEqual(result["size_bytes"], len(self.render_bytes))

    def test_r2_key_tat_dinh_theo_noi_dung_khong_ngau_nhien(self):
        result, upload_calls, *_ = self._run(slug="wikitongues-henan-chinese")
        expected_key = (
            f"rendered_media/svc_harvester/"
            f"wikitongues-henan-chinese-{self.expected_sha256[:16]}.mkv"
        )
        self.assertEqual(result["r2_key"], expected_key)
        self.assertEqual(len(upload_calls), 1)
        key, data, content_type = upload_calls[0]
        self.assertEqual(key, expected_key)
        self.assertEqual(data, self.render_bytes)
        self.assertEqual(content_type, "video/x-matroska")

    def test_drive_remote_path_tat_dinh_theo_noi_dung(self):
        result, _, rclone_calls, _ = self._run(slug="wikitongues-henan-chinese")
        expected_dir = (
            f"{cmp.DRIVE_FINAL_MEDIA_REMOTE}/"
            f"wikitongues-henan-chinese-{self.expected_sha256[:16]}"
        )
        self.assertEqual(result["drive_remote_dir"], expected_dir)
        copy_call = next(c for c in rclone_calls if c[0] == "copy")
        self.assertEqual(copy_call[1], str(self.render_path))
        self.assertEqual(copy_call[2], expected_dir)

    def test_drive_file_id_lay_tu_lsjson_khong_phai_duong_dan(self):
        result, *_ = self._run(drive_id="1RealDriveFileId")
        self.assertEqual(result["drive_file_id"], "1RealDriveFileId")
        self.assertNotEqual(result["drive_file_id"], result["drive_remote_dir"])

    def test_patch_chi_dung_dung_4_truong(self):
        result, _, _, goi_calls = self._run(novel_id="nov_41c9c967f40845a0")
        self.assertEqual(len(goi_calls), 1)
        method, path, payload = goi_calls[0]
        self.assertEqual(method, "PATCH")
        self.assertEqual(path, "/api/novels/nov_41c9c967f40845a0/media-processing")
        self.assertEqual(
            set(payload.keys()),
            {"rendered_media_key", "rendered_archive_file_id",
             "rendered_checksum", "rendered_size_bytes"},
        )
        self.assertNotIn("qa_state", payload)
        self.assertEqual(payload["rendered_media_key"], result["r2_key"])
        self.assertEqual(payload["rendered_archive_file_id"], result["drive_file_id"])
        self.assertEqual(payload["rendered_checksum"], self.expected_sha256)
        self.assertEqual(payload["rendered_size_bytes"], len(self.render_bytes))

    # -- slug validation (path traversal / injection guard) ---------------

    def test_slug_chua_dau_cham_gap_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self._run(slug="../../etc/passwd")

    def test_slug_chua_dau_gach_cheo_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self._run(slug="foo/bar")

    def test_slug_chua_khoang_trang_hoac_hoa_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self._run(slug="Foo Bar")

    def test_slug_rong_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self._run(slug="")

    def test_slug_hop_le_khong_bi_anh_huong(self):
        # Regression guard: slug hop le (dung format cac test khac dung)
        # phai KHONG bi anh huong boi validation moi them vao.
        result, *_ = self._run(slug="wikitongues-henan-chinese")
        self.assertIn("wikitongues-henan-chinese", result["r2_key"])

    # -- idempotency ------------------------------------------------------

    def test_goi_lai_cung_tep_ra_dung_r2_key_va_drive_path_moi_lan(self):
        result1, _, rclone_calls1, goi_calls1 = self._run()
        result2, _, rclone_calls2, goi_calls2 = self._run()

        self.assertEqual(result1["r2_key"], result2["r2_key"])
        self.assertEqual(result1["drive_remote_dir"], result2["drive_remote_dir"])
        self.assertEqual(result1["sha256"], result2["sha256"])

        copy1 = next(c for c in rclone_calls1 if c[0] == "copy")
        copy2 = next(c for c in rclone_calls2 if c[0] == "copy")
        self.assertEqual(copy1[2], copy2[2])  # cung dich, khong bao gio doi

        payload1 = goi_calls1[0][2]
        payload2 = goi_calls2[0][2]
        self.assertEqual(payload1, payload2)


class DiscoveredPlaceholderRegressionTest(unittest.TestCase):
    """Kich ban regression THAT cua mission nay: mot Novel placeholder
    (rendered_media_key="") duoc archive mot local render, RỒI archive
    CUNG mot tep do lan nua — lan hai phai cho ra DUNG cung gia tri, khong
    bao gio tao them mot doi tuong R2/Drive moi, va khong bao gio tao them
    mot ban ghi Novel thu hai (ham nay chi bao gio PATCH, khong bao gio
    POST)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.render_path = Path(self._tmp.name) / "wikitongues_henan_final.mkv"
        self.render_path.write_bytes(b"real-looking final render bytes" * 500)

    def test_discovered_placeholder_den_populated_qua_hai_lan_chay(self):
        # Mo phong Novel that trong Appwrite: bat dau la placeholder rong,
        # dung mau voi novel_id=nov_41c9c967f40845a0 that trong production.
        novel_state = {
            "novel_id": "nov_41c9c967f40845a0",
            "rendered_media_key": "", "rendered_archive_file_id": "",
            "rendered_checksum": "", "rendered_size_bytes": 0,
        }
        goi_calls = []
        rclone_calls = []

        def fake_goi(api, method, path, payload=None, token=None, timeout=60):
            goi_calls.append((method, path, payload))
            self.assertEqual(method, "PATCH",
                             "khong bao gio POST - day la ban ghi DA TON TAI")
            novel_state.update(payload or {})
            return 200, {"novel": dict(novel_state)}

        with mock.patch.object(cmp, "upload_to_r2"), \
             mock.patch.object(cmp, "rclone_copy",
                               side_effect=_fake_rclone_copy_ok(rclone_calls)), \
             mock.patch.object(cmp, "rclone_verify",
                               side_effect=_fake_rclone_verify_ok(
                                   rclone_calls, file_name=self.render_path.name,
                                   drive_id="1RealDriveFileId")), \
             mock.patch.object(cmp, "goi", side_effect=fake_goi):

            self.assertEqual(novel_state["rendered_media_key"], "")

            first = cmp.archive_final_render(
                local_render_path=self.render_path,
                novel_id="nov_41c9c967f40845a0",
                slug="wikitongues-henan-chinese", token="fake-token",
            )
            self.assertTrue(novel_state["rendered_media_key"])
            self.assertTrue(novel_state["rendered_archive_file_id"])
            self.assertTrue(novel_state["rendered_checksum"])
            self.assertGreater(novel_state["rendered_size_bytes"], 0)
            after_first = dict(novel_state)

            second = cmp.archive_final_render(
                local_render_path=self.render_path,
                novel_id="nov_41c9c967f40845a0",
                slug="wikitongues-henan-chinese", token="fake-token",
            )

        self.assertEqual(first["r2_key"], second["r2_key"])
        self.assertEqual(first["drive_remote_dir"], second["drive_remote_dir"])
        self.assertEqual(first["drive_file_id"], second["drive_file_id"])
        self.assertEqual(novel_state, after_first)  # khong doi sau lan hai
        self.assertEqual(len(goi_calls), 2)
        self.assertEqual(goi_calls[0][2], goi_calls[1][2])
        # Chi DUY NHAT mot novel_id xuat hien trong moi call - khong co ban
        # ghi thu hai nao duoc dung toi.
        novel_ids_touched = {c[1].split("/")[3] for c in goi_calls}
        self.assertEqual(novel_ids_touched, {"nov_41c9c967f40845a0"})


if __name__ == "__main__":
    unittest.main()
