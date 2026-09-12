# -*- coding: utf-8 -*-
"""TRA CỨU THÀNH PHẦN DỰ ÁN — thang leo có ĐÁY, tất định, không LLM.

VÌ SAO CÓ FILE NÀY (dogfood thật, 2026-09-12). Người dùng hỏi tự nhiên:

    "ê cái tool cạo audio t sao r"

Leader tra Ký ức/Viên nang, KHÔNG thấy, rồi **hỏi ngược người dùng tên
script/thư mục**. Với một dự án đã nhận nuôi và trưởng thành, đó là câu trả
lời sai: người dùng không phải nhớ đường dẫn nội bộ.

Và thứ đó CÓ THẬT trong kho — `server/scraper/` (23 tệp, có
`chinese_media_sources.py`) cùng `scripts/chinese_media_pipeline.py` dùng
`yt_dlp`. Nên đây KHÔNG phải thiếu kiến thức; đây là **thiếu phép tra cứu**.

THANG LEO, dừng ngay khi đủ chắc, và mỗi bậc ghi lại NGUỒN:

    1. ký ức dự án (L1/L2)        5. tài liệu + HANDOFF/báo cáo
    2. viên nang                  6. lần thực thi / việc Router đã chạy
    3. tìm trong KHO (tên + nội dung)
    4. lịch sử git

Ba luật:

* **Không bịa.** Không tìm thấy thì nói không tìm thấy, kèm ĐÃ TRA NHỮNG ĐÂU.
* **Nói thật về vùng phủ.** Lịch sử ChatGPT Project không nằm trong tầm với
  của Router; báo đó là KHOẢNG TRỐNG chứ không im lặng lấp bằng phỏng đoán.
* **Không tạo việc worker** chỉ để trả lời một câu mà tra cứu trực tiếp đã
  đủ — đúng luật đã có của `nguon_git`/`web_reader`/`probe_van_hanh`.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.tien_trinh import an_cua_so

#: Bậc thang. Thứ tự CÓ NGHĨA: rẻ và chính xác trước, quét rộng sau.
BAC = ("ky_uc", "vien_nang", "kho", "git", "tai_lieu", "router")

#: Trần kết quả mỗi bậc — một câu trả lời 200 dòng cũng vô dụng như không có.
TRAN_MOI_BAC = 8

#: Từ khoá tiếng Việt thường gặp -> khái niệm kỹ thuật. Dùng để MỞ RỘNG câu
#: hỏi, không phải để kết luận. "cạo/cào" = scrape là cách nói của người dùng
#: này, đo được từ chính câu hỏi thật.
_MO_RONG: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("cạo", ("scrape", "scraper", "crawl", "harvest")),
    ("cào", ("scrape", "scraper", "crawl", "harvest")),
    ("crawl", ("scrape", "scraper", "crawler")),
    ("audio", ("audio", "tts", "voice", "yt_dlp", "media")),
    ("giọng", ("tts", "voice", "audio")),
    ("web", ("web", "next", "wrangler", "cloudflare", "frontend")),
    ("farmer", ("farmer", "rclone", "systemd")),
    ("lưu trữ", ("r2", "drive", "rclone", "archive")),
    ("kho ảnh", ("r2", "bucket")),
    ("truyện", ("story", "chapter", "fanfic", "harvest")),
    ("dịch", ("translat", "dich")),
    ("duyệt", ("review", "moderation", "queue")),
)

#: Thư mục KHÔNG phải "thành phần dự án" — nhiễu thuần tuý.
_BO_QUA = ("node_modules", ".git", "__pycache__", ".router", "dist", "build",
           "installer_output", ".venv", "venv")

#: Gốc chứa MÃ — nơi một "thành phần" thật sự sống.
_GOC_MA = ("server", "web", "desktop_app", "capcut_tts_api")

#: Thư mục là BẰNG CHỨNG *về* thành phần, không phải thành phần. Giữ chúng
#: ở ngoài danh sách ứng viên: tên tệp báo cáo khớp gần như mọi từ khoá, nên
#: để chúng dự thi thì `docs` luôn thắng và câu trả lời thành vô dụng.
_KHONG_PHAI_THANH_PHAN = ("docs", "deploy", "tests", "infra", ".github")


@dataclass
class BangChungTim:
    """MỘT mẩu bằng chứng, kèm bậc thang đã tìm ra nó."""

    bac: str
    nhan: str
    chi_tiet: str = ""
    duong: str = ""

    def to_dict(self) -> Dict:
        return {"bac": self.bac, "nhan": self.nhan,
                "chi_tiet": self.chi_tiet[:400], "duong": self.duong}


@dataclass
class KetQuaTim:
    """Kết luận tra cứu. `chac` = đủ chắc để trả lời thẳng."""

    cau_hoi: str
    ung_vien: List[Dict] = field(default_factory=list)
    bang_chung: List[BangChungTim] = field(default_factory=list)
    da_tra: List[str] = field(default_factory=list)
    khong_voi_toi: List[str] = field(default_factory=list)

    @property
    def chac(self) -> bool:
        """ĐÚNG MỘT ứng viên nổi trội rõ ràng."""
        if not self.ung_vien:
            return False
        if len(self.ung_vien) == 1:
            return True
        return (self.ung_vien[0].get("diem", 0)
                >= 2 * self.ung_vien[1].get("diem", 0))

    def to_dict(self) -> Dict:
        return {"cau_hoi": self.cau_hoi, "chac": self.chac,
                "ung_vien": self.ung_vien[:5],
                "bang_chung": [b.to_dict() for b in self.bang_chung[:20]],
                "da_tra": list(self.da_tra),
                "khong_voi_toi": list(self.khong_voi_toi)}


def mo_rong_tu_khoa(cau: str) -> List[str]:
    """Câu người dùng -> tập từ khoá kỹ thuật. TẤT ĐỊNH."""
    t = (cau or "").lower()
    ra: List[str] = []
    for k, dm in _MO_RONG:
        if k in t:
            ra.extend(dm)
    # Giữ lại cả từ dài của chính câu hỏi (tên riêng, tên module).
    for w in re.findall(r"[A-Za-z_][A-Za-z0-9_\-]{3,}", t):
        if w not in ra:
            ra.append(w)
    return ra[:12]


class BoTimThanhPhan:
    """Thang leo tra cứu. Mỗi bậc là một phép đọc AN TOÀN, không mạng."""

    def __init__(self, project_id: str, repo_root: Path, *, store=None,
                 ky_uc=None, so_thuc_thi=None, vien_nang: Optional[Dict] = None):
        self.project_id = project_id
        self.goc = Path(repo_root)
        self.store = store
        self.ky_uc = ky_uc
        self.so_thuc_thi = so_thuc_thi
        self.vien_nang = vien_nang or {}

    # ----------------------------------------------------------- bậc thang --

    def tim(self, cau: str, *, den_bac: str = "router") -> KetQuaTim:
        """Leo thang tới khi ĐỦ CHẮC hoặc hết bậc."""
        kq = KetQuaTim(cau_hoi=cau)
        tu = mo_rong_tu_khoa(cau)
        het = BAC.index(den_bac) if den_bac in BAC else len(BAC) - 1
        for b in BAC[:het + 1]:
            try:
                getattr(self, f"_bac_{b}")(cau, tu, kq)
            except Exception as exc:                          # noqa: BLE001
                kq.khong_voi_toi.append(f"{b}: {type(exc).__name__}")
                continue
            kq.da_tra.append(b)
            if kq.chac and b in ("ky_uc", "vien_nang", "kho"):
                break
        # VÙNG PHỦ: nói THẲNG thứ Router không với tới được.
        kq.khong_voi_toi.append(
            "lịch sử hội thoại ChatGPT Project: KHÔNG trong tầm với của Router")
        self._xep_hang(kq)
        return kq

    def _them(self, kq: KetQuaTim, ten: str, *, bac: str, diem: int,
              duong: str = "", vi_sao: str = "") -> None:
        for u in kq.ung_vien:
            if u["ten"] == ten:
                u["diem"] += diem
                if vi_sao and vi_sao not in u["vi_sao"]:
                    u["vi_sao"].append(vi_sao)
                return
        kq.ung_vien.append({"ten": ten, "diem": diem, "duong": duong,
                            "bac": bac, "vi_sao": [vi_sao] if vi_sao else []})

    def _bac_ky_uc(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        if self.ky_uc is None:
            kq.khong_voi_toi.append("ký ức dự án: không nạp được")
            return
        pv = self.ky_uc.provider(self.project_id)
        if pv is None:
            return
        for t in list(tu)[:6]:
            try:
                ds = pv.tim(t, limit=4)
            except Exception:                                 # noqa: BLE001
                continue
            for m in ds or ():
                nhan = str(getattr(m, "tom_tat", "") or getattr(m, "noi_dung", ""))[:160]
                if not nhan:
                    continue
                kq.bang_chung.append(BangChungTim("ky_uc", nhan))

    def _bac_vien_nang(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        for k, v in (self.vien_nang or {}).items():
            gt = v.get("gia_tri") if isinstance(v, dict) else v
            s = " ".join(gt) if isinstance(gt, (list, tuple)) else str(gt or "")
            hit = [t for t in tu if t.lower() in s.lower()]
            if hit:
                kq.bang_chung.append(
                    BangChungTim("vien_nang", f"mục {k}", s[:200]))

    def _bac_kho(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        """Tìm trong KHO: tên tệp/thư mục TRƯỚC, rồi nội dung."""
        tep = self._ls_files()
        for t in tu:
            tl = t.lower()
            khop = [p for p in tep if tl in p.lower()]
            for p in khop[:TRAN_MOI_BAC]:
                goi = self._goi_cua(p)
                kq.bang_chung.append(BangChungTim("kho", f"tệp khớp {t!r}", p, p))
                if goi:
                    self._them(kq, goi, bac="kho", diem=3, duong=goi,
                               vi_sao=f"tên tệp khớp {t!r}: {p}")
        # Nội dung — chỉ khi tên chưa cho ứng viên nào.
        if not kq.ung_vien:
            for t in list(tu)[:4]:
                ma, ra = self._git("grep", "-l", "-i", t, "--", "*.py", "*.ts",
                                   "*.tsx", "*.md")
                if ma != 0:
                    continue
                for p in [x for x in ra.splitlines() if x][:TRAN_MOI_BAC]:
                    goi = self._goi_cua(p)
                    if goi:
                        self._them(kq, goi, bac="kho", diem=1, duong=goi,
                                   vi_sao=f"nội dung nhắc {t!r}: {p}")

    def _bac_git(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        for t in list(tu)[:4]:
            ma, ra = self._git("log", "--oneline", "-8", f"--grep={t}", "-i")
            for d in [x for x in (ra or "").splitlines() if x][:4]:
                kq.bang_chung.append(BangChungTim("git", f"commit nhắc {t!r}", d))

    def _bac_tai_lieu(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        for t in list(tu)[:5]:
            ma, ra = self._git("grep", "-l", "-i", t, "--", "docs/")
            if ma != 0:
                continue
            for p in [x for x in ra.splitlines() if x][:4]:
                kq.bang_chung.append(BangChungTim("tai_lieu", f"tài liệu nhắc {t!r}", p, p))

    def _bac_router(self, cau: str, tu: Sequence[str], kq: KetQuaTim) -> None:
        if self.store is None:
            kq.khong_voi_toi.append("lịch sử Router: không nạp được")
            return
        try:
            ds = self.store.tasks(self.project_id, limit=200)
        except Exception:                                     # noqa: BLE001
            return
        for t in ds:
            van = f"{t.title} {t.objective}".lower()
            if any(x.lower() in van for x in tu):
                kq.bang_chung.append(BangChungTim(
                    "router", f"việc {t.task_id} [{t.state.value}]",
                    (t.title or "")[:120]))

    # ------------------------------------------------------------- tiện ích --

    def _xep_hang(self, kq: KetQuaTim) -> None:
        kq.ung_vien.sort(key=lambda u: -int(u.get("diem") or 0))

    def _goi_cua(self, duong: str) -> str:
        """Quy một tệp về THÀNH PHẦN chứa nó. `""` = KHÔNG phải thành phần.

        Hai điều đã đo được ở lần thử đầu và phải sửa:

        * `docs/` và `deploy/` KHÔNG phải thành phần — chúng là BẰNG CHỨNG
          *về* thành phần. Để chúng làm ứng viên thì câu "tool cạo audio" ra
          ngay `docs` (điểm 51) trên `server/scraper` (45), vì tên tệp báo
          cáo có đủ mọi từ khoá. Đó là câu trả lời vô dụng.
        * `scripts/<tool>.py` thì CHÍNH TỆP là công cụ, không phải cả thư
          mục `scripts/` (hàng trăm tệp).
        """
        p = [x for x in duong.replace("\\", "/").split("/") if x]
        if not p:
            return ""
        if p[0] in _KHONG_PHAI_THANH_PHAN:
            return ""
        # Thư mục bài kiểm ở BẤT KỲ tầng nào cũng là bằng chứng, không phải
        # thành phần: `server/tests/test_local_voice_allowlist.py` không phải
        # câu trả lời cho "tool cạo audio".
        if "tests" in p[:-1]:
            return ""
        if p[0] == "scripts":
            if len(p) == 2 and p[1].endswith(".py"):
                return f"scripts/{p[1][:-3]}"
            return f"scripts/{p[1]}" if len(p) >= 3 else "scripts"
        if p[0] in _GOC_MA and len(p) >= 3:
            return f"{p[0]}/{p[1]}"
        return p[0]

    def _ls_files(self) -> List[str]:
        ma, ra = self._git("ls-files")
        if ma != 0:
            return []
        return [x for x in ra.splitlines()
                if x and not any(b in x for b in _BO_QUA)]

    def _git(self, *args: str) -> Tuple[int, str]:
        try:
            r = subprocess.run(["git", *args], cwd=str(self.goc),
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               **an_cua_so())
        except (OSError, subprocess.TimeoutExpired):
            return 127, ""
        return int(r.returncode), (r.stdout or "")


def goi_tra_loi(kq: KetQuaTim) -> str:
    """Khối BẰNG CHỨNG cho Leader. Không kết luận hộ, chỉ đưa cái đã tra."""
    d = [f"TRA CỨU THÀNH PHẦN cho: {kq.cau_hoi!r}",
         f"  đã tra: {', '.join(kq.da_tra) or '(không bậc nào)'}"]
    if kq.ung_vien:
        d.append("  ỨNG VIÊN (điểm cao nhất trước):")
        for u in kq.ung_vien[:3]:
            d.append(f"    · {u['ten']}  (điểm {u['diem']})")
            for v in u["vi_sao"][:2]:
                d.append(f"        {v[:150]}")
    else:
        d.append("  KHÔNG tìm thấy ứng viên nào trong các bậc đã tra.")
    if kq.bang_chung:
        d.append("  bằng chứng:")
        for b in kq.bang_chung[:6]:
            d.append(f"    [{b.bac}] {b.nhan} {b.chi_tiet[:90]}")
    if kq.khong_voi_toi:
        d.append("  VÙNG KHÔNG PHỦ (nói thật, không đoán):")
        for x in kq.khong_voi_toi[:4]:
            d.append(f"    - {x}")
    return "\n".join(d)
