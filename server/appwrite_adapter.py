"""
Adapter Appwrite that cho Auth va metadata.

Goi qua REST API cua Appwrite bang `httpx` - khong them SDK nang.

NGUYEN TAC:
- API key CHI song o backend. Frontend khong bao gio thay no.
- Cau hinh sai KHONG duoc am tham lui ve mock: nem `AppwriteConfigError` de
  nguoi van hanh biet ngay.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from server.adapters import AuthError
from server.config import AppwriteSettings
from server.domain import Profile, Tier

#: Ten collection tuong ung voi schema trong docs/APPWRITE_SCHEMA.md
COLLECTION_PROFILES = "profiles"
COLLECTION_NOVELS = "novels"
COLLECTION_CHAPTERS = "chapters"
COLLECTION_TTS_JOBS = "tts_jobs"
COLLECTION_AUDIO_TRACKS = "audio_tracks"

REQUEST_TIMEOUT = 15.0


class AppwriteConfigError(RuntimeError):
    """Cau hinh Appwrite thieu hoac sai - bao ro thay vi im lang dung mock."""


def profile_permissions(user_id: str) -> list:
    """
    Quyen tren document `profiles`: CHI DOC, va chi cho chinh chu ho so.

    KHONG cap `update`/`delete` cho nguoi dung. `profiles` chua cac truong do
    SERVER quyet dinh - `tier`, `listened_minutes`, `tts_characters_used` va
    cac bo dem quota sau nay. Nguoi dung nam session/JWT hop le co the goi
    thang Appwrite API ngoai giao dien; neu con quyen `update` thi ho tu nang
    goi cua minh duoc.

    Moi thay doi cac truong nay di qua backend bang API key, ma API key thi
    bo qua document permission - nen bo `update`/`delete` khong lam hong chuc
    nang nao.

    Van giu `read` de nguoi dung doc duoc ho so cua chinh minh. Neu sau nay
    can sua ten hien thi / avatar thi phai lam qua route cua backend voi
    danh sach truong duoc phep - khong bao gio cap quyen ghi thang.
    """
    return [f'read("user:{user_id}")']


class AppwriteIdentityAdapter:
    """Auth bang email/password qua Appwrite."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings):
        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ. Cần cả bốn biến: APPWRITE_ENDPOINT, "
                "APPWRITE_PROJECT_ID, APPWRITE_API_KEY, APPWRITE_DATABASE_ID."
            )
        endpoint = settings.endpoint.rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise AppwriteConfigError(
                f"APPWRITE_ENDPOINT phải bắt đầu bằng http:// hoặc https:// (nhận được: {endpoint!r})."
            )
        self._settings = settings
        # `api_base` da bo `/v1` o cuoi neu co - moi path duoi day tu them `/v1`
        self._endpoint = settings.api_base

    # -- ha tang --------------------------------------------------------------

    def _headers(self, *, admin: bool = True, session: str = "") -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
        }
        if session:
            # Session secret cua NGUOI DUNG. Khong bao gio gui kem API key -
            # request nay phai chay voi dung quyen cua nguoi dung do.
            headers["X-Appwrite-Session"] = session
        elif admin:
            # API key CHI dung o phia server
            headers["X-Appwrite-Key"] = self._settings.api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        session: str = "",
        admin: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        try:
            # Client MOI moi lan, khong giu cookie: neu cookie phien truoc con
            # sot lai, Appwrite se tra 403 "JWT and cookie used in the same
            # request", va te hon la request co the chay bang danh tinh cu.
            with httpx.Client(timeout=REQUEST_TIMEOUT, cookies=None) as client:
                response = client.request(
                    method, url, json=payload,
                    headers=self._headers(admin=admin, session=session),
                )
        except httpx.HTTPError as exc:
            raise AuthError(f"Không kết nối được Appwrite: {exc}") from exc

        if response.status_code >= 400:
            message = f"Appwrite trả về lỗi {response.status_code}."
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("message"):
                    message = str(body["message"])
            except Exception:
                pass
            if response.status_code in (401, 403):
                raise AuthError(message)
            raise AuthError(message)

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # -- API ------------------------------------------------------------------

    def register(self, email: str, password: str, display_name: str = "") -> Profile:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise AuthError("Email không hợp lệ.")
        if len(password or "") < 8:
            raise AuthError("Mật khẩu phải có ít nhất 8 ký tự.")

        data = self._request(
            "POST",
            "/v1/users",
            payload={
                "userId": "unique()",
                "email": email,
                "password": password,
                "name": display_name or email.split("@")[0],
            },
        )
        user_id = str(data.get("$id") or "")
        if not user_id:
            raise AuthError("Appwrite không trả về userId.")

        profile = Profile(
            user_id=user_id,
            email=email,
            display_name=display_name or email.split("@")[0],
            tier=Tier.FREE,
        )
        self._request(
            "POST",
            f"/v1/databases/{self._settings.database_id}/collections/{COLLECTION_PROFILES}/documents",
            payload={
                "documentId": user_id,
                "data": profile.to_dict(),
                "permissions": profile_permissions(user_id),
            },
        )
        return profile

    def login(self, email: str, password: str) -> str:
        """
        Dang nhap, tra ve SESSION SECRET.

        Phai goi KEM API key (`admin=True`, mac dinh). Da kiem chung tren
        Appwrite that: goi khong kem key thi Appwrite tra ve session nhung
        truong `secret` RONG - no dat cookie thay vi tra secret. Backend khong
        dung cookie nen phai lay secret theo duong server-side nay.

        TUYET DOI khong fallback sang `$id`: do la ma dinh danh phien, khong
        phai credential, va Appwrite se tu choi no o moi request sau.
        """
        data = self._request(
            "POST",
            "/v1/account/sessions/email",
            payload={"email": (email or "").strip().lower(), "password": password},
        )
        secret = str(data.get("secret") or "")
        if not secret:
            raise AuthError("Appwrite không trả về session secret.")
        return secret

    def logout(self, token: str) -> bool:
        """
        Xoa phien hien tai o phia Appwrite. Xem contract o `IdentityAdapter`.

        `token` la SESSION SECRET, nen huy duoc that su — khac JWT von chi het
        han theo thoi gian. Gui bang header `X-Appwrite-Session` va `admin=False`,
        dung nhu `profile_from_token`: chinh phien do tu xoa minh.

        IDEMPOTENT. Token da het han hoac rac thi Appwrite tra 401; day khong
        phai loi can bao cho nguoi dung — ket qua mong muon (phien khong con
        dung duoc) da dat roi. Chi nuot DUNG truong hop do, moi loi khac van
        nem len.
        """
        token = (token or "").strip()
        if not token:
            return False
        try:
            self._request("DELETE", "/v1/account/sessions/current",
                          session=token, admin=False)
            return True
        except AuthError:
            # Phien khong con hop le -> muc tieu da dat. Khong nuot loi mang:
            # `_request` bao loi ket noi cung bang AuthError, nhung ca hai
            # truong hop nguoi dung deu nen duoc coi la da dang xuat o client,
            # va route se van xoa token phia trinh duyet.
            return False

    def profile_from_token(self, token: str) -> Profile:
        """
        Xac minh session secret voi Appwrite va lay danh tinh tu ket qua.

        Dung header `X-Appwrite-Session`, KHONG phai `X-Appwrite-JWT`: session
        secret khong phai JWT, Appwrite tra loi "Invalid token: Incomplete
        segments" neu gui nham cho.

        Danh tinh LUON lay tu phan hoi cua Appwrite, khong bao gio tu client.
        """
        data = self._request(
            "GET", "/v1/account", session=(token or "").strip(), admin=False
        )
        user_id = str(data.get("$id") or "")
        if not user_id:
            raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
        return Profile(
            user_id=user_id,
            email=str(data.get("email") or ""),
            display_name=str(data.get("name") or ""),
            tier=Tier.FREE,
        )

    # -- OAuth ----------------------------------------------------------------

    def oauth_start_url(self, provider: str, success: str, failure: str) -> str:
        """
        Xem contract o `IdentityAdapter.oauth_start_url`.

        Dung LUONG TOKEN (`/v1/account/tokens/oauth2/...`), khong phai luong
        session. Khac biet quan trong: luong session ket thuc bang mot COOKIE
        tren ten mien Appwrite, ma backend nay khong dung cookie va frontend
        thi o ten mien khac. Luong token thi tra ve `userId` + `secret` tren
        URL callback, va backend doi chung lay session secret — dung loai token
        ma `login()` da tra ve.

        `project` di o QUERY chu khong o header: buoc nay la mot lan dieu huong
        cua trinh duyet, va trinh duyet thi khong gan header cua ta duoc.
        """
        query = urlencode({
            "project": self._settings.project_id,
            "success": success,
            "failure": failure,
        })
        return f"{self._endpoint}/v1/account/tokens/oauth2/{provider}?{query}"

    def exchange_oauth_token(self, user_id: str, secret: str) -> str:
        """
        Xem contract o `IdentityAdapter.exchange_oauth_token`.

        Goi KEM API key (`admin=True`), cung ly do nhu `login()`: khong kem key
        thi Appwrite dat cookie va tra ve `secret` RONG.
        """
        user_id = (user_id or "").strip()
        secret = (secret or "").strip()
        if not user_id or not secret:
            raise AuthError("Thiếu thông tin đăng nhập từ nhà cung cấp.")
        try:
            data = self._request(
                "POST",
                "/v1/account/sessions/token",
                payload={"userId": user_id, "secret": secret},
            )
        except AuthError as exc:
            # KHONG chuyen tiep thong diep goc cua Appwrite. No co the nhac lai
            # tham so vua gui — tuc la chinh cai secret — va thong diep loi thi
            # di thang ra trinh duyet va vao log.
            raise AuthError(
                "Đăng nhập bằng nhà cung cấp không thành công. Vui lòng thử lại."
            ) from exc
        session_secret = str(data.get("secret") or "")
        if not session_secret:
            raise AuthError("Appwrite không trả về session secret.")
        return session_secret

    def ensure_profile(self, profile: Profile) -> Profile:
        """
        Xem contract o `IdentityAdapter.ensure_profile`. TIM-HOAC-TAO.

        Doc truoc roi moi ghi, va KHONG bao gio `PATCH`: ho so da co phai tra
        ve nguyen ven. Nguoi dung doi ten hien thi trong Fanfic roi sau do dang
        nhap bang Google khong duoc bi Google dat lai ten ho.
        """
        path = (f"/v1/databases/{self._settings.database_id}"
                f"/collections/{COLLECTION_PROFILES}/documents/{profile.user_id}")
        try:
            self._request("GET", path)
            return profile
        except AuthError:
            # Chua co -> tao. `_request` bien MOI loi >=400 thanh AuthError, nen
            # o day khong phan biet duoc 404 voi loi khac; buoc tao ngay duoi se
            # nem tiep neu that su hong.
            pass
        self._request(
            "POST",
            (f"/v1/databases/{self._settings.database_id}"
             f"/collections/{COLLECTION_PROFILES}/documents"),
            payload={
                "documentId": profile.user_id,
                # CUNG schema va cung gia tri mac dinh voi dang ky thuong —
                # khong co bang rieng cho nguoi dung OAuth.
                "data": profile.to_dict(),
                "permissions": profile_permissions(profile.user_id),
            },
        )
        return profile

    def healthcheck(self) -> bool:
        """Kiem tra cau hinh co dung khong. Loi thi nem ra, khong nuot."""
        self._request("GET", "/v1/health")
        return True
