"""TOẢ — tách một yêu cầu "gọi N agent…" thành N việc con độc lập, có sức chứa thật.

KHUYẾT TẬT (nghiệm thu tay `dist-v061`): người dùng gõ
    "gọi 8 agent gemini 3.8 và phân mỗi đứa đi lục cho t 1 bộ fanfic audi"
Leader tạo MỘT việc to ("Khảo sát toàn bộ kho…") và Router giao đúng một
khe (AG02). Nguyên nhân KHÔNG ở bộ lập lịch V4 — nó chỉ nhận một việc.
Nguyên nhân ở chỗ không tầng nào mang SỐ AGENT được yêu cầu: `delegate_work`
chỉ có `objective/hints/che_do`, `RulePlanner.tach()` cắt câu theo mệnh đề,
`PlannedTask`/`Task`/`TaskContract` không có trường nào cho "8". Và kể cả có
8 việc thì `max_parallel=3` (mặc định desktop) + `max_sessions=3` chặn còn 3.

Module này làm BA việc, đều TẤT ĐỊNH (không LLM):

  xet_toa(text)            đọc cardinality tường minh: "gọi 8 agent", "cho 4
                           agent mỗi đứa…", "chia cho mỗi agent một X: a, b, c"
                           (N = số mục liệt kê). Câu mơ hồ -> None: KHÔNG bao
                           giờ tự bịa ra 8 agent. "MAX" là chế độ CHẤT LƯỢNG,
                           không phải số agent.
  chia_con(...)            N việc con với ràng buộc KHÔNG TRÙNG: mỗi con biết
                           mình là i/N, chỉ trả về đúng MỘT kết quả, phân vùng
                           theo thứ tự liệt kê ổn định, và phải nêu vì sao kết
                           quả của mình khác các anh em.
  tinh_suc_chua(fabric…)   sức chứa THẬT cho đúng yêu cầu này: khe rảnh trên các
                           runtime đủ điều kiện (đã trừ chỗ Leader chiếm), tài
                           khoản phân biệt, trần song song của Control Center.
                           Ra một câu người đọc được: "N việc; K chạy ngay, N−K
                           chờ slot" — không bao giờ nói 8 khi chỉ có 7.
  tong_hop(...)            gộp kết quả các con vào cha: khử trùng ứng viên, giữ
                           nguồn gốc từng con (việc, runtime, model, phiên).

Ba khái niệm PHẢI TÁCH (yêu cầu 4 của đề bài): chế độ suy luận/chất lượng
(`che_do`), số agent được yêu cầu (`so_agent`), và trần song song của bộ lập
lịch (`max_parallel`/khe). Mỗi cái một trường, một dòng trong câu trả lời.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

#: Tran so agent mot cau duoc yeu cau. Lon hon -> tu choi (khong cat lang).
TRAN_SO_AGENT = 32

_SO_CHU = {
    "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8,
    "chin": 9, "muoi": 10, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}
_DON_VI = r"(?:agent|agents|worker|workers|con|dua|thang|bot|bots|model|models|luong|tien trinh)"
_SO = r"(\d{1,2}|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|two|three|four|five|six|seven|eight|nine|ten|twelve)"

#: "goi 8 agent", "cho 4 agent", "8 agents", "tam agent", "dung 6 worker"
_SO_AGENT = re.compile(
    r"(?:\b(?:goi|cho|dung|lay|tao|chay|spawn|run|use|call|launch|start|mo|bat|chia|voi)\s+)?"
    r"\b" + _SO + r"\s+" + _DON_VI + r"\b")
#: "moi dua mot", "moi agent 1", "each agent one", "mỗi con một"
_MOI_MOT = re.compile(
    r"\bmoi\s+(?:dua|agent|con|worker|thang|bot|model|nguoi)\b"
    r"|\beach\s+(?:agent|worker|bot|one)\b|\bper\s+(?:agent|worker)\b")
#: Liet ke sau dau hai cham: "…: a, b, c" hoac "…: a; b; c"
_LIET_KE = re.compile(r":\s*([^\n]+)$")
#: Mot dong muc trong danh sach nhieu dong: "1. README/docs", "- tests", "• x".
_MUC_DONG = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+(.+?)\s*$")
#: Nhac toi TRANG THAI GIT (doc): git history/log/blame/show, lich su git/commit.
NHAC_GIT = re.compile(
    r"\b(git (?:history|log|blame|show|status|diff|rev-parse)|lịch sử git|lich su git|"
    r"commit history|lịch sử commit|lich su commit|git history)\b", re.I)
#: Duong dan trong mot muc: "docs/", "web/admin", "scripts/tim.py", "tests".
_DUONG_MUC = re.compile(r"(?<![\w./-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.*-]*|[A-Za-z0-9_.-]+/)")
#: Tu khoa muc -> thu muc quen thuoc (khi muc khong co duong dan tuong minh).
_TU_KHOA_THU_MUC = (
    (re.compile(r"\b(tests?|unit tests?|kiểm thử|kiem thu)\b", re.I), "tests"),
    (re.compile(r"\b(docs?|documentation|tài liệu|tai lieu|readme)\b", re.I), "docs"),
    (re.compile(r"\b(scripts?)\b", re.I), "scripts"),
    (re.compile(r"\b(web|frontend)\b", re.I), "web"),
    (re.compile(r"\b(server|backend|api)\b", re.I), "server"),
)
#: Goi y model / nha cung cap.
_MODEL = (
    (re.compile(r"gemini\s*3[.,]?8\s*(?:flash)?\s*(?:medium)"), "gemini-3.8-flash-medium"),
    (re.compile(r"gemini\s*3[.,]?8|gemini\s*flash|\bflash\b"), "gemini-3.8-flash-high"),
    (re.compile(r"gemini\s*3[.,]?1\s*pro|gemini\s*pro"), "gemini-3.1-pro-low"),
    (re.compile(r"claude\s*opus|\bopus\b"), "claude-opus-4-6-thinking"),
    (re.compile(r"claude\s*sonnet|\bsonnet\b"), "claude-sonnet-4-6"),
    (re.compile(r"gpt[- ]?oss"), "gpt-oss-120b-medium"),
)
_PROVIDER = (
    (re.compile(r"gemini|antigravity|\bagy\b|\bag0\d\b|claude opus|claude sonnet|gpt[- ]?oss"),
     "antigravity"),
    (re.compile(r"\bcodex\b"), "codex"),
    (re.compile(r"\bopencode\b"), "opencode"),
)


def gap_dau(s: str) -> str:
    """Gấp dấu + `đ→d` + thường hoá — cùng cách với `memory.model.gap_dau`."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


