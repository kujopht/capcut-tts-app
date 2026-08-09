"""
Adapter cho danh tinh (Appwrite) va luu tru file (Cloudflare R2).

Backend LUON chay duoc: khi chua co credential that, he thong dung ban mock
(trong bo nho + dia cuc bo). Doi sang ban that chi la doi bien moi truong,
khong phai sua code goi.

Giao dien duoc thiet ke san cho signed URL / Worker kiem tra quyen o giai doan
sau: `signed_url()` da co san trong Protocol.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from datetime import datetime, timezone
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
)

from server.config import ConfigError, Settings
from server.domain import (
    AudioStamp,
    AudioTrack,
    Chapter,
    JobStatus,
    Novel,
    Profile,
    PublishState,
    TtsJob,
    new_id,
    now_iso,
)


@dataclass(frozen=True)
class StoredObject:
    """Mot object trong kho, chi phan metadata ma doi soat can."""

    key: str
    size_bytes: int
    #: ISO 8601, UTC. Dung cho thoi gian an han — object vua upload khong duoc
    #: coi la mo coi chi vi ban ghi metadata chua kip xuat hien.
    modified_at: str


class AuthError(Exception):
    """Sai thong tin dang nhap hoac phien khong hop le."""


class NotFoundError(Exception):
    """Khong tim thay ban ghi."""


class PermissionDenied(Exception):
    """Nguoi dung khong so huu tai nguyen nay."""


# -----------------------------------------------------------------------------
# Giao dien
# -----------------------------------------------------------------------------


class IdentityAdapter(Protocol):
    """Auth + metadata. Ban that se do Appwrite dam nhiem."""

    mode: str

    def register(self, email: str, password: str, display_name: str = "") -> Profile: ...
    def login(self, email: str, password: str) -> str: ...
    def profile_from_token(self, token: str) -> Profile: ...

    def logout(self, token: str) -> bool:
        """
        Huy phien o PHIA MAY CHU. Sau lenh nay, `token` phai het gia tri.

        Tra ve True neu THAT SU vua huy mot phien dang song, False neu token
        von da khong dung duoc. Gia tri nay di thang ra `/api/auth/logout`, nen
        no phai dung — bao "da huy" cho mot token rac la noi doi.

        Xoa token o trinh duyet thoi la CHUA du: credential van song, va ai
        nhat duoc no (may dung chung, log, lich su) van dung tiep duoc. Nut
        "Dang xuat" hua rang phien da ket thuc, nen phien PHAI ket thuc that.

        IDEMPOTENT: goi voi token da het han hoac khong hop le thi im lang tra
        ve, khong nem. Nguoi dung bam "Dang xuat" hai lan khong duoc nhan loi.
        """
        ...

    # -- OAuth ---------------------------------------------------------------
    #
    # Danh tinh OAuth do APPWRITE so huu. Backend khong tu sinh id rieng cho
    # nguoi dung Google/Facebook: nguoi dung chinh danh cua Fanfic van la
    # Appwrite user id, nen truyen, audio va quota cu van gan dung nguoi.

    def oauth_start_url(self, provider: str, success: str, failure: str) -> str:
        """
        URL de DAY TRINH DUYET toi, bat dau dang nhap bang `provider`.

        KHONG goi mang. Chi dung chuoi — buoc tiep theo phai xay ra trong
        trinh duyet cua nguoi dung, khong phai o backend.

        `provider` da duoc route kiem theo DANH SACH TRANG truoc khi toi day.
        Ghep thang tham so tu URL vao day la mot open redirect.
        """
        ...

    def exchange_oauth_token(self, user_id: str, secret: str) -> str:
        """
        Doi cap `userId`/`secret` DUNG MOT LAN lay tu callback thanh session
        secret — cung loai token ma `login()` tra ve.

        Day la ly do ca luong nay ton tai: sau buoc nay, nguoi dung dang nhap
        bang Google trong y het nguoi dung dang nhap bang mat khau, va khong co
        he thong phien thu hai nao duoc sinh ra.

        Nem `AuthError` khi cap nay thieu, sai, het han hoac da dung roi. Thong
        diep nem ra KHONG duoc chua secret.
        """
        ...

    def ensure_profile(self, profile: Profile) -> Profile:
        """
        Bao dam ho so ung dung ton tai cho nguoi dung nay.

        Nguoi dang nhap bang Google/Facebook KHONG di qua `register()`, nen ho
        khong co ban ghi ho so nao. Ham nay lap cho trong do, dung CUNG schema
        va cung gia tri mac dinh (`tier=FREE`) ma dang ky thuong dung — khong
        co bang rieng cho nguoi dung OAuth.

        TIM-HOAC-TAO, khong bao gio ghi de: ho so da co thi tra ve NGUYEN VEN.
        Nguoi dung doi ten hien thi trong Fanfic roi mot thang sau dang nhap
        bang Google khong duoc bi Google dat lai ten ho.
        """
        ...


class StorageAdapter(Protocol):
    """Luu file lon. Ban that se la Cloudflare R2 qua API tuong thich S3."""

    mode: str

    def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def signed_url(self, key: str, expires_seconds: int = 3600,
                   download_name: Optional[str] = None) -> Optional[str]: ...

    def delete(self, key: str) -> bool:
        """Xoa mot object. Tra True neu da xoa, False neu von khong ton tai."""
        ...

    def list_objects(self, prefix: str = "") -> Iterator["StoredObject"]:
        """
        Liet ke MOI object co khoa bat dau bang `prefix`.

        Ban cai dat PHAI lat trang day du — S3/R2 tra toi da 1000 khoa moi lan.
        Sinh dan (iterator) thay vi dung mot danh sach: kho co the chua rat nhieu
        object, va cong cu doi soat chi can di qua mot luot.

        KHONG tao presigned URL: doi soat chi doc metadata cua khoa.
        """
        ...


class MetadataStore(Protocol):
    """
    Kho metadata: novels, chapters, tts_jobs, audio_tracks.

    HAI ban hien thuc PHAI tuan theo cung contract nay - `MockMetadataStore`
    (trong bo nho) va `AppwriteMetadataStore`. Tang route chi duoc goi qua day,
    khong bao gio cham thang Appwrite.

    CONTRACT chung cho moi thao tac GHI:
    - Kiem tra quyen so huu o phia server. `user_id` do client gui len KHONG
      bao gio duoc tin; chu so huu luon lay tu token da xac minh.
    - Khong tim thay -> `NotFoundError`. Sai chu so huu -> `PermissionDenied`.
    - Thao tac ghi phai BEN VUNG truoc khi tra ve. Goi xong ma doc lai phai
      thay dung trang thai moi, khong phu thuoc object tam o tang tren.
    """

    # -- novel ---------------------------------------------------------------
    def create_novel(self, novel: Novel) -> Novel: ...
    def get_novel(self, novel_id: str) -> Novel: ...
    def owned_novel(self, novel_id: str, owner_id: str) -> Novel: ...
    def list_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False) -> List[Novel]: ...

    def find_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False, query: str = "",
                    tag: str = "", limit: Optional[int] = None,
                    offset: int = 0) -> Tuple[List[Novel], int]:
        """
        Tim truyen co LOC va PHAN TRANG, tra ve `(trang_hien_tai, tong_so)`.

        `tong_so` la so ban ghi KHOP DIEU KIEN, khong phai so ban ghi tra ve —
        giao dien can no de biet con trang sau hay khong.

        - `query` khop ten HOAC mo ta. Khong phan biet hoa/thuong.
        - `tag` khop mot the trong mang `tags`.
        - `limit=None` nghia la khong phan trang: tra ve HET. Day la mac dinh de
          `list_novels` va cac client cu khong doi hanh vi.
        - Loc va phan trang PHAI lam o tang kho, khong duoc tai het ve roi loc:
          ca ly do ton tai cua ham nay la de trang kham pha khong keo ca nghin
          truyen ve trinh duyet.
        """
        ...

    def novel_tags(self, published_only: bool = True) -> List[str]:
        """Cac the dang co, da bo trung va sap theo bang chu cai."""
        ...

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Chuyen novel sang `published` VA luu ben vung.

        - Chi chu so huu moi duoc goi; nguoi khac -> `PermissionDenied`.
        - IDEMPOTENT: goi lai tren novel da `published` khong loi, khong tao
          du lieu trung, va tra ve chinh novel do.
        - Ban Appwrite con mo them quyen doc cong khai; quyen update/delete
          VAN chi thuoc chu so huu.
        - Luu that bai thi NEM LOI - tuyet doi khong tra ve nhu da thanh cong.
        """
        ...

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        """Sua truyen. Chi chu so huu; chi nhan cac truong nguoi dung duoc sua."""
        ...

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """Dua truyen ve ban nhap VA thu hoi quyen doc cong khai. Idempotent."""
        ...

    def delete_novel(self, novel_id: str, owner_id: str) -> None: ...

    # -- chapter -------------------------------------------------------------
    def create_chapter(self, chapter: Chapter) -> Chapter: ...
    def get_chapter(self, chapter_id: str) -> Chapter: ...
    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter: ...
    def list_chapters(self, novel_id: str) -> List[Chapter]: ...

    def chapters_for_owner(self, owner_id: str) -> List[Chapter]:
        """
        MOI chuong cua mot nguoi dung, khong ke thuoc truyen nao.

        Ban cai dat PHAI tra loi bang so truy van khong phu thuoc so truyen —
        day la ly do ky thuat cua ham nay: truoc do thu vien audio goi
        `/api/novels/{id}` cho tung truyen chi de tra ten chuong.

        Chi tra ve chuong CUA `owner_id`, khong bao gio cua nguoi khac.
        """
        ...

    def update_chapter(self, chapter_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> Chapter: ...
    def delete_chapter(self, chapter_id: str, owner_id: str) -> None: ...

    def reorder_chapters(self, novel_id: str, owner_id: str,
                         chapter_ids: Sequence[str]) -> List[Chapter]:
        """
        Dat lai `order_index` cua CA truyen theo dung thu tu `chapter_ids`.

        - Chi chu so huu truyen; nguoi khac -> `PermissionDenied`.
        - `chapter_ids` phai la DUNG tap chuong cua truyen do, khong thieu khong
          thua. Lech mot cai -> `ValueError`, va KHONG duoc ghi gi ca. Rang buoc
          nay la thu chan viec lam mat chuong: khong the "sap xep lai" ma vo tinh
          bo roi mot chuong ra ngoai danh sach.
        - Chi doi `order_index`. Tieu de, noi dung, audio va trang thai publish
          khong duoc dong toi.
        - Tra ve danh sach chuong sau khi doi, da sap theo thu tu moi.
        """
        ...

    # -- tts job -------------------------------------------------------------
    def create_job(self, job: TtsJob) -> TtsJob: ...
    def save_job(self, job: TtsJob) -> TtsJob: ...
    def get_job(self, job_id: str) -> TtsJob: ...
    def owned_job(self, job_id: str, owner_id: str) -> TtsJob: ...
    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str,
                                fingerprint: str) -> Optional[TtsJob]: ...
    def list_jobs(self, owner_id: str,
                  chapter_id: Optional[str] = None) -> List[TtsJob]: ...

    def job_settings(self, owner_id: str,
                     fingerprints: Sequence[str]) -> Dict[str, Tuple[str, int]]:
        """
        `{content_hash: (rate, chunk_chars)}` cua cac job khop dau van tay.

        Ly do ton tai: `AudioTrack.content_hash` la
        `job_fingerprint(noi dung, giong, toc do, kich thuoc doan)`, nhung track
        khong luu `rate`/`chunk_chars`. Job THI CO — nen ghep tu day, khong phai
        them thuoc tinh vao `audio_tracks`.

        Ban cai dat PHAI tra loi bang so truy van khong phu thuoc so dau van tay
        (theo lo), neu khong danh sach chuong lai thanh N+1.

        - Danh sach rong -> tra ve dict rong, KHONG duoc goi kho.
        - Chi tra ve job CUA `owner_id`.
        - Job da bi xoa thi dau van tay do khong xuat hien trong ket qua.
        """
        ...

    def delete_job(self, job_id: str) -> None: ...

    def claim_job(self, job: TtsJob, worker_id: str,
                  lease_expires_at: str) -> Optional[int]:
        """
        Nhan mot job de chay. Tra ve FENCING TOKEN neu thang, `None` neu thua.

        Fencing token la so lan thu (`attempts`) sau khi nhan. Moi ghi ve sau
        phai kem token nay — xem `save_job_fenced`.

        PHAI NGUYEN TU. Doc-roi-kiem-roi-ghi la KHONG dat: hai worker cung doc
        thay job ket, ca hai cung ghi, ca hai cung tuong minh thang.

        Ban Appwrite: MOT transaction gom `create` hang khoa co id tat dinh
        `{job_id}-{attempt}` VA `update` job row. Tinh duy nhat cua rowId do
        database cuong che, nam ben trong transaction, nen worker thua co commit
        hong han va update job cung khong duoc ap dung.

        Thua thi DUNG LAI: khong goi TTS, khong thu lai mu quang (thu lai se
        cuop mat lease vua duoc cap cho worker thang).

        LEASE CON SONG THI TU CHOI, KE CA VOI CHINH CHU LEASE. Truoc day dieu
        kien la `lease_is_live() and lease_owner != worker_id`, tuc la mot worker
        van nhan lai duoc job MA CHINH NO dang chay. Do khong phai chuyen ly
        thuyet: `recover_stale_jobs()` quet moi 3 giay va doc danh sach job qua
        Appwrite, ban doc do co the con cu hon lan claim vua roi vai giay. Khi
        ay bo quet thay job "chua ai giu", goi lai `claim_job` voi CUNG
        `worker_id`, duoc cap fence 2, va tien trinh khoi dong THREAD THU HAI
        tong hop lai chinh chuong do. Da do that tren staging: mot job duy nhat
        ket thuc voi `attempts=2` va hai lan goi TTS. Vi `output_key` tat dinh
        va `create_track` la tim-hoac-tao nen khong ai thay du lieu hong — chi
        ton mot lan quota va gap doi thoi gian.

        Muon lam moi lease thi dung `renew_lease`, khong phai `claim_job`.
        """
        ...

    def renew_lease(self, job_id: str, fence: int, worker_id: str,
                    lease_expires_at: str) -> bool:
        """
        Gia han lease cho job DANG chay. Tra ve False khi da mat quyen.

        Chi ghi `lease_expires_at` va `lease_owner`, TUYET DOI khong ghi gi khac.
        Truoc day heartbeat dung `save_job_fenced()` voi mot ban sao `TtsJob`
        chup tu luc khoi dong thread, tuc la moi 30 giay lai dap NGUYEN CA HANG
        bang trang thai cu. Do la mot lan ghi de mu: da do tren staging thay no
        keo `status` tu `running` nguoc ve `pending`, va bat ky truong nao worker
        chua kip cap nhat trong bo nho cung bi lui theo.

        Cung dieu kien fence nhu `save_job_fenced`: `attempts` phai bang `fence`
        va `lease_owner` phai bang `worker_id`. False nghia la worker khac da
        nhan job — nguoi goi phai BUONG, khong duoc ghi tiep.
        """
        ...

    def create_job_once(self, job: TtsJob, fingerprint: str) -> Tuple[TtsJob, bool]:
        """
        Tao job, NHUNG chi mot lan cho moi `(owner, chapter, fingerprint)`.

        Tra ve `(job, da_tao_moi)`. `da_tao_moi=False` nghia la mot request
        khac da thang cuoc — job tra ve la CUA HO, va nguoi goi TUYET DOI khong
        duoc chay TTS cho no.

        VI SAO CAN — mot loi da xay ra that tren production: idempotency cu la
        DOC-ROI-GHI khong nguyen tu (`find_job_by_fingerprint()` roi
        `create_job()`). Nam request gan nhu dong thoi deu doc thay "chua co" va
        deu tao mot job. Bang chung trong kho: nam hang `tts_jobs` cung
        fingerprint, tao trong 2 giay, cho MOT chuong.

        (Thiet hai chi la metadata: `output_key` tat dinh theo `content_hash` va
        `create_track` la tim-hoac-tao, nen ca nam lan ghi de cung mot object va
        chi sinh mot track. Cai mat that su la CONG: TTS chay nam lan.)

        Chan bang mot HANG KHOA co `rowId` TAT DINH dan xuat tu bo ba tren, tao
        trong CUNG transaction voi hang job. Uniqueness cua `rowId` duoc cuong
        che ben trong transaction, nen ke thua khong ghi duoc gi ca — khong co
        khe ho nao giua "tao khoa" va "tao job".

        Nguoi goi VAN nen goi `find_job_by_fingerprint()` truoc: no bat duoc
        truong hop pho bien (tai lai trang roi bam lai sau vai phut) ma khong
        ton mot transaction nao.
        """
        ...

    def save_progress(self, job_id: str, fence: int, worker_id: str,
                      done_parts: int, total_parts: int) -> bool:
        """
        Luu tien do cua job DANG chay. Tra ve False khi da mat quyen.

        Chi ghi `done_parts` va `total_parts`, cung ly do voi `renew_lease`:
        worker khong nam giu trang thai moi nhat cua ca hang, nen moi truong
        thua no gui deu la mot ban cu co kha nang lui nguoc du lieu.

        KHONG luu `progress`. No la thuoc tinh DAN XUAT
        (`TtsJob.progress_percent`) tinh tu hai truong tren, nen khong the troi
        khoi chung — mot con so phan tram luu rieng thi co the.

        VI SAO CAN: truoc day tien do chi song trong bo nho cua tien trinh
        worker. `GET /api/jobs/{id}` doc tu kho ben vung, nen nguoi dung thay
        thanh tien trinh dung im o 0% suot ca job; tai lai trang thi mat sach.

        Nguoi goi PHAI tu tiet che nhip goi — xem `_progress_sink` trong
        `server/main.py`. Ghi moi tick se dam nat Appwrite.

        Cung dieu kien fence nhu `save_job_fenced`.
        """
        ...

    def save_job_fenced(self, job: TtsJob, fence: int, worker_id: str) -> bool:
        """
        Ghi job, NHUNG chi khi nguoi goi con giu quyen.

        Tra ve False (khong ghi gi) neu `attempts` da khac `fence` hoac
        `lease_owner` da khac `worker_id` — nghia la mot worker khac da nhan job
        nay roi.

        Vi sao can: worker cu chua chet han, chi bi treo. No tinh day va co ghi
        `completed` de len ket qua cua worker moi. Fence chan dieu do.

        Dung cho cac TRANSITION (running/completed/failed). Gia han lease thi
        dung `renew_lease` — ghi ca hang chi de doi mot moc thoi gian la thua va
        co hai.
        """
        ...

    def list_jobs_by_status(self, status: JobStatus) -> List[TtsJob]:
        """
        MOI job dang o mot trang thai, cua MOI nguoi dung.

        Chi dung cho viec quet job ket luc khoi dong va theo chu ky. Khong co
        route nao phoi bay ham nay ra ngoai — no doc du lieu cua tat ca nguoi
        dung nen phai o lai trong tien trinh backend.

        Ban cai dat phai lat trang: so job `running` khong co tran tren.
        """
        ...

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        """
        Ghi track, hoac TRA VE track da co neu trung `(chapter_id, content_hash)`.

        TIM-HOAC-TAO chu khong phai luon tao moi. Day la thu lam cho viec chay
        lai mot job tro nen VO HAI: hai worker cung xu ly mot job se cho ra cung
        `content_hash` va cung `object_key` (khoa la tat dinh), nen ban thu hai
        chi nhan lai track cua ban thu nhat thay vi tao them mot ban ghi.

        Nho vay tinh dung dan cua recovery KHONG phu thuoc vao lease. Lease chi
        de tranh lam viec thua.

        KHONG bao gio ghi de track da co: ban ghi cu duoc tra ve nguyen ven.
        """
        ...
    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]: ...
    def tracks_for_chapter(self, chapter_id: str) -> List[AudioTrack]: ...

    def audio_by_chapter(self, chapter_ids: Sequence[str]) -> Dict[str, AudioStamp]:
        """
        Chuong nao DA co audio, va dau van tay cua audio moi nhat.

        Tra ve `{chapter_id: AudioStamp cua track moi nhat}`. Chuong khong co
        audio thi khong xuat hien trong ket qua.

        Ly do ton tai: danh sach chuong can hai dieu — co audio hay khong, va
        audio con khop noi dung hien tai hay khong. Hoi tung chuong mot lam so
        truy van tang tuyen tinh theo so chuong. Ban cai dat PHAI tra loi bang
        so truy van khong phu thuoc so chuong (hang so, hoac theo lo) — day la
        ca ly do ky thuat cua ham nay.

        MOT truy van cho ca hai dieu, khong phai hai truy van.

        - Danh sach rong -> tra ve dict rong, KHONG duoc goi kho.
        - Khong tra ve URL ky: trang danh sach chua phat gi ca.
        """
        ...

    def delete_track(self, track_id: str) -> None: ...


