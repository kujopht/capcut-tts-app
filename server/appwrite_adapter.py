"""
Adapter Appwrite that cho Auth va metadata.

Goi qua REST API cua Appwrite bang `httpx` - khong them SDK nang.

NGUYEN TAC:
- API key CHI song o backend. Frontend khong bao gio thay no.
- Cau hinh sai KHONG duoc am tham lui ve mock: nem `AppwriteConfigError` de
  nguoi van hanh biet ngay.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from server.adapters import AuthError
from server.appwrite_store import (
    q_contains as _q_contains,
    q_equal as _q_equal,
    q_greater_equal as _q_greater_equal,
    q_limit as _q_limit,
    q_offset as _q_offset,
    q_or as _q_or,
    q_order_asc as _q_order_asc,
    q_order_desc as _q_order_desc,
)
from server.config import AppwriteSettings
from server.secret_redaction import thong_diep_loi_an_toan
from server.domain import AccountSession, AccountStatus, AuthorStatus, Profile, Tier

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
        #: Ten thuoc tinh that su co trong `profiles`, hoi mot lan roi nho. `None`
        #: = chua hoi. Xem `_profile_attributes`.
        self._profile_attrs: Optional[set] = None
        #: Client dung lai. Xem `_http`.
        self._client: Optional[httpx.Client] = None

    # -- ha tang --------------------------------------------------------------

    def _http(self) -> httpx.Client:
        """MOT client dung lai — xem ghi chu trong `_request`."""
        if self._client is None:
            self._client = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._client

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
        params: Optional[Dict[str, Any]] = None,
        session: str = "",
        admin: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        try:
            client = self._http()
            # KHONG giu cookie giua cac request: neu cookie phien truoc con sot
            # lai, Appwrite tra 403 "JWT and cookie used in the same request",
            # va te hon la request co the chay bang danh tinh cu.
            #
            # Truoc day dieu nay duoc bao dam bang cach tao MOT CLIENT MOI moi
            # lan — dung, nhung ton 1.5-2.0 giay bat tay TLS moi lan goi (do
            # duoc tren staging). Xoa cookie tren mot client dung lai giu nguyen
            # bao dam do va lay lai keep-alive.
            client.cookies.clear()
            response = client.request(
                method, url, json=payload, params=params,
                headers=self._headers(admin=admin, session=session),
            )
        except httpx.HTTPError as exc:
            raise AuthError(f"Không kết nối được Appwrite: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            message = thong_diep_loi_an_toan(body, status_code=response.status_code)
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
                # LOC truong, y het `ensure_profile`. `to_dict()` gio kem ca
                # `username`/`bio`/`author_status`, va ba thuoc tinh do co the
                # CHUA ton tai trong Appwrite neu migration V2 chua chay — gui
                # mot thuoc tinh chua co thi Appwrite tu choi CA document, tuc la
                # KHONG DANG KY DUOC NUA.
                #
                # Duong nay tung bi bo sot: `ensure_profile` (dang ky bang
                # Google) da duoc loc, con `register` (dang ky bang email) thi
                # chua. Hai duong tao ho so phai di qua cung mot bo loc.
                "data": self._writable_profile(profile),
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
        return self._merge_stored(Profile(
            user_id=user_id,
            email=str(data.get("email") or ""),
            display_name=str(data.get("name") or ""),
            tier=Tier.FREE,
        ))

    def _merge_stored(self, profile: Profile) -> Profile:
        """
        Ghep `username` / `bio` / `author_status` / `avatar_key` / cac truong
        "tiep tuc doc/nghe" tu hang `profiles` vao.

        VI SAO CAN: `/v1/account` cua Appwrite chi biet email va ten — no khong
        biet gi ve ba truong V2. Khong ghep thi moi request tra ve mot ho so
        `author_status = "none"`, va toan bo he thong tac gia vo hinh o che do
        Appwrite du du lieu da nam dung trong bang.

        HONG THI BO QUA: bang chua co ba thuoc tinh (migration chua chay), mang
        loi, hay khong du quyen — tat ca deu tra ve ho so goc. Mot tinh nang
        khong hien con hon mot duong dang nhap bi chan.
        """
        try:
            row = self._request("GET", self._profile_path(profile.user_id))
        except Exception:
            return profile
        profile.username = str(row.get("username") or "")
        profile.bio = str(row.get("bio") or "")
        try:
            profile.author_status = AuthorStatus(row.get("author_status") or "none")
        except ValueError:
            profile.author_status = AuthorStatus.NONE
        profile.avatar_key = str(row.get("avatar_key") or "")
        profile.last_read_novel_id = str(row.get("last_read_novel_id") or "")
        profile.last_read_chapter_id = str(row.get("last_read_chapter_id") or "")
        profile.last_read_at = str(row.get("last_read_at") or "")
        profile.last_listen_novel_id = str(row.get("last_listen_novel_id") or "")
        profile.last_listen_chapter_id = str(row.get("last_listen_chapter_id") or "")
        profile.last_listen_position_seconds = float(
            row.get("last_listen_position_seconds") or 0.0)
        profile.last_listen_at = str(row.get("last_listen_at") or "")
        profile.last_watch_series_id = str(row.get("last_watch_series_id") or "")
        profile.last_watch_episode_id = str(row.get("last_watch_episode_id") or "")
        profile.last_watch_position_seconds = float(
            row.get("last_watch_position_seconds") or 0.0)
        profile.last_watch_duration_seconds = float(
            row.get("last_watch_duration_seconds") or 0.0)
        profile.last_watch_at = str(row.get("last_watch_at") or "")
        return profile

    def _profile_path(self, user_id: str) -> str:
        return (f"/v1/databases/{self._settings.database_id}"
                f"/collections/{COLLECTION_PROFILES}/documents/{user_id}")

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
        path = self._profile_path(profile.user_id)
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
                #
                # LOC truong: `to_dict()` gio kem ca `username`/`bio`/
                # `author_status`, va ba thuoc tinh do co the CHUA ton tai trong
                # Appwrite neu migration V2 chua chay. Gui mot thuoc tinh chua co
                # thi Appwrite tu choi CA document — tuc la khong dang ky duoc
                # nua. Cung ly do va cung cach lam nhu `_supported_fields` o
                # `appwrite_store.py`.
                "data": self._writable_profile(profile),
                "permissions": profile_permissions(profile.user_id),
            },
        )
        return profile

    #: Thuoc tinh cua `profiles` da co tu ban dau. Ba truong V2 nam ngoai tap
    #: nay va chi duoc gui khi Appwrite bao la no co.
    _PROFILE_BASE_FIELDS = (
        "user_id", "email", "display_name", "tier",
        "listened_minutes", "tts_characters_used", "created_at",
    )
    _PROFILE_V2_FIELDS = (
        "username", "bio", "author_status", "avatar_key",
        # "Tiep tuc doc/nghe" (V4 visual completion) — them SAU, cung co che
        # dong-thieu-thi-bo-qua nay: chua chay schema thi tinh nang chi an,
        # khong lam vo dang ky/cap nhat ho so.
        "last_read_novel_id", "last_read_chapter_id", "last_read_at",
        "last_listen_novel_id", "last_listen_chapter_id",
        "last_listen_position_seconds", "last_listen_at",
        # "Tiep tuc xem" (V6, overnight Phase 5) — them SAU, cung co che
        # dong-thieu-thi-bo-qua nay.
        "last_watch_series_id", "last_watch_episode_id",
        "last_watch_position_seconds", "last_watch_duration_seconds",
        "last_watch_at",
    )

    #: Truong co INDEX UNIQUE. Chuoi rong KHONG duoc ghi vao day.
    #:
    #: LOI DA XAY RA TREN STAGING: `register()` ghi `username: ""` cho moi ho so
    #: moi. Index `username_unique` coi hai chuoi rong la TRUNG NHAU, nen nguoi
    #: thu HAI dang ky nhan 409 va khong co hang ho so nao — Auth co 7 user, bang
    #: `profiles` chi co 2 hang. Loi nay khong the lo ra o kho mock, va no chan
    #: dung buoc dang ky.
    #:
    #: Bo han khoa khi gia tri rong thi cot la NULL, va index unique cua Appwrite
    #: cho phep nhieu NULL.
    _PROFILE_UNIQUE_FIELDS = ("username",)

    def _writable_profile(self, profile: Profile) -> Dict[str, Any]:
        data = profile.to_dict()
        co = self._profile_attributes()
        ra = {k: data[k] for k in self._PROFILE_BASE_FIELDS if k in data}
        for k in self._PROFILE_V2_FIELDS:
            # `co is None` = khong hoi duoc schema. Luc do BO QUA ba truong moi:
            # gui bua vao co the lam vo ca buoc tao ho so.
            if co is None or k not in co:
                continue
            if k in self._PROFILE_UNIQUE_FIELDS and not data[k]:
                # Xem `_PROFILE_UNIQUE_FIELDS`: de NULL, khong de chuoi rong.
                continue
            ra[k] = data[k]
        return ra

    def _profile_attributes(self) -> Optional[set]:
        """Ten thuoc tinh THUC SU co trong `profiles`, hoi Appwrite MOT lan."""
        if self._profile_attrs is not None:
            return self._profile_attrs or None
        try:
            meta = self._request(
                "GET",
                (f"/v1/databases/{self._settings.database_id}"
                 f"/collections/{COLLECTION_PROFILES}"),
            )
        except Exception:
            return None
        ten = {a.get("key") for a in (meta.get("attributes") or []) if a.get("key")}
        self._profile_attrs = ten
        return ten or None

    def save_profile(self, profile: Profile) -> Profile:
        """
        Ghi ba truong V2 cua mot ho so da ton tai.

        `PATCH` chu khong phai `PUT`: chi dat nhung gi minh biet, va khong bao gio
        cham vao `email`/`tier`/quota — do la cac truong ma tang khac quan ly.

        Ba thuoc tinh chua ton tai trong Appwrite thi day la mot phep KHONG-LAM-GI
        (va nem loi de tang tren biet): khong the luu username vao mot cot chua co,
        va lam nhu da luu thanh cong con te hon.
        """
        co = self._profile_attributes()
        data = {k: getattr(profile, k) for k in self._PROFILE_V2_FIELDS
                if co is not None and k in co}
        if "author_status" in data:
            data["author_status"] = profile.author_status.value
        if not data:
            raise AuthError(
                "Chưa thể lưu danh tính công khai: bảng `profiles` còn thiếu các "
                "thuộc tính username/bio/author_status. Cần chạy migration V2."
            )
        if "username" in data and not data["username"]:
            # Cung ly do voi `_writable_profile`: dat lai chuoi rong se dam vao
            # index unique cua nguoi khac cung dang de trong.
            data.pop("username")
        try:
            self._request("PATCH", self._profile_path(profile.user_id),
                          payload={"data": data})
        except AuthError:
            # Hang ho so co the CHUA ton tai: nguoi dung dang nhap bang OAuth
            # truoc khi `ensure_profile` chay, hoac mot lan tao truoc do that bai.
            # Tao lai thay vi de mot thao tac hop le chet vi mot hang thieu.
            self._request(
                "POST",
                (f"/v1/databases/{self._settings.database_id}"
                 f"/collections/{COLLECTION_PROFILES}/documents"),
                payload={
                    "documentId": profile.user_id,
                    "data": self._writable_profile(profile),
                    "permissions": profile_permissions(profile.user_id),
                },
            )
        return profile

    def get_profile(self, user_id: str) -> Profile:
        """Doc ho so tu bang. Dung cho tang service, khong cho duong dang nhap."""
        row = self._request("GET", self._profile_path(user_id))
        profile = Profile(
            user_id=user_id,
            email=str(row.get("email") or ""),
            display_name=str(row.get("display_name") or ""),
        )
        return self._merge_stored(profile)


    # =========================================================== V2: tim ho so
    #
    # Ba ham duoi day doc THANG bang `profiles`, khong qua `/v1/account`:
    # `/v1/account` chi biet ve NGUOI DANG GOI, con o day ta can tim nguoi khac.
    #
    # RIENG TU: cac ham nay tra ve `Profile` DAY DU, ke ca `email`. Chung la
    # nguyen lieu cho CA hai duong — cong khai va quan tri — va viec chieu xuong
    # danh sach cho phep nam o `creator.public_profile()`. Khong bao gio tra
    # thang ket qua cua chung ra API cong khai.

    def profile_by_username(self, username: str) -> Optional[Profile]:
        """
        Tim theo ten cong khai, dang da chuan hoa.

        Tra `None` khi khong co — route se doi thanh 404. Khong phan biet "khong
        ton tai" voi "co nhung chua chon username": phan biet ra thi thanh mot
        cach do xem ai da dang ky.
        """
        ten = (username or "").strip().lower()
        if not ten:
            return None
        rows = self._rows(COLLECTION_PROFILES, [
            _q_equal("username", ten), _q_limit(1),
        ])
        return _profile_from(rows[0]) if rows else None

    def search_profiles(self, query: str, limit: int = 20,
                        offset: int = 0) -> Tuple[List[Profile], int]:
        """
        Tim theo ten hien thi VA username, LOC va PHAN TRANG o phia Appwrite.

        Tai het nguoi dung ve roi loc o Python la vua cham vua khong co tran —
        no hong dan theo so nguoi dung, va hong am tham.

        CHI nguoi da co username: chua chon thi chua co trang cong khai, nen dua
        ho vao ket qua la dan nguoi dung toi mot lien ket khong mo duoc.

        `contains` cua Appwrite khong phan biet hoa/thuong VA khong phan biet dau
        — da kiem chung tren Cloud 1.9.6 — nen tim "ke det" ra "Kẻ Dệt Mộng".
        """
        from server.creator import normalize_username

        queries: List[str] = [_q_not_equal("username", "")]
        tu = (query or "").strip()
        if tu:
            # Hai cach viet cham cung mot o: dang chuan cho `username`, dang tho
            # cho `display_name` (ten hien thi CO dau).
            queries.append(_q_or(
                _q_contains("username", normalize_username(tu)),
                _q_contains("display_name", tu),
            ))
        # Sap TAT DINH: phan trang tren mot thu tu khong on dinh thi trang 2 co
        # the lap lai hoac bo sot ban ghi cua trang 1.
        queries += [_q_order_asc("username"), _q_limit(limit), _q_offset(offset)]
        rows, total = self._page(COLLECTION_PROFILES, queries)
        return [_profile_from(r) for r in rows], total

    def count_profiles(self, created_after: str = "") -> int:
        """
        Tong so ho so, TUY CHON chi tinh tu mot moc thoi gian — dung cho cac o
        "moi dang ky hom nay/7 ngay/30 ngay" o bang dieu khien quan tri (Admin
        Control Center V2, A1). `limit(1)` + doc `total`, KHONG keo ban ghi
        ve — cung idiom voi `total_published_novels`/`count_applications`.
        """
        queries = [_q_limit(1)]
        if created_after:
            queries.insert(0, _q_greater_equal("created_at", created_after))
        return self._page(COLLECTION_PROFILES, queries)[1]

    def all_usernames(self) -> List[str]:
        """
        Cac ten da co, de goi y mot ten chua ai lay.

        Lay TOI DA 500: day chi phuc vu mot goi y o o nhap, va tinh duy nhat that
        su do index `username_unique` cuong che. Keo ca bang ve chi de goi y mot
        cai ten la mot phep doi vo ly.
        """
        rows = self._rows(COLLECTION_PROFILES, [
            _q_not_equal("username", ""), _q_limit(500),
        ])
        return [str(r.get("username")) for r in rows if r.get("username")]

    def profiles_by_ids(self, user_ids: List[str]) -> Dict[str, Profile]:
        """
        Nhieu ho so trong MOT truy van.

        `equal` cua Appwrite nhan NHIEU gia tri va hoat dong nhu `IN`. Truoc day
        khu quan tri goi `get_profile` cho tung hang — mot vong mang moi hang, va
        `/api/admin/author-applications` mat 34 giay cho sau persona tren staging.

        Chia lo 50: URL co tran do dai, va mot truy van voi vai tram id se bi tu
        choi truoc khi toi duoc database.
        """
        ds = [u for u in dict.fromkeys(user_ids) if u]
        ra: Dict[str, Profile] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            rows = self._rows(COLLECTION_PROFILES, [
                _q_equal("user_id", *lo), _q_limit(len(lo)),
            ])
            for row in rows:
                pf = _profile_from(row)
                if pf.user_id:
                    ra[pf.user_id] = pf
        return ra

    # =========================================================== V3: tai khoan
    #
    # Goi THANG Appwrite Users API (`/v1/users*`), KHONG PHAI bang `profiles`
    # — day la du lieu Auth native (email verification, khoa dang nhap, phien
    # dang nhap), khong co ban sao va khong bao gio nen ghi vao `profiles`.
    # Xem `AccountStatus`/`AccountSession` (server/domain.py) va muc "Kien
    # truc bao mat quan tri" trong handoff Phase 3.

    def list_accounts(self, query: str = "", limit: int = 25,
                      offset: int = 0) -> Tuple[List[AccountStatus], int]:
        """
        Danh sach TAI KHOAN, phan trang o phia Appwrite — nguon cho
        `/api/admin/users` (Phase 3), thay cho `search_profiles` cu (chi thay
        nguoi da chon username).

        `search` la THAM SO RIENG cua Appwrite cho `/v1/users` (khac voi
        `contains`/`search()` trong queries[] cua Databases) — no tim toan
        van tren name/email/phone do Appwrite tu quan ly index, KHONG can
        index fulltext tu cau hinh nhu ben `profiles`.
        """
        params: Dict[str, Any] = {
            "queries[]": [_q_order_desc("registration"), _q_limit(limit),
                         _q_offset(offset)],
        }
        tu = (query or "").strip()
        if tu:
            params["search"] = tu
        data = self._request("GET", "/v1/users", params=params)
        rows = list(data.get("users") or [])
        total = data.get("total")
        return ([_account_from(r) for r in rows],
                int(total) if isinstance(total, int) else len(rows))

    def account_status(self, user_id: str) -> Optional[AccountStatus]:
        try:
            row = self._request("GET", f"/v1/users/{user_id}")
        except AuthError:
            # `_request` khong giu status code goc (xem ghi chu o `ensure_profile`
            # ve cung han che nay) — khong the tach 404 khoi loi khac o day,
            # nen coi MOI loi la "khong tim thay". Cac route goi ham nay chi
            # dung no de doi ra 404, khong dua vao de phat hien su co ha tang.
            return None
        return _account_from(row)

    def list_sessions(self, user_id: str) -> List[AccountSession]:
        data = self._request("GET", f"/v1/users/{user_id}/sessions")
        return [_session_from(s) for s in (data.get("sessions") or [])]

    def terminate_session(self, user_id: str, session_id: str) -> bool:
        """IDEMPOTENT, cung tinh than voi `logout`: phien von da mat thi coi
        nhu muc tieu da dat, khong nem loi."""
        try:
            self._request("DELETE", f"/v1/users/{user_id}/sessions/{session_id}")
            return True
        except AuthError:
            return False

    def terminate_all_sessions(self, user_id: str) -> int:
        """
        Appwrite tra `204 No Content` cho lenh xoa hang loat — khong biet da
        xoa BAO NHIEU tu chinh response do. Dem TRUOC roi moi xoa.
        """
        phien = self.list_sessions(user_id)
        if not phien:
            return 0
        self._request("DELETE", f"/v1/users/{user_id}/sessions")
        return len(phien)

    def set_account_enabled(self, user_id: str, enabled: bool) -> Optional[AccountStatus]:
        try:
            row = self._request("PATCH", f"/v1/users/{user_id}/status",
                                payload={"status": enabled})
        except AuthError:
            return None
        return _account_from(row)

    def count_accounts(self, *, email_verified: Optional[bool] = None,
                       enabled: Optional[bool] = None) -> int:
        queries: List[str] = [_q_limit(1)]
        if email_verified is not None:
            queries.append(_q_equal("emailVerification", email_verified))
        if enabled is not None:
            queries.append(_q_equal("status", enabled))
        data = self._request("GET", "/v1/users", params={"queries[]": queries})
        total = data.get("total")
        return int(total) if isinstance(total, int) else 0

    # -- ha tang truy van ----------------------------------------------------

    def _rows(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        return self._page(collection, queries)[0]

    def _page(self, collection: str,
              queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        data = self._request(
            "GET",
            f"/v1/databases/{self._settings.database_id}"
            f"/collections/{collection}/documents",
            params={"queries[]": queries},
        )
        docs = list(data.get("documents") or [])
        total = data.get("total")
        return docs, int(total) if isinstance(total, int) else len(docs)

    def healthcheck(self) -> bool:
        """Kiem tra cau hinh co dung khong. Loi thi nem ra, khong nuot."""
        self._request("GET", "/v1/health")
        return True


def _q_not_equal(attribute: str, value: Any) -> str:
    """
    Khac gia tri. Dung de loai cac ho so CHUA chon username.

    Kho chua can toi phep nay nen no nam o day; neu sau co cho thu hai dung, hay
    chuyen no sang `appwrite_store` cung cac ham truy van khac thay vi nhan ban.
    """
    import json

    return json.dumps({"method": "notEqual", "attribute": attribute,
                       "values": [value]})


def _profile_from(row: Dict[str, Any]) -> Profile:
    """
    Hang `profiles` -> ban ghi domain.

    Tra ve ban DAY DU, ke ca `email`: day la nguyen lieu cho ca duong cong khai
    lan duong quan tri, va phep chieu xuong danh sach cho phep nam o
    `creator.public_profile()`. Mot ham doc kho khong phai cho quyet dinh cai gi
    duoc lo ra.
    """
    try:
        status = AuthorStatus(row.get("author_status") or "none")
    except ValueError:
        status = AuthorStatus.NONE
    return Profile(
        user_id=str(row.get("user_id") or row.get("") or ""),
        email=str(row.get("email") or ""),
        display_name=str(row.get("display_name") or ""),
        tier=Tier.FREE,
        listened_minutes=int(row.get("listened_minutes") or 0),
        tts_characters_used=int(row.get("tts_characters_used") or 0),
        created_at=str(row.get("created_at") or ""),
        username=str(row.get("username") or ""),
        bio=str(row.get("bio") or ""),
        author_status=status,
        avatar_key=str(row.get("avatar_key") or ""),
        last_read_novel_id=str(row.get("last_read_novel_id") or ""),
        last_read_chapter_id=str(row.get("last_read_chapter_id") or ""),
        last_read_at=str(row.get("last_read_at") or ""),
        last_listen_novel_id=str(row.get("last_listen_novel_id") or ""),
        last_listen_chapter_id=str(row.get("last_listen_chapter_id") or ""),
        last_listen_position_seconds=float(
            row.get("last_listen_position_seconds") or 0.0),
        last_listen_at=str(row.get("last_listen_at") or ""),
        last_watch_series_id=str(row.get("last_watch_series_id") or ""),
        last_watch_episode_id=str(row.get("last_watch_episode_id") or ""),
        last_watch_position_seconds=float(
            row.get("last_watch_position_seconds") or 0.0),
        last_watch_duration_seconds=float(
            row.get("last_watch_duration_seconds") or 0.0),
        last_watch_at=str(row.get("last_watch_at") or ""),
    )


def _account_from(row: Dict[str, Any]) -> AccountStatus:
    """Hang nguoi dung tu Appwrite Users API -> `AccountStatus`. `status` cua
    Appwrite la bool (`True` = con dung duoc) — CHINH la `enabled`."""
    return AccountStatus(
        user_id=str(row.get("$id") or ""),
        email=str(row.get("email") or ""),
        name=str(row.get("name") or ""),
        enabled=bool(row.get("status", True)),
        email_verified=bool(row.get("emailVerification", False)),
        phone_verified=bool(row.get("phoneVerification", False)),
        registered_at=str(row.get("registration") or ""),
    )


def _session_from(row: Dict[str, Any]) -> AccountSession:
    return AccountSession(
        session_id=str(row.get("$id") or ""),
        provider=str(row.get("provider") or ""),
        ip=str(row.get("ip") or ""),
        os_name=str(row.get("osName") or ""),
        client_name=str(row.get("clientName") or ""),
        device_name=str(row.get("deviceName") or ""),
        country_name=str(row.get("countryName") or ""),
        current=bool(row.get("current", False)),
        created_at=str(row.get("$createdAt") or ""),
    )
