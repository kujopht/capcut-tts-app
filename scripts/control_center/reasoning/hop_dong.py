"""HỢP ĐỒNG CHIẾN LƯỢC — lược đồ đầu ra của Strategist và Reviewer (V0.8).

VÌ SAO PHẢI CÓ LƯỢC ĐỒ, chứ không nhận văn xuôi. Nếu Strategist trả về một
đoạn văn và Reviewer trả về một đoạn văn khác, thì Leader phải TỰ ĐỌC HIỂU
hai đoạn văn để biết "bản phản biện có chấp nhận không". Lúc đó cả kiến trúc
ba vai chỉ là ba lần gọi model rồi nối chuỗi — và chính cái tín hiệu mà
Reviewer tồn tại để tạo ra (ACCEPT / REVISE / REJECT) trở thành thứ phải
đoán từ giọng điệu.

Nên: **phán xử là một trường có kiểu, và không đọc được nó là FAIL CLOSED.**
Cùng khuôn với `leader.doc_quyet_dinh`: thứ có hậu quả đòi JSON hợp lệ, thứ
vô hại thì khoan dung.

KHÔNG ĐỔ NHẮC NHỞ THÔ RA CHO NGƯỜI DÙNG (§10 câu cuối). `to_khoi_leader()`
trả một khối GỌN, có cấu trúc, để Leader tổng hợp; nhắc nhở gốc và văn bản
thô của vai chỉ đi vào nhật ký chẩn đoán. Người dùng đọc câu trả lời của
Leader, không đọc biên bản nội bộ.

MỘT ĐỀ XUẤT KHÔNG PHẢI MỘT QUYẾT ĐỊNH (§18). `BanChienLuoc` mang nhãn
`de_xuat` ở mọi chỗ nó hiện ra, và `LUAT_HOI_DONG` trong `leader.py` nói
thẳng rằng thẩm quyền của người dùng khác với kiến nghị của model. Không
đường nào trong gói này ghi một bản chiến lược vào ký ức như một quyết định
đang hiệu lực.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class HopDongLoi(ValueError):
    """Đầu ra của vai không dùng được. FAIL CLOSED."""


class PhanXu(str, Enum):
    """Phán xử của Reviewer. Danh sách ĐÓNG — một phán xử lạ bị từ chối."""

    ACCEPT = "ACCEPT"
    REVISE = "REVISE"
    REJECT = "REJECT"

    @property
    def nhan(self) -> str:
        return {"ACCEPT": "CHẤP NHẬN", "REVISE": "SỬA LẠI",
                "REJECT": "TỪ CHỐI"}[self.value]


def _khoi_json(van: str) -> Optional[Dict]:
    """Khối JSON đầu tiên trong một câu trả lời. `None` nếu không có.

    Chép cùng chiến lược khoan dung với `leader._khoi_json` — model hay bọc
    JSON trong ```…``` hoặc kèm một câu dẫn, và đòi model tuyệt đối sạch
    nghĩa là mỗi lần nó lịch sự thêm một chữ là cả lượt hỏng.
    """
    van = (van or "").strip()
    if not van:
        return None
    ung: List[str] = []
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", van, re.S)
    if m:
        ung.append(m.group(1))
    i = van.find("{")
    if i >= 0:
        ung.append(van[i:van.rfind("}") + 1])
    ung.append(van)
    for x in ung:
        try:
            o = json.loads(x)
        except (ValueError, TypeError):
            continue
        if isinstance(o, dict):
            return o
    return None


def _ds(v: Any, *, toi_da: int = 10, dai: int = 400) -> Tuple[str, ...]:
    """Một trường "danh sách" từ model -> tuple chuỗi đã cắt.

    Nhận cả chuỗi nhiều dòng: model rất hay trả `"- a\\n- b"` cho một mảng,
    và từ chối nó chỉ để đúng lược đồ sẽ làm mất nội dung thật.
    """
    if v is None:
        return ()
    if isinstance(v, str):
        phan = [x.strip(" -*\t") for x in v.splitlines()]
        return tuple(x[:dai] for x in phan if x)[:toi_da]
    if isinstance(v, (list, tuple)):
        ra: List[str] = []
        for x in v:
            if isinstance(x, dict):
                # `{"option": "...", "trade_off": "..."}` -> mot dong doc duoc.
                x = " — ".join(f"{k}: {vv}" for k, vv in x.items() if vv)
            s = str(x).strip()
            if s:
                ra.append(s[:dai])
        return tuple(ra)[:toi_da]
    return (str(v)[:dai],)


def _lay(o: Dict, *khoa: str) -> Any:
    """Giá trị của khoá ĐẦU TIÊN CÓ MẶT. `None` khi không khoá nào có.

    KHÔNG dùng `o.get(a) or o.get(b)`, và đây là một lỗi đã đo được: với
    `{"do_tin": 0}` thì `0 or None` cho ra `None`, tức là một độ tin "0"
    (model nói thẳng nó không tin bản này) bị đọc thành "model không nêu độ
    tin". Đúng một lớp lỗi với "UNAVAILABLE vs 0" mà `UsageMetric` ép bằng
    máy — chỉ khác là ở đây `or` làm hỏng chứ không ai gõ sai.
    """
    for k in khoa:
        if k in o:
            return o[k]
    return None


def _so(v: Any) -> Optional[float]:
    """Độ tin -> `float` trong [0,1], hoặc `None`.

    `None` là một giá trị hợp lệ và nó KHÁC `0.0`: "model không nói độ tin"
    không phải "model hoàn toàn không tin". Cùng luật với `UsageMetric`.
    """
    if v is None or v == "":
        return None
    if isinstance(v, str):
        s = v.strip().rstrip("%")
        nhan = {"high": 0.85, "cao": 0.85, "medium": 0.6, "trung": 0.6,
                "trung bình": 0.6, "low": 0.3, "thấp": 0.3}.get(s.lower())
        if nhan is not None:
            return nhan
        try:
            v = float(s)
        except ValueError:
            return None
        if v > 1.0:
            v = v / 100.0
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- strategist --

@dataclass
class BanChienLuoc:
    """Đầu ra của Strategist. Một ĐỀ XUẤT, không phải một quyết định."""

    muc_tieu: str = ""
    bang_chung: Tuple[str, ...] = ()
    gia_dinh: Tuple[str, ...] = ()
    phuong_an: Tuple[str, ...] = ()
    danh_doi: Tuple[str, ...] = ()
    de_xuat: str = ""
    rui_ro: Tuple[str, ...] = ()
    viec_can_lam: Tuple[str, ...] = ()
    do_tin: Optional[float] = None
    cau_hoi_can_nguoi: Tuple[str, ...] = ()
    tho: str = ""                       # van ban goc, CHI cho chan doan

    @property
    def dung_duoc(self) -> bool:
        """Có đủ để Leader tổng hợp không.

        `de_xuat` HOẶC `phuong_an` là tối thiểu: một bản chiến lược không nêu
        được hướng nào cũng không nêu được phương án nào thì nó chưa là một
        bản chiến lược, và Leader tổng hợp từ nó sẽ chỉ diễn đạt lại câu hỏi.
        """
        return bool(self.de_xuat.strip() or self.phuong_an)

    def to_dict(self) -> Dict:
        return {"muc_tieu": self.muc_tieu, "bang_chung": list(self.bang_chung),
                "gia_dinh": list(self.gia_dinh),
                "phuong_an": list(self.phuong_an),
                "danh_doi": list(self.danh_doi), "de_xuat": self.de_xuat,
                "rui_ro": list(self.rui_ro),
                "viec_can_lam": list(self.viec_can_lam), "do_tin": self.do_tin,
                "cau_hoi_can_nguoi": list(self.cau_hoi_can_nguoi),
                "dung_duoc": self.dung_duoc}

    def to_khoi_leader(self) -> str:
        """Khối GỌN cho nhắc nhở của Leader. Không chứa nhắc nhở gốc."""
        d = ["BẢN CHIẾN LƯỢC (do vai STRATEGIST soạn — ĐỀ XUẤT, chưa phải "
             "quyết định của bạn hay của người dùng)"]
        if self.muc_tieu:
            d.append(f"Mục tiêu       : {self.muc_tieu[:300]}")
        _ke(d, "Bằng chứng đã dựa", self.bang_chung)
        _ke(d, "Giả định", self.gia_dinh)
        _ke(d, "Phương án", self.phuong_an)
        _ke(d, "Đánh đổi", self.danh_doi)
        if self.de_xuat:
            d.append(f"Hướng đề xuất  : {self.de_xuat[:600]}")
        _ke(d, "Rủi ro", self.rui_ro)
        _ke(d, "Việc sẽ cần (CHƯA tạo việc nào)", self.viec_can_lam)
        d.append(f"Độ tin của Strategist: "
                 + (f"{self.do_tin:.2f}" if self.do_tin is not None
                    else "KHÔNG NÊU"))
        _ke(d, "Câu hỏi cần THẨM QUYỀN CỦA NGƯỜI DÙNG", self.cau_hoi_can_nguoi)
        return "\n".join(d)


def _ke(d: List[str], nhan: str, ds: Sequence[str], *, toi_da: int = 6) -> None:
    if not ds:
        return
    d.append(f"{nhan}:")
    d += [f"  - {x[:300]}" for x in ds[:toi_da]]


def doc_ban_chien_luoc(van: str) -> BanChienLuoc:
    """Văn bản Strategist trả về -> `BanChienLuoc`. Ném khi không dùng được.

    Không có JSON thì vẫn thử đọc theo TIÊU ĐỀ MỤC: một bản chiến lược viết
    bằng văn xuôi có đầu mục vẫn là một bản chiến lược, và ném nó đi để giữ
    lược đồ cho sạch sẽ là đánh đổi sai — khác hẳn với phán xử của Reviewer,
    nơi một giá trị sai có hậu quả.
    """
    o = _khoi_json(van)
    if o is None:
        o = _theo_tieu_de(van)
    b = BanChienLuoc(
        muc_tieu=str(o.get("muc_tieu") or o.get("goal") or "")[:600],
        bang_chung=_ds(o.get("bang_chung") or o.get("current_evidence")
                       or o.get("evidence")),
        gia_dinh=_ds(o.get("gia_dinh") or o.get("assumptions")),
        phuong_an=_ds(o.get("phuong_an") or o.get("options")),
        danh_doi=_ds(o.get("danh_doi") or o.get("trade_offs")
                     or o.get("tradeoffs")),
        de_xuat=str(o.get("de_xuat") or o.get("recommended_direction")
                    or o.get("recommendation") or "")[:1500],
        rui_ro=_ds(o.get("rui_ro") or o.get("risks")),
        viec_can_lam=_ds(o.get("viec_can_lam") or o.get("required_work")),
        do_tin=_so(_lay(o, "do_tin", "confidence")),
        cau_hoi_can_nguoi=_ds(o.get("cau_hoi_can_nguoi")
                              or o.get("questions_requiring_user_authority")
                              or o.get("questions")),
        tho=van or "")
    if not b.dung_duoc:
        raise HopDongLoi(
            "bản chiến lược không nêu được hướng đề xuất nào và cũng không nêu "
            "phương án nào — không dùng được để tổng hợp")
    return b


#: Tiêu đề mục -> khoá lược đồ, cho đường đọc văn xuôi dự phòng.
_TIEU_DE: Tuple[Tuple[str, str], ...] = (
    (r"mục tiêu|^goal", "muc_tieu"),
    (r"bằng chứng|current evidence|^evidence", "bang_chung"),
    (r"giả định|assumptions?", "gia_dinh"),
    (r"phương án|options?", "phuong_an"),
    (r"đánh đổi|trade-?offs?", "danh_doi"),
    (r"hướng đề xuất|đề xuất|recommend(ed)?( direction)?", "de_xuat"),
    (r"rủi ro|risks?", "rui_ro"),
    (r"việc (cần|sẽ cần)|required work", "viec_can_lam"),
    (r"độ tin|confidence", "do_tin"),
    (r"câu hỏi|questions?", "cau_hoi_can_nguoi"),
    (r"phán xử|verdict", "phan_xu"),
    (r"khẳng định (không|thiếu)|unsupported claims?", "khang_dinh_khong_chung"),
    (r"bằng chứng thiếu|missing evidence", "bang_chung_thieu"),
    (r"(vi phạm|xung đột) ràng buộc|constraint conflicts?", "xung_dot_rang_buoc"),
    (r"phát hiện rủi ro|risk findings?", "phat_hien_rui_ro"),
    (r"sửa|đề nghị sửa|suggested corrections?", "de_nghi_sua"),
)


def _theo_tieu_de(van: str) -> Dict[str, Any]:
    """Đọc một đầu ra văn xuôi CÓ ĐẦU MỤC thành dict lược đồ.

    Chỉ nhận những dòng đầu mục ở đầu dòng theo dạng `Nhãn:` hoặc
    `## Nhãn` — không đi mò trong câu, vì mò trong câu sẽ bắt nhầm chính nội
    dung (một câu "rủi ro chính là …" nằm trong mục Đề xuất sẽ mở một mục
    mới và cắt đôi phần đề xuất).
    """
    ra: Dict[str, Any] = {}
    khoa_hien = ""
    dem: Dict[str, List[str]] = {}
    for dong in (van or "").splitlines():
        s = dong.strip()
        if not s:
            continue
        dau = re.match(r"^\s*(?:[#*\-\d.)\s]*)([A-Za-zÀ-ỹ][^:#]{2,60})\s*[::]\s*(.*)$", dong)
        nhan = (dau.group(1).strip().lower() if dau else
                (re.sub(r"^#+\s*", "", s).strip().lower()
                 if s.startswith("#") else ""))
        khoa_moi = ""
        if nhan:
            for mau, khoa in _TIEU_DE:
                if re.search(rf"^({mau})\b", nhan, re.I):
                    khoa_moi = khoa
                    break
        if khoa_moi:
            khoa_hien = khoa_moi
            dem.setdefault(khoa_hien, [])
            con = (dau.group(2).strip() if dau else "")
            if con:
                dem[khoa_hien].append(con)
            continue
        if khoa_hien:
            dem[khoa_hien].append(s.lstrip("-*• \t"))
    for k, v in dem.items():
        ra[k] = "\n".join(v).strip()
    return ra


# ----------------------------------------------------------------- reviewer --

@dataclass
class BanPhanBien:
    """Đầu ra của Reviewer. `phan_xu` là trường KHÔNG được đoán."""

    phan_xu: PhanXu = PhanXu.REVISE
    khang_dinh_khong_chung: Tuple[str, ...] = ()
    bang_chung_thieu: Tuple[str, ...] = ()
    xung_dot_rang_buoc: Tuple[str, ...] = ()
    phat_hien_rui_ro: Tuple[str, ...] = ()
    de_nghi_sua: Tuple[str, ...] = ()
    do_tin: Optional[float] = None
    tho: str = ""

    @property
    def co_phat_hien(self) -> bool:
        return bool(self.khang_dinh_khong_chung or self.bang_chung_thieu
                    or self.xung_dot_rang_buoc or self.phat_hien_rui_ro)

    def to_dict(self) -> Dict:
        return {"phan_xu": self.phan_xu.value,
                "khang_dinh_khong_chung": list(self.khang_dinh_khong_chung),
                "bang_chung_thieu": list(self.bang_chung_thieu),
                "xung_dot_rang_buoc": list(self.xung_dot_rang_buoc),
                "phat_hien_rui_ro": list(self.phat_hien_rui_ro),
                "de_nghi_sua": list(self.de_nghi_sua), "do_tin": self.do_tin,
                "co_phat_hien": self.co_phat_hien}

    def to_khoi_leader(self, *, doc_lap: Optional[bool] = None,
                       nguon: str = "") -> str:
        d = [f"BẢN PHẢN BIỆN (do vai REVIEWER soạn{(' — ' + nguon) if nguon else ''})",
             f"Phán xử: {self.phan_xu.value} ({self.phan_xu.nhan})"]
        if doc_lap is False:
            d.append("(!) ĐỘ ĐỘC LẬP SUY GIẢM: Reviewer chạy CÙNG họ model với "
                     "Strategist — đây là một lần tự đọc lại, không phải một "
                     "phản biện độc lập. Nói rõ điều này khi trả lời.")
        _ke(d, "Khẳng định KHÔNG có bằng chứng", self.khang_dinh_khong_chung)
        _ke(d, "Bằng chứng còn thiếu", self.bang_chung_thieu)
        _ke(d, "Xung đột với ràng buộc dự án", self.xung_dot_rang_buoc)
        _ke(d, "Phát hiện rủi ro", self.phat_hien_rui_ro)
        _ke(d, "Đề nghị sửa", self.de_nghi_sua)
        d.append("Độ tin của Reviewer: "
                 + (f"{self.do_tin:.2f}" if self.do_tin is not None
                    else "KHÔNG NÊU"))
        return "\n".join(d)


def doc_ban_phan_bien(van: str) -> BanPhanBien:
    """Văn bản Reviewer trả về -> `BanPhanBien`. FAIL CLOSED ở `phan_xu`.

    Không đọc được phán xử thì NÉM. Đây là chỗ khác biệt có ý thức so với
    `doc_ban_chien_luoc`: một bản chiến lược thiếu mục vẫn hữu ích, còn một
    phán xử ĐOÁN SAI là tồi tệ nhất trong cả kiến trúc — nó có thể biến một
    REJECT thành một ACCEPT trong phần tổng hợp.
    """
    o = _khoi_json(van)
    if o is None:
        o = _theo_tieu_de(van)
    tho_px = str(o.get("phan_xu") or o.get("verdict") or "").strip().upper()
    # Chi nhan dung ba gia tri. `ACCEPT WITH CHANGES` -> REVISE la mot phep
    # chuan hoa AN TOAN (nghieng ve phia can nguoi xem lai), khong phai mot
    # phep doan: no khong bao gio bien mot REJECT thanh ACCEPT.
    m = re.search(r"\b(ACCEPT|REVISE|REJECT)\b", tho_px)
    if m is None:
        m = re.search(r"\b(ACCEPT|REVISE|REJECT)\b", (van or "").upper())
    if m is None:
        raise HopDongLoi(
            "bản phản biện không nêu phán xử ACCEPT/REVISE/REJECT đọc được — "
            "FAIL CLOSED: không đoán phán xử, vì đoán sai một REJECT thành "
            "ACCEPT là chế độ hỏng tệ nhất của kiến trúc này")
    px = PhanXu(m.group(1))
    if px is PhanXu.ACCEPT and re.search(r"\bWITH (CHANGES|CAVEATS|CONDITIONS)\b",
                                         tho_px):
        px = PhanXu.REVISE
    return BanPhanBien(
        phan_xu=px,
        khang_dinh_khong_chung=_ds(o.get("khang_dinh_khong_chung")
                                   or o.get("unsupported_claims")),
        bang_chung_thieu=_ds(o.get("bang_chung_thieu")
                             or o.get("missing_evidence")),
        xung_dot_rang_buoc=_ds(o.get("xung_dot_rang_buoc")
                               or o.get("constraint_conflicts")),
        phat_hien_rui_ro=_ds(o.get("phat_hien_rui_ro")
                             or o.get("risk_findings")),
        de_nghi_sua=_ds(o.get("de_nghi_sua")
                        or o.get("suggested_corrections")),
        do_tin=_so(_lay(o, "do_tin", "confidence")),
        tho=van or "")


# ------------------------------------------------------------------- nhac nho --

#: Nhắc nhở cho STRATEGIST. Ba điều nó phải biết, và cả ba đều đã trả giá:
#:
#: * KHÔNG CÓ CÔNG CỤ — `agy --print` tự chối mọi công cụ cần duyệt quyền
#:   (đo 2026-09-10). Mọi thứ nó cần đã nằm trong gói ngữ cảnh.
#: * UNKNOWN LÀ CÂU TRẢ LỜI HỢP LỆ — bài học đo được của V0.7: khi mục
#:   "Kiến trúc lưu trữ" chỉ có tên tài liệu, một lượt vẫn khẳng định chắc
#:   nịch vai trò của R2 và Google Drive, không mã bằng chứng nào.
#: * NÓ ĐỀ XUẤT, KHÔNG QUYẾT — §18.
NHAC_STRATEGIST = """\
Bạn là **STRATEGIST** — vai suy luận sâu bên trong Router Control Center. Bạn
KHÔNG nói chuyện với người dùng; đầu ra của bạn đi cho Project Leader tổng hợp.

