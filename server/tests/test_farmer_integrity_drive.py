"""Toan ven trinh thong dich + luu tru Drive.

Hai bai hoc that duoc dong cung o day:

1. **Phai giai symlink.** Mot bao cao truoc do (cua chinh du an nay) ket luan
   `.venv/bin/python` la `root:root 777` world-writable va goi do la duong leo
   thang quyen. SAI: bon muc do la symlink, va Linux BO QUA bit quyen cua
   symlink. Trinh thong dich that la `/usr/bin/python3.12` mode 755.
   Te hon: "sua" no bang `chmod o-w .venv/bin/python` se DI THEO symlink va
   doi quyen trinh thong dich CUA CA MAY.

2. **Su co Drive khong duoc cham vao R2.** Drive la ban sao ben vung; R2 la
   duong phuc vu. Mot loi Drive chi duoc phep tao `ARCHIVE_PENDING`.
"""
from __future__ import annotations

import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from server.farmer import drive_archive as da
from server.farmer.integrity import (
    ENV_SKIP, InterpreterNotSecure, assert_interpreter_secure, check_interpreter,
)

POSIX = os.name == "posix"


class SymlinkFalsePositiveTest(unittest.TestCase):
    """Bai quan trong nhat cua tep nay."""

    @unittest.skipUnless(POSIX, "bit quyen POSIX")
    def test_a_777_symlink_to_a_safe_binary_is_not_a_finding(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            that = base / "python-real"
            that.write_text("#!/bin/sh\n")
            that.chmod(0o755)
            lien_ket = base / "python"
            lien_ket.symlink_to(that)
            base.chmod(0o755)

            bao_cao = check_interpreter(str(lien_ket))

        self.assertTrue(
            bao_cao.ok,
            f"symlink 777 tro toi binary 755 KHONG phai loi; van de: "
            f"{bao_cao.problems}")
        self.assertEqual(bao_cao.real_interpreter, str(that))

    @unittest.skipUnless(POSIX, "bit quyen POSIX")
    def test_a_world_writable_real_interpreter_IS_a_finding(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            base.chmod(0o755)
            that = base / "python-real"
            that.write_text("#!/bin/sh\n")
            that.chmod(0o777)          # ai cung ghi duoc — day moi la that
            lien_ket = base / "python"
            lien_ket.symlink_to(that)

            bao_cao = check_interpreter(str(lien_ket))

        self.assertFalse(bao_cao.ok)
        self.assertTrue(any("other" in p for p in bao_cao.problems))

    @unittest.skipUnless(POSIX, "bit quyen POSIX")
    def test_a_group_writable_real_interpreter_IS_a_finding(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            base.chmod(0o755)
            that = base / "python-real"
            that.write_text("#!/bin/sh\n")
            that.chmod(0o775)
            bao_cao = check_interpreter(str(that))
        self.assertFalse(bao_cao.ok)
        self.assertTrue(any("group" in p for p in bao_cao.problems))

    @unittest.skipUnless(POSIX, "bit quyen POSIX")
    def test_a_writable_parent_directory_IS_a_finding(self):
        """Ghi duoc thu muc = thay the duoc tep ben trong no."""
        with TemporaryDirectory() as d:
            base = Path(d)
            thu_muc = base / "bin"
            thu_muc.mkdir()
            that = thu_muc / "python"
            that.write_text("#!/bin/sh\n")
            that.chmod(0o755)
            thu_muc.chmod(0o777)
            try:
                bao_cao = check_interpreter(str(that))
            finally:
                thu_muc.chmod(0o755)
        self.assertFalse(bao_cao.ok)

    @unittest.skipUnless(POSIX, "bit quyen POSIX")
    def test_a_sticky_world_writable_dir_is_accepted(self):
        """`/tmp` la 1777. Sticky nghia la chi chu so huu moi xoa/doi ten
        duoc — no KHONG cho thay the tep cua nguoi khac. Bo qua chi tiet nay
        se bao dong gia tren bat ky he thong nao dat ma trong /tmp."""
        with TemporaryDirectory() as d:
            base = Path(d)
            thu_muc = base / "sticky"
            thu_muc.mkdir()
            that = thu_muc / "python"
            that.write_text("#!/bin/sh\n")
            that.chmod(0o755)
            thu_muc.chmod(0o1777)
            try:
                bao_cao = check_interpreter(str(that))
                van_de_thu_muc = [p for p in bao_cao.problems if "sticky" not in p
                                  and str(thu_muc) in p]
            finally:
                thu_muc.chmod(0o755)
        self.assertEqual(van_de_thu_muc, [])


class IntegrityGateTest(unittest.TestCase):
    def test_assert_raises_when_not_secure(self):
        bao_cao = mock.Mock(ok=False, problems=["gia dinh"])
        with mock.patch("server.farmer.integrity.check_interpreter",
                        return_value=bao_cao):
            with self.assertRaises(InterpreterNotSecure):
                assert_interpreter_secure()

    def test_skip_flag_reports_unchecked_not_a_false_pass(self):
        with mock.patch.dict("os.environ", {ENV_SKIP: "1"}):
            bao_cao = check_interpreter()
        self.assertTrue(bao_cao.ok)
        self.assertFalse(bao_cao.checked,
                         "bo qua phai bao 'khong kiem', khong phai tick gia")

    def test_windows_reports_unchecked_rather_than_a_fake_pass(self):
        with mock.patch("server.farmer.integrity.os.name", "nt"):
            bao_cao = check_interpreter()
        self.assertTrue(bao_cao.ok)
        self.assertFalse(bao_cao.checked)


class DriveNeverHarmsR2Test(unittest.TestCase):
    """Bat bien trung tam cua lop luu tru."""

    def test_archive_only_ever_copies_never_syncs_or_deletes(self):
        """`sync`/`move`/`delete` o day se bien mot loi cuc bo thanh mat du
        lieu tren ban luu tru. Chi `copy` duoc phep."""
        with TemporaryDirectory() as d:
            tep = Path(d) / "a.mp3"
            tep.write_bytes(b"x")
            proc = mock.Mock(returncode=0, stdout="[]", stderr="")
            with mock.patch.object(da.shutil, "which", return_value="rclone"), \
                 mock.patch.object(da.subprocess, "run", return_value=proc) as run:
                da.archive_file(tep, work_key="fw_1")

            argv = run.call_args_list[0][0][0]
        self.assertIn("copy", argv)
        for cam in ("sync", "move", "delete", "purge", "rmdirs"):
            self.assertNotIn(cam, argv)

    def test_missing_rclone_yields_pending_not_an_exception(self):
        with TemporaryDirectory() as d:
            tep = Path(d) / "a.mp3"
            tep.write_bytes(b"x")
            with mock.patch.object(da.shutil, "which", return_value=None):
                ket_qua = da.archive_file(tep, work_key="fw_1")
        self.assertEqual(ket_qua.status, da.ARCHIVE_PENDING)

    def test_rclone_failure_yields_pending_not_an_exception(self):
        with TemporaryDirectory() as d:
            tep = Path(d) / "a.mp3"
            tep.write_bytes(b"x")
            proc = mock.Mock(returncode=1, stdout="", stderr="invalid_grant")
            with mock.patch.object(da.shutil, "which", return_value="rclone"), \
                 mock.patch.object(da.subprocess, "run", return_value=proc):
                ket_qua = da.archive_file(tep, work_key="fw_1")
        self.assertEqual(ket_qua.status, da.ARCHIVE_PENDING)
        self.assertIn("invalid_grant", ket_qua.detail)

    def test_a_drive_outage_touches_no_r2_code_path(self):
        """Kiem tren CAY CU PHAP: tang luu tru khong duoc phep nhac toi R2 hay
        xoa. Mot bai test hanh vi khong bat duoc mot dong `delete` chi chay o
        nhanh hiem."""
        import ast
        import server.farmer.drive_archive as module

        cay = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        goi = {n.func.attr for n in ast.walk(cay)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertNotIn("delete", goi)
        self.assertNotIn("put", goi)
        nguon = Path(module.__file__).read_text(encoding="utf-8")
        for cam in ("R2StorageAdapter", "upload_to_r2", "storage_backend"):
            self.assertNotIn(cam, nguon,
                             f"tang luu tru Drive khong duoc cham toi R2: {cam}")


class CanonicalRemoteTest(unittest.TestCase):
    def test_farmer_uses_the_same_canonical_remote_as_existing_paths(self):
        """Mot ten remote thu hai se lang le tach kho luu tru lam doi."""
        from server.scraper.raw_archive import DRIVE_ARCHIVE_REMOTE

        self.assertTrue(DRIVE_ARCHIVE_REMOTE.startswith(da.CANONICAL_REMOTE + ":"))
        self.assertTrue(da.farmer_remote_path("x").startswith(
            da.CANONICAL_REMOTE + ":" + da.CANONICAL_ROOT))

    def test_farmer_archives_under_production_never_the_legacy_tree(self):
        """`FanficWorld/archive/` la LEGACY va phai duoc de yen."""
        duong = da.farmer_remote_path("fw_abc", "a.mp3")
        self.assertIn("FanficWorld/production/", duong)
        self.assertNotIn("FanficWorld/archive/", duong)

    def test_work_path_mirrors_the_canonical_r2_layout(self):
        """Duong tren Drive va duong tren R2 khong duoc lech nhau."""
        from server.farmer import canonical as c

        url = "https://e.com/a"
        drive = da.work_remote_path(c.BUCKET_FANFIC_TTS, url, c.ARTIFACT_AUDIO_VI)
        self.assertIn(c.canonical_dir(c.BUCKET_FANFIC_TTS, url), drive)
        self.assertTrue(drive.endswith("/audio/vi.mp3"))
        self.assertNotIn("FanficWorld/archive/", drive)

    def test_probe_reports_disabled_without_calling_rclone(self):
        with mock.patch.dict("os.environ", {da.ENV_ENABLED: "0"}), \
             mock.patch.object(da.shutil, "which") as which:
            ket_qua = da.probe()
        which.assert_not_called()
        self.assertEqual(ket_qua["status"], da.ARCHIVE_DISABLED)

    def test_probe_names_an_expired_token_plainly(self):
        proc = mock.Mock(returncode=1, stdout="",
                         stderr="couldn't fetch token: invalid_grant")
        with mock.patch.object(da.shutil, "which", return_value="rclone"), \
             mock.patch.object(da.subprocess, "run", return_value=proc):
            ket_qua = da.probe()
        self.assertEqual(ket_qua["status"], da.ARCHIVE_UNAVAILABLE)
        self.assertIn("reconnect", ket_qua["detail"])


if __name__ == "__main__":
    unittest.main()
