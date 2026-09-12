"""Bộ máy Control Center — nơi mọi thứ nối vào Router V4.

ĐÂY LÀ LÁT CẮT DỌC của V0.1:

    ô chat -> phân rã việc -> quyết định định tuyến -> tạo/dùng lại worktree
    -> dựng phiên agent -> chạy -> phát sự kiện -> ghi sổ -> Pause/Stop
    -> sống sót qua khởi động lại

RANH GIỚI VỚI ROUTER V4, và vì sao nó nằm ở đúng chỗ này:

Control Center KHÔNG lập lịch lại, KHÔNG chấm điểm lại, KHÔNG dựng adapter,
KHÔNG kiểm định lại kết quả. Bốn thứ đó là Router V4 và chúng đã được đập
thật (xem `docs/reports/ROUTER_V4_REAL_PROOF.md`). Cái Control Center thêm
vào là thứ V4 cố ý không có: **trạng thái sống lâu hơn một mission**.

Cụ thể, `RouterV4.run_task()` tự chọn placement cho từng việc — đúng cho một
mission chạy một lần. Nhưng nó không thể DÙNG LẠI một phiên, vì với nó phiên
không tồn tại. Nên ở đây ta gọi thẳng `Executor.run(contract, placement)` với
placement do `SessionManager` đã chốt, và mượn lease khe runtime của V4 để
hai tầng không giao trùng một khe. Mọi cơ chế bên trong `Executor` — adapter,
worktree, cổng kiểm định, bằng chứng thắng lời khai — chạy y nguyên.

THỨ TỰ GIÀNH TÀI NGUYÊN LÀ CỐ ĐỊNH, và đảo nó là tạo ra deadlock:

    1. khoá tài nguyên (LockManager)   — rẻ nhất, nhả nhanh nhất
    2. quyết định phiên (SessionManager)
    3. lease khe runtime (Router V4)
    4. nhận việc (claim, nguyên tử)

Nhả thì theo thứ tự NGƯỢC LẠI, luôn luôn, trong `finally`.
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v3.worktree import WorktreeError, WorktreeHandle
from scripts.router_v4 import fabric_config as FC
from scripts.router_v4.contract import ContractError, TaskContract
from scripts.router_v4.envelope import RawLogStore
from scripts.router_v4.executor import Executor, ExecutionResult
from scripts.router_v4.history import BenchmarkStore
from scripts.router_v4.leases import LeaseStore, owner_id
from scripts.router_v4.runtime import Fabric, Placement
from scripts.router_v4.modes import hop_dong_review
from scripts.router_v4.scheduler import Demand, Scheduler

from scripts.control_center import leader
from scripts.control_center.bootstrap import la_kho_git
from scripts.control_center.execution import dieu_phoi as DP
from scripts.control_center.execution import ghi_nho as EGN
from scripts.control_center.execution import ke_hoach as EKH
from scripts.control_center.execution import kiem_dinh as EKD
from scripts.control_center.execution import lap_ke_hoach as ELK
from scripts.control_center.execution import ket_qua as EKQ
from scripts.control_center.execution import tiep_noi as ETN
from scripts.control_center.execution import y_dinh as EYD
from scripts.control_center.execution.so import SoThucThi
from scripts.control_center.execution.trang_thai import TrangThaiThucThi
from scripts.control_center.locks import (LockManager, chuoi_tai_nguyen,
                                          doc_chuoi_tai_nguyen)
from scripts.control_center.model import (LockKind, PermissionClass, Project,
                                          Session, SessionAction, SessionState,
                                          Task, TaskState, TransitionError,
                                          map_envelope_status)
from scripts.control_center.permissions import PermissionEnvelope, envelope_for
from scripts.control_center.planner import PlannedTask, PlanResult, RulePlanner
from scripts.control_center.sessions import SessionManager, dao_pid
from scripts.control_center.store import ControlStore
from scripts.control_center.usage import UsageReporter
from scripts.control_center.worktrees import WorktreeCoordinator

#: Bao nhieu luot cho MOI viec truoc khi bo cuoc. Trung `MAX_ATTEMPTS` cua
#: `router_v4/orchestrator.py` co chu dich — hai tang dem cung mot cach.
MAX_ATTEMPTS = 3
#: Tran song song khi `max_parallel=0` (tu dong) ma fabric chua dung, va san
#: duoi cua gia tri tu dong. 3 la con so V0.1 da chon.
TRAN_SONG_SONG_MAC_DINH = 3
#: San tren cua gia tri tu dong: moi khe la mot tien trinh agent that.
TRAN_SONG_SONG_TOI_DA = 12

#: Nhip vong lap dieu phoi. Du nhanh de bang dieu khien thay thay doi, du
#: cham de khong quay CPU khi khong co viec.
TICK_SECONDS = 1.0

#: Viec ket thuc bao lau thi con duoc phep "thuat lai" o o chat.
#:
#: Co han vi mot ly do cu the: mo lai ung dung sau mot tuan KHONG duoc do
#: nguoc ca tram ket qua cu vao hoi thoai. Rong rai du de che truong hop
#: that (tat may giua chung, bam Dung, mot nhip dieu phoi truot).
TRAN_QUET_KET_QUA = 1800.0

#: Mot viec `FAILED` phai LANG bao lau thi luoi an toan moi thuat lai.
#:
#: Duong dieu phoi ghi `FAILED` xuong so TRUOC khi quyet dinh thu lai; roi
#: vao khe do ma bao ngay thi nguoi dung doc "hong" cho mot viec sap chay
#: lai. Duong dieu phoi van tu bao ngay lap tuc sau khi da quyet dinh, nen
#: cho o day khong lam cham truong hop binh thuong.
CHO_LANG_KET_QUA = 8.0

#: Dau hieu NHAN DANG truong hop "khai rong ma dia co doi" cua cong `diff`.
#:
#: Lay tu `router_v3/pool/validation.cong_diff`. Chuoi nay chi duoc sinh o
#: DUNG mot nhanh, nhanh doi hoi `status=="ok" and not khai and that` — nen
#: no la dau hieu chinh xac, khong phai suy doan. Khoa lai bang bai kiem.
DAU_HIEU_KHAI_THIEU = "worker không khai sửa gì nhưng đĩa đổi"


def _loai_viec_cua(b) -> str:
    """Loại việc của một bước — dùng lại từ vựng của `planner.RulePlanner`.

    Một từ vựng thứ hai ở đây sẽ làm `_hop_dong` chọn sai `Requirements`, và
    hậu quả là một bước viết mã bị xếp lên một model không có `coding`.

    `che_do_ghi` THẮNG MỌI TỪ KHOÁ, và nó phải được hỏi TRƯỚC. Bản đầu để
    phép kiểm `not b.ghi` ở CUỐI, nên một bước CHỈ ĐỌC có chữ "tài liệu"
    trong mục tiêu ("đọc tài liệu bàn giao") bị xếp `documentation` — một
    loại CÓ GHI. Hậu quả đo được trên Fanfic thật (2026-09-11): agent đọc
    đúng, tóm tắt đúng, rồi cổng `diff` của Router V4 đánh hỏng với
    "báo ok cho một việc CÓ GHI nhưng không tệp nào đổi" — ba lần liên tiếp,
    cho một việc mà đề bài nói rõ là chỉ đọc.

    Kế hoạch KHAI `CheDoGhi.DOC` là một tuyên bố, không phải một gợi ý.
    """
    if not b.ghi:
        return "review" if any(
            x in (b.tieu_de + " " + b.muc_tieu).lower()
            for x in ("review", "phản biện", "soi")) else "analysis"
    van = (b.tieu_de + " " + b.muc_tieu).lower()
    if any(x in van for x in ("test", "bài kiểm", "kiểm thử")):
        return "testing"
    if any(x in van for x in ("tài liệu", "doc", "readme")):
        return "documentation"
    return "implementation"


@dataclass
class ProjectContext:
    """Mọi thứ gắn với MỘT dự án. Dựng lười — mở dự án mới không dò gì cả."""

    project: Project
    fabric: Fabric
    scheduler: Scheduler
    executor: Executor
    sessions: SessionManager
    worktrees: WorktreeCoordinator
    leases: LeaseStore
    planner: RulePlanner
    logs: RawLogStore


class ControlCenter:
    """Mặt tiền của Control Center. Dựng rẻ; không khởi động agent nào."""

    def __init__(self, *, root: Optional[Path] = None,
                 store: Optional[ControlStore] = None,
                 fabric: Optional[Fabric] = None,
                 executor_factory=None,
                 probe: bool = False,
                 max_parallel: int = 3,
                 leader_bat: bool = False,
                 kho_bi_mat=None,
                 bo_goi_vai=None):
        # GOC DU LIEU CHINH TAC khi nguoi goi khong noi ro. KHONG `Path.cwd()`:
        # `cwd` doi theo cho mo terminal / cho bam doi, nen mac dinh cu sinh
        # MOT SO RIENG cho moi thu muc — dung khuyet tat lien tuc 2026-09-10
        # (cung `project_id` ma nhieu quyen so). Xem `duong_du_lieu.py`.
        from scripts.control_center.duong_du_lieu import goc_du_lieu
        self.root = Path(root) if root else goc_du_lieu()
        self.store = store if store is not None else ControlStore(root=self.root)
        #: `DichVuProvider` (V0.6.1) — dung muon; `kho_bi_mat` chi de bo kiem
        #: cam `KhoBiMatBoNho` vao. Mac dinh la kho an toan cua may (hoac
        #: "khong san" — KHONG BAO GIO la tep thuong).
        self._providers = None
        self._kho_bi_mat = kho_bi_mat
        #: Tran viec song song. `0` = TU DONG theo be tai khoan (tong khe cua
        #: runtime da cap phat + nhan dispatch, ke tu TRAN_SONG_SONG_MAC_DINH
        #: den TRAN_SONG_SONG_TOI_DA). Nghiem thu tay V0.6.1: "goi 8 agent"
        #: bi tran 3 (mac dinh cu) chan con 3 du be co 10 khe — tran cua
        #: Control Center va so agent nguoi dung xin la HAI khai niem, va
        #: tran phai theo be that chu khong theo mot hang so viet tu V0.1.
        self._max_parallel_cau_hinh = max(0, int(max_parallel))
        #: Khoa cho buoc TONG HOP viec cha (hai con xong cung luc).
        self._khoa_toa = threading.Lock()
        #: Khoa cho "ket qua ve chat DUNG MOT LAN": phep kiem `da_bao_ket_qua`
        #: + ghi tin + ghi dau phai NGUYEN TU giua cac luong. Luong `_chay`
        #: (hoac `_tong_hop_toa`) va luoi an toan trong `tick()` cung thay mot
        #: viec vua DONE — khong khoa thi ca hai deu qua phep kiem va nguoi
        #: dung doc HAI lan cung mot ket qua (do that o bai kiem toa).
        self._khoa_bao = threading.Lock()
        self.owner = owner_id()
        # `probe=False` mac dinh: dung Control Center KHONG duoc goi mang.
        # Do suc khoe that la mot thao tac cham va ton mot luot moi provider;
        # no thuoc ve nut "lam moi", khong thuoc ve ham dung.
        self._fabric = fabric
        self._probe = probe
        #: Moc lan do suc khoe gan nhat. `0.0` = CHUA BAO GIO do.
        #:
        #: Khong the de mac dinh `probe=False` co nghia la "khong bao gio do":
        #: `dung_fabric` dat moi runtime o `OFFLINE`/`last_seen=0`, va
        #: `Scheduler.decide` loai sach ca 42 ung vien voi ly do "runtime
        #: KHONG nhan dispatch". Duong mac dinh cua ban phat hanh
        #: (`router-cc`, khong co `--probe`) vi vay KHONG BAO GIO giao duoc
        #: viec nao — moi viec nam `WAITING` vinh vien. Da do that: mot luot
        #: chung minh READ+WRITE cho 901s, 0 luot, khong placement nao.
        #:
        #: Nen do LUOI: khong do luc dung (giu dung y "khong goi mang luc
        #: khoi dong"), do lan dau khi THAT SU can mot placement.
        self._lan_do_cuoi = 0.0
        #: Fabric do BEN GOI dua vao (bo kiem, hoac mot phien dac biet). Ta
        #: KHONG duoc do suc khoe cai do: no la fabric dung tay, va
        #: `do_suc_khoe` goi that ra `agy`/`codex`. Mot bo kiem offline se
        #: bien thanh bo kiem goi mang.
        self._fabric_ngoai = fabric is not None
        self._executor_factory = executor_factory
        self._ctx: Dict[str, ProjectContext] = {}
        self._khoa = threading.Lock()
        self._dang_chay: Dict[str, threading.Thread] = {}
        self._dung_lai = threading.Event()
        self._luong_vong: Optional[threading.Thread] = None
        self._usage: Optional[UsageReporter] = None
        self._dinh_kem = None
        #: Leader CO BAT khong. MAC DINH TAT, va day la mot lua chon can
        #: giai thich: `chat()` co Leader se SINH MOT TIEN TRINH AGENT. Mot
        #: mac dinh "bat" bien moi bo kiem goi `chat()` thanh mot bo kiem
        #: goi ra nha cung cap — cham, gion, va ton quota that.
        #:
        #: Nen: cac diem vao THAT (desktop/web/TUI) bat tuong minh; moi thu
        #: khac giu hanh vi cu, tat dinh. Co bai kiem doi ba diem vao do
        #: phai bat, de "tat dinh cho bo kiem" khong lang le thanh "tat cho
        #: ca san pham".
        self.leader_bat = bool(leader_bat)
        #: Phien Leader AM theo du an. Giu ngoai `_ctx` vi no song lau hon
        #: mot lan `ctx` bi lam moi, va vi dong no phai la mot hanh vi
        #: tuong minh (`shutdown`), khong phai mot tac dung phu.
        self._leader_phien: Dict[str, object] = {}
        self._khoa_leader = threading.Lock()
        #: Viec DA bao ket qua ve o chat. Chan bao HAI LAN cung mot ket qua
        #: — vong lap dieu phoi co the thay lai mot viec da ket thuc.
        self._da_bao_ket_qua: set = set()
        #: `DichVuQuanSat`, dung muon (V0.5). Xem property `quan_sat`.
        self._quan_sat = None
        #: `DichVuKyUc` (V0.6). KHONG dung muon nhu `quan_sat`: nguoi ghi
        #: cua no phai duoc cam vao `store` TRUOC su kien dau tien, khong
        #: thi lich su bo lo dung nhung gi xay ra luc khoi dong. Hong thi
        #: `None` va Router chay tiep — ky uc khong duoc giet Router.
        self._ky_uc = None
        self._ky_uc_loi = ""
        self._bat_ky_uc()
        #: HOI DONG SUY LUAN (V0.8). Dung muon: dung no keo theo
        #: `BoDinhTuyenVai` + mot `Scheduler` rieng cho moi (vai, che do), va
        #: mot phien chat tam thuong khong duoc tra gia cho thu no khong dung.
        self._hoi_dong = None
        #: `BoGoi` — bom duoc vao de bo kiem chay tat dinh, khong sinh tien
        #: trinh nao. `None` = dung `BoGoiThat` khi that su can.
        self._bo_goi_vai = bo_goi_vai
        #: Chinh sach model cao cap theo du an, DOC TU KY UC, co bo dem.
        #: `{pid: (ChinhSachCaoCap, moc_doc)}`.
        self._chinh_sach_cache: Dict[str, tuple] = {}
        #: Nguon goc dinh tuyen cua LUOT GAN NHAT, theo du an — thu §12 hien
        #: len giao dien. Chi giu luot cuoi: lich su dai da co o `cc_events`.
        self._nguon_goc_suy_luan: Dict[str, Dict] = {}
        #: V0.9 — VONG KIN THUC THI. So dung chung `control.db`; bo dieu
        #: phoi dung muon vi no can `MoiGioiKiem` gan vao DUNG kho cua du
        #: an, ma du an chua chac da co luc khoi tao.
        self.so_thuc_thi = SoThucThi(self.store)
        self._dieu_phoi: Dict[str, DP.BoDieuPhoi] = {}
        self._khoa_thuc_thi = threading.Lock()
        #: Lan thuc thi DA bao ket luan ve o chat — chan bao hai lan, cung
        #: khuon `_da_bao_ket_qua`.
        self._da_bao_thuc_thi: set = set()
        #: BUOC DANG LAM cua `chat()`, theo du an: `{pid: (nhan, tu_luc)}`.
        #:
        #: VI SAO CAN. `chat()` chay DONG BO trong mot luong; mot lan mo
        #: Leader lanh do duoc 67.87s. Trong suot khoang do frontend chi
        #: thay mot nut bi vo hieu hoa — khong phan biet duoc "dang nghi"
        #: voi "treo", va nguoi dung bam lai hoac dong app. Nen BUOC duoc
        #: ghi o day va di ra qua `snapshot()`, tuc la qua WebSocket: moi
        #: tab dang mo deu thay, khong chi tab vua gui.
        self._buoc: Dict[str, tuple] = {}

    # -- 0. Fabric dung chung ------------------------------------------------

    @property
    def max_parallel(self) -> int:
        """Trần việc song song ĐANG HIỆU LỰC.

        Cấu hình > 0 thì đúng số đó. `0` (tự động): tổng khe của các runtime
        đã cấp phát và nhận dispatch trong fabric — kẹp giữa
        `TRAN_SONG_SONG_MAC_DINH` và `TRAN_SONG_SONG_TOI_DA`. Fabric chưa dựng
        (chưa việc nào cần) thì tạm là mặc định; KHÔNG dựng fabric chỉ để
        đọc con số này.
        """
        if self._max_parallel_cau_hinh > 0:
            return self._max_parallel_cau_hinh
        f = self._fabric
        if f is None:
            return TRAN_SONG_SONG_MAC_DINH
        n = sum(int(r.concurrency) for r in f.runtimes.values()
                if r.provisioned and r.dispatchable)
        return max(TRAN_SONG_SONG_MAC_DINH, min(n, TRAN_SONG_SONG_TOI_DA))

    @property
    def fabric(self) -> Fabric:
        """Fabric DÙNG CHUNG cho mọi dự án.

        Cố ý dùng chung: `WorkerRuntime` mang `running_tasks` và hạn mức
        đồng thời của một TÀI KHOẢN THẬT. Hai dự án dựng hai fabric riêng sẽ
        mỗi bên tưởng AG01 đang rảnh, và cùng đẩy việc vào một tài khoản chỉ
        có 3 khe. Tài khoản là tài nguyên toàn cục, nên sổ của nó cũng phải
        toàn cục.
        """
        if self._fabric is None:
            f, _w, _e = FC.nap(root=self.root, probe=self._probe)
            self._fabric = f
            if self._probe:
                # Da do ngay luc nap: dung moc lai de nhip dau tien khong
                # do lan thu hai (moi lan do ton mot luot moi provider).
                self._lan_do_cuoi = time.time()
            # V0.6.1: provider ngoai vao so dinh tuyen o trang thai KHONG
            # nhan dispatch — `explain` thay, khong duong tu dong nao giao.
            try:
                self.providers.dang_ky_vao_fabric(f)
            except Exception:                               # noqa: BLE001
                pass
        return self._fabric

    @property
    def providers(self):
        """`DichVuProvider` — provider ngoài + kho bí mật (V0.6.1)."""
        if self._providers is None:
            from scripts.control_center.providers import DichVuProvider
            self._providers = DichVuProvider(self.store, self.root,
                                             kho_bi_mat=self._kho_bi_mat,
                                             sau_khi_doi=self._dong_bo_provider_fabric)
        return self._providers

    def _dong_bo_provider_fabric(self) -> None:
        """Sổ provider vừa đổi → đồng bộ vào fabric ĐANG SỐNG (không dựng mới,
        không dò). Fabric chưa dựng thì lần dựng đầu tự đăng ký."""
        f = self._fabric
        if f is None or self._providers is None:
            return
        self._providers.dang_ky_vao_fabric(f)

    #: Han dung cua mot lan do suc khoe. Qua han thi do lai truoc khi ket
    #: luan "khong co worker nao" — neu khong, mot provider vua song lai se
    #: bi coi la chet cho tan phien.
    HAN_DO_SUC_KHOE = 300.0

    def _dam_bao_suc_khoe(self, ly_do: str) -> bool:
        """Dò sức khoẻ nếu chưa từng dò, hoặc lần dò cuối đã quá hạn.

        Gọi NGAY TRƯỚC khi cần một placement, không phải lúc dựng — dò thật
        gọi ra `agy`/`codex` nên nó không thuộc về hàm dựng.

        Trả `True` nếu vừa dò. Không bao giờ nâng ngoại lệ ra ngoài: dò hỏng
        thì fabric giữ nguyên trạng thái cũ và việc vẫn `WAITING` với lý do
        đọc được — fail closed, không đoán là provider đang sống.
        """
        if self._fabric_ngoai:
            return False
        if time.time() - self._lan_do_cuoi < self.HAN_DO_SUC_KHOE:
            return False
        try:
            FC.do_suc_khoe(self.fabric)
        except Exception as exc:                              # noqa: BLE001
            self.store.ghi_su_kien(
                "FABRIC_PROBE_FAILED", level="WARN",
                detail=f"dò sức khoẻ hỏng ({ly_do}): "
                       f"{type(exc).__name__}: {exc}"[:400])
            # Van danh dau da do: neu khong, moi tick se lai goi ra mang.
            self._lan_do_cuoi = time.time()
            return False
        self._lan_do_cuoi = time.time()
        # `Fabric.runtimes` la DICT (`runtime_id -> WorkerRuntime`); duyet
        # truc tiep se cho ra CHUOI. Da vap dung loi nay khi viet bai kiem.
        rts = list(self.fabric.runtimes.values())
        song = [r for r in rts if r.dispatchable
                and str(getattr(r, "status", "")).upper().find("OFFLINE") < 0]
        self.store.ghi_su_kien(
            "FABRIC_PROBED",
            detail=f"dò sức khoẻ ({ly_do}): {len(song)}/"
                   f"{len(rts)} runtime nhận dispatch")
        return True

    @property
    def dinh_kem(self) -> "KhoDinhKem":
        """Kho đính kèm. Dựng lười: mở app ra xem sổ thì không cần nó."""
        if self._dinh_kem is None:
            from scripts.control_center.attachments import KhoDinhKem
            self._dinh_kem = KhoDinhKem(self.store, goc=self.root)
        return self._dinh_kem

    @property
    def usage(self) -> UsageReporter:
        if self._usage is None:
            self._usage = UsageReporter(self.store, fabric=self.fabric)
        return self._usage

    @property
    def quan_sat(self):
        """`DichVuQuanSat` — trạng thái SỐNG của dự án (V0.5).

        TÁCH HẲN khỏi `usage`/`snapshot`: hai cái đó đọc sổ của CHÍNH
        Control Center, còn cái này đo những hệ thống BÊN NGOÀI mà Router
        không điều phối. Gộp chúng lại là đúng lỗi V0.5 tồn tại để sửa —
        xem `observability/model.py`.
        """
        if getattr(self, "_quan_sat", None) is None:
            from scripts.control_center.observability.service import \
                DichVuQuanSat
            self._quan_sat = DichVuQuanSat(self.store)
        return self._quan_sat

    def _bat_ky_uc(self) -> None:
        """Mở `DichVuKyUc` và cắm người ghi vào sổ. Không bao giờ ném."""
        try:
            from scripts.control_center.memory.service import DichVuKyUc
            self._ky_uc = DichVuKyUc(self.store, self.root)
            # HYDRAT: phien MOI biet ngay minh dang tiep tuc cai gi. Ghi
            # mot su kien de nghiem thu dem duoc, va de Logs noi thang
            # "da nap diem dung X" thay vi im lang.
            for p in self.store.projects():
                tt = self._ky_uc.tiep_tuc(p.project_id)
                if tt.get("co_gi_de_tiep_tuc"):
                    dd = tt.get("diem_dung") or {}
                    self.store.ghi_su_kien(
                        "MEMORY_RESUMED", project_id=p.project_id,
                        detail=(f"nạp ký ức: {tt.get('so_su_kien', 0)} sự kiện, "
                                f"{tt.get('so_ky_uc', 0)} ký ức, điểm dừng "
                                f"{dd.get('ma', '-')} ({dd.get('ly_do', '')})"),
                        meta={"diem_dung": dd.get("ma", ""),
                              "so_su_kien": tt.get("so_su_kien", 0)})
        except Exception as exc:                            # noqa: BLE001
            self._ky_uc = None
            self._ky_uc_loi = f"{type(exc).__name__}: {exc}"[:300]
            try:
                self.store.ghi_su_kien("MEMORY_UNAVAILABLE", level="WARNING",
                                       detail=f"ký ức không mở được: {self._ky_uc_loi}")
            except Exception:                               # noqa: BLE001
                pass

    @property
    def ky_uc(self):
        """`DichVuKyUc` hoặc `None` khi không mở được (đã ghi sự kiện)."""
        return self._ky_uc

    #: Cache VIEN NANG theo du an: ((muc, phien_ban), luc). Giu `muc` chu
    #: KHONG giu van ban da render — ban gon cat theo TUNG CAU HOI. Doc so moi
    #: luot chat la mot truy van SQLite + phep so mocs: re, nhung khong can
    #: lam moi giay.
    _NANG_TTL = 30.0

    # -- 0b. Hoi dong suy luan (V0.8) -----------------------------------------

    #: Bao lau moi doc lai chinh sach model cao cap tu ky uc. Mot quyet dinh
    #: du an khong doi theo giay; doc lai moi luot chat la mot truy van FTS
    #: thua cho MOI tin nhan.
    HAN_CHINH_SACH = 120.0

    def chinh_sach_cao_cap(self, project_id: str):
        """`ChinhSachCaoCap` của dự án — TRA TỪ KÝ ỨC, có bộ đệm ngắn.

        Không bao giờ ném: mọi đường hỏng ra `fail_closed` + HẠN CHẾ. Xem
        `reasoning/chinh_sach.py` cho lý do mặc định là hạn chế.
        """
        from scripts.control_center.reasoning import chinh_sach as CS

        now = time.time()
        with self._khoa:
            cu = self._chinh_sach_cache.get(project_id)
        if cu and now - cu[1] < self.HAN_CHINH_SACH:
            return cu[0]
        try:
            # `self._fabric` (RIÊNG, có thể `None`) chứ KHÔNG phải `self.fabric`:
            # đọc chính sách không được kéo theo một lần dựng fabric. Fabric
            # chưa dựng thì `ten_model_cao_cap` rơi về `MODEL_ASTRA` — đủ cho
            # phép tra, vì `_khoi_hoi_dong` đã gọi `_dam_bao_suc_khoe()` (tức
            # đã dựng fabric) TRƯỚC khi hỏi tới hàm này.
            cs = CS.doc_chinh_sach(self._ky_uc, project_id,
                                   ten_model=CS.ten_model_cao_cap(self._fabric))
        except Exception as exc:                            # noqa: BLE001
            cs = CS.ChinhSachCaoCap(
                han_che=True, nguon="fail_closed",
                ghi_chu=f"{type(exc).__name__}: {exc}"[:160])
        with self._khoa:
            self._chinh_sach_cache[project_id] = (cs, now)
        return cs

    @property
    def hoi_dong(self):
        """`HoiDong` dùng chung. Dựng muộn — xem ghi chú ở `__init__`."""
        if self._hoi_dong is None:
            from scripts.control_center.reasoning.dinh_tuyen import BoDinhTuyenVai
            from scripts.control_center.reasoning.goi import BoGoiThat
            from scripts.control_center.reasoning.hoi_dong import HoiDong

            # TRONG SO cua kho, va no KHONG duoc lam vo hoi dong khi thieu.
            #
            # `_khoi_hoi_dong` nuot moi ngoai le vao `REASONING_ERROR` de mot
            # luot chat khong bao gio vo — nghia la bat ky thu gi nem o day
            # se TAT hoi dong mot cach cam. Da mat mot lan vi dung ly le do
            # (xem `BenchmarkStore` ngay duoi), nen duong nay rot ve trong so
            # mac dinh thay vi nem.
            try:
                _f, w, _e = FC.nap(root=self.root, probe=False)
            except Exception as exc:                        # noqa: BLE001
                from scripts.router_v4.scheduler import Weights
                w = Weights()
                self.store.ghi_su_kien(
                    "REASONING_WEIGHTS_FALLBACK", level="WARNING",
                    detail=(f"không nạp được trọng số fabric "
                            f"({type(exc).__name__}) — dùng mặc định")[:200])
            # `root=` CHU KHONG phai vi tri dau: tham so vi tri dau cua
            # `BenchmarkStore` la mot DUONG DAN TEP, con `self.root` la mot
            # THU MUC — truyen nham thi no mo thu muc nhu mot tep va nem
            # `PermissionError: [Errno 13]`, ma `_khoi_hoi_dong` nuot vao
            # `REASONING_ERROR`. Hau qua: hoi dong KHONG BAO GIO chay, va
            # giao dien chi thay ban ghi cu cua luot truoc. Do that o phep
            # kiem duong day cua engine truoc khi commit.
            # LICH SU CUA VAI nam o TEP RIENG (`history.duong_vai`) — KHONG
            # tron voi lich su worker. Cung mot kho doc no de cho diem VA ghi
            # vao no sau moi luot: do la ca vong phan hoi, va no la thu bien
            # `benchmark_profile` tu tien nghiem cau hinh thanh so DO DUOC.
            from scripts.router_v4.history import duong_vai
            ls_vai = BenchmarkStore(path=duong_vai(self.root))
            bdt = BoDinhTuyenVai(self.fabric, weights=w, history=ls_vai)
            bo_goi = self._bo_goi_vai
            if bo_goi is None:
                bo_goi = BoGoiThat(providers=self._providers)
            self._hoi_dong = HoiDong(bo_dinh_tuyen=bdt, bo_goi=bo_goi,
                                     ghi_su_kien=self.store.ghi_su_kien,
                                     lich_su=ls_vai,
                                     rubric="docs/reports/REASONING_V08_REAL.md#rubric")
        return self._hoi_dong

    def nguon_goc_suy_luan(self, project_id: str) -> Dict:
        """Nguồn gốc định tuyến của lượt gần nhất — §12. `{}` khi chưa có."""
        with self._khoa:
            return dict(self._nguon_goc_suy_luan.get(project_id) or {})

    def dat_che_do(self, project_id: str, che_do: str) -> Dict:
        """Đặt chế độ chất lượng ECO/AUTO/STRONG/MAX cho một dự án. BỀN.

        FAIL CLOSED trên một giá trị lạ: một chế độ gõ sai không được âm
        thầm thành AUTO, vì người dùng sẽ tưởng họ đang ở MAX.
        """
        from scripts.router_v4.premium import CheDo

        try:
            cd = CheDo(str(che_do or "").strip().upper())
        except ValueError as exc:
            raise ValueError(
                f"chế độ {che_do!r} không hợp lệ — chỉ nhận "
                f"{[c.value for c in CheDo]}") from exc
        bg = self.leader_ban_ghi(project_id)
        cu = bg.che_do
        bg.che_do = cd.value
        bg.updated_at = time.time()
        self.store.luu_leader(bg.to_dict())
        self.store.ghi_su_kien(
            "QUALITY_MODE", project_id=project_id,
            detail=f"chế độ chất lượng {cu} -> {cd.value}",
            meta={"tu": cu, "sang": cd.value})
        return {"project_id": project_id, "che_do": cd.value, "truoc": cu}

    def _khoi_vien_nang(self, project_id: str, text: str = "") -> str:
        """Khối VIÊN NANG DỰ ÁN (bản GỌN, có trần token) cho nhắc nhở Leader.

        Phần I của V0.7: Leader phải hydrate RẺ. Viên nang đầy của một dự án
        thật ~3.9k token; bản gọn ~0.9k. KHÔNG nạp hàng nghìn sự kiện lịch sử —
        đó là việc của truy hồi sâu khi lượt cần.

        Bản gọn chọn mục THEO CÂU HỎI (`text`), nên bộ đệm phải giữ `muc` —
        thứ đắt vì phải đọc sổ — chứ KHÔNG giữ văn bản đã render: giữ văn bản
        thì lượt sau nhận đúng bản cắt của câu hỏi trước.
        """
        if not project_id:
            return ""
        now = time.time()
        with self._khoa:
            cu = getattr(self, "_nang_cache", {}).get(project_id)
        goi = None
        if cu and now - cu[1] < self._NANG_TTL:
            goi = cu[0]
        try:
            from scripts.control_center import vien_nang_du_an as VN
            if goi is None:
                goi = VN.nap(self, project_id)
                with self._khoa:
                    if not hasattr(self, "_nang_cache"):
                        self._nang_cache = {}
                    self._nang_cache[project_id] = (goi, now)
            muc, pb = goi
            if not muc:
                return ""
            van = VN.render_gon(muc, cau_hoi=text or "")
            return (f"(Viên nang v{pb})\n" + van) if van else ""
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "MEMORY_ERROR", project_id=project_id, level="WARNING",
                detail=f"dựng khối viên nang: {type(exc).__name__}: {exc}"[:200])
            return ""

    def _khoi_ky_uc(self, project_id: str, text: str, *,
                    kem_su_kien: bool = False) -> str:
        """Khối KÝ ỨC DỰ ÁN cho nhắc nhở Leader, hoặc `""`.

        Có trần token riêng (`memory.json`), độc lập với kích thước lịch
        sử. Đi kèm `leader.LUAT_KY_UC` ở MỌI lượt có khối — xem lý do ở
        `leader.py`. Lỗi ở đây không được làm vỡ lượt chat. `kem_su_kien`
        (câu hỏi lịch sử) đính thêm dòng L0 khớp câu hỏi làm bằng chứng.
        """
        if self._ky_uc is None:
            return ""
        try:
            van = self._ky_uc.khoi_cho_leader(project_id, text,
                                              kem_su_kien=kem_su_kien)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien("MEMORY_ERROR", project_id=project_id,
                                   level="WARNING",
                                   detail=f"dựng khối ký ức: {type(exc).__name__}: {exc}"[:200])
            return ""
        if van:
            from scripts.control_center.memory.model import uoc_token
            self.store.ghi_su_kien("MEMORY_CONTEXT", project_id=project_id,
                                   detail=f"khối ký ức {uoc_token(van)} token",
                                   meta={"token": uoc_token(van)})
        return van

    # -- 1. Du an ------------------------------------------------------------

    def them_project(self, project: Project) -> Project:
        self.store.luu_project(project)
        self.store.ghi_su_kien("PROJECT_ADDED", project_id=project.project_id,
                               detail=f"{project.name} @ {project.repo_path}")
        # Lam am Leader NGAY khi co du an dau tien.
        #
        # `start()` cung goi, nhung tren mot ban cai moi (EXE ngoai kho git)
        # luc `start()` chua co du an nao — nen neu chi am o do thi tin nhan
        # dau tien cua nguoi dung van chiu tron ~8 giay khoi dong nguoi.
        # Do that o luot nghiem thu: 14.5s cho cau chao dau.
        self._am_leader_nen()
        return project

    def projects(self) -> List[Project]:
        return self.store.projects()

    #: Du an MAC DINH cua ban phat hanh. `bootstrap.du_an_mac_dinh()` la
    #: nguon su that; lap lai ten o day chi de `xoa_project` biet cai gi
    #: KHONG duoc xoa nham.
    DU_AN_MAC_DINH = ("fanfic", "router")

    def xoa_project(self, project_id: str, *,
                    xac_nhan: bool = False) -> Dict[str, int]:
        """Gỡ MỘT dự án khỏi sổ. Dành cho dọn trạng thái thử nghiệm/demo.

        `xac_nhan=True` là bắt buộc. Đây là thao tác không hoàn tác được, và
        một tham số mặc định an toàn là thứ chặn nó xảy ra do gọi nhầm.

        TỪ CHỐI xoá dự án mặc định của bản phát hành (`fanfic`, `router`) —
        chúng là dự án THẬT của người dùng, không phải đồ thử. Muốn bỏ thì
        `archived`, đừng xoá.

        KHÔNG chạm tới worktree trên đĩa. Xem `ControlStore.xoa_project`.
        """
        if not xac_nhan:
            raise ValueError(
                f"xoá {project_id!r} là thao tác không hoàn tác được — "
                f"truyền `xac_nhan=True` nếu thật sự muốn.")
        if project_id in self.DU_AN_MAC_DINH:
            raise ValueError(
                f"{project_id!r} là dự án mặc định của bản phát hành, không "
                f"phải trạng thái thử nghiệm. Dùng `archived` nếu muốn ẩn nó.")
        p = self.store.project(project_id)
        if p is None:
            return {}
        # TU CHOI khi con viec DANG CHAY.
        #
        # Xoa giua chung thi agent van chay tiep, nhung moi hang cua no da
        # biet mat: `ghi_ket_qua` thanh no-op, `doi_trang_thai` nem
        # `StoreError`, va toan bo ket qua mat. Te hon: `lm.tra()` o duoi
        # nha MOI khoa cua du an — ke ca khoa PRODUCTION, thu ma `reclaim()`
        # co y khong bao gio dung toi — trong khi mot agent van dang ghi.
        # Worktree thi con nguyen tren dia nhung khong con hang nao noi ai
        # so huu, nen lan `doi_soat()` sau dang ky lai no nhu mot cay RANH.
        dang = [t.task_id for t in self.store.tasks(project_id)
                if t.state is TaskState.RUNNING]
        with self._khoa:
            dang += [x for x in self._dang_chay if x.startswith(project_id + ".")]
        if dang:
            raise ValueError(
                f"{project_id!r} còn {len(dang)} việc ĐANG CHẠY "
                f"({sorted(set(dang))[:3]}) — dừng chúng trước "
                f"(`stop`), nếu không kết quả của chúng sẽ mất và khoá của "
                f"chúng bị nhả trong khi agent vẫn đang ghi.")
        # Nha khoa TRUOC khi xoa hang: neu du an bien mat truoc, `tra()`
        # khong con biet khoa nao thuoc ve no.
        lm = LockManager(self.store)
        for t in self.store.tasks(project_id):
            lm.tra(project_id, t.task_id)
        with self._khoa:
            self._ctx.pop(project_id, None)
        dem = self.store.xoa_project(project_id)
        self.store.ghi_su_kien(
            "PROJECT_REMOVED", level="WARNING",
            detail=(f"đã gỡ dự án {project_id!r} ({p.name}) khỏi sổ: "
                    f"{dem}. Worktree trên đĩa KHÔNG bị đụng tới."),
            meta={"project_id": project_id, "deleted": dem})
        return dem

    def ctx(self, project_id: str) -> ProjectContext:
        """Ngữ cảnh của một dự án. Dựng một lần, giữ lại."""
        with self._khoa:
            c = self._ctx.get(project_id)
            if c is not None:
                return c
        p = self.store.project(project_id)
        if p is None:
            raise KeyError(f"không có dự án {project_id!r}")

        goc = Path(p.repo_path)
        f = self.fabric
        sched = Scheduler(f, history=BenchmarkStore(root=goc))
        wt = WorktreeCoordinator(project_id, goc, self.store)
        logs = RawLogStore(root=goc)

        if self._executor_factory is not None:
            ex = self._executor_factory(p, f)
        else:
            ex = Executor(f, root=goc, worktrees=wt.manager, logs=logs)
        # Phien so huu worktree, nen Executor phai HOI phien thay vi tu tao.
        ex.worktree_provider = self._cap_worktree(project_id)

        sm = SessionManager(project_id, self.store, fabric=f, scheduler=sched,
                            worktrees=wt, max_sessions=self.max_parallel)
        ctx = ProjectContext(
            project=p, fabric=f, scheduler=sched, executor=ex, sessions=sm,
            worktrees=wt, leases=LeaseStore(root=self.root),
            planner=RulePlanner(default_write_scope=self._scope_mac_dinh(p)),
            logs=logs)
        with self._khoa:
            self._ctx[project_id] = ctx
        return ctx

    @staticmethod
    def _scope_mac_dinh(p: Project) -> Tuple[str, ...]:
        """Phạm vi ghi mặc định khai trong `resources` với tiền tố `write:`.

        Không có thì bộ lập kế hoạch KHÔNG đoán — việc bị hạ xuống chỉ đọc
        kèm ghi chú. Xem `planner.RulePlanner.plan`.
        """
        return tuple(r.split(":", 1)[1] for r in p.resources
                     if str(r).startswith("write:") and ":" in r)

    def _cap_worktree(self, project_id: str):
        """Hook cho `Executor.worktree_provider` — trả cây của PHIÊN.

        Trả `None` khi không tra được phiên: `Executor` sẽ tự tạo cây mới,
        tức là lùi về đúng hành vi Router V4 vốn có. Không bao giờ ném từ
        đây — một lỗi tra sổ không được phép làm hỏng một lượt chạy đã tới
        tận bước dựng cây.
        """
        def _lay(c: TaskContract, p: Placement, base_sha: str, attempt: int):
            try:
                t = self.store.task(c.task_id)
                if t is None or not t.owner_session:
                    return None
                s = self.store.session(t.owner_session)
                if s is None or not s.worktree:
                    return None
                h = self.store.worktree(s.worktree)
                if h is None or not Path(s.worktree).exists():
                    return None
                return WorktreeHandle(
                    worker_id=s.runtime_id, task_id=c.task_id,
                    path=Path(s.worktree), branch=s.branch,
                    base_sha=h.get("base_sha", "") or base_sha)
            except Exception:                             # noqa: BLE001
                return None
        return _lay

    # -- 2. O chat -----------------------------------------------------------

    def chat(self, project_id: str, text: str, *,
             attachment_ids: Optional[Sequence[str]] = None) -> Dict:
        """Ý định người dùng -> việc được quản lý. Đây là CỔNG VÀO của V0.1.

        Việc GATED KHÔNG vào hàng đợi. Nó được tạo ở `BLOCKED` kèm câu hỏi
        cụ thể — người dùng phải mở khoá bằng `mo_khoa_gated()`. Cho phép nó
        `QUEUED` rồi chặn ở bước sau là để một lỗi lập lịch duy nhất đủ để
        nó chạy.

        `attachment_ids` (V0.2): những đính kèm người dùng gửi CÙNG tin
        nhắn này. Chúng được gán cho ĐÚNG những việc do tin nhắn này sinh
        ra, và không cho việc nào khác — xem `attachments.py` bất biến #4.
        Chỉ nhận **mã**, không nhận đường dẫn: frontend không có cách nào
        bảo tầng này đọc một tệp tuỳ ý.
        """
        # `try/finally` bao CA than ham: bo dem tien do phai duoc xoa ke ca
        # khi Leader nem, khong thi o chat treo mai o "dang suy nghi".
        try:
            return self._chat(project_id, text, attachment_ids)
        finally:
            self._dat_buoc(project_id, "")

    def _chat(self, project_id: str, text: str,
              attachment_ids: Optional[Sequence[str]] = None) -> Dict:
        ctx = self.ctx(project_id)
        tin = self.store.them_chat(project_id, "user", text)

        # Gan dinh kem vao TIN NHAN truoc khi phan ra, de neu phan ra hong
        # thi dinh kem van con o tin nhan chu khong mo coi.
        dk_hop_le: List[str] = []
        for aid in (attachment_ids or ()):
            dk = self.store.dinh_kem(aid)
            if dk is None or dk.project_id != project_id:
                # FAIL CLOSED: ma la, hoac ma cua DU AN KHAC -> bo qua va
                # ghi lai. Khong nem ngoai le vi mot ma xau khong duoc lam
                # mat ca tin nhan nguoi dung vua go.
                self.store.ghi_su_kien(
                    "ATTACHMENT_REJECTED", project_id=project_id,
                    level="WARN",
                    detail=f"mã đính kèm không thuộc dự án này: {aid!r}")
                continue
            self.store.gan_dinh_kem_cho_message(aid, tin.message_id)
            dk_hop_le.append(aid)

        # V0.9 — BA CỔNG TRƯỚC LEADER, và cả ba đều TẤT ĐỊNH (0 lượt model,
        # 0 việc khảo sát). Thứ tự có nghĩa:
        #
        #   1. ĐIỀU KHIỂN ("dừng task này")  — §13. Phải đứng trước hết: câu
        #      này chứa động từ hành động và sẽ bị `xet_tiep_noi` hiểu nhầm
        #      thành một lệnh XIN LÀM nếu để sau.
        #   2. HỎI TRẠNG THÁI ("xong chưa bro?") — §12. Trả lời TỪ SỔ.
        #   3. TIẾP NỐI ("ok làm đi") — §1. Nối về đúng đề xuất trước đó.
        #
        # Hai cổng đầu chỉ mở khi dự án THẬT SỰ có lần thực thi còn sống —
        # không thì "dừng đi" giữa một cuộc trò chuyện bình thường sẽ rơi
        # vào nhánh điều khiển và không ai trả lời.
        cong = self._cong_thuc_thi(project_id, text, tin, dk_hop_le)
        if cong is not None:
            return cong

        # V0.3: ĐI QUA LEADER. Một tin nhắn KHÔNG còn mặc nhiên thành việc.
        #
        # Leader quyết CHAT/STATUS/CONTROL/WORK trong MỘT lượt (ảnh chụp dự
        # án được đính kèm sẵn, nên câu hỏi trạng thái không cần lượt thứ
        # hai và không cần một agent nào). Chỉ WORK mới xuống tới bộ phân
        # rã + Router V4 như cũ.
        self._dat_buoc(project_id, "Leader đang đọc ảnh chụp dự án")
        qd = self._leader_quyet_dinh(ctx, text)
        if qd is not None and qd.y_dinh != leader.WORK:
            return self._leader_khong_uy_thac(ctx, qd, tin, dk_hop_le)

        # LEADER KHONG DUNG DUOC + CAU HOI LICH SU -> KHONG dispatch.
        #
        # Do that 2026-09-10: Leader (chay qua `agy` headless) tu chon cong cu
        # `read_file` de di doc kho, chi do bi TU CHOI QUYEN (headless khong
        # hoi duoc ai), luot tra ve RONG -> `LeaderLoi` -> engine roi ve bo
        # phan ra va TAO MOT VIEC. Nguoi dung thay dung cai minh khong muon:
        # mot worker 200s cho mot cau hoi ma so da tra loi duoc.
        #
        # Nguyen tac "mat Leader khong duoc mat kha nang giao viec" GIU NGUYEN
        # cho viec THAT. Nhung mot cau hoi LICH SU khong phai viec: rot ve
        # dispatch o day la sai theo nghia, khong chi ton kem. Tra ve dung
        # nhung gi KY UC co, kem ma ban ghi, va noi ro Leader dang khong dung
        # duoc — 0 khe AG.
        if qd is None:
            la_ls, _dh = leader.la_cau_hoi_lich_su(text)
            if la_ls:
                khoi = self._khoi_ky_uc(project_id, text, kem_su_kien=True)
                if khoi.strip():
                    loi = ("Leader tạm thời không dùng được (phiên headless bị "
                           "từ chối quyền công cụ), nên tôi trả lời TRỰC TIẾP từ "
                           "ký ức dự án — không tạo việc nào:\n\n" + khoi
                           + "\n\nCần điều tra sâu hơn trong kho thì nói rõ, tôi "
                             "sẽ uỷ thác.")
                    t2 = self.store.them_chat(project_id, role="assistant",
                                              text=loi, meta={"loai": "ky_uc"})
                    self.store.ghi_su_kien(
                        "MEMORY_ANSWER_FALLBACK", project_id=project_id,
                        detail=("Leader không dùng được; trả lời câu hỏi lịch sử "
                                "từ ký ức, KHÔNG dispatch")[:300])
                    return {"reply": loi, "tasks": [], "plan": None,
                            "message_id": tin.message_id,
                            "attachment_ids": list(dk_hop_le),
                            "leader": None, "control": [],
                            "ky_uc_fallback": True,
                            "assistant_message_id": getattr(t2, "message_id", 0)}

        goal = text
        if qd is not None:
            for a in qd.actions:
                if a.loai == "delegate_work":
                    goal = str(a.tham_so.get("objective") or text)
                    break

        self._dat_buoc(project_id, "đang phân rã mục tiêu thành việc")
        kh: PlanResult = ctx.planner.plan(goal, ctx.project)
        self._dat_buoc(project_id, "đang giao việc cho Router V4")
        tao: List[Task] = []
        # V0.6.1 — TOA: nguoi dung noi ro "goi N agent…"/"moi agent mot…" ->
        # MOT viec cha + N viec con doc lap, khong phai mot viec to. Doc tu
        # CAU NGUOI DUNG GO (`text`), khong tu loi dien dat lai cua Leader —
        # chinh cho do lam mat so 8 o nghiem thu tay. Xem `toa.py`.
        from scripts.control_center import toa as TOA
        yc = TOA.xet_toa(text)
        thong_bao_toa = ""
        toa_meta: Optional[Dict] = None
        if yc is not None and kh.tasks:
            cha, con, sc = self._tao_toa(ctx, project_id, yc, kh, goal)
            tao = [cha] + con
            thong_bao_toa = TOA.cau_thong_bao(sc, cha_id=cha.task_id)
            toa_meta = {"cha": cha.task_id, "con": [c.task_id for c in con],
                        "yeu_cau": yc.to_dict(), "suc_chua": sc.to_dict()}
        for pt in ([] if toa_meta else kh.tasks):
            gated = pt.envelope.gated
            hd_pt = self._hop_dong_dict(pt, project_id)
            if any(k is LockKind.GIT for k, _r, _m in pt.resources):
                # Viec doc lich su git (khong toa): cung mot cach — Router doc
                # `git log` va dinh vao muc tieu, agent khong can lenh shell.
                self._kem_nhat_ky_git(ctx.project.repo_path, hd_pt)
            # Viec co URL cong khai -> Router doc trang HO va dinh bang chung,
            # agent headless khong dung duoc `read_url`. Quyen agent KHONG doi.
            self._kem_web_vao_hd(text, hd_pt)
            # Viec CHAN DOAN VAN HANH -> dinh bang chung probe. Day chinh la
            # cho `fanfic.t2efd-1` chet: khong co dong nay thi worker phai xin
            # `command` va headless tu choi.
            self._kem_probe_vao_hd(self._khoi_probe(text, project_id), hd_pt)
            t = Task(
                task_id=f"{project_id}.{pt.task_id}",
                project_id=project_id, title=pt.title, objective=pt.objective,
                state=TaskState.BLOCKED if gated else TaskState.QUEUED,
                priority=pt.priority,
                dependencies=tuple(f"{project_id}.{d}"
                                   for d in pt.dependencies),
                contract=hd_pt,
                permission=pt.envelope.decision.value,
                gate_reason=pt.envelope.ly_do(),
                blocked_reason=(pt.envelope.cau_hoi_cho_nguoi_dung()
                                if gated else ""),
                resources=tuple(chuoi_tai_nguyen(k, r, m) for k, r, m in pt.resources))
            self.store.luu_task(t)
            tao.append(t)
            self.store.ghi_su_kien(
                "TASK_CREATED", project_id=project_id, task_id=t.task_id,
                level="WARNING" if gated else "INFO",
                detail=f"{pt.kind}: {pt.title}",
                meta={"permission": t.permission, "kind": pt.kind,
                      "scope": list(pt.contract.allowed_scope),
                      "resources": list(t.resources)})

        # Cap dinh kem cho DUNG nhung viec vua sinh ra tu tin nhan nay.
        for aid in dk_hop_le:
            for t in tao:
                self.store.gan_dinh_kem_cho_task(aid, t.task_id)
            if tao:
                self.store.ghi_su_kien(
                    "ATTACHMENT_GRANTED", project_id=project_id,
                    detail=f"{aid} -> {', '.join(t.task_id for t in tao)}",
                    meta={"attachment_id": aid,
                          "task_ids": [t.task_id for t in tao]})

        # Loi cua LEADER dan dau, ke hoach cua bo phan ra di sau. Nguoi dung
        # can biet "chuyen gi sap xay ra" bang mot cau, khong phai bang mot
        # bang ke hoach.
        if toa_meta:
            # Cau ve suc chua do ENGINE viet tu fabric that — khong phai loi
            # hua cua Leader. Leader co the noi gi cung duoc o tren; dong nay
            # la su that ve so viec va so khe.
            tra_loi = thong_bao_toa + "\n" + "\n".join(
                f"  • [{t.task_id}] {t.title}" for t in tao[1:])
        else:
            tra_loi = kh.render()
        if qd is not None and qd.reply:
            tra_loi = qd.reply + "\n\n" + tra_loi
        self.store.them_chat(project_id, "assistant", tra_loi,
                             meta={"plan": kh.to_dict(), "toa": toa_meta,
                                   "task_ids": [t.task_id for t in tao],
                                   "attachment_ids": list(dk_hop_le),
                                   "leader": (qd.to_dict() if qd else None),
                                   "loai": "delegation"})
        return {"reply": tra_loi, "tasks": [t.to_dict() for t in tao],
                "plan": kh.to_dict(), "toa": toa_meta, "message_id": tin.message_id,
                "attachment_ids": list(dk_hop_le),
                "leader": (qd.to_dict() if qd else None)}

    # -- 2a. Ba cong TAT DINH truoc Leader (V0.9) ---------------------------

    def _cong_thuc_thi(self, project_id: str, text: str, tin,
                       dk_hop_le: List[str]) -> Optional[Dict]:
        """Điều khiển / hỏi trạng thái / tiếp nối. `None` = không cổng nào mở.

        Mọi nhánh ở đây trả lời mà KHÔNG gọi một model nào và KHÔNG tạo một
        việc khảo sát nào. Đó là yêu cầu §12 viết thành mã, không phải một
        tối ưu: một Leader phải uỷ thác một việc để biết trạng thái của
        chính mình là một vòng lặp vô nghĩa mà người dùng trả tiền.
        """
        song = self.so_thuc_thi.dang_chay(project_id)

        # 1. DIEU KHIEN — §13
        lenh = ETN.lenh_dieu_khien(text)
        if lenh and song:
            y = song[0]
            bd = self.dieu_phoi(project_id)
            try:
                if lenh == "huy":
                    y2 = bd.huy(y.execution_id, ly_do=f"người dùng: {text[:120]}")
                    loi = (f"Đã huỷ `{y.execution_id}` — {y.goal[:100]}\n\n"
                           f"Việc con đang bay đã được dừng, khoá đã nhả. "
                           f"Lịch sử và bằng chứng GIỮ NGUYÊN, không xoá gì.")
                elif lenh == "tam_dung":
                    y2 = bd.tam_dung(y.execution_id,
                                     ly_do=f"người dùng: {text[:120]}")
                    loi = (f"Đã tạm dừng `{y.execution_id}`. Lượt agent đang "
                           f"bay vẫn chạy nốt và vẫn trả kết quả — nhưng "
                           f"không bước mới nào được giao. Nói 'tiếp tục' "
                           f"khi muốn chạy lại.")
                else:
                    bd.tiep_tuc(y.execution_id)
                    y2 = self.so_thuc_thi.y_dinh(y.execution_id) or y
                    loi = (f"Đang chạy tiếp `{y.execution_id}`.\n\n"
                           + DP.cau_trang_thai(self.so_thuc_thi, project_id))
            except Exception as exc:                        # noqa: BLE001
                loi = (f"Không đổi được trạng thái `{y.execution_id}`: "
                       f"{type(exc).__name__}: {exc}")
                y2 = y
            t2 = self.store.them_chat(
                project_id, "assistant", loi,
                meta={"loai": "dieu_khien_thuc_thi", "lenh": lenh,
                      "execution_id": y.execution_id,
                      "trang_thai": getattr(y2, "trang_thai", y.trang_thai).value})
            return {"reply": loi, "tasks": [], "plan": None,
                    "message_id": tin.message_id,
                    "attachment_ids": list(dk_hop_le), "leader": None,
                    "control": [{"lenh": lenh, "execution_id": y.execution_id}],
                    "assistant_message_id": t2.message_id}

        # 2. HOI TRANG THAI — §12
        if song and ETN.la_cau_hoi_trang_thai(text):
            loi = DP.cau_trang_thai(self.so_thuc_thi, project_id)
            self.store.ghi_su_kien(
                "EXEC_STATUS_ANSWERED", project_id=project_id,
                detail=(f"trả lời trạng thái TỪ SỔ cho {len(song)} lần thực "
                        f"thi — 0 việc khảo sát"))
            t2 = self.store.them_chat(
                project_id, "assistant", loi,
                meta={"loai": "trang_thai_thuc_thi",
                      "execution_id": [y.execution_id for y in song]})
            return {"reply": loi, "tasks": [], "plan": None,
                    "message_id": tin.message_id,
                    "attachment_ids": list(dk_hop_le), "leader": None,
                    "control": [], "assistant_message_id": t2.message_id}

        # 3. TIEP NOI — §1
        kn = ETN.giai_quyet(text,
                            self.so_thuc_thi.de_xuat(project_id, chua_dung=True),
                            nguon="user")
        if kn.noi_duoc:
            return self._khoi_dong_tu_de_xuat(project_id, text, tin,
                                              dk_hop_le, kn)
        return None

    def _khoi_dong_tu_de_xuat(self, project_id: str, text: str, tin,
                              dk_hop_le: List[str], kn) -> Dict:
        """"ok làm đi" -> ý định thực thi + kế hoạch + chạy. §1, §2, §3, §4.

        Người dùng KHÔNG phải nhắc lại kế hoạch: mục tiêu lấy từ đề xuất đã
        lưu. Nhưng THẨM QUYỀN thì không thừa hưởng: `tao_y_dinh` quét lại cả
        mục tiêu lẫn câu người dùng vừa gõ, và một kế hoạch chạm production
        dừng ở `WAITING_AUTHORITY` dù người dùng vừa nói "ok làm đi".
        """
        self._dat_buoc(project_id, "đang dựng ý định thực thi")
        ctx = self.ctx(project_id)
        dx = kn.de_xuat
        y = EYD.tao_y_dinh(
            project_id=project_id, goal=kn.muc_tieu, cau_nguoi_dung=text,
            message_id=tin.message_id, de_xuat=(dx.ma if dx else ""),
            rang_buoc=tuple(dx.cac_buoc[:0]) if dx else ())
        kq: PlanResult = ctx.planner.plan(kn.muc_tieu, ctx.project)
        if kn.tin_hieu.pham_vi_noi_ro:
            kq = ELK.cat_theo_pham_vi(kq, kn.tin_hieu.pham_vi_noi_ro)
        if not kq.tasks:
            loi = (f"Mình nối được câu này về đề xuất `{dx.ma if dx else '?'}` "
                   f"nhưng không phân rã ra bước nào chạy được. Nói rõ hơn "
                   f"phần nào cần làm nhé.")
            self.store.them_chat(project_id, "assistant", loi,
                                 meta={"loai": "tiep_noi_rong"})
            return {"reply": loi, "tasks": [], "plan": None,
                    "message_id": tin.message_id,
                    "attachment_ids": list(dk_hop_le), "leader": None,
                    "control": []}
        kh = ELK.tu_plan_result(y, kq, ctx.project)
        bd = self.dieu_phoi(project_id)
        y = bd.bat_dau(y, kh)
        if dx is not None:
            self.so_thuc_thi.danh_dau_de_xuat(dx.ma, y.execution_id)
        for aid in dk_hop_le:
            for st in self.so_thuc_thi.buoc(y.execution_id, kh.phien_ban):
                if st["task_id"]:
                    self.store.gan_dinh_kem_cho_task(aid, st["task_id"])

        d = [f"Ok bro — {kn.ly_do}.", "", f"Mục tiêu: {y.goal}", "",
             kh.render()]
        if y.trang_thai is TrangThaiThucThi.WAITING_AUTHORITY:
            d += ["", EYD.cau_hoi_tham_quyen(y)]
        else:
            bd.tick(y.execution_id)
            d += ["", "Đã bắt đầu. Hỏi 'xong chưa bro?' bất cứ lúc nào — "
                      "mình trả lời từ sổ, không tạo thêm việc nào."]
        loi = "\n".join(d)
        t2 = self.store.them_chat(
            project_id, "assistant", loi,
            meta={"loai": "bat_dau_thuc_thi", "execution_id": y.execution_id,
                  "de_xuat": (dx.ma if dx else ""),
                  "plan": kh.to_dict(), "tiep_noi": kn.to_dict(),
                  "attachment_ids": list(dk_hop_le)})
        return {"reply": loi, "tasks": [], "plan": kh.to_dict(),
                "execution": y.to_dict(), "message_id": tin.message_id,
                "attachment_ids": list(dk_hop_le), "leader": None,
                "control": [], "assistant_message_id": t2.message_id}

    def _luu_de_xuat(self, project_id: str, message_id: int) -> Optional[str]:
        """Chiến lược vừa nói ra -> một `DeXuat` BỀN. §1.

        Không lưu thì "ok làm đi" ở lượt sau chỉ còn hai chữ và Leader phải
        đoán — đúng thứ vòng kín tồn tại để bỏ đi. Lưu KHÔNG khởi động gì:
        một đề xuất là một đề xuất cho tới khi người dùng xin làm.
        """
        with self._khoa:
            ng = dict(self._nguon_goc_suy_luan.get(project_id) or {})
        cl = ng.get("chien_luoc") or {}
        if not isinstance(cl, dict) or not cl:
            return None
        tom = str(cl.get("de_xuat") or cl.get("muc_tieu") or "").strip()
        buoc = [str(x) for x in (cl.get("viec_can_lam")
                                 or cl.get("phuong_an") or ())][:12]
        if not tom:
            tom = (buoc[0] if buoc else "")
        if not tom:
            return None
        van = tom + " " + " ".join(buoc)
        lop, hits = EYD.phan_lop_tham_quyen(van)
        ma = f"dx_{uuid.uuid4().hex[:10]}"
        # AI ĐÃ ĐỀ XUẤT (§B). `nguon_goc` là danh sách `NguonGocVai`; lấy của
        # đúng vai STRATEGIST. Không ghim được thì để rỗng — và lúc đó
        # `phan_hoi.dung_quan_sat` trả `None`, tức là KHÔNG sinh một mẫu vô
        # danh. Thà không có dữ liệu còn hơn có dữ liệu không gắn được vào ai.
        nv = next((x for x in (ng.get("nguon_goc") or [])
                   if isinstance(x, dict) and x.get("vai") == "strategist"), {})
        chon = (nv.get("chon") or {}) if isinstance(nv, dict) else {}
        self.so_thuc_thi.luu_de_xuat(ETN.DeXuat(
            ma=ma, project_id=project_id, message_id=int(message_id or 0),
            tom_tat=tom, cac_buoc=tuple(buoc),
            rui_ro=("HIGH" if hits else "LOW"),
            tac_dong_production=bool(
                {h.operation for h in hits} & EYD.GATED_PRODUCTION),
            tu_vai="strategist",
            provider=str(chon.get("provider") or ""),
            model=str(chon.get("model_id") or ""),
            runtime_id=str(chon.get("runtime_id") or "")))
        self.store.ghi_su_kien(
            "RECOMMENDATION_SAVED", project_id=project_id,
            detail=f"{ma}: {tom[:160]}",
            meta={"ma": ma, "so_buoc": len(buoc), "tham_quyen": lop.value})
        return ma

    def _tao_toa(self, ctx: ProjectContext, project_id: str, yc, kh: PlanResult,
                 goal: str):
        """MỘT việc cha (vật chứa, không chạy agent) + N việc con độc lập.

        Mẫu hợp đồng/phong bì quyền lấy từ việc đầu của bộ phân rã — loại việc,
        phạm vi, khoá tài nguyên, cổng GATED đều giữ nguyên, chỉ NHÂN ra N bản
        với phân vùng khác nhau. Sức chứa được ĐO từ fabric đang sống (có dò
        sức khoẻ nếu đã cũ) ngay lúc tách, để câu trả lời nói đúng số.
        """
        from scripts.control_center import toa as TOA
        mau = kh.tasks[0]
        tien_to = mau.task_id.rsplit("-", 1)[0]
        ma_cha = f"{project_id}.{tien_to}-cha"
        try:
            self._dam_bao_suc_khoe(f"tách {yc.so_agent} việc song song")
        except Exception:                                   # noqa: BLE001
            pass
        with self._khoa:
            dang = len([x for x in self._dang_chay.values() if x.is_alive()])
        sc = TOA.tinh_suc_chua(self.fabric, yc, max_parallel=self.max_parallel,
                               dang_chay=dang)
        # Muc tieu con = CA CAU cua nguoi dung (khong phai menh de dau ma bo
        # phan ra cat ra — "goi 4 agent" khong phai viec). Hop dong/phong bi
        # lay tu viec mau; van ban muc tieu dung lai khuon `_muc_tieu` de agent
        # van nhan dung cac rao cong cu.
        from scripts.control_center.planner import _tieu_de
        try:
            muc_tieu_goc = ctx.planner._muc_tieu(goal, mau.kind, mau.contract.allowed_scope,
                                                 suy_ra=mau.scope_inferred)
        except Exception:                                   # noqa: BLE001
            muc_tieu_goc = mau.objective
        tieu_de_goc = _tieu_de(goal)
        chi_doc = not mau.contract.requirements.repo_write
        cac_con = TOA.chia_con(yc, muc_tieu_goc, tieu_de_goc, chi_doc=chi_doc,
                               pham_vi_mau=tuple(mau.contract.allowed_scope),
                               nhac_git=bool(TOA.NHAC_GIT.search(goal or "")))
        con_ids = [f"{project_id}.{tien_to}-{c.chi_so}" for c in cac_con]
        gated = mau.envelope.gated

        hd_cha = self._hop_dong_dict(mau, project_id)
        hd_cha["task_id"] = ma_cha
        hd_cha["_toa"] = {"cha": True, "so": yc.so_agent, "con": con_ids,
                          "yeu_cau": yc.to_dict(), "suc_chua": sc.to_dict()}
        cha = Task(task_id=ma_cha, project_id=project_id,
                   title=f"[cha · {yc.so_agent} agent] {tieu_de_goc}"[:120],
                   objective=goal, state=TaskState.WAITING, priority=mau.priority,
                   contract=hd_cha, permission=mau.envelope.decision.value,
                   gate_reason=mau.envelope.ly_do())
        self.store.luu_task(cha)
        self.store.ghi_su_kien(
            "TASK_CREATED", project_id=project_id, task_id=ma_cha,
            detail=f"toa: cha của {yc.so_agent} việc con — {tieu_de_goc}",
            meta={"permission": cha.permission, "kind": mau.kind, "toa": hd_cha["_toa"]})

        # URL cong khai trong muc tieu chung: doc MOT lan, dinh cho moi con
        # (tranh N lan doc cung trang). `web_khoi` rong neu khong co URL.
        web_khoi = ""
        try:
            from scripts.control_center.web_reader import rut_url
            _urls = rut_url(goal or "")
            if _urls:
                _kqs = [k for k in self._doc_web_nhieu(_urls, toi_da=2)
                        if k.ok and k.van_ban]
                if _kqs:
                    web_khoi = ("\n\n" + self.DAU_WEB + " (chỉ đọc, công khai). "
                                "KHÔNG dùng read_url/lệnh (headless bị từ chối "
                                "quyền) — phân tích NGAY trên nội dung dưới đây.\n"
                                + "\n\n".join(k.khoi_bang_chung() for k in _kqs))
        except Exception:                                   # noqa: BLE001
            web_khoi = ""
        con_tasks: List[Task] = []
        for c, cid in zip(cac_con, con_ids):
            hd = self._hop_dong_dict(mau, project_id)
            hd["task_id"] = cid
            hd["dependencies"] = []
            hd["objective"] = c.muc_tieu + "\n\n" + mau.envelope.render_for_agent()
            if sc.provider or sc.model:
                req = dict(hd.get("requirements") or {})
                if sc.provider:
                    req["pin_provider"] = sc.provider
                if sc.model:
                    req["pin_model"] = sc.model
                hd["requirements"] = req
            hd["_toa"] = {"cha": False, "cha_id": ma_cha, "chi_so": c.chi_so,
                          "so": yc.so_agent, "phan_vung": c.phan_vung,
                          "che_do": c.che_do, "tai_nguyen": list(c.tai_nguyen)}
            # Pham vi/tai nguyen THEO TUNG CON, khong sao chep cua viec mau:
            # bon con doc bon cho khac nhau phai xin bon khoa READ khac nhau
            # (song chung), khong phai bon lan cung mot khoa WRITE (tuan tu).
            if chi_doc:
                hd["inputs"] = list(c.pham_vi)
            elif c.pham_vi:
                hd["allowed_scope"] = list(c.pham_vi)
            # Con "git history": Router doc `git log` thay agent va dinh vao
            # muc tieu — agent headless khong chay duoc lenh shell (do that:
            # con nay chet `tool_permission_denied`). Quyen agent KHONG doi.
            if any((doc_chuoi_tai_nguyen(r) or (None,))[0] is LockKind.GIT
                   for r in c.tai_nguyen):
                self._kem_nhat_ky_git(ctx.project.repo_path, hd)
            # URL cong khai trong muc tieu chung -> dinh noi dung web (doc MOT
            # lan o tren, tai dung cho moi con) — agent headless khong doc URL.
            if web_khoi:
                hd["objective"] = (hd.get("objective") or "").rstrip() + web_khoi
            t = Task(task_id=cid, project_id=project_id, title=c.tieu_de,
                     objective=c.muc_tieu,
                     state=TaskState.BLOCKED if gated else TaskState.QUEUED,
                     priority=mau.priority, parent_id=ma_cha, contract=hd,
                     permission=mau.envelope.decision.value,
                     gate_reason=mau.envelope.ly_do(),
                     blocked_reason=(mau.envelope.cau_hoi_cho_nguoi_dung()
                                     if gated else ""),
                     resources=tuple(c.tai_nguyen))
            self.store.luu_task(t)
            con_tasks.append(t)
            self.store.ghi_su_kien(
                "TASK_CREATED", project_id=project_id, task_id=cid,
                level="WARNING" if gated else "INFO",
                detail=f"{mau.kind}: {c.tieu_de}",
                meta={"permission": t.permission, "kind": mau.kind,
                      "scope": list(mau.contract.allowed_scope), "toa": hd["_toa"]})
        self.store.ghi_su_kien(
            "TOA_SPLIT", project_id=project_id, task_id=ma_cha,
            detail=TOA.cau_thong_bao(sc, cha_id=ma_cha)[:500],
            meta={"yeu_cau": yc.to_dict(), "suc_chua": sc.to_dict(), "con": con_ids})
        return cha, con_tasks, sc

    #: Dau khoi nhat ky git trong muc tieu — bai kiem va UI nhan ra bang chuoi nay.
    DAU_NHAT_KY_GIT = "NHẬT KÝ GIT DO ROUTER CUNG CẤP"

    def _kem_nhat_ky_git(self, repo_path: str, hd: Dict) -> bool:
        """Đính bản tóm tắt `git log` (chỉ đọc, đã lọc bí mật) vào mục tiêu của
        một việc đọc lịch sử git. Trả `True` nếu có đính.

        VÌ SAO: agent chạy headless bị TỰ CHỐI quyền `command` (không ai để
        hỏi), nên "lục git history" là việc không thể tự làm — con [4/4] của
        nghiệm thu toả 2026-09-10 chết `tool_permission_denied` đúng vì thế.
        Router có sẵn đường đọc git an toàn (`nguon_git`: ba lệnh đọc, tham
        số cố định, có timeout, không cửa sổ) nên đọc thay và đưa dữ liệu
        cho agent phân tích. KHÔNG nới quyền của agent, không thêm cờ nào.
        Không phải kho git / git hỏng -> không đính, việc vẫn chạy như cũ.
        """
        try:
            from scripts.control_center.nguon_git import git_nhat_ky_doc
            van = git_nhat_ky_doc(Path(repo_path))
        except Exception:                                   # noqa: BLE001
            return False
        if not van:
            return False
        hd["objective"] = (
            (hd.get("objective") or "").rstrip()
            + f"\n\n{self.DAU_NHAT_KY_GIT} (chỉ đọc). Phân tích NGAY trên dữ liệu "
              "dưới đây. KHÔNG chạy lệnh git/shell: phiên headless từ chối quyền "
              "`command` và lượt của bạn sẽ kết thúc rỗng. Cần thêm chi tiết của "
              "một commit thì nói rõ mã commit trong findings thay vì chạy lệnh.\n"
            + van)
        return True

    #: Dau khoi noi dung web trong muc tieu worker — bai kiem/UI nhan ra.
    DAU_WEB = "NỘI DUNG WEB DO ROUTER CUNG CẤP"

    def _doc_web_nhieu(self, urls, *, toi_da: int = 2):
        """Đọc tối đa `toi_da` URL bằng WebReader (chỉ đọc, an toàn SSRF).
        Trả list `KetQuaDoc`. Không bao giờ ném."""
        ra = []
        try:
            from scripts.control_center.web_reader import doc_web
        except Exception:                                   # noqa: BLE001
            return ra
        for u in list(urls)[:toi_da]:
            try:
                ra.append(doc_web(u))
            except Exception:                               # noqa: BLE001
                pass
        return ra

    #: Dau khoi bang chung van hanh — bai kiem/UI nhan ra.
    DAU_PROBE = "BẰNG CHỨNG VẬN HÀNH DO ROUTER ĐO"
    #: Bao lau thi mot lan kiem toan duong ong con dung lai duoc. Gom probe
    #: la ~11s va co ban chat la SPAM vao may production, nen khong lam moi
    #: luot chat — nhung cung khong duoc de cu: cau hoi van hanh la cau hoi
    #: "bay gio the nao".
    _PROBE_TTL = 45.0

    def _khoi_probe(self, text: str, project_id: str = "") -> str:
        """Khối BẰNG CHỨNG VẬN HÀNH cho nhắc nhở Leader, hoặc `""`.

        VÌ SAO: `fanfic.t2efd-1` (2026-09-11) chết `tool_permission_denied` vì
        câu hỏi production bị biến thành một việc phân tích kho, rồi worker
        phải xin công cụ `command` — thứ mà `agy --print` tự chối. Router có
        đường đọc production an toàn (`probe_van_hanh`: thao tác CÓ KIỂU,
        tham số theo cấu hình, chỉ đọc, không sudo) nên nó đo TRƯỚC và đưa
        số cho Leader. Quyền của agent KHÔNG đổi.

        Chỉ chạy cho câu hỏi CHẨN ĐOÁN vận hành: một câu trạng thái đơn
        ("farmer chạy không?") đã có `DichVuQuanSat` của V0.5 lo, và gom 11
        probe cho nó là phí.
        """
        from scripts.control_center import leader as _ld
        la_vh, la_chan, _dau = _ld.la_cau_hoi_van_hanh(text or "")
        if not (la_vh and la_chan):
            return ""
        now = time.time()
        with self._khoa:
            cu = getattr(self, "_probe_cache", {}).get(project_id)
        if cu and now - cu[1] < self._PROBE_TTL:
            return cu[0]
        try:
            from scripts.control_center import probe_van_hanh as PV
            mg = PV.tu_du_an(project_id)
            if not mg.kha_dung().get("san_sang"):
                return ""
            bao = PV.kiem_duong_ong(mg)
            van = PV.goi_bang_chung(bao)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "PROBE_ERROR", project_id=project_id, level="WARNING",
                detail=f"gom bằng chứng vận hành: {type(exc).__name__}: {exc}"[:200])
            return ""
        do_duoc = sum(1 for b in bao.bang_chung if b.hieu_luc().do_duoc)
        self.store.ghi_su_kien(
            "PROBE_AUDIT", project_id=project_id, level="INFO",
            detail=(f"kiểm toán đường ống -> {bao.phan_loai} "
                    f"({do_duoc}/{len(bao.bang_chung)} quan sát đo được)")[:300],
            meta={"phan_loai": bao.phan_loai, "so_quan_sat": len(bao.bang_chung),
                  "do_duoc": do_duoc, "thieu": bao.thieu[:6]})
        with self._khoa:
            if not hasattr(self, "_probe_cache"):
                self._probe_cache = {}
            self._probe_cache[project_id] = (van, now)
        return van

    def _khoi_thanh_phan(self, text: str, project_id: str = "") -> str:
        """Khối TRA CỨU THÀNH PHẦN cho câu hỏi gọi tên dân dã.

        Cùng khuôn `nguon_git`/`web_reader`/`probe_van_hanh`: Router làm phép
        đọc an toàn rồi đính BẰNG CHỨNG; quyền của agent KHÔNG đổi, và câu
        hỏi này KHÔNG được biến thành một việc worker.
        """
        from scripts.control_center import leader as _ld
        la_tp, _dh = _ld.la_cau_hoi_thanh_phan(text or "")
        if not la_tp or not project_id:
            return ""
        try:
            from scripts.control_center import tim_thanh_phan as TTP
            p = self.store.project(project_id)
            if p is None:
                return ""
            bt = TTP.BoTimThanhPhan(
                project_id, Path(p.repo_path), store=self.store,
                ky_uc=self._ky_uc, so_thuc_thi=self.so_thuc_thi,
                vien_nang=self._vien_nang_muc(project_id))
            kq = bt.tim(text)
        except Exception as exc:                              # noqa: BLE001
            self.store.ghi_su_kien(
                "RECALL_ERROR", project_id=project_id, level="WARNING",
                detail=f"tra cứu thành phần: {type(exc).__name__}: {exc}"[:200])
            return ""
        self.store.ghi_su_kien(
            "RECALL_AUDIT", project_id=project_id, level="INFO",
            detail=(f"tra cứu {text[:60]!r} -> "
                    f"{len(kq.ung_vien)} ứng viên, chắc={kq.chac}")[:300],
            meta=kq.to_dict())
        self._va_ky_uc_thanh_phan(project_id, text, kq)
        return TTP.goi_tra_loi(kq)

    def _va_ky_uc_thanh_phan(self, project_id: str, text: str, kq) -> None:
        """VÁ KÝ ỨC: thứ vừa tra ra từ kho phải được NHỚ, khỏi tra lại.

        Hai rào, và cả hai đều quan trọng:

        * **Chỉ ghi khi CHẮC.** Còn mơ hồ mà đã đóng đinh một bí danh thì
          lần sau ta trả lời sai một cách tự tin — tệ hơn là không biết.
        * **Ghi BẰNG CHỨNG, không ghi suy luận.** Bản ghi là "bí danh X trỏ
          tới thành phần Y, thấy ở những đường dẫn này" — một sự thật tra lại
          được, không phải dòng suy nghĩ của model.
        """
        if self._ky_uc is None or not getattr(kq, "chac", False):
            return
        if not kq.ung_vien:
            return
        u = kq.ung_vien[0]
        bi_danh = (text or "").strip()[:80]
        thanh_phan = str(u.get("ten") or "")
        if not thanh_phan:
            return
        try:
            pv = self._ky_uc.provider(project_id)
            if pv is not None:
                # Idempotent: đã có bản ghi cho đúng thành phần này thì thôi.
                for m in (pv.tim(thanh_phan, limit=5) or ()):
                    if "bí danh" in str(getattr(m, "tieu_de", "")).lower():
                        return
            bc = "; ".join(str(v)[:120] for v in (u.get("vi_sao") or [])[:3])
            self._ky_uc.ghi_ky_uc(
                project_id, "semantic",
                (f"Bí danh dự án: người dùng gọi «{bi_danh}» — đó là thành "
                 f"phần `{thanh_phan}`. Bằng chứng: {bc}"),
                tieu_de=f"bí danh → {thanh_phan}",
                the=("bi_danh", "thanh_phan"), tin_cay="do_duoc",
                ai="router:tra_cuu_thanh_phan", nguon_loai="recall")
            self.store.ghi_su_kien(
                "RECALL_MEMORY_REPAIR", project_id=project_id, level="INFO",
                detail=f"ghi bí danh «{bi_danh}» -> {thanh_phan}"[:300],
                meta={"bi_danh": bi_danh, "thanh_phan": thanh_phan})
        except Exception as exc:                              # noqa: BLE001
            self.store.ghi_su_kien(
                "RECALL_ERROR", project_id=project_id, level="WARNING",
                detail=f"vá ký ức bí danh: {type(exc).__name__}: {exc}"[:200])

    def _vien_nang_muc(self, project_id: str) -> Dict:
        """Mục viên nang dạng thô cho bộ tra cứu. Rỗng nếu dựng không được."""
        try:
            from scripts.control_center import vien_nang_du_an as VN
            return VN.dung_muc(self, project_id)
        except Exception:                                     # noqa: BLE001
            return {}

    def _kem_probe_vao_hd(self, khoi: str, hd: Dict) -> bool:
        """Đính khối bằng chứng vận hành vào mục tiêu của một việc.

        Cùng khuôn với `_kem_nhat_ky_git`/`_kem_web_vao_hd`: worker headless
        nhận DỮ LIỆU, không nhận quyền chạy lệnh.
        """
        if not khoi:
            return False
        hd["objective"] = ((hd.get("objective") or "").rstrip()
                           + "\n\n" + khoi)
        return True

    def _khoi_web(self, text: str, project_id: str = "") -> str:
        """Khối NỘI DUNG WEB cho nhắc nhở Leader khi câu có URL công khai.

        Router đọc trang HỘ (WebReader) rồi đính bằng chứng — worker/Leader
        headless KHÔNG dùng được `read_url` (bị tự chối quyền). `""` nếu câu
        không có URL. Ghi sự kiện để bảng điều khiển/nghiệm thu thấy.
        """
        try:
            from scripts.control_center.web_reader import rut_url
        except Exception:                                   # noqa: BLE001
            return ""
        urls = rut_url(text or "")
        if not urls:
            return ""
        kqs = self._doc_web_nhieu(urls, toi_da=2)
        if not kqs:
            return ""
        for kq in kqs:
            self.store.ghi_su_kien(
                "WEB_READ", project_id=project_id,
                level="INFO" if kq.ok else "WARNING",
                detail=(f"{kq.url_goc} -> {kq.trang_thai} {kq.content_type} "
                        f"{kq.so_byte}B" if kq.ok else f"{kq.url_goc}: {kq.loi}")[:300],
                meta={"url": kq.url_goc, "url_cuoi": kq.url_cuoi, "ok": kq.ok,
                      "trang_thai": kq.trang_thai, "bam": kq.bam_noi_dung,
                      "nguon": kq.nguon})
        return "\n\n".join(kq.khoi_bang_chung() for kq in kqs)

    def _kem_web_vao_hd(self, text: str, hd: Dict) -> bool:
        """Đính nội dung web (Router đọc) vào MỤC TIÊU một việc worker có URL —
        như `_kem_nhat_ky_git`. Agent headless không đọc được URL; Router đọc
        hộ, quyền agent KHÔNG đổi. Trả `True` nếu có đính."""
        try:
            from scripts.control_center.web_reader import rut_url
        except Exception:                                   # noqa: BLE001
            return False
        urls = rut_url((hd.get("objective") or "") + " " + (text or ""))
        if not urls:
            return False
        kqs = self._doc_web_nhieu(urls, toi_da=2)
        kem = [kq for kq in kqs if kq.ok and kq.van_ban]
        if not kem:
            return False
        khoi = "\n\n".join(kq.khoi_bang_chung() for kq in kem)
        hd["objective"] = (
            (hd.get("objective") or "").rstrip()
            + f"\n\n{self.DAU_WEB} (chỉ đọc, công khai). KHÔNG dùng read_url/lệnh: "
              "phiên headless từ chối quyền và lượt của bạn sẽ kết thúc rỗng — "
              "phân tích NGAY trên nội dung dưới đây.\n" + khoi)
        return True

    def _khoi_toa(self, project_id: str, text: str) -> str:
        """Khối cho nhắc nhở Leader khi câu có cardinality tường minh — để
        `reply` của Leader nói ĐÚNG số việc/số khe mà engine sẽ tạo."""
        from scripts.control_center import toa as TOA
        yc = TOA.xet_toa(text)
        if yc is None:
            return ""
        try:
            self._dam_bao_suc_khoe(f"tính sức chứa cho {yc.so_agent} agent")
        except Exception:                                   # noqa: BLE001
            pass
        with self._khoa:
            dang = len([x for x in self._dang_chay.values() if x.is_alive()])
        try:
            sc = TOA.tinh_suc_chua(self.fabric, yc, max_parallel=self.max_parallel,
                                   dang_chay=dang)
        except Exception:                                   # noqa: BLE001
            return ""
        return ("YÊU CẦU SONG SONG TƯỜNG MINH: người dùng xin "
                f"{yc.so_agent} agent" + (" (mỗi agent một mục)" if yc.moi_agent_mot else "")
                + ". Hệ thống SẼ tự tách thành 1 việc cha + "
                f"{yc.so_agent} việc con độc lập khi bạn trả WORK + delegate_work. "
                + TOA.cau_thong_bao(sc)
                + " Trong `reply` hãy nói đúng các con số này; KHÔNG nói chế độ "
                  "MAX/STRONG thay cho số agent; KHÔNG hứa nhiều hơn số slot khả dụng.")

    # -- buoc dang lam (tien do SONG cho o chat) -----------------------------

    def _dat_buoc(self, project_id: str, nhan: str) -> None:
        """Ghi bước đang làm. `nhan` rỗng = xong, xoá khỏi sổ."""
        with self._khoa:
            if nhan:
                cu = self._buoc.get(project_id)
                # Giu nguyen moc thoi gian cua BUOC DAU: dong ho tren man
                # hinh phai dem tong thoi gian cho, khong reset moi buoc.
                self._buoc[project_id] = (nhan, cu[1] if cu else time.time())
            else:
                self._buoc.pop(project_id, None)

    def buoc_dang_lam(self, project_id: str) -> Optional[Dict]:
        with self._khoa:
            b = self._buoc.get(project_id)
        return {"nhan": b[0], "tu_luc": b[1]} if b else None

    # -- Leader --------------------------------------------------------------

    def leader_ban_ghi(self, project_id: str) -> leader.BanGhiLeader:
        """Danh tính Leader của dự án, tạo mới nếu chưa có. BỀN qua khởi lại."""
        d = self.store.leader(project_id)
        if d is None:
            bg = leader.BanGhiLeader.moi(project_id)
            self.store.luu_leader(bg.to_dict())
            self.store.ghi_su_kien(
                "LEADER_CREATED", project_id=project_id,
                detail=f"{bg.provider}/{bg.model} thread={bg.thread_id}")
            return bg
        return leader.BanGhiLeader(
            project_id=d["project_id"], thread_id=d.get("thread_id", ""),
            che_do=d.get("che_do") or "AUTO",
            provider=d.get("provider") or leader.PROVIDER_LEADER,
            model=d.get("model") or leader.MODEL_LEADER,
            context=d.get("context") or {},
            created_at=d.get("created_at") or time.time(),
            updated_at=d.get("updated_at") or time.time())

    def anh_chup_du_an(self, project_id: str):
        """`AnhChupDuAn` — TẤT ĐỊNH, chỉ đọc sổ + `git`. Không agent nào."""
        from scripts.control_center import snapshot as _snap
        ctx = self.ctx(project_id)
        bg = self.leader_ban_ghi(project_id)
        return _snap.chup(self.store, ctx.project, che_do=bg.che_do,
                          usage=self._usage_neu_do_duoc(project_id))

    def _usage_neu_do_duoc(self, project_id: str) -> Dict:
        """Usage ĐO ĐƯỢC từ sổ của chính Control Center.

        Chỉ lấy phần `cuc_bo()` — phần luôn là ACTUAL vì nó đếm trong sổ
        mình tự ghi. KHÔNG hỏi nhà cung cấp ở đây: một câu "project tới đâu
        rồi?" không được biến thành một lượt gọi CLI, và một nguồn không đo
        được thì phải ở `UNAVAILABLE` chứ không phải `0`.
        """
        try:
            ds = UsageReporter(self.store).cuc_bo(project_id)
        except Exception:                                   # noqa: BLE001
            return {}
        # `value is None` = UNAVAILABLE. Bo han khoi anh chup thay vi dien
        # 0 — `UsageMetric.__post_init__` cam mau thuan do o tang duoi, va
        # anh chup khong duoc pha luat do o tang tren.
        return {m.label: m.value for m in ds if m.value is not None}

    def _khoi_song(self, project_id: str, text: str) -> str:
        """Khối TRẠNG THÁI SỐNG cho nhắc nhở Leader, hoặc `""`.

        Chỉ đo khi câu hỏi ĐÒI trạng thái hiện tại (`xet_cau_hoi`). Đo
        mọi lượt là tự thêm vài giây SSH vào từng tin nhắn — kể cả "viết
        cho tôi bài kiểm này", thứ chẳng cần biết farmer có chạy hay
        không.

        Probe hỏng KHÔNG được làm vỡ lượt chat: khi đó vẫn trả về một
        khối, nhưng khối đó nói rõ là chưa xác minh được và kèm lý do —
        `cau_tu_choi_bia()` viết sẵn hình dạng câu đó.
        """
        from scripts.control_center.observability import (cau_tu_choi_bia,
                                                          tom_tat_cho_leader,
                                                          xet_cau_hoi)
        yc = xet_cau_hoi(text)
        if not yc.can_live:
            return ""
        try:
            a = self.quan_sat.anh_chup(project_id)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "LIVE_PROBE_FAILED", project_id=project_id, level="WARNING",
                detail=f"{type(exc).__name__}: {exc}"[:200])
            return ("TRẠNG THÁI SỐNG: KHÔNG đo được lần này — "
                    f"{type(exc).__name__}: {exc}\n"
                    + cau_tu_choi_bia(0, [str(exc)]))
        van = tom_tat_cho_leader(a)
        self.store.ghi_su_kien(
            "LIVE_PROBE", project_id=project_id,
            detail=(f"{a.trang_thai_chung.value} · bằng chứng sống="
                    f"{a.co_bang_chung_song()}"),
            meta={"dau_hieu": yc.dau_hieu[:6],
                  "nhat_ky": a.nhat_ky_provider})
        if not a.co_bang_chung_song():
            # KHONG mot probe ngoai nao do duoc. Noi thang, va noi luon
            # cau khong duoc bia — de model khong tu dien vao cho trong.
            r = a.router.get("router")
            sv = r.lay("running_tasks") if r else None
            van += "\n\n" + cau_tu_choi_bia(
                int(sv.gia_tri or 0) if sv and sv.gia_tri is not None else 0,
                [k.ly_do or f"{k.khoa}: {k.trang_thai.value}"
                 for k in a.khoi_ngoai()])
        return van

    def _leader_quyet_dinh(self, ctx, text: str):
        """Hỏi Leader. `None` nghĩa là KHÔNG hỏi được — rơi về đường cũ.

        Rơi về đường cũ (phân rã + Router) khi Leader không dùng được là có
        chủ ý: mất Leader thì mất sự tiện, nhưng KHÔNG được mất khả năng
        giao việc. Và mọi lần rơi đều được ghi lại — một sự tiện lặng lẽ
        biến mất là cách một sản phẩm xấu đi mà không ai biết.
        """
        pid = ctx.project.project_id
        if not self.leader_bat and pid not in self._leader_phien:
            return None            # tat -> hanh vi V0.2, tat dinh
        try:
            bg = self.leader_ban_ghi(pid)
            anh = self.anh_chup_du_an(pid)
            ls = [m.to_dict() for m in self.store.chat(pid, limit=40)]
            # V0.5 — CAU HOI VE HIEN TAI THI PHAI DI DO.
            #
            # Truoc ban nay, moi cau deu chi thay `anh_chup_du_an()` (so +
            # git). Nen "production farmer con chay khong?" duoc tra loi
            # bang so viec cua Router, va cau tra loi la SAI.
            khoi_song = self._khoi_song(pid, text)
            # V0.6.1 — CAU HOI LICH SU/KIEN THUC DU AN: tra tu KY UC truoc,
            # dinh kem bang chung L0, va bat `LUAT_LICH_SU` de Leader KHONG
            # dispatch mot worker cho cau hoi ma so da tra loi duoc (khuyet tat
            # nghiem thu tay: "cai vu SSH ... truoc day bi gi" -> AG02 200s).
            la_lich_su, _dh_ls = leader.la_cau_hoi_lich_su(text)
            # V0.6 — KY UC DU AN dat SAU anh chup tinh, kem luat rieng.
            khoi_ky_uc = self._khoi_ky_uc(pid, text, kem_su_kien=la_lich_su)
            khoi_toa = self._khoi_toa(pid, text)
            # V0.6.1 — cau co URL cong khai: Router doc trang HO (WebReader,
            # chi doc, an toan SSRF) va dinh vao nhac nho. Cau don gian "URL
            # nay la gi" -> Leader tra tu day, KHONG dispatch mot worker chi de
            # doc mot trang (agent headless bi tu choi `read_url`).
            khoi_web = self._khoi_web(text, pid)
            # V0.7 — BANG CHUNG VAN HANH: cau hoi chan doan production duoc
            # DO TRUOC, thay vi bien thanh mot viec doi quyen `command`.
            khoi_probe = self._khoi_probe(text, pid)
            # V0.9.1 — TRA CỨU THÀNH PHẦN. Người dùng gọi thành phần bằng tên
            # dân dã ("tool cạo audio"); Router leo thang tra cứu HỘ (ký ức →
            # viên nang → kho → git → tài liệu → lịch sử Router) rồi đính ứng
            # viên CÓ BẰNG CHỨNG. Thiếu khối này, Leader trượt Ký ức rồi hỏi
            # ngược người dùng tên script — đo được ở dogfood thật.
            khoi_tp = self._khoi_thanh_phan(text, pid)
            # V0.7 — VIEN NANG: mo hinh du an GON, nap MOI luot (co cache TTL).
            khoi_nang = self._khoi_vien_nang(pid, text)
            # V0.8 — HOI DONG SUY LUAN. Chay TRUOC luot Leader, vi ket qua cua
            # no la mot khoi du lieu NUA trong nhac nho cua Leader: mot luot,
            # khong phai hai. Cau tam thuong khong goi vai nao va khoi nay rong
            # — xem `reasoning/phan_loai.py` mục CONG TAM THUONG.
            # V0.9 (§16) — KHOI RANG BUOC: quyet dinh dang hieu luc + rang
            # buoc an toan + yeu cau, xep theo THAM QUYEN va co SAN ngan sach
            # rieng trong goi cua moi vai. V0.8 khong dung khoi nay, nen rang
            # buoc phai canh tranh voi lich su du an trong cung mot cuc van
            # ban — do la ly do do duoc cua 2724/3400 o nghiem thu that.
            khoi_rb, gon_rb = self._khoi_rang_buoc(pid)
            khoi_hd = self._khoi_hoi_dong(
                pid, text, bg,
                khoi={"vien_nang": khoi_nang, "ky_uc": khoi_ky_uc,
                      "trang_thai_song": khoi_song,
                      "bang_chung_van_hanh": khoi_probe,
                      "noi_dung_web": khoi_web,
                      "rang_buoc": khoi_rb,
                      "trang_thai_kho": anh.tom_tat()},
                khoi_gon={"rang_buoc": gon_rb})
            nn = leader.dung_nhac_nho(anh, ls, text, khoi_song=khoi_song,
                                      khoi_ky_uc=khoi_ky_uc, khoi_toa=khoi_toa,
                                      la_lich_su=la_lich_su, khoi_web=khoi_web,
                                      khoi_nang=khoi_nang, khoi_probe=khoi_probe,
                                      khoi_hoi_dong=khoi_hd)
            if khoi_tp:
                # Đặt LUẬT ngay trước khối, cùng khuôn `LUAT_LICH_SU`: luật
                # phải đứng cạnh dữ liệu nó nói về, không trôi lên đầu.
                nn = nn + "\n\n" + leader.LUAT_THANH_PHAN + "\n" + khoi_tp
            # Hai buoc RIENG vi chung lech nhau mot bac do lon: mo phien
            # lanh do duoc 67.87s, con mot luot hoi khi da am la 2.40s.
            # Gop chung lai thi thanh tien do noi doi o lan dau tien.
            self._dat_buoc(pid, "đang mở phiên Leader" if pid not in
                           self._leader_phien else "Leader đang suy nghĩ")
            ph = self._phien_leader(pid, bg)
            self._dat_buoc(pid, "Leader đang suy nghĩ")
            van = ph.hoi(nn)
            qd = leader.doc_quyet_dinh(van)
            self.store.ghi_su_kien(
                "LEADER_DECISION", project_id=pid,
                detail=f"{qd.y_dinh}: {[a.loai for a in qd.actions]}",
                meta={"y_dinh": qd.y_dinh, "model": bg.model,
                      "actions": [a.to_dict() for a in qd.actions]})
            return qd
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "LEADER_UNAVAILABLE", project_id=pid, level="WARNING",
                detail=(f"{type(exc).__name__}: {exc}"[:400]
                        + " — rơi về phân rã trực tiếp"))
            return None

    def _khoi_rang_buoc(self, project_id: str) -> Tuple[str, str]:
        """`(bản đầy đủ, bản gọn)` của khối ràng buộc — V0.9 §16.

        Bản GỌN được dựng SẴN ở đây chứ không để `ngu_canh.py` tự cắt: cắt
        một khối văn xuôi làm đôi thì nửa còn lại trông y như một khối đầy
        đủ. Bản gọn của `rang_buoc.KhoiRangBuoc` là một khối hoàn chỉnh
        khác — nó tự NÊU TÊN những mã nó đã lược.

        Hỏng ở đây KHÔNG được làm vỡ lượt chat, cùng nguyên tắc
        `_khoi_ky_uc`: mất khối ràng buộc thì phản biện kém đi, không phải
        cả cuộc trò chuyện hỏng.
        """
        try:
            from scripts.control_center.reasoning import rang_buoc as RB
            from scripts.control_center.reasoning.ngu_canh import san_cua
            from scripts.control_center.reasoning.vai import VaiTro, ho_so
            k = RB.dung_khoi(self.ky_uc, project_id)
            if k.rong:
                return "", ""
            day, _ = k.render()
            # San CHAT NHAT trong ba vai — mot ban gon vua san hep nhat thi
            # vua moi san.
            hep = min(san_cua(v, "rang_buoc", ho_so(v).tran_token_ngu_canh)
                      for v in (VaiTro.LEADER, VaiTro.STRATEGIST,
                                VaiTro.REVIEWER))
            gon, _luoc = k.render(tran_token=hep)
            return day, gon
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "CONSTRAINT_BLOCK_ERROR", project_id=project_id,
                level="WARNING",
                detail=f"khối ràng buộc: {type(exc).__name__}: {exc}"[:300])
            return "", ""

    def _khoi_hoi_dong(self, project_id: str, text: str, bg,
                       khoi: Dict[str, str],
                       khoi_gon: Optional[Dict[str, str]] = None) -> str:
        """Chạy hội đồng suy luận và trả KHỐI cho nhắc nhở Leader, hoặc `""`.

        Ba tính chất, mỗi cái ứng với một chế độ hỏng thật:

        * **Lượt tầm thường không tốn gì.** `phan_loai_luot` chạy trong vài
          chục micro-giây và cổng tầm thường trả về ngay — "ê bro" không
          chạm tới fabric, không dựng `Scheduler`, không thêm một token nào
          vào nhắc nhở của Leader.
        * **Hỏng ở đây KHÔNG được làm vỡ lượt chat.** Mất hội đồng thì mất
          chiều sâu; Leader vẫn trả lời. Cùng nguyên tắc `_khoi_ky_uc`.
        * **KHÔNG tạo việc** (§11). Hàm này chỉ trả về văn bản.
        """
        from scripts.control_center.reasoning.phan_loai import (
            lap_ke_hoach_vai, phan_loai_luot)

        try:
            pl = phan_loai_luot(text)
            cd = bg.che_do_enum()
            kh = lap_ke_hoach_vai(pl, cd)
            if not kh.co_strategist:
                # KHONG cham `self.hoi_dong` o nhanh nay, va do la ca diem:
                # property do dung fabric + mot `Scheduler` cho moi (vai, che
                # do). Mot cau chao khong duoc tra gia cho thu no khong dung.
                #
                # Van ghi nguon goc lai — mot lan KHONG leo thang cung phai
                # giai thich duoc, khong thi nguoi dung chi thay im lang.
                with self._khoa:
                    self._nguon_goc_suy_luan[project_id] = {
                        "phan_loai": pl.to_dict(), "ke_hoach": kh.to_dict(),
                        "nguon_goc": [], "so": {"che_do": cd.value,
                                                "ban_ghi": [], "tong_giay": None},
                        "da_chay": False, "suy_giam": False, "loi": [],
                        "dong_nguon_goc": [
                            f"{cd.value}  [{pl.bac.value}/{pl.tac_dong.value}]  "
                            f"{kh.ly_do}",
                            "Leader      (một mình — không gọi vai suy luận nào)"],
                        "ts": time.time()}
                return ""
            # DO SUC KHOE TRUOC KHI CAN MOT PLACEMENT — cung khuon `_san_sang`.
            #
            # Khong co dong nay thi tren duong mac dinh (`probe=False`) moi
            # runtime nam o OFFLINE, `Scheduler` loai sach 51 ung vien, va
            # hoi dong bao `KHONG_CO_CHO` cho MOI cau hoi kho — dung khuyet
            # tat ma `_lan_do_cuoi` da ghi lai cho duong giao viec, lap lai
            # nguyen ven o mot cua moi. Do that o ban nghiem thu dau tien.
            self._dam_bao_suc_khoe("hội đồng suy luận")
            self._dat_buoc(project_id, "hội đồng suy luận đang chạy "
                           f"({', '.join(v.nhan for v in kh.vai if v.value != 'leader')})")
            kq = self.hoi_dong.chay(
                cau=text, phan_loai=pl, che_do=cd,
                khoi_san_co={k: v for k, v in (khoi or {}).items() if v},
                nguon_khoi={"rang_buoc": "ký ức dự án — quyết định/ràng buộc "
                                         "đang hiệu lực (V0.9)",
                            "vien_nang": "viên nang dự án (V0.7)",
                            "ky_uc": "ký ức dự án (V0.6)",
                            "trang_thai_song": "probe sống (V0.5)",
                            "bang_chung_van_hanh": "ProductionProbeBroker (V0.7)",
                            "trang_thai_kho": "git + sổ Control Center"},
                khoi_gon={k: v for k, v in (khoi_gon or {}).items() if v},
                chinh_sach=self.chinh_sach_cao_cap(project_id),
                project_id=project_id)
            with self._khoa:
                self._nguon_goc_suy_luan[project_id] = {
                    **kq.to_dict(), "ts": time.time()}
            return kq.khoi_leader()
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "REASONING_ERROR", project_id=project_id, level="WARNING",
                detail=f"hội đồng suy luận: {type(exc).__name__}: {exc}"[:300])
            return ""

    def _phien_leader(self, project_id: str, bg):
        with self._khoa_leader:
            ph = self._leader_phien.get(project_id)
            if ph is None:
                # Tra BAC tu fabric, khong chi dua ten cho `PhienLeader`:
                # chan Astra theo ten la mot chot chuoi, con theo bac thi
                # chan duoc ca mot model cao cap mang ten khac.
                bac = 0
                try:
                    m = self.fabric.models.get(bg.model)
                    bac = int(getattr(m, "premium_tier", 0) or 0)
                except Exception:                           # noqa: BLE001
                    bac = 0
                ph = leader.PhienLeader(model=bg.model, premium_tier=bac)
                self._leader_phien[project_id] = ph
                # Leader va worker dung CUNG be tai khoan AG (mac dinh AG01).
                # Cho Leader chiem phai HIEN ra voi bo lap lich — xem
                # `leader.chiem_cho_fabric`. Tra lai o `shutdown`.
                try:
                    leader.chiem_cho_fabric(self.fabric, ph.runtime_id,
                                            f"LEADER:{project_id}")
                except Exception:                           # noqa: BLE001
                    pass
            return ph

    def _leader_khong_uy_thac(self, ctx, qd, tin, dk_hop_le) -> Dict:
        """CHAT / STATUS / CONTROL — trả lời, có thể điều khiển, KHÔNG tạo việc."""
        pid = ctx.project.project_id
        ket: List[Dict] = []
        de_xuat: List[Dict] = []
        for a in qd.actions:
            if a.loai in leader.HANH_DONG_TU_CHAY:
                ket.append(self._chay_dieu_khien(pid, a))
            elif a.loai in leader.HANH_DONG_DE_XUAT:
                # KHONG tu chay. Xem `HANH_DONG_TU_CHAY` cho ly do day du:
                # van ban di vao ngu canh Leader khong hoan toan do nguoi
                # dung viet, nen mot hanh dong pha huy hoac mo cong bao mat
                # phai co NGUOI bam.
                de_xuat.append({"loai": a.loai,
                                "task_id": str(a.tham_so.get("task_id") or "")})
                self.store.ghi_su_kien(
                    "LEADER_DE_XUAT", project_id=pid,
                    task_id=str(a.tham_so.get("task_id") or ""),
                    level="WARNING",
                    detail=(f"Leader đề xuất {a.loai} — KHÔNG tự chạy, cần "
                            f"người bấm"))
        loi = qd.reply
        for k in ket:
            if k.get("loi"):
                loi += f"\n\n(!) {k['loi']}"
            elif k.get("ok"):
                loi += f"\n\n✓ {k['ok']}"
        for d in de_xuat:
            nhan = {"approve_gate": "DUYỆT CỔNG", "cancel_task": "HUỶ",
                    "reassign_task": "GIAO LẠI"}.get(d["loai"], d["loai"])
            loi += (f"\n\n⚠ Mình **không tự** {nhan} được — việc này cần "
                    f"bạn bấm. Mở `{d['task_id']}` ở tab Tasks rồi xác nhận.")
        t2 = self.store.them_chat(pid, "assistant", loi,
                                  meta={"leader": qd.to_dict(),
                                        "loai": qd.y_dinh.lower(),
                                        "ket_qua_dieu_khien": ket,
                                        "attachment_ids": list(dk_hop_le)})
        # V0.9 (§1) — LUU DE XUAT, KHONG chay no. Day la mot cau THAO LUAN
        # (`_leader_khong_uy_thac` chi vao khi y dinh KHAC `WORK`), nen viec
        # duy nhat ta lam them la ghi nho lai loi khuyen de lan sau nguoi
        # dung noi "ok lam di" thi khong phai nhac lai ca ke hoach.
        ma_dx = None
        try:
            ma_dx = self._luu_de_xuat(pid, t2.message_id)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "RECOMMENDATION_SAVE_ERROR", project_id=pid, level="WARNING",
                detail=f"{type(exc).__name__}: {exc}"[:200])
        return {"reply": loi, "tasks": [], "plan": None,
                "message_id": tin.message_id,
                "attachment_ids": list(dk_hop_le),
                "leader": qd.to_dict(), "control": ket, "de_xuat": ma_dx,
                "assistant_message_id": t2.message_id}

    def _bao_ket_qua_ve_chat(self, ctx, task_id: str) -> Optional[Dict]:
        """Việc kết thúc -> MỘT tin nhắn assistant trong đúng hội thoại đó.

        Ba tính chất phải giữ, và mỗi cái ứng với một chế độ hỏng thật:

        * **Đúng một lần.** Vòng lặp điều phối có thể thấy lại một việc đã
          kết thúc; báo hai lần thì người dùng đọc hai lần cùng một kết
          quả và không biết cái nào mới.
        * **Đúng hội thoại.** `project_id` lấy từ CHÍNH việc đó, không lấy
          từ ngữ cảnh đang mở — một kết quả rơi nhầm vào hội thoại khác là
          lỗi tệ hơn cả không báo.
        * **Chưa xong thì chưa báo.** Việc còn được xếp lại để thử tiếp thì
          chưa phải kết quả cuối.
        """
        t = self.store.task(task_id)
        if t is None:
            return None
        tt = t.state.value if hasattr(t.state, "value") else str(t.state)
        if tt not in ("DONE", "FAILED", "BLOCKED"):
            return None            # con dang chay / da duoc xep lai
        # KHOA THEO `(task_id, state)`, va no BEN tren dia.
        #
        # Theo ma viec thoi thi mot viec GATED (`BLOCKED` -> nguoi duyet ->
        # `DONE`) se bi lan `BLOCKED` chiem cho, va ket qua `DONE` THAT
        # khong bao gio toi duoc o chat. Ben tren dia vi bo nho trong rong
        # sau moi lan khoi dong lai.
        # NGUYEN TU giua cac luong: kiem "da bao" + ghi tin + ghi dau trong
        # MOT khoa. Xem `_khoa_bao` o `__init__`.
        with self._khoa_bao:
            if self.store.da_bao_ket_qua(task_id, tt):
                return None

            # Con cua mot lan TOA: ket qua DONE/FAILED di vao TONG HOP cua
            # cha, khong rai N tin nhan rieng. BLOCKED van bao rieng — no can
            # nguoi.
            toa = (t.contract or {}).get("_toa") or {}
            if toa and not toa.get("cha") and tt in ("DONE", "FAILED"):
                self.store.ghi_da_bao_ket_qua(task_id, tt, project_id=t.project_id,
                                              message_id=0)
                return None

            # V0.9 — BUOC cua mot lan thuc thi: ket qua di vao KIEM DINH roi
            # vao MOT cau tong hop cua ca lan thuc thi (§21), khong rai N tin
            # nhan. `BLOCKED` van bao rieng: no can nguoi, va cau tong hop co
            # the con lau moi toi.
            tx = (t.contract or {}).get("_thuc_thi") or {}
            if tx.get("execution_id") and tt in ("DONE", "FAILED"):
                self.store.ghi_da_bao_ket_qua(task_id, tt,
                                              project_id=t.project_id,
                                              message_id=0)
                return None

            pb = ((t.result or {}).get("envelope") or {}) if t.result else {}
            van = self._soan_ket_qua(t, tt, pb)
            # GHI TRUOC, DANH DAU SAU. Danh dau truoc roi `them_chat` nem (dia
            # day, so hong) thi ket qua mat vinh vien — dau da danh, chat thi
            # rong.
            #
            # `t.project_id`, KHONG phai `ctx` — xem docstring.
            tin = self.store.them_chat(
                t.project_id, "assistant", van,
                meta={"loai": "ket_qua", "task_id": task_id, "state": tt,
                      "worker": pb.get("worker"), "model": pb.get("model"),
                      "provider": pb.get("provider"),
                      "duration": pb.get("duration"),
                      "raw_log_ref": pb.get("raw_log_ref"),
                      "failure_reason": pb.get("failure_reason") or ""})
            self.store.ghi_da_bao_ket_qua(task_id, tt,
                                          project_id=t.project_id,
                                          message_id=tin.message_id)
        self.store.ghi_su_kien(
            "RESULT_TO_CHAT", project_id=t.project_id, task_id=task_id,
            detail=f"{tt} -> tin nhắn #{tin.message_id}")
        return {"message_id": tin.message_id, "text": van}

    def _quet_ket_qua_chua_bao(self) -> int:
        """Việc đã KẾT THÚC mà chưa có câu trả lời nào trong chat -> báo.

        Lưới an toàn cho **mọi** đường kết thúc, không chỉ đường điều phối
        bình thường. Đã vấp thật ở nghiệm thu V0.3: người dùng bấm Dừng,
        việc sang `FAILED` qua `stop()` — một đường KHÔNG đi qua chỗ báo
        kết quả — và ô chat im lặng. Đúng cái "huy hiệu FAILED không lời
        giải thích" mà V0.3 sinh ra để bỏ.

        Cũng che luôn trường hợp tắt máy giữa chừng: lần mở sau, việc đã
        kết thúc vẫn được thuật lại đúng một lần (`_da_bao_roi` đọc bảng
        chat nên nó bền qua khởi động lại).

        Chỉ xét việc kết thúc GẦN ĐÂY — quét cả lịch sử mỗi nhịp là một
        phép O(n) vô ích trên một cái sổ chạy hàng tuần.
        """
        n, bay_gio = 0, time.time()
        for p in self.projects():
            for t in self.store.tasks(p.project_id):
                tt = t.state.value if hasattr(t.state, "value") else str(t.state)
                if tt not in ("DONE", "FAILED", "BLOCKED"):
                    continue
                # MOC THOI GIAN: `ended_at` la 0 voi mot viec GATED duoc
                # tao THANG o `BLOCKED` (khong qua `doi_trang_thai`). Dung
                # `if t.ended_at and …` thi 0 la falsy va chot tuoi khong
                # chan duoc gi — mo app sau mot tuan se do lai moi viec
                # BLOCKED cu vao hoi thoai nhu tin moi.
                moc = t.ended_at or t.updated_at or t.created_at or bay_gio
                if (bay_gio - moc) > TRAN_QUET_KET_QUA:
                    continue
                # CHO LANG cho FAILED: duong dieu phoi ghi `FAILED` xuong
                # so TRUOC khi `_thu_lai_neu_dang` xep viec lai. Nhip 1.0s
                # roi dung vao cua so do se bao "❌ Hỏng" cho mot viec sap
                # duoc thu lai — mot cau tra loi SAI gui cho nguoi dung.
                #
                # Duong dieu phoi tu bao ngay sau khi da quyet dinh thu
                # lai, nen phep quet nay chi la luoi an toan; cho vai giay
                # khong lam mat gi.
                if tt == "FAILED" and (bay_gio - moc) < CHO_LANG_KET_QUA:
                    continue
                try:
                    if self._bao_ket_qua_ve_chat(self.ctx(p.project_id),
                                                 t.task_id):
                        n += 1
                except Exception:                           # noqa: BLE001
                    pass
        return n

    @staticmethod
    def _soan_ket_qua(t, tt: str, pb: Dict) -> str:
        """Câu người dùng đọc. Ngắn, cụ thể, không phải bãi nhật ký."""
        d = []
        if tt == "DONE":
            d.append(f"✅ Xong: {t.title}")
        elif tt == "BLOCKED":
            d.append(f"⛔ Bị chặn: {t.title}")
        else:
            d.append(f"❌ Hỏng: {t.title}")

        tom = str(pb.get("summary") or "").strip()
        if tom:
            d += ["", tom]
        elif tt == "DONE":
            d += ["", "(worker không để lại tóm tắt nào — xem Chi tiết việc.)"]

        if tt != "DONE":
            ly = str(pb.get("failure_reason") or "").strip()
            if ly:
                d += ["", f"Lý do: `{ly}`"]
            if t.blocked_reason:
                d += ["", f"Cần bạn quyết: {t.blocked_reason}"]

        ch = list(pb.get("changes") or [])
        if ch:
            d += ["", "Tệp đã đổi:"] + [f"  • {c}" for c in ch[:12]]
            if len(ch) > 12:
                d.append(f"  … và {len(ch) - 12} tệp nữa")
        for nhan, khoa in (("Phát hiện", "findings"), ("Rủi ro", "risks"),
                           ("Việc tiếp", "followups")):
            v = [str(x) for x in (pb.get(khoa) or [])][:5]
            if v:
                d += ["", f"{nhan}:"] + [f"  • {x[:200]}" for x in v]
        te = pb.get("tests") or {}
        if isinstance(te, dict) and (te.get("passed") or te.get("failed")):
            d += ["", f"Test: {te.get('passed', 0)} đạt / "
                      f"{te.get('failed', 0)} hỏng"]
        if pb.get("commit"):
            d += ["", f"Commit: `{pb['commit']}`"]

        cho = []
        if pb.get("worker"):
            cho.append(f"{pb['worker']}/{pb.get('model') or '?'}")
        if pb.get("duration"):
            cho.append(f"{float(pb['duration']):.0f}s")
        if cho:
            d += ["", f"_({' · '.join(cho)} · `{t.task_id}`)_"]
        return "\n".join(d)

    def _chay_dieu_khien(self, project_id: str, a) -> Dict:
        """Thực hiện MỘT hành động điều khiển. Fail closed, có dấu vết."""
        if a.loai == "record_memory":
            # V0.6.1 — Leader de nghi ghi mot ky uc noi len tu hoi thoai.
            # Chi cham SO KY UC; `tin_cay=leader`; co dau vet.
            if self._ky_uc is None:
                return {"loi": "ký ức không sẵn — không ghi được"}
            loai = str(a.tham_so.get("loai") or "fact").lower()
            nd = str(a.tham_so.get("noi_dung") or "").strip()
            if not nd:
                return {"loi": "record_memory thiếu nội dung"}
            try:
                if loai == "decision":
                    r = self._ky_uc.ghi_quyet_dinh(
                        project_id, nd, ly_do=str(a.tham_so.get("ly_do") or ""),
                        tieu_de=str(a.tham_so.get("tieu_de") or ""),
                        thay_the_cho=[str(x) for x in (a.tham_so.get("thay_the_cho") or [])],
                        ai="leader", tin_cay="leader")
                else:
                    r = self._ky_uc.ghi_ky_uc(
                        project_id, loai, nd, tieu_de=str(a.tham_so.get("tieu_de") or ""),
                        quan_trong=6, ai="leader", tin_cay="leader", nguon_loai="leader")
            except Exception as exc:                        # noqa: BLE001
                return {"loi": f"record_memory: {type(exc).__name__}: {exc}"[:300]}
            if not r or r.get("loi"):
                return {"loi": f"record_memory: {(r or {}).get('loi', 'không ghi được')}"}
            return {"ok": f"đã ghi {loai} {r.get('ma', '')} (nguồn: Leader)"}
        tid = str(a.tham_so.get("task_id") or "")
        t = self.store.task(tid)
        if t is None or t.project_id != project_id:
            return {"loi": f"không có việc {tid!r} trong dự án này"}
        try:
            if a.loai == "pause_task":
                self.pause(tid, reason="Leader (người dùng yêu cầu)")
                return {"ok": f"đã tạm dừng {tid}"}
            if a.loai == "resume_task":
                self.resume(tid)
                return {"ok": f"đã cho chạy tiếp {tid}"}
            # `cancel_task` / `reassign_task` / `approve_gate` KHONG o day,
            # va do khong phai bo sot — xem `leader.HANH_DONG_TU_CHAY`.
            # Chung la DE XUAT; nguoi bam. Dac biet `approve_gate`: de
            # Leader goi `mo_khoa_gated` la pha dung bat bien ma docstring
            # cua chinh ham do tuyen bo.
            if a.loai in leader.HANH_DONG_DE_XUAT:
                return {"loi": f"{a.loai} cần người bấm, Leader không tự chạy"}
        except Exception as exc:                            # noqa: BLE001
            return {"loi": f"{a.loai} {tid}: {type(exc).__name__}: {exc}"[:300]}
        return {"loi": f"hành động {a.loai!r} chưa nối"}

    @staticmethod
    def _hop_dong_dict(pt: PlannedTask, project_id: str) -> Dict:
        """Hợp đồng đã gắn `task_id` có tiền tố dự án + phong bì quyền.

        Phong bì được RENDER VÀO mục tiêu, không chỉ lưu bên cạnh: agent
        phải đọc được ranh giới của nó trong đúng văn bản nó nhận. Một
        trường JSON mà agent không bao giờ thấy thì không phải là một rào.
        """
        d = pt.contract.to_dict()
        d["task_id"] = f"{project_id}.{pt.task_id}"
        d["dependencies"] = [f"{project_id}.{x}" for x in pt.dependencies]
        d["objective"] = (pt.objective + "\n\n" +
                          pt.envelope.render_for_agent())
        d["_permission"] = pt.envelope.to_dict()
        return d

    def mo_khoa_gated(self, task_id: str, *, approved_by: str = "user",
                      note: str = "") -> Task:
        """Người dùng cho phép một việc GATED chạy. CHỈ người mới gọi được.

        Không có đường tự động nào tới hàm này. Nó tồn tại để việc mở cổng
        là một hành vi CÓ DẤU VẾT: ai duyệt, lúc nào, với ghi chú gì.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if t.permission != PermissionClass.GATED.value:
            return t
        # GHI DAU DUYET LEN CHINH VIEC, khong chi vao nhat ky su kien.
        #
        # Mot su kien la thu doc lai duoc, khong phai thu KIEM duoc luc lap
        # lich. Bo lap lich can tra loi "viec nay da duoc duyet chua" bang
        # mot phep doc re, ngay tren hang cua no — xem `_da_duyet_cong`.
        hd = dict(t.contract or {})
        pq = dict(hd.get("_permission") or {})
        pq["approved_by"] = str(approved_by)[:80]
        pq["approved_at"] = time.time()
        pq["approval_note"] = str(note)[:300]
        hd["_permission"] = pq
        t.contract = hd
        self.store.luu_task(t)

        self.store.ghi_su_kien(
            "GATE_APPROVED", project_id=t.project_id, task_id=task_id,
            level="ALERT",
            detail=f"người dùng ({approved_by}) mở cổng: {t.gate_reason}",
            meta={"approved_by": approved_by, "note": note,
                  "gate_reason": t.gate_reason})
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="người dùng đã duyệt cổng")

    @staticmethod
    def _da_duyet_cong(t: Task) -> bool:
        """Việc GATED này đã được NGƯỜI duyệt chưa.

        Việc không GATED thì luôn `True` — không có cổng nào để duyệt.
        """
        if t.permission != PermissionClass.GATED.value:
            return True
        pq = (t.contract or {}).get("_permission") or {}
        return bool(pq.get("approved_by"))

    # -- 2b. VONG KIN THUC THI (V0.9) ---------------------------------------

    def dieu_phoi(self, project_id: str) -> DP.BoDieuPhoi:
        """Bộ điều phối của MỘT dự án. Dựng muộn, giữ lại.

        Một bộ mỗi dự án chứ không một bộ dùng chung: `MoiGioiKiem` phải neo
        vào ĐÚNG kho của dự án đó, và một môi giới dùng chung sẽ chạy `git
        status` của kho A để kiểm định một bước của kho B.
        """
        with self._khoa_thuc_thi:
            bd = self._dieu_phoi.get(project_id)
            if bd is not None:
                return bd
            p = self.store.project(project_id)
            mg = None
            if p is not None and p.repo_path:
                try:
                    mg = EKD.MoiGioiKiem(p.repo_path)
                except Exception:                           # noqa: BLE001
                    mg = None
            bd = DP.BoDieuPhoi(
                self.so_thuc_thi,
                tao_viec=self._tao_viec_cho_buoc,
                trang_thai_viec=self._trang_thai_viec,
                dung_viec=self._dung_viec_cua_thuc_thi,
                nha_tai_nguyen=lambda pid, tid: LockManager(self.store).tra(
                    pid, tid),
                moi_gioi=mg, goi_phan_bien=self._phan_bien_ket_qua,
                song_song=self.max_parallel)
            self._dieu_phoi[project_id] = bd
            return bd

    def _trang_thai_viec(self, task_id: str) -> str:
        t = self.store.task(task_id)
        return t.state.value if t is not None else ""

    def _phan_bien_ket_qua(self, y, kh, bc) -> Optional[Dict]:
        """Gọi Reviewer NGỮ NGHĨA trên một kết quả đã chạy — V0.9 §A.

        Bộ điều phối đã quyết ĐỊNH CÓ GỌI HAY KHÔNG (`nen_goi_reviewer`);
        hàm này chỉ lo chạy. Ba điều nó phải làm đúng:

        1. **Đưa BẰNG CHỨNG, không đưa lời khai.** Khối gửi Reviewer là mục
           tiêu gốc + tiêu chí nghiệm thu + phán quyết từng phép kiểm tất
           định + tệp đã đổi. Không có tóm tắt tự khen của worker.
        2. **ĐỘC LẬP THẬT.** `ho_tac_gia` là họ model ĐÃ LÀM VIỆC, lấy từ
           chính hợp đồng kết quả. Không truyền thì `doi_doc_lap=True` không
           có gì để tránh và "độc lập" thành một nhãn dán.
        3. **Hỏng thì trả `None`.** Mất Reviewer là SUY GIẢM, và bộ điều phối
           nói ra điều đó — không phải một lần kiểm định bị vỡ.
        """
        from scripts.control_center.reasoning.phan_loai import phan_loai_luot
        pid = y.project_id
        try:
            hd = self.hoi_dong
        except Exception:                                   # noqa: BLE001
            return None
        if hd is None:
            return None

        # HO MODEL DA LAM VIEC — de bo dinh tuyen tranh dung ho do.
        ho = ""
        tep: List[str] = []
        for st in self.so_thuc_thi.buoc(y.execution_id, kh.phien_ban):
            d = st.get("ket_qua") or {}
            tep += list(d.get("files_changed") or ())
            if not ho and d.get("model"):
                try:
                    m = self.fabric.models.get(str(d.get("model")))
                    ho = str(getattr(m, "model_family", "") or "")
                except Exception:                           # noqa: BLE001
                    ho = ""

        # GOI TIN CO NHAN NGUON GOC.
        #
        # Ban truoc tron ba loai noi dung vao mot danh sach phang, va Reviewer
        # da chi ra dung cho do (`ex_181f8dd29fbe`): no che dong
        # "BƯỚC CHƯA CHỨNG MINH: (không)" mau thuan voi dong
        # "[THIEU_BANG_CHUNG] <tieu chi ngu nghia>" ngay ben tren. Ca hai deu
        # do ROUTER sinh, va ca hai deu dung theo nghia rieng cua chung — "khong
        # buoc nao thieu bang chung" va "mot TIEU CHI thieu bang chung" — nhung
        # khong co nhan nguon goc thi chung doc nhu mot loi khai tu mau thuan
        # cua agent. Reviewer cham cai mau thuan do cho AGENT, va mot lan chay
        # dung bi danh REVISE.
        #
        # Nen: tach MUC ro rang, noi thang muc nao do AI sinh, va khong bao gio
        # dat van ban cua Router canh van ban cua worker nhu the chung cung
        # loai.
        ngu = [t.mo_ta for t in kh.nghiem_thu
               if not any(c.tat_dinh for c, _ in t.cach_kiem)]
        d = ["=== MỤC TIÊU GỐC (NGƯỜI DÙNG viết) ===", y.goal, "",
             "=== TIÊU CHÍ NGHIỆM THU (siêu dữ liệu của KẾ HOẠCH) ==="]
        d += [f"  [{i + 1}] {'BẮT BUỘC' if t.bat_buoc else 'NÊN CÓ'} · "
              f"{'NGỮ NGHĨA' if t.mo_ta in ngu else 'TẤT ĐỊNH'} · {t.mo_ta}"
              for i, t in enumerate(kh.nghiem_thu)] or \
             ["  (kế hoạch không khai tiêu chí nào)"]
        d += ["",
              "=== HIỆN VẬT DO AGENT TẠO (worker-produced) ===",
              f"  tệp đã đổi ({len(set(tep))}): "
              f"{', '.join(sorted(set(tep))[:25]) or '(không)'}",
              "",
              "=== BẰNG CHỨNG THỰC THI (MÁY đo, không phải lời khai) ==="]
        for t in bc.tieu_chi:
            d.append(f"  [{t.trang_thai.value}] {t.mo_ta}"
                     + ("" if t.bat_buoc else "  (nên có)"))
            for k in t.kiem[:4]:
                goc = (f" @ {Path(k.nguon).name}" if getattr(k, "nguon", "")
                       else "")
                d.append(f"      {'✓' if k.dat else '✗'} {k.cach}: "
                         f"{k.chi_tiet[:160]}{goc}")
            if not t.kiem:
                d.append("      (không có phép kiểm tất định nào — tiêu chí "
                         "này CHỜ CHÍNH BẠN phán đoán)")
        d += ["",
              "=== SIÊU DỮ LIỆU CỦA ROUTER (do Router sinh, KHÔNG phải lời "
              "khai của agent) ===",
              f"  bước đã qua kiểm định: {', '.join(bc.buoc_dat) or '(không)'}",
              f"  bước chưa chứng minh được: "
              f"{', '.join(bc.buoc_thieu_bang_chung) or '(không)'}"]
        if ngu:
            # NOI RO vi sao hai dong tren KHONG mau thuan voi cac dong
            # `[THIEU_BANG_CHUNG]` o muc bang chung.
            d.append("  lưu ý: 'bước' và 'tiêu chí' là HAI thứ khác nhau — "
                     "mọi BƯỚC có thể đã chứng minh xong trong khi một TIÊU "
                     "CHÍ ngữ nghĩa vẫn chờ bạn chấm. Hai dòng trên nói về "
                     "BƯỚC.")
        d += ["", "=== CÂU HỎI CHO BẠN ===",
              "Công việc trên có THỰC SỰ đạt mục tiêu gốc không?",
              "Chấm theo TIÊU CHÍ ở trên. Nếu lời chê của bạn nhắm vào chính "
              "các mục 'SIÊU DỮ LIỆU CỦA ROUTER' (cách Router trình bày), "
              "hãy nói rõ — đó là lỗi của Router, không phải của agent."]

        khoi_rb, gon_rb = self._khoi_rang_buoc(pid)
        try:
            self._dam_bao_suc_khoe("phản biện ngữ nghĩa kết quả")
            ban, ng = hd.phan_bien_ket_qua(
                cau=y.goal, ban_ket_qua="\n".join(d),
                phan_loai=phan_loai_luot(y.goal),
                che_do=self.leader_ban_ghi(pid).che_do_enum(),
                khoi_san_co={"rang_buoc": khoi_rb,
                             "vien_nang": self._khoi_vien_nang(pid, y.goal)},
                khoi_gon={"rang_buoc": gon_rb},
                ho_tac_gia=ho, chinh_sach=self.chinh_sach_cao_cap(pid),
                project_id=pid)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "REVIEW_ERROR", project_id=pid, level="WARNING",
                detail=f"{type(exc).__name__}: {exc}"[:300])
            return None
        if ban is None:
            return None
        chon = ng.chon
        return {"phan_xu": ban.phan_xu.value,
                "doc_lap": bool(chon.doc_lap) if chon else False,
                "suy_giam": bool(chon.suy_giam) if chon else True,
                "provider": (chon.provider if chon else ""),
                "model": (chon.model_id if chon else ""),
                "ho_model": (chon.model_family if chon else ""),
                "ho_tac_gia": ho,
                "ly_do": ban.to_khoi_leader()[:1500]}

    def _dung_viec_cua_thuc_thi(self, task_id: str, ly_do: str) -> None:
        """Dừng một việc con THAY MẶT tầng bước — và CẤM tầng việc thử lại nó.

        HAI TẦNG CÙNG THỬ LẠI MỘT VIỆC LÀ MỘT LỖI KIẾN TRÚC, và nó đã khoá
        chết một lần thực thi thật (đo 2026-09-11):

            tầng BƯỚC bỏ lượt cũ, giao lượt mới   (§9 — nó sở hữu vòng phục hồi)
            tầng VIỆC thấy việc cũ `FAILED` và
              tự đưa về `QUEUED` (`_thu_lai_neu_dang`)
            -> hai việc cùng xin khoá ghi `web`
            -> cả hai nằm `WAITING`, `in_flight` rỗng, đứng im vĩnh viễn

        Không tầng nào sai một mình; cái sai là cả hai cùng chủ động. Tầng
        bước là tầng biết về kế hoạch, tiêu chí nghiệm thu và trần §9, nên
        nó thắng — và cách nói điều đó cho tầng việc là làm cạn lượt thử của
        việc bị bỏ. `_thu_lai_neu_dang` đọc đúng con số đó rồi dừng.
        """
        t = self.store.task(task_id)
        if t is not None and t.attempts < MAX_ATTEMPTS:
            t.attempts = MAX_ATTEMPTS
            self.store.luu_task(t)
            self.store.ghi_su_kien(
                "TASK_ABANDONED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=("tầng thực thi bỏ việc này; cạn lượt thử để tầng việc "
                        f"KHÔNG tự chạy lại — {ly_do}")[:300])
        self.stop(task_id, reason=ly_do)

    def _tao_viec_cho_buoc(self, y: EYD.YDinhThucThi, b: EKH.BuocKeHoach,
                           lan: int, phien_ban: int = 1) -> str:
        """Một BƯỚC kế hoạch -> một `Task` thật của Router V4.

        Đi qua ĐÚNG những rào mà `_chat` đã đi: `permissions.envelope_for`
        quét cả mục tiêu bước lẫn câu gốc người dùng, và một bước chạm lớp
        GATED vào thẳng `BLOCKED`. Bước đó KHÔNG BAO GIỜ được `QUEUED` chỉ
        vì lần thực thi cha đã được duyệt — cổng của lần thực thi và cổng
        của một việc là hai cổng khác nhau.
        """
        from scripts.control_center import permissions as PERM
        pid = y.project_id
        ctx = self.ctx(pid)
        # PHẠM VI GHI CHỈ TỒN TẠI CHO BƯỚC GHI.
        #
        # Bước CHỈ ĐỌC phải có phạm vi RỖNG: `RulePlanner._hop_dong` suy
        # `chi_doc = kind in _CHI_DOC or not scope`, nên một phạm vi mặc định
        # không rỗng đủ để biến một bước đọc thành một việc đòi `repo_write`
        # + worktree, và rồi cổng `diff` đánh hỏng nó vì "không tệp nào đổi".
        # Bản đầu viết `scope if b.ghi else scope` — một phép chọn vô nghĩa
        # do gõ nhầm, và nó che đúng lỗi này.
        scope: Tuple[str, ...] = ()
        if b.ghi:
            scope = tuple(x for _k, x, m in b.tai_nguyen if m == "write") or \
                self._scope_mac_dinh(ctx.project)
        # MÃ VIỆC MANG CẢ BẢN KẾ HOẠCH. Không mang thì lượt đầu của bản v2
        # trùng mã với bản v1, `luu_task` ghi đè một việc đã kết thúc về
        # `QUEUED`, và lịch sử của bản trước biến mất — đúng thứ §10 tồn tại
        # để giữ.
        tid = (f"{pid}.{b.buoc_id}"
               + (f"-v{phien_ban}" if int(phien_ban or 1) > 1 else "")
               + (f"-r{lan}" if lan else ""))
        pb = PERM.envelope_for(tid, objective=b.muc_tieu,
                               intent=y.nguon_cau_nguoi_dung or y.goal,
                               owned_scope=scope if b.ghi else ())
        hd = ctx.planner._hop_dong(                         # noqa: SLF001
            tid, b.muc_tieu, _loai_viec_cua(b), scope,
            cau_goc=y.nguon_cau_nguoi_dung or y.goal, deps=())
        d = hd.to_dict()
        d["task_id"] = tid
        d["objective"] = b.muc_tieu + "\n\n" + pb.render_for_agent()
        d["_permission"] = pb.to_dict()
        d["_thuc_thi"] = {"execution_id": y.execution_id, "buoc_id": b.buoc_id,
                          "tieu_chi": list(b.tieu_chi_dat)}
        # Router doc HO nhung thu agent headless khong doc duoc — cung khuon
        # `_chat`. Quyen cua agent KHONG doi.
        if any(k is LockKind.GIT for k, _r, _m in b.tai_nguyen):
            self._kem_nhat_ky_git(ctx.project.repo_path, d)
        self._kem_web_vao_hd(y.nguon_cau_nguoi_dung or y.goal, d)
        self._kem_probe_vao_hd(self._khoi_probe(b.muc_tieu, pid), d)

        t = Task(task_id=tid, project_id=pid, title=b.tieu_de or b.buoc_id,
                 objective=b.muc_tieu,
                 state=TaskState.BLOCKED if pb.gated else TaskState.QUEUED,
                 priority=40, contract=d, permission=pb.decision.value,
                 gate_reason=pb.ly_do(),
                 blocked_reason=(pb.cau_hoi_cho_nguoi_dung() if pb.gated
                                 else ""),
                 resources=tuple(chuoi_tai_nguyen(k, r, m)
                                 for k, r, m in b.tai_nguyen))
        self.store.luu_task(t)
        self.store.ghi_su_kien(
            "TASK_CREATED", project_id=pid, task_id=tid,
            level="WARNING" if pb.gated else "INFO",
            detail=f"bước {b.buoc_id} của {y.execution_id}: {t.title}",
            meta={"execution_id": y.execution_id, "buoc_id": b.buoc_id,
                  "permission": t.permission})
        return tid

    def _quet_thuc_thi(self) -> Dict:
        """Một nhịp cho MỌI lần thực thi còn sống. Gọi từ `tick()`.

        Ba việc, theo thứ tự:

        1. Việc con đã KẾT THÚC -> đưa kết quả vào bộ điều phối để chấm.
        2. Đẩy mỗi lần thực thi đi tiếp một nhịp.
        3. Lần thực thi vừa KẾT THÚC -> nói một câu trong chat (§21) và ghi
           ký ức (§14), ĐÚNG MỘT LẦN.

        Hỏng ở đây KHÔNG được làm vỡ vòng lặp điều phối: một lần thực thi
        hỏng không được kéo theo mọi việc lẻ khác.
        """
        ra: Dict = {"nhan": [], "tick": [], "ket_luan": []}
        for y in self.so_thuc_thi.dang_chay():
            bd = self.dieu_phoi(y.project_id)
            kh = self.so_thuc_thi.ke_hoach(y.execution_id)
            if kh is None:
                continue
            for st in self.so_thuc_thi.buoc(y.execution_id, kh.phien_ban):
                if st["state"] != DP.TrangThaiBuoc.DANG_CHAY.value:
                    continue
                t = self.store.task(st["task_id"]) if st["task_id"] else None
                if t is None or not t.state.terminal:
                    continue
                # TIÊU THỤ KẾT QUẢ NGAY KHI VIỆC KẾT THÚC — KHÔNG chờ tầng
                # việc cạn lượt.
                #
                # Đã thử chiều ngược lại (chờ `attempts >= MAX_ATTEMPTS` rồi
                # mới đọc) để tránh vứt đi một lượt thử sau đó thành công.
                # Nó gây DEADLOCK đo được: tầng bước không tiêu thụ nên không
                # gọi `bo_viec`, không ai nhả khoá ghi, và lượt kế tiếp nằm
                # `WAITING` vĩnh viễn với `in_flight` rỗng — thang phục hồi
                # từ 4,0 giây thành không bao giờ dừng.
                #
                # Cuộc đua "tầng việc thử lại sau khi tầng bước đã bỏ" đã
                # được chặn ở NGUỒN: `_dung_viec_cua_thuc_thi` làm CẠN lượt
                # thử của việc bị bỏ, nên tầng việc không thể hồi sinh nó.
                # Chặn ở một chỗ là đủ; chặn ở cả hai thì hai tầng cùng chờ
                # nhau.
                pb = ((t.result or {}).get("envelope") or {}) if t.result else {}
                kq = EKQ.HopDongKetQua(
                    task_id=t.task_id, buoc_id=st["buoc_id"],
                    status=str(pb.get("status")
                               or ("ok" if t.state is TaskState.DONE
                                   else "failed")),
                    summary=str(pb.get("summary") or ""),
                    artifacts=tuple(pb.get("artifacts") or ()),
                    files_changed=tuple(pb.get("changes") or ()),
                    tests_run=dict(pb.get("tests") or {}),
                    evidence=tuple(x for x in
                                   [f"log:{pb.get('raw_log_ref')}"
                                    if pb.get("raw_log_ref") else "",
                                    f"commit:{pb.get('commit')}"
                                    if pb.get("commit") else ""] if x),
                    warnings=tuple(pb.get("warnings") or ()),
                    known_limitations=tuple(pb.get("risks") or ()),
                    follow_up_needed=tuple(pb.get("followups") or ()),
                    provider=str(pb.get("provider") or ""),
                    model=str(pb.get("model") or ""),
                    runtime_id=str(pb.get("worker") or ""),
                    duration=float(pb.get("duration") or 0.0),
                    commit=str(pb.get("commit") or ""),
                    branch=str(pb.get("branch") or ""),
                    raw_log_ref=str(pb.get("raw_log_ref") or ""),
                    # WORKTREE la cho KIEM DINH phai chay. Xem
                    # `BoDieuPhoi._moi_gioi_cua`: chay `git status` o goc kho
                    # se thay mot cay SACH va moi buoc ghi bi cham la hong.
                    worktree=str(t.worktree or ""))
                try:
                    bd.nhan_ket_qua(t.task_id, kq,
                                    premium_tier=self._bac_gia(pb.get("model")))
                    ra["nhan"].append(f"{y.execution_id}/{st['buoc_id']}")
                except Exception as exc:                    # noqa: BLE001
                    self.store.ghi_su_kien(
                        "EXEC_RESULT_ERROR", project_id=y.project_id,
                        level="WARNING",
                        detail=f"{y.execution_id}: {type(exc).__name__}: {exc}"
                        [:300])
            if y.trang_thai is TrangThaiThucThi.REPLANNING:
                self._lap_lai_ke_hoach(y, kh)
                continue
            try:
                kt = bd.tick(y.execution_id)
                ra["tick"].append(kt.to_dict())
            except Exception as exc:                        # noqa: BLE001
                self.store.ghi_su_kien(
                    "EXEC_TICK_ERROR", project_id=y.project_id, level="WARNING",
                    detail=f"{y.execution_id}: {type(exc).__name__}: {exc}"[:300])
        for y in self.so_thuc_thi.danh_sach(dang_song=False, limit=20):
            k = self._ket_luan_thuc_thi(y)
            if k:
                ra["ket_luan"].append(k)
        return ra

    def _tieu_chi_chua_dat(self, eid: str):
        """`[(mô tả, cách kiểm)]` của tiêu chí nghiệm thu CHƯA ĐẠT.

        Đọc từ sự kiện `EXEC_VERIFIED` gần nhất — đó là bản chấm THẬT vừa
        chạy, nên bước sửa nhắm vào đúng thứ đã trượt chứ không vào một bản
        chấm dựng lại có thể khác đi.
        """
        from scripts.control_center.execution.ke_hoach import CachKiem
        bc = None
        for e in self.so_thuc_thi.su_kien(eid, limit=120):
            if e["kind"] == "EXEC_VERIFIED":
                bc = e.get("meta") or {}
                break
        if not bc:
            return []
        kh = self.so_thuc_thi.ke_hoach(eid)
        theo_mo = {t.mo_ta: t for t in (kh.nghiem_thu if kh else ())}
        ra = []
        for t in (bc.get("tieu_chi") or []):
            if str(t.get("trang_thai")) in ("DAT", "SUY_GIAM"):
                continue
            if not t.get("bat_buoc", True):
                continue
            mo = str(t.get("mo_ta") or "")
            goc = theo_mo.get(mo)
            ra.append((mo, tuple(goc.cach_kiem) if goc is not None else ()))
        del CachKiem
        return ra

    def _sua_theo_chien_luoc(self, y, kh, tieu_chi, *, lan: int):
        """(B) Tiêu chí NGỮ NGHĨA -> hỏi Strategist một bản sửa CÓ BIÊN.

        KHÔNG phải mọi lần sửa đều gọi model: đường này chỉ chạy khi
        `buoc_sua_tieu_chi` đã từ chối, tức là tiêu chí không đo một đường
        dẫn nào và máy không suy ra được việc cần làm.

        HAI RÀO giữ cho một đề xuất của model không nở ra thành một lần viết
        lại kho:

        * **phạm vi ghi do TA cấp, không do model chọn** — lấy từ phạm vi
          ghi mà kế hoạch hiện tại đã khai. Model chỉ nói LÀM GÌ, không nói
          ĐƯỢC GHI Ở ĐÂU.
        * **vẫn qua `lap_lai_ke_hoach`**, nên nó chịu đúng `TRAN_LAP_KE_HOACH`
          như mọi bản sửa khác.

        Hỏng/không có hội đồng -> trả rỗng, và bên gọi dừng cho người.
        """
        from scripts.control_center.reasoning.phan_loai import phan_loai_luot
        pid = y.project_id
        duong = sorted({r for b in kh.buoc for _k, r, m in b.tai_nguyen
                        if m == "write"})
        if not duong:
            duong = list(self._scope_mac_dinh(self.ctx(pid).project))
        try:
            hd = self.hoi_dong
        except Exception:                                   # noqa: BLE001
            hd = None
        if hd is None or not duong:
            return [], "", []

        cau = (f"Mục tiêu gốc: {y.goal}\n\n"
               "TIÊU CHÍ NGHIỆM THU CHƯA ĐẠT:\n"
               + "\n".join(f"  - {m}" for m, _ in tieu_chi)
               + "\n\nKế hoạch hiện tại đã chạy xong và MỌI BƯỚC ĐỀU ĐẠT, "
                 "nhưng tiêu chí trên vẫn chưa đạt. Đề xuất MỘT việc sửa CÓ "
                 "BIÊN để đạt nó. Chỉ được sửa trong: "
               + ", ".join(duong)
               + ".\nĐừng đề xuất đổi tiêu chí, đừng đề xuất nới phạm vi.")
        try:
            self._dam_bao_suc_khoe("chiến lược sửa")
            kq = hd.chay(cau=cau, phan_loai=phan_loai_luot(cau),
                         che_do=self.leader_ban_ghi(pid).che_do_enum(),
                         khoi_san_co={"rang_buoc": self._khoi_rang_buoc(pid)[0],
                                      "vien_nang": self._khoi_vien_nang(pid, cau)},
                         chinh_sach=self.chinh_sach_cao_cap(pid),
                         project_id=pid)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "REPAIR_STRATEGY_ERROR", project_id=pid, level="WARNING",
                detail=f"{type(exc).__name__}: {exc}"[:300])
            return [], "", []
        cl = kq.chien_luoc
        if cl is None or not cl.dung_duoc:
            return [], "", []
        muc = (cl.de_xuat or "").strip()
        if cl.viec_can_lam:
            muc += "\n\nViệc cần làm:\n" + "\n".join(
                f"  - {x}" for x in cl.viec_can_lam[:6])
        buoc = ELK.buoc_tu_de_xuat_sua(kh, muc_tieu=muc, duong=duong, lan=lan)
        if not buoc:
            return [], "", []
        ng = next((x for x in kq.nguon_goc
                   if getattr(x, "vai", None) and x.vai.value == "strategist"),
                  None)
        chon = getattr(ng, "chon", None)
        self.so_thuc_thi.ghi_su_kien(
            y.execution_id, "REPAIR_STRATEGY", project_id=pid,
            detail=(f"Strategist đề xuất bản sửa · "
                    f"{getattr(chon, 'provider', '?')}/"
                    f"{getattr(chon, 'model_id', '?')}")[:300],
            meta={"provider": getattr(chon, "provider", ""),
                  "model": getattr(chon, "model_id", ""),
                  "pham_vi": duong})
        return (buoc,
                "tiêu chí NGỮ NGHĨA chưa đạt — Strategist đề xuất bản sửa",
                [f"tieu_chi:{m[:60]}" for m, _ in tieu_chi])

    def _lap_lai_ke_hoach(self, y: EYD.YDinhThucThi, kh) -> Optional[Dict]:
        """`REPLANNING` -> bản kế hoạch kế tiếp, hoặc `BLOCKED`. §9, §10.

        MỘT lần thực thi ở `REPLANNING` mà không ai lập lại kế hoạch là một
        lần thực thi KẸT — nó không kết thúc, không chạy, và không ai được
        báo. Đó đúng là lỗi đo được ở lát cắt dọc đầu tiên của V0.9.

        Bản mới do `lap_ke_hoach.buoc_sua_chua` dựng: giữ bước đã đạt, thay
        bước hỏng bằng bước CÙNG MÃ mang thêm BẰNG CHỨNG hỏng. Không thêm
        được gì (đã sửa đủ số lần, hoặc không bước nào sửa được) thì DỪNG
        cho người — chứ không sinh ra một bản v3 giống hệt v2.
        """
        eid = y.execution_id
        bd = self.dieu_phoi(y.project_id)
        hong: Dict[str, str] = {}
        for st in self.so_thuc_thi.buoc(eid, kh.phien_ban):
            if st["xac_minh"] in ("DAT", "SUY_GIAM"):
                continue
            ly = "; ".join(
                f"{k.get('cach')}: {k.get('chi_tiet')}"
                for k in (st.get("kiem") or []) if not k.get("dat"))
            hong[st["buoc_id"]] = ly or (
                f"trạng thái {st['state']}, xác minh {st['xac_minh']}")
        buoc = ELK.buoc_sua_chua(kh, hong) if hong else []
        ly_do_sua = (f"{len(hong)} bước không qua kiểm định: "
                     + ", ".join(sorted(hong)))
        bang_chung = [f"buoc:{k}" for k in sorted(hong)]

        # --- TIÊU CHÍ NGHIỆM THU CHƯA ĐẠT: SỬA, chứ không bỏ cuộc (§1) ------
        #
        # `hong` rỗng nghĩa là MỌI BƯỚC ĐỀU ĐẠT và thứ chưa đạt là TIÊU CHÍ
        # của mục tiêu GỐC. Bản đầu dừng luôn ở `BLOCKED` — và đó là một lần
        # bỏ cuộc quá sớm: nếu tiêu chí ĐO MỘT ĐƯỜNG DẪN và lần thực thi đã
        # có thẩm quyền ghi ở đó, thì việc cần làm rất cụ thể và hoàn toàn
        # nằm trong quyền đã cấp.
        if not buoc:
            tc = self._tieu_chi_chua_dat(eid)
            if tc:
                lan = kh.phien_ban
                # (C) CẦN THẨM QUYỀN MỚI -> KHÔNG tự sửa.
                if y.can_tham_quyen_moi:
                    self.so_thuc_thi.doi_trang_thai(
                        eid, TrangThaiThucThi.WAITING_AUTHORITY,
                        ly_do=(EYD.cau_hoi_tham_quyen(y)
                               or "cần bạn cho phép trước khi sửa"),
                        pha="chờ bạn cho phép")
                    return None
                # (A) SỬA TẤT ĐỊNH — tiêu chí đo một đường dẫn cụ thể.
                buoc = ELK.buoc_sua_tieu_chi(kh, tc, lan=lan)
                if buoc:
                    ly_do_sua = ("tiêu chí nghiệm thu chưa đạt, sửa có mục "
                                 "tiêu: " + "; ".join(m[:80] for m, _ in tc[:2]))
                    bang_chung = [f"tieu_chi:{m[:60]}" for m, _ in tc]
                else:
                    # (B) TIÊU CHÍ NGỮ NGHĨA -> để STRATEGIST đề xuất.
                    buoc, ly_do_sua, bang_chung = self._sua_theo_chien_luoc(
                        y, kh, tc, lan=lan)

        if not buoc:
            tc = self._tieu_chi_chua_dat(eid)
            if hong:
                ly = ("lập lại kế hoạch không thêm được gì — bước hỏng đã "
                      "được sửa hết số lần cho phép. Cần bạn xem: "
                      + "; ".join(f"{k}: {v[:120]}"
                                  for k, v in list(hong.items())[:3]))
            elif tc:
                ly = ("MỌI BƯỚC ĐỀU ĐẠT nhưng tiêu chí nghiệm thu chưa đạt, "
                      "và Router KHÔNG suy ra được một việc sửa CÓ BIÊN cho "
                      "nó (tiêu chí không đo một đường dẫn nào, và Strategist "
                      "cũng không đề xuất được). Cần bạn quyết: "
                      + "; ".join(m[:90] for m, _ in tc[:2]))
            else:
                ly = ("kiểm định không đạt nhưng không xác định được thứ gì "
                      "để sửa — cần bạn xem")
            self.so_thuc_thi.doi_trang_thai(
                eid, TrangThaiThucThi.BLOCKED, ly_do=ly, pha="cần bạn xem")
            bd.nha_tai_nguyen(self.so_thuc_thi.y_dinh(eid) or y)
            return None
        try:
            moi = bd.lap_lai_ke_hoach(eid, buoc, ly_do=ly_do_sua,
                                      bang_chung=bang_chung)
        except RuntimeError as exc:
            self.so_thuc_thi.doi_trang_thai(
                eid, TrangThaiThucThi.BLOCKED, ly_do=str(exc)[:400],
                pha="cần bạn xem")
            bd.nha_tai_nguyen(self.so_thuc_thi.y_dinh(eid) or y)
            return None
        bd.tick(eid)
        return {"execution_id": eid, "phien_ban": moi.phien_ban}

    def _bac_gia(self, model_id) -> int:
        try:
            m = self.fabric.models.get(str(model_id or ""))
            return int(getattr(m, "premium_tier", 0) or 0)
        except Exception:                                   # noqa: BLE001
            return 0

    def _ket_luan_thuc_thi(self, y: EYD.YDinhThucThi) -> Optional[Dict]:
        """§21 + §14 — nói một câu và ghi ký ức, ĐÚNG MỘT LẦN.

        Dùng `ket_qua_da_bao` (bảng BỀN) chứ không một `set` trong RAM: một
        lần khởi động lại giữa chừng không được làm mất câu kết luận, và
        cũng không được làm nó hiện ra hai lần.
        """
        khoa = f"exec:{y.execution_id}"
        with self._khoa_bao:
            if self.store.da_bao_ket_qua(khoa, y.trang_thai.value):
                return None
            bc = None
            try:
                kh = self.so_thuc_thi.ke_hoach(y.execution_id)
                if kh is not None:
                    # CÙNG bối cảnh kiểm định với tầng điều phối — kể cả
                    # `moi_gioi_khac`. Bản trước chỉ đưa `moi_gioi` chung,
                    # nên phán quyết ghi vào KÝ ỨC và vào vòng phản hồi chất
                    # lượng có thể nói một bước ĐÃ ĐẠT là hỏng, chỉ vì nó
                    # sống ở cây của bước anh em.
                    dp = self.dieu_phoi(y.project_id)
                    kqb, mg, khac = dp.canh_kiem(y.execution_id, kh)
                    bc = EKD.kiem_dinh_thuc_thi(
                        y, kh, kqb, moi_gioi=mg, moi_gioi_khac=khac)
            except Exception:                               # noqa: BLE001
                bc = None
            ghi = self._ghi_ky_uc_thuc_thi(y, bc)
            # §B — VÒNG PHẢN HỒI CHẤT LƯỢNG. Nằm TRONG khối đã khoá chống
            # trùng của `_ket_luan_thuc_thi`, nên một lần thực thi sinh ĐÚNG
            # MỘT quan sát kể cả khi app khởi động lại giữa chừng: khoá là
            # bảng `ket_qua_da_bao` trên đĩa, không phải một `set` trong RAM.
            qs = self._phan_hoi_chat_luong(y, bc)
            van = DP.cau_ket_thuc(y, bc, ghi_nho=ghi)
            tin = self.store.them_chat(
                y.project_id, "assistant", van,
                meta={"loai": "ket_luan_thuc_thi",
                      "execution_id": y.execution_id,
                      "trang_thai": y.trang_thai.value,
                      "kiem_dinh": (bc.to_dict() if bc else None),
                      "ky_uc": ghi, "phan_hoi": qs})
            self.store.ghi_da_bao_ket_qua(khoa, y.trang_thai.value,
                                          project_id=y.project_id,
                                          message_id=tin.message_id)
            self.so_thuc_thi.dat_ket_luan(y.execution_id, van)
        self.store.ghi_su_kien(
            "EXEC_REPORTED", project_id=y.project_id,
            detail=f"{y.execution_id} [{y.trang_thai.value}] -> "
                   f"tin nhắn #{tin.message_id}")
        return {"execution_id": y.execution_id,
                "message_id": tin.message_id, "text": van}

    def _phan_hoi_chat_luong(self, y: EYD.YDinhThucThi, bc) -> Optional[Dict]:
        """§B — kết quả đã kiểm định -> MỘT quan sát trong lịch sử VAI.

        Nối `chiến lược -> kế hoạch -> thực thi -> kiểm định -> kết quả` bằng
        `de_xuat` mà `_khoi_dong_tu_de_xuat` đã ghim vào ý định. Không có đề
        xuất (người dùng gõ thẳng một việc, không qua một lời khuyên nào) thì
        KHÔNG có ai để gắn kết quả vào, và `dung_quan_sat` trả `None` — im
        lặng là câu trả lời đúng, không phải một mẫu vô danh.

        Hỏng ở đây KHÔNG được làm hỏng câu kết luận: một dòng telemetry
        không đáng đổi lấy việc người dùng không biết việc đã xong.
        """
        from scripts.control_center.execution import phan_hoi as EPH
        try:
            dx = self.so_thuc_thi.de_xuat_theo_ma(y.nguon_de_xuat)
            giay = None
            try:
                giay = self.dieu_phoi(y.project_id).chi_phi(
                    y.execution_id).tong_giay or None
            except Exception:                               # noqa: BLE001
                giay = None
            pb = None
            for e in self.so_thuc_thi.su_kien(y.execution_id, limit=80):
                if e["kind"] == "REVIEW_VERDICT":
                    pb = e.get("meta") or {}
                    break
            qs = EPH.dung_quan_sat(y, bc, de_xuat=dx, phan_bien=pb, giay=giay)
            if qs is None:
                return None
            ra = EPH.ghi_phan_hoi(self._lich_su_vai(), qs,
                                  rubric="docs/reports/CLOSED_LOOP_V09.md")
            if ra:
                self.so_thuc_thi.ghi_su_kien(
                    y.execution_id, "QUALITY_OBSERVED",
                    project_id=y.project_id,
                    detail=(f"{qs.task_type} · {qs.provider}/{qs.model_id} · "
                            f"{'ĐẠT' if qs.thanh_cong else 'KHÔNG ĐẠT'} · "
                            f"lập lại {qs.so_lan_lap_lai}")[:300],
                    meta=ra)
            return ra
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "QUALITY_FEEDBACK_ERROR", project_id=y.project_id,
                level="WARNING",
                detail=f"{y.execution_id}: {type(exc).__name__}: {exc}"[:300])
            return None

    def _lich_su_vai(self):
        """`BenchmarkStore` của tệp VAI — CÙNG tệp mà `HoiDong` đang ghi.

        Lấy qua `self.hoi_dong` chứ không dựng một kho thứ hai: hai
        `BenchmarkStore` trỏ cùng một tệp sẽ có hai bộ đệm lệch nhau, và
        `summary_for` sẽ trả hai con số khác nhau cho cùng một câu hỏi.
        """
        try:
            hd = self.hoi_dong
        except Exception:                                   # noqa: BLE001
            return None
        return getattr(hd, "lich_su", None) if hd is not None else None

    def _ghi_ky_uc_thuc_thi(self, y: EYD.YDinhThucThi, bc) -> List[Dict]:
        """§14 — kết quả đã kiểm định -> ký ức. Hỏng thì bỏ qua, không nổ."""
        if bc is None:
            return []
        try:
            g = EGN.GhiNhoThucThi(self.ky_uc)
            if not g.dung_duoc:
                return []
            tep = sorted({x for st in self.so_thuc_thi.buoc(y.execution_id)
                          for x in ((st.get("ket_qua") or {})
                                    .get("files_changed") or ())})
            ds = EGN.phan_loai_ghi_nho(y, bc, tep_da_sua=tep)
            ra = g.ghi(y.project_id, ds)
            g.diem_dung(y.project_id, y, bc)
            return ra
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "EXEC_MEMORY_ERROR", project_id=y.project_id, level="WARNING",
                detail=f"{y.execution_id}: {type(exc).__name__}: {exc}"[:300])
            return []

    # -- 2c. API cong khai cua vong kin -------------------------------------

    def thuc_thi_danh_sach(self, project_id: str = "",
                           dang_song: Optional[bool] = None) -> List[Dict]:
        return [y.to_dict() for y in
                self.so_thuc_thi.danh_sach(project_id, dang_song=dang_song)]

    def thuc_thi_anh_chup(self, execution_id: str) -> Dict:
        d = self.so_thuc_thi.anh_chup(execution_id)
        if d:
            ns = self.dieu_phoi(d["y_dinh"]["project_id"]).ngan_sach(
                execution_id)
            d["ngan_sach"] = ns.to_dict() if ns else None
            d["chi_phi"] = self.dieu_phoi(
                d["y_dinh"]["project_id"]).chi_phi(execution_id).to_dict()
        return d

    def thuc_thi_duyet(self, execution_id: str, *, boi: str = "user",
                       dong_y: bool = True) -> Dict:
        """NGƯỜI duyệt cổng thẩm quyền. Chỉ người — không đường tự động nào."""
        y = self.so_thuc_thi.y_dinh(execution_id)
        if y is None:
            raise KeyError(execution_id)
        bd = self.dieu_phoi(y.project_id)
        y2 = bd.duyet(execution_id, boi=boi, dong_y=dong_y)
        if dong_y:
            bd.tick(execution_id)
        return y2.to_dict()

    def thuc_thi_tam_dung(self, execution_id: str, *, ly_do: str = "") -> Dict:
        y = self.so_thuc_thi.y_dinh(execution_id)
        if y is None:
            raise KeyError(execution_id)
        return self.dieu_phoi(y.project_id).tam_dung(
            execution_id, ly_do=ly_do or "người dùng tạm dừng").to_dict()

    def thuc_thi_tiep_tuc(self, execution_id: str) -> Dict:
        y = self.so_thuc_thi.y_dinh(execution_id)
        if y is None:
            raise KeyError(execution_id)
        return self.dieu_phoi(y.project_id).tiep_tuc(execution_id).to_dict()

    def thuc_thi_huy(self, execution_id: str, *, ly_do: str = "") -> Dict:
        y = self.so_thuc_thi.y_dinh(execution_id)
        if y is None:
            raise KeyError(execution_id)
        return self.dieu_phoi(y.project_id).huy(
            execution_id, ly_do=ly_do or "người dùng huỷ").to_dict()

    # -- 3. Vong lap dieu phoi ----------------------------------------------

    def tick(self) -> Dict:
        """Một nhịp điều phối. Trả về những gì nhịp này đã làm.

        Hàm này KHÔNG chặn: mọi việc chạy trong luồng riêng. Một `tick` chỉ
        quyết định và giao; nó không bao giờ đợi một agent.
        """
        da_giao: List[str] = []
        cho: List[Dict] = []
        # LUOI AN TOAN cho "ket qua phai ve toi o chat". Chay TRUOC phep
        # kiem tran song song: mot viec da ket thuc thi khong con chiem khe
        # nao, va cau tra loi cua no khong duoc phai cho mot khe trong.
        try:
            self._quet_ket_qua_chua_bao()
        except Exception:                                   # noqa: BLE001
            pass
        # V0.9 — NHIP CUA VONG KIN. Chay TRUOC phep kiem tran song song,
        # cung ly do: mot buoc da ket thuc thi khong con chiem khe nao, va
        # phan quyet kiem dinh cua no khong duoc phai cho mot khe trong.
        try:
            self._quet_thuc_thi()
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien("EXEC_SCAN_ERROR", level="WARNING",
                                   detail=f"{type(exc).__name__}: {exc}"[:300])
        with self._khoa:
            đang = len([t for t in self._dang_chay.values() if t.is_alive()])
            self._dang_chay = {k: v for k, v in self._dang_chay.items()
                               if v.is_alive()}
        if đang >= self.max_parallel:
            return {"dispatched": [], "waiting": [],
                    "note": f"đã chạm trần {self.max_parallel} việc song song"}

        san_sang = [(p.project_id, t) for p in self.projects()
                    for t in self._san_sang(p.project_id)]
        # Chi do khi THAT SU co viec cho giao. Mo Control Center ra xem sổ
        # thi khong goi mang lan nao.
        if san_sang:
            self._dam_bao_suc_khoe(f"{len(san_sang)} việc chờ giao")
        for _pid, t in san_sang:
            with self._khoa:
                if len(self._dang_chay) >= self.max_parallel:
                    break
                if t.task_id in self._dang_chay:
                    continue
            kq = self._giao(t)
            if kq.get("dispatched"):
                da_giao.append(t.task_id)
            else:
                cho.append(kq)
        return {"dispatched": da_giao, "waiting": cho}

    def _san_sang(self, project_id: str) -> List[Task]:
        """Việc đủ điều kiện chạy: QUEUED/WAITING + mọi phụ thuộc đã DONE.

        Phụ thuộc HỎNG thì việc con không bao giờ chạy — đánh dấu ngay thay
        vì để nó nằm `WAITING` mãi mãi và trông như đang tiến triển.
        """
        ra: List[Task] = []
        tat_ca = {t.task_id: t for t in self.store.tasks(project_id)}
        for t in tat_ca.values():
            if t.state not in (TaskState.QUEUED, TaskState.WAITING):
                continue
            # Viec CHA cua mot lan toa la VAT CHUA: khong giao cho agent nao;
            # no ket thuc khi `_tong_hop_toa` gop xong cac con.
            if ((t.contract or {}).get("_toa") or {}).get("cha"):
                continue
            # LƯỚI CUỐI CỦA CỔNG AN TOÀN, và nó nằm ĐÚNG ở đây có lý do.
            #
            # `chat()` đã đặt việc GATED vào thẳng `BLOCKED`, nhưng đó là MỘT
            # đường. Bất kỳ đường nào khác đưa nó về `QUEUED` đều mở cổng mà
            # không ai duyệt. Đã có một đường như thế và nó CHẠY ĐƯỢC THẬT:
            #
            #     pause(việc GATED)   BLOCKED -> PAUSED   (hợp lệ)
            #     resume(việc đó)     PAUSED  -> QUEUED   (hợp lệ)
            #     -> tick() giao việc, agent chạy, KHÔNG một lần duyệt nào
            #
            # Sửa riêng `resume()` là bịt đúng một lỗ và để ngỏ mọi lỗ chưa
            # nghĩ ra. Kiểm ở CỔNG VÀO của bộ lập lịch thì mọi đường — hiện
            # tại và về sau — đều phải đi qua đây.
            if not self._da_duyet_cong(t):
                self.store.doi_trang_thai(
                    t.task_id, TaskState.BLOCKED, force=True,
                    reason=(f"việc GATED chưa được duyệt ({t.gate_reason}) — "
                            f"đưa lại BLOCKED. Chỉ `mo_khoa_gated()` mới mở "
                            f"được cổng này."))
                self.store.ghi_su_kien(
                    "GATE_REASSERTED", project_id=t.project_id,
                    task_id=t.task_id, level="ALERT",
                    detail=(f"việc GATED lọt vào hàng đợi mà chưa có ai duyệt "
                            f"— đã chặn lại trước khi giao"))
                continue
            deps = [tat_ca.get(d) for d in t.dependencies]
            if any(d is not None and d.state is TaskState.FAILED for d in deps):
                self.store.doi_trang_thai(
                    t.task_id, TaskState.BLOCKED,
                    reason="phụ thuộc đã hỏng — không tự chạy tiếp")
                continue
            # Mot viec REVIEW phu thuoc vao CHA cua no, nhung cha chi thoat
            # `REVIEW` SAU KHI review chay xong. Doi cha phai `DONE` truoc
            # thi hai ben khoa nhau vinh vien: cha cho review, review cho
            # cha. Nen voi dung quan he cha-con nay, `REVIEW` la du dieu
            # kien — do chinh la trang thai "da xong phan viec, dang cho
            # kiem cheo".
            #
            # Not loi nay hep co chu dich: chi ap cho `parent_id` cua chinh
            # viec do, khong ap cho phu thuoc thuong. Mot viec thuong van
            # phai cho phu thuoc `DONE` that.
            chua = [d.task_id for d in deps
                    if d is not None and d.state is not TaskState.DONE
                    and not (d.task_id == t.parent_id
                             and d.state is TaskState.REVIEW)]
            if chua:
                if t.state is not TaskState.WAITING:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.WAITING,
                        reason=f"chờ {', '.join(chua)}")
                continue
            ra.append(t)
        ra.sort(key=lambda x: (x.priority, x.created_at))
        return ra

    def _giao(self, t: Task) -> Dict:
        """Thử giao MỘT việc. Không chặn, không ném.

        LƯỚI CUỐI CHO KHOÁ. Mọi lối thoát ĐÃ BIẾT bên trong `_giao_khong_luoi`
        đều nhả khoá bằng tay, nhưng "đã biết" là chỗ hỏng: một
        `sqlite3.OperationalError` lúc `claim_task`, hay một `KeyError` từ
        `fabric.model()`, sẽ thoát ra ngoài, bị `tick()` nuốt thành
        `TICK_FAILED`, và khoá đã giành KHÔNG BAO GIỜ được nhả.

        Với khoá FILESYSTEM/SERVICE thì nó tự lành sau TTL. Với khoá
        PRODUCTION thì KHÔNG — `reclaim()` cố ý không nhả chúng. Nghĩa là một
        lỗi SQLite nhất thời có thể khoá vĩnh viễn một tài nguyên production
        cho tới khi có người gỡ tay. Đó là cái giá quá đắt cho một ngoại lệ
        không lường trước, nên ở đây có `finally`.
        """
        ctx = self.ctx(t.project_id)
        lm = LockManager(self.store)
        giao_duoc = False
        try:
            kq = self._giao_khong_luoi(t, ctx, lm)
            giao_duoc = bool(kq.get("dispatched"))
            return kq
        except Exception as exc:                          # noqa: BLE001
            self.store.ghi_su_kien(
                "DISPATCH_CRASHED", project_id=t.project_id,
                task_id=t.task_id, level="ERROR",
                detail=f"{type(exc).__name__}: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": f"{type(exc).__name__}: {exc}"[:200]}
        finally:
            # Giao ĐƯỢC thì luồng `_chay` sở hữu khoá và sẽ tự nhả trong
            # `finally` của nó. Chỉ nhả ở đây khi việc KHÔNG được giao —
            # nhả nhầm lúc agent đang chạy còn tệ hơn không nhả.
            if not giao_duoc:
                try:
                    lm.tra(t.project_id, t.task_id)
                except Exception:                         # noqa: BLE001
                    pass

    def _hop_dong_kem_dinh_kem(self, t: Task) -> Dict:
        """Hợp đồng + danh sách đính kèm ĐƯỢC CẤP cho đúng việc này.

        Chèn ở lúc GIAO, không lúc tạo: đính kèm được gán sau khi việc đã
        được tạo (`chat()` phải có `task_id` mới gán được), và người dùng
        còn có thể cấp thêm về sau. Dựng lại đoạn này mỗi lượt giao thì nó
        luôn khớp với quyền hiện tại.

        Agent nhận **đường dẫn cục bộ** và tự đọc bằng công cụ đọc tệp của
        nó. Không tệp nào được tải lên đâu.
        """
        hd = dict(t.contract or {})
        try:
            mo = self.dinh_kem.mo_ta_cho_agent(t.task_id)
        except Exception as exc:                          # noqa: BLE001
            # Khong de mot loi o tang dinh kem lam chet ca luot giao.
            self.store.ghi_su_kien(
                "ATTACHMENT_DESC_FAILED", project_id=t.project_id,
                task_id=t.task_id, level="WARN",
                detail=f"{type(exc).__name__}: {exc}"[:200])
            return hd
        if mo:
            hd["objective"] = ((hd.get("objective") or "")
                               + "\n" + mo)
        return hd

    def _nha_phien_moi(self, ctx: "ProjectContext", session_id: str,
                       ly_do: str) -> None:
        """Trả lại một phiên VỪA DỰNG khi lần giao hỏng sau đó.

        KHUYẾT TẬT ĐÃ RÒ (đo trên sổ chính tắc 2026-09-12, 8 phiên `STARTING`
        rò trong MỘT lần chạy): `_giao_khong_luoi` dựng phiên ở bước (2), rồi
        bước (3) (hết lease runtime) và bước (4) (việc bị vòng khác nhận
        trước) `return` mà chỉ trả KHOÁ và LEASE — phiên vừa dựng ở lại sổ
        mãi ở `STARTING`.

        `SessionState.STARTING.alive` là `True`, nên mỗi lần giao hỏng ĂN
        VĨNH VIỄN một khe. Sau ~12 lần thì `WAIT: đã có 12/12 phiên sống` và
        không việc nào được giao nữa. `recover()` có dọn `STARTING` quá hạn
        nhưng nó CHỈ chạy lúc khởi động, nên trong một lần chạy dài thì vô
        nghĩa — đó là lý do một lần nghiệm thu tự bóp cổ chính nó giữa chừng.

        Chỉ gọi cho phiên do CHÍNH lần giao này dựng. Phiên DÙNG LẠI thì
        không được đụng: nó đã sống từ trước và có thể vừa được giao việc
        khác.
        """
        if not session_id:
            return
        try:
            ctx.sessions.dung(session_id, state=SessionState.STOPPED,
                              reason=f"lần giao không thành: {ly_do}"[:280])
        except Exception as exc:                              # noqa: BLE001
            # Không để việc dọn dẹp làm hỏng đường trả lời của lần giao.
            self.store.ghi_su_kien(
                "SESSION_RELEASE_FAILED", project_id=ctx.project.project_id,
                session_id=session_id, level="WARNING",
                detail=f"{type(exc).__name__}: {exc}"[:200])

    def _giao_khong_luoi(self, t: Task, ctx: "ProjectContext",
                         lm: LockManager) -> Dict:
        """Thân thật của `_giao`. Thứ tự giành tài nguyên cố định — xem
        docstring module."""
        try:
            hd = TaskContract.from_dict(self._hop_dong_kem_dinh_kem(t))
        except (ContractError, KeyError, ValueError) as exc:
            self.store.doi_trang_thai(
                t.task_id, TaskState.FAILED,
                reason=f"hợp đồng hỏng: {type(exc).__name__}: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": "hợp đồng hỏng"}

        # (1) khoa tai nguyen — kem CHE DO (READ/WRITE, V0.6.1). Dang cu
        # `FILESYSTEM:web` doc thanh WRITE, khong bao gio noi long cho ghi.
        xin = [x for x in (doc_chuoi_tai_nguyen(r) for r in t.resources) if x]
        grant = lm.xin(t.project_id, xin, task_id=t.task_id) if xin else None
        if grant is not None and not grant.granted:
            self._sang_waiting(t, grant.reason)
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": grant.reason, "conflict": grant.to_dict()}

        # (2) quyet dinh phien
        try:
            nhu_cau = Demand.from_contracts(
                [TaskContract.from_dict(x.contract)
                 for x in self.store.tasks(
                     t.project_id, states=(TaskState.QUEUED, TaskState.WAITING))
                 if x.contract])
        except (ContractError, ValueError):
            nhu_cau = None

        # TOA: anh em dang chay o runtime nao thi con nay TRANH runtime do
        # (khi con cho khac) — "8 agent" phai la 8 tai khoan khi be du, khong
        # phai 8 luot xep chong len mot tai khoan ranh nhat. Bo lap lich V4
        # khong doi: chi nhan them `exclude`, va `decide()` tu roi ve khong
        # tranh khi khong con ai.
        tranh = tuple(self._runtime_anh_em_dang_chay(t))
        cam, ly_do_cam = self._cam_runtime_theo_nang_luc(ctx, hd)
        da_tu_choi = self._cam_runtime_da_tu_choi(t.contract)
        if da_tu_choi:
            cam = tuple(sorted(set(cam) | set(da_tu_choi)))
            ly_do_cam = ((ly_do_cam + "; ") if ly_do_cam else "") + \
                f"đã từ chối việc này ở lượt trước: {list(da_tu_choi)}"
        qd = ctx.sessions.decide(
            t, hd, demand=nhu_cau,
            conflicting_task=(grant.conflict_holder_task
                              if grant is not None and not grant.granted
                              else ""),
            tranh_runtime=tranh, cam_runtime=cam, ly_do_cam=ly_do_cam)
        self.store.ghi_su_kien(
            "SESSION_DECISION", project_id=t.project_id, task_id=t.task_id,
            detail=f"{qd.action.value}: {qd.reason}"[:400], meta=qd.to_dict())

        if qd.action is SessionAction.WAIT:
            lm.tra(t.project_id, t.task_id)
            self._sang_waiting(t, qd.reason)
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": qd.reason, "decision": qd.to_dict()}

        try:
            if qd.action is SessionAction.REUSE:
                s = ctx.sessions.reuse(qd.session_id, t, contract=hd)
            else:
                s = ctx.sessions.create(qd, t, contract=hd)  # RÒ ở (3)/(4)
        except (WorktreeError, ValueError) as exc:
            lm.tra(t.project_id, t.task_id)
            self.store.doi_trang_thai(
                t.task_id, TaskState.BLOCKED,
                reason=f"không cấp được cây làm việc: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": str(exc)[:200]}

        # Phien VUA DUNG cho lan giao nay. Neu lan giao hong o (3) hoac (4)
        # thi no chua tung chay gi, va phai duoc tra lai — xem `_nha_phien_moi`.
        moi = s.session_id if qd.action is not SessionAction.REUSE else ""

        # (3) lease KHE runtime cua Router V4
        khoa_lease = self._muon_lease(ctx, s.runtime_id, t.task_id)
        if khoa_lease is None:
            lm.tra(t.project_id, t.task_id)
            ly_do = (f"runtime {s.runtime_id} hết khe đồng thời — chờ lượt "
                     f"sau thay vì đẩy thêm vào một tài khoản đã đầy")
            self._nha_phien_moi(ctx, moi, ly_do)
            self._sang_waiting(t, ly_do)
            return {"task_id": t.task_id, "dispatched": False, "reason": ly_do}

        # (4) NHAN VIEC — nguyen tu. Truoc buoc nay moi thu deu hoan tac duoc.
        if not self.store.claim_task(t.task_id, s.session_id):
            ctx.leases.release(khoa_lease, self.owner)
            lm.tra(t.project_id, t.task_id)
            self._nha_phien_moi(
                ctx, moi, "việc đã bị một vòng lập lịch khác nhận trước")
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": "việc đã bị một vòng lập lịch khác nhận trước"}

        # ĐỌC LẠI việc sau khi `claim`. Bản `t` trong tay đã CŨ: `claim_task`
        # đổi trạng thái bằng một câu `UPDATE` thẳng xuống SQL (nó phải vậy
        # để nguyên tử), nên ghi đè bằng đối tượng cũ sẽ kéo trạng thái từ
        # `RUNNING` ngược về `QUEUED` — và việc coi như chưa từng được nhận.
        # Đây đúng là chế độ hỏng "đọc–sửa–ghi" mà docstring của `store.py`
        # cảnh báo; nó lọt vào ngay lần dựng đầu tiên.
        t = self.store.task(t.task_id) or t
        # Chi ghi worktree cho viec THAT SU co ghi. Mot viec CHI DOC dung
        # lai mot phien tung chay viec co ghi se thua huong `s.worktree`,
        # va bang dieu khien se hien no nhu the viec do so huu cay ay —
        # sai, va sai theo huong nguy hiem: nguoi van hanh doc bang se
        # tuong mot viec chi doc dang sua tep o do.
        if hd.execution.worktree_required:
            t.worktree, t.branch = s.worktree, s.branch
        t.owner_session = s.session_id
        self.store.luu_task(t)
        ctx.sessions.bat_dau_viec(s.session_id, t.task_id)
        # CHIEM KHE NGAY LUC GIAO, khong doi luong `_chay` chay toi
        # `mark_started`. Mot nhip `tick()` giao nhieu viec lien tiep (toa N
        # con): neu khe chi duoc danh dau trong luong, viec ke tiep trong CUNG
        # nhip van thay runtime do "con cho" va bo lap lich xep hai con len
        # mot tai khoan da day (RT01 + Leader) — do that o bai kiem toa.
        # `mark_started` idempotent, nen lan goi lai trong `_chay` vo hai.
        try:
            ctx.fabric.mark_started(s.runtime_id, t.task_id)
        except Exception:                                   # noqa: BLE001
            pass
        # Con dau tien cua mot lan TOA chay -> viec cha sang RUNNING (no la
        # vat chua, khong co phien; `recover()` biet dieu do). Bang dieu khien
        # thay "cha RUNNING, con AG02/AG03/... RUNNING" dung nhu thuc te.
        if t.parent_id:
            try:
                cha = self.store.task(t.parent_id)
                if cha is not None and cha.state is TaskState.WAITING and \
                        ((cha.contract or {}).get("_toa") or {}).get("cha"):
                    self.store.doi_trang_thai(cha.task_id, TaskState.RUNNING, force=True,
                                              reason="việc con đầu tiên bắt đầu chạy")
            except Exception:                               # noqa: BLE001
                pass

        luong = threading.Thread(
            target=self._chay, name=f"cc-{t.task_id}", daemon=True,
            args=(ctx, t.task_id, hd, Placement(s.runtime_id, s.model_id),
                  s.session_id, khoa_lease))
        with self._khoa:
            self._dang_chay[t.task_id] = luong
        luong.start()
        return {"task_id": t.task_id, "dispatched": True,
                "session_id": s.session_id, "placement": s.placement_key,
                "action": qd.action.value}

    def _cau_hinh_fabric(self) -> Dict:
        """Cấu hình fabric THÔ (có khối `security`), đọc một lần rồi nhớ.

        `Fabric` đã dựng không giữ khối `security`, mà đó lại là nơi
        `security_refusal_family` được KHAI BÁO. Đọc lại tệp là rẻ và chỉ
        xảy ra khi có việc thực sự đòi một năng lực đặc biệt.
        """
        cu = getattr(self, "_fabric_cfg_cache", None)
        if cu is not None:
            return cu
        try:
            cfg = FC.doc_cau_hinh(root=self.root)
        except Exception:                                   # noqa: BLE001
            cfg = {}
        self._fabric_cfg_cache = cfg if isinstance(cfg, dict) else {}
        return self._fabric_cfg_cache

    def _cam_runtime_theo_nang_luc(self, ctx, hd) -> Tuple[Tuple[str, ...], str]:
        """`(runtime bị CẤM, lý do)` theo NĂNG LỰC việc đòi hỏi.

        Đây là bản thay thế đúng tầng cho `_runtime_codex_neu_hinh_dang_bao_mat`:
        thay vì quét từ khoá trên cả gói việc đã render (nơi chữ "quyền" của
        lời nhắc công cụ làm MỌI việc thành "bảo mật"), nó hỏi
        `nang_luc.nang_luc_viec()` — thứ chỉ đọc phần NGƯỜI VIẾT và dùng cụm
        từ chuyên môn — rồi đối chiếu với khai báo TỪ CHỐI của từng chỗ chạy.

        Rào này là CỨNG: gửi việc tới một chỗ đã khai từ chối nó là tốn một
        lượt để nhận về đúng một lời từ chối.
        """
        try:
            from scripts.control_center import nang_luc as NL
            can = NL.nang_luc_viec(hd if isinstance(hd, dict) else {})
            if not can:
                return (), ""
            fab = getattr(getattr(ctx, "sessions", None), "fabric", None)
            if fab is None:
                return (), ""
            cam = NL.runtime_khong_tuong_thich(fab, can, self._cau_hinh_fabric())
            if not cam:
                return (), ""
            return cam, NL.ly_do_khong_hop(", ".join(cam), can)
        except (ImportError, AttributeError, TypeError):
            return (), ""

    def _cam_runtime_da_tu_choi(self, hd) -> Tuple[str, ...]:
        """Chỗ chạy đã TỪ CHỐI việc này ở một lượt trước — cấm hẳn.

        Nguồn là `_cam_runtime` do `_dinh_tuyen_lai` ghi vào hợp đồng. Một
        chỗ đã từ chối sẽ từ chối y hệt; gửi lại là tốn một lượt để nhận về
        cùng một câu.
        """
        if not isinstance(hd, dict):
            return ()
        return tuple(sorted({str(x) for x in (hd.get("_cam_runtime") or [])
                             if str(x)}))

    def _runtime_codex_neu_hinh_dang_bao_mat(self, ctx, hd) -> tuple:
        """Runtime Codex cần TRÁNH khi gói việc mang hình dạng bảo mật.

        Codex TỪ CHỐI loại việc này (bằng chứng 2026-08-28, và
        `pool/adapters.py` chặn sẵn ở phía Router). Trước bản này, phép chặn
        đó chỉ xảy ra SAU khi đã xếp chỗ: việc bị `blocked` với lý do
        `codex_security_shaped_refusal`, mà lý do đó lại nằm trong
        `KHONG_THU_LAI` — nên việc CHẾT ở đó, dù thông báo hứa "định tuyến
        sang worker khác". Đo được ở nghiệm thu probe: `fanfic.t78ce-1`
        BLOCKED, 0 việc chạy.

        Nặng hơn thế: lời nhắc công cụ tiêu chuẩn của mọi việc đều chứa chữ
        "quyền", nên GẦN NHƯ MỌI việc xếp vào Codex đều rơi vào đây.

        Nên: kiểm hình dạng TRƯỚC khi xếp chỗ và tránh Codex ngay — tránh là
        ưu tiên chứ không phải rào, `decide()` vẫn rơi về như cũ khi không
        còn chỗ nào khác.
        """
        try:
            from scripts.router_v3.pool.adapters import _HINH_DANG_BAO_MAT
        except ImportError:
            return ()
        # `str(dict)` la du de quet TU KHOA, va khong keo theo mot import
        # `json` ma tep nay khong co — ban dau dung `json.dumps` o day, va
        # `except Exception` da NUOT gon NameError, tat lang le ca tinh nang.
        # Bai kiem `test_hop_dong_bao_mat_thi_TRANH_codex` bat duoc.
        tho = str(hd or "").lower()
        if not any(k in tho for k in _HINH_DANG_BAO_MAT):
            return ()
        fab = getattr(getattr(ctx, "sessions", None), "fabric", None)
        if fab is None:
            return ()
        try:
            return tuple(sorted(
                r.runtime_id for r in fab.runtimes.values()
                if str(getattr(r, "provider", "")).lower() == "codex"))
        except (AttributeError, TypeError):
            return ()

    def _runtime_anh_em_dang_chay(self, t: Task) -> tuple:
        """Runtime mà các việc con CÙNG CHA đang chạy — để con này tránh."""
        toa = (t.contract or {}).get("_toa") or {}
        if not toa or toa.get("cha") or not t.parent_id:
            return ()
        ra = set()
        try:
            for x in self.store.tasks(t.project_id, states=(TaskState.RUNNING,)):
                if x.parent_id != t.parent_id or not x.owner_session:
                    continue
                s = self.store.session(x.owner_session)
                if s is not None and s.runtime_id:
                    ra.add(s.runtime_id)
        except Exception:                                   # noqa: BLE001
            return ()
        return tuple(sorted(ra))

    def _tong_hop_toa(self, ctx: ProjectContext, cha_id: str) -> Optional[Dict]:
        """Mọi con đã kết thúc -> gộp vào cha, khử trùng, giữ nguồn gốc.

        Con BLOCKED (cần người) hay còn chạy/chờ thì cha CHỜ — không gộp nửa
        chừng. Hai con xong cùng lúc gọi vào đây cùng lúc: khoá + kiểm lại
        trạng thái cha, chỉ một lượt gộp.
        """
        from scripts.control_center import toa as TOA
        with self._khoa_toa:
            cha = self.store.task(cha_id)
            if cha is None:
                return None
            toa = (cha.contract or {}).get("_toa") or {}
            if not toa.get("cha") or cha.state in (TaskState.DONE, TaskState.FAILED):
                return None
            con = [self.store.task(cid) for cid in (toa.get("con") or [])]
            con = [c for c in con if c is not None]
            if not con or any(c.state not in (TaskState.DONE, TaskState.FAILED) for c in con):
                return None
            ds = []
            for c in con:
                s = self.store.session(c.owner_session) if c.owner_session else None
                ds.append({"task_id": c.task_id, "state": c.state.value, "result": c.result,
                           "chi_so": ((c.contract or {}).get("_toa") or {}).get("chi_so"),
                           "runtime": s.runtime_id if s else "",
                           "owner_session": c.owner_session})
            th = TOA.tong_hop(cha.to_dict(), ds)
            kq = dict(cha.result or {})
            kq["toa"] = th
            kq["envelope"] = {
                "status": "ok" if th["xong"] else "failed",
                "summary": TOA.soan_tong_hop(th),
                "worker": "control-center", "model": "", "provider": "control-center",
                "failure_reason": "" if th["xong"] else "moi_con_deu_hong",
                "findings": [m["ung_vien"] for m in th["ung_vien"]][:20]}
            self.store.ghi_ket_qua(cha_id, result=kq)
            moi = TaskState.DONE if th["xong"] > 0 else TaskState.FAILED
            try:
                self.store.doi_trang_thai(cha_id, TaskState.RUNNING, force=True,
                                          reason="tổng hợp việc con")
                self.store.doi_trang_thai(cha_id, moi,
                                          reason=f"{th['xong']}/{th['so_con']} việc con xong")
            except TransitionError:
                self.store.doi_trang_thai(cha_id, moi, force=True,
                                          reason=f"{th['xong']}/{th['so_con']} việc con xong")
            self.store.ghi_su_kien(
                "TOA_AGGREGATED", project_id=cha.project_id, task_id=cha_id,
                level="INFO" if th["xong"] else "ERROR",
                detail=(f"{th['xong']}/{th['so_con']} con xong · {len(th['ung_vien'])} kết quả "
                        f"· khử {th['trung_da_bo']} trùng"),
                meta={"xong": th["xong"], "hong": th["hong"], "ung_vien": len(th["ung_vien"]),
                      "trung": th["trung_da_bo"],
                      "runtimes": sorted({c["runtime"] for c in th["con"] if c["runtime"]})})
        try:
            self._bao_ket_qua_ve_chat(ctx, cha_id)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "RESULT_TO_CHAT_FAILED", project_id=cha.project_id, task_id=cha_id,
                level="WARNING", detail=f"{type(exc).__name__}: {exc}"[:300])
        try:
            self._leader_tom_tat_toa(cha.project_id, th)
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "TOA_LEADER_SUMMARY_FAILED", project_id=cha.project_id, task_id=cha_id,
                level="WARNING", detail=f"{type(exc).__name__}: {exc}"[:300])
        return th

    def _leader_tom_tat_toa(self, project_id: str, th: Dict) -> None:
        """Leader (nếu đang mở) tóm tắt kết quả cuối cho người dùng — MỘT lượt,
        trên phiên ấm đã có. Không mở phiên mới chỉ để tóm tắt."""
        from scripts.control_center import toa as TOA
        if not self.leader_bat:
            return
        with self._khoa_leader:
            ph = self._leader_phien.get(project_id)
        if ph is None or not getattr(ph, "song", False):
            return
        nn = (leader.HUONG_DAN + "\n\n" + leader.RANH_GIOI
              + "\n--- BẮT ĐẦU DỮ LIỆU: TỔNG HỢP KẾT QUẢ CÁC VIỆC CON (do worker sinh) ---\n"
              + TOA.soan_tong_hop(th)
              + "\n--- HẾT DỮ LIỆU ---\n\n=== TIN NHẮN MỚI CỦA NGƯỚI DÙNG (đây là yêu cầu THẬT) ===\n"
              + f"Tóm tắt cho tôi {th['xong']}/{th['so_con']} kết quả ở trên thành vài dòng: "
                "giữ đúng số, nêu từng kết quả kèm mã việc con, nói rõ con nào hỏng. "
                "KHÔNG bịa thêm kết quả. y_dinh CHAT, actions [reply_only].\n\n"
                "Trả lời bằng ĐÚNG một khối JSON như đã mô tả.")
        van = ph.hoi(nn)
        qd = leader.doc_quyet_dinh(van)
        if qd.reply:
            self.store.them_chat(project_id, "assistant", qd.reply,
                                 meta={"loai": "toa_tom_tat", "cha": th.get("cha"),
                                       "so_con": th.get("so_con"), "xong": th.get("xong")})

    def _dat_review(self, ctx: ProjectContext, task_id: str,
                    hd: TaskContract, p: Placement) -> None:
        """Đặt một việc REVIEW ĐỘC LẬP làm CON của việc vừa xong.

        VÌ SAO PHẢI CÓ: không có bước này, `REVIEW` là ngõ cụt — việc xong,
        hợp đồng đòi review, và nó nằm đó mãi mãi. Một trạng thái không ai
        đưa ra khỏi được thì tệ hơn là không có trạng thái đó.

        ĐỘC LẬP THẬT, không chỉ trên danh nghĩa: `hop_dong_review()` của
        Router V4 loại HỌ MODEL của tác giả (`exclude_families`) và KHÔNG
        cấp `repo_write`. Một reviewer cùng họ với tác giả, hoặc sửa được
        thứ nó vừa chấm, không phải kiểm tra độc lập.

        Việc review là CON (`parent_id`) chứ không phải anh em: nó không tồn
        tại nếu không có việc cha, và bảng điều khiển phải xếp nó dưới cha
        thay vì thành một dòng lơ lửng không ai hiểu từ đâu ra.
        """
        try:
            ho = ctx.fabric.model(p.model_id).model_family
        except KeyError:
            ho = ""
        rid = f"{task_id}-review"
        if self.store.task(rid) is not None:
            return                            # da dat roi — khong nhan doi
        try:
            hd_review = hop_dong_review(hd, author_family=ho, review_id=rid)
        except (ContractError, ValueError) as exc:
            self.store.ghi_su_kien(
                "REVIEW_SKIPPED", project_id=ctx.project.project_id,
                task_id=task_id, level="WARNING",
                detail=f"không dựng được hợp đồng review: {exc}"[:300])
            return

        cha = self.store.task(task_id)
        d = hd_review.to_dict()
        # Reviewer phai DOC duoc ket qua no dang cham. Voi viec CO GHI, ket
        # qua nam trong worktree co lap, KHONG nam o goc kho — bang chung
        # that 2026-09-03: mot nut review bao "khong tim thay tep" trong khi
        # tep CO ton tai, chi la o worktree cua nut truoc.
        if cha is not None and cha.worktree:
            d["objective"] += (
                f"\n\nĐỌC KẾT QUẢ Ở ĐÂY (không phải ở gốc kho): "
                f"{cha.worktree}\nnhánh: {cha.branch}")
        self.store.luu_task(Task(
            task_id=rid, project_id=ctx.project.project_id,
            title=f"review độc lập: {(cha.title if cha else task_id)}"[:120],
            objective=d["objective"], state=TaskState.QUEUED,
            priority=(cha.priority - 1 if cha else 40),
            parent_id=task_id, dependencies=(task_id,), contract=d,
            permission=PermissionClass.AUTO.value))
        self.store.ghi_su_kien(
            "REVIEW_QUEUED", project_id=ctx.project.project_id, task_id=rid,
            detail=(f"review độc lập cho {task_id}; loại họ model "
                    f"{ho or '(không rõ)'} để tác giả không tự chấm bài"),
            meta={"parent": task_id, "exclude_family": ho})

    #: Ly do hong KHONG BAO GIO duoc thu lai tu dong.
    #:
    #: `security_gate` lay thang tu Router V4: thu lai chi tang co hoi lot
    #: mot thay doi chua thu giong credential (xem `orchestrator.py`).
    #: `tool_permission_denied` la mot buc tuong CAU HINH — chay lai y het
    #: se bi tu choi y het, chi ton them mot luot quota.
    KHONG_THU_LAI = frozenset({
        "security_gate", "requires_decision", "tool_permission_denied",
        "codex_security_shaped_refusal", "no_eligible_placement",
        # `repo_path` khong phai kho git: doi nha cung cap khong sua duoc
        # gi ca, va moi luot thu lai chi tao them mot phien vo ich.
        "project_repo_invalid",
    })

    #: Ly do KHONG PHU THUOC CHO CHAY — hong o day thi hong o mọi nơi.
    #:
    #: CHI nhung ly do nay moi bi phep "hong y het thi thoi" ap dung. Danh
    #: sach HEP co chu y, va day la ly do:
    #:
    #: Mot lan hong LAP LAI chua chac la loi cau hinh. Hai tai khoan cung
    #: het quota van co the con tai khoan thu ba; hai lan `timeout` van co
    #: the do may ban nhat thoi. Chan thu lai trong nhung truong hop do
    #: chinh la chế độ hỏng "bao FAILED trong khi mot nha cung cap khoe
    #: khac dang lam duoc" — doi mot bao thu lai lay mot loi bo sot.
    #:
    #: Nen: chi chan khi ly do TU NO da noi "day la cau hinh".
    LY_DO_KHONG_PHU_THUOC_CHO = frozenset({
        "session_start_failed",     # switch/launcher/thong dich hong
        "no_model_pinned",          # fabric chua ghim model
        "executor_error",           # hop dong/worktree hong truoc khi chay
        "no_session",               # ban cu cua `session_start_failed`
    })

    #: Thu PHAI bo khoi chu ky vi no doi theo TUNG CHO CHAY, khong theo
    #: ban chat cua loi. Danh tinh tai khoan la cai quan trong nhat: thong
    #: diep that cua adapter la "switch acc1 hỏng: …", nen cung mot loi cau
    #: hinh o AG01/AG02/AG03 ra BA chu ky khac nhau va phep so KHONG BAO
    #: GIO khop — tuc la rao chong bao thu lai chet lang le, dung cho lop
    #: loi no duoc viet ra de chan.
    _XOA_KHOI_CHU_KY = re.compile(
        r"\bacc\d+\b"                      # acc1, acc2, … (danh tinh)
        r"|\bAG\d{2}\b"                    # AG01, AG02, …  (khe)
        r"|\bs-[0-9a-f]{6,}\b"             # id phien
        r"|\b\d+(?:\.\d+)?s\b"             # so giay
        r"|\b(?:19|20)\d{2}-\d{2}-\d{2}\b"  # ngay thang
        r"|\b\d{4,}\b",                    # pid, cong, moc thoi gian
        re.IGNORECASE)

    @classmethod
    def _chu_ky_hong(cls, pb) -> str:
        """Chữ ký NGẮN của một lần hỏng, để so hai lượt với nhau.

        Gồm `failure_reason` và phần ĐẦU của câu tóm tắt, sau khi đã **bỏ
        mọi thứ đổi theo chỗ chạy** — tên tài khoản, mã khe, id phiên, số
        giây, pid. Không chuẩn hoá thì phép so vô dụng: adapter Antigravity
        ghi `f"switch {self._acc} hỏng: …"`, nên đúng một lỗi cấu hình ở
        AG01/AG02/AG03 ra ba chữ ký khác nhau, không chữ ký nào khớp chữ ký
        nào, và rào chống bão thử lại **không bao giờ nổ**.

        Cắt phần đầu chứ không lấy cả câu cũng vì thế: đuôi câu hay mang
        đường dẫn tạm và mã băm chỉ sống một lượt.
        """
        ly_do = (getattr(pb, "failure_reason", "") or "").strip()
        tom = " ".join((getattr(pb, "summary", "") or "").split())
        tom = cls._XOA_KHOI_CHU_KY.sub("·", tom)[:80]
        return f"{ly_do}|{tom}" if (ly_do or tom) else ""

    def _lan_hong_truoc(self, task_id: str) -> Dict:
        """Meta của lần hỏng TRƯỚC lần vừa xong.

        BỎ QUA bản ghi đầu tiên có chủ ý: `TASK_FINISHED` của lượt hiện tại
        đã được ghi TRƯỚC khi đường thử lại chạy, nên bản ghi mới nhất
        chính là lượt đang xét. So nó với chính nó thì lượt thử lại đầu
        tiên nào cũng bị từ chối.
        """
        hong = []
        for e in self.store.su_kien(task_id=task_id, limit=40):
            if e.get("kind") != "TASK_FINISHED":
                continue
            m = e.get("meta") or {}
            if m.get("ok") or not m.get("fail_sig"):
                continue
            hong.append(m)
            if len(hong) >= 2:
                break
        return hong[1] if len(hong) >= 2 else {}

    def _doi_soat_khai_thieu(self, ctx: "ProjectContext", task_id: str,
                             hd: TaskContract, kq: ExecutionResult) -> bool:
        """ĐỐI SOÁT lời khai thiếu với TRẠNG THÁI THẬT — vẫn FAIL CLOSED.

        Đây KHÔNG phải hạ cổng `diff` xuống mức cảnh báo. Cổng đó giữ nguyên
        trong Router V4, không sửa một dòng. Ở đây Control Center làm một
        việc KHÁC và CHẶT HƠN: thay vì tin danh sách worker khai, nó lấy
        danh sách THẬT từ `git` rồi kiểm lại chính danh sách đó.

        Chỉ áp đúng MỘT trường hợp hẹp — cái mà `cong_diff` gọi là "worker
        không khai sửa gì nhưng đĩa đổi":

            worker báo `ok`  +  `changes` RỖNG  +  đĩa CÓ đổi
            +  cổng `diff` là cổng DUY NHẤT hỏng

        Mọi trường hợp khác giữ nguyên `FAILED`. Đặc biệt KHÔNG đụng tới
        chiều ngược lại ("khai có sửa mà đĩa SẠCH") — đó là thất bại im lặng
        thật sự, và nó phải hỏng.

        Điều kiện để CHẤP NHẬN, tất cả phải đúng:

          1. mọi tệp đổi THẬT nằm trong `allowed_scope` và không chạm
             `forbidden_scope` (`TaskContract.scope_violations`, hàm thuần);
          2. `scope_violations` do tầng kiểm định tính cũng rỗng;
          3. cổng `security` ĐẠT — nó vốn đã chạy trên diff THẬT của đĩa
             (`_diff_van_ban` đọc cả tệp chưa theo dõi), nên nó là phán
             quyết trên tập THẬT chứ không phải trên lời khai;
          4. mọi cổng khác (`shape`, `scope`, `tests`, `artifacts`, …) ĐẠT.

        Một tệp đổi ngoài phạm vi ⇒ TỪ CHỐI, việc ở lại `FAILED`. Đó chính
        là chỗ bất biến được giữ: chấp nhận ở đây KHÔNG BAO GIỜ dựa vào lời
        khai, và không bao giờ bỏ qua một thay đổi chưa được kiểm.

        Trả `True` nghĩa là đã đối soát xong và việc được đi tiếp; lúc đó
        `changes` trong phong bì được ĐIỀN LẠI bằng tập THẬT, để mọi báo cáo
        về sau nói đúng thứ đã xảy ra.
        """
        bc = kq.validation
        if bc is None or bc.passed:
            return False
        if bc.failed_gates != ["diff"]:
            return False                    # con cong khac hong -> giu FAILED

        pb = kq.envelope
        that = sorted({str(t).replace("\\", "/").strip("/")
                       for t in bc.files_changed_observed if t})
        # ĐĨA PHẢI CÓ ĐỔI. Chiều ngược lại ("khai có sửa mà đĩa SẠCH") là
        # thất bại im lặng thật sự và KHÔNG BAO GIỜ được chấp nhận ở đây —
        # nhánh đó đã bị `cong_diff` chặn và ta không đụng tới.
        if not that:
            return False
        # KHÔNG tự suy lại "worker có khai gì không" từ `pb.changes`.
        #
        # ĐÂY LÀ KHUYẾT TẬT ĐÃ LÀM HỎNG CẢ MỘT ĐỢT NGHIỆM THU THẬT, và nó
        # nằm hoàn toàn trong mã của ta chứ không phải ở nhà cung cấp:
        #
        # `cong_diff` phán "worker không khai sửa gì" dựa trên `TaskResult.
        # files_changed` — một bản ĐÃ LỌC, chỉ giữ thứ trông như đường dẫn.
        # Hàm này lại đọc `pb.changes` THÔ. Khi model điền vào `changes` một
        # CÂU MÔ TẢ ("Tạo docs/reports/x.md với tiêu đề, 4 gạch đầu dòng…")
        # thay vì một đường dẫn, hai cái nhìn lệch nhau: cổng thấy RỖNG nên
        # nó báo khai thiếu, còn hàm này thấy CÓ nên nó từ chối đối soát —
        # và một việc LÀM ĐÚNG bị đánh hỏng.
        #
        # ĐO ĐƯỢC (Fanfic thật, 2026-09-12): 9/9 lượt worker ghi ĐÚNG tệp,
        # đúng phạm vi, `scope`/`security`/`artifacts` đều xanh, `diff` là
        # cổng DUY NHẤT hỏng — và cả 9 đều `FAILED`.
        #
        # GỐC RỄ của 9 lần đó đã được sửa Ở CHỖ KHÁC và nó còn tầm thường
        # hơn: `parse_result` của V3 chỉ đọc `files_changed`, trong khi lời
        # nhắc của Control Center BẮT BUỘC worker khai vào `changes`. Cổng
        # chấm worker trên một trường mà chính ta không bao giờ yêu cầu nó
        # điền, nên MỌI việc ghi đều hỏng một cách tất định — không phải may
        # rủi theo nhà cung cấp. Xem `router_v3/packet.py::parse_result`.
        #
        # Hàm này VẪN cần thiết sau khi sửa gốc: khi model điền `changes`
        # bằng một CÂU MÔ TẢ thay vì đường dẫn (đã thấy thật), lời khai và
        # đĩa vẫn lệch nhau, và đây là nơi đối soát trên tập THẬT.
        #
        # Nguồn sự thật DUY NHẤT về việc worker đã khai gì LÚC QUA CỔNG là
        # chính thông điệp của cổng, và nó được khớp ngay dưới đây.
        # KHONG duoc hoi `pb.status` o day — no da BI GHI DE.
        #
        # `Executor.run` dat `pb.status = "failed"` va
        # `failure_reason = f"gate_{hong[0]}"` NGAY KHI bat ky cong nao hong
        # (executor.py). Nen dieu kien "worker bao ok" khong bao gio con dung
        # o dau ra cua Executor, va ban truoc cua ham nay CHET CUNG tren
        # duong that: no luon thoat o day. Bai kiem cu khong bat duoc vi no
        # tu dung mot `ResultEnvelope(status="ok")` canh mot cong `diff`
        # hong — mot to hop production khong sinh ra.
        #
        # Nguon su that con lai la CHINH CONG `diff`: thong diep duoi day chi
        # duoc sinh o DUNG mot nhanh cua `cong_diff`, nhanh doi hoi
        # `kq.status == "ok" and not khai and that`. Nen khop no la khop
        # chinh xac dieu kien can, khong phai doan.
        #
        # `test_thong_diep_cong_diff_khong_doi` khoa lai chuoi nay: neu V4
        # doi loi van, bai kiem do hong NGAY thay vi doi soat am tham chet.
        chi_tiet = next((g.detail for g in bc.gates
                         if g.name == "diff" and not g.passed), "")
        if not chi_tiet.startswith(DAU_HIEU_KHAI_THIEU):
            return False

        vi_pham = sorted(set(hd.scope_violations(that))
                         | set(bc.scope_violations))
        if vi_pham:
            self.store.ghi_su_kien(
                "UNDERDECLARED_CHANGES_REJECTED",
                project_id=ctx.project.project_id, task_id=task_id,
                level="ALERT",
                detail=(f"worker không khai gì, và {len(vi_pham)} tệp đổi "
                        f"THẬT nằm NGOÀI phạm vi — giữ FAILED"),
                meta={"actual": that[:50], "violations": vi_pham[:50]})
            return False

        # Bat buoc moi cong con lai DAT (gom `security`, da chay tren diff
        # THAT cua dia). `failed_gates == ["diff"]` o tren da bao dam dieu
        # nay; kiem lai tuong minh de mot lan sua ve sau khong lam mat no.
        khong_dat = [g.name for g in bc.gates
                     if not g.passed and g.name != "diff"]
        if khong_dat:
            return False

        pb.changes = that                   # bao cao noi dung THAT
        # VA CA TRANG THAI. Day la ve thu hai, va thieu no thi ca cuoc doi
        # soat chi chua duoc mot nua:
        #
        # Ben goi (`_chay`) dung ket qua `True` de nang TRANG THAI VIEC len
        # `DONE`, nhung phong bi thi VAN mang `status="failed"` +
        # `failure_reason="gate_diff"`. Hai cai nhin ve CUNG mot su that lai
        # noi nguoc nhau, va moi tang doc sau do doc phai cai sai:
        #   * `HopDongKetQua` dung tu phong bi -> `status="failed"` -> tang
        #     BUOC ket luan buoc HONG va di sua chua, DU viec da `DONE`;
        #   * su kien phien in ra "việc hỏng; phiên giữ ấm để dùng lại" ngay
        #     duoi mot dong `TASK_FINISHED DONE`.
        # Do duoc (Fanfic that, ex_ca0dc426af20): `ghi_tailieu` DAT doi soat
        # ba lan lien tiep, ba lan deu `RUNNING -> DONE`, va ca ba lan tang
        # buoc van xep KHONG_DAT roi sua chua -> lap lai ke hoach -> BLOCKED.
        # Tep da nam tren dia voi dung dau xac nhan tu lan dau.
        #
        # Da doi soat tren tap THAT va moi cong khac deu dat, nen ket luan
        # dung la "viec NAY xong". Giu `failed` o day la mot loi khai sai do
        # CHINH ta viet ra, khong phai loi cua worker.
        pb.status = "ok"
        pb.failure_reason = ""
        pb.warnings.append(
            f"worker KHÔNG khai `changes` nhưng đĩa đổi {len(that)} tệp. "
            f"Đã đối soát với `git`: mọi tệp đều trong phạm vi và mọi cổng "
            f"khác đều đạt, nên việc được tính là xong. Danh sách `changes` "
            f"đã được điền lại bằng tập THẬT.")
        self.store.ghi_su_kien(
            "UNDERDECLARED_CHANGES", project_id=ctx.project.project_id,
            task_id=task_id, level="WARNING",
            detail=(f"khai 0 tệp, đĩa đổi {len(that)} tệp — đã đối soát và "
                    f"kiểm lại phạm vi/bảo mật trên tập THẬT"),
            meta={"declared": [], "actual": that[:50],
                  "gates": [g.name for g in bc.gates if g.passed]})
        return True

    def _viec_dang_co_lease(self, ctx: "ProjectContext") -> set:
        """`task_id` nao dang giu mot lease Router V4 CON HAN.

        Day la tin hieu LIEN TIEN TRINH dang tin duy nhat: lease song trong
        SQLite, co TTL va nhip tim, va chu cua no dap nhip trong khi luot
        agent dang bay. Mot tien trinh Control Center thu hai doc duoc no, va
        nho vay biet dung dung vao viec cua tien trinh thu nhat.

        Khong doc duoc so lease thi tra tap RONG co chu dich: luc do
        `recover()` quay ve hanh vi cu (dua tren phien), tuc than trong theo
        chieu "coi la mo coi". Chieu do chi mat mot luot; chieu nguoc lai la
        hai agent cung ghi mot cay.
        """
        try:
            return {l.task_id for l in ctx.leases.all()
                    if l.task_id and l.con_han()}
        except Exception:                                 # noqa: BLE001
            return set()

    def _nha_khoa_mo_coi(self, project_id: str) -> List[str]:
        """BẤT BIẾN: một khoá chỉ được giữ bởi một việc ĐANG CHẠY.

        Chủ khoá ở bất kỳ trạng thái nào khác — `BLOCKED`, `FAILED`, `DONE`,
        `QUEUED`, `WAITING` — là khoá MỒ CÔI: việc giữ nó đã không còn chạy,
        nhưng khoá vẫn chặn mọi việc khác cho tới hết TTL (1 giờ).

        Vì sao cần RIÊNG chỗ này chứ không chỉ nhả lúc gỡ việc mồ côi khỏi
        `RUNNING`: một lượt `recover()` TRƯỚC ĐÓ có thể đã chuyển việc sang
        `BLOCKED` mà chưa nhả khoá (đúng thứ đã xảy ra 2026-09-08). Từ đó
        việc không còn ở `RUNNING` nữa nên vòng lặp kia không bao giờ thấy
        nó, và khoá kẹt lại vĩnh viễn. Kiểm theo TRẠNG THÁI CHỦ KHOÁ bắt
        được cả hai trường hợp.

        THẬN TRỌNG: `_giao()` giành khoá TRƯỚC khi `claim_task` lật việc
        sang `RUNNING`. Nên chỉ nhả khi việc đó cũng KHÔNG nằm trong
        `_dang_chay` — nếu không sẽ cướp khoá của một việc đang được giao.
        """
        with self._khoa:
            bay = set(self._dang_chay)
        # Viec dang co lease SONG = dang chay o mot tien trinh khac. Khoa cua
        # no khong phai khoa mo coi.
        try:
            bay |= self._viec_dang_co_lease(self.ctx(project_id))
        except Exception:                                 # noqa: BLE001
            pass
        lm = LockManager(self.store)
        da_nha: List[str] = []
        for l in self.store.locks(project_id):
            # KHOA PRODUCTION KHONG BAO GIO TU VE — ke ca o day.
            #
            # `LockKind.tu_thu_hoi_duoc` la mot bat bien cua ca he, khong
            # phai mot chi tiet cua `reclaim()`. Mot khoa production "mo coi"
            # co the la mot cutover dang chay lau hon du kien; doan sai la
            # tha viec thu hai vao giua no. Bao cho nguoi, dung tu nha.
            # (Da vap: ban dau ham nay nha ca khoa production va lam hong
            # dung bai kiem giu bat bien do.)
            if not l.kind.tu_thu_hoi_duoc:
                continue
            if not l.holder_task or l.holder_task in bay:
                continue
            t = self.store.task(l.holder_task)
            if t is None:
                # Chu khoa khong con ton tai -> chac chan mo coi.
                pass
            elif t.state is TaskState.RUNNING:
                continue
            if self.store.xoa_lock(l.lock_id, holder_task=l.holder_task):
                da_nha.append(l.lock_id)
                self.store.ghi_su_kien(
                    "LOCK_ORPHANED", project_id=project_id,
                    task_id=l.holder_task, level="WARNING",
                    detail=(f"nhả khoá mồ côi {l.kind.value} {l.resource!r} — "
                            f"chủ đang ở "
                            f"{t.state.value if t else '(không còn)'}, "
                            f"không phải RUNNING"))
        return da_nha

    #: Lý do TỪ CHỐI vì CHÍNH SÁCH/NĂNG LỰC — an toàn để định tuyến lại.
    #:
    #: Khác hẳn một lần việc hỏng thật: chỗ chạy không hề THỬ làm việc, nó từ
    #: chối nhận. Chạy lại y hệt ở chỗ ĐÓ thì vô ích, nhưng chạy ở chỗ KHÁC
    #: thì đúng — và thông báo từ chối vốn đã hứa như vậy.
    LY_DO_DINH_TUYEN_LAI = frozenset({"codex_security_shaped_refusal"})

    #: Trần định tuyến lại. Hẹp có chủ ý: nếu hai chỗ khác nhau đều từ chối
    #: thì đó là chuyện của phân loại việc, không phải chuyện thiếu chỗ chạy.
    MAX_DINH_TUYEN_LAI = 2

    def _dinh_tuyen_lai(self, ctx: ProjectContext, t: Task, ly_do: str,
                        cho_cu: str) -> bool:
        """Nhả chỗ rồi xếp lại việc sang chỗ chạy TƯƠNG THÍCH. `True` nếu đã xếp.

        Giữ NGUỒN GỐC đầy đủ trong hợp đồng (`_dinh_tuyen_lai`): chỗ ban đầu,
        lý do từ chối, lần thứ mấy — để người đọc sau biết việc đã đi qua đâu
        chứ không thấy một việc "tự nhiên chạy ở chỗ khác".
        """
        hd = dict(t.contract or {})
        ls = list(hd.get("_dinh_tuyen_lai") or [])
        if len(ls) >= self.MAX_DINH_TUYEN_LAI:
            return False
        ls.append({"tu_runtime": cho_cu, "ly_do": ly_do,
                   "lan": len(ls) + 1, "luc": time.time()})
        hd["_dinh_tuyen_lai"] = ls
        # Cho da TU CHOI thi lan sau CAM, khong phai "tranh": no se tu choi
        # y het, va mot luot nua chi de nhan lai mot loi tu choi.
        hd["_cam_runtime"] = sorted({str(x.get("tu_runtime") or "")
                                     for x in ls if x.get("tu_runtime")})
        t.contract = hd
        if t.owner_session:
            ctx.sessions.dung(
                t.owner_session, state=SessionState.STOPPED,
                reason=f"định tuyến lại {t.task_id}: {cho_cu} từ chối ({ly_do})")
        t.owner_session = ""
        self.store.luu_task(t)
        self.store.doi_trang_thai(
            t.task_id, TaskState.QUEUED, force=True,
            reason=(f"định tuyến lại lần {len(ls)}/{self.MAX_DINH_TUYEN_LAI} — "
                    f"{cho_cu} từ chối vì {ly_do}"))
        self.store.ghi_su_kien(
            "REROUTE_QUEUED", project_id=t.project_id, task_id=t.task_id,
            detail=(f"{cho_cu} TỪ CHỐI ({ly_do}) — nhả phiên, cấm chỗ đó và "
                    f"xếp lại (lần {len(ls)}/{self.MAX_DINH_TUYEN_LAI})"),
            meta={"tu_runtime": cho_cu, "ly_do": ly_do, "lan": len(ls),
                  "cam": hd["_cam_runtime"]})
        return True

    def _thu_lai_neu_dang(self, ctx: ProjectContext, task_id: str, pb,
                          session_id: str, placement_key: str = "") -> None:
        """Thử lại một việc hỏng — CÓ TRẦN, và đổi chỗ chạy.

        VÌ SAO CẦN: `Executor.run()` chạy đúng MỘT lượt. Đường thử lại của
        Router V4 nằm trong `RouterV4._chay_co_thu_lai`, mà Control Center cố
        ý không đi qua (nó cần giữ placement của phiên). Không có gì ở đây
        thì một lần nhà cung cấp hắt hơi là việc hỏng vĩnh viễn — với một hệ
        chạy qua đêm không người trực, đó là chế độ hỏng thường gặp nhất.

        VÌ SAO PHẢI CÓ TRẦN: thử lại vô hạn là "bão thử lại", đúng chế độ
        hỏng số 4 mà `leases.py` liệt kê. `attempts` do `claim_task` tự tăng
        nên trần này đếm được, không tin vào bộ nhớ.

        VÌ SAO DỪNG PHIÊN: lượt sau phải chạy ở CHỖ KHÁC. Nhả phiên hiện tại
        rồi để `decide()` chọn lại — cùng cơ chế `reassign`, không phải một
        đường định tuyến thứ hai. Lặp lại đúng bài học của V4: "từ lượt 2,
        ĐỔI placement".
        """
        t = self.store.task(task_id)
        if t is None:
            return
        ly_do = (pb.failure_reason or "").strip()

        # HONG Y HET O MOT CHO KHAC = loi khong phu thuoc placement.
        #
        # Thu lai co ich khi lan hong la CUC BO: mot tai khoan het quota,
        # mot tien trinh chet. No vo ich — va ton dung mot luot quota moi
        # lan — khi nguyen nhan nam o CAU HINH, vi luot sau se hong y het.
        # Da vap that (2026-09-09): mot loi `sys.executable` trong ban dong
        # goi lam ba runtime AG01/AG02/AG03 hong lien tiep trong 6 giay,
        # cung mot cau chu.
        #
        # Khong doan xem ly do nao la "tat dinh" — DO. Neu chu ky hong cua
        # lan nay trung lan truoc MA CHO CHAY DA KHAC, thi doi cho nua chi
        # lap lai ket qua.
        ck = self._chu_ky_hong(pb)
        truoc = self._lan_hong_truoc(task_id)
        cho_nay = placement_key or (pb.worker or "")
        if ly_do in self.LY_DO_KHONG_PHU_THUOC_CHO \
                and truoc and ck and truoc.get("fail_sig") == ck \
                and truoc.get("placement") and truoc["placement"] != cho_nay:
            self.store.ghi_su_kien(
                "RETRY_REFUSED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=(f"KHÔNG thử lại: đã hỏng Y HỆT ({ck}) ở "
                        f"{truoc['placement']} rồi ở {cho_nay} — lỗi không "
                        f"phụ thuộc chỗ chạy, đổi chỗ nữa chỉ tốn quota"),
                meta={"fail_sig": ck,
                      "placements": [truoc["placement"], cho_nay]})
            return

        # ĐỊNH TUYẾN LẠI: chỗ chạy TỪ CHỐI vì chính sách/năng lực, không phải
        # vì việc hỏng. Chạy lại ở chỗ KHÁC là đúng và rẻ; điều sai là để việc
        # chết tại chỗ — đúng thứ đã xảy ra với `fanfic.t78ce-1`.
        if ly_do in self.LY_DO_DINH_TUYEN_LAI:
            if self._dinh_tuyen_lai(ctx, t, ly_do, cho_nay):
                return
            self.store.ghi_su_kien(
                "REROUTE_EXHAUSTED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=(f"đã định tuyến lại {self.MAX_DINH_TUYEN_LAI} lần vì "
                        f"{ly_do!r} mà vẫn bị từ chối — để người xem"))
            return

        if ly_do in self.KHONG_THU_LAI or pb.requires_decision:
            self.store.ghi_su_kien(
                "RETRY_REFUSED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=(f"KHÔNG thử lại {ly_do!r} — chạy lại y hệt sẽ hỏng y "
                        f"hệt, chỉ tốn thêm một lượt quota"))
            return
        if t.attempts >= MAX_ATTEMPTS:
            self.store.ghi_su_kien(
                "RETRY_EXHAUSTED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=f"đã cạn {MAX_ATTEMPTS} lượt thử — để người xem")
            return

        if t.owner_session:
            ctx.sessions.dung(
                t.owner_session, state=SessionState.STOPPED,
                reason=f"thử lại {task_id} ở chỗ khác (lượt {t.attempts})")
        t.owner_session = ""
        self.store.luu_task(t)
        self.store.doi_trang_thai(
            task_id, TaskState.QUEUED, force=True,
            reason=(f"thử lại tự động lượt {t.attempts + 1}/{MAX_ATTEMPTS} "
                    f"sau lỗi {ly_do or 'không rõ'}"))
        self.store.ghi_su_kien(
            "RETRY_QUEUED", project_id=t.project_id, task_id=task_id,
            detail=(f"lượt {t.attempts}/{MAX_ATTEMPTS} hỏng ({ly_do}); nhả "
                    f"phiên cũ để lượt sau chọn chỗ khác"))

    def _khep_review(self, t: Task) -> None:
        """Việc review xong -> đóng việc CHA.

        Phát hiện của reviewer KHÔNG tự động làm việc cha thất bại — nó là
        thông tin cho người tích hợp, đúng như `RouterV4.run_task` đã quyết.
        Nhưng nó PHẢI hiện ra: một lượt review tốn tiền mà không ai thấy kết
        quả thì chỉ là đốt quota.
        """
        cha = self.store.task(t.parent_id)
        if cha is None or cha.state is not TaskState.REVIEW:
            return
        pb = ((t.result or {}).get("envelope") or {})
        pham = list(pb.get("findings") or [])
        if t.state is TaskState.FAILED:
            self.store.doi_trang_thai(
                cha.task_id, TaskState.BLOCKED,
                reason=(f"review độc lập ({t.task_id}) không chạy được — "
                        f"kết quả CHƯA được kiểm tra chéo"))
            return
        self.store.doi_trang_thai(
            cha.task_id, TaskState.DONE,
            reason=(f"review độc lập xong: {len(pham)} phát hiện"
                    if pham else "review độc lập không thấy vấn đề"))
        if pham:
            c = self.store.task(cha.task_id)
            if c is not None:
                kq = dict(c.result or {})
                env = dict(kq.get("envelope") or {})
                env["findings"] = list(env.get("findings") or []) + [
                    f"[review/{pb.get('model', '?')}] {x}" for x in pham[:10]]
                kq["envelope"] = env
                c.result = kq
                self.store.luu_task(c)
            self.store.ghi_su_kien(
                "REVIEW_FINDINGS", project_id=cha.project_id,
                task_id=cha.task_id, level="WARNING",
                detail=f"{len(pham)} phát hiện từ review độc lập",
                meta={"findings": pham[:10], "reviewer": pb.get("model", "")})

    def _sang_waiting(self, t: Task, reason: str) -> None:
        if t.state is not TaskState.WAITING:
            try:
                self.store.doi_trang_thai(t.task_id, TaskState.WAITING,
                                          reason=reason[:400])
            except TransitionError:
                pass

    def _muon_lease(self, ctx: ProjectContext, runtime_id: str,
                    task_id: str) -> Optional[str]:
        """Giành MỘT KHE của runtime — cùng ngữ nghĩa `RouterV4._muon_lease`.

        Khoá theo KHE (`AG01#0`), không theo runtime. Bằng chứng thật
        2026-09-03: khoá theo runtime ép AG01 (3 khe) xuống 1 việc một lúc
        và "song song" mất sạch ý nghĩa. Lặp lại đúng ngữ nghĩa ở đây để
        Control Center và một lượt `run_mission` của V4 chạy cạnh nhau mà
        không giao trùng khe.
        """
        r = ctx.fabric.runtimes.get(runtime_id)
        for i in range(max(1, r.concurrency if r else 1)):
            khoa = f"{runtime_id}#{i}"
            if ctx.leases.acquire(khoa, self.owner, task_id=task_id) is not None:
                return khoa
        return None

    # -- 4. Chay mot viec ----------------------------------------------------

    def _chay(self, ctx: ProjectContext, task_id: str, hd: TaskContract,
              p: Placement, session_id: str, khoa_lease: str) -> None:
        """Chạy MỘT việc trên MỘT placement. Chạy trong luồng riêng.

        Không bao giờ để một ngoại lệ thoát ra: luồng này chết im lặng sẽ để
        việc kẹt ở `RUNNING` mãi mãi, khoá không được nhả, và bảng điều
        khiển nói dối. Mọi đường ra đều đi qua `finally`.
        """
        t0 = time.time()
        kq: Optional[ExecutionResult] = None
        lm = LockManager(self.store)
        da_nha_khoa = False          # khoa da nha som (sau trang thai cuoi)?
        nhip = threading.Event()

        def _dap_nhip() -> None:
            # Viec dai hon TTL van phai giu duoc lease VA khoa cua no.
            while not nhip.wait(20.0):
                try:
                    con_giu = ctx.leases.heartbeat(khoa_lease, self.owner)
                    lm.gia_han(ctx.project.project_id, task_id)
                except Exception:                         # noqa: BLE001
                    # `continue`, KHONG `return`. Ban dau cho nay thoat han
                    # sau MOT ngoai le — va `sqlite3.OperationalError:
                    # database is locked` la chuyen binh thuong khi hai tien
                    # trinh Control Center cung ghi. Mot lan nghen o dia the
                    # la giet luon ca vong nhip: `lm.gia_han` ngung chay,
                    # sau LOCK_TTL (3600s) khoa cua viec het han, va mot viec
                    # khac CUOP duoc khoa trong khi agent thu nhat VAN DANG
                    # GHI. Hop dong cho phep `max_wall_time` 2400s cong thu
                    # lai, nen viec chay qua mot tieng khong phai ngoai le.
                    continue
                if con_giu:
                    continue
                # LEASE DA BI CUOP. Hop dong cua `LeaseStore.heartbeat` noi
                # ro: `False` nghia la ta khong con so huu khe do nua.
                #
                # KHONG giet luot dang bay, va day la mot danh doi CO Y CHON,
                # khong phai bo sot: TTL 90s / nhip 20s nghia la phai truot
                # BON nhip lien tiep moi mat lease — gan nhu chac chan la mot
                # lan SQLite kho tho, khong phai mot bo lap lich thu hai that
                # su. Giet mot luot agent dang chay dung 60 giay vi mot cai
                # nac cua o dia la doi mot hong hiem lay mot hong thuong xuyen.
                #
                # Nhung cung KHONG im lang: neu that su co hai chu, do la
                # dung che do hong ma lease ton tai de chan, va no phai hien
                # ra o muc ALERT chu khong chim trong log. Ngung dap nhip —
                # tiep tuc dap la gia vo con so huu mot thu da mat.
                self.store.ghi_su_kien(
                    "LEASE_LOST", project_id=ctx.project.project_id,
                    task_id=task_id, session_id=session_id, level="ALERT",
                    detail=(f"lease {khoa_lease} đã bị chủ khác giành — việc "
                            f"này KHÔNG còn sở hữu khe đó. Lượt đang bay vẫn "
                            f"chạy nốt (giết nó vì một lần nghẽn sổ còn tệ "
                            f"hơn), nhưng nếu thấy sự kiện này thì CÓ một bộ "
                            f"lập lịch thứ hai đang chạy — kiểm tra ngay."),
                    meta={"lease": khoa_lease, "owner": self.owner})
                return

        tim = threading.Thread(target=_dap_nhip, daemon=True,
                               name=f"cc-hb-{task_id}")
        tim.start()
        try:
            # CONG VAO: `repo_path` cua du an phai la mot kho git THAT.
            #
            # Kiem o day, mot lan, voi mot cau doc duoc — thay vi de
            # `git rev-parse HEAD` ne ra giua duong dieu phoi. Su co that
            # (2026-09-09): mot du an duoc gieo tro vao chinh thu muc EXE
            # (khong phai kho git), va viec dau tien nguoi dung go chet
            # bang `WorktreeError: not a git repository` — mot cau khong
            # noi cho ai biet phai sua gi, o mot cho khong ai ngo toi.
            #
            # Day KHONG phai loi cua nha cung cap: doi sang AG02 hay Codex
            # deu hong y het. Nen no FAILED va khong fallback — nhung phai
            # FAILED voi ly do dung.
            if not la_kho_git(ctx.project.repo_path):
                self.store.ghi_su_kien(
                    "PROJECT_REPO_INVALID", project_id=ctx.project.project_id,
                    task_id=task_id, session_id=session_id, level="ERROR",
                    detail=(f"repo_path của dự án không phải kho git: "
                            f"{ctx.project.repo_path!r}. Router làm việc "
                            f"trên kho git — sửa đường dẫn dự án rồi gửi "
                            f"lại. Không nhà cung cấp nào chạy được việc "
                            f"này, nên KHÔNG chuyển sang chỗ khác."),
                    meta={"repo_path": str(ctx.project.repo_path)})
                self.store.doi_trang_thai(
                    task_id, TaskState.FAILED, force=True,
                    reason=(f"project_repo_invalid: {ctx.project.repo_path!r} "
                            f"không phải kho git"))
                ctx.sessions.ket_thuc_viec(session_id, task_id, ok=False)
                return

            ctx.fabric.mark_started(p.runtime_id, task_id)
            self.store.ghi_su_kien(
                "TASK_STARTED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id,
                detail=f"{p.key} @ {hd.execution.max_wall_time:.0f}s trần")

            # `base_sha` CHI tinh khi viec that su can mot worktree.
            #
            # Truoc day no duoc tinh vo dieu kien, ngay trong danh sach doi
            # so — nen `git rev-parse HEAD` chay cho CA nhung viec CHI DOC
            # khong bao gio cham toi git. Hau qua that (2026-09-09): mot
            # viec `analysis` voi `worktree_required=false` chet vi
            # `WorktreeError: not a git repository` TRUOC KHI
            # `Executor.run()` kip duoc vao — khong adapter nao duoc goi,
            # khong tien trinh nao duoc sinh, `result_json` rong.
            #
            # Mot viec khong can git thi khong duoc phep chet vi git.
            base = (ctx.worktrees.base_sha()
                    if hd.execution.worktree_required else "")
            t_chay0 = time.time()
            kq = ctx.executor.run(
                hd, p, base_sha=base,
                attempt=max(1, (self.store.task(task_id) or Task(
                    task_id, "", "", "")).attempts))
            # KHOANG CHAY THAT cua luot agent (V0.6.1): de do song song thuc
            # su giua cac con — khong suy tu trang thai RUNNING trong so.
            khoang_chay = {"bat_dau": t_chay0, "ket_thuc": time.time(),
                           "runtime": p.runtime_id, "model": p.model_id}

            pb = kq.envelope
            pid = dao_pid(ctx.executor._cache.get(p.key))
            moi = map_envelope_status(
                pb.status,
                need_review=hd.verification.independent_review_required)
            # Cong kiem dinh cua V4 THANG loi khai cua worker. `kq.ok` da gop
            # ca hai; dung `pb.status` mot minh se de mot ket qua "ok" vuot
            # qua mot cong `diff`/`scope` hong.
            if moi is not TaskState.BLOCKED and not kq.ok:
                moi = TaskState.FAILED
                if self._doi_soat_khai_thieu(ctx, task_id, hd, kq):
                    moi = map_envelope_status(
                        "ok",
                        need_review=hd.verification.independent_review_required)

            # UPDATE HEP, khong phai doc-sua-ghi. Xem `store.ghi_ket_qua`:
            # `luu_task` ghi ca cot `state`, nen luu mot doi tuong doc tu
            # TRUOC luot agent se nuot mat mot lenh `pause` nguoi dung vua bam.
            kq_dict = kq.to_dict()
            kq_dict["khoang_chay"] = khoang_chay
            self.store.ghi_ket_qua(task_id, result=kq_dict,
                                   worktree=kq.worktree, branch=kq.branch)

            ly_do = pb.failure_reason or ""
            if pb.requires_decision:
                ly_do = (pb.decision_request or ly_do or
                         "agent yêu cầu một quyết định")
            self.store.doi_trang_thai(task_id, moi, reason=ly_do[:600],
                                      session_id=session_id)
            if moi is TaskState.REVIEW:
                self._dat_review(ctx, task_id, hd, p)
            self.store.ghi_su_kien(
                "TASK_FINISHED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id,
                level=("INFO" if moi in (TaskState.DONE, TaskState.REVIEW)
                       else "ERROR"),
                detail=f"{moi.value} sau {time.time()-t0:.1f}s — {pb.summary}"[:600],
                meta={"status": pb.status, "ok": kq.ok,
                      "raw_log_ref": pb.raw_log_ref, "changes": pb.changes[:20],
                      "findings": pb.findings[:10], "risks": pb.risks[:10],
                      "placement": p.key, "duration": round(pb.duration, 2),
                      "fail_sig": self._chu_ky_hong(pb)})
            # `moi`, khong phai `kq.ok`: sau một cuộc ĐỐI SOÁT đạt, `kq.ok`
            # vẫn `False` (nó đọc cổng `diff` đã hỏng) trong khi việc đã
            # `DONE`. Dùng `kq.ok` ở đây in ra "việc hỏng; phiên giữ ấm" ngay
            # dưới một dòng `TASK_FINISHED DONE` — cùng một sự thật, hai câu
            # trả lời ngược nhau, và người vận hành đọc sổ sẽ tin câu sai.
            ctx.sessions.ket_thuc_viec(
                session_id, task_id,
                ok=moi in (TaskState.DONE, TaskState.REVIEW), pid=pid)
            # NHA KHOA NGAY KHI VIEC DA O TRANG THAI CUOI — truoc khi thu lai,
            # truoc khi bao chat, truoc khi gop vao cha. Hai ly do do that:
            #   * Toa: `_tong_hop_toa` chay TRONG luong cua con cuoi, nen neu
            #     chi nha o `finally` thi cha DONE truoc khi khoa cua con nha
            #     vai ms — bang dieu khien/nghiem thu thay "cha xong ma khoa
            #     con giu" (do 2026-09-10: khoa READ `.` cua con [3/4]).
            #   * Thu lai: `_thu_lai_neu_dang` xep lai viec trong khi luong nay
            #     con giu khoa; luot sau xin lai (cung chu -> duoc), roi
            #     `finally` cua luong nay nha SACH — ke ca khoa luot sau vua
            #     xin. Nha truoc thi khong con cua so do.
            # `tra()` idempotent; `finally` chi nha lai neu chua nha o day.
            lm.tra(ctx.project.project_id, task_id)
            da_nha_khoa = True
            if moi is TaskState.FAILED:
                self._thu_lai_neu_dang(ctx, task_id, pb, session_id,
                                       placement_key=p.key)
            # KET QUA PHAI VE TOI O CHAT. Day la yeu cau CHAN PHAT HANH.
            #
            # Mot huy hieu DONE ma khong co cau tra loi thi khong phai la
            # xong: nguoi dung phai mo tab Logs moi biet chuyen gi da xay
            # ra, va do dung la thu V0.3 sinh ra de bo.
            #
            # Goi SAU khi da ghi trang thai + su kien + da quyet dinh thu
            # lai: neu viec con duoc thu lai thi chua phai luc bao ket qua.
            #
            # BOC RIENG. Loi goi nay nam trong `try` lon cua `_chay`, ma
            # nhanh `except` cua no EP viec sang FAILED bang `force=True`.
            # Mot ngoai le trong buoc dang chat (dia day, so kho tho) se
            # lat mot viec DA XONG thanh HONG — doi mot loi hien thi lay
            # mot loi du lieu. Luoi an toan o `tick()` se thuat lai sau.
            try:
                self._bao_ket_qua_ve_chat(ctx, task_id)
            except Exception as exc:                        # noqa: BLE001
                self.store.ghi_su_kien(
                    "RESULT_TO_CHAT_FAILED", project_id=ctx.project.project_id,
                    task_id=task_id, level="WARNING",
                    detail=f"{type(exc).__name__}: {exc}"[:300])
            # Viec vua xong la mot REVIEW -> khep viec CHA lai. Lam sau khi
            # da ghi trang thai/su kien cua chinh no, de neu buoc khep hong
            # thi ket qua review van con nguyen tren so.
            xong = self.store.task(task_id)
            if xong is not None and xong.parent_id:
                self._khep_review(xong)
                # Con cua mot lan TOA: neu day la con cuoi cung ket thuc thi
                # gop vao cha. Con con dang chay/cho thi ham nay tu tra ve.
                if ((xong.contract or {}).get("_toa") or {}).get("cha_id"):
                    self._tong_hop_toa(ctx, xong.parent_id)

        except Exception as exc:                          # noqa: BLE001
            self.store.ghi_su_kien(
                "TASK_CRASHED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id, level="ERROR",
                detail=f"{type(exc).__name__}: {exc}"[:600])
            try:
                self.store.doi_trang_thai(
                    task_id, TaskState.FAILED, force=True,
                    reason=f"luồng điều phối hỏng: {type(exc).__name__}: {exc}"[:400])
            except Exception:                             # noqa: BLE001
                pass
            ctx.sessions.ket_thuc_viec(session_id, task_id, ok=False)
        finally:
            nhip.set()
            try:
                ctx.fabric.mark_finished(
                    p.runtime_id, task_id, ok=bool(kq and kq.ok),
                    model_id=p.model_id,
                    seconds=kq.envelope.duration if kq else time.time() - t0)
            except Exception:                             # noqa: BLE001
                pass
            ctx.leases.release(khoa_lease, self.owner)
            if not da_nha_khoa:
                lm.tra(ctx.project.project_id, task_id)
            with self._khoa:
                self._dang_chay.pop(task_id, None)

    # -- 5. Dieu khien ------------------------------------------------------

    def pause(self, task_id: str, *, reason: str = "người dùng tạm dừng") -> Task:
        """Tạm dừng một việc.

        Việc CHƯA chạy thì dừng ngay và sạch. Việc ĐANG chạy thì `PAUSED`
        được ghi nhận nhưng lượt đang bay vẫn chạy nốt — nói rõ như vậy thay
        vì giả vờ đã dừng: `Executor.run` là đồng bộ, và cách duy nhất cắt
        nó giữa chừng là giết tiến trình agent (đó là `stop`, không phải
        `pause`).
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        dang_chay = t.state is TaskState.RUNNING
        t2 = self.store.doi_trang_thai(
            task_id, TaskState.PAUSED,
            reason=reason + (" (lượt đang bay vẫn chạy nốt)" if dang_chay else ""))
        if t.owner_session:
            self.ctx(t.project_id).sessions.drain(
                t.owner_session, reason=f"việc {task_id} bị tạm dừng")
        return t2

    def resume(self, task_id: str) -> Task:
        """Tiếp tục một việc đã tạm dừng.

        `resume` KHÔNG phải một cách duyệt cổng. Một việc GATED chưa ai duyệt
        thì quay về `BLOCKED`, không phải `QUEUED` — nếu không thì
        `pause` rồi `resume` là một đường vòng đầy đủ quanh cổng an toàn
        (đã kiểm: nó chạy được thật trước bản này).
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if not self._da_duyet_cong(t):
            self.store.ghi_su_kien(
                "GATE_HELD", project_id=t.project_id, task_id=task_id,
                level="ALERT",
                detail=("`resume` KHÔNG mở được cổng an toàn — việc vẫn "
                        "BLOCKED cho tới khi có người duyệt"))
            return self.store.doi_trang_thai(
                task_id, TaskState.BLOCKED, force=True,
                reason=(f"{t.gate_reason} — `resume` không phải là duyệt. "
                        f"Dùng `mo_khoa_gated()` (phím `g` trên giao diện)."))
        if t.owner_session:
            s = self.store.session(t.owner_session)
            if s is not None and s.state is SessionState.DRAINING:
                self.store.dat_trang_thai_session(
                    s.session_id, SessionState.IDLE, note="tiếp tục")
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="người dùng tiếp tục")

    def stop(self, task_id: str, *, reason: str = "người dùng dừng") -> Task:
        """Dừng hẳn một việc VÀ cắt lượt agent đang bay nếu có.

        Cắt thật = gọi `adapter.cancel()`, và với mọi adapter trong kho này
        `cancel()` nghĩa là GIẾT tiến trình (adapter tự ghi rõ như vậy). Kết
        quả của lượt đang chạy mất — đó là cái giá của việc dừng thật, và nó
        được ghi vào sự kiện thay vì giấu đi.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        ctx = self.ctx(t.project_id)
        s = self.store.session(t.owner_session) if t.owner_session else None
        cat = False
        if s is not None:
            ad = ctx.executor._cache.get(s.placement_key)
            if ad is not None and hasattr(ad, "cancel"):
                try:
                    ad.cancel()
                    cat = True
                except Exception as exc:                  # noqa: BLE001
                    self.store.ghi_su_kien(
                        "AGENT_CANCEL_FAILED", project_id=t.project_id,
                        task_id=task_id, session_id=s.session_id,
                        level="WARNING", detail=f"{type(exc).__name__}: {exc}"[:300])
            ctx.sessions.dung(s.session_id, reason=reason,
                              state=SessionState.STOPPED)
        t2 = self.store.doi_trang_thai(
            task_id, TaskState.FAILED, force=True,
            reason=reason + ("; đã cắt tiến trình agent, kết quả lượt đang "
                             "chạy bị mất" if cat else "; không có tiến trình "
                             "agent nào để cắt"))
        LockManager(self.store).tra(t.project_id, task_id)
        self.store.ghi_su_kien(
            "TASK_STOPPED", project_id=t.project_id, task_id=task_id,
            level="WARNING", detail=reason[:300], meta={"agent_killed": cat})
        return t2

    def reassign(self, task_id: str, *,
                 exclude_runtime: str = "") -> Task:
        """Giao lại việc cho một phiên/placement KHÁC.

        Nhả phiên hiện tại rồi đưa việc về `QUEUED`. Lượt sau, `decide()` sẽ
        không thấy phiên cũ trong danh sách sống nữa nên tự chọn chỗ khác —
        không cần một đường định tuyến thứ hai.

        HAI THỨ HÀM NÀY TỪ CHỐI LÀM, và cả hai đều từng làm được:

        1. **Việc đã DONE.** Bản trước dùng `force=True`, tức đi vòng qua
           TOÀN BỘ bảng chuyển trạng thái — `DONE` không còn là ngõ cụt nữa.
           Bấm `r` trên một việc `DONE` sẽ chạy lại nó và `ghi_ket_qua()` ghi
           đè kết quả cũ: báo cáo, danh sách `changes`, và cả phần `findings`
           mà review độc lập vừa gộp vào đều biến mất. `r` nằm ngay cạnh
           `o`/`s` trên một bảng dùng lúc 3 giờ sáng.

           `FAILED` thì VẪN giao lại được: không có kết quả nào đáng giữ, và
           "hỏng rồi, thử chỗ khác" đúng là việc `reassign` sinh ra để làm.
           Bỏ `force=True` là đủ — bảng chuyển đã cho `FAILED -> QUEUED` và
           đã cấm `DONE -> QUEUED`; để bảng đó lên tiếng thay vì dựng một
           luật thứ hai song song với nó.
        2. **Việc ĐANG chạy.** `sessions.dung()` gọi `worktrees.nha()`, tức
           xoá chủ sở hữu cây làm việc TRONG KHI luồng `_chay` vẫn đang ghi
           vào đúng cây đó — và `assert_exclusive` mất tác dụng ngay lúc nó
           cần nhất. Muốn dừng một việc đang chạy thì dùng `stop()`, hàm có
           cắt tiến trình thật và có hộp xác nhận.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if t.state is TaskState.DONE:
            raise TransitionError(
                f"{task_id} đã DONE — `reassign` KHÔNG chạy lại một việc đã "
                f"xong, vì làm vậy sẽ ghi đè mất kết quả và cả phát hiện của "
                f"review độc lập. Muốn làm lại thì tạo một việc mới.")
        with self._khoa:
            dang_bay = task_id in self._dang_chay
        if dang_bay or t.state is TaskState.RUNNING:
            raise TransitionError(
                f"{task_id} đang chạy — `reassign` sẽ nhả cây làm việc trong "
                f"khi agent vẫn đang ghi vào đó. Dùng `stop()` trước.")

        ctx = self.ctx(t.project_id)
        if t.owner_session:
            ctx.sessions.dung(
                t.owner_session, state=SessionState.STOPPED,
                reason=f"giao lại {task_id}"
                       + (f" (tránh {exclude_runtime})" if exclude_runtime else ""))
        t.owner_session = ""
        self.store.luu_task(t)
        self.store.ghi_su_kien(
            "TASK_REASSIGNED", project_id=t.project_id, task_id=task_id,
            detail=f"nhả phiên cũ; sẽ chọn chỗ mới ở nhịp sau")
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="giao lại")

    # -- 6. Phuc hoi ---------------------------------------------------------

    def recover(self) -> Dict:
        """Đối soát MỌI trạng thái với thực tế. Chạy lúc khởi động.

        Bốn nhóm, theo thứ tự an toàn tăng dần:

            1. khoá  — hết hạn thì thu, TRỪ khoá production (cần người).
            2. phiên — có PID sống thì gắn lại; chết thì `DEAD`.
            3. worktree — đối soát với đĩa; chỉ đánh dấu, KHÔNG xoá.
            4. việc  — `RUNNING` mà chủ đã chết thì về `QUEUED` để chạy lại,
                       trừ khi đã cạn lượt thử.

        Việc `RUNNING` mồ côi KHÔNG bị đánh `FAILED` ngay: một tiến trình
        agent có thể vẫn đang chạy thật (Control Center tắt không giết nó).
        Đưa về `QUEUED` để nó được xét lại là hành vi thu hồi được; đánh
        `FAILED` thì mất luôn công việc đã làm.
        """
        bc: Dict = {"locks": {}, "sessions": {}, "worktrees": {}, "tasks": []}
        bc["locks"] = LockManager(self.store).reclaim()

        for p in self.projects():
            ctx = self.ctx(p.project_id)
            # VIEC DANG DUOC MOT TIEN TRINH KHAC CHAY -> KHONG DUOC DUNG VAO.
            #
            # `recover()` chay vo dieu kien moi lan mo Control Center, ke ca
            # `--headless` chi de xem mot anh chup. Neu mot TUI khac dang
            # chay mot viec, ban truoc se: thay `sessions.pid IS NULL` (pid
            # chi duoc ghi luc KET THUC viec), dat phien ve IDLE va XOA
            # `current_task`, roi coi viec RUNNING la mo coi -> dua ve QUEUED
            # va NHA KHOA cua mot agent dang ghi. Hai agent giam chung mot
            # cay; va khi luot that ket thuc, `QUEUED -> DONE` nem
            # `TransitionError` nen ca viec lam dung bi ghi thanh FAILED.
            #
            # Lease cua Router V4 la tin hieu LIEN TIEN TRINH dung cho viec
            # nay: no song trong SQLite, co TTL + nhip tim, va mang `task_id`.
            # Viec nao con lease SONG thi that su dang chay o dau do — de yen.
            dang_thue = self._viec_dang_co_lease(ctx)
            if dang_thue:
                bc.setdefault("leased", []).extend(sorted(dang_thue))
            bc["sessions"][p.project_id] = ctx.sessions.recover(
                bo_qua_viec=dang_thue)
            bc["worktrees"][p.project_id] = ctx.worktrees.doi_soat()
            bc.setdefault("stale_locks", []).extend(
                self._nha_khoa_mo_coi(p.project_id))

            for t in self.store.tasks(p.project_id, states=(TaskState.RUNNING,)):
                # "PHIEN CON SONG" KHONG DU — phai la "phien DANG CHAY DUNG
                # VIEC NAY".
                #
                # Ban dau cho nay chi hoi phien co con song khong. Nhung mot
                # phien RANH (IDLE, `current_task` rong) van "con song", nen
                # mot viec ma phien chu da bo lai se o `RUNNING` VINH VIEN:
                # `recover()` bo qua no, va bo lap lich khong bao gio nhat no
                # len vi no khong o QUEUED/WAITING.
                #
                # Do that 2026-09-08: `rev2.tda87-1` ket o RUNNING qua BA lan
                # goi `--headless` lien tiep, moi lan deu chay `recover()`.
                # Day dung la che do hong ma `recover()` ton tai de chan, va
                # no song sot duoc vi phep kiem hoi sai cau hoi.
                if t.task_id in dang_thue:
                    continue                  # tien trinh khac dang chay
                if ((t.contract or {}).get("_toa") or {}).get("cha"):
                    # Viec CHA cua mot lan toa: vat chua, khong co phien theo
                    # thiet ke — khong phai mo coi. Neu moi con da ket thuc
                    # trong luc app tat thi gop luon.
                    try:
                        self._tong_hop_toa(ctx, t.task_id)
                    except Exception:                       # noqa: BLE001
                        pass
                    continue
                s = (self.store.session(t.owner_session)
                     if t.owner_session else None)
                if s is not None and s.state.alive and \
                        s.current_task == t.task_id:
                    continue                  # that su dang chay -> de yen
                if t.attempts >= MAX_ATTEMPTS:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.BLOCKED, force=True,
                        reason=(f"đang RUNNING khi Control Center tắt và đã "
                                f"cạn {MAX_ATTEMPTS} lượt thử — cần người xem"))
                else:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.QUEUED, force=True,
                        reason=("phiên chủ không còn sau khởi động lại — đưa "
                                "về hàng đợi để xét lại"))
                # VIEC DA RA KHOI `RUNNING` THI KHOA CUA NO PHAI VE THEO.
                #
                # Khong nha o day thi khoa cua mot viec mo coi con giu toi
                # het TTL (1 tieng), va MOI viec khac cham cung tai nguyen
                # phai CHO het tieng do — trong khi viec giu khoa thi da
                # khong con chay nua. Do that 2026-09-08: mot luot chung
                # minh bi cat giua chung de lai hai khoa, va lan chay ke
                # tiep ket o `WAITING` vinh vien.
                #
                # An toan vi ta VUA XAC MINH viec nay khong con phien nao
                # dang chay no — day chinh la dieu kien de vao nhanh nay.
                nha = LockManager(self.store).tra(p.project_id, t.task_id)
                if nha:
                    self.store.ghi_su_kien(
                        "LOCK_RELEASED_ON_RECOVER", project_id=p.project_id,
                        task_id=t.task_id, level="WARNING",
                        detail=(f"nhả {nha} khoá của một việc mồ côi — nó "
                                f"không còn chạy nữa"))
                bc["tasks"].append(t.task_id)
        # V0.9 (§11) — DOI SOAT VONG KIN. Sau viec le, vi no doc trang thai
        # viec da duoc doi soat o tren: mot buoc coi la mo coi chi khi viec
        # cua no that su khong con.
        try:
            bc["thuc_thi"] = DP.BoDieuPhoi(
                self.so_thuc_thi, tao_viec=self._tao_viec_cho_buoc,
                trang_thai_viec=self._trang_thai_viec).doi_soat_khoi_dong()
        except Exception as exc:                            # noqa: BLE001
            bc["thuc_thi"] = {"loi": f"{type(exc).__name__}: {exc}"[:200]}
        self.store.ghi_su_kien(
            "RECOVERED", level="WARNING",
            detail=(f"phục hồi: {len(bc['tasks'])} việc mồ côi, "
                    f"{len(bc['locks'].get('reclaimed', []))} khoá thu hồi, "
                    f"{len(bc['locks'].get('needs_human', []))} khoá "
                    f"production CẦN NGƯỜI"),
            meta=bc)
        return bc

    # -- 7. Vong lap nen -----------------------------------------------------

    def _am_leader_nen(self) -> None:
        """Mở sẵn phiên Leader ở NỀN, cho dự án đầu tiên.

        Khởi động nguội `agy` mất ~8 giây (đo được). Không làm ấm trước thì
        tin nhắn ĐẦU TIÊN của người dùng — thường là một câu chào — phải
        chờ trọn 8 giây đó, và ấn tượng đầu về sản phẩm là "chậm". Đo
        được ở lượt nghiệm thu: lần đầu 14.8s, các lần sau 4.8–6.4s.

        Best-effort tuyệt đối: chạy ở luồng nền, nuốt mọi lỗi. Không ấm
        được thì lượt đầu chỉ chậm như cũ, KHÔNG hỏng.
        """
        if not self.leader_bat:
            return

        def _lam() -> None:
            try:
                ps = self.projects()
                if not ps:
                    return
                pid = ps[0].project_id
                bg = self.leader_ban_ghi(pid)
                ph = self._phien_leader(pid, bg)
                if ph.mo():
                    self.store.ghi_su_kien(
                        "LEADER_WARM", project_id=pid,
                        detail=f"phiên Leader đã ấm ({bg.model})")
            except Exception:                               # noqa: BLE001
                pass                # am truoc chi la tien nghi

        threading.Thread(target=_lam, daemon=True, name="cc-leader-warm").start()

    def start(self, *, interval: float = TICK_SECONDS) -> None:
        """Chạy vòng lặp điều phối trong nền."""
        if self._luong_vong is not None and self._luong_vong.is_alive():
            return
        self._dung_lai.clear()
        self._am_leader_nen()

        def _vong() -> None:
            while not self._dung_lai.wait(interval):
                try:
                    self.tick()
                except Exception as exc:                  # noqa: BLE001
                    # Vong lap dieu phoi KHONG duoc chet vi mot nhip hong —
                    # nhung cung KHONG duoc im lang. Mot `pass` o day nghia
                    # la bang dieu khien tiep tuc ve trong khi khong con gi
                    # duoc giao nua.
                    self.store.ghi_su_kien(
                        "TICK_FAILED", level="ERROR",
                        detail=f"{type(exc).__name__}: {exc}"[:400])

        self._luong_vong = threading.Thread(target=_vong, daemon=True,
                                            name="cc-scheduler")
        self._luong_vong.start()
        self.store.ghi_su_kien("ENGINE_STARTED",
                               detail=f"nhịp {interval}s, trần "
                                      f"{self.max_parallel} việc song song")

    def stop_engine(self, *, timeout: float = 5.0) -> None:
        self._dung_lai.set()
        if self._luong_vong is not None:
            self._luong_vong.join(timeout=timeout)
        self.store.ghi_su_kien("ENGINE_STOPPED", detail="vòng lặp đã dừng")

    def shutdown(self) -> None:
        """Đóng sạch. KHÔNG giết agent đang chạy và KHÔNG xoá worktree.

        Tắt Control Center không được phép phá công việc đang dở: một lượt
        agent đang bay vẫn chạy nốt, và `recover()` ở lần khởi động sau sẽ
        đối soát lại. Đây là điều kiện để "sống sót qua khởi động lại" có
        nghĩa gì đó.
        """
        self.stop_engine()
        # V0.6 — DIEM DUNG KHI TAT: mot phien sau mo len phai biet dang lam
        # gi. Dung tren trang thai THAT trong so (viec dang chay/con chan),
        # sau khi vong lap da dung nen khong con gi doi duoi chan. `ep=True`
        # bo qua gian cach toi thieu — day la lan cuoi cua phien nay.
        if self._ky_uc is not None:
            try:
                if (self._ky_uc.cau_hinh.get("diem_dung") or {}).get(
                        "khi_tat_app", True):
                    for p in self.projects():
                        dd = self._ky_uc.diem_dung_tu_dong(
                            p.project_id, "tắt ứng dụng", ep=True)
                        if dd is None:
                            # KHONG nuot im lang: mot diem dung khong ghi
                            # duoc luc tat la thu phien sau se thieu, va
                            # khong ai biet neu day chi la `pass`.
                            pv = self._ky_uc.provider(p.project_id)
                            self.store.ghi_su_kien(
                                "MEMORY_ERROR", project_id=p.project_id,
                                level="WARNING",
                                detail="điểm dừng lúc tắt KHÔNG ghi được: "
                                       + (pv.loi_cuoi if pv else "provider None")[:200])
            except Exception as exc:                      # noqa: BLE001
                try:
                    self.store.ghi_su_kien(
                        "MEMORY_ERROR", level="WARNING",
                        detail=f"điểm dừng lúc tắt: {type(exc).__name__}: {exc}"[:300])
                except Exception:                         # noqa: BLE001
                    pass
            try:
                self._ky_uc.close()
            except Exception:                             # noqa: BLE001
                pass
        # Phien Leader la tien trinh `agy` AM cua CHINH ta — dong no la
        # dung, khac han voi mot luot agent dang bay cua worker.
        with self._khoa_leader:
            ph = list(self._leader_phien.items())
            self._leader_phien.clear()
        for pid, x in ph:
            if self._fabric is not None:
                leader.tra_cho_fabric(self._fabric, getattr(x, "runtime_id", ""),
                                      f"LEADER:{pid}")
            try:
                x.dong()
            except Exception:                             # noqa: BLE001
                pass
        with self._khoa:
            ctxs = list(self._ctx.values())
        for c in ctxs:
            try:
                c.leases.close()
            except Exception:                             # noqa: BLE001
                pass
        if self._providers is not None:
            try:
                self._providers.close()
            except Exception:                             # noqa: BLE001
                pass
        # V0.8 — phien AM cua cac vai suy luan. Cung ly le nhu phien Leader:
        # chung la tien trinh cua CHINH ta, nen dong chung la dung.
        if self._hoi_dong is not None:
            try:
                self._hoi_dong.bo_goi.dong()
            except Exception:                             # noqa: BLE001
                pass

    # -- 8. Doc trang thai ---------------------------------------------------

    def snapshot(self, project_id: str = "") -> Dict:
        """Ảnh chụp cho giao diện. Chỉ ĐỌC sổ — không gọi mạng, không dò."""
        ps = self.projects()
        pid = project_id or (ps[0].project_id if ps else "")
        d: Dict = {"projects": [p.to_dict() for p in ps],
                   "selected": pid, "ts": time.time()}
        if not pid:
            return d
        d["tasks"] = [t.to_dict() for t in self.store.tasks(pid)]
        d["sessions"] = [s.to_dict() for s in self.store.sessions(pid)]
        d["locks"] = LockManager(self.store).snapshot(pid)
        d["worktrees"] = self.store.worktrees(pid)
        d["events"] = self.store.su_kien(project_id=pid, limit=200)
        d["chat"] = [m.to_dict() for m in self.store.chat(pid, limit=100)]
        with self._khoa:
            d["in_flight"] = sorted(self._dang_chay)
            b = self._buoc.get(pid)
            ngg = self._nguon_goc_suy_luan.get(pid)
        d["buoc"] = {"nhan": b[0], "tu_luc": b[1]} if b else None
        # V0.8 — CHE DO CHAT LUONG di theo NHIP NHANH.
        #
        # No cung co trong `AnhChupDuAn` (`/api/snapshot`), nhung duong do
        # chay ~6 lenh `git` nen frontend goi no CHAM va co bo dem 30 giay.
        # Hau qua do duoc bang Chrome that: doi che do o mot tab thi thanh
        # tren cua tab kia giu gia tri cu toi 30 giay — nguoi dung tuong minh
        # dang o MAX trong khi so ghi AUTO. Nguon su that phai toi theo dung
        # nhip ma no doi.
        try:
            d["che_do"] = self.leader_ban_ghi(pid).che_do
        except Exception:                                   # noqa: BLE001
            d["che_do"] = ""
        # V0.8 — §12 ĐỊNH TUYẾN GIẢI THÍCH ĐƯỢC. Đi qua `snapshot` nên nó tới
        # giao diện qua CÙNG nhịp WebSocket, không cần một lần gọi nữa.
        #
        # Chỉ phần GỌN: `nguon_goc` đầy đủ mang cả `Decision` với 60+ ứng viên
        # và điểm từng chiều — đó là dữ liệu gỡ lỗi, và nhồi nó vào mỗi nhịp
        # một giây sẽ biến một ô quan sát thành một vòi dữ liệu. Bản đầy đủ ở
        # `GET /api/reasoning`.
        d["suy_luan"] = ({
            "che_do": (ngg.get("so") or {}).get("che_do") or "",
            "da_chay": bool(ngg.get("da_chay")),
            "suy_giam": bool(ngg.get("suy_giam")),
            "dong": list(ngg.get("dong_nguon_goc") or []),
            "ts": ngg.get("ts") or 0.0,
        } if ngg else None)
        # V0.9 — VONG KIN. Phan GON di theo nhip nhanh (giong `suy_luan`):
        # muc tieu, trang thai, tien do, cong tham quyen. Anh chup DAY DU cua
        # mot lan thuc thi o `GET /api/execution?id=…` — nhoi ca ke hoach +
        # bang chung vao moi nhip mot giay se bien o quan sat thanh voi.
        try:
            d["thuc_thi"] = self._thuc_thi_gon(pid)
        except Exception:                                   # noqa: BLE001
            d["thuc_thi"] = []
        return d

    def _thuc_thi_gon(self, project_id: str) -> List[Dict]:
        """Dòng GỌN cho mỗi lần thực thi — đủ cho thanh tiến độ và nút bấm."""
        from scripts.control_center.execution.so import tien_do
        ra: List[Dict] = []
        ds = self.so_thuc_thi.dang_chay(project_id) or             self.so_thuc_thi.danh_sach(project_id, limit=5)
        for y in ds[:8]:
            kh = self.so_thuc_thi.ke_hoach(y.execution_id)
            bs = {b["buoc_id"]: b
                  for b in self.so_thuc_thi.buoc(y.execution_id,
                                                 kh.phien_ban if kh else 1)}
            ra.append({
                "execution_id": y.execution_id, "goal": y.goal,
                "trang_thai": y.trang_thai.value,
                "trang_thai_nhan": y.trang_thai.nhan,
                "pha": y.pha, "ban_ke_hoach": y.ban_ke_hoach,
                "tham_quyen": y.tham_quyen.value, "duyet": y.duyet.value,
                "can_tham_quyen_moi": y.can_tham_quyen_moi,
                "tac_dong_production": y.tac_dong_production,
                "ly_do_dung": y.ly_do_dung,
                "so_lan_thu_lai": y.so_lan_thu_lai,
                "so_lan_lap_lai": y.so_lan_lap_lai,
                "ket_thuc": y.trang_thai.ket_thuc,
                "tien_do": tien_do(kh, bs),
                "buoc": [{"buoc_id": m, "state": b["state"],
                          "xac_minh": b["xac_minh"], "task_id": b["task_id"],
                          "tieu_de": (kh.buoc_theo_ma(m).tieu_de
                                      if kh and kh.buoc_theo_ma(m) else m),
                          "che_do_ghi": (kh.buoc_theo_ma(m).che_do_ghi.value
                                         if kh and kh.buoc_theo_ma(m) else ""),
                          "phu_thuoc": (list(kh.buoc_theo_ma(m).phu_thuoc)
                                        if kh and kh.buoc_theo_ma(m) else [])}
                         for m, b in sorted(bs.items())]})
        return ra

    def log_cua_viec(self, task_id: str, *, limit: int = 400) -> str:
        """Nhật ký của một việc: sự kiện + nhật ký THÔ của agent nếu có.

        Nhật ký thô nằm trên đĩa sau `raw_log_ref` (đó là cách Router V4 giữ
        ngữ cảnh nhỏ). Đọc nó qua `RawLogStore.read`, hàm đã chặn đi ngang
        thư mục — `raw_log_ref` đến từ phong bì, và phong bì chịu ảnh hưởng
        của worker.
        """
        t = self.store.task(task_id)
        if t is None:
            return f"không có việc {task_id!r}"
        d = [f"=== VIỆC {task_id} — {t.state.value} ===",
             f"tiêu đề : {t.title}",
             f"phiên   : {t.owner_session or '(chưa có)'}",
             f"worktree: {t.worktree or '(không)'}",
             f"nhánh   : {t.branch or '(không)'}",
             f"lượt thử: {t.attempts}",
             ""]
        if t.blocked_reason:
            d += ["LÝ DO CHẶN:", t.blocked_reason, ""]
        d.append("=== SỰ KIỆN ===")
        for e in reversed(self.store.su_kien(task_id=task_id, limit=limit)):
            gio = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
            d.append(f"[{gio}] {e['level']:<7} {e['kind']:<18} {e['detail']}")

        ref = ((t.result or {}).get("envelope") or {}).get("raw_log_ref", "")
        if ref:
            ctx = self.ctx(t.project_id)
            tho = ctx.logs.read(ref)
            d += ["", f"=== NHẬT KÝ THÔ CỦA AGENT ({ref}) ==="]
            d.append(tho if tho else "(không đọc được — tệp không còn?)")
        return "\n".join(d)
