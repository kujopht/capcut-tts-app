"""
Test cho adapter that (Appwrite / R2) - chay HOAN TOAN offline.

Khong goi Appwrite hay R2 that: chi kiem tra logic chon adapter, phat hien
cau hinh sai, va nguyen tac "khong am tham lui ve mock".
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from server.adapters import (
    LocalStorageAdapter,
    MockIdentityAdapter,
    NotFoundError,
    build_identity,
    build_storage,
)
from server.config import AppwriteSettings, R2Settings, Settings


def _settings(**kwargs) -> Settings:
    base = {"environment": "development", "var_dir": Path(tempfile.mkdtemp())}
    base.update(kwargs)
    return Settings(**base)


class TestAdapterSelection(unittest.TestCase):
    def test_mock_when_no_credentials(self):
        settings = _settings()
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)
        self.assertIsInstance(build_storage(settings), LocalStorageAdapter)
        self.assertEqual(settings.identity_mode, "mock")
        self.assertEqual(settings.storage_mode, "mock")

    def test_partial_appwrite_config_stays_mock(self):
        """Thieu mot bien -> coi nhu chua cau hinh, khong nua voi."""
        settings = _settings(appwrite=AppwriteSettings(
            endpoint="https://x/v1", project_id="p", api_key="k",  # thieu database_id
        ))
        self.assertFalse(settings.appwrite.configured)
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)

    def test_partial_r2_config_stays_mock(self):
        settings = _settings(r2=R2Settings(
            account_id="a", access_key_id="k", secret_access_key="s",  # thieu bucket
        ))
        self.assertFalse(settings.r2.configured)
        self.assertIsInstance(build_storage(settings), LocalStorageAdapter)

    def test_full_appwrite_config_does_not_fall_back_to_mock(self):
        """Da khai bao du ma sai thi phai BAO LOI, khong duoc im lang dung mock."""
        settings = _settings(appwrite=AppwriteSettings(
            endpoint="khong-phai-url", project_id="p", api_key="k", database_id="d",
        ))
        self.assertTrue(settings.appwrite.configured)
        from server.appwrite_adapter import AppwriteConfigError

        with self.assertRaises(AppwriteConfigError):
            build_identity(settings)

    def test_full_r2_config_does_not_fall_back_to_mock(self):
        settings = _settings(r2=R2Settings(
            account_id="acc", access_key_id="k", secret_access_key="s", bucket="b",
        ))
        self.assertTrue(settings.r2.configured)
        from server.r2_adapter import R2ConfigError

        try:
            adapter = build_storage(settings)
        except R2ConfigError:
            return          # chua cai boto3 -> bao loi ro, dung nhu thiet ke
        self.assertEqual(adapter.mode, "r2")
        self.assertNotIsInstance(adapter, LocalStorageAdapter)

    def test_r2_endpoint_is_derived_not_hardcoded(self):
        r2 = R2Settings(account_id="abc123", access_key_id="k",
                        secret_access_key="s", bucket="b")
        self.assertEqual(r2.endpoint_url, "https://abc123.r2.cloudflarestorage.com")

    def test_settings_describe_never_leaks_secrets(self):
        settings = _settings(
            appwrite=AppwriteSettings(endpoint="https://x/v1", project_id="p",
                                      api_key="BIMAT", database_id="d"),
            r2=R2Settings(account_id="a", access_key_id="KHOABIMAT",
                          secret_access_key="RATBIMAT", bucket="b"),
        )
        text = str(settings.describe())
        for secret in ("BIMAT", "KHOABIMAT", "RATBIMAT"):
            self.assertNotIn(secret, text)


class TestLocalStorage(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.storage = LocalStorageAdapter(self.root)

    def test_put_and_get(self):
        self.storage.put("audio/u1/c1/x.mp3", b"\x00" * 2048)
        self.assertEqual(len(self.storage.get("audio/u1/c1/x.mp3")), 2048)
        self.assertTrue(self.storage.exists("audio/u1/c1/x.mp3"))
        self.assertEqual(self.storage.size("audio/u1/c1/x.mp3"), 2048)

    def test_missing_key_raises(self):
        with self.assertRaises(NotFoundError):
            self.storage.get("khong/co.mp3")

    def test_path_traversal_blocked(self):
        with self.assertRaises(ValueError):
            self.storage.put("../../thoat.mp3", b"x")

    def test_no_partial_file_left_behind(self):
        self.storage.put("a/b.mp3", b"\x00" * 512)
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_local_has_no_signed_url(self):
        """Ban cuc bo tra None de tang tren biet phai stream qua backend."""
        self.assertIsNone(self.storage.signed_url("a/b.mp3"))


class TestAppwriteAdapterGuards(unittest.TestCase):
    def test_incomplete_config_rejected(self):
        from server.appwrite_adapter import AppwriteConfigError, AppwriteIdentityAdapter

        with self.assertRaises(AppwriteConfigError):
            AppwriteIdentityAdapter(AppwriteSettings())

    def test_bad_endpoint_rejected_with_clear_message(self):
        from server.appwrite_adapter import AppwriteConfigError, AppwriteIdentityAdapter

        with self.assertRaises(AppwriteConfigError) as ctx:
            AppwriteIdentityAdapter(AppwriteSettings(
                endpoint="ftp://sai", project_id="p", api_key="k", database_id="d",
            ))
        self.assertIn("http", str(ctx.exception).lower())

    def test_api_key_only_in_server_headers(self):
        """API key chi duoc gan o header phia server, khong lot ra cho khac."""
        from server.appwrite_adapter import AppwriteIdentityAdapter

        adapter = AppwriteIdentityAdapter(AppwriteSettings(
            endpoint="https://example.test/v1", project_id="p",
            api_key="SIEUBIMAT", database_id="d",
        ))
        admin = adapter._headers(admin=True)
        self.assertEqual(admin["X-Appwrite-Key"], "SIEUBIMAT")

        # Khi dung JWT cua nguoi dung thi TUYET DOI khong gui API key
        with_jwt = adapter._headers(jwt="jwt-cua-nguoi-dung")
        self.assertNotIn("X-Appwrite-Key", with_jwt)


class TestR2AdapterGuards(unittest.TestCase):
    def test_incomplete_config_rejected(self):
        from server.r2_adapter import R2ConfigError, R2StorageAdapter

        with self.assertRaises(R2ConfigError):
            R2StorageAdapter(R2Settings())

    def test_missing_boto3_reports_clearly(self):
        """Da cau hinh R2 ma thieu boto3 thi phai noi ro cach khac phuc."""
        import importlib.util

        if importlib.util.find_spec("boto3") is not None:
            self.skipTest("boto3 đã được cài")
        from server.r2_adapter import R2ConfigError, R2StorageAdapter

        with self.assertRaises(R2ConfigError) as ctx:
            R2StorageAdapter(R2Settings(account_id="a", access_key_id="k",
                                        secret_access_key="s", bucket="b"))
        self.assertIn("boto3", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
