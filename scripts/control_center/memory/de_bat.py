"""ĐỀ BẠT — biến một tuyên bố tường minh của người dùng thành ký ức có cấu trúc.

KHUYẾT TẬT V0.6 (nghiệm thu tay, bản EXE): người dùng gõ

    "hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được
    dùng cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc
    định cho task thường."

Dòng L0 được lưu, tìm lại được sau khi mở lại — nhưng tab Memory vẫn báo
`Decisions = 0` và Leader nói chưa có quyết định `qd_*` nào. V0.6 chỉ ghi
quyết định qua API/nút, cố ý không suy từ chat vì "một câu 'tôi nghĩ nên…'
không phải một quyết định". Đúng — nhưng "hãy ghi nhớ đây là một quyết
định" thì ĐÚNG LÀ một quyết định, và người dùng đã nói thẳng.

CÁCH LÀM: TẤT ĐỊNH, KHÔNG LLM. Một tuyên bố tường minh có DẤU HIỆU tường
minh — "hãy ghi nhớ", "đây là (một) quyết định", "từ giờ rule là",
"constraint của project", "requirement", "đây là sự cố", "chúng ta quyết
định", "không được", "luôn luôn", "remember that", "we decided"… Bộ mẫu
dưới đây nhận diện chúng và phân loại:

    DECISION > INCIDENT > CONSTRAINT > REQUIREMENT > PROCEDURAL > FACT

Điều kiện đề bạt là **có dấu hiệu TUYÊN BỐ** ("ghi nhớ", "đây là …", "từ
giờ", "quyết định", "sự cố", "rule là"…). Một câu chỉ có "không được" mà
không tuyên bố gì thì KHÔNG được đề bạt — nếu không mọi câu "không được
quên tắt máy" đều thành ràng buộc dự án. Thà bỏ lỡ một tuyên bố mờ (người
dùng nói lại rõ hơn, hoặc Leader dùng `record_memory`) còn hơn bịa ra một
quyết định.

THẨM QUYỀN: `TinCay.USER_EXPLICIT` — cao nhất. Nguồn: `nguon_loai =
"chat_user"`, `nguon_id` = id dòng L0, và một mắt xích bằng chứng trỏ về
đúng dòng đó. "Vì sao anh nhớ điều này?" → "vì bạn nói lúc <ts>, đây là
nguyên văn".

THAY THẾ chỉ khi NGƯỜI DÙNG NÓI THẾ: "thay thế quyết định trước", "thay
cho qd_0003", "không còn áp dụng", "bỏ rule cũ"… Khi không có mã tường
minh, bản ghi HIỆU LỰC cùng loại có nhiều từ đặc trưng trùng nhất bị thay
thế. Không có dấu hiệu thay thế → cả hai cùng hiệu lực, và Leader sẽ thấy
cả hai (nó có thể hỏi lại). Không bao giờ tự đoán rằng câu mới huỷ câu cũ.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from scripts.control_center.memory.model import (LoaiKyUc, chuan_hoa,
                                                 gap_dau)

# ------------------------------------------------------------- dấu hiệu ----

#: Dau hieu TUYEN BO — phai co it nhat mot trong so nay (so tren dang GAP
#: DAU, chu thuong) de mot tin nhan duoc xet de bat.
_TUYEN_BO = (
    r"\bhay ghi nho\b", r"\bghi nho (giup|lai|rang|la|:)", r"\bnho giup\b",
    r"\bnho rang\b", r"\bluu y (rang|:)", r"\bday la (mot )?(quyet dinh|su co|rang buoc|"
    r"yeu cau|quy trinh|quy tac|rule|constraint|requirement|incident|sop)",
    r"\bchung ta (da )?quyet dinh\b", r"\bta (da )?quyet dinh\b",
    r"\btoi quyet dinh\b", r"\bquyet dinh( cua (project|du an))?\s*:",
    r"\btu (gio|nay)( tro di)?[, ]", r"\brule( cua (project|du an))? la\b",
    r"\bquy tac( cua (project|du an))? la\b",
    r"\bconstraint( cua (project|du an))?\s*[:]", r"\brequirement\s*[:]",
    r"\byeu cau( cua (project|du an))?\s*:", r"\brang buoc( cua (project|du an))?\s*:",
    r"\bsu co\s*:", r"\bincident\s*:", r"\bquy trinh\s*:", r"\bsop\s*:",
    r"\bremember (that|this|:)", r"\bwe (have )?decided\b", r"\bdecision\s*:",
    r"\bfrom now on\b", r"\bthe rule is\b", r"\bnote (that|:)",
    r"\bproject (rule|constraint|requirement|decision)\b",
)

#: Dau hieu PHAN LOAI, theo thu tu uu tien. Moi loai: (mau, diem).
_PHAN_LOAI: Tuple[Tuple[LoaiKyUc, Tuple[str, ...]], ...] = (
    (LoaiKyUc.DECISION, (r"\bquyet dinh\b", r"\bdecid(e|ed|sion)\b",
                         r"\bchot (la|phuong an)\b", r"\bchon (phuong an|cach)\b")),
    (LoaiKyUc.INCIDENT, (r"\bsu co\b", r"\bincident\b", r"\broot cause\b",
                         r"\bnguyen nhan goc\b", r"\bbi loi\b.*\b(vi|do)\b",
                         r"\bpostmortem\b", r"\bhong .* vi\b")),
    (LoaiKyUc.CONSTRAINT, (r"\bconstraint\b", r"\brang buoc\b", r"\brule\b",
                           r"\bquy tac\b", r"\bluat (la|:)", r"\bkhong duoc\b",
                           r"\bkhong bao gio\b", r"\btuyet doi khong\b",
                           r"\bnever\b", r"\bmust not\b", r"\bluon luon\b",
                           r"\balways\b", r"\bbat buoc\b", r"\bcam\b",
                           r"\bchi duoc\b", r"\bonly (for|when|use)\b")),
    (LoaiKyUc.REQUIREMENT, (r"\brequirement\b", r"\byeu cau\b", r"\bphai co\b",
                            r"\bmust have\b", r"\bcan phai\b", r"\bneeds? to\b",
                            r"\bshould\b")),
    (LoaiKyUc.PROCEDURAL, (r"\bquy trinh\b", r"\bsop\b", r"\bcac buoc\b",
                           r"\bcach lam\b", r"\bprocedure\b", r"\brunbook\b",
                           r"\bde .{3,60} thi (chay|lam|dung)\b", r"\bbuoc [0-9]\b",
                           r"\bkhi .{3,60} (thi|hay) (chay|lam)\b")),
)

#: Dau hieu THAY THE — chi khi nguoi dung noi the.
_THAY_THE = (
    r"\bthay the (quyet dinh|rule|quy tac|rang buoc|cai|ban)( truoc| cu| hien tai)?\b",
    r"\bthay cho (quyet dinh|rule|quy tac)( truoc| cu)?\b", r"\bsupersed(e|es|ing)\b",
    r"\bkhong con ap dung\b", r"\bbo (quyet dinh|rule|quy tac) cu\b",
    r"\bhuy (quyet dinh|rule|quy tac) (truoc|cu)\b", r"\bcap nhat (quyet dinh|rule)\b",
    r"\bsua (quyet dinh|rule) (truoc|cu)\b", r"\breplaces? (the )?(previous|old) (decision|rule)\b",
    r"\bthay vi (nhu )?truoc\b",
)
_MA_QD = re.compile(r"\b(qd_\d{4}|ku_[0-9a-f]{16})\b", re.I)

#: Cum mo dau bi CAT khoi noi dung — de ban ghi la NOI DUNG, khong phai loi
#: dan. Chay tren van ban GOC (co dau), khong phan biet hoa thuong.
_CAT_DAU = re.compile(
    r"^\s*(?:ok[,.]?\s*)?(?:hãy|please|xin|làm ơn)?\s*(?:ghi nhớ giúp|ghi nhớ lại|"
    r"ghi nhớ rằng|ghi nhớ là|ghi nhớ|nhớ giúp|nhớ rằng|"
    r"lưu ý rằng|lưu ý|remember(?: that| this)?|note(?: that)?)?[,:]?\s*"
    r"(?:đây là (?:một )?(?:quyết định|sự cố|ràng buộc|yêu cầu|quy trình|quy tắc|rule|"
    r"constraint|requirement|incident|sop)(?: của (?:project|dự án))?|"
    r"(?:chúng ta|ta|tôi) (?:đã )?quyết định(?: là| rằng)?|quyết định(?: của (?:project|dự án))?|"
    r"từ (?:giờ|nay)(?: trở đi)?[, ]*(?:rule|quy tắc|luật)?(?: của (?:project|dự án))?(?: là)?|"
    r"rule(?: của (?:project|dự án))? là|quy tắc(?: của (?:project|dự án))? là|"
    r"constraint(?: của (?:project|dự án))?|requirement(?: của (?:project|dự án))?|"
    r"yêu cầu(?: của (?:project|dự án))?|ràng buộc(?: của (?:project|dự án))?|"
    r"sự cố|incident|quy trình|sop|decision|we (?:have )?decided(?: that)?|from now on|"
    r"the rule is(?: that)?)?\s*[:,\-–—]?\s*",
    re.I)

_TU_DAC_TRUNG_BO = frozenset((
    "quyet", "dinh", "project", "du", "an", "task", "cho", "dung", "duoc",
    "khong", "cac", "voi", "trong", "va", "hoac", "khi", "thi", "chi", "mac",
    "thuong", "hay", "ghi", "nho", "day", "mot", "cua", "rule", "la", "the",
    "this", "that", "with", "only", "for", "not", "and", "use", "used",
))


@dataclass
class KetQuaDeBat:
    loai: LoaiKyUc
    noi_dung: str
    tieu_de: str
    dau_hieu: Tuple[str, ...] = ()
    thay_the_tuong_minh: Tuple[str, ...] = ()   # ma qd_/ku_ nguoi dung neu
    muon_thay_the: bool = False                  # co dau hieu thay the
    tu_dac_trung: Tuple[str, ...] = ()

    def to_dict(self):
        return {"loai": self.loai.value, "noi_dung": self.noi_dung,
                "tieu_de": self.tieu_de, "dau_hieu": list(self.dau_hieu),
                "thay_the_tuong_minh": list(self.thay_the_tuong_minh),
                "muon_thay_the": self.muon_thay_the,
                "tu_dac_trung": list(self.tu_dac_trung)}


def _khop(mau: Sequence[str], van_gap: str) -> List[str]:
    return [m for m in mau if re.search(m, van_gap)]


def tu_dac_trung(van: str) -> Tuple[str, ...]:
    """Từ ≥4 ký tự (dạng gấp dấu), bỏ từ chung — để so trùng khi thay thế."""
    ra = []
    for t in re.findall(r"[a-z0-9][a-z0-9_.-]{3,}", gap_dau(van)):
        if t not in _TU_DAC_TRUNG_BO and t not in ra:
            ra.append(t)
    return tuple(ra[:24])


def xet(van: str) -> Optional[KetQuaDeBat]:
    """Tin nhắn người dùng -> kết quả đề bạt, hoặc `None` (không tuyên bố)."""
    goc = chuan_hoa(van).strip()
    if len(goc) < 12:
        return None
    gap = gap_dau(goc)
    tb = _khop(_TUYEN_BO, gap)
    if not tb:
        return None
    loai = LoaiKyUc.FACT
    dau: List[str] = list(tb)
    for lo, maus in _PHAN_LOAI:
        k = _khop(maus, gap)
        if k:
            loai = lo
            dau += k
            break
    # Noi dung: cat cum mo dau (chi khi phan con lai van du dai).
    noi_dung = _CAT_DAU.sub("", goc, count=1).strip() or goc
    if len(noi_dung) < 8:
        noi_dung = goc
    noi_dung = noi_dung[0].upper() + noi_dung[1:] if noi_dung else goc
    tieu_de = re.split(r"[.;\n]", noi_dung, maxsplit=1)[0].strip()[:90]
    ma = tuple(dict.fromkeys(m.lower() for m in _MA_QD.findall(goc)))
    muon = bool(_khop(_THAY_THE, gap)) or bool(ma)
    return KetQuaDeBat(loai=loai, noi_dung=noi_dung, tieu_de=tieu_de,
                       dau_hieu=tuple(dau), thay_the_tuong_minh=ma,
                       muon_thay_the=muon, tu_dac_trung=tu_dac_trung(noi_dung))


def chon_ban_bi_thay_the(kq: KetQuaDeBat, ung_vien, *, toi_thieu: int = 2
                         ) -> Optional[str]:
    """Trong các bản ghi HIỆU LỰC cùng loại, bản nào bị thay thế?

    `ung_vien`: iterable các `KyUc`. Trả `ma` hoặc `None`. Chỉ được gọi khi
    `kq.muon_thay_the`. Ưu tiên mã người dùng nêu đích danh; không có thì
    bản có ≥ `toi_thieu` từ đặc trưng trùng nhiều nhất.
    """
    ds = list(ung_vien)
    if kq.thay_the_tuong_minh:
        for k in ds:
            if k.ma.lower() in kq.thay_the_tuong_minh:
                return k.ma
    tot, diem_tot = None, 0
    moi = set(kq.tu_dac_trung)
    for k in ds:
        trung = len(moi & set(tu_dac_trung(f"{k.tieu_de} {k.noi_dung}")))
        if trung > diem_tot:
            tot, diem_tot = k.ma, trung
    return tot if diem_tot >= toi_thieu else None
