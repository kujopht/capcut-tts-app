"""NHẬP KHẨU lịch sử — QUÁ KHỨ của một dự án đi vào ký ức, có nguồn gốc.

    QUÁ KHỨ + HIỆN TẠI + TƯƠNG LAI  ->  KÝ ỨC DỰ ÁN

V0.6 chỉ ghi từ lúc ký ức được bật. Mọi thứ trước đó — sự kiện Router,
commit, tài liệu, báo cáo, HANDOFF, phiên Claude Code của chính kho này —
là lịch sử THẬT của dự án và nằm sẵn trên đĩa. Module này đưa chúng vào
L0 dưới `loai = "backfill:<adapter>:<kind>"`, mỗi dòng mang `tham_chieu`
= mã nguồn (đường tệp + mốc) và `meta` = băm/mtime, rồi ĐỀ BẠT theo cùng
luật tất định của `de_bat.py`.

BỐN ADAPTER, MỖI CÁI MỘT PHẠM VI DỰ ÁN TƯỜNG MINH:

  so_chinh   `cc_events` + `chat` của CHÍNH dự án trong sổ Control Center
  git        `git log` của `repo_path` — commit của kho dự án
  tai_lieu   `docs/**/*.md`, `README.md`, `CLAUDE.md`, `HANDOFF*.md` trong
             `repo_path`, cắt theo tiêu đề `##`
  phien_claude  `~/.claude/projects/<slug>/*.jsonl` CHỈ cho những slug ứng
             với các WORKTREE của đúng kho git này (`git worktree list` từ
             `repo_path`). Phiên của dự án khác không bao giờ được đọc.

KHÔNG quét cả máy. KHÔNG bịa nguồn: nguồn không có thì báo `khong_san`
kèm lý do, không im lặng và không "coi như đã nhập".

AN TOÀN NHẬP KHẨU:
  * idempotent — sổ `nhap_khau` ghi `(nguon, ma_nguon, sha)`; đã có thì bỏ
    qua (đếm vào `trung`);
  * chỉ ĐỌC nguồn — không tệp nguồn nào bị sửa;
  * L0 chỉ-thêm — không dòng cũ nào bị ghi đè;
  * bí mật bị lọc ở cổng vào như mọi dòng khác (`kho.ghi_su_kien` →
    `bi_mat.loc`); `da_loc` được cộng dồn vào thống kê;
  * resumable — chạy lại tiếp tục từ chỗ dừng vì sổ nhập khẩu là theo mục;
  * `thu_kho=True` (dry-run) chỉ đếm, không ghi.

ĐỀ BẠT TỪ LỊCH SỬ — LUÔN `tin_cay = backfill`, KHÔNG BAO GIỜ `user_explicit`:
  * tin nhắn NGƯỞI DÙNG trong phiên cũ / chat cũ: `de_bat.xet()` → nếu là
    tuyên bố tường minh thì đề bạt, `the` ghi `chat_user`. Thẩm quyền vẫn
    là `backfill` vì vai "user" trong tệp phiên KHÔNG chứng minh người gõ:
    bản tóm tắt nén ngữ cảnh, thân skill, đầu ra lệnh `/…`, nhắc nhở hệ
    thống đều mang vai "user". Những dòng đó bị LOẠI hẳn (`_TIN_TONG_HOP`),
    và phần còn lại vẫn chỉ được xếp dưới mọi tuyên bố sống;
  * mục tài liệu có tiêu đề kiểu "Bẫy đã gặp"/"Sự cố"/"Incident" →
    INCIDENT; "Quy trình"/"Runbook" → PROCEDURAL;
  * tin nhắn TRỢ LÝ trong phiên cũ: INCIDENT chỉ khi có ≥3 dấu hiệu sự cố
    KHÁC NHAU, trong đó ít nhất một dấu hiệu MẠNH (root cause / nguyên nhân
    gốc / sự cố / typo / permission denied / ACL…), VÀ nêu đích danh một
    tệp/dịch vụ. Báo cáo "Done." chỉ có "fixed"+"failed" thì không đủ.
  Mọi bản ghi đều có bằng chứng trỏ về đúng dòng L0 vừa nhập.

CHỈ ĐỀ BẠT LỊCH SỬ TRƯỚC KHI KÝ ỨC TỒN TẠI (`ts < moc_ky_uc`). Mọi thứ sau
mốc đó đã/đang được người ghi trực tiếp lo; và một tin nhắn hôm nay mô tả
một sự cố cũ (kể cả chính đề bài của một task) KHÔNG được biến thành bản
ghi "lịch sử" — đó là bịa nguồn gốc.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from scripts.control_center.memory import de_bat as DB
from scripts.control_center.memory.model import (BangChung, KyUc, LoaiKyUc,
                                                 SuKien, TinCay, bam, gap_dau)
# `git` song NGOAI goi memory (rao: khong subprocess trong memory/).
from scripts.control_center.nguon_git import (git_log_tho, git_worktrees,
                                              ly_do_khong_phai_kho)

#: Tran inline cho mot muc nhap; phan day di vao blob.
TRAN_TOM_TAT = 2000
#: Tran mot tin nhan phien Claude duoc giu (blob). Lon hon thi cat + ghi ro.
TRAN_TIN_PHIEN = 64 * 1024
#: Tran so muc moi lan chay (resumable — lan sau tiep).
TRAN_MOI_LAN = 5000
#: Tep phien Claude sua trong khoang nay = PHIEN DANG MO -> bo qua lan nay.
#: Mot phien dang chay la HIEN TAI, khong phai lich su: no chua xong, va no
#: co the chua chinh de bai dang mo ta mot su co cu — nhap no la bia nguon.
PHIEN_DANG_MO_GIAY = 600.0

#: Ten tep tai lieu KHONG doc (bi mat/khong phai tai lieu).
_BO_TEP = re.compile(r"(^\.env|\.pem$|\.key$|credentials|secret|\.p12$|\.pfx$)", re.I)

#: Tieu de muc tai lieu -> INCIDENT / PROCEDURAL (so tren dang gap dau).
_TIEU_DE_SU_CO = re.compile(r"\b(bay da gap|bay|su co|incident|postmortem|loi that|"
                            r"khuyet tat|defect|hong)\b")
_TIEU_DE_QUY_TRINH = re.compile(r"\b(quy trinh|cach (chay|build|deploy|dung)|runbook|"
                                r"sop|lenh thuong dung|huong dan)\b")

#: Dau hieu su co trong tin nhan TRO LY (lich su phien cu). Can >= 3 dau hieu
#: KHAC NHAU, it nhat mot dau hieu MANH, + mot dinh danh (ten tep .ext / dich
#: vu) de tranh nhieu: bao cao cuoi phien nao cung co "fixed"/"failed".
_DAU_SU_CO_MANH = (
    r"\broot cause\b", r"\bnguyen nhan (goc|that)\b", r"\btypo\b", r"\bsai ten\b",
    r"\bmis-?(spell|typ)(ed|ing)?\b", r"\bwrong (path|name|file|key)\b",
    r"\bpermission denied\b", r"\bauthentication failed\b", r"\bincident\b", r"\bsu co\b",
    r"\bpost-?mortem\b", r"\bregression\b", r"\bacl\b", r"\bicacls\b", r"\bwas gone\b",
)
_DAU_SU_CO_YEU = (
    r"\bkhong khop\b", r"\bmismatch\b", r"\bthat bai\b", r"\bfailed\b", r"\bbi loi\b",
    r"\bloi that\b", r"\bda sua\b", r"\bfixed\b", r"\bworkaround\b", r"\brejected\b",
    r"\bkhong ton tai\b", r"\b(does|did) not exist\b", r"\bno such file\b", r"\bnot found\b",
)
_DAU_SU_CO = _DAU_SU_CO_MANH + _DAU_SU_CO_YEU
_DINH_DANH = re.compile(r"\b[\w-]+\.(pem|py|json|db|env|md|exe|yml|yaml|toml|sh|ps1|cmd|log)\b"
                        r"|\bfanfic-[\w-]+\b|\bsystemd\b|\bssh\b", re.I)
_TEN_TEP = re.compile(r"\b[\w-]{4,}\.(pem|py|json|db|env|md|exe|yml|yaml|toml|sh|ps1|cmd|log|key)\b",
                      re.I)


def _lech_mot(a: str, b: str) -> bool:
    """Hai tên chỉ lệch MỘT phép sửa (thêm/bớt/đổi một ký tự)?"""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    dai, ngan = (a, b) if len(a) > len(b) else (b, a)
    for i in range(len(dai)):
        if dai[:i] + dai[i + 1:] == ngan:
            return True
    return False


def ten_hai_cach_viet(van: str) -> Optional[tuple]:
    """Một tên tệp xuất hiện với HAI cách viết lệch một ký tự trong cùng văn bản
    (`fanficappwrite.pem` / `fanficappwrrite.pem`) — chữ ký của sự cố sai tên /
    sai đường dẫn, độc lập ngôn ngữ. Trả (tên_a, tên_b) hoặc None."""
    ten = []
    for mo in _TEN_TEP.finditer(van):
        t = mo.group(0).lower()
        if t not in ten:
            ten.append(t)
        if len(ten) >= 60:
            break
    for i, a in enumerate(ten):
        for b in ten[i + 1:]:
            if _lech_mot(a, b):
                return (a, b)
    return None


def _trich(van: str, vi_tri: int, rong: int = 700) -> str:
    """Đoạn quanh `vi_tri`, cắt ở ranh giới dòng/câu, có dấu `…` khi bị cắt."""
    a = max(0, vi_tri - rong)
    b = min(len(van), vi_tri + rong)
    doan = van[a:b]
    if a > 0:
        cat = re.search(r"[.!?]\s+|\n", doan[:rong // 2])
        if cat:
            doan = doan[cat.end():]
        doan = "… " + doan.lstrip()
    if b < len(van):
        cat = None
        for mo in re.finditer(r"[.!?](?=\s)|\n", doan):
            if mo.start() > len(doan) - rong // 2:
                cat = mo
                break
        if cat:
            doan = doan[:cat.end()]
        doan = doan.rstrip() + " …"
    return doan.strip()

#: Vai "user" trong tep phien NHUNG khong phai nguoi go: tom tat nen ngu canh,
#: than skill / lenh gach cheo, nhac nho he thong, ngat. KHONG de bat tu day.
_TIN_TONG_HOP = re.compile(
    r"^\s*this session is being continued from a previous conversation"
    r"|<system-reminder>|<command-name>|<command-message>|<local-command-stdout>"
    r"|<local-command-caveat>|\[request interrupted"
    r"|^\s*#\s+[^\n]{0,80}\bskill\b", re.I)


def tin_nguoi_go(van: str, d: Optional[Dict] = None) -> bool:
    """Tin vai "user" này có phải do NGƯỜI gõ không (đủ để xét đề bạt)?"""
    if d and (d.get("isMeta") or d.get("isCompactSummary") or d.get("isSidechain")):
        return False
    return not _TIN_TONG_HOP.search(van[:4000])


@dataclass
class MucNhap:
    """Một mục lịch sử từ một adapter."""
    ma_nguon: str            # duy nhat trong adapter: "chat:12", "<sha>", "docs/x.md#tieu-de"
    ts: float
    loai: str                # "chat_user" | "chat_assistant" | "event" | "commit" | "doc" | ...
    tom_tat: str
    noi_dung_day: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    vai: str = ""            # "user" | "assistant" | "" (cho de bat)
    tieu_de: str = ""

    @property
    def sha(self) -> str:
        return bam(f"{self.ma_nguon}\x1f{self.noi_dung_day or self.tom_tat}")


@dataclass
class ThongKeNhap:
    nguon: str
    thu_kho: bool
    kham_pha: int = 0
    da_nhap: int = 0
    trung: int = 0
    bo_qua: int = 0
    da_loc: int = 0
    de_bat: int = 0
    khong_san: str = ""      # ly do nguon khong san, rong = san
    con_lai: int = 0         # muc chua nhap vi tran moi lan
    giay: float = 0.0
    ghi_chu: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"nguon": self.nguon, "thu_kho": self.thu_kho, "kham_pha": self.kham_pha,
                "da_nhap": self.da_nhap, "trung": self.trung, "bo_qua": self.bo_qua,
                "da_loc": self.da_loc, "de_bat": self.de_bat,
                "khong_san": self.khong_san, "con_lai": self.con_lai,
                "giay": round(self.giay, 2), "ghi_chu": self.ghi_chu[:8]}


# ================================================================ adapter ==

class Adapter:
    ma = "co-so"
    nhan = "Cơ sở"

    def san(self) -> str:
        """`""` nếu nguồn sẵn, ngược lại lý do (đọc được) vì sao không."""
        return "chưa cài"

    def muc(self) -> Iterator[MucNhap]:                     # pragma: no cover
        return iter(())


class SoChinhAdapter(Adapter):
    """`cc_events` + `chat` của đúng dự án trong sổ Control Center."""
    ma = "so_chinh"
    nhan = "Lịch sử Router (sổ Control Center)"

    def __init__(self, store, project_id: str):
        self.store = store
        self.project_id = project_id

    def san(self) -> str:
        try:
            self.store.su_kien(project_id=self.project_id, limit=1)
            return ""
        except Exception as exc:                            # noqa: BLE001
            return f"không đọc được sổ: {type(exc).__name__}"

    def muc(self) -> Iterator[MucNhap]:
        for e in reversed(self.store.su_kien(project_id=self.project_id, limit=100000)):
            k = str(e.get("kind") or "")
            if k.startswith("MEMORY_"):
                continue
            yield MucNhap(ma_nguon=f"cc_events:{e['id']}", ts=float(e["ts"]), loai="event",
                          tom_tat=f"{k}: {e.get('detail') or ''}",
                          meta={"kind": k, "level": e.get("level"), "task_id": e.get("task_id"),
                                "cc_event_id": e["id"]})
        for m in self.store.chat(self.project_id, limit=100000):
            yield MucNhap(ma_nguon=f"chat:{m.message_id}", ts=float(m.ts),
                          loai=f"chat_{m.role}", tom_tat=m.text, noi_dung_day=m.text,
                          vai=m.role, meta={"message_id": m.message_id,
                                            "loai_tin": str((m.meta or {}).get("loai") or "")})


class GitAdapter(Adapter):
    ma = "git"
    nhan = "Lịch sử git (commit của kho dự án)"

    def __init__(self, repo_path: str, *, gioi_han: int = 3000):
        self.repo = Path(repo_path)
        self.gioi_han = gioi_han

    def san(self) -> str:
        return ly_do_khong_phai_kho(self.repo)

    def muc(self) -> Iterator[MucNhap]:
        tho = git_log_tho(self.repo, gioi_han=self.gioi_han)
        if not tho:
            return
        for rec in tho.split("\x1e"):
            rec = rec.strip("\n\r ")
            if not rec:
                continue
            phan = rec.split("\x1f")
            if len(phan) < 4:
                continue
            sha, at, an, subj = phan[0].strip(), phan[1].strip(), phan[2].strip(), phan[3].strip()
            body = phan[4].strip() if len(phan) > 4 else ""
            try:
                ts = float(at)
            except ValueError:
                ts = time.time()
            day = f"{subj}\n\n{body}".strip()
            yield MucNhap(ma_nguon=sha, ts=ts, loai="commit", tom_tat=f"{sha[:10]} {subj}",
                          noi_dung_day=day, tieu_de=subj,
                          meta={"sha": sha, "author": an, "subject": subj})


class TaiLieuAdapter(Adapter):
    ma = "tai_lieu"
    nhan = "Tài liệu / báo cáo / HANDOFF của dự án"

    def __init__(self, repo_path: str):
        self.repo = Path(repo_path)

    def san(self) -> str:
        if not self.repo.is_dir():
            return f"không có thư mục kho: {self.repo}"
        if not any(self._tep()):
            return "không có tài liệu .md nào"
        return ""

    def _tep(self) -> Iterator[Path]:
        goc = self.repo
        for p in (goc / "README.md", goc / "CLAUDE.md"):
            if p.is_file():
                yield p
        for p in sorted(goc.glob("HANDOFF*.md")):
            yield p
        d = goc / "docs"
        if d.is_dir():
            for p in sorted(d.rglob("*.md")):
                if not _BO_TEP.search(p.name) and ".router" not in p.parts:
                    yield p

    def muc(self) -> Iterator[MucNhap]:
        for p in self._tep():
            try:
                van = p.read_text(encoding="utf-8", errors="replace")
                mtime = p.stat().st_mtime
            except OSError:
                continue
            rel = p.relative_to(self.repo).as_posix()
            for tieu_de, than in _cat_theo_tieu_de(van):
                if len(than.strip()) < 40:
                    continue
                slug = re.sub(r"[^a-z0-9]+", "-", gap_dau(tieu_de))[:60].strip("-") or "dau"
                sha = bam(than)[:12]
                yield MucNhap(ma_nguon=f"{rel}#{slug}#{sha}", ts=mtime, loai="doc",
                              tom_tat=f"{rel} § {tieu_de}\n{than}", noi_dung_day=than,
                              tieu_de=tieu_de,
                              meta={"path": rel, "heading": tieu_de, "sha12": sha})


def _cat_theo_tieu_de(van: str) -> Iterator[tuple]:
    """(tiêu đề, thân) cho mỗi mục `#`/`##`/`###`; phần trước tiêu đề đầu = 'mở đầu'."""
    tieu_de, dong = "mở đầu", []
    for line in van.splitlines():
        if re.match(r"^#{1,3}\s+\S", line):
            if dong:
                yield tieu_de, "\n".join(dong)
            tieu_de, dong = re.sub(r"^#+\s+", "", line).strip(), []
        else:
            dong.append(line)
    if dong:
        yield tieu_de, "\n".join(dong)


class PhienClaudeAdapter(Adapter):
    """Phiên Claude Code CỦA ĐÚNG KHO NÀY — theo `git worktree list`."""
    ma = "phien_claude"
    nhan = "Phiên Claude Code của kho (theo worktree)"

    def __init__(self, repo_path: str, *, goc_claude: Optional[Path] = None,
                 loai_tru: Sequence[str] = ()):
        self.repo = Path(repo_path)
        self.goc = Path(goc_claude) if goc_claude else Path.home() / ".claude" / "projects"
        self.loai_tru = set(loai_tru)
        self._slugs: Optional[List[str]] = None
        #: Ghi chu cho thong ke lan chay (phien dang mo bi bo qua, ...).
        self.ghi_chu: List[str] = []

    @staticmethod
    def slug_cua(duong: str) -> str:
        """`C:\\FanficWorkers\\claude-lead` -> `C--FanficWorkers-claude-lead`."""
        s = str(duong).replace("\\", "/").rstrip("/")
        return re.sub(r"[:/]", "-", s)

    def worktrees(self) -> List[str]:
        if self._slugs is not None:
            return self._slugs
        ra: List[str] = []
        for d in git_worktrees(self.repo):
            # Bo worktree con do Router/Claude tu sinh ben trong kho.
            if "/.router/" in d.replace("\\", "/") or "/.claude/" in d.replace("\\", "/"):
                continue
            ra.append(d)
        if not ra:
            ra = [str(self.repo)]
        self._slugs = [self.slug_cua(d) for d in ra]
        return self._slugs

    def thu_muc(self) -> List[Path]:
        return [self.goc / s for s in self.worktrees() if (self.goc / s).is_dir()]

    def san(self) -> str:
        if not self.goc.is_dir():
            return f"không có {self.goc}"
        ds = self.thu_muc()
        if not ds:
            return "không có phiên Claude nào ứng với worktree của kho này"
        return ""

    def tep(self, *, now: Optional[float] = None) -> List[Path]:
        ra = []
        curr = time.time() if now is None else now
        dang_mo = 0
        for d in self.thu_muc():
            for f in sorted(d.glob("*.jsonl")):
                if f.stem in self.loai_tru:
                    continue
                try:
                    if curr - f.stat().st_mtime < PHIEN_DANG_MO_GIAY:
                        dang_mo += 1
                        continue
                except OSError:
                    continue
                ra.append(f)
        self.ghi_chu = ([f"bỏ qua {dang_mo} phiên đang mở (sửa < {int(PHIEN_DANG_MO_GIAY)}s) "
                         f"— là hiện tại, không phải lịch sử; lần sau nhập tiếp"]
                        if dang_mo else [])
        return ra

    def muc(self) -> Iterator[MucNhap]:
        for f in self.tep():
            slug = f.parent.name
            try:
                fh = f.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for i, line in enumerate(fh):
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    t = d.get("type")
                    if t not in ("user", "assistant"):
                        continue
                    msg = d.get("message") or {}
                    van = _van_ban_tin(msg)
                    if not van or len(van.strip()) < 3:
                        continue
                    ts = _ts_iso(d.get("timestamp")) or f.stat().st_mtime
                    uuid = str(d.get("uuid") or i)
                    day = van if len(van) <= TRAN_TIN_PHIEN else \
                        van[:TRAN_TIN_PHIEN] + "\n[... ĐÃ CẮT: tin nhắn vượt 64 KiB ...]"
                    vai = str(msg.get("role") or t)
                    # Vai "user" nhung khong phai nguoi go -> van vao L0 (lich
                    # su that) nhung vai rong => khong bao gio duoc de bat.
                    if vai == "user" and not tin_nguoi_go(van, d):
                        vai = ""
                    yield MucNhap(ma_nguon=f"{slug}/{f.stem}:{uuid}", ts=ts,
                                  loai=f"chat_{msg.get('role') or t}", tom_tat=day,
                                  noi_dung_day=day, vai=vai,
                                  meta={"slug": slug, "session": f.stem, "line": i,
                                        "uuid": uuid, "path": str(f),
                                        "tong_hop": vai == ""})


def _van_ban_tin(msg: Dict) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    ra = []
    for kh in c or []:
        if isinstance(kh, dict) and kh.get("type") == "text":
            ra.append(str(kh.get("text") or ""))
    return "\n".join(ra)


def _ts_iso(s) -> float:
    if not s:
        return 0.0
    try:
        from datetime import datetime, timezone
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ============================================================== de bat ====

def de_bat_tu_muc(m: MucNhap) -> Optional[tuple]:
    """(loai, noi_dung, tieu_de, tin_cay, dau_hieu, kq_de_bat) hoặc None.

    `tin_cay` LUÔN là `BACKFILL`: lịch sử không bao giờ mang thẩm quyền của
    một tuyên bố sống (xem docstring module).
    """
    if m.vai == "user":
        if not tin_nguoi_go(m.tom_tat):
            return None
        kq = DB.xet(m.tom_tat)
        if kq is None:
            return None
        return (kq.loai, kq.noi_dung, kq.tieu_de, TinCay.BACKFILL,
                tuple(kq.dau_hieu)[:4], kq)
    if m.loai == "doc":
        td = gap_dau(m.tieu_de)
        if _TIEU_DE_SU_CO.search(td):
            return (LoaiKyUc.INCIDENT, m.noi_dung_day[:1500], m.tieu_de[:90],
                    TinCay.BACKFILL, ("tieu_de_su_co",), None)
        if _TIEU_DE_QUY_TRINH.search(td):
            return (LoaiKyUc.PROCEDURAL, m.noi_dung_day[:1500], m.tieu_de[:90],
                    TinCay.BACKFILL, ("tieu_de_quy_trinh",), None)
        return None
    if m.vai == "assistant":
        van = m.tom_tat
        if len(van) > 12000 or len(van) < 60:
            return None
        gap = gap_dau(van)
        manh = [x for x in _DAU_SU_CO_MANH if re.search(x, gap)]
        yeu = [x for x in _DAU_SU_CO_YEU if re.search(x, gap)]
        lech = ten_hai_cach_viet(van)
        du = (bool(manh) and len(manh) + len(yeu) >= 3) or (lech is not None and (manh or yeu))
        if not du or not _DINH_DANH.search(van):
            return None
        dau = ([f"ten_hai_cach_viet:{lech[0]}≠{lech[1]}"] if lech else []) + manh + yeu
        # Noi dung = doan QUANH dau hieu, khong phai 1500 ky tu dau cua mot bao
        # cao dai — ket luan ve su co thuong nam giua bai.
        vi_tri = 0
        if lech:
            mo = re.search(re.escape(lech[0]) + "|" + re.escape(lech[1]), van, re.I)
            vi_tri = mo.start() if mo else 0
        else:
            mo = re.search(manh[0], gap)
            vi_tri = mo.start() if mo else 0
        doan = _trich(van, vi_tri) if len(van) > 1500 else van
        cau = re.split(r"(?<=[.!?])\s+|\n", doan.lstrip("… ").strip(), maxsplit=1)[0]
        return (LoaiKyUc.INCIDENT, doan[:1500], cau[:90], TinCay.BACKFILL,
                tuple(dau)[:4], None)
    return None


# =============================================================== dich vu ==

LUOC_DO_NHAP = """
CREATE TABLE IF NOT EXISTS nhap_khau (
    nguon      TEXT NOT NULL,
    ma_nguon   TEXT NOT NULL,
    sha        TEXT NOT NULL,
    su_kien_id INTEGER NOT NULL DEFAULT 0,
    ts         REAL NOT NULL,
    PRIMARY KEY (nguon, ma_nguon)
);
CREATE TABLE IF NOT EXISTS nhap_khau_lan (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nguon     TEXT NOT NULL,
    ts        REAL NOT NULL,
    thu_kho   INTEGER NOT NULL DEFAULT 0,
    thong_ke  TEXT NOT NULL DEFAULT '{}'
);
"""


class BoNhapKhau:
    """Chạy các adapter cho MỘT dự án vào MỘT provider ký ức."""

    def __init__(self, provider, adapters: Sequence[Adapter], *,
                 moc_ky_uc: Optional[float] = None, tran: int = TRAN_MOI_LAN):
        self.p = provider
        self.adapters = list(adapters)
        self.tran = tran
        kho = provider.kho
        kho._c().executescript(LUOC_DO_NHAP)
        # Moc: chi de bat lich su TRUOC khi so ky uc ton tai.
        if moc_ky_uc is None:
            try:
                r = kho._c().execute("SELECT MIN(ts) FROM su_kien WHERE loai NOT LIKE 'backfill:%'"
                                     ).fetchone()
                moc_ky_uc = float(r[0]) if r and r[0] else time.time()
            except Exception:                               # noqa: BLE001
                moc_ky_uc = time.time()
        self.moc_ky_uc = moc_ky_uc

    def _da_co(self, nguon: str, ma_nguon: str) -> bool:
        r = self.p.kho._c().execute(
            "SELECT 1 FROM nhap_khau WHERE nguon=? AND ma_nguon=?", (nguon, ma_nguon)).fetchone()
        return r is not None

    def trang_thai(self) -> List[Dict]:
        """Nguồn nào sẵn, đã nhập bao nhiêu, lần cuối khi nào."""
        c = self.p.kho._c()
        ra = []
        for a in self.adapters:
            ly = a.san()
            n = int(c.execute("SELECT count(*) FROM nhap_khau WHERE nguon=?", (a.ma,)).fetchone()[0])
            lan = c.execute("SELECT ts, thu_kho, thong_ke FROM nhap_khau_lan WHERE nguon=? "
                            "ORDER BY id DESC LIMIT 1", (a.ma,)).fetchone()
            ra.append({"nguon": a.ma, "nhan": a.nhan, "san": not ly, "ly_do": ly,
                       "da_nhap": n,
                       "lan_cuoi": {"ts": lan["ts"], "thu_kho": bool(lan["thu_kho"]),
                                    "thong_ke": json.loads(lan["thong_ke"] or "{}")} if lan else None})
        return ra

    def chay(self, *, thu_kho: bool = False, chi: Optional[Sequence[str]] = None,
             han_giay: float = 120.0) -> List[ThongKeNhap]:
        """Chạy mọi adapter (hoặc `chi`). Mỗi lượt tối đa `tran` mục; lặp lượt
        cho tới khi hết `con_lai` hoặc quá `han_giay` — quá thì dừng SẠCH và
        `con_lai` nói còn bao nhiêu (lần chạy sau tiếp, vì sổ nhập là theo mục)."""
        ra = []
        t0 = time.perf_counter()
        for a in self.adapters:
            if chi and a.ma not in chi:
                continue
            tk = self._chay_mot(a, thu_kho=thu_kho)
            while (tk.con_lai and not thu_kho and not tk.khong_san
                   and time.perf_counter() - t0 < han_giay):
                them = self._chay_mot(a, thu_kho=False)
                # `trung` giu so cua LUOT DAU: la muc da co TRUOC lan chay nay.
                # Luot sau thay ca muc luot truoc vua nhap la "trung" — khong
                # phai trung theo nghia nguoi dung can biet.
                tk.kham_pha, tk.con_lai = them.kham_pha, them.con_lai
                tk.da_nhap += them.da_nhap
                tk.bo_qua += them.bo_qua; tk.da_loc += them.da_loc
                tk.de_bat += them.de_bat; tk.giay += them.giay
                tk.ghi_chu.extend(them.ghi_chu)
                if them.da_nhap == 0:        # khong tien duoc -> khong lap vo han
                    break
            if tk.con_lai:
                tk.ghi_chu.append(f"còn {tk.con_lai} mục — chạy lại để tiếp")
            ra.append(tk)
        return ra

    def _chay_mot(self, a: Adapter, *, thu_kho: bool) -> ThongKeNhap:
        t0 = time.perf_counter()
        tk = ThongKeNhap(nguon=a.ma, thu_kho=thu_kho)
        ly = a.san()
        if ly:
            tk.khong_san = ly
            tk.giay = time.perf_counter() - t0
            self._ghi_lan(tk)
            return tk
        c = self.p.kho._c()
        so = 0
        try:
            for m in a.muc():
                tk.kham_pha += 1
                if self._da_co(a.ma, m.ma_nguon):
                    tk.trung += 1
                    continue
                if so >= self.tran:
                    tk.con_lai += 1
                    continue
                so += 1
                if thu_kho:
                    tk.da_nhap += 1
                    if m.ts < self.moc_ky_uc and de_bat_tu_muc(m):
                        tk.de_bat += 1
                    continue
                sk = self.p.ghi_su_kien(
                    SuKien(loai=f"backfill:{a.ma}:{m.loai}", ts=m.ts or time.time(),
                           tom_tat=m.tom_tat, nguon=f"backfill:{a.ma}",
                           tham_chieu=m.ma_nguon,
                           meta={**m.meta, "sha": m.sha, "vai": m.vai}),
                    noi_dung_day=m.noi_dung_day or "")
                if sk is None:
                    tk.bo_qua += 1
                    tk.ghi_chu.append(f"không ghi được {m.ma_nguon[:60]}: {self.p.loi_cuoi}")
                    continue
                tk.da_nhap += 1
                tk.da_loc += int(sk.da_loc)
                c.execute("INSERT OR REPLACE INTO nhap_khau (nguon, ma_nguon, sha, su_kien_id, ts) "
                          "VALUES (?,?,?,?,?)", (a.ma, m.ma_nguon, m.sha, sk.id, time.time()))
                if m.ts and m.ts < self.moc_ky_uc:
                    if self._de_bat(a, m, sk):
                        tk.de_bat += 1
        except Exception as exc:                            # noqa: BLE001
            tk.ghi_chu.append(f"dừng sớm: {type(exc).__name__}: {exc}"[:200])
        for g in getattr(a, "ghi_chu", None) or []:
            if g not in tk.ghi_chu:
                tk.ghi_chu.append(g)
        tk.giay = time.perf_counter() - t0
        self._ghi_lan(tk)
        return tk

    def _de_bat(self, a: Adapter, m: MucNhap, sk: SuKien) -> bool:
        kq = de_bat_tu_muc(m)
        if kq is None:
            return False
        loai, noi_dung, tieu_de, tin_cay, dau, kq_db = kq
        assert tin_cay is TinCay.BACKFILL, "lịch sử không được mang thẩm quyền sống"
        k = KyUc(loai=loai, noi_dung=noi_dung, tieu_de=tieu_de,
                 quan_trong=6 if loai is LoaiKyUc.DECISION else 5, tin_cay=tin_cay,
                 ts_su_kien=m.ts or sk.ts,
                 the=(loai.value, tin_cay.value, f"backfill:{a.ma}", m.loai),
                 bang_chung=(BangChung(su_kien_id=sk.id, ghi_chu=f"backfill:{a.ma}"),),
                 meta={"dau_hieu": list(dau), "ma_nguon": m.ma_nguon[:200], "vai": m.vai},
                 nguon_loai=f"backfill:{a.ma}", nguon_id=str(sk.id))
        if loai is LoaiKyUc.DECISION:
            return self.p.them_quyet_dinh(k, ly_do=f"lịch sử: {a.ma}", ai="backfill") is not None
        return self.p.luu_ky_uc(k, ai="backfill") is not None

    def _ghi_lan(self, tk: ThongKeNhap) -> None:
        try:
            self.p.kho._c().execute(
                "INSERT INTO nhap_khau_lan (nguon, ts, thu_kho, thong_ke) VALUES (?,?,?,?)",
                (tk.nguon, time.time(), int(tk.thu_kho),
                 json.dumps(tk.to_dict(), ensure_ascii=False)))
        except Exception:                                   # noqa: BLE001
            pass


def adapters_mac_dinh(store, project, *, goc_claude: Optional[Path] = None,
                      loai_tru_phien: Sequence[str] = ()) -> List[Adapter]:
    """Bốn adapter chuẩn cho một dự án của Control Center."""
    return [SoChinhAdapter(store, project.project_id),
            GitAdapter(project.repo_path),
            TaiLieuAdapter(project.repo_path),
            PhienClaudeAdapter(project.repo_path, goc_claude=goc_claude,
                               loai_tru=loai_tru_phien)]
