"""
Test viec nap `server/.env`.

Vi sao can bo test nay: tai lieu bao nguoi van hanh dat cau hinh cloud vao
`server/.env`, nhung TRUOC DAY khong co doan code nao nap file do. Backend chi
doc `os.environ`, nen file la file tro: dien dung van chay o che do mock. Co
che fail-fast khong sai - no chi khong bao gio duoc kich hoat.

TOAN BO test o day dung gia tri GIA trong thu muc tam. Khong doc, khong ghi va
khong can secret that; khong bao gio cham toi `server/.env` cua may that.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from server.config import (
    DEFAULT_ENV_FILE,
    SERVER_ROOT,
    ConfigError,
    env_file_path,
    load_settings,
    reset_settings,
)

REPO_ROOT = SERVER_ROOT.parent

#: Bien duoc dung trong cac phep thu duoi day. Gia tri deu la chuoi GIA.
_TOUCHED = (
    "FAS_ENV_FILE", "DATA_BACKEND", "STORAGE_BACKEND", "FAS_ENV",
    "APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_API_KEY",
    "APPWRITE_DATABASE_ID",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
    "TRANSLATION_BASE_URL", "TRANSLATION_API_KEY", "TRANSLATION_MODEL",
)


class EnvFileTestCase(unittest.TestCase):
    """Nen chung: cach ly hoan toan khoi moi truong that."""

    def setUp(self) -> None:
        self._saved = {name: os.environ.get(name) for name in _TOUCHED}
        for name in _TOUCHED:
            os.environ.pop(name, None)
        self._dir = tempfile.mkdtemp()
        reset_settings()

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_settings()

    def _write_env(self, text: str, name: str = ".env") -> Path:
        path = Path(self._dir) / name
        path.write_text(text, encoding="utf-8")
        os.environ["FAS_ENV_FILE"] = str(path)
        return path


class TestEnvFileIsRead(EnvFileTestCase):
    def test_values_from_env_file_reach_settings(self):
        self._write_env("DATA_BACKEND=mock\nSTORAGE_BACKEND=local\nFAS_ENV=production\n")
        settings = load_settings()
        self.assertEqual(settings.environment, "production")
        self.assertTrue(settings.env_file_loaded)

    def test_default_path_is_resolved_from_module_not_cwd(self):
        """Duong dan mac dinh phai bam theo vi tri module, khong theo cwd."""
        os.environ.pop("FAS_ENV_FILE", None)
        self.assertEqual(env_file_path(), DEFAULT_ENV_FILE)
        self.assertEqual(DEFAULT_ENV_FILE, SERVER_ROOT / ".env")
        self.assertTrue(DEFAULT_ENV_FILE.is_absolute())

    def test_env_file_path_can_be_disabled(self):
        os.environ["FAS_ENV_FILE"] = ""
        self.assertIsNone(env_file_path())
        self.assertFalse(load_settings().env_file_loaded)


class TestTranslationSettings(EnvFileTestCase):
    """
    `TRANSLATION_BASE_URL`/`API_KEY`/`MODEL` (V5, DocuTranslateProvider) —
    rao chan hoi quy cho cai bay da tim thay that: `Settings` truoc day
    khong khai bao ba truong nay nen `load_settings()` khong bao gio doc
    duoc chung du `.env` co dien gia tri — mot API key that se im lang
    khong co tac dung gi. Xem `translation_providers.py::build_provider`.
    """

    def test_ca_ba_bien_den_duoc_settings(self):
        self._write_env(
            "TRANSLATION_BASE_URL=https://api.vidu.test/v1\n"
            "TRANSLATION_API_KEY=khoa-thu\n"
            "TRANSLATION_MODEL=vidu-model\n"
        )
        settings = load_settings()
        self.assertEqual(settings.translation_base_url, "https://api.vidu.test/v1")
        self.assertEqual(settings.translation_api_key, "khoa-thu")
        self.assertEqual(settings.translation_model, "vidu-model")

    def test_khong_dat_thi_rong_khong_loi(self):
        settings = load_settings()
        self.assertEqual(settings.translation_base_url, "")
        self.assertEqual(settings.translation_api_key, "")
        self.assertEqual(settings.translation_model, "")


class TestPrecedence(EnvFileTestCase):
    """Bien da co trong process environment LUON thang file."""

    def test_process_environment_overrides_env_file(self):
        self._write_env("FAS_ENV=production\nDATA_BACKEND=appwrite\n")
        os.environ["FAS_ENV"] = "development"
        os.environ["DATA_BACKEND"] = "mock"

        settings = load_settings()
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.data_backend, "mock")

    def test_env_file_fills_only_what_is_missing(self):
        self._write_env("FAS_ENV=production\nSTORAGE_BACKEND=local\n")
        os.environ["FAS_ENV"] = "development"

        settings = load_settings()
        self.assertEqual(settings.environment, "development")   # tu shell
        self.assertEqual(settings.storage_backend, "local")     # tu file


class TestMissingFileIsHarmless(EnvFileTestCase):
    def test_absent_env_file_keeps_mock_mode_working(self):
        os.environ["FAS_ENV_FILE"] = str(Path(self._dir) / "khong-ton-tai.env")
        settings = load_settings()
        settings.validate()          # khong duoc nem loi

        self.assertFalse(settings.env_file_loaded)
        self.assertEqual(settings.data_backend, "mock")
        self.assertEqual(settings.storage_backend, "local")

    def test_health_reports_whether_the_env_file_was_loaded(self):
        os.environ["FAS_ENV_FILE"] = str(Path(self._dir) / "khong-ton-tai.env")
        self.assertIs(load_settings().describe()["env_file_loaded"], False)

        self._write_env("FAS_ENV=development\n")
        self.assertIs(load_settings().describe()["env_file_loaded"], True)


class TestFailFastStillApplies(EnvFileTestCase):
    """Nap `.env` KHONG duoc lam mem nguyen tac fail-fast."""

    def test_appwrite_mode_from_env_file_without_credentials_fails_fast(self):
        self._write_env("DATA_BACKEND=appwrite\n")
        with self.assertRaises(ConfigError) as ctx:
            load_settings().validate()
        self.assertIn("APPWRITE_ENDPOINT", str(ctx.exception))

    def test_r2_mode_from_env_file_without_credentials_fails_fast(self):
        self._write_env("STORAGE_BACKEND=r2\n")
        with self.assertRaises(ConfigError) as ctx:
            load_settings().validate()
        self.assertIn("R2_ACCOUNT_ID", str(ctx.exception))

    def test_partial_appwrite_config_still_fails_fast(self):
        """Dien thieu mot bien cung phai dung, khong duoc lui ve mock."""
        self._write_env(
            "DATA_BACKEND=appwrite\n"
            "APPWRITE_ENDPOINT=https://khong-co-that.example/v1\n"
            "APPWRITE_PROJECT_ID=gia\n"
            "APPWRITE_DATABASE_ID=gia\n"          # thieu APPWRITE_API_KEY
        )
        settings = load_settings()
        self.assertEqual(settings.data_backend, "appwrite")
        self.assertFalse(settings.appwrite.configured)
        with self.assertRaises(ConfigError):
            settings.validate()

    def test_invalid_backend_name_from_env_file_fails_fast(self):
        self._write_env("STORAGE_BACKEND=s3\n")
        with self.assertRaises(ConfigError):
            load_settings().validate()


class TestWorkingDirectoryIndependence(unittest.TestCase):
    """
    File `.env` phai duoc nap du tien trinh chay tu dau.

    Chay tien trinh Python THAT o hai thu muc lam viec khac nhau, tro
    `FAS_ENV_FILE` vao cung mot file tam.
    """

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        self.env_file = Path(self._dir) / "thu.env"
        # Gia tri GIA, khong phai secret
        self.env_file.write_text("FAS_ENV=production\n", encoding="utf-8")

    def _run_from(self, cwd: Path) -> str:
        env = dict(os.environ)
        env["FAS_ENV_FILE"] = str(self.env_file)
        env["PYTHONPATH"] = str(REPO_ROOT)
        for name in ("FAS_ENV", "DATA_BACKEND", "STORAGE_BACKEND"):
            env.pop(name, None)
        result = subprocess.run(
            [sys.executable, "-c",
             "from server.config import load_settings;"
             "s = load_settings();"
             "print(s.environment, s.env_file_loaded)"],
            cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_loaded_when_run_from_repository_root(self):
        self.assertEqual(self._run_from(REPO_ROOT), "production True")

    def test_loaded_when_run_from_another_directory(self):
        self.assertEqual(self._run_from(Path(self._dir)), "production True")

    def test_same_result_from_both_directories(self):
        self.assertEqual(self._run_from(REPO_ROOT), self._run_from(Path(self._dir)))


class TestFixturesStayOutsideTheRepository(EnvFileTestCase):
    """File thu phai nam trong thu muc tam, khong bao gio la `server/.env` that."""

    def test_fixture_never_points_at_the_repository_env_file(self):
        path = self._write_env("FAS_ENV=development\n")
        self.assertNotEqual(path, DEFAULT_ENV_FILE)
        self.assertEqual(env_file_path(), path)
        self.assertNotIn(
            str(REPO_ROOT), str(path), "file thử phải nằm ngoài repository"
        )

    def test_repository_env_file_is_not_read_during_tests(self):
        """`FAS_ENV_FILE` cua fixture tach hoan toan khoi file that tren may."""
        self._write_env("FAS_ENV=production\n")
        self.assertTrue(load_settings().env_file_loaded)
        self.assertNotEqual(env_file_path(), DEFAULT_ENV_FILE)


class TestSuiteIsHermetic(unittest.TestCase):
    """
    Bo test khong bao gio duoc chay vao Appwrite/R2 that.

    `server/main.py` chon adapter ngay luc import, nen mot `server/.env` tro
    toi cloud that se keo ca bo test len cloud - sai ket qua va co the ghi de
    du lieu that. `server/tests/__init__.py` ep mock/local truoc khi nap module.
    """

    def test_backend_under_test_is_always_mock_and_local(self):
        from server import main as server_main

        self.assertEqual(server_main.settings.data_backend, "mock")
        self.assertEqual(server_main.settings.storage_backend, "local")

    def test_no_cloud_credentials_are_visible_to_the_test_process(self):
        for name in ("APPWRITE_API_KEY", "APPWRITE_ENDPOINT",
                     "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
            self.assertIsNone(
                os.environ.get(name),
                f"{name} không được lọt vào tiến trình test",
            )

    def test_env_file_loading_is_disabled_for_the_suite(self):
        self.assertEqual(os.environ.get("FAS_ENV_FILE"), "")


class TestNoRealSecretsInTests(unittest.TestCase):
    """Bo test nay khong duoc dung hay ghi secret that."""

    def test_env_file_is_gitignored(self):
        ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            any(line.strip() in (".env", ".env.*", "*.env")
                for line in ignore.splitlines()),
            "server/.env phải bị .gitignore chặn",
        )

    def test_dotenv_is_declared_as_a_runtime_dependency(self):
        text = (REPO_ROOT / "server" / "requirements.txt").read_text(encoding="utf-8")
        declared = [
            line.split("#")[0].strip() for line in text.splitlines()
            if line.split("#")[0].strip().lower().startswith("python-dotenv")
        ]
        self.assertTrue(declared, "python-dotenv phải nằm trong server/requirements.txt")
        self.assertRegex(declared[0], r"[<>=~!]", "phải có ràng buộc phiên bản")




class SchemaKeyTest(unittest.TestCase):
    """
    `APPWRITE_SCHEMA_API_KEY` — khoa quan schema RIENG, khong bao gio lo ra.

    Khoa runtime tren Render chi co quyen documents; khoa schema chi song o
    may van hanh. Hai bai duoi day ghim hai dieu: khoa duoc NAP dung, va khong
    duong mo ta/health nao mang no ra ngoai.
    """

    def test_nap_va_khong_lo_qua_describe(self):
        import os
        from server.config import load_settings

        cu = os.environ.get("APPWRITE_SCHEMA_API_KEY")
        os.environ["APPWRITE_SCHEMA_API_KEY"] = "khoa-thu-khong-in-ra"
        try:
            s = load_settings()
            self.assertEqual(s.appwrite.schema_api_key, "khoa-thu-khong-in-ra")
            chu = repr(s.describe())
            self.assertNotIn("khoa-thu-khong-in-ra", chu)
            self.assertNotIn("schema_api_key", chu)
        finally:
            if cu is None:
                os.environ.pop("APPWRITE_SCHEMA_API_KEY", None)
            else:
                os.environ["APPWRITE_SCHEMA_API_KEY"] = cu

    def test_translation_api_key_khong_lo_qua_describe(self):
        """
        Cung nguyen tac voi khoa schema o tren, ap cho `TRANSLATION_API_KEY`
        (V5) — `describe()` CHI duoc phep noi CO cau hinh hay khong
        (`translation_provider_configured`, mot boolean), khong bao gio in
        chinh gia tri khoa.
        """
        import os
        from server.config import load_settings

        cu = os.environ.get("TRANSLATION_API_KEY")
        os.environ["TRANSLATION_API_KEY"] = "khoa-dich-khong-in-ra"
        try:
            s = load_settings()
            self.assertEqual(s.translation_api_key, "khoa-dich-khong-in-ra")
            chu = repr(s.describe())
            self.assertNotIn("khoa-dich-khong-in-ra", chu)
            self.assertNotIn("translation_api_key", chu)
        finally:
            if cu is None:
                os.environ.pop("TRANSLATION_API_KEY", None)
            else:
                os.environ["TRANSLATION_API_KEY"] = cu

    def test_script_schema_uu_tien_khoa_rieng(self):
        """Khoa schema khi co, lui ve khoa runtime khi vang — dung phep chon
        ma `scripts/setup_appwrite.py::Setup.__init__` dung."""
        from server.config import AppwriteSettings

        co = AppwriteSettings(endpoint="e", project_id="p", api_key="runtime",
                              database_id="d", schema_api_key="schema")
        khong = AppwriteSettings(endpoint="e", project_id="p",
                                 api_key="runtime", database_id="d")
        self.assertEqual(co.schema_api_key or co.api_key, "schema")
        self.assertEqual(khong.schema_api_key or khong.api_key, "runtime")


if __name__ == "__main__":
    unittest.main(verbosity=2)
