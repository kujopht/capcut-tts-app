"""
Rao chan chong tro nham tai nguyen o phuong an staging goi Free.

O goi Free, worker TTS chay tren MAY LAP TRINH VIEN — cung cai may co
`server/.env` tro vao tai nguyen dev. Quen `FAS_ENV_FILE` mot lan la worker lang
le xu ly job cua dev bang credential dev, va khong co gi bao loi.
"""

from __future__ import annotations

import os
import unittest
from dataclasses import replace

from server.config import ConfigError, Settings, AppwriteSettings, R2Settings


def cau_hinh(**thay) -> Settings:
    """Mot cau hinh cloud day du, roi thay cai can thu."""
    goc = Settings(
        environment="staging",
        data_backend="appwrite",
        storage_backend="r2",
        cors_origins=["https://vi-du.test"],
        appwrite=AppwriteSettings(endpoint="https://vi-du.test/v1",
                                  project_id="p", api_key="k", database_id="d"),
        r2=R2Settings(account_id="a", access_key_id="i",
                      secret_access_key="s", bucket="b"),
        inline_worker=False,
    )
    return replace(goc, **thay)


class TestARealEnvironmentRefusesTheInlineWorker(unittest.TestCase):
    """
    O staging/production, web tu chay job la sai hinh dang.

    Nguy hiem cu the o goi Free: Render NGU web service sau 15 phut khong co
    traffic. Neu job TTS chay trong tien trinh web thi no bi ngu giua chung —
    dung cai ma viec tach worker nham loai bo.
    """

    def test_staging_with_inline_worker_stops_at_startup(self):
        with self.assertRaises(ConfigError) as ngu_canh:
            cau_hinh(environment="staging", inline_worker=True).validate()
        loi = str(ngu_canh.exception)
        self.assertIn("FAS_INLINE_WORKER", loi)
        self.assertIn("server.worker", loi, "phai chi ra cach lam dung")

    def test_production_with_inline_worker_stops_at_startup(self):
        with self.assertRaises(ConfigError):
            cau_hinh(environment="production", inline_worker=True).validate()

    def test_staging_without_inline_worker_is_fine(self):
        cau_hinh(environment="staging", inline_worker=False).validate()

    def test_development_may_keep_the_inline_worker(self):
        """Che do cu cua may lap trinh vien khong duoc bi pha."""
        cau_hinh(environment="development", inline_worker=True,
                 cors_origins=["http://localhost:3000"]).validate()

    def test_the_emergency_override_still_works(self):
        """
        `deploy/RUNBOOK.md` muc 7c cho phep quay ve inline de chua chay.

        Rao chan khong duoc bit duong thoat hiem da ghi trong tai lieu — chi bat
        no phai TUONG MINH.
        """
        cau_hinh(environment="staging", inline_worker=True,
                 allow_inline_worker_in_real_env=True).validate()

    def test_the_override_is_off_by_default(self):
        self.assertFalse(Settings().allow_inline_worker_in_real_env)


class TestTheWorkerRefusesTheWrongEnvironment(unittest.TestCase):
    def test_a_mismatch_exits_with_code_2(self):
        from server import worker

        self.assertEqual(worker.chay("staging"), 2,
                         "cau hinh dang la development, phai bi tu choi")

    def test_the_check_is_case_insensitive(self):
        from server import worker

        # Cau hinh that o may nay la `development`; yeu cau `DEVELOPMENT` thi
        # KHONG duoc coi la lech. Kiem gian tiep: yeu cau `STAGING` van lech.
        self.assertEqual(worker.chay("STAGING"), 2)

    def test_no_requirement_means_no_check(self):
        """
        Khong truyen `--require-env` thi khong kiem — giu duoc cach dung cu.

        Khong goi `chay(None)` that vi no vao vong lap vo han; doc ma nguon.
        """
        import inspect

        from server import worker

        nguon = inspect.getsource(worker.chay)
        self.assertIn("if doi_moi_truong and", nguon,
                      "chi kiem khi nguoi dung yeu cau")

    def test_the_guard_runs_before_the_sweep_loop(self):
        import inspect

        from server import worker

        nguon = inspect.getsource(worker.chay)
        vi_tri_chan = nguon.find("dung_vi_sai_moi_truong")
        vi_tri_quet = nguon.find("recover_stale_jobs(")
        self.assertGreater(vi_tri_chan, 0)
        self.assertLess(vi_tri_chan, vi_tri_quet,
                        "phai chan TRUOC khi cham vao kho du lieu")

    def test_the_guard_runs_before_enabling_job_execution(self):
        import inspect

        from server import worker

        nguon = inspect.getsource(worker.chay)
        self.assertLess(nguon.find("dung_vi_sai_moi_truong"),
                        nguon.find("enable_job_execution()"),
                        "sai moi truong thi khong duoc bat quyen chay job")

    def test_the_cli_exposes_require_env(self):
        from server import worker

        tham_so = worker._doc_tham_so(["--require-env", "staging"])
        self.assertEqual(tham_so.require_env, "staging")
        self.assertFalse(tham_so.check)

    def test_the_cli_still_supports_check(self):
        from server import worker

        tham_so = worker._doc_tham_so(["--check"])
        self.assertTrue(tham_so.check)
        self.assertIsNone(tham_so.require_env)


