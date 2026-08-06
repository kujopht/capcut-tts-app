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
        self._endpoint = endpoint

    # -- ha tang --------------------------------------------------------------

    def _headers(self, *, admin: bool = True, jwt: str = "") -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
        }
        if jwt:
            headers["X-Appwrite-JWT"] = jwt
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
        jwt: str = "",
        admin: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.request(
                    method, url, json=payload, headers=self._headers(admin=admin, jwt=jwt)
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
        # Ghi ho so vao collection profiles; quyen doc/ghi thuoc chinh chu so huu
        self._request(
            "POST",
            f"/v1/databases/{self._settings.database_id}/collections/{COLLECTION_PROFILES}/documents",
            payload={
                "documentId": user_id,
                "data": profile.to_dict(),
                "permissions": [
                    f'read("user:{user_id}")',
                    f'update("user:{user_id}")',
                    f'delete("user:{user_id}")',
                ],
            },
        )
        return profile

    def login(self, email: str, password: str) -> str:
        data = self._request(
            "POST",
            "/v1/account/sessions/email",
            payload={"email": (email or "").strip().lower(), "password": password},
            admin=False,
        )
        secret = str(data.get("secret") or data.get("$id") or "")
        if not secret:
            raise AuthError("Appwrite không trả về phiên đăng nhập.")
        return secret

    def profile_from_token(self, token: str) -> Profile:
        data = self._request("GET", "/v1/account", jwt=(token or "").strip(), admin=False)
        user_id = str(data.get("$id") or "")
        if not user_id:
            raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
        return Profile(
            user_id=user_id,
            email=str(data.get("email") or ""),
            display_name=str(data.get("name") or ""),
            tier=Tier.FREE,
        )

    def healthcheck(self) -> bool:
        """Kiem tra cau hinh co dung khong. Loi thi nem ra, khong nuot."""
        self._request("GET", "/v1/health")
        return True