BẠN KHÔNG CÓ CÔNG CỤ NÀO. Không đọc tệp, không mở URL, không chạy lệnh —
phiên này chạy headless nên mọi công cụ cần duyệt quyền sẽ bị TỰ ĐỘNG TỪ CHỐI
và lượt của bạn kết thúc RỖNG. Mọi bằng chứng bạn được phép dùng đã nằm trong
các khối DỮ LIỆU bên dưới.

BA LUẬT KHÔNG ĐƯỢC PHÁ:

1. **Mỗi khẳng định về dự án phải KÈM MÃ bằng chứng** lấy từ khối dữ liệu
   (`qd_…`, `ku_…`, `sk#…`, `doc:…`, tên tệp, SHA commit). Không có mã cho một
   ý thì nói rõ đó là GIẢ ĐỊNH của bạn và đặt nó vào mục `gia_dinh`.
2. **UNKNOWN là câu trả lời hợp lệ.** Một mục chỉ chứa TÊN TÀI LIỆU là CHỖ ĐỂ
   TRA, không phải câu trả lời. Thiếu bằng chứng thì viết thẳng "hồ sơ dự án
   chưa ghi rõ X" và đưa X vào `cau_hoi_can_nguoi` — TUYỆT ĐỐI không lấy kiến
   thức chung về công nghệ đó mà nói như thể đó là sự thật của dự án này.
