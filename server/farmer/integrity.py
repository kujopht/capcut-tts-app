"""Toan ven ma chay — farmer tu choi khoi dong neu trinh thong dich ghi duoc.

Neu mot user khac sua duoc trinh thong dich (hoac thu muc chua no), thi moi
bao dam khac cua farmer deu vo nghia: cong quyen, cong danh gia, han muc —
tat ca chi la ma, va ke sua duoc ma thi khong can vuot cong nao ca.

## Bai hoc dat ra module nay: PHAI theo symlink

Ban dau tep nay duoc viet vi mot bao cao (cua chinh phien nay) noi rang
`/opt/fanfic-audio/.venv/bin/python` la `root:root 777` — world-writable.

Do la MOT KET LUAN SAI. `stat` khong theo symlink theo mac dinh, va bon muc
"777" trong `.venv/bin` deu la SYMLINK. Tren Linux, bit quyen cua symlink
**khong duoc dung de kiem soat truy cap** va cung khong doi duoc. Trinh thong
dich that la `/usr/bin/python3.12`, `root:root 755` — dung.

Nen phep kiem o day LUON giai symlink truoc (`os.path.realpath`). Mot phep
kiem khong giai symlink se tai lap dung sai lam do va bao dong gia mai mai.

Va con mot cai bay thu hai, nguy hiem hon bao dong gia: `chmod o-w
.venv/bin/python` se ĐI THEO symlink va sua `/usr/bin/python3.12` — tuc la
doi quyen trinh thong dich CUA CA MAY. "Sua" mot bao dong gia o day co the
lam hong he dieu hanh.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

#: Cho phep bo qua phep kiem — CHI dung tren may lap trinh vien, noi venv
#: thuong thuoc chinh nguoi dung va thu muc co the group-writable mot cach
#: vo hai. Mac dinh BAT.
ENV_SKIP = "FARMER_SKIP_INTEGRITY_CHECK"


@dataclass
class IntegrityReport:
    ok: bool
    interpreter: str
    real_interpreter: str
    problems: List[str] = field(default_factory=list)
    checked: bool = True

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "interpreter": self.interpreter,
            "real_interpreter": self.real_interpreter,
            "problems": list(self.problems),
        }


class InterpreterNotSecure(RuntimeError):
    """Trinh thong dich (hoac duong dan toi no) ghi duoc boi group/other."""


def _writable_by_others(path: Path) -> Optional[str]:
    """Tra ve mo ta van de, hoac None neu on.

    Thu muc co bit STICKY (vd `/tmp` = 1777) duoc chap nhan du co `o+w`: sticky
    nghia la chi chu so huu moi xoa/doi ten duoc muc ben trong, nen no KHONG
    cho phep thay the tep cua nguoi khac. Bo qua chi tiet nay se bao dong gia
    tren bat ky he thong nao dat ma trong `/tmp`.
    """
    try:
        st = path.lstat() if path.is_symlink() else path.stat()
    except OSError as exc:
        return f"khong doc duoc quyen cua {path}: {exc}"

    # Symlink: bit quyen bi Linux BO QUA hoan toan, va khong doi duoc. Kiem no
    # la nguon goc cua bao dong gia — bo qua co chu dich, muc tieu that nam o
    # `realpath` va da duoc kiem rieng.
    if stat.S_ISLNK(st.st_mode):
        return None

    mode = st.st_mode
    if stat.S_ISDIR(mode) and (mode & stat.S_ISVTX):
        return None

    xau = []
    if mode & stat.S_IWGRP:
        xau.append("group")
    if mode & stat.S_IWOTH:
        xau.append("other")
    if xau:
        return f"{path} ghi duoc boi {'+'.join(xau)} (mode {oct(mode & 0o7777)})"
    return None


def check_interpreter(python_path: str = "") -> IntegrityReport:
    """Kiem trinh thong dich dang chay + moi thu muc tren duong toi no."""
    interpreter = python_path or os.sys.executable or ""
    real = os.path.realpath(interpreter) if interpreter else ""

    if os.name != "posix":
        # Bit quyen POSIX khong co y nghia tuong duong tren Windows; bao cao
        # trung thuc la "khong kiem" thay vi mot dau tick gia.
        return IntegrityReport(True, interpreter, real, checked=False)

    if (os.environ.get(ENV_SKIP) or "").strip() == "1":
        return IntegrityReport(True, interpreter, real,
                               problems=["bo qua theo " + ENV_SKIP],
                               checked=False)

    problems: List[str] = []
    if not real or not os.path.exists(real):
        return IntegrityReport(False, interpreter, real,
                               [f"khong tim thay trinh thong dich that: {real!r}"])

    real_path = Path(real)
    van_de = _writable_by_others(real_path)
    if van_de:
        problems.append(van_de)

    # Moi thu muc tren duong toi trinh thong dich THAT: ghi duoc mot thu muc
    # nghia la thay the duoc tep ben trong no.
    for parent in real_path.parents:
        van_de = _writable_by_others(parent)
        if van_de:
            problems.append(van_de)
        if str(parent) == parent.root:
            break

    # Va thu muc chua chinh symlink duoc goi: ghi duoc no nghia la doi huong
    # duoc symlink sang mot binary khac.
    if interpreter and os.path.islink(interpreter):
        van_de = _writable_by_others(Path(interpreter).parent)
        if van_de:
            problems.append(f"thu muc chua symlink: {van_de}")

    return IntegrityReport(not problems, interpreter, real, problems)


def assert_interpreter_secure(python_path: str = "") -> IntegrityReport:
    """Nem `InterpreterNotSecure` neu khong dat. Goi luc KHOI DONG farmer."""
    report = check_interpreter(python_path)
    if not report.ok:
        raise InterpreterNotSecure(
            "trinh thong dich khong an toan, farmer tu choi khoi dong:\n  - "
            + "\n  - ".join(report.problems))
    return report
