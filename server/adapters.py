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
    AN_DANH_DA_XOA,
    AccountSession,
    AccountStatus,
    AudioStamp,
    AudioTrack,
    AuthorApplication,
    AuthorStats,
    AuthorStatus,
    Chapter,
    JobStatus,
    ListenCredit,
    ModerationEvent,
    Novel,
    Profile,
    PublishState,
    TtsJob,
    bao_cao_xoa_tai_khoan,
    new_id,
    now_iso,
)
from server.social_store import MockSocialStore


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


class AppwriteUnavailableError(AuthError):
    """
    Khong ket noi duoc Appwrite (mang loi/DNS/timeout/host chet) - KHAC voi
    sai thong tin dang nhap hay phien het han.

    La CON cua `AuthError` (khong phai loai moi hoan toan) de code cu bat
    `except AuthError` van bat duoc no va khong crash - nhung noi nao CAN
    phan biet "backend phu thuoc dang gian doan" (503, loi tam thoi, thu lai
    duoc) voi "nguoi dung sai thong tin" (401/400, loi vinh vien cho toi khi
    ho sua) PHAI bat lop nay TRUOC `AuthError`. Xem `server/appwrite_adapter.py`
    (`_request`) noi no duoc nem, va `server/main.py` noi no duoc bat.
    """


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

    # -- Quan ly tai khoan (Phase 3, Admin Control Center V2) ----------------
    #
    # Nam TACH BACH voi cac ham "ho so cong khai" ben duoi (`search_profiles`,
    # `profiles_by_ids`...): nhung ham do doc bang `profiles` do CHINH backend
    # ghi, con day la NGUYEN LIEU tu thang Appwrite Auth — mot nguon du lieu
    # KHAC, khong co ban sao trong `profiles` va khong bao gio nen co.

    def list_accounts(self, query: str = "", limit: int = 25,
                      offset: int = 0) -> Tuple[List[AccountStatus], int]:
        """
        Danh sach TAI KHOAN (native), phan trang o MAY CHU — nguon cho
        `/api/admin/users`.

        KHAC voi `search_profiles`: tra ve MOI tai khoan da dang ky, ke ca
        nguoi CHUA chon username/chua co ho so cong khai. Day la quan ly TAI
        KHOAN (ai co the dang nhap), khong phai danh ba cong khai — mot tai
        khoan spam moi tao, chua kip chon ten, van phai hien o day de quan tri
        xu ly duoc.
        """
        ...

    def account_status(self, user_id: str) -> Optional[AccountStatus]:
        """Trang thai tai khoan cua MOT user_id. `None` neu khong ton tai."""
        ...

    def list_sessions(self, user_id: str) -> List[AccountSession]:
        """Danh sach phien dang nhap DANG SONG cua mot tai khoan."""
        ...

    def terminate_session(self, user_id: str, session_id: str) -> bool:
        """
        Cham dut MOT phien. Tra True neu vua huy that, False neu phien do von
        da khong con (IDEMPOTENT — cung tinh than voi `logout`).
        """
        ...

    def terminate_all_sessions(self, user_id: str) -> int:
        """Cham dut MOI phien cua mot tai khoan. Tra ve SO PHIEN da huy."""
        ...

    def set_account_enabled(self, user_id: str, enabled: bool) -> Optional[AccountStatus]:
        """
        Bat/khoa dang nhap cua MOT tai khoan. `enabled=False` chan MOI duong
        dang nhap (email lan OAuth) — TACH BACH voi treo tac gia
        (`CreatorService.suspend`, chi chan xuat ban). Tra `None` neu khong
        tim thay tai khoan.
        """
        ...

    def count_accounts(self, *, email_verified: Optional[bool] = None,
                       enabled: Optional[bool] = None) -> int:
        """
        Dem tai khoan theo dieu kien, BI CHAN (`limit(1)` + doc `total`, khong
        keo ban ghi) — dung cho o "verified/unverified/suspended" o bang dieu
        khien (Admin Control Center V2, A1). Bo trong ca hai tham so = tong so
        tai khoan.
        """
        ...

    def delete_account(self, user_id: str) -> bool:
        """
        Xoa DANH TINH cua mot nguoi dung: ban ghi `profiles` VA tai khoan Auth.

        Day la BUOC CUOI CUNG cua `AccountDeletionService.delete_account` — moi
        du lieu ung dung phai bi don TRUOC. Neu lam nguoc lai (xoa danh tinh
        truoc) va mot buoc sau hong, ta con lai truyen/chuong/job khong con chu:
        khong route nao doi lai duoc, va nguoi dung cung khong con duong nao
        goi lai de don not.

        IDEMPOTENT: tai khoan von khong con thi tra `False`, KHONG nem. Mot
        request bi thu lai (hoac bam hai lan) khong duoc thanh 500.

        Tra `True` neu that su vua xoa mot tai khoan dang ton tai.
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

    def set_novel_cover(self, novel_id: str, owner_id: str,
                        cover_key: Optional[str]) -> Novel:
        """
        Dat/xoa khoa anh bia. TACH khoi `update_novel`.

        `NOVEL_EDITABLE` cua `update_novel` la danh sach TRUONG NGUOI DUNG GO
        TAY (title/description/tags) — mo them `cover_key` vao do se cho phep
        mot request PATCH gan khoa cua BAT KY object nao trong R2 lam bia
        truyen, ke ca object khong phai anh hay khong thuoc ve minh. `cover_key`
        chi duoc may chu tinh RA sau khi tu upload va kiem tra, nen no can
        duong ghi rieng, khong di qua duong nhan du lieu tho tu client.
        """
        ...

    def unpublish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """Dua truyen ve ban nhap VA thu hoi quyen doc cong khai. Idempotent."""
        ...

    def delete_novel(self, novel_id: str, owner_id: str) -> None: ...

    # -- chapter -------------------------------------------------------------
    def create_chapter(self, chapter: Chapter) -> Chapter: ...

    def create_chapter_once(self, chapter: Chapter) -> Tuple[Chapter, bool]:
        """
        TAO-HOAC-LAY theo `chapter.chapter_id`. Tra `(chuong, vua_tao)`.

        VI SAO CAN: nhap chuong hang loat (`server/bulk_import_service.py`) dat
        `chapter_id` TAT DINH cho tung muc, roi dua vao tinh duy nhat cua
        `documentId` ben Appwrite de "tao chuong xong roi chet TRUOC KHI kip ghi
        id vao muc" KHONG sinh ra chuong trung — lan chay sau tao lai dung id do
        va nhan ve ban da co.

        Kiem tra "chapter_id da co chua roi moi tao" KHONG thay the duoc cho nay:
        giua doc va ghi van con mot khe ho, va do la dung khe ho ma mot dot nhap
        500 chuong se roi vao it nhat mot lan.

        `vua_tao=False` PHAI ngan moi tac dung phu chi duoc phep chay mot lan
        (thong bao nguoi theo doi, thuong XP) — xem `_tao_chuong_cho_truyen`.

        KHONG BAO GIO ghi de ban da co: noi dung tac gia da sua bang tay thang
        noi dung trong lo nhap.
        """
        ...

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

    def jobs_by_ids(self, job_ids: Sequence[str]) -> Dict[str, TtsJob]:
        """
        Nhieu job trong SO TRUY VAN KHONG PHU THUOC so job — cung hop dong voi
        `novels_by_ids`/`chapter_counts`.

        VI SAO CAN: bo dieu phoi nhap hang loat phai doi soat trang thai cua moi
        muc `job_queued` MOI chu ky quet (3 giay). Goi `get_job` cho tung muc la
        mot request Appwrite moi muc moi chu ky — dung hinh dang N+1 da bi bo o
        cac trang khac, va o day no dap vao han muc doc that.

        Id khong ton tai thi VANG MAT trong ket qua, khong nem loi: job co the
        da bi xoa cung chuong (`_purge_chapter`), va do la mot trang thai hop le
        ma nguoi goi phai xu ly duoc.
        """
        ...

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

    # -- xoa tai khoan --------------------------------------------------------

    def delete_account(self, user_id: str) -> Dict[str, Any]:
        """
        Don MOI du lieu cua mot nguoi dung trong kho nay — mot buoc cua
        `AccountDeletionService.delete_account`, KHONG phai ca viec xoa tai
        khoan (gamification, ban dich va danh tinh nam o kho khac).

        XOA HET (noi dung cua chinh nguoi dung, khong ai khac co quyen tren no
        — KE CA truyen/chuong DA XUAT BAN dang co nguoi doc. Do la mot QUYET
        DINH SAN PHAM da chot, khong phai mot thieu sot: ta KHONG co co che
        "tac gia thay the" hay bia mo `[da xoa]`, va giu lai noi dung cua mot
        nguoi da yeu cau xoa tai khoan thi loi hua "xoa" khong con dung):
          novels, chapters, tts_jobs (+ job_claims/job_locks cua chung),
          audio_tracks, posts, comments, post_likes, notifications cua chinh
          ho, user_follows (CA HAI CHIEU — mot canh theo doi tro toi tai khoan
          khong con la mot lien ket vo hieu trong danh sach cua nguoi khac),
          story_follows do ho tao, author_stats.

        GIU NGUYEN, KHONG DUOC DONG TOI:
          - `moderation_events` — CHI THEM o moi tang, ke ca hang co nguoi nay
            la actor hay target. Mot nhat ky sua duoc la mot nhat ky vo dung.
          - `listen_credits` ma nguoi nay la NGUOI NGHE (`listener_id`): hang
            do da tinh vao uy tin cua MOT TAC GIA KHAC. Xoa chung la lam tut
            thanh tich cua nguoi khong lien quan.

        GIU HANG NHUNG AN DANH van ban nhan dang (`domain.AN_DANH_DA_XOA`):
          - `author_applications` — giu `status`/`decided_at`/`reviewer_note`
            (lich su quyet dinh cua nguoi duyet) va giu ca `user_id` de con
            truy vet duoc; chi thay `pen_name`/`bio`/`intro`.
          - `content_reports` ma nguoi nay la NGUOI BAO (`reporter_id`) — bao
            cao la bang chung ve nguoi BI bao cao, xoa no la xoa bang chung.

        KHONG chay theo hang cua NGUOI KHAC tro toi noi dung vua xoa (luot
        thich/binh luan tren bai da xoa, theo doi truyen da xoa). Do la dung
        quy uoc san co cua kho nay: `SocialService.delete_post` va
        `DELETE /api/novels/{id}` cung de lai nhung hang do — chung khong con
        duong doc nao (moi truy van deu di qua post_id/novel_id da mat).

        Tra ve so hang da don theo tung bang, kem `object_keys`: khoa doi tuong
        trong kho tep (audio, phu de, bia truyen, anh bai dang) ma NGUOI GOI
        phai xoa — kho metadata khong biet gi ve R2, dung phan cong voi
        `main.py::_purge_chapter`.

        IDEMPOTENT: nguoi dung khong co du lieu nao thi tra ve cac so 0, KHONG
        nem — mot request bi thu lai khong duoc thanh 500.

        Rieng hai bo dem `*_anonymized` KHONG ve 0 giong nhau o lan goi thu hai,
        va do la HAI CO CHE TIM khac nhau chu khong phai mot lech:
          - don tac gia tim theo `rowId` (= `user_id`) nen lan hai VAN thay hang
            va ghi lai dung gia tri an danh (mot phep TU CHUA neu lan truoc hong
            nua duong) -> van dem 1;
          - bao cao tim theo `reporter_id`, ma truong do vua bi thay bang dau an
            danh, nen lan hai khong con hang nao khop -> dem 0.
        Ca hai duong deu ve CUNG mot trang thai cuoi.
        """
        ...


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
        #: token = session_id trong ban mock (xem `list_sessions`).
        self._session_created_at: Dict[str, str] = {}  # token -> ISO
        #: user_id bi KHOA dang nhap (Phase 3, Admin Control Center V2) — TACH
        #: BACH voi `Profile.author_status`, xem `AccountStatus`.
        self._disabled: Set[str] = set()

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
            # Kiem TAI KHOAN bi khoa SAU khi mat khau da dung — mot nguoi
            # khong biet mat khau khong duoc biet them "tai khoan nay dang bi
            # tam dung", cung ly do voi thong diep loi chung o tren.
            if user_id in self._disabled:
                raise AuthError("Tài khoản này đã bị tạm dừng.")
            token = new_id("tok")
            self._tokens[token] = user_id
            self._session_created_at[token] = now_iso()
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
            token = (token or "").strip()
            self._session_created_at.pop(token, None)
            return self._tokens.pop(token, None) is not None

    # -- ho so cong khai -----------------------------------------------------
    #
    # `username`, `bio`, `author_status` song CUNG CHO voi ho so, khong o mot
    # bang rieng: chung la thuoc tinh cua danh tinh, va tach ra thi moi lan doc
    # mot ho so lai la hai lan doc.

    def get_profile(self, user_id: str) -> Profile:
        with self._lock:
            profile = self._profiles.get(user_id)
            if profile is None:
                raise NotFoundError("Không tìm thấy hồ sơ.")
            return profile

    def save_profile(self, profile: Profile) -> Profile:
        """
        Ghi de ho so. Kiem TRUNG username ngay o day.

        Vi sao kiem o tang luu tru chu khong chi o route: day la cho duy nhat
        thay duoc TAT CA username, va mot cho goi quen kiem la du de hai nguoi
        cung mot ten. Ban Appwrite dat rang buoc nay bang mot index `unique`.
        """
        with self._lock:
            if profile.username:
                for khac in self._profiles.values():
                    if (khac.user_id != profile.user_id
                            and khac.username == profile.username):
                        raise AuthError("Tên người dùng này đã có người dùng.")
            self._profiles[profile.user_id] = profile
            return profile

    def profile_by_username(self, username: str) -> Optional[Profile]:
        ten = (username or "").strip().lower()
        if not ten:
            return None
        with self._lock:
            for profile in self._profiles.values():
                if profile.username == ten:
                    return profile
            return None

    def search_profiles(self, query: str, limit: int = 20,
                        offset: int = 0) -> Tuple[List[Profile], int]:
        """
        Tim theo ten hien thi VA username. Tra ve `(trang, tong)`.

        CHI nguoi da co username: chua chon username thi chua co trang cong
        khai, nen hien ho trong ket qua tim kiem la dua nguoi dung toi mot lien
        ket khong mo duoc.

        Sap xep TAT DINH (username tang dan) chu khong theo thu tu tu dien cua
        dict: phan trang tren mot thu tu khong on dinh thi trang 2 co the lap
        lai hoac bo sot ban ghi cua trang 1.
        """
        from server.creator import normalize_username

        can = normalize_username(query)
        tho = (query or "").strip().lower()
        with self._lock:
            khop = [
                p for p in self._profiles.values()
                if p.username
                and (not can
                     or can in p.username
                     or tho in (p.display_name or "").lower())
            ]
        khop.sort(key=lambda p: p.username)
        return khop[offset:offset + limit], len(khop)

    def healthcheck(self) -> bool:
        """Kho trong bo nho luon 'khoe' — chi de CUNG mot chu ky voi ban
        Appwrite (`AppwriteIdentityAdapter.healthcheck`) khi goi da hinh tu
        bang dieu khien quan tri (Admin Control Center V2, muc SYSTEM)."""
        return True

    def count_profiles(self, created_after: str = "") -> int:
        """Tong so ho so (MOI nguoi dung, khong loc theo username) — dung cho
        cac o "moi dang ky hom nay/7/30 ngay" o bang dieu khien (Admin
        Control Center V2, A1)."""
        with self._lock:
            if not created_after:
                return len(self._profiles)
            return sum(1 for p in self._profiles.values()
                      if p.created_at >= created_after)

    def all_usernames(self) -> List[str]:
        with self._lock:
            return [p.username for p in self._profiles.values() if p.username]

    # -- Quan ly tai khoan (Phase 3, Admin Control Center V2) ----------------
    #
    # Mock KHONG co xac minh email/dien thoai that: `email_verified` luon tra
    # `True` (khong ai o mock "chua xac minh"). Ghi ro dieu nay o TUNG ham thay
    # vi mot dong comment chung o dau, de ai doc mot ham rieng le van thay ngay.

    def _account_from_profile(self, p: Profile) -> AccountStatus:
        return AccountStatus(
            user_id=p.user_id, email=p.email, name=p.display_name,
            enabled=p.user_id not in self._disabled,
            email_verified=True, phone_verified=False,
            registered_at=p.created_at,
        )

    def list_accounts(self, query: str = "", limit: int = 25,
                      offset: int = 0) -> Tuple[List[AccountStatus], int]:
        tu = (query or "").strip().lower()
        with self._lock:
            khop = [
                p for p in self._profiles.values()
                if not tu or tu in p.email.lower()
                or tu in (p.display_name or "").lower()
            ]
            # Moi dang ky truoc len dau — cung thu tu voi `count_profiles`
            # "moi dang ky hom nay/7/30 ngay" o bang dieu khien. `user_id` la
            # nhan phu TAT DINH: hai tai khoan tao trong cung mot giay
            # (`now_iso()` cat o giay) khong duoc doi thu tu giua hai trang.
            khop.sort(key=lambda p: (p.created_at, p.user_id), reverse=True)
            trang = khop[offset:offset + limit]
            return [self._account_from_profile(p) for p in trang], len(khop)

    def account_status(self, user_id: str) -> Optional[AccountStatus]:
        with self._lock:
            profile = self._profiles.get(user_id)
            return self._account_from_profile(profile) if profile else None

    def list_sessions(self, user_id: str) -> List[AccountSession]:
        with self._lock:
            return [
                AccountSession(
                    session_id=tok, provider="email", ip="", os_name="",
                    client_name="", device_name="mock", country_name="",
                    current=False,
                    created_at=self._session_created_at.get(tok, ""),
                )
                for tok, uid in self._tokens.items() if uid == user_id
            ]

    def terminate_session(self, user_id: str, session_id: str) -> bool:
        with self._lock:
            if self._tokens.get(session_id) != user_id:
                return False
            del self._tokens[session_id]
            self._session_created_at.pop(session_id, None)
            return True

    def terminate_all_sessions(self, user_id: str) -> int:
        with self._lock:
            token_cua_ho = [t for t, uid in self._tokens.items() if uid == user_id]
            for tok in token_cua_ho:
                del self._tokens[tok]
                self._session_created_at.pop(tok, None)
            return len(token_cua_ho)

    def set_account_enabled(self, user_id: str, enabled: bool) -> Optional[AccountStatus]:
        with self._lock:
            if user_id not in self._profiles:
                return None
            if enabled:
                self._disabled.discard(user_id)
            else:
                self._disabled.add(user_id)
            return self._account_from_profile(self._profiles[user_id])

    def count_accounts(self, *, email_verified: Optional[bool] = None,
                       enabled: Optional[bool] = None) -> int:
        with self._lock:
            n = 0
            for uid in self._profiles:
                if email_verified is False:
                    # Mock luon coi MOI tai khoan la da xac minh — khong ai
                    # khop dieu kien "chua xac minh".
                    continue
                if enabled is not None and (uid not in self._disabled) != enabled:
                    continue
                n += 1
            return n

    def delete_account(self, user_id: str) -> bool:
        """
        Xem contract o `IdentityAdapter.delete_account`.

        Xoa ca MAT KHAU va MOI TOKEN cua nguoi do trong cung mot lan giu khoa.
        Bo sot token la mot lo that o ban mock: `profile_from_token` tra ve
        `self._profiles[user_id]`, nen mot token con sot lai tro toi ho so da
        mat se thanh `KeyError` (500) o moi request tiep theo, thay vi 401.
        """
        with self._lock:
            profile = self._profiles.pop(user_id, None)
            if profile is None:
                return False
            self._by_email.pop((profile.email or "").strip().lower(), None)
            self._passwords.pop(user_id, None)
            self._disabled.discard(user_id)
            for tok in [t for t, uid in self._tokens.items() if uid == user_id]:
                del self._tokens[tok]
                self._session_created_at.pop(tok, None)
            for secret in [s for s, uid in self._oauth_tokens.items()
                           if uid == user_id]:
                del self._oauth_tokens[secret]
            return True

    def profiles_by_ids(self, user_ids: Sequence[str]) -> Dict[str, Profile]:
        """
        Nhieu ho so trong MOT lan doc. Thieu ai thi khong co khoa do trong ket qua.

        Xem ban Appwrite de biet vi sao ham nay ton tai: khu quan tri tung goi
        `get_profile` cho tung hang, va do la mot vong mang moi hang.
        """
        with self._lock:
            return {uid: self._profiles[uid] for uid in dict.fromkeys(user_ids)
                    if uid in self._profiles}

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


class MockMetadataStore(MockSocialStore):
    """
    Kho metadata trong bo nho: profiles, novels, chapters, tts_jobs, audio_tracks.

    Phan XA HOI (theo doi, bai dang, thich, binh luan, thong bao, bao cao) o
    `server/social_store.py` — cung mot kho, tach tep vi do dai. Xem ghi chu dau
    tep do.

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

        #: Tac gia. MOT don moi nguoi dung — nop lai thi ghi de, xem
        #: `AuthorApplication`.
        self._applications: Dict[str, AuthorApplication] = {}
        self._stats: Dict[str, AuthorStats] = {}
        #: credit_id (tat dinh) -> ban ghi. Xem `create_credit_once`.
        self._credits: Dict[str, ListenCredit] = {}
        #: Nhat ky kiem duyet. CHI THEM, khong bao gio sua hay xoa.
        self._events: List[ModerationEvent] = []

        self._khoi_tao_xa_hoi()

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

    def set_novel_cover(self, novel_id: str, owner_id: str,
                        cover_key: Optional[str]) -> Novel:
        with self._lock:
            current = self.owned_novel(novel_id, owner_id)
            updated = replace(current, cover_key=cover_key, updated_at=now_iso())
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

    def create_chapter_once(self, chapter: Chapter) -> Tuple[Chapter, bool]:
        """Xem contract o `MetadataStore.create_chapter_once`. Mo phong dung
        hanh vi Appwrite tu choi `POST` trung `documentId`."""
        with self._lock:
            hien_co = self.chapters.get(chapter.chapter_id)
            if hien_co is not None:
                return hien_co, False
        # Ghi QUA `create_chapter()`, khong ghi thang vao `self.chapters`: cac
        # test double ke thua lop nay va ghi de `create_chapter` de theo doi
        # thu tu ghi — cung ly do voi `create_job_once`.
        return self.create_chapter(chapter), True

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

    def jobs_by_ids(self, job_ids: Sequence[str]) -> Dict[str, TtsJob]:
        """Xem contract o `MetadataStore.jobs_by_ids`."""
        wanted = {j for j in job_ids if j}
        if not wanted:
            return {}
        with self._lock:
            return {jid: job for jid, job in self.jobs.items() if jid in wanted}

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

    def total_jobs(self) -> int:
        with self._lock:
            return len(self.jobs)

    def count_jobs(self, *, status: Optional[JobStatus] = None,
                  created_after: str = "") -> int:
        """Bo dem cho bang dieu khien quan tri (Phase 7 analytics) — loc
        THEO status/ngay tao, khong keo document nao ve."""
        with self._lock:
            items = self.jobs.values()
            if status is not None:
                items = [j for j in items if j.status is status]
            if created_after:
                items = [j for j in items if j.created_at >= created_after]
            return len(list(items))

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

    # -- xoa tai khoan --------------------------------------------------------

    def delete_account(self, user_id: str) -> Dict[str, Any]:
        """Xem contract o `MetadataStore.delete_account` — ban Appwrite
        (`AppwriteMetadataStore.delete_account`) phai cho ket qua GIONG HET,
        va `test_account_deletion.py` chay cung mot kich ban qua ca hai."""
        bc = bao_cao_xoa_tai_khoan()
        if not user_id:
            return bc

        with self._lock:
            # -- noi dung: chuong (kem audio) roi truyen ----------------------
            for chapter in [c for c in self.chapters.values()
                            if c.owner_id == user_id]:
                for track in [t for t in self.tracks.values()
                              if t.chapter_id == chapter.chapter_id]:
                    bc["object_keys"] += [k for k in (track.object_key,
                                                      track.transcript_key) if k]
                    self.tracks.pop(track.track_id, None)
                    bc["audio_tracks"] += 1
                self.chapters.pop(chapter.chapter_id, None)
                bc["chapters"] += 1

            for novel in [n for n in self.novels.values()
                          if n.owner_id == user_id]:
                if novel.cover_key:
                    bc["object_keys"].append(novel.cover_key)
                self.novels.pop(novel.novel_id, None)
                bc["novels"] += 1

            # Job theo CHU SO HUU, khong theo chuong: bat ca job mo coi (chuong
            # da xoa truoc do bang duong khac) — `delete_job` don luon claim.
            for job in [j for j in self.jobs.values() if j.owner_id == user_id]:
                self.delete_job(job.job_id)
                bc["tts_jobs"] += 1
            self._job_locks = {k: v for k, v in self._job_locks.items()
                               if k[0] != user_id}

            # -- xa hoi -------------------------------------------------------
            for post in [p for p in self._posts.values()
                         if p.author_user_id == user_id]:
                bc["object_keys"] += [str(a.get("key") or "")
                                      for a in post.all_images()
                                      if a.get("key")]
                self._posts.pop(post.post_id, None)
                bc["posts"] += 1

            for cid in [c.comment_id for c in self._comments.values()
                        if c.author_user_id == user_id]:
                self._comments.pop(cid, None)
                bc["comments"] += 1

            for lid in [lk.like_id for lk in self._post_likes.values()
                        if lk.user_id == user_id]:
                self._post_likes.pop(lid, None)
                bc["post_likes"] += 1

            for fid in [f.follow_id for f in self._user_follows.values()
                        if user_id in (f.follower_id, f.target_id)]:
                self._user_follows.pop(fid, None)
                bc["user_follows"] += 1

            for fid in [f.follow_id for f in self._story_follows.values()
                        if f.follower_id == user_id]:
                self._story_follows.pop(fid, None)
                bc["story_follows"] += 1

            for nid in [n.notification_id for n in self._notifications.values()
                        if n.user_id == user_id]:
                self._notifications.pop(nid, None)
                bc["notifications"] += 1

            # -- uy tin tac gia -----------------------------------------------
            if self._stats.pop(user_id, None) is not None:
                bc["author_stats"] = 1

            # CHI phia TAC GIA. Hang ma nguoi nay la NGUOI NGHE o lai: chung da
            # tinh vao uy tin cua mot tac gia KHAC.
            for cid in [c.credit_id for c in self._credits.values()
                        if c.author_id == user_id]:
                self._credits.pop(cid, None)
                bc["listen_credits"] += 1

            # -- giu hang, an danh --------------------------------------------
            don = self._applications.get(user_id)
            if don is not None:
                don.pen_name = AN_DANH_DA_XOA
                don.bio = AN_DANH_DA_XOA
                don.intro = AN_DANH_DA_XOA
                bc["applications_anonymized"] = 1

            for report in [r for r in self._reports.values()
                           if r.reporter_id == user_id]:
                report.reporter_id = AN_DANH_DA_XOA
                bc["reports_anonymized"] += 1

        return bc


    # -- doc theo LO -----------------------------------------------------------
    #
    # Bon ham duoi day ton tai vi mot ly do do duoc: khu quan tri tung goi
    # `get_stats` / `list_novels` / `get_profile` cho TUNG HANG. Tren kho mock do
    # la vai phep tra dict; tren Appwrite that do la mot vong mang moi hang, va
    # `/api/admin/author-applications` mat 34 giay cho SAU persona.
    #
    # Ban mock giu cung CHU KY va cung ngu nghia de bo test hop dong doi soat
    # duoc hai ban.

    def stats_by_ids(self, user_ids: Sequence[str]) -> Dict[str, AuthorStats]:
        """Ban tong hop cua nhieu nguoi. Thieu ai thi tra ban RONG cho nguoi do."""
        with self._lock:
            return {
                uid: (self._stats.get(uid) or AuthorStats(user_id=uid))
                for uid in user_ids
            }

    def published_counts(self, owner_ids: Sequence[str]) -> Dict[str, int]:
        """So truyen DA XUAT BAN cua nhieu chu so huu."""
        can = set(owner_ids)
        dem = {uid: 0 for uid in can}
        with self._lock:
            for n in self.novels.values():
                if n.owner_id in can and n.state is PublishState.PUBLISHED:
                    dem[n.owner_id] += 1
        return dem

    def novels_by_ids(self, novel_ids: Sequence[str]) -> Dict[str, Novel]:
        """
        Nhieu truyen, MOT luot. Thieu truyen nao thi vang mat khoi ket qua.

        Dung cho bang tin: mot bai "cap nhat truyen" can tieu de truyen, va hoi
        tung bai mot la mot truy van moi bai.
        """
        can = set(novel_ids)
        with self._lock:
            return {nid: n for nid, n in self.novels.items() if nid in can}

    def chapter_counts(self, novel_ids: Sequence[str]) -> Dict[str, int]:
        """So chuong cua nhieu truyen."""
        can = set(novel_ids)
        dem = {nid: 0 for nid in can}
        with self._lock:
            for c in self.chapters.values():
                if c.novel_id in can:
                    dem[c.novel_id] += 1
        return dem

    def total_published_novels(self) -> int:
        with self._lock:
            return sum(1 for n in self.novels.values()
                       if n.state is PublishState.PUBLISHED)

    def total_novels(self) -> int:
        with self._lock:
            return len(self.novels)

    def total_chapters(self) -> int:
        with self._lock:
            return len(self.chapters)

    def sum_qualified_listens(self) -> int:
        """Tong luot nghe hop le tren toan he thong, tu ban TONG HOP."""
        with self._lock:
            return sum(s.qualified_listens for s in self._stats.values())

    def count_applications(self, status: Optional[AuthorStatus] = None) -> int:
        with self._lock:
            rows = list(self._applications.values())
        if status is not None:
            rows = [r for r in rows if r.status is status]
        return len(rows)

    # -- tac gia: don, thong ke, luot nghe ------------------------------------
    #
    # Ba bang, ba vai ro rang:
    #
    #   applications  moderation — ai duoc xuat ban
    #   stats         ban TONG HOP de doc nhanh (uy tin)
    #   credits       nguon SU THAT cua tung lan nghe hop le
    #
    # `stats` co the dung lai tu `credits` bat cu luc nao; chieu nguoc lai thi
    # khong. Do la ly do `credits` la bang duoc ghi truoc, va `stats` chi la mot
    # phep cong theo sau.

    def get_application(self, user_id: str) -> Optional[AuthorApplication]:
        with self._lock:
            return self._applications.get(user_id)

    def save_application(self, app: AuthorApplication) -> AuthorApplication:
        with self._lock:
            app.updated_at = now_iso()
            self._applications[app.user_id] = app
            return app

    def list_applications(self, status: Optional[AuthorStatus] = None,
                          limit: int = 50,
                          offset: int = 0) -> Tuple[List[AuthorApplication], int]:
        """
        Danh sach don cho TRANG QUAN TRI sau nay. Chua co route nao goi toi.

        Sap theo `created_at` tang dan: nguoi cho lau nhat duoc xem truoc. Do la
        thu tu duy nhat khong lam ai bi bo quen vinh vien.
        """
        with self._lock:
            rows = list(self._applications.values())
        if status is not None:
            rows = [r for r in rows if r.status is status]
        rows.sort(key=lambda r: (r.created_at, r.user_id))
        return rows[offset:offset + limit], len(rows)

    def get_stats(self, user_id: str) -> AuthorStats:
        """Chua co hang thi tra ve ban RONG, khong nem loi: mot tac gia chua ai
        nghe van la mot tac gia hop le, va uy tin cua ho dung bang khong."""
        with self._lock:
            return self._stats.get(user_id) or AuthorStats(user_id=user_id)

    def save_stats(self, stats: AuthorStats) -> AuthorStats:
        with self._lock:
            stats.updated_at = now_iso()
            self._stats[stats.user_id] = stats
            return stats

    def add_qualified_listen(self, author_id: str, delta: int = 1) -> AuthorStats:
        with self._lock:
            stats = self._stats.get(author_id) or AuthorStats(user_id=author_id)
            stats.qualified_listens = max(0, stats.qualified_listens + delta)
            stats.updated_at = now_iso()
            self._stats[author_id] = stats
            return stats

    def create_credit_once(self, credit: ListenCredit) -> bool:
        """
        Ghi mot lan tinh, va tra ve `False` neu khoa da ton tai.

        `credit_id` la khoa TAT DINH theo (nguoi nghe, chuong, ngay UTC). Tinh
        duy nhat cua no la co che chong dua: hai request cung luc thi chi mot
        cai tao duoc hang. Ban Appwrite dat cung rang buoc bang `rowId`.
        """
        with self._lock:
            if credit.credit_id in self._credits:
                return False
            self._credits[credit.credit_id] = credit
            return True

    def last_credit_at(self, listener_id: str, chapter_id: str) -> Optional[str]:
        """Moc cua lan tinh GAN NHAT cho cap nay, de kiem cua so 24 gio truot."""
        with self._lock:
            moc = [c.created_at for c in self._credits.values()
                   if c.listener_id == listener_id and c.chapter_id == chapter_id]
        return max(moc) if moc else None

    def count_credits(self, author_id: str) -> int:
        """Dem lai tu bang su that — dung de doi soat `stats` khi nghi no lech."""
        with self._lock:
            return sum(1 for c in self._credits.values() if c.author_id == author_id)

    # -- nhat ky kiem duyet ---------------------------------------------------

    def record_event(self, event: ModerationEvent) -> ModerationEvent:
        """CHI THEM. Khong co duong sua hay xoa, va do la ca muc dich."""
        with self._lock:
            self._events.append(event)
            return event

    def list_events(self, target_user_id: str = "", limit: int = 50,
                    offset: int = 0, target_type: str = "",
                    target_id: str = "", action: str = "",
                    created_after: str = "") -> Tuple[List[ModerationEvent], int]:
        """Moi nhat truoc — nguoi doc nhat ky luon hoi "vua co gi xay ra".

        `target_id` (Phase 4, Admin Control Center V2) — loc dung MOT doi
        tuong khong phai user (vd mot series/tap Animation cu the), cung
        tinh than voi `target_type`/`action`. `created_after` (Phase 7
        analytics) — loc theo ngay tao, dung cho bo dem theo khoang thoi
        gian (vd so lan doi chieu WebSub trong 7 ngay qua)."""
        with self._lock:
            rows = [e for e in self._events
                    if not target_user_id or e.target_user_id == target_user_id]
            if target_type:
                rows = [e for e in rows if e.target_type == target_type]
            if target_id:
                rows = [e for e in rows if e.target_id == target_id]
            if action:
                rows = [e for e in rows if e.action == action]
            if created_after:
                rows = [e for e in rows if e.created_at >= created_after]
        # Dao TRUOC roi moi sap xep: `sorted` cua Python on dinh, nen hai ban ghi
        # cung moc thoi gian se giu thu tu ghi dao nguoc — tuc la cai ghi sau
        # dung truoc. Mot lop bao ve nua ben canh moc micro giay.
        rows.reverse()
        rows.sort(key=lambda e: e.created_at, reverse=True)
        return rows[offset:offset + limit], len(rows)


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