3. **Bạn ĐỀ XUẤT, bạn không QUYẾT.** `viec_can_lam` là việc SẼ CẦN nếu người
   dùng đồng ý — không việc nào được tạo từ đầu ra của bạn. Thứ cần thẩm quyền
   của người dùng thì đặt vào `cau_hoi_can_nguoi`.

Trả về ĐÚNG một khối JSON, không kèm chữ nào ngoài khối:

{"muc_tieu": "...",
 "bang_chung": ["... (kèm mã)"],
 "gia_dinh": ["..."],
 "phuong_an": ["A: ...", "B: ..."],
 "danh_doi": ["A đổi X lấy Y; B ngược lại"],
 "de_xuat": "hướng bạn khuyên, và vì sao",
 "rui_ro": ["..."],
 "viec_can_lam": ["..."],
 "do_tin": 0.0-1.0,
 "cau_hoi_can_nguoi": ["..."]}
"""

#: Nhắc nhở cho REVIEWER. Nó KHÔNG được "review giúp cho đẹp": mặc định của
#: một bản phản biện không tìm ra gì là ACCEPT, và một ACCEPT rỗng là tín
#: hiệu hợp lệ — nhưng một REVISE/REJECT phải nêu được phát hiện cụ thể.
NHAC_REVIEWER = """\
Bạn là **REVIEWER** — vai phản biện ĐỘC LẬP bên trong Router Control Center.
Bạn KHÔNG nói chuyện với người dùng. Việc của bạn là soi BẢN CHIẾN LƯỢC bên
dưới và tìm ra chỗ nó SAI hoặc chỗ nó KHÔNG CÓ BẰNG CHỨNG.

