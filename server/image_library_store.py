"""
Thu vien anh da luu — Image Studio V1, PHASE 9.

CHI metadata (`SavedImage`) song o day, theo khuon
`gamification_store.py`/`image_wallet_store.py`. Binary anh di qua
`StorageAdapter` da co san (`server/adapters.py` — Local/R2), KHONG viet lai
lop luu tru rieng.

Production Appwrite dang bi chan — kho THAT (Appwrite-backed) se noi tiep
sau; `MockImageLibraryStore` la NGUON SU THAT cho dev/test hien tai va la
GIAO DIEN de kho that trien khai lai sau nay (cung tinh than voi
`MockGamificationStore`/`AppwriteGamificationStore`).
"""

from __future__ import annotations

import threading
from typing import Dict, List

from server.image_domain import SavedImage


class MockImageLibraryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: owner_user_id -> {image_id: SavedImage}
        self._anh: Dict[str, Dict[str, SavedImage]] = {}

    def luu(self, image: SavedImage) -> SavedImage:
        with self._lock:
            self._anh.setdefault(image.owner_user_id, {})[image.image_id] = image
            return image

    def liet_ke(self, owner_user_id: str) -> List[SavedImage]:
        with self._lock:
            ds = list(self._anh.get(owner_user_id, {}).values())
        return sorted(ds, key=lambda a: a.created_at, reverse=True)

    def lay(self, owner_user_id: str, image_id: str) -> SavedImage:
        with self._lock:
            hop = self._anh.get(owner_user_id, {})
        if image_id not in hop:
            from server.adapters import NotFoundError
            raise NotFoundError(f"Không có ảnh {image_id!r} của người dùng này.")
        return hop[image_id]

    def xoa(self, owner_user_id: str, image_id: str) -> bool:
        with self._lock:
            hop = self._anh.get(owner_user_id, {})
            return hop.pop(image_id, None) is not None
