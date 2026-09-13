"""
Kho du an Video Composer — CHI metadata.

Theo dung khuon `image_library_store.py`: nhi phan di qua `StorageBackend`
da co, kho nay chi giu ban ghi.

Chu y mot chi tiet co chu dich trong CHU KY ham: moi phep doc/ghi deu nhan
`owner_user_id`. Quyen so huu duoc cuong che o TANG KHO, khong phai o tang
dich vu — nghia la mot duong goi moi quen kiem quyen se khong lay duoc du
lieu cua nguoi khac, thay vi lay duoc va cho ai do nho kiem.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from server.video_domain import VideoProject


class MockVideoProjectStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: owner_id -> {project_id: VideoProject}
        self._du_an: Dict[str, Dict[str, VideoProject]] = {}

    def luu(self, du_an: VideoProject) -> VideoProject:
        with self._lock:
            self._du_an.setdefault(du_an.owner_id, {})[du_an.project_id] = du_an
            return du_an

    def liet_ke(self, owner_user_id: str) -> List[VideoProject]:
        with self._lock:
            ds = list(self._du_an.get(owner_user_id, {}).values())
        return sorted(ds, key=lambda d: d.updated_at, reverse=True)

    def lay(self, owner_user_id: str, project_id: str) -> VideoProject:
        with self._lock:
            hop = self._du_an.get(owner_user_id, {})
            du_an = hop.get(project_id)
        if du_an is None:
            from server.adapters import NotFoundError
            raise NotFoundError("Không tìm thấy dự án video.")
        return du_an

    def tim(self, owner_user_id: str, project_id: str) -> Optional[VideoProject]:
        """Nhu `lay` nhung tra `None` — cho duong goi tu xu ly vang mat."""
        with self._lock:
            return self._du_an.get(owner_user_id, {}).get(project_id)

    def xoa(self, owner_user_id: str, project_id: str) -> bool:
        with self._lock:
            return self._du_an.get(owner_user_id, {}).pop(project_id, None) is not None

    def dem(self, owner_user_id: str) -> int:
        with self._lock:
            return len(self._du_an.get(owner_user_id, {}))