@dataclass
class YeuCauToa:
    so_agent: int
    moi_agent_mot: bool = False
    model_hint: str = ""
    provider_hint: str = ""
    dau_hieu: Tuple[str, ...] = ()
    muc_liet_ke: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {"so_agent": self.so_agent, "moi_agent_mot": self.moi_agent_mot,
                "model_hint": self.model_hint, "provider_hint": self.provider_hint,
                "dau_hieu": list(self.dau_hieu), "muc_liet_ke": list(self.muc_liet_ke)}


def _so(tu: str) -> int:
    tu = tu.strip().lower()
    if tu.isdigit():
        return int(tu)
    return _SO_CHU.get(tu, 0)


def _liet_ke(van: str) -> Tuple[str, ...]:
    """Danh sách mục người dùng liệt kê — nhiều dòng đánh số/gạch đầu dòng sau
    một dòng kết bằng `:`, hoặc một dòng "…: a, b, c"."""
    dong = [d for d in van.strip().splitlines()]
    for i, d in enumerate(dong):
        if not d.rstrip().endswith(":"):
            continue
        muc: List[str] = []
        for d2 in dong[i + 1:]:
            m = _MUC_DONG.match(d2)
            if m:
                muc.append(m.group(1).strip(" .;"))
            elif not d2.strip():
                continue
            else:
                break
        if len(muc) >= 2:
            return tuple(x for x in muc if x and len(x) <= 120)[:TRAN_SO_AGENT]
    dau = dong[0] if dong else ""
    m = _LIET_KE.search(dau.strip()) or _LIET_KE.search(van.strip())
    if not m or "\n" in m.group(1):
        return ()
    phan = [p.strip(" .") for p in re.split(r"[;,]|\bvà\b|\bva\b|\band\b", m.group(1))]
    phan = [p for p in phan if p and len(p) <= 120]
    return tuple(phan) if len(phan) >= 2 else ()