# -----------------------------------------------------------------------------
# Ban mock: danh tinh
# -----------------------------------------------------------------------------


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}\x1f{password}".encode("utf-8")).hexdigest()


class MockIdentityAdapter:
    """
    Danh tinh trong bo nho - CHI dung cho phat trien cuc bo.

    Mat khau duoc bam kem salt (khong luu dang thuong), nhung day KHONG phai
    giai phap production: khong co rate limit, khong xac minh email, token
    khong het han. Ban that phai la Appwrite.
    """

    mode = "mock"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._profiles: Dict[str, Profile] = {}      # user_id -> Profile
        self._by_email: Dict[str, str] = {}          # email -> user_id
        self._passwords: Dict[str, tuple] = {}       # user_id -> (salt, hash)
        self._tokens: Dict[str, str] = {}            # token -> user_id
        self._oauth_tokens: Dict[str, str] = {}      # secret dung-1-lan -> user_id

    def register(self, email: str, password: str, display_name: str = "") -> Profile:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise AuthError("Email không hợp lệ.")
        if len(password or "") < 8:
            raise AuthError("Mật khẩu phải có ít nhất 8 ký tự.")
        with self._lock:
            if email in self._by_email:
                raise AuthError("Email này đã được đăng ký.")
            user_id = new_id("usr")
            salt = os.urandom(16).hex()
            self._passwords[user_id] = (salt, _hash_password(password, salt))
            profile = Profile(user_id=user_id, email=email, display_name=display_name)
            self._profiles[user_id] = profile
            self._by_email[email] = user_id
            return profile

    def login(self, email: str, password: str) -> str:
        email = (email or "").strip().lower()
        with self._lock:
            user_id = self._by_email.get(email)
            if user_id is None:
                raise AuthError("Email hoặc mật khẩu không đúng.")
            salt, expected = self._passwords[user_id]
            if _hash_password(password or "", salt) != expected:
                raise AuthError("Email hoặc mật khẩu không đúng.")
            token = new_id("tok")
            self._tokens[token] = user_id
            return token

    def profile_from_token(self, token: str) -> Profile:
        with self._lock:
            user_id = self._tokens.get((token or "").strip())
            if user_id is None:
                raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            return self._profiles[user_id]

    def logout(self, token: str) -> bool:
        """Xem contract o `IdentityAdapter.logout`."""
        with self._lock:
            return self._tokens.pop((token or "").strip(), None) is not None

    # -- OAuth ---------------------------------------------------------------

    def oauth_start_url(self, provider: str, success: str, failure: str) -> str:
        """
        Xem contract o `IdentityAdapter`.

        Mang CA `success` lan `failure` y nhu ban that, du ban mock khong dung
        toi `failure`: bo test kiem duoc route co truyen du hai duong hay
        khong, va mot ban gia lam roi tham so se lam phep kiem do thanh vo
        nghia ma van xanh.
        """
        from urllib.parse import urlencode

        query = urlencode({"success": success, "failure": failure})
        return f"https://mock-oauth.invalid/{provider}?{query}"

    def seed_oauth_token(self, user_id: str, secret: str) -> None:
        """
        CHI DANH CHO TEST: gia lap mot cap dung-mot-lan ma Appwrite se cap.

        Khong nam trong `IdentityAdapter` — day khong phai hanh vi cua ban
        that, chi la cach dung san boi canh cho bo test.
        """
        with self._lock:
            self._oauth_tokens[secret] = user_id

    def exchange_oauth_token(self, user_id: str, secret: str) -> str:
        """Xem contract o `IdentityAdapter`."""
        user_id = (user_id or "").strip()
        secret = (secret or "").strip()
        if not user_id or not secret:
            raise AuthError("Thiếu thông tin đăng nhập từ nhà cung cấp.")
        with self._lock:
            # `pop` chu khong phai `get`: cap nay dung MOT LAN. Dung lai lan hai
            # phai hong — neu khong, mot secret lot ra ngoai (lich su trinh
            # duyet, log proxy) van con doi duoc thanh phien.
            owner = self._oauth_tokens.pop(secret, None)
            if owner is None or owner != user_id:
                raise AuthError("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            token = new_id("tok")
            self._tokens[token] = user_id
            return token

    def ensure_profile(self, profile: Profile) -> Profile:
        """Xem contract o `IdentityAdapter`. TIM-HOAC-TAO, khong ghi de."""
        with self._lock:
            existing = self._profiles.get(profile.user_id)
            if existing is not None:
                return existing
            self._profiles[profile.user_id] = profile
            if profile.email:
                self._by_email.setdefault(profile.email, profile.user_id)
            return profile


# -----------------------------------------------------------------------------
# Ban mock: luu tru
# -----------------------------------------------------------------------------


class LocalStorageAdapter:
    """
    Luu file xuong dia cuc bo, thay cho R2 khi chua co credential.

    Ghi ra file tam roi doi ten (atomic) de khong bao gio de lai file do dang.
    """

    mode = "mock"

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Chan duong dan vuot ra ngoai thu muc goc
        safe = key.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError(f"Object key không hợp lệ: {key}")
        return self._root / safe

    def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with open(tmp, "wb") as fp:
            fp.write(data)
        os.replace(tmp, target)
        return key

    def put_file(self, key: str, source: Path) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)
        return key

    def get(self, key: str) -> bytes:
        target = self._path(key)
        if not target.is_file():
            raise NotFoundError(f"Không tìm thấy file: {key}")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def list_objects(self, prefix: str = "") -> Iterator[StoredObject]:
        """Di het cay thu muc. Bo qua file `.part` dang ghi do dang."""
        if not self._root.is_dir():
            return
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.name.endswith(".part"):
                continue
            key = path.relative_to(self._root).as_posix()
            if prefix and not key.startswith(prefix):
                continue
            stat = path.stat()
            yield StoredObject(
                key=key,
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
            )

    def size(self, key: str) -> int:
        target = self._path(key)
        return target.stat().st_size if target.is_file() else 0

    def delete(self, key: str) -> bool:
        target = self._path(key)
        if not target.is_file():
            return False
        target.unlink()
        return True

    def signed_url(self, key: str, expires_seconds: int = 3600,
                   download_name: Optional[str] = None) -> Optional[str]:
        """
        Ban cuc bo khong co URL ky san.

        Tra None de tang tren biet phai stream qua backend. Khi doi sang R2,
        ham nay se tra URL ky that va tang tren khong can doi.
        """
        return None