class TestWorkerLoggingSurvivesAWindowsConsole(unittest.TestCase):
    """
    LOI DA GAP: worker CHET khi log tieng Viet tren console cp1252.

    `UnicodeEncodeError: 'charmap' codec can't encode character '\\u1edb'` —
    chinh thong bao "FAS_ENV không khớp" lam tien trinh sap truoc khi kip in ly
    do. Moi dong log co dau deu la mot qua min.
    """

    def test_the_module_forces_utf8_on_stdout(self):
        import inspect

        from server import worker

        nguon = inspect.getsource(worker)
        self.assertIn("reconfigure(encoding=\"utf-8\"", nguon)
        self.assertIn("errors=\"replace\"", nguon,
                      "mot ky tu la khong duoc quan trong hon viec worker song")

    def test_it_is_applied_at_import_time(self):
        import inspect

        from server import worker

        nguon = inspect.getsource(worker)
        self.assertIn("\n_ep_utf8()\n", nguon,
                      "phai goi ngay khi import, truoc moi lan ghi log")

    def test_vietnamese_text_can_be_encoded_after_the_fix(self):
        """Dong log that su lam sap worker truoc day."""
        cau = "FAS_ENV không khớp. Nhiều khả năng đang nạp nhầm file cấu hình"
        self.assertTrue(cau.encode("utf-8"))
        with self.assertRaises(UnicodeEncodeError):
            cau.encode("cp1252")


class TestTheFreeBlueprintIsCoherent(unittest.TestCase):
    def setUp(self) -> None:
        import pathlib

        import yaml

        goc = pathlib.Path(__file__).resolve().parents[2]
        self.duong = goc / "deploy" / "render.free.yaml"
        self.d = yaml.safe_load(self.duong.read_text(encoding="utf-8"))
        self.services = self.d["services"]

    def test_every_service_is_on_the_free_plan(self):
        for s in self.services:
            self.assertEqual(s.get("plan"), "free",
                             f"{s['name']} khong o goi free")

    def test_there_is_no_background_worker(self):
        """Goi Free khong co worker — co worker o day la cau hinh khong chay duoc."""
        loai = [s["type"] for s in self.services]
        self.assertNotIn("worker", loai)
        self.assertEqual(len(self.services), 2, "chi frontend va backend")

    def test_the_backend_must_not_run_jobs_inline(self):
        api = [s for s in self.services if s.get("runtime") == "python"][0]
        co = {e["key"]: e.get("value") for e in api["envVars"] if "value" in e}
        self.assertEqual(co.get("FAS_INLINE_WORKER"), "false")
        self.assertEqual(co.get("FAS_ENV"), "staging")

    def test_no_secret_has_a_value_in_the_repo(self):
        for s in self.services:
            for e in s.get("envVars", []):
                if any(k in e["key"] for k in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                    self.assertNotIn("value", e,
                                     f"{s['name']}.{e['key']} co gia tri viet san")
                    self.assertIs(e.get("sync"), False)

    def test_the_paid_blueprint_is_untouched(self):
        """Nguoi dung yeu cau giu nguyen `deploy/render.yaml`."""
        import pathlib

        import yaml

        goc = pathlib.Path(__file__).resolve().parents[2]
        d = yaml.safe_load((goc / "deploy" / "render.yaml").read_text(encoding="utf-8"))
        loai = [s["type"] for s in d["services"]]
        self.assertIn("worker", loai, "ban tra phi phai con Background Worker")
        self.assertEqual(len(d["services"]), 3)


if __name__ == "__main__":
    unittest.main()
