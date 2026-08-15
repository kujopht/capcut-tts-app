"""
BYOP (Bring-Your-Own-Pollinations) — OAuth 2.1 Authorization Code + PKCE.

PHASE 4C cua dac ta overnight yeu cau CHINH XAC luong nay (KHONG phai fragment
flow cu). Endpoint duoc xac nhan qua RFC 8414 discovery THAT (KHONG doan):

    GET https://enter.pollinations.ai/.well-known/oauth-authorization-server

tra ve (2026-08-16, khong dung credential nao de doc trang nay):

    authorization_endpoint = https://enter.pollinations.ai/authorize
    token_endpoint         = https://enter.pollinations.ai/api/oauth/token
    userinfo_endpoint      = https://enter.pollinations.ai/api/oauth/userinfo
    scopes_supported       = ["profile", "usage", "keys"]
    code_challenge_methods_supported = ["S256"]
    token_endpoint_auth_methods_supported = ["none"]  # public client, PKCE bat buoc

KHONG co `revocation_endpoint` duoc cong bo — "Ngat ket noi" phia Fanfic World
la XOA/thu hoi token da luu O PHIA CHUNG TA (ngung dung no), KHONG phai mot
loi goi API revoke that su toi Pollinations (tai lieu chinh thuc chua co
endpoint do). Ghi lai o day de khong ai tuong lam co san.

Chi xin scope `"keys"` (toi thieu can de sinh anh thay mat nguoi dung) — KHONG
xin them "profile"/"usage" tru khi san pham thuc su can hien thong tin do
(PHASE 4C: "Do not request unnecessary OAuth scopes").
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

import httpx

from server.image_byop_crypto import PROVIDER_ID, ByokCrypto
from server.image_domain import PollinationsConnection, now_iso

AUTHORIZATION_ENDPOINT = "https://enter.pollinations.ai/authorize"
TOKEN_ENDPOINT = "https://enter.pollinations.ai/api/oauth/token"
DEFAULT_SCOPE = "keys"

_PENDING_TTL_SECONDS = 600  # 10 phut - du de nguoi dung xac thuc ben Pollinations


class ByopError(Exception):
    pass


class ByopStateMismatch(ByopError):
    """CSRF: `state` tra ve khong khop voi state da phat hanh, hoac da het
    han/da dung — LUON tu choi, khong co ngoai le."""


class ByopExchangeFailed(ByopError):
    """Doi code lay token that bai — thong diep O DAY phai an toan de hien
    thi (khong dump body loi tho cua Pollinations)."""


@dataclass(frozen=True)
class PendingAuthorization:
    state: str
    code_verifier: str
    user_id: str
    redirect_uri: str
    created_at_monotonic: float


@dataclass(frozen=True)
class PkcePair:
    code_verifier: str
    code_challenge: str


def tao_pkce() -> PkcePair:
    """`code_verifier`: 43-128 ky tu URL-safe (RFC 7636). `code_challenge`:
    BASE64URL(SHA256(verifier)), khong padding — phuong phap S256 DUY NHAT
    duoc Pollinations cong bo ho tro."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return PkcePair(code_verifier=verifier, code_challenge=challenge)


def tao_state() -> str:
    return secrets.token_urlsafe(32)


