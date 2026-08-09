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

from server.adapters import NotFoundError, PermissionDenied
from server.config import AppwriteSettings
from server.domain import (
    AudioStamp,
    AudioTrack,
    Chapter,
    JobStatus,
    Novel,
    PublishState,
    TtsJob,
    now_iso,
)

COL_NOVELS = "novels"
COL_CHAPTERS = "chapters"
COL_JOBS = "tts_jobs"
COL_TRACKS = "audio_tracks"
COL_CLAIMS = "job_claims"
#: Khoa tat dinh chan hai request cung tao mot job. Xem `create_job_once`.
COL_JOB_LOCKS = "job_locks"

REQUEST_TIMEOUT = 15.0


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
    ),
    COL_CHAPTERS: (
        "chapter_id", "novel_id", "owner_id", "title", "content",
        "order_index", "state", "created_at", "updated_at",
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
    ),
}


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
    """
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


class AppwriteMetadataStore:
    """Novels / chapters / tts_jobs / audio_tracks tren Appwrite."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        """:param client: cho phep test tiem client gia lap thay cho httpx."""
        from server.appwrite_adapter import AppwriteConfigError

        #: Bang `job_locks` da co trong Appwrite chua.
        #:
        #: Bat dau bang True va chi tat khi `create_job_once` that su khong doc
        #: duoc hang khoa — tuc la doan mo duoc suy ra tu HANH VI THAT chu
        #: khong tu mot lan probe rieng luc khoi dong. `/api/health` bao ra co
        #: nay de nguoi van hanh biet minh dang o che do nao.
        self._job_lock_ready = True

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
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.request(method, url, json=payload, params=params,
                                          headers=self._headers())
        except httpx.HTTPError as exc:
            raise NotFoundError(f"Không kết nối được Appwrite: {exc}") from exc

        if response.status_code == 404:
            raise NotFoundError("Không tìm thấy bản ghi.")
        if response.status_code >= 400:
            message = f"Appwrite trả về lỗi {response.status_code}."
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("message"):
                    message = str(body["message"])
            except Exception:
                pass
            raise NotFoundError(message)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

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
    NOVEL_EDITABLE = ("title", "description", "tags")

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        current = self.owned_novel(novel_id, owner_id)
        allowed = {k: v for k, v in fields.items() if k in self.NOVEL_EDITABLE}
        updated = replace(current, **allowed, updated_at=now_iso())
        # KHONG gui `permissions`: sua noi dung khong duoc dong toi pham vi
        # hien thi. Doi cong khai/rieng tu chi qua publish/unpublish.
        self._update(COL_NOVELS, novel_id,
                     {**allowed, "updated_at": updated.updated_at})
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
                                     "created_at": now_iso()}},
                           {"action": "create", "databaseId": self._db,
                            "tableId": COL_JOBS, "rowId": job.job_id,
                            "data": job.to_dict()},
                       ]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
            if result.get("status") == "committed":
                return job, True
        except Exception:
            pass

        # Khong commit duoc. Hai kha nang, va chung can hai cach xu ly khac han:
        #   1. mot request khac da thang -> hang khoa TON TAI, doc ra job cua ho;
        #   2. bang `job_locks` chua co -> khong doc duoc, lui ve hanh vi cu.
        try:
            khoa = self._get(COL_JOB_LOCKS, row_id)
        except Exception:
            self._job_lock_ready = False
            self._create(COL_JOBS, job.job_id, job.to_dict(), job.owner_id)
            return job, True

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


def _novel_from_doc(doc: Dict[str, Any]) -> Novel:
    return Novel(
        novel_id=str(doc.get("novel_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        description=str(doc.get("description") or ""),
        cover_key=doc.get("cover_key"),
        state=PublishState(str(doc.get("state") or "draft")),
        tags=list(doc.get("tags") or []),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _chapter_from_doc(doc: Dict[str, Any]) -> Chapter:
    return Chapter(
        chapter_id=str(doc.get("chapter_id") or doc.get("$id") or ""),
        novel_id=str(doc.get("novel_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        content=str(doc.get("content") or ""),
        order_index=int(doc.get("order_index") or 1),
        state=PublishState(str(doc.get("state") or "draft")),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _job_from_doc(doc: Dict[str, Any]) -> TtsJob:
    return TtsJob(
        job_id=str(doc.get("job_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        chapter_id=str(doc.get("chapter_id") or ""),
        voice_id=str(doc.get("voice_id") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        status=JobStatus(str(doc.get("status") or "pending")),
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
    )