def _duong_dan_cua_muc(muc: str) -> Tuple[str, ...]:
    """Đường dẫn/thư mục mà một mục liệt kê nhắc tới, hoặc rỗng."""
    ra: List[str] = []
    for m in _DUONG_MUC.finditer(muc or ""):
        p = m.group(1).strip("/")
        if p and not p.lower().startswith(("http", "https")) and "://" not in p:
            ra.append(p)
    if not ra:
        for mau, thu_muc in _TU_KHOA_THU_MUC:
            if mau.search(muc or ""):
                ra.append(thu_muc)
                break
    return tuple(dict.fromkeys(ra))


def xet_toa(text: str) -> Optional[YeuCauToa]:
    """Cardinality TƯỞNG MINH trong câu, hoặc `None`.

    Chỉ trả về khi người dùng NÓI RA số agent, hoặc nói "mỗi agent một X" kèm
    một danh sách X đếm được. Không suy từ độ to của việc, không suy từ chế độ
    MAX/STRONG, không suy từ số tài khoản có sẵn.
    """
    if not text or not text.strip():
        return None
    gap = gap_dau(text)
    dau: List[str] = []
    so = 0
    m = _SO_AGENT.search(gap)
    if m:
        so = _so(m.group(1))
        if so:
            dau.append(f"so_agent:{m.group(0).strip()}")
    moi = bool(_MOI_MOT.search(gap))
    if moi:
        dau.append("moi_agent_mot")
    # Danh sach muc: dung lam PHAN VUNG cho tung con khi so muc = so agent
    # (hoac lam chinh so agent khi cau chi noi "moi agent mot…").
    muc: Tuple[str, ...] = _liet_ke(text) if (moi or so) else ()
    if not so and moi and muc:
        so = len(muc)
        dau.append(f"liet_ke:{so}")
    if so and muc and len(muc) != so:
        muc = ()                                     # khong khop -> phan vung chung
    if not so:
        return None
    if so < 2 or so > TRAN_SO_AGENT:
        return None                                  # 1 agent = viec thuong; >32 = tu choi
    model = ""
    for mau, ten in _MODEL:
        if mau.search(gap):
            model = ten
            break
    provider = ""
    for mau, ten in _PROVIDER:
        if mau.search(gap):
            provider = ten
            break
    if model and not provider:
        provider = "antigravity"
    return YeuCauToa(so_agent=so, moi_agent_mot=moi, model_hint=model, provider_hint=provider,
                     dau_hieu=tuple(dau), muc_liet_ke=muc)


# ---------------------------------------------------------------- chia con ---

@dataclass
class ConToa:
    chi_so: int
    tong: int
    tieu_de: str
    muc_tieu: str
    phan_vung: str
    #: Che do truy cap cua con: "read" | "write".
    che_do: str = "read"
    #: Duong dan/thu muc rieng cua con (rong = ca kho).
    pham_vi: Tuple[str, ...] = ()
    #: Chuoi tai nguyen cho `Task.resources`: "READ:FILESYSTEM:docs", ...
    tai_nguyen: Tuple[str, ...] = ()


