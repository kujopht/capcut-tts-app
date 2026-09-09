#!/usr/bin/env python3
"""TÌM/ĐỌC an toàn trong kho — một cửa duy nhất, không cần `cd`, không shell.

VÌ SAO TỆP NÀY TỒN TẠI

Không phải vì `grep` chậm. Vì `grep` **không chứng minh được phạm vi đọc
của chính nó**, và Claude Code phải fail closed khi không chứng minh được.

Hình dạng gây ra chuyện đó:

    cd <kho> && grep -rn "x" .

Người phân tích lệnh của Claude Code coi `grep -r <dir>` là một phép ĐỌC,
nên nó phải đối chiếu `<dir>` với các luật `Read(...)` trong `deny`
(`Read(**/.env)`, `Read(**/*.pem)`, …). Sau một `cd`, thư mục hiệu lực
không suy ra được TĨNH, nên nó không thể chứng minh phép tìm không chạm
vào `.env`. Không chứng minh được thì phải HỎI NGƯỜI — đúng như một lớp an
toàn nên làm.

Cách sửa KHÔNG PHẢI là dặn model "đừng dùng `cd && grep`". Một quy ước dựa
vào việc model ngoan thì không phải một rào. Cách sửa là cho một lệnh mà
phạm vi đọc của nó **đúng theo cấu tạo**:

  * gốc kho suy từ VỊ TRÍ CỦA CHÍNH TỆP NÀY, không từ `cwd` — nên `cd` trở
    thành vô nghĩa, không phải bị cấm;
  * danh sách tệp lấy từ `git ls-files` (đã theo dõi + chưa theo dõi nhưng
    KHÔNG bị `.gitignore` bỏ) — nên mọi thứ `.gitignore` che (`.env`,
    `.venv/`, `.router/`, `dist-*/`, `node_modules/`) không bao giờ vào
    tầm nhìn, kể cả khi không ai nghĩ tới nó;
  * TRÊN nữa còn một danh sách LOẠI TRỪ theo tên (`*.pem`, `id_rsa*`,
    `credentials*`, …) — để một bí mật lỡ được commit vẫn không đọc được
    qua đây;
  * mọi đường dẫn đều `resolve()` rồi kiểm CHỨA TRONG gốc kho — không có
    `../..` nào ra ngoài được;
  * dòng in ra đi qua bộ lọc bí mật, nên ngay cả một tệp được phép cũng
    không in ra thứ trông như credential.

Nhờ vậy MỘT luật tiền tố duy nhất — `Bash(python scripts/tim.py:*)` — an
toàn, và nó không cần một luật `deny` nào đi kèm để bù. So sánh với
`Bash(grep:*)`: luật đó phải kéo theo cả một chùm `deny` (`grep *.env*`,
`grep *.pem`, …) mà vẫn không đóng được lỗ `cd`.

DÙNG

    python scripts/tim.py "TrangThai"
    python scripts/tim.py "def thu" scripts/control_center
    python scripts/tim.py "khoa" --glob "*.py" -i -C 2
    python scripts/tim.py --doc scripts/control_center/store.py --tu 1 --den 60
    python scripts/tim.py --kiem            # tự kiểm: in chính sách loại trừ

Mã thoát theo đúng quy ước `grep`, để nó thay được `grep` trong script:
0 = có khớp, 1 = không khớp, 2 = sai cách dùng / bị từ chối.
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Sequence, Tuple

#: Gốc kho, suy từ VỊ TRÍ TỆP NÀY. Đây là lý do `cd` không còn ảnh hưởng
#: gì: hai lần chạy từ hai `cwd` khác nhau đọc đúng một tập tệp.
GOC = Path(__file__).resolve().parents[1]

#: Mọi chữ đi ra đều qua đây. Console Windows mặc định cp1252, và tệp này
#: in tiếng Việt — cùng loại lỗi đã làm EXE chết ở V0.4 (xem
#: `docs/CONTROL_CENTER.md` mục 14).
RA = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                      errors="replace", line_buffering=True)
LOI = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                       errors="replace", line_buffering=True)

# --------------------------------------------------------------- loại trừ ----

#: TÊN TỆP không bao giờ đọc. Khớp theo `fnmatch` trên TÊN (không phải cả
#: đường), không phân biệt hoa thường.
#:
#: Đây là lớp thứ HAI. Lớp thứ nhất là `.gitignore` (qua `git ls-files
#: --exclude-standard`). Cần cả hai vì chúng hỏng theo hai cách khác nhau:
#: `.gitignore` bỏ sót khi ai đó `git add -f` một bí mật; danh sách tên bỏ
#: sót khi bí mật mang một tên không ai đoán được.
TEN_LOAI_TRU: Sequence[str] = (
    # `env.*` KHONG co o day: no loai luon `env.test.mjs` — mot tep nguon
    # that. Loai tru phai HEP theo hinh dang cua bi mat, khong theo chu
    # "env" xuat hien o dau do trong ten.
    ".env", ".env.*", "*.env",
    "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.ppk",
    "*.asc", "*.gpg", "*.kdbx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials",
    "credentials", "credentials.*", "*credentials.json", "*-credentials.*",
    "rclone.conf", "hosts.yml", "hosts.yaml",
    "Login Data", "Login Data For Account", "Cookies", "Web Data",
    "*.sqlite-wal", "*.sqlite-shm",
    "secrets.*", "*.secrets", "secret.*", "*_secret", "*_secret.*",
    "service-account*.json", "*serviceaccount*.json",
    ".dockercfg", "config.json.enc",
)

#: ĐOẠN ĐƯỜNG DẪN không bao giờ đi vào. Khớp theo tên thư mục, để một
#: `.ssh` nằm sâu trong kho cũng bị loại như `.ssh` ở gốc.
DOAN_LOAI_TRU: Sequence[str] = (
    ".ssh", ".aws", ".azure", ".gnupg", ".wrangler", ".docker", ".kube",
    ".config/gh", "credentials", "secrets", ".git",
)

#: Thứ giống credential — LỌC TRÊN ĐƯỜNG RA, ngay cả với tệp được phép.
#:
#: Tệp này giữ BỘ RIÊNG thay vì `import` từ `router_v3.packet`, và đó là
#: có chủ đích: `tim.py` phải chạy được khi các gói của kho đang hỏng (đó
#: chính là lúc người ta cần tìm nhất). Đổi lại, có bài kiểm đòi bộ này
#: PHỦ bộ của `packet._MAU_BI_MAT` — nên hai chỗ không thể lệch nhau lặng
#: lẽ.
MAU_BI_MAT: Sequence[re.Pattern] = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bstandard_[A-Za-z0-9]{40,}"),
    re.compile(r"\brnd_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\."),
    # Thêm so voi `packet`: nhung thu mot lop KY UC/TIM se gap.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{15,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    re.compile(r"(?i)\b(?:pass(?:word)?|passwd|secret|token|api[_-]?key)"
               r"\s*[:=]\s*['\"]?[^\s'\"#]{8,}"),
    re.compile(r"(?i)://[^/\s:@]+:[^/\s@]{4,}@"),
)

DA_LOC = "[DA-LOC]"

#: Trần MỘT tệp. Vượt thì bỏ qua và đếm — một tệp 200 MB trong kho không
#: được làm phép tìm treo.
TRAN_TEP = 4 * 1024 * 1024

#: Trần số dòng in ra, để một mẫu quá rộng không đổ nghìn dòng vào ngữ cảnh.
TRAN_DONG = 200


def loc(van: str) -> str:
    ra = van
    for mau in MAU_BI_MAT:
        ra = mau.sub(DA_LOC, ra)
    return ra


def bi_loai_tru(rel: PurePosixPath) -> str:
    """Lý do loại trừ, hoặc `""` nếu được đọc."""
    ten = rel.name
    for m in TEN_LOAI_TRU:
        if fnmatch.fnmatch(ten.lower(), m.lower()):
            return f"tên khớp mẫu loại trừ {m!r}"
    doan = {p.lower() for p in rel.parts[:-1]}
    for d in DOAN_LOAI_TRU:
        if "/" in d:
            if d.lower() in str(rel).lower():
                return f"đường dẫn chứa {d!r}"
        elif d.lower() in doan:
            return f"đường dẫn đi qua thư mục {d!r}"
    return ""


# ----------------------------------------------------------------- phạm vi ----

class BiTuChoi(RuntimeError):
    """Yêu cầu ra ngoài phạm vi. Luôn kèm lý do đọc được."""


def trong_kho(p: Path) -> Path:
    """`resolve()` rồi ĐÒI nằm trong `GOC`. Ném nếu không.

    Kiểm SAU `resolve()`, không trước: `scripts/../../..` chỉ lộ ra là ở
    ngoài sau khi đã rút gọn. Đây đúng cùng một phép kiểm mà
    `attachments.py::_kiem_trong_kho` làm cho tệp đính kèm.
    """
    q = Path(p).resolve()
    try:
        q.relative_to(GOC)
    except ValueError:
        raise BiTuChoi(f"ngoài kho: {q} (kho là {GOC})") from None
    return q


def _giai_pathspec(ds: Sequence[str]) -> List[PurePosixPath]:
    """Đường người dùng đưa -> đường TƯƠNG ĐỐI so với gốc kho.

    Giải theo GỐC KHO, không theo `cwd`. Nhờ vậy `python scripts/tim.py x
    scripts/tests` cho cùng kết quả dù chạy từ đâu — và đó là cả điểm của
    tệp này.
    """
    ra: List[PurePosixPath] = []
    for s in ds:
        p = Path(s)
        tuyet = trong_kho(p if p.is_absolute() else GOC / p)
        ra.append(PurePosixPath(tuyet.relative_to(GOC).as_posix()))
    return ra


def _duoi_pathspec(rel: PurePosixPath,
                   pathspec: Sequence[PurePosixPath]) -> bool:
    if not pathspec:
        return True
    for ps in pathspec:
        if rel == ps or str(rel).startswith(str(ps) + "/"):
            return True
    return False


# ------------------------------------------------------------- danh sách tệp ----

def _git(*args: str) -> Tuple[int, str]:
    """Chạy `git` ở gốc kho, cửa sổ ẩn (luật V0.4)."""
    kw = {}
    if os.name == "nt":                                 # pragma: no cover
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                              # SW_HIDE
        kw = {"creationflags": 0x08000000, "startupinfo": si}
    try:
        p = subprocess.run(("git",) + args, cwd=str(GOC),
                           capture_output=True, timeout=120, **kw)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return p.returncode, p.stdout.decode("utf-8", "replace")


def liet_ke() -> Tuple[List[PurePosixPath], str]:
    """Tệp ĐƯỢC PHÉP nhìn thấy, và nguồn của danh sách.

    `git ls-files --cached --others --exclude-standard`: đã theo dõi CỘNG
    chưa theo dõi nhưng không bị `.gitignore` bỏ. Chính `--exclude-standard`
    là thứ làm phép loại trừ bí mật đúng THEO CẤU TẠO ở kho này — `.env`,
    `.venv/`, `.router/`, `dist-*/` đều đã nằm trong `.gitignore`.

    Không có git thì rơi về đi bộ cây thư mục KÈM danh sách bỏ qua thủ
    công. Rơi về chứ không tắt: một kho vừa `git init` hỏng cũng phải tìm
    được, và lớp loại trừ theo tên vẫn còn nguyên ở trên.
    """
    ma, ra = _git("ls-files", "-z", "--cached", "--others",
                  "--exclude-standard")
    if ma == 0:
        ds = [PurePosixPath(x) for x in ra.split("\0") if x]
        return ds, "git ls-files (--exclude-standard)"
    BO_QUA = {".git", ".venv", "venv", "node_modules", "__pycache__",
              ".router", "build", ".pytest_cache", ".mypy_cache",
              ".ruff_cache", ".idea", ".vs"}
    ds = []
    for goc, thu_muc, tep in os.walk(GOC):
        thu_muc[:] = [d for d in thu_muc
                      if d not in BO_QUA and not d.startswith("dist-")
                      and d != "dist"]
        for t in tep:
            rel = Path(goc, t).relative_to(GOC).as_posix()
            ds.append(PurePosixPath(rel))
    return ds, "đi bộ cây thư mục (không có git)"


def _nhi_phan(dau: bytes) -> bool:
    return b"\0" in dau


# -------------------------------------------------------------------- tìm ----

def tim(mau: str, *, pathspec: Sequence[str] = (), glob: Sequence[str] = (),
        khong_phan_biet: bool = False, chi_ten: bool = False,
        quanh: int = 0, gioi_han: int = TRAN_DONG) -> int:
    try:
        ps = _giai_pathspec(pathspec)
    except BiTuChoi as exc:
        LOI.write(f"TỪ CHỐI: {exc}\n")
        return 2
    try:
        re_mau = re.compile(mau, re.IGNORECASE if khong_phan_biet else 0)
    except re.error as exc:
        LOI.write(f"mẫu không hợp lệ: {exc}\n")
        return 2

    ds, nguon = liet_ke()
    dem_khop = dem_tep = bo_bi_mat = bo_lon = bo_nhi_phan = 0
    dong_ra = 0
    for rel in sorted(ds):
        if not _duoi_pathspec(rel, ps):
            continue
        if glob and not any(fnmatch.fnmatch(rel.name, g)
                            or fnmatch.fnmatch(str(rel), g) for g in glob):
            continue
        if bi_loai_tru(rel):
            bo_bi_mat += 1
            continue
        try:
            tuyet = trong_kho(GOC / rel)
        except BiTuChoi:
            bo_bi_mat += 1
            continue
        try:
            if tuyet.stat().st_size > TRAN_TEP:
                bo_lon += 1
                continue
            du = tuyet.read_bytes()
        except OSError:
            continue
        if _nhi_phan(du[:8192]):
            bo_nhi_phan += 1
            continue
        dong = du.decode("utf-8", "replace").splitlines()
        khop = [i for i, d in enumerate(dong) if re_mau.search(d)]
        if not khop:
            continue
        dem_tep += 1
        dem_khop += len(khop)
        if chi_ten:
            RA.write(f"{rel}\n")
            dong_ra += 1
        else:
            da_in = set()
            for i in khop:
                lo, hi = max(0, i - quanh), min(len(dong), i + quanh + 1)
                for j in range(lo, hi):
                    if j in da_in:
                        continue
                    da_in.add(j)
                    dau = ":" if j == i else "-"
                    RA.write(f"{rel}{dau}{j + 1}{dau}"
                             f"{loc(dong[j])[:400]}\n")
                    dong_ra += 1
                    if dong_ra >= gioi_han:
                        break
                if dong_ra >= gioi_han:
                    break
        if dong_ra >= gioi_han:
            RA.write(f"... dừng ở {gioi_han} dòng (dùng --gioi-han để nới)\n")
            break
    RA.write(f"# {dem_khop} khớp / {dem_tep} tệp · nguồn danh sách: {nguon}"
             f" · bỏ qua: {bo_bi_mat} loại-trừ, {bo_lon} quá-lớn,"
             f" {bo_nhi_phan} nhị-phân\n")
    return 0 if dem_khop else 1


# -------------------------------------------------------------------- đọc ----

def doc(duong: str, *, tu: int = 1, den: int = 0) -> int:
    """Đọc một tệp trong kho — thay `sed -n 'a,bp'`, cùng phép kiểm."""
    try:
        rel_p = Path(duong)
        tuyet = trong_kho(rel_p if rel_p.is_absolute() else GOC / rel_p)
    except BiTuChoi as exc:
        LOI.write(f"TỪ CHỐI: {exc}\n")
        return 2
    rel = PurePosixPath(tuyet.relative_to(GOC).as_posix())
    ly_do = bi_loai_tru(rel)
    if ly_do:
        LOI.write(f"TỪ CHỐI: {rel} — {ly_do}\n")
        return 2
    if not tuyet.is_file():
        LOI.write(f"không phải tệp: {rel}\n")
        return 2
    if tuyet.stat().st_size > TRAN_TEP:
        LOI.write(f"tệp quá lớn (> {TRAN_TEP} byte): {rel}\n")
        return 2
    du = tuyet.read_bytes()
    if _nhi_phan(du[:8192]):
        LOI.write(f"tệp nhị phân: {rel}\n")
        return 2
    dong = du.decode("utf-8", "replace").splitlines()
    a = max(1, tu)
    b = len(dong) if den <= 0 else min(len(dong), den)
    for i in range(a - 1, b):
        RA.write(f"{i + 1}\t{loc(dong[i])}\n")
    return 0


# ------------------------------------------------------------------ tự kiểm ----

def kiem() -> int:
    """In chính sách — để người (và bài kiểm) đọc được điều tệp này hứa."""
    ds, nguon = liet_ke()
    bo = [r for r in ds if bi_loai_tru(r)]
    RA.write(f"gốc kho          : {GOC}\n")
    RA.write(f"cwd hiện tại     : {Path.cwd()}  (KHÔNG ảnh hưởng kết quả)\n")
    RA.write(f"nguồn danh sách  : {nguon}\n")
    RA.write(f"tệp nhìn thấy    : {len(ds) - len(bo)}\n")
    RA.write(f"tệp bị loại trừ  : {len(bo)}\n")
    for r in bo[:20]:
        RA.write(f"   - {r}  ({bi_loai_tru(r)})\n")
    RA.write(f"mẫu tên loại trừ : {len(TEN_LOAI_TRU)}\n")
    RA.write(f"đoạn đường loại trừ: {len(DOAN_LOAI_TRU)}\n")
    RA.write(f"mẫu lọc bí mật   : {len(MAU_BI_MAT)}\n")
    RA.write("ra ngoài kho     : KHÔNG THỂ (resolve() + kiểm chứa trong)\n")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tim.py", add_help=True,
        description="Tìm/đọc an toàn trong kho — không cần cd, không shell.")
    ap.add_argument("mau", nargs="?", default="", help="mẫu regex")
    ap.add_argument("pathspec", nargs="*", help="giới hạn trong đường này")
    ap.add_argument("-i", "--khong-phan-biet", action="store_true")
    ap.add_argument("-l", "--chi-ten", action="store_true")
    ap.add_argument("-C", "--quanh", type=int, default=0)
    ap.add_argument("--glob", action="append", default=[])
    ap.add_argument("--gioi-han", type=int, default=TRAN_DONG)
    ap.add_argument("--doc", default="", help="đọc một tệp thay vì tìm")
    ap.add_argument("--tu", type=int, default=1)
    ap.add_argument("--den", type=int, default=0)
    ap.add_argument("--kiem", action="store_true", help="tự kiểm chính sách")
    a = ap.parse_args(list(argv) if argv is not None else None)

    if a.kiem:
        return kiem()
    if a.doc:
        return doc(a.doc, tu=a.tu, den=a.den)
    if not a.mau:
        ap.print_usage(LOI)
        LOI.write("thiếu mẫu tìm (hoặc dùng --doc / --kiem)\n")
        return 2
    return tim(a.mau, pathspec=a.pathspec, glob=a.glob,
               khong_phan_biet=a.khong_phan_biet, chi_ten=a.chi_ten,
               quanh=a.quanh, gioi_han=a.gioi_han)


if __name__ == "__main__":
    raise SystemExit(main())
