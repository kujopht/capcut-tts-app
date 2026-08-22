"""
Nhap chuong hang loat — tang DIEU PHOI.

TRACH NHIEM: chi giu "dot nhap nay dang o dau" va goi lai HAI duong da co.
KHONG tu tao chuong, KHONG tu goi TTS, KHONG tu gioi han so job.

  - Tao chuong  -> `tao_chuong` do `server/main.py` tiem vao, va no la CHINH
    than cua route `POST /api/chapters` (xem `_tao_chuong_cho_truyen`).
  - Tao job TTS -> `tao_job` do `server/main.py` tiem vao, va no la CHINH than
    cua route `POST /api/jobs` (xem `_tao_job_cho_chuong`), ke ca tinh
    idempotent theo dau van tay va tran `MAX_ACTIVE_JOBS`.

VI SAO BO DIEU PHOI CHAY O WORKER, KHONG O REQUEST: mot lo 500 chuong khong
the nam trong mot vong request/response, va yeu cau "tiep tuc duoc sau khi
backend/worker restart" doi mot tien trinh nen SONG LAU. `server/worker.py` da
la tien trinh do; day chi la mot lan goi them trong vong quet cua no, khong
phai mot bo lap lich thu hai.

VI SAO KHONG CAN KHOA/LEASE: moi buoc chuyen trang thai deu IDEMPOTENT nho
dinh danh tat dinh (xem docstring `server/bulk_import_domain.py`). Hai bo dieu
phoi chay song song tren cung mot lo se lam cung mot viec hai lan va ra cung
mot ket qua — khong sinh chuong trung, khong sinh job trung. Nho vay khong co
lease nao de het han, khong co khoa nao de mo coi. O production van chi co MOT
bo dieu phoi (worker GCE) vi khong can hai, chu khong vi hai la sai.

THU TU BA PHA trong mot chu ky, va thu tu do quan trong:

  Pha C (doi soat) truoc — muc `job_queued` nao da xong thi ket lai, GIAI
     PHONG cho o `MAX_ACTIVE_JOBS` ngay trong chu ky nay.
  Pha A (tao chuong) — KHONG bi chan boi tran job. Chu truyen can 500 chuong
     hien ra som; audio nho giot ve sau la binh thuong. Neu gop pha nay vao
     sau pha B thi toc do tao chuong bi rang buoc vao toc do tong hop audio,
     tuc la hang ngay.
  Pha B (xep job) — chi khi con o trong, va DUNG khi gap 429.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Sequence, Tuple

from server.adapters import NotFoundError, PermissionDenied
from server.bulk_import_domain import (
    ACTIVE_ITEM_STATUSES,
    DRIVER_BATCH_STATUSES,
    BatchStatus,
    BulkImportFormatError,
    BulkImportStateError,
    ChapterJobRejected,
    ImportBatch,
    ImportItem,
    ItemStatus,
    JobQueueFull,
    ParsedChapter,
    batch_fingerprint,
    chapter_id_for,
)
from server.domain import Chapter, JobStatus, Novel, now_iso

#: Bao nhieu CHUONG duoc tao moi chu ky, moi lo. Khong phai tran an toan — chi
#: de mot lo 500 chuong khong chiem het mot chu ky quet cua worker, von con
#: phai chay `recover_stale_jobs` dung gio.
CHAPTERS_PER_CYCLE = int(os.environ.get("FAS_IMPORT_CHAPTERS_PER_CYCLE", "5"))

#: Bao nhieu job duoc THU xep moi chu ky. Tran that la `MAX_ACTIVE_JOBS` cua
#: `POST /api/jobs`; con so nay chi chan viec goi vao mot ham chac chan tra 429.
JOBS_PER_CYCLE = int(os.environ.get("FAS_IMPORT_JOBS_PER_CYCLE", "3"))

#: Bao nhieu muc `job_queued` duoc doi soat moi chu ky. Ca lo doi soat bang MOT
#: truy van (`jobs_by_ids`), nen con so nay chi chan kich thuoc mot truy van.
RECONCILE_PER_CYCLE = int(os.environ.get("FAS_IMPORT_RECONCILE_PER_CYCLE", "50"))

#: Bao nhieu lo duoc quet moi chu ky.
BATCHES_PER_CYCLE = int(os.environ.get("FAS_IMPORT_BATCHES_PER_CYCLE", "5"))

#: Lo ket o `preparing` lau hon muc nay thi coi nhu viec ghi danh sach muc da
#: chet giua chung. 15 phut: 500 hang tren Appwrite mat khoang hai phut, nen
#: nguong nay khong bao gio dam vao mot lan ghi dang chay binh thuong.
PREPARING_STALE_SECONDS = int(
    os.environ.get("FAS_IMPORT_PREPARING_STALE_SECONDS", "900"))

#: Chu ky quet cua bo dieu phoi khi web TU chay (che do inline, dev). O
#: staging/production `FAS_INLINE_WORKER=false` nen worker rieng lo viec nay.
IMPORT_SWEEP_SECONDS = int(os.environ.get("FAS_IMPORT_SWEEP_SECONDS", "5"))

#: Nghi bao lau sau mot chu ky KHONG THAY lo nao dang chay. Dat 0 de tat.
IDLE_BACKOFF_SECONDS = float(
    os.environ.get("FAS_IMPORT_IDLE_BACKOFF_SECONDS", "30"))


class ImportDriveGate:
    """
    Phanh nghi cua bo dieu phoi — quyet dinh SUY RA TU KET QUA TRUY VAN.

    VI SAO CAN PHANH: worker quet moi `POLL_SECONDS` (3 giay). Khong co con nay
    thi mot he thong KHONG CO lo nhap nao van ton mot truy van Appwrite moi 3
    giay — khoang 860.000 luot doc mot thang chi de hoi "co viec gi khong". Han
    muc doc cua Appwrite da mot lan can kiet tren production (20/08).

    VI SAO PULL, KHONG PHAI PUSH — va day la mot loi da vap va da sua:
    ban dau lop nay la mot bien toan cuc trong `server/main.py` kem mot ham
    `reset_import_backoff()` ma cac route goi khi chu vua mo/thu lai mot lo, VOI
    Y DINH "danh thuc" bo dieu phoi ngay. Y dinh do KHONG BAO GIO thanh:
    o production `server/worker.py` la mot TIEN TRINH KHAC, tren mot MAY KHAC
    (GCE), va `from server import main as api` cho no mot ban module RIENG voi
    bien toan cuc RIENG. Route chay o tien trinh web reset bien cua chinh tien
    trinh web — dung cai tien trinh khong dieu phoi gi ca. Bo test cu khong bat
    duoc vi no goi `drive_chapter_imports()` trong CUNG mot tien trinh.

    Nen bay gio KHONG co tin hieu danh thuc nao, va khong co ai duoc phep day
    trang thai vao day tu ben ngoai. Phanh chi doc DUY NHAT mot dau vao: chu ky
    truoc thay bao nhieu lo. Nho vay hai tien trinh chay doc lap co hanh vi
    GIONG NHAU tuyet doi, va mot lo vua tao duoc nhin thay o chu ky ke tiep cua
    worker ma khong ai phai bao no.

    MOT THE HIEN = MOT TIEN TRINH. Do la su that ve kien truc, khong phai han
    che: khong co gi trong lop nay muon duoc chia se qua ranh gioi tien trinh.

    DANH DOI da can: mot lo vua tao co the phai cho toi `backoff_seconds` truoc
    khi nhich. Chap nhan duoc, va thuong la vo hinh — route tra ve lo o trang
    thai `preparing`, va viec ghi 500 hang muc con lau hon nhieu so voi 30 giay.
    Doi lai la khong them mot truy van nao vao chu ky quet luc rong viec. Muon
    do tre thap hon thi ha `FAS_IMPORT_IDLE_BACKOFF_SECONDS` (10 giay -> khoang
    260.000 luot doc/thang) hoac dat 0 de tat han (~860.000 luot doc/thang).
    """

    def __init__(self, backoff_seconds: float = IDLE_BACKOFF_SECONDS,
                 dong_ho: Callable[[], float] = time.monotonic):
        #: `time.monotonic` — KHONG phai gio he thong: doi gio/NTP nhay khong
        #: duoc lam bo dieu phoi ngu mot tieng.
        self._dong_ho = dong_ho
        self._backoff = max(0.0, float(backoff_seconds))
        self._nghi_den = 0.0

    def should_skip(self) -> bool:
        """Chu ky nay co bo qua khong. KHONG doc gi ngoai trang thai cua chinh
        the hien nay."""
        return self._backoff > 0 and self._dong_ho() < self._nghi_den

    def record(self, so_lo_thay_duoc: int) -> None:
        """
        Ghi nhan KET QUA truy van cua chu ky vua chay.

        Day la duong VAO DUY NHAT cua lop nay. Khong co `reset()` cong khai, va
        do la co y: mot ham nhu vay chi co the duoc goi tu tien trinh web, noi
        no khong co tac dung gi len bo dieu phoi that.
        """
        self._nghi_den = (0.0 if so_lo_thay_duoc
                          else self._dong_ho() + self._backoff)

    def xoa_de_test(self) -> None:
        """CHI cho bo test — trang thai o cap module phai sach giua hai bai.

        KHONG duoc goi tu route nao. Xem doan "VI SAO PULL" o docstring lop:
        goi tu tien trinh web la mot phep khong lam gi ca duoc viet ra nhu the
        no co tac dung."""
        self._nghi_den = 0.0


def _tuoi_giay(stamp: str) -> float:
    """Tuoi cua mot moc ISO, tinh bang giay. Khong doc duoc -> 0 (coi nhu vua
    xong), de mot moc hong KHONG lam lo bi danh `failed` oan."""
    if not stamp:
        return 0.0
    try:
        moc = datetime.fromisoformat(stamp)
    except ValueError:
        return 0.0
    if moc.tzinfo is None:
        moc = moc.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moc).total_seconds()


#: Kieu cua ham tao chuong duoc tiem vao — tra `(chapter, vua_tao)`.
TaoChuong = Callable[..., Tuple[Chapter, bool]]
#: Kieu cua ham tao job duoc tiem vao — tra dict `{"job": ..., "reused": ...}`.
TaoJob = Callable[..., Dict[str, Any]]


class BulkImportService:
    def __init__(self, bulk_store: Any, store: Any, *,
                 tao_chuong: TaoChuong, tao_job: TaoJob,
                 max_active_jobs: int = 3,
                 chapters_per_cycle: int = CHAPTERS_PER_CYCLE,
                 jobs_per_cycle: int = JOBS_PER_CYCLE,
                 reconcile_per_cycle: int = RECONCILE_PER_CYCLE,
                 batches_per_cycle: int = BATCHES_PER_CYCLE,
                 preparing_stale_seconds: int = PREPARING_STALE_SECONDS):
        self._bulk = bulk_store
        self._store = store
        self._tao_chuong = tao_chuong
        self._tao_job = tao_job
        self._max_active_jobs = max(1, int(max_active_jobs))
        self._chapters_per_cycle = max(1, int(chapters_per_cycle))
        self._jobs_per_cycle = max(1, int(jobs_per_cycle))
        self._reconcile_per_cycle = max(1, int(reconcile_per_cycle))
        self._batches_per_cycle = max(1, int(batches_per_cycle))
        self._preparing_stale_seconds = max(60, int(preparing_stale_seconds))

    # =========================================================================
    # Duong CHU TRUYEN goi (qua route)
    # =========================================================================

    def create_or_resume(self, owner_id: str, novel: Novel,
                         items: Sequence[ParsedChapter], *,
                         voice_id: str = "", rate: str = "1.0",
                         chunk_chars: int = 2000,
                         source_name: str = "") -> Dict[str, Any]:
        """
        Tao lo MOI, hoac TIEP TUC dung lo cu neu dau vao y het.

        Ba nhanh, va tat ca deu KHONG bao gio tao chuong trung:

        - chua co lo    -> ghi hang lo (`preparing`), ghi danh sach muc, `running`;
        - lo `preparing`-> ghi lai danh sach muc (idempotent) roi `running`;
        - lo da KET     -> hoi sinh ve `running` NEU con muc dang cho.

        Lo da ket ma KHONG con muc dang cho (da xong, hoac chi con muc that
        bai) thi KHONG hoi sinh: muc that bai phai do chu bam "thử lại" mot
        cach tuong minh — tu dong thu lai moi lan gui lai tep se che mat loi
        that.
        """
        fingerprint = batch_fingerprint(owner_id, novel.novel_id, items)
        # `order_base` chot MOT LAN, luc tao lo. Doc lai moi lan chay se day
        # thu tu chuong di neu chu them chuong bang tay giua hai chu ky.
        order_base = max((c.order_index for c in
                          self._store.list_chapters(novel.novel_id)), default=0)
        lo = ImportBatch(
            owner_id=owner_id, novel_id=novel.novel_id, fingerprint=fingerprint,
            total_items=len(items), voice_id=voice_id, rate=rate,
            chunk_chars=chunk_chars, order_base=max(order_base, 0),
            source_name=source_name[:200],
        )
        lo, vua_tao = self._bulk.create_batch_once(lo)

        if vua_tao:
            return {"batch": lo, "created": True, "resumed": False,
                    "voice_ignored": False, "items": list(items)}

        # Da co lo nay. Giong doc cua lan gui truoc THANG — xem
        # `batch_fingerprint` ve ly do `voice_id` khong nam trong dau van tay.
        voice_ignored = bool(voice_id) and voice_id != lo.voice_id

        if lo.status is BatchStatus.PREPARING:
            return {"batch": lo, "created": False, "resumed": True,
                    "voice_ignored": voice_ignored, "items": list(items)}

        if lo.status is BatchStatus.RUNNING:
            return {"batch": lo, "created": False, "resumed": False,
                    "voice_ignored": voice_ignored, "items": []}

        # Lo da KET (huy / xong / mot phan / loi). Hoi sinh CHI khi con viec.
        dem = self._bulk.count_items_by_status(lo.batch_id)
        con_viec = sum(dem.get(s.value, 0) for s in ACTIVE_ITEM_STATUSES)
        if con_viec <= 0:
            return {"batch": lo, "created": False, "resumed": False,
                    "voice_ignored": voice_ignored, "items": []}
        lo = self._bulk.save_batch(lo.batch_id, {
            "status": BatchStatus.RUNNING, "cancelled_at": "",
            "finished_at": "", "last_error": "",
            **self._truong_dem(dem),
        })
        return {"batch": lo, "created": False, "resumed": True,
                "voice_ignored": voice_ignored, "items": []}

    def materialize(self, batch_id: str,
                    items: Sequence[ParsedChapter]) -> ImportBatch:
        """
        Ghi danh sach muc roi chuyen lo `preparing` -> `running`.

        AN TOAN KHI CHAY LAI: `create_item_once` co `item_id` tat dinh, nen
        lan chay thu hai chi bo qua nhung hang da co. Nho vay mot lan ghi bi
        cat giua chung (backend restart, mang dut) duoc cuu bang dung mot hanh
        dong: chu gui lai CUNG tep do.

        CHAY TRONG THREAD NEN, khong trong request: 500 hang Appwrite la vai
        chuc giay den vai phut, va khong request nao nen giu lau nhu vay.
        """
        lo = self._bulk.get_batch(batch_id)
        if lo.status is not BatchStatus.PREPARING:
            return lo
        for chi_so, muc in enumerate(items, start=1):
            self._bulk.create_item_once(ImportItem(
                batch_id=lo.batch_id, owner_id=lo.owner_id,
                novel_id=lo.novel_id, item_index=chi_so,
                title=muc.title, content=muc.content,
            ))
        # Chi bay gio moi duoc bat bo dieu phoi: truoc do danh sach muc chua
        # day, va mot lo thieu muc se bi ket luan "xong" oan.
        return self._bulk.save_batch(lo.batch_id, {
            "status": BatchStatus.RUNNING,
            "count_pending": lo.total_items,
            "count_chapter_created": 0, "count_job_queued": 0,
            "count_completed": 0, "count_failed": 0,
        })

    def owned_batch(self, owner_id: str, novel_id: str,
                    batch_id: str) -> ImportBatch:
        """
        Rao quyen cua MOI duong doc/ghi cua chu truyen.

        Route da goi `store.owned_novel()` truoc do; cho nay la lop THU HAI, va
        no khong thua: `batch_id` doan duoc (bam tu noi dung) nen mot lo phai tu
        chung minh no thuoc dung chu VA dung truyen, khong dua vao duong URL.
        """
        lo = self._bulk.get_batch(batch_id)
        if lo.owner_id != owner_id or lo.novel_id != novel_id:
            # 404 chu khong phai 403: nguoi la khong duoc biet lo nay ton tai.
            raise NotFoundError("Không tìm thấy lô nhập chương.")
        return lo

    def batch_view(self, owner_id: str, novel_id: str, batch_id: str, *,
                   limit: int = 50, offset: int = 0,
                   status: str = "") -> Dict[str, Any]:
        lo = self.owned_batch(owner_id, novel_id, batch_id)
        loc = None
        if status:
            try:
                loc = [ItemStatus(status)]
            except ValueError as exc:
                # 400 doc duoc, KHONG phai `ValueError` xuyen ra thanh 500: day
                # la mot tham so truy van do client gui, va client co the cu.
                raise BulkImportFormatError(
                    f"Trạng thái '{status}' không hợp lệ. Chấp nhận: "
                    + ", ".join(s.value for s in ItemStatus)) from exc
        muc, tong = self._bulk.list_items(
            batch_id, statuses=loc, limit=max(1, min(limit, 200)),
            offset=max(0, offset), include_content=False)
        return {
            "batch": lo.to_dict(),
            "progress": lo.progress(),
            "items": [m.to_dict() for m in muc],
            "count": tong,
        }

    def list_for_novel(self, owner_id: str, novel_id: str) -> Dict[str, Any]:
        ds, tong = self._bulk.list_batches(owner_id=owner_id, novel_id=novel_id)
        return {
            "batches": [b.to_dict() for b in ds],
            "progress": {b.batch_id: b.progress() for b in ds},
            "count": tong,
        }

    def cancel(self, owner_id: str, novel_id: str,
               batch_id: str) -> Dict[str, Any]:
        """
        Huy AN TOAN: dung xep viec MOI, KHONG cat job dang bay.

        Job dang tong hop van chay den cung, va bo dieu phoi VAN doi soat ket
        qua cua chung (trang thai `cancelling`). Bo audio da tong hop xong chi
        vi chu bam "huy" la nem di dung phan viec dat nhat.
        """
        lo = self.owned_batch(owner_id, novel_id, batch_id)
        if lo.is_terminal:
            return {"batch": lo.to_dict(), "progress": lo.progress(),
                    "cancelled": False, "already_finished": True}
        dem = self._bulk.count_items_by_status(batch_id)
        dang_bay = dem.get(ItemStatus.JOB_QUEUED.value, 0)
        moi = BatchStatus.CANCELLING if dang_bay else BatchStatus.CANCELLED
        luc = now_iso()
        lo = self._bulk.save_batch(batch_id, {
            "status": moi, "cancelled_at": luc,
            "finished_at": "" if dang_bay else luc,
            **self._truong_dem(dem),
        })
        return {"batch": lo.to_dict(), "progress": lo.progress(),
                "cancelled": True, "already_finished": False,
                "jobs_in_flight": dang_bay}

    def retry(self, owner_id: str, novel_id: str, batch_id: str, *,
              item_id: str = "") -> Dict[str, Any]:
        """
        Thu lai MOT muc that bai (hoac tat ca muc that bai neu `item_id` rong).

        Dua muc ve `pending`, KHONG ve `chapter_created`, ke ca khi muc da co
        `chapter_id`. Ly do: `chapter_id` la TAT DINH va viec tao chuong la
        tao-hoac-lay, nen quay ve `pending` xu ly dung CA HAI truong hop bang
        mot duong — chuong con day (lay lai, khong ghi de gi cua tac gia) hay
        chuong da bi xoa (tao lai dung id do) — ma khong ton mot lan doc de
        biet chuong con ton tai hay khong.
        """
        lo = self.owned_batch(owner_id, novel_id, batch_id)
        if lo.status in (BatchStatus.CANCELLED, BatchStatus.CANCELLING):
            raise BulkImportStateError(
                "Lô này đã huỷ. Hãy gửi lại đúng tệp cũ để tiếp tục, rồi thử "
                "lại chương lỗi.")
        if lo.status is BatchStatus.PREPARING:
            raise BulkImportStateError("Lô đang ghi danh sách chương, hãy đợi.")

        if item_id:
            muc = self._bulk.get_item(item_id)
            if muc.batch_id != batch_id or muc.owner_id != owner_id:
                raise NotFoundError("Không tìm thấy chương trong lô nhập.")
            can_thu = [muc]
        else:
            can_thu, _ = self._bulk.list_items(
                batch_id, statuses=[ItemStatus.FAILED], limit=None)

        da_thu = 0
        for muc in can_thu:
            if muc.status is not ItemStatus.FAILED:
                if item_id:
                    raise BulkImportStateError(
                        "Chương này không ở trạng thái lỗi nên không cần thử lại.")
                continue
            self._bulk.save_item(muc.item_id, {
                "status": ItemStatus.PENDING, "job_id": "",
                "error_message": "", "attempts": muc.attempts + 1,
            })
            da_thu += 1

        if da_thu:
            dem = self._bulk.count_items_by_status(batch_id)
            lo = self._bulk.save_batch(batch_id, {
                "status": BatchStatus.RUNNING, "finished_at": "",
                "last_error": "", **self._truong_dem(dem),
            })
        return {"batch": lo.to_dict(), "progress": lo.progress(),
                "retried": da_thu}

    # =========================================================================
    # Bo DIEU PHOI (worker)
    # =========================================================================

    def drive_once(self) -> Dict[str, int]:
        """
        MOT chu ky dieu phoi. Goi bao nhieu lan cung duoc, luc nao cung duoc.

        Mot lo loi KHONG duoc lam cac lo khac dung: cung triet ly voi
        `recover_stale_jobs` — mot vong quet chet la mat recovery.
        """
        bao = {"lo": 0, "chuong_tao": 0, "job_xep": 0, "muc_xong": 0,
               "muc_loi": 0, "lo_ket": 0}
        try:
            ds, _ = self._bulk.list_batches(statuses=DRIVER_BATCH_STATUSES,
                                            limit=self._batches_per_cycle)
        except Exception:
            return bao
        for lo in ds:
            bao["lo"] += 1
            try:
                self._drive_batch(lo, bao)
            except Exception:
                # Khong ghi gi vao hang lo o day: mot loi mang tam thoi khong
                # duoc bien thanh `last_error` vinh vien. Chu ky sau thu lai.
                pass
        return bao

    def _drive_batch(self, lo: ImportBatch, bao: Dict[str, int]) -> None:
        if lo.status is BatchStatus.PREPARING:
            if _tuoi_giay(lo.created_at) > self._preparing_stale_seconds:
                self._bulk.save_batch(lo.batch_id, {
                    "status": BatchStatus.FAILED, "finished_at": now_iso(),
                    "last_error": ("Chưa ghi xong danh sách chương. Hãy gửi lại "
                                   "đúng tệp cũ để tiếp tục từ chỗ đang dở."),
                })
            return

        # Truyen phai con day VA con dung chu. Truyen bi xoa giua mot dot nhap
        # se lam moi muc that bai lien tuc mai mai neu khong chan o day.
        try:
            novel = self._store.owned_novel(lo.novel_id, lo.owner_id)
        except (NotFoundError, PermissionDenied) as exc:
            self._bulk.save_batch(lo.batch_id, {
                "status": BatchStatus.FAILED, "finished_at": now_iso(),
                "last_error": f"Không truy cập được truyện: {exc}",
            })
            return

        chi_doi_soat = lo.status is BatchStatus.CANCELLING
        dem = self._dem_tu_lo(lo)

        thay_doi = self._pha_doi_soat(lo, dem, bao)

        if chi_doi_soat:
            # LO DA HUY. Dieu kien ket KHONG phai "khong con muc dang cho" —
            # muc `pending`/`chapter_created` cua mot lo da huy se KHONG BAO GIO
            # duoc xu ly, nen doi chung la doi mai mai. Dieu kien dung la
            # "khong con job nao dang bay": do la ranh gioi cua "huy nhung
            # khong bo phan viec da tra tien".
            dang_bay = dem[ItemStatus.JOB_QUEUED.value]
            if dang_bay <= 0:
                dem = self._bulk.count_items_by_status(lo.batch_id)
                dang_bay = dem[ItemStatus.JOB_QUEUED.value]
            if dang_bay <= 0:
                self._bulk.save_batch(lo.batch_id, {
                    "status": BatchStatus.CANCELLED, "finished_at": now_iso(),
                    **self._truong_dem(dem),
                })
                bao["lo_ket"] += 1
            elif thay_doi:
                self._bulk.save_batch(lo.batch_id, self._truong_dem(dem))
            return

        thay_doi = self._pha_tao_chuong(lo, novel, dem, bao) or thay_doi
        thay_doi = self._pha_xep_job(lo, dem, bao) or thay_doi

        con_viec = sum(dem[s.value] for s in ACTIVE_ITEM_STATUSES)
        if con_viec <= 0:
            # DEM LAI CHINH XAC dung mot lan trong ca doi lo: truoc khi tuyen
            # bo no da xong. Bo dem tang/giam theo tung buoc co the lech neu co
            # hai bo dieu phoi cung chay, va "xong" la ket luan duy nhat khong
            # duoc phep sai.
            dem = self._bulk.count_items_by_status(lo.batch_id)
            con_viec = sum(dem[s.value] for s in ACTIVE_ITEM_STATUSES)
        if con_viec <= 0:
            ket = (BatchStatus.PARTIAL if dem[ItemStatus.FAILED.value]
                   else BatchStatus.COMPLETED)
            self._bulk.save_batch(lo.batch_id, {
                "status": ket, "finished_at": now_iso(),
                **self._truong_dem(dem),
            })
            bao["lo_ket"] += 1
            return
        if thay_doi:
            self._bulk.save_batch(lo.batch_id, self._truong_dem(dem))

    # -- pha C: doi soat -------------------------------------------------------

    def _pha_doi_soat(self, lo: ImportBatch, dem: Dict[str, int],
                      bao: Dict[str, int]) -> bool:
        ds, _ = self._bulk.list_items(
            lo.batch_id, statuses=[ItemStatus.JOB_QUEUED],
            limit=self._reconcile_per_cycle, include_content=False)
        if not ds:
            return False
        # MOT truy van cho ca lo — xem `RECONCILE_PER_CYCLE`.
        jobs = self._store.jobs_by_ids([m.job_id for m in ds if m.job_id])
        thay_doi = False
        for muc in ds:
            job = jobs.get(muc.job_id) if muc.job_id else None
            if job is None:
                # Job bien mat. Ly do thuong gap nhat: chu XOA chuong giua mot
                # dot nhap, va `_purge_chapter` don luon job cua no.
                #
                # TUYET DOI khong dua muc ve `pending` o day. `chapter_id` la
                # TAT DINH, nen `pending` se lam bo dieu phoi TAO LAI dung cai
                # chuong ma chu vua xoa — mot thao tac xoa co y bi mot vong quet
                # nen am tham hoan tac. Ranh gioi la: bo dieu phoi khong bao gio
                # tu quyet dinh phuc hoi noi dung; chi `retry` (hanh dong tuong
                # minh cua chu) duoc lam viec do.
                thay_doi = True
                if self._chuong_con_ton_tai(muc.chapter_id):
                    # Chuong con day, chi job mat -> xep lai job. An toan.
                    self._bulk.save_item(muc.item_id, {
                        "status": ItemStatus.CHAPTER_CREATED, "job_id": ""})
                    self._chuyen(dem, ItemStatus.JOB_QUEUED,
                                 ItemStatus.CHAPTER_CREATED)
                    continue
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.FAILED, "job_id": "",
                    "error_message": ("Chương này không còn tồn tại (có thể đã "
                                      "bị xoá). Bấm “thử lại” nếu muốn tạo "
                                      "lại từ nội dung đã nhập.")})
                self._chuyen(dem, ItemStatus.JOB_QUEUED, ItemStatus.FAILED)
                bao["muc_loi"] += 1
                continue
            if job.status is JobStatus.COMPLETED:
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.COMPLETED, "error_message": ""})
                self._chuyen(dem, ItemStatus.JOB_QUEUED, ItemStatus.COMPLETED)
                bao["muc_xong"] += 1
                thay_doi = True
            elif job.status is JobStatus.FAILED:
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.FAILED,
                    "error_message": (job.error_message
                                      or "Tạo audio thất bại.")[:1000]})
                self._chuyen(dem, ItemStatus.JOB_QUEUED, ItemStatus.FAILED)
                bao["muc_loi"] += 1
                thay_doi = True
        return thay_doi

    def _chuong_con_ton_tai(self, chapter_id: str) -> bool:
        """
        Chuong con trong kho hay khong.

        Loi HA TANG tra `True` — "chua biet", chu khong phai "da mat". Coi mot
        lan mat mang la "chuong da bi xoa" se danh `failed` oan hang loat muc,
        va o quy mo 500 chuong thi do la mot bang tien do day so do khong ai
        tin duoc nua.
        """
        if not chapter_id:
            return False
        try:
            self._store.get_chapter(chapter_id)
            return True
        except NotFoundError:
            return False
        except Exception:
            return True

    # -- pha A: tao chuong -----------------------------------------------------

    def _pha_tao_chuong(self, lo: ImportBatch, novel: Novel,
                        dem: Dict[str, int], bao: Dict[str, int]) -> bool:
        ds, _ = self._bulk.list_items(
            lo.batch_id, statuses=[ItemStatus.PENDING],
            limit=self._chapters_per_cycle, include_content=True)
        thay_doi = False
        for muc in ds:
            try:
                chuong, vua_tao = self._tao_chuong(
                    novel=novel, owner_id=lo.owner_id, title=muc.title,
                    content=muc.content,
                    order_index=lo.order_base + muc.item_index,
                    chapter_id=chapter_id_for(muc.item_id),
                )
            except Exception as exc:
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.FAILED,
                    "error_message": f"Không tạo được chương: {exc}"[:1000]})
                self._chuyen(dem, ItemStatus.PENDING, ItemStatus.FAILED)
                bao["muc_loi"] += 1
                thay_doi = True
                continue
            self._bulk.save_item(muc.item_id, {
                "status": ItemStatus.CHAPTER_CREATED,
                "chapter_id": chuong.chapter_id, "error_message": ""})
            self._chuyen(dem, ItemStatus.PENDING, ItemStatus.CHAPTER_CREATED)
            if vua_tao:
                bao["chuong_tao"] += 1
            thay_doi = True
        return thay_doi

    # -- pha B: xep job --------------------------------------------------------

    def _pha_xep_job(self, lo: ImportBatch, dem: Dict[str, int],
                     bao: Dict[str, int]) -> bool:
        if not lo.voice_id:
            # Lo CHI TAO CHUONG. Hop le: nhieu tac gia dang van ban truoc, chon
            # giong sau (bang duong don chuong da co).
            ds, _ = self._bulk.list_items(
                lo.batch_id, statuses=[ItemStatus.CHAPTER_CREATED],
                limit=self._chapters_per_cycle, include_content=False)
            for muc in ds:
                self._bulk.save_item(muc.item_id,
                                     {"status": ItemStatus.COMPLETED})
                self._chuyen(dem, ItemStatus.CHAPTER_CREATED,
                             ItemStatus.COMPLETED)
                bao["muc_xong"] += 1
            return bool(ds)

        o_trong = self._max_active_jobs - dem[ItemStatus.JOB_QUEUED.value]
        if o_trong <= 0:
            # KHONG goi `tao_job` de an mot cai 429 duoc bao truoc: moi lan goi
            # do phai dem lai job dang xep hang cua nguoi dung, va o quy mo 500
            # chuong thi day la duong de dot han muc doc cua Appwrite.
            return False
        ds, _ = self._bulk.list_items(
            lo.batch_id, statuses=[ItemStatus.CHAPTER_CREATED],
            limit=max(1, min(o_trong, self._jobs_per_cycle)),
            include_content=False)
        thay_doi = False
        for muc in ds:
            if not muc.chapter_id:
                continue
            # KHONG BAO GIO tao lai audio cho chuong DA CO ban hoan tat. Dau
            # van tay cua `POST /api/jobs` chi bao ve truong hop CUNG giong +
            # cung thiet lap; mot ban audio giong KHAC van se bi ghi de neu
            # khong chan o day. Doi giong la viec chu tu lam cho TUNG chuong.
            try:
                da_co = self._store.track_for_chapter(muc.chapter_id)
            except Exception:
                da_co = None
            if da_co is not None:
                self._bulk.save_item(muc.item_id,
                                     {"status": ItemStatus.COMPLETED})
                self._chuyen(dem, ItemStatus.CHAPTER_CREATED,
                             ItemStatus.COMPLETED)
                bao["muc_xong"] += 1
                thay_doi = True
                continue
            try:
                ket = self._tao_job(
                    owner_id=lo.owner_id, chapter_id=muc.chapter_id,
                    voice_id=lo.voice_id, rate=lo.rate,
                    chunk_chars=lo.chunk_chars)
            except JobQueueFull:
                # Tran cua chinh nguoi dung. DUNG ca pha nay, thu lai chu ky
                # sau — day la co che gioi han dong thoi, khong phai loi.
                break
            except ChapterJobRejected as exc:
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.FAILED,
                    "error_message": str(exc)[:1000]})
                self._chuyen(dem, ItemStatus.CHAPTER_CREATED, ItemStatus.FAILED)
                bao["muc_loi"] += 1
                thay_doi = True
                continue
            except Exception as exc:
                self._bulk.save_item(muc.item_id, {
                    "status": ItemStatus.FAILED,
                    "error_message": f"Không tạo được audio: "
                                     f"{type(exc).__name__}"[:1000]})
                self._chuyen(dem, ItemStatus.CHAPTER_CREATED, ItemStatus.FAILED)
                bao["muc_loi"] += 1
                thay_doi = True
                continue
            job_id = str((ket.get("job") or {}).get("job_id") or "")
            self._bulk.save_item(muc.item_id, {
                "status": ItemStatus.JOB_QUEUED, "job_id": job_id,
                "error_message": ""})
            self._chuyen(dem, ItemStatus.CHAPTER_CREATED, ItemStatus.JOB_QUEUED)
            bao["job_xep"] += 1
            thay_doi = True
        return thay_doi

    # -- bo dem ----------------------------------------------------------------

    @staticmethod
    def _dem_tu_lo(lo: ImportBatch) -> Dict[str, int]:
        return {
            ItemStatus.PENDING.value: lo.count_pending,
            ItemStatus.CHAPTER_CREATED.value: lo.count_chapter_created,
            ItemStatus.JOB_QUEUED.value: lo.count_job_queued,
            ItemStatus.COMPLETED.value: lo.count_completed,
            ItemStatus.FAILED.value: lo.count_failed,
        }

    @staticmethod
    def _truong_dem(dem: Dict[str, int]) -> Dict[str, int]:
        return {
            "count_pending": max(0, dem.get(ItemStatus.PENDING.value, 0)),
            "count_chapter_created": max(
                0, dem.get(ItemStatus.CHAPTER_CREATED.value, 0)),
            "count_job_queued": max(0, dem.get(ItemStatus.JOB_QUEUED.value, 0)),
            "count_completed": max(0, dem.get(ItemStatus.COMPLETED.value, 0)),
            "count_failed": max(0, dem.get(ItemStatus.FAILED.value, 0)),
        }

    @staticmethod
    def _chuyen(dem: Dict[str, int], tu: ItemStatus, den: ItemStatus) -> None:
        dem[tu.value] = max(0, dem.get(tu.value, 0) - 1)
        dem[den.value] = dem.get(den.value, 0) + 1
