"""
Tang dich vu Novel Translation Studio (V5).

Cung triet ly voi `SocialService`/`CreatorService`: MOI duong ghi di qua day.
Khong biet gi ve HTTP — nem `TranslationError`/`NotFoundError`/
`PermissionDenied`, tang route (`main.py`) doi thanh ma trang thai.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from server.adapters import NotFoundError, PermissionDenied
from server.domain import now_iso
from server.translation import (
    GenrePreset,
    GlossaryCategory,
    GlossaryEntry,
    NamingMode,
    QualityMode,
    QuotaExceeded,
    TranslationError,
    TranslationJobStatus,
    ap_dung_khoa_glossary,
    buoc_tiep_theo,
    kiem_glossary_entry,
    tach_chuong,
    tach_doan_trong_chuong,
    uoc_luong,
)
from server.translation_domain import TranslationJob, TranslationProject
from server.translation_providers import (
    TranslationContext,
    TranslationProvider,
    TranslationProviderError,
    build_provider,
)

#: Tran cau hinh — doc tu bien moi truong o `server/config.py` khi wiring vao
#: main.py; hang so o day la GIA TRI MAC DINH cho luc kiem thu truc tiep.
MAX_CHARS_PER_PROJECT = 300_000
MAX_CHAPTERS_PER_PROJECT = 200
MAX_CONCURRENT_JOBS_PER_USER = 3

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
                 provider: Optional[TranslationProvider] = None):
        self._store = store
        #: Store CUA SAN PHAM AUDIO — chi dung o `import_to_draft`, de tao
        #: novel/chapter that. Khong bang nao khac cua no duoc cham vao.
        self._novel_store = novel_store
        self._provider = provider or build_provider(None)

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
        """
        project = self._store.owned_project(project_id, owner_id)
        dang_chay = self._store.active_job_for_project(project_id)
        if dang_chay is not None:
            return dang_chay

        dang_dung = sum(
            1 for p in self._store.list_projects(owner_id)
            for j in self._store.jobs_for_project(p.project_id)
            if j.status not in (TranslationJobStatus.COMPLETED,
                                TranslationJobStatus.FAILED,
                                TranslationJobStatus.CANCELLED))
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
        # Mock KHONG co do tre mang — chay het NGAY trong request nay la mot
        # don gian hoa CO Y, ghi ro trong bao cao V5: mot worker nen rieng
        # (nhu `server/worker.py` cua TTS) la buoc tiep theo khi co API that
        # va thoi gian cho dai hon mot request HTTP nen chiu duoc.
        return self._chay_toi_khi_xong(job, project)

    def get_job(self, job_id: str, owner_id: str) -> TranslationJob:
        return self._store.owned_job(job_id, owner_id)

    def cancel_job(self, job_id: str, owner_id: str) -> TranslationJob:
        job = self._store.owned_job(job_id, owner_id)
        if job.status in (TranslationJobStatus.COMPLETED,
                         TranslationJobStatus.FAILED,
                         TranslationJobStatus.CANCELLED):
            return job  # idempotent — huy job da xong khong phai loi
        job.status = TranslationJobStatus.CANCELLED
        job.finished_at = now_iso()
        job.updated_at = job.finished_at
        return self._store.save_job(job)

    def _chay_toi_khi_xong(self, job: TranslationJob,
                           project: TranslationProject) -> TranslationJob:
        """
        Chay LAN LUOT tung chuong: moi chuong tu di het may trang thai (tu
        ANALYZING den COMPLETED-cua-chuong-do), roi vong lap ngoai chuyen
        sang chuong ke tiep (dat lai trang thai ve ANALYZING). CHI khi het
        chuong CUOI CUNG job moi thuc su ket thuc (kem `finished_at`).
        """
        chuong = tach_chuong(project.source_text)
        try:
            for idx, noi_dung in enumerate(chuong):
                if job.status is TranslationJobStatus.CANCELLED:
                    return job
                job.current_chapter = idx + 1
                trang_thai = TranslationJobStatus.ANALYZING
                job.status = trang_thai
                job.updated_at = now_iso()
                self._store.save_job(job)

                ban_dich = ""
                while trang_thai is not TranslationJobStatus.COMPLETED:
                    if trang_thai is TranslationJobStatus.TRANSLATING:
                        ban_dich = self._dich_mot_chuong(project, noi_dung,
                                                         idx, job)
                    trang_thai = buoc_tiep_theo(trang_thai, project.quality_mode)
                    job.status = trang_thai
                    job.updated_at = now_iso()
                    self._store.save_job(job)

                project.translated_chapters.append(ban_dich)
                project.chapter_summaries.append(_tom_tat_tho(ban_dich))
                project.updated_at = now_iso()
                self._store.save_project(project)
                job.current_chapter_done_segments = 0
                job.current_chapter_total_segments = 0

            job.status = TranslationJobStatus.COMPLETED
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            return self._store.save_job(job)
        except TranslationProviderError as exc:
            job.status = TranslationJobStatus.FAILED
            job.error = self._loi_an_toan(exc)
            job.finished_at = now_iso()
            job.updated_at = job.finished_at
            return self._store.save_job(job)

    def _dich_mot_chuong(self, project: TranslationProject, noi_dung: str,
                         chuong_idx: int, job: TranslationJob) -> str:
        doan = tach_doan_trong_chuong(noi_dung, DOAN_KY_TU_MOI_LAN_GOI)
        job.current_chapter_total_segments = len(doan)
        self._store.save_job(job)

        tom_tat = "\n".join(
            project.chapter_summaries[max(0, chuong_idx - SO_CHUONG_TOM_TAT_NGU_CANH):
                                      chuong_idx])
        glossary = {e.original: e.translated
                    for e in self._store.list_glossary(project.project_id)}

        vai_tro_ds = _VAI_TRO_THEO_CHE_DO[project.quality_mode]
        ket_qua = []
        for i, phan in enumerate(doan):
            # Ba pass THAT (khong chi may trang thai): dich truoc, roi lan
            # luot chuyen ket qua qua bien tap/QA neu che do yeu cau — moi
            # vai tro nhan dau ra cua vai tro TRUOC lam van ban dau vao.
            dich = phan
            for vai_tro in vai_tro_ds:
                ctx = TranslationContext(
                    vai_tro=vai_tro, genre=project.genre.value,
                    naming_mode=project.naming_mode.value,
                    tom_tat_truoc=tom_tat, glossary=glossary,
                    custom_instruction=project.custom_instruction)
                dich = self._provider.translate_segment(dich, context=ctx)
            ket_qua.append(dich)
            job.current_chapter_done_segments = i + 1
            job.updated_at = now_iso()
            self._store.save_job(job)

        ban_ghep = "\n\n".join(ket_qua)
        # Ap khoa glossary SAU CUNG — rao chan cuoi, xem
        # `translation.ap_dung_khoa_glossary`. O day ap theo tung tu THAY THE
        # TRUC TIEP trong van ban da dich (khac ham chinh, von lam viec tren
        # mot dict de xuat — o day dau ra la VAN BAN, khong phai dict).
        for e in self._store.list_glossary(project.project_id):
            if e.locked and e.original in ban_ghep:
                ban_ghep = ban_ghep.replace(e.original, e.translated)
        return ban_ghep

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