class MockPendingAuthorizationStore:
    """Giu (state -> PendingAuthorization) TAM THOI giua buoc /authorize va
    /callback — trong bo nho, tu het han sau `_PENDING_TTL_SECONDS`. Du cho
    MOT tien trinh (dev/test); production nhieu tien trinh can chuyen sang
    kho dung chung (Redis/Appwrite) — ghi ro trong tai lieu ban giao."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cho: Dict[str, PendingAuthorization] = {}

    def luu(self, pending: PendingAuthorization) -> None:
        with self._lock:
            self._don_rac()
            self._cho[pending.state] = pending

    def lay_va_xoa(self, state: str) -> Optional[PendingAuthorization]:
        """MOT LAN DUY NHAT: state da dung (thanh cong hay that bai) deu bi
        xoa ngay — chan replay callback voi cung state."""
        with self._lock:
            self._don_rac()
            return self._cho.pop(state, None)

    def _don_rac(self) -> None:
        now = time.monotonic()
        het_han = [
            s for s, p in self._cho.items()
            if now - p.created_at_monotonic > _PENDING_TTL_SECONDS
        ]
        for s in het_han:
            del self._cho[s]


class MockByopConnectionStore:
    """user_id -> PollinationsConnection (encrypted-at-rest qua ByokCrypto) —
    theo khuon MockWalletStore/MockGamificationStore. Ban Appwrite se noi
    tiep sau khi production Appwrite duoc mo lai (PHASE 9)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ket_noi: Dict[str, PollinationsConnection] = {}

    def luu(self, connection: PollinationsConnection) -> PollinationsConnection:
        with self._lock:
            self._ket_noi[connection.user_id] = connection
            return connection

    def lay(self, user_id: str) -> Optional[PollinationsConnection]:
        with self._lock:
            return self._ket_noi.get(user_id)

    def ngat_ket_noi(self, user_id: str) -> Optional[PollinationsConnection]:
        """Xoa token phia CHUNG TA — xem canh bao dau file ve viec khong co
        `revocation_endpoint`."""
        with self._lock:
            hien_tai = self._ket_noi.get(user_id)
            if hien_tai is None:
                return None
            moi = PollinationsConnection(
                **{**hien_tai.__dict__, "encrypted_access_token": "",
                  "encrypted_refresh_token": "", "revoked_at": now_iso()}
            )
            self._ket_noi[user_id] = moi
            return moi