BẠN KHÔNG CÓ CÔNG CỤ NÀO (headless tự chối mọi công cụ cần duyệt quyền). Bạn
chỉ có đúng những khối dữ liệu dưới đây — và đó là một phần của việc: nếu bản
chiến lược khẳng định một điều mà KHÔNG khối nào chống lưng, thì đó chính là
một phát hiện, không phải một thứ bạn phải đi tra.

BỐN LUẬT:

1. **Đừng phản biện cho có.** Không tìm ra gì thật thì `phan_xu` = ACCEPT và
   các danh sách để rỗng. Một ACCEPT trung thực hữu ích hơn ba phát hiện bịa.
2. **REVISE/REJECT phải có phát hiện cụ thể.** Nêu ĐÚNG câu bị nghi và nói
   thiếu bằng chứng gì.
3. **Kiểm cả RÀNG BUỘC dự án** trong khối dữ liệu (quyết định đang hiệu lực,
   ràng buộc, yêu cầu). Một đề xuất vi phạm một quyết định `hieu_luc` là
   `xung_dot_rang_buoc`, và nó nặng hơn một rủi ro kỹ thuật.
4. **Bất đồng ý kiến KHÔNG phải lỗi vận chuyển.** Nếu bạn không đồng ý với
   Strategist, hãy nói REJECT kèm lý do — đừng trả về rỗng.

Trả về ĐÚNG một khối JSON, không kèm chữ nào ngoài khối:

{"phan_xu": "ACCEPT|REVISE|REJECT",
 "khang_dinh_khong_chung": ["..."],
 "bang_chung_thieu": ["..."],
 "xung_dot_rang_buoc": ["..."],
 "phat_hien_rui_ro": ["..."],
 "de_nghi_sua": ["..."],
 "do_tin": 0.0-1.0}
"""
