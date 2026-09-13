"""
Kho du an Studio — CHI tham chieu, khong mot byte noi dung nao.

Cung khuon `video_project_store.py`/`image_library_store.py`, va cung mot
chi tiet co chu dich trong CHU KY: moi phep doc/ghi deu nhan `owner_user_id`.
Quyen so huu duoc cuong che o TANG KHO, nen mot duong goi moi quen kiem
quyen se khong lay duoc du lieu cua nguoi khac — thay vi lay duoc va cho ai
do nho kiem ho.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from server.studio_project import StudioProject


class MockStudioProjectStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: owner_id -> {project_id: StudioProject}
        self._du_an: Dict[str, Dict[str, StudioProject]] = {}

    def luu(self, du_an: StudioProject) -> StudioProject:
        with self._lock:
            self._du_an.setdefault(du_an.owner_id, {})[du_an.project_id] = du_an
            return du_an

    def liet_ke(self, owner_user_id: str) -> List[StudioProject]:
        with self._lock:
            ds = list(self._du_an.get(owner_user_id, {}).values())
        return sorted(ds, key=lambda d: d.updated_at, reverse=True)

    def lay(self, owner_user_id: str, project_id: str) -> StudioProject:
        with self._lock:
            du_an = self._du_an.get(owner_user_id, {}).get(project_id)
        if du_an is None:
            from server.adapters import NotFoundError
            raise NotFoundError("Không tìm thấy dự án Studio.")
        return du_an

    def tim(self, owner_user_id: str, project_id: str) -> Optional[StudioProject]:
        with self._lock:
            return self._du_an.get(owner_user_id, {}).get(project_id)

    def xoa(self, owner_user_id: str, project_id: str) -> bool:
        """Xoa BAN GHI du an. KHONG dung toi tai san no tro toi.

        Du an la mot CACH NHIN, khong phai mot cai thung — xem docstring dau
        `studio_project.py`. Xoa mot cach nhin khong duoc pha huy thu no dang
        nhin vao.
        """
        with self._lock:
            return self._du_an.get(owner_user_id, {}).pop(project_id, None) is not None

    def dem(self, owner_user_id: str) -> int:
        with self._lock:
            return len(self._du_an.get(owner_user_id, {}))

    def chua_tham_chieu(self, owner_user_id: str, truong: str,
                        ma: str) -> List[StudioProject]:
        """Cac du an dang tro toi `ma` — de giao dien noi "dùng ở 2 dự án"."""
        with self._lock:
            ds = list(self._du_an.get(owner_user_id, {}).values())
        return [d for d in ds if ma in getattr(d, truong, [])]
