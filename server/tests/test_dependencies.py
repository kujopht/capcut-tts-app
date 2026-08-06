"""
Xac minh dependency runtime cua backend.

Muc dich: bat dung tinh huong "code da viet nhung moi truong thieu goi". Truoc
day `boto3` khong duoc khai bao o bat ky file dependency nao duoc commit, nen
mot moi truong cai dung theo tai lieu van khong khoi tao duoc R2 adapter.

Toan bo test o day chay offline va KHONG can credential that.
"""

from __future__ import annotations

import importlib
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "server" / "requirements.txt"


def _declared_requirements() -> dict:
    """{ten goi (chu thuong): rang buoc phien ban} tu file dependency."""
    found = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)\s*(\[[^\]]*\])?\s*(.*)$", line)
        if match:
            found[match.group(1).lower()] = match.group(3).strip()
    return found


class TestRequirementsFile(unittest.TestCase):
    """File dependency phai ton tai va khai bao du goi runtime."""

    def test_requirements_file_is_committed(self):
        self.assertTrue(
            REQUIREMENTS.is_file(),
            "server/requirements.txt phải tồn tại và được commit",
        )

    def test_boto3_is_declared_with_a_version_constraint(self):
        declared = _declared_requirements()
        self.assertIn(
            "boto3", declared,
            "boto3 phải được khai báo trong server/requirements.txt, "
            "không phải cài tay bằng pip install",
        )
        self.assertTrue(
            declared["boto3"],
            "boto3 phải có ràng buộc phiên bản, không được để trống",
        )
        self.assertRegex(
            declared["boto3"], r"[<>=~!]",
            "ràng buộc phiên bản của boto3 phải dùng toán tử so sánh",
        )

    def test_core_runtime_packages_are_declared(self):
        declared = _declared_requirements()
        for package in ("fastapi", "uvicorn", "pydantic", "httpx", "requests"):
            self.assertIn(
                package, declared, f"{package} là dependency runtime, phải khai báo"
            )
            self.assertTrue(
                declared[package], f"{package} phải có ràng buộc phiên bản"
            )

    def test_gui_only_packages_are_not_pulled_into_the_backend(self):
        """Backend khong duoc keo theo phu thuoc cua desktop app."""
        declared = _declared_requirements()
        for package in ("pyside6", "gradio", "pyinstaller", "python-docx"):
            self.assertNotIn(
                package, declared,
                f"{package} chỉ dành cho desktop, không thuộc backend",
            )

    def test_requirements_file_contains_no_secret(self):
        text = REQUIREMENTS.read_text(encoding="utf-8")
        for marker in ("APPWRITE_API_KEY", "R2_SECRET_ACCESS_KEY", "R2_ACCESS_KEY_ID"):
            self.assertNotIn(marker, text)


class TestImportVerification(unittest.TestCase):
    """Moi truong cai tu file dependency phai khoi tao duoc module R2."""

    def test_boto3_is_importable(self):
        boto3 = importlib.import_module("boto3")
        self.assertTrue(hasattr(boto3, "client"))

    def test_botocore_config_is_importable(self):
        """`server/r2_adapter.py` can ca `botocore.config.Config`."""
        module = importlib.import_module("botocore.config")
        self.assertTrue(hasattr(module, "Config"))

    def test_r2_adapter_module_imports(self):
        from server.r2_adapter import R2ConfigError, R2StorageAdapter

        self.assertTrue(callable(R2StorageAdapter))
        self.assertTrue(issubclass(R2ConfigError, RuntimeError))

    def test_r2_adapter_can_be_constructed_with_dummy_settings(self):
        """
        Khoi tao that su duoc client S3 - day la phep thu chung minh goi da co.

        Gia tri o day la CHUOI GIA, khong phai credential; boto3 khong goi mang
        khi tao client.
        """
        from server.config import R2Settings
        from server.r2_adapter import R2StorageAdapter

        adapter = R2StorageAdapter(R2Settings(
            account_id="khong-co-that",
            access_key_id="khong-co-that",
            secret_access_key="khong-co-that",
            bucket="khong-co-that",
        ))
        self.assertEqual(adapter.mode, "r2")
        self.assertIsNotNone(adapter._client)


class TestBackendSelection(unittest.TestCase):
    """Mock/local van chay khi khong co credential; r2 thieu cau hinh -> fail fast."""

    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in ("DATA_BACKEND", "STORAGE_BACKEND", "R2_ACCOUNT_ID",
                        "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
                        "APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID",
                        "APPWRITE_API_KEY", "APPWRITE_DATABASE_ID",
                        "FAS_ENV_FILE")
        }
        for key in self._saved:
            os.environ.pop(key, None)
        # Tach khoi `server/.env` that tren may lap trinh vien: cac test nay
        # noi ve MAC DINH khi khong co cau hinh, khong ve cau hinh cuc bo.
        os.environ["FAS_ENV_FILE"] = ""

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from server.config import reset_settings

        reset_settings()

    def test_mock_and_local_work_without_any_credential(self):
        from server.adapters import (
            LocalStorageAdapter,
            MockIdentityAdapter,
            MockMetadataStore,
            build_identity,
            build_metadata_store,
            build_storage,
        )
        from server.config import load_settings

        settings = load_settings()
        settings.validate()      # khong duoc nem loi khi thieu credential

        self.assertEqual(settings.data_backend, "mock")
        self.assertEqual(settings.storage_backend, "local")
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)
        self.assertIsInstance(build_storage(settings), LocalStorageAdapter)
        self.assertIsInstance(build_metadata_store(settings), MockMetadataStore)

    def test_storage_backend_r2_without_config_fails_fast(self):
        from server.config import ConfigError, load_settings

        os.environ["STORAGE_BACKEND"] = "r2"
        settings = load_settings()
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        message = str(ctx.exception)
        self.assertIn("R2_ACCOUNT_ID", message)
        self.assertNotIn("mock", message.lower(),
                         "không được gợi ý âm thầm quay về mock")

    def test_data_backend_appwrite_without_config_fails_fast(self):
        from server.config import ConfigError, load_settings

        os.environ["DATA_BACKEND"] = "appwrite"
        settings = load_settings()
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        self.assertIn("APPWRITE_ENDPOINT", str(ctx.exception))

    def test_unknown_backend_value_fails_fast(self):
        from server.config import ConfigError, load_settings

        os.environ["STORAGE_BACKEND"] = "s3"
        settings = load_settings()
        with self.assertRaises(ConfigError):
            settings.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
