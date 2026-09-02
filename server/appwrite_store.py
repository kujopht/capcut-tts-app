"""
Kho metadata tren Appwrite Databases.

Cung giao dien voi `MockMetadataStore` nen `main.py` khong phai biet dang chay
che do nao.

NGUYEN TAC:
- Moi truy van deu kiem tra QUYEN SO HUU o phia server. Khong bao gio tin
  `user_id` do client gui len - chu so huu luon lay tu token da xac minh.
- Document permission duoc gan cho dung chu so huu; truyen da xuat ban moi
  them quyen doc cong khai.
- API key CHI dung o phia server.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from server.adapters import AppwriteUnavailableError, NotFoundError, PermissionDenied, raise_for_appwrite_404
from server.appwrite_social import (
    COL_COMMENTS,
    COL_NOTIFICATIONS,
    COL_POST_LIKES,
    COL_POSTS,
    COL_REPORTS,
    COL_STORY_FOLLOWS,
    COL_USER_FOLLOWS,
    AppwriteSocialStore,
    SOCIAL_PERSISTED_FIELDS,
    _post_from,
)
from server.config import AppwriteSettings
from server.secret_redaction import thong_diep_loi_an_toan
from server.domain import (
    AN_DANH_DA_XOA,
    AuthorApplication,
    AuthorStats,
    AuthorStatus,
    ChineseMediaQueueItem,
    ListenCredit,
    ModerationEvent,
    AudioStamp,
    AudioTrack,
    Chapter,
    JobStatus,
    Novel,
    NovelStatus,
    PublicationMode,
    PublishState,
    TtsJob,
    bao_cao_xoa_tai_khoan,
    now_iso,
)

COL_NOVELS = "novels"
COL_CHAPTERS = "chapters"
COL_JOBS = "tts_jobs"
COL_TRACKS = "audio_tracks"
COL_CLAIMS = "job_claims"
#: Khoa tat dinh chan hai request cung tao mot job. Xem `create_job_once`.
COL_JOB_LOCKS = "job_locks"
#: Chinese Media Watcher foundation (2026-09-02) -- hang doi phat hien/xu ly,
#: doc lap voi novels (chi ghi vao novels luc THAT SU tao duoc draft).
COL_CONTENT_QUEUE = "content_queue"
#: Danh tinh dich vu ghi hang doi nay -- tu dong hoa, khong phai nguoi dung
#: that, cung mau voi `harvester_owner_user_id` ("svc_harvester") o noi khac.
CONTENT_QUEUE_OWNER = "svc_harvester"

#: --- V2: tac gia -----------------------------------------------------------
#: Bon bang moi. Moi bang mot cach dat `rowId` khac nhau, va do la thu quyet
#: dinh tinh dung dan — xem khoi "V2: TAC GIA" o cuoi lop.
COL_APPLICATIONS = "author_applications"
COL_STATS = "author_stats"
COL_CREDITS = "listen_credits"
COL_EVENTS = "moderation_events"

REQUEST_TIMEOUT = 15.0

#: Cum tu XAC MINH THAT (khong doan) tu thong diep Appwrite Cloud khi mot
#: du an het han muc — bat tren staging that, 2026-08-23:
#: "Database reads limit for the current billing cycle has been exceeded.
#: Please upgrade to a higher plan or update your budget cap."
#: Khop THEO CUM TU, khong phai toan bo cau: cau chinh xac co the doi (vi du
#: "writes" thay "reads", hoac Appwrite doi cau chu), nhung ca hai cum deu
#: la dau hieu chac chan cua HET HAN MUC/RATE LIMIT, khong phai ban ghi that
#: su khong ton tai. Them cum moi vao day CHI khi da xac nhan qua phan hoi
#: THAT tu Appwrite — dung mau voi cach `scripts/setup_appwrite.py` khop
#: "already an index with the same attributes and orders".
_CUM_TU_HA_TANG_TAM_THOI = (
    "billing cycle",
    "usage limit",
    "rate limit",
    "too many requests",
)


def _la_loi_ha_tang_tam_thoi(body: Any) -> bool:
    """
    Phan biet "Appwrite tam thoi khong phuc vu duoc" (het han muc/rate limit
    — nen la `AppwriteUnavailableError` -> 503, thu lai duoc) voi "ban ghi
    that su khong ton tai" (nen la `NotFoundError` -> 404, KHONG thu lai
    duoc, vi thu lai se tra ve dung ket qua do).

    CHI doc `message` — cung truong `thong_diep_loi_an_toan` uu tien, va la
    truong DUY NHAT da xac nhan chua cum tu can tim trong phan hoi Appwrite
    THAT (xem hang so o tren).
    """
    if not isinstance(body, dict):
        return False
    message = str(body.get("message") or "").lower()
    return any(cum in message for cum in _CUM_TU_HA_TANG_TAM_THOI)


def _job_lock_id(owner_id: str, chapter_id: str, fingerprint: str) -> str:
    """
    `rowId` TAT DINH cho hang khoa cua mot job.

    Bam thay vi noi chuoi: Appwrite gioi han do dai `rowId` (36 ky tu) va cam
    mot so ky tu, con ba dau vao gop lai thi dai hon nhieu.

    Chi de CHONG TRUNG, khong phai de bao mat.
    """
    import hashlib

    thong = f"{owner_id}{chapter_id}{fingerprint}".encode()
    return "lock" + hashlib.sha256(thong).hexdigest()[:28]

#: Appwrite chi nhan `ttl` trong khoang 60..3600 giay — da do that.
TRANSACTION_TTL_SECONDS = 60

#: Thuoc tinh THUC SU ton tai trong schema Appwrite (xem docs/APPWRITE_SCHEMA.md
#: va scripts/setup_appwrite.py).
#:
#: `to_dict()` cua tang domain la hinh dang cua API, khong phai hinh dang luu
#: tru: no kem ca cac truong TINH TOAN (`char_count` cua Chapter, `progress`
#: cua TtsJob) ma frontend can. Gui thang len Appwrite thi bi tu choi:
#:     Invalid document structure: Unknown attribute: "char_count"
#: Loc o day de hai hinh dang do tach bach han.
PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_NOVELS: (
        "novel_id", "owner_id", "title", "description", "cover_key",
        "state", "tags", "created_at", "updated_at",
        # Anime Fanfic Production Canary: fandom + provenance nguon ngoai.
        "publication_mode", "fandom_ids", "external_author_name",
        "external_source_url", "external_chapter_count",
        "external_updated_at", "language",
        "characters", "pairings", "status",
        # Video draft fields (mission "SHIP 3 CHINESE AI-ANIMATION VIDEO
        # DRAFTS", 2026-09-01) — see Novel's own docstring. `_supported_fields`
        # drops these automatically until the Appwrite migration adding them
        # actually runs, same recovery-field pattern as COL_JOBS above.
        "platform", "rights_mode", "subtitle_status", "embed_ref",
        # Chinese Media Watcher foundation (2026-09-02) — same recovery-field
        # pattern: dropped by `_supported_fields` until the migration runs.
        "subtitle_key", "dub_audio_key",
    ),
    COL_CHAPTERS: (
        "chapter_id", "novel_id", "owner_id", "title", "content",
        "order_index", "state", "created_at", "updated_at",
    ),
    COL_CONTENT_QUEUE: (
        "item_id", "source_id", "platform", "series_slug", "episode_ref",
        "title", "source_url", "discovered_at", "rights_mode",
        "transcript_state", "translation_state", "subtitle_state",
        "dub_state", "render_state", "draft_state", "novel_id",
        "transcript_key", "attempts", "last_error", "updated_at", "created_at",
    ),
    COL_JOBS: (
        "job_id", "owner_id", "chapter_id", "voice_id", "content_hash",
        "status", "output_key", "error_kind", "error_message",
        "total_parts", "done_parts", "rate", "chunk_chars",
        # Ba truong recovery. Chung co the CHUA ton tai trong Appwrite neu
        # migration chua chay — xem `_supported_fields`, code tu bo chung ra
        # thay vi lam vo viec tao audio.
        "lease_expires_at", "lease_owner", "attempts",
        "created_at", "started_at", "finished_at",
    ),
    COL_TRACKS: (
        "track_id", "chapter_id", "owner_id", "voice_id", "object_key",
        "content_hash", "duration_seconds", "size_bytes", "created_at",
        # Phu de dong bo (V4, Phan 2H) — additive, xem `AudioTrack` va
        # `scripts/setup_appwrite.py`. `_supported_fields` tu bo qua ba truong
        # nay neu migration Appwrite chua chay, cung co che voi ba truong
        # recovery cua `tts_jobs` o tren.
        "transcript_key", "transcript_version", "source_content_hash",
    ),
    COL_APPLICATIONS: (
        "application_id", "user_id", "pen_name", "bio", "genres", "intro",
        "accepted_rules", "status", "reviewer_note", "attempts",
        "created_at", "updated_at", "decided_at",
    ),
    COL_STATS: (
        "user_id", "qualified_listens", "published_novels", "updated_at",
    ),
    COL_CREDITS: (
        "credit_id", "listener_id", "author_id", "chapter_id", "day_bucket",
        "listened_seconds", "created_at",
    ),
    COL_EVENTS: (
        "event_id", "action", "target_user_id", "actor_id", "actor_role",
        "target_type", "target_id", "note", "metadata", "created_at",
    ),
}

#: Bay bang cua tang xa hoi. Khai o `server/appwrite_social.py` de danh sach
#: thuoc tinh nam CANH ma doi hang cua chinh chung — hai thu do luon phai doi
#: cung nhau, va de chung o hai tep khac nhau la moi mot lan quen.
PERSISTED_FIELDS.update(SOCIAL_PERSISTED_FIELDS)


def _theo_lo(items, co=50):
    """
    Chia thanh cac lo nho. URL cua Appwrite co tran do dai, va mot truy van
     voi vai tram gia tri se bi tu choi TRUOC khi toi duoc database.

    50 la con so an toan cho id 20-24 ky tu; mot trang quan tri 25 hang chi can
    dung MOT lo.
    """
    for i in range(0, len(items), co):
        yield items[i:i + co]


def _application_from(row: Dict[str, Any]) -> "AuthorApplication":
    """Hang Appwrite -> ban ghi domain. Mot cho duy nhat lam phep doi nay."""
    from server.domain import AuthorApplication, AuthorStatus

    try:
        status = AuthorStatus(row.get("status") or "pending")
    except ValueError:
        status = AuthorStatus.PENDING
    return AuthorApplication(
        user_id=str(row.get("user_id") or ""),
        pen_name=str(row.get("pen_name") or ""),
        bio=str(row.get("bio") or ""),
        genres=list(row.get("genres") or []),
        intro=str(row.get("intro") or ""),
        accepted_rules=bool(row.get("accepted_rules")),
        status=status,
        reviewer_note=str(row.get("reviewer_note") or ""),
        attempts=int(row.get("attempts") or 1),
        application_id=str(row.get("application_id") or row.get("$id") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        decided_at=row.get("decided_at") or None,
    )


# -----------------------------------------------------------------------------
# Query
# -----------------------------------------------------------------------------
#
# Appwrite tu ban 1.5 CHI nhan query dang JSON, gui qua tham so `queries[]`.
# Cu phap chuoi cu (`equal("owner_id", ["x"])`) bi tra ve 400:
#     Invalid query: Syntax error
# Da kiem chung tren Appwrite Cloud 1.9.6.
#
# Ma hoa bang `json.dumps` con loai bo luon nguy co QUERY INJECTION: truoc day
# gia tri duoc noi suy thang vao chuoi, mot `owner_id` chua dau nháy co the pha
# vo cau truc query.


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_greater_equal(attribute: str, value: Any) -> str:
    """
    `attribute >= value` — dung cho khoang thoi gian (vd `created_at >=` mot
    moc ISO) khi dem "moi dang ky hom nay/7 ngay/30 ngay" (Admin Control
    Center V2, A1) MA KHONG can keo ban ghi ve — ket hop `q_limit(1)` de doc
    `total` nhu cac phep dem bi chan khac trong tep nay.

    TEN PHUONG THUC THAT cua Appwrite la `greaterThanEqual`, KHONG PHAI
    `greaterEqual` — da doan sai va bi Appwrite tu choi ("Invalid query
    method: greaterEqual") khi smoke test that tren appwrite-dev.fanfic.world,
    khong phai chi tu tai lieu.
    """
    return json.dumps({"method": "greaterThanEqual", "attribute": attribute,
                       "values": [value]})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def q_contains(attribute: str, value: Any) -> Dict[str, Any]:
    """
    Chua chuoi con, hoac mang co chua phan tu.

    Da kiem chung tren Appwrite Cloud 1.9.6:
    - `equal` tren thuoc tinh MANG (nhu `tags`) bi tu choi:
      'Cannot query equal on attribute "tags" because it is an array' — phai
      dung `contains`.
    - `search` doi INDEX FULLTEXT: 'Searching by attribute "title" requires a
      fulltext index' — schema hien tai khong co, nen cung dung `contains`.
    - `contains` khong phan biet hoa/thuong VA khong phan biet dau: tim "tac"
      ra "Hải Tặc". Rat tien cho tieng Viet.

    Tra ve DICT chu khong phai chuoi JSON, de con long vao `q_or` duoc.
    """
    return {"method": "contains", "attribute": attribute, "values": [value]}


def q_or(*conditions: Dict[str, Any]) -> str:
    """
    Thoa MOT trong cac dieu kien.

    Cac dieu kien phai long vao duoi dang DOI TUONG. Long dang chuoi JSON thi
    Appwrite tra 'Server Error' — da gap that khi chay.

    MOT dieu kien thi tra ve CHINH dieu kien do, khong boc `or`: Appwrite that
    tu choi 'Or queries require at least two queries' — do duoc tren staging,
    o dung truy van tim bai dang dau tien. Nguoi goi thuong xay danh sach dieu
    kien dong (mot tu khoa -> mot `contains`), va bat ho tu dem so dieu kien
    truoc khi chon ham la giao cho moi cho goi mot viec de quen.
    """
    if len(conditions) == 1:
        return json.dumps(conditions[0])
    return json.dumps({"method": "or", "values": list(conditions)})


def q_select(*attributes: str) -> str:
    """
    Chi lay ve nhung thuoc tinh can dung, cho nhe duong truyen.

    Danh sach thuoc tinh di trong `values`, KHONG phai `attributes` — dat sai
    khoa thi Appwrite tra ve 'Invalid query: No attributes selected'. Da gap
    that khi chay tren Appwrite Cloud 1.9.6.
    """
    return json.dumps({"method": "select", "values": list(attributes)})


#: `equal` nhan mot mang gia tri, tuc la mot truy van IN. Appwrite gioi han do
#: dai moi truy van, nen hoi theo lo thay vi nhoi ca nghin id vao mot lan.
BATCH_IDS = 50

#: So document toi da moi trang. Appwrite mac dinh chi tra 25 — khong dat tay
#: thi mot truyen tren 25 chuong se bi cat am tham.
PAGE_SIZE = 100


def persistable(collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Chi giu lai nhung truong that su co trong schema cua collection do."""
    allowed = PERSISTED_FIELDS.get(collection)
    if allowed is None:
        return dict(data)
    return {key: value for key, value in data.items() if key in allowed}


class AppwriteMetadataStore(AppwriteSocialStore):
    """
    Novels / chapters / tts_jobs / audio_tracks tren Appwrite.

    Phan XA HOI o `server/appwrite_social.py` — cung mot kho, tach tep vi do
    dai. Mixin do dung lai ha tang cua lop nay (`_create`, `_page`, ...) va
    khong mo ket noi rieng nao.
    """

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        """:param client: cho phep test tiem client gia lap thay cho httpx."""
        from server.appwrite_adapter import AppwriteConfigError

        #: Duong khoa job da duoc CHUNG MINH chay chua. Ba trang thai:
        #:
        #:   None  — chua biet: chua co lan tao job nao di qua duong nay
        #:   True  — mot giao dich khoa DA commit thanh cong
        #:   False — da thu va HONG; he thong dang chay o duong cu, khong khoa
        #:
        #: KHONG duoc khoi tao `True`. Ban truoc lam vay, va co do da NOI DOI:
        #: `/api/health` bao `job_lock_ready=true` ngay sau khi deploy, trong
        #: khi duong khoa chua he duoc thu — roi moi lan tao job deu hong am
        #: tham. Mot co tien kiem chi dung SAU khi da hong thi vo dung dung o
        #: luc can no nhat.
        self._job_lock_ready = None

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho metadata. Cần cả bốn biến "
                "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID."
            )
        self._settings = settings
        # `api_base` da bo `/v1` o cuoi neu co - moi path duoi day tu them `/v1`
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        #: Ten thuoc tinh that su co trong tung collection, hoi mot lan roi nho.
        self._attrs_cache: Dict[str, Set[str]] = {}
        #: Ket noi dung chung. TEN KHAC `_client`: truong do da danh cho client
        #: gia lap ma test tiem vao, va dung chung mot ten se lam nhanh "client
        #: duoc tiem" cua `_call` bat nham ket noi that.
        self._pool: Optional[httpx.Client] = None

    # -- ha tang --------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        # API key CHI o phia server, khong bao gio ra khoi tien trinh nay
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            response = self._http().request(method, url, json=payload,
                                            params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            # PHAI la `AppwriteUnavailableError` (loi ha tang TAM THOI, thu lai
            # duoc), KHONG phai `NotFoundError` (ban ghi that su khong ton
            # tai): mot loi TRANSPORT (mat mang/DNS/timeout) nghia la ta CHUA
            # BIET ban ghi co ton tai hay khong, khac han mot response that su
            # tra 404. Phat hien khi review PR #23 (2026-08-21): truoc day ca
            # hai bi gop lam mot, nen mot dot Appwrite gian doan giua luc xoa
            # tai khoan (`AccountDeletionService`) bao ve khach hang la 404
            # ("khong tim thay gi de xoa") thay vi 503 ("thu lai sau") — dung
            # cung mau voi `appwrite_adapter.py::AppwriteIdentityAdapter._request`.
            raise AppwriteUnavailableError(
                f"Không kết nối được Appwrite: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = None
            # PHAI kiem tra ha tang TAM THOI (quota/rate-limit het han muc)
            # TRUOC ca hai nhanh duoi day, KE CA truoc `== 404`: phat hien
            # THAT tren staging (2026-08-23) — Appwrite Cloud het han muc DOC
            # tra ve mot loi ma tang nay tung doi thanh "khong tim thay ban
            # ghi", lam MOT truyen vua tao THANH CONG (201) bi bao 404 khi
            # doc lai NGAY LAP TUC, va `/api/ready` bao sai "loai_loi:
            # NotFoundError" cho mot su co han muc chu khong phai ban ghi
            # thieu that. Cung mot loi ha tang co the di kem BAT KY status
            # code nao Appwrite chon dung cho no — khong gia dinh la 404 hay
            # 400 cu the, chi doc THONG DIEP.
            if _la_loi_ha_tang_tam_thoi(body):
                raise AppwriteUnavailableError(
                    thong_diep_loi_an_toan(body, status_code=response.status_code))
            if response.status_code == 404:
                # Phan biet "thieu collection" voi "thieu ban ghi".
                raise_for_appwrite_404(response, path)
            raise NotFoundError(
                thong_diep_loi_an_toan(body, status_code=response.status_code))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _http(self) -> httpx.Client:
        """
        MOT client dung lai, thay vi mot client moi cho tung request.

        Do duoc tren staging that: mot `httpx.Client` moi ton 1.5-2.0 giay moi
        lan goi — phan lon la bat tay TLS toi `sgp.cloud.appwrite.io`. Dung lai
        mot client co keep-alive thi cac lan sau con 0.5-0.9 giay.

        Voi mot trang quan tri goi bay truy van, khac biet do la vai chuc giay.

        An toan luong: `httpx.Client` an toan cho nhieu luong, va o day khong
        co trang thai nao duoc chia se ngoai ket noi — header duoc truyen theo
        tung request.
        """
        if self._pool is None:
            self._pool = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._pool

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    @staticmethod
    def _owner_permissions(owner_id: str, public_read: bool = False) -> List[str]:
        """
        Quyen tren document: CHI DOC. Khong client nao duoc ghi thang.

        Truoc day co cap them `update`/`delete` cho chu so huu. Nhung cac
        collection nay chua toan truong do SERVER quyet dinh:

        - `novels.state`      - xuat ban hay chua
        - `tts_jobs.status`   - va `output_key`
        - `audio_tracks.object_key` - tro toi file audio nao

        Nguoi dung nam session/JWT hop le goi thang Appwrite API duoc. Voi
        quyen `update` tren `audio_tracks` cua chinh minh, ho chi can doi
        `object_key` sang key cua nguoi khac la `/api/audio/{chapter}` se phuc
        vu audio cua nguoi do - vuot qua ca `_may_listen()`.

        Moi thao tac ghi deu di qua backend bang API key (API key bo qua
        document permission), nen bo `update`/`delete` khong hong chuc nang.

        `public_read` chi them quyen DOC cong khai cho truyen da xuat ban.
        """
        perms = [f'read("user:{owner_id}")']
        if public_read:
            perms.append('read("any")')
        return perms

    def _supported_fields(self, collection: str) -> Optional[Set[str]]:
        """
        Ten cac thuoc tinh THUC SU dang co trong collection, hoi Appwrite MOT lan.

        Vi sao can: `PERSISTED_FIELDS` la thu ta MUON luu, con day la thu Appwrite
        DANG co. Hai cai lech nhau khi code duoc trien khai truoc khi chay
        `scripts/setup_appwrite.py`. Gui mot thuoc tinh chua ton tai thi Appwrite
        tu choi CA document — tuc la khong tao duoc audio nua.

        Loc theo danh sach nay thi thu tu trien khai code/schema khong con quan
        trong: thieu thuoc tinh recovery thi chi mat tinh nang recovery.

        Khong hoi duoc (mang loi, khong du quyen) -> tra None, va tang tren giu
        nguyen hanh vi cu la gui het.
        """
        cached = self._attrs_cache.get(collection)
        if cached is not None:
            return cached or None
        try:
            data = self._call(
                "GET", f"/v1/databases/{self._db}/collections/{collection}")
        except Exception:
            self._attrs_cache[collection] = set()
            return None
        names = {a.get("key") for a in (data.get("attributes") or []) if a.get("key")}
        self._attrs_cache[collection] = names
        return names or None

    def _writable(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """`persistable()` roi bo tiep nhung thuoc tinh Appwrite chua co."""
        fields = persistable(collection, data)
        available = self._supported_fields(collection)
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
                owner_id: str, public_read: bool = False) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            "permissions": self._owner_permissions(owner_id, public_read),
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _list(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        return self._page(collection, queries)[0]

    def _page(self, collection: str,
              queries: List[str]) -> Tuple[List[Dict[str, Any]], int]:
        """
        Nhu `_list` nhung tra kem TONG so ban ghi khop dieu kien.

        Appwrite tra `total` doc lap voi `limit`/`offset` — da kiem chung: dat
        `limit=1` van thay `total=3`. Nho vay biet duoc con trang sau hay khong
        ma khong phai dem lai.
        """
        data = self._call("GET", self._docs(collection), params={"queries[]": queries})
        docs = list(data.get("documents") or [])
        total = data.get("total")
        return docs, int(total) if isinstance(total, int) else len(docs)

    def _list_all(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        """
        Nhu `_list` nhung LAY HET, khong dung o 25 document dau tien.

        Appwrite mac dinh tra ve 25 document. Truy van nao co the vuot con so do
        ma goi thang `_list` se bi CAT AM THAM — khong loi, khong canh bao, chi
        thieu du lieu. Mot truyen 40 chuong se chi hien 25 chuong.
        """
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            page = self._list(collection, queries + [q_limit(PAGE_SIZE),
                                                     q_offset(offset)])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any],
                permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"data": self._writable(collection, data)}
        if permissions is not None:
            payload["permissions"] = permissions
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}", payload=payload)

    def _delete(self, collection: str, doc_id: str) -> None:
        self._call("DELETE", f"{self._docs(collection)}/{doc_id}")

    # -- novel ---------------------------------------------------------------

    def create_novel(self, novel: Novel) -> Novel:
        self._create(COL_NOVELS, novel.novel_id, novel.to_dict(), novel.owner_id)
        return novel

    def get_novel(self, novel_id: str) -> Novel:
        return _novel_from_doc(self._get(COL_NOVELS, novel_id))

    def owned_novel(self, novel_id: str, owner_id: str) -> Novel:
        novel = self.get_novel(novel_id)
        if novel.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tiểu thuyết này.")
        return novel

    def list_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False) -> List[Novel]:
        items, _ = self.find_novels(owner_id=owner_id, published_only=published_only)
        return items

    def find_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False, query: str = "",
                    tag: str = "", limit: Optional[int] = None,
                    offset: int = 0) -> Tuple[List[Novel], int]:
        """
        Loc va phan trang HOAN TOAN o phia Appwrite.

        Khong tai het ve roi loc: day la ca ly do ton tai cua L2 — trang kham
        pha khong duoc keo ca nghin truyen ve trinh duyet.

        Xem contract o `MetadataStore.find_novels`.
        """
        queries: List[str] = [q_order_desc("created_at")]
        if owner_id:
            queries.append(q_equal("owner_id", owner_id))
        if published_only:
            queries.append(q_equal("state", "published"))
        if tag:
            # `tags` la mang -> phai `contains`, `equal` bi Appwrite tu choi
            queries.append(json.dumps(q_contains("tags", tag)))
        needle = query.strip()
        if needle:
            queries.append(q_or(q_contains("title", needle),
                                q_contains("description", needle)))

        if limit is None:
            # Khong phan trang: lay het, nhung van phai lat trang vi Appwrite
            # mac dinh chi tra 25 document.
            items = [_novel_from_doc(d) for d in self._list_all(COL_NOVELS, queries)]
            return items, len(items)

        docs, total = self._page(COL_NOVELS, queries + [
            q_limit(max(1, limit)),
            q_offset(max(0, offset)),
        ])
        return [_novel_from_doc(d) for d in docs], total

    def novel_tags(self, published_only: bool = True) -> List[str]:
        """
        Cac the dang co. Chi xin ve truong `tags`, va lat trang.

        Mot vong quet toan bo truyen — nhung chi lay MOT truong, va chay mot lan
        moi lan mo trang kham pha. Khi so truyen lon len den muc nay thanh van
        de thi cach dung la mot collection `tags` rieng, chua lam.
        """
        queries: List[str] = [q_select("tags")]
        if published_only:
            queries.append(q_equal("state", "published"))
        tags = set()
        for doc in self._list_all(COL_NOVELS, queries):
            for tag in doc.get("tags") or []:
                if tag:
                    tags.add(tag)
        return sorted(tags, key=lambda t: t.casefold())

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Xuat ban: cap nhat trang thai VA mo quyen doc cong khai.

        NGUYEN TU: Appwrite cho phep PATCH ca `data` lan `permissions` trong
        MOT request, nen khong ton tai cua so ma trang thai da doi con quyen
        thi chua - hoac ca hai cung doi, hoac khong gi doi ca.

        Quyen sau khi xuat ban: cong khai chi duoc `read`. `update`/`delete`
        VAN chi thuoc chu so huu - khong bao gio mo quyen sua cho public.

        IDEMPOTENT: goi lai tren novel da `published` van gui lai dung PATCH
        do. PATCH khong tao ban ghi trung, va viec ap lai quyen giup TU CHUA
        neu quyen bi lech vi mot lan sua tay tren console Appwrite.
        """
        current = self.owned_novel(novel_id, owner_id)    # 404 / 403 o day

        # Dung `replace()` thay vi doi tai cho: chi cong bo ban `published`
        # SAU KHI PATCH thanh cong. Neu `_update` nem loi thi khong co object
        # nao mang trang thai `published` duoc tra ve.
        published = replace(
            current, state=PublishState.PUBLISHED, updated_at=now_iso()
        )
        self._update(
            COL_NOVELS, published.novel_id,
            {"state": published.state.value, "updated_at": published.updated_at},
            permissions=self._owner_permissions(published.owner_id, public_read=True),
        )
        return published

    #: Chi nhung truong nay moi cho nguoi dung sua.
    NOVEL_EDITABLE = (
        "title", "description", "tags",
        "fandom_ids", "publication_mode", "external_author_name",
        "external_source_url", "external_chapter_count",
        "external_updated_at", "language",
        "characters", "pairings", "status",
    )

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        current = self.owned_novel(novel_id, owner_id)
        allowed = {k: v for k, v in fields.items() if k in self.NOVEL_EDITABLE}
        updated = replace(current, **allowed, updated_at=now_iso())
        # `publication_mode` va `status` la enum trong `allowed` (can the cho `replace()`
        # o tren) nhung Appwrite can `.value` — cung quy uoc voi `state` o
        # `publish_novel`/`unpublish_novel`.
        wire = dict(allowed)
        if "publication_mode" in wire:
            wire["publication_mode"] = wire["publication_mode"].value
        if "status" in wire:
            wire["status"] = wire["status"].value
        # KHONG gui `permissions`: sua noi dung khong duoc dong toi pham vi
        # hien thi. Doi cong khai/rieng tu chi qua publish/unpublish.
        self._update(COL_NOVELS, novel_id,
                     {**wire, "updated_at": updated.updated_at})
        return updated

    def set_novel_cover(self, novel_id: str, owner_id: str,
                        cover_key: Optional[str]) -> Novel:
        """Xem contract o `MetadataStore.set_novel_cover` — duong ghi RIENG,
        khong di qua `NOVEL_EDITABLE` cua `update_novel`."""
        current = self.owned_novel(novel_id, owner_id)
        updated = replace(current, cover_key=cover_key, updated_at=now_iso())
        self._update(COL_NOVELS, novel_id,
                     {"cover_key": cover_key, "updated_at": updated.updated_at})
        return updated

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Ve ban nhap VA thu hoi `read("any")` trong CUNG mot request PATCH.

        Nguyen tu nhu publish: hoac ca trang thai lan quyen cung doi, hoac
        khong gi doi ca. Idempotent.
        """
        current = self.owned_novel(novel_id, owner_id)
        reverted = replace(current, state=PublishState.DRAFT, updated_at=now_iso())
        self._update(
            COL_NOVELS, novel_id,
            {"state": reverted.state.value, "updated_at": reverted.updated_at},
            permissions=self._owner_permissions(current.owner_id, public_read=False),
        )
        return reverted

    def delete_novel(self, novel_id: str, owner_id: str) -> None:
        self.owned_novel(novel_id, owner_id)
        self._delete(COL_NOVELS, novel_id)

    # -- chapter -------------------------------------------------------------

    CHAPTER_EDITABLE = ("title", "content", "order_index")

    def update_chapter(self, chapter_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> Chapter:
        current = self.owned_chapter(chapter_id, owner_id)
        allowed = {k: v for k, v in fields.items() if k in self.CHAPTER_EDITABLE}
        updated = replace(current, **allowed, updated_at=now_iso())
        self._update(COL_CHAPTERS, chapter_id,
                     {**allowed, "updated_at": updated.updated_at})
        return updated

    def delete_chapter(self, chapter_id: str, owner_id: str) -> None:
        self.owned_chapter(chapter_id, owner_id)
        self._delete(COL_CHAPTERS, chapter_id)

    def create_chapter(self, chapter: Chapter) -> Chapter:
        self._create(COL_CHAPTERS, chapter.chapter_id, chapter.to_dict(),
                     chapter.owner_id)
        return chapter

    def create_chapter_once(self, chapter: Chapter) -> Tuple[Chapter, bool]:
        """
        Xem contract o `MetadataStore.create_chapter_once`.

        Appwrite tu choi `POST` trung `documentId` (409, `_call` boc thanh
        `NotFoundError`) nen day la compare-and-set THAT SU, khong can
        transaction rieng — cung ky thuat voi
        `AppwriteAnimationStore.create_episode_once`.

        Loi TRANSPORT khong roi vao nhanh nay: `_call` nem
        `AppwriteUnavailableError` (con cua `AuthError`, KHONG phai
        `NotFoundError`), nen mot lan mat mang se noi len that thay vi bien
        thanh "chuong nay da co roi".
        """
        try:
            self._create(COL_CHAPTERS, chapter.chapter_id, chapter.to_dict(),
                         chapter.owner_id)
            return chapter, True
        except NotFoundError:
            return _chapter_from_doc(self._get(COL_CHAPTERS,
                                               chapter.chapter_id)), False

    # -- Chinese Media Watcher hang doi (2026-09-02) --------------------------

    def create_queue_item_once(
            self, item: ChineseMediaQueueItem) -> Tuple[ChineseMediaQueueItem, bool]:
        """Dedup vinh vien theo (platform, episode_ref): xem
        `chinese_media_watcher.py::queue_item_id` — `item.item_id` sinh TAT
        DINH tu hai truong do, nen goi lai voi CUNG video la mot no-op an
        toan, cung ky thuat voi `create_chapter_once` (409 -> NotFoundError
        -> coi la 'da co', khong phai loi)."""
        try:
            self._create(COL_CONTENT_QUEUE, item.item_id, item.to_dict(),
                        CONTENT_QUEUE_OWNER)
            return item, True
        except NotFoundError:
            return _queue_item_from_doc(
                self._get(COL_CONTENT_QUEUE, item.item_id)), False

    def get_queue_item(self, item_id: str) -> ChineseMediaQueueItem:
        return _queue_item_from_doc(self._get(COL_CONTENT_QUEUE, item_id))

    def update_queue_item(self, item_id: str, **fields: Any) -> ChineseMediaQueueItem:
        """Cap nhat MOT vai truong (vd `transcript_state="DONE"`) — luon them
        `updated_at` moi, khong bao gio ghi de `item_id`/`created_at`."""
        fields.pop("item_id", None)
        fields.pop("created_at", None)
        fields["updated_at"] = now_iso()
        self._update(COL_CONTENT_QUEUE, item_id, fields)
        return self.get_queue_item(item_id)

    def list_queue_items_by_state(
            self, *, stage: str, state: str, limit: int = 50) -> List[ChineseMediaQueueItem]:
        """Vd `stage="transcript_state", state="PENDING"` — muc dich duy nhat
        cua ham nay la nguon viec cho `chinese_media_orchestrator.py`."""
        docs = self._list(COL_CONTENT_QUEUE,
                          [q_equal(stage, state), q_limit(limit)])
        return [_queue_item_from_doc(d) for d in docs]

    def get_chapter(self, chapter_id: str) -> Chapter:
        return _chapter_from_doc(self._get(COL_CHAPTERS, chapter_id))

    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        if chapter.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu chương này.")
        return chapter

    def list_chapters(self, novel_id: str) -> List[Chapter]:
        """Lay HET chuong cua truyen — truyen dai khong duoc mat chuong."""
        return [
            _chapter_from_doc(d)
            for d in self._list_all(COL_CHAPTERS, [
                q_equal("novel_id", novel_id),
                q_order_asc("order_index"),
            ])
        ]

    def chapters_for_owner(self, owner_id: str) -> List[Chapter]:
        """
        MOI chuong cua mot nguoi dung, mot truy van (co lat trang).

        Ly do ton tai: thu vien audio truoc day goi `/api/novels/{id}` cho TUNG
        truyen chi de dung mot bang tra ten chuong — so request tang tuyen tinh
        theo so truyen. Xem contract o `MetadataStore.chapters_for_owner`.
        """
        return [
            _chapter_from_doc(d)
            for d in self._list_all(COL_CHAPTERS, [
                q_equal("owner_id", owner_id),
                q_order_asc("order_index"),
            ])
        ]

    # -- job -----------------------------------------------------------------

    def create_job(self, job: TtsJob) -> TtsJob:
        self._create(COL_JOBS, job.job_id, job.to_dict(), job.owner_id)
        return job

    def create_job_once(self, job: TtsJob, fingerprint: str):
        """
        Tao job kem KHOA TAT DINH. Xem contract o `MetadataStore.create_job_once`.

        Hang khoa va hang job duoc tao trong CUNG mot transaction. Uniqueness
        cua `rowId` khoa duoc cuong che ben trong transaction, nen ke thua
        khong ghi duoc gi ca — khong co khe ho giua "tao khoa" va "tao job", va
        khi khoa da ton tai thi job cung chac chan da ton tai.

        Cung khuon voi `claim_job`, va vi cung mot ly do: doc-roi-ghi khong
        chan duoc hai request cham nhau trong cung mot phan giay.

        TUONG THICH NGUOC: neu bang `job_locks` chua duoc tao trong Appwrite,
        transaction se hong va ta LUI VE hanh vi cu (tao thang, khong khoa).
        Lui ve mot hanh vi kem an toan hon la co y va co gioi han: no giu he
        thong chay duoc truoc khi migration kip chay, va `/api/health` bao ra
        co `job_lock_ready` de nguoi van hanh thay ngay minh dang o che do nao.
        """
        row_id = _job_lock_id(job.owner_id, job.chapter_id, fingerprint)
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [
                           {"action": "create", "databaseId": self._db,
                            "tableId": COL_JOB_LOCKS, "rowId": row_id,
                            "data": {"job_id": job.job_id,
                                     "owner_id": job.owner_id,
                                     "created_at": now_iso()},
                            "permissions": self._owner_permissions(job.owner_id)},
                           {"action": "create", "databaseId": self._db,
                            "tableId": COL_JOBS, "rowId": job.job_id,
                            # `_writable` chu KHONG phai `to_dict()` tho.
                            #
                            # `to_dict()` la hinh dang cua API, khong phai hinh
                            # dang luu tru: no kem `progress`, mot thuoc tinh
                            # DAN XUAT khong co cot tuong ung. Appwrite tu choi
                            # ca giao dich voi "Unknown attribute: progress",
                            # va vi loi bi nuot o `except` ben duoi, he thong
                            # lang le lui ve duong cu — khoa KHONG BAO GIO duoc
                            # ghi. Da do that tren production: 44 job, 0 hang
                            # `job_locks`.
                            "data": self._writable(COL_JOBS, job.to_dict()),
                            # Hang job co rowSecurity; thieu quyen thi chinh
                            # chu so huu doc khong ra. Moi duong ghi khac deu
                            # di qua `_create`, von luon gan quyen nay.
                            "permissions": self._owner_permissions(job.owner_id)},
                       ]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
            if result.get("status") == "committed":
                # Chi bay gio moi duoc khang dinh duong khoa chay: mot giao
                # dich da commit that.
                self._job_lock_ready = True
                return job, True
        except Exception:
            pass

        # Khong commit duoc. Hai kha nang, va chung can hai cach xu ly khac han:
        #   1. mot request khac da thang -> hang khoa TON TAI, doc ra job cua ho;
        #   2. bang `job_locks` chua co -> khong doc duoc, lui ve hanh vi cu.
        # Toi day nghia la giao dich khong commit duoc. HAI ly do rat khac nhau,
        # va chung noi nguoc nhau ve suc khoe cua duong khoa:
        #
        #   * mot request khac da THANG — hang khoa TON TAI. Day la bang chung
        #     duong khoa DANG CHAY dung nhu thiet ke, khong phai su co;
        #   * bang chua co / cau hinh sai — khong doc duoc hang nao.
        #
        # Nen phai doc truoc roi moi ket luan, chu khong ha co ngay.
        try:
            khoa = self._get(COL_JOB_LOCKS, row_id)
        except Exception:
            self._job_lock_ready = False
            self._create(COL_JOBS, job.job_id, job.to_dict(), job.owner_id)
            return job, True

        # Doc duoc hang khoa => co ai do da ghi duoc no => duong khoa chay.
        self._job_lock_ready = True

        cua_ho = str(khoa.get("job_id") or "")
        giu_khoa = None
        try:
            giu_khoa = self.get_job(cua_ho)
        except NotFoundError:
            pass                    # khoa mo coi: job da bi xoa

        # Job THAT BAI khong giu khoa nua: nguoi dung phai thu lai duoc.
        # `find_job_by_fingerprint` cung bo qua `failed` vi dung ly do do.
        if giu_khoa is not None and giu_khoa.status != JobStatus.FAILED:
            return giu_khoa, False

        # Doc quyen lai: tro khoa sang job moi, roi tao job.
        self._call("PATCH",
                   f"/v1/tablesdb/{self._db}/tables/{COL_JOB_LOCKS}/rows/{row_id}",
                   payload={"data": {"job_id": job.job_id}})
        self._create(COL_JOBS, job.job_id, job.to_dict(), job.owner_id)
        return job, True

    def get_job(self, job_id: str) -> TtsJob:
        return _job_from_doc(self._get(COL_JOBS, job_id))

    def owned_job(self, job_id: str, owner_id: str) -> TtsJob:
        job = self.get_job(job_id)
        if job.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job này.")
        return job

    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str,
                                fingerprint: str) -> Optional[TtsJob]:
        """
        Idempotency: dua vao index to hop owner_id + chapter_id + content_hash.

        Lat trang: moi lan tao lai that bai la mot job nua cung dau van tay, nen
        so ban ghi khong co tran tren. Cat o 25 thi mot job `completed` nam sau
        25 job `failed` se bi bo qua, va he thong tao lai audio mot cach vo ich.
        """
        for doc in self._list_all(COL_JOBS, [
            q_equal("owner_id", owner_id),
            q_equal("chapter_id", chapter_id),
            q_equal("content_hash", fingerprint),
        ]):
            job = _job_from_doc(doc)
            if job.status != JobStatus.FAILED:
                return job
        return None

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None) -> List[TtsJob]:
        """
        Lich su job cua mot nguoi dung.

        Lat trang: lich su nay chi tang len theo thoi gian, khong co tran tren.
        Appwrite mac dinh chi tra 25 document, nen `_list` se lam thu vien audio
        va lich su Studio mat ban ghi mot cach am tham.
        """
        queries = [q_equal("owner_id", owner_id), q_order_desc("created_at")]
        if chapter_id:
            queries.append(q_equal("chapter_id", chapter_id))
        return [_job_from_doc(d) for d in self._list_all(COL_JOBS, queries)]

    def jobs_by_ids(self, job_ids: Sequence[str]) -> Dict[str, TtsJob]:
        """
        Xem contract o `MetadataStore.jobs_by_ids`.

        MOT truy van moi lo 50 id — cung ky thuat voi `job_settings` va
        `novels_by_ids`. Loc theo `job_id` (thuoc tinh), KHONG theo `$id`: chi
        muc `job_id` khong ton tai rieng nhung `equal` nhieu gia tri van chay,
        va cach nay dung y voi cac ham `*_by_ids` khac cua kho nay.
        """
        ds = [j for j in dict.fromkeys(job_ids) if j]
        if not ds:
            return {}
        ra: Dict[str, TtsJob] = {}
        for i in range(0, len(ds), 50):
            lo = ds[i:i + 50]
            for row in self._list_all(COL_JOBS, [q_equal("job_id", *lo)]):
                job = _job_from_doc(row)
                ra[job.job_id] = job
        return ra

    def save_job(self, job: TtsJob) -> TtsJob:
        """Ghi lai trang thai job sau khi chay xong."""
        self._update(COL_JOBS, job.job_id, job.to_dict())
        return job

    def job_settings(self, owner_id: str,
                     fingerprints: Sequence[str]) -> Dict[str, Tuple[str, int]]:
        """
        MOT truy van IN moi lo, khong phai mot truy van moi dau van tay.

        Xem contract o `MetadataStore.job_settings`. Khong dung `q_select`: `rate`
        va `chunk_chars` von co san trong schema job, nhung giu nguyen cach lay ca
        document cho thong nhat voi `audio_by_chapter` va khoi rang buoc them.
        """
        wanted = list(dict.fromkeys(fingerprints))
        if not wanted:
            return {}
        out: Dict[str, Tuple[str, int]] = {}
        for start in range(0, len(wanted), BATCH_IDS):
            batch = wanted[start:start + BATCH_IDS]
            for doc in self._list_all(COL_JOBS, [
                q_equal("owner_id", owner_id),
                q_equal("content_hash", *batch),
            ]):
                fingerprint = str(doc.get("content_hash") or "")
                if not fingerprint or fingerprint in out:
                    continue
                out[fingerprint] = (
                    str(doc.get("rate") or "1.0"),
                    int(doc.get("chunk_chars") or 0),
                )
        return out

    def claim_job(self, job: TtsJob, worker_id: str,
                  lease_expires_at: str) -> Optional[int]:
        """
        Compare-and-set THAT SU bang mot transaction.

        Da do truc tiep tren Appwrite Cloud 1.9.6:
        - `POST /v1/tablesdb/transactions` nhan `ttl` trong khoang 60..3600;
        - thao tac phai dung ten TablesDB (`tableId`/`rowId`), dung
          `collectionId`/`documentId` thi bi tu choi 400;
        - hai transaction cung cham mot hang -> cai thu hai nhan
          `409 The transaction has a conflict`;
        - 10 worker commit dong thoi -> DUNG MOT cai thanh cong.

        Transaction nay gom HAI thao tac:
          1. `create` hang khoa co id tat dinh `{job_id}-{attempt}` — tinh duy
             nhat do database cuong che;
          2. `update` job row (lease, attempts, status).

        Vi (1) nam trong cung transaction voi (2), worker thua co commit hong HAN:
        no khong ghi duoc lease va cung khong ghi duoc gi vao job. Do la ly do
        day la CAS that su chu khong phai doc-roi-doc-lai.

        Thua -> tra None. Nguoi goi phai DUNG LAI, khong thu lai mu quang.
        """
        current = self.get_job(job.job_id)
        if current.status.is_terminal:
            return None
        if current.lease_is_live():
            # KE CA khi lease la cua chinh `worker_id`. Xem contract o
            # `MetadataStore.claim_job`: bo quet doc danh sach job qua Appwrite,
            # ban doc do co the cu hon lan claim vua roi, nen mot tien trinh
            # hoan toan co the tu nhan lai job MA CHINH NO dang chay va sinh ra
            # thread thu hai. Uniqueness cua `rowId` khong cuu duoc: lan nay
            # `attempt` la mot so KHAC nen khong dung do voi hang khoa nao.
            return None

        fence = (current.attempts or 0) + 1
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
        except Exception:
            return None
        tx_id = tx.get("$id")
        if not tx_id:
            return None

        operations = [
            {"action": "create", "databaseId": self._db, "tableId": COL_CLAIMS,
             "rowId": f"{job.job_id}-{fence}",
             "data": {"job_id": job.job_id, "attempt": fence,
                      "worker_id": worker_id, "created_at": now_iso()}},
            {"action": "update", "databaseId": self._db, "tableId": COL_JOBS,
             "rowId": job.job_id,
             "data": {"status": JobStatus.RUNNING.value, "attempts": fence,
                      "lease_owner": worker_id,
                      "lease_expires_at": lease_expires_at}},
        ]
        try:
            self._call("POST", f"/v1/tablesdb/transactions/{tx_id}/operations",
                       payload={"operations": operations})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx_id}",
                                payload={"commit": True})
        except Exception:
            # 409 conflict hoac bat ky loi nao khac -> coi nhu THUA. Day la ket
            # qua binh thuong khi nhieu worker cung tranh, khong phai su co.
            return None
        return fence if result.get("status") == "committed" else None

    def renew_lease(self, job_id: str, fence: int, worker_id: str,
                    lease_expires_at: str) -> bool:
        """
        Gia han lease. Xem contract o `MetadataStore.renew_lease`.

        Chi hai truong di trong payload. So voi `save_job_fenced` thi day khong
        phai toi uu duong truyen ma la tinh dung dan: heartbeat khong nam giu
        trang thai moi nhat cua job (progress, output_key, transition vua ghi),
        nen moi truong no gui deu la mot ban cu co kha nang lui nguoc du lieu.
        """
        try:
            current = self.get_job(job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job_id,
                           "data": {"lease_expires_at": lease_expires_at,
                                    "lease_owner": worker_id}}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            # Mang chap chon. Nguoi goi coi nhu nhip nay lo, lease cu con han.
            return False
        return result.get("status") == "committed"

    def save_progress(self, job_id: str, fence: int, worker_id: str,
                      done_parts: int, total_parts: int) -> bool:
        """
        Luu tien do. Xem contract o `MetadataStore.save_progress`.

        Dung mot khuon voi `renew_lease` ngay tren, va vi cung mot ly do: chi
        hai truong di trong payload. `save_job_fenced` gui ca hang tu mot ban
        sao trong bo nho cua worker, nen dung no o day se lui nguoc bat ky
        truong nao vua duoc ghi boi mot duong khac.

        `progress` KHONG di kem: no la thuoc tinh dan xuat, khong phai cot.
        """
        try:
            current = self.get_job(job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job_id,
                           "data": {"done_parts": max(0, int(done_parts)),
                                    "total_parts": max(0, int(total_parts))}}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            # Mang chap chon. Mat mot lan ghi tien do la vo hai: lan sau se ghi
            # con so moi hon, va cac transition van ghi day du.
            return False
        return result.get("status") == "committed"

    def save_job_fenced(self, job: TtsJob, fence: int, worker_id: str) -> bool:
        """
        Ghi job chi khi nguoi goi con giu quyen. Xem contract o `MetadataStore`.

        Doc lai truoc, roi ghi trong mot transaction: neu mot worker khac dang
        nhan job nay cung luc, hai transaction cham cung hang va mot cai se nhan
        409 — nen khong the co chuyen ca hai cung ghi de len nhau.
        """
        try:
            current = self.get_job(job.job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False

        data = persistable(COL_JOBS, replace(job, attempts=fence).to_dict())
        available = self._supported_fields(COL_JOBS)
        if available is not None:
            data = {k: v for k, v in data.items() if k in available}
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job.job_id, "data": data}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            return False
        return result.get("status") == "committed"

    def total_jobs(self) -> int:
        """Tong so job TTS TREN TOAN NEN TANG — bang dieu khien quan tri
        (Admin Control Center V2, A1). `limit(1)` + doc `total`."""
        return self._page(COL_JOBS, [q_limit(1)])[1]

    def count_jobs(self, *, status: Optional[JobStatus] = None,
                  created_after: str = "") -> int:
        """Bo dem BI CHAN cho bang dieu khien quan tri (Phase 7 analytics) —
        loc THEO status/ngay tao qua Appwrite, KHONG quet toan bang."""
        queries: List[str] = [q_limit(1)]
        if status is not None:
            queries.append(q_equal("status", status.value))
        if created_after:
            queries.append(q_greater_equal("created_at", created_after))
        return self._page(COL_JOBS, queries)[1]

    def list_jobs_by_status(self, status: JobStatus) -> List[TtsJob]:
        """
        Lat trang: so job `running` khong co tran tren.

        Xem contract o `MetadataStore.list_jobs_by_status`.
        """
        return [
            _job_from_doc(d)
            for d in self._list_all(COL_JOBS, [
                q_equal("status", status.value),
                q_order_asc("created_at"),
            ])
        ]

    def delete_job(self, job_id: str) -> None:
        """
        Xoa job VA cac dong `job_claims` cua no.

        Khong don claim thi chung nam lai vinh vien: `job_claims` chi tang len,
        khong bao gio giam, va moi lan nhan job lai them mot dong. Da thay that
        — sau hai luot kiem thu, kho con lai hang chuc dong tro toi job khong con
        ton tai.

        Xoa job TRUOC. Neu buoc xoa claim hong, thu con lai la vai dong so ghi
        chep khong ai doc; lam nguoc lai va buoc hai hong thi job da mat claim
        van co the bi nhan lai voi `attempt` da dung.
        """
        self._delete(COL_JOBS, job_id)
        for doc in self._list_all(COL_CLAIMS, [q_equal("job_id", job_id)]):
            try:
                self._delete(COL_CLAIMS, doc["$id"])
            except Exception:
                # So ghi chep thua khong lam hong gi. Cong cu doi soat va lan xoa
                # job sau se don not.
                continue

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        """TIM-HOAC-TAO — xem contract o `MetadataStore.create_track`."""
        for doc in self._list_all(COL_TRACKS, [
            q_equal("chapter_id", track.chapter_id),
            q_equal("content_hash", track.content_hash),
        ]):
            return _track_from_doc(doc)
        self._create(COL_TRACKS, track.track_id, track.to_dict(), track.owner_id)
        return track

    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]:
        docs = self._list(COL_TRACKS, [
            q_equal("chapter_id", chapter_id),
            q_order_desc("created_at"),
            q_limit(1),
        ])
        return _track_from_doc(docs[0]) if docs else None

    def tracks_for_chapter(self, chapter_id: str) -> List[AudioTrack]:
        """
        MOI track cua chuong.

        Lat trang, va day la cho quan trong nhat: `_purge_chapter` dung ham nay
        de lay danh sach object can xoa khoi kho. Cat o 25 thi track thu 26 tro
        di khong bao gio duoc xoa — de lai object mo coi trong R2 mot cach am
        tham. Moi lan tao lai audio la mot track nua, nen con so nay khong co
        tran tren.
        """
        return [
            _track_from_doc(d)
            for d in self._list_all(COL_TRACKS, [q_equal("chapter_id", chapter_id)])
        ]

    def audio_by_chapter(self, chapter_ids: Sequence[str]) -> Dict[str, AudioStamp]:
        """
        MOT truy van IN cho ca lo, thay vi mot truy van moi chuong.

        `q_equal` nhan nhieu gia tri, va Appwrite hieu do la IN. Nho vay so
        vong goi len Appwrite phu thuoc so LO (50 chuong mot lo) chu khong phu
        thuoc so chuong — dung contract o `MetadataStore.audio_by_chapter`.

        Van phai lat trang: mot chuong co the co nhieu track (moi lan tao lai
        audio la mot ban ghi), nen so document tra ve khong bang so chuong hoi.

        CO Y KHONG dung `q_select`: neu liet ke ten thuoc tinh thi truy van nay
        se phu thuoc vao viec `rate`/`chunk_chars` da ton tai trong Appwrite chua,
        va trien khai code truoc khi chay migration se lam ca trang truyen do.
        Lay ca document thi khong co rang buoc thu tu do — track la ban ghi nho.
        """
        wanted = list(dict.fromkeys(chapter_ids))   # bo trung, giu thu tu
        if not wanted:
            return {}

        newest: Dict[str, AudioStamp] = {}
        for start in range(0, len(wanted), BATCH_IDS):
            batch = wanted[start:start + BATCH_IDS]
            for doc in self._list_all(COL_TRACKS,
                                      [q_equal("chapter_id", *batch)]):
                chapter_id = doc.get("chapter_id")
                made_at = str(doc.get("created_at") or "")
                if not chapter_id:
                    continue
                seen = newest.get(chapter_id)
                if seen is not None and made_at <= seen.created_at:
                    continue
                newest[chapter_id] = AudioStamp(
                    created_at=made_at,
                    content_hash=str(doc.get("content_hash") or ""),
                    voice_id=str(doc.get("voice_id") or ""),
                )
        return newest

    def reorder_chapters(self, novel_id: str, owner_id: str,
                         chapter_ids: Sequence[str]) -> List[Chapter]:
        """
        Xem contract o `MetadataStore.reorder_chapters`.

        Appwrite khong co PATCH nhieu document trong mot request, nen buoc ghi
        van la N vong goi len Appwrite. Nhung TRINH DUYET chi gui MOT request —
        do la cho quan trong, vi truoc day doi thu tu tu frontend se thanh N
        request giong dung cai N+1 vua bo di.

        Kiem tra tap chuong TRUOC KHI ghi bat ky document nao.
        """
        self.owned_novel(novel_id, owner_id)
        existing = self.list_chapters(novel_id)
        current = {c.chapter_id for c in existing}
        wanted = list(dict.fromkeys(chapter_ids))
        if set(wanted) != current or len(wanted) != len(chapter_ids):
            raise ValueError(
                "Danh sách thứ tự phải gồm đúng các chương của truyện này.")

        by_id = {c.chapter_id: c for c in existing}
        out: List[Chapter] = []
        for position, chapter_id in enumerate(wanted, start=1):
            chapter = by_id[chapter_id]
            if chapter.order_index != position:
                # CHI `order_index`. Khong gui `updated_at` — sap xep lai khong
                # sua noi dung, ma `updated_at` la moc de biet audio con khop
                # noi dung hay khong.
                self._update(COL_CHAPTERS, chapter_id, {"order_index": position})
                chapter = replace(chapter, order_index=position)
            out.append(chapter)
        return out

    def delete_track(self, track_id: str) -> None:
        self._delete(COL_TRACKS, track_id)


