"""
Kho Animation trong bo nho (V6, overnight Phase 5).

CUNG MAU va CUNG NGUYEN TAC voi `server/gamification_store.py`: module nay
chi dinh nghia `MockAnimationStore` — ban ben vung that qua restart la
`server/appwrite_animation_store.py::AppwriteAnimationStore`, CUNG giao dien,
va `build_animation_store()` (chon Mock/Appwrite theo `DATA_BACKEND`) nam o
do, KHONG phai o day.

MOT KHO DOC LAP — khong dung chung bang voi `novels`/`chapters`. Xem docstring
dau `server/animation_domain.py` ve vi sao Animation la mot san pham RIENG.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.adapters import NotFoundError, PermissionDenied
from server.animation_domain import AnimationEpisode, AnimationSeries
from server.domain import PublishState, now_iso


class MockAnimationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.series: Dict[str, AnimationSeries] = {}
        self.episodes: Dict[str, AnimationEpisode] = {}

    # -- series ---------------------------------------------------------------

    def create_series(self, series: AnimationSeries) -> AnimationSeries:
        with self._lock:
            self.series[series.series_id] = series
            return series

    def get_series(self, series_id: str) -> AnimationSeries:
        series = self.series.get(series_id)
        if series is None:
            raise NotFoundError("Không tìm thấy series animation.")
        return series

    def owned_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        series = self.get_series(series_id)
        if series.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu series này.")
        return series

    def find_series(self, owner_id: Optional[str] = None,
                    published_only: bool = False, query: str = "",
                    tag: str = "", limit: Optional[int] = None,
                    offset: int = 0) -> Tuple[List[AnimationSeries], int]:
        """Tim series co LOC va PHAN TRANG — cung contract voi
        `MetadataStore.find_novels`."""
        with self._lock:
            items = list(self.series.values())
        if owner_id:
            items = [s for s in items if s.owner_id == owner_id]
        if published_only:
            items = [s for s in items if s.state.value == "published"]
        if tag:
            items = [s for s in items if tag in s.tags]
        needle = query.strip().casefold()
        if needle:
            items = [s for s in items
                     if needle in s.title.casefold()
                     or needle in (s.description or "").casefold()]
        items.sort(key=lambda s: s.created_at, reverse=True)
        total = len(items)
        start = max(0, offset)
        page = items[start:] if limit is None else items[start:start + max(0, limit)]
        return page, total

    def series_tags(self, published_only: bool = True) -> List[str]:
        with self._lock:
            items = list(self.series.values())
        if published_only:
            items = [s for s in items if s.state.value == "published"]
        tags = {t for s in items for t in s.tags if t}
        return sorted(tags, key=lambda t: t.casefold())

    #: Chi nhung truong nay moi cho nguoi dung sua truc tiep.
    SERIES_EDITABLE = ("title", "description", "tags", "related_novel_id")

    def update_series(self, series_id: str, owner_id: str,
                      fields: Dict[str, Any]) -> AnimationSeries:
        with self._lock:
            current = self.owned_series(series_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.SERIES_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.series[series_id] = updated
            return updated

    def set_series_cover(self, series_id: str, owner_id: str,
                         cover_key: Optional[str]) -> AnimationSeries:
        with self._lock:
            current = self.owned_series(series_id, owner_id)
            updated = replace(current, cover_key=cover_key, updated_at=now_iso())
            self.series[series_id] = updated
            return updated

    def publish_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        with self._lock:
            current = self.owned_series(series_id, owner_id)
            if current.state == PublishState.PUBLISHED:
                return current
            published = replace(current, state=PublishState.PUBLISHED,
                                updated_at=now_iso())
            self.series[series_id] = published
            return published

    def unpublish_series(self, series_id: str, owner_id: str) -> AnimationSeries:
        with self._lock:
            current = self.owned_series(series_id, owner_id)
            if current.state != PublishState.PUBLISHED:
                return current
            reverted = replace(current, state=PublishState.DRAFT,
                               updated_at=now_iso())
            self.series[series_id] = reverted
            return reverted

    def delete_series(self, series_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_series(series_id, owner_id)
            self.series.pop(series_id, None)

    # -- episode ----------------------------------------------------------------

    def create_episode(self, episode: AnimationEpisode) -> AnimationEpisode:
        with self._lock:
            self.episodes[episode.episode_id] = episode
            return episode

    def get_episode(self, episode_id: str) -> AnimationEpisode:
        episode = self.episodes.get(episode_id)
        if episode is None:
            raise NotFoundError("Không tìm thấy tập animation.")
        return episode

    def owned_episode(self, episode_id: str, owner_id: str) -> AnimationEpisode:
        episode = self.get_episode(episode_id)
        if episode.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tập này.")
        return episode

    def list_episodes(self, series_id: str) -> List[AnimationEpisode]:
        with self._lock:
            items = [e for e in self.episodes.values() if e.series_id == series_id]
        items.sort(key=lambda e: e.order_index)
        return items

    def total_episodes(self) -> int:
        """Tong so tap TREN TOAN NEN TANG — bang dieu khien quan tri (Admin
        Control Center V2, A1). Mot phep dem, khong phai vong lap tren tung
        series (do se la N+1)."""
        with self._lock:
            return len(self.episodes)

    #: `owner_id`, `series_id`, `state`, `source` khong cho client sua qua day.
    EPISODE_EDITABLE = ("title", "external_id", "order_index", "duration_seconds")

    def update_episode(self, episode_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> AnimationEpisode:
        with self._lock:
            current = self.owned_episode(episode_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.EPISODE_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.episodes[episode_id] = updated
            return updated

    def delete_episode(self, episode_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_episode(episode_id, owner_id)
            self.episodes.pop(episode_id, None)

    def reorder_episodes(self, series_id: str, owner_id: str,
                         episode_ids: Sequence[str]) -> List[AnimationEpisode]:
        """Dat lai `order_index` — cung contract voi
        `MetadataStore.reorder_chapters`."""
        self.owned_series(series_id, owner_id)
        with self._lock:
            current = {e.episode_id for e in self.episodes.values()
                       if e.series_id == series_id}
            wanted = list(dict.fromkeys(episode_ids))
            if set(wanted) != current or len(wanted) != len(episode_ids):
                raise ValueError(
                    "Danh sách thứ tự phải gồm đúng các tập của series này.")
            for position, episode_id in enumerate(wanted, start=1):
                episode = self.episodes[episode_id]
                self.episodes[episode_id] = replace(episode, order_index=position)
            return [self.episodes[eid] for eid in wanted]