def chia_con(yc: YeuCauToa, muc_tieu_goc: str, tieu_de_goc: str, *,
             chi_doc: bool = True, pham_vi_mau: Sequence[str] = (),
             nhac_git: bool = False) -> List[ConToa]:
    """N việc con, mỗi con một phân vùng, ràng buộc KHÔNG TRÙNG, và TÀI NGUYÊN
    RIÊNG kèm CHẾ ĐỘ TRUY CẬP (V0.6.1).

    Con CHỈ ĐỌC: khoá `READ FILESYSTEM` trên thư mục của mục mình (không có thì
    gốc kho `.`), `READ GIT history` nếu mục là lịch sử git — mọi khoá READ sống
    chung, nên N con chạy đồng thời. Con GHI: `WRITE FILESYSTEM` trên đường dẫn
    riêng của mục (không có thì phạm vi ghi của việc mẫu — lúc đó các con GIẪM
    NHAU và bị tuần tự hoá, ĐÚNG như phải thế).
    """
    from scripts.control_center.locks import GOC, READ, WRITE, chuoi_tai_nguyen
    from scripts.control_center.model import LockKind
    n = yc.so_agent
    co_muc = bool(yc.muc_liet_ke) and len(yc.muc_liet_ke) == n
    ra: List[ConToa] = []
    for i in range(1, n + 1):
        muc = yc.muc_liet_ke[i - 1] if co_muc else ""
        if co_muc:
            pv = f"mục được giao riêng cho bạn: «{muc}»"
        else:
            pv = (f"phân vùng {i}/{n}: liệt kê mọi ứng viên theo MỘT thứ tự ổn định "
                  f"(đường dẫn/tên theo bảng chữ cái), rồi lấy ứng viên thứ {i}, "
                  f"{i + n}, {i + 2 * n}… (bước {n}); bỏ qua mọi ứng viên không thuộc "
                  f"dãy của bạn")
        la_git = bool(muc and NHAC_GIT.search(muc))
        duong = () if la_git else _duong_dan_cua_muc(muc)
        tai_nguyen: List[str] = []
        if chi_doc:
            if la_git:
                # Muc "git history": chi doc TRANG THAI GIT — khong cham cay
                # lam viec, nen khong giu READ goc kho (se chan vo ich mot
                # anh em GHI o bat ky duong dan nao).
                tai_nguyen.append(chuoi_tai_nguyen(LockKind.GIT, "history", READ))
            else:
                for p in (duong or (GOC,)):
                    tai_nguyen.append(chuoi_tai_nguyen(LockKind.FILESYSTEM, p, READ))
                if not co_muc and nhac_git:
                    tai_nguyen.append(chuoi_tai_nguyen(LockKind.GIT, "history", READ))
            che_do = READ
        else:
            for p in (duong or tuple(pham_vi_mau)):
                tai_nguyen.append(chuoi_tai_nguyen(LockKind.FILESYSTEM, p, WRITE))
            che_do = WRITE
        mo_ta_tn = ", ".join(f"{x.split(':', 2)[0]} {x.split(':', 2)[2]}" for x in tai_nguyen) \
            or "(không khoá)"
        muc_tieu = (
            f"{muc_tieu_goc.strip()}\n\n"
            f"BẠN LÀ AGENT {i}/{n} TRONG MỘT NHÓM {n} AGENT CHẠY SONG SONG, CÙNG MỤC TIÊU.\n"
            f"* Chỉ trả về ĐÚNG MỘT kết quả (một bộ/một mục) — không phải danh sách.\n"
            f"* KHÔNG TRÙNG với các agent anh em: {pv}.\n"
            f"* Tài nguyên/phạm vi của bạn: {mo_ta_tn}. Không đụng phạm vi của anh em.\n"
            f"* Trong `summary`, dòng đầu ghi `KẾT QUẢ [{i}/{n}]: <tên/đường dẫn kết quả>` "
            f"rồi một câu vì sao nó thuộc phân vùng của bạn.\n"
            f"* Không thấy ứng viên nào trong phân vùng của mình thì nói rõ "
            f"`KẾT QUẢ [{i}/{n}]: KHÔNG CÓ` thay vì lấy của người khác.")
        ra.append(ConToa(chi_so=i, tong=n, tieu_de=f"[{i}/{n}] {tieu_de_goc}"[:120],
                         muc_tieu=muc_tieu, phan_vung=pv, che_do=che_do,
                         pham_vi=tuple(duong), tai_nguyen=tuple(tai_nguyen)))
    return ra


