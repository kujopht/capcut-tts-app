"""MỤC TIÊU ĐƯỢC DUYỆT -> KẾ HOẠCH THỰC THI — V0.9, §3.

KHÔNG DỰNG BỘ PHÂN RÃ THỨ HAI. `planner.RulePlanner` đã biết tách một câu
thành mệnh đề, đoán loại việc, suy phạm vi ghi, dựng `TaskContract` và
`PermissionEnvelope`. Tệp này NÂNG kết quả đó lên thành một kế hoạch v0.9:
thêm DAG tường minh, cách kiểm TẤT ĐỊNH cho mỗi bước, và tiêu chí nghiệm thu
cho CẢ mục tiêu.

HAI THỨ ĐƯỢC THÊM, VÀ CHÚNG LÀ ĐIỂM CHÍNH CỦA §7–§8:

1. **Mỗi bước GHI có ít nhất một phép kiểm tất định.** `suy_cach_kiem` gắn
   `GIT_CO_THAY_DOI` + `GIT_TRONG_PHAM_VI` cho bước ghi, `BIEN_DICH_PYTHON`
   khi phạm vi có `.py`, `TEST_DA_CHAY` cho bước kiểm thử. Thiếu thì
   `kiem_dinh.kiem_dinh_buoc` trả `THIEU_BANG_CHUNG` — nên "quên khai" hỏng
   ồn ào thay vì âm thầm thành DONE.
2. **Tiêu chí nghiệm thu đến từ CÂU NGƯỜI DÙNG trước, kế hoạch sau.** Tiêu
   chí người dùng nói thẳng (`y_dinh.tieu_chi_tu_cau`) luôn có mặt; nếu
   không buộc được vào phép kiểm nào thì nó vẫn ở đó dưới dạng
   `THIEU_BANG_CHUNG`. Một mục tiêu không nói được "thế nào là xong" thì
   không được lặng lẽ thành "xong".
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.ke_hoach import (BuocKeHoach, CachKiem,
                                                       CheDoGhi,
                                                       KeHoachThucThi,
                                                       TieuChiNghiemThu)
from scripts.control_center.execution.y_dinh import YDinhThucThi
from scripts.control_center.model import LockKind, Project
from scripts.control_center.planner import PlannedTask, PlanResult

#: Loại việc của bộ phân rã -> lớp model mong muốn (§18). KHÔNG phải tên
#: model: `reasoning/dinh_tuyen.py` và `Scheduler` ghép năng lực, và ghim tên
#: ở đây sẽ biến bộ định tuyến động thành một bảng tra cứng.
LOP_MODEL: Dict[str, str] = {
    "analysis": "manh",
    "review": "manh",
    "implementation": "thuong",
    "testing": "re",
    "documentation": "re",
    "search": "re",
}


def suy_cach_kiem(pt: PlannedTask) -> Tuple[Tuple[CachKiem, Dict], ...]:
    """Phép kiểm TẤT ĐỊNH cho một bước, suy từ loại việc + phạm vi.

    Bước CHỈ ĐỌC không cần chứng minh đĩa đổi — nó chứng minh bằng chính
    lời khai đã qua `du_bang_chung` (không rỗng). Ép nó phải có
    `GIT_CO_THAY_DOI` sẽ làm mọi việc khảo sát hỏng vĩnh viễn.
    """
    chi_doc = not pt.contract.requirements.repo_write
    scope = [str(x) for x in pt.contract.allowed_scope]
    if chi_doc:
        return ()
    ds: List[Tuple[CachKiem, Dict]] = [
        (CachKiem.GIT_CO_THAY_DOI, {"so_voi": "HEAD"}),
        (CachKiem.GIT_TRONG_PHAM_VI, {"pham_vi": scope}),
    ]
    py = [x for x in scope if x.endswith(".py") or "/" not in x or
          not x.rsplit("/", 1)[-1].count(".")]
    if py:
        ds.append((CachKiem.BIEN_DICH_PYTHON, {"duong": py[:6]}))
    if pt.kind == "testing":
        ds.append((CachKiem.TEST_DA_CHAY, {"it_nhat": 1}))
    return tuple(ds)


def tu_plan_result(y: YDinhThucThi, kq: PlanResult, project: Project, *,
                   nghiem_thu: Sequence[TieuChiNghiemThu] = (),
                   phien_ban: int = 1, ly_do_sua: str = "",
                   thay_doi: Sequence[str] = (),
                   bang_chung: Sequence[str] = ()) -> KeHoachThucThi:
    """`PlanResult` -> `KeHoachThucThi`. Giữ NGUYÊN DAG của bộ phân rã."""
    buoc: List[BuocKeHoach] = []
    for pt in kq.tasks:
        ghi = bool(pt.contract.requirements.repo_write)
        buoc.append(BuocKeHoach(
            buoc_id=pt.task_id, tieu_de=pt.title, muc_tieu=pt.objective,
            phu_thuoc=tuple(pt.dependencies),
            nang_luc=tuple(sorted(_nang_luc(pt))),
            tai_nguyen=tuple(pt.resources),
            che_do_ghi=CheDoGhi.GHI if ghi else CheDoGhi.DOC,
            artifact_mong_doi=tuple(
                x for x in pt.contract.verification.artifact_checks),
            tieu_chi_dat=(),
            cach_kiem=suy_cach_kiem(pt),
            rui_ro=("HIGH" if pt.gated else "MEDIUM" if ghi else "LOW"),
            lop_model=LOP_MODEL.get(pt.kind, "")))
    nt = list(nghiem_thu) or list(suy_nghiem_thu(y, kq, project))
    return KeHoachThucThi(
        execution_id=y.execution_id, phien_ban=int(phien_ban),
        buoc=tuple(buoc), nghiem_thu=tuple(nt), ly_do_sua=ly_do_sua,
        thay_doi=tuple(thay_doi), bang_chung_gay_ra=tuple(bang_chung))


def _nang_luc(pt: PlannedTask) -> List[str]:
    r = pt.contract.requirements
    ra = ["structured_output"]
    if getattr(r, "coding", False):
        ra.append("coding")
    if getattr(r, "long_context", False):
        ra.append("long_context")
    if getattr(r, "repo_write", False):
        ra.append("repo_write")
    elif getattr(r, "repo_read", False):
        ra.append("repo_read")
    return ra


def suy_nghiem_thu(y: YDinhThucThi, kq: PlanResult,
                   project: Project) -> List[TieuChiNghiemThu]:
    """Tiêu chí nghiệm thu cho CẢ mục tiêu — §8.

    Thứ tự nguồn có nghĩa: tiêu chí NGƯỜI DÙNG nói thẳng đứng trước, và
    chúng KHÔNG bị bỏ khi không buộc được vào phép kiểm nào — chúng đi vào
    kế hoạch với `cach_kiem` rỗng, và `kiem_dinh` sẽ báo `THIEU_BANG_CHUNG`.
    Đó là cách §8 khác với "mọi việc con đều DONE".
    """
    ra: List[TieuChiNghiemThu] = []
    pv = sorted({str(x) for t in kq.tasks
                 for x in t.contract.allowed_scope if str(x or "").strip()})

    for mo in y.tieu_chi_dat:
        ra.append(TieuChiNghiemThu(mo_ta=mo,
                                   cach_kiem=_buoc_cho_tieu_chi(mo, pv)))

    co_ghi = any(t.contract.requirements.repo_write for t in kq.tasks)
    if co_ghi:
        ra.append(TieuChiNghiemThu(
            mo_ta="mọi thay đổi nằm trong phạm vi ghi đã khai",
            cach_kiem=((CachKiem.GIT_TRONG_PHAM_VI, {"pham_vi": pv}),)))
        if any(str(x).endswith(".py") or "." not in str(x).rsplit("/", 1)[-1]
               for x in pv):
            ra.append(TieuChiNghiemThu(
                mo_ta="mã Python còn biên dịch được sau thay đổi",
                cach_kiem=((CachKiem.BIEN_DICH_PYTHON,
                            {"duong": [x for x in pv
                                       if "." not in x.rsplit("/", 1)[-1]
                                       or x.endswith(".py")][:6]}),)))
    del project
    return ra


#: Từ khoá trong một tiêu chí -> phép kiểm buộc được vào nó. Tất định và
#: NGHÈO có chủ đích: một bảng đoán rộng sẽ buộc nhầm, và một tiêu chí buộc
#: nhầm còn tệ hơn một tiêu chí không buộc được — cái sau ít nhất báo
#: `THIEU_BANG_CHUNG`, cái trước báo `DAT` cho thứ chưa ai kiểm.
_TU_KHOA: Tuple[Tuple[Tuple[str, ...], CachKiem], ...] = (
    (("test", "bài kiểm", "unittest", "pytest"), CachKiem.TEST_DA_CHAY),
    (("biên dịch", "compile", "import được"), CachKiem.BIEN_DICH_PYTHON),
    (("phạm vi", "scope", "không đụng", "không chạm"),
     CachKiem.GIT_TRONG_PHAM_VI),
)


def _buoc_cho_tieu_chi(mo_ta: str, pham_vi: Sequence[str]
                       ) -> Tuple[Tuple[CachKiem, Dict], ...]:
    van = str(mo_ta or "").lower()
    for tu, cach in _TU_KHOA:
        if any(t in van for t in tu):
            if cach is CachKiem.TEST_DA_CHAY:
                return ((cach, {"it_nhat": 1}),)
            if cach is CachKiem.GIT_TRONG_PHAM_VI:
                return ((cach, {"pham_vi": list(pham_vi)}),)
            return ((cach, {"duong": [x for x in pham_vi
                                      if "." not in x.rsplit("/", 1)[-1]
                                      or x.endswith(".py")][:6]}),)
    return ()


#: Bao nhiêu lần một bước được SỬA bằng cách lập lại kế hoạch. Thấp có chủ
#: đích: quá số này thì giả thuyết "bước sai" đã sai, và cái sai nằm ở đâu
#: khác — dừng cho người xem còn rẻ hơn một vòng nữa.
TRAN_SUA_MOI_BUOC = 2


def buoc_sua_chua(kh: KeHoachThucThi, hong: Dict[str, str]) -> List[BuocKeHoach]:
    """Danh sách bước cho BẢN KẾ HOẠCH KẾ TIẾP — §9 "create repair task".

    Giữ nguyên bước đã đạt; bước hỏng được thay bằng MỘT bước cùng mã nhưng
    mục tiêu mang THÊM bằng chứng hỏng. Đó là điểm khác giữa "lập lại kế
    hoạch" và "chạy lại": chạy lại gửi cùng một lời nhắc cho cùng một model
    và mong một kết quả khác; lập lại kế hoạch gửi thêm thông tin.

    Trả về danh sách RỖNG khi không bước nào sửa được — bộ gọi phải hiểu đó
    là "dừng cho người", không phải "kế hoạch trống".
    """
    ra: List[BuocKeHoach] = []
    doi = False
    for b in kh.buoc:
        ly = str(hong.get(b.buoc_id) or "").strip()
        if not ly:
            ra.append(b)
            continue
        if b.muc_tieu.count(NHAN_SUA) >= TRAN_SUA_MOI_BUOC:
            return []
        doi = True
        ra.append(BuocKeHoach(
            buoc_id=b.buoc_id, tieu_de=b.tieu_de,
            muc_tieu=(b.muc_tieu + f"\n\n{NHAN_SUA} Lần trước bước này KHÔNG "
                                   f"qua kiểm định. Bằng chứng:\n  " + ly[:800]
                      + "\nSửa ĐÚNG nguyên nhân đó. Đừng làm lại từ đầu, và "
                        "đừng nới phạm vi."),
            phu_thuoc=b.phu_thuoc, nang_luc=b.nang_luc,
            tai_nguyen=b.tai_nguyen, che_do_ghi=b.che_do_ghi,
            artifact_mong_doi=b.artifact_mong_doi,
            tieu_chi_dat=b.tieu_chi_dat, cach_kiem=b.cach_kiem,
            rui_ro=b.rui_ro, lop_model=_nang_lop(b.lop_model)))
    return ra if doi else []


#: Mốc đánh dấu một bước ĐÃ là bước sửa. Đếm nó trong mục tiêu là cách biết
#: một bước đã được sửa mấy lần mà không cần thêm một cột trong sổ.
NHAN_SUA = "[SỬA LẦN TRƯỚC]"


def _nang_lop(lop: str) -> str:
    """Bước sửa xin một lớp model MẠNH HƠN một bậc — §18.

    Không nhảy thẳng lên lớp cao nhất: §19 cấm đốt hạn mức cao cấp qua những
    lần thử hỏng liên tiếp, và `chi_phi.xet_ngan_sach` sẽ đòi hạ bậc nếu lớp
    mạnh cũng hỏng hai lần.
    """
    return {"re": "thuong", "thuong": "manh", "": "thuong"}.get(lop, lop)


def cat_theo_pham_vi(kq: PlanResult, pham_vi_noi_ro: str) -> PlanResult:
    """Giữ lại bước khớp `pham_vi_noi_ro` — "ok triển khai phần repo-local đó".

    Cắt ở tầng `PlanResult` chứ không ở `KeHoachThucThi`: bỏ một bước khỏi
    một DAG đã dựng sẽ để lại phụ thuộc treo, và `kiem_dag` sẽ ném. Ở đây ta
    cắt rồi CẮT LUÔN phụ thuộc trỏ tới bước đã bỏ — một bước mất phụ thuộc
    thì chạy sớm hơn, không phải chạy sai.

    Không khớp gì thì trả nguyên: thu hẹp thành RỖNG là biến một câu xin làm
    thành không làm gì, và người dùng sẽ không hiểu vì sao.
    """
    tu = [x for x in str(pham_vi_noi_ro or "").lower().split() if len(x) > 2]
    if not tu:
        return kq
    giu = [t for t in kq.tasks
           if any(x in (t.title + " " + t.objective + " "
                        + " ".join(t.contract.allowed_scope)).lower()
                  for x in tu)]
    if not giu or len(giu) == len(kq.tasks):
        return kq
    con = {t.task_id for t in giu}
    moi: List[PlannedTask] = []
    for t in giu:
        moi.append(PlannedTask(
            task_id=t.task_id, title=t.title, objective=t.objective,
            kind=t.kind, contract=t.contract, envelope=t.envelope,
            dependencies=tuple(d for d in t.dependencies if d in con),
            resources=t.resources, priority=t.priority,
            scope_inferred=t.scope_inferred, note=t.note))
    return PlanResult(intent=kq.intent, tasks=moi,
                      notes=list(kq.notes) + [
                          f"thu hẹp theo yêu cầu người dùng "
                          f"({pham_vi_noi_ro!r}): giữ {len(moi)}/"
                          f"{len(kq.tasks)} bước"],
                      planner=kq.planner)
