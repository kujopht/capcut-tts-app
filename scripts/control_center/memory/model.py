"""Từ vựng của ký ức dự án — và những bất biến được cưỡng chế bằng mã.

Mỗi kiểu ở đây mang một `__post_init__` ném khi bản ghi VI PHẠM một điều
mà phần còn lại của gói dựa vào. Cách này rẻ hơn mọi bài kiểm ở tầng
trên: một bản ghi sai không thể tồn tại, nên không cần kiểm nó ở mọi chỗ
đọc.

BA BẤT BIẾN QUAN TRỌNG NHẤT:

1. **Mọi bản ghi có mốc thời gian THẬT.** `ts` là lúc ghi, `ts_su_kien` là
   lúc chuyện xảy ra. Không có "bây giờ" ngầm định — một ký ức không biết
   nó cũ bao nhiêu thì không thể nói "3 ngày trước", và Leader sẽ đọc nó
   như hiện tại. Đây là đối trọng của `observability.QuanSat.han_tuoi=0 =
   không bao giờ cũ`: với ký ức, mặc định đó là NGƯỢC.
2. **Ước lượng token là THEO BYTE.** `uoc_token()` không cần tokenizer:
   với mọi BPE mức byte, `tokens ≤ số byte UTF-8` là một chặn trên toán
   học, không phải heuristic. Chia cho `BPT` (byte/token) chỉ để ước lượng
   gần; chặn trên thì luôn giữ. Tiếng Việt nhiều dấu → nhiều byte → ước
   lượng cao hơn → an toàn hơn.
3. **Chuẩn hoá NFC MỘT LẦN ở biên vào.** `chuan_hoa()` chạy trước mọi băm.
   Bỏ bước này thì "quan sát" dạng NFC và dạng NFD ra HAI sha256 khác
   nhau và phép khử trùng lặp vỡ âm thầm.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ------------------------------------------------------------- chuẩn hoá ----

#: Byte trên một token, để ƯỚC LƯỢNG. 2.5 là mức "an toàn" (ước cao) —
#: khảo sát: Claude ≈ 3.0, o200k ≈ 4.0, cl100k ≈ 2.8. Chọn mức thấp vì
#: đây là một NGÂN SÁCH: ước cao thì gói nhỏ hơn thật, không bao giờ lớn
#: hơn thật.
BPT = 2.5


def chuan_hoa(s: Any) -> str:
    """NFC. Mọi chuỗi đi vào kho đều qua đây trước khi băm hay lưu."""
    return unicodedata.normalize("NFC", str(s if s is not None else ""))


def gap_dau(s: str) -> str:
    """Gấp dấu về ASCII + `đ`→`d`, chữ thường — cho cột `chuan`.

    Vì sao cần dù FTS5 đã có `remove_diacritics 2`: (a) rd=2 KHÔNG gấp
    `đ`→`d` (đo được), nên "du an" không khớp "dự án" ở ký tự đ; (b) đây
    là đường DỰ PHÒNG khi FTS5 không dựng được — `LIKE` trên cột này vẫn
    tra không dấu, không phân biệt hoa thường được.
    """
    t = chuan_hoa(s).lower().replace("đ", "d").replace("Đ", "d")
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def bam(s: Any) -> str:
    """sha256 của NFC(s), hex."""
    return hashlib.sha256(chuan_hoa(s).encode("utf-8")).hexdigest()


def uoc_token(s: Any, bpt: float = BPT) -> int:
    """Ước lượng token từ BYTE UTF-8, kèm chặn trên `≤ số byte`."""
    b = len(chuan_hoa(s).encode("utf-8"))
    if b == 0:
        return 0
    return min(b, max(1, math.ceil(b / bpt)))


def khong_gian_ten(project_id: str) -> str:
    """Tên thư mục cho một dự án: đọc được + không thể thoát đường dẫn.

    `project_id` do NGƯỜI DÙNG gõ (`POST /api/project`), nên nó có thể là
    `../..` hay `C:\\x`. Phần đọc được bị làm sạch về `[a-z0-9_-]`, phần
    băm giữ tính duy nhất — hai dự án "Fanfic" và "fanfic" không được đụng
    nhau chỉ vì làm sạch làm chúng giống nhau.
    """
    goc = re.sub(r"[^a-z0-9_-]+", "_", chuan_hoa(project_id).lower())
    goc = goc.strip("_")[:40] or "du_an"
    return f"{goc}-{bam(project_id)[:10]}"


# ---------------------------------------------------------------- enum ----

class LoaiKyUc(str, Enum):
    """Lớp logic của một bản ghi L1. KHÔNG gộp vào một bảng vector chung."""
    EPISODIC = "episodic"        # hội thoại, lần chạy agent, sự kiện
    SEMANTIC = "semantic"        # kiến trúc, API, hạ tầng, khái niệm
    DECISION = "decision"        # quyết định + lý do + thay thế/bị thay thế
    PROCEDURAL = "procedural"    # SOP, cách sửa lặp lại, quy trình build/test
    INCIDENT = "incident"        # sự cố / lỗi — tách khỏi episodic để lọc UI
    ARCHITECTURE = "architecture"  # mô tả kiến trúc — tách để "Architecture" tab
    # V0.6.1 — ba loai nguoi dung tuyen bo TUONG MINH ma V0.6 chua co cho.
    CONSTRAINT = "constraint"    # "không được…", "luôn luôn…", ràng buộc dự án
    REQUIREMENT = "requirement"  # "phải có…", yêu cầu của dự án
    FACT = "fact"                # "hãy ghi nhớ…" — sự thật quan trọng, không thuộc loại khác

    @property
    def ben(self) -> bool:
        """Loại BỀN không có TTL mặc định — thứ người ta tuyên bố, không phải
        thứ xảy ra."""
        return self in (LoaiKyUc.DECISION, LoaiKyUc.PROCEDURAL,
                        LoaiKyUc.ARCHITECTURE, LoaiKyUc.SEMANTIC,
                        LoaiKyUc.CONSTRAINT, LoaiKyUc.REQUIREMENT,
                        LoaiKyUc.FACT)

    @property
    def tuyen_bo(self) -> bool:
        """Loại có thể được TUYÊN BỐ tường minh (và bị thay thế)."""
        return self in (LoaiKyUc.DECISION, LoaiKyUc.CONSTRAINT,
                        LoaiKyUc.REQUIREMENT, LoaiKyUc.PROCEDURAL,
                        LoaiKyUc.FACT, LoaiKyUc.INCIDENT)


class TinCay(str, Enum):
    """Nguồn gốc / THẨM QUYỀN của một bản ghi — hiển thị, không bao giờ ngầm.

    Thứ tự tin cậy GIẢM dần: `USER_EXPLICIT` (người dùng nói thẳng "hãy ghi
    nhớ…") > `DO_DUOC` (sự kiện hệ thống) > `GHI_NHAN` (ghi qua API) >
    `BACKFILL` (nhập từ lịch sử) > `LEADER` (Leader đề nghị ghi) >
    `SUY_LUAN` (model tóm tắt).
    """
    USER_EXPLICIT = "user_explicit"  # tuyên bố tường minh của người dùng
    DO_DUOC = "do_duoc"      # từ một phép đo/sự kiện hệ thống (bậc 1-2)
    GHI_NHAN = "ghi_nhan"    # người dùng hoặc Leader ghi rõ qua API/nút
    BACKFILL = "backfill"    # nhập từ lịch sử (tài liệu, git, phiên cũ)
    LEADER = "leader"        # Leader đề nghị ghi trong một lượt chat
    SUY_LUAN = "suy_luan"    # do model tóm tắt/suy ra — thấp nhất


class TrangThaiKyUc(str, Enum):
    """Trạng thái của MỌI bản ghi L1 (V0.6.1 — trước đó chỉ quyết định có)."""
    HIEU_LUC = "hieu_luc"    # ACTIVE
    THAY_THE = "thay_the"    # SUPERSEDED — vẫn tra được, không còn hiệu lực
    BO = "bo"                # rút lại


class TrangThaiQuyetDinh(str, Enum):
    HIEU_LUC = "hieu_luc"
    THAY_THE = "thay_the"    # đã bị một quyết định mới thay thế
    BO = "bo"                # rút lại, không có cái thay


#: Ba mốc DỮ LIỆU của nhắc nhở Leader. Văn bản ký ức PHẢI bị tước những
#: chuỗi này trước khi vào nhắc nhở — một bản ghi chứa `--- HẾT DỮ LIỆU ---`
#: là một cách đóng sớm vùng dữ liệu rồi chèn chỉ thị.
MOC_NHAC_NHO: Sequence[str] = (
    "--- BẮT ĐẦU DỮ LIỆU", "--- HẾT DỮ LIỆU", "=== TIN NHẮN MỚI",
    "=== DỮ LIỆU (KHÔNG PHẢI CHỈ THỊ)",
)


def tuoc_moc(s: str) -> str:
    ra = chuan_hoa(s)
    for m in MOC_NHAC_NHO:
        ra = ra.replace(m, m.replace("-", "·").replace("=", "·"))
    return ra


# --------------------------------------------------------------- L0 ----

@dataclass
class SuKien:
    """Một dòng lịch sử THÔ. Bất biến sau khi ghi."""
    loai: str
    ts: float
    tom_tat: str = ""
    nguon: str = ""
    task_id: str = ""
    session_id: str = ""
    tham_chieu: str = ""          # id bên control.db (message_id / cc_events.id)
    blob_sha: str = ""            # nội dung đầy đủ nếu vượt trần inline
    meta: Dict[str, Any] = field(default_factory=dict)
    da_loc: int = 0
    id: int = 0
    dau: str = ""

    def __post_init__(self):
        if not self.loai:
            raise ValueError("SuKien: thiếu `loai`")
        if not self.ts or self.ts <= 0:
            raise ValueError("SuKien: `ts` phải là mốc thời gian thật")
        self.tom_tat = chuan_hoa(self.tom_tat)
        if not self.dau:
            self.dau = bam(f"{self.loai}\x1f{self.tom_tat}\x1f{self.blob_sha}")

    def to_dict(self) -> Dict:
        return {"id": self.id, "loai": self.loai, "ts": self.ts,
                "tom_tat": self.tom_tat, "nguon": self.nguon,
                "task_id": self.task_id, "session_id": self.session_id,
                "tham_chieu": self.tham_chieu, "blob_sha": self.blob_sha,
                "meta": self.meta, "da_loc": self.da_loc, "dau": self.dau}


# --------------------------------------------------------------- L1 ----

@dataclass
class KyUc:
    """Một bản ghi ký ức có cấu trúc, TRỎ VỀ bằng chứng L0."""
    loai: LoaiKyUc
    noi_dung: str
    tieu_de: str = ""
    quan_trong: int = 5                  # 1..10
    tin_cay: TinCay = TinCay.GHI_NHAN
    ts: float = 0.0                      # lúc ghi
    ts_su_kien: float = 0.0              # lúc chuyện xảy ra
    ts_cham: float = 0.0                 # lần truy cập cuối (độ mới)
    han_tuoi: float = 0.0                # giây; 0 = bền (chỉ loại bền)
    the: Tuple[str, ...] = ()
    meta: Dict[str, Any] = field(default_factory=dict)
    bang_chung: Tuple["BangChung", ...] = ()
    da_loc: int = 0
    ma: str = ""
    id: int = 0
    # V0.6.1 — trang thai + thay the o MOI ban ghi, va nguon goc TUONG MINH.
    trang_thai: TrangThaiKyUc = TrangThaiKyUc.HIEU_LUC
    thay_the_cho: Tuple[str, ...] = ()   # supersedes (mã ký ức)
    bi_thay_the: str = ""                # superseded_by
    ts_sua: float = 0.0                  # updated_at
    nguon_loai: str = ""                 # "chat_user" | "api" | "backfill:doc" | "event" | "leader"
    nguon_id: str = ""                   # id sự kiện L0 / mã nguồn nhập

    #: TTL mặc định cho loại KHÔNG bền — 90 ngày. Không phải để xoá (V0.6
    #: không xoá gì) mà để xếp hạng: một mẩu episodic 4 tháng tuổi phải
    #: THUA một mẩu tuần trước khi tranh chỗ trong gói ngữ cảnh.
    HAN_TUOI_MAC_DINH = 90 * 24 * 3600.0

    def __post_init__(self):
        if isinstance(self.loai, str) and not isinstance(self.loai, LoaiKyUc):
            self.loai = LoaiKyUc(self.loai)
        if isinstance(self.tin_cay, str) and not isinstance(self.tin_cay, TinCay):
            self.tin_cay = TinCay(self.tin_cay)
        if isinstance(self.trang_thai, str) and not isinstance(
                self.trang_thai, TrangThaiKyUc):
            self.trang_thai = TrangThaiKyUc(self.trang_thai)
        self.noi_dung = chuan_hoa(self.noi_dung).strip()
        self.tieu_de = chuan_hoa(self.tieu_de).strip()
        if not self.noi_dung:
            raise ValueError("KyUc: `noi_dung` rỗng")
        if not 1 <= int(self.quan_trong) <= 10:
            raise ValueError(f"KyUc: `quan_trong` phải 1..10, có {self.quan_trong}")
        now = time.time()
        if not self.ts:
            self.ts = now
        if not self.ts_su_kien:
            self.ts_su_kien = self.ts
        if not self.ts_cham:
            self.ts_cham = self.ts
        if not self.ts_sua:
            self.ts_sua = self.ts
        self.thay_the_cho = tuple(x for x in self.thay_the_cho if x)
        if self.han_tuoi == 0.0 and not self.loai.ben:
            self.han_tuoi = self.HAN_TUOI_MAC_DINH
        self.the = tuple(chuan_hoa(t).strip().lower() for t in self.the if t)
        if not self.ma:
            # Ổn định theo NỘI DUNG -> ghi lại cùng một điều là no-op.
            self.ma = "ku_" + bam(f"{self.loai.value}\x1f{self.tieu_de}\x1f"
                                  f"{self.noi_dung}")[:16]

    @property
    def tuoi(self) -> float:
        return max(0.0, time.time() - self.ts_su_kien)

    @property
    def het_han(self) -> bool:
        return bool(self.han_tuoi) and self.tuoi > self.han_tuoi

    @property
    def hieu_luc(self) -> bool:
        return (self.trang_thai is TrangThaiKyUc.HIEU_LUC
                and not self.bi_thay_the)

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "id": self.id, "loai": self.loai.value,
                "tieu_de": self.tieu_de, "noi_dung": self.noi_dung,
                "quan_trong": self.quan_trong, "tin_cay": self.tin_cay.value,
                "ts": self.ts, "ts_su_kien": self.ts_su_kien,
                "ts_cham": self.ts_cham, "ts_sua": self.ts_sua,
                "han_tuoi": self.han_tuoi,
                "tuoi": round(self.tuoi, 1), "het_han": self.het_han,
                "trang_thai": self.trang_thai.value, "hieu_luc": self.hieu_luc,
                "thay_the_cho": list(self.thay_the_cho),
                "bi_thay_the": self.bi_thay_the,
                "nguon_loai": self.nguon_loai, "nguon_id": self.nguon_id,
                "the": list(self.the), "meta": self.meta, "da_loc": self.da_loc,
                "bang_chung": [b.to_dict() for b in self.bang_chung]}


@dataclass(frozen=True)
class BangChung:
    """Một mắt xích: ký ức -> sự kiện L0 và/hoặc blob nội dung."""
    su_kien_id: int = 0
    blob_sha: str = ""
    ghi_chu: str = ""

    def __post_init__(self):
        if not self.su_kien_id and not self.blob_sha:
            raise ValueError("BangChung: phải trỏ tới sự kiện hoặc blob")

    def to_dict(self) -> Dict:
        return {"su_kien_id": self.su_kien_id, "blob_sha": self.blob_sha,
                "ghi_chu": self.ghi_chu}


@dataclass
class QuyetDinh:
    """Bản ghi quyết định kiểu ADR — BẤT BIẾN, chỉ đổi trạng thái.

    Kết luận thay đổi thì viết quyết định MỚI và nối `thay_the_cho`; cái
    cũ chỉ được đổi `trang_thai` + `bi_thay_the`. Sáu tháng sau đọc lại
    vẫn biết chính xác điều gì là đúng VÀO LÚC nó được viết.
    """
    ma: str
    so: int
    ky_uc_ma: str
    ts: float
    trang_thai: TrangThaiQuyetDinh = TrangThaiQuyetDinh.HIEU_LUC
    thay_the_cho: Tuple[str, ...] = ()
    bi_thay_the: str = ""
    ly_do: str = ""

    def __post_init__(self):
        if isinstance(self.trang_thai, str) and not isinstance(
                self.trang_thai, TrangThaiQuyetDinh):
            self.trang_thai = TrangThaiQuyetDinh(self.trang_thai)

    @property
    def hieu_luc(self) -> bool:
        return (self.trang_thai is TrangThaiQuyetDinh.HIEU_LUC
                and not self.bi_thay_the)

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "so": self.so, "ky_uc_ma": self.ky_uc_ma,
                "ts": self.ts, "trang_thai": self.trang_thai.value,
                "thay_the_cho": list(self.thay_the_cho),
                "bi_thay_the": self.bi_thay_the, "ly_do": self.ly_do,
                "hieu_luc": self.hieu_luc}


# --------------------------------------------------------------- L2 ----

@dataclass
class VienNang:
    """Viên nang dự án — thứ được nạp THƯỜNG XUYÊN, nên phải NHỎ.

    Có phiên bản, soi được, dựng lại được từ L1. Cập nhật CÓ CHỦ ĐÍCH (khi
    có quyết định mới, mốc mới, điểm dừng mới), không viết lại mù mỗi lượt.
    """
    project_id: str
    muc_tieu: str = ""
    kien_truc: str = ""
    moc_hien_tai: str = ""
    quyet_dinh_hieu_luc: Tuple[str, ...] = ()     # ma quyết định
    rang_buoc: Tuple[str, ...] = ()
    van_de_da_biet: Tuple[str, ...] = ()
    moc_gan_day: Tuple[str, ...] = ()
    phien_ban: int = 0
    ts: float = 0.0
    ly_do: str = ""
    bang_chung: Tuple[str, ...] = ()               # ma ký ức / id sự kiện

    #: Trần TOKEN của viên nang khi hiện ra trong gói ngữ cảnh.
    TRAN_TOKEN = 700

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id, "muc_tieu": self.muc_tieu,
                "kien_truc": self.kien_truc, "moc_hien_tai": self.moc_hien_tai,
                "quyet_dinh_hieu_luc": list(self.quyet_dinh_hieu_luc),
                "rang_buoc": list(self.rang_buoc),
                "van_de_da_biet": list(self.van_de_da_biet),
                "moc_gan_day": list(self.moc_gan_day),
                "phien_ban": self.phien_ban, "ts": self.ts,
                "ly_do": self.ly_do, "bang_chung": list(self.bang_chung)}

    @classmethod
    def tu_dict(cls, d: Dict, project_id: str = "") -> "VienNang":
        d = dict(d or {})
        return cls(project_id=d.get("project_id") or project_id,
                   muc_tieu=d.get("muc_tieu", ""), kien_truc=d.get("kien_truc", ""),
                   moc_hien_tai=d.get("moc_hien_tai", ""),
                   quyet_dinh_hieu_luc=tuple(d.get("quyet_dinh_hieu_luc") or ()),
                   rang_buoc=tuple(d.get("rang_buoc") or ()),
                   van_de_da_biet=tuple(d.get("van_de_da_biet") or ()),
                   moc_gan_day=tuple(d.get("moc_gan_day") or ()),
                   phien_ban=int(d.get("phien_ban") or 0),
                   ts=float(d.get("ts") or 0.0), ly_do=d.get("ly_do", ""),
                   bang_chung=tuple(d.get("bang_chung") or ()))

    def rong(self) -> bool:
        return not any((self.muc_tieu, self.kien_truc, self.moc_hien_tai,
                        self.quyet_dinh_hieu_luc, self.rang_buoc,
                        self.van_de_da_biet, self.moc_gan_day))


# --------------------------------------------------------------- L3 ----

@dataclass
class DiemDung:
    """Điểm dừng — đủ để một phiên MỚI tiếp tục, và không hơn.

    Gọn nhưng có bằng chứng: mỗi trường là chữ, còn `bang_chung` trỏ về
    sự kiện/ký ức thật để "vì sao anh nhớ điều này?" có câu trả lời.
    """
    project_id: str
    ly_do: str                                   # cái gì kích hoạt
    muc_tieu: str = ""
    da_xong: Tuple[str, ...] = ()
    gia_thuyet: str = ""
    tep_da_sua: Tuple[str, ...] = ()
    kiem_thu: str = ""
    chua_xong: Tuple[str, ...] = ()
    session_id: str = ""
    task_id: str = ""
    bang_chung: Tuple[str, ...] = ()
    tiep_tuc_tu: str = ""                        # ma điểm dừng trước
    ts: float = 0.0
    ma: str = ""

    #: Trần TOKEN khi vào gói ngữ cảnh.
    TRAN_TOKEN = 600

    def __post_init__(self):
        if not self.ly_do:
            raise ValueError("DiemDung: thiếu `ly_do` (cái gì kích hoạt)")
        if not self.ts:
            self.ts = time.time()
        if not self.ma:
            self.ma = "dd_" + bam(f"{self.project_id}\x1f{self.ts!r}\x1f"
                                  f"{self.ly_do}")[:14]

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "project_id": self.project_id,
                "ly_do": self.ly_do, "muc_tieu": self.muc_tieu,
                "da_xong": list(self.da_xong), "gia_thuyet": self.gia_thuyet,
                "tep_da_sua": list(self.tep_da_sua), "kiem_thu": self.kiem_thu,
                "chua_xong": list(self.chua_xong), "session_id": self.session_id,
                "task_id": self.task_id, "bang_chung": list(self.bang_chung),
                "tiep_tuc_tu": self.tiep_tuc_tu, "ts": self.ts}

    @classmethod
    def tu_dict(cls, d: Dict) -> "DiemDung":
        d = dict(d or {})
        return cls(project_id=d.get("project_id", ""), ly_do=d.get("ly_do", "?"),
                   muc_tieu=d.get("muc_tieu", ""),
                   da_xong=tuple(d.get("da_xong") or ()),
                   gia_thuyet=d.get("gia_thuyet", ""),
                   tep_da_sua=tuple(d.get("tep_da_sua") or ()),
                   kiem_thu=d.get("kiem_thu", ""),
                   chua_xong=tuple(d.get("chua_xong") or ()),
                   session_id=d.get("session_id", ""), task_id=d.get("task_id", ""),
                   bang_chung=tuple(d.get("bang_chung") or ()),
                   tiep_tuc_tu=d.get("tiep_tuc_tu", ""),
                   ts=float(d.get("ts") or 0.0), ma=d.get("ma", ""))