# ---------------------------------------------------------------- suc chua ---

@dataclass
class SucChua:
    yeu_cau: int
    khe_ranh: int                       # tong khe con trong tren runtime du dieu kien
    tai_khoan_ranh: int                 # runtime co >= 1 khe trong
    tai_khoan_du_dk: int                # runtime du dieu kien (ke ca dang day)
    tran_song_song: int                 # max_parallel cua Control Center
    dang_chay: int                      # viec dang chay (moi du an)
    chay_ngay: int
    cho: int
    leader_chiem: Tuple[str, ...] = ()
    runtime_ranh: Tuple[str, ...] = ()
    provider: str = ""
    model: str = ""
    ghi_chu: Tuple[str, ...] = ()

    @property
    def gioi_han_boi(self) -> str:
        if self.chay_ngay >= self.yeu_cau:
            return ""
        if self.khe_ranh < self.yeu_cau and self.khe_ranh <= max(0, self.tran_song_song - self.dang_chay):
            return "khe tài khoản"
        return "trần song song của Control Center"

    def to_dict(self) -> Dict:
        return {"yeu_cau": self.yeu_cau, "khe_ranh": self.khe_ranh,
                "tai_khoan_ranh": self.tai_khoan_ranh, "tai_khoan_du_dk": self.tai_khoan_du_dk,
                "tran_song_song": self.tran_song_song, "dang_chay": self.dang_chay,
                "chay_ngay": self.chay_ngay, "cho": self.cho,
                "leader_chiem": list(self.leader_chiem), "runtime_ranh": list(self.runtime_ranh),
                "provider": self.provider, "model": self.model, "gioi_han_boi": self.gioi_han_boi,
                "ghi_chu": list(self.ghi_chu)}


def tinh_suc_chua(fabric, yc: YeuCauToa, *, max_parallel: int, dang_chay: int = 0,
                  now: Optional[float] = None) -> SucChua:
    """Sức chứa THẬT cho yêu cầu này, đọc từ fabric đang sống. Không đoán.

    Runtime đủ điều kiện: đã cấp phát, nhận dispatch, trạng thái nhận việc
    được (không OFFLINE/COOLDOWN/STARTING), đúng nhà cung cấp nếu người dùng
    nêu, hỗ trợ model nếu người dùng nêu. Khe rảnh = `concurrency − in_flight`
    — `in_flight` ĐÃ gồm nhãn `LEADER:<project>` (V0.6.1), nên chỗ Leader
    chiếm tự động bị trừ, và được nêu tên trong câu trả lời.
    """
    ghi_chu: List[str] = []
    provider = yc.provider_hint
    model = yc.model_hint
    if model and model not in getattr(fabric, "models", {}):
        ghi_chu.append(f"model gợi ý {model!r} không có trong fabric — không ghim model")
        model = ""
    du: List = []
    for r in fabric.runtimes.values():
        if not r.provisioned or not r.dispatchable:
            continue
        if provider and r.provider != provider:
            continue
        if model and model not in r.supported_models:
            continue
        du.append(r)
    khe = 0
    ranh: List[str] = []
    leader: List[str] = []
    for r in du:
        tt = r.trang_thai_hien_tai(now=now)
        if any(str(x).startswith("LEADER:") for x in r.running_tasks):
            leader.append(r.runtime_id)
        if not getattr(tt, "nhan_viec_duoc", False):
            continue
        trong = max(0, r.concurrency - r.in_flight)
        if trong > 0:
            ranh.append(r.runtime_id)
        khe += trong
    tran_con = max(0, int(max_parallel) - int(dang_chay))
    chay_ngay = max(0, min(yc.so_agent, khe, tran_con))
    return SucChua(yeu_cau=yc.so_agent, khe_ranh=khe, tai_khoan_ranh=len(ranh),
                   tai_khoan_du_dk=len(du), tran_song_song=int(max_parallel),
                   dang_chay=int(dang_chay), chay_ngay=chay_ngay, cho=yc.so_agent - chay_ngay,
                   leader_chiem=tuple(sorted(leader)), runtime_ranh=tuple(sorted(ranh)),
                   provider=provider, model=model, ghi_chu=tuple(ghi_chu))