# -----------------------------------------------------------------------------
# Ban mock: metadata
# -----------------------------------------------------------------------------


class MockMetadataStore:
    """
    Kho metadata trong bo nho: profiles, novels, chapters, tts_jobs, audio_tracks.

    Moi truy van deu kiem tra QUYEN SO HUU - dung mo hinh phan quyen ma Appwrite
    se ap dung o ban that.

    KHONG PHAI kho ben vung. Du lieu chi song trong vong doi tien trinh: khoi
    dong lai backend la mat sach. Chi dung cho phat trien va kiem thu cuc bo.
    """

    def __init__(self) -> None:
        #: (owner, chapter, fingerprint) -> job_id. Ban trong bo nho cua
        #: hang khoa `job_locks` ben Appwrite.
        self._job_locks: Dict[Tuple[str, str, str], str] = {}

        #: Khoa cua ban mock la mot `threading.RLock` trong cung tien trinh:
        #: no khong the "chua duoc tao" hay hong vi mang. Khai bao tuong minh
        #: `True` de `/api/health` o che do mock khong bao "chua biet" mot
        #: cach vo co — day la mot su that ve kien truc, khong phai lac quan.
        self._job_lock_ready = True
        self._lock = threading.RLock()
        self.novels: Dict[str, Novel] = {}
        self.chapters: Dict[str, Chapter] = {}
        self.jobs: Dict[str, TtsJob] = {}
        self.tracks: Dict[str, AudioTrack] = {}
        #: `(job_id, attempt)` da co worker nhan. Vai tro y het tinh duy nhat cua
        #: rowId ben Appwrite: mot lan thu chi mot worker duoc nhan.
        self._claims: Set[Tuple[str, int]] = set()

    # -- novel ---------------------------------------------------------------

    def create_novel(self, novel: Novel) -> Novel:
        with self._lock:
            self.novels[novel.novel_id] = novel
            return novel

    def get_novel(self, novel_id: str) -> Novel:
        novel = self.novels.get(novel_id)
        if novel is None:
            raise NotFoundError("Không tìm thấy tiểu thuyết.")
        return novel

    def owned_novel(self, novel_id: str, owner_id: str) -> Novel:
        novel = self.get_novel(novel_id)
        if novel.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tiểu thuyết này.")
        return novel

    def list_novels(self, owner_id: Optional[str] = None, published_only: bool = False) -> List[Novel]:
        items, _ = self.find_novels(owner_id=owner_id, published_only=published_only)
        return items

    def find_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False, query: str = "",
                    tag: str = "", limit: Optional[int] = None,
                    offset: int = 0) -> Tuple[List[Novel], int]:
        """Xem contract o `MetadataStore.find_novels`."""
        with self._lock:
            items = list(self.novels.values())
        if owner_id:
            items = [n for n in items if n.owner_id == owner_id]
        if published_only:
            items = [n for n in items if n.state.value == "published"]
        if tag:
            items = [n for n in items if tag in n.tags]
        needle = query.strip().casefold()
        if needle:
            items = [n for n in items
                     if needle in n.title.casefold()
                     or needle in (n.description or "").casefold()]

        items.sort(key=lambda n: n.created_at, reverse=True)
        total = len(items)
        start = max(0, offset)
        page = items[start:] if limit is None else items[start:start + max(0, limit)]
        return page, total

    def novel_tags(self, published_only: bool = True) -> List[str]:
        with self._lock:
            items = list(self.novels.values())
        if published_only:
            items = [n for n in items if n.state.value == "published"]
        tags = {t for n in items for t in n.tags if t}
        return sorted(tags, key=lambda t: t.casefold())

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Xuat ban novel - xem contract o `MetadataStore.publish_novel`.

        Dung `replace()` roi moi gan lai vao kho, thay vi doi tai cho: neu co
        loi xay ra giua chung thi ban ghi dang luu VAN NGUYEN VEN, khong bao
        gio ket o trang thai nua voi. Day cung la cach ban Appwrite hanh xu
        (PATCH thanh cong hoac khong doi gi ca).
        """
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            # Idempotent: da `published` thi khong co gi de doi
            if current.state == PublishState.PUBLISHED:
                return current
            published = replace(
                current, state=PublishState.PUBLISHED, updated_at=now_iso()
            )
            self.novels[published.novel_id] = published
            return published

    #: Chi nhung truong nay moi cho nguoi dung sua. `state`, `owner_id`,
    #: `novel_id` deu do SERVER quyet dinh.
    NOVEL_EDITABLE = ("title", "description", "tags")

    def update_novel(self, novel_id: str, owner_id: str,
                     fields: Dict[str, Any]) -> Novel:
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.NOVEL_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.novels[novel_id] = updated
            return updated

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            if current.state != PublishState.PUBLISHED:
                return current
            reverted = replace(
                current, state=PublishState.DRAFT, updated_at=now_iso()
            )
            self.novels[novel_id] = reverted
            return reverted

    def delete_novel(self, novel_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_novel(novel_id, owner_id)
            self.novels.pop(novel_id, None)

    # -- chapter -------------------------------------------------------------

    #: `owner_id`, `novel_id`, `state` khong cho client sua.
    CHAPTER_EDITABLE = ("title", "content", "order_index")

    def update_chapter(self, chapter_id: str, owner_id: str,
                       fields: Dict[str, Any]) -> Chapter:
        with self._lock:
            current = self.owned_chapter(chapter_id, owner_id)
            allowed = {k: v for k, v in fields.items() if k in self.CHAPTER_EDITABLE}
            updated = replace(current, **allowed, updated_at=now_iso())
            self.chapters[chapter_id] = updated
            return updated

    def delete_chapter(self, chapter_id: str, owner_id: str) -> None:
        with self._lock:
            self.owned_chapter(chapter_id, owner_id)
            self.chapters.pop(chapter_id, None)

    def reorder_chapters(self, novel_id: str, owner_id: str,
                         chapter_ids: Sequence[str]) -> List[Chapter]:
        """Xem contract o `MetadataStore.reorder_chapters`."""
        self.owned_novel(novel_id, owner_id)
        with self._lock:
            current = {c.chapter_id for c in self.chapters.values()
                       if c.novel_id == novel_id}
            wanted = list(dict.fromkeys(chapter_ids))
            if set(wanted) != current or len(wanted) != len(chapter_ids):
                raise ValueError(
                    "Danh sách thứ tự phải gồm đúng các chương của truyện này.")

            # Ghi sau khi da kiem tra xong: sai mot cai thi khong doi gi ca.
            #
            # KHONG dong vao `updated_at`: sap xep lai khong sua noi dung chuong,
            # ma `updated_at` chinh la moc dung de biet audio con khop noi dung
            # hay khong (xem `_audio_outdated` trong main.py). Bump o day thi moi
            # chuong deu bi bao "audio cu" oan sau mot lan keo thu tu.
            for position, chapter_id in enumerate(wanted, start=1):
                chapter = self.chapters[chapter_id]
                self.chapters[chapter_id] = replace(chapter, order_index=position)
            return [self.chapters[cid] for cid in wanted]

    def create_chapter(self, chapter: Chapter) -> Chapter:
        with self._lock:
            self.chapters[chapter.chapter_id] = chapter
            return chapter

    def get_chapter(self, chapter_id: str) -> Chapter:
        chapter = self.chapters.get(chapter_id)
        if chapter is None:
            raise NotFoundError("Không tìm thấy chương.")
        return chapter

    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        if chapter.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu chương này.")
        return chapter

    def list_chapters(self, novel_id: str) -> List[Chapter]:
        with self._lock:
            items = [c for c in self.chapters.values() if c.novel_id == novel_id]
        return sorted(items, key=lambda c: c.order_index)

    def chapters_for_owner(self, owner_id: str) -> List[Chapter]:
        """Xem contract o `MetadataStore.chapters_for_owner`."""
        with self._lock:
            items = [c for c in self.chapters.values() if c.owner_id == owner_id]
        return sorted(items, key=lambda c: (c.novel_id, c.order_index))

    # -- job -----------------------------------------------------------------

    def create_job(self, job: TtsJob) -> TtsJob:
        """Ghi job lan dau - day chinh la luc trang thai `pending` duoc luu."""
        with self._lock:
            self.jobs[job.job_id] = job
            return job

    def create_job_once(self, job: TtsJob, fingerprint: str) -> Tuple[TtsJob, bool]:
        """Xem contract o `MetadataStore.create_job_once`."""
        khoa = (job.owner_id, job.chapter_id, fingerprint)
        with self._lock:
            # `self._lock` o day dong vai tro cua transaction ben Appwrite: hai
            # request khong the cung di qua doan nay.
            chu_cu = self._job_locks.get(khoa)
            if chu_cu is not None:
                da_co = self.jobs.get(chu_cu)
                # Job THAT BAI khong giu khoa nua: nguoi dung phai thu lai
                # duoc. `find_job_by_fingerprint` cung bo qua `failed` vi dung
                # ly do do — khoa ma chat hon no thi bam "Thử lại" se khong bao
                # gio tao duoc gi.
                #
                # Khoa mo coi (job da bi xoa) cung roi vao day.
                if da_co is not None and da_co.status != JobStatus.FAILED:
                    return da_co, False
            self._job_locks[khoa] = job.job_id

        # Ghi QUA `create_job()`, khong ghi thang vao `self.jobs`: cac test
        # double ke thua lop nay va ghi de `create_job` de theo doi thu tu ghi.
        # Ghi thang se di vong qua ho, va ban ghi `pending` bien mat khoi so
        # theo doi cua ho ma khong ai thay.
        return self.create_job(job), True

    def save_job(self, job: TtsJob) -> TtsJob:
        """
        Ghi lai trang thai job sau moi transition.

        Ban mock luu cung mot doi tuong nen thao tac nay "co ve" thua - nhung
        `AppwriteMetadataStore.save_job()` moi la ban that: khong goi thi moi
        thay doi trang thai deu bien mat khi doc lai tu Appwrite. Giu chung
        mot giao dien de job runner khong phai biet dang chay che do nao.
        """
        with self._lock:
            self.jobs[job.job_id] = job
            return job

    def get_job(self, job_id: str) -> TtsJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise NotFoundError("Không tìm thấy job.")
        return job

    def owned_job(self, job_id: str, owner_id: str) -> TtsJob:
        job = self.get_job(job_id)
        if job.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job này.")
        return job

    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str, fingerprint: str) -> Optional[TtsJob]:
        """Tim job da co cho CUNG noi dung + giong + thiet lap (idempotency)."""
        with self._lock:
            for job in self.jobs.values():
                if (
                    job.owner_id == owner_id
                    and job.chapter_id == chapter_id
                    and job.content_hash == fingerprint
                    and job.status.value != "failed"
                ):
                    return job
        return None

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None) -> List[TtsJob]:
        with self._lock:
            items = [j for j in self.jobs.values() if j.owner_id == owner_id]
        if chapter_id:
            items = [j for j in items if j.chapter_id == chapter_id]
        return sorted(items, key=lambda j: j.created_at, reverse=True)

    def job_settings(self, owner_id: str,
                     fingerprints: Sequence[str]) -> Dict[str, Tuple[str, int]]:
        """Xem contract o `MetadataStore.job_settings`."""
        wanted = set(fingerprints)
        if not wanted:
            return {}
        out: Dict[str, Tuple[str, int]] = {}
        with self._lock:
            for job in self.jobs.values():
                if job.owner_id != owner_id or job.content_hash not in wanted:
                    continue
                out.setdefault(job.content_hash, (job.rate, job.chunk_chars))
        return out

    def claim_job(self, job: TtsJob, worker_id: str,
                  lease_expires_at: str) -> Optional[int]:
        """
        Xem contract o `MetadataStore.claim_job`.

        Trong bo nho thi `self._lock` chinh la thu cuong che tinh duy nhat: ca
        khoi kiem-va-ghi nam gon trong mot lan giu khoa, khong the xen ngang.
        """
        with self._lock:
            current = self.jobs.get(job.job_id)
            if current is None or current.status.is_terminal:
                return None
            if current.lease_is_live():
                # KE CA khi `lease_owner == worker_id`. Xem contract: tu nhan lai
                # job cua chinh minh la duong dan toi hai thread cung tong hop
                # mot chuong.
                return None
            fence = (current.attempts or 0) + 1
            key = (job.job_id, fence)
            if key in self._claims:
                return None            # da co worker khac nhan dung lan thu nay
            self._claims.add(key)
            self.jobs[job.job_id] = replace(
                current, status=JobStatus.RUNNING, attempts=fence,
                lease_owner=worker_id, lease_expires_at=lease_expires_at,
            )
            return fence

    def renew_lease(self, job_id: str, fence: int, worker_id: str,
                    lease_expires_at: str) -> bool:
        """Xem contract o `MetadataStore.renew_lease`."""
        with self._lock:
            current = self.jobs.get(job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            # CHI hai truong lease. `replace` tren ban ghi DANG CO trong kho, chu
            # khong phai tren mot ban sao cua nguoi goi.
            self.jobs[job_id] = replace(current,
                                        lease_expires_at=lease_expires_at,
                                        lease_owner=worker_id)
            return True

    def save_progress(self, job_id: str, fence: int, worker_id: str,
                      done_parts: int, total_parts: int) -> bool:
        """Xem contract o `MetadataStore.save_progress`."""
        with self._lock:
            current = self.jobs.get(job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            # CHI hai truong tien do, tren ban ghi DANG CO trong kho.
            self.jobs[job_id] = replace(current,
                                        done_parts=max(0, int(done_parts)),
                                        total_parts=max(0, int(total_parts)))
            return True

    def save_job_fenced(self, job: TtsJob, fence: int, worker_id: str) -> bool:
        """Xem contract o `MetadataStore.save_job_fenced`."""
        with self._lock:
            current = self.jobs.get(job.job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            self.jobs[job.job_id] = replace(job, attempts=fence)
            return True

    def list_jobs_by_status(self, status: JobStatus) -> List[TtsJob]:
        """Xem contract o `MetadataStore.list_jobs_by_status`."""
        with self._lock:
            items = [j for j in self.jobs.values() if j.status is status]
        return sorted(items, key=lambda j: j.created_at)

    def delete_job(self, job_id: str) -> None:
        """Xoa job VA so ghi chep claim cua no — xem contract o Appwrite."""
        with self._lock:
            self.jobs.pop(job_id, None)
            self._claims = {k for k in self._claims if k[0] != job_id}

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        """TIM-HOAC-TAO — xem contract o `MetadataStore.create_track`."""
        with self._lock:
            for existing in self.tracks.values():
                if (existing.chapter_id == track.chapter_id
                        and existing.content_hash == track.content_hash):
                    return existing
            self.tracks[track.track_id] = track
            return track

    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]:
        with self._lock:
            items = [t for t in self.tracks.values() if t.chapter_id == chapter_id]
        return sorted(items, key=lambda t: t.created_at, reverse=True)[0] if items else None

    def tracks_for_chapter(self, chapter_id: str) -> List[AudioTrack]:
        with self._lock:
            return [t for t in self.tracks.values() if t.chapter_id == chapter_id]

    def audio_by_chapter(self, chapter_ids: Sequence[str]) -> Dict[str, AudioStamp]:
        """Mot luot duy nhat qua bang track — xem contract o `MetadataStore`."""
        wanted = set(chapter_ids)
        if not wanted:
            return {}
        newest: Dict[str, AudioStamp] = {}
        with self._lock:
            for track in self.tracks.values():
                if track.chapter_id not in wanted:
                    continue
                seen = newest.get(track.chapter_id)
                if seen is not None and track.created_at <= seen.created_at:
                    continue
                newest[track.chapter_id] = AudioStamp(
                    created_at=track.created_at,
                    content_hash=track.content_hash,
                    voice_id=track.voice_id,
                )
        return newest

    def delete_track(self, track_id: str) -> None:
        with self._lock:
            self.tracks.pop(track_id, None)


# -----------------------------------------------------------------------------
# Lua chon adapter theo cau hinh
# -----------------------------------------------------------------------------


def build_identity(settings: Settings) -> IdentityAdapter:
    """
    Chon adapter danh tinh theo DATA_BACKEND (tuong minh).

    `appwrite` ma thieu/sai cau hinh thi NEM LOI - tuyet doi khong am tham lui
    ve mock, vi nguoi van hanh se tuong dang chay that.
    """
    if settings.data_backend == "appwrite":
        from server.appwrite_adapter import AppwriteIdentityAdapter

        return AppwriteIdentityAdapter(settings.appwrite)
    if settings.data_backend != "mock":
        raise ConfigError(f"DATA_BACKEND không hợp lệ: {settings.data_backend!r}")
    return MockIdentityAdapter()


def build_storage(settings: Settings) -> StorageAdapter:
    """Chon adapter luu tru theo STORAGE_BACKEND (tuong minh)."""
    if settings.storage_backend == "r2":
        from server.r2_adapter import R2StorageAdapter

        return R2StorageAdapter(settings.r2)
    if settings.storage_backend != "local":
        raise ConfigError(f"STORAGE_BACKEND không hợp lệ: {settings.storage_backend!r}")
    return LocalStorageAdapter(settings.var_dir / "storage")


def build_metadata_store(settings: Settings) -> MetadataStore:
    """Kho metadata: Appwrite khi DATA_BACKEND=appwrite, nguoc lai trong bo nho."""
    if settings.data_backend == "appwrite":
        from server.appwrite_store import AppwriteMetadataStore

        return AppwriteMetadataStore(settings.appwrite)
    return MockMetadataStore()