class PollinationsByopService:
    def __init__(
        self, *, client_id: str, redirect_uri: str, crypto: Optional[ByokCrypto],
        pending_store: Optional[MockPendingAuthorizationStore] = None,
        connection_store: Optional[MockByopConnectionStore] = None,
        http_client: Optional[httpx.Client] = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not client_id:
            raise ByopError("Thiếu POLLINATIONS_CLIENT_ID (pk_...).")
        if not redirect_uri:
            raise ByopError("Thiếu redirect URI cấu hình cho BYOP.")
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._crypto = crypto
        self._pending = pending_store or MockPendingAuthorizationStore()
        self._connections = connection_store or MockByopConnectionStore()
        self._http_client = http_client
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        """BYOP chi thuc su hoat dong khi CO ma hoa cau hinh — xem PHASE 4C:
        'otherwise keep implementation behind a feature flag until secure
        persistence is available'."""
        return self._crypto is not None

    def bat_dau_ket_noi(self, *, user_id: str) -> str:
        """Tra ve URL de dieu huong trinh duyet toi Pollinations. Luu
        (state, code_verifier) TAM THOI de doi chieu o buoc callback."""
        if not self.enabled:
            raise ByopError(
                "BYOP chưa sẵn sàng — thiếu IMAGE_BYOP_MASTER_KEY (mã hoá "
                "token cá nhân) trên máy chủ."
            )
        pkce = tao_pkce()
        state = tao_state()
        self._pending.luu(PendingAuthorization(
            state=state, code_verifier=pkce.code_verifier, user_id=user_id,
            redirect_uri=self._redirect_uri, created_at_monotonic=time.monotonic(),
        ))
        tham_so = (
            f"response_type=code&client_id={self._client_id}"
            f"&redirect_uri={_url_encode(self._redirect_uri)}"
            f"&state={state}&code_challenge={pkce.code_challenge}"
            f"&code_challenge_method=S256&scope={DEFAULT_SCOPE}"
        )
        return f"{AUTHORIZATION_ENDPOINT}?{tham_so}"

    def xu_ly_callback(
        self, *, user_id: str, state: str, code: str, redirect_uri: str,
        user_budget_micro: int = 0,
    ) -> PollinationsConnection:
        """Xac thuc `state` (CSRF), doi `code` lay token, ma hoa va luu.

        `redirect_uri` truyen vao PHAI khop CHINH XAC voi redirect_uri da
        dang ky/da dung o `bat_dau_ket_noi` — Pollinations doi chieu chinh
        xac scheme+host+port+path; sai lech o day la dau hieu callback bi
        gia mao hoac cau hinh redirect sai.
        """
        pending = self._pending.lay_va_xoa(state)
        if pending is None or pending.user_id != user_id:
            raise ByopStateMismatch(
                "Phiên kết nối Pollinations không hợp lệ hoặc đã hết hạn — "
                "vui lòng thử kết nối lại."
            )
        if pending.redirect_uri != redirect_uri:
            raise ByopStateMismatch("Redirect URI không khớp với phiên đã bắt đầu.")

        token = self._doi_code_lay_token(code=code, code_verifier=pending.code_verifier)

        if self._crypto is None:
            raise ByopError("BYOP chưa sẵn sàng — thiếu cấu hình mã hoá.")
        enc_access = self._crypto.ma_hoa(
            token["access_token"], user_id=user_id, provider_id=PROVIDER_ID)
        enc_refresh = ""
        if token.get("refresh_token"):
            enc_refresh = self._crypto.ma_hoa(
                token["refresh_token"], user_id=user_id, provider_id=PROVIDER_ID)

        connection = PollinationsConnection(
            user_id=user_id,
            encrypted_access_token=enc_access,
            encrypted_refresh_token=enc_refresh,
            scope=token.get("scope", DEFAULT_SCOPE),
            expires_at=_tinh_expires_at(token.get("expires_in")),
            user_budget_micro=user_budget_micro,
        )
        return self._connections.luu(connection)

    def _doi_code_lay_token(self, *, code: str, code_verifier: str) -> dict:
        than = (
            f"grant_type=authorization_code&code={_url_encode(code)}"
            f"&redirect_uri={_url_encode(self._redirect_uri)}"
            f"&client_id={self._client_id}&code_verifier={code_verifier}"
        )
        client = self._http_client or httpx.Client(timeout=self._timeout, trust_env=False)
        try:
            resp = client.post(
                TOKEN_ENDPOINT, content=than,
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as exc:
            raise ByopExchangeFailed(
                "Không đổi được mã xác thực lấy quyền truy cập — "
                "Pollinations hiện không phản hồi."
            ) from exc
        finally:
            if self._http_client is None:
                client.close()

        if resp.status_code != 200:
            raise ByopExchangeFailed(
                "Mã xác thực không hợp lệ hoặc đã hết hạn — vui lòng kết nối lại."
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise ByopExchangeFailed("Phản hồi từ Pollinations không hợp lệ.") from exc
        if "access_token" not in data:
            raise ByopExchangeFailed("Phản hồi từ Pollinations thiếu access_token.")
        return data

    def trang_thai(self, user_id: str) -> Optional[PollinationsConnection]:
        return self._connections.lay(user_id)

    def ngat_ket_noi(self, user_id: str) -> Optional[PollinationsConnection]:
        return self._connections.ngat_ket_noi(user_id)

    def giai_ma_access_token(self, connection: PollinationsConnection) -> str:
        """CHI goi tu tang service NGAY TRUOC khi goi Pollinations — khong
        bao gio giu plaintext token lau hon mot lan goi, khong bao gio log."""
        if self._crypto is None:
            raise ByopError("BYOP chưa sẵn sàng — thiếu cấu hình mã hoá.")
        return self._crypto.giai_ma(
            connection.encrypted_access_token,
            user_id=connection.user_id, provider_id=PROVIDER_ID,
        )


def _url_encode(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")


def _tinh_expires_at(expires_in) -> str:
    if not expires_in:
        return ""
    try:
        giay = int(expires_in)
    except (TypeError, ValueError):
        return ""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(seconds=giay)).isoformat(timespec="seconds")