def cau_thong_bao(sc: SucChua, *, cha_id: str = "") -> str:
    """Câu Leader/Router nói TRƯỚC khi chạy — đúng số, đúng lý do giới hạn."""
    d = [f"Đã tách thành {sc.yeu_cau} tác vụ độc lập"
         + (f" (việc cha `{cha_id}`)" if cha_id else "") + "."]
    be = (f"Bể worker{(' ' + sc.provider) if sc.provider else ''}: {sc.tai_khoan_ranh} tài khoản "
          f"rảnh / {sc.tai_khoan_du_dk} đủ điều kiện, {sc.khe_ranh} slot trống")
    if sc.leader_chiem:
        be += f" (Leader đang chiếm 1 chỗ ở {', '.join(sc.leader_chiem)})"
    be += f"; trần song song của Control Center: {sc.tran_song_song}"
    if sc.dang_chay:
        be += f", đang chạy {sc.dang_chay}"
    d.append(be + ".")
    if sc.model:
        d.append(f"Model ghim theo yêu cầu: {sc.model}.")
    if sc.cho == 0:
        d.append(f"{sc.chay_ngay}/{sc.yeu_cau} worker slots khả dụng — dispatch {sc.yeu_cau} "
                 f"worker song song.")
    else:
        d.append(f"Hiện {sc.chay_ngay}/{sc.yeu_cau} worker slots khả dụng; {sc.chay_ngay} chạy "
                 f"ngay, {sc.cho} chờ slot (giới hạn bởi {sc.gioi_han_boi}).")
    for g in sc.ghi_chu:
        d.append(f"(ghi chú) {g}")
    return " ".join(d)


# ---------------------------------------------------------------- tong hop ---

_KET_QUA = re.compile(r"K[ẾE]T QU[ẢA]\s*\[\s*\d+\s*/\s*\d+\s*\]\s*:\s*(.+)", re.I)


def _chuan_ung_vien(s: str) -> str:
    s = gap_dau(s)
    s = re.sub(r"[`*_\"'“”‘’()\[\]{}<>]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,;:-—")
    return s


def ung_vien_tu_ket_qua(pb: Dict[str, Any]) -> str:
    """Ứng viên MỘT dòng của một con: dòng `KẾT QUẢ [i/N]: …` nếu có, không thì
    câu đầu của `summary`."""
    tom = str(pb.get("summary") or "").strip()
    m = _KET_QUA.search(tom)
    if m:
        return m.group(1).strip().splitlines()[0][:300]
    dau = re.split(r"(?<=[.!?])\s+|\n", tom, maxsplit=1)[0] if tom else ""
    return dau[:300]


