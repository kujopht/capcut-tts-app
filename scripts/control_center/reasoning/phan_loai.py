"""Phân loại ĐỘ KHÓ / TÁC ĐỘNG của một lượt, và kế hoạch vai — V0.8.

MỘT BỘ TỪ KHOÁ KHÔNG PHẢI MỘT BỘ PHÂN LOẠI, và kho này đã trả giá cho bài
học đó hai lần:

* `fanfic.t78ce-1` — chữ **"quyền"** trong lời nhắc công cụ TIÊU CHUẨN làm
  MỌI việc xếp vào Codex bị từ chối rồi chết ở `BLOCKED`. Sửa (V0.7) là
  phân loại theo CỤM TỪ chuyên môn, chỉ trên phần NGƯỜI VIẾT.
* `fanfic.t2efd-1` — một câu hỏi production bị xếp thành việc PHÂN TÍCH
  KHO, worker phải xin `command`, headless tự chối.

Nên ở đây: **đặc trưng có cấu trúc, có tên, cho điểm có trọng số, và giải
thích được từng dấu hiệu đã bắt.** Dấu hiệu chữ nghĩa là MỘT trong các đặc
trưng, không phải toàn bộ phép quyết định — và mỗi đặc trưng có thể bị các
đặc trưng khác ĐẢO (một câu chứa chữ "production" vẫn là tra cứu nếu nó là
câu hỏi trạng thái đơn).

TẤT ĐỊNH, KHÔNG LLM. Cùng đầu vào -> cùng phân loại, nên mọi bài kiểm định
tuyến chạy được không cần một tiến trình model nào — cùng lý do
`Scheduler.decide()` tách khỏi `Executor`.

CỔNG TẦM THƯỜNG là rào CỨNG, không phải một ưu tiên mềm. Một câu chào, một
câu tra cứu `git`, một câu hỏi trạng thái sống đơn — KHÔNG vai nào được gọi,
ở MỌI chế độ, **kể cả MAX**. Đây là chỗ duy nhất chặn "MAX biến 'ê bro'
thành một hội đồng ba model".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple

from scripts.control_center import leader as LEADER
from scripts.control_center.reasoning.vai import VaiTro
from scripts.router_v4.premium import CheDo


class Bac(str, Enum):
    """Độ khó SUY LUẬN của lượt. Thang có thứ tự, so sánh được."""

    TAM_THUONG = "TAM_THUONG"
    THUONG = "THUONG"
    KHO = "KHO"
    RAT_KHO = "RAT_KHO"

    @property
    def rank(self) -> int:
        return {"TAM_THUONG": 0, "THUONG": 1, "KHO": 2, "RAT_KHO": 3}[self.value]

    def __ge__(self, o) -> bool:                        # type: ignore[override]
        return self.rank >= o.rank if isinstance(o, Bac) else NotImplemented

    def __gt__(self, o) -> bool:                        # type: ignore[override]
        return self.rank > o.rank if isinstance(o, Bac) else NotImplemented

    def __le__(self, o) -> bool:                        # type: ignore[override]
        return self.rank <= o.rank if isinstance(o, Bac) else NotImplemented

    def __lt__(self, o) -> bool:                        # type: ignore[override]
        return self.rank < o.rank if isinstance(o, Bac) else NotImplemented


class TacDong(str, Enum):
    """Tác động lên DỰ ÁN nếu câu trả lời sai. Khác độ khó có chủ ý: một câu
    dễ vẫn có thể tác động lớn (“xoá bucket nào?”), và một câu khó vẫn có thể
    vô hại (“giải thích giúp cơ chế X”)."""

    THAP = "THAP"
    TRUNG = "TRUNG"
    CAO = "CAO"

    @property
    def rank(self) -> int:
        return {"THAP": 0, "TRUNG": 1, "CAO": 2}[self.value]


class PhamVi(str, Enum):
    LOCAL = "LOCAL"
    MODULE = "MODULE"
    REPO = "REPO"
    MULTI_SYSTEM = "MULTI_SYSTEM"


# ----------------------------------------------------------------- tu vung --
#
# Mỗi nhóm là một ĐẶC TRƯNG CÓ TÊN, không phải một túi từ khoá chung. Cụm từ
# được ưu tiên hơn từ đơn ở đúng những chỗ mà từ đơn sẽ bắt bừa.

def _c(*mau: str) -> Tuple[re.Pattern, ...]:
    return tuple(re.compile(m, re.I) for m in mau)


#: Chào hỏi / tán gẫu. NGẮN là một phần của định nghĩa: "ê bro" là xã giao,
#: "ê bro, kiến trúc storage nên đổi thế nào" thì không.
_XA_GIAO = _c(
    r"^\s*(ê|ê\s*bro|bro|hê+|hey|hi|hello|yo|chào|xin chào|alo|hallo)\b",
    r"^\s*(ok|oke|okay|ừ|uh|vâng|dạ|thanks|thank you|cảm ơn|cám ơn|good\s*(morning|night))\b",
    r"^\s*(m|mày|bạn|you)\s*(ơi|à|hả)?\s*$",
)

#: Tra cứu KHO — sổ và `git` trả lời được, không cần suy luận.
_TRA_CUU_KHO = _c(
    r"\bcommit\b.{0,20}\b(gần nhất|cuối|mới nhất|hiện tại|nào)\b",
    r"\b(nhánh|branch)\b.{0,20}\b(nào|gì|hiện tại|đang)\b",
    r"\b(head|sha|hash)\b.{0,20}\b(là gì|nào|bao nhiêu)\b",
    r"\bđang ở (nhánh|branch|commit)\b",
    r"\b(cây làm việc|working tree|git status)\b",
    r"\bbao nhiêu (việc|task|test|tệp|file)\b",
    r"\b(latest|current) commit\b",
)

#: Xin TƯ VẤN — câu hỏi "nên thế nào", tức là xin một PHÁN ĐOÁN.
_TU_VAN = _c(
    r"\b(có )?nên\b", r"\bshould (i|we|you)\b", r"\btheo (m|mày|bạn|anh|em|you)\b",
    r"\bđề xuất\b", r"\bgợi ý\b", r"\btư vấn\b", r"\bkhuyên\b",
    r"\brecommend\b", r"\bsuggest\b", r"\badvise\b", r"\bý kiến\b",
)

#: CHIẾN LƯỢC DỰ ÁN — hỏi về HƯỚNG ĐI, không về một sự kiện cụ thể. Tách
#: riêng khỏi `_TU_VAN` vì đây chính là lớp câu hỏi mà v0.8 tồn tại để trả
#: lời (nghiệm thu D), và một câu như thế phải nâng bậc dù không có chữ
#: "kiến trúc" nào trong đó.
_CHIEN_LUOC = _c(
    r"\b(ưu tiên|priority|prioriti[sz]e)\b.{0,30}\b(gì|nào|tiếp|next)\b",
    r"\b(làm|phát triển|build|ship)\b.{0,20}\b(gì|phần nào|cái gì)\b.{0,15}\b(tiếp|next|sau)\b",
    r"\b(roadmap|lộ trình|kế hoạch dài hạn|định hướng|hướng (đi|phát triển))\b",
    r"\b(bước|phase|giai đoạn)\b.{0,15}\b(tiếp theo|kế tiếp|next)\b",
    r"\bwhat('?s| is| should)\b.{0,20}\bnext\b",
    r"\b(project|dự án)\b.{0,30}\bnên\b",
    r"\bnên (làm|đi|tập trung|đầu tư)\b.{0,20}\b(gì|đâu|phần nào)\b",
)

#: ĐÁNH ĐỔI — có ít nhất hai phương án đang được cân.
_DANH_DOI = _c(
    r"\bcó nên\b", r"\bhay (là|không)\b", r"\bso sánh\b", r"\bđánh đổi\b",
    r"\btrade-?off\b", r"\bphương án\b", r"\blựa chọn\b", r"\bvs\.?\b",
    r"\bhoặc\b.{0,40}\bhoặc\b", r"\bor\b.{0,30}\bwhich\b",
    r"\bpros and cons\b", r"\bưu (điểm|nhược)\b",
)

#: PHẠM VI KIẾN TRÚC — câu chạm tới hình dạng hệ thống, không tới một tệp.
_KIEN_TRUC = _c(
    r"\bkiến trúc\b", r"\barchitectur", r"\bredesign\b", r"\bthiết kế lại\b",
    r"\btái cấu trúc\b", r"\bre-?architect\b",
    r"\b(migrate|migration|di trú|chuyển đổi)\b",
    r"\bscale\b", r"\bmở rộng (quy mô|hệ thống)\b", r"\bthroughput\b",
    r"\b(storage|lưu trữ|data)\s*(architecture|layer|model)\b",
    r"\brefactor\b.{0,20}\b(lớn|toàn|whole|large)\b",
    r"\b(monolith|microservice|multi-?region|sharding)\b",
)

#: TÁC ĐỘNG PRODUCTION — hệ thống thật, người dùng thật.
_PRODUCTION = _c(
    r"\bproduction\b", r"\bprod\b", r"\bfanfic\.world\b", r"\blive\b",
    r"\bkhách hàng\b", r"\bngười dùng thật\b", r"\bsản xuất\b",
)

#: KHÓ ĐẢO NGƯỢC — làm sai thì không lùi lại được bằng một `git revert`.
_DAO_NGUOC = _c(
    r"\b(migrate|migration|di trú)\b", r"\bschema\b", r"\bcutover\b",
    r"\b(xoá|xóa|delete|drop|truncate)\b", r"\bdeploy\b", r"\brollout\b",
    r"\bredesign\b", r"\bthiết kế lại\b", r"\bđổi (nhà cung cấp|provider)\b",
    r"\bxoay (khoá|key|credential)\b", r"\brotate\b",
)

#: ĐÒI PHẢN BIỆN — người dùng nói thẳng là muốn bị phản bác.
_PHAN_BIEN = _c(
    r"\bphản biện\b", r"\bphản bác\b", r"\bphê phán\b", r"\bchỉ ra\b.{0,25}\b(điểm yếu|lỗ hổng|sai)\b",
    r"\bcritique\b", r"\bchallenge\b", r"\bdevil'?s advocate\b",
    r"\bsteel-?man\b", r"\bpoke holes\b", r"\bđối chất\b",
    r"\bself-?review\b", r"\btự phản biện\b",
)

#: MƠ HỒ — câu mở, không nêu đối tượng cụ thể.
_MO_HO = _c(
    r"\b(thế nào|ra sao|như nào)\b", r"\bphần nào\b", r"\bcái gì\b",
    r"\bđâu là\b", r"\bwhat (should|would|could)\b", r"\bhow (should|would)\b",
    r"\bhướng nào\b", r"\bcách nào\b",
)

#: CẦN NGHIÊN CỨU NGOÀI — đánh giá một thứ bên ngoài kho.
_NGHIEN_CUU = _c(
    r"\b(đánh giá|evaluate|khảo sát|nghiên cứu|research)\b",
    r"\b(thư viện|library|framework|sdk|dịch vụ|service|provider)\b.{0,30}\b(nào|nên dùng|tốt hơn)\b",
    r"\bbest practice\b", r"\bstate of the art\b", r"\bso với\b.{0,30}\b(ngành|industry|others)\b",
)

#: THỰC THI — người dùng xin LÀM, không xin tư vấn. §11 của yêu cầu v0.8:
#: một đề xuất KHÔNG tự thành việc; chỉ câu người dùng mới mở cửa thực thi.
#: `chạy` TRẦN cố ý KHÔNG có ở đây: "production farmer hiện chạy không?" là
#: một câu hỏi TRẠNG THÁI, và bản đầu đã phân loại nó thành yêu cầu thực thi
#: đúng vì một động từ trần. Chỉ `chạy <thứ chạy được>` mới là thực thi.
_THUC_THI = _c(
    r"\b(hãy |giúp |làm ơn )?(sửa|fix|viết|tạo|thêm|xoá bỏ|cài|triển khai|implement|"
    r"refactor|rename|đổi tên|dựng|build)\b",
    r"\bchạy (test|kiểm|lint|typecheck|suite|script|lệnh|lại)\b",
    r"\b(bắt đầu|start|tiến hành|thực hiện|tiếp tục) (đi|luôn|ngay|việc)\b",
    r"\bdispatch\b", r"\buỷ thác\b", r"\bgọi \d+ agent\b", r"\bmỗi agent\b",
)

#: DẤU HIỆU LÀM NGAY — thắng cả veto tư vấn. "nên sửa thế nào" là tư vấn;
#: "nên sửa, làm đi" là thực thi.
_LAM_NGAY = _c(
    r"\blàm (đi|luôn|ngay)\b", r"\b(đi|luôn|ngay) nhé\b", r"\btriển khai luôn\b",
    r"\bdo it\b", r"\bgo ahead\b", r"\bproceed\b", r"\bbắt tay vào\b",
    r"\bthực thi luôn\b",
)

#: NHIỀU YÊU CẦU trong một câu — "… và phản biện …", "… rồi so sánh …".
_NHIEU_YEU_CAU = _c(
    r"\bvà (phản biện|so sánh|đánh giá|đề xuất|giải thích|kiểm)\b",
    r"\brồi (phản biện|so sánh|đánh giá|đề xuất)\b",
    r"\bsau đó\b", r"\bthen (critique|compare|review)\b",
    r"\band (critique|challenge|compare)\b",
)


def _bat(mau: Tuple[re.Pattern, ...], van: str) -> List[str]:
    return [r.pattern for r in mau if r.search(van)]


# ------------------------------------------------------------------ dac trung --

@dataclass
class DacTrung:
    """Đặc trưng CÓ CẤU TRÚC của một lượt. Mỗi trường đo được, kiểm được.

    Không có trường nào tên "khó" hay "quan trọng": những thứ đó là KẾT
    LUẬN, và chúng được tính ở `phan_loai_luot()` từ các trường dưới đây.
    """

    so_tu: int = 0
    so_cau_hoi: int = 0
    co_url: bool = False

    la_xa_giao: bool = False
    la_tra_cuu_kho: bool = False
    la_tra_cuu_song: bool = False        # hỏi trạng thái vận hành, KHÔNG chẩn đoán
    la_chan_doan: bool = False           # vận hành + cần suy luận nhiều bước
    la_lich_su: bool = False

    xin_tu_van: bool = False
    chien_luoc_du_an: bool = False
    danh_doi: bool = False
    pham_vi_kien_truc: bool = False
    tac_dong_production: bool = False
    kho_dao_nguoc: bool = False
    doi_phan_bien: bool = False
    mo_ho: bool = False
    can_nghien_cuu: bool = False
    nhieu_yeu_cau: bool = False
    xin_thuc_thi: bool = False

    #: `{tên đặc trưng: [mẫu đã khớp]}` — để `giai_thich()` nói được VÌ SAO.
    dau_hieu: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if k != "dau_hieu"}


def rut_dac_trung(cau: str) -> DacTrung:
    """Câu người dùng -> đặc trưng. CHỈ đọc câu người dùng viết.

    KHÔNG đọc lời nhắc công cụ, phong bì quyền, khối bằng chứng hay tóm tắt
    do worker sinh — đó là chỗ chữ "quyền" của `fanfic.t78ce-1` sinh ra, và
    nó không nói gì về lượt này.
    """
    van = (cau or "").strip()
    d = DacTrung()
    if not van:
        return d
    d.so_tu = len([x for x in re.split(r"\s+", van) if x])
    d.so_cau_hoi = van.count("?") + len(re.findall(
        r"\b(là gì|thế nào|ra sao|vì sao|tại sao|bao nhiêu|có không|không\?)\b",
        van, re.I))
    d.co_url = bool(re.search(r"https?://", van))

    def _dat(ten: str, mau: Tuple[re.Pattern, ...]) -> bool:
        kh = _bat(mau, van)
        if kh:
            d.dau_hieu[ten] = kh
        return bool(kh)

    # XA GIAO doi THEM dieu kien NGAN: mot cau mo dau bang "ê bro" nhung dai
    # va co noi dung thi khong phai tan gau. Nguong 6 tu do bang kiem khoa.
    xa = _dat("xa_giao", _XA_GIAO)
    d.la_xa_giao = xa and d.so_tu <= 6

    d.la_tra_cuu_kho = _dat("tra_cuu_kho", _TRA_CUU_KHO)

    d.xin_tu_van = _dat("tu_van", _TU_VAN)
    d.chien_luoc_du_an = _dat("chien_luoc", _CHIEN_LUOC)
    d.danh_doi = _dat("danh_doi", _DANH_DOI)
    d.pham_vi_kien_truc = _dat("kien_truc", _KIEN_TRUC)
    d.tac_dong_production = _dat("production", _PRODUCTION)
    d.kho_dao_nguoc = _dat("dao_nguoc", _DAO_NGUOC)
    d.doi_phan_bien = _dat("phan_bien", _PHAN_BIEN)
    d.mo_ho = _dat("mo_ho", _MO_HO)
    d.can_nghien_cuu = _dat("nghien_cuu", _NGHIEN_CUU) or d.co_url
    d.nhieu_yeu_cau = _dat("nhieu_yeu_cau", _NHIEU_YEU_CAU)

    # TÍN HIỆU SUY LUẬN — cái ĐẢO hai bộ nhận dạng "đã có nguồn tất định"
    # bên dưới, và nó là sửa lỗi hiệu chuẩn quan trọng nhất của bộ này.
    #
    # `leader.la_cau_hoi_van_hanh` bắt chữ "production", còn
    # `leader.la_cau_hoi_lich_su` bắt chữ "tại sao". Cả hai ĐÚNG cho việc
    # chúng được viết ra (đính khối probe / khối ký ức). Nhưng dùng thẳng
    # chúng làm cổng tầm thường thì:
    #
    #   "đề xuất một redesign lớn cho production architecture và phản biện"
    #       -> "production" -> tra cứu trạng thái -> KHÔNG gọi vai nào
    #   "project Fanfic nên ưu tiên phát triển phần nào tiếp theo và tại sao?"
    #       -> "tại sao" -> câu hỏi lịch sử -> KHÔNG gọi vai nào
    #
    # Cả hai đo được trên chính bộ hiệu chuẩn A–F, và cả hai là hỏng câm.
    # Một câu XIN PHÁN ĐOÁN không phải một câu tra cứu, dù nó có nhắc tới
    # production hay có chữ "tại sao" trong đó.
    co_tin_hieu_suy_luan = bool(
        d.xin_tu_van or d.chien_luoc_du_an or d.danh_doi
        or d.pham_vi_kien_truc or d.doi_phan_bien)

    # VAN HANH: dung lai chinh bo nhan dang cua V0.7 thay vi viet bo thu hai.
    # Hai danh sach song song la dung cach de chung lech nhau tro lai — va lan
    # lech truoc (`nang_luc.py` vs `router_v3.policy`) da lam moi viec xep vao
    # Codex deu chet.
    van_hanh, chan_doan, dh_vh = LEADER.la_cau_hoi_van_hanh(van)
    d.la_chan_doan = bool(chan_doan)
    d.la_tra_cuu_song = (bool(van_hanh) and not chan_doan
                         and not co_tin_hieu_suy_luan)
    if dh_vh:
        d.dau_hieu["van_hanh"] = list(dh_vh)[:4]

    # LICH SU: mot cau CHAN DOAN hoi ve HIEN TAI, khong ve qua khu — nen dau
    # hieu lich su bi tat o do. Va mot cau XIN PHAN DOAN cung khong phai cau
    # tra ky uc, du no co chu "vi sao".
    ls_tho, dh_ls = LEADER.la_cau_hoi_lich_su(van)
    d.la_lich_su = bool(ls_tho) and not chan_doan and not co_tin_hieu_suy_luan
    if d.la_lich_su and dh_ls:
        d.dau_hieu["lich_su"] = list(dh_ls)[:4]

    # THUC THI vs TU VAN — cho nay quyet dinh §11, nen no khong duoc doan.
    #
    # "nên sửa thế nào" CHUA dong tu `sửa` nhung la mot cau hoi tu van. Nen
    # dau hieu thuc thi bi VETO khi co dau hieu tu van, TRU khi co mot dau
    # hieu LAM NGAY tuong minh ("làm đi", "do it"). Cau hoi TRANG THAI cung
    # veto: "farmer hiện chạy không?" khong phai mot lenh.
    tt = _dat("thuc_thi", _THUC_THI)
    ngay = _dat("lam_ngay", _LAM_NGAY)
    d.xin_thuc_thi = bool(ngay) or (
        tt and not (d.xin_tu_van or d.danh_doi or d.chien_luoc_du_an)
        and not d.la_tra_cuu_song)
    return d


# ------------------------------------------------------------------ phan loai --

#: Trọng số cho ĐỘ KHÓ. Hằng số ở MỘT chỗ, kiểm được, và mọi con số dưới đây
#: được hiệu chuẩn trên các tình huống nghiệm thu A–F của yêu cầu v0.8.
TRONG_SO_KHO: Dict[str, float] = {
    "pham_vi_kien_truc": 2.0,
    "danh_doi": 1.2,
    "doi_phan_bien": 1.0,
    "chien_luoc_du_an": 1.0,
    "mo_ho": 0.8,
    "kho_dao_nguoc": 0.8,
    "la_chan_doan": 0.7,
    "xin_tu_van": 0.6,
    "can_nghien_cuu": 0.6,
    "nhieu_yeu_cau": 0.5,
}

#: Điểm TRỪ — những đặc trưng nói "câu này đã có nguồn trả lời tất định".
#: Số âm lớn có chủ ý: chúng phải thắng được cả một câu dài có nhiều dấu hiệu.
TRONG_SO_DE: Dict[str, float] = {
    "la_xa_giao": -5.0,
    "la_tra_cuu_kho": -3.0,
    "la_tra_cuu_song": -3.0,
    "la_lich_su": -2.0,
}

#: Trọng số cho TÁC ĐỘNG.
TRONG_SO_TAC_DONG: Dict[str, float] = {
    "tac_dong_production": 1.0,
    "kho_dao_nguoc": 1.0,
    "pham_vi_kien_truc": 1.0,
    "chien_luoc_du_an": 0.8,
    "danh_doi": 0.4,
}

NGUONG_KHO: Tuple[float, float, float] = (0.6, 1.6, 3.0)
NGUONG_TAC_DONG: Tuple[float, float] = (1.0, 2.0)


@dataclass
class PhanLoai:
    """Kết luận về một lượt. Mọi trường ở đây suy ra ĐƯỢC từ `dac_trung`."""

    bac: Bac = Bac.TAM_THUONG
    tac_dong: TacDong = TacDong.THAP
    pham_vi: PhamVi = PhamVi.LOCAL
    dao_nguoc_duoc: bool = True
    production: bool = False
    can_nghien_cuu: bool = False
    la_thuc_thi: bool = False
    #: Câu này đã có nguồn trả lời TẤT ĐỊNH (sổ/git/probe/ký ức) -> không vai.
    la_tam_thuong: bool = False
    do_tin: float = 0.0
    diem_kho: float = 0.0
    diem_tac_dong: float = 0.0
    dac_trung: DacTrung = field(default_factory=DacTrung)

    def to_dict(self) -> Dict:
        return {"bac": self.bac.value, "tac_dong": self.tac_dong.value,
                "pham_vi": self.pham_vi.value,
                "dao_nguoc_duoc": self.dao_nguoc_duoc,
                "production": self.production,
                "can_nghien_cuu": self.can_nghien_cuu,
                "la_thuc_thi": self.la_thuc_thi,
                "la_tam_thuong": self.la_tam_thuong,
                "do_tin": round(self.do_tin, 3),
                "diem_kho": round(self.diem_kho, 3),
                "diem_tac_dong": round(self.diem_tac_dong, 3),
                "dac_trung": self.dac_trung.to_dict(),
                "dau_hieu": {k: v[:3] for k, v in
                             self.dac_trung.dau_hieu.items()}}

    def giai_thich(self) -> str:
        """Bản in cho người đọc. Không có dòng này thì bộ phân loại thành
        một hộp đen, và người vận hành sẽ quay về ghim tay chế độ."""
        d = [f"độ khó   : {self.bac.value} (điểm {self.diem_kho:+.2f})",
             f"tác động : {self.tac_dong.value} (điểm {self.diem_tac_dong:+.2f})",
             f"phạm vi  : {self.pham_vi.value}",
             f"đảo được : {'CÓ' if self.dao_nguoc_duoc else 'KHÔNG'}",
             f"độ tin   : {self.do_tin:.2f}",
             f"thực thi : {'CÓ (người dùng xin làm)' if self.la_thuc_thi else 'KHÔNG (thảo luận)'}"]
        if self.la_tam_thuong:
            d.append("CỔNG TẦM THƯỜNG: câu này đã có nguồn trả lời tất định "
                     "— không gọi vai nào, ở mọi chế độ")
        if self.dac_trung.dau_hieu:
            d.append("dấu hiệu đã bắt:")
            for k, v in sorted(self.dac_trung.dau_hieu.items()):
                d.append(f"  {k}: {', '.join(v[:2])}")
        return "\n".join(d)


def phan_loai_luot(cau: str) -> PhanLoai:
    """Câu người dùng -> `PhanLoai`. Tất định, không LLM, không mạng."""
    dt = rut_dac_trung(cau)
    p = PhanLoai(dac_trung=dt)

    diem = 0.0
    for ten, w in TRONG_SO_KHO.items():
        if getattr(dt, ten, False):
            diem += w
    for ten, w in TRONG_SO_DE.items():
        if getattr(dt, ten, False):
            diem += w
    # Do dai la mot tin hieu YEU co tran: mot cau dai khong tu nhien thanh
    # mot cau kho (xem `~/.claude/CLAUDE.md`: "khong leo thang chi vi task
    # dai ve token").
    diem += min(0.6, dt.so_tu / 60.0)
    p.diem_kho = diem

    lo, tb, cao = NGUONG_KHO
    if diem < lo:
        p.bac = Bac.TAM_THUONG
    elif diem < tb:
        p.bac = Bac.THUONG
    elif diem < cao:
        p.bac = Bac.KHO
    else:
        p.bac = Bac.RAT_KHO

    td = 0.0
    for ten, w in TRONG_SO_TAC_DONG.items():
        if getattr(dt, ten, False):
            td += w
    p.diem_tac_dong = td

    # CONG TAM THUONG — rao CUNG.
    #
    # Mot cau hoi trang thai song ("production farmer con chay khong?") chua
    # chu "production", nen diem tac dong cua no khac 0. Neu khong co cong
    # nay, MAX se goi Strategist cho no. Cong dat TRUOC khi xep tac dong, va
    # no ep tac dong ve THAP: khong phai vi cau tra loi khong quan trong, ma
    # vi NGUON tra loi la mot phep do, khong phai mot phep suy luan.
    # `la_tra_cuu_song` va `la_lich_su` DA chiu phep dao o `rut_dac_trung`
    # (xem "TÍN HIỆU SUY LUẬN"), nen o day chung dung duoc thang.
    p.la_tam_thuong = bool(dt.la_xa_giao or dt.la_tra_cuu_kho
                           or dt.la_tra_cuu_song or dt.la_lich_su)
    if p.la_tam_thuong:
        p.tac_dong = TacDong.THAP
        p.bac = Bac.TAM_THUONG if p.bac.rank <= Bac.THUONG.rank else p.bac
    else:
        n1, n2 = NGUONG_TAC_DONG
        p.tac_dong = (TacDong.THAP if td < n1
                      else TacDong.TRUNG if td < n2 else TacDong.CAO)

    p.production = dt.tac_dong_production
    p.dao_nguoc_duoc = not dt.kho_dao_nguoc
    p.can_nghien_cuu = dt.can_nghien_cuu
    p.la_thuc_thi = dt.xin_thuc_thi

    if dt.tac_dong_production and (dt.pham_vi_kien_truc or dt.kho_dao_nguoc):
        p.pham_vi = PhamVi.MULTI_SYSTEM
    elif dt.pham_vi_kien_truc or dt.chien_luoc_du_an:
        p.pham_vi = PhamVi.REPO
    elif dt.xin_thuc_thi:
        p.pham_vi = PhamVi.MODULE
    else:
        p.pham_vi = PhamVi.LOCAL

    p.do_tin = _do_tin(dt, p)
    return p


def _do_tin(dt: DacTrung, p: PhanLoai) -> float:
    """Độ tin của CHÍNH PHÉP PHÂN LOẠI, trong [0,1] — không phải độ tin của
    câu trả lời.

    Cao khi lượt rơi vào một lớp phân biệt rõ (xã giao, tra cứu, hoặc một câu
    kiến trúc có nhiều dấu hiệu đồng hướng). Thấp khi điểm nằm SÁT ngưỡng —
    và `lap_ke_hoach_vai()` dùng đúng con số này để không leo thang ở chế độ
    AUTO khi phép phân loại chưa chắc.
    """
    if dt.la_xa_giao:
        return 0.95
    if p.la_tam_thuong:
        return 0.9
    manh = sum(1 for t in ("pham_vi_kien_truc", "danh_doi", "doi_phan_bien",
                           "chien_luoc_du_an", "kho_dao_nguoc")
               if getattr(dt, t, False))
    tin = 0.5 + 0.1 * manh
    # Sat nguong -> bot tin. `khoang` la khoang cach toi nguong gan nhat.
    khoang = min(abs(p.diem_kho - x) for x in NGUONG_KHO)
    if khoang < 0.25:
        tin -= 0.15
    elif khoang < 0.5:
        tin -= 0.07
    # LAM TRON TRUOC KHI SO NGUONG. Khong co dong nay thi `0.6 - 0.15` ra
    # 0.44999999999999996 trong dau phay dong, va mot luot dang le leo thang
    # (`>= 0.45`) im lang khong leo thang — dung kieu loi khong ai truy ra
    # duoc tu ban ghi dinh tuyen.
    return round(max(0.2, min(0.95, tin)), 3)


# ------------------------------------------------------------- ke hoach vai --

@dataclass
class KeHoachVai:
    """Vai nào chạy lượt này, và VÌ SAO. Đây là thứ giao diện hiển thị."""

    vai: Tuple[VaiTro, ...] = ()
    ly_do: str = ""
    #: Reviewer bắt buộc vì NGƯỜI DÙNG xin phản biện tường minh (≠ vì điểm).
    phan_bien_tuong_minh: bool = False
    che_do: CheDo = CheDo.AUTO
    #: Ghi lại NGƯỠNG đã dùng — để một lượt không leo thang giải thích được.
    nguong: Dict[str, Any] = field(default_factory=dict)

    @property
    def co_strategist(self) -> bool:
        return VaiTro.STRATEGIST in self.vai

    @property
    def co_reviewer(self) -> bool:
        return VaiTro.REVIEWER in self.vai

    def to_dict(self) -> Dict:
        return {"vai": [v.value for v in self.vai], "ly_do": self.ly_do,
                "phan_bien_tuong_minh": self.phan_bien_tuong_minh,
                "che_do": self.che_do.value, "nguong": dict(self.nguong)}


#: Bậc độ khó TỐI THIỂU để gọi Strategist, theo chế độ chất lượng.
#:
#: ECO không phải "tắt Strategist": một câu RẤT KHÓ vẫn đáng một bộ não
#: mạnh, và ECO đã tiết kiệm ở chỗ khác (Astra bị `GacAstra` cấm tuyệt đối,
#: và `dinh_tuyen.py` hạ `reasoning_level` xuống MEDIUM).
NGUONG_STRATEGIST: Dict[CheDo, Bac] = {
    CheDo.ECO: Bac.RAT_KHO,
    CheDo.AUTO: Bac.KHO,
    CheDo.STRONG: Bac.THUONG,
    CheDo.MAX: Bac.THUONG,
}

#: Độ tin TỐI THIỂU của phép phân loại để AUTO/ECO leo thang. STRONG/MAX là
#: lựa chọn TƯỜNG MINH của người dùng, nên chúng không đòi ngưỡng này.
DO_TIN_TOI_THIEU: Dict[CheDo, float] = {
    CheDo.ECO: 0.5, CheDo.AUTO: 0.45, CheDo.STRONG: 0.0, CheDo.MAX: 0.0,
}


def lap_ke_hoach_vai(p: PhanLoai, che_do: CheDo) -> KeHoachVai:
    """`PhanLoai` + chế độ -> vai nào chạy. Tất định và giải thích được.

    LEADER luôn có mặt: nó sở hữu hội thoại và nó tổng hợp. Câu hỏi thật của
    hàm này là "có gọi thêm bộ não nào không".
    """
    kh = KeHoachVai(che_do=che_do)
    nguong_bac = NGUONG_STRATEGIST[che_do]
    kh.nguong = {"bac_toi_thieu": nguong_bac.value,
                 "do_tin_toi_thieu": DO_TIN_TOI_THIEU[che_do],
                 "bac_do_duoc": p.bac.value, "do_tin_do_duoc": round(p.do_tin, 2)}

    if p.la_tam_thuong:
        kh.vai = (VaiTro.LEADER,)
        kh.ly_do = ("CỔNG TẦM THƯỜNG: lượt này có nguồn trả lời tất định "
                    "(sổ/git/probe/ký ức) — không gọi vai suy luận nào, kể cả "
                    "ở chế độ MAX")
        return kh

    # YÊU CẦU THỰC THI RÕ RÀNG -> ROUTER V4, KHÔNG PHẢI HỘI ĐỒNG.
    #
    # "sửa bug ở store.py rồi chạy test" không cần một bản chiến lược; nó cần
    # một worker. Cân nhắc kiến trúc cho một việc đã rõ hình dạng là tiêu hai
    # lượt model để nói lại đúng thứ người dùng vừa nói.
    #
    # Ngưỡng là `KHO`: một yêu cầu thực thi ĐỦ KHÓ ("refactor toàn bộ tầng lưu
    # trữ") vẫn đáng được lập kế hoạch trước — lúc đó Strategist chạy, rồi
    # Leader vẫn uỷ thác như thường.
    if p.la_thuc_thi and p.bac.rank < Bac.KHO.rank:
        kh.vai = (VaiTro.LEADER,)
        kh.ly_do = (f"người dùng xin THỰC THI và việc ở bậc {p.bac.value} "
                    f"(< KHO) — đi thẳng Router V4, không cần hội đồng")
        return kh

    # PHAN BIEN TUONG MINH thang moi nguong, ke ca ECO: nguoi dung xin bi
    # phan bac thi khong co con so nao duoc lat lai loi xin do. ECO van tiet
    # kiem bang cach ha bac suy luan va cam Astra.
    kh.phan_bien_tuong_minh = p.dac_trung.doi_phan_bien

    du_tin = p.do_tin >= DO_TIN_TOI_THIEU[che_do]
    du_bac = p.bac.rank >= nguong_bac.rank
    goi_strategist = (du_bac and du_tin) or kh.phan_bien_tuong_minh

    if not goi_strategist:
        kh.vai = (VaiTro.LEADER,)
        if not du_bac:
            kh.ly_do = (f"độ khó {p.bac.value} dưới ngưỡng {nguong_bac.value} "
                        f"của chế độ {che_do.value} — Leader trả lời một mình")
        else:
            kh.ly_do = (f"độ khó {p.bac.value} đạt ngưỡng nhưng phép phân loại "
                        f"chỉ tin {p.do_tin:.2f} (<{DO_TIN_TOI_THIEU[che_do]:.2f}) "
                        f"— không leo thang khi chưa chắc")
        return kh

    # REVIEWER. Ba duong vao, va chung KHAC NHAU ve nghia:
    #   1. nguoi dung xin tuong minh;
    #   2. viec RAT KHO (mot ban chien luoc khong ai soi la mot ban chua xong);
    #   3. viec KHO + tac dong CAO (kien truc/production/khong dao nguoc duoc).
    ly_reviewer = ""
    if kh.phan_bien_tuong_minh:
        ly_reviewer = "người dùng xin phản biện tường minh"
    elif che_do is CheDo.ECO:
        # ECO = "minimal escalation". Mot Reviewer la mot luot model NUA, nen
        # o ECO no chi chay khi nguoi dung XIN — nhanh tren da bat truong hop
        # do roi. Khong co dong nay thi ECO va AUTO giong het nhau tren moi
        # cau RAT_KHO, tuc la ECO khong tiet kiem gi.
        ly_reviewer = ""
    elif che_do is CheDo.MAX:
        ly_reviewer = "chế độ MAX: mọi bản chiến lược đều được soi độc lập"
    elif p.bac is Bac.RAT_KHO:
        ly_reviewer = f"độ khó {p.bac.value}"
    elif p.bac is Bac.KHO and p.tac_dong is TacDong.CAO:
        ly_reviewer = (f"độ khó {p.bac.value} + tác động {p.tac_dong.value} "
                       f"(phạm vi {p.pham_vi.value}"
                       + (", KHÔNG đảo ngược được" if not p.dao_nguoc_duoc else "")
                       + ")")
    elif che_do is CheDo.STRONG and p.bac.rank >= Bac.KHO.rank:
        ly_reviewer = "chế độ STRONG: việc khó được soi độc lập"

    # LY DO PHAI DUNG. Strategist co the duoc goi vi DU BAC, hoac vi NGUOI
    # DUNG XIN PHAN BIEN — va hai thu do khong thay nhau duoc. Ban dau dong
    # nay luon in "độ khó X ≥ Y", nen mot luot ECO bac THUONG co chu "phản
    # biện" se khoe "THUONG ≥ RAT_KHO" ngay tren bang dieu khien.
    ly_strategist = (f"độ khó {p.bac.value} ≥ {nguong_bac.value} "
                     f"({che_do.value})" if (du_bac and du_tin)
                     else "người dùng xin phản biện tường minh nên cần một bản "
                          "chiến lược để phản biện")
    if ly_reviewer:
        kh.vai = (VaiTro.LEADER, VaiTro.STRATEGIST, VaiTro.REVIEWER)
        kh.ly_do = f"Strategist: {ly_strategist}; Reviewer: {ly_reviewer}"
    else:
        kh.vai = (VaiTro.LEADER, VaiTro.STRATEGIST)
        kh.ly_do = (f"Strategist: {ly_strategist}; Reviewer: KHÔNG — tác động "
                    f"{p.tac_dong.value} chưa đủ và người dùng không xin phản biện")
    return kh
