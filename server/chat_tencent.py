"""
Tencent — ky UserSig PHIA MAY CHU. DE DANH cho goi thoai/video (TRTC) sau nay.

TU 2026-09-28 TIN NHAN CHU KHONG CON DUNG TENCENT: Appwrite so huu du lieu + Realtime
(`server/messaging/`), va `/api/chat/session` khong con ky UserSig. Module nay giu nguyen
(kem bai test) vi TRTC dung CUNG thuat toan TLSSigAPIv2 va CUNG ma nguoi dung `fw_<id>`
(`server/messaging/ids.py` la nguon DUY NHAT cua ma do).

Trinh duyet KHONG BAO GIO thay SDKSecretKey. No chi nhan `{sdkAppId, userId,
userSig, expiresAt}` tu `POST /api/chat/session`, va `userSig` la mot chu ky
ngan han, gan voi DUNG MOT `userId` — lo ra thi ke khac chi dang nhap duoc
dung tai khoan chat do cho toi khi het han, khong ky duoc gi khac.

HAI MOI TRUONG, TEN BIEN TACH BIET (khong co bien "SDKAPPID" tran):

    FAS_TENCENT_CHAT_ENV                  dev | prod        (BAT BUOC — de trong = chat TAT)
    FAS_TENCENT_CHAT_DEV_SDKAPPID         vd 20047363       (Chat only — QA)
    FAS_TENCENT_CHAT_DEV_SECRET_KEY       khoa bi mat app DEV
    FAS_TENCENT_CHAT_PROD_SDKAPPID        vd 20047362       (Chat + RTC)
    FAS_TENCENT_CHAT_PROD_SECRET_KEY      khoa bi mat app PROD
    FAS_TENCENT_CHAT_USERSIG_TTL_SECONDS  mac dinh 7200, kep [300, 86400]

`FAS_TENCENT_CHAT_ENV=prod` ma thieu bien PROD thi KHONG roi ve DEV: moi
truong da chon khong du cau hinh = chat TAT (fail closed). Mot may chu
production vo tinh ky UserSig bang app DEV se tron nguoi dung that vao du
lieu thu nghiem — tat han con hon.

THUAT TOAN: TLSSigAPIv2 (ban tham chieu chinh thuc cua Tencent, dong
`tls-sig-api-v2-python`): HMAC-SHA256 tren chuoi "TLS.identifier:...\\n
TLS.sdkappid:...\\nTLS.time:...\\nTLS.expire:...\\n", ghep vao JSON, zlib,
base64 roi thay `+ / =` bang `* - _`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import zlib
from dataclasses import dataclass
from typing import Optional

#: Tencent Chat: userID toi da 32 byte. Ta chi dung ky tu ASCII an toan.
USER_ID_MAX = 32
_HOP_LE = re.compile(r"^[A-Za-z0-9_-]+$")
#: Hai tien to KHAC NHAU o ky tu thu ba (`_` vs `h`) — khong the trung nhau.
TIEN_TO = "fw_"
TIEN_TO_BAM = "fwh_"

TTL_MAC_DINH = 7200
TTL_MIN = 300
TTL_MAX = 86400


class ChatNotConfigured(RuntimeError):
    """Moi truong chat da chon chua du cau hinh — endpoint phai tra 503."""


@dataclass(frozen=True)
class TencentChatSettings:
    env: str = ""
    dev_sdk_app_id: int = 0
    dev_secret_key: str = ""
    prod_sdk_app_id: int = 0
    prod_secret_key: str = ""
    usersig_ttl_seconds: int = TTL_MAC_DINH

    @classmethod
    def from_env(cls, environ: Optional[dict] = None) -> "TencentChatSettings":
        e = os.environ if environ is None else environ

        def so(ten: str) -> int:
            gia_tri = (e.get(ten) or "").strip()
            return int(gia_tri) if gia_tri.isdigit() else 0

        ttl_tho = (e.get("FAS_TENCENT_CHAT_USERSIG_TTL_SECONDS") or "").strip()
        ttl = int(ttl_tho) if ttl_tho.isdigit() else TTL_MAC_DINH
        return cls(
            # KHONG co mac dinh: quen dat ENV tren may co ca bien DEV lan PROD
            # khong duoc lang le ky bang app DEV — de trong = chat TAT.
            env=(e.get("FAS_TENCENT_CHAT_ENV") or "").strip().lower(),
            dev_sdk_app_id=so("FAS_TENCENT_CHAT_DEV_SDKAPPID"),
            dev_secret_key=(e.get("FAS_TENCENT_CHAT_DEV_SECRET_KEY") or "").strip(),
            prod_sdk_app_id=so("FAS_TENCENT_CHAT_PROD_SDKAPPID"),
            prod_secret_key=(e.get("FAS_TENCENT_CHAT_PROD_SECRET_KEY") or "").strip(),
            usersig_ttl_seconds=min(max(ttl, TTL_MIN), TTL_MAX),
        )

    @property
    def sdk_app_id(self) -> int:
        if self.env == "prod":
            return self.prod_sdk_app_id
        if self.env == "dev":
            return self.dev_sdk_app_id
        return 0  # gia tri `env` la -> khong co app nao

    @property
    def _secret(self) -> str:
        if self.env == "prod":
            return self.prod_secret_key
        if self.env == "dev":
            return self.dev_secret_key
        return ""

    @property
    def configured(self) -> bool:
        return self.sdk_app_id > 0 and bool(self._secret)

    def describe(self) -> dict:
        """KHONG BAO GIO chua khoa bi mat — chi co/khong co."""
        return {"env": self.env or None, "configured": self.configured,
                "sdk_app_id": self.sdk_app_id or None,
                "usersig_ttl_seconds": self.usersig_ttl_seconds}

    def __repr__(self) -> str:  # khong de khoa lot vao log qua repr()
        return f"TencentChatSettings({self.describe()!r})"


def chat_user_id(fanfic_user_id: str) -> str:
    """Ma nguoi dung Fanfic -> userID Tencent/TRTC. CHUNG ma voi tin nhan — xem `server.messaging.ids`."""
    from server.messaging.ids import chat_user_id as _ma

    return _ma(fanfic_user_id)


def fanfic_user_id_tu_chat(chat_id: str) -> Optional[str]:
    """Nguoc cua `chat_user_id` cho dang `fw_<id>`; dang bam -> None."""
    from server.messaging.ids import fanfic_user_id_from_chat

    return fanfic_user_id_from_chat(chat_id)


def _base64_url(du_lieu: bytes) -> str:
    return (base64.b64encode(du_lieu).decode("ascii")
            .replace("+", "*").replace("/", "-").replace("=", "_"))


def _hmac(secret: str, identifier: str, sdk_app_id: int, luc: int, han: int) -> str:
    noi_dung = (f"TLS.identifier:{identifier}\n" f"TLS.sdkappid:{sdk_app_id}\n"
                f"TLS.time:{luc}\n" f"TLS.expire:{han}\n")
    return base64.b64encode(hmac.new(secret.encode("utf-8"), noi_dung.encode("utf-8"),
                                     hashlib.sha256).digest()).decode("ascii")


def gen_user_sig(sdk_app_id: int, secret: str, identifier: str, expire: int,
                 now: Optional[int] = None) -> str:
    """TLSSigAPIv2 `gen_sig` (khong userbuf)."""
    luc = int(time.time()) if now is None else int(now)
    goi = {
        "TLS.ver": "2.0",
        "TLS.identifier": str(identifier),
        "TLS.sdkappid": int(sdk_app_id),
        "TLS.expire": int(expire),
        "TLS.time": luc,
        "TLS.sig": _hmac(secret, str(identifier), int(sdk_app_id), luc, int(expire)),
    }
    return _base64_url(zlib.compress(json.dumps(goi).encode("utf-8")))


def cap_phien(settings: TencentChatSettings, fanfic_user_id: str,
              now: Optional[int] = None) -> dict:
    """
    Phien chat cho MOT nguoi dung Fanfic. Nem `ChatNotConfigured` khi moi
    truong da chon chua du cau hinh — KHONG bao gio tra mot phien rong.
    """
    if not settings.configured:
        raise ChatNotConfigured("Tin nhắn chưa được bật trên máy chủ.")
    luc = int(time.time()) if now is None else int(now)
    uid = chat_user_id(fanfic_user_id)
    ttl = settings.usersig_ttl_seconds
    return {
        "sdkAppId": settings.sdk_app_id,
        "userId": uid,
        "userSig": gen_user_sig(settings.sdk_app_id, settings._secret, uid, ttl, now=luc),
        # Mili-giay, de trinh duyet so thang voi Date.now().
        "expiresAt": (luc + ttl) * 1000,
        "environment": settings.env,
    }