def tong_hop(cha: Dict[str, Any], cac_con: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Gộp kết quả các con. `cac_con`: list dict {task_id, state, result, chi_so, runtime…}.

    Khử trùng theo dạng chuẩn (gấp dấu, bỏ ký tự trang trí); mỗi ứng viên giữ
    nguồn gốc: việc con, runtime, model, phiên. Con hỏng vẫn được kể — với lý
    do — chứ không biến mất.
    """
    ung: List[Dict[str, Any]] = []
    da_thay: Dict[str, Dict[str, Any]] = {}
    con_ra: List[Dict[str, Any]] = []
    xong = hong = khac = 0
    for c in sorted(cac_con, key=lambda x: int(x.get("chi_so") or 0)):
        st = str(c.get("state") or "")
        pb = ((c.get("result") or {}).get("envelope") or {}) if c.get("result") else {}
        uv = ung_vien_tu_ket_qua(pb) if st == "DONE" else ""
        nguon = {"task_id": c.get("task_id"), "chi_so": c.get("chi_so"),
                 "runtime": pb.get("worker") or c.get("runtime") or "",
                 "model": pb.get("model") or "", "session": c.get("owner_session") or "",
                 "duration": pb.get("duration")}
        con_ra.append({**nguon, "state": st, "ung_vien": uv,
                       "tom_tat": str(pb.get("summary") or "")[:400],
                       "failure_reason": str(pb.get("failure_reason") or "")})
        if st == "DONE":
            xong += 1
        elif st == "FAILED":
            hong += 1
        else:
            khac += 1
        if not uv or gap_dau(uv).startswith("khong co"):
            continue
        khoa = _chuan_ung_vien(uv)
        if khoa in da_thay:
            da_thay[khoa].setdefault("trung_voi", []).append(nguon["task_id"])
            continue
        muc = {"ung_vien": uv, "khoa": khoa, "nguon": nguon}
        da_thay[khoa] = muc
        ung.append(muc)
    trung = sum(len(m.get("trung_voi") or []) for m in ung)
    khoang = [dict((c.get("result") or {}).get("khoang_chay") or {}, task_id=c.get("task_id"))
              for c in cac_con if (c.get("result") or {}).get("khoang_chay")]
    return {"so_con": len(cac_con), "xong": xong, "hong": hong, "khac": khac,
            "ung_vien": ung, "trung_da_bo": trung, "con": con_ra,
            "cha": cha.get("task_id"), "muc_tieu": str(cha.get("title") or ""),
            "khoang_chay": khoang, "song_song_toi_da": song_song_toi_da(khoang)}


def song_song_toi_da(khoang: Sequence[Dict[str, Any]]) -> int:
    """Số khoảng chạy THẬT giao nhau nhiều nhất tại một thời điểm (quét mốc).
    Đây là số đo "song song thực" — không phải đếm trạng thái RUNNING trong sổ."""
    moc: List[Tuple[float, int]] = []
    for k in khoang:
        try:
            a, b = float(k.get("bat_dau")), float(k.get("ket_thuc"))
        except (TypeError, ValueError):
            continue
        if b <= a:
            continue
        moc.append((a, +1))
        moc.append((b, -1))
    # Ket thuc truoc bat dau khi trung moc: hai khoang cham nhau khong tinh la giao.
    moc.sort(key=lambda x: (x[0], x[1]))
    hien = cao = 0
    for _, d in moc:
        hien += d
        cao = max(cao, hien)
    return cao


def soan_tong_hop(th: Dict[str, Any]) -> str:
    """Câu người đọc: N/N con, ứng viên duy nhất, mỗi cái kèm nguồn gốc."""
    d = [f"🧩 Tổng hợp {th['xong']}/{th['so_con']} tác vụ con xong"
         + (f", {th['hong']} hỏng" if th.get("hong") else "")
         + (f", {th['khac']} chưa kết thúc" if th.get("khac") else "")
         + f" — {th['muc_tieu']}"
         + (f" · song song thực đo tối đa {th['song_song_toi_da']}/{th['so_con']}"
            if th.get("song_song_toi_da") else "")]
    if th["ung_vien"]:
        d.append("")
        d.append(f"{len(th['ung_vien'])} kết quả (đã khử {th['trung_da_bo']} trùng):")
        for k, m in enumerate(th["ung_vien"], start=1):
            ng = m["nguon"]
            d.append(f"  {k}. {m['ung_vien']}  _(từ [{ng.get('chi_so')}] {ng.get('runtime') or '?'}"
                     f"/{ng.get('model') or '?'} · `{ng.get('task_id')}`)_")
    else:
        d += ["", "(không con nào trả về ứng viên — xem từng việc con)"]
    hong = [c for c in th["con"] if c["state"] != "DONE"]
    if hong:
        d.append("")
        d.append("Con không xong:")
        for c in hong:
            d.append(f"  • [{c.get('chi_so')}] {c.get('task_id')} — {c['state']}"
                     + (f": {c['failure_reason']}" if c.get("failure_reason") else ""))
    return "\n".join(d)
