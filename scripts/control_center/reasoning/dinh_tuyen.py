"""BỘ ĐỊNH TUYẾN VAI — ghép VAI với (runtime, model) một cách động (V0.8).

YÊU CẦU §6, nguyên ý: *"Do not select models using a static priority list
alone."* Nên ở đây không có danh sách ưu tiên nào. Có một **phép tính**:

    VAI  +  YÊU CẦU CỦA LƯỢT  +  NĂNG LỰC MODEL  +  SỨC KHOẺ NHÀ CUNG CẤP
    +  ĐỘ TRỄ  +  THÔNG TIN HẠN MỨC  +  CHÍNH SÁCH DỰ ÁN  +  CHẾ ĐỘ
    ----------------------------------------------------------------------
    -> (runtime, model), kèm điểm từng chiều và lý do LOẠI của từng ứng viên

DÙNG LẠI `router_v4.Scheduler`, KHÔNG VIẾT BỘ THỨ HAI. Đây là quyết định
kiến trúc quan trọng nhất của tệp này. `Scheduler` đã có ba giai đoạn (lọc
cứng / cho điểm nhiều chiều / giải thích), đã biết sức khoẻ runtime, bể
quota, độ khan hiếm theo hàng đợi thật, thưởng đa dạng họ model, và đã có
rào chặn bậc cao cấp. Viết một bộ chọn thứ hai cho vai suy luận là tạo ra
đúng cái nguồn sự thật thứ hai mà `nang_luc.py` đã ghi lại hậu quả: hai danh
sách song song lệch nhau, và mọi việc xếp vào Codex đều chết.

Việc của tệp này là **dịch một VAI thành một `Requirements`** rồi đọc lại
`Decision` — cộng ba thứ `Scheduler` cố ý không biết:

1. **ĐỘC LẬP HỌ MODEL LÀ RÀO, KHÔNG PHẢI ĐIỂM** (§9). `Scheduler` có
   `independence_bonus` — một tín hiệu cho điểm. Với Reviewer thế là chưa
   đủ: một bản phản biện do CÙNG model viết chỉ là bản tự đọc lại. Nên
   Reviewer đi vòng MỘT: `exclude_families=(họ của Strategist,)` làm rào
   cứng. Không ai thoả -> đi vòng HAI không rào, và bản ghi mang
   `doc_lap=False, suy_giam=True`. **Báo DEGRADED, không giả vờ độc lập.**
2. **RÀO TƯƠNG XỨNG CHI PHÍ** (§8). Một model bậc `CAO_CAP` không được nhận
   một lượt bậc `THUONG` — xem `ngan_sach.kiem_tuong_xung`.
3. **CHÍNH SÁCH DỰ ÁN VỀ MODEL CAO CẤP** (§5), tra từ ký ức
   (`chinh_sach.py`), đặt TRƯỚC `GacAstra`. Hai rào độc lập; cả hai phải mở.

ASTRA KHÔNG BAO GIỜ ĐI VÀO BẰNG ĐƯỜNG TỰ ĐỘNG. `Scheduler._loai_vi` loại
mọi `premium_tier >= 3` trừ khi `requirements.pin_model` gọi đích danh. Tệp
này chỉ ghim khi CẢ BỐN điều kiện cùng đúng: chính sách dự án cho phép,
`GacAstra.xin_phep` cho phép, có LÝ DO LEO THANG tường minh, và lượt đủ khó.
Thiếu một điều -> không ghim, và `ChonVai.astra_ly_do` ghi rõ thiếu cái gì.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.reasoning.chinh_sach import ChinhSachCaoCap
from scripts.control_center.reasoning.ngan_sach import (BacChiPhi, bac_chi_phi,
                                                        kiem_tuong_xung,
                                                        tran_chi_phi)
from scripts.control_center.reasoning.phan_loai import Bac, PhanLoai, TacDong
from scripts.control_center.reasoning.vai import VaiTro, ho_so
from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import Execution, TaskContract
from scripts.router_v4.premium import (BAC_CAO_CAP, CheDo, GacAstra,
                                       LyDoLeoThang, bac_cua)
from scripts.router_v4.scheduler import Decision, Scheduler, Weights


class KhongCoCho(RuntimeError):
    """Không placement nào nhận được vai này. FAIL CLOSED.

    KHÔNG hạ chuẩn để lấp chỗ: một Reviewer chạy trên một model không đủ bậc
    suy luận sẽ trả về một bản phản biện nghe được mà không phát hiện gì, và
    đó tệ hơn việc nói thẳng "không có ai soi được lượt này".
    """


#: Lý do leo thang hợp lệ, suy từ PHÂN LOẠI — không từ một nhãn model tự dán.
#:
#: `LyDoLeoThang` là danh sách ĐÓNG trong `premium.py`. Bản đồ này nói: đặc
#: trưng nào của lượt tương ứng với lý do nào. Không khớp gì -> `None`, và
#: `None` nghĩa là KHÔNG leo thang (mặc định của `GacAstra.xin_phep`).
def ly_do_leo_thang(p: PhanLoai, *, nguoi_yeu_cau: bool = False,
                    model_manh_da_hong: bool = False,
                    agent_bat_dong: bool = False) -> Optional[LyDoLeoThang]:
    """Lý do leo thang lên bậc cao cấp cho lượt này, hoặc `None`.

    Thứ tự có ý nghĩa: một lý do do NGƯỜI nêu thắng mọi suy diễn từ đặc
    trưng, và một lần hỏng thật (`model_manh_da_hong`) thắng một phép đọc
    chữ nghĩa — bằng chứng thắng suy luận, cùng bậc thẩm quyền mà
    `leader.LUAT_SONG` đã dựng cho câu hỏi trạng thái.
    """
    if nguoi_yeu_cau:
        return LyDoLeoThang.NGUOI_YEU_CAU
    if model_manh_da_hong:
        return LyDoLeoThang.MODEL_MANH_DA_HONG
    if agent_bat_dong:
        return LyDoLeoThang.AGENT_BAT_DONG
    if p.bac is not Bac.RAT_KHO:
        # Chi viec RAT KHO moi co the co ly do leo thang suy dien. Day la
        # rao thu hai cho §16 ("Astra not used for trivial prompts"): rao
        # thu nhat la cong tam thuong o `phan_loai.py`.
        return None
    dt = p.dac_trung
    if dt.pham_vi_kien_truc and (p.tac_dong is TacDong.CAO or not p.dao_nguoc_duoc):
        return LyDoLeoThang.PHAN_XU_KIEN_TRUC
    if dt.kho_dao_nguoc and dt.pham_vi_kien_truc:
        return LyDoLeoThang.DI_TRU_PHUC_TAP
    return None


@dataclass
class ChonVai:
    """Kết quả định tuyến cho MỘT vai. Giải thích được đầy đủ (§12)."""

    vai: VaiTro
    runtime_id: str = ""
    model_id: str = ""
    provider: str = ""
    model_family: str = ""
    bac_gia: BacChiPhi = BacChiPhi.RE
    ly_do: str = ""
    #: `None` khi khái niệm không áp dụng (Leader/Strategist).
    doc_lap: Optional[bool] = None
    suy_giam: bool = False
    suy_giam_ly_do: str = ""
    astra: bool = False
    astra_ly_do: str = ""
    du_phong: Tuple[str, ...] = ()
    #: `Decision` của `Scheduler` — giữ nguyên để `explain()` dùng được.
    quyet_dinh: Optional[Decision] = None
    yeu_cau: Optional[Requirements] = None

    @property
    def co_cho(self) -> bool:
        return bool(self.runtime_id and self.model_id)

    def to_dict(self) -> Dict:
        return {"vai": self.vai.value, "runtime_id": self.runtime_id,
                "model_id": self.model_id, "provider": self.provider,
                "model_family": self.model_family,
                "bac_gia": self.bac_gia.value, "ly_do": self.ly_do,
                "doc_lap": self.doc_lap, "suy_giam": self.suy_giam,
                "suy_giam_ly_do": self.suy_giam_ly_do,
                "astra": self.astra, "astra_ly_do": self.astra_ly_do,
                "du_phong": list(self.du_phong),
                "yeu_cau": self.yeu_cau.to_dict() if self.yeu_cau else None,
                "ung_vien_du": (self.quyet_dinh.eligible_count
                                if self.quyet_dinh else 0),
                "ung_vien_xet": (len(self.quyet_dinh.candidates)
                                 if self.quyet_dinh else 0)}

    def explain(self) -> str:
        d = [f"VAI {self.vai.nhan}",
             f"  chọn   : {self.runtime_id}/{self.model_id} "
             f"({self.provider}, họ {self.model_family}, giá {self.bac_gia.value})"
             if self.co_cho else "  chọn   : (KHÔNG CÓ CHỖ)",
             f"  lý do  : {self.ly_do}"]
        if self.doc_lap is not None:
            d.append(f"  độc lập: {'CÓ' if self.doc_lap else 'KHÔNG — DEGRADED'}"
                     + (f" ({self.suy_giam_ly_do})" if self.suy_giam_ly_do else ""))
        if self.astra_ly_do:
            d.append(f"  cao cấp: {'DÙNG' if self.astra else 'KHÔNG'} — "
                     f"{self.astra_ly_do}")
        if self.quyet_dinh is not None:
            d.append("  " + self.quyet_dinh.explain().replace("\n", "\n  "))
        return "\n".join(d)


#: HỆ SỐ TRỌNG SỐ THEO VAI. Nhân vào `Weights` của fabric, không thay nó.
#:
#: VÌ SAO CẦN, và đây là một phép đo trên fabric thật (2026-09-11): với trọng
#: số mặc định, `gemini-3.8-flash-high` thắng `claude-opus-4-6-thinking` cho
#: vai STRATEGIST trên một câu hỏi kiến trúc RAT_KHO — vì `latency` (25s vs
#: 90s) và `expected_cost` (0.3 vs 0.9) cộng lại lớn hơn khoảng cách
#: `benchmark_quality` (0.8 vs 0.9). Với một worker cơ học thì đó là lựa chọn
#: ĐÚNG. Với vai Strategist thì "nhanh và rẻ" không phải tiêu chí.
#:
#: `Weights` vốn được thiết kế để cấu hình được ("đổi chính sách là đổi tệp
#: cấu hình, không phải sửa hàm"), nên dùng lại đúng cơ chế đó cho vai là
#: đường ít nợ nhất — KHÔNG phải viết một công thức cho điểm thứ hai.
HE_SO_VAI: Dict[VaiTro, Dict[str, float]] = {
    VaiTro.LEADER: {
        # Leader chay o MOI tin nhan, ke ca cau chao: do tre va chi phi la
        # tieu chi THAT o day.
        "latency": 1.6, "expected_cost": 1.5, "benchmark_quality": 0.8,
    },
    VaiTro.STRATEGIST: {
        "benchmark_quality": 2.5, "reasoning_fit": 1.5,
        "latency": 0.25, "expected_cost": 0.35,
        # Mot vai ma ca ke hoach dua vao thi khong nen chay tren nang luc
        # MOI CHI LA LOI KHAI — nang phat "chua do" len.
        "evidence_discount": 1.5,
    },
    VaiTro.REVIEWER: {
        "benchmark_quality": 2.2, "reasoning_fit": 1.5,
        "latency": 0.3, "expected_cost": 0.4, "evidence_discount": 1.5,
        # Da dang ho model la CHUYEN CHINH cua vai nay. Rao cung o `chon()`
        # da lo phan bat buoc; he so nay lo phan UU TIEN khi co nhieu ho
        # khac nhau cung thoa.
        "independence_bonus": 2.0,
    },
}

#: HỆ SỐ THEO CHẾ ĐỘ. Đây là chỗ ECO/STRONG/MAX khác nhau bằng SỐ, không
#: bằng một cái nhãn — §4 đòi "real quality modes".
HE_SO_CHE_DO: Dict[CheDo, Dict[str, float]] = {
    CheDo.ECO: {"expected_cost": 2.5, "latency": 2.0,
                "benchmark_quality": 0.6, "quota_health": 1.5},
    CheDo.AUTO: {},
    CheDo.STRONG: {"benchmark_quality": 1.4, "reasoning_fit": 1.2,
                   "expected_cost": 0.6},
    CheDo.MAX: {"benchmark_quality": 1.8, "reasoning_fit": 1.3,
                "expected_cost": 0.3, "latency": 0.5},
}


def trong_so_cho(goc: Weights, vai: VaiTro, che_do: CheDo) -> Weights:
    """`Weights` của fabric × hệ số vai × hệ số chế độ.

    Nhân chứ không thay: một kho chỉnh `weights` trong `.router/v4/fabric.json`
    vẫn giữ được ý định của mình, và quan hệ TƯƠNG ĐỐI giữa các vai không
    đổi. Thay thẳng bằng một bảng hằng số sẽ âm thầm bỏ qua cấu hình của kho.
    """
    d = goc.to_dict()
    for bang in (HE_SO_VAI.get(vai, {}), HE_SO_CHE_DO.get(che_do, {})):
        for k, hs in bang.items():
            if k in d:
                d[k] = round(d[k] * float(hs), 6)
    return Weights.from_dict(d)


class BoDinhTuyenVai:
    """Ghép vai với placement. KHÔNG chạy gì — chỉ quyết định.

    Cùng lý do `Scheduler` tách khỏi `Executor`: mọi bài kiểm định tuyến của
    v0.8 chạy tất định, không cần một tiến trình model nào.
    """

    def __init__(self, fabric, *, scheduler: Optional[Scheduler] = None,
                 gac: Optional[GacAstra] = None,
                 chinh_sach: Optional[ChinhSachCaoCap] = None,
                 weights: Optional[Weights] = None,
                 history=None):
        self.fabric = fabric
        self.scheduler = scheduler or Scheduler(fabric)
        #: Trọng số GỐC của kho — nguồn để nhân hệ số vai/chế độ lên.
        self.weights = weights or getattr(self.scheduler, "weights", Weights())
        self.history = history if history is not None else getattr(
            self.scheduler, "history", None)
        self.gac = gac or GacAstra()
        #: `None` = CHƯA TRA. Coi như HẠN CHẾ — không suy ra "được phép".
        self.chinh_sach = chinh_sach
        self._bo_lich: Dict[Tuple[str, str], Scheduler] = {}

    def _lich_cho(self, vai: VaiTro, che_do: CheDo) -> Scheduler:
        """`Scheduler` riêng cho (vai, chế độ), dùng lại giữa các lượt."""
        khoa = (vai.value, che_do.value)
        bo = self._bo_lich.get(khoa)
        if bo is None:
            bo = Scheduler(self.fabric,
                           weights=trong_so_cho(self.weights, vai, che_do),
                           history=self.history)
            self._bo_lich[khoa] = bo
        return bo

    # -- vai -> Requirements -------------------------------------------------

    def yeu_cau_cho_vai(self, vai: VaiTro, p: PhanLoai, che_do: CheDo, *,
                        loai_tru_ho: Sequence[str] = (),
                        ghim_model: str = "") -> Requirements:
        """Hồ sơ vai + phân loại lượt + chế độ -> `Requirements`.

        BA NĂNG LỰC VẮNG MẶT CÓ CHỦ Ý: `repo_read`, `repo_write`, `shell`.
        Vai suy luận KHÔNG có công cụ — `agy --print` tự chối mọi công cụ cần
        duyệt quyền (đo 2026-09-10), nên một vai đòi `repo_read` sẽ được xếp
        lên một chỗ chạy không đọc nổi tệp rồi chết rỗng. Ngữ cảnh tới từ
        `ngu_canh.py`, do Router đọc hộ.
        """
        h = ho_so(vai)
        rs = h.reasoning_toi_thieu
        # NANG bac suy luan theo do kho cua LUOT — ho so la san, khong phai tran.
        if p.bac is Bac.RAT_KHO or (p.bac is Bac.KHO and p.tac_dong is TacDong.CAO):
            rs = Reasoning.HIGH
        # ECO HA bac mot nac (tru khi lop vai doi HIGH cho viec RAT KHO):
        # day la cho ECO thuc su tiet kiem, thay vi chi la mot cai nhan.
        if che_do is CheDo.ECO and p.bac is not Bac.RAT_KHO:
            rs = Reasoning.MEDIUM

        chat = h.uu_tien_chat_luong
        if che_do is CheDo.ECO:
            chat = Priority.BALANCED if chat is Priority.HIGH else chat
        elif che_do in (CheDo.STRONG, CheDo.MAX):
            chat = Priority.HIGH

        return Requirements(
            structured_output=True,
            # Ngu canh dai chi doi khi goi ngu canh cua vai that su lon. Doi
            # `long_context` cho Leader se loai mot model nhanh khoi mot luot
            # chao hoi — dung kieu "doi thua" ma `capabilities.py` canh bao.
            long_context=(h.tran_token_ngu_canh >= 3000),
            reasoning_level=rs,
            latency_priority=h.uu_tien_do_tre,
            quality_priority=chat,
            pin_model=ghim_model or None,
            exclude_families=tuple(loai_tru_ho))

    def _hop_dong(self, vai: VaiTro, p: PhanLoai, yc: Requirements,
                  *, task_id: str) -> TaskContract:
        """Hợp đồng TỔNG HỢP cho một lượt suy luận.

        KHÔNG phải một việc Router: không `allowed_scope`, không
        `worktree_required`, `destructive_actions_allowed=False`. Nó tồn tại
        vì `Scheduler.decide()` nhận một `TaskContract` — dựng một đường vào
        thứ hai cho bộ lập lịch sẽ là đúng cái nguồn sự thật thứ hai mà tệp
        này mở đầu bằng việc từ chối.
        """
        h = ho_so(vai)
        return TaskContract(
            task_id=task_id,
            objective=f"vai suy luận {vai.value}: {p.bac.value}/{p.tac_dong.value}",
            type=f"reasoning_{vai.value}",
            requirements=yc,
            execution=Execution(expected_duration=min(h.han_giay * 0.5, 120.0),
                                max_wall_time=h.han_giay,
                                destructive_actions_allowed=False,
                                worktree_required=False),
            impact={TacDong.THAP: 0.2, TacDong.TRUNG: 0.5,
                    TacDong.CAO: 0.9}[p.tac_dong],
            uncertainty=round(1.0 - p.do_tin, 3))

    # -- Astra ---------------------------------------------------------------

    def _xet_astra(self, vai: VaiTro, p: PhanLoai, che_do: CheDo, *,
                   task_id: str, nguoi_yeu_cau: bool,
                   model_manh_da_hong: bool,
                   chinh_sach: Optional[ChinhSachCaoCap] = None
                   ) -> Tuple[str, str]:
        """`(model_id để ghim, lý do)`. Model rỗng = KHÔNG dùng bậc cao cấp.

        BỐN điều kiện, kiểm theo thứ tự từ rào CHÍNH SÁCH ra rào CƠ CHẾ.
        Thiếu một điều là không ghim, và lý do nói rõ thiếu cái gì — §5 đòi
        "Record why escalation occurred", và một lần KHÔNG leo thang cũng
        đáng được giải thích y như một lần có.
        """
        # CHINH SACH THEO TUNG LUOT thang chinh sach cua ca bo dinh tuyen.
        #
        # Mot `BoDinhTuyenVai` duoc DUNG CHUNG cho moi du an trong tien trinh
        # (xem `engine.hoi_dong`), nen chinh sach KHONG duoc gan vao `self`:
        # lam the thi quyet dinh cua du an A se ap cho luot cua du an B, va
        # `chinh_sach.py` ton tai chinh de chan dieu do ("fail closed, khong
        # suy ra tu du an khac"). Truyen theo luot la cach duy nhat khong co
        # trang thai chia se.
        cs = chinh_sach if chinh_sach is not None else self.chinh_sach
        ten_cao_cap = [m.model_id for m in
                       (getattr(self.fabric, "models", {}) or {}).values()
                       if bac_cua(m.model_id, getattr(m, "premium_tier", 0))
                       >= BAC_CAO_CAP]
        if not ten_cao_cap:
            return "", "fabric không khai model bậc cao cấp nào"

        if cs is None:
            return "", ("chưa tra chính sách dự án về model cao cấp — FAIL "
                        "CLOSED, không dùng")
        if cs.han_che:
            # HAN CHE khong phai CAM: no nghia la "chi viec dac biet kho".
            # Nen o day van di tiep, nhung chi khi lop LY DO cho phep.
            pass

        ly = ly_do_leo_thang(p, nguoi_yeu_cau=nguoi_yeu_cau,
                             model_manh_da_hong=model_manh_da_hong)
        if ly is None:
            return "", (f"không có lý do leo thang tường minh; {cs.ly_do()}"
                        if cs.han_che else
                        "không có lý do leo thang tường minh")
        if cs.han_che and p.bac is not Bac.RAT_KHO and not nguoi_yeu_cau:
            return "", (f"chính sách dự án HẠN CHẾ bậc cao cấp cho việc đặc "
                        f"biệt khó, lượt này bậc {p.bac.value} — {cs.ly_do()}")

        ok, vi_sao = self.gac.xin_phep(
            task_id=task_id, che_do=che_do, ly_do=ly,
            loai_viec=f"reasoning_{vai.value}")
        if not ok:
            return "", f"GacAstra từ chối: {vi_sao}"
        # Chon model cao cap RE NHAT trong so cac model bac 3 — khong co ly
        # do gi chon cai dat hon khi ca hai deu la bac 3.
        ten_cao_cap.sort(key=lambda mid: float(
            getattr(self.fabric.models[mid], "cost_profile", 1.0)))
        chon = ten_cao_cap[0]
        nguon = cs.ma or cs.nguon
        return chon, (f"leo thang {ly.value}; {vi_sao}; chính sách dự án "
                      f"{nguon}")

    # -- chon ----------------------------------------------------------------

    def chon(self, vai: VaiTro, p: PhanLoai, che_do: CheDo, *,
             task_id: str = "", ho_tac_gia: str = "",
             doi_doc_lap: bool = False, nguoi_yeu_cau_cao_cap: bool = False,
             model_manh_da_hong: bool = False,
             loai_tru_placement: Sequence[str] = (),
             cho_ghim_cao_cap: bool = True,
             chinh_sach: Optional[ChinhSachCaoCap] = None,
             now: Optional[float] = None) -> ChonVai:
        """Chọn (runtime, model) cho `vai`. Ném `KhongCoCho` khi không ai thoả.

        `doi_doc_lap` + `ho_tac_gia`: dành cho Reviewer. Vòng MỘT loại trừ họ
        của Strategist (rào cứng); nếu không ai thoả thì vòng HAI bỏ rào và
        đánh dấu `suy_giam` — xem docstring module, mục §9.
        """
        tid = task_id or f"reason-{vai.value}-{int((now or time.time()) * 1000)}"
        cv = ChonVai(vai=vai)

        if cho_ghim_cao_cap:
            ghim, ly_astra = self._xet_astra(
                vai, p, che_do, task_id=tid,
                nguoi_yeu_cau=nguoi_yeu_cau_cao_cap,
                model_manh_da_hong=model_manh_da_hong,
                chinh_sach=chinh_sach)
        else:
            ghim, ly_astra = "", ""
        cv.astra_ly_do = ly_astra

        vong: List[Tuple[Tuple[str, ...], bool, str]] = []
        if doi_doc_lap and ho_tac_gia:
            vong.append(((ho_tac_gia,), True, ""))
            vong.append(((), False,
                         f"không có placement nào NGOÀI họ {ho_tac_gia!r} thoả "
                         f"yêu cầu của vai — review chạy CÙNG họ, tức là KHÔNG "
                         f"độc lập"))
        else:
            vong.append(((), None if not doi_doc_lap else True, ""))

        cuoi: Optional[Decision] = None
        for loai_tru_ho, doc_lap, ly_suy_giam in vong:
            yc = self.yeu_cau_cho_vai(vai, p, che_do, loai_tru_ho=loai_tru_ho,
                                      ghim_model=ghim)
            hd = self._hop_dong(vai, p, yc, task_id=tid)
            qd = self._lich_cho(vai, che_do).decide(
                hd, exclude=tuple(loai_tru_placement),
                author_family=ho_tac_gia if doi_doc_lap else "", now=now)
            cuoi = qd
            chon = self._loc_tuong_xung(qd, p, che_do)
            if chon is None:
                continue
            m = self.fabric.models[chon.model_id]
            cv.runtime_id = chon.runtime_id
            cv.model_id = chon.model_id
            cv.provider = m.provider
            cv.model_family = m.model_family
            cv.bac_gia = bac_chi_phi(m.cost_profile,
                                     getattr(m, "premium_tier", 0))
            cv.ly_do = qd.reason
            cv.du_phong = tuple(qd.fallbacks)
            cv.quyet_dinh = qd
            cv.yeu_cau = yc
            cv.doc_lap = doc_lap
            if ly_suy_giam:
                cv.suy_giam = True
                cv.suy_giam_ly_do = ly_suy_giam
            cv.astra = bool(ghim) and chon.model_id == ghim
            if ghim and not cv.astra:
                cv.astra_ly_do = (f"đã ghim {ghim} nhưng bộ lập lịch chọn "
                                  f"{chon.model_id} — ghim không thoả được")
            return cv

        # Khong ai thoa o moi vong. Ghim Astra co the la nguyen nhan -> thu
        # lai MOT lan khong ghim, vi mot luot khong co Reviewer con te hon
        # mot Reviewer khong phai bac cao cap.
        #
        # `cho_ghim_cao_cap=False` PHAI tuong minh. Ban dau cho nay chi tat
        # hai co `nguoi_yeu_cau`/`model_manh_da_hong` roi de quy — nhung
        # `ly_do_leo_thang` con SUY DIEN duoc mot ly do tu chinh dac trung
        # cua luot (`PHAN_XU_KIEN_TRUC` cho viec RAT_KHO), nen `ghim` duoc
        # dat lai o lan de quy va vong lap khong bao gio dung:
        # `RecursionError` sau ~990 tang, do that tren fabric that.
        if ghim:
            cv2 = self.chon(vai, p, che_do, task_id=tid, ho_tac_gia=ho_tac_gia,
                            doi_doc_lap=doi_doc_lap,
                            nguoi_yeu_cau_cao_cap=False,
                            model_manh_da_hong=False,
                            loai_tru_placement=loai_tru_placement,
                            cho_ghim_cao_cap=False, chinh_sach=chinh_sach,
                            now=now)
            cv2.astra_ly_do = (f"{ly_astra} — nhưng không placement nào chạy "
                               f"được {ghim}; đã hạ về bậc thường")
            return cv2
        raise KhongCoCho(
            f"không placement nào nhận được vai {vai.value} "
            f"(bậc {p.bac.value}, chế độ {che_do.value}, trần chi phí "
            f"{tran_chi_phi(p.bac, che_do).value}). "
            + (cuoi.reason if cuoi else "không dựng được quyết định"))

    def _loc_tuong_xung(self, qd: Decision, p: PhanLoai, che_do: CheDo):
        """Placement thắng ĐẦU TIÊN còn thoả rào tương xứng chi phí.

        `Scheduler` đã xếp hạng; ở đây chỉ đi xuống danh sách và bỏ những
        ứng viên quá đắt cho bậc của lượt. Không cho điểm lại — cho điểm hai
        lần bằng hai công thức là cách hai tầng bắt đầu mâu thuẫn.
        """
        hop = [c for c in qd.candidates if c.eligible and c.score is not None]
        hop.sort(key=lambda x: (-x.score.total, x.placement.key))
        for c in hop:
            m = self.fabric.models.get(c.placement.model_id)
            if m is None:
                continue
            bg = bac_chi_phi(m.cost_profile, getattr(m, "premium_tier", 0))
            # Mot model duoc GHIM tuong minh (Astra da qua bon rao) khong bi
            # rao tuong xung chan lai: rao do ton tai de chan viec AM THAM
            # tieu nhieu, va mot lan ghim thi khong am tham.
            ghim = (qd.pinned and m.model_id ==
                    (getattr(qd.selected, "model_id", "") or ""))
            ok, _ = kiem_tuong_xung(bac_kho=p.bac, bac_gia=bg, che_do=che_do,
                                    model_id=m.model_id)
            if ok or ghim:
                return c.placement
        return None

    # -- bao cao -------------------------------------------------------------

    def nang_luc_bay(self, *, now: Optional[float] = None) -> List[Dict]:
        """Năng lực CÓ CẤU TRÚC của từng (runtime, model) đang bay — §6/§7.

        Đây là thứ giao diện dùng để trả lời "Router có những gì". Mọi số
        đến từ fabric và từ trạng thái runtime THẬT; không trường nào bịa,
        và bể quota không đọc được số dư thì trường đó là `None`.
        """
        ra: List[Dict] = []
        for pl in getattr(self.fabric, "placements", lambda: ())():
            r = self.fabric.runtimes.get(pl.runtime_id)
            m = self.fabric.models.get(pl.model_id)
            if r is None or m is None:
                continue
            pool = None
            try:
                pool = self.fabric.pool_cua_placement(pl)
            except Exception:                               # noqa: BLE001
                pool = None
            tt = r.trang_thai_hien_tai(now=now)
            ra.append({
                "placement": pl.key,
                "runtime_id": r.runtime_id, "provider": m.provider,
                "model_id": m.model_id, "model_family": m.model_family,
                "trang_thai": tt.value,
                "nhan_viec_duoc": bool(tt.nhan_viec_duoc),
                "dispatchable": bool(r.dispatchable),
                "provisioned": bool(r.provisioned),
                "con_cho": bool(r.con_cho),
                "concurrency": r.concurrency, "in_flight": r.in_flight,
                # NANG LUC CO CAU TRUC (§6).
                "nang_luc": sorted(m.effective_capabilities),
                "reasoning": m.reasoning.value,
                "benchmark_profile": m.benchmark_profile,
                "latency_profile": m.latency_profile,
                "reliability": m.reliability,
                "bac_gia": bac_chi_phi(m.cost_profile,
                                       getattr(m, "premium_tier", 0)).value,
                "premium_tier": int(getattr(m, "premium_tier", 0) or 0),
                "do_tin_nang_luc": round(m.do_tin_nang_luc, 3),
                # HAN MUC: `None` khi khong doc duoc — KHONG phai 0.
                "quota_pool": (pool.pool_id if pool else ""),
                "quota_con_lai": (round(pool.remaining_estimate * 100, 1)
                                  if pool is not None and pool.source.value
                                  in ("probed", "declared") else None),
                "quota_nguon": (pool.source.value if pool else "unknown"),
                # HOP VAI: vai nao model nay dung duoc, theo BAC suy luan.
                "hop_vai": sorted(
                    v.value for v in (VaiTro.LEADER, VaiTro.STRATEGIST,
                                      VaiTro.REVIEWER)
                    if m.reasoning >= ho_so(v).reasoning_toi_thieu
                    and "structured_output" in m.effective_capabilities),
            })
        ra.sort(key=lambda x: x["placement"])
        return ra
