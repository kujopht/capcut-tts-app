"""
TAI THANG len kho doi tuong — thay cho base64 trong than JSON.

VI SAO DOI: PR #202 gui video bang base64 trong than JSON. Base64 lam moi
byte thanh ~1.37 byte tren duong truyen, VA bat ca tep di qua tien trinh web
— mot tep 200 MB nghia la 274 MB chuoi nam trong bo nho cua mot tien trinh
dang phuc vu HTTP cho moi nguoi khac.

Luong moi:

    trinh duyet  -> xin MOT PHIEN tai len (kem loai/kich thuoc/MIME)
                 -> tai THANG len kho doi tuong bang URL ky san
                 -> goi `finalize` de backend kiem va ghi metadata
                 -> tai san dung duoc

BA DIEU QUYET DINH AN TOAN CUA CA LUONG NAY:

1. **Khoa doi tuong do MAY CHU sinh.** Khong bao gio nhan tu than yeu cau.
   Nhan khoa tu client la cho phep ghi de len khoa cua nguoi khac.
2. **Phien CO HAN va gan chat MOT chu.** `finalize` doi dung chu da xin
   phien; mot phien cua nguoi khac khong finalize duoc.
3. **`finalize` KIEM THAT.** Kich thuoc that duoc doc lai TU KHO, khong tin
   con so client khai — neu khong, khai 1 byte roi day len 2 GB la xong.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Protocol

from server.domain import MediaType, new_id, now_iso

#: Phien song bao lau. Du de tai mot tep lon tren mang cham, khong du de mot
#: URL ro ri con dung duoc vao ngay mai.
HAN_PHIEN_GIAY = 30 * 60

#: Tran kich thuoc theo loai — CHOT O MAY CHU, khong theo con so client khai.
TRAN_BYTE: Dict[MediaType, int] = {
    MediaType.VIDEO: 2 * 1024 * 1024 * 1024,      # 2 GB
    MediaType.AUDIO: 512 * 1024 * 1024,
    MediaType.IMAGE: 32 * 1024 * 1024,
    MediaType.SUBTITLES: 4 * 1024 * 1024,
}

#: Danh sach CHO PHEP cho tung loai. Danh sach cam la mot danh sach luon
#: thieu mot dong.
MIME_CHO_PHEP: Dict[MediaType, frozenset] = {
    MediaType.VIDEO: frozenset({
        "video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}),
    MediaType.AUDIO: frozenset({
        "audio/mpeg", "audio/mp4", "audio/aac", "audio/wav", "audio/ogg"}),
    MediaType.IMAGE: frozenset({
        "image/jpeg", "image/png", "image/webp"}),
    MediaType.SUBTITLES: frozenset({
        "text/vtt", "application/x-subrip", "text/plain"}),
}

#: Duoi tep theo loai — de khoa doi tuong mang duoi dung, khong lay tu ten
#: nguoi dung gui (mot ten `.mp4.exe` khong duoc bien thanh khoa `.exe`).
DUOI: Dict[MediaType, str] = {
    MediaType.VIDEO: "mp4", MediaType.AUDIO: "mp3",
    MediaType.IMAGE: "jpg", MediaType.SUBTITLES: "srt",
}


class UploadState(str, Enum):
    PENDING = "pending"
    FINALIZED = "finalized"
    ABANDONED = "abandoned"


class UploadError(ValueError):
    """Thong diep danh cho NGUOI DUNG doc."""


@dataclass
class UploadSession:
    owner_id: str
    media_type: MediaType
    mime: str
    #: Kich thuoc client KHAI — chi de tu choi som. `finalize` do lai that.
    declared_bytes: int
    object_key: str
    expires_at: float
    state: UploadState = UploadState.PENDING
    session_id: str = field(default_factory=lambda: new_id("ups"))
    created_at: str = field(default_factory=now_iso)

    def con_han(self, *, now: Optional[float] = None) -> bool:
        return (time.time() if now is None else now) < self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "media_type": self.media_type.value,
            "mime": self.mime,
            "expires_at": self.expires_at,
            "state": self.state.value,
            #: `object_key` CO tra ve — nhung no do may chu sinh, va
            #: `finalize` khong nhan khoa tu client nen biet no khong giup gi
            #: cho mot ke tan cong.
            "object_key": self.object_key,
        }


class UploadProvider(Protocol):
    """Cach cap mot duong GHI co han cho mot khoa."""

    def presign_put(self, key: str, mime: str, expires_seconds: int) -> str: ...


class LocalUploadProvider:
    """Kho cuc bo khong ky duoc URL — tra ve duong PUT qua backend.

    Cung hinh dang voi `LocalStorageAdapter.signed_url` tra `None`: ban cuc
    bo di qua backend, ban R2 di thang. Giao dien khong can biet no dang noi
    chuyen voi ban nao.
    """

    def presign_put(self, key: str, mime: str, expires_seconds: int) -> str:
        return ""


class R2UploadProvider:
    """Ky mot `put_object` that.

    CHUA duoc chay tren production trong dot nay — no o day de hop dong
    duoc dinh nghia va kiem, con viec bat len la mot lan cau hinh.
    """

    def __init__(self, r2_adapter) -> None:
        self._r2 = r2_adapter

    def presign_put(self, key: str, mime: str, expires_seconds: int) -> str:
        client = getattr(self._r2, "_client", None)
        bucket = getattr(self._r2, "_bucket", None)
        if client is None or not bucket:
            return ""
        try:
            return client.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket, "Key": key, "ContentType": mime},
                ExpiresIn=int(expires_seconds))
        except Exception:                                       # noqa: BLE001
            return ""


class MockUploadSessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._phien: Dict[str, UploadSession] = {}

    def luu(self, p: UploadSession) -> UploadSession:
        with self._lock:
            self._phien[p.session_id] = p
            return p

    def lay(self, owner_user_id: str, session_id: str) -> UploadSession:
        with self._lock:
            p = self._phien.get(session_id)
        # Khong phai cua minh = khong ton tai. Xem ghi chu dau tep.
        if p is None or p.owner_id != owner_user_id:
            from server.adapters import NotFoundError
            raise NotFoundError("Không tìm thấy phiên tải lên.")
        return p

    def don_het_han(self, *, now: Optional[float] = None) -> int:
        """Danh dau cac phien qua han la BO DO.

        Khong xoa ban ghi: mot phien bo do la mot su that dang giu lai (co
        bao nhieu lan tai len that bai?), va ban ghi thi re. Doi tuong mo coi
        trong kho la viec cua duong don rac, khong phai cua ham nay.
        """
        curr = time.time() if now is None else now
        n = 0
        with self._lock:
            for p in self._phien.values():
                if p.state is UploadState.PENDING and curr >= p.expires_at:
                    p.state = UploadState.ABANDONED
                    n += 1
        return n


def khoa_moi(owner_id: str, loai: MediaType) -> str:
    """Khoa doi tuong — MAY CHU sinh, client khong bao gio chon.

    Hinh dang `studio/<chu>/<loai>/<ngau nhien>.<duoi>`: co chu so huu trong
    duong dan de doi soat/don rac doc duoc bang mat, va phan ngau nhien du
    dai de khong doan duoc.
    """
    return (f"studio/{owner_id}/{loai.value}/"
            f"{uuid.uuid4().hex}.{DUOI[loai]}")


def kiem_xin_phien(loai: MediaType, mime: str, so_byte: Any) -> int:
    """Kiem tham so XIN phien. Tra ve kich thuoc khai da lam sach."""
    sach = (mime or "").split(";")[0].strip().lower()
    if sach not in MIME_CHO_PHEP.get(loai, frozenset()):
        raise UploadError(f"Định dạng {mime!r} không được hỗ trợ cho {loai.value}.")
    if isinstance(so_byte, bool) or not isinstance(so_byte, int):
        raise UploadError("Kích thước tệp không hợp lệ.")
    if so_byte <= 0:
        raise UploadError("Tệp rỗng.")
    tran = TRAN_BYTE[loai]
    if so_byte > tran:
        raise UploadError(
            f"Tệp vượt quá {tran // (1024 * 1024)} MB.")
    return so_byte
