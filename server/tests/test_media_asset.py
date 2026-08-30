import unittest
from unittest.mock import MagicMock, patch

from server.domain import (
    MediaAsset,
    MediaType,
    StorageTier,
    MediaProcessingState,
    PublishState,
)
from server.adapters import MockMediaAssetStore, NotFoundError
from server.storage_backend import (
    R2StorageBackendWrapper,
    DriveArchiveBackend,
)
from server.r2_adapter import R2StorageAdapter
from server.adapters import StoredObject

class TestMediaAsset(unittest.TestCase):
    def test_dataclass_construction_and_to_dict(self):
        asset = MediaAsset(
            owner_id="user_123",
            media_type=MediaType.AUDIO,
            storage_tier=StorageTier.HOT,
            object_key="audio/123.mp3",
            content_hash="hash123",
            source="youtube_harvester",
            codec="mp3",
            bitrate=128,
            duration_seconds=60.5,
            size_bytes=1024,
            processing_state=MediaProcessingState.READY,
            rights_state=PublishState.PUBLISHED,
        )

        self.assertTrue(asset.asset_id.startswith("mas_"))
        self.assertTrue(len(asset.created_at) > 0)

        data = asset.to_dict()
        self.assertEqual(data["owner_id"], "user_123")
        self.assertEqual(data["media_type"], "audio")
        self.assertEqual(data["storage_tier"], "hot")
        self.assertEqual(data["object_key"], "audio/123.mp3")
        self.assertEqual(data["content_hash"], "hash123")
        self.assertEqual(data["source"], "youtube_harvester")
        self.assertEqual(data["codec"], "mp3")
        self.assertEqual(data["bitrate"], 128)
        self.assertEqual(data["duration_seconds"], 60.5)
        self.assertEqual(data["size_bytes"], 1024)
        self.assertEqual(data["processing_state"], "ready")
        self.assertEqual(data["rights_state"], "published")


class TestMockMediaAssetStore(unittest.TestCase):
    def setUp(self):
        self.store = MockMediaAssetStore()

    def test_create_and_get(self):
        asset = MediaAsset(
            owner_id="user_1",
            media_type=MediaType.IMAGE,
            storage_tier=StorageTier.HOT,
            object_key="img/1.png",
            content_hash="img1"
        )
        self.store.create_asset(asset)

        retrieved = self.store.get_asset(asset.asset_id)
        self.assertEqual(retrieved.object_key, "img/1.png")

        with self.assertRaises(NotFoundError):
            self.store.get_asset("mas_invalid")

    def test_list_assets(self):
        a1 = MediaAsset("user_1", MediaType.IMAGE, StorageTier.HOT, "k1", "h1")
        a2 = MediaAsset("user_1", MediaType.AUDIO, StorageTier.HOT, "k2", "h2")
        a3 = MediaAsset("user_2", MediaType.AUDIO, StorageTier.HOT, "k3", "h3")

        self.store.create_asset(a1)
        self.store.create_asset(a2)
        self.store.create_asset(a3)

        assets_u1 = self.store.list_assets("user_1")
        self.assertEqual(len(assets_u1), 2)
        keys = {a.object_key for a in assets_u1}
        self.assertEqual(keys, {"k1", "k2"})


class TestStorageBackends(unittest.TestCase):
    def test_r2_backend_wrapper(self):
        # We can just mock the adapter instance entirely
        mock_adapter = MagicMock(spec=R2StorageAdapter)
        mock_adapter.put.return_value = "key/path"
        mock_adapter.signed_url.return_value = "https://signed.url"
        mock_adapter.delete.return_value = True
        mock_adapter.list_objects.return_value = [
            StoredObject("k1", 100, "2023"),
            StoredObject("k2", 200, "2023"),
        ]

        backend = R2StorageBackendWrapper(mock_adapter)
        
        self.assertEqual(backend.put("key", b"data"), "key/path")
        mock_adapter.put.assert_called_once_with("key", b"data", "application/octet-stream")

        self.assertEqual(backend.get_url("key", 3600), "https://signed.url")
        mock_adapter.signed_url.assert_called_once_with("key", 3600)

        self.assertTrue(backend.delete("key"))
        mock_adapter.delete.assert_called_once_with("key")

        self.assertEqual(backend.usage_bytes(), 300)
        mock_adapter.list_objects.assert_called_once()

    def test_drive_archive_backend_stub(self):
        backend = DriveArchiveBackend()

        with self.assertRaises(NotImplementedError):
            backend.put("key", b"data")

        with self.assertRaises(NotImplementedError):
            backend.get_url("key")

        with self.assertRaises(NotImplementedError):
            backend.delete("key")

        with self.assertRaises(NotImplementedError):
            backend.usage_bytes()
