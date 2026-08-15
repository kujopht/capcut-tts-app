"""
Tang dich vu Novel Translation Studio (V5).

Cung triet ly voi `SocialService`/`CreatorService`: MOI duong ghi di qua day.
Khong biet gi ve HTTP — nem `TranslationError`/`NotFoundError`/
`PermissionDenied`, tang route (`main.py`) doi thanh ma trang thai.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from server.adapters import NotFoundError, PermissionDenied
from server.domain import now_iso, now_iso_us
from server.translation import (
    TERMINAL_STATUSES,
    GenrePreset,
    GlossaryCategory,
    GlossaryEntry,
    ManualEditWouldBeOverwritten,
    NamingMode,
    QualityMode,
    QuotaExceeded,
    TranslationError,
    TranslationJobStatus,
    ap_dung_khoa_glossary,
    buoc_tiep_theo,
    kiem_glossary_entry,
    phat_hien_canh_bao,
    tach_chuong,
    tach_doan_hien_thi,
    tach_doan_trong_chuong,
    uoc_luong,
)
from server.translation_domain import (
    TranslationJob,
    TranslationProject,
    TranslationVersion,
)
from server.translation_providers import (
    TranslationContext,
    TranslationProvider,
    TranslationProviderError,
    build_provider,
)
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    ConfiguredProvider,
    ProviderProvenance,
    ProviderRegistry,
)

#: Tran cau hinh — doc tu bien moi truong o `server/config.py` khi wiring vao
#: main.py; hang so o day la GIA TRI MAC DINH cho luc kiem thu truc tiep.
MAX_CHARS_PER_PROJECT = 300_000
MAX_CHAPTERS_PER_PROJECT = 200
MAX_CONCURRENT_JOBS_PER_USER = 3

# =============================================================================
# Worker nen — claim/lease/fencing, CUNG KHUON voi `server/worker.py` (TTS)
# nhung tren bang RIENG (`translation_jobs`/`translation_job_claims`), hoan
# toan doc lap. Xem `server/translation_worker.py` cho tien trinh worker
# rieng chay ben ngoai web.
# =============================================================================

#: Lease bao lau truoc khi mot job bi coi la "worker da mat". Do dai chuong
#: khong lien quan — mien heartbeat con dap thi lease duoc gia han truoc khi
#: het han. Xem `FAS_JOB_LEASE_SECONDS` (TTS) cho cung ly do thiet ke.
TRANSLATION_JOB_LEASE_SECONDS = int(
    os.environ.get("FAS_TRANSLATION_JOB_LEASE_SECONDS", "90"))

#: Chu ky lam moi lease tu trong worker.
TRANSLATION_JOB_HEARTBEAT_SECONDS = int(
    os.environ.get("FAS_TRANSLATION_JOB_HEARTBEAT_SECONDS", "20"))

if TRANSLATION_JOB_LEASE_SECONDS < TRANSLATION_JOB_HEARTBEAT_SECONDS * 3:
    raise RuntimeError(
        f"FAS_TRANSLATION_JOB_LEASE_SECONDS={TRANSLATION_JOB_LEASE_SECONDS} "
        "quá ngắn so với FAS_TRANSLATION_JOB_HEARTBEAT_SECONDS="
        f"{TRANSLATION_JOB_HEARTBEAT_SECONDS}. Lease phải dài ít nhất gấp ba "
        "chu kỳ nhịp.")

#: So lan claim toi da cho MOT job. Vuot thi `failed` kem thong bao ro rang
#: thay vi xoay vong mai. KHONG ap dung cho job dang `waiting_for_provider`
#: (Part Q4) — cho han muc mien phi la mot vong lap BINH THUONG, khong phai
#: dau hieu worker cu bi loi, nen khong duoc phep dot mat luot thu.
TRANSLATION_JOB_MAX_ATTEMPTS = 3

#: Backoff MAC DINH (giay) khi TAT CA provider het han muc nhung KHONG
#: provider nao bao duoc moc reset — dung khi
#: `AllProvidersUnavailable.retry_not_before` rong. Xem `_thuc_thi_job`.
TRANSLATION_WAITING_DEFAULT_RETRY_SECONDS = int(
    os.environ.get("FAS_TRANSLATION_WAITING_DEFAULT_RETRY_SECONDS", "300"))

#: Cac trang thai job dang "song" (chua ket thuc) — mot job dang o bat ky
#: trang thai nao trong day ma mat lease se can duoc mot worker khac nhan lai.
NON_TERMINAL_STATUSES = tuple(
    s for s in TranslationJobStatus if s not in TERMINAL_STATUSES)


def _lease_until(seconds: int = TRANSLATION_JOB_LEASE_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="seconds")


def _older_than(stamp: str, seconds: int) -> bool:
    """Moc thoi gian ISO da cu hon `seconds` giay chua. Doc khong duoc -> False."""
    if not stamp:
        return False
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < datetime.now(timezone.utc) - timedelta(seconds=seconds)

#: Doan van gui cho MOI lan goi provider — kiem soat token cho mot LLM that.
DOAN_KY_TU_MOI_LAN_GOI = 2000

#: Bao nhieu chuong TRUOC duoc tom tat lam ngu canh — xem yeu cau muc 7.
#: 2 la du de nhat quan xung ho/tinh tiet gan nhat ma khong nhet ca cuon vao
#: prompt; qua nhieu chi tang chi phi ma it cai thien lien mach.
SO_CHUONG_TOM_TAT_NGU_CANH = 2

#: Do dai toi da mot cau tom tat chuong — chinh no cung phai gon de khong
#: phinh dan prompt qua nhieu chuong.
DO_DAI_TOM_TAT = 240


#: Thu tu vai-tro provider CHAY THAT cho MOI doan, theo che do chat luong.
#: `NHANH`: chi dich, dung cho ban nhap nhanh. `CAN_BANG`: dich + mot lan QA
#: sua loi cuc bo (khong bien tap van hoc rieng — do la diem KHAC voi
#: `VAN_HOC`, dung y voi yeu cau goc muc 9 "CAN_BANG/VAN_HOC khac nhau o SO
#: LUOT dich that"). `VAN_HOC`: du ba pass — dich, bien tap van hoc, roi QA
#: sua loi cuc bo tren ban da bien tap.
_VAI_TRO_THEO_CHE_DO: Dict[QualityMode, tuple] = {
    QualityMode.NHANH: ("translator",),
    QualityMode.CAN_BANG: ("translator", "qa"),
    QualityMode.VAN_HOC: ("translator", "editor", "qa"),
}


#: Doi so nay khi thay doi CACH GOP prompt he thong/nguoi dung (xem
#: `translation_providers._he_thong_prompt`/`_nguoi_dung_prompt`) de cac muc
#: cache CU (gop theo cach cu) khong bi dung nham lam ket qua cua cach MOI.
_CACHE_PROMPT_VERSION = "v1"


class _KetQuaCache:
    """Mot ket qua da dich LUU TRONG CACHE — giu lai provider/model/nguon
    credential GOC de `ProviderProvenance` cua mot lan CACHE HIT van bao dung
    "ai da dich lan dau", chi kem co `from_cache=True`."""

    __slots__ = ("van_ban", "provider_id", "model_id", "credential_source")

    def __init__(self, van_ban: str, provider_id: str, model_id: str,
                credential_source: str):
        self.van_ban = van_ban
        self.provider_id = provider_id
        self.model_id = model_id
        self.credential_source = credential_source


class _TranslationSegmentCache:
    """
    Cache dich TRONG TIEN TRINH, THEO TUNG INSTANCE `TranslationService` —
    KHONG PHAI mot singleton toan cuc cap module. Mot cache dung CHUNG giua
    nhieu instance (vd giua cac bai test khac nhau trong cung mot tien trinh
    pytest) se lam MOT test ro ri ket qua sang test khac dung chung van ban —
    day la loai loi that de gap va kho tim (test B "tinh co" thanh cong vi
    dung lai ket qua da cache tu test A, thay vi tu goi provider gia cua
    chinh no) nen kien truc nay CO CHU DICH gan cache vao instance, khong
    dung bien cap module.

    Khoa la sha256 cua dau vao anh huong ket qua dich: van ban + MOI truong
    on dinh tu `TranslationContext` (vai_tro/quality_mode/genre/naming_mode/
    glossary/custom_instruction) + `_CACHE_PROMPT_VERSION` — CO CHU DICH
    KHONG gom lua chon provider (provider_mode/selected_provider_id): cache
    nay la "cung dau vao + cung chi dan -> cung ket qua", giong triet ly bo
    nho dich (translation memory) trong cac cong cu CAT, doc lap voi model
    NAO thuc su tao ra no lan dau — chuyen provider khong lam mat gia tri
    cache da co.

    CO CHU DICH KHONG gom `tom_tat_truoc` (tom tat cac chuong TRUOC, xem
    `SO_CHUONG_TOM_TAT_NGU_CANH`): gia tri nay THAY DOI o HAU NHU MOI chuong
    (moi chuong dich xong lai doi tom tat chuong truoc do cua CHINH no) —
    neu dua vao khoa cache, hai doan van GIONG HET nhau o hai chuong khac
    nhau (vd mot cau hoi thoai lap lai, rat thuong gap trong fanfic mang) se
    GAN NHU KHONG BAO GIO trung cache duoc, vo hieu hoa gan het gia tri thuc
    te cua cache nay. Danh doi: mot doan van lap lai co the duoc dich giong
    het nhau du boi canh chuong truoc da doi — chap nhan duoc vi ban than
    tom tat chi la "tri nho long", khong phai mot chi dan NGON NGU truc tiep
    anh huong tu vung/ngu phap cua CHINH doan dang dich.
    """

    GIOI_HAN = 2000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._kho: Dict[str, _KetQuaCache] = {}
        #: FIFO don gian de gioi han kich thuoc — khong can LRU chinh xac,
        #: chi can khong phinh vo han qua mot phien server chay lau.
        self._thu_tu: List[str] = []

    @staticmethod
    def _khoa(text: str, ctx: "TranslationContext") -> str:
        phan = {
            "text": text,
            "vai_tro": ctx.vai_tro,
            "quality_mode": ctx.quality_mode,
            "genre": ctx.genre,
            "naming_mode": ctx.naming_mode,
            "glossary": sorted(ctx.glossary.items()),
            "custom_instruction": ctx.custom_instruction,
            "prompt_version": _CACHE_PROMPT_VERSION,
        }
        tho = json.dumps(phan, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(tho.encode("utf-8")).hexdigest()

    def lay(self, text: str, ctx: "TranslationContext") -> Optional[_KetQuaCache]:
        with self._lock:
            return self._kho.get(self._khoa(text, ctx))

    def luu(self, text: str, ctx: "TranslationContext", *, van_ban: str,
           provider_id: str, model_id: str, credential_source: str) -> None:
        khoa = self._khoa(text, ctx)
        with self._lock:
            if khoa not in self._kho and len(self._thu_tu) >= self.GIOI_HAN:
                cu = self._thu_tu.pop(0)
                self._kho.pop(cu, None)
            if khoa not in self._kho:
                self._thu_tu.append(khoa)
            self._kho[khoa] = _KetQuaCache(
                van_ban=van_ban, provider_id=provider_id, model_id=model_id,
                credential_source=credential_source)


def _tom_tat_tho(van_ban_da_dich: str) -> str:
    """Tom tat THO: cau dau + cau cuoi cua chuong da dich. Khong goi LLM rieng
    cho viec tom tat — mot lan goi them cho MOI chuong la chi phi khong xung
    dang cho loi ich (ngu canh chi can gon, khong can hay)."""
    sach = (van_ban_da_dich or "").strip()
    if len(sach) <= DO_DAI_TOM_TAT:
        return sach
    return sach[:DO_DAI_TOM_TAT].rsplit(" ", 1)[0] + "…"


class TranslationService:
    def __init__(self, store: Any, novel_store: Any,
                 provider: Optional[TranslationProvider] = None,
                 inline_worker: bool = True,
                 max_concurrent_jobs: Optional[int] = None,
                 registry: Optional[ProviderRegistry] = None,
                 byok: Optional[Any] = None):
        self._store = store
        #: Store CUA SAN PHAM AUDIO — chi dung o `import_to_draft`, de tao
        #: novel/chapter that. Khong bang nao khac cua no duoc cham vao.
        self._novel_store = novel_store
        self._provider = provider or build_provider(None)
        #: Part Q1-Q3 — TUY CHON, chi khac None khi wiring vao voi it nhat
        #: mot provider MIEN PHI da cau hinh du (xem `build_provider_registry`
        #: o `main.py`). Khi None, `_dich_mot_chuong` dung THANG `self._provider`
        #: nhu truoc gio — giu nguyen HANH VI VA TUONG THICH cho toan bo test
        #: hien co (~1574 bai), khong bat buoc phai co registry moi chay duoc.
        self._registry = registry if registry else None
        #: V5.1 BYOK — TUY CHON (`ProviderConnectionService`, kieu `Any` de
        #: tranh vong lap import — `translation_byok_service.py` KHONG import
        #: nguoc lai module nay). None = tinh nang BYOK khong tham gia vao
        #: duong dich, hanh vi Y HET truoc khi co V5.1 (chi dung
        #: `self._registry` neu co, roi `self._provider`).
        self._byok = byok

        #: Danh tinh cua TIEN TRINH NAY — hai worker khac nhau (hoac hai
        #: instance service khac nhau, vd trong test mo phong "worker chet
        #: roi tien trinh moi thay the") co gia tri khac nhau.
        self._worker_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        #: job_id -> Thread dang chay job do TRONG TIEN TRINH NAY. Instance
        #: RIENG cho tung `TranslationService` — mot instance moi (vd sau khi
        #: "worker chet") KHONG thay thread cua instance cu, dung y muon khi
        #: mo phong worker restart trong test.
        self._job_threads: Dict[str, threading.Thread] = {}
        self._job_lock = threading.RLock()
        #: Tien trinh NAY co duoc chay job hay khong. Mac dinh True (che do
        #: inline — tien trinh web tu chay job, tien loi cho dev/test, dung
        #: khuon voi `FAS_INLINE_WORKER` cua TTS). `server/translation_worker.py`
        #: (worker rieng) tu dat `inline_worker=False` luc khoi tao roi goi
        #: `enable_job_execution()` — dung mau voi `server/worker.py`.
        self._can_run_jobs = inline_worker
        #: So job THUC SU chay dong thoi TRONG TIEN TRINH NAY — CAU HINH
        #: DUOC (env `FAS_TRANSLATION_MAX_CONCURRENT_JOBS`, mac dinh 3). Moi
        #: chuong goi provider that (LLM) co the mat toi hang chuc giay; khong
        #: co tran nay, mot dot nhieu job cung het lease se sinh mot so
        #: luong khong gioi han, moi luong tu goi mang rieng — co the lam
        #: qua tai backend LLM hoac vuot han muc so request dong thoi cua no.
        self._max_concurrent_jobs = (
            max_concurrent_jobs if max_concurrent_jobs is not None
            else int(os.environ.get("FAS_TRANSLATION_MAX_CONCURRENT_JOBS", "3")))
        #: Cache dich RIENG cua instance nay — xem docstring
        #: `_TranslationSegmentCache` ve ly do KHONG dung bien cap module.
        self._cache = _TranslationSegmentCache()

    # ==================================================================== DU AN

    def create_project(self, owner_id: str, *, title: str, source_text: str,
                       source_filename: str = "",
                       genre: str = "auto", naming_mode: str = "auto",
                       quality_mode: str = "can_bang",
                       custom_instruction: str = "") -> TranslationProject:
        sach = (source_text or "").strip()
        if not sach:
            raise TranslationError("Thiếu nội dung cần dịch.")
        if len(sach) > MAX_CHARS_PER_PROJECT:
            mb = MAX_CHARS_PER_PROJECT
            raise QuotaExceeded(
                f"Nội dung vượt quá {mb:,} ký tự cho một dự án.".replace(",", "."))
        so_chuong = len(tach_chuong(sach))
        if so_chuong > MAX_CHAPTERS_PER_PROJECT:
            raise QuotaExceeded(
                f"Dự án có {so_chuong} chương, vượt trần "
                f"{MAX_CHAPTERS_PER_PROJECT} chương.")
        try:
            genre_e = GenrePreset(genre)
        except ValueError:
            genre_e = GenrePreset.AUTO
        try:
            naming_e = NamingMode(naming_mode)
        except ValueError:
            naming_e = NamingMode.AUTO
        try:
            quality_e = QualityMode(quality_mode)
        except ValueError:
            quality_e = QualityMode.CAN_BANG

        now = now_iso()
        project = TranslationProject(
            owner_id=owner_id,
            title=(title or "").strip()[:200] or "Bản dịch không tên",
            source_text=sach,
            source_filename=source_filename[:200],
            genre=genre_e, naming_mode=naming_e, quality_mode=quality_e,
            custom_instruction=(custom_instruction or "").strip()[:1000],
            created_at=now, updated_at=now,
        )
        return self._store.create_project(project)

    def get_project(self, project_id: str, owner_id: str) -> TranslationProject:
        return self._store.owned_project(project_id, owner_id)

    def list_projects(self, owner_id: str) -> List[TranslationProject]:
        return self._store.list_projects(owner_id)

    def estimate(self, source_text: str) -> Dict[str, int]:
        return uoc_luong(source_text)

    # ==================================================================== JOB

    def create_job(self, project_id: str, owner_id: str) -> TranslationJob:
        """
        Tao job dich cho mot du an. IDEMPOTENT: da co job CHUA KET THUC cho
        du an nay thi tra ve CHINH NO — F5/goi lai khong tao job thu hai.

        TRA VE NGAY o trang thai `queued` — KHONG chay job trong request nay.
        Neu tien trinh nay duoc phep chay job (`self._can_run_jobs`, mac dinh
        True cho dev/test) thi mot thread nen duoc khoi dong ngay sau do,
        nhung route/nguoi goi khong cho no xong. O staging/production,
        `server/translation_worker.py` (tien trinh RIENG) se nhan job nay
        trong vong quet ke tiep. Trinh duyet CHI doc trang thai qua
        `GET /api/translate/jobs/{id}`.
        """
        project = self._store.owned_project(project_id, owner_id)
        dang_chay = self._store.active_job_for_project(project_id)
        if dang_chay is not None:
            return dang_chay

        dang_dung = sum(
            1 for p in self._store.list_projects(owner_id)
            for j in self._store.jobs_for_project(p.project_id)
            if j.status not in TERMINAL_STATUSES)
        if dang_dung >= MAX_CONCURRENT_JOBS_PER_USER:
            raise QuotaExceeded(
                f"Bạn đang có {dang_dung} job dịch chạy đồng thời, "
                f"tối đa {MAX_CONCURRENT_JOBS_PER_USER}.")

        now = now_iso()
        so_chuong = len(tach_chuong(project.source_text))
        job = TranslationJob(project_id=project_id, owner_id=owner_id,
                            total_chapters=so_chuong,
                            created_at=now, updated_at=now)
        job = self._store.create_job(job)
        # Chup TRUOC khi khoi dong thread: neu doc sau `start()`, thread nen
        # co the da doi sang `analyzing` va phan hoi "vua tao" se mo ta sai —
        # cung ly do voi `main.py::create_job` (TTS).
        vua_tao = job
        self._start_job_thread(job, None, f"tr-job-{job.job_id}")
        return vua_tao

    def get_job(self, job_id: str, owner_id: str) -> TranslationJob:
        return self._store.owned_job(job_id, owner_id)

    def cancel_job(self, job_id: str, owner_id: str) -> TranslationJob:
        """
        Huy job. IDEMPOTENT voi job da ket thuc.

        Day la mot TIN HIEU, khong phai mot khoa: worker dang chay job nay (o
        mot thread/tien trinh khac) doc lai trang thai tu kho o giua moi
        chuong VA moi buoc trong may trang thai cua chuong, roi tu dung —
        xem `_run_job`. Ghi o day KHONG can fencing vi day khong phai tranh
        quyen so huu job, chi la mot co bao "dung lai khi tien".
        """
        job = self._store.owned_job(job_id, owner_id)
        if job.status in TERMINAL_STATUSES:
            return job  # idempotent — huy job da xong khong phai loi
        job.status = TranslationJobStatus.CANCELLED
        job.finished_at = now_iso()
        job.updated_at = job.finished_at
        job.lease_owner = ""
        job.lease_expires_at = ""
        return self._store.save_job(job)

    def retry_job(self, job_id: str, owner_id: str) -> TranslationJob:
        """
        Thu lai MOT job da `failed`. Vi tien do da luu o CHUONG (
        `project.translated_chapters`), dat job ve `queued` la du: worker
        tiep theo se tu chay tiep TU CHUONG CON DANG DO (xem `_run_job`),
        khong dich lai cac chuong da xong — day cung la co che "thu lai MOT
        chuong da that bai" ma yeu cau da noi: trong mot duong ong tuan tu,
        chuong "that bai" LUON la chuong dau tien CHUA co trong
        `translated_chapters`, nen khong co truong hop "chuong N loi nhung
        chuong N+1 da xong" — resume va retry la CUNG MOT hanh dong.
        """
        job = self._store.owned_job(job_id, owner_id)
        if job.status is not TranslationJobStatus.FAILED:
            raise TranslationError("Chỉ có thể thử lại job đã thất bại.")
        job.status = TranslationJobStatus.QUEUED
        job.error = ""
        job.finished_at = ""
        job.updated_at = now_iso()
        job = self._store.save_job(job)
        self._start_job_thread(job, None, f"tr-retry-{job.job_id}")
        return job

    # -------------------------------------------------------------- worker

    def enable_job_execution(self) -> None:
        """Cho phep tien trinh nay chay job. CHI `server/translation_worker.py`
        duoc goi — tien trinh web mac dinh da True (che do inline)."""
        self._can_run_jobs = True

    def can_run_jobs(self) -> bool:
        return self._can_run_jobs

    @property
    def worker_id(self) -> str:
        """Danh tinh tien trinh/instance nay — dung trong log cua
        `server/translation_worker.py`. Chi doc, khong doi duoc tu ben ngoai."""
        return self._worker_id

    def job_threads_alive(self) -> int:
        with self._job_lock:
            return sum(1 for t in self._job_threads.values() if t.is_alive())

    def stop_accepting_new_jobs(self) -> None:
        """Ngung NHAN job moi — job dang chay van duoc de tiep tuc. Goi luc
        worker nhan tin hieu dung (xem `server/translation_worker.py`)."""
        self._can_run_jobs = False

    def _start_job_thread(self, job: TranslationJob, fence: Optional[int],
                          ten: str) -> bool:
        """
        Chay job trong thread nen cua CHINH tien trinh nay.

        Tra False va khong lam gi khi tien trinh nay khong duoc phep chay
        job, HOAC da du `self._max_concurrent_jobs` job dang chay — job da
        nam ben vung o `queued`/trang thai do dang, khong mat gi ca, va
        `server/translation_worker.py` (hoac vong quet ke tiep) se nhan no
        khi co cho trong.

        (`create_job` chua claim truoc khi goi ham nay, nen tu choi o day
        khong dot mat luot thu nao — khac voi `recover_stale_jobs`, DA claim
        TRUOC khi goi, nen no tu kiem cho truoc rieng de khong lang phi mot
        claim cho mot job roi khong chay duoc.)
        """
        if not self._can_run_jobs:
            return False
        thread = threading.Thread(target=self._run_job, args=(job, fence),
                                  daemon=True, name=ten)
        with self._job_lock:
            # CHOT CHAN CUOI CUNG trong tien trinh nay — khoa trong bo nho,
            # kiem duoc TRUOC ca mang. Cung ly do voi `main.py::_start_job_thread`.
            dang_chay = self._job_threads.get(job.job_id)
            if dang_chay is not None and dang_chay.is_alive():
                return False
            if self.job_threads_alive() >= self._max_concurrent_jobs:
                return False
            self._job_threads[job.job_id] = thread
        thread.start()
        return True

    def recover_stale_jobs(self,
                          pending_min_age_seconds: Optional[int] = None
                          ) -> Dict[str, int]:
        """
        Tim job CHUA KET THUC da mat worker (lease het han) va chay lai
        DUNG MOT LAN. IDEMPOTENT — chay lai bao nhieu lan cung duoc.

        Cung kien truc voi `main.recover_stale_jobs` (TTS): job `queued` moi
        tinh duoc cho du lau (`pending_min_age_seconds`) truoc khi bi nhan —
        o che do inline thread cua `create_job` dang lo no; worker rieng
        truyen 0 vi khong co thread nao nhu vay ca.
        """
        nguong = (TRANSLATION_JOB_LEASE_SECONDS if pending_min_age_seconds is None
                 else max(0, pending_min_age_seconds))
        report = {"da_quet": 0, "bo_qua_con_lease": 0, "chay_lai": 0,
                 "het_luot_thu": 0, "khong_nhan_duoc": 0, "bo_qua_con_moi": 0}
        if not self._can_run_jobs:
            report["khong_duoc_phep_chay"] = 1
            return report

        candidates: List[TranslationJob] = []
        try:
            for trang_thai in NON_TERMINAL_STATUSES:
                jobs = self._store.list_jobs_by_status(trang_thai)
                if trang_thai is TranslationJobStatus.QUEUED:
                    for job in jobs:
                        if nguong == 0 or _older_than(job.created_at, nguong):
                            candidates.append(job)
                        else:
                            report["bo_qua_con_moi"] += 1
                else:
                    candidates.extend(jobs)
        except Exception:
            return report

        for job in candidates:
            report["da_quet"] += 1
            if job.lease_is_live():
                report["bo_qua_con_lease"] += 1
                continue
            with self._job_lock:
                dang_chay = self._job_threads.get(job.job_id)
            if dang_chay is not None and dang_chay.is_alive():
                report["bo_qua_dang_chay_o_day"] = (
                    report.get("bo_qua_dang_chay_o_day", 0) + 1)
                continue
            # TRAN DONG THOI CAU HINH DUOC — kiem TRUOC khi claim, khong sau:
            # claim TON MOT LUOT THU (`attempts`) cua job; tu choi sau khi da
            # claim se dot mat luot thu do ma khong he chay, day job den
            # `failed` som hon that can thiet. Job o day CHUA claim (van
            # cua worker cu/khong ai giu), nen bo qua o day khong ton gi ca —
            # vong quet SAU se thu lai khi co cho trong.
            if self.job_threads_alive() >= self._max_concurrent_jobs:
                report["bo_qua_qua_tai"] = report.get("bo_qua_qua_tai", 0) + 1
                continue
            if (job.status is not TranslationJobStatus.WAITING_FOR_PROVIDER
                    and (job.attempts or 0) >= TRANSLATION_JOB_MAX_ATTEMPTS):
                job.status = TranslationJobStatus.FAILED
                job.error = (
                    f"Đã thử dịch {job.attempts} lần nhưng lần nào tiến "
                    "trình cũng bị dừng giữa chừng. Hãy thử lại.")
                job.finished_at = now_iso()
                job.updated_at = job.finished_at
                self._store.save_job(job)
                report["het_luot_thu"] += 1
                continue
            try:
                fence = self._store.claim_job(job, self._worker_id, _lease_until())
            except Exception:
                fence = None
            if fence is None:
                report["khong_nhan_duoc"] += 1
                continue
            if self._start_job_thread(job, fence, f"tr-recover-{job.job_id}"):
                report["chay_lai"] += 1
            else:
                report["khong_chay_duoc"] = report.get("khong_chay_duoc", 0) + 1
        return report

    def try_resume_user_jobs(self, user_id: str) -> int:
        """
        V5.1 Part G — goi SAU KHI nguoi dung ket noi THANH CONG mot provider
        ca nhan, de cac job dang `waiting_for_provider` CUA CHINH nguoi do
        duoc thu lai NGAY, khong doi den moc `waiting_retry_at` (co the con
        xa vai phut).

        KHONG tao job moi (van la CHINH job da co), KHONG dich lai chuong da
        xong — chi ep `lease_expires_at` ve qua khu de job do coi la "co the
        nhan lai duoc" ngay lap tuc, roi goi `recover_stale_jobs` mot lan.
        Neu van khong du provider (vd key moi ket noi cung het han muc ngay),
        job tu quay lai `waiting_for_provider` — khong co gi mat.

        Tra ve so job DA THU lai (khong dam bao thanh cong).
        """
        try:
            jobs = self._store.list_jobs_by_status(
                TranslationJobStatus.WAITING_FOR_PROVIDER)
        except Exception:
            return 0
        da_thu = 0
        for job in jobs:
            if job.owner_id != user_id:
                continue
            job.lease_expires_at = "2000-01-01T00:00:00+00:00"
            self._store.save_job(job)
            da_thu += 1
        if da_thu:
            self.recover_stale_jobs(pending_min_age_seconds=0)
        return da_thu

    def _run_job(self, job: TranslationJob, fence: Optional[int]) -> None:
        """
        Nhan job (neu chua co fence), chay den khi xong/loi/mat quyen, roi
        don dep ban ghi thread cua chinh minh. KHONG BAO GIO nem ra ngoai —
        day la ham chay trong mot thread nen, khong ai bat duoc loi tu day.
        """
        if fence is None:
            try:
                fence = self._store.claim_job(job, self._worker_id, _lease_until())
            except Exception:
                fence = None
            if fence is None:
                return

        try:
            project = self._store.get_project(job.project_id)
        except NotFoundError:
            job.status = TranslationJobStatus.FAILED
            job.error = "Dự án dịch đã bị xoá."
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            job.lease_owner = ""
            job.lease_expires_at = ""
            try:
                self._store.save_job_fenced(job, fence, self._worker_id)
            except Exception:
                pass
            return

        beat_stop = threading.Event()
        #: Bat len khi mot worker KHAC da nhan job nay (heartbeat bi tu choi).
        lost = threading.Event()

        def heartbeat() -> None:
            while not beat_stop.wait(TRANSLATION_JOB_HEARTBEAT_SECONDS):
                try:
                    ok = self._store.renew_lease(job.job_id, fence,
                                                 self._worker_id, _lease_until())
                except Exception:
                    continue  # mang chap chon — lease cu con han
                if not ok:
                    lost.set()
                    return

        beater = threading.Thread(target=heartbeat, daemon=True,
                                  name=f"tr-beat-{job.job_id}")
        try:
            job.attempts = fence
            job.lease_owner = self._worker_id
            job.lease_expires_at = _lease_until()
            beater.start()
            self._thuc_thi_job(job, project, fence, lost)
        finally:
            beat_stop.set()
            with self._job_lock:
                if self._job_threads.get(job.job_id) is threading.current_thread():
                    self._job_threads.pop(job.job_id, None)

    def _nen_dung_lai(self, job_id: str, lost: threading.Event) -> bool:
        """
        MOT lan doc kho, tra loi CA HAI cau hoi: co nen dung lai khong, vi
        (a) mat quyen so huu job (worker khac da nhan — bao boi `lost` TU
        heartbeat, hoac phat hien truc tiep o day vi heartbeat chay dinh ky
        chu khong lien tuc), hoac (b) nguoi dung da bam Huy.

        Goi truoc MOI buoc co the ton thoi gian (moi chuong, moi buoc trong
        may trang thai cua chuong, xem `_thuc_thi_job`) — day la ly do huy
        THAT SU co hieu luc "giua cac pass" nhu yeu cau da noi, du khong the
        ngat ngang mot cuoc goi provider dang cho phan hoi.
        """
        if lost.is_set():
            return True
        try:
            hien_tai = self._store.get_job(job_id)
        except NotFoundError:
            return True
        if hien_tai.lease_owner != self._worker_id:
            return True
        return hien_tai.status is TranslationJobStatus.CANCELLED

    def _thuc_thi_job(self, job: TranslationJob, project: TranslationProject,
                      fence: int, lost: threading.Event) -> None:
        """
        Chay LAN LUOT tung chuong CON THIEU: bat dau tu
        `len(project.translated_chapters)`, KHONG phai tu 0 — day la co che
        RESUME THAT. Mot worker chet giua chuong K khong lam mat cac chuong
        1..K-1 (da nam trong `translated_chapters`), va chuong K se duoc lam
        lai TU DAU (chua kip ghi vao `translated_chapters` nen khong co gi
        de mat).
        """
        chuong = tach_chuong(project.source_text)
        bat_dau_tu = len(project.translated_chapters)
        try:
            for idx in range(bat_dau_tu, len(chuong)):
                noi_dung = chuong[idx]
                if self._nen_dung_lai(job.job_id, lost):
                    return

                job.current_chapter = idx + 1
                trang_thai = TranslationJobStatus.ANALYZING
                job.status = trang_thai
                job.current_pass = trang_thai.value
                job.updated_at = now_iso()
                if not self._store.save_job_fenced(job, fence, self._worker_id):
                    return  # mat quyen giua chung — worker khac da nhan

                ban_dich = ""
                provenance_by_role: Dict[str, ProviderProvenance] = {}
                while trang_thai is not TranslationJobStatus.COMPLETED:
                    if self._nen_dung_lai(job.job_id, lost):
                        return
                    if trang_thai is TranslationJobStatus.TRANSLATING:
                        ban_dich, provenance_by_role = self._dich_mot_chuong(
                            project, noi_dung, idx, job, fence, lost)
                        if self._nen_dung_lai(job.job_id, lost):
                            return
                    trang_thai = buoc_tiep_theo(trang_thai, project.quality_mode)
                    if trang_thai is TranslationJobStatus.COMPLETED:
                        # `COMPLETED` o day nghia la "pipeline cua RIENG
                        # chuong nay xong" — KHONG PHAI "ca job xong". Day
                        # la lo hong THAT tung ton tai: ghi gia tri nay vao
                        # `job.status` giua mot tieu thuyet nhieu chuong se
                        # lam mot lan poll dung luc thay `status=completed,
                        # progress=100` du chi moi xong CHUONG DAU. Thoat
                        # vong lap ma KHONG ghi gi them — trang thai THAT
                        # (chuong ke tiep, hoac COMPLETED that cua ca job
                        # sau vong for) se tu ghi de ngay sau day.
                        break
                    job.status = trang_thai
                    job.current_pass = trang_thai.value
                    job.updated_at = now_iso()
                    if not self._store.save_job_fenced(job, fence, self._worker_id):
                        return

                project.translated_chapters.append(ban_dich)
                project.chapter_summaries.append(_tom_tat_tho(ban_dich))
                project.chapter_warnings.append(phat_hien_canh_bao(ban_dich))
                project.updated_at = now_iso()
                self._store.save_project(project)
                self._ghi_version_tu_dong(project.project_id, idx,
                                          ban_dich, provenance_by_role)
                job.current_chapter_done_segments = 0
                job.current_chapter_total_segments = 0

            job.status = TranslationJobStatus.COMPLETED
            job.current_pass = ""
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            job.lease_owner = ""
            job.lease_expires_at = ""
            self._store.save_job_fenced(job, fence, self._worker_id)
        except AllProvidersUnavailable as exc:
            # Part Q4: KHONG PHAI mot loi that — tat ca provider mien phi da
            # cau hinh dang het han muc/gap loi TAM THOI. Nha lease nhung dat
            # `lease_expires_at` bang moc "khong nhan lai truoc" (tai su dung
            # dung co che claim/lease da co — xem `TranslationJobStatus.
            # WAITING_FOR_PROVIDER`): `claim_job`/`recover_stale_jobs` tu bo
            # qua job nay cho toi luc do, KHONG dot mat luot thu nao (da loai
            # tru trang thai nay khoi kiem tra `TRANSLATION_JOB_MAX_ATTEMPTS`
            # o `recover_stale_jobs`). Cac chuong da xong VAN CON NGUYEN.
            retry_at = exc.retry_not_before or _lease_until(
                TRANSLATION_WAITING_DEFAULT_RETRY_SECONDS)
            job.status = TranslationJobStatus.WAITING_FOR_PROVIDER
            job.error = ""
            job.waiting_retry_at = retry_at
            # V5.1 Part G — ly do/hanh dong AN TOAN cho frontend: nguoi dung
            # CHUA co ket noi ca nhan nao thi moi CTA "kết nối Groq cá
            # nhân"; da co roi nhung CUNG het han muc thi chi con cho (khong
            # moi ket noi THEM — ket noi da co khong giup gi luc nay).
            co_ket_noi_ca_nhan = bool(
                self._byok and self._byok.list_connections(job.owner_id))
            if co_ket_noi_ca_nhan:
                job.waiting_reason = "personal_quota_exhausted"
                job.waiting_action = ""
            else:
                job.waiting_reason = "shared_free_quota_exhausted"
                job.waiting_action = "connect_personal_provider"
            job.updated_at = now_iso()
            job.lease_owner = ""
            job.lease_expires_at = retry_at
            self._store.save_job_fenced(job, fence, self._worker_id)
        except TranslationProviderError as exc:
            job.status = TranslationJobStatus.FAILED
            job.error = self._loi_an_toan(exc)
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            job.lease_owner = ""
            job.lease_expires_at = ""
            self._store.save_job_fenced(job, fence, self._worker_id)
        except Exception as exc:
            # Loi khong luong truoc (bug, mang chap chon o mot cho khac...) —
            # job PHAI thanh `failed`, tuyet doi khong duoc phep im lang treo
            # o trang thai dang chay mai. Cung nguyen tac voi
            # `main._run_job` (TTS): mot ngoai le la chuyen "trang thai job",
            # khong phai mot tien trinh sap.
            job.status = TranslationJobStatus.FAILED
            job.error = self._loi_an_toan(exc)
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            job.lease_owner = ""
            job.lease_expires_at = ""
            try:
                self._store.save_job_fenced(job, fence, self._worker_id)
            except Exception:
                pass

    def _goi_dich_mot_doan(self, text: str, ctx: TranslationContext,
                           project: TranslationProject,
                           personal_providers: List["ConfiguredProvider"],
                           allow_cache: bool = True
                           ) -> "tuple[str, ProviderProvenance]":
        """
        MOT diem goi DUY NHAT vao provider/registry — dung boi CA
        `_dich_mot_chuong` (job nen) LAN `_chay_vai_tro_tren_van_ban` (editor,
        Part N). V5.1 BYOK: neu co `self._byok`, dung
        `translate_segment_with_personal` (Fanfic chung + ca nhan cua CHINH
        chu du an theo dung thu tu `project.prefer_personal_provider`);
        neu khong, hanh vi Y HET truoc V5.1.

        Cache (xem `_TranslationSegmentCache`) duoc kiem TRUOC TIEN khi
        `allow_cache=True` — trung cache thi tra ve NGAY, KHONG cham toi
        provider/registry nao (khong ton request/token, khong ghi usage gia).
        Chi ket qua THANH CONG moi duoc luu vao cache — loi khong bao gio
        duoc cache (mot lan loi tam thoi khong duoc phep "dinh" mai trong
        cache).

        `allow_cache=False` (dung boi `_chay_vai_tro_tren_van_ban`, tuc MOI
        hanh dong "dịch lại"/"chạy lại pass" cua nguoi dung — Part N): nguoi
        dung bam "Dịch lại đoạn/chương này" ro rang MUON mot KET QUA MOI, dung
        cache o day se tra ve Y HET ban dich cu, pha vo hoan toan muc dich
        cua nut "dịch lại". CHI duong ong TU DONG (`_dich_mot_chuong`) moi
        duoc dung cache — gia tri that cua no la tranh dich lai NHUNG DOAN DA
        TUNG THANH CONG khi mot chuong phai lam lai tu dau sau
        `waiting_for_provider` (xem `_thuc_thi_job`), hoac cac doan trung
        lap tu nhien giua nhieu chuong (hoi thoai/cau van lap lai).
        """
        cache_hit = self._cache.lay(text, ctx) if allow_cache else None
        if cache_hit is not None:
            return cache_hit.van_ban, ProviderProvenance(
                provider_id=cache_hit.provider_id, model_id=cache_hit.model_id,
                pass_type=ctx.vai_tro, success=True, attempted_at=now_iso(),
                credential_source=cache_hit.credential_source, from_cache=True)

        if self._registry and self._byok:
            ket_qua, prov = self._registry.translate_segment_with_personal(
                text, context=ctx, mode=project.provider_mode,
                selected_provider_id=project.selected_provider_id,
                allow_fallback=project.allow_fallback,
                personal_providers=personal_providers,
                prefer_personal=project.prefer_personal_provider)
        elif self._registry:
            ket_qua, prov = self._registry.translate_segment(
                text, context=ctx, mode=project.provider_mode,
                selected_provider_id=project.selected_provider_id,
                allow_fallback=project.allow_fallback)
        else:
            van_ban = self._provider.translate_segment(text, context=ctx)
            ket_qua, prov = van_ban, ProviderProvenance(
                provider_id=self._provider.name, model_id="",
                pass_type=ctx.vai_tro, success=True, attempted_at=now_iso())

        if allow_cache:
            self._cache.luu(text, ctx, van_ban=ket_qua, provider_id=prov.provider_id,
                           model_id=prov.model_id, credential_source=prov.credential_source)
        return ket_qua, prov

    def _dich_mot_chuong(self, project: TranslationProject, noi_dung: str,
                         chuong_idx: int, job: TranslationJob,
                         fence: int, lost: threading.Event
                         ) -> "tuple[str, Dict[str, ProviderProvenance]]":
        doan = tach_doan_trong_chuong(noi_dung, DOAN_KY_TU_MOI_LAN_GOI)
        job.current_chapter_total_segments = len(doan)
        self._store.save_progress(
            job.job_id, fence, self._worker_id,
            current_chapter_total_segments=len(doan))

        tom_tat = "\n".join(
            project.chapter_summaries[max(0, chuong_idx - SO_CHUONG_TOM_TAT_NGU_CANH):
                                      chuong_idx])
        glossary = {e.original: e.translated
                    for e in self._store.list_glossary(project.project_id)}

        vai_tro_ds = _VAI_TRO_THEO_CHE_DO[project.quality_mode]
        ket_qua = []
        #: Provider/model xu ly LAN CUOI moi vai tro trong chuong nay (Part
        #: Q5) — don gian hoa co chu dich: neu AUTO fallback giua chung mot
        #: chuong dai nhieu doan, gia tri o day la provider CUOI CUNG chu
        #: khong phai tung doan rieng — du de biet "chuong nay ai dich",
        #: khong nham lam mot so lieu benchmark tung-doan chi tiet hon.
        provenance_by_role: Dict[str, ProviderProvenance] = {}
        # V5.1 BYOK — xay danh sach provider CA NHAN cua CHU du an MOT LAN
        # cho ca chuong (khong giai ma lai moi doan) — xem
        # `_goi_dich_mot_doan`.
        personal_providers = (
            self._byok.build_all_configured_providers(project.owner_id)
            if self._byok else [])
        try:
            for i, phan in enumerate(doan):
                # Kiem huy/mat quyen GIUA TUNG DOAN — min hon "giua cac pass":
                # mot chuong dai nhieu doan khong phai cho het chuong moi biet
                # nguoi dung da bam Huy.
                if self._nen_dung_lai(job.job_id, lost):
                    return "\n\n".join(ket_qua), provenance_by_role
                # Ba pass THAT (khong chi may trang thai): dich truoc, roi lan
                # luot chuyen ket qua qua bien tap/QA neu che do yeu cau — moi
                # vai tro nhan dau ra cua vai tro TRUOC lam van ban dau vao.
                dich = phan
                for vai_tro in vai_tro_ds:
                    ctx = TranslationContext(
                        vai_tro=vai_tro, quality_mode=project.quality_mode.value,
                        genre=project.genre.value,
                        naming_mode=project.naming_mode.value,
                        tom_tat_truoc=tom_tat, glossary=glossary,
                        custom_instruction=project.custom_instruction)
                    dich, prov = self._goi_dich_mot_doan(
                        dich, ctx, project, personal_providers)
                    provenance_by_role[vai_tro] = prov
                ket_qua.append(dich)
                job.current_chapter_done_segments = i + 1
                job.updated_at = now_iso()
                self._store.save_progress(
                    job.job_id, fence, self._worker_id,
                    current_chapter_done_segments=i + 1)
        finally:
            # Dong bo trang thai provider CA NHAN xuong kho ben vung NGAY CA
            # KHI that bai (vd `AllProvidersUnavailable` bay len) — nguoi
            # dung can thay "Groq của bạn đã đạt giới hạn" ma khong phai tu
            # bam "Kiểm tra lại" (xem `ProviderConnectionService.sync_status`).
            if self._byok:
                for cp in personal_providers:
                    self._byok.sync_status(project.owner_id, cp)

        ban_ghep = "\n\n".join(ket_qua)
        # Ap khoa glossary SAU CUNG — rao chan cuoi, xem
        # `translation.ap_dung_khoa_glossary`. O day ap theo tung tu THAY THE
        # TRUC TIEP trong van ban da dich (khac ham chinh, von lam viec tren
        # mot dict de xuat — o day dau ra la VAN BAN, khong phai dict).
        for e in self._store.list_glossary(project.project_id):
            if e.locked and e.original in ban_ghep:
                ban_ghep = ban_ghep.replace(e.original, e.translated)
        return ban_ghep, provenance_by_role

    def _ghi_version_tu_dong(self, project_id: str, chuong_idx: int,
                             ban_dich: str,
                             provenance_by_role: Dict[str, "ProviderProvenance"]
                             ) -> None:
        """Ghi MOT ban ghi lich su cho MOI vai tro da chay trong lan dich TU
        DONG nay cua chuong (Part O + Q5 dung chung MOT co che). Khong bao
        gio nem loi ra ngoai — mat mot ban ghi provenance khong duoc phep lam
        hong ca job dich."""
        try:
            for vai_tro, prov in provenance_by_role.items():
                self._store.add_version(TranslationVersion(
                    project_id=project_id, chapter_index=chuong_idx,
                    operation="auto_translate", pass_type=vai_tro,
                    previous_text="", new_text=ban_dich,
                    provider_id=prov.provider_id, model_id=prov.model_id,
                    created_at=now_iso_us()))
        except Exception:
            pass

    @staticmethod
    def _loi_an_toan(exc: Exception) -> str:
        """Thong diep loi DA LAM SACH — khong ro ri chi tiet noi bo/stack."""
        return str(exc)[:300] or "Lỗi không xác định từ nhà cung cấp dịch."

    # ==================================================================== GLOSSARY

    def add_glossary_entry(self, project_id: str, owner_id: str, *,
                           category: str, original: str, translated: str,
                           note: str = "") -> GlossaryEntry:
        self._store.owned_project(project_id, owner_id)
        goc, dich, note = kiem_glossary_entry(
            original=original, translated=translated, note=note)
        if len(self._store.list_glossary(project_id)) >= 2000:
            raise QuotaExceeded("Từ điển dự án đã đạt trần 2000 mục.")
        try:
            cat = GlossaryCategory(category)
        except ValueError:
            cat = GlossaryCategory.OTHER
        now = now_iso()
        entry = GlossaryEntry(
            term_id=f"gls_{abs(hash((project_id, goc))) % (10 ** 12):012x}",
            project_id=project_id, category=cat, original=goc,
            translated=dich, note=note, created_at=now, updated_at=now)
        return self._store.add_glossary_entry(entry)

    def update_glossary_entry(self, project_id: str, owner_id: str,
                              term_id: str, *,
                              translated: Optional[str] = None,
                              note: Optional[str] = None,
                              locked: Optional[bool] = None) -> GlossaryEntry:
        self._store.owned_project(project_id, owner_id)
        entry = self._store.get_glossary_entry(project_id, term_id)
        if translated is not None:
            _, dich, _ = kiem_glossary_entry(
                original=entry.original, translated=translated)
            entry.translated = dich
        if note is not None:
            _, _, note_sach = kiem_glossary_entry(
                original=entry.original, translated=entry.translated, note=note)
            entry.note = note_sach
        if locked is not None:
            entry.locked = bool(locked)
        entry.updated_at = now_iso()
        return self._store.save_glossary_entry(entry)

    def delete_glossary_entry(self, project_id: str, owner_id: str,
                              term_id: str) -> None:
        self._store.owned_project(project_id, owner_id)
        entry = self._store.get_glossary_entry(project_id, term_id)
        if entry.locked:
            raise TranslationError(
                "Thuật ngữ đã khoá — mở khoá trước khi xoá.")
        self._store.delete_glossary_entry(project_id, term_id)

    def list_glossary(self, project_id: str, owner_id: str) -> List[GlossaryEntry]:
        self._store.owned_project(project_id, owner_id)
        return self._store.list_glossary(project_id)

    # ==================================================================== EDITOR (Part N)

    def _kiem_tra_sua_tay(self, project_id: str, chuong_idx: int,
                          force: bool) -> None:
        """CANH BAO TRUOC khi mot hanh dong tai sinh sap ghi de sua tay —
        xem `ManualEditWouldBeOverwritten`. `force=True` bo qua kiem tra nay
        (nguoi dung da xac nhan o hop thoai)."""
        if force:
            return
        gan_nhat = self._store.list_versions(project_id, chapter_index=chuong_idx)
        if gan_nhat and gan_nhat[0].pass_type == "manual":
            raise ManualEditWouldBeOverwritten(
                "Chương này đã được chỉnh sửa thủ công sau lần dịch gần "
                "nhất. Việc tạo lại sẽ GHI ĐÈ nội dung đã sửa.")

    def _chay_vai_tro_tren_van_ban(self, van_ban: str, vai_tro_ds: tuple,
                                   project: TranslationProject, chuong_idx: int
                                   ) -> "tuple[str, Optional[ProviderProvenance]]":
        """
        Chay MOT hoac nhieu vai tro LIEN TIEP tren MOT khoi van ban tuy y —
        dung cho cac hanh dong editor (regen doan/chuong, chay lai mot pass),
        KHAC voi `_dich_mot_chuong` (danh RIENG cho vong lap job nen, giu
        nguyen khong doi de khong anh huong hanh vi/test da co).

        Van chia nho theo `tach_doan_trong_chuong` truoc khi goi provider —
        cung gioi han kich thuoc voi duong ong tu dong, tranh mot doan qua
        dai vuot kha nang MOT lan goi.
        """
        doan = tach_doan_trong_chuong(van_ban, DOAN_KY_TU_MOI_LAN_GOI)
        tom_tat = "\n".join(project.chapter_summaries[
            max(0, chuong_idx - SO_CHUONG_TOM_TAT_NGU_CANH):chuong_idx])
        glossary = {e.original: e.translated
                    for e in self._store.list_glossary(project.project_id)}
        ket_qua = []
        prov: Optional[ProviderProvenance] = None
        personal_providers = (
            self._byok.build_all_configured_providers(project.owner_id)
            if self._byok else [])
        try:
            for phan in doan:
                dich = phan
                for vai_tro in vai_tro_ds:
                    ctx = TranslationContext(
                        vai_tro=vai_tro, quality_mode=project.quality_mode.value,
                        genre=project.genre.value,
                        naming_mode=project.naming_mode.value,
                        tom_tat_truoc=tom_tat, glossary=glossary,
                        custom_instruction=project.custom_instruction)
                    dich, prov = self._goi_dich_mot_doan(
                        dich, ctx, project, personal_providers,
                        allow_cache=False)
                ket_qua.append(dich)
        finally:
            if self._byok:
                for cp in personal_providers:
                    self._byok.sync_status(project.owner_id, cp)
        ban_ghep = "\n\n".join(ket_qua)
        for e in self._store.list_glossary(project.project_id):
            if e.locked and e.original in ban_ghep:
                ban_ghep = ban_ghep.replace(e.original, e.translated)
        return ban_ghep, prov

    @staticmethod
    def _kiem_tra_chuong_da_dich(project: TranslationProject, chuong_idx: int
                                 ) -> None:
        so_chuong = len(tach_chuong(project.source_text))
        if chuong_idx < 0 or chuong_idx >= so_chuong:
            raise TranslationError("Không có chương này trong dự án.")
        if chuong_idx >= len(project.translated_chapters):
            raise TranslationError(
                "Chương này chưa được dịch xong, chưa thể chỉnh sửa.")

    def get_chapter_detail(self, project_id: str, owner_id: str,
                           chuong_idx: int) -> Dict[str, Any]:
        """Toan bo du lieu editor can cho MOT chuong: nguon, ban dich, canh
        bao, doan hien thi (nguon+dich), tom tat chuong truoc, da sua tay hay
        chua. Cho phep xem chuong CHUA dich xong (ban dich rong) — nguoi dung
        van muon doc nguon truoc khi job toi luot no."""
        project = self._store.owned_project(project_id, owner_id)
        chuong_goc = tach_chuong(project.source_text)
        so_chuong = len(chuong_goc)
        if chuong_idx < 0 or chuong_idx >= so_chuong:
            raise TranslationError("Không có chương này trong dự án.")
        nguon = chuong_goc[chuong_idx]
        da_dich = (project.translated_chapters[chuong_idx]
                  if chuong_idx < len(project.translated_chapters) else "")
        canh_bao = (project.chapter_warnings[chuong_idx]
                   if chuong_idx < len(project.chapter_warnings) else [])
        lich_su = self._store.list_versions(project_id, chapter_index=chuong_idx)
        return {
            "chapter_index": chuong_idx,
            "chapter_count": so_chuong,
            "source_text": nguon,
            "translated_text": da_dich,
            "source_paragraphs": tach_doan_hien_thi(nguon),
            "translated_paragraphs": tach_doan_hien_thi(da_dich),
            "warnings": canh_bao,
            "manually_edited": bool(lich_su) and lich_su[0].pass_type == "manual",
            "previous_chapter_summary": (
                project.chapter_summaries[chuong_idx - 1]
                if 0 < chuong_idx <= len(project.chapter_summaries) else ""),
            "is_translated": chuong_idx < len(project.translated_chapters),
        }

    def save_chapter_edit(self, project_id: str, owner_id: str,
                          chuong_idx: int, new_text: str) -> Dict[str, Any]:
        """Luu sua tay CUA NGUOI DUNG cho MOT chuong — luon cho phep (KHONG
        qua kiem tra `_kiem_tra_sua_tay`: sua tay khong bao gio "ghi de" sua
        tay cua chinh minh, chi co CAC HANH DONG TAI SINH moi can canh bao)."""
        project = self._store.owned_project(project_id, owner_id)
        self._kiem_tra_chuong_da_dich(project, chuong_idx)
        cu = project.translated_chapters[chuong_idx]
        moi = (new_text or "").strip()
        if not moi:
            raise TranslationError("Nội dung bản dịch không được để trống.")
        project.translated_chapters[chuong_idx] = moi
        while len(project.chapter_warnings) <= chuong_idx:
            project.chapter_warnings.append([])
        project.chapter_warnings[chuong_idx] = phat_hien_canh_bao(moi)
        project.updated_at = now_iso()
        self._store.save_project(project)
        self._store.add_version(TranslationVersion(
            project_id=project_id, chapter_index=chuong_idx,
            operation="manual_edit", pass_type="manual",
            previous_text=cu, new_text=moi, actor_id=owner_id,
            created_at=now_iso_us()))
        return self.get_chapter_detail(project_id, owner_id, chuong_idx)

    def regenerate_chapter(self, project_id: str, owner_id: str,
                           chuong_idx: int, force: bool = False
                           ) -> Dict[str, Any]:
        """Dich lai TOAN BO mot chuong tu NGUON — dong bo (nguoi dung bam va
        cho ket qua), KHONG qua job nen: day la MOT chuong, khac han "chay
        toan bo tieu thuyet trong mot request" ma kien truc worker nen (Part
        K) ton tai de tranh."""
        project = self._store.owned_project(project_id, owner_id)
        self._kiem_tra_chuong_da_dich(project, chuong_idx)
        self._kiem_tra_sua_tay(project_id, chuong_idx, force)
        chuong_goc = tach_chuong(project.source_text)
        cu = project.translated_chapters[chuong_idx]
        vai_tro_ds = _VAI_TRO_THEO_CHE_DO[project.quality_mode]
        moi, prov = self._chay_vai_tro_tren_van_ban(
            chuong_goc[chuong_idx], vai_tro_ds, project, chuong_idx)
        project.translated_chapters[chuong_idx] = moi
        project.chapter_summaries[chuong_idx] = _tom_tat_tho(moi)
        while len(project.chapter_warnings) <= chuong_idx:
            project.chapter_warnings.append([])
        project.chapter_warnings[chuong_idx] = phat_hien_canh_bao(moi)
        project.updated_at = now_iso()
        self._store.save_project(project)
        self._store.add_version(TranslationVersion(
            project_id=project_id, chapter_index=chuong_idx,
            operation="regenerate_chapter", pass_type=vai_tro_ds[-1],
            previous_text=cu, new_text=moi, actor_id=owner_id,
            provider_id=(prov.provider_id if prov else ""),
            model_id=(prov.model_id if prov else ""),
            created_at=now_iso_us()))
        return self.get_chapter_detail(project_id, owner_id, chuong_idx)

    def regenerate_paragraph(self, project_id: str, owner_id: str,
                             chuong_idx: int, doan_idx: int,
                             force: bool = False) -> Dict[str, Any]:
        """
        Dich lai MOT doan hien thi trong chuong, GIU NGUYEN phan con lai —
        yeu cau bat buoc cua Part N: "Paragraph regeneration must preserve
        the rest of the chapter exactly."

        Gia dinh so doan NGUON va so doan DA DICH khop nhau (chia cung mot bo
        tach `tach_doan_hien_thi`) — dung voi da so ban dich van xuoi giu
        nguyen so doan; neu mot provider tung gop/tach doan lam lech so
        luong, ham nay bao loi ro rang thay vi ghi sai vi tri.
        """
        project = self._store.owned_project(project_id, owner_id)
        self._kiem_tra_chuong_da_dich(project, chuong_idx)
        self._kiem_tra_sua_tay(project_id, chuong_idx, force)
        chuong_goc = tach_chuong(project.source_text)
        doan_nguon = tach_doan_hien_thi(chuong_goc[chuong_idx])
        cu_toan_chuong = project.translated_chapters[chuong_idx]
        doan_dich = tach_doan_hien_thi(cu_toan_chuong)
        if not (0 <= doan_idx < len(doan_nguon)):
            raise TranslationError("Không có đoạn này trong chương.")
        if len(doan_dich) != len(doan_nguon):
            raise TranslationError(
                "Số đoạn bản dịch không khớp số đoạn nguồn (có thể do một "
                "lần dịch trước đã gộp/tách đoạn) — hãy dùng \"Dịch lại cả "
                "chương\" thay vì từng đoạn.")

        vai_tro_ds = _VAI_TRO_THEO_CHE_DO[project.quality_mode]
        doan_moi, prov = self._chay_vai_tro_tren_van_ban(
            doan_nguon[doan_idx], vai_tro_ds, project, chuong_idx)
        doan_dich[doan_idx] = doan_moi
        moi_toan_chuong = "\n\n".join(doan_dich)
        project.translated_chapters[chuong_idx] = moi_toan_chuong
        while len(project.chapter_warnings) <= chuong_idx:
            project.chapter_warnings.append([])
        project.chapter_warnings[chuong_idx] = phat_hien_canh_bao(moi_toan_chuong)
        project.updated_at = now_iso()
        self._store.save_project(project)
        self._store.add_version(TranslationVersion(
            project_id=project_id, chapter_index=chuong_idx,
            paragraph_index=doan_idx,
            operation="regenerate_paragraph", pass_type=vai_tro_ds[-1],
            previous_text=cu_toan_chuong, new_text=moi_toan_chuong,
            actor_id=owner_id,
            provider_id=(prov.provider_id if prov else ""),
            model_id=(prov.model_id if prov else ""),
            created_at=now_iso_us()))
        return self.get_chapter_detail(project_id, owner_id, chuong_idx)

    def rerun_pass(self, project_id: str, owner_id: str, chuong_idx: int,
                   pass_type: str, force: bool = False) -> Dict[str, Any]:
        """Chay LAI DUNG MOT pass ("translator"|"editor"|"qa") tren ban dich
        HIEN TAI cua chuong (KHONG dich lai tu nguon) — vi du "chay lai rieng
        QA" sau khi da tu sua tay phan con lai."""
        if pass_type not in ("translator", "editor", "qa"):
            raise TranslationError(
                "Chỉ có thể chạy lại translator/editor/qa.")
        project = self._store.owned_project(project_id, owner_id)
        self._kiem_tra_chuong_da_dich(project, chuong_idx)
        self._kiem_tra_sua_tay(project_id, chuong_idx, force)
        cu = project.translated_chapters[chuong_idx]
        moi, prov = self._chay_vai_tro_tren_van_ban(
            cu, (pass_type,), project, chuong_idx)
        project.translated_chapters[chuong_idx] = moi
        while len(project.chapter_warnings) <= chuong_idx:
            project.chapter_warnings.append([])
        project.chapter_warnings[chuong_idx] = phat_hien_canh_bao(moi)
        project.updated_at = now_iso()
        self._store.save_project(project)
        self._store.add_version(TranslationVersion(
            project_id=project_id, chapter_index=chuong_idx,
            operation="rerun_pass", pass_type=pass_type,
            previous_text=cu, new_text=moi, actor_id=owner_id,
            provider_id=(prov.provider_id if prov else ""),
            model_id=(prov.model_id if prov else ""),
            created_at=now_iso_us()))
        return self.get_chapter_detail(project_id, owner_id, chuong_idx)

    # ==================================================================== LICH SU (Part O)

    def list_versions(self, project_id: str, owner_id: str,
                      chuong_idx: Optional[int] = None
                      ) -> List[TranslationVersion]:
        self._store.owned_project(project_id, owner_id)
        return self._store.list_versions(project_id, chapter_index=chuong_idx)

    def restore_version(self, project_id: str, owner_id: str,
                        version_id: str) -> Dict[str, Any]:
        """
        Phuc hoi mot phien ban CU cua mot chuong — ghi THEM mot ban ghi moi
        (`operation="restore"`), KHONG xoa lich su sau diem do (Part O:
        "Do not build Git complexity", giu tinh chat ADDITIVE).
        """
        project = self._store.owned_project(project_id, owner_id)
        phien_ban = self._store.get_version(project_id, version_id)
        chuong_idx = phien_ban.chapter_index
        self._kiem_tra_chuong_da_dich(project, chuong_idx)
        cu = project.translated_chapters[chuong_idx]
        moi = phien_ban.new_text
        project.translated_chapters[chuong_idx] = moi
        while len(project.chapter_warnings) <= chuong_idx:
            project.chapter_warnings.append([])
        project.chapter_warnings[chuong_idx] = phat_hien_canh_bao(moi)
        project.updated_at = now_iso()
        self._store.save_project(project)
        self._store.add_version(TranslationVersion(
            project_id=project_id, chapter_index=chuong_idx,
            operation="restore", pass_type=phien_ban.pass_type,
            previous_text=cu, new_text=moi, actor_id=owner_id,
            provider_id=phien_ban.provider_id, model_id=phien_ban.model_id,
            created_at=now_iso_us()))
        return self.get_chapter_detail(project_id, owner_id, chuong_idx)

    # ==================================================================== PROVIDER (Part Q)

    def provider_catalog(self) -> List[Dict[str, Any]]:
        """Danh sach AN TOAN de tra ve qua API — xem
        `ProviderCatalogEntry.to_dict` (KHONG BAO GIO chua api key/secret)."""
        if not self._registry:
            return []
        return [e.to_dict() for e in self._registry.catalog()]

    def update_provider_settings(self, project_id: str, owner_id: str, *,
                                 provider_mode: Optional[str] = None,
                                 selected_provider_id: Optional[str] = None,
                                 allow_fallback: Optional[bool] = None,
                                 prefer_personal_provider: Optional[bool] = None,
                                 ) -> TranslationProject:
        project = self._store.owned_project(project_id, owner_id)
        if provider_mode is not None:
            if provider_mode not in ("auto", "manual"):
                raise TranslationError("provider_mode chỉ nhận auto/manual.")
            project.provider_mode = provider_mode
        if selected_provider_id is not None:
            project.selected_provider_id = selected_provider_id
        if allow_fallback is not None:
            project.allow_fallback = bool(allow_fallback)
        if prefer_personal_provider is not None:
            project.prefer_personal_provider = bool(prefer_personal_provider)
        project.updated_at = now_iso()
        return self._store.save_project(project)

    # ==================================================================== NHAP VAO TRUYEN

    def import_to_draft(self, project_id: str, owner_id: str, *,
                        novel_id: str = "",
                        new_novel_title: str = "") -> Dict[str, Any]:
        """
        Dua ban dich vao truyen nhap THAT cua Fanfic World.

        IDEMPOTENT theo mot cach CO CHU DICH: goi lai SAU KHI da nhap thanh
        cong se KHONG tao them ban sao — tra ve novel_id da nhap truoc do.
        Nguoi dung muon nhap them chuong moi (sau khi dich tiep) thi dung
        route rieng cho tung chuong — ngoai pham vi ban dau nay.
        """
        project = self._store.owned_project(project_id, owner_id)
        if project.imported_to_novel_id:
            return {"novel_id": project.imported_to_novel_id,
                    "already_imported": True, "chapters_created": 0}
        if not project.translated_chapters:
            raise TranslationError(
                "Chưa có chương nào dịch xong để nhập.")

        if novel_id:
            novel = self._novel_store.owned_novel(novel_id, owner_id)
        else:
            from server.domain import Novel

            novel = self._novel_store.create_novel(Novel(
                owner_id=owner_id,
                title=(new_novel_title or project.title).strip()[:200],
            ))

        chuong_goc = tach_chuong(project.source_text)
        so_tao = 0
        from server.domain import Chapter

        for i, ban_dich in enumerate(project.translated_chapters):
            if not ban_dich:
                continue
            tieu_de = f"Chương {i + 1}"
            self._novel_store.create_chapter(Chapter(
                novel_id=novel.novel_id, owner_id=owner_id,
                title=tieu_de, content=ban_dich, order_index=i + 1,
            ))
            so_tao += 1

        project.imported_to_novel_id = novel.novel_id
        project.updated_at = now_iso()
        self._store.save_project(project)
        return {"novel_id": novel.novel_id, "already_imported": False,
                "chapters_created": so_tao}
