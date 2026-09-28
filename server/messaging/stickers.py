"""
Nhan dan (sticker) GOC cua Fanfic cho tin nhan — kien truc san cho goi nhan dan mo khoa sau nay.

  Tin nhan dan = `Message(kind="sticker", sticker_id=...)`. Tin KHONG BAO GIO nhung anh: chi ma nhan dan.
  Anh la tai san tinh: ban phat trien o `web/public/stickers/dev/*.svg` (anh GIU CHO tu ve, khong phai
  tranh cua ben thu ba); production dat `FAS_STICKER_ASSET_BASE` tro vao R2 (vd
  `https://cdn.fanfic.world/stickers`) — duong dan tuong doi (`/stickers`) thi trinh duyet tai tu CHINH
  web.

  Catalog = hop dong `StickerCatalog`. Ban hien tai `DevStickerCatalog` khai bao trong ma. Ban sau:
  `AppwriteStickerCatalog` doc hai bang metadata — `sticker_packs {pack_id, name, order, unlock_kind,
  unlock_value, unlock_label}` + `stickers {sticker_id, pack_id, asset_key, alt, order}` — anh o R2 theo
  `asset_key` (`<pack>/<sticker>.webp`). Doi catalog KHONG doi tin cu: tin chi giu `sticker_id`.

  MO KHOA (may chu quyet, KHONG tin trinh duyet): `free` | `level` (Lv. >= N, tu tien do XP) |
  `achievement` | `event` | `season`. Ba loai sau CHUA co nguon du lieu -> KHOA (hien trong bo chon voi
  dieu kien mo khoa, khong gui duoc). Gui nhan dan cua goi dang khoa -> 403 `chat_sticker_locked`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Tuple

UNLOCK_KINDS = ("free", "level", "achievement", "event", "season")


@dataclass(frozen=True)
class Unlock:
    kind: str = "free"
    #: `level`: so cap toi thieu; `achievement`/`event`/`season`: ma cua nguon do.
    value: str = ""
    #: Dieu kien doc duoc cho nguoi dung ("Mở khoá ở Lv. 5").
    label: str = ""


@dataclass(frozen=True)
class Sticker:
    id: str
    pack_id: str
    #: Duong dan tuong doi trong kho tai san (R2 / `web/public/stickers`) — KHONG phai URL day du.
    asset_key: str
    #: Nhan thay the (doc man hinh, ban xem truoc hop thu, anh loi).
    alt: str


@dataclass(frozen=True)
class StickerPack:
    id: str
    name: str
    unlock: Unlock
    stickers: Tuple[Sticker, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NguoiXem:
    """Nhung gi may chu biet ve nguoi gui de quyet mo khoa. Nguon them sau (thanh tich, su kien)."""
    level: int = 0
    achievements: frozenset = frozenset()
    events: frozenset = frozenset()


class StickerCatalog(Protocol):
    def packs(self) -> List[StickerPack]: ...
    def get(self, sticker_id: str) -> Optional[Sticker]: ...
    def pack(self, pack_id: str) -> Optional[StickerPack]: ...


def asset_base() -> str:
    return (os.environ.get("FAS_STICKER_ASSET_BASE") or "/stickers").rstrip("/")


def asset_url(s: Sticker) -> str:
    return f"{asset_base()}/{s.asset_key}"


def mo_khoa(pack: StickerPack, nguoi: NguoiXem) -> bool:
    u = pack.unlock
    if u.kind == "free":
        return True
    if u.kind == "level":
        try:
            return nguoi.level >= int(u.value)
        except ValueError:
            return False
    if u.kind == "achievement":
        return u.value in nguoi.achievements
    if u.kind in ("event", "season"):
        return u.value in nguoi.events
    return False


def _goi(pack_id: str, name: str, unlock: Unlock, cac: List[Tuple[str, str]]) -> StickerPack:
    return StickerPack(id=pack_id, name=name, unlock=unlock, stickers=tuple(
        Sticker(id=f"{pack_id}.{ma}", pack_id=pack_id, asset_key=f"dev/{pack_id}-{ma}.svg", alt=alt)
        for ma, alt in cac))


#: Goi PHAT TRIEN — anh giu cho tu ve (`web/public/stickers/dev`), thay bang goi that o R2 sau.
DEV_PACKS: Tuple[StickerPack, ...] = (
    _goi("coban", "Cơ bản", Unlock("free"), [
        ("vay-tay", "Vẫy tay"), ("cuoi", "Cười"), ("tim", "Thả tim"), ("cam-on", "Cảm ơn"),
        ("ok", "OK"), ("buon", "Buồn"), ("wow", "Wow"), ("ngu", "Buồn ngủ"),
    ]),
    _goi("tacgia", "Tác giả", Unlock("level", "5", "Mở khoá ở Lv. 5"), [
        ("viet-tiep", "Viết tiếp đi"), ("hong-chuong", "Hóng chương mới"),
        ("tuyet-pham", "Tuyệt phẩm"), ("cam-hung", "Đầy cảm hứng"),
    ]),
    _goi("sukien", "Sự kiện", Unlock("event", "ra-mat-chat", "Mở khoá trong sự kiện ra mắt Tin nhắn"), [
        ("chuc-mung", "Chúc mừng"), ("phao-hoa", "Pháo hoa"), ("qua", "Quà tặng"), ("sao", "Ngôi sao"),
    ]),
)


class DevStickerCatalog:
    def __init__(self, packs: Tuple[StickerPack, ...] = DEV_PACKS) -> None:
        self._packs = list(packs)
        self._theo_id: Dict[str, Sticker] = {s.id: s for p in self._packs for s in p.stickers}
        self._goi: Dict[str, StickerPack] = {p.id: p for p in self._packs}

    def packs(self) -> List[StickerPack]:
        return list(self._packs)

    def get(self, sticker_id: str) -> Optional[Sticker]:
        return self._theo_id.get(sticker_id or "")

    def pack(self, pack_id: str) -> Optional[StickerPack]:
        return self._goi.get(pack_id or "")


DEFAULT_CATALOG = DevStickerCatalog()


def sticker_dto(sticker_id: str, catalog: StickerCatalog = DEFAULT_CATALOG) -> Optional[Dict[str, str]]:
    """Hinh dang cho trinh duyet. Ma khong con trong catalog -> `None` (giao dien hien nhan thay the)."""
    s = catalog.get(sticker_id)
    if s is None:
        return None
    return {"id": s.id, "url": asset_url(s), "alt": s.alt}


def catalog_dto(nguoi: NguoiXem, catalog: StickerCatalog = DEFAULT_CATALOG) -> Dict[str, object]:
    """Bo chon nhan dan: moi goi kem trang thai khoa CUA NGUOI XEM va dieu kien mo khoa (goi khoa van
    liet ke nhan dan de xem truoc, nhung khong gui duoc)."""
    return {"packs": [{
        "id": p.id, "name": p.name, "locked": not mo_khoa(p, nguoi),
        "unlock": {"kind": p.unlock.kind, "label": p.unlock.label},
        "stickers": [{"id": s.id, "url": asset_url(s), "alt": s.alt} for s in p.stickers],
    } for p in catalog.packs()]}


NguoiXemTheoId = Callable[[str], NguoiXem]