# -----------------------------------------------------------------------------
# Doi document -> dataclass
# -----------------------------------------------------------------------------



    # -- doc theo LO -----------------------------------------------------------
    #
    # MOT vong mang cho N hang, thay vi N vong.
    #
    # `equal` cua Appwrite nhan NHIEU gia tri va hoat dong nhu `IN` — da kiem
    # chung. Do la ca co so cua khoi nay: mot truy van `equal(user_id, [a,b,c])`
    # thay cho ba lan `GET /documents/{id}`.
    #
    # LY DO TON TAI: khu quan tri tung goi `get_stats`/`list_novels`/`get_profile`
    # cho TUNG HANG, va `/api/admin/author-applications` mat 34 giay cho sau
    # persona tren staging that.

    def stats_by_ids(self, user_ids: Sequence[str]) -> Dict[str, AuthorStats]:
        ds = [u for u in dict.fromkeys(user_ids) if u]
        ra = {uid: AuthorStats(user_id=uid) for uid in ds}
        if not ds:
            return ra
        for lo in _theo_lo(ds):
            for row in self._list_all(COL_STATS, [q_equal("user_id", *lo)]):
                uid = str(row.get("user_id") or "")
                if uid in ra:
                    ra[uid] = AuthorStats(
                        user_id=uid,
                        qualified_listens=int(row.get("qualified_listens") or 0),
                        published_novels=int(row.get("published_novels") or 0),
                        updated_at=str(row.get("updated_at") or ""),
                    )
        return ra

    def published_counts(self, owner_ids: Sequence[str]) -> Dict[str, int]:
        ds = [u for u in dict.fromkeys(owner_ids) if u]
        dem = {uid: 0 for uid in ds}
        if not ds:
            return dem
        for lo in _theo_lo(ds):
            rows = self._list_all(COL_NOVELS, [
                q_equal("owner_id", *lo),
                q_equal("state", PublishState.PUBLISHED.value),
                q_select("owner_id"),
            ])
            for row in rows:
                uid = str(row.get("owner_id") or "")
                if uid in dem:
                    dem[uid] += 1
        return dem

    def novels_by_ids(self, novel_ids: Sequence[str]) -> Dict[str, Novel]:
        """Nhieu truyen, doc theo LO — xem contract o `MockMetadataStore`."""
        ds = [n for n in dict.fromkeys(novel_ids) if n]
        ra: Dict[str, Novel] = {}
        for lo in _theo_lo(ds):
            for row in self._list(COL_NOVELS, [q_equal("novel_id", *lo),
                                               q_limit(len(lo))]):
                n = _novel_from_doc(row)
                ra[n.novel_id] = n
        return ra

    def chapter_counts(self, novel_ids: Sequence[str]) -> Dict[str, int]:
        ds = [n for n in dict.fromkeys(novel_ids) if n]
        dem = {nid: 0 for nid in ds}
        if not ds:
            return dem
        for lo in _theo_lo(ds):
            for row in self._list_all(COL_CHAPTERS,
                                      [q_equal("novel_id", *lo),
                                       q_select("novel_id")]):
                nid = str(row.get("novel_id") or "")
                if nid in dem:
                    dem[nid] += 1
        return dem

    def total_published_novels(self) -> int:
        """
        Dung `total` cua Appwrite, KHONG keo ban ghi ve.

        `limit(1)` van tra `total` cua ca tap khop dieu kien — da kiem chung, va
        `_page` da dua vao dieu do tu truoc.
        """
        _, total = self._page(COL_NOVELS, [
            q_equal("state", PublishState.PUBLISHED.value), q_limit(1)])
        return total

    def total_novels(self) -> int:
        """Tong so truyen o MOI trang thai (nhap + xuat ban) — bang dieu khien
        quan tri (Admin Control Center V2, A1). Cung idiom bi chan nhu
        `total_published_novels`."""
        return self._page(COL_NOVELS, [q_limit(1)])[1]

    def total_chapters(self) -> int:
        """Tong so chuong TREN TOAN NEN TANG — mot phep dem bi chan, khong
        phai vong lap tren tung truyen (do se la N+1)."""
        return self._page(COL_CHAPTERS, [q_limit(1)])[1]

    def sum_qualified_listens(self) -> int:
        """
        Tong tu ban TONG HOP, khong tu bang su kien.

        Dem lai tu `listen_credits` cho moi lan mo bang dieu khien la mot phep
        quet toan bang. `author_stats` co mot hang moi tac gia, va so tac gia
        nho hon so luot nghe nhieu bac.
        """
        return sum(int(r.get("qualified_listens") or 0)
                   for r in self._list_all(COL_STATS,
                                           [q_select("qualified_listens")]))

    def count_applications(self, status: Optional[AuthorStatus] = None) -> int:
        queries = [q_limit(1)]
        if status is not None:
            queries.insert(0, q_equal("status", status.value))
        return self._page(COL_APPLICATIONS, queries)[1]

    # =========================================================== V2: TAC GIA
    #
    # Bon bang moi, va moi bang mot cach dat `rowId` khac nhau — do la thu quyet
    # dinh tinh dung dan cua ca khoi nay:
    #
    #   author_applications  rowId = user_id       MOT don moi nguoi
    #   author_stats         rowId = user_id       MOT ban tong hop moi nguoi
    #   listen_credits       rowId = khoa TAT DINH  chong dua, xem `credit_key`
    #   moderation_events    rowId = event_id      chi THEM
    #
    # `listen_credits` la cho quan trong nhat: tinh duy nhat cua `rowId` do chinh
    # Appwrite cuong che, nen hai request cung luc thi mot cai nhan 409 va KHONG
    # co lan tinh thu hai. Khong can transaction, khong can khoa rieng — day la
    # co che manh nhat ma kien truc hien tai co san, va no giong het cach
    # `job_locks` chan hai worker cung nhan mot job.

    def _create_kin(self, collection: str, doc_id: str,
                    data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tao hang KHONG cap quyen doc cho bat ky client nao.

        Dung cho `moderation_events`: hang do chua ghi chu noi bo cua nguoi duyet
        va `actor_id` cua quan tri. Moi duong doc hop le deu di qua backend bang
        API key (API key bo qua permission), nen danh sach quyen rong khong lam
        hong chuc nang nao — no chi dong duong doc THANG tu trinh duyet.
        """
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            "permissions": [],
        })

    # -- don tac gia ----------------------------------------------------------

    def get_application(self, user_id: str) -> Optional[AuthorApplication]:
        try:
            row = self._get(COL_APPLICATIONS, user_id)
        except NotFoundError:
            return None
        return _application_from(row)

    def save_application(self, app: AuthorApplication) -> AuthorApplication:
        """
        TAO-HOAC-CAP-NHAT. `rowId` la `user_id`, nen nop lai chinh la ghi de.

        Thu tao truoc roi moi vá: mot don moi la truong hop thuong gap han, va
        lam nguoc lai thi moi lan nop don deu ton mot lan doc that bai.
        """
        app.updated_at = now_iso()
        data = app.to_dict()
        try:
            self._create(COL_APPLICATIONS, app.user_id, data, app.user_id)
        except NotFoundError:
            # Da ton tai (Appwrite tra 409, `_call` doi thanh NotFoundError) ->
            # cap nhat. Giu nguyen quyen cua hang cu.
            self._update(COL_APPLICATIONS, app.user_id, data)
        return app

    def list_applications(self, status: Optional[AuthorStatus] = None,
                          limit: int = 50,
                          offset: int = 0) -> Tuple[List[AuthorApplication], int]:
        """
        Cu lau nhat truoc — thu tu duy nhat khong lam ai bi bo quen vinh vien.

        Loc va phan trang HOAN TOAN o phia Appwrite: mot hang doi co the dai, va
        keo het ve roi cat o Python la cach lam hong dan theo so nguoi dung.
        """
        queries: List[str] = []
        if status is not None:
            queries.append(q_equal("status", status.value))
        queries += [q_order_asc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_APPLICATIONS, queries)
        return [_application_from(r) for r in rows], total

    # -- ban tong hop uy tin --------------------------------------------------

    def get_stats(self, user_id: str) -> AuthorStats:
        """Chua co hang thi tra ban RONG: mot tac gia chua ai nghe van hop le."""
        try:
            row = self._get(COL_STATS, user_id)
        except NotFoundError:
            return AuthorStats(user_id=user_id)
        return AuthorStats(
            user_id=user_id,
            qualified_listens=int(row.get("qualified_listens") or 0),
            published_novels=int(row.get("published_novels") or 0),
            updated_at=str(row.get("updated_at") or now_iso()),
        )

    def save_stats(self, stats: AuthorStats) -> AuthorStats:
        stats.updated_at = now_iso()
        data = stats.to_dict()
        try:
            self._create(COL_STATS, stats.user_id, data, stats.user_id)
        except NotFoundError:
            self._update(COL_STATS, stats.user_id, data)
        return stats

    def add_qualified_listen(self, author_id: str, delta: int = 1) -> AuthorStats:
        """
        Cong don vao ban tong hop.

        HAN CHE DA BIET: day la DOC-ROI-GHI. Appwrite khong co phep cong nguyen
        tu, va mot transaction cung khong cuu duoc vi gia tri moi phai tinh tu
        gia tri cu. Hai lan tinh cho CUNG mot tac gia trong cung mot phan giay co
        the lam mat mot don vi.

        Vi sao van chap nhan duoc:
          - buoc QUAN TRONG — khong tao hai lan tinh cho cung mot nguoi nghe —
            da duoc `create_credit_once` chan tuyet doi bang tinh duy nhat cua
            `rowId`. Cai co the mat o day chi la mot con so dem;
          - `listen_credits` la nguon su that, va `recount_listens()` dung lai
            ban tong hop bat cu luc nao. Chay lai bao nhieu lan cung duoc.

        Xem `docs/AUTHOR_RANK.md` muc "Han che da biet".
        """
        stats = self.get_stats(author_id)
        stats.qualified_listens = max(0, stats.qualified_listens + delta)
        return self.save_stats(stats)

    # -- luot nghe hop le -----------------------------------------------------

    def create_credit_once(self, credit: ListenCredit) -> bool:
        """
        Ghi mot lan tinh, tra `False` neu khoa da ton tai.

        `credit_id` la khoa TAT DINH tu (nguoi nghe, chuong, ngay UTC) — xem
        `creator.credit_key`. Tinh duy nhat cua `rowId` do APPWRITE cuong che,
        nen hai request cung luc thi mot cai nhan 409 va khong co lan tinh thu
        hai. Khong can transaction: day la co che nguyen tu manh nhat ma kien
        truc hien tai co san, y het cach `job_locks` chan hai worker.

        `_call` doi MOI ma >= 400 thanh `NotFoundError`, nen khong phan biet
        duoc 409 voi mot loi khac. Doi lai: mot loi mang o day cung tra `False`,
        tuc la BO QUA mot lan tinh thay vi tinh hai lan. Voi mot he thong uy tin,
        thieu mot lan an han thua mot lan.
        """
        try:
            self._create(COL_CREDITS, credit.credit_id, credit.to_dict(),
                         credit.listener_id)
            return True
        except NotFoundError:
            return False

    def last_credit_at(self, listener_id: str, chapter_id: str) -> Optional[str]:
        """Moc cua lan tinh GAN NHAT cho cap nay, cho phep kiem cua so 24 gio."""
        rows = self._list(COL_CREDITS, [
            q_equal("listener_id", listener_id),
            q_equal("chapter_id", chapter_id),
            q_order_desc("created_at"),
            q_limit(1),
        ])
        return str(rows[0].get("created_at")) if rows else None

    def count_credits(self, author_id: str) -> int:
        """Dem lai tu bang su that — de doi soat `stats` khi nghi no lech."""
        _, total = self._page(COL_CREDITS, [q_equal("author_id", author_id),
                                            q_limit(1)])
        return total

    # -- nhat ky kiem duyet ---------------------------------------------------

    def record_event(self, event: ModerationEvent) -> ModerationEvent:
        """
        CHI THEM. Khong co `_update` hay `_delete` cho bang nay o bat ky tang nao.

        Hang duoc tao KHONG co quyen doc cho client — xem `_create_kin`.
        """
        self._create_kin(COL_EVENTS, event.event_id, event.to_dict())
        return event

    def list_events(self, target_user_id: str = "", limit: int = 50,
                    offset: int = 0, target_type: str = "",
                    target_id: str = "", action: str = "",
                    created_after: str = "") -> Tuple[List[ModerationEvent], int]:
        """
        Moi nhat truoc — nguoi doc nhat ky luon hoi "vua co gi xay ra".

        `target_type`/`action` (Admin Control Center V2, A5) loc THEM cho
        `/admin/audit-log` — CHI equal, khong tim mo (nhat ky khong can tim
        chuoi con, chi can loc dung loai/dung hanh dong). `target_id` (Phase
        4) loc dung MOT doi tuong (vd mot series/tap Animation cu the) — dung
        cho lich su kiem duyet trong trang chi tiet, KHONG phai N truy van
        rieng cho tung tap cua series do. `created_after` (Phase 7 analytics)
        loc theo ngay tao — dung cho bo dem theo khoang thoi gian.
        """
        queries: List[str] = []
        if target_user_id:
            queries.append(q_equal("target_user_id", target_user_id))
        if target_type:
            queries.append(q_equal("target_type", target_type))
        if target_id:
            queries.append(q_equal("target_id", target_id))
        if action:
            queries.append(q_equal("action", action))
        if created_after:
            queries.append(q_greater_equal("created_at", created_after))
        queries += [q_order_desc("created_at"), q_limit(limit), q_offset(offset)]
        rows, total = self._page(COL_EVENTS, queries)
        return [
            ModerationEvent(
                action=str(r.get("action") or ""),
                target_user_id=str(r.get("target_user_id") or ""),
                actor_id=str(r.get("actor_id") or ""),
                actor_role=str(r.get("actor_role") or ""),
                target_type=str(r.get("target_type") or ""),
                target_id=str(r.get("target_id") or ""),
                note=str(r.get("note") or ""),
                metadata=str(r.get("metadata") or ""),
                event_id=str(r.get("event_id") or r.get("$id") or ""),
                created_at=str(r.get("created_at") or ""),
            )
            for r in rows
        ], total

    # ==================================================== XOA TAI KHOAN
    #
    # Xem contract DAY DU o `MetadataStore.delete_account` (server/adapters.py):
    # bang nao xoa, bang nao GIU NGUYEN (`moderation_events`, `listen_credits`
    # phia nguoi nghe), bang nao giu-nhung-an-danh.
    #
    # Moi truy van o day deu di theo mot chi muc DA CO (`owner_idx` cua
    # novels/chapters, `idempotency_idx` cua tts_jobs, `chapter_idx` cua
    # audio_tracks, cac `*_created_idx`/`user_*_idx` cua tang xa hoi,
    # `author_idx` cua listen_credits) — xem `scripts/setup_appwrite.py`.
    # KHONG them chi muc nao cho duong nay. Ngoai le duy nhat la `job_locks`
    # (khong co chi muc nao ca) — xem `_don_job_locks` ben duoi.

    def delete_account(self, user_id: str) -> Dict[str, Any]:
        """Xem contract o `MetadataStore.delete_account`."""
        bc = bao_cao_xoa_tai_khoan()
        if not user_id:
            return bc

        # -- noi dung: chuong (kem audio) roi truyen --------------------------
        for chapter in self.chapters_for_owner(user_id):
            for track in self.tracks_for_chapter(chapter.chapter_id):
                bc["object_keys"] += [k for k in (track.object_key,
                                                  track.transcript_key) if k]
                self._delete(COL_TRACKS, track.track_id)
                bc["audio_tracks"] += 1
            self._delete(COL_CHAPTERS, chapter.chapter_id)
            bc["chapters"] += 1

        for novel in self.list_novels(owner_id=user_id):
            if novel.cover_key:
                bc["object_keys"].append(novel.cover_key)
            self._delete(COL_NOVELS, novel.novel_id)
            bc["novels"] += 1

        # Job theo CHU SO HUU, khong theo chuong: bat ca job mo coi (chuong da
        # bi xoa truoc do bang duong khac). `delete_job` don luon `job_claims`.
        for job in self.list_jobs(user_id):
            self.delete_job(job.job_id)
            bc["tts_jobs"] += 1
        self._don_job_locks(user_id)

        # -- xa hoi -----------------------------------------------------------
        # Dung `_post_from` (ban doi hang cua tang xa hoi) thay vi tu doc
        # `images_json`: danh sach anh cua mot bai co HAI dang (mot anh ban cu,
        # nhieu anh ban V3) va viec lai phep doi do o day la mot cho nua se
        # lech. `appwrite_social.py` la CUNG mot kho, chi tach tep vi do dai.
        for row in self._list_all(COL_POSTS, [q_equal("author_user_id", user_id)]):
            bc["object_keys"] += [str(a.get("key") or "")
                                  for a in _post_from(row).all_images()
                                  if a.get("key")]
            self._delete(COL_POSTS, str(row.get("$id") or ""))
            bc["posts"] += 1

        bc["comments"] = self._xoa_theo_truy_van(
            COL_COMMENTS, [q_equal("author_user_id", user_id)])
        bc["post_likes"] = self._xoa_theo_truy_van(
            COL_POST_LIKES, [q_equal("user_id", user_id)])
        # CA HAI CHIEU cua `user_follows` — hai truy van rieng thay vi mot `or`:
        # moi cai di dung mot chi muc (`follower_created_idx`/
        # `target_created_idx`), con `or` thi khong dung chi muc nao.
        bc["user_follows"] = (
            self._xoa_theo_truy_van(COL_USER_FOLLOWS,
                                    [q_equal("follower_id", user_id)])
            + self._xoa_theo_truy_van(COL_USER_FOLLOWS,
                                      [q_equal("target_id", user_id)]))
        bc["story_follows"] = self._xoa_theo_truy_van(
            COL_STORY_FOLLOWS, [q_equal("follower_id", user_id)])
        bc["notifications"] = self._xoa_theo_truy_van(
            COL_NOTIFICATIONS, [q_equal("user_id", user_id)])

        # -- uy tin tac gia ---------------------------------------------------
        # Truy van thay vi `_delete(COL_STATS, user_id)` du `rowId` = `user_id`:
        # `_call` doi MOI ma >= 400 thanh `NotFoundError`, nen mot loi mang se
        # khong phan biet duoc voi "khong co hang" va ta se bao cao SAI la da
        # don. `user_unique` phu truy van nay.
        bc["author_stats"] = self._xoa_theo_truy_van(
            COL_STATS, [q_equal("user_id", user_id)])

        # CHI phia TAC GIA. Hang ma nguoi nay la NGUOI NGHE o lai: chung da
        # tinh vao uy tin cua mot tac gia KHAC.
        bc["listen_credits"] = self._xoa_theo_truy_van(
            COL_CREDITS, [q_equal("author_id", user_id)])

        # -- giu hang, an danh ------------------------------------------------
        # DOC TRUOC roi moi ghi: cung ly do voi `author_stats` o tren, va o day
        # con quan trong hon — nuot loi ghi nghia la GIU LAI van ban nhan dang
        # cua mot tai khoan da xoa ma khong ai biet. Ghi hong thi NEM len, lan
        # xoa nay bi coi la that bai va nguoi dung con goi lai duoc (danh tinh
        # chi bi xoa o buoc cuoi cung).
        if self.get_application(user_id) is not None:
            self._update(COL_APPLICATIONS, user_id,
                         {"pen_name": AN_DANH_DA_XOA, "bio": AN_DANH_DA_XOA,
                          "intro": AN_DANH_DA_XOA})
            bc["applications_anonymized"] = 1

        for row in self._list_all(COL_REPORTS, [q_equal("reporter_id", user_id)]):
            self._update(COL_REPORTS, str(row.get("$id") or ""),
                         {"reporter_id": AN_DANH_DA_XOA})
            bc["reports_anonymized"] += 1

        return bc

    def _xoa_theo_truy_van(self, collection: str, queries: List[str]) -> int:
        """Xoa MOI hang khop dieu kien, tra ve so hang da xoa.

        Lay HET danh sach TRUOC roi moi xoa (`_list_all` da lat trang): vua xoa
        vua lat trang thi offset truot va bo sot hang — mot lo kinh dien."""
        rows = self._list_all(collection, queries)
        dem = 0
        for row in rows:
            doc_id = str(row.get("$id") or "")
            if not doc_id:
                continue
            self._delete(collection, doc_id)
            dem += 1
        return dem

    def _don_job_locks(self, user_id: str) -> None:
        """Don hang `job_locks` cua nguoi dung — NO LUC TOT NHAT.

        Hai ly do khong de loi o day lam vo ca lan xoa tai khoan:

        - `job_locks` KHONG co chi muc nao (`rowId` la bam tat dinh cua
          (owner_id, chapter_id, fingerprint) — xem `_job_lock_id`), nen mot
          truy van theo `owner_id` la thu duy nhat lam duoc, va no co the bi
          Appwrite tu choi tuy cau hinh;
        - hang khoa con lai la VO HAI: `create_job_once` da xu ly "khoa mo coi"
          (job da bi xoa) bang cach tro khoa sang job moi. Cung triet ly voi
          `job_claims` trong `delete_job`.
        """
        try:
            self._xoa_theo_truy_van(COL_JOB_LOCKS, [q_equal("owner_id", user_id)])
        except Exception:
            pass


def _publish_state_from_doc(doc: Dict[str, Any]) -> PublishState:
    """Chuoi hong/la (du lieu cu, gia tri thu cong tren console) -> DRAFT thay
    vi nem `ValueError` va lam sap ca request. Cung mau voi
    `appwrite_animation_store.py::_moderation_state_from_doc`."""
    try:
        return PublishState(str(doc.get("state") or "draft"))
    except ValueError:
        return PublishState.DRAFT


def _novel_from_doc(doc: Dict[str, Any]) -> Novel:
    return Novel(
        novel_id=str(doc.get("novel_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        description=str(doc.get("description") or ""),
        cover_key=doc.get("cover_key"),
        state=_publish_state_from_doc(doc),
        tags=list(doc.get("tags") or []),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
        publication_mode=_publication_mode_from_doc(doc),
        fandom_ids=list(doc.get("fandom_ids") or []),
        external_author_name=str(doc.get("external_author_name") or ""),
        external_source_url=str(doc.get("external_source_url") or ""),
        external_chapter_count=int(doc.get("external_chapter_count") or 0),
        external_updated_at=str(doc.get("external_updated_at") or ""),
        language=str(doc.get("language") or ""),
        characters=list(doc.get("characters") or []),
        pairings=list(doc.get("pairings") or []),
        status=_novel_status_from_doc(doc),
        platform=str(doc.get("platform") or ""),
        rights_mode=str(doc.get("rights_mode") or ""),
        subtitle_status=str(doc.get("subtitle_status") or ""),
        embed_ref=str(doc.get("embed_ref") or ""),
        subtitle_key=str(doc.get("subtitle_key") or ""),
        dub_audio_key=str(doc.get("dub_audio_key") or ""),
    )


def _publication_mode_from_doc(doc: Dict[str, Any]) -> PublicationMode:
    raw = str(doc.get("publication_mode") or PublicationMode.FULL_TEXT.value)
    try:
        return PublicationMode(raw)
    except ValueError:
        return PublicationMode.FULL_TEXT


def _novel_status_from_doc(doc: Dict[str, Any]) -> NovelStatus:
    raw = str(doc.get("status") or NovelStatus.ONGOING.value)
    try:
        return NovelStatus(raw)
    except ValueError:
        return NovelStatus.ONGOING


def _chapter_from_doc(doc: Dict[str, Any]) -> Chapter:
    return Chapter(
        chapter_id=str(doc.get("chapter_id") or doc.get("$id") or ""),
        novel_id=str(doc.get("novel_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        content=str(doc.get("content") or ""),
        order_index=int(doc.get("order_index") or 1),
        state=_publish_state_from_doc(doc),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _queue_item_from_doc(doc: Dict[str, Any]) -> ChineseMediaQueueItem:
    return ChineseMediaQueueItem(
        item_id=str(doc.get("item_id") or doc.get("$id") or ""),
        source_id=str(doc.get("source_id") or ""),
        platform=str(doc.get("platform") or ""),
        series_slug=str(doc.get("series_slug") or ""),
        episode_ref=str(doc.get("episode_ref") or ""),
        title=str(doc.get("title") or ""),
        source_url=str(doc.get("source_url") or ""),
        discovered_at=str(doc.get("discovered_at") or ""),
        rights_mode=str(doc.get("rights_mode") or "REFERENCE_ONLY"),
        transcript_state=str(doc.get("transcript_state") or "PENDING"),
        translation_state=str(doc.get("translation_state") or "PENDING"),
        subtitle_state=str(doc.get("subtitle_state") or "PENDING"),
        dub_state=str(doc.get("dub_state") or "PENDING"),
        render_state=str(doc.get("render_state") or "PENDING"),
        draft_state=str(doc.get("draft_state") or "PENDING"),
        novel_id=str(doc.get("novel_id") or ""),
        transcript_key=str(doc.get("transcript_key") or ""),
        attempts=int(doc.get("attempts") or 0),
        last_error=str(doc.get("last_error") or ""),
        updated_at=str(doc.get("updated_at") or ""),
        created_at=str(doc.get("created_at") or ""),
    )


def _job_status_from_doc(doc: Dict[str, Any]) -> JobStatus:
    """Cung ly do voi `_publish_state_from_doc`: gia tri la/hong -> PENDING
    thay vi nem `ValueError`."""
    try:
        return JobStatus(str(doc.get("status") or "pending"))
    except ValueError:
        return JobStatus.PENDING


def _job_from_doc(doc: Dict[str, Any]) -> TtsJob:
    return TtsJob(
        job_id=str(doc.get("job_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        chapter_id=str(doc.get("chapter_id") or ""),
        voice_id=str(doc.get("voice_id") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        status=_job_status_from_doc(doc),
        output_key=doc.get("output_key"),
        error_kind=doc.get("error_kind"),
        error_message=str(doc.get("error_message") or ""),
        total_parts=int(doc.get("total_parts") or 0),
        done_parts=int(doc.get("done_parts") or 0),
        rate=str(doc.get("rate") or "1.0"),
        chunk_chars=int(doc.get("chunk_chars") or 2000),
        # Job cu (hoac Appwrite chua co thuoc tinh) -> None/0. `or` la an toan o
        # day: khong co lease thi dung la "khong con worker nao giu".
        lease_expires_at=doc.get("lease_expires_at"),
        lease_owner=doc.get("lease_owner"),
        attempts=int(doc.get("attempts") or 0),
        created_at=str(doc.get("created_at") or ""),
        started_at=doc.get("started_at"),
        finished_at=doc.get("finished_at"),
    )


def _track_from_doc(doc: Dict[str, Any]) -> AudioTrack:
    return AudioTrack(
        track_id=str(doc.get("track_id") or doc.get("$id") or ""),
        chapter_id=str(doc.get("chapter_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        voice_id=str(doc.get("voice_id") or ""),
        object_key=str(doc.get("object_key") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        duration_seconds=float(doc.get("duration_seconds") or 0.0),
        size_bytes=int(doc.get("size_bytes") or 0),
        created_at=str(doc.get("created_at") or ""),
        # Ba truong nay CO THE vang mat tren tai lieu cu (audio tao truoc khi
        # tinh nang phu de ton tai) — `.get(...) or ""`/`or 0` cho ket qua
        # "chua co transcript" trung thuc, khong nem loi.
        transcript_key=str(doc.get("transcript_key") or ""),
        transcript_version=int(doc.get("transcript_version") or 0),
        source_content_hash=str(doc.get("source_content_hash") or ""),
    )
